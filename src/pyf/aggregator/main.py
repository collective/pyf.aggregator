from .fetcher import Aggregator
from .fetcher import PLUGINS
from .fetcher import PLONE_CLASSIFIER
from .indexer import Indexer
from .plugins import register_plugins
from .profiles import ProfileManager
from argparse import ArgumentParser
from dotenv import load_dotenv
from pyf.aggregator.logger import logger

import json
import os
import sys

load_dotenv()

DEFAULT_PROFILE = os.getenv("DEFAULT_PROFILE")


COLLECTION_NAME = "packages1"


def show_package(package_name, collection_name, all_versions=False):
    """Show indexed data for a single package from Typesense (for debugging)."""
    from .db import TypesenceConnection

    conn = TypesenceConnection()

    if not conn.collection_exists(name=collection_name):
        logger.error(f"Collection '{collection_name}' does not exist.")
        sys.exit(1)

    # Search for exact package name, sorted by upload_timestamp descending (newest first)
    result = conn.client.collections[collection_name].documents.search({
        "q": package_name,
        "query_by": "name",
        "filter_by": f"name:={package_name}",
        "sort_by": "upload_timestamp:desc",
        "per_page": 100,
    })

    hits = result.get("hits", [])
    if not hits:
        logger.error(f"Package '{package_name}' not found in collection '{collection_name}'.")
        sys.exit(1)

    documents = [hit["document"] for hit in hits]

    if all_versions:
        # Output all versions
        print(json.dumps(documents, indent=2))
    else:
        # Output only the newest version (first after sort)
        print(json.dumps(documents[0], indent=2))


def run_refresh_mode(settings):
    """Refresh indexed packages data from PyPi - fetches ALL versions.

    Lists all unique package names from Typesense, fetches fresh data from PyPI
    for ALL versions of each package, and removes packages that return 404 or
    no longer have the required classifiers.
    """
    from .db import TypesenceConnection, TypesensePackagesCollection
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from datetime import datetime
    import os

    class RefreshHelper(TypesenceConnection, TypesensePackagesCollection):
        pass

    helper = RefreshHelper()
    indexer = Indexer()

    # Verify collection exists
    if not indexer.collection_exists(name=settings["target"]):
        logger.error(f"Collection '{settings['target']}' does not exist. Cannot refresh.")
        sys.exit(1)

    # Get all unique package names
    logger.info(f"Fetching unique package names from collection '{settings['target']}'...")
    package_names = helper.get_unique_package_names(settings["target"])
    total = len(package_names)
    logger.info(f"Found {total} unique packages to refresh")

    # Apply limit if specified
    if settings["limit"] and settings["limit"] > 0:
        package_names = list(package_names)[:settings["limit"]]
        logger.info(f"Limiting to {len(package_names)} packages")

    # Apply name filter if specified
    if settings["filter_name"]:
        package_names = [p for p in package_names if settings["filter_name"] in p]
        logger.info(f"Filtered to {len(package_names)} packages matching '{settings['filter_name']}'")

    # Create aggregator for PyPI fetching (reuse existing methods)
    agg = Aggregator(
        mode="first",
        filter_troove=settings["filter_troove"],
    )

    stats = {"updated": 0, "deleted": 0, "failed": 0, "skipped": 0}
    packages_to_delete = []

    max_workers = int(os.getenv("PYPI_MAX_WORKERS", 20))

    def process_package(package_name):
        """Process a single package - fetch ALL versions from PyPI."""
        try:
            package_json = agg._get_pypi_json(package_name)

            if package_json is None:
                return {"status": "delete", "package": package_name, "reason": "not_found"}

            # Check classifier filter if specified (once per package)
            if settings["filter_troove"]:
                if not agg.has_classifiers(package_json, settings["filter_troove"]):
                    return {"status": "delete", "package": package_name, "reason": "no_classifier"}

            releases = package_json.get("releases", {})
            if not releases:
                return {"status": "skip", "package": package_name, "reason": "no_releases"}

            versions_data = []
            for release_id, release_info in agg._all_package_versions(releases):
                # Get upload timestamp from release info
                ts = release_info[0].get("upload_time") if release_info else None

                # Fetch version-specific metadata
                version_data = agg._get_pypi(package_name, release_id)
                if not version_data:
                    continue

                # Set identifiers
                identifier = f"{package_name}-{release_id}"
                version_data["id"] = identifier
                version_data["identifier"] = identifier

                # Convert timestamp to Unix int64
                if ts:
                    try:
                        dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                        version_data["upload_timestamp"] = int(dt.timestamp())
                    except (ValueError, TypeError):
                        version_data["upload_timestamp"] = 0
                else:
                    version_data["upload_timestamp"] = 0

                # Apply plugins
                for plugin in PLUGINS:
                    plugin(identifier, version_data)

                versions_data.append(version_data)

            return {"status": "update", "package": package_name, "versions": versions_data}

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
                versions = result.get("versions", [])
                if versions:
                    try:
                        # Delete existing versions first (clean slate)
                        helper.delete_package_by_name(settings["target"], package_name)

                        # Batch upsert all versions
                        cleaned_versions = [indexer.clean_data(v) for v in versions]
                        helper.client.collections[settings["target"]].documents.import_(
                            cleaned_versions, {"action": "upsert"}
                        )
                        stats["updated"] += len(versions)
                        logger.info(f"[{i}/{len(package_names)}] Updated {package_name}: {len(versions)} versions")
                    except Exception as e:
                        stats["failed"] += 1
                        logger.error(f"[{i}/{len(package_names)}] Failed to index {package_name}: {e}")

            elif result["status"] == "delete":
                packages_to_delete.append(package_name)
                logger.info(f"[{i}/{len(package_names)}] Marked for deletion: {package_name} ({result['reason']})")

            elif result["status"] == "skip":
                stats["skipped"] += 1
                logger.warning(f"[{i}/{len(package_names)}] Skipped: {package_name} ({result['reason']})")

            elif result["status"] == "error":
                stats["failed"] += 1
                logger.error(f"[{i}/{len(package_names)}] Error processing {package_name}: {result['error']}")

    # Delete packages that are no longer valid
    if packages_to_delete:
        logger.info(f"Deleting {len(packages_to_delete)} packages from index...")
        for package_name in packages_to_delete:
            try:
                helper.delete_package_by_name(settings["target"], package_name)
                stats["deleted"] += 1
                logger.info(f"Deleted: {package_name}")
            except Exception as e:
                stats["failed"] += 1
                logger.error(f"Failed to delete {package_name}: {e}")

    logger.info(f"Refresh complete: {stats}")


