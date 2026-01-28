"""
Integration tests for version_sortable schema and sorting.

This module tests:
- Zero-padded version_sortable format generation
- Correct indexing of version_sortable in Typesense
- Proper lexicographic sorting of versions in Typesense queries
- Pre-release version ordering (alpha < beta < stable)
"""

import time
import pytest
import typesense
from typesense.exceptions import ObjectNotFound

from pyf.aggregator.plugins.version_slicer import make_version_sortable, process
from pyf.aggregator.db import TypesenceConnection, TypesensePackagesCollection


# ============================================================================
# Test Data
# ============================================================================

# Test versions and their expected version_sortable values
# Format: STABLE.MAJOR.MINOR.BUGFIX.PRETYPE.PRENUM
# STABLE=1 for stable releases, 0 for pre-releases
VERSION_TEST_DATA = [
    ("1.0.3", "1.0001.0000.0003.0000.0000"),
    ("2.1.2", "1.0002.0001.0002.0000.0000"),
    ("2.1.3", "1.0002.0001.0003.0000.0000"),
    ("2.1.5", "1.0002.0001.0005.0000.0000"),
    ("12.5.9", "1.0012.0005.0009.0000.0000"),
]

# Expected ascending sort order for test versions
EXPECTED_SORT_ORDER_ASC = ["1.0.3", "2.1.2", "2.1.3", "2.1.5", "12.5.9"]

# Pre-release test data
# STABLE=0 for pre-releases, PRETYPE: alpha=0001, beta=0002, rc=0003, dev=0000
PRERELEASE_TEST_DATA = [
    ("2.0.0a1", "0.0002.0000.0000.0001.0001"),  # alpha
    ("2.0.0b1", "0.0002.0000.0000.0002.0001"),  # beta
    ("2.0.0", "1.0002.0000.0000.0000.0000"),    # stable
]

# Ascending order: pre-releases first (by type: alpha < beta), then stable
PRERELEASE_SORT_ORDER_ASC = ["2.0.0a1", "2.0.0b1", "2.0.0"]


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def check_typesense_available():
    """Skip test if Typesense is not available."""
    try:
        conn = TypesenceConnection()
        conn.client.health.retrieve()
    except Exception as e:
        pytest.skip(f"Typesense not available: {e}")


@pytest.fixture
def typesense_client(check_typesense_available):
    """Create a real Typesense client connection."""
    conn = TypesenceConnection()
    return conn.client


@pytest.fixture
def test_collection(typesense_client):
    """Create a temporary test collection with cleanup."""
    collection_name = f"test_version_sortable_{int(time.time() * 1000)}"

    # Minimal schema for version sorting tests
    schema = {
        "name": collection_name,
        "fields": [
            {"name": "identifier", "type": "string"},
            {"name": "name", "type": "string"},
            {"name": "version", "type": "string"},
            {"name": "version_sortable", "type": "string", "sort": True},
            {"name": "version_major", "type": "int32", "sort": True},
            {"name": "version_minor", "type": "int32", "sort": True},
            {"name": "version_bugfix", "type": "int32", "sort": True},
        ],
    }

    typesense_client.collections.create(schema)

    yield collection_name

    # Cleanup
    try:
        typesense_client.collections[collection_name].delete()
    except ObjectNotFound:
        pass  # Already deleted


@pytest.fixture
def create_test_package():
    """Factory for creating minimal test package data."""
    def _create(name: str, version: str) -> dict:
        data = {
            "identifier": f"{name}-{version}",
            "name": name,
            "version": version,
        }
        # Apply version_slicer plugin to set version_sortable
        process(data["identifier"], data)
        return data

    return _create


# ============================================================================
# Unit Tests: version_sortable Format
# ============================================================================

