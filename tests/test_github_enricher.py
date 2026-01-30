"""
Unit tests for pyf.aggregator.enrichers.github module.

This module tests:
- GitHub API data fetching
- Rate limiting behavior
- Repository identifier extraction
- GitHub contributors fetching
- Typesense document updates with GitHub data
- Full enrichment flow
"""

import time
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime

from pyf.aggregator.enrichers.github import Enricher, memoize


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def enricher():
    """Create an Enricher instance for testing."""
    with patch(
        "pyf.aggregator.enrichers.github.TypesenceConnection.__init__",
        return_value=None,
    ):
        with patch(
            "pyf.aggregator.enrichers.github.TypesensePackagesCollection.__init__",
            return_value=None,
        ):
            e = Enricher()
            e.client = MagicMock()
            return e


@pytest.fixture
def sample_github_repo():
    """Create a mock GitHub repository object."""
    repo = MagicMock()
    repo.stargazers_count = 500
    repo.subscribers_count = 50
    repo.open_issues = 10
    repo.archived = False
    repo.updated_at = datetime(2023, 6, 15, 12, 30, 0)
    repo.html_url = "https://github.com/plone/plone.api"
    repo.full_name = "plone/plone.api"
    repo.description = "A simple API for Plone"
    repo.forks_count = 100
    repo.language = "Python"
    repo.default_branch = "main"
    return repo


@pytest.fixture
def sample_github_contributors():
    """Create mock GitHub contributor objects."""
    contributors = []
    for i, (username, contributions) in enumerate(
        [
            ("timo", 150),
            ("davisagli", 120),
            ("sneridagh", 80),
            ("tisto", 60),
            ("jensens", 40),
            ("someone", 10),
        ]
    ):
        contributor = MagicMock()
        contributor.login = username
        contributor.avatar_url = f"https://avatars.githubusercontent.com/u/{1000 + i}"
        contributor.contributions = contributions
        contributors.append(contributor)
    return contributors


@pytest.fixture
def sample_typesense_search_results():
    """Sample Typesense search results."""
    return {
        "found": 2,
        "request_params": {"per_page": 50},
        "grouped_hits": [
            {
                "hits": [
                    {
                        "document": {
                            "id": "plone.api-2.0.0",
                            "name": "plone.api",
                            "version": "2.0.0",
                            "home_page": "https://github.com/plone/plone.api",
                        }
                    }
                ]
            },
            {
                "hits": [
                    {
                        "document": {
                            "id": "plone.restapi-8.0.0",
                            "name": "plone.restapi",
                            "version": "8.0.0",
                            "project_urls": {
                                "Homepage": "https://github.com/plone/plone.restapi"
                            },
                        }
                    }
                ]
            },
        ],
    }


# ============================================================================
# Repository Identifier Extraction Tests
# ============================================================================


class TestGetPackageRepoIdentifier:
    """Test the get_package_repo_identifier method."""

    def test_extracts_from_home_page(self, enricher):
        """Test extraction from home_page field."""
        data = {"home_page": "https://github.com/plone/plone.api"}
        result = enricher.get_package_repo_identifier(data)
        assert result == "plone/plone.api"

    def test_extracts_from_project_url(self, enricher):
        """Test extraction from project_url field."""
        data = {"home_page": None, "project_url": "https://github.com/plone/plone.api"}
        result = enricher.get_package_repo_identifier(data)
        assert result == "plone/plone.api"

    def test_extracts_from_url_field(self, enricher):
        """Test extraction from url field."""
        data = {
            "home_page": None,
            "project_url": None,
            "url": "https://github.com/plone/plone.api",
        }
        result = enricher.get_package_repo_identifier(data)
        assert result == "plone/plone.api"

    def test_extracts_from_project_urls(self, enricher):
        """Test extraction from project_urls dict."""
        data = {
            "home_page": None,
            "project_url": None,
            "project_urls": {"Homepage": "https://github.com/plone/plone.api"},
        }
        result = enricher.get_package_repo_identifier(data)
        assert result == "plone/plone.api"

    def test_handles_github_url_with_www(self, enricher):
        """Test handling of www.github.com URLs."""
        data = {"home_page": "www.github.com/plone/plone.api"}
        result = enricher.get_package_repo_identifier(data)
        assert result == "plone/plone.api"

    def test_handles_github_url_with_subpath(self, enricher):
        """Test handling of GitHub URLs with subpaths."""
        data = {"home_page": "https://github.com/plone/plone.api/tree/main/docs"}
        result = enricher.get_package_repo_identifier(data)
        assert result == "plone/plone.api"

    def test_returns_none_for_non_github_url(self, enricher):
        """Test that None is returned for non-GitHub URLs."""
        data = {"home_page": "https://readthedocs.io/plone.api"}
        result = enricher.get_package_repo_identifier(data)
        assert result is None

    def test_returns_none_for_empty_data(self, enricher):
        """Test that None is returned for empty data."""
        data = {}
        result = enricher.get_package_repo_identifier(data)
        assert result is None


