from celery import Celery
from celery.schedules import crontab
from dotenv import load_dotenv
from github import Github
from github import RateLimitExceededException
from github import UnknownObjectException
from pyf.aggregator.db import TypesenceConnection, TypesensePackagesCollection
from pyf.aggregator.fetcher import Aggregator, PLONE_CLASSIFIER
from pyf.aggregator.logger import logger

import os
import re
import time


load_dotenv()

# Target collection for indexing - uses environment variable with default
TYPESENSE_COLLECTION = os.getenv("TYPESENSE_COLLECTION", "packages1")

# GitHub configuration
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

# Task rate limiting - format: "tasks/period" e.g., "10/m", "100/h", "1/s"
# See: https://docs.celeryq.dev/en/stable/userguide/tasks.html#Task.rate_limit
CELERY_TASK_RATE_LIMIT = os.getenv("CELERY_TASK_RATE_LIMIT", None)

# Celery periodic task schedules (crontab format: minute hour day_of_month month day_of_week)
# Set to empty string to disable a task
CELERY_SCHEDULE_RSS_PROJECTS = os.getenv("CELERY_SCHEDULE_RSS_PROJECTS", "*/1 * * * *")
CELERY_SCHEDULE_RSS_RELEASES = os.getenv("CELERY_SCHEDULE_RSS_RELEASES", "*/1 * * * *")
CELERY_SCHEDULE_WEEKLY_REFRESH = os.getenv("CELERY_SCHEDULE_WEEKLY_REFRESH", "0 2 * * 0")
CELERY_SCHEDULE_MONTHLY_FETCH = os.getenv("CELERY_SCHEDULE_MONTHLY_FETCH", "0 3 1 * *")
CELERY_SCHEDULE_WEEKLY_DOWNLOADS = os.getenv("CELERY_SCHEDULE_WEEKLY_DOWNLOADS", "0 4 * * 0")

# GitHub URL regex pattern
github_regex = re.compile(r"^(http[s]{0,1}:\/\/|www\.)github\.com/(.+/.+)")

# GitHub API field mapping
GH_KEYS_MAP = {
    "stars": "stargazers_count",
    "open_issues": "open_issues",
    "is_archived": "archived",
    "watchers": "subscribers_count",
    "updated": "updated_at",
    "gh_url": "html_url",
}

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


@app.task(bind=True, max_retries=3, default_retry_delay=60, rate_limit=CELERY_TASK_RATE_LIMIT)
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

@app.task(bind=True, max_retries=3, default_retry_delay=60, rate_limit=CELERY_TASK_RATE_LIMIT)
def update_project(self, package_id):
    """
    Update/re-index a known Plone package from PyPI.

    This task fetches the latest package metadata from PyPI JSON API and
    indexes it to Typesense. Unlike inspect_project, this task does NOT
    check for the Plone classifier - it assumes the package is already
    known to be a Plone package (used for updating existing packages).

    Args:
        package_id (str): The package name to update.

    Returns:
        dict: Status dict with 'status', 'package_id', and optionally 'identifier' or 'reason'.
    """
    if not package_id:
        logger.warning("update_project called without package_id, skipping")
        return {"status": "skipped", "reason": "no package_id"}

    logger.info(f"Updating package: {package_id}")

    try:
        # Create aggregator to fetch package data
        aggregator = Aggregator(mode="first")

        # Fetch full package JSON from PyPI (latest version)
        package_json = aggregator._get_pypi_json(package_id)

        if not package_json:
            logger.warning(f"Could not fetch package JSON for: {package_id}")
            return {"status": "skipped", "reason": "fetch_failed", "package_id": package_id}

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

        # Index to Typesense
        indexer = PackageIndexer()
        data = indexer.clean_data(data)
        indexer.index_single(data, TYPESENSE_COLLECTION)

        logger.info(f"Successfully updated package: {identifier}")
        return {"status": "indexed", "package_id": package_id, "identifier": identifier}

    except Exception as e:
        logger.error(f"Error updating package {package_id}: {e}")
        # Retry on transient errors
        try:
            raise self.retry(exc=e)
        except self.MaxRetriesExceededError:
            logger.error(f"Max retries exceeded for package {package_id}")
            return {"status": "failed", "reason": str(e), "package_id": package_id}

