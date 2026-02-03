"""
Unit tests for pyf.aggregator.npm_fetcher module.

This module tests:
- npm search by keyword and scope
- npm package metadata fetching
- Rate limiting behavior
- Data transformation
- Git URL parsing
"""

import pytest
import responses
import re

from pyf.aggregator.npm_fetcher import NpmAggregator


# ============================================================================
# Sample Data Fixtures
# ============================================================================


@pytest.fixture
def sample_npm_search_response():
    """Sample npm search API response."""
    return {
        "objects": [
            {
                "package": {
                    "name": "@plone/volto",
                    "scope": "plone",
                    "version": "18.0.0",
                    "description": "Volto is the React-based frontend for Plone 6",
                    "keywords": ["plone", "volto", "react", "frontend"],
                    "date": "2024-01-15T10:30:00.000Z",
                    "links": {
                        "npm": "https://www.npmjs.com/package/%40plone%2Fvolto",
                        "homepage": "https://github.com/plone/volto",
                        "repository": "https://github.com/plone/volto",
                    },
                },
                "score": {
                    "final": 0.85,
                    "detail": {
                        "quality": 0.90,
                        "popularity": 0.75,
                        "maintenance": 0.88,
                    },
                },
            },
            {
                "package": {
                    "name": "@plone/registry",
                    "scope": "plone",
                    "version": "1.0.0",
                    "description": "Plone Registry",
                    "keywords": ["plone", "registry"],
                    "date": "2024-01-10T08:00:00.000Z",
                },
                "score": {
                    "final": 0.70,
                    "detail": {
                        "quality": 0.75,
                        "popularity": 0.60,
                        "maintenance": 0.80,
                    },
                },
            },
        ],
        "total": 2,
    }


@pytest.fixture
def sample_npm_package_json():
    """Sample npm package JSON response."""
    return {
        "name": "@plone/volto",
        "description": "Volto is the React-based frontend for Plone 6",
        "dist-tags": {"latest": "18.0.0"},
        "versions": {
            "17.0.0": {
                "name": "@plone/volto",
                "version": "17.0.0",
                "description": "Volto is the React-based frontend for Plone 6",
                "keywords": ["plone", "volto", "react"],
                "homepage": "https://github.com/plone/volto",
                "repository": {
                    "type": "git",
                    "url": "git+https://github.com/plone/volto.git",
                },
                "bugs": {"url": "https://github.com/plone/volto/issues"},
                "license": "MIT",
                "author": {"name": "Plone Foundation", "email": "info@plone.org"},
                "maintainers": [{"name": "plone", "email": "release@plone.org"}],
                "dependencies": {"react": "^18.2.0", "redux": "^4.2.0"},
                "readme": "# @plone/volto\n\nVolto is the React-based frontend.",
            },
            "18.0.0": {
                "name": "@plone/volto",
                "version": "18.0.0",
                "description": "Volto is the React-based frontend for Plone 6",
                "keywords": ["plone", "volto", "react", "frontend"],
                "homepage": "https://github.com/plone/volto",
                "repository": {
                    "type": "git",
                    "url": "git+https://github.com/plone/volto.git",
                },
                "bugs": {"url": "https://github.com/plone/volto/issues"},
                "license": "MIT",
                "author": {"name": "Plone Foundation", "email": "info@plone.org"},
                "maintainers": [{"name": "plone", "email": "release@plone.org"}],
                "dependencies": {"react": "^18.2.0", "redux": "^5.0.0"},
                "readme": "# @plone/volto\n\nVolto is the React-based frontend.",
            },
        },
        "time": {
            "created": "2023-01-01T00:00:00.000Z",
            "modified": "2024-01-15T10:30:00.000Z",
            "17.0.0": "2023-06-15T12:00:00.000Z",
            "18.0.0": "2024-01-15T10:30:00.000Z",
        },
        "repository": {
            "type": "git",
            "url": "git+https://github.com/plone/volto.git",
        },
        "readme": "# @plone/volto\n\nVolto is the React-based frontend.",
        "keywords": ["plone", "volto", "react", "frontend"],
    }


@pytest.fixture
def sample_npm_unscoped_package_json():
    """Sample npm package JSON for an unscoped package."""
    return {
        "name": "plone-react",
        "description": "A Plone React library",
        "readme": "# plone-react\n\nA Plone React library for building apps.",
        "versions": {
            "1.0.0": {
                "name": "plone-react",
                "version": "1.0.0",
                "description": "A Plone React library",
                "keywords": ["plone"],
                "homepage": "https://github.com/example/plone-react",
                "repository": "https://github.com/example/plone-react",
                "license": "MIT",
                "author": "Test Author",
                "dependencies": {},
            },
        },
        "time": {
            "1.0.0": "2024-01-01T00:00:00.000Z",
        },
    }


