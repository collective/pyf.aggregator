# -*- coding: utf-8 -*-
from argparse import ArgumentParser
from pyf.aggregator.fetcher import Aggregator
from pyf.aggregator.indexer import Indexer

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
parser.add_argument("--filter", nargs="?", type=str, default="")
parser.add_argument("--limit", nargs="?", type=int, default=0)


def main():
    args = parser.parse_args()
    mode = "incremental" if args.incremental else "first"
    agg = Aggregator(
        mode, sincefile=args.sincefile, name_filter=args.filter, limit=args.limit
    )
    indexer = Indexer()
    indexer(agg)


if __name__ == "__main__":
    main()
