"""
Unit tests for pyf.aggregator.npm_indexer module.

This module tests:
- Data cleaning and normalization
- npm-specific field handling
- Registry field setting
"""

import pytest
from unittest.mock import MagicMock, patch

from pyf.aggregator.npm_indexer import NpmIndexer


# ============================================================================
# Sample Data Fixtures
# ============================================================================


@pytest.fixture
def sample_npm_package_data():
    """Sample npm package data for indexing."""
    return {
        "name": "@plone/volto",
        "name_sortable": "@plone/volto",
        "version": "18.0.0",
        "summary": "Volto is the React-based frontend for Plone 6",
        "description": "# @plone/volto\n\nVolto is the React-based frontend.",
        "description_content_type": "text/markdown",
        "author": "Plone Foundation",
        "author_email": "info@plone.org",
        "maintainer": "plone",
        "maintainer_email": "release@plone.org",
        "license": "MIT",
        "keywords": ["plone", "volto", "react"],
        "classifiers": [],
        "framework_versions": [],
        "python_versions": [],
        "home_page": "https://github.com/plone/volto",
        "repository_url": "git+https://github.com/plone/volto.git",
        "project_url": "",
        "package_url": "https://www.npmjs.com/package/%40plone%2Fvolto",
        "release_url": "https://www.npmjs.com/package/%40plone%2Fvolto/v/18.0.0",
        "docs_url": "",
        "bugtrack_url": "https://github.com/plone/volto/issues",
        "requires_dist": ["react@^18.2.0", "redux@^5.0.0"],
        "platform": "node",
        "yanked": False,
        "yanked_reason": "",
        "urls": [],
        "project_urls": {"Homepage": "https://github.com/plone/volto"},
        "upload_timestamp": 1705315800,
        "registry": "npm",
        "npm_scope": "plone",
        "npm_quality_score": 0.90,
        "npm_popularity_score": 0.75,
        "npm_maintenance_score": 0.88,
        "npm_final_score": 0.85,
    }


@pytest.fixture
def sample_npm_package_data_minimal():
    """Sample npm package data with minimal fields."""
    return {
        "name": "plone-helper",
        "version": "1.0.0",
        "registry": "npm",
    }


@pytest.fixture
def mock_typesense_client():
    """Mock Typesense client for testing."""
    mock_client = MagicMock()
    mock_collection = MagicMock()
    mock_collection.documents.import_.return_value = [{"success": True}]
    mock_client.collections.__getitem__.return_value = mock_collection
    return mock_client


# ============================================================================
# Data Cleaning Tests
# ============================================================================


