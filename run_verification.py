#!/usr/bin/env python
"""Manual verification script for downloads enricher."""

from pyf.aggregator.db import TypesenceConnection, TypesensePackagesCollection
from pyf.aggregator.enrichers.downloads import Enricher
from pyf.aggregator.logger import logger
import sys


def main():
    # Step 1: Check Typesense connection
    logger.info("=== Step 1: Checking Typesense connection ===")

    # Use both base classes for full functionality
    class TSUtil(TypesenceConnection, TypesensePackagesCollection):
        pass

    ts = TSUtil()
    collections = ts.get_collection_names()
    logger.info(f"Available collections: {collections}")

    # Step 2: Create or use test collection
    logger.info("\n=== Step 2: Setting up test collection ===")
    test_collection = "test_downloads"

    if not ts.collection_exists(test_collection):
        logger.info(f"Creating test collection: {test_collection}")
        ts.create_collection(name=test_collection)

        # Add a few test packages
        logger.info("Adding test packages...")
        test_packages = [
            {
                "id": "requests",
                "name": "requests",
                "version": "2.31.0",
                "summary": "HTTP library for Python",
                "license": "Apache-2.0",
            },
            {
                "id": "django",
                "name": "django",
                "version": "5.0.0",
                "summary": "High-level Python web framework",
                "license": "BSD",
            },
            {
                "id": "flask",
                "name": "flask",
                "version": "3.0.0",
                "summary": "Lightweight WSGI web application framework",
                "license": "BSD-3-Clause",
            },
            {
                "id": "nonexistent-pkg-test-12345",
                "name": "nonexistent-pkg-test-12345",
                "version": "1.0.0",
                "summary": "This package does not exist",
                "license": "MIT",
            },
        ]

        for pkg in test_packages:
            ts.client.collections[test_collection].documents.create(pkg)
        logger.info(f"Added {len(test_packages)} test packages")
    else:
        logger.info(f"Test collection already exists: {test_collection}")

    # Step 3: Run enricher with limit
    logger.info("\n=== Step 3: Running downloads enricher ===")
    enricher = Enricher()
    enricher.run(target=test_collection, limit=5)

    # Step 4: Verify download fields are populated
    logger.info("\n=== Step 4: Verifying download fields ===")
    docs = ts.client.collections[test_collection].documents.search(
        {"q": "*", "query_by": "name", "per_page": 10}
    )

    found_downloads = False
    for hit in docs["hits"]:
        doc = hit["document"]
        name = doc.get("name", "unknown")
        download_last_day = doc.get("download_last_day", "N/A")
        download_last_week = doc.get("download_last_week", "N/A")
        download_last_month = doc.get("download_last_month", "N/A")

        logger.info(f"\nPackage: {name}")
        logger.info(f"  - Last day: {download_last_day}")
        logger.info(f"  - Last week: {download_last_week}")
        logger.info(f"  - Last month: {download_last_month}")

        if download_last_month != "N/A":
            found_downloads = True

    # Step 5: Summary
    logger.info("\n=== Verification Summary ===")
    if found_downloads:
        logger.info("✓ Download statistics successfully fetched and stored")
    else:
        logger.warning("⚠ No download statistics found in documents")

    logger.info("\n=== Manual verification complete ===")
    logger.info(f"Collection '{test_collection}' is ready for inspection")
    logger.info("You can query it using Typesense UI or API")

    return 0 if found_downloads else 1


if __name__ == "__main__":
    sys.exit(main())
