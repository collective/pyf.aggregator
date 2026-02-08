"""
CLI entry point for npm package aggregation.

Usage:
    pyfa npm -f -p plone                    # Full download using plone profile
    pyfa npm -f -p plone -l 10              # Full download, limit to 10 packages
    pyfa npm -i -p plone                    # Incremental update

    # Refresh mode - re-fetch indexed packages from npm, removing non-matching ones
    pyfa npm --refresh-from-npm -p plone              # Refresh all npm packages
    pyfa npm --refresh-from-npm -p plone -l 10        # Refresh with limit
    pyfa npm --refresh-from-npm -p plone -fn volto    # Refresh packages matching 'volto'

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

import sys

load_dotenv()

GITHUB_FIELDS = [
    "github_stars",
    "github_watchers",
    "github_updated",
    "github_open_issues",
    "github_url",
    "contributors",
]


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


def add_subcommand_args(parser):
    """Add npm-specific arguments to a subparser."""
    from pyf.aggregator.cli_utils import add_common_args, add_limit_arg

    add_common_args(parser)
    add_limit_arg(parser)
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
                # Sanitize package name for Typesense document ID (replace / with --)
                safe_pkg_name = pkg_name.replace("/", "--")
                identifier = f"npm:{safe_pkg_name}:{version}"
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


def run_command(args):
    """Run npm aggregation with pre-parsed args."""
    from pyf.aggregator.cli_utils import resolve_profile_and_target

    # Validate mode flags
    modes = [args.first, args.incremental, args.refresh_from_npm]
    if sum(modes) != 1:
        logger.error(
            "Must specify exactly one of -f (full), -i (incremental), or --refresh-from-npm"
        )
        sys.exit(1)

    if args.refresh_from_npm:
        mode = "refresh"
    elif args.incremental:
        mode = "incremental"
    else:
        mode = "first"

    # Resolve profile with npm validation
    effective_profile, profile_data, profile_manager = resolve_profile_and_target(
        args, validate_npm=True
    )

    if not effective_profile:
        logger.error(
            "Profile is required for npm aggregation. "
            "Use -p <profile_name> or set DEFAULT_PROFILE env var"
        )
        sys.exit(1)

    # Get npm configuration
    npm_config = profile_manager.get_npm_config(effective_profile)

    logger.info(
        f"npm profile has "
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

    # Auto-create versioned collection with alias for fresh start
    if not indexer.collection_exists(name=settings["target"]) and not indexer.get_alias(
        settings["target"]
    ):
        from pyf.aggregator.typesense_util import TypesenceUtil

        ts_util = TypesenceUtil()
        ts_util.recreate_collection(name=settings["target"])

    # Execute the aggregation
    indexer(agg, settings["target"])

    logger.info(f"npm aggregation complete for collection: {settings['target']}")


def main():
    parser = ArgumentParser(
        description="Aggregate npm packages into Typesense. "
        "Use -f for full download or -i for incremental updates."
    )
    add_subcommand_args(parser)
    args = parser.parse_args()
    run_command(args)


if __name__ == "__main__":
    main()
