"""
Live PyPI integration tests for version sorting.

This module tests that the "newest" package version returned by Typesense
(sorted by version_sortable:desc) matches PyPI's actual latest stable version.

These tests:
1. Fetch real package data from PyPI JSON API
2. Index ALL versions into a temporary Typesense collection
3. Verify that sort_by: version_sortable:desc returns PyPI's latest stable version first

This validates that stable versions sort above pre-releases, which is the
expected behavior matching PyPI's definition of "latest".
"""

import time

import pytest
import requests

from pyf.aggregator.db import TypesenceConnection
from pyf.aggregator.plugins.version_slicer import process


# Test packages covering different namespaces and pre-release scenarios
TEST_PACKAGES = [
    "plone.api",  # Has pre-release 3.0.0a2, stable 2.5.3
    "plone.restapi",  # Has pre-release 10.0.0a1, stable 9.x
    "collective.easyform",  # Likely no pre-release issues
    "kitconcept.seo",  # kitconcept namespace
    "Products.CMFPlone",  # Products namespace, has 6.2.0a1
    "plone.volto",  # Has pre-release 6.0.0a1, stable 5.x
]


def fetch_pypi_package_data(package_name: str) -> dict:
    """Fetch package data from PyPI JSON API."""
    url = f"https://pypi.org/pypi/{package_name}/json"
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.json()


def get_pypi_latest_stable_version(package_data: dict) -> str:
    """Get the latest stable version as reported by PyPI."""
    return package_data["info"]["version"]


def get_all_versions(package_data: dict) -> list[str]:
    """Get all release versions from PyPI package data."""
    return list(package_data.get("releases", {}).keys())


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
    collection_name = f"test_pypi_sorting_{int(time.time() * 1000)}"

    # Schema matching production with version_sortable for sorting
    schema = {
        "name": collection_name,
        "fields": [
            {"name": "identifier", "type": "string"},
            {"name": "name", "type": "string"},
            {"name": "version", "type": "string"},
            {"name": "version_raw", "type": "string", "optional": True},
            {"name": "version_sortable", "type": "string", "sort": True},
            {"name": "version_major", "type": "int32", "sort": True},
            {"name": "version_minor", "type": "int32", "sort": True},
            {"name": "version_bugfix", "type": "int32", "sort": True},
            {"name": "version_postfix", "type": "string", "optional": True},
        ],
    }

    typesense_client.collections.create(schema)

    yield collection_name

    # Cleanup
    try:
        typesense_client.collections[collection_name].delete()
    except Exception:
        pass


def create_package_document(name: str, version: str) -> dict:
    """Create a minimal package document with version_sortable calculated."""
    data = {
        "identifier": f"{name}-{version}",
        "name": name,
        "version": version,
    }
    # Apply version_slicer plugin to set version_sortable and other fields
    process(data["identifier"], data)
    return data


@pytest.mark.integration
class TestNewestVersionMatchesPyPI:
    """Test that Typesense newest version matches PyPI's latest stable."""

    @pytest.mark.parametrize("package_name", TEST_PACKAGES)
    def test_newest_version_matches_pypi_latest(
        self, typesense_client, test_collection, package_name
    ):
        """Verify that sorting by version_sortable:desc returns PyPI's latest stable first.

        This test:
        1. Fetches all versions from PyPI for the package
        2. Indexes all versions into Typesense
        3. Queries with sort_by: version_sortable:desc
        4. Asserts the first result matches PyPI's reported latest stable version
        """
        # Fetch real data from PyPI
        package_data = fetch_pypi_package_data(package_name)
        pypi_latest = get_pypi_latest_stable_version(package_data)
        all_versions = get_all_versions(package_data)

        # Index all versions into Typesense
        for version in all_versions:
            doc = create_package_document(package_name, version)
            try:
                typesense_client.collections[test_collection].documents.upsert(doc)
            except Exception as e:
                # Skip versions that fail validation (unusual formats)
                print(f"Warning: Could not index {package_name} {version}: {e}")
                continue

        # Query Typesense for newest version (sort by version_sortable descending)
        result = typesense_client.collections[test_collection].documents.search(
            {
                "q": package_name,
                "query_by": "name",
                "filter_by": f"name:={package_name}",
                "sort_by": "version_sortable:desc",
                "per_page": 1,
            }
        )

        assert result["found"] > 0, f"No documents found for {package_name}"

        typesense_newest = result["hits"][0]["document"]["version"]

        assert typesense_newest == pypi_latest, (
            f"Package {package_name}: "
            f"Typesense newest '{typesense_newest}' != PyPI latest '{pypi_latest}'. "
            f"version_sortable: {result['hits'][0]['document'].get('version_sortable')}"
        )


