"""
Unit tests for pyf.aggregator.fetcher module.

This module tests:
- Classifier filtering (has_plone_classifier method)
- PyPI JSON API parsing and error handling
- PyPI Simple API parsing
- RSS feed parsing
- Rate limiting behavior
"""

import time
import pytest
import responses
from unittest.mock import patch, MagicMock
import re

from pyf.aggregator.fetcher import Aggregator, PLONE_CLASSIFIER


class FeedParserEntry:
    """Mock feedparser entry that supports both dict-like and attribute access."""

    def __init__(self, data):
        self._data = data
        for key, value in data.items():
            setattr(self, key, value)

    def get(self, key, default=""):
        return self._data.get(key, default)

    def __contains__(self, key):
        return key in self._data


# ============================================================================
# Classifier Filtering Tests
# ============================================================================

class TestHasPloneClassifier:
    """Test the has_plone_classifier method."""

    def test_returns_true_for_exact_plone_classifier(self, aggregator_first_mode):
        """Test that exact 'Framework :: Plone' classifier matches."""
        package_json = {
            "info": {
                "classifiers": ["Framework :: Plone"]
            }
        }
        assert aggregator_first_mode.has_plone_classifier(package_json) is True

    def test_returns_true_for_plone_subclassifier(self, aggregator_first_mode):
        """Test that Plone subclassifiers like 'Framework :: Plone :: 6.0' match."""
        package_json = {
            "info": {
                "classifiers": [
                    "Development Status :: 5 - Production/Stable",
                    "Framework :: Plone :: 6.0",
                ]
            }
        }
        assert aggregator_first_mode.has_plone_classifier(package_json) is True

    def test_returns_true_for_multiple_plone_classifiers(self, aggregator_first_mode):
        """Test that multiple Plone classifiers work correctly."""
        package_json = {
            "info": {
                "classifiers": [
                    "Framework :: Plone",
                    "Framework :: Plone :: 5.2",
                    "Framework :: Plone :: 6.0",
                ]
            }
        }
        assert aggregator_first_mode.has_plone_classifier(package_json) is True

    def test_returns_false_for_non_plone_package(self, aggregator_first_mode, sample_pypi_json_non_plone):
        """Test that non-Plone packages return False."""
        assert aggregator_first_mode.has_plone_classifier(sample_pypi_json_non_plone) is False

    def test_returns_false_for_empty_classifiers(self, aggregator_first_mode, sample_pypi_json_empty_classifiers):
        """Test that empty classifiers list returns False."""
        assert aggregator_first_mode.has_plone_classifier(sample_pypi_json_empty_classifiers) is False

    def test_returns_false_for_missing_info(self, aggregator_first_mode, sample_pypi_json_no_info):
        """Test that missing 'info' section returns False."""
        assert aggregator_first_mode.has_plone_classifier(sample_pypi_json_no_info) is False

    def test_returns_false_for_missing_classifiers(self, aggregator_first_mode):
        """Test that missing 'classifiers' key returns False."""
        package_json = {"info": {"name": "test"}}
        assert aggregator_first_mode.has_plone_classifier(package_json) is False

    def test_returns_false_for_empty_dict(self, aggregator_first_mode):
        """Test that empty dict returns False without error."""
        assert aggregator_first_mode.has_plone_classifier({}) is False

    def test_returns_false_for_other_frameworks(self, aggregator_first_mode):
        """Test that other framework classifiers don't match."""
        package_json = {
            "info": {
                "classifiers": [
                    "Framework :: Django",
                    "Framework :: Flask",
                    "Framework :: Pyramid",
                ]
            }
        }
        assert aggregator_first_mode.has_plone_classifier(package_json) is False


# ============================================================================
# PyPI JSON API Tests
# ============================================================================

