from .fetcher import Aggregator
from .fetcher import PLUGINS
from .indexer import Indexer
from .plugins import register_plugins
from argparse import ArgumentParser

import time


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
parser.add_argument("-n", "--filter-name", nargs="?", type=str, default="")
parser.add_argument("-t", "--filter-troove", action="append", default=[])

parser.add_argument(
    "--github-token",
    help="Github OAuth token",
    nargs="?",
    type=str,
    default="",
)

parser.add_argument(
    "--skip-github",
    help="Don't call Github for meta data",
    action="store_true"
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
        "github_token": args.github_token,
        "skip_github": args.skip_github,
    }

    register_plugins(PLUGINS, settings)

    agg = Aggregator(
        mode,
        sincefile=settings["sincefile"],
        filter_name=settings["filter_name"],
        filter_troove=settings["filter_troove"],
        skip_github=settings["skip_github"],
        limit=settings["limit"],
    )
    indexer = Indexer()
    indexer(agg)


if __name__ == "__main__":
    main()
