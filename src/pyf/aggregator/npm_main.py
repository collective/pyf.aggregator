"""
CLI entry point for npm package aggregation.

Usage:
    pyfnpm -f -p plone                    # Full download using plone profile
    pyfnpm -f -p plone -l 10              # Full download, limit to 10 packages
    pyfnpm -i -p plone                    # Incremental update
    pyfnpm --show @plone/volto -t plone   # Show indexed data for a package

    # Refresh mode - re-fetch indexed packages from npm, removing non-matching ones
    pyfnpm --refresh-from-npm -p plone              # Refresh all npm packages
    pyfnpm --refresh-from-npm -p plone -l 10        # Refresh with limit
    pyfnpm --refresh-from-npm -p plone -fn volto    # Refresh packages matching 'volto'

Refresh mode:
    The --refresh-from-npm option iterates over all indexed npm packages and:
    1. Fetches fresh metadata from npm registry
    2. Validates packages still match profile keywords/scopes
    3. Removes packages that return 404 or no longer match filters
    4. Preserves GitHub enrichment fields (stars, watchers, etc.) during refresh
"""

from argparse import ArgumentParser
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
from pyf.aggregator.logger import logger
from pyf.aggregator.npm_fetcher import NpmAggregator, NPM_PLUGINS
from pyf.aggregator.npm_indexer import NpmIndexer
from pyf.aggregator.profiles import ProfileManager

import json
import os
import sys

load_dotenv()

DEFAULT_PROFILE = os.getenv("DEFAULT_PROFILE")

GITHUB_FIELDS = [
    "github_stars",
    "github_watchers",
    "github_updated",
    "github_open_issues",
    "github_url",
    "contributors",
]


def show_package(package_name, collection_name, all_versions=False):
    """Show indexed data for a single npm package from Typesense (for debugging)."""
    from pyf.aggregator.db import TypesenceConnection

    conn = TypesenceConnection()

    if not conn.collection_exists(name=collection_name):
        logger.error(f"Collection '{collection_name}' does not exist.")
        sys.exit(1)

    # Search for exact package name with npm registry filter
    result = conn.client.collections[collection_name].documents.search(
        {
            "q": package_name,
            "query_by": "name",
            "filter_by": f"name:={package_name} && registry:=npm",
            "sort_by": "upload_timestamp:desc",
            "per_page": 100,
        }
    )

    hits = result.get("hits", [])
    if not hits:
        # Try without registry filter in case it wasn't set
        result = conn.client.collections[collection_name].documents.search(
            {
                "q": package_name,
                "query_by": "name",
                "filter_by": f"name:={package_name}",
                "sort_by": "upload_timestamp:desc",
                "per_page": 100,
            }
        )
        hits = result.get("hits", [])

    if not hits:
        logger.error(
            f"Package '{package_name}' not found in collection '{collection_name}'."
        )
        sys.exit(1)

    documents = [hit["document"] for hit in hits]

    if all_versions:
        print(json.dumps(documents, indent=2))
    else:
        print(json.dumps(documents[0], indent=2))


def register_npm_plugins(settings):
    """Register plugins for npm package processing.

    Uses the same plugins as PyPI where applicable.
    """
    from pyf.aggregator.plugins import version_slicer
    from pyf.aggregator.plugins import rst_to_html
    from pyf.aggregator.plugins import description_splitter

    # Version slicer works for npm versions too
    NPM_PLUGINS.append(version_slicer.load(settings))

    # RST to HTML handles markdown descriptions
    NPM_PLUGINS.append(rst_to_html.load(settings))

    # Description splitter extracts title, first_chapter, etc.
    NPM_PLUGINS.append(description_splitter.load(settings))


