# -*- coding: utf-8 -*-
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
parser.add_argument(
    "-t",
    "--token",
    help="Github OAuth token",
    nargs="?",
    type=str,
    default="",
)
parser.add_argument("--filter-name", nargs="?", type=str, default="")
parser.add_argument("--filter-troove", nargs="?", type=str, default="")
parser.add_argument("--limit", nargs="?", type=int, default=0)


def main():
    args = parser.parse_args()
    mode = "incremental" if args.incremental else "first"
    settings = {
        "mode": mode,
        "sincefile": args.sincefile,
        "name_filter": args.filter_name,
        "troove_filter": args.filter_troove,
        "limit": args.limit,
        "github_token": args.token,
    }

    register_plugins(PLUGINS, settings)

    agg = Aggregator(
        mode,
        sincefile=settings["sincefile"],
        name_filter=settings["name_filter"],
        troove_filter=settings["troove_filter"],
        limit=settings["limit"],
    )
    indexer = Indexer()
    indexer(agg)


if __name__ == "__main__":
    main()
