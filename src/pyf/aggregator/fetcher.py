from dotenv import load_dotenv
from lxml import html
from pathlib import Path
from pyf.aggregator.logger import logger

import os
import requests
import time
import xmlrpc.client

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
    def _all_packages(self):
        for package_id in self._all_package_ids:
            package_json = self._get_pypi_json(package_id)
            if package_json and "releases" in package_json:
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
        """Get all package ids by pypi simple index"""
        logger.info(f"get package ids pypi...")
        if self.filter_troove:
            # we can use an API to filter by troove
            client = xmlrpc.client.ServerProxy(self.pypi_base_url + "/pypi")
            for package_id in sorted({_[0] for _ in client.browse(self.filter_troove)}):
                if self.filter_name and self.filter_name not in package_id:
                    continue
                yield package_id
        else:
            pypi_index_url = self.pypi_base_url + "/simple"
            # Use PyPI Simple API JSON format
            headers = {"Accept": "application/vnd.pypi.simple.v1+json"}
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
        """Get all package ids by pypi updated after given time."""
        client = xmlrpc.client.ServerProxy(self.pypi_base_url + "/pypi")
        all_package_ids = set(self._all_package_ids)
        seen = set()
        for package_id, release_id, ts, action in client.changelog(since):
            if package_id in seen or (
                self.filter_name and self.filter_name not in package_id
            ):
                continue
            if all_package_ids.isdisjoint([package_id]):
                logger.debug(f"package_id '{package_id}' not wanted by filter-troove, skip!")
                continue
            seen.update({package_id})
            yield package_id, release_id, ts

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

    def has_plone_classifier(self, package_json):
        """Check if a package has the Framework :: Plone classifier.

        Args:
            package_json: Dict containing package metadata with 'info.classifiers'

        Returns:
            True if any classifier starts with 'Framework :: Plone', False otherwise
        """
        classifiers = package_json.get("info", {}).get("classifiers", [])
        return any(c.startswith(PLONE_CLASSIFIER) for c in classifiers)
