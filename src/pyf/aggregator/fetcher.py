import json
import logging
import requests
from lxml import html
from pyf.aggregator.logger import logger

PLUGINS = []


class Aggregator(object):
    def __init__(self, pypi_base_url="https://pypi.org/", name_filter=None, limit=None):
        self.pypi_base_url = pypi_base_url
        self.name_filter = name_filter
        self.limit = limit

    def __iter__(self):
        """ create all json for every package release """
        for num, package_id in enumerate(self.package_ids):
            if self.limit is not None and num > self.limit:
                break
            package_json = self.get_package(package_id)
            if not package_json or "releases" not in package_json:
                continue
            logging.info("PACKAGE: {0:5d}: {1}".format(num, package_id))

            for release_id in sorted(package_json["releases"]):
                logging.info("- {0}".format(release_id))
                package_json = self.get_package(package_id, release_id)
                identifier, data = self._get_pypi(package_id, package_json, release_id)
                for plugin in PLUGINS:
                    plugin(identifier, data)
                yield identifier, data

    @property
    def package_ids(self):
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
        all_links = tree.xpath("//a")

        for link in all_links:
            package_id = link.text
            if self.name_filter and self.name_filter not in package_id:
                continue

            yield package_id

    def get_package(self, package_id, release_id=str()):
        """ get json for a package release """
        package_url = self.pypi_base_url + "/pypi/" + package_id
        if release_id:
            package_url += "/" + release_id
        package_url += "/json"

        request_obj = requests.get(package_url)
        if not request_obj.status_code == 200:
            logger.warning('Error on Package url "{}"'.format(package_url))

        try:
            package_json = request_obj.json()
            return package_json
        except Exception as e:
            print("ERROR", e)
            return None

    @staticmethod
    def _get_pypi(package_id, package_json, release_id=str()):
        # build file path
        identifier = package_id
        if release_id:
            identifier += "-" + release_id

        # restructure
        data = package_json["info"]
        data["urls"] = package_json["urls"]
        del data["downloads"]
        for url in data["urls"]:
            del url["downloads"]
            del url["md5_digest"]
        data['name_sortable'] = data['name']
        return identifier, json.dumps(data, indent=2)