# ============================================================================
# GitHub API Data Fetching Tests
# ============================================================================


class TestGetGithubData:
    """Test the _get_github_data method."""

    def test_returns_github_data_for_valid_repo(self, enricher, sample_github_repo):
        """Test successful GitHub data retrieval."""
        # Clear the memoization cache
        if hasattr(enricher._get_github_data, "cache"):
            enricher._get_github_data.cache.clear()

        with patch("pyf.aggregator.enrichers.github.Github") as mock_github_class:
            mock_github = MagicMock()
            mock_github.get_repo.return_value = sample_github_repo
            mock_github_class.return_value = mock_github

            result = enricher._get_github_data("plone/plone.api")

        assert result is not None
        assert "github" in result
        assert result["github"]["stars"] == 500
        assert result["github"]["watchers"] == 50
        assert result["github"]["open_issues"] == 10
        assert result["github"]["gh_url"] == "https://github.com/plone/plone.api"

    def test_returns_empty_dict_for_404(self, enricher):
        """Test that empty dict is returned for non-existent repo."""
        if hasattr(enricher._get_github_data, "cache"):
            enricher._get_github_data.cache.clear()

        from github import UnknownObjectException

        with patch("pyf.aggregator.enrichers.github.Github") as mock_github_class:
            mock_github = MagicMock()
            mock_github.get_repo.side_effect = UnknownObjectException(
                404, "Not Found", {}
            )
            mock_github_class.return_value = mock_github

            result = enricher._get_github_data("nonexistent/repo")

        assert result == {}

    def test_handles_rate_limit_exceeded(self, enricher, sample_github_repo):
        """Test handling of GitHub rate limit exceeded."""
        if hasattr(enricher._get_github_data, "cache"):
            enricher._get_github_data.cache.clear()

        from github import RateLimitExceededException

        with patch("pyf.aggregator.enrichers.github.Github") as mock_github_class:
            mock_github = MagicMock()
            # First call raises rate limit, second succeeds
            mock_github.get_repo.side_effect = [
                RateLimitExceededException(403, "Rate limit exceeded", {}),
                sample_github_repo,
            ]
            mock_github.rate_limiting_resettime = time.time() + 0.1
            mock_github_class.return_value = mock_github

            result = enricher._get_github_data("plone/plone.api")

        assert result is not None
        assert result["github"]["stars"] == 500

    def test_memoizes_results(self, enricher, sample_github_repo):
        """Test that GitHub data is memoized."""
        if hasattr(enricher._get_github_data, "cache"):
            enricher._get_github_data.cache.clear()

        with patch("pyf.aggregator.enrichers.github.Github") as mock_github_class:
            mock_github = MagicMock()
            mock_github.get_repo.return_value = sample_github_repo
            mock_github_class.return_value = mock_github

            # First call
            result1 = enricher._get_github_data("plone/plone.api")
            # Second call should use cache
            result2 = enricher._get_github_data("plone/plone.api")

        assert result1 == result2
        # get_repo should only be called once due to memoization
        assert mock_github.get_repo.call_count == 1


# ============================================================================
# GitHub Contributors Tests
# ============================================================================


