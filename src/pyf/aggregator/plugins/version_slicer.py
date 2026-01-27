from packaging.version import InvalidVersion, parse as parse_version

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
    data["version_sortable"] = "0000.0000.0000.0000.0000"
    try:
        version = parse_version(data["version"])
    except (TypeError, InvalidVersion):
        pass  # Continue with regex parsing for non-PEP 440 versions
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
    """Return a zero-padded sortable string from version components.

    Format: MAJOR.MINOR.BUGFIX.PRERELEASE_TYPE.PRERELEASE_NUM
    - PRERELEASE_TYPE: 0000=alpha, 0001=beta, 0002=stable
    - Each segment is zero-padded to 4 digits for correct lexicographic sort.
    """
    postfix = groups.get('postfix1') or groups.get('postfix2') or ""
    major = groups.get('major', '0') or '0'
    minor = groups.get('minor', '0') or '0'
    bugfix = groups.get('bugfix', '0') or '0'

    # Map pre-release type to sortable number
    if postfix.startswith("a"):
        pre_type = "0000"
        pre_num = ''.join(c for c in postfix if c.isdigit()) or '0'
    elif postfix.startswith("b"):
        pre_type = "0001"
        pre_num = ''.join(c for c in postfix if c.isdigit()) or '0'
    else:
        pre_type = "0002"
        pre_num = "0"

    return (
        f"{major.zfill(4)}.{minor.zfill(4)}.{bugfix.zfill(4)}"
        f".{pre_type}.{pre_num.zfill(4)}"
    )


def load(settings):
    return process
