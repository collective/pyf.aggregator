from lxml import html

import json
import logging
import os
import requests


logger = logging.getLogger(__name__)

PLUGINS = []


class Aggregator(object):
    def __init__(self, pypi_base_url="https://pypi.org/", name_filter=None):
        self.pypi_base_url = pypi_base_url
        self.name_filter = name_filter

    def __iter__(self):
        """ create all json for every package release """

        for package_id in self.package_ids[:100]:
            package_json = self.get_package(package_id)
            if not package_json or "releases" not in package_json:
                continue

            for release_id in package_json["releases"]:
                package_json = self.get_package(package_id, release_id)
                identifier, data = self._get_pypi(package_id, package_json, release_id)
                for plugin in PLUGINS:
                    plugin(identifier, data)
                yield data

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

        tree = html.fromstring(result)
        all_links = tree.xpath("//a")

        for link in all_links:
            package_id = link.text
            if self.name_filter and self.name_filter not in package_id:
                continue

            yield (package_id)

    def get_package(self, package_id, release_id=str()):
        """ get json for a package release """
        package_url = self.pypi_base_url + "/pypi/" + package_id
        if release_id:
            package_url += "/" + release_id
        package_url += "/json"

        request_obj = requests.get(package_url)
        if not request_obj.status_code == 200:
            print('Error on Package url "{}"'.format(package_url))

        try:
            package_json = request_obj.json()
            return package_json
        except Exception as e:
            print("ERROR", e)
            return None

    def _get_pypi(self, package_id, package_json, release_id=str()):
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
        return identifier, json.dumps(data, indent=2)

    def _create_packages_folder(self):
        current_dir = os.path.dirname(os.path.realpath(__file__))
        packages_dir = current_dir + "/" + self.packages_directory_name
        if not os.path.exists(packages_dir):
            os.makedirs(packages_dir)
        return True

