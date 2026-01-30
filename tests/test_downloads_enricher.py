"""
Unit tests for pyf.aggregator.enrichers.downloads module.

This module tests:
- pypistats.org API fetching and error handling
- Rate limiting behavior
- Download statistics data enrichment
- Typesense document updates
- Memoization of API results
"""

import time
import pytest
import responses
from unittest.mock import patch, MagicMock
from datetime import datetime
import re

from pyf.aggregator.enrichers.downloads import Enricher, memoize


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def enricher():
    """Create an Enricher instance for testing."""
    with patch(
        "pyf.aggregator.enrichers.downloads.TypesenceConnection.__init__",
        return_value=None,
    ):
        with patch(
            "pyf.aggregator.enrichers.downloads.TypesensePackagesCollection.__init__",
            return_value=None,
        ):
            e = Enricher(limit=None)
            e.client = MagicMock()
            return e


@pytest.fixture
def enricher_with_limit():
    """Create an Enricher instance with a limit for testing."""
    with patch(
        "pyf.aggregator.enrichers.downloads.TypesenceConnection.__init__",
        return_value=None,
    ):
        with patch(
            "pyf.aggregator.enrichers.downloads.TypesensePackagesCollection.__init__",
            return_value=None,
        ):
            e = Enricher(limit=5)
            e.client = MagicMock()
            return e


@pytest.fixture
def sample_pypistats_response():
    """Sample pypistats.org API response."""
    return {
        "data": {
            "last_day": 1234,
            "last_week": 8765,
            "last_month": 35421,
        },
        "package": "plone.api",
        "type": "recent_downloads",
    }


@pytest.fixture
def sample_pypistats_response_with_nulls():
    """Sample pypistats.org API response with null values."""
    return {
        "data": {
            "last_day": None,
            "last_week": 100,
            "last_month": None,
        },
        "package": "test-package",
        "type": "recent_downloads",
    }


@pytest.fixture
def sample_typesense_search_results():
    """Sample Typesense search results."""
    return {
        "found": 100,
        "request_params": {"per_page": 50},
        "grouped_hits": [
            {
                "hits": [
                    {
                        "document": {
                            "id": "plone.api-1",
                            "name": "plone.api",
                            "version": "2.0.0",
                        }
                    }
                ]
            },
            {
                "hits": [
                    {
                        "document": {
                            "id": "plone.restapi-1",
                            "name": "plone.restapi",
                            "version": "8.0.0",
                        }
                    }
                ]
            },
        ],
    }


# ============================================================================
# pypistats.org API Tests
# ============================================================================


