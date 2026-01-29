from dotenv import load_dotenv
from argparse import ArgumentParser
from datetime import datetime
from pyf.aggregator.db import TypesenceConnection, TypesensePackagesCollection
from pyf.aggregator.logger import logger
from pyf.aggregator.profiles import ProfileManager
from pprint import pprint
from github import Github
from github import RateLimitExceededException
from github import UnknownObjectException
from pyf.aggregator.logger import logger

import functools
import re
import sys
import time
import os

load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
DEFAULT_PROFILE = os.getenv("DEFAULT_PROFILE")
# GitHub API rate limits: 5000 req/hour authenticated (~1.4/sec), 60/hour unauthenticated
# Default 0.75s delay = ~1.3 req/sec, staying just under the authenticated limit
GITHUB_REQUEST_DELAY = float(os.getenv("GITHUB_REQUEST_DELAY", 0.75))

parser = ArgumentParser(
    description="updates/migrates typesense collections and export/import documents"
)
parser.add_argument("-t", "--target", nargs="?", type=str)
parser.add_argument(
    "-p", "--profile",
    help="Profile name for classifier filtering (overrides DEFAULT_PROFILE env var)",
    nargs="?",
    type=str
)
parser.add_argument(
    "-n", "--name",
    help="Single package name to enrich (enriches only this package)",
    type=str
)
parser.add_argument(
    "-v", "--verbose",
    help="Show raw data from Typesense (PyPI) and GitHub API",
    action="store_true"
)

github_regex = re.compile(r"^(http[s]{0,1}:\/\/|www\.)github\.com/(.+/.+)")

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

    def run(self, target=None, package_name=None, verbose=False):
        search_parameters = {
            "q": "*",
            "query_by": "name",
            "group_by": "name_sortable",
            "group_limit": 1,
            "per_page": 50,
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

        logger.info(f"[{datetime.now()}][found {found}] Start enriching data from github...")
        enrich_counter = 0
        page = 0
        for p in range(0, found, per_page):
            page +=1
            results = self.ts_search(target, search_parameters, page)
            for group in results["grouped_hits"]:
                for item in group["hits"]:
                    data = item["document"]

                    if verbose:
                        print(f"\n{'='*60}")
                        print(f"=== Processing package: {data.get('name')} ===")
                        print(f"{'='*60}")
                        print("\n--- Typesense Document (PyPI data) ---")
                        pprint(data)

                    package_repo_identifier = self.get_package_repo_identifier(data)
                    if not package_repo_identifier:
                        if verbose:
                            print("\n--- No GitHub repository found ---")
                        continue

                    if verbose:
                        print(f"\n--- GitHub Repository: {package_repo_identifier} ---")

                    gh_data = self._get_github_data(package_repo_identifier, verbose=verbose)
                    if not gh_data:
                        logger.warning(
                            f"GitHub repository not found for package '{data.get('name')}': "
                            f"{package_repo_identifier}"
                        )
                        if verbose:
                            print("--- No GitHub data available ---")
                        continue

                    if verbose:
                        print("\n--- Enrichment Result ---")
                        pprint({
                            'github_stars': gh_data["github"]["stars"],
                            'github_watchers': gh_data["github"]["watchers"],
                            'github_updated': gh_data["github"]["updated"],
                            'github_open_issues': gh_data["github"]["open_issues"],
                            'github_url': gh_data["github"]["gh_url"],
                        })

                    enrich_counter +=1
                    self.update_doc(target, data['id'], gh_data, page, enrich_counter)
        logger.info(f"[{datetime.now()}] done")

    def update_doc(self, target, id, data, page, enrich_counter):
        document = {
            'github_stars': data["github"]["stars"],
            'github_watchers': data["github"]["watchers"],
            'github_updated': data["github"]["updated"].timestamp(),
            'github_open_issues': data["github"]["open_issues"],
            'github_url': data["github"]["gh_url"],
        }

        # Include contributors if available
        if data["github"].get("contributors"):
            document['contributors'] = data["github"]["contributors"]

        doc = self.client.collections[target].documents[id].update(document)
        logger.info(f"[{page}/{enrich_counter}] Updated document {id}")

    def ts_search(self, target, search_parameters, page=1):
        search_parameters['page'] = page
        return self.client.collections[target].documents.search(search_parameters)

    def get_package_repo_identifier(self, data):
        urls = [data.get("home_page"), data.get("project_url"), data.get("url")] + list(
            (data.get("project_urls") or {}).values()
        )
        for url in urls:
            if not url:
                continue
            match = github_regex.match(url)
            if match:
                repo_identifier_parts = match.groups()[-1].split("/")
                repo_identifier = "/".join(repo_identifier_parts[0:2])
                return repo_identifier
        else:
            logger.info(f"no github url repository found for {data.get('name')}")
            return

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
                contributors.append({
                    "username": contributor.login,
                    "avatar_url": contributor.avatar_url,
                    "contributions": contributor.contributions,
                })
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
                logger.warning(f"GitHub API 404: repository '{repo_identifier}' not found")
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


def main():
    args = parser.parse_args()

    # Handle profile (CLI argument or DEFAULT_PROFILE env var)
    effective_profile = args.profile or DEFAULT_PROFILE
    profile_source = "from CLI" if args.profile else "from DEFAULT_PROFILE"

    if effective_profile:
        profile_manager = ProfileManager()
        profile = profile_manager.get_profile(effective_profile)

        if not profile:
            available_profiles = profile_manager.list_profiles()
            logger.error(
                f"Profile '{effective_profile}' not found. "
                f"Available profiles: {', '.join(available_profiles)}"
            )
            sys.exit(1)

        if not profile_manager.validate_profile(effective_profile):
            logger.error(f"Profile '{effective_profile}' is invalid")
            sys.exit(1)

        # Auto-set collection name from profile if not specified
        if not args.target:
            args.target = effective_profile
            logger.info(f"Auto-setting target collection from profile: {args.target}")

        logger.info(f"Using profile '{effective_profile}' ({profile_source}) for target collection '{args.target}'")

    # Validate target is specified
    if not args.target:
        logger.error(
            "Target collection name is required. "
            "Use -t <collection_name>, -p <profile_name>, or set DEFAULT_PROFILE env var"
        )
        sys.exit(1)

    enricher = Enricher()
    enricher.run(target=args.target, package_name=args.name, verbose=args.verbose)