class TestGetTopContributors:
    """Test the _get_top_contributors method."""

    def test_returns_top_5_contributors(self, enricher, sample_github_contributors):
        """Test that top 5 contributors are returned."""
        mock_repo = MagicMock()
        mock_repo.get_contributors.return_value = sample_github_contributors

        result = enricher._get_top_contributors(mock_repo)

        assert len(result) == 5
        # Check they are sorted by contributions (descending)
        assert result[0]["username"] == "timo"
        assert result[0]["contributions"] == 150
        assert result[4]["username"] == "jensens"
        assert result[4]["contributions"] == 40

    def test_returns_all_contributors_when_less_than_limit(
        self, enricher, sample_github_contributors
    ):
        """Test when there are fewer contributors than the limit."""
        mock_repo = MagicMock()
        mock_repo.get_contributors.return_value = sample_github_contributors[:3]

        result = enricher._get_top_contributors(mock_repo, limit=5)

        assert len(result) == 3

    def test_includes_avatar_url(self, enricher, sample_github_contributors):
        """Test that avatar URLs are included."""
        mock_repo = MagicMock()
        mock_repo.get_contributors.return_value = sample_github_contributors[:2]

        result = enricher._get_top_contributors(mock_repo, limit=2)

        assert "avatar_url" in result[0]
        assert result[0]["avatar_url"].startswith(
            "https://avatars.githubusercontent.com/"
        )

    def test_returns_empty_list_on_error(self, enricher):
        """Test that empty list is returned on API error."""
        mock_repo = MagicMock()
        mock_repo.get_contributors.side_effect = Exception("API Error")

        result = enricher._get_top_contributors(mock_repo)

        assert result == []

    def test_custom_limit(self, enricher, sample_github_contributors):
        """Test with custom contributor limit."""
        mock_repo = MagicMock()
        mock_repo.get_contributors.return_value = sample_github_contributors

        result = enricher._get_top_contributors(mock_repo, limit=3)

        assert len(result) == 3


# ============================================================================
# GitHub Data with Contributors Tests
# ============================================================================


class TestGetGithubDataWithContributors:
    """Test _get_github_data with contributors enabled."""

    def test_includes_contributors_in_result(
        self, enricher, sample_github_repo, sample_github_contributors
    ):
        """Test that contributors are included in the result."""
        if hasattr(enricher._get_github_data, "cache"):
            enricher._get_github_data.cache.clear()

        sample_github_repo.get_contributors.return_value = sample_github_contributors

        with patch("pyf.aggregator.enrichers.github.Github") as mock_github_class:
            mock_github = MagicMock()
            mock_github.get_repo.return_value = sample_github_repo
            mock_github_class.return_value = mock_github

            result = enricher._get_github_data("plone/plone.api")

        assert result is not None
        assert "github" in result
        assert "contributors" in result["github"]
        assert len(result["github"]["contributors"]) == 5


# ============================================================================
# Document Update Tests
# ============================================================================


class TestUpdateDoc:
    """Test the update_doc method."""

    def test_updates_document_with_github_data(self, enricher):
        """Test updating a document with GitHub data."""
        mock_doc = MagicMock()
        enricher.client.collections = {
            "test_collection": MagicMock(documents={"plone.api-2.0.0": mock_doc})
        }

        data = {
            "github": {
                "stars": 500,
                "watchers": 50,
                "updated": datetime(2023, 6, 15, 12, 30, 0),
                "open_issues": 10,
                "gh_url": "https://github.com/plone/plone.api",
            }
        }

        enricher.update_doc(
            "test_collection", "plone.api-2.0.0", data, page=1, enrich_counter=1
        )

        mock_doc.update.assert_called_once()
        call_args = mock_doc.update.call_args[0][0]
        assert call_args["github_stars"] == 500
        assert call_args["github_watchers"] == 50
        assert call_args["github_open_issues"] == 10
        assert call_args["github_url"] == "https://github.com/plone/plone.api"

    def test_updates_document_with_contributors(self, enricher):
        """Test updating a document with contributors data."""
        mock_doc = MagicMock()
        enricher.client.collections = {
            "test_collection": MagicMock(documents={"plone.api-2.0.0": mock_doc})
        }

        contributors = [
            {
                "username": "timo",
                "avatar_url": "https://example.com/1",
                "contributions": 150,
            },
            {
                "username": "davisagli",
                "avatar_url": "https://example.com/2",
                "contributions": 120,
            },
        ]

        data = {
            "github": {
                "stars": 500,
                "watchers": 50,
                "updated": datetime(2023, 6, 15, 12, 30, 0),
                "open_issues": 10,
                "gh_url": "https://github.com/plone/plone.api",
                "contributors": contributors,
            }
        }

        enricher.update_doc(
            "test_collection", "plone.api-2.0.0", data, page=1, enrich_counter=1
        )

        call_args = mock_doc.update.call_args[0][0]
        assert "contributors" in call_args
        assert len(call_args["contributors"]) == 2
        assert call_args["contributors"][0]["username"] == "timo"


# ============================================================================
# Rate Limiting Tests
# ============================================================================


