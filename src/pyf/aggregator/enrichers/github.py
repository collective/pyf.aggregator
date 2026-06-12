from argparse import ArgumentParser
from datetime import datetime
from dotenv import load_dotenv
from pyf.aggregator.db import TypesenceConnection, TypesensePackagesCollection
from pyf.aggregator.logger import logger
from pprint import pprint
from github import Github
from github import RateLimitExceededException
from github import UnknownObjectException

import functools
import json
import re
import time
import os

import typesense.exceptions

load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
# GitHub API rate limits: 5000 req/hour authenticated (~1.4/sec), 60/hour unauthenticated
# Default 0.75s delay = ~1.3 req/sec, staying just under the authenticated limit
GITHUB_REQUEST_DELAY = float(os.getenv("GITHUB_REQUEST_DELAY", 0.75))


def add_subcommand_args(parser):
    """Add github-specific arguments to a subparser."""
    from pyf.aggregator.cli_utils import add_common_args

    add_common_args(parser)
    parser.add_argument(
        "-n",
        "--name",
        help="Single package name to enrich (enriches only this package)",
        type=str,
    )
    parser.add_argument(
        "-v",
        "--verbose",
        help="Show raw data from Typesense (PyPI) and GitHub API",
        action="store_true",
    )
    parser.add_argument(
        "--report-dir",
        help="Directory for the github_problems.{json,md} reports (default: current directory)",
        type=str,
        default=".",
    )


# Regex patterns for extracting GitHub repository from various URL formats
# Standard HTTPS/HTTP URLs
github_regex = re.compile(r"^(http[s]{0,1}:\/\/|www\.)github\.com/(.+/.+)")
# Git protocol URLs (git://github.com/owner/repo.git)
github_git_regex = re.compile(r"^git:\/\/github\.com/([^/]+/[^/]+?)(?:\.git)?$")
# Git+HTTPS URLs (git+https://github.com/owner/repo.git)
github_git_https_regex = re.compile(
    r"^git\+https:\/\/github\.com/([^/]+/[^/]+?)(?:\.git)?$"
)
# Git+SSH URLs (git+ssh://git@github.com/owner/repo.git)
github_git_ssh_regex = re.compile(
    r"^git\+ssh:\/\/git@github\.com[:/]([^/]+/[^/]+?)(?:\.git)?$"
)
# SSH URLs (git@github.com:owner/repo.git)
github_ssh_regex = re.compile(r"^git@github\.com[:/]([^/]+/[^/]+?)(?:\.git)?$")

# GitHub paths that look like "owner/repo" but are not real repositories.
GITHUB_RESERVED_OWNERS = {
    "about",
    "apps",
    "collections",
    "marketplace",
    "orgs",
    "settings",
    "sponsors",
    "topics",
}

# A valid GitHub owner or repository name (GitHub allows letters, digits, ".", "_", "-").
_repo_name_part = re.compile(r"^[A-Za-z0-9._-]+$")

# Human-readable labels for the reasons a repository could not be enriched.
PROBLEM_REASON_LABELS = {
    "no_repo_url": "No GitHub URL in package metadata",
    "malformed_identifier": "Malformed repository identifier",
    "not_found": "Repository not found (404)",
}


def clean_repo_identifier(repo_identifier):
    """Strip URL fragments/query strings captured into a repo identifier.

    e.g. "collective/collective-rercaptcha#readme" -> "collective/collective-rercaptcha"
    """
    if not repo_identifier:
        return repo_identifier
    return repo_identifier.split("#")[0].split("?")[0]


def is_valid_repo_identifier(repo_identifier):
    """Return True if ``repo_identifier`` looks like a real "owner/repo"."""
    if not repo_identifier:
        return False
    parts = repo_identifier.split("/")
    if len(parts) != 2:
        return False
    owner, repo = parts
    if not owner or not repo:
        return False
    if owner.lower() in GITHUB_RESERVED_OWNERS:
        return False
    return bool(_repo_name_part.match(owner) and _repo_name_part.match(repo))


