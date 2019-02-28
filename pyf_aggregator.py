from lxml import html

import json
import logging
import os
import requests


logger = logging.getLogger(__name__)


class PyfAggregator(object):

    pypi_base_url = "https://pypi.org/"
    packages_directory_name = "data"

    def build_json_files(self, find_package=str()):
        """ create all json files for every package release """
        package_ids = self.get_package_ids(find_package)
        if not package_ids:
            return False

        self._create_packages_folder()

        for package_id in package_ids[:100]:
            package_json = self.get_package(package_id)
            if not package_json or "releases" not in package_json:
                continue

            for release_id in package_json["releases"]:
                package_json = self.get_package(package_id, release_id)
                self._build_json_file(package_id, package_json, release_id)

        return True

    def get_package_ids(self, find_package=""):
        """ Get all package ids by pypi simple index """
        pypi_index_url = self.pypi_base_url + "/simple"

        request_obj = requests.get(pypi_index_url)
        if not request_obj.status_code == 200:
            raise Exception("[ERROR] No result for {}".format(pypi_index_url))

        result = getattr(request_obj, "text", "")
        if not result:
            return list()

        tree = html.fromstring(result)
        all_links = tree.xpath("//a")

        package_ids = list()
        for link in all_links:
            package_id = link.text

            if find_package and find_package not in package_id:
                continue

            package_ids.append(package_id)

        return sorted(package_ids)

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

    def _build_json_file(self, package_id, package_json, release_id=str()):
        # build file path
        filename = package_id
        if release_id:
            filename += "-" + release_id
        filename += ".json"
        file_path = self.packages_directory_name + "/" + filename

        # restructure
        data = package_json["info"]
        data["urls"] = package_json["urls"]
        del data["downloads"]
        for url in data["urls"]:
            del url["downloads"]
            del url["md5_digest"]

        # write file
        with open(file_path, "w") as file_obj:
            json.dump(data, file_obj, indent=2)

        return True

    def _create_packages_folder(self):
        current_dir = os.path.dirname(os.path.realpath(__file__))
        packages_dir = current_dir + "/" + self.packages_directory_name
        if not os.path.exists(packages_dir):
            os.makedirs(packages_dir)
        return True


def main():
    PyfAggregator().build_json_files("collective.")


if __name__ == "__main__":
    main()
