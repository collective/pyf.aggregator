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
    3. Removes packages that return 404 or no longer match filters (npm
       documents only - a PyPI package of the same name is left alone)
    4. Preserves the enrichment fields (GitHub stats, npm scores) during refresh
    5. Writes the same document ids as a full fetch and drops the package's
       stale npm documents, so a refresh never duplicates versions
"""

from argparse import ArgumentParser
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
from pyf.aggregator.logger import logger
from pyf.aggregator.npm_fetcher import (
    NpmAggregator,
    NPM_PLUGINS,
    npm_identifier,
)
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

# npm scores are only available from the search API, which the refresh does not
# call. Together with the GitHub fields they would be lost on every refresh,
# because an upsert replaces the whole document.
NPM_SCORE_FIELDS = [
    "npm_quality_score",
    "npm_popularity_score",
    "npm_maintenance_score",
    "npm_final_score",
]

PRESERVED_FIELDS = GITHUB_FIELDS + NPM_SCORE_FIELDS


def register_npm_plugins(settings):
    """Register plugins for npm package processing.

    Uses the same plugins as PyPI where applicable. The plugins are not
    cosmetic: version_slicer fills the version_* fields, which the collection
    schema declares as required. Documents built without them are rejected by
    Typesense, so every mode that writes npm documents has to register them.
    """
    from pyf.aggregator.plugins import version_slicer
    from pyf.aggregator.plugins import rst_to_html
    from pyf.aggregator.plugins import description_splitter

    # Swapped in as a whole so registering twice cannot stack the chain up and
    # a concurrent reader never sees a half-built chain.
    NPM_PLUGINS[:] = [
        # Version slicer works for npm versions too
        version_slicer.load(settings),
        # RST to HTML handles markdown descriptions
        rst_to_html.load(settings),
        # Description splitter extracts title, first_chapter, etc.
        description_splitter.load(settings),
    ]


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
    return helper.get_unique_package_names(collection_name, registry="npm")


def collect_preserved_fields(helper, collection_name, package_name):
    """Collect the enrichment-only fields of an indexed npm package.

    Returns:
        Dict of field values found on the package's npm documents.
    """
    preserved = {}
    for doc in helper.get_documents_by_name(
        collection_name, package_name, registry="npm"
    ):
        for field in PRESERVED_FIELDS:
            if field not in preserved and doc.get(field):
                preserved[field] = doc[field]
    return preserved


def build_refresh_batch(
    agg, indexer, package_name, package_json, preserved_fields, readmes
):
    """Build the Typesense documents for every version of a refreshed package.

    Args:
        agg: NpmAggregator used to transform the registry payload.
        indexer: NpmIndexer used to clean the documents.
        package_name: npm package name.
        package_json: Fresh package document from the npm registry.
        preserved_fields: Enrichment fields carried over from the indexed
            documents (GitHub stats, npm scores).
        readmes: Mapping of version to its own README (from the CDN).

    Returns:
        List of cleaned documents, keyed by the same ids a full fetch writes.
    """
    versions = package_json.get("versions", {})
    time_info = package_json.get("time", {})

    batch = []
    for version, version_data in versions.items():
        transformed = agg._transform_npm_data(
            package_name, version_data, time_info, package_json
        )
        if not transformed:
            continue

        transformed["upload_timestamp"] = agg._to_unix_ts(
            transformed.get("upload_time")
        )

        # Override the (latest) package document readme with this version's own
        readme = readmes.get(version)
        if readme is not None:
            transformed["description"] = readme

        # Add GitHub fields from existing data
        for field, value in preserved_fields.items():
            transformed[field] = value

        identifier = npm_identifier(package_name, version)
        transformed["id"] = identifier
        transformed["identifier"] = identifier

        # Same plugin chain a full fetch runs - it fills the required
        # version_* fields and the weighted description fields.
        for plugin in NPM_PLUGINS:
            plugin(identifier, transformed)

        batch.append(indexer.clean_data(transformed))

    return batch


def run_npm_refresh_mode(settings):
    """Refresh indexed npm packages from npm registry.

    This function:
    - Gets all indexed npm package names from Typesense
    - Fetches fresh data from npm for each package
    - Validates packages still match profile keywords/scopes
    - Deletes the npm documents of packages that return 404 or no longer match
    - Preserves the enrichment fields (GitHub stats, npm scores) during refresh
    """
    from pyf.aggregator.db import TypesenceConnection, TypesensePackagesCollection

    class RefreshHelper(TypesenceConnection, TypesensePackagesCollection):
        """Connection plus the registry-aware collection operations."""

    helper = RefreshHelper()
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

            # Carry the enrichment-only fields (GitHub stats, npm scores) over
            # from the indexed documents - the upsert would drop them otherwise.
            preserved_fields = collect_preserved_fields(
                helper, collection_name, package_name
            )

            # Fetch each version's own README (the registry only serves the
            # latest version's readme). Done here in the parallel worker so the
            # CDN fetches run concurrently across packages.
            readmes = {
                version: agg.get_version_readme(package_name, version)
                for version in package_json.get("versions", {})
            }

            return ("update", package_name, package_json, preserved_fields, readmes)

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
                preserved_fields = result[3]
                readmes = result[4]
                packages_to_update.append(
                    (pkg_name, package_json, preserved_fields, readmes)
                )
            elif action == "error":
                error = result[2]
                stats["failed"] += 1
                logger.error(f"Error processing {pkg_name}: {error}")

    # Delete packages that no longer match. Only npm documents are removed -
    # a PyPI package published under the same name has to survive.
    for pkg_name in packages_to_delete:
        try:
            helper.delete_package_by_name(collection_name, pkg_name, registry="npm")
            stats["deleted"] += 1
            logger.info(f"Deleted package: {pkg_name}")
        except Exception as e:
            stats["failed"] += 1
            logger.error(f"Error deleting {pkg_name}: {e}")

    # Update packages with fresh data
    for pkg_name, package_json, preserved_fields, readmes in packages_to_update:
        try:
            batch = build_refresh_batch(
                agg, indexer, pkg_name, package_json, preserved_fields, readmes
            )

            if batch:
                # Drop the package's npm documents that are not part of this
                # batch: unpublished versions and documents written under an
                # older id scheme would otherwise linger as duplicates.
                fresh_ids = {doc["id"] for doc in batch}
                for stale_id in helper.get_package_document_ids(
                    collection_name, pkg_name, registry="npm"
                ):
                    if stale_id not in fresh_ids:
                        helper.client.collections[collection_name].documents[
                            stale_id
                        ].delete()
                        logger.info(f"Removed stale document: {stale_id}")

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

    # Register plugins. Refresh mode needs them too: without version_slicer the
    # documents lack the required version_* fields and Typesense rejects them.
    register_npm_plugins(settings)

    # Handle refresh mode separately
    if mode == "refresh":
        run_npm_refresh_mode(settings)
        return

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
