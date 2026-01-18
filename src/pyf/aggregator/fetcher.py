from dotenv import load_dotenv
from lxml import html
from pathlib import Path
from pyf.aggregator.logger import logger

import feedparser
import os
import re
import requests
import time

load_dotenv()

# Plugin storage
PLUGINS = []

# Classifier constant for Plone framework filtering
PLONE_CLASSIFIER = "Framework :: Plone"

# Rate limiting configuration from environment
PYPI_RATE_LIMIT_DELAY = float(os.getenv("PYPI_RATE_LIMIT_DELAY", 0.1))
PYPI_MAX_RETRIES = int(os.getenv("PYPI_MAX_RETRIES", 3))
PYPI_RETRY_BACKOFF = float(os.getenv("PYPI_RETRY_BACKOFF", 2.0))


class Aggregator:
    def __init__(
        self,
        mode,
        sincefile=".pyfaggregator",
        pypi_base_url="https://pypi.org/",
        filter_name=None,
        filter_troove=None,
        skip_github=False,
        limit=None,
    ):
        self.mode = mode
        self.sincefile = sincefile
        self.pypi_base_url = pypi_base_url
        self.filter_name = filter_name
        self.filter_troove = filter_troove
        self.skip_github = skip_github
        self.limit = limit
        self._last_request_time = 0

    def __iter__(self):
        """create all json for every package release"""
        start = int(time.time())
        filepath = Path(self.sincefile)
        if self.mode == "first":
            iterator = self._all_packages
        elif self.mode == "incremental":
            if not filepath.exists():
                raise ValueError(f"given since file does not exist {self.sincefile}")
            with open(filepath) as fd:
                since = int(fd.read())
            iterator = self._package_updates(since)
        with open(self.sincefile, "w") as fd:
            fd.write(str(start))
        count = 0
        for package_id, release_id, ts in iterator:
            if self.limit and count > self.limit:
                return
            count += 1
            identifier = f"{package_id}-{release_id}"
            data = self._get_pypi(package_id, release_id)
            if not data:
                continue
            data["upload_timestamp"] = ts

            for plugin in PLUGINS:
                plugin(identifier, data)
            yield identifier, data

    @property
    def _project_list(self):
        """Get list of package IDs, optionally filtered by classifier.

        When filter_troove is set (typically to 'Framework :: Plone'), each
        package's JSON metadata is fetched to check if it has the classifier.
        This is slower but necessary since XML-RPC browse() is deprecated.

        Yields:
            package_id: Package name/identifier
        """
        count = 0
        for package_id in self._all_package_ids:
            # Check limit
            if self.limit and count >= self.limit:
                return

            # If classifier filtering is enabled, check each package
            if self.filter_troove:
                package_json = self._get_pypi_json(package_id)
                if not package_json:
                    continue
                if not self.has_classifiers(package_json, self.filter_troove):
                    logger.debug(f"Skipping {package_id} - no matching classifier")
                    continue
                logger.info(f"Found matching package: {package_id}")

            count += 1
            yield package_id

    @property
    def _all_packages(self):
        """Get all package releases, with optional classifier filtering.

        When filter_troove is set, only packages with the matching classifier
        (e.g., 'Framework :: Plone') are yielded.

        Yields:
            Tuple of (package_id, release_id, timestamp) for each release
        """
        for package_id in self._all_package_ids:
            package_json = self._get_pypi_json(package_id)
            if not package_json:
                continue

            # Apply classifier filter if set
            if self.filter_troove and not self.has_classifiers(package_json, self.filter_troove):
                logger.debug(f"Skipping {package_id} - no matching classifier")
                continue

            if self.filter_troove:
                logger.info(f"Found matching package: {package_id}")

            if "releases" in package_json:
                releases = package_json["releases"]
                for release_id, release in self._all_package_versions(releases):
                    if len(release) > 0 and "upload_time" in release[0]:
                        ts = release[0]["upload_time"]
                    else:
                        ts = None
                    yield package_id, release_id, ts

    def _all_package_versions(self, releases):
        sorted_releases = sorted(releases.items())
        return sorted_releases

    @property
    def _all_package_ids(self):
        """Get all package ids by pypi simple index.

        Note: filter_troove is deprecated as XML-RPC browse() is no longer available.
        When filter_troove is set, classifier filtering now happens in _all_packages
        via has_plone_classifier() check on each package's JSON metadata.
        """
        logger.info("Fetching package list from PyPI Simple API...")

        if self.filter_troove:
            logger.warning(
                f"filter_troove='{self.filter_troove}' is set but XML-RPC browse() "
                "is deprecated. Classifier filtering will be done via JSON API "
                "for each package (slower but works)."
            )

        pypi_index_url = self.pypi_base_url + "/simple"
        # Use PyPI Simple API JSON format
        headers = {"Accept": "application/vnd.pypi.simple.v1+json"}

        # Apply rate limiting
        self._apply_rate_limit()

        request_obj = requests.get(pypi_index_url, headers=headers)
        if not request_obj.status_code == 200:
            raise ValueError(f"Not 200 OK for {pypi_index_url}")

        try:
            result = request_obj.json()
        except Exception:
            logger.exception(f"Error parsing JSON from {pypi_index_url}")
            raise ValueError(f"Invalid JSON response from {pypi_index_url}")

        projects = result.get("projects", [])
        if not projects:
            raise ValueError(f"Empty projects list from {pypi_index_url}")

        logger.info(f"Got package list with {len(projects)} projects.")

        for project in projects:
            package_id = project.get("name")
            if not package_id:
                continue
            if self.filter_name and self.filter_name not in package_id:
                continue
            yield package_id

    def _package_updates(self, since):
        """Get package updates since given timestamp using RSS feeds.

        Uses PyPI RSS feeds (updates.xml and packages.xml) instead of
        deprecated XML-RPC changelog() API. RSS feeds return the latest ~40
        entries, so this method filters by timestamp.

        Args:
            since: Unix timestamp to filter updates from

        Yields:
            Tuple of (package_id, release_id, timestamp) for each update
        """
        logger.info(f"Fetching package updates since {since} via RSS feeds...")

        # Collect entries from both RSS feeds
        # updates.xml = recently updated packages
        # packages.xml = newly created packages
        rss_feeds = [
            self.pypi_base_url.rstrip("/") + "/rss/updates.xml",
            self.pypi_base_url.rstrip("/") + "/rss/packages.xml",
        ]

        seen = set()
        all_entries = []

        for feed_url in rss_feeds:
            entries = self._parse_rss_feed(feed_url)
            all_entries.extend(entries)

        # Sort by timestamp descending (newest first) and deduplicate
        all_entries.sort(key=lambda e: e.get("timestamp") or 0, reverse=True)

        for entry in all_entries:
            package_id = entry.get("package_id")
            release_id = entry.get("release_id")
            timestamp = entry.get("timestamp")

            if not package_id:
                continue

            # Skip if we've already seen this package
            if package_id in seen:
                continue

            # Skip if timestamp is before our "since" cutoff
            # Note: RSS feeds only contain ~40 latest entries, so if timestamp
            # is None we include it to be safe
            if timestamp is not None and timestamp < since:
                logger.debug(
                    f"Skipping {package_id} - timestamp {timestamp} is before {since}"
                )
                continue

            # Apply name filter
            if self.filter_name and self.filter_name not in package_id:
                continue

            seen.add(package_id)
            logger.debug(f"Found update: {package_id} {release_id}")
            yield package_id, release_id, timestamp

        logger.info(f"Found {len(seen)} package updates from RSS feeds")

    @property
    def package_ids(self):
        if self.mode == "first":
            return self._all_packages
        elif self.mode == "incremental":
            return self._package_updates

    def _apply_rate_limit(self):
        """Apply rate limiting delay between PyPI API requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < PYPI_RATE_LIMIT_DELAY:
            sleep_time = PYPI_RATE_LIMIT_DELAY - elapsed
            time.sleep(sleep_time)
        self._last_request_time = time.time()

    def _get_pypi_json(self, package_id, release_id=""):
        """Get JSON for a package release with rate limiting and error handling.

        Args:
            package_id: The package name/identifier
            release_id: Optional specific release version

        Returns:
            Package JSON dict or None if package not found or on error
        """
        logger.info(f"fetch data from pypi for: {package_id}")
        package_url = self.pypi_base_url + "/pypi/" + package_id
        if release_id:
            package_url += "/" + release_id
        package_url += "/json"

        retries = 0
        while retries <= PYPI_MAX_RETRIES:
            # Apply rate limiting
            self._apply_rate_limit()

            try:
                request_obj = requests.get(package_url, timeout=30)
            except requests.exceptions.Timeout:
                logger.warning(f'Timeout fetching URL "{package_url}"')
                retries += 1
                if retries <= PYPI_MAX_RETRIES:
                    backoff = PYPI_RETRY_BACKOFF ** retries
                    logger.info(f"Retrying in {backoff:.1f}s (attempt {retries}/{PYPI_MAX_RETRIES})")
                    time.sleep(backoff)
                continue
            except requests.exceptions.RequestException as e:
                logger.warning(f'Request error fetching URL "{package_url}": {e}')
                retries += 1
                if retries <= PYPI_MAX_RETRIES:
                    backoff = PYPI_RETRY_BACKOFF ** retries
                    logger.info(f"Retrying in {backoff:.1f}s (attempt {retries}/{PYPI_MAX_RETRIES})")
                    time.sleep(backoff)
                continue

            # Handle HTTP status codes
            if request_obj.status_code == 404:
                logger.warning(f'Package not found: "{package_id}"')
                return None
            elif request_obj.status_code == 429:
                # Rate limited - wait and retry
                retry_after = int(request_obj.headers.get("Retry-After", 60))
                logger.info(f"Rate limited by PyPI. Waiting {retry_after}s before retry.")
                time.sleep(retry_after)
                retries += 1
                continue
            elif request_obj.status_code >= 500:
                # Server error - retry with backoff
                logger.warning(f'Server error {request_obj.status_code} for "{package_url}"')
                retries += 1
                if retries <= PYPI_MAX_RETRIES:
                    backoff = PYPI_RETRY_BACKOFF ** retries
                    logger.info(f"Retrying in {backoff:.1f}s (attempt {retries}/{PYPI_MAX_RETRIES})")
                    time.sleep(backoff)
                continue
            elif request_obj.status_code != 200:
                logger.warning(f'Unexpected status {request_obj.status_code} for "{package_url}"')
                return None

            # Parse JSON response
            try:
                package_json = request_obj.json()
                return package_json
            except Exception:
                logger.exception(f'Error reading JSON from "{package_url}"')
                return None

        logger.error(f'Max retries exceeded for "{package_url}"')
        return None

    def _get_pypi(self, package_id, release_id):
        package_json = self._get_pypi_json(package_id, release_id)
        # restructure
        data = package_json.get("info")
        if not data:
            return
        data["urls"] = package_json.get("urls", [])
        if "downloads" in data:
            del data["downloads"]
        for url in data.get("urls"):
            del url["downloads"]
            del url["md5_digest"]
        data["name_sortable"] = data.get("name")
        return data

    def has_classifiers(self, package_json, filter_classifiers):
        """Check if a package has any of the specified classifiers.

        Args:
            package_json: Dict containing package metadata with 'info.classifiers'
            filter_classifiers: String or list of classifier prefixes to match

        Returns:
            True if any package classifier starts with any filter classifier, False otherwise
        """
        # Support both string and list input
        if isinstance(filter_classifiers, str):
            filter_classifiers = [filter_classifiers]

        package_classifiers = package_json.get("info", {}).get("classifiers", [])

        # Check if any package classifier starts with any filter classifier
        for filter_classifier in filter_classifiers:
            if any(c.startswith(filter_classifier) for c in package_classifiers):
                return True
        return False

    def _parse_rss_feed(self, feed_url):
        """Parse a PyPI RSS feed and extract package update information.

        Args:
            feed_url: URL of the RSS feed (e.g., https://pypi.org/rss/updates.xml)

        Returns:
            List of dicts with package_id, release_id (if available), and timestamp
        """
        logger.info(f"Fetching RSS feed: {feed_url}")

        # Apply rate limiting
        self._apply_rate_limit()

        retries = 0
        while retries <= PYPI_MAX_RETRIES:
            try:
                feed = feedparser.parse(feed_url)
            except Exception as e:
                logger.warning(f"Error parsing RSS feed {feed_url}: {e}")
                retries += 1
                if retries <= PYPI_MAX_RETRIES:
                    backoff = PYPI_RETRY_BACKOFF ** retries
                    logger.info(f"Retrying in {backoff:.1f}s (attempt {retries}/{PYPI_MAX_RETRIES})")
                    time.sleep(backoff)
                continue

            # Check for feed parsing errors
            if feed.bozo and feed.bozo_exception:
                logger.warning(f"RSS feed parsing issue: {feed.bozo_exception}")
                # feedparser still returns partial data even on errors, so continue

            # Check if we have entries
            if not feed.entries:
                logger.warning(f"No entries found in RSS feed: {feed_url}")
                return []

            entries = []
            for entry in feed.entries:
                parsed_entry = self._parse_rss_entry(entry)
                if parsed_entry:
                    entries.append(parsed_entry)

            logger.info(f"Parsed {len(entries)} entries from RSS feed")
            return entries

        logger.error(f"Max retries exceeded for RSS feed: {feed_url}")
        return []

    def _parse_rss_entry(self, entry):
        """Parse a single RSS feed entry to extract package information.

        PyPI RSS feeds have two formats:
        - packages.xml (new packages): title="package-name added to PyPI", link="/project/package-name/"
        - updates.xml (releases): title="package-name version", link="/project/package-name/version/"

        Args:
            entry: A feedparser entry object

        Returns:
            Dict with package_id, release_id, timestamp, and link, or None if parsing fails
        """
        title = entry.get("title", "")
        link = entry.get("link", "")

        package_id = None
        release_id = None

        # Primary: extract from link (most reliable)
        # Link format: https://pypi.org/project/package-name/ or https://pypi.org/project/package-name/1.0.0/
        if link:
            match = re.search(r"/project/([^/]+)/?(?:([^/]+)/?)?$", link)
            if match:
                package_id = match.group(1)
                release_id = match.group(2) if match.group(2) else None

        # Fallback: try to extract from title for updates.xml format "package-name version"
        if not package_id and title:
            # Check if title ends with "added to PyPI" (packages.xml format)
            if title.endswith(" added to PyPI"):
                package_id = title[:-len(" added to PyPI")].strip()
            else:
                # Title format is typically "package-name version"
                # Split on last space to handle package names with spaces/dashes
                parts = title.rsplit(" ", 1)
                if len(parts) == 2:
                    package_id = parts[0].strip()
                    release_id = parts[1].strip()
                else:
                    package_id = title.strip()

        if not package_id:
            logger.debug(f"Could not parse package_id from RSS entry: {title}")
            return None

        # Extract timestamp
        timestamp = None
        if "published_parsed" in entry and entry.published_parsed:
            timestamp = time.mktime(entry.published_parsed)
        elif "updated_parsed" in entry and entry.updated_parsed:
            timestamp = time.mktime(entry.updated_parsed)

        # Apply name filter if set
        if self.filter_name and self.filter_name not in package_id:
            return None

        return {
            "package_id": package_id,
            "release_id": release_id,
            "timestamp": timestamp,
            "link": link,
            "description": entry.get("summary", ""),
        }
