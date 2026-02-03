# from .curated import load_curated
from . import version_slicer
from . import framwork_versions
from . import python_versions
from . import rst_to_html
from . import description_splitter

# Note: health_score plugin removed - use `pyfhealth` command instead
# This ensures health scores are calculated after GitHub data is available


def register_plugins(PLUGINS, settings):
    # PLUGINS.append(load_curated(settings))
    PLUGINS.append(version_slicer.load(settings))
    PLUGINS.append(framwork_versions.load(settings))
    PLUGINS.append(python_versions.load(settings))
    PLUGINS.append(rst_to_html.load(settings))
    PLUGINS.append(description_splitter.load(settings))
