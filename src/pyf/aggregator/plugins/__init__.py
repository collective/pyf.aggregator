from .curated import load_curated
from .github import load_github_stats
from .version import load_version


def register_plugins(PLUGINS, settings):
    # PLUGINS.append(load_curated(settings))
    # PLUGINS.append(load_github_stats(settings))
    PLUGINS.append(load_version(settings))