class TestGetPypiJson:
    """Test the _get_pypi_json method."""

    @responses.activate
    def test_returns_json_for_valid_package(self, sample_pypi_json_plone):
        """Test successful JSON retrieval for a valid package."""
        # Match both single and double slash patterns
        responses.add(
            responses.GET,
            re.compile(r"https://pypi\.org/+pypi/plone\.api/json"),
            json=sample_pypi_json_plone,
            status=200,
        )

        aggregator = Aggregator(mode="first")
        result = aggregator._get_pypi_json("plone.api")
        assert result is not None
        assert result["info"]["name"] == "plone.api"
        assert "Framework :: Plone" in result["info"]["classifiers"]

    @responses.activate
    def test_returns_none_for_404(self):
        """Test that 404 response returns None."""
        responses.add(
            responses.GET,
            re.compile(r"https://pypi\.org/+pypi/nonexistent-package/json"),
            status=404,
        )

        aggregator = Aggregator(mode="first")
        result = aggregator._get_pypi_json("nonexistent-package")
        assert result is None

    @responses.activate
    def test_handles_rate_limiting(self, sample_pypi_json_plone):
        """Test that 429 rate limiting is handled with retry."""
        # First request returns 429, second succeeds
        responses.add(
            responses.GET,
            re.compile(r"https://pypi\.org/+pypi/rate-limited-package/json"),
            status=429,
            headers={"Retry-After": "1"},
        )
        responses.add(
            responses.GET,
            re.compile(r"https://pypi\.org/+pypi/rate-limited-package/json"),
            json=sample_pypi_json_plone,
            status=200,
        )

        aggregator = Aggregator(mode="first")
        result = aggregator._get_pypi_json("rate-limited-package")
        assert result is not None
        assert result["info"]["name"] == "plone.api"

    @responses.activate
    def test_handles_server_error_with_retry(self, sample_pypi_json_plone):
        """Test that 500 errors trigger retry."""
        # First request returns 500, second succeeds
        responses.add(
            responses.GET,
            re.compile(r"https://pypi\.org/+pypi/server-error-package/json"),
            status=500,
        )
        responses.add(
            responses.GET,
            re.compile(r"https://pypi\.org/+pypi/server-error-package/json"),
            json=sample_pypi_json_plone,
            status=200,
        )

        aggregator = Aggregator(mode="first")
        result = aggregator._get_pypi_json("server-error-package")
        assert result is not None

    @responses.activate
    def test_handles_json_parse_error(self):
        """Test that invalid JSON returns None."""
        responses.add(
            responses.GET,
            re.compile(r"https://pypi\.org/+pypi/bad-json-package/json"),
            body="not valid json {{{",
            status=200,
            content_type="application/json",
        )

        aggregator = Aggregator(mode="first")
        result = aggregator._get_pypi_json("bad-json-package")
        assert result is None

    @responses.activate
    def test_with_specific_release_version(self, sample_pypi_json_plone):
        """Test fetching a specific release version."""
        responses.add(
            responses.GET,
            re.compile(r"https://pypi\.org/+pypi/plone\.api/2\.0\.0/json"),
            json=sample_pypi_json_plone,
            status=200,
        )

        aggregator = Aggregator(mode="first")
        result = aggregator._get_pypi_json("plone.api", "2.0.0")
        assert result is not None
        assert result["info"]["version"] == "2.0.0"


# ============================================================================
# Simple API Tests
# ============================================================================

class TestAllPackageIds:
    """Test the _all_package_ids property."""

    @responses.activate
    def test_returns_package_list(self, sample_simple_api_response):
        """Test that Simple API returns package list."""
        responses.add(
            responses.GET,
            re.compile(r"https://pypi\.org/+simple"),
            json=sample_simple_api_response,
            status=200,
        )

        aggregator = Aggregator(mode="first")
        package_ids = list(aggregator._all_package_ids)
        assert len(package_ids) == 4
        assert "plone.api" in package_ids
        assert "requests" in package_ids

    @responses.activate
    def test_applies_name_filter(self, sample_simple_api_response):
        """Test that filter_name filters packages correctly."""
        responses.add(
            responses.GET,
            re.compile(r"https://pypi\.org/+simple"),
            json=sample_simple_api_response,
            status=200,
        )

        aggregator = Aggregator(mode="first", filter_name="plone")
        package_ids = list(aggregator._all_package_ids)

        assert "plone.api" in package_ids
        assert "plone.app.contenttypes" in package_ids
        assert "requests" not in package_ids
        assert "django" not in package_ids

    @responses.activate
    def test_handles_empty_projects(self):
        """Test that empty projects list raises ValueError."""
        responses.add(
            responses.GET,
            re.compile(r"https://pypi\.org/+simple"),
            json={"projects": []},
            status=200,
        )

        aggregator = Aggregator(mode="first")
        with pytest.raises(ValueError, match="Empty projects list"):
            list(aggregator._all_package_ids)

    @responses.activate
    def test_handles_non_200_response(self):
        """Test that non-200 response raises ValueError."""
        responses.add(
            responses.GET,
            re.compile(r"https://pypi\.org/+simple"),
            status=500,
        )

        aggregator = Aggregator(mode="first")
        with pytest.raises(ValueError, match="Not 200 OK"):
            list(aggregator._all_package_ids)


