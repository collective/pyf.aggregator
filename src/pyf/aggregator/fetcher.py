from lxml import html
from pyf.aggregator.logger import logger
from pathlib import Path

import requests
import xmlrpc.client
import time

PLUGINS = []


class Aggregator(object):
    def __init__(
        self,
        mode,
        sincefile=".pyfaggregator",
        pypi_base_url="https://pypi.org/",
        name_filter=None,
        limit=None,
    ):
        self.mode = mode
        self.sincefile = sincefile
        self.pypi_base_url = pypi_base_url
        self.name_filter = name_filter
        self.limit = limit

    def __iter__(self):
        """ create all json for every package release """
        start = int(time.time())
        filepath = Path(self.sincefile)
        if self.mode == "first":
            iterator = self._all_packages
        elif self.mode == "incremental":
            if not filepath.exists():
                raise ValueError(
                    "given since file does not exist {0}".format(self.sincefile)
                )
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
            identifier = "{0}-{1}".format(package_id, release_id)
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
            for release_id in sorted(package_json["releases"]):
                yield release_id

    @property
    def _all_package_ids(self):
        """ Get all package ids by pypi simple index """
        pypi_index_url = self.pypi_base_url + "/simple"

        request_obj = requests.get(pypi_index_url)
        if not request_obj.status_code == 200:
            raise ValueError("Not 200 OK for {}".format(pypi_index_url))

        result = getattr(request_obj, "text", "")
        if not result:
            raise ValueError("Empty result for {}".format(pypi_index_url))

        logger.info("Got package list.")

        tree = html.fromstring(result)
        for link in tree.xpath("//a"):
            package_id = link.text
            if self.name_filter and self.name_filter not in package_id:
                continue
            yield package_id

    def _package_updates(self, since):
        """ Get all package ids by pypi updated after given time."""
        client = xmlrpc.client.ServerProxy(self.pypi_base_url + "/pypi")
        seen = set()
        for package_id, release_id, ts, action in client.changelog(since):
            if package_id in seen or (
                self.name_filter and self.name_filter not in package_id
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
            logger.warning('Error fetching URL "{}"'.format(package_url))

        try:
            package_json = request_obj.json()
            return package_json
        except Exception:
            logger.Exception('Error reading JSON from "{}"'.format(package_url))
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
