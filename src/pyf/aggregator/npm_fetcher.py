"""
npm package fetcher for aggregating npm package metadata.

Fetches packages from the npm registry based on keywords and scopes,
similar to how the PyPI aggregator fetches packages by classifiers.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from dotenv import load_dotenv
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from pyf.aggregator.logger import logger
from pyf.aggregator.ratelimit import TokenBucket
from requests.adapters import HTTPAdapter
from urllib.parse import quote

import os
import requests
import threading
import time

load_dotenv()

# Identify ourselves to the registry. npm's acceptable-use policy asks
# consumers to be identifiable so they can be contacted instead of blocked.
try:
    _VERSION = _pkg_version("pyf.aggregator")
except PackageNotFoundError:
    _VERSION = "0.0.0"
USER_AGENT = (
    f"pyf.aggregator/{_VERSION} (+https://github.com/collective/pyf.aggregator)"
)

# Throughput configuration from environment.
# npm publishes no per-hour request limit. Its acceptable-use policy treats up
# to ~5M requests/month as reasonable; above that is excessive use. Clients must
# handle HTTP 429, and authenticated (token) requests get a higher rate than
# anonymous ones. See:
#   https://blog.npmjs.org/post/187698412060/acceptible-use.html
#   https://blog.npmjs.org/post/164799520460/api-rate-limiting-rolling-out.html
NPM_AUTH_TOKEN = os.getenv("NPM_AUTH_TOKEN", "")
# Concurrency is the primary throughput control: the thread pool runs up to
# NPM_MAX_WORKERS requests at once. NPM_MAX_RPS optionally caps the *average*
# request rate via a token bucket WITHOUT serializing those concurrent requests
# (a fixed per-request delay would defeat the pool, which is what the previous
# global lock did). 0 disables the cap, leaving concurrency bounded only by
# NPM_MAX_WORKERS. 429 responses are always honored via Retry-After.
NPM_MAX_WORKERS = int(os.getenv("NPM_MAX_WORKERS", 16))
NPM_MAX_RPS = float(os.getenv("NPM_MAX_RPS", 0))
NPM_MAX_RETRIES = int(os.getenv("NPM_MAX_RETRIES", 3))
NPM_RETRY_BACKOFF = float(os.getenv("NPM_RETRY_BACKOFF", 2.0))

# jsDelivr CDN — source of per-version READMEs. The npm registry's JSON API only
# exposes the latest version's readme (the package document root); each version's actual
# readme lives in its published files. jsDelivr serves individual files per
# version, so we fetch just the README rather than downloading whole tarballs.
JSDELIVR_DATA_URL = os.getenv(
    "JSDELIVR_DATA_URL", "https://data.jsdelivr.com/v1/packages/npm"
)
JSDELIVR_CDN_URL = os.getenv("JSDELIVR_CDN_URL", "https://cdn.jsdelivr.net/npm")

# Plugin storage (populated by register_npm_plugins)
NPM_PLUGINS = []


class NpmAggregator:
    """Fetches package metadata from npm registry."""

    def __init__(
        self,
        mode,
        npm_base_url="https://registry.npmjs.org",
        filter_keywords=None,
        filter_scopes=None,
        limit=None,
    ):
        """Initialize npm aggregator.

        Args:
            mode: "first" for full download, "incremental" for recent updates
            npm_base_url: Base URL for npm registry API
            filter_keywords: List of keywords to search for (e.g., ["plone"])
            filter_scopes: List of scopes to search for (e.g., ["@plone", "@plone-collective"])
            limit: Maximum number of packages to process
        """
        self.mode = mode
        self.npm_base_url = npm_base_url.rstrip("/")
        self.filter_keywords = filter_keywords or []
        self.filter_scopes = filter_scopes or []
        self.limit = limit
        self._fetch_counter = 0
        self._fetch_counter_lock = threading.Lock()
        self._total_packages = 0
        self._limiter = TokenBucket(NPM_MAX_RPS)
        # Registry session carries auth + identifying UA; connection-pooled to the
        # worker count so concurrent requests reuse connections.
        self._session = self._build_session(with_auth=True)
        # Separate CDN session for jsDelivr — never send the npm token to a third
        # party. Same pooling, identifying UA, no Authorization header.
        self._cdn_session = self._build_session(with_auth=False)

    def _build_session(self, with_auth):
        """Build a connection-pooled requests.Session sized to the worker count."""
        session = requests.Session()
        adapter = HTTPAdapter(
            pool_connections=NPM_MAX_WORKERS, pool_maxsize=NPM_MAX_WORKERS
        )
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        session.headers["User-Agent"] = USER_AGENT
        if with_auth and NPM_AUTH_TOKEN:
            session.headers["Authorization"] = f"Bearer {NPM_AUTH_TOKEN}"
        return session

    def __iter__(self):
        """Iterate over all package versions, yielding (identifier, data) tuples."""
        start = int(time.time())
        logger.info(f"[{datetime.now()}] Start aggregating packages from npm...")

        if self.mode == "first":
            iterator = self._all_packages
        elif self.mode == "incremental":
            # For npm, incremental mode searches for recently updated packages
            iterator = self._incremental_packages
        else:
            raise ValueError(f"Unknown mode: {self.mode}")

        count = 0
        # _all_packages / _incremental_packages now yield fully-built
        # (identifier, data) records — including each version's own README —
        # so iteration only has to apply plugins and enforce the limit.
        for identifier, data in iterator:
            if self.limit and count >= self.limit:
                return
            count += 1

            for plugin in NPM_PLUGINS:
                plugin(identifier, data)

            yield identifier, data

        elapsed = time.time() - start
        logger.info(
            f"[{datetime.now()}] npm aggregation finished! Processed {count} versions in {elapsed:.1f}s"
        )

    def _apply_rate_limit(self):
        """Pace requests via a token bucket.

        Caps the average request rate (NPM_MAX_RPS) without serializing the
        concurrent requests, so the worker pool actually runs in parallel.
        A no-op when NPM_MAX_RPS <= 0.
        """
        self._limiter.acquire()

    def _is_valid_package(self, pkg):
        """Check if package matches filter criteria (keyword or scope).

        Args:
            pkg: Search result package object

        Returns:
            True if package has valid keyword or is in valid scope
        """
        pkg_data = pkg.get("package", {})
        name = pkg_data.get("name", "")
        keywords = pkg_data.get("keywords", [])

        # Check if package is in a configured scope
        for scope in self.filter_scopes:
            if name.startswith(f"{scope}/"):
                return True

        # Check if package has a configured keyword (case-insensitive)
        pkg_keywords_lower = {k.lower() for k in keywords if isinstance(k, str)}
        for keyword in self.filter_keywords:
            if keyword.lower() in pkg_keywords_lower:
                return True

        return False

    def _search_packages(self):
        """Search for packages by keywords and scopes.

        Returns:
            Dict mapping package name to search result data (includes scores)
        """
        packages = {}
        rejected_count = 0

        # Search by keywords
        for keyword in self.filter_keywords:
            logger.info(f"Searching npm for keyword: {keyword}")
            results = self._search_by_keyword(keyword)
            for pkg in results:
                name = pkg.get("package", {}).get("name")
                if name and name not in packages:
                    if self._is_valid_package(pkg):
                        packages[name] = pkg
                    else:
                        rejected_count += 1
                        logger.debug(
                            f"Rejected package {name}: no matching keyword/scope"
                        )

        # Search by scopes
        for scope in self.filter_scopes:
            logger.info(f"Searching npm for scope: {scope}")
            results = self._search_by_scope(scope)
            for pkg in results:
                name = pkg.get("package", {}).get("name")
                if name and name not in packages:
                    if self._is_valid_package(pkg):
                        packages[name] = pkg
                    else:
                        rejected_count += 1
                        logger.debug(
                            f"Rejected package {name}: no matching keyword/scope"
                        )

        logger.info(
            f"Found {len(packages)} valid packages, rejected {rejected_count} non-matching"
        )
        return packages

    def _search_by_keyword(self, keyword):
        """Search npm for packages with a specific keyword.

        Args:
            keyword: Keyword to search for (e.g., "plone")

        Returns:
            List of package search results
        """
        return self._npm_search(f"keywords:{keyword}")

    def _search_by_scope(self, scope):
        """Search npm for packages in a specific scope.

        Args:
            scope: Scope to search for (e.g., "@plone")

        Returns:
            List of package search results
        """
        # Remove @ prefix if present for the search query
        scope_name = scope.lstrip("@")
        return self._npm_search(f"scope:{scope_name}")

    def _npm_search(self, text, size=250):
        """Execute npm search API request.

        Args:
            text: Search query text
            size: Maximum results per page

        Returns:
            List of all search results (handles pagination)
        """
        all_results = []
        offset = 0

        while True:
            url = f"{self.npm_base_url}/-/v1/search"
            params = {"text": text, "size": size, "from": offset}

            self._apply_rate_limit()

            retries = 0
            while retries <= NPM_MAX_RETRIES:
                try:
                    response = self._session.get(url, params=params, timeout=30)
                except requests.exceptions.Timeout:
                    logger.warning(f"Timeout searching npm: {text}")
                    retries += 1
                    if retries <= NPM_MAX_RETRIES:
                        backoff = NPM_RETRY_BACKOFF**retries
                        logger.info(f"Retrying in {backoff:.1f}s")
                        time.sleep(backoff)
                    continue
                except requests.exceptions.RequestException as e:
                    logger.warning(f"Request error searching npm: {e}")
                    retries += 1
                    if retries <= NPM_MAX_RETRIES:
                        backoff = NPM_RETRY_BACKOFF**retries
                        time.sleep(backoff)
                    continue

                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 60))
                    logger.info(f"Rate limited by npm. Waiting {retry_after}s")
                    time.sleep(retry_after)
                    retries += 1
                    continue
                elif response.status_code != 200:
                    logger.warning(f"npm search returned {response.status_code}")
                    return all_results

                try:
                    data = response.json()
                    objects = data.get("objects", [])
                    all_results.extend(objects)

                    # Check if there are more results
                    total = data.get("total", 0)
                    if offset + len(objects) >= total:
                        return all_results
                    offset += len(objects)
                    break
                except Exception as e:
                    logger.error(f"Error parsing npm search response: {e}")
                    return all_results

            if retries > NPM_MAX_RETRIES:
                logger.error(f"Max retries exceeded for npm search: {text}")
                return all_results

        return all_results

    def _get_npm_json(self, package_name):
        """Get full package metadata from npm registry.

        Args:
            package_name: Package name (e.g., "@plone/volto" or "plone-react")

        Returns:
            Package JSON dict or None if not found
        """
        with self._fetch_counter_lock:
            self._fetch_counter += 1
            counter = self._fetch_counter
        logger.info(f"[{counter}] Fetching npm data for: {package_name}")

        # URL-encode the package name (handles scoped packages)
        encoded_name = quote(package_name, safe="")
        url = f"{self.npm_base_url}/{encoded_name}"

        retries = 0
        while retries <= NPM_MAX_RETRIES:
            self._apply_rate_limit()

            try:
                response = self._session.get(url, timeout=30)
            except requests.exceptions.Timeout:
                logger.warning(f"Timeout fetching {package_name}")
                retries += 1
                if retries <= NPM_MAX_RETRIES:
                    backoff = NPM_RETRY_BACKOFF**retries
                    time.sleep(backoff)
                continue
            except requests.exceptions.RequestException as e:
                logger.warning(f"Request error fetching {package_name}: {e}")
                retries += 1
                if retries <= NPM_MAX_RETRIES:
                    backoff = NPM_RETRY_BACKOFF**retries
                    time.sleep(backoff)
                continue

            if response.status_code == 404:
                logger.warning(f"Package not found: {package_name}")
                return None
            elif response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 60))
                logger.info(f"Rate limited. Waiting {retry_after}s")
                time.sleep(retry_after)
                retries += 1
                continue
            elif response.status_code != 200:
                logger.warning(
                    f"npm returned {response.status_code} for {package_name}"
                )
                return None

            try:
                return response.json()
            except Exception as e:
                logger.error(f"Error parsing npm JSON for {package_name}: {e}")
                return None

        logger.error(f"Max retries exceeded for {package_name}")
        return None

    def get_version_readme(self, package_name, version):
        """Fetch a specific version's README from the jsDelivr CDN.

        The npm registry only serves the latest version's readme; each version's
        actual readme lives in its published files, which jsDelivr exposes per
        file. Most packages ship ``README.md``, so we try that directly and only
        consult the file-listing API (one extra request) when it is missing.

        Returns:
            The README text, or None if unavailable (callers fall back to the
            package document's latest readme).
        """
        text = self._jsdelivr_file(package_name, version, "README.md")
        if text is not None:
            return text
        filename = self._jsdelivr_find_readme(package_name, version)
        if filename and filename != "README.md":
            return self._jsdelivr_file(package_name, version, filename)
        return None

    def _jsdelivr_file(self, package_name, version, filename):
        """GET a single file for a package version from jsDelivr; None if missing."""
        url = f"{JSDELIVR_CDN_URL}/{package_name}@{version}/{filename.lstrip('/')}"
        response = self._cdn_get(url)
        if response is None or response.status_code != 200:
            return None
        return response.text

    def _jsdelivr_find_readme(self, package_name, version):
        """Resolve the readme filename at the package root via jsDelivr's file API.

        Handles unusual casing/extensions (readme.md, README.markdown, ...).
        """
        url = f"{JSDELIVR_DATA_URL}/{package_name}@{version}"
        response = self._cdn_get(url)
        if response is None or response.status_code != 200:
            return None
        try:
            files = response.json().get("files", [])
        except ValueError:
            return None
        for entry in files:
            name = entry.get("name", "")
            if entry.get("type") == "file" and name.lower().startswith("readme"):
                return name
        return None

    def _cdn_get(self, url):
        """GET a jsDelivr URL with pacing, retries, and 429 handling.

        Returns the Response (which may carry a 404 for a missing file) or None
        after repeated transport/server errors.
        """
        retries = 0
        while retries <= NPM_MAX_RETRIES:
            self._apply_rate_limit()
            try:
                response = self._cdn_session.get(url, timeout=30)
            except requests.exceptions.RequestException as e:
                logger.warning(f"Request error fetching {url}: {e}")
                retries += 1
                if retries <= NPM_MAX_RETRIES:
                    time.sleep(NPM_RETRY_BACKOFF**retries)
                continue

            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 60))
                logger.info(f"Rate limited by CDN. Waiting {retry_after}s")
                time.sleep(retry_after)
                retries += 1
                continue
            if response.status_code >= 500:
                logger.warning(f"CDN server error {response.status_code} for {url}")
                retries += 1
                if retries <= NPM_MAX_RETRIES:
                    time.sleep(NPM_RETRY_BACKOFF**retries)
                continue
            return response

        logger.error(f"Max retries exceeded for CDN URL: {url}")
        return None

    def _transform_npm_data(self, package_name, version_data, time_info, package_json):
        """Transform npm package data to match Typesense schema.

        Args:
            package_name: Package name
            version_data: Version-specific metadata from npm
            time_info: Time information for all versions
            package_json: Full package JSON (contains readme at root level)

        Returns:
            Dict matching the Typesense packages schema
        """
        version = version_data.get("version", "")

        # Extract scope from scoped package name
        npm_scope = ""
        if package_name.startswith("@"):
            npm_scope = package_name.split("/")[0].lstrip("@")

        # Get repository URL
        repository = version_data.get("repository", {})
        if isinstance(repository, str):
            repository_url = repository
        else:
            repository_url = repository.get("url", "")

        # Clean up git URL formats
        home_page = version_data.get("homepage", "")
        if not home_page and repository_url:
            # Convert git URLs to https for home_page
            home_page = self._git_url_to_https(repository_url)

        # Get author info
        author = version_data.get("author", {})
        if isinstance(author, str):
            author_name = author
            author_email = ""
        else:
            author_name = author.get("name", "")
            author_email = author.get("email", "")

        # Get maintainers
        maintainers = version_data.get("maintainers", [])
        maintainer_name = ""
        maintainer_email = ""
        if maintainers:
            first_maintainer = maintainers[0]
            if isinstance(first_maintainer, str):
                maintainer_name = first_maintainer
            else:
                maintainer_name = first_maintainer.get("name", "")
                maintainer_email = first_maintainer.get("email", "")

        # Get keywords
        keywords = version_data.get("keywords", [])
        if isinstance(keywords, str):
            keywords = [k.strip() for k in keywords.split(",") if k.strip()]

        # Get dependencies as requires_dist equivalent
        deps = version_data.get("dependencies", {})
        requires_dist = [f"{k}@{v}" for k, v in deps.items()] if deps else []

        # Get upload timestamp
        upload_time = time_info.get(version, "")

        return {
            "name": package_name,
            "name_sortable": package_name,
            "version": version,
            "summary": version_data.get("description", ""),
            "description": package_json.get("readme", ""),
            "description_content_type": "text/markdown",
            "author": author_name,
            "author_email": author_email,
            "maintainer": maintainer_name,
            "maintainer_email": maintainer_email,
            "license": version_data.get("license", ""),
            "keywords": keywords,
            "classifiers": [],  # npm doesn't have classifiers
            "framework_versions": [],
            "python_versions": [],
            "home_page": home_page,
            "repository_url": repository_url,
            "project_url": "",
            "package_url": f"https://www.npmjs.com/package/{quote(package_name, safe='')}",
            "release_url": f"https://www.npmjs.com/package/{quote(package_name, safe='')}/v/{version}",
            "docs_url": "",
            "bugtrack_url": version_data.get("bugs", {}).get("url", "")
            if isinstance(version_data.get("bugs"), dict)
            else "",
            "requires_dist": requires_dist,
            "platform": "node",
            "yanked": version_data.get("deprecated", False) is not False,
            "yanked_reason": version_data.get("deprecated", "")
            if isinstance(version_data.get("deprecated"), str)
            else "",
            "urls": [],
            "project_urls": {"Homepage": home_page} if home_page else {},
            "upload_time": upload_time,
            # Registry identification
            "registry": "npm",
            "npm_scope": npm_scope,
        }

    def _git_url_to_https(self, git_url):
        """Convert git URL to https URL for display.

        Handles formats like:
        - git+https://github.com/owner/repo.git
        - git://github.com/owner/repo.git
        - git+ssh://git@github.com/owner/repo.git
        - https://github.com/owner/repo.git

        Returns:
            https URL or original URL if conversion not possible
        """
        if not git_url:
            return ""

        url = git_url

        # Remove git+ prefix
        if url.startswith("git+"):
            url = url[4:]

        # Convert git:// to https://
        if url.startswith("git://"):
            url = "https://" + url[6:]

        # Convert ssh URLs
        if url.startswith("ssh://git@"):
            url = "https://" + url[10:]
        elif url.startswith("git@"):
            # git@github.com:owner/repo.git -> https://github.com/owner/repo.git
            url = "https://" + url[4:].replace(":", "/", 1)

        # Remove .git suffix for cleaner URLs
        if url.endswith(".git"):
            url = url[:-4]

        return url

    def _get_all_versions(self, package_json):
        """Get all versions of a package with timestamps.

        Args:
            package_json: Full package metadata

        Returns:
            List of (version, timestamp) tuples sorted by version
        """
        versions = package_json.get("versions", {})
        time_info = package_json.get("time", {})

        result = []
        for version in versions.keys():
            ts = time_info.get(version, "")
            result.append((version, ts))

        # Sort by version (newest first is harder to do correctly, so just alphabetical)
        result.sort(key=lambda x: x[0])
        return result

    @staticmethod
    def _extract_scores(search_result):
        """Pull npm search scores into the per-document extra fields."""
        if not search_result:
            return {}
        score = search_result.get("score", {})
        detail = score.get("detail", {})
        return {
            "npm_quality_score": detail.get("quality", 0.0),
            "npm_popularity_score": detail.get("popularity", 0.0),
            "npm_maintenance_score": detail.get("maintenance", 0.0),
            "npm_final_score": score.get("final", 0.0),
        }

    @staticmethod
    def _to_unix_ts(iso_ts):
        """Convert an ISO-8601 timestamp string to a Unix int, or 0 on failure."""
        if not iso_ts:
            return 0
        try:
            dt = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
            return int(dt.timestamp())
        except (ValueError, TypeError, AttributeError):
            return 0

    def _build_version_records(self, package_name, search_result):
        """Fetch a package's package document once and build a base record per version.

        A single package document request covers *every* version (short description,
        deps, timestamps, ...), so there is no per-version package document refetch.
        ``_transform_npm_data`` seeds ``description`` with the package document's latest
        readme as a fallback; the true per-version README is attached later from
        jsDelivr in ``_all_packages``.

        Returns:
            List of {"identifier", "name", "version", "data"} dicts (possibly
            empty).
        """
        package_json = self._get_npm_json(package_name)
        if not package_json:
            return []

        extra_data = self._extract_scores(search_result)
        time_info = package_json.get("time", {})
        safe_name = package_name.replace("/", "--")

        records = []
        for version, version_data in package_json.get("versions", {}).items():
            data = self._transform_npm_data(
                package_name, version_data, time_info, package_json
            )
            if not data:
                continue
            data["upload_timestamp"] = self._to_unix_ts(data.get("upload_time"))
            if extra_data:
                data.update(extra_data)
            records.append(
                {
                    "identifier": f"{safe_name}-{version}",
                    "name": package_name,
                    "version": version,
                    "data": data,
                }
            )
        return records

    @property
    def _all_packages(self):
        """Yield (identifier, data) for every version of every matching package.

        Two concurrent phases:
          1. Fetch each package's package document once and expand it into one base
             record per version (cheap — all versions from a single request).
          2. Fetch each version's README from jsDelivr in parallel and attach
             it, so every version carries its *own* readme.

        This replaces the previous design, which refetched the full package document
        once per version and stamped every version with the latest readme.
        """
        packages = self._search_packages()
        self._total_packages = len(packages)
        if not packages:
            logger.warning("No packages found matching search criteria")
            return

        start_time = time.time()

        # Phase 1: package documents -> base version records (concurrent across packages).
        logger.info(
            f"Phase 1: fetching {len(packages)} package documents with {NPM_MAX_WORKERS} threads..."
        )
        records = []
        completed = 0
        with ThreadPoolExecutor(max_workers=NPM_MAX_WORKERS) as executor:
            futures = {
                executor.submit(self._build_version_records, name, search_result): name
                for name, search_result in packages.items()
            }
            for future in as_completed(futures):
                completed += 1
                if completed % 10 == 0:
                    logger.info(
                        f"  package documents: {completed}/{self._total_packages}"
                    )
                try:
                    records.extend(future.result())
                except Exception as e:
                    name = futures[future]
                    logger.error(f"Error fetching package document for {name}: {e}")

        # Honor the version limit before the (more expensive) README phase.
        if self.limit:
            records = records[: self.limit]

        # Phase 2: per-version READMEs from jsDelivr (concurrent across versions).
        logger.info(
            f"Phase 2: fetching READMEs for {len(records)} versions with {NPM_MAX_WORKERS} threads..."
        )
        with ThreadPoolExecutor(max_workers=NPM_MAX_WORKERS) as executor:
            futures = {
                executor.submit(
                    self.get_version_readme, rec["name"], rec["version"]
                ): rec
                for rec in records
            }
            done = 0
            for future in as_completed(futures):
                rec = futures[future]
                done += 1
                if done % 50 == 0:
                    elapsed = time.time() - start_time
                    rate = done / elapsed if elapsed > 0 else 0
                    logger.info(f"  readmes: {done}/{len(records)} ({rate:.1f}/sec)")
                try:
                    readme = future.result()
                except Exception as e:
                    readme = None
                    logger.error(
                        f"Error fetching readme for {rec['name']}@{rec['version']}: {e}"
                    )
                if readme is not None:
                    rec["data"]["description"] = readme
                yield rec["identifier"], rec["data"]

        elapsed = time.time() - start_time
        logger.info(
            f"Completed: {len(records)} versions from {self._total_packages} "
            f"packages in {elapsed:.1f}s"
        )

    @property
    def _incremental_packages(self):
        """Get recently updated packages.

        For npm, we search with a date filter or rely on search ranking.
        Currently just returns all packages (npm search doesn't have date filter).

        Yields:
            Tuple of (identifier, data) for each version.
        """
        # npm search API doesn't support date filtering
        # For now, just do a full fetch but could be optimized with a separate
        # changes feed or by checking npm's "time" field after fetching
        logger.info(
            "Incremental mode for npm: fetching all packages (limited by search)"
        )
        yield from self._all_packages