parser = ArgumentParser(
    description="Aggregate npm packages into Typesense. "
    "Use -f for full download or -i for incremental updates."
)
parser.add_argument(
    "-f",
    "--first",
    help="Full download: fetch all npm packages matching profile",
    action="store_true",
)
parser.add_argument(
    "-i",
    "--incremental",
    help="Incremental update: fetch recent package updates",
    action="store_true",
)
parser.add_argument(
    "-l",
    "--limit",
    help="Limit the number of packages to process (useful for testing)",
    nargs="?",
    type=int,
    default=0,
)
parser.add_argument(
    "-t",
    "--target",
    help="Target Typesense collection name (required)",
    nargs="?",
    type=str,
)
parser.add_argument(
    "-p",
    "--profile",
    help="Profile name for npm filtering (overrides DEFAULT_PROFILE env var)",
    nargs="?",
    type=str,
)
parser.add_argument(
    "--show",
    help="Show indexed data for a package by name (for debugging)",
    type=str,
    metavar="PACKAGE_NAME",
)
parser.add_argument(
    "--all-versions",
    help="Show all versions when using --show (default: only newest)",
    action="store_true",
)
parser.add_argument(
    "--recreate-collection",
    help="Delete and recreate the target collection with current schema (use with -f)",
    action="store_true",
)
parser.add_argument(
    "--force",
    help="Skip confirmation prompts for destructive operations",
    action="store_true",
)
parser.add_argument(
    "--refresh-from-npm",
    help="Refresh indexed npm packages from npm registry, removing non-matching packages",
    action="store_true",
)
parser.add_argument(
    "-fn",
    "--filter-name",
    help="Filter packages by name substring",
    nargs="?",
    type=str,
    default="",
)


def get_npm_package_names(helper, collection_name):
    """Get unique npm package names from collection (registry=npm only)."""
    unique_names = set()
    page = 1
    per_page = 250
    while True:
        result = helper.client.collections[collection_name].documents.search(
            {
                "q": "*",
                "query_by": "name",
                "filter_by": "registry:=npm",
                "include_fields": "name",
                "per_page": per_page,
                "page": page,
                "group_by": "name",
                "group_limit": 1,
            }
        )
        for group in result.get("grouped_hits", []):
            for hit in group.get("hits", []):
                name = hit.get("document", {}).get("name")
                if name:
                    unique_names.add(name)
        if len(result.get("grouped_hits", [])) < per_page:
            break
        page += 1
    return unique_names


