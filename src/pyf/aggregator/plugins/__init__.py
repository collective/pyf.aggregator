# from .curated import load_curated
from . import version_slicer
# from . import version_timestamp
from . import framwork_versions
from . import python_versions
from . import rst_to_html


def register_plugins(PLUGINS, settings):
    # PLUGINS.append(load_curated(settings))
    PLUGINS.append(version_slicer.load(settings))
    # PLUGINS.append(version_timestamp.load(settings))
    PLUGINS.append(framwork_versions.load(settings))
    PLUGINS.append(python_versions.load(settings))
    PLUGINS.append(rst_to_html.load(settings))