@app.task(bind=True, max_retries=3, default_retry_delay=60, rate_limit=CELERY_TASK_RATE_LIMIT)
def update_github(self, package_id):
    """
    Fetch GitHub repository data and update package in Typesense.

    This task fetches the package document from Typesense, extracts the GitHub
    repository URL from package metadata (home_page, project_url, project_urls),
    makes a GitHub API call to fetch repository stats, and updates the Typesense
    document with GitHub data (stars, watchers, open_issues, updated timestamp, URL).

    Args:
        package_id (str): The document ID in Typesense (e.g., "plone.api-2.0.0").

    Returns:
        dict: Status dict with 'status', 'package_id', and optionally 'reason'.
    """
    if not package_id:
        logger.warning("update_github called without package_id, skipping")
        return {"status": "skipped", "reason": "no package_id"}

    logger.info(f"Updating GitHub data for package: {package_id}")

    try:
        # Fetch package document from Typesense
        indexer = PackageIndexer()

        try:
            document = indexer.client.collections[TYPESENSE_COLLECTION].documents[package_id].retrieve()
        except Exception as e:
            logger.warning(f"Could not fetch document {package_id} from Typesense: {e}")
            return {"status": "skipped", "reason": "fetch_from_typesense_failed", "package_id": package_id}

        # Extract GitHub repository identifier from package metadata
        repo_identifier = _get_package_repo_identifier(document)

        if not repo_identifier:
            logger.debug(f"No GitHub URL found for package: {package_id}")
            return {"status": "skipped", "reason": "no_github_url", "package_id": package_id}

        logger.info(f"Found GitHub repo for {package_id}: {repo_identifier}")

        # Fetch GitHub repository data
        gh_data = _get_github_data(repo_identifier)

        if not gh_data:
            logger.warning(f"Could not fetch GitHub data for repo: {repo_identifier}")
            return {"status": "skipped", "reason": "github_fetch_failed", "package_id": package_id, "repo": repo_identifier}

        # Update Typesense document with GitHub data
        update_document = {
            'github_stars': gh_data["github"]["stars"],
            'github_watchers': gh_data["github"]["watchers"],
            'github_updated': gh_data["github"]["updated"].timestamp(),
            'github_open_issues': gh_data["github"]["open_issues"],
            'github_url': gh_data["github"]["gh_url"],
        }

        indexer.client.collections[TYPESENSE_COLLECTION].documents[package_id].update(update_document)

        logger.info(f"Successfully updated GitHub data for package: {package_id}")
        return {"status": "updated", "package_id": package_id, "repo": repo_identifier}

    except RateLimitExceededException as e:
        logger.warning(f"GitHub rate limit exceeded for {package_id}, will retry later")
        # Retry after rate limit cooldown
        try:
            raise self.retry(exc=e, countdown=300)  # Retry after 5 minutes
        except self.MaxRetriesExceededError:
            logger.error(f"Max retries exceeded for package {package_id} due to rate limits")
            return {"status": "failed", "reason": "rate_limit_exceeded", "package_id": package_id}

    except Exception as e:
        logger.error(f"Error updating GitHub data for {package_id}: {e}")
        # Retry on transient errors
        try:
            raise self.retry(exc=e)
        except self.MaxRetriesExceededError:
            logger.error(f"Max retries exceeded for package {package_id}")
            return {"status": "failed", "reason": str(e), "package_id": package_id}


def _get_package_repo_identifier(data):
    """
    Extract GitHub repository identifier from package metadata.

    Searches home_page, project_url, and project_urls for a GitHub URL and
    extracts the owner/repo identifier.

    Args:
        data (dict): Package document data from Typesense.

    Returns:
        str: GitHub repo identifier (e.g., "plone/plone.api") or None if not found.
    """
    urls = [data.get("home_page"), data.get("project_url")] + list(
        (data.get("project_urls") or {}).values()
    )
    for url in urls:
        if not url:
            continue
        match = github_regex.match(url)
        if match:
            repo_identifier_parts = match.groups()[-1].split("/")
            repo_identifier = "/".join(repo_identifier_parts[0:2])
            return repo_identifier
    return None


