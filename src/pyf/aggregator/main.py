from .fetcher import Aggregator
from .fetcher import PLUGINS
from .fetcher import PLONE_CLASSIFIER
from .indexer import Indexer
from .plugins import register_plugins
from .profiles import ProfileManager
from argparse import ArgumentParser
from pyf.aggregator.logger import logger

import sys


COLLECTION_NAME = "packages1"


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
    help="Profile name for classifier filtering",
    nargs="?",
    type=str
)


def main():
    args = parser.parse_args()

    # Validate mode flags - must specify exactly one of -f or -i
    if args.first and args.incremental:
        logger.error("Cannot specify both -f (--first) and -i (--incremental). Choose one.")
        sys.exit(1)

    if not args.first and not args.incremental:
        logger.error("Must specify either -f (--first) for full download or -i (--incremental) for updates.")
        parser.print_help()
        sys.exit(1)

    # Validate target collection is specified
    if not args.target:
        logger.error("Target collection name is required. Use -t <collection_name>")
        sys.exit(1)

    # Determine mode
    mode = "incremental" if args.incremental else "first"

    # Build filter_troove list
    # If profile is specified, load classifiers from profile
    # Otherwise, use default Plone filtering logic
    if args.profile:
        profile_manager = ProfileManager()
        profile = profile_manager.get_profile(args.profile)

        if not profile:
            available_profiles = profile_manager.list_profiles()
            logger.error(
                f"Profile '{args.profile}' not found. "
                f"Available profiles: {', '.join(available_profiles)}"
            )
            sys.exit(1)

        if not profile_manager.validate_profile(args.profile):
            logger.error(f"Profile '{args.profile}' is invalid")
            sys.exit(1)

        filter_troove = profile["classifiers"]
        logger.info(f"Using profile '{args.profile}' with {len(filter_troove)} classifiers")
    else:
        # Default behavior: filter for Plone packages unless --no-plone-filter is specified
        filter_troove = list(args.filter_troove) if args.filter_troove else []
        if not args.no_plone_filter and PLONE_CLASSIFIER not in filter_troove:
            filter_troove.append(PLONE_CLASSIFIER)
            logger.info(f"Filtering for packages with classifier: {PLONE_CLASSIFIER}")

        if args.no_plone_filter:
            logger.warning("Plone classifier filtering disabled. Processing ALL packages.")

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

    agg = Aggregator(
        mode,
        sincefile=settings["sincefile"],
        filter_name=settings["filter_name"],
        filter_troove=settings["filter_troove"],
        limit=settings["limit"],
    )

    indexer = Indexer()
    if not indexer.collection_exists(name=settings["target"]):
        logger.info(
            f"Target collection '{settings['target']}' not found, creating it."
        )
        indexer.create_collection(name=settings["target"])

    # Execute the aggregation flow
    indexer(agg, settings['target'])

    logger.info(f"Aggregation complete for collection: {settings['target']}")


if __name__ == "__main__":
    main()