class TestGetPypistatsData:
    """Test the _get_pypistats_data method."""

    @responses.activate
    def test_returns_data_for_valid_package(self, enricher, sample_pypistats_response):
        """Test successful stats retrieval for a valid package."""
        responses.add(
            responses.GET,
            "https://pypistats.org/api/packages/plone.api/recent",
            json=sample_pypistats_response,
            status=200,
        )

        result = enricher._get_pypistats_data("plone.api")

        assert result is not None
        assert "downloads" in result
        assert result["downloads"]["last_day"] == 1234
        assert result["downloads"]["last_week"] == 8765
        assert result["downloads"]["last_month"] == 35421
        assert result["downloads"]["total"] is None
        assert isinstance(result["downloads"]["updated"], datetime)

    @responses.activate
    def test_returns_empty_dict_for_404(self, enricher):
        """Test that 404 response returns empty dict."""
        responses.add(
            responses.GET,
            "https://pypistats.org/api/packages/nonexistent-package/recent",
            status=404,
        )

        result = enricher._get_pypistats_data("nonexistent-package")
        assert result == {}

    @responses.activate
    def test_handles_rate_limiting_with_retry_after_header(
        self, enricher, sample_pypistats_response
    ):
        """Test that 429 rate limiting is handled with Retry-After header."""
        # First request returns 429, second succeeds
        responses.add(
            responses.GET,
            "https://pypistats.org/api/packages/rate-limited-package/recent",
            status=429,
            headers={"Retry-After": "0.1"},
        )
        responses.add(
            responses.GET,
            "https://pypistats.org/api/packages/rate-limited-package/recent",
            json=sample_pypistats_response,
            status=200,
        )

        result = enricher._get_pypistats_data("rate-limited-package")
        assert result is not None
        assert result["downloads"]["last_day"] == 1234

    @responses.activate
    def test_handles_rate_limiting_without_retry_after_header(
        self, enricher, sample_pypistats_response
    ):
        """Test that 429 rate limiting is handled without Retry-After header (exponential backoff)."""
        # First request returns 429, second succeeds
        responses.add(
            responses.GET,
            "https://pypistats.org/api/packages/rate-limited-package/recent",
            status=429,
        )
        responses.add(
            responses.GET,
            "https://pypistats.org/api/packages/rate-limited-package/recent",
            json=sample_pypistats_response,
            status=200,
        )

        result = enricher._get_pypistats_data("rate-limited-package")
        assert result is not None
        assert result["downloads"]["last_day"] == 1234

    @responses.activate
    def test_handles_invalid_retry_after_header(
        self, enricher, sample_pypistats_response
    ):
        """Test that invalid Retry-After header falls back to exponential backoff."""
        # First request returns 429 with invalid Retry-After, second succeeds
        responses.add(
            responses.GET,
            "https://pypistats.org/api/packages/rate-limited-package/recent",
            status=429,
            headers={"Retry-After": "invalid"},
        )
        responses.add(
            responses.GET,
            "https://pypistats.org/api/packages/rate-limited-package/recent",
            json=sample_pypistats_response,
            status=200,
        )

        result = enricher._get_pypistats_data("rate-limited-package")
        assert result is not None

    @responses.activate
    def test_returns_empty_dict_after_max_retries(self, enricher):
        """Test that empty dict is returned after max retries."""
        # All requests return 429
        for _ in range(4):  # More than max retries
            responses.add(
                responses.GET,
                "https://pypistats.org/api/packages/always-rate-limited/recent",
                status=429,
            )

        result = enricher._get_pypistats_data("always-rate-limited")
        assert result == {}

    @responses.activate
    def test_handles_timeout_with_retry(self, enricher, sample_pypistats_response):
        """Test that timeout triggers retry."""
        import requests

        # First request times out, second succeeds
        responses.add(
            responses.GET,
            "https://pypistats.org/api/packages/timeout-package/recent",
            body=requests.exceptions.Timeout(),
        )
        responses.add(
            responses.GET,
            "https://pypistats.org/api/packages/timeout-package/recent",
            json=sample_pypistats_response,
            status=200,
        )

        result = enricher._get_pypistats_data("timeout-package")
        assert result is not None
        assert result["downloads"]["last_day"] == 1234

    @responses.activate
    def test_returns_empty_dict_after_timeout_retries(self, enricher):
        """Test that empty dict is returned after timeout retries."""
        import requests

        # All requests time out
        for _ in range(4):
            responses.add(
                responses.GET,
                "https://pypistats.org/api/packages/always-timeout/recent",
                body=requests.exceptions.Timeout(),
            )

        result = enricher._get_pypistats_data("always-timeout")
        assert result == {}

    @responses.activate
    def test_handles_json_parse_error(self, enricher):
        """Test that invalid JSON returns empty dict."""
        responses.add(
            responses.GET,
            "https://pypistats.org/api/packages/bad-json-package/recent",
            body="not valid json {{{",
            status=200,
            content_type="application/json",
        )

        result = enricher._get_pypistats_data("bad-json-package")
        assert result == {}

    @responses.activate
    def test_handles_unexpected_status_code(self, enricher):
        """Test that unexpected status codes return empty dict."""
        responses.add(
            responses.GET,
            "https://pypistats.org/api/packages/server-error/recent",
            status=500,
        )

        result = enricher._get_pypistats_data("server-error")
        assert result == {}

    @responses.activate
    def test_handles_missing_data_field(self, enricher):
        """Test handling of response without 'data' field."""
        responses.add(
            responses.GET,
            "https://pypistats.org/api/packages/no-data/recent",
            json={"package": "no-data"},
            status=200,
        )

        result = enricher._get_pypistats_data("no-data")

        assert result is not None
        assert result["downloads"]["last_day"] == 0
        assert result["downloads"]["last_week"] == 0
        assert result["downloads"]["last_month"] == 0

    @responses.activate
    def test_handles_null_values_in_stats(
        self, enricher, sample_pypistats_response_with_nulls
    ):
        """Test that null values in stats are converted to 0."""
        responses.add(
            responses.GET,
            "https://pypistats.org/api/packages/test-package/recent",
            json=sample_pypistats_response_with_nulls,
            status=200,
        )

        result = enricher._get_pypistats_data("test-package")

        assert result["downloads"]["last_day"] == 0
        assert result["downloads"]["last_week"] == 100
        assert result["downloads"]["last_month"] == 0

    @responses.activate
    def test_handles_request_exception(self, enricher):
        """Test that request exceptions return empty dict."""
        import requests

        responses.add(
            responses.GET,
            "https://pypistats.org/api/packages/error-package/recent",
            body=requests.exceptions.ConnectionError("Connection failed"),
        )

        result = enricher._get_pypistats_data("error-package")
        assert result == {}


