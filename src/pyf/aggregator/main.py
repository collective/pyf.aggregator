from pyf.aggregator.fetcher import Aggregator
from pyf.aggregator.indexer import Indexer

from pyf.aggregator.logger import logger


def main():
    logger.info("Start ...")
    agg = Aggregator(limit=100, name_filter="collective")
    indexer = Indexer()
    indexer(agg)


if __name__ == "__main__":
    main()
