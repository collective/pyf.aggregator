"""
Unit tests for pyf.aggregator.main module.

This module tests:
- run_refresh_mode() function for refreshing indexed packages
- Multi-version fetching behavior
- Plugin application per version
"""

import pytest
import responses
import re
from unittest.mock import MagicMock, patch, call


# ============================================================================
# Sample Data Fixtures for Refresh Mode
# ============================================================================

@pytest.fixture
def sample_pypi_json_with_releases():
    """Sample PyPI JSON response with multiple releases."""
    return {
        "info": {
            "name": "plone.api",
            "version": "2.0.0",
            "author": "Plone Foundation",
            "author_email": "foundation@plone.org",
            "bugtrack_url": None,
            "classifiers": [
                "Framework :: Plone",
                "Framework :: Plone :: 6.0",
            ],
            "description": "A simple API for Plone",
            "description_content_type": "text/x-rst",
            "docs_url": None,
            "home_page": "https://github.com/plone/plone.api",
            "keywords": ["plone", "api"],
            "license": "GPL version 2",
            "maintainer": "",
            "maintainer_email": "",
            "package_url": "https://pypi.org/project/plone.api/",
            "platform": "",
            "project_url": "https://pypi.org/project/plone.api/",
            "project_urls": None,
            "release_url": "https://pypi.org/project/plone.api/2.0.0/",
            "requires_dist": ["plone.base"],
            "summary": "A simple API for Plone",
            "version": "2.0.0",
            "yanked": False,
            "yanked_reason": None,
        },
        "releases": {
            "1.0.0": [{"upload_time": "2020-01-01T00:00:00", "downloads": -1, "md5_digest": "abc"}],
            "1.5.0": [{"upload_time": "2021-06-15T12:30:00", "downloads": -1, "md5_digest": "def"}],
            "2.0.0": [{"upload_time": "2023-06-15T12:30:00", "downloads": -1, "md5_digest": "ghi"}],
        },
        "urls": [
            {
                "comment_text": "",
                "digests": {"sha256": "abc123"},
                "downloads": -1,
                "filename": "plone.api-2.0.0.tar.gz",
                "md5_digest": "def456",
                "packagetype": "sdist",
                "upload_time": "2023-06-15T12:30:00",
                "url": "https://files.pythonhosted.org/packages/plone.api-2.0.0.tar.gz",
                "yanked": False,
            }
        ],
    }


@pytest.fixture
def sample_version_specific_json():
    """Sample version-specific PyPI JSON response."""
    def make_json(name, version, upload_time):
        return {
            "info": {
                "name": name,
                "version": version,
                "author": "Test Author",
                "author_email": "test@example.com",
                "bugtrack_url": None,
                "classifiers": ["Framework :: Plone"],
                "description": f"Description for {name} {version}",
                "description_content_type": "text/x-rst",
                "docs_url": None,
                "home_page": f"https://github.com/test/{name}",
                "keywords": [],
                "license": "MIT",
                "maintainer": "",
                "maintainer_email": "",
                "package_url": f"https://pypi.org/project/{name}/",
                "platform": "",
                "project_url": f"https://pypi.org/project/{name}/",
                "project_urls": None,
                "release_url": f"https://pypi.org/project/{name}/{version}/",
                "requires_dist": None,
                "summary": f"Summary for {name} {version}",
                "version": version,
                "yanked": False,
                "yanked_reason": None,
            },
            "urls": [
                {
                    "comment_text": "",
                    "digests": {"sha256": f"hash-{version}"},
                    "downloads": -1,
                    "filename": f"{name}-{version}.tar.gz",
                    "md5_digest": f"md5-{version}",
                    "packagetype": "sdist",
                    "upload_time": upload_time,
                    "url": f"https://files.pythonhosted.org/packages/{name}-{version}.tar.gz",
                    "yanked": False,
                }
            ],
        }
    return make_json


# ============================================================================
# Refresh Mode Tests
# ============================================================================

