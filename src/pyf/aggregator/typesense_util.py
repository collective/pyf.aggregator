from argparse import ArgumentParser
from datetime import datetime
from pyf.aggregator.db import TypesenceConnection, TypesensePackagesCollection
from pyf.aggregator.logger import logger
from pyf.aggregator.profiles import ProfileManager
from pyf.aggregator.queue import app as celery_app
from pprint import pprint
from urllib.parse import urlparse

import os
import redis
import sys


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
    action="store_true",
)
parser.add_argument(
    "--delete-apikey",
    help="Delete an API key by its ID",
    type=int,
)

parser.add_argument(
    "-key",
    "--key",
    help="key to be used, if missing we will generate one",
    nargs="?",
    default="gen",
    type=str,
)
parser.add_argument(
    "-p", "--profile",
    help="Profile name for collection operations",
    nargs="?",
    type=str
)
parser.add_argument(
    "--purge-queue",
    help="Purge all pending tasks from the Celery queue",
    action="store_true",
)
parser.add_argument(
    "--queue-stats",
    help="Show Celery queue statistics (pending tasks, workers)",
    action="store_true",
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

    def add_search_only_apikey(self, collection_filter, key=None):
        q = {
                "description": "Search-only key.",
                "actions": ["documents:search"],
                "collections": [
                    collection_filter,
                ],
        }
        if key:
            q["value"] = key
        res_key = self.client.keys.create(q)
        logger.info(f"add search only API key {key}, with collection filter: {collection_filter}")
        print(f"res_key: {res_key}")

    def delete_apikey(self, key_id):
        res = self.client.keys[key_id].delete()
        logger.info(f"Deleted API key with ID: {key_id}")
        return res


def main():
    args = parser.parse_args()

    # Handle profile-based target collection
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

        # Auto-set target collection name from profile if not specified
        if not args.target:
            args.target = args.profile
            logger.info(f"Auto-setting target collection from profile: {args.target}")

        logger.info(f"Using profile '{args.profile}'")

    ts_util = TypesenceUtil()
    if (
        not args.migrate
        and not args.add_alias
        and not args.list_collections
        and not args.list_collection_names
        and not args.list_aliases
        and not args.list_search_only_apikeys
        and not args.add_search_only_apikey
        and args.delete_apikey is None
        and not args.purge_queue
        and not args.queue_stats
    ):
        logger.info(
            f" No action provided, provide at least one action: "
            f"--migrate, --add_alias, --list-aliases, --list-collections, "
            f"--list-collection-names, --add-search-only-apikey, --delete-apikey, "
            f"--purge-queue, --queue-stats"
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
        if args.key != "gen":
            key = args.key
        else:
            key = None
        ts_util.add_search_only_apikey(collection_filter=args.target, key=key)
    if args.delete_apikey is not None:
        result = ts_util.delete_apikey(key_id=args.delete_apikey)
        pprint(result)
    if args.queue_stats:
        # Get Redis queue length (pending tasks)
        redis_url = os.getenv('REDIS_HOST', 'redis://localhost:6379')
        parsed = urlparse(redis_url)
        r = redis.Redis(host=parsed.hostname or 'localhost', port=parsed.port or 6379, db=0)
        pending_count = r.llen('celery')

        print("Queue Statistics:")
        print("-" * 40)
        print(f"\nPending tasks in queue: {pending_count}")

        # Worker stats
        inspect = celery_app.control.inspect()
        active = inspect.active()
        scheduled = inspect.scheduled()
        reserved = inspect.reserved()

        if active:
            for worker, tasks in active.items():
                print(f"\nWorker: {worker}")
                print(f"  Active tasks: {len(tasks)}")
                for task in tasks:
                    print(f"    - {task.get('name', 'unknown')} [{task.get('id', '')[:8]}...]")
        else:
            print("\n  No active workers connected")

        if scheduled:
            print("\nScheduled tasks:")
            for worker, tasks in scheduled.items():
                print(f"  {worker}: {len(tasks)} tasks")
                for task in tasks:
                    req = task.get('request', {})
                    print(f"    - {req.get('name', 'unknown')}")
        else:
            print("\n  No scheduled tasks")

        if reserved:
            print("\nReserved tasks:")
            for worker, tasks in reserved.items():
                print(f"  {worker}: {len(tasks)} tasks")
                for task in tasks:
                    print(f"    - {task.get('name', 'unknown')}")
        else:
            print("\n  No reserved tasks")
    if args.purge_queue:
        confirm = input("Are you sure you want to purge all pending tasks? (y/N): ")
        if confirm.lower() == 'y':
            num_purged = celery_app.control.purge()
            logger.info(f"Purged {num_purged} pending tasks from queue")
        else:
            logger.info("Purge cancelled")
