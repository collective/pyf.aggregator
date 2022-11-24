from argparse import ArgumentParser
from datetime import datetime
from pyf.aggregator.db import TypesenceConnection, TypesensePackagesCollection
from pyf.aggregator.logger import logger
from pprint import pprint


parser = ArgumentParser(
    description="updates/migrates typesense collections and export/import documents"
)
parser.add_argument("-ls", "--list-collections", action="store_true")
parser.add_argument("-lsn", "--list-collection-names", action="store_true")
parser.add_argument("-lsa", "--list-aliases", action="store_true")
parser.add_argument("-lssoa", "--list-search-only-apikeys", action="store_true")
parser.add_argument("-s", "--source", nargs="?", type=str, default="")
parser.add_argument("-t", "--target", nargs="?", type=str, default="")
parser.add_argument(
    "--migrate",
    help="Migrate data of source collection to target collection",
    action="store_true",
)
parser.add_argument(
    "--add-alias",
    help="Add collection alias, instead of migrating",
    action="store_true",
)
parser.add_argument(
    "--add-search-only-apikey",
    help="Add a search only API key, for given collection filter",
    nargs="?",
    type=str,
)


class TypesenceUtil(TypesenceConnection, TypesensePackagesCollection):
    """
    migrate typesence collection data from one collection into another
    """

    def migrate(self, source=None, target=None):
        """ """
        data = self.export_data(collection_name=source)
        if not self.collection_exists(target):
            logger.info(
                f"no target collection with the name {target} found, create one."
            )
            self.create_collection(name=target)
        self.import_data(collection_name=target, data=data)

    def export_data(self, collection_name=None):
        logger.info(
            f"[{datetime.now()}] exporting data from typesense collection '{collection_name}' ..."
        )
        data = self.client.collections[collection_name].documents.export()
        logger.info(f"[{datetime.now()}] done.")
        return data

    def import_data(self, collection_name, data):
        logger.info(
            f"[{datetime.now()}] importing data into typesense collection '{collection_name}' ..."
        )
        self.client.collections[collection_name].documents.import_(
            data.encode("utf-8"), {"action": "create"}
        )
        logger.info(f"[{datetime.now()}] done.")

    def add_alias(self, source=None, target=None):
        aliased_collection = {"collection_name": target}
        self.client.aliases.upsert(source, aliased_collection)
        logger.info(f"add collection alias: [{source}] => [{target}]")

    def add_search_only_apikey(self, collection_filter):
        key = self.client.keys.create(
            {
                "description": "Search-only companies key.",
                "actions": ["*"],
                "collections": [
                    collection_filter,
                ],
            }
        )
        logger.info(f"add search only API key, with collection filter: {collection_filter}")
        print(key)


def main():
    args = parser.parse_args()
    ts_util = TypesenceUtil()
    if (
        not args.migrate
        and not args.add_alias
        and not args.list_collections
        and not args.list_collection_names
        and not args.list_aliases
        and not args.list_search_only_apikeys
        and not args.add_search_only_apikey
    ):
        logger.info(
            f" No action provided, provide at least one action: "
            f"--migrate, --add_alias, --list-aliases, ---list-collections, "
            f"--list-collection-names, --add-search-only-apikey"
        )
    if args.list_search_only_apikeys:
        keys = ts_util.get_search_only_apikeys()
        pprint(keys)
    if args.list_aliases:
        aliases = ts_util.get_aliases()
        pprint(aliases)
    if args.list_collections:
        collections = ts_util.get_collections()
        pprint(collections)
    if args.list_collection_names:
        collections = ts_util.get_collection_names()
        pprint(collections)
    if args.migrate:
        ts_util.migrate(target=args.target, source=args.source)
    if args.add_alias:
        ts_util.add_alias(source=args.source, target=args.target)
    if args.add_search_only_apikey:
        ts_util.add_search_only_apikey(collection_filter=args.add_search_only_apikey)
