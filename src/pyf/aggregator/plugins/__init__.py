from .curated import load_curated
from .github import load_github_stats


def register_plugins(PLUGINS, settings):
    PLUGINS.append(load_curated(settings))
    PLUGINS.append(load_github_stats(settings))