# ============================================================================
# Rate Limiting Tests
# ============================================================================


class TestRateLimiting:
    """Test the _apply_rate_limit method."""

    def test_sleeps_when_requests_too_fast(self, enricher):
        """Test that rate limiting sleeps when requests are too fast."""
        import pyf.aggregator.enrichers.downloads as downloads_module

        # Save original value
        original_delay = downloads_module.PYPISTATS_RATE_LIMIT_DELAY

        try:
            # Set a very short delay for testing
            downloads_module.PYPISTATS_RATE_LIMIT_DELAY = 0.1

            enricher._last_request_time = time.time()

            # Immediately try another request
            start_time = time.time()
            enricher._apply_rate_limit()
            elapsed = time.time() - start_time

            # Should have slept for approximately the delay time
            assert elapsed >= 0.05  # Allow some tolerance
        finally:
            # Restore original value
            downloads_module.PYPISTATS_RATE_LIMIT_DELAY = original_delay

    def test_no_sleep_when_enough_time_passed(self, enricher):
        """Test that rate limiting doesn't sleep when enough time has passed."""
        import pyf.aggregator.enrichers.downloads as downloads_module

        # Save original value
        original_delay = downloads_module.PYPISTATS_RATE_LIMIT_DELAY

        try:
            # Set a very short delay for testing
            downloads_module.PYPISTATS_RATE_LIMIT_DELAY = 0.1

            # Set last request time to past
            enricher._last_request_time = time.time() - 1.0

            # Should not sleep
            start_time = time.time()
            enricher._apply_rate_limit()
            elapsed = time.time() - start_time

            # Should be very fast (no sleep)
            assert elapsed < 0.05
        finally:
            # Restore original value
            downloads_module.PYPISTATS_RATE_LIMIT_DELAY = original_delay

    def test_updates_last_request_time(self, enricher):
        """Test that _apply_rate_limit updates the last request time."""
        old_time = enricher._last_request_time
        enricher._apply_rate_limit()
        assert enricher._last_request_time > old_time


# ============================================================================
# Memoization Tests
# ============================================================================


class TestMemoization:
    """Test the memoization decorator."""

    @responses.activate
    def test_memoizes_api_results(self, enricher, sample_pypistats_response):
        """Test that API results are memoized."""
        # Clear the memoization cache
        if hasattr(enricher._get_pypistats_data, "cache"):
            enricher._get_pypistats_data.cache.clear()

        # Only add one response
        responses.add(
            responses.GET,
            "https://pypistats.org/api/packages/plone.api/recent",
            json=sample_pypistats_response,
            status=200,
        )

        # First call should make HTTP request
        result1 = enricher._get_pypistats_data("plone.api")
        assert result1 is not None

        # Second call should use cached result (no additional HTTP request)
        result2 = enricher._get_pypistats_data("plone.api")
        assert result2 is not None

        # Both results should be the same
        assert result1["downloads"]["last_day"] == result2["downloads"]["last_day"]

        # Only one HTTP request should have been made
        assert len(responses.calls) == 1

    def test_memoize_decorator_with_simple_function(self):
        """Test the memoize decorator works correctly."""
        call_count = 0

        @memoize
        def test_func(self, key):
            nonlocal call_count
            call_count += 1
            return f"result-{key}"

        # Create a simple object to use as self
        obj = type("obj", (), {})()

        # First call
        result1 = test_func(obj, "test")
        assert result1 == "result-test"
        assert call_count == 1

        # Second call with same key should use cache
        result2 = test_func(obj, "test")
        assert result2 == "result-test"
        assert call_count == 1  # Should not increment

        # Call with different key
        result3 = test_func(obj, "other")
        assert result3 == "result-other"
        assert call_count == 2  # Should increment