def _get_github_data(repo_identifier):
    """
    Return stats from a given Github repository.

    Args:
        repo_identifier (str): GitHub repository identifier (e.g., "plone/plone.api").

    Returns:
        dict: Dictionary with 'github' key containing repo stats, or empty dict on error.
    """
    github = Github(GITHUB_TOKEN or None)

    while True:
        try:
            repo = github.get_repo(repo_identifier)
        except UnknownObjectException:
            logger.warning(f"GitHub repository not found: {repo_identifier}")
            return {}
        except RateLimitExceededException:
            reset_time = github.rate_limiting_resettime
            delta = reset_time - time.time()
            logger.info(
                f"Waiting until {reset_time} (UTC) reset time to perform more Github requests."
            )
            time.sleep(delta)
        else:
            data = {"github": {}}
            for key, key_github in GH_KEYS_MAP.items():
                data["github"][key] = getattr(repo, key_github)
            return data

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

@app.task(bind=True, max_retries=3, default_retry_delay=120)
def read_rss_new_releases_and_queue(self):
    """
    Read PyPI RSS feed for package updates and queue inspect_project for each.

    This task fetches the PyPI updates RSS feed, parses each entry,
    and queues an inspect_project task for each updated package found.
    The inspect_project task will check if the package has the Plone
    classifier and index it if so.

    RSS Feed: https://pypi.org/rss/updates.xml (latest 100 package updates)
    """
    PYPI_UPDATES_RSS = "https://pypi.org/rss/updates.xml"

    logger.info("Starting RSS new releases scan...")

    try:
        # Create aggregator instance to use its RSS parsing methods
        aggregator = Aggregator(mode="incremental")

        # Parse the RSS feed
        entries = aggregator._parse_rss_feed(PYPI_UPDATES_RSS)

        if not entries:
            logger.info("No new releases found in RSS feed")
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
            logger.debug(f"Queued inspect_project for release: {package_id}")

        logger.info(f"RSS new releases scan complete: {queued_count} packages queued")
        return {"status": "completed", "packages_queued": queued_count}

    except Exception as e:
        logger.error(f"Error reading RSS new releases feed: {e}")
        try:
            raise self.retry(exc=e)
        except self.MaxRetriesExceededError:
            logger.error("Max retries exceeded for RSS new releases scan")
            return {"status": "failed", "reason": str(e)}

@app.task
def queue_all_github_updates():
    # TODO
    pass


