from .fetcher import Aggregator
from .fetcher import PLUGINS
from .indexer import Indexer
from .plugins import register_plugins
from argparse import ArgumentParser
from pyf.aggregator.logger import logger


COLLECTION_NAME = "packages1"


parser = ArgumentParser(
    description="Fetch information about pinned versions and its overrides in "
    "simple and complex/cascaded buildouts."
)
parser.add_argument("-f", "--first", help="First fetch from PyPI", action="store_true")
parser.add_argument(
    "-i", "--incremental", help="Incremental fetch from PyPI", action="store_true"
)
parser.add_argument(
    "-s",
    "--sincefile",
    help="File with timestamp of last run",
    nargs="?",
    type=str,
    default=".pyaggregator.since",
)
parser.add_argument("-l", "--limit", nargs="?", type=int, default=0)
parser.add_argument("-fn", "--filter-name", nargs="?", type=str, default="")
parser.add_argument("-ft", "--filter-troove", action="append", default=[])
parser.add_argument(
    "-t", "--target", help="target collection name", nargs="?", type=str
)


def main():
    args = parser.parse_args()
    mode = "incremental" if args.incremental else "first"
    settings = {
        "mode": mode,
        "sincefile": args.sincefile,
        "filter_name": args.filter_name,
        "filter_troove": args.filter_troove,
        "limit": args.limit,
        "target": args.target,
    }

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
            f"no target collection with the name {settings['target']} found, create one."
        )
        indexer.create_collection(name=settings["target"])
    indexer(agg)


if __name__ == "__main__":
    main()
