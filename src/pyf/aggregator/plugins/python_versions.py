import re


def process(identifier, data):
    """ convert pypi programming languages classifiers into readable Python versions
    """
    data["python_versions"] = []
    regex = re.compile(r"^Programming Language\s*::\s*(?P<python>\w+.*)\s*::\s*(?P<version>\d+.*)$", re.MULTILINE | re.IGNORECASE)
    for cf in data["classifiers"]:
        version = regex.search(cf)
        if not version:
            continue
        data["python_versions"].append(f"{version.group('python')} {version.group('version')}")


def load(settings):
    return process