@app.task(bind=True, max_retries=2, default_retry_delay=300)
def refresh_all_indexed_packages(self, collection_name=None, profile_name=None):
    """
    Weekly task: Refresh all indexed packages from PyPI.

    Lists all unique package names from the collection, fetches fresh data
    from PyPI for each, and removes packages that return 404 or no longer
    have the required classifiers.

    Args:
        collection_name: Target collection (defaults to TYPESENSE_COLLECTION)
        profile_name: Profile for classifier filtering (defaults to "plone")

    Returns:
        dict: Summary statistics of the refresh operation
    """
    from pyf.aggregator.profiles import ProfileManager
    from pyf.aggregator.fetcher import PLUGINS
    from pyf.aggregator.plugins import register_plugins
    from concurrent.futures import ThreadPoolExecutor, as_completed

    collection = collection_name or TYPESENSE_COLLECTION
    profile = profile_name or "plone"

    logger.info(f"Starting weekly refresh task for collection '{collection}' with profile '{profile}'")

    try:
        # Load profile classifiers
        filter_troove = None
        if profile:
            profile_manager = ProfileManager()
            profile_config = profile_manager.get_profile(profile)
            if profile_config:
                filter_troove = profile_config.get("classifiers", [])
                logger.info(f"Using {len(filter_troove)} classifiers from profile '{profile}'")

        # Setup settings and register plugins
        settings = {"filter_troove": filter_troove}
        register_plugins(PLUGINS, settings)

        # Get helper and aggregator
        indexer = PackageIndexer()
        aggregator = Aggregator(mode="first", filter_troove=filter_troove)

        # Get all unique package names
        logger.info(f"Fetching unique package names from collection '{collection}'...")
        package_names = indexer.get_unique_package_names(collection)
        total = len(package_names)
        logger.info(f"Found {total} unique packages to refresh")

        stats = {"total": total, "updated": 0, "deleted": 0, "failed": 0, "skipped": 0}
        packages_to_delete = []

        max_workers = int(os.getenv("PYPI_MAX_WORKERS", 20))

        def process_package(package_name):
            """Process a single package - fetch from PyPI and return result."""
            try:
                package_json = aggregator._get_pypi_json(package_name)

                if package_json is None:
                    return {"status": "delete", "package": package_name, "reason": "not_found"}

                # Check classifier filter if specified
                if filter_troove:
                    if not aggregator.has_classifiers(package_json, filter_troove):
                        return {"status": "delete", "package": package_name, "reason": "no_classifier"}

                # Extract and prepare data for indexing
                data = package_json.get("info")
                if not data:
                    return {"status": "skip", "package": package_name, "reason": "no_info"}

                data["urls"] = package_json.get("urls", [])

                # Clean up unwanted fields
                if "downloads" in data:
                    del data["downloads"]
                for url in data.get("urls", []):
                    if "downloads" in url:
                        del url["downloads"]
                    if "md5_digest" in url:
                        del url["md5_digest"]

                # Set identifiers
                version = data.get("version", "")
                identifier = f"{package_name}-{version}" if version else package_name
                data["id"] = identifier
                data["identifier"] = identifier
                data["name_sortable"] = data.get("name", package_name)

                # Apply plugins
                for plugin in PLUGINS:
                    plugin(identifier, data)

                return {"status": "update", "package": package_name, "identifier": identifier, "data": data}

            except Exception as e:
                return {"status": "error", "package": package_name, "error": str(e)}

        # Process packages in parallel
        logger.info(f"Processing packages with {max_workers} workers...")
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(process_package, pkg): pkg for pkg in package_names}

            for i, future in enumerate(as_completed(futures), 1):
                result = future.result()
                package_name = result["package"]

                if result["status"] == "update":
                    try:
                        cleaned_data = indexer.clean_data(result["data"])
                        indexer.client.collections[collection].documents.upsert(cleaned_data)
                        stats["updated"] += 1
                        if i % 100 == 0:
                            logger.info(f"[{i}/{total}] Progress: {stats}")
                    except Exception as e:
                        stats["failed"] += 1
                        logger.error(f"Failed to index {package_name}: {e}")

                elif result["status"] == "delete":
                    packages_to_delete.append(package_name)

                elif result["status"] == "skip":
                    stats["skipped"] += 1

                elif result["status"] == "error":
                    stats["failed"] += 1
                    logger.error(f"Error processing {package_name}: {result['error']}")

        # Delete packages that are no longer valid
        if packages_to_delete:
            logger.info(f"Deleting {len(packages_to_delete)} packages from index...")
            for package_name in packages_to_delete:
                try:
                    indexer.delete_package_by_name(collection, package_name)
                    stats["deleted"] += 1
                except Exception as e:
                    stats["failed"] += 1
                    logger.error(f"Failed to delete {package_name}: {e}")

        logger.info(f"Weekly refresh complete: {stats}")
        return {"status": "completed", "stats": stats}

    except Exception as e:
        logger.error(f"Error in weekly refresh task: {e}")
        try:
            raise self.retry(exc=e)
        except self.MaxRetriesExceededError:
            logger.error("Max retries exceeded for weekly refresh task")
            return {"status": "failed", "reason": str(e)}


@app.task(bind=True, max_retries=2, default_retry_delay=600)
def full_fetch_all_packages(self, collection_name=None, profile_name=None):
    """
    Monthly task: Full fetch of all packages matching the profile.

    This performs a complete re-fetch from PyPI, similar to running
    `pyfaggregator -f -p plone` but as a Celery task.

    Args:
        collection_name: Target collection (defaults to profile name)
        profile_name: Profile for classifier filtering (defaults to "plone")

    Returns:
        dict: Summary of the full fetch operation
    """
    from pyf.aggregator.profiles import ProfileManager
    from pyf.aggregator.fetcher import PLUGINS
    from pyf.aggregator.plugins import register_plugins
    from pyf.aggregator.indexer import Indexer

    profile = profile_name or "plone"
    collection = collection_name or profile

    logger.info(f"Starting monthly full fetch for collection '{collection}' with profile '{profile}'")

    try:
        # Load profile
        profile_manager = ProfileManager()
        profile_config = profile_manager.get_profile(profile)

        if not profile_config:
            logger.error(f"Profile '{profile}' not found")
            return {"status": "failed", "reason": f"profile_not_found: {profile}"}

        filter_troove = profile_config.get("classifiers", [])
        logger.info(f"Using {len(filter_troove)} classifiers from profile '{profile}'")

        # Setup settings
        settings = {
            "mode": "first",
            "sincefile": ".pyfaggregator.monthly",
            "filter_name": "",
            "filter_troove": filter_troove,
            "limit": 0,
            "target": collection,
        }

        # Register plugins
        register_plugins(PLUGINS, settings)

        # Create aggregator
        agg = Aggregator(
            mode="first",
            sincefile=settings["sincefile"],
            filter_name=settings["filter_name"],
            filter_troove=settings["filter_troove"],
            limit=settings["limit"],
        )

        # Create/verify collection
        indexer = Indexer()
        if not indexer.collection_exists(name=collection):
            logger.info(f"Creating collection '{collection}'")
            indexer.create_collection(name=collection)

        # Execute aggregation
        indexer(agg, collection)

        logger.info(f"Monthly full fetch complete for collection '{collection}'")
        return {"status": "completed", "collection": collection, "profile": profile}

    except Exception as e:
        logger.error(f"Error in monthly full fetch task: {e}")
        try:
            raise self.retry(exc=e)
        except self.MaxRetriesExceededError:
            logger.error("Max retries exceeded for monthly full fetch task")
            return {"status": "failed", "reason": str(e)}


