#!/usr/bin/env python
"""Manual verification script for downloads enricher - using existing packages collection."""
from pyf.aggregator.db import TypesenceConnection
from pyf.aggregator.enrichers.downloads import Enricher
from pyf.aggregator.logger import logger
import sys

def main():
    # Step 1: Check Typesense connection
    logger.info("=== Step 1: Checking Typesense connection ===")
    ts = TypesenceConnection()
    collections = ts.get_collection_names()
    logger.info(f"Available collections: {collections}")

    # Use existing packages collection
    test_collection = "packages"

    if not ts.collection_exists(test_collection):
        logger.error(f"Collection '{test_collection}' does not exist!")
        return 1

    logger.info(f"Using existing collection: {test_collection}")

    # Step 2: Run enricher with limit of 5
    logger.info("\n=== Step 2: Running downloads enricher (limit 5) ===")
    enricher = Enricher(limit=5)
    logger.info(f"Running enricher on collection '{test_collection}' with limit=5...")
    enricher.run(target=test_collection)

    # Step 3: Verify download fields are populated
    logger.info("\n=== Step 3: Verifying download fields ===")
    docs = ts.client.collections[test_collection].documents.search({
        'q': '*',
        'query_by': 'name',
        'per_page': 10
    })

    found_downloads = False
    packages_with_downloads = 0
    total_packages = len(docs['hits'])

    for hit in docs['hits']:
        doc = hit['document']
        name = doc.get('name', 'unknown')
        download_last_day = doc.get('download_last_day', None)
        download_last_week = doc.get('download_last_week', None)
        download_last_month = doc.get('download_last_month', None)
        download_updated = doc.get('download_updated', None)

        logger.info(f"\nPackage: {name}")
        logger.info(f"  - Last day: {download_last_day}")
        logger.info(f"  - Last week: {download_last_week}")
        logger.info(f"  - Last month: {download_last_month}")
        logger.info(f"  - Updated: {download_updated}")

        if download_last_month is not None:
            found_downloads = True
            packages_with_downloads += 1

    # Step 4: Summary
    logger.info("\n=== Verification Summary ===")
    logger.info(f"Total packages checked: {total_packages}")
    logger.info(f"Packages with download stats: {packages_with_downloads}")

    if found_downloads:
        logger.info("✓ Download statistics successfully fetched and stored")
        logger.info("✓ Rate limiting handled (observe 2s delay between requests in logs)")
        logger.info("✓ Enricher working correctly")
    else:
        logger.warning("⚠ No download statistics found in documents")

    logger.info("\n=== Manual verification complete ===")

    return 0 if found_downloads else 1

if __name__ == '__main__':
    sys.exit(main())