def run_npm_refresh_mode(settings):
    """Refresh indexed npm packages from npm registry.

    This function:
    - Gets all indexed npm package names from Typesense
    - Fetches fresh data from npm for each package
    - Validates packages still match profile keywords/scopes
    - Deletes packages that return 404 or no longer match filters
    - Preserves GitHub enrichment fields during refresh
    """
    from pyf.aggregator.db import TypesenceConnection

    helper = TypesenceConnection()
    collection_name = settings["target"]
    limit = settings.get("limit", 0)
    filter_name = settings.get("filter_name", "")

    # Get all indexed npm package names
    logger.info(f"Getting indexed npm package names from collection: {collection_name}")
    all_package_names = get_npm_package_names(helper, collection_name)
    logger.info(f"Found {len(all_package_names)} unique npm packages in index")

    # Apply name filter if specified
    if filter_name:
        all_package_names = {n for n in all_package_names if filter_name in n}
        logger.info(
            f"Filtered to {len(all_package_names)} packages matching '{filter_name}'"
        )

    # Apply limit if specified
    package_names = list(all_package_names)
    if limit > 0:
        package_names = package_names[:limit]
        logger.info(f"Limited to {len(package_names)} packages")

    # Create aggregator for validation and npm fetching
    agg = NpmAggregator(
        mode="first",
        filter_keywords=settings["filter_keywords"],
        filter_scopes=settings["filter_scopes"],
        limit=0,
    )

    # Create indexer for upserting
    indexer = NpmIndexer()

    # Stats tracking
    stats = {"updated": 0, "deleted": 0, "failed": 0, "skipped": 0}

    def process_package(package_name):
        """Process a single package for refresh."""
        try:
            # Fetch fresh data from npm
            package_json = agg._get_npm_json(package_name)

            if package_json is None:
                # Package no longer exists on npm - mark for deletion
                return ("delete", package_name, "404 from npm")

            # Build mock search result for _is_valid_package
            mock_search_result = {
                "package": {
                    "name": package_name,
                    "keywords": package_json.get("keywords", []),
                }
            }
            if not agg._is_valid_package(mock_search_result):
                # Package no longer matches profile filters
                return ("delete", package_name, "no longer matches profile filters")

            # Get existing document to preserve GitHub fields
            existing_docs = helper.client.collections[collection_name].documents.search(
                {
                    "q": package_name,
                    "query_by": "name",
                    "filter_by": f"name:={package_name} && registry:=npm",
                    "per_page": 100,
                }
            )

            # Collect GitHub field values from existing docs
            github_data = {}
            for hit in existing_docs.get("hits", []):
                doc = hit.get("document", {})
                for field in GITHUB_FIELDS:
                    if field in doc and doc[field]:
                        github_data[field] = doc[field]
                if github_data:
                    break  # Got data from first doc with GitHub fields

            return ("update", package_name, package_json, github_data)

        except Exception as e:
            return ("error", package_name, str(e))

    # Process packages in parallel
    logger.info(f"Processing {len(package_names)} packages...")
    packages_to_delete = []
    packages_to_update = []

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            executor.submit(process_package, name): name for name in package_names
        }

        for future in as_completed(futures):
            result = future.result()
            action = result[0]
            pkg_name = result[1]

            if action == "delete":
                reason = result[2]
                packages_to_delete.append(pkg_name)
                logger.info(f"Will delete {pkg_name}: {reason}")
            elif action == "update":
                package_json = result[2]
                github_data = result[3]
                packages_to_update.append((pkg_name, package_json, github_data))
            elif action == "error":
                error = result[2]
                stats["failed"] += 1
                logger.error(f"Error processing {pkg_name}: {error}")

    # Delete packages that no longer match
    for pkg_name in packages_to_delete:
        try:
            # Delete all versions of this package
            helper.client.collections[collection_name].documents.delete(
                {"filter_by": f"name:={pkg_name} && registry:=npm"}
            )
            stats["deleted"] += 1
            logger.info(f"Deleted package: {pkg_name}")
        except Exception as e:
            stats["failed"] += 1
            logger.error(f"Error deleting {pkg_name}: {e}")

    # Update packages with fresh data
    for pkg_name, package_json, github_data in packages_to_update:
        try:
            # Process all versions using aggregator's logic
            versions = package_json.get("versions", {})
            time_info = package_json.get("time", {})

            batch = []
            for version, version_data in versions.items():
                # Transform to our schema
                transformed = agg._transform_npm_data(
                    pkg_name, version_data, time_info, package_json
                )
                if not transformed:
                    continue

                # Add GitHub fields from existing data
                for field, value in github_data.items():
                    transformed[field] = value

                # Create identifier
                identifier = f"npm:{pkg_name}:{version}"
                transformed["id"] = identifier
                transformed["identifier"] = identifier

                # Clean and add to batch
                transformed = indexer.clean_data(transformed)
                batch.append(transformed)

            if batch:
                indexer.index_data(batch, len(batch), collection_name)
                stats["updated"] += 1
                logger.info(f"Updated package: {pkg_name} ({len(batch)} versions)")
            else:
                stats["skipped"] += 1
                logger.warning(f"No valid versions for: {pkg_name}")

        except Exception as e:
            stats["failed"] += 1
            logger.error(f"Error updating {pkg_name}: {e}")

    # Print summary
    logger.info("=" * 50)
    logger.info("Refresh complete!")
    logger.info(f"  Updated: {stats['updated']}")
    logger.info(f"  Deleted: {stats['deleted']}")
    logger.info(f"  Failed:  {stats['failed']}")
    logger.info(f"  Skipped: {stats['skipped']}")
    logger.info("=" * 50)


