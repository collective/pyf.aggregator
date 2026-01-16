from celery import Celery
from celery.schedules import crontab
from dotenv import load_dotenv
from pyf.aggregator.db import TypesenceConnection, TypesensePackagesCollection
from pyf.aggregator.fetcher import Aggregator, PLONE_CLASSIFIER
from pyf.aggregator.logger import logger

import os


load_dotenv()

# Target collection for indexing - uses environment variable with default
TYPESENSE_COLLECTION = os.getenv("TYPESENSE_COLLECTION", "packages1")

app = Celery(
    "pyf-aggregator",
    broker=os.getenv('REDIS_HOST'),
    broker_connection_retry_on_startup=True,
)


#### Celery tasks

class PackageIndexer(TypesenceConnection, TypesensePackagesCollection):
    """Helper class for indexing packages to Typesense within Celery tasks."""

    def clean_data(self, data):
        """Clean data for Typesense indexing - ensure no None values.

        Based on Indexer.clean_data() pattern from indexer.py.
        """
        list_fields = ["requires_dist", "classifiers"]
        for key, value in data.items():
            if key in list_fields and value is None:
                data[key] = []
                continue
            if value is None:
                data[key] = ""
        return data

    def index_single(self, data, target):
        """Index a single document to Typesense.

        Args:
            data: Package data dict to index
            target: Target collection name
        """
        try:
            res = self.client.collections[target].documents.upsert(data)
            logger.info(f"Indexed package: {data.get('id', 'unknown')}")
            return res
        except Exception as e:
            logger.error(f"Error indexing package {data.get('id', 'unknown')}: {e}")
            raise


@app.task(bind=True, max_retries=3, default_retry_delay=60)
def inspect_project(self, package_data):
    """
    Inspect a project and insert if it has the Framework :: Plone classifier.

    This task fetches full package metadata from PyPI JSON API, checks if the
    package has the Plone classifier, and if so, indexes it to Typesense.

    Args:
        package_data (dict): Package information containing at minimum:
            - package_id (str): The package name
            - release_id (str, optional): Specific version, if None uses latest
            - timestamp (float, optional): Upload timestamp from RSS
    """
    package_id = package_data.get("package_id")
    release_id = package_data.get("release_id")
    timestamp = package_data.get("timestamp")

    if not package_id:
        logger.warning("inspect_project called without package_id, skipping")
        return {"status": "skipped", "reason": "no package_id"}

    logger.info(f"Inspecting package: {package_id} (release: {release_id})")

    try:
        # Create aggregator to fetch package data
        aggregator = Aggregator(mode="first")

        # Fetch full package JSON from PyPI
        package_json = aggregator._get_pypi_json(package_id, release_id or "")

        if not package_json:
            logger.warning(f"Could not fetch package JSON for: {package_id}")
            return {"status": "skipped", "reason": "fetch_failed", "package_id": package_id}

        # Check if package has Plone classifier
        if not aggregator.has_plone_classifier(package_json):
            logger.debug(f"Package {package_id} does not have Plone classifier, skipping")
            return {"status": "skipped", "reason": "no_plone_classifier", "package_id": package_id}

        logger.info(f"Package {package_id} has Plone classifier, indexing...")

        # Extract and prepare data for indexing (following fetcher._get_pypi pattern)
        data = package_json.get("info")
        if not data:
            logger.warning(f"Package {package_id} has no 'info' section")
            return {"status": "skipped", "reason": "no_info", "package_id": package_id}

        data["urls"] = package_json.get("urls", [])

        # Remove unwanted fields
        if "downloads" in data:
            del data["downloads"]
        for url in data.get("urls", []):
            if "downloads" in url:
                del url["downloads"]
            if "md5_digest" in url:
                del url["md5_digest"]

        # Set identifier and sortable name
        version = data.get("version", "")
        identifier = f"{package_id}-{version}" if version else package_id
        data["id"] = identifier
        data["identifier"] = identifier
        data["name_sortable"] = data.get("name", package_id)

        # Add upload timestamp if available
        if timestamp:
            data["upload_timestamp"] = str(timestamp)

        # Index to Typesense
        indexer = PackageIndexer()
        data = indexer.clean_data(data)
        indexer.index_single(data, TYPESENSE_COLLECTION)

        logger.info(f"Successfully indexed package: {identifier}")
        return {"status": "indexed", "package_id": package_id, "identifier": identifier}

    except Exception as e:
        logger.error(f"Error inspecting package {package_id}: {e}")
        # Retry on transient errors
        try:
            raise self.retry(exc=e)
        except self.MaxRetriesExceededError:
            logger.error(f"Max retries exceeded for package {package_id}")
            return {"status": "failed", "reason": str(e), "package_id": package_id}

@app.task
def update_project(package_id):
    """
    Process a package release data.

    Args:
        package_id (str): The ID of the package.
    """
    logger.info(f"Processing {package_id}")
    # TODO

@app.task
def update_github(package_id):
    """
    Process a package release data.

    Args:
        package_id (str): The ID of the package.
    """
    logger.info(f"Processing {package_id}")
    # TODO

@app.task(bind=True, max_retries=3, default_retry_delay=120)
def read_rss_new_projects_and_queue(self):
    """
    Read PyPI RSS feed for new packages and queue inspect_project for each.

    This task fetches the PyPI new packages RSS feed, parses each entry,
    and queues an inspect_project task for each new package found.
    The inspect_project task will check if the package has the Plone
    classifier and index it if so.

    RSS Feed: https://pypi.org/rss/packages.xml (latest 40 new packages)
    """
    PYPI_NEW_PACKAGES_RSS = "https://pypi.org/rss/packages.xml"

    logger.info("Starting RSS new projects scan...")

    try:
        # Create aggregator instance to use its RSS parsing methods
        aggregator = Aggregator(mode="incremental")

        # Parse the RSS feed
        entries = aggregator._parse_rss_feed(PYPI_NEW_PACKAGES_RSS)

        if not entries:
            logger.info("No new packages found in RSS feed")
            return {"status": "completed", "packages_queued": 0}

        queued_count = 0
        for entry in entries:
            package_id = entry.get("package_id")
            if not package_id:
                continue

            # Queue inspect_project task for this package
            package_data = {
                "package_id": package_id,
                "release_id": entry.get("release_id"),
                "timestamp": entry.get("timestamp"),
            }
            inspect_project.delay(package_data)
            queued_count += 1
            logger.debug(f"Queued inspect_project for new package: {package_id}")

        logger.info(f"RSS new projects scan complete: {queued_count} packages queued")
        return {"status": "completed", "packages_queued": queued_count}

    except Exception as e:
        logger.error(f"Error reading RSS new projects feed: {e}")
        try:
            raise self.retry(exc=e)
        except self.MaxRetriesExceededError:
            logger.error("Max retries exceeded for RSS new projects scan")
            return {"status": "failed", "reason": str(e)}

@app.task
def read_rss_new_releases_and_queue():
    # TODO
    pass

@app.task
def queue_all_github_updates():
    # TODO
    pass

####  Celery periodic tasks

@app.on_after_configure.connect
def setup_periodic_tasks(sender, **kw):
    """
    Setup periodic tasks for the Celery app.
    """
    sender.add_periodic_task(
        crontab(minute="*/1", hour="*"),
        read_rss_new_projects_and_queue.s(),
        name='read RSS new projects and add to queue'
    )
    sender.add_periodic_task(
        crontab(minute="*/1", hour="*"),
        read_rss_new_releases_and_queue.s(),
        name='read RSS new releases and add to queue'
    )
    pass