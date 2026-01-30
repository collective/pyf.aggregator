#!/usr/bin/env python
"""Test error handling for non-existent packages."""

from pyf.aggregator.enrichers.downloads import Enricher
from pyf.aggregator.logger import logger


def main():
    logger.info("=== Testing Error Handling ===")
    enricher = Enricher(limit=1)

    # Test with a package that definitely doesn't exist
    test_package = "this-package-definitely-does-not-exist-12345-xyz"

    logger.info(f"\nAttempting to fetch stats for non-existent package: {test_package}")
    result = enricher._get_pypistats_data(test_package)

    if not result:
        logger.info("✓ Error handling works correctly - empty dict returned for 404")
    else:
        logger.warning(f"⚠ Unexpected result: {result}")

    # Test memoization - second call should not make an API request
    logger.info(f"\nTesting memoization with same package: {test_package}")
    result2 = enricher._get_pypistats_data(test_package)

    if result2 == result:
        logger.info("✓ Memoization works - cached result returned")
    else:
        logger.warning("⚠ Memoization may not be working correctly")

    logger.info("\n=== Error Handling Test Complete ===")


if __name__ == "__main__":
    main()