def main():
    args = parser.parse_args()

    # Handle --show mode separately (for debugging indexed data)
    if args.show:
        target = args.target
        effective_profile = args.profile or DEFAULT_PROFILE
        if not target and effective_profile:
            profile_manager = ProfileManager()
            if profile_manager.get_profile(effective_profile):
                target = effective_profile
        if not target:
            logger.error(
                "Target collection name is required. Use -t <collection_name> or -p <profile>"
            )
            sys.exit(1)
        show_package(args.show, target, all_versions=args.all_versions)
        return

    # Validate mode flags
    modes = [args.first, args.incremental, args.refresh_from_npm]
    if sum(modes) != 1:
        logger.error(
            "Must specify exactly one of -f (full), -i (incremental), or --refresh-from-npm"
        )
        parser.print_help()
        sys.exit(1)

    if args.refresh_from_npm:
        mode = "refresh"
    elif args.incremental:
        mode = "incremental"
    else:
        mode = "first"

    # Handle profile
    effective_profile = args.profile or DEFAULT_PROFILE
    profile_source = "from CLI" if args.profile else "from DEFAULT_PROFILE"

    if not effective_profile:
        logger.error(
            "Profile is required for npm aggregation. "
            "Use -p <profile_name> or set DEFAULT_PROFILE env var"
        )
        sys.exit(1)

    profile_manager = ProfileManager()
    profile = profile_manager.get_profile(effective_profile)

    if not profile:
        available_profiles = profile_manager.list_profiles()
        logger.error(
            f"Profile '{effective_profile}' not found. "
            f"Available profiles: {', '.join(available_profiles)}"
        )
        sys.exit(1)

    # Get npm configuration
    npm_config = profile_manager.get_npm_config(effective_profile)
    if not npm_config:
        logger.error(
            f"Profile '{effective_profile}' has no npm configuration. "
            f"Add 'npm:' section with 'keywords:' and/or 'scopes:' to the profile."
        )
        sys.exit(1)

    if not profile_manager.validate_npm_profile(effective_profile):
        logger.error(f"Profile '{effective_profile}' has invalid npm configuration")
        sys.exit(1)

    # Auto-set collection name from profile if not specified
    if not args.target:
        args.target = effective_profile
        logger.info(f"Auto-setting target collection from profile: {args.target}")

    logger.info(
        f"Using profile '{effective_profile}' ({profile_source}) with "
        f"{len(npm_config['keywords'])} keywords and {len(npm_config['scopes'])} scopes"
    )

    settings = {
        "mode": mode,
        "filter_keywords": npm_config["keywords"],
        "filter_scopes": npm_config["scopes"],
        "limit": args.limit,
        "target": args.target,
        "filter_name": args.filter_name,
    }

    logger.info(f"Starting npm aggregation in '{mode}' mode")
    logger.info(f"Target collection: {settings['target']}")
    if settings["limit"]:
        logger.info(f"Limiting to {settings['limit']} packages")

    # Handle refresh mode separately
    if mode == "refresh":
        run_npm_refresh_mode(settings)
        return

    # Register plugins
    register_npm_plugins(settings)

    # Create aggregator
    agg = NpmAggregator(
        mode=mode,
        filter_keywords=settings["filter_keywords"],
        filter_scopes=settings["filter_scopes"],
        limit=settings["limit"],
    )

    indexer = NpmIndexer()

    # Handle --recreate-collection
    if args.recreate_collection:
        from pyf.aggregator.typesense_util import TypesenceUtil

        ts_util = TypesenceUtil()
        result = ts_util.recreate_collection(name=settings["target"], delete_old=False)

        if result.get("old_collection"):
            if args.force:
                ts_util.delete_collection(name=result["old_collection"])
                logger.info(f"Deleted old collection '{result['old_collection']}'")
            else:
                confirm = input(
                    f"Delete old collection '{result['old_collection']}'? (Y/n): "
                )
                if confirm.lower() != "n":
                    ts_util.delete_collection(name=result["old_collection"])
                    logger.info(f"Deleted old collection '{result['old_collection']}'")
                else:
                    logger.info(f"Kept old collection '{result['old_collection']}'")
    elif not indexer.collection_exists(
        name=settings["target"]
    ) and not indexer.get_alias(settings["target"]):
        # Create versioned collection with alias for fresh start
        from pyf.aggregator.typesense_util import TypesenceUtil

        ts_util = TypesenceUtil()
        ts_util.recreate_collection(name=settings["target"])

    # Execute the aggregation
    indexer(agg, settings["target"])

    logger.info(f"npm aggregation complete for collection: {settings['target']}")


if __name__ == "__main__":
    main()
