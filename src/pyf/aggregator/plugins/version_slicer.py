from packaging.version import parse as parse_version

import re

regex = re.compile(r"^(?P<major>\d*)\.(?P<minor>\d*)\.?(?P<postfix1>[a-zA-Z]+\d*)?(?P<bugfix>\d)?(?P<postfix2>[a-zA-Z]+\d*)?$", re.MULTILINE | re.IGNORECASE)

def process(identifier, data):
    # parse version to test against:
    version = data.get("version")
    if not version:
        return
    data["version_raw"] = version
    data["version_major"] = 0
    data["version_minor"] = 0
    data["version_bugfix"] = 0
    data["version_postfix"] = ""
    data["version_sortable"] = "0.0.0.0.0"
    try:
        version = parse_version(data["version"])
    except TypeError:
        return
    try:
        vmatch = regex.search(data["version"])
        if not vmatch:
            return
        groups = vmatch.groupdict()
        if groups.get('major'):
            data["version_major"] = int(groups.get('major'))
        if groups.get('minor'):
            data["version_minor"] = int(groups.get('minor'))
        if groups.get('bugfix'):
            data["version_bugfix"] = int(groups.get('bugfix'))
        if groups.get('postfix1'):
            data["postfix"] = groups.get('postfix1')
        if groups.get('postfix2'):
            data["version_postfix"] = groups.get('postfix2')
        data["version_sortable"] = make_version_sortable(groups)
    except ValueError:
        return

def make_version_sortable(groups):
    """ return a sortable string out of major, minor, bugfix and postfix1/2
    """
    postfix = groups.get('postfix1') or groups.get('postfix2') or ""
    sortable_version = "0.0.0.0.0"
    sortable_postfix = None
    if postfix.startswith("a"):
        sortable_postfix = postfix.replace('a', '0.')
    if postfix and postfix.startswith("b"):
        sortable_postfix = postfix.replace('b', '1.')
    if not postfix:
        sortable_postfix = '2.0'
    sortable_version = ""
    major = groups.get('major')
    minor = groups.get('minor', '0')
    bugfix = groups.get('bugfix', '0')
    sortable_version += major
    if minor:
        sortable_version += f".{minor}"
    if bugfix:
        sortable_version += f".{bugfix}"
    if sortable_postfix:
        sortable_version += f".{sortable_postfix}"
    return sortable_version


def load(settings):
    return process