class TestNpmIndexerCleanData:
    """Test the clean_data method."""

    @patch("pyf.aggregator.npm_indexer.TypesenceConnection.__init__", return_value=None)
    def test_sets_registry_if_missing(self, mock_init):
        """Test that registry is set to npm if missing."""
        indexer = NpmIndexer()
        data = {"name": "test-pkg", "version": "1.0.0"}
        result = indexer.clean_data(data)
        assert result["registry"] == "npm"

    @patch("pyf.aggregator.npm_indexer.TypesenceConnection.__init__", return_value=None)
    def test_preserves_existing_registry(self, mock_init):
        """Test that existing registry value is preserved."""
        indexer = NpmIndexer()
        data = {"name": "test-pkg", "registry": "npm"}
        result = indexer.clean_data(data)
        assert result["registry"] == "npm"

    @patch("pyf.aggregator.npm_indexer.TypesenceConnection.__init__", return_value=None)
    def test_converts_keywords_string_to_list(self, mock_init):
        """Test that string keywords are converted to list."""
        indexer = NpmIndexer()
        data = {"name": "test-pkg", "keywords": "plone, volto, react"}
        result = indexer.clean_data(data)
        assert isinstance(result["keywords"], list)
        assert "plone" in result["keywords"]
        assert "volto" in result["keywords"]
        assert "react" in result["keywords"]

    @patch("pyf.aggregator.npm_indexer.TypesenceConnection.__init__", return_value=None)
    def test_preserves_keywords_list(self, mock_init):
        """Test that keywords list is preserved."""
        indexer = NpmIndexer()
        data = {"name": "test-pkg", "keywords": ["plone", "volto"]}
        result = indexer.clean_data(data)
        assert result["keywords"] == ["plone", "volto"]

    @patch("pyf.aggregator.npm_indexer.TypesenceConnection.__init__", return_value=None)
    def test_handles_none_list_fields(self, mock_init):
        """Test that None list fields are converted to empty lists."""
        indexer = NpmIndexer()
        data = {
            "name": "test-pkg",
            "requires_dist": None,
            "classifiers": None,
            "keywords": None,
        }
        result = indexer.clean_data(data)
        assert result["requires_dist"] == []
        assert result["classifiers"] == []
        assert result["keywords"] == []

    @patch("pyf.aggregator.npm_indexer.TypesenceConnection.__init__", return_value=None)
    def test_handles_none_upload_timestamp(self, mock_init):
        """Test that None upload_timestamp is converted to 0."""
        indexer = NpmIndexer()
        data = {"name": "test-pkg", "upload_timestamp": None}
        result = indexer.clean_data(data)
        assert result["upload_timestamp"] == 0

    @patch("pyf.aggregator.npm_indexer.TypesenceConnection.__init__", return_value=None)
    def test_handles_empty_upload_timestamp(self, mock_init):
        """Test that empty upload_timestamp is converted to 0."""
        indexer = NpmIndexer()
        data = {"name": "test-pkg", "upload_timestamp": ""}
        result = indexer.clean_data(data)
        assert result["upload_timestamp"] == 0

    @patch("pyf.aggregator.npm_indexer.TypesenceConnection.__init__", return_value=None)
    def test_preserves_npm_score_fields(self, mock_init, sample_npm_package_data):
        """Test that npm score fields are preserved."""
        indexer = NpmIndexer()
        result = indexer.clean_data(sample_npm_package_data.copy())
        assert result["npm_quality_score"] == 0.90
        assert result["npm_popularity_score"] == 0.75
        assert result["npm_maintenance_score"] == 0.88
        assert result["npm_final_score"] == 0.85

    @patch("pyf.aggregator.npm_indexer.TypesenceConnection.__init__", return_value=None)
    def test_handles_none_npm_scores(self, mock_init):
        """Test that None npm score fields are converted to 0.0."""
        indexer = NpmIndexer()
        data = {
            "name": "test-pkg",
            "npm_quality_score": None,
            "npm_popularity_score": None,
            "npm_maintenance_score": None,
            "npm_final_score": None,
        }
        result = indexer.clean_data(data)
        assert result["npm_quality_score"] == 0.0
        assert result["npm_popularity_score"] == 0.0
        assert result["npm_maintenance_score"] == 0.0
        assert result["npm_final_score"] == 0.0

    @patch("pyf.aggregator.npm_indexer.TypesenceConnection.__init__", return_value=None)
    def test_converts_none_fields_to_empty_string(self, mock_init):
        """Test that None string fields are converted to empty strings."""
        indexer = NpmIndexer()
        data = {
            "name": "test-pkg",
            "author": None,
            "license": None,
            "summary": None,
        }
        result = indexer.clean_data(data)
        assert result["author"] == ""
        assert result["license"] == ""
        assert result["summary"] == ""


# ============================================================================
# Indexing Tests
# ============================================================================


class TestNpmIndexerIndexData:
    """Test the index_data method."""

    @patch("pyf.aggregator.npm_indexer.TypesenceConnection.__init__", return_value=None)
    def test_index_data_calls_import(self, mock_init, mock_typesense_client):
        """Test that index_data calls Typesense import."""
        indexer = NpmIndexer()
        indexer.client = mock_typesense_client

        data = [{"name": "test-pkg", "version": "1.0.0"}]
        indexer.index_data(data, 1, "test-collection")

        mock_typesense_client.collections[
            "test-collection"
        ].documents.import_.assert_called_once_with(data, {"action": "upsert"})


# ============================================================================
# Full Indexing Flow Tests
# ============================================================================


class TestNpmIndexerCall:
    """Test the __call__ method."""

    @patch("pyf.aggregator.npm_indexer.TypesenceConnection.__init__", return_value=None)
    def test_call_processes_aggregator(
        self, mock_init, mock_typesense_client, sample_npm_package_data
    ):
        """Test that __call__ processes packages from aggregator."""
        indexer = NpmIndexer()
        indexer.client = mock_typesense_client

        # Create mock aggregator that yields one package
        mock_aggregator = MagicMock()
        mock_aggregator.__iter__ = MagicMock(
            return_value=iter([("@plone/volto-18.0.0", sample_npm_package_data.copy())])
        )

        indexer(mock_aggregator, "test-collection")

        # Verify import was called
        assert mock_typesense_client.collections[
            "test-collection"
        ].documents.import_.called

    @patch("pyf.aggregator.npm_indexer.TypesenceConnection.__init__", return_value=None)
    def test_call_sets_id_and_identifier(
        self, mock_init, mock_typesense_client, sample_npm_package_data
    ):
        """Test that id and identifier are set correctly."""
        indexer = NpmIndexer()
        indexer.client = mock_typesense_client

        captured_data = []

        def capture_import(data, opts):
            captured_data.extend(data)
            return [{"success": True}]

        mock_typesense_client.collections[
            "test-collection"
        ].documents.import_.side_effect = capture_import

        mock_aggregator = MagicMock()
        mock_aggregator.__iter__ = MagicMock(
            return_value=iter([("@plone/volto-18.0.0", sample_npm_package_data.copy())])
        )

        indexer(mock_aggregator, "test-collection")

        assert len(captured_data) == 1
        assert captured_data[0]["id"] == "@plone/volto-18.0.0"
        assert captured_data[0]["identifier"] == "@plone/volto-18.0.0"


