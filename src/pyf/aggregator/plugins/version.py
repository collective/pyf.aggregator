from pkg_resources import parse_version

def process_version(identifier, data):
    # parse version to test against:
    try:
        version = parse_version(data['version'])
    except TypeError:
        data['version_major'] = data['version']
        return
    try:
        parts = version.base_version.split(".")
        parts += ["0"] * (4 - len(parts))
        (
            data['version_major'],
            data['version_minor'],
            data['version_bugfix'],
            data['version_postfix']
        ) = [int(_) for _ in parts]
    except ValueError:
        data['version_major'] = data['version']
        return

def load_version(settings):
    return process_version
