#!/usr/bin/env python
"""Migration script to fix version_sortable format.

After deploying commit f15d6d5, --refresh-from-pypi only updates the latest version
of each package. Older versions in Typesense still have the old version_sortable
format (e.g., "2.1.0.2.0") which sorts incorrectly relative to the new zero-padded
format (e.g., "0002.0001.0003.0002.0000").

This script iterates through ALL documents in a collection and recalculates
version_sortable with the new zero-padded format.

Usage:
    # Dry run (shows what would be updated without making changes)
    uv run python migrate_version_sortable.py --collection plone --dry-run

    # Execute migration
    uv run python migrate_version_sortable.py --collection plone

    # With verbose output
    uv run python migrate_version_sortable.py --collection plone -v

DELETE THIS SCRIPT after migration is complete.
"""

import argparse
import os
import re
import sys

import typesense
from dotenv import load_dotenv

load_dotenv()

# Same regex as version_slicer.py
VERSION_REGEX = re.compile(
    r"^(?P<major>\d*)\.(?P<minor>\d*)\.?(?P<postfix1>[a-zA-Z]+\d*)?(?P<bugfix>\d)?(?P<postfix2>[a-zA-Z]+\d*)?$",
    re.MULTILINE | re.IGNORECASE,
)


def make_version_sortable(groups):
    """Return a zero-padded sortable string from version components.

    Format: MAJOR.MINOR.BUGFIX.PRERELEASE_TYPE.PRERELEASE_NUM
    - PRERELEASE_TYPE: 0000=alpha, 0001=beta, 0002=stable
    - Each segment is zero-padded to 4 digits for correct lexicographic sort.
    """
    postfix = groups.get("postfix1") or groups.get("postfix2") or ""
    major = groups.get("major", "0") or "0"
    minor = groups.get("minor", "0") or "0"
    bugfix = groups.get("bugfix", "0") or "0"

    # Map pre-release type to sortable number
    if postfix.startswith("a"):
        pre_type = "0000"
        pre_num = "".join(c for c in postfix if c.isdigit()) or "0"
    elif postfix.startswith("b"):
        pre_type = "0001"
        pre_num = "".join(c for c in postfix if c.isdigit()) or "0"
    else:
        pre_type = "0002"
        pre_num = "0"

    return f"{major.zfill(4)}.{minor.zfill(4)}.{bugfix.zfill(4)}.{pre_type}.{pre_num.zfill(4)}"


def get_typesense_client():
    """Create Typesense client from environment variables."""
    return typesense.Client(
        {
            "nodes": [
                {
                    "host": os.getenv("TYPESENSE_HOST"),
                    "port": os.getenv("TYPESENSE_PORT"),
                    "protocol": os.getenv("TYPESENSE_PROTOCOL"),
                }
            ],
            "api_key": os.getenv("TYPESENSE_API_KEY"),
            "connection_timeout_seconds": int(os.getenv("TYPESENSE_TIMEOUT", "300")),
        }
    )


def is_old_format(version_sortable):
    """Check if version_sortable uses the old non-padded format."""
    if not version_sortable:
        return True
    parts = version_sortable.split(".")
    # New format has 5 parts, each with 4 digits (zero-padded)
    if len(parts) != 5:
        return True
    return any(len(part) != 4 for part in parts)


def migrate_collection(collection_name, dry_run=False, verbose=False):
    """Migrate all documents in a collection to use new version_sortable format."""
    client = get_typesense_client()

    # Verify collection exists
    try:
        client.collections[collection_name].retrieve()
    except typesense.exceptions.ObjectNotFound:
        print(f"Error: Collection '{collection_name}' not found.")
        sys.exit(1)

    stats = {"total": 0, "updated": 0, "skipped": 0, "errors": 0}
    page = 1
    per_page = 250

    print(f"{'[DRY RUN] ' if dry_run else ''}Migrating collection: {collection_name}")
    print("-" * 60)

    while True:
        # Fetch documents page by page
        result = client.collections[collection_name].documents.search(
            {
                "q": "*",
                "query_by": "name",
                "include_fields": "id,name,version,version_sortable",
                "per_page": per_page,
                "page": page,
            }
        )

        hits = result.get("hits", [])
        if not hits:
            break

        for hit in hits:
            doc = hit.get("document", {})
            stats["total"] += 1

            doc_id = doc.get("id")
            name = doc.get("name")
            version = doc.get("version")
            old_sortable = doc.get("version_sortable", "")

            # Skip if already in new format
            if not is_old_format(old_sortable):
                stats["skipped"] += 1
                if verbose:
                    print(f"  SKIP: {name} {version} (already new format: {old_sortable})")
                continue

            # Parse version and calculate new sortable
            if not version:
                stats["errors"] += 1
                if verbose:
                    print(f"  ERROR: {name} - no version field")
                continue

            vmatch = VERSION_REGEX.search(version)
            if not vmatch:
                stats["errors"] += 1
                if verbose:
                    print(f"  ERROR: {name} {version} - version doesn't match regex")
                continue

            groups = vmatch.groupdict()
            new_sortable = make_version_sortable(groups)

            # Update document if format changed
            if old_sortable != new_sortable:
                if verbose:
                    print(f"  UPDATE: {name} {version}: {old_sortable} -> {new_sortable}")

                if not dry_run:
                    try:
                        client.collections[collection_name].documents[doc_id].update(
                            {"version_sortable": new_sortable}
                        )
                        stats["updated"] += 1
                    except Exception as e:
                        stats["errors"] += 1
                        print(f"  ERROR updating {name} {version}: {e}")
                else:
                    stats["updated"] += 1
            else:
                stats["skipped"] += 1

        # Progress indicator for large collections
        if not verbose and stats["total"] % 1000 == 0:
            print(f"  Processed {stats['total']} documents...")

        page += 1

    # Print summary
    print("-" * 60)
    print(f"{'[DRY RUN] ' if dry_run else ''}Migration complete!")
    print(f"  Total documents: {stats['total']}")
    print(f"  Updated: {stats['updated']}")
    print(f"  Skipped (already new format): {stats['skipped']}")
    print(f"  Errors: {stats['errors']}")

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Migrate version_sortable to new zero-padded format"
    )
    parser.add_argument(
        "--collection",
        "-c",
        required=True,
        help="Typesense collection name to migrate",
    )
    parser.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        help="Show what would be updated without making changes",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show detailed output for each document",
    )

    args = parser.parse_args()

    migrate_collection(args.collection, dry_run=args.dry_run, verbose=args.verbose)


if __name__ == "__main__":
    main()