# ============================================================================
# Document Update Tests
# ============================================================================


class TestUpdateDoc:
    """Test the update_doc method."""

    def test_updates_document_with_complete_data(self, enricher):
        """Test updating a document with complete download data."""
        mock_doc = MagicMock()
        enricher.client.collections = {
            "test_collection": MagicMock(documents={"test-id": mock_doc})
        }

        updated_time = datetime(2023, 6, 15, 12, 30, 0)
        data = {
            "downloads": {
                "last_day": 100,
                "last_week": 700,
                "last_month": 3000,
                "total": None,
                "updated": updated_time,
            }
        }

        enricher.update_doc(
            "test_collection", "test-id", data, page=1, enrich_counter=1
        )

        # Verify update was called with correct data
        mock_doc.update.assert_called_once()
        call_args = mock_doc.update.call_args[0][0]

        assert call_args["download_last_day"] == 100
        assert call_args["download_last_week"] == 700
        assert call_args["download_last_month"] == 3000
        assert call_args["download_updated"] == updated_time.timestamp()
        assert "download_total" not in call_args  # Should not include total when None

    def test_updates_document_with_total(self, enricher):
        """Test updating a document with total download count."""
        mock_doc = MagicMock()
        enricher.client.collections = {
            "test_collection": MagicMock(documents={"test-id": mock_doc})
        }

        updated_time = datetime(2023, 6, 15, 12, 30, 0)
        data = {
            "downloads": {
                "last_day": 100,
                "last_week": 700,
                "last_month": 3000,
                "total": 50000,
                "updated": updated_time,
            }
        }

        enricher.update_doc(
            "test_collection", "test-id", data, page=1, enrich_counter=1
        )

        # Verify update was called with correct data including total
        call_args = mock_doc.update.call_args[0][0]
        assert call_args["download_total"] == 50000


# ============================================================================
# Typesense Search Tests
# ============================================================================


class TestTsSearch:
    """Test the ts_search method."""

    def test_search_with_page_number(self, enricher):
        """Test that search adds page number to parameters."""
        mock_search = MagicMock(return_value={"found": 0})
        enricher.client.collections = {
            "test_collection": MagicMock(documents=MagicMock(search=mock_search))
        }

        search_params = {"q": "*", "query_by": "name"}
        enricher.ts_search("test_collection", search_params, page=3)

        # Verify search was called with page added to params
        mock_search.assert_called_once()
        call_args = mock_search.call_args[0][0]
        assert call_args["page"] == 3
        assert call_args["q"] == "*"


# ============================================================================
# Full Enrichment Flow Tests
# ============================================================================


