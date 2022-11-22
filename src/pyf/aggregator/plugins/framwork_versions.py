from pkg_resources import parse_version

import re


def process(identifier, data):
    """ convert pypi framework classifiers into readable versions
    """
    data["framework_versions"] = []
    regex = re.compile(r"^Framework :: (?P<framework>\w+.*) :: (?P<version>\d+.*)$", re.MULTILINE | re.IGNORECASE)
    for cf in data["classifiers"]:
        version = regex.search(cf)
        if not version:
            continue
        data["framework_versions"].append(f"{version.group('framework')} {version.group('version')}")


def load(settings):
    return process