# ============================================================================
# Aggregator Initialization Tests
# ============================================================================


class TestNpmAggregatorInit:
    """Test NpmAggregator initialization."""

    def test_default_npm_base_url(self):
        """Test that default npm base URL is set correctly."""
        aggregator = NpmAggregator(mode="first")
        assert aggregator.npm_base_url == "https://registry.npmjs.org"

    def test_custom_npm_base_url(self):
        """Test that custom npm base URL can be set."""
        aggregator = NpmAggregator(
            mode="first", npm_base_url="https://registry.example.com/"
        )
        assert aggregator.npm_base_url == "https://registry.example.com"

    def test_mode_first(self):
        """Test first mode initialization."""
        aggregator = NpmAggregator(mode="first")
        assert aggregator.mode == "first"

    def test_mode_incremental(self):
        """Test incremental mode initialization."""
        aggregator = NpmAggregator(mode="incremental")
        assert aggregator.mode == "incremental"

    def test_filter_keywords_set(self):
        """Test filter_keywords is set correctly."""
        aggregator = NpmAggregator(mode="first", filter_keywords=["plone"])
        assert aggregator.filter_keywords == ["plone"]

    def test_filter_scopes_set(self):
        """Test filter_scopes is set correctly."""
        aggregator = NpmAggregator(mode="first", filter_scopes=["@plone", "@eeacms"])
        assert aggregator.filter_scopes == ["@plone", "@eeacms"]

    def test_limit_set(self):
        """Test limit is set correctly."""
        aggregator = NpmAggregator(mode="first", limit=100)
        assert aggregator.limit == 100


# ============================================================================
# Search API Tests
# ============================================================================


class TestNpmSearch:
    """Test npm search functionality."""

    @responses.activate
    def test_search_by_keyword(self, sample_npm_search_response):
        """Test searching npm by keyword."""
        # URL-encoded: keywords%3Aplone
        responses.add(
            responses.GET,
            re.compile(r"https://registry\.npmjs\.org/-/v1/search.*keywords%3Aplone"),
            json=sample_npm_search_response,
            status=200,
        )

        aggregator = NpmAggregator(mode="first", filter_keywords=["plone"])
        results = aggregator._search_by_keyword("plone")

        assert len(results) == 2
        assert results[0]["package"]["name"] == "@plone/volto"

    @responses.activate
    def test_search_by_scope(self, sample_npm_search_response):
        """Test searching npm by scope."""
        # URL-encoded: scope%3Aplone
        responses.add(
            responses.GET,
            re.compile(r"https://registry\.npmjs\.org/-/v1/search.*scope%3Aplone"),
            json=sample_npm_search_response,
            status=200,
        )

        aggregator = NpmAggregator(mode="first", filter_scopes=["@plone"])
        results = aggregator._search_by_scope("@plone")

        assert len(results) == 2

    @responses.activate
    def test_search_handles_empty_results(self):
        """Test search with no results."""
        responses.add(
            responses.GET,
            re.compile(r"https://registry\.npmjs\.org/-/v1/search"),
            json={"objects": [], "total": 0},
            status=200,
        )

        aggregator = NpmAggregator(mode="first")
        results = aggregator._npm_search("nonexistent")

        assert results == []

    @responses.activate
    def test_search_handles_rate_limiting(self, sample_npm_search_response):
        """Test search handles 429 rate limiting."""
        responses.add(
            responses.GET,
            re.compile(r"https://registry\.npmjs\.org/-/v1/search"),
            status=429,
            headers={"Retry-After": "1"},
        )
        responses.add(
            responses.GET,
            re.compile(r"https://registry\.npmjs\.org/-/v1/search"),
            json=sample_npm_search_response,
            status=200,
        )

        aggregator = NpmAggregator(mode="first")
        results = aggregator._npm_search("plone")

        assert len(results) == 2


# ============================================================================
# Package Metadata Tests
# ============================================================================