GH_KEYS_MAP = {
    "stars": "stargazers_count",
    "open_issues": "open_issues",
    "is_archived": "archived",
    "watchers": "subscribers_count",
    "updated": "updated_at",
    "gh_url": "html_url",
}


def memoize(obj):
    """Decorator for memoizing the return value."""
    cache = obj.cache = {}

    @functools.wraps(obj)
    def memoizer(*args, **kwargs):
        key = args[1]
        if key not in cache:
            cache[key] = obj(*args, **kwargs)
        return cache[key]

    return memoizer


class Enricher(TypesenceConnection, TypesensePackagesCollection):
    """
    Enrich pyf data with data from Github
    """

    def __init__(self):
        super().__init__()
        self._last_github_request = 0

    def _apply_github_rate_limit(self):
        """Apply rate limiting delay between GitHub API requests."""
        elapsed = time.time() - self._last_github_request
        if elapsed < GITHUB_REQUEST_DELAY:
            sleep_time = GITHUB_REQUEST_DELAY - elapsed
            time.sleep(sleep_time)
        self._last_github_request = time.time()

    def run(self, target=None, package_name=None, verbose=False, report_dir="."):
        self.problems = []
        self._report_dir = report_dir
        search_parameters = {
            "q": "*",
            "query_by": "name",
            "group_by": "name_sortable",
            "group_limit": 1,
            "per_page": 50,
            "sort_by": "upload_timestamp:desc",
        }
        if package_name:
            search_parameters["filter_by"] = f"name:={package_name}"
            logger.info(f"Filtering for single package: {package_name}")

        results = self.ts_search(target, search_parameters)

        per_page = results["request_params"]["per_page"]
        found = results["found"]

        if package_name and found == 0:
            logger.error(f"Package '{package_name}' not found in collection '{target}'")
            return

        logger.info(
            f"[{datetime.now()}][found {found}] Start enriching data from github..."
        )
        enrich_counter = 0
        page = 0
        try:
            for p in range(0, found, per_page):
                page += 1
                results = self.ts_search(target, search_parameters, page)
                for group in results["grouped_hits"]:
                    for item in group["hits"]:
                        data = item["document"]

                        if verbose:
                            print(f"\n{'=' * 60}")
                            print(f"=== Processing package: {data.get('name')} ===")
                            print(f"{'=' * 60}")
                            print("\n--- Typesense Document (PyPI data) ---")
                            pprint(data)

                        package_repo_identifier = self.get_package_repo_identifier(data)
                        if not package_repo_identifier:
                            self._record_problem(data, None, "no_repo_url")
                            if verbose:
                                print("\n--- No GitHub repository found ---")
                            continue

                        if not is_valid_repo_identifier(package_repo_identifier):
                            self._record_problem(
                                data, package_repo_identifier, "malformed_identifier"
                            )
                            logger.warning(
                                f"Malformed GitHub identifier for package "
                                f"'{data.get('name')}': {package_repo_identifier}"
                            )
                            if verbose:
                                print(
                                    f"\n--- Malformed GitHub identifier: "
                                    f"{package_repo_identifier} ---"
                                )
                            continue

                        if verbose:
                            print(
                                f"\n--- GitHub Repository: "
                                f"{package_repo_identifier} ---"
                            )

                        gh_data = self._get_github_data(
                            package_repo_identifier, verbose=verbose
                        )
                        if not gh_data:
                            # The chosen version's repo URL 404s. Other versions
                            # of the same package may carry a different, still
                            # working link (e.g. the repo was renamed or moved
                            # between releases). Fall back to the newest version
                            # whose link actually resolves.
                            fallback_identifier, gh_data = (
                                self._find_working_repo_in_versions(
                                    target,
                                    data.get("name"),
                                    tried={package_repo_identifier},
                                    verbose=verbose,
                                )
                            )
                            if gh_data:
                                logger.info(
                                    f"GitHub repository '{package_repo_identifier}' "
                                    f"not found for package '{data.get('name')}'; "
                                    f"falling back to '{fallback_identifier}' from "
                                    f"another version"
                                )
                                package_repo_identifier = fallback_identifier
                            else:
                                self._record_problem(
                                    data, package_repo_identifier, "not_found"
                                )
                                logger.warning(
                                    f"GitHub repository not found for package "
                                    f"'{data.get('name')}': {package_repo_identifier}"
                                )
                                if verbose:
                                    print("--- No GitHub data available ---")
                                continue

                        if verbose:
                            print("\n--- Enrichment Result ---")
                            pprint(
                                {
                                    "github_stars": gh_data["github"]["stars"],
                                    "github_watchers": gh_data["github"]["watchers"],
                                    "github_updated": gh_data["github"]["updated"],
                                    "github_open_issues": gh_data["github"][
                                        "open_issues"
                                    ],
                                    "github_url": gh_data["github"]["gh_url"],
                                }
                            )

                        enrich_counter += 1
                        self.update_doc(
                            target, data["id"], gh_data, page, enrich_counter
                        )
        finally:
            # Always flush whatever problems were collected, even if the run is
            # interrupted (exception, KeyboardInterrupt) part-way through. The
            # report is also written incrementally as each problem is recorded,
            # so it survives a hard kill of the process.
            self._write_problem_report(report_dir)
            if self.problems:
                logger.info(
                    f"Wrote {len(self.problems)} problematic repositories to "
                    f"{os.path.abspath(os.path.join(report_dir, 'github_problems.json'))}"
                    f" and "
                    f"{os.path.abspath(os.path.join(report_dir, 'github_problems.md'))}"
                )
        logger.info(f"[{datetime.now()}] done")

    @staticmethod
    def _candidate_urls(data):
        """Return the non-empty URLs considered when looking for a GitHub repo."""
        urls = {
            "home_page": data.get("home_page"),
            "project_url": data.get("project_url"),
            "url": data.get("url"),
            "repository_url": data.get("repository_url"),
        }
        for key, value in (data.get("project_urls") or {}).items():
            urls[f"project_urls.{key}"] = value
        return {key: value for key, value in urls.items() if value}

    def _record_problem(self, data, repo_identifier, reason):
        """Collect a package whose GitHub repo could not be enriched.

        The report is flushed to disk immediately so it becomes visible right
        after the first problem is found, rather than only when the (long) run
        completes.
        """
        self.problems.append(
            {
                "name": data.get("name"),
                "repo_identifier": repo_identifier,
                "reason": reason,
                "urls": self._candidate_urls(data),
            }
        )
        self._write_problem_report(getattr(self, "_report_dir", "."))

    def _write_problem_report(self, report_dir="."):
        """Write the collected problems to JSON and Markdown report files."""
        if not self.problems:
            return

        json_path = os.path.join(report_dir, "github_problems.json")
        md_path = os.path.join(report_dir, "github_problems.md")

        with open(json_path, "w") as fh:
            json.dump(
                {"count": len(self.problems), "problems": self.problems},
                fh,
                indent=2,
                sort_keys=True,
            )

        with open(md_path, "w") as fh:
            fh.write(self._render_problem_markdown())

    def _render_problem_markdown(self):
        """Render the collected problems as a Markdown report grouped by reason."""
        grouped = {}
        for problem in self.problems:
            grouped.setdefault(problem["reason"], []).append(problem)

        lines = [
            "# Problematic GitHub Repositories",
            "",
            f"Total: {len(self.problems)}",
            "",
        ]
        for reason in PROBLEM_REASON_LABELS:
            entries = grouped.get(reason)
            if not entries:
                continue
            lines.append(f"## {PROBLEM_REASON_LABELS[reason]} ({len(entries)})")
            lines.append("")
            lines.append("| Package | Repo identifier | URLs |")
            lines.append("| --- | --- | --- |")
            for entry in sorted(entries, key=lambda e: e["name"] or ""):
                urls = "<br>".join(
                    f"{key}: {value}" for key, value in entry["urls"].items()
                )
                lines.append(
                    f"| {entry['name']} | {entry['repo_identifier'] or ''} | {urls} |"
                )
            lines.append("")
        return "\n".join(lines)

    def update_doc(self, target, id, data, page, enrich_counter):
        document = {
            "github_stars": data["github"]["stars"],
            "github_watchers": data["github"]["watchers"],
            "github_updated": data["github"]["updated"].timestamp(),
            "github_open_issues": data["github"]["open_issues"],
            "github_url": data["github"]["gh_url"],
        }

        # Include contributors if available
        if data["github"].get("contributors"):
            document["contributors"] = data["github"]["contributors"]

        try:
            self.client.collections[target].documents[id].update(document)
            logger.info(f"[{page}/{enrich_counter}] Updated document {id}")
        except typesense.exceptions.ObjectNotFound:
            logger.warning(
                f"[{page}/{enrich_counter}] Document {id} not found, skipping update"
            )

    def ts_search(self, target, search_parameters, page=1):
        search_parameters["page"] = page
        return self.client.collections[target].documents.search(search_parameters)

    def _version_repo_identifiers(self, target, package_name):
        """Yield distinct, valid GitHub identifiers across all versions of a
        package, newest version first.

        Different releases of the same package may point at different repository
        URLs (e.g. the repo was renamed or moved between releases). Walking every
        version lets a release with a still-working link serve as a fallback.
        """
        seen = set()
        search_parameters = {
            "q": "*",
            "query_by": "name",
            "filter_by": f"name:={package_name}",
            "sort_by": "upload_timestamp:desc",
            "per_page": 100,
        }
        page = 1
        while True:
            results = self.ts_search(target, search_parameters, page)
            hits = results.get("hits") or []
            if not hits:
                break
            for hit in hits:
                identifier = self.get_package_repo_identifier(hit["document"])
                if (
                    identifier
                    and is_valid_repo_identifier(identifier)
                    and identifier not in seen
                ):
                    seen.add(identifier)
                    yield identifier
            if len(hits) < search_parameters["per_page"]:
                break
            page += 1

    def _find_working_repo_in_versions(
        self, target, package_name, tried, verbose=False
    ):
        """Return ``(identifier, github_data)`` for the newest version whose
        GitHub repository resolves, skipping identifiers already in ``tried``.

        Returns ``(None, {})`` when no other version points at a resolvable repo.
        """
        if not package_name:
            return None, {}
        for identifier in self._version_repo_identifiers(target, package_name):
            if identifier in tried:
                continue
            tried.add(identifier)
            gh_data = self._get_github_data(identifier, verbose=verbose)
            if gh_data:
                return identifier, gh_data
        return None, {}

    def get_package_repo_identifier(self, data):
        # Collect all potential URLs including npm-specific repository_url
        urls = [
            data.get("home_page"),
            data.get("project_url"),
            data.get("url"),
            data.get("repository_url"),  # npm packages often have this
        ] + list((data.get("project_urls") or {}).values())

        for url in urls:
            if not url:
                continue

            # Try standard HTTPS/HTTP URL first
            match = github_regex.match(url)
            if match:
                repo_identifier_parts = match.groups()[-1].split("/")
                repo_identifier = "/".join(repo_identifier_parts[0:2])
                return clean_repo_identifier(repo_identifier)

            # Try git:// URL (common in npm packages)
            match = github_git_regex.match(url)
            if match:
                return clean_repo_identifier(match.group(1))

            # Try git+https:// URL (common in npm packages)
            match = github_git_https_regex.match(url)
            if match:
                return clean_repo_identifier(match.group(1))

            # Try git+ssh:// URL
            match = github_git_ssh_regex.match(url)
            if match:
                return clean_repo_identifier(match.group(1))

            # Try git@github.com: URL (SSH format)
            match = github_ssh_regex.match(url)
            if match:
                return clean_repo_identifier(match.group(1))

        logger.info(f"no github url repository found for {data.get('name')}")
        return None

    def _get_top_contributors(self, repo, limit=5):
        """Get top N contributors from a GitHub repository.

        Args:
            repo: PyGithub Repository object
            limit: Maximum number of contributors to return (default: 5)

        Returns:
            List of dicts with username, avatar_url, and contributions count
        """
        try:
            contributors = []
            for contributor in repo.get_contributors():
                contributors.append(
                    {
                        "username": contributor.login,
                        "avatar_url": contributor.avatar_url,
                        "contributions": contributor.contributions,
                    }
                )
                if len(contributors) >= limit:
                    break
            return contributors
        except Exception as e:
            logger.warning(f"Failed to fetch contributors for {repo.full_name}: {e}")
            return []

    @memoize
    def _get_github_data(self, repo_identifier, verbose=False):
        """Return stats from a given Github repository (e.g. Owner/repo)."""
        # Apply rate limiting before making request
        self._apply_github_rate_limit()
        github = Github(GITHUB_TOKEN or None)
        while True:
            try:
                repo = github.get_repo(repo_identifier)
            except UnknownObjectException:
                logger.warning(
                    f"GitHub API 404: repository '{repo_identifier}' not found"
                )
                if verbose:
                    print(f"GitHub repository not found: {repo_identifier}")
                return {}
            except RateLimitExceededException:
                reset_time = github.rate_limiting_resettime
                delta = reset_time - time.time()
                logger.info(
                    "Waiting until {} (UTC) reset time to perform more Github requests.".format(
                        datetime.fromtimestamp(reset_time, tz=None).strftime(
                            "%Y-%m-%d %H:%M:%S"
                        )
                    )
                )
                time.sleep(delta)
            else:
                if verbose:
                    print("Raw GitHub API data:")
                    raw_data = {
                        "stargazers_count": repo.stargazers_count,
                        "subscribers_count": repo.subscribers_count,
                        "open_issues": repo.open_issues,
                        "archived": repo.archived,
                        "updated_at": str(repo.updated_at),
                        "html_url": repo.html_url,
                        "full_name": repo.full_name,
                        "description": repo.description,
                        "forks_count": repo.forks_count,
                        "language": repo.language,
                        "default_branch": repo.default_branch,
                    }
                    pprint(raw_data)

                data = {"github": {}}
                for key, key_github in GH_KEYS_MAP.items():
                    data["github"][key] = getattr(repo, key_github)

                # Fetch top contributors
                contributors = self._get_top_contributors(repo)
                data["github"]["contributors"] = contributors

                if verbose and contributors:
                    print("Top contributors:")
                    pprint(contributors)

                return data


def run_command(args):
    """Run the GitHub enrichment with pre-parsed args."""
    from pyf.aggregator.cli_utils import resolve_profile_and_target

    resolve_profile_and_target(args)

    enricher = Enricher()
    enricher.run(
        target=args.target,
        package_name=args.name,
        verbose=args.verbose,
        report_dir=getattr(args, "report_dir", "."),
    )


def main():
    from pyf.aggregator.cli_utils import add_common_args

    parser = ArgumentParser(
        description="Enrich indexed packages with GitHub data (stars, watchers, issues, contributors)"
    )
    add_common_args(parser)
    parser.add_argument(
        "-n",
        "--name",
        help="Single package name to enrich (enriches only this package)",
        type=str,
    )
    parser.add_argument(
        "-v",
        "--verbose",
        help="Show raw data from Typesense (PyPI) and GitHub API",
        action="store_true",
    )
    parser.add_argument(
        "--report-dir",
        help="Directory for the github_problems.{json,md} reports (default: current directory)",
        type=str,
        default=".",
    )
    args = parser.parse_args()
    run_command(args)