class TestVersionSortableFormat:
    """Unit tests for zero-padded version_sortable format generation."""

    @pytest.mark.parametrize("version,expected", VERSION_TEST_DATA)
    def test_version_sortable_format(self, version, expected):
        """Test that version_sortable has correct zero-padded format."""
        data = {"version": version}
        process("test-pkg", data)

        assert data.get("version_sortable") == expected, \
            f"Version {version} should produce {expected}, got {data.get('version_sortable')}"

    @pytest.mark.parametrize("version,expected", VERSION_TEST_DATA)
    def test_all_segments_have_correct_format(self, version, expected):
        """Verify version_sortable has 6 segments with correct padding.

        Format: STABLE.MAJOR.MINOR.BUGFIX.PRETYPE.PRENUM
        - STABLE: 1 digit (0 or 1)
        - All other segments: 4 digits zero-padded
        """
        data = {"version": version}
        process("test-pkg", data)

        sortable = data.get("version_sortable")
        segments = sortable.split(".")

        assert len(segments) == 6, \
            f"Expected 6 segments, got {len(segments)}: {sortable}"

        # First segment (stable flag) is 1 digit
        assert len(segments[0]) == 1, \
            f"Stable flag should be 1 digit: {segments[0]}"
        assert segments[0] in ("0", "1"), \
            f"Stable flag should be 0 or 1: {segments[0]}"

        # Remaining segments are 4 digits each
        for i, segment in enumerate(segments[1:], start=1):
            assert len(segment) == 4, \
                f"Segment {i} should be 4 digits: {segment}"
            assert segment.isdigit(), \
                f"Segment {i} should be all digits: {segment}"

    @pytest.mark.parametrize("version,expected", PRERELEASE_TEST_DATA)
    def test_prerelease_version_sortable_format(self, version, expected):
        """Test that pre-release versions produce correct version_sortable."""
        data = {"version": version}
        process("test-pkg", data)

        assert data.get("version_sortable") == expected, \
            f"Version {version} should produce {expected}, got {data.get('version_sortable')}"


# ============================================================================
# Integration Tests: Indexing
# ============================================================================

@pytest.mark.integration
class TestVersionSortableIndexing:
    """Integration tests for version_sortable indexing in Typesense."""

    def test_documents_indexed_with_correct_version_sortable(
        self, typesense_client, test_collection, create_test_package
    ):
        """Verify that indexed documents have correct version_sortable values."""
        # Index test packages
        for version, expected_sortable in VERSION_TEST_DATA:
            pkg = create_test_package("test-pkg", version)
            typesense_client.collections[test_collection].documents.upsert(pkg)

        # Verify each document
        for version, expected_sortable in VERSION_TEST_DATA:
            doc_id = f"test-pkg-{version}"
            doc = typesense_client.collections[test_collection].documents[doc_id].retrieve()

            assert doc["version_sortable"] == expected_sortable, \
                f"Document for {version} has wrong version_sortable: {doc['version_sortable']}"

    def test_prerelease_documents_indexed_correctly(
        self, typesense_client, test_collection, create_test_package
    ):
        """Verify that pre-release documents have correct version_sortable values."""
        for version, expected_sortable in PRERELEASE_TEST_DATA:
            pkg = create_test_package("test-pkg", version)
            typesense_client.collections[test_collection].documents.upsert(pkg)

        for version, expected_sortable in PRERELEASE_TEST_DATA:
            doc_id = f"test-pkg-{version}"
            doc = typesense_client.collections[test_collection].documents[doc_id].retrieve()

            assert doc["version_sortable"] == expected_sortable, \
                f"Document for {version} has wrong version_sortable: {doc['version_sortable']}"


# ============================================================================
# Integration Tests: Sort Order
# ============================================================================

@pytest.mark.integration
class TestVersionSortableSortOrder:
    """Integration tests for version_sortable sorting in Typesense."""

    def test_sort_by_version_sortable_ascending(
        self, typesense_client, test_collection, create_test_package
    ):
        """Verify ascending sort by version_sortable returns correct order."""
        # Index all test packages
        for version, _ in VERSION_TEST_DATA:
            pkg = create_test_package("test-pkg", version)
            typesense_client.collections[test_collection].documents.upsert(pkg)

        # Search with ascending sort
        result = typesense_client.collections[test_collection].documents.search({
            "q": "*",
            "query_by": "name",
            "sort_by": "version_sortable:asc",
            "per_page": 100,
        })

        # Extract versions in order
        sorted_versions = [hit["document"]["version"] for hit in result["hits"]]

        assert sorted_versions == EXPECTED_SORT_ORDER_ASC, \
            f"Expected {EXPECTED_SORT_ORDER_ASC}, got {sorted_versions}"

    def test_sort_by_version_sortable_descending(
        self, typesense_client, test_collection, create_test_package
    ):
        """Verify descending sort by version_sortable returns correct order."""
        # Index all test packages
        for version, _ in VERSION_TEST_DATA:
            pkg = create_test_package("test-pkg", version)
            typesense_client.collections[test_collection].documents.upsert(pkg)

        # Search with descending sort
        result = typesense_client.collections[test_collection].documents.search({
            "q": "*",
            "query_by": "name",
            "sort_by": "version_sortable:desc",
            "per_page": 100,
        })

        # Extract versions in order
        sorted_versions = [hit["document"]["version"] for hit in result["hits"]]

        expected_desc = list(reversed(EXPECTED_SORT_ORDER_ASC))
        assert sorted_versions == expected_desc, \
            f"Expected {expected_desc}, got {sorted_versions}"