class TestRun:
    """Test the run method (full enrichment flow)."""

    @responses.activate
    def test_enriches_packages_without_limit(self, enricher, sample_pypistats_response):
        """Test enriching packages without a limit."""
        # Mock Typesense search results
        mock_search_results = {
            "found": 2,
            "request_params": {"per_page": 50},
            "grouped_hits": [
                {"hits": [{"document": {"id": "plone.api-1", "name": "plone.api"}}]},
                {
                    "hits": [
                        {"document": {"id": "plone.restapi-1", "name": "plone.restapi"}}
                    ]
                },
            ],
        }

        enricher.ts_search = MagicMock(return_value=mock_search_results)
        enricher.update_doc = MagicMock()

        # Mock pypistats API
        responses.add(
            responses.GET,
            re.compile(r"https://pypistats\.org/api/packages/.+/recent"),
            json=sample_pypistats_response,
            status=200,
        )

        enricher.run("test_collection")

        # Should have updated both packages
        assert enricher.update_doc.call_count == 2

    @responses.activate
    def test_enriches_packages_with_limit(
        self, enricher_with_limit, sample_pypistats_response
    ):
        """Test enriching packages with a limit."""
        # Mock Typesense search results with many packages
        hits = [
            {"hits": [{"document": {"id": f"package-{i}", "name": f"package-{i}"}}]}
            for i in range(10)
        ]

        mock_search_results = {
            "found": 10,
            "request_params": {"per_page": 50},
            "grouped_hits": hits,
        }

        enricher_with_limit.ts_search = MagicMock(return_value=mock_search_results)
        enricher_with_limit.update_doc = MagicMock()

        # Mock pypistats API
        responses.add(
            responses.GET,
            re.compile(r"https://pypistats\.org/api/packages/.+/recent"),
            json=sample_pypistats_response,
            status=200,
        )

        enricher_with_limit.run("test_collection")

        # Should have updated only 5 packages (the limit)
        assert enricher_with_limit.update_doc.call_count == 5

    @responses.activate
    def test_skips_packages_without_name(self, enricher, sample_pypistats_response):
        """Test that packages without a name are skipped."""
        mock_search_results = {
            "found": 2,
            "request_params": {"per_page": 50},
            "grouped_hits": [
                {
                    "hits": [
                        {
                            "document": {
                                "id": "package-1",
                                # No name field
                            }
                        }
                    ]
                },
                {"hits": [{"document": {"id": "package-2", "name": "valid-package"}}]},
            ],
        }

        enricher.ts_search = MagicMock(return_value=mock_search_results)
        enricher.update_doc = MagicMock()

        # Mock pypistats API
        responses.add(
            responses.GET,
            "https://pypistats.org/api/packages/valid-package/recent",
            json=sample_pypistats_response,
            status=200,
        )

        enricher.run("test_collection")

        # Should have updated only the valid package
        assert enricher.update_doc.call_count == 1

    @responses.activate
    def test_skips_packages_with_no_stats(self, enricher):
        """Test that packages with no stats are skipped."""
        mock_search_results = {
            "found": 2,
            "request_params": {"per_page": 50},
            "grouped_hits": [
                {
                    "hits": [
                        {"document": {"id": "package-1", "name": "no-stats-package"}}
                    ]
                },
                {"hits": [{"document": {"id": "package-2", "name": "valid-package"}}]},
            ],
        }

        enricher.ts_search = MagicMock(return_value=mock_search_results)
        enricher.update_doc = MagicMock()

        # First package returns 404, second succeeds
        responses.add(
            responses.GET,
            "https://pypistats.org/api/packages/no-stats-package/recent",
            status=404,
        )
        responses.add(
            responses.GET,
            "https://pypistats.org/api/packages/valid-package/recent",
            json={"data": {"last_day": 100, "last_week": 700, "last_month": 3000}},
            status=200,
        )

        enricher.run("test_collection")

        # Should have updated only the valid package
        assert enricher.update_doc.call_count == 1

    def test_handles_pagination(self, enricher):
        """Test that pagination is handled correctly."""
        # First page
        first_page_results = {
            "found": 100,
            "request_params": {"per_page": 50},
            "grouped_hits": [
                {"hits": [{"document": {"id": f"package-{i}", "name": f"package-{i}"}}]}
                for i in range(50)
            ],
        }

        # Second page
        second_page_results = {
            "found": 100,
            "request_params": {"per_page": 50},
            "grouped_hits": [
                {"hits": [{"document": {"id": f"package-{i}", "name": f"package-{i}"}}]}
                for i in range(50, 100)
            ],
        }

        # Mock search to return different results based on page
        def mock_search_side_effect(target, params, page=1):
            if page == 1:
                return first_page_results
            elif page == 2:
                return second_page_results
            return {
                "found": 100,
                "request_params": {"per_page": 50},
                "grouped_hits": [],
            }

        enricher.ts_search = MagicMock(side_effect=mock_search_side_effect)
        enricher._get_pypistats_data = MagicMock(
            return_value={}
        )  # Return empty to skip updates

        enricher.run("test_collection")

        # Should have called search for page 1 and page 2
        assert enricher.ts_search.call_count >= 2
