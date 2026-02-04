"""
npm package fetcher for aggregating npm package metadata.

Fetches packages from the npm registry based on keywords and scopes,
similar to how the PyPI aggregator fetches packages by classifiers.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from dotenv import load_dotenv
from itertools import islice
from pyf.aggregator.logger import logger
from urllib.parse import quote

import os
import requests
import threading
import time

load_dotenv()

# Rate limiting configuration from environment
# npm registry: 1000 req/hr unauthenticated (~0.28 req/sec = 3.6s delay)
# With auth token: 5000 req/hr (~1.4 req/sec = 0.72s delay)
NPM_RATE_LIMIT_DELAY = float(os.getenv("NPM_RATE_LIMIT_DELAY", 0.72))
NPM_MAX_RETRIES = int(os.getenv("NPM_MAX_RETRIES", 3))
NPM_RETRY_BACKOFF = float(os.getenv("NPM_RETRY_BACKOFF", 2.0))
NPM_MAX_WORKERS = int(os.getenv("NPM_MAX_WORKERS", 10))
NPM_BATCH_SIZE = int(os.getenv("NPM_BATCH_SIZE", 100))
NPM_AUTH_TOKEN = os.getenv("NPM_AUTH_TOKEN", "")

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
        self._last_request_time = 0
        self._rate_limit_lock = threading.Lock()
        self._fetch_counter = 0
        self._fetch_counter_lock = threading.Lock()
        self._total_packages = 0
        self._session = requests.Session()
        # Set auth header if token provided
        if NPM_AUTH_TOKEN:
            self._session.headers["Authorization"] = f"Bearer {NPM_AUTH_TOKEN}"

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
        for package_id, release_id, ts, extra_data in iterator:
            if self.limit and count >= self.limit:
                return
            count += 1

            identifier = f"{package_id}-{release_id}"
            data = self._get_npm_version(package_id, release_id)
            if not data:
                continue

            # Add upload timestamp
            if ts:
                try:
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    data["upload_timestamp"] = int(dt.timestamp())
                except (ValueError, TypeError):
                    data["upload_timestamp"] = 0
            else:
                data["upload_timestamp"] = 0

            # Add extra data from search results (scores)
            if extra_data:
                data.update(extra_data)

            # Apply plugins
            for plugin in NPM_PLUGINS:
                plugin(identifier, data)

            yield identifier, data

        elapsed = time.time() - start
        logger.info(
            f"[{datetime.now()}] npm aggregation finished! Processed {count} versions in {elapsed:.1f}s"
        )

    def _apply_rate_limit(self):
        """Apply rate limiting delay between npm API requests (thread-safe)."""
        with self._rate_limit_lock:
            elapsed = time.time() - self._last_request_time
            if elapsed < NPM_RATE_LIMIT_DELAY:
                sleep_time = NPM_RATE_LIMIT_DELAY - elapsed
                time.sleep(sleep_time)
            self._last_request_time = time.time()

    def _batched(self, iterable, batch_size):
        """Yield batches from an iterable without loading all into memory."""
        iterator = iter(iterable)
        while True:
            batch = list(islice(iterator, batch_size))
            if not batch:
                break
            yield batch

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

    def _get_npm_version(self, package_name, version):
        """Get metadata for a specific package version.

        Args:
            package_name: Package name
            version: Version string

        Returns:
            Transformed package data dict or None if not found
        """
        package_json = self._get_npm_json(package_name)
        if not package_json:
            return None

        versions = package_json.get("versions", {})
        version_data = versions.get(version)
        if not version_data:
            logger.warning(f"Version {version} not found for {package_name}")
            return None

        # Get time information
        time_info = package_json.get("time", {})

        # Transform to common schema
        return self._transform_npm_data(
            package_name, version_data, time_info, package_json
        )

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

    def _fetch_package_metadata(self, package_name, search_result):
        """Fetch metadata for all versions of a package (thread-safe).

        Args:
            package_name: Package name
            search_result: Search result data containing scores

        Returns:
            List of (package_name, version, timestamp, extra_data) tuples
        """
        package_json = self._get_npm_json(package_name)
        if not package_json:
            return None

        # Extract scores from search result
        extra_data = {}
        if search_result:
            score = search_result.get("score", {})
            detail = score.get("detail", {})
            extra_data = {
                "npm_quality_score": detail.get("quality", 0.0),
                "npm_popularity_score": detail.get("popularity", 0.0),
                "npm_maintenance_score": detail.get("maintenance", 0.0),
                "npm_final_score": score.get("final", 0.0),
            }

        results = []
        for version, ts in self._get_all_versions(package_json):
            results.append((package_name, version, ts, extra_data))

        return results if results else None

    @property
    def _all_packages(self):
        """Get all package versions using parallel fetching.

        Yields:
            Tuple of (package_name, version, timestamp, extra_data)
        """
        # First, search for all matching packages
        packages = self._search_packages()
        self._total_packages = len(packages)

        if not packages:
            logger.warning("No packages found matching search criteria")
            return

        logger.info(
            f"Starting parallel fetch for {len(packages)} packages with {NPM_MAX_WORKERS} threads..."
        )

        completed = 0
        start_time = time.time()

        with ThreadPoolExecutor(max_workers=NPM_MAX_WORKERS) as executor:
            for batch in self._batched(packages.items(), NPM_BATCH_SIZE):
                futures = {
                    executor.submit(
                        self._fetch_package_metadata, pkg_name, search_result
                    ): pkg_name
                    for pkg_name, search_result in batch
                }

                for future in as_completed(futures):
                    completed += 1
                    if completed % 10 == 0:
                        elapsed = time.time() - start_time
                        rate = completed / elapsed if elapsed > 0 else 0
                        pct = (
                            (completed / self._total_packages * 100)
                            if self._total_packages > 0
                            else 0
                        )
                        logger.info(
                            f"Progress: {completed}/{self._total_packages} ({pct:.1f}%) packages ({rate:.1f}/sec)"
                        )

                    try:
                        results = future.result()
                        if results:
                            for item in results:
                                yield item
                    except Exception as e:
                        pkg_name = futures[future]
                        logger.error(f"Error fetching {pkg_name}: {e}")

        elapsed = time.time() - start_time
        logger.info(f"Completed: {completed} packages in {elapsed:.1f}s")

    @property
    def _incremental_packages(self):
        """Get recently updated packages.

        For npm, we search with a date filter or rely on search ranking.
        Currently just returns all packages (npm search doesn't have date filter).

        Yields:
            Tuple of (package_name, version, timestamp, extra_data)
        """
        # npm search API doesn't support date filtering
        # For now, just do a full fetch but could be optimized with a separate
        # changes feed or by checking npm's "time" field after fetching
        logger.info(
            "Incremental mode for npm: fetching all packages (limited by search)"
        )
        yield from self._all_packages