# ============================================================================
# RSS Feed Parsing Tests
# ============================================================================

class TestParseRssFeed:
    """Test the _parse_rss_feed method."""

    def test_parses_rss_entries(self, aggregator_first_mode, sample_rss_feed_xml):
        """Test that RSS feed entries are parsed correctly."""
        with patch('feedparser.parse') as mock_parse:
            # Create mock feed with entries
            mock_feed = MagicMock()
            mock_feed.bozo = False
            mock_feed.bozo_exception = None
            mock_feed.entries = [
                FeedParserEntry({
                    "title": "plone.api 2.0.0",
                    "link": "https://pypi.org/project/plone.api/2.0.0/",
                    "summary": "A simple API for Plone",
                    "published_parsed": time.strptime("2023-06-15", "%Y-%m-%d"),
                }),
                FeedParserEntry({
                    "title": "requests 2.31.0",
                    "link": "https://pypi.org/project/requests/2.31.0/",
                    "summary": "Python HTTP for Humans",
                    "published_parsed": time.strptime("2023-05-22", "%Y-%m-%d"),
                }),
                FeedParserEntry({
                    "title": "plone.restapi 8.0.0",
                    "link": "https://pypi.org/project/plone.restapi/8.0.0/",
                    "summary": "RESTful API for Plone",
                    "published_parsed": time.strptime("2023-06-14", "%Y-%m-%d"),
                }),
            ]
            mock_parse.return_value = mock_feed

            entries = aggregator_first_mode._parse_rss_feed("https://pypi.org/rss/updates.xml")

            assert len(entries) == 3
            assert entries[0]["package_id"] == "plone.api"
            assert entries[0]["release_id"] == "2.0.0"
            assert entries[0]["link"] == "https://pypi.org/project/plone.api/2.0.0/"

    def test_extracts_timestamp(self, aggregator_first_mode):
        """Test that timestamps are extracted from RSS entries."""
        with patch('feedparser.parse') as mock_parse:
            mock_feed = MagicMock()
            mock_feed.bozo = False
            mock_feed.bozo_exception = None
            mock_feed.entries = [
                FeedParserEntry({
                    "title": "test-package 1.0.0",
                    "link": "https://pypi.org/project/test-package/1.0.0/",
                    "summary": "",
                    "published_parsed": time.strptime("2023-06-15", "%Y-%m-%d"),
                }),
            ]
            mock_parse.return_value = mock_feed

            entries = aggregator_first_mode._parse_rss_feed("https://pypi.org/rss/updates.xml")

            assert len(entries) == 1
            assert entries[0]["timestamp"] is not None
            assert isinstance(entries[0]["timestamp"], float)

    def test_applies_name_filter(self):
        """Test that filter_name is applied to RSS entries."""
        with patch('feedparser.parse') as mock_parse:
            mock_feed = MagicMock()
            mock_feed.bozo = False
            mock_feed.bozo_exception = None
            mock_feed.entries = [
                FeedParserEntry({
                    "title": "plone.api 2.0.0",
                    "link": "https://pypi.org/project/plone.api/2.0.0/",
                    "summary": "",
                    "published_parsed": time.strptime("2023-06-15", "%Y-%m-%d"),
                }),
                FeedParserEntry({
                    "title": "requests 2.31.0",
                    "link": "https://pypi.org/project/requests/2.31.0/",
                    "summary": "",
                    "published_parsed": time.strptime("2023-05-22", "%Y-%m-%d"),
                }),
                FeedParserEntry({
                    "title": "plone.restapi 8.0.0",
                    "link": "https://pypi.org/project/plone.restapi/8.0.0/",
                    "summary": "",
                    "published_parsed": time.strptime("2023-06-14", "%Y-%m-%d"),
                }),
            ]
            mock_parse.return_value = mock_feed

            aggregator = Aggregator(mode="incremental", filter_name="plone")
            entries = aggregator._parse_rss_feed("https://pypi.org/rss/updates.xml")

            # Only plone packages should be returned
            package_ids = [e["package_id"] for e in entries]
            assert "plone.api" in package_ids
            assert "plone.restapi" in package_ids
            assert "requests" not in package_ids

    def test_handles_empty_feed(self, aggregator_first_mode):
        """Test that empty RSS feed returns empty list."""
        with patch('feedparser.parse') as mock_parse:
            mock_feed = MagicMock()
            mock_feed.bozo = False
            mock_feed.bozo_exception = None
            mock_feed.entries = []
            mock_parse.return_value = mock_feed

            entries = aggregator_first_mode._parse_rss_feed("https://pypi.org/rss/empty.xml")
            assert entries == []


