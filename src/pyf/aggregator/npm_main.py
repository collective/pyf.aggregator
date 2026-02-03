"""
CLI entry point for npm package aggregation.

Usage:
    pyfnpm -f -t plone -p plone           # Full download using plone profile
    pyfnpm -f -t plone -p plone -l 10     # Full download, limit to 10 packages
    pyfnpm --show @plone/volto -t plone   # Show indexed data for a package
"""

from argparse import ArgumentParser
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
    modes = [args.first, args.incremental]
    if sum(modes) != 1:
        logger.error("Must specify exactly one of -f (full) or -i (incremental)")
        parser.print_help()
        sys.exit(1)

    mode = "first" if args.first else "incremental"

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
    }

    logger.info(f"Starting npm aggregation in '{mode}' mode")
    logger.info(f"Target collection: {settings['target']}")
    if settings["limit"]:
        logger.info(f"Limiting to {settings['limit']} packages")

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
