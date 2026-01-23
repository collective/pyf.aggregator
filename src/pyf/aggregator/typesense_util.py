from argparse import ArgumentParser
from datetime import datetime
from dotenv import load_dotenv
from pyf.aggregator.db import TypesenceConnection, TypesensePackagesCollection, parse_versioned_name, get_next_version
from pyf.aggregator.logger import logger
from pyf.aggregator.profiles import ProfileManager
from pyf.aggregator.queue import app as celery_app
from pprint import pprint
from urllib.parse import urlparse

import os
import redis
import sys
import typesense

load_dotenv()

DEFAULT_PROFILE = os.getenv("DEFAULT_PROFILE")


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
    help="Profile name for collection operations (overrides DEFAULT_PROFILE env var)",
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
parser.add_argument(
    "--recreate-collection",
    help="Delete and recreate a collection with current schema (requires -t)",
    action="store_true",
)
parser.add_argument(
    "--delete-collection",
    help="Delete a collection by name (requires confirmation)",
    type=str,
    metavar="COLLECTION_NAME",
)
parser.add_argument(
    "-f", "--force",
    help="Skip confirmation prompts for destructive operations",
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
        response = self.client.collections[collection_name].documents.import_(
            data, {"action": "upsert"}
        )
        # Check for import errors
        if isinstance(response, list):
            errors = [r for r in response if not r.get("success", True)]
            if errors:
                logger.warning(f"Import had {len(errors)} failed documents")
                for err in errors[:5]:  # Log first 5 errors
                    logger.warning(f"  - {err}")
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

    def recreate_collection(self, name, delete_old=True):
        """
        Zero-downtime collection recreation with alias switching.

        1. If alias exists: migrate from old versioned collection to new one
        2. If no alias: create versioned collection and alias

        Args:
            name: The collection name (or alias name)
            delete_old: If True, delete the old collection after migration.
                        If False, keep it for manual deletion later.

        Returns:
            dict with 'old_collection' (name of old collection or None) and
            'new_collection' (name of newly created collection)
        """
        current_collection = self.get_alias(name)

        if current_collection:
            # Alias exists - do zero-downtime migration
            base_name, current_version = parse_versioned_name(current_collection)
            new_collection, new_version = get_next_version(base_name, current_version)

            logger.info(f"Creating new collection '{new_collection}' with current schema...")
            self.create_collection(name=new_collection)

            logger.info(f"Migrating data from '{current_collection}' to '{new_collection}'...")
            self.migrate(source=current_collection, target=new_collection)

            logger.info(f"Switching alias '{name}' to '{new_collection}'...")
            self.add_alias(source=name, target=new_collection)

            if delete_old:
                logger.info(f"Deleting old collection '{current_collection}'...")
                self.delete_collection(name=current_collection)
                logger.info(f"Collection recreation complete: {name} → {new_collection}")
            else:
                logger.info(f"Collection migration complete: {name} → {new_collection} (old collection kept)")

            return {"old_collection": current_collection, "new_collection": new_collection}
        else:
            # No alias - check if it's a direct collection
            if self.collection_exists(name):
                # Convert existing collection to versioned scheme
                logger.info(f"Converting '{name}' to versioned collection scheme...")
                new_collection = f"{name}-1"

                self.create_collection(name=new_collection)
                self.migrate(source=name, target=new_collection)
                self.add_alias(source=name, target=new_collection)

                if delete_old:
                    self.delete_collection(name=name)
                    logger.info(f"Converted: alias '{name}' → '{new_collection}'")
                else:
                    logger.info(f"Converted: alias '{name}' → '{new_collection}' (old collection kept)")

                return {"old_collection": name, "new_collection": new_collection}
            else:
                # Fresh start - create versioned collection with alias
                new_collection = f"{name}-1"
                logger.info(f"Creating new versioned collection '{new_collection}'...")
                self.create_collection(name=new_collection)
                self.add_alias(source=name, target=new_collection)
                logger.info(f"Created: alias '{name}' → '{new_collection}'")

                return {"old_collection": None, "new_collection": new_collection}


def main():
    args = parser.parse_args()

    # Handle profile (CLI argument or DEFAULT_PROFILE env var)
    effective_profile = args.profile or DEFAULT_PROFILE
    profile_source = "from CLI" if args.profile else "from DEFAULT_PROFILE"

    if effective_profile:
        profile_manager = ProfileManager()
        profile = profile_manager.get_profile(effective_profile)

        if not profile:
            available_profiles = profile_manager.list_profiles()
            logger.error(
                f"Profile '{effective_profile}' not found. "
                f"Available profiles: {', '.join(available_profiles)}"
            )
            sys.exit(1)

        if not profile_manager.validate_profile(effective_profile):
            logger.error(f"Profile '{effective_profile}' is invalid")
            sys.exit(1)

        # Auto-set target collection name from profile if not specified
        if not args.target:
            args.target = effective_profile
            logger.info(f"Auto-setting target collection from profile: {args.target}")

        logger.info(f"Using profile '{effective_profile}' ({profile_source})")

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
        and not args.recreate_collection
        and args.delete_collection is None
    ):
        logger.info(
            f" No action provided, provide at least one action: "
            f"--migrate, --add_alias, --list-aliases, --list-collections, "
            f"--list-collection-names, --add-search-only-apikey, --delete-apikey, "
            f"--purge-queue, --queue-stats, --recreate-collection, --delete-collection"
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
    if args.recreate_collection:
        if not args.target:
            logger.error(
                "Target collection name is required. "
                "Use -t <collection_name>, -p <profile_name>, or set DEFAULT_PROFILE env var"
            )
            sys.exit(1)

        # Run migration first (no confirmation needed), then ask about deletion
        result = ts_util.recreate_collection(name=args.target, delete_old=False)

        # Confirmation for deletion (unless --force)
        if result.get("old_collection"):
            if args.force:
                ts_util.delete_collection(name=result["old_collection"])
                logger.info(f"Deleted old collection '{result['old_collection']}'")
            else:
                confirm = input(
                    f"Delete old collection '{result['old_collection']}'? (Y/n): "
                )
                if confirm.lower() != 'n':  # Default is Yes
                    ts_util.delete_collection(name=result["old_collection"])
                    logger.info(f"Deleted old collection '{result['old_collection']}'")
                else:
                    logger.info(f"Kept old collection '{result['old_collection']}'")

    if args.delete_collection:
        collection_name = args.delete_collection

        # Check if collection exists
        if not ts_util.collection_exists(collection_name):
            # Check if it's an alias
            alias_target = ts_util.get_alias(collection_name)
            if alias_target:
                logger.error(
                    f"'{collection_name}' is an alias pointing to '{alias_target}'. "
                    f"Use --delete-collection {alias_target} to delete the actual collection."
                )
            else:
                logger.error(f"Collection '{collection_name}' does not exist")
            sys.exit(1)

        # Warn about aliases pointing to this collection
        aliases = ts_util.get_aliases()
        pointing_aliases = [
            alias.get("name")
            for alias in aliases.get("aliases", [])
            if alias.get("collection_name") == collection_name
        ]
        if pointing_aliases:
            logger.warning(
                f"The following aliases point to '{collection_name}': {', '.join(pointing_aliases)}"
            )
            logger.warning("These aliases will become orphaned after deletion.")

        # Confirmation (unless --force)
        if not args.force:
            confirm = input(f"Are you sure you want to delete collection '{collection_name}'? (y/N): ")
            if confirm.lower() != 'y':
                logger.info("Delete operation cancelled")
                sys.exit(0)

        # Perform deletion
        try:
            result = ts_util.delete_collection(collection_name)
            logger.info(f"Successfully deleted collection '{collection_name}'")
            pprint(result)
        except typesense.exceptions.ObjectNotFound:
            logger.error(f"Collection '{collection_name}' not found")
            sys.exit(1)
        except Exception as e:
            logger.error(f"Failed to delete collection '{collection_name}': {e}")
            sys.exit(1)