@pytest.mark.integration
class TestStableVersionSortsAbovePreRelease:
    """Test that stable versions always sort above pre-releases."""

    def test_stable_2_5_3_above_prerelease_3_0_0a2(
        self, typesense_client, test_collection
    ):
        """Verify 2.5.3 (stable) sorts above 3.0.0a2 (alpha pre-release).

        This is the core issue: version numbers alone would put 3.0.0a2 higher,
        but PyPI considers 2.5.3 as "latest" because it's stable.
        """
        versions = ["2.5.3", "3.0.0a2", "2.5.2", "3.0.0a1"]

        for version in versions:
            doc = create_package_document("test-pkg", version)
            typesense_client.collections[test_collection].documents.upsert(doc)

        result = typesense_client.collections[test_collection].documents.search(
            {
                "q": "*",
                "query_by": "name",
                "filter_by": "name:=test-pkg",
                "sort_by": "version_sortable:desc",
                "per_page": 10,
            }
        )

        sorted_versions = [hit["document"]["version"] for hit in result["hits"]]

        # Expected order: stable versions first (by version), then pre-releases (by version)
        # 2.5.3 > 2.5.2 > 3.0.0a2 > 3.0.0a1
        assert sorted_versions[0] == "2.5.3", (
            f"Expected '2.5.3' as newest, got '{sorted_versions[0]}'. "
            f"Full order: {sorted_versions}"
        )

    def test_stable_always_above_any_prerelease_of_higher_version(
        self, typesense_client, test_collection
    ):
        """Verify that ANY stable version sorts above ANY pre-release.

        Even 1.0.0 stable should sort above 99.0.0a1 alpha.
        """
        versions = [
            "1.0.0",  # stable, low version
            "99.0.0a1",  # alpha, very high version
            "50.0.0b1",  # beta, high version
            "2.0.0rc1",  # release candidate
        ]

        for version in versions:
            doc = create_package_document("test-pkg", version)
            typesense_client.collections[test_collection].documents.upsert(doc)

        result = typesense_client.collections[test_collection].documents.search(
            {
                "q": "*",
                "query_by": "name",
                "filter_by": "name:=test-pkg",
                "sort_by": "version_sortable:desc",
                "per_page": 10,
            }
        )

        sorted_versions = [hit["document"]["version"] for hit in result["hits"]]

        # Only stable version should be first
        assert sorted_versions[0] == "1.0.0", (
            f"Expected '1.0.0' (stable) as newest, got '{sorted_versions[0]}'. "
            f"Full order: {sorted_versions}"
        )

    def test_prerelease_ordering_among_prereleases(
        self, typesense_client, test_collection
    ):
        """Verify correct ordering among pre-release types: dev < alpha < beta < rc."""
        versions = [
            "2.0.0dev1",
            "2.0.0a1",
            "2.0.0b1",
            "2.0.0rc1",
            "2.0.0",  # stable
        ]

        for version in versions:
            doc = create_package_document("test-pkg", version)
            typesense_client.collections[test_collection].documents.upsert(doc)

        result = typesense_client.collections[test_collection].documents.search(
            {
                "q": "*",
                "query_by": "name",
                "filter_by": "name:=test-pkg",
                "sort_by": "version_sortable:desc",
                "per_page": 10,
            }
        )

        sorted_versions = [hit["document"]["version"] for hit in result["hits"]]

        # Expected order (newest to oldest):
        # 2.0.0 (stable) > 2.0.0rc1 > 2.0.0b1 > 2.0.0a1 > 2.0.0dev1
        expected_order = ["2.0.0", "2.0.0rc1", "2.0.0b1", "2.0.0a1", "2.0.0dev1"]
        assert sorted_versions == expected_order, (
            f"Expected order {expected_order}, got {sorted_versions}"
        )


@pytest.mark.integration
class TestVersionSortableFormat:
    """Test the version_sortable format produces correct values."""

    def test_stable_version_has_prefix_1(self, typesense_client, test_collection):
        """Verify stable versions have '1.' prefix in version_sortable."""
        doc = create_package_document("test-pkg", "2.5.3")
        typesense_client.collections[test_collection].documents.upsert(doc)

        result = (
            typesense_client.collections[test_collection]
            .documents[doc["identifier"]]
            .retrieve()
        )

        version_sortable = result["version_sortable"]
        assert version_sortable.startswith("1."), (
            f"Stable version should have '1.' prefix, got: {version_sortable}"
        )

    def test_prerelease_version_has_prefix_0(self, typesense_client, test_collection):
        """Verify pre-release versions have '0.' prefix in version_sortable."""
        doc = create_package_document("test-pkg", "3.0.0a2")
        typesense_client.collections[test_collection].documents.upsert(doc)

        result = (
            typesense_client.collections[test_collection]
            .documents[doc["identifier"]]
            .retrieve()
        )

        version_sortable = result["version_sortable"]
        assert version_sortable.startswith("0."), (
            f"Pre-release version should have '0.' prefix, got: {version_sortable}"
        )

    def test_version_sortable_has_six_segments(self, typesense_client, test_collection):
        """Verify version_sortable has exactly 6 dot-separated segments."""
        doc = create_package_document("test-pkg", "2.5.3")
        typesense_client.collections[test_collection].documents.upsert(doc)

        result = (
            typesense_client.collections[test_collection]
            .documents[doc["identifier"]]
            .retrieve()
        )

        version_sortable = result["version_sortable"]
        segments = version_sortable.split(".")

        assert len(segments) == 6, (
            f"Expected 6 segments, got {len(segments)}: {version_sortable}"
        )