# ============================================================================
# Integration Tests: Pre-release Sorting
# ============================================================================

@pytest.mark.integration
class TestVersionSortablePreRelease:
    """Integration tests for pre-release version sorting."""

    def test_prerelease_sort_order(
        self, typesense_client, test_collection, create_test_package
    ):
        """Verify alpha < beta < stable sort order."""
        # Index pre-release packages
        for version, _ in PRERELEASE_TEST_DATA:
            pkg = create_test_package("test-pkg", version)
            typesense_client.collections[test_collection].documents.upsert(pkg)

        # Search with ascending sort
        result = typesense_client.collections[test_collection].documents.search({
            "q": "*",
            "query_by": "name",
            "sort_by": "version_sortable:asc",
            "per_page": 100,
        })

        sorted_versions = [hit["document"]["version"] for hit in result["hits"]]

        assert sorted_versions == PRERELEASE_SORT_ORDER_ASC, \
            f"Expected {PRERELEASE_SORT_ORDER_ASC}, got {sorted_versions}"

    def test_prerelease_before_stable_in_mixed_versions(
        self, typesense_client, test_collection, create_test_package
    ):
        """Verify pre-release versions sort before stable in ascending order.

        With stable flag prefix:
        - All pre-releases (0.*) sort before all stable (1.*)
        - Within pre-releases, sorted by version then pre-release type
        - Within stable, sorted by version
        """
        versions = ["2.0.0", "2.0.0a1", "2.0.0b1", "1.9.0"]
        # Ascending: pre-releases first (alpha < beta), then stable (1.9.0 < 2.0.0)
        expected_order = ["2.0.0a1", "2.0.0b1", "1.9.0", "2.0.0"]

        for version in versions:
            pkg = create_test_package("test-pkg", version)
            typesense_client.collections[test_collection].documents.upsert(pkg)

        result = typesense_client.collections[test_collection].documents.search({
            "q": "*",
            "query_by": "name",
            "sort_by": "version_sortable:asc",
            "per_page": 100,
        })

        sorted_versions = [hit["document"]["version"] for hit in result["hits"]]

        assert sorted_versions == expected_order, \
            f"Expected {expected_order}, got {sorted_versions}"

    def test_stable_sorts_above_higher_prerelease_descending(
        self, typesense_client, test_collection, create_test_package
    ):
        """Verify stable versions sort above pre-releases in descending order.

        This is the key test: when sorting descending (newest first), stable
        versions must appear before ANY pre-release, regardless of version number.

        Example: 2.5.3 (stable) should sort above 3.0.0a2 (alpha pre-release)
        because PyPI considers 2.5.3 as "latest" - pre-releases are not
        considered stable/production releases.
        """
        versions = ["2.5.3", "3.0.0a2", "2.5.2", "3.0.0a1"]

        for version in versions:
            pkg = create_test_package("test-pkg", version)
            typesense_client.collections[test_collection].documents.upsert(pkg)

        result = typesense_client.collections[test_collection].documents.search({
            "q": "*",
            "query_by": "name",
            "sort_by": "version_sortable:desc",
            "per_page": 100,
        })

        sorted_versions = [hit["document"]["version"] for hit in result["hits"]]

        # Descending: stable versions first (by version desc), then pre-releases
        # 2.5.3 > 2.5.2 > 3.0.0a2 > 3.0.0a1
        expected_order = ["2.5.3", "2.5.2", "3.0.0a2", "3.0.0a1"]
        assert sorted_versions == expected_order, \
            f"Expected {expected_order}, got {sorted_versions}"

        # The "newest" (first) version should be the latest stable, not the alpha
        assert sorted_versions[0] == "2.5.3", \
            f"Expected '2.5.3' as newest, got '{sorted_versions[0]}'"