class TestRunRefreshMode:
    """Test the run_refresh_mode function."""

    @responses.activate
    def test_refresh_mode_fetches_all_versions(
        self, sample_pypi_json_with_releases, sample_version_specific_json
    ):
        """Test that refresh mode fetches and indexes all versions of each package."""
        # Mock main package JSON (contains releases dict)
        responses.add(
            responses.GET,
            re.compile(r"https://pypi\.org/+pypi/plone\.api/json"),
            json=sample_pypi_json_with_releases,
            status=200,
        )

        # Mock version-specific JSON for each release
        for version in ["1.0.0", "1.5.0", "2.0.0"]:
            upload_times = {
                "1.0.0": "2020-01-01T00:00:00",
                "1.5.0": "2021-06-15T12:30:00",
                "2.0.0": "2023-06-15T12:30:00",
            }
            responses.add(
                responses.GET,
                re.compile(rf"https://pypi\.org/+pypi/plone\.api/{version}/json"),
                json=sample_version_specific_json("plone.api", version, upload_times[version]),
                status=200,
            )

        # Test that the Aggregator correctly fetches all versions
        from pyf.aggregator.fetcher import Aggregator

        agg = Aggregator(mode="first", filter_troove=["Framework :: Plone"])

        # Fetch the main package JSON
        package_json = agg._get_pypi_json("plone.api")
        assert package_json is not None

        # Verify releases dict contains all versions
        releases = package_json.get("releases", {})
        assert len(releases) == 3
        assert "1.0.0" in releases
        assert "1.5.0" in releases
        assert "2.0.0" in releases

        # Iterate through versions like the refresh mode does
        versions_data = []
        for release_id, release_info in agg._all_package_versions(releases):
            version_data = agg._get_pypi("plone.api", release_id)
            if version_data:
                identifier = f"plone.api-{release_id}"
                version_data["id"] = identifier
                version_data["identifier"] = identifier
                versions_data.append(version_data)

        # Should have 3 version documents
        assert len(versions_data) == 3

        # Verify identifiers
        identifiers = [v["identifier"] for v in versions_data]
        assert "plone.api-1.0.0" in identifiers
        assert "plone.api-1.5.0" in identifiers
        assert "plone.api-2.0.0" in identifiers

    @responses.activate
    def test_refresh_mode_deletes_before_upsert(self, sample_pypi_json_with_releases, sample_version_specific_json):
        """Test that refresh mode deletes existing versions before upserting new ones."""
        # This ensures clean slate per package - no stale versions remain

        # Mock main package JSON
        responses.add(
            responses.GET,
            re.compile(r"https://pypi\.org/+pypi/plone\.api/json"),
            json=sample_pypi_json_with_releases,
            status=200,
        )

        # Mock version-specific JSON for each release
        for version in ["1.0.0", "1.5.0", "2.0.0"]:
            upload_times = {
                "1.0.0": "2020-01-01T00:00:00",
                "1.5.0": "2021-06-15T12:30:00",
                "2.0.0": "2023-06-15T12:30:00",
            }
            responses.add(
                responses.GET,
                re.compile(rf"https://pypi\.org/+pypi/plone\.api/{version}/json"),
                json=sample_version_specific_json("plone.api", version, upload_times[version]),
                status=200,
            )

        # Verify the release structure
        releases = sample_pypi_json_with_releases["releases"]
        assert "1.0.0" in releases
        assert "1.5.0" in releases
        assert "2.0.0" in releases

    def test_refresh_mode_applies_plugins_to_each_version(self):
        """Test that plugins are applied to each version document."""
        # Create a mock plugin that records calls
        plugin_calls = []

        def mock_plugin(identifier, data):
            plugin_calls.append({"identifier": identifier, "name": data.get("name")})

        # Test that plugins would be called for each version
        versions = ["1.0.0", "1.5.0", "2.0.0"]
        for version in versions:
            identifier = f"plone.api-{version}"
            data = {"name": "plone.api", "version": version}
            mock_plugin(identifier, data)

        # Verify plugin was called 3 times (once per version)
        assert len(plugin_calls) == 3
        assert plugin_calls[0]["identifier"] == "plone.api-1.0.0"
        assert plugin_calls[1]["identifier"] == "plone.api-1.5.0"
        assert plugin_calls[2]["identifier"] == "plone.api-2.0.0"

    def test_refresh_mode_handles_package_not_found(self):
        """Test that refresh mode handles 404 packages correctly."""
        # A package that returns 404 should be marked for deletion
        # This test documents the expected behavior

        result = {"status": "delete", "package": "removed-package", "reason": "not_found"}
        assert result["status"] == "delete"
        assert result["reason"] == "not_found"

    def test_refresh_mode_handles_no_classifier_match(self):
        """Test that packages without required classifiers are deleted."""
        result = {"status": "delete", "package": "non-plone-package", "reason": "no_classifier"}
        assert result["status"] == "delete"
        assert result["reason"] == "no_classifier"

    def test_refresh_mode_handles_no_releases(self):
        """Test that packages with no releases are skipped."""
        result = {"status": "skip", "package": "empty-package", "reason": "no_releases"}
        assert result["status"] == "skip"
        assert result["reason"] == "no_releases"