class TestNpmPackageMetadata:
    """Test npm package metadata fetching."""

    @responses.activate
    def test_get_npm_json_scoped_package(self, sample_npm_package_json):
        """Test fetching metadata for a scoped package."""
        responses.add(
            responses.GET,
            "https://registry.npmjs.org/%40plone%2Fvolto",
            json=sample_npm_package_json,
            status=200,
        )

        aggregator = NpmAggregator(mode="first")
        result = aggregator._get_npm_json("@plone/volto")

        assert result is not None
        assert result["name"] == "@plone/volto"
        assert "18.0.0" in result["versions"]

    @responses.activate
    def test_get_npm_json_unscoped_package(self, sample_npm_unscoped_package_json):
        """Test fetching metadata for an unscoped package."""
        responses.add(
            responses.GET,
            "https://registry.npmjs.org/plone-react",
            json=sample_npm_unscoped_package_json,
            status=200,
        )

        aggregator = NpmAggregator(mode="first")
        result = aggregator._get_npm_json("plone-react")

        assert result is not None
        assert result["name"] == "plone-react"

    @responses.activate
    def test_get_npm_json_returns_none_for_404(self):
        """Test that 404 response returns None."""
        responses.add(
            responses.GET,
            "https://registry.npmjs.org/nonexistent-package",
            status=404,
        )

        aggregator = NpmAggregator(mode="first")
        result = aggregator._get_npm_json("nonexistent-package")

        assert result is None

    @responses.activate
    def test_get_npm_json_handles_rate_limiting(self, sample_npm_package_json):
        """Test that rate limiting is handled with retry."""
        responses.add(
            responses.GET,
            "https://registry.npmjs.org/%40plone%2Fvolto",
            status=429,
            headers={"Retry-After": "1"},
        )
        responses.add(
            responses.GET,
            "https://registry.npmjs.org/%40plone%2Fvolto",
            json=sample_npm_package_json,
            status=200,
        )

        aggregator = NpmAggregator(mode="first")
        result = aggregator._get_npm_json("@plone/volto")

        assert result is not None


# ============================================================================
# Data Transformation Tests
# ============================================================================


class TestDataTransformation:
    """Test npm data transformation to Typesense schema."""

    def test_transform_scoped_package(self, sample_npm_package_json):
        """Test transformation of scoped package data."""
        aggregator = NpmAggregator(mode="first")
        version_data = sample_npm_package_json["versions"]["18.0.0"]
        time_info = sample_npm_package_json["time"]

        result = aggregator._transform_npm_data(
            "@plone/volto", version_data, time_info, sample_npm_package_json
        )

        assert result["name"] == "@plone/volto"
        assert result["name_sortable"] == "@plone/volto"
        assert result["version"] == "18.0.0"
        assert result["registry"] == "npm"
        assert result["npm_scope"] == "plone"
        assert result["summary"] == "Volto is the React-based frontend for Plone 6"
        assert result["author"] == "Plone Foundation"
        assert result["author_email"] == "info@plone.org"
        assert result["license"] == "MIT"
        assert "plone" in result["keywords"]
        assert result["platform"] == "node"

    def test_transform_unscoped_package(self, sample_npm_unscoped_package_json):
        """Test transformation of unscoped package data."""
        aggregator = NpmAggregator(mode="first")
        version_data = sample_npm_unscoped_package_json["versions"]["1.0.0"]
        time_info = sample_npm_unscoped_package_json["time"]

        result = aggregator._transform_npm_data(
            "plone-react", version_data, time_info, sample_npm_unscoped_package_json
        )

        assert result["name"] == "plone-react"
        assert result["npm_scope"] == ""
        assert result["registry"] == "npm"

    def test_transform_handles_string_author(self):
        """Test transformation handles author as string."""
        aggregator = NpmAggregator(mode="first")
        version_data = {
            "name": "test-pkg",
            "version": "1.0.0",
            "author": "John Doe",
            "description": "",
        }

        result = aggregator._transform_npm_data("test-pkg", version_data, {}, {})

        assert result["author"] == "John Doe"
        assert result["author_email"] == ""

    def test_transform_handles_string_repository(self):
        """Test transformation handles repository as string."""
        aggregator = NpmAggregator(mode="first")
        version_data = {
            "name": "test-pkg",
            "version": "1.0.0",
            "repository": "https://github.com/example/test",
            "description": "",
        }

        result = aggregator._transform_npm_data("test-pkg", version_data, {}, {})

        assert result["repository_url"] == "https://github.com/example/test"

    def test_transform_handles_deprecated_package(self):
        """Test transformation handles deprecated packages."""
        aggregator = NpmAggregator(mode="first")
        version_data = {
            "name": "old-pkg",
            "version": "1.0.0",
            "deprecated": "Use new-pkg instead",
            "description": "",
        }

        result = aggregator._transform_npm_data("old-pkg", version_data, {}, {})

        assert result["yanked"] is True
        assert result["yanked_reason"] == "Use new-pkg instead"

    def test_transform_description_from_package_json_readme(
        self, sample_npm_package_json
    ):
        """Test that description is populated from package_json root-level readme."""
        aggregator = NpmAggregator(mode="first")
        version_data = sample_npm_package_json["versions"]["18.0.0"]
        time_info = sample_npm_package_json["time"]

        result = aggregator._transform_npm_data(
            "@plone/volto", version_data, time_info, sample_npm_package_json
        )

        # description should come from package_json's readme, not version_data
        assert result["description"] == sample_npm_package_json["readme"]
        assert "# @plone/volto" in result["description"]
        # summary should come from version_data's description
        assert result["summary"] == "Volto is the React-based frontend for Plone 6"