# ============================================================================
# Profile Integration Tests
# ============================================================================


class TestNpmProfileConfig:
    """Test npm profile configuration."""

    def test_profile_manager_get_npm_config(self):
        """Test ProfileManager.get_npm_config method."""
        from pyf.aggregator.profiles import ProfileManager

        pm = ProfileManager()
        npm_config = pm.get_npm_config("plone")

        assert npm_config is not None
        assert "keywords" in npm_config
        assert "scopes" in npm_config
        assert "plone" in npm_config["keywords"]
        assert "@plone" in npm_config["scopes"]

    def test_profile_manager_validate_npm_profile(self):
        """Test ProfileManager.validate_npm_profile method."""
        from pyf.aggregator.profiles import ProfileManager

        pm = ProfileManager()
        assert pm.validate_npm_profile("plone") is True

    def test_profile_manager_npm_config_nonexistent_profile(self):
        """Test get_npm_config returns None for nonexistent profile."""
        from pyf.aggregator.profiles import ProfileManager

        pm = ProfileManager()
        npm_config = pm.get_npm_config("nonexistent")

        assert npm_config is None

    def test_profile_without_npm_config(self):
        """Test get_npm_config returns None for profile without npm section."""
        from pyf.aggregator.profiles import ProfileManager

        pm = ProfileManager()
        # Django profile doesn't have npm config
        npm_config = pm.get_npm_config("django")

        assert npm_config is None


# ============================================================================
# GitHub Enricher npm URL Tests
# ============================================================================


class TestGitHubEnricherNpmUrls:
    """Test GitHub enricher handles npm repository URL formats."""

    @patch(
        "pyf.aggregator.enrichers.github.TypesenceConnection.__init__",
        return_value=None,
    )
    def test_extracts_repo_from_git_plus_https(self, mock_init):
        """Test extraction from git+https:// URL."""
        from pyf.aggregator.enrichers.github import Enricher

        enricher = Enricher()
        data = {
            "name": "@plone/volto",
            "repository_url": "git+https://github.com/plone/volto.git",
        }

        repo_id = enricher.get_package_repo_identifier(data)
        assert repo_id == "plone/volto"

    @patch(
        "pyf.aggregator.enrichers.github.TypesenceConnection.__init__",
        return_value=None,
    )
    def test_extracts_repo_from_git_protocol(self, mock_init):
        """Test extraction from git:// URL."""
        from pyf.aggregator.enrichers.github import Enricher

        enricher = Enricher()
        data = {
            "name": "@plone/volto",
            "repository_url": "git://github.com/plone/volto.git",
        }

        repo_id = enricher.get_package_repo_identifier(data)
        assert repo_id == "plone/volto"

    @patch(
        "pyf.aggregator.enrichers.github.TypesenceConnection.__init__",
        return_value=None,
    )
    def test_extracts_repo_from_ssh_url(self, mock_init):
        """Test extraction from git@github.com: URL."""
        from pyf.aggregator.enrichers.github import Enricher

        enricher = Enricher()
        data = {
            "name": "@plone/volto",
            "repository_url": "git@github.com:plone/volto.git",
        }

        repo_id = enricher.get_package_repo_identifier(data)
        assert repo_id == "plone/volto"

    @patch(
        "pyf.aggregator.enrichers.github.TypesenceConnection.__init__",
        return_value=None,
    )
    def test_extracts_repo_from_standard_https(self, mock_init):
        """Test extraction from standard https:// URL."""
        from pyf.aggregator.enrichers.github import Enricher

        enricher = Enricher()
        data = {
            "name": "@plone/volto",
            "home_page": "https://github.com/plone/volto",
        }

        repo_id = enricher.get_package_repo_identifier(data)
        assert repo_id == "plone/volto"

    @patch(
        "pyf.aggregator.enrichers.github.TypesenceConnection.__init__",
        return_value=None,
    )
    def test_returns_none_for_no_github_url(self, mock_init):
        """Test returns None when no GitHub URL found."""
        from pyf.aggregator.enrichers.github import Enricher

        enricher = Enricher()
        data = {
            "name": "some-pkg",
            "home_page": "https://example.com",
        }

        repo_id = enricher.get_package_repo_identifier(data)
        assert repo_id is None