class TestRateLimiting:
    """Test the _apply_github_rate_limit method."""

    def test_applies_delay_between_requests(self, enricher):
        """Test that rate limiting applies delay."""
        import pyf.aggregator.enrichers.github as github_module

        original_delay = github_module.GITHUB_REQUEST_DELAY

        try:
            github_module.GITHUB_REQUEST_DELAY = 0.1
            enricher._last_github_request = time.time()

            start = time.time()
            enricher._apply_github_rate_limit()
            elapsed = time.time() - start

            assert elapsed >= 0.05
        finally:
            github_module.GITHUB_REQUEST_DELAY = original_delay

    def test_no_delay_when_enough_time_passed(self, enricher):
        """Test no delay when enough time has passed."""
        import pyf.aggregator.enrichers.github as github_module

        original_delay = github_module.GITHUB_REQUEST_DELAY

        try:
            github_module.GITHUB_REQUEST_DELAY = 0.1
            enricher._last_github_request = time.time() - 1.0

            start = time.time()
            enricher._apply_github_rate_limit()
            elapsed = time.time() - start

            assert elapsed < 0.05
        finally:
            github_module.GITHUB_REQUEST_DELAY = original_delay


# ============================================================================
# Memoization Tests
# ============================================================================


class TestMemoization:
    """Test the memoization decorator."""

    def test_memoize_decorator(self):
        """Test the memoize decorator works correctly."""
        call_count = 0

        @memoize
        def test_func(self, key):
            nonlocal call_count
            call_count += 1
            return f"result-{key}"

        obj = type("obj", (), {})()

        # First call
        result1 = test_func(obj, "test")
        assert result1 == "result-test"
        assert call_count == 1

        # Second call with same key should use cache
        result2 = test_func(obj, "test")
        assert result2 == "result-test"
        assert call_count == 1

        # Call with different key
        result3 = test_func(obj, "other")
        assert result3 == "result-other"
        assert call_count == 2


# ============================================================================
# Search Parameters Tests
# ============================================================================


class TestSearchParameters:
    """Test that search parameters are correctly configured."""

    def test_search_uses_sort_by_upload_timestamp_desc(
        self, enricher, sample_github_repo, sample_github_contributors
    ):
        """
        Test that the enricher uses sort_by: upload_timestamp:desc to get newest versions.

        This is critical because when using group_by without sort_by, Typesense may return
        an arbitrary version of each package. If project_urls with GitHub links was added
        in a recent version, the enricher might pick up an older version without the URLs.

        Regression test for: GitHub enricher not finding GitHub URLs from project_urls
        """
        if hasattr(enricher._get_github_data, "cache"):
            enricher._get_github_data.cache.clear()

        sample_github_repo.get_contributors.return_value = sample_github_contributors

        # Track calls to ts_search to verify search parameters
        search_calls = []

        def mock_ts_search(target, search_parameters, page=1):
            search_calls.append(search_parameters.copy())
            return {
                "found": 1,
                "request_params": {"per_page": 50},
                "grouped_hits": [
                    {
                        "hits": [
                            {
                                "document": {
                                    "id": "test-package-2.0.0",
                                    "name": "test-package",
                                    "version": "2.0.0",
                                    "project_urls": {
                                        "Source": "https://github.com/org/test-package"
                                    },
                                }
                            }
                        ]
                    }
                ],
            }

        with patch("pyf.aggregator.enrichers.github.Github") as mock_github_class:
            mock_github = MagicMock()
            mock_github.get_repo.return_value = sample_github_repo
            mock_github_class.return_value = mock_github

            enricher.ts_search = mock_ts_search
            enricher.update_doc = MagicMock()

            enricher.run("test_collection")

        # Verify that sort_by was included in search parameters
        assert len(search_calls) >= 1
        first_call_params = search_calls[0]

        assert "sort_by" in first_call_params, (
            "search_parameters must include 'sort_by' to ensure newest version is fetched"
        )
        assert first_call_params["sort_by"] == "upload_timestamp:desc", (
            "sort_by must be 'upload_timestamp:desc' to get newest package versions"
        )

        # Also verify group_by is present (the combination is what matters)
        assert "group_by" in first_call_params, (
            "search_parameters must include 'group_by' for deduplication"
        )
        assert first_call_params["group_by"] == "name_sortable"

    def test_search_finds_github_url_from_newest_version_project_urls(
        self, enricher, sample_github_repo, sample_github_contributors
    ):
        """
        Test that the enricher finds GitHub URLs from project_urls in the newest version.

        Simulates the scenario where:
        - Package v1.0.0 has no GitHub URL in project_urls
        - Package v2.0.0 (newest) has GitHub URL in project_urls

        The enricher should find the GitHub URL because it should be getting v2.0.0.
        """
        if hasattr(enricher._get_github_data, "cache"):
            enricher._get_github_data.cache.clear()

        sample_github_repo.get_contributors.return_value = sample_github_contributors

        # Simulate Typesense returning the newest version (v2.0.0) which has project_urls
        search_results = {
            "found": 1,
            "request_params": {"per_page": 50},
            "grouped_hits": [
                {
                    "hits": [
                        {
                            "document": {
                                "id": "wcs.samlauth-1.3.0",
                                "name": "wcs.samlauth",
                                "version": "1.3.0",
                                "home_page": None,
                                "project_url": None,
                                # GitHub URL only available in project_urls (added in recent version)
                                "project_urls": {
                                    "Homepage": "https://github.com/webcloud7/wcs.samlauth",
                                    "Documentation": "https://docs.example.com",
                                },
                            }
                        }
                    ]
                }
            ],
        }

        with patch("pyf.aggregator.enrichers.github.Github") as mock_github_class:
            mock_github = MagicMock()
            mock_github.get_repo.return_value = sample_github_repo
            mock_github_class.return_value = mock_github

            enricher.ts_search = MagicMock(return_value=search_results)
            enricher.update_doc = MagicMock()

            enricher.run("test_collection")

        # The enricher should have found the GitHub URL and updated the document
        assert enricher.update_doc.call_count == 1, (
            "Enricher should find GitHub URL from project_urls and update the document"
        )

        # Verify GitHub API was called with the correct repo identifier
        mock_github.get_repo.assert_called_with("webcloud7/wcs.samlauth")