# ============================================================================
# Git URL Conversion Tests
# ============================================================================


class TestGitUrlConversion:
    """Test Git URL to HTTPS conversion."""

    def test_git_plus_https_url(self):
        """Test conversion of git+https:// URL."""
        aggregator = NpmAggregator(mode="first")
        url = "git+https://github.com/plone/volto.git"
        result = aggregator._git_url_to_https(url)
        assert result == "https://github.com/plone/volto"

    def test_git_protocol_url(self):
        """Test conversion of git:// URL."""
        aggregator = NpmAggregator(mode="first")
        url = "git://github.com/plone/volto.git"
        result = aggregator._git_url_to_https(url)
        assert result == "https://github.com/plone/volto"

    def test_ssh_url(self):
        """Test conversion of git@github.com: URL."""
        aggregator = NpmAggregator(mode="first")
        url = "git@github.com:plone/volto.git"
        result = aggregator._git_url_to_https(url)
        assert result == "https://github.com/plone/volto"

    def test_ssh_protocol_url(self):
        """Test conversion of ssh://git@ URL."""
        aggregator = NpmAggregator(mode="first")
        url = "ssh://git@github.com/plone/volto.git"
        result = aggregator._git_url_to_https(url)
        assert result == "https://github.com/plone/volto"

    def test_https_url_unchanged(self):
        """Test that https:// URL is returned without .git suffix."""
        aggregator = NpmAggregator(mode="first")
        url = "https://github.com/plone/volto.git"
        result = aggregator._git_url_to_https(url)
        assert result == "https://github.com/plone/volto"

    def test_empty_url(self):
        """Test that empty URL returns empty string."""
        aggregator = NpmAggregator(mode="first")
        assert aggregator._git_url_to_https("") == ""
        assert aggregator._git_url_to_https(None) == ""


# ============================================================================
# Version Extraction Tests
# ============================================================================


class TestVersionExtraction:
    """Test version extraction from package metadata."""

    def test_get_all_versions(self, sample_npm_package_json):
        """Test extracting all versions from package JSON."""
        aggregator = NpmAggregator(mode="first")
        versions = aggregator._get_all_versions(sample_npm_package_json)

        assert len(versions) == 2
        version_numbers = [v[0] for v in versions]
        assert "17.0.0" in version_numbers
        assert "18.0.0" in version_numbers

    def test_get_all_versions_includes_timestamps(self, sample_npm_package_json):
        """Test that version timestamps are extracted."""
        aggregator = NpmAggregator(mode="first")
        versions = aggregator._get_all_versions(sample_npm_package_json)

        for version, timestamp in versions:
            if version == "18.0.0":
                assert timestamp == "2024-01-15T10:30:00.000Z"
            elif version == "17.0.0":
                assert timestamp == "2023-06-15T12:00:00.000Z"


# ============================================================================
# Integration Tests
# ============================================================================


class TestNpmAggregatorIntegration:
    """Integration tests for NpmAggregator."""

    @responses.activate
    def test_search_packages_combines_keywords_and_scopes(
        self, sample_npm_search_response
    ):
        """Test that search combines keywords and scopes."""
        # Mock keyword search (URL-encoded: keywords%3Aplone)
        responses.add(
            responses.GET,
            re.compile(r"https://registry\.npmjs\.org/-/v1/search.*keywords%3Aplone"),
            json=sample_npm_search_response,
            status=200,
        )
        # Mock scope search (URL-encoded: scope%3Aplone)
        responses.add(
            responses.GET,
            re.compile(r"https://registry\.npmjs\.org/-/v1/search.*scope%3Aplone"),
            json=sample_npm_search_response,
            status=200,
        )

        aggregator = NpmAggregator(
            mode="first",
            filter_keywords=["plone"],
            filter_scopes=["@plone"],
        )
        packages = aggregator._search_packages()

        # Should deduplicate packages found by both keyword and scope
        assert "@plone/volto" in packages
        assert "@plone/registry" in packages
