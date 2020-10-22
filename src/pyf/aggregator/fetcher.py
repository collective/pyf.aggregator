from lxml import html
from pathlib import Path
from pyf.aggregator.logger import logger

import requests
import time
import xmlrpc.client


# Plugin storage
PLUGINS = []


class Aggregator:
    def __init__(
        self,
        mode,
        sincefile=".pyfaggregator",
        pypi_base_url="https://pypi.org/",
        filter_name=None,
        filter_troove=None,
        limit=None,
    ):
        self.mode = mode
        self.sincefile = sincefile
        self.pypi_base_url = pypi_base_url
        self.filter_name = filter_name
        self.filter_troove = filter_troove
        self.limit = limit

    def __iter__(self):
        """ create all json for every package release """
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
        for package_id, release_id in iterator:
            if self.limit and count > self.limit:
                return
            count += 1
            identifier = f"{package_id}-{release_id}"
            data = self._get_pypi(package_id, release_id)
            for plugin in PLUGINS:
                plugin(identifier, data)
            yield identifier, data

    @property
    def _all_packages(self):
        for package_id in self._all_package_ids:
            for release_id in self._all_package_versions(package_id):
                yield package_id, release_id

    def _all_package_versions(self, package_id):
        package_json = self._get_pypi_json(package_id)
        if package_json and "releases" in package_json:
            yield from sorted(package_json["releases"])

    @property
    def _all_package_ids(self):
        """ Get all package ids by pypi simple index """
        if self.filter_troove:
            # we can use an API to filter by troove
            client = xmlrpc.client.ServerProxy(self.pypi_base_url + "/pypi")
            for package_id in sorted({_[0] for _ in client.browse(self.filter_troove)}):
                if self.filter_name and self.filter_name not in package_id:
                    continue
                yield package_id
        else:
            pypi_index_url = self.pypi_base_url + "/simple"
            request_obj = requests.get(pypi_index_url)
            if not request_obj.status_code == 200:
                raise ValueError(f"Not 200 OK for {pypi_index_url}")

            result = getattr(request_obj, "text", "")
            if not result:
                raise ValueError(f"Empty result for {pypi_index_url}")

            logger.info("Got package list.")

            tree = html.fromstring(result)
            for link in tree.xpath("//a"):
                package_id = link.text
                if self.filter_name and self.filter_name not in package_id:
                    continue
                yield package_id

    def _package_updates(self, since):
        """ Get all package ids by pypi updated after given time."""
        client = xmlrpc.client.ServerProxy(self.pypi_base_url + "/pypi")
        seen = set()
        for package_id, release_id, ts, action in client.changelog(since):
            if package_id in seen or (
                self.filter_name and self.filter_name not in package_id
            ):
                continue
            seen.update({package_id})
            yield package_id, release_id

    @property
    def package_ids(self):
        if self.mode == "first":
            return self._all_packages
        elif self.mode == "incremental":
            return self._package_updates

    def _get_pypi_json(self, package_id, release_id=""):
        """ get json for a package release """
        package_url = self.pypi_base_url + "/pypi/" + package_id
        if release_id:
            package_url += "/" + release_id
        package_url += "/json"

        request_obj = requests.get(package_url)
        if not request_obj.status_code == 200:
            logger.warning(f'Error fetching URL "{package_url}"')

        try:
            package_json = request_obj.json()
            return package_json
        except Exception:
            logger.exception(f'Error reading JSON from "{package_url}"')
            return None

    def _get_pypi(self, package_id, release_id):
        package_json = self._get_pypi_json(package_id, release_id)
        # restructure
        data = package_json["info"]
        data["urls"] = package_json["urls"]
        del data["downloads"]
        for url in data["urls"]:
            del url["downloads"]
            del url["md5_digest"]
        data["name_sortable"] = data["name"]
        return data