@app.task(bind=True, max_retries=3, default_retry_delay=60)
def enrich_downloads_all_packages(self):
    """Enrich all indexed packages with download statistics from pypistats.org."""
    from pyf.aggregator.enrichers.downloads import Enricher
    from pyf.aggregator.profiles import ProfileManager

    logger.info("Starting weekly download stats enrichment")

    profile_manager = ProfileManager()
    profiles = profile_manager.list_profiles()

    results = {}
    for profile_name in profiles:
        try:
            enricher = Enricher()
            enricher.run(target=profile_name)
            results[profile_name] = "completed"
            logger.info(f"Download enrichment complete for profile '{profile_name}'")
        except Exception as e:
            logger.error(f"Error enriching downloads for profile '{profile_name}': {e}")
            results[profile_name] = f"failed: {e}"

    return {"status": "completed", "profiles": results}


####  Celery periodic tasks


def parse_crontab(cron_string):
    """Parse a crontab string into celery crontab kwargs.

    Format: "minute hour day_of_month month day_of_week"
    Returns None if string is empty (task disabled).
    """
    if not cron_string or not cron_string.strip():
        return None

    parts = cron_string.strip().split()
    if len(parts) != 5:
        logger.warning(f"Invalid crontab format: {cron_string}, expected 5 parts")
        return None

    return crontab(
        minute=parts[0],
        hour=parts[1],
        day_of_month=parts[2],
        month_of_year=parts[3],
        day_of_week=parts[4],
    )


@app.on_after_configure.connect
def setup_periodic_tasks(sender, **kw):
    """Setup periodic tasks for the Celery app."""

    # RSS new projects
    schedule = parse_crontab(CELERY_SCHEDULE_RSS_PROJECTS)
    if schedule:
        sender.add_periodic_task(
            schedule,
            read_rss_new_projects_and_queue.s(),
            name='read RSS new projects and add to queue'
        )
    else:
        logger.info("RSS new projects task disabled")

    # RSS new releases
    schedule = parse_crontab(CELERY_SCHEDULE_RSS_RELEASES)
    if schedule:
        sender.add_periodic_task(
            schedule,
            read_rss_new_releases_and_queue.s(),
            name='read RSS new releases and add to queue'
        )
    else:
        logger.info("RSS new releases task disabled")

    # Weekly refresh
    schedule = parse_crontab(CELERY_SCHEDULE_WEEKLY_REFRESH)
    if schedule:
        sender.add_periodic_task(
            schedule,
            refresh_all_indexed_packages.s(),
            name='weekly refresh all indexed packages'
        )
    else:
        logger.info("Weekly refresh task disabled")

    # Monthly full fetch
    schedule = parse_crontab(CELERY_SCHEDULE_MONTHLY_FETCH)
    if schedule:
        sender.add_periodic_task(
            schedule,
            full_fetch_all_packages.s(),
            name='monthly full fetch all packages'
        )
    else:
        logger.info("Monthly full fetch task disabled")

    # Weekly download stats enrichment
    schedule = parse_crontab(CELERY_SCHEDULE_WEEKLY_DOWNLOADS)
    if schedule:
        sender.add_periodic_task(
            schedule,
            enrich_downloads_all_packages.s(),
            name='weekly download stats enrichment'
        )
    else:
        logger.info("Weekly download stats enrichment task disabled")