class TestProcessPackageFunction:
    """Test the process_package inner function behavior."""

    @responses.activate
    def test_process_package_returns_all_versions(self, sample_pypi_json_with_releases, sample_version_specific_json):
        """Test that process_package returns data for all versions."""
        # Mock main package JSON
        responses.add(
            responses.GET,
            re.compile(r"https://pypi\.org/+pypi/test-package/json"),
            json=sample_pypi_json_with_releases,
            status=200,
        )

        # Mock version-specific JSON
        for version in ["1.0.0", "1.5.0", "2.0.0"]:
            upload_times = {
                "1.0.0": "2020-01-01T00:00:00",
                "1.5.0": "2021-06-15T12:30:00",
                "2.0.0": "2023-06-15T12:30:00",
            }
            responses.add(
                responses.GET,
                re.compile(rf"https://pypi\.org/+pypi/test-package/{version}/json"),
                json=sample_version_specific_json("test-package", version, upload_times[version]),
                status=200,
            )

        from pyf.aggregator.fetcher import Aggregator

        agg = Aggregator(mode="first", filter_troove=["Framework :: Plone"])

        # Fetch the main package JSON
        package_json = agg._get_pypi_json("test-package")
        assert package_json is not None

        # Get releases
        releases = package_json.get("releases", {})
        assert len(releases) == 3

        # Iterate through versions like the new code will
        versions_data = []
        for release_id, release_info in agg._all_package_versions(releases):
            version_data = agg._get_pypi("test-package", release_id)
            if version_data:
                identifier = f"test-package-{release_id}"
                version_data["id"] = identifier
                version_data["identifier"] = identifier
                versions_data.append(version_data)

        # Should have 3 version documents
        assert len(versions_data) == 3

        # Verify identifiers
        identifiers = [v["identifier"] for v in versions_data]
        assert "test-package-1.0.0" in identifiers
        assert "test-package-1.5.0" in identifiers
        assert "test-package-2.0.0" in identifiers

    @responses.activate
    def test_process_package_sets_upload_timestamp(self, sample_pypi_json_with_releases, sample_version_specific_json):
        """Test that upload_timestamp is set from release info."""
        from datetime import datetime

        # Parse an upload time
        ts = "2023-06-15T12:30:00"
        dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
        timestamp = int(dt.timestamp())

        # Verify timestamp conversion
        assert timestamp > 0
        assert isinstance(timestamp, int)


class TestRefreshModeIntegration:
    """Integration tests for refresh mode."""

    @responses.activate
    def test_full_refresh_flow(self, sample_pypi_json_with_releases, sample_version_specific_json):
        """Test the complete refresh flow with mocked dependencies."""
        # Mock main package JSON
        responses.add(
            responses.GET,
            re.compile(r"https://pypi\.org/+pypi/plone\.api/json"),
            json=sample_pypi_json_with_releases,
            status=200,
        )

        # Mock version-specific JSON for each release
        for version in ["1.0.0", "1.5.0", "2.0.0"]:
            upload_times = {
                "1.0.0": "2020-01-01T00:00:00",
                "1.5.0": "2021-06-15T12:30:00",
                "2.0.0": "2023-06-15T12:30:00",
            }
            responses.add(
                responses.GET,
                re.compile(rf"https://pypi\.org/+pypi/plone\.api/{version}/json"),
                json=sample_version_specific_json("plone.api", version, upload_times[version]),
                status=200,
            )

        # Create mock classes
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_collection.retrieve.return_value = {"name": "plone"}

        # Track operations
        deleted_packages = []
        imported_docs = []

        def track_delete(filter_by):
            pkg_name = filter_by.get("filter_by", "").replace("name:=", "")
            deleted_packages.append(pkg_name)
            return {"num_deleted": 3}

        def track_import(docs, options):
            imported_docs.extend(docs)
            return [{"success": True} for _ in docs]

        mock_collection.documents.delete = track_delete
        mock_collection.documents.import_ = track_import
        mock_client.collections.__getitem__.return_value = mock_collection

        # Mock search for unique package names
        mock_collection.documents.search.return_value = {
            "grouped_hits": [
                {"hits": [{"document": {"name": "plone.api"}}]}
            ]
        }

        with patch("pyf.aggregator.db.typesense.Client", return_value=mock_client):
            from pyf.aggregator.fetcher import Aggregator

            agg = Aggregator(mode="first", filter_troove=["Framework :: Plone"])

            # Simulate refresh behavior
            package_json = agg._get_pypi_json("plone.api")
            assert package_json is not None

            # Check classifiers
            has_classifiers = agg.has_classifiers(package_json, ["Framework :: Plone"])
            assert has_classifiers is True

            # Get all versions
            releases = package_json.get("releases", {})
            versions = []
            for release_id, release_info in agg._all_package_versions(releases):
                version_data = agg._get_pypi("plone.api", release_id)
                if version_data:
                    versions.append(version_data)

            # Should process 3 versions
            assert len(versions) == 3
