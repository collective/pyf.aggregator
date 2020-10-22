from pkg_resources import parse_version

def process_version(identifier, data):
    # parse version to test against:
    data['version_raw'] = data['version']
    try:
        version = parse_version(data['version'])
    except TypeError:
        return
    try:
        parts = version.base_version.split(".")
        parts += ["0"] * (4 - len(parts))
        data['version_major'] = int(parts[0])
        data['version_minor'] = int(parts[1])
        data['version_bugfix'] = int(parts[2])
        data['version_postfix']  = parts[3]
    except ValueError:
        return

def load_version(settings):
    return process_version
