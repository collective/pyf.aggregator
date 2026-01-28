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
    data["version_sortable"] = "0.0000.0000.0000.0000.0000"
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

def extract_digits(s: str) -> str:
    """Extract digits from a string."""
    return ''.join(c for c in s if c.isdigit()) or '0'


def make_version_sortable(groups):
    """Return a zero-padded sortable string from version components.

    Format: STABLE.MAJOR.MINOR.BUGFIX.PRERELEASE_TYPE.PRERELEASE_NUM
    - STABLE: 1 for stable releases, 0 for pre-releases
    - PRERELEASE_TYPE: 0000=alpha, 0001=beta, 0002=rc, 0003=dev (sorted newest first)
    - Each segment is zero-padded to 4 digits for correct lexicographic sort.

    This ensures stable versions ALWAYS sort above pre-releases regardless of
    version number. For example:
    - 2.5.3 (stable) -> 1.0002.0005.0003.0000.0000
    - 3.0.0a2 (alpha) -> 0.0003.0000.0000.0000.0002

    Sorting descending: 2.5.3 > 3.0.0a2 (matches PyPI's "latest" behavior)
    """
    postfix = groups.get('postfix1') or groups.get('postfix2') or ""
    major = groups.get('major', '0') or '0'
    minor = groups.get('minor', '0') or '0'
    bugfix = groups.get('bugfix', '0') or '0'

    postfix_lower = postfix.lower()

    # Determine if pre-release and map type
    # Pre-release type values sorted for descending order: rc(0002) > beta(0001) > alpha(0000) > dev(0003 but stable_flag=0)
    # Actually for desc sort within pre-releases: rc > beta > alpha > dev
    # So: rc=0003, beta=0002, alpha=0001, dev=0000
    if postfix_lower.startswith(("a", "alpha")):
        stable_flag = "0"
        pre_type = "0001"
        pre_num = extract_digits(postfix)
    elif postfix_lower.startswith(("b", "beta")):
        stable_flag = "0"
        pre_type = "0002"
        pre_num = extract_digits(postfix)
    elif postfix_lower.startswith(("rc", "c")):
        stable_flag = "0"
        pre_type = "0003"
        pre_num = extract_digits(postfix)
    elif postfix_lower.startswith("dev"):
        stable_flag = "0"
        pre_type = "0000"  # dev sorts before alpha
        pre_num = extract_digits(postfix)
    else:
        stable_flag = "1"
        pre_type = "0000"
        pre_num = "0"

    return (
        f"{stable_flag}."
        f"{major.zfill(4)}.{minor.zfill(4)}.{bugfix.zfill(4)}."
        f"{pre_type}.{pre_num.zfill(4)}"
    )


def load(settings):
    return process