# ============================================================================
# Full Enrichment Flow Tests
# ============================================================================


class TestRun:
    """Test the run method (full enrichment flow)."""

    def test_enriches_packages(
        self,
        enricher,
        sample_github_repo,
        sample_typesense_search_results,
        sample_github_contributors,
    ):
        """Test full enrichment flow."""
        if hasattr(enricher._get_github_data, "cache"):
            enricher._get_github_data.cache.clear()

        sample_github_repo.get_contributors.return_value = sample_github_contributors

        with patch("pyf.aggregator.enrichers.github.Github") as mock_github_class:
            mock_github = MagicMock()
            mock_github.get_repo.return_value = sample_github_repo
            mock_github_class.return_value = mock_github

            enricher.ts_search = MagicMock(return_value=sample_typesense_search_results)
            enricher.update_doc = MagicMock()

            enricher.run("test_collection")

        # Should have updated both packages
        assert enricher.update_doc.call_count == 2

    def test_skips_packages_without_github_url(self, enricher):
        """Test that packages without GitHub URL are skipped."""
        search_results = {
            "found": 1,
            "request_params": {"per_page": 50},
            "grouped_hits": [
                {
                    "hits": [
                        {
                            "document": {
                                "id": "some-package-1.0.0",
                                "name": "some-package",
                                "home_page": "https://readthedocs.io/some-package",
                            }
                        }
                    ]
                }
            ],
        }

        enricher.ts_search = MagicMock(return_value=search_results)
        enricher.update_doc = MagicMock()

        enricher.run("test_collection")

        # Should not have updated any packages
        assert enricher.update_doc.call_count == 0

    def test_verbose_mode_outputs_data(
        self, enricher, sample_github_repo, sample_github_contributors, capsys
    ):
        """Test that verbose mode outputs raw data."""
        if hasattr(enricher._get_github_data, "cache"):
            enricher._get_github_data.cache.clear()

        sample_github_repo.get_contributors.return_value = sample_github_contributors

        search_results = {
            "found": 1,
            "request_params": {"per_page": 50},
            "grouped_hits": [
                {
                    "hits": [
                        {
                            "document": {
                                "id": "plone.api-2.0.0",
                                "name": "plone.api",
                                "home_page": "https://github.com/plone/plone.api",
                            }
                        }
                    ]
                }
            ],
        }

        with patch("pyf.aggregator.enrichers.github.Github") as mock_github_class:
            mock_github = MagicMock()
            mock_github.get_repo.return_value = sample_github_repo
            mock_github_class.return_value = mock_github

            enricher.ts_search = MagicMock(return_value=search_results)
            enricher.update_doc = MagicMock()

            enricher.run("test_collection", verbose=True)

        captured = capsys.readouterr()
        assert "plone.api" in captured.out