class TestParseRssEntry:
    """Test the _parse_rss_entry method."""

    def test_parses_standard_entry(self, aggregator_first_mode):
        """Test parsing a standard RSS entry."""
        entry = FeedParserEntry({
            "title": "plone.api 2.0.0",
            "link": "https://pypi.org/project/plone.api/2.0.0/",
            "summary": "A simple API for Plone",
            "published_parsed": time.strptime("2023-06-15", "%Y-%m-%d"),
        })

        result = aggregator_first_mode._parse_rss_entry(entry)

        assert result["package_id"] == "plone.api"
        assert result["release_id"] == "2.0.0"
        assert result["timestamp"] is not None

    def test_parses_entry_with_dashes_in_name(self, aggregator_first_mode):
        """Test parsing entry with dashes in package name."""
        entry = FeedParserEntry({
            "title": "plone-app-contenttypes 1.0.0",
            "link": "https://pypi.org/project/plone-app-contenttypes/1.0.0/",
            "summary": "",
            "published_parsed": None,
        })

        result = aggregator_first_mode._parse_rss_entry(entry)

        assert result["package_id"] == "plone-app-contenttypes"
        assert result["release_id"] == "1.0.0"

    def test_returns_none_for_empty_title(self, aggregator_first_mode):
        """Test that empty title with no link returns None."""
        entry = FeedParserEntry({
            "title": "",
            "link": "",
            "summary": "",
        })

        result = aggregator_first_mode._parse_rss_entry(entry)
        assert result is None

    def test_extracts_from_link_fallback(self, aggregator_first_mode):
        """Test extraction from link when title is missing."""
        entry = FeedParserEntry({
            "title": "",
            "link": "https://pypi.org/project/some-package/1.0.0/",
            "summary": "",
            "published_parsed": None,
        })

        result = aggregator_first_mode._parse_rss_entry(entry)

        assert result["package_id"] == "some-package"
        assert result["release_id"] == "1.0.0"

    def test_handles_entry_without_version(self, aggregator_first_mode):
        """Test parsing entry without version in title."""
        entry = FeedParserEntry({
            "title": "some-package",
            "link": "https://pypi.org/project/some-package/",
            "summary": "",
            "published_parsed": None,
        })

        result = aggregator_first_mode._parse_rss_entry(entry)

        assert result["package_id"] == "some-package"
        # release_id may be None when not specified


# ============================================================================
# Package Updates (Incremental Mode) Tests
# ============================================================================

class TestPackageUpdates:
    """Test the _package_updates method for incremental mode."""

    def test_yields_updates_since_timestamp(self, aggregator_incremental_mode):
        """Test that updates are filtered by timestamp."""
        with patch('feedparser.parse') as mock_parse:
            mock_feed = MagicMock()
            mock_feed.bozo = False
            mock_feed.bozo_exception = None
            mock_feed.entries = [
                FeedParserEntry({
                    "title": "plone.api 2.0.0",
                    "link": "https://pypi.org/project/plone.api/2.0.0/",
                    "summary": "",
                    "published_parsed": time.strptime("2023-06-15", "%Y-%m-%d"),
                }),
                FeedParserEntry({
                    "title": "requests 2.31.0",
                    "link": "https://pypi.org/project/requests/2.31.0/",
                    "summary": "",
                    "published_parsed": time.strptime("2023-05-22", "%Y-%m-%d"),
                }),
            ]
            mock_parse.return_value = mock_feed

            # Use a very old timestamp so all entries pass
            updates = list(aggregator_incremental_mode._package_updates(0))

            # Should have unique packages from the feed
            package_ids = [u[0] for u in updates]
            assert len(set(package_ids)) == len(package_ids)  # All unique

    def test_deduplicates_packages(self):
        """Test that duplicate packages from both feeds are deduplicated."""
        with patch('feedparser.parse') as mock_parse:
            mock_feed = MagicMock()
            mock_feed.bozo = False
            mock_feed.bozo_exception = None
            mock_feed.entries = [
                FeedParserEntry({
                    "title": "plone.api 2.0.0",
                    "link": "https://pypi.org/project/plone.api/2.0.0/",
                    "summary": "",
                    "published_parsed": time.strptime("2023-06-15", "%Y-%m-%d"),
                }),
            ]
            mock_parse.return_value = mock_feed

            aggregator = Aggregator(mode="incremental", sincefile=".test_sincefile")
            updates = list(aggregator._package_updates(0))

            # Should only have one plone.api entry despite appearing in both feeds
            assert len(updates) == 1
            assert updates[0][0] == "plone.api"


