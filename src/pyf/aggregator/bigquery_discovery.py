"""BigQuery-based package discovery for PyPI.

The full ("first") fetch normally brute-forces the entire PyPI Simple index
(~650k projects) and downloads each project's JSON just to check whether it
carries the wanted classifier. That is the dominant cost of a full run.

This module offers a server-side alternative: the public
``bigquery-public-data.pypi.distribution_metadata`` table exposes each
distribution's ``classifiers`` array, so a single SQL query returns only the
project names that match the classifier filter. The downstream metadata fetch
then runs over those few thousand names instead of all of PyPI.

Optional: requires the ``bigquery`` extra (``google-cloud-bigquery``) and
Google Cloud credentials (Application Default Credentials). Reading the public
dataset is free, but BigQuery bills the bytes scanned to *your* billing
project, so a project must be configured (``BIGQUERY_PROJECT`` /
``GOOGLE_CLOUD_PROJECT`` or the ADC default).
"""

from pyf.aggregator.logger import logger

import os


try:  # google-cloud-bigquery is an optional dependency (the 'bigquery' extra)
    from google.cloud import bigquery
except ImportError:  # pragma: no cover - exercised via monkeypatch in tests
    bigquery = None


# Public dataset table holding per-distribution metadata including classifiers.
BIGQUERY_PYPI_TABLE = os.getenv(
    "BIGQUERY_PYPI_TABLE", "bigquery-public-data.pypi.distribution_metadata"
)
# Billing project for the query. The public dataset is free to read, but
# BigQuery still bills the scanned bytes to a project of yours. Falls back to
# the ADC default project when unset.
BIGQUERY_PROJECT = os.getenv("BIGQUERY_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT")


def _build_client(project=None):
    """Build a BigQuery client, raising a helpful error if the extra is missing."""
    if bigquery is None:
        raise RuntimeError(
            "BigQuery discovery requires the 'bigquery' extra. Install it with: "
            "uv pip install 'pyf.aggregator[bigquery]'"
        )
    return bigquery.Client(project=project or BIGQUERY_PROJECT)


def discover_package_names(filter_classifiers, client=None, table=None):
    """Return PyPI project names carrying any of the given classifier prefixes.

    The match mirrors ``Aggregator.has_classifiers``: a project matches when any
    of its classifiers *starts with* any filter prefix, so ``"Framework ::
    Plone"`` also captures ``"Framework :: Plone :: 6.0"``.

    Args:
        filter_classifiers: A classifier prefix string or list of them.
        client: Optional pre-built BigQuery client (injected in tests / reuse).
        table: Optional fully-qualified table override.

    Returns:
        Sorted list of unique project names.
    """
    if bigquery is None and client is None:
        # Surface the actionable install hint before doing anything else.
        _build_client()

    if isinstance(filter_classifiers, str):
        filter_classifiers = [filter_classifiers]
    filter_classifiers = [c for c in filter_classifiers if c]
    if not filter_classifiers:
        raise ValueError("BigQuery discovery requires at least one classifier")

    client = client or _build_client()
    table = table or BIGQUERY_PYPI_TABLE

    # Match a project when ANY of its classifiers starts with ANY filter prefix.
    conditions = " OR ".join(
        f"STARTS_WITH(c, @cls{i})" for i in range(len(filter_classifiers))
    )
    query = (
        "SELECT DISTINCT name\n"
        f"FROM `{table}`\n"
        "WHERE EXISTS (\n"
        f"    SELECT 1 FROM UNNEST(classifiers) AS c WHERE {conditions}\n"
        ")\n"
        "ORDER BY name"
    )
    params = [
        bigquery.ScalarQueryParameter(f"cls{i}", "STRING", c)
        for i, c in enumerate(filter_classifiers)
    ]
    job_config = bigquery.QueryJobConfig(query_parameters=params)

    logger.info(
        f"Querying BigQuery {table} for packages matching {filter_classifiers}..."
    )
    rows = client.query(query, job_config=job_config).result()
    names = [row["name"] for row in rows]
    logger.info(f"BigQuery discovery returned {len(names)} package names")
    return names