parser = ArgumentParser(
    description="Aggregate PyPI packages with Framework :: Plone classifier into Typesense. "
    "Use -f for full download or -i for incremental updates via RSS feeds."
)
parser.add_argument(
    "-f", "--first",
    help="Full download: fetch all PyPI packages with Plone classifier",
    action="store_true"
)
parser.add_argument(
    "-i", "--incremental",
    help="Incremental update: fetch recent package updates via RSS feeds",
    action="store_true"
)
parser.add_argument(
    "-s",
    "--sincefile",
    help="File with timestamp of last run (for incremental mode)",
    nargs="?",
    type=str,
    default=".pyaggregator.since",
)
parser.add_argument(
    "-l", "--limit",
    help="Limit the number of packages to process (useful for testing)",
    nargs="?",
    type=int,
    default=0
)
parser.add_argument(
    "-fn", "--filter-name",
    help="Filter packages by name substring",
    nargs="?",
    type=str,
    default=""
)
parser.add_argument(
    "-ft", "--filter-troove",
    help="Filter by classifier (deprecated: Plone filtering is now automatic)",
    action="append",
    default=[]
)
parser.add_argument(
    "-t", "--target",
    help="Target Typesense collection name (required)",
    nargs="?",
    type=str
)
parser.add_argument(
    "--no-plone-filter",
    help="Disable automatic Plone classifier filtering (process all packages)",
    action="store_true"
)
parser.add_argument(
    "-p", "--profile",
    help="Profile name for classifier filtering (overrides DEFAULT_PROFILE env var)",
    nargs="?",
    type=str
)
parser.add_argument(
    "--refresh-from-pypi",
    help="Refresh indexed packages data from PyPi",
    action="store_true"
)
parser.add_argument(
    "--show",
    help="Show indexed data for a package by name (for debugging)",
    type=str,
    metavar="PACKAGE_NAME"
)
parser.add_argument(
    "--all-versions",
    help="Show all versions when using --show (default: only newest)",
    action="store_true"
)
parser.add_argument(
    "--recreate-collection",
    help="Delete and recreate the target collection with current schema (use with -f)",
    action="store_true"
)
parser.add_argument(
    "--force",
    help="Skip confirmation prompts for destructive operations",
    action="store_true"
)