# ============================================================================
# Rate Limiting Tests
# ============================================================================

class TestRateLimiting:
    """Test the rate limiting functionality."""

    @responses.activate
    def test_applies_rate_limit_delay(self, sample_pypi_json_plone, sample_pypi_json_non_plone):
        """Test that rate limiting delay is applied between requests."""
        responses.add(
            responses.GET,
            re.compile(r"https://pypi\.org/+pypi/plone\.api/json"),
            json=sample_pypi_json_plone,
            status=200,
        )
        responses.add(
            responses.GET,
            re.compile(r"https://pypi\.org/+pypi/requests/json"),
            json=sample_pypi_json_non_plone,
            status=200,
        )

        aggregator = Aggregator(mode="first")
        # Make two requests quickly
        start_time = time.time()

        aggregator._get_pypi_json("plone.api")
        aggregator._get_pypi_json("requests")

        elapsed = time.time() - start_time

        # Should have waited at least the rate limit delay between requests
        # Default is 0.1 seconds
        assert elapsed >= 0.1


# ============================================================================
# Full Download Flow Tests
# ============================================================================

class TestAllPackages:
    """Test the _all_packages property for full download."""

    @responses.activate
    def test_yields_package_releases(self, sample_simple_api_response, sample_pypi_json_plone):
        """Test that _all_packages yields package releases."""
        # Mock simple API
        responses.add(
            responses.GET,
            re.compile(r"https://pypi\.org/+simple"),
            json={"projects": [{"name": "plone.api"}]},
            status=200,
        )
        # Mock JSON API
        responses.add(
            responses.GET,
            re.compile(r"https://pypi\.org/+pypi/plone\.api/json"),
            json=sample_pypi_json_plone,
            status=200,
        )

        aggregator = Aggregator(mode="first", limit=5)
        packages = list(aggregator._all_packages)

        # Should yield tuples of (package_id, release_id, timestamp)
        assert len(packages) > 0
        assert packages[0][0] == "plone.api"  # package_id
        assert packages[0][1] in ["1.0.0", "2.0.0"]  # release_id

    @responses.activate
    def test_filters_by_plone_classifier(self, sample_pypi_json_plone, sample_pypi_json_non_plone):
        """Test that classifier filtering works in full download mode."""
        # Mock simple API
        responses.add(
            responses.GET,
            re.compile(r"https://pypi\.org/+simple"),
            json={"projects": [{"name": "plone.api"}, {"name": "requests"}]},
            status=200,
        )
        # Mock JSON API for both packages
        responses.add(
            responses.GET,
            re.compile(r"https://pypi\.org/+pypi/plone\.api/json"),
            json=sample_pypi_json_plone,
            status=200,
        )
        responses.add(
            responses.GET,
            re.compile(r"https://pypi\.org/+pypi/requests/json"),
            json=sample_pypi_json_non_plone,
            status=200,
        )

        aggregator = Aggregator(mode="first", filter_troove="Framework :: Plone", limit=10)
        packages = list(aggregator._all_packages)

        # Should only yield Plone packages
        package_ids = [p[0] for p in packages]
        assert "plone.api" in package_ids
        assert "requests" not in package_ids


# ============================================================================
# Project List Tests
# ============================================================================

