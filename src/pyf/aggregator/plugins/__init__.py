# from .curated import load_curated
from . import version_slicer
from . import framwork_versions
from . import python_versions
from . import rst_to_html
from . import description_splitter

# Note: health_score plugin removed - use `pyfa health` command instead
# This ensures health scores are calculated after GitHub data is available


def register_plugins(PLUGINS, settings):
    """Install the plugin chain into ``PLUGINS`` (in place).

    Registering is idempotent: Celery workers are long-lived and register once
    per task run, which would otherwise stack the chain up over time. The chain
    is swapped in with a single slice assignment so a worker thread iterating
    the list never observes a half-built chain.
    """
    PLUGINS[:] = [
        # load_curated(settings),
        version_slicer.load(settings),
        framwork_versions.load(settings),
        python_versions.load(settings),
        rst_to_html.load(settings),
        description_splitter.load(settings),
    ]