def main():
    args = parser.parse_args()

    # Handle --show mode separately (for debugging indexed data)
    if args.show:
        target = args.target
        # Auto-set target from profile if not specified
        effective_profile = args.profile or DEFAULT_PROFILE
        if not target and effective_profile:
            profile_manager = ProfileManager()
            if profile_manager.get_profile(effective_profile):
                target = effective_profile
        if not target:
            logger.error("Target collection name is required. Use -t <collection_name> or -p <profile>")
            sys.exit(1)
        show_package(args.show, target, all_versions=args.all_versions)
        return

    # Validate mode flags - must specify exactly one of -f, -i, or --refresh-from-pypi
    modes = [args.first, args.incremental, args.refresh_from_pypi]
    if sum(modes) != 1:
        logger.error("Must specify exactly one of -f (full), -i (incremental), or --refresh-from-pypi")
        parser.print_help()
        sys.exit(1)

    # Determine mode
    if args.refresh_from_pypi:
        mode = "refresh"
    elif args.incremental:
        mode = "incremental"
    else:
        mode = "first"

    # Build filter_troove list
    # If profile is specified (CLI or DEFAULT_PROFILE), load classifiers from profile
    # Otherwise, use default Plone filtering logic
    effective_profile = args.profile or DEFAULT_PROFILE
    profile_source = "from CLI" if args.profile else "from DEFAULT_PROFILE"

    if effective_profile:
        profile_manager = ProfileManager()
        profile = profile_manager.get_profile(effective_profile)

        if not profile:
            available_profiles = profile_manager.list_profiles()
            logger.error(
                f"Profile '{effective_profile}' not found. "
                f"Available profiles: {', '.join(available_profiles)}"
            )
            sys.exit(1)

        if not profile_manager.validate_profile(effective_profile):
            logger.error(f"Profile '{effective_profile}' is invalid")
            sys.exit(1)

        filter_troove = profile["classifiers"]
        logger.info(f"Using profile '{effective_profile}' ({profile_source}) with {len(filter_troove)} classifiers")

        # Auto-set collection name from profile if not specified
        if not args.target:
            args.target = effective_profile
            logger.info(f"Auto-setting target collection from profile: {args.target}")
    else:
        # Default behavior: filter for Plone packages unless --no-plone-filter is specified
        filter_troove = list(args.filter_troove) if args.filter_troove else []
        if not args.no_plone_filter and PLONE_CLASSIFIER not in filter_troove:
            filter_troove.append(PLONE_CLASSIFIER)
            logger.info(f"Filtering for packages with classifier: {PLONE_CLASSIFIER}")

        if args.no_plone_filter:
            logger.warning("Plone classifier filtering disabled. Processing ALL packages.")

    # Validate target collection is specified
    if not args.target:
        logger.error("Target collection name is required. Use -t <collection_name>")
        sys.exit(1)

    settings = {
        "mode": mode,
        "sincefile": args.sincefile,
        "filter_name": args.filter_name,
        "filter_troove": filter_troove,
        "limit": args.limit,
        "target": args.target,
    }

    logger.info(f"Starting PyPI aggregation in '{mode}' mode")
    logger.info(f"Target collection: {settings['target']}")
    if settings['limit']:
        logger.info(f"Limiting to {settings['limit']} packages")
    if settings['filter_name']:
        logger.info(f"Filtering by name: {settings['filter_name']}")

    register_plugins(PLUGINS, settings)

    # Handle refresh mode separately
    if mode == "refresh":
        run_refresh_mode(settings)
        return

    agg = Aggregator(
        mode,
        sincefile=settings["sincefile"],
        filter_name=settings["filter_name"],
        filter_troove=settings["filter_troove"],
        limit=settings["limit"],
    )

    indexer = Indexer()

    # Handle --recreate-collection: use zero-downtime alias switching
    if args.recreate_collection:
        from pyf.aggregator.typesense_util import TypesenceUtil
        ts_util = TypesenceUtil()

        # Run migration first (no confirmation needed), then ask about deletion
        result = ts_util.recreate_collection(name=settings["target"], delete_old=False)

        # Confirmation for deletion (unless --force)
        if result.get("old_collection"):
            if args.force:
                ts_util.delete_collection(name=result["old_collection"])
                logger.info(f"Deleted old collection '{result['old_collection']}'")
            else:
                confirm = input(
                    f"Delete old collection '{result['old_collection']}'? (Y/n): "
                )
                if confirm.lower() != 'n':  # Default is Yes
                    ts_util.delete_collection(name=result["old_collection"])
                    logger.info(f"Deleted old collection '{result['old_collection']}'")
                else:
                    logger.info(f"Kept old collection '{result['old_collection']}'")
    elif not indexer.collection_exists(name=settings["target"]) and not indexer.get_alias(settings["target"]):
        # Create versioned collection with alias for fresh start
        from pyf.aggregator.typesense_util import TypesenceUtil
        ts_util = TypesenceUtil()
        ts_util.recreate_collection(name=settings["target"])

    # Execute the aggregation flow
    indexer(agg, settings['target'])

    logger.info(f"Aggregation complete for collection: {settings['target']}")


if __name__ == "__main__":
    main()