class TestProjectList:
    """Test the _project_list property."""

    @responses.activate
    def test_yields_all_packages_without_filter(self, sample_simple_api_response):
        """Test that project list yields all packages when no filter."""
        responses.add(
            responses.GET,
            re.compile(r"https://pypi\.org/+simple"),
            json=sample_simple_api_response,
            status=200,
        )

        aggregator = Aggregator(mode="first", limit=10)
        package_ids = list(aggregator._project_list)

        assert len(package_ids) == 4
        assert "plone.api" in package_ids
        assert "requests" in package_ids

    @responses.activate
    def test_applies_classifier_filter(self, sample_pypi_json_plone, sample_pypi_json_non_plone):
        """Test that classifier filter is applied in project list."""
        # Mock simple API
        responses.add(
            responses.GET,
            re.compile(r"https://pypi\.org/+simple"),
            json={"projects": [{"name": "plone.api"}, {"name": "requests"}]},
            status=200,
        )
        # Mock JSON API
        responses.add(
            responses.GET,
            re.compile(r"https://pypi\.org/+pypi/plone\.api/json"),
            json=sample_pypi_json_plone,
            status=200,
        )
        responses.add(
            responses.GET,
            re.compile(r"https://pypi\.org/+pypi/requests/json"),
            json=sample_pypi_json_non_plone,
            status=200,
        )

        aggregator = Aggregator(
            mode="first",
            filter_troove="Framework :: Plone",
            limit=10,
        )
        package_ids = list(aggregator._project_list)

        assert "plone.api" in package_ids
        assert "requests" not in package_ids

    @responses.activate
    def test_respects_limit(self, sample_simple_api_response):
        """Test that limit is respected in project list."""
        responses.add(
            responses.GET,
            re.compile(r"https://pypi\.org/+simple"),
            json=sample_simple_api_response,
            status=200,
        )

        aggregator = Aggregator(mode="first", limit=2)
        package_ids = list(aggregator._project_list)

        assert len(package_ids) == 2


# ============================================================================
# PLONE_CLASSIFIER Constant Tests
# ============================================================================

class TestPloneClassifierConstant:
    """Test the PLONE_CLASSIFIER constant."""

    def test_constant_value(self):
        """Test that PLONE_CLASSIFIER has correct value."""
        assert PLONE_CLASSIFIER == "Framework :: Plone"

    def test_used_in_has_plone_classifier(self, aggregator_first_mode):
        """Test that constant is used in has_plone_classifier method."""
        # This is implicitly tested by the classifier tests above,
        # but explicit test confirms the integration
        package_json = {"info": {"classifiers": [PLONE_CLASSIFIER]}}
        assert aggregator_first_mode.has_plone_classifier(package_json) is True


# ============================================================================
# Aggregator Initialization Tests
# ============================================================================

class TestAggregatorInit:
    """Test Aggregator initialization."""

    def test_default_pypi_base_url(self):
        """Test that default PyPI base URL is set correctly."""
        aggregator = Aggregator(mode="first")
        assert aggregator.pypi_base_url == "https://pypi.org/"

    def test_custom_pypi_base_url(self):
        """Test that custom PyPI base URL can be set."""
        aggregator = Aggregator(mode="first", pypi_base_url="https://test.pypi.org/")
        assert aggregator.pypi_base_url == "https://test.pypi.org/"

    def test_mode_first(self):
        """Test first mode initialization."""
        aggregator = Aggregator(mode="first")
        assert aggregator.mode == "first"

    def test_mode_incremental(self):
        """Test incremental mode initialization."""
        aggregator = Aggregator(mode="incremental")
        assert aggregator.mode == "incremental"

    def test_filter_name_set(self):
        """Test filter_name is set correctly."""
        aggregator = Aggregator(mode="first", filter_name="plone")
        assert aggregator.filter_name == "plone"

    def test_filter_troove_set(self):
        """Test filter_troove is set correctly."""
        aggregator = Aggregator(mode="first", filter_troove="Framework :: Plone")
        assert aggregator.filter_troove == "Framework :: Plone"

    def test_limit_set(self):
        """Test limit is set correctly."""
        aggregator = Aggregator(mode="first", limit=100)
        assert aggregator.limit == 100

    def test_skip_github_set(self):
        """Test skip_github is set correctly."""
        aggregator = Aggregator(mode="first", skip_github=True)
        assert aggregator.skip_github is True
