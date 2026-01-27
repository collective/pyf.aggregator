"""
Unit tests for pyf.aggregator.queue module.

This module tests:
- PackageIndexer helper class
- inspect_project Celery task
- update_project Celery task
- read_rss_new_projects_and_queue Celery task
- read_rss_new_releases_and_queue Celery task
- Periodic task setup
"""

import time
import pytest
import responses
from unittest.mock import patch, MagicMock
import re

from pyf.aggregator.queue import (
    app,
    PackageIndexer,
    inspect_project,
    update_project,
    read_rss_new_projects_and_queue,
    read_rss_new_releases_and_queue,
    update_github,
    queue_all_github_updates,
    refresh_all_indexed_packages,
    full_fetch_all_packages,
    enrich_downloads_all_packages,
    setup_periodic_tasks,
    parse_crontab,
    get_dedup_redis,
    is_package_recently_queued,
    RSS_DEDUP_TTL,
    TYPESENSE_COLLECTION,
    CELERY_WORKER_POOL,
    CELERY_WORKER_CONCURRENCY,
    CELERY_WORKER_PREFETCH_MULTIPLIER,
    CELERY_TASK_SOFT_TIME_LIMIT,
    CELERY_TASK_TIME_LIMIT,
)


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
# PackageIndexer Tests
# ============================================================================

class TestPackageIndexer:
    """Test the PackageIndexer helper class."""

    def test_clean_data_replaces_none_with_empty_string(self):
        """Test that None values are replaced with empty strings."""
        with patch("pyf.aggregator.db.typesense.Client"):
            indexer = PackageIndexer()
            data = {"name": "test", "author": None, "version": "1.0"}
            result = indexer.clean_data(data)

            assert result["name"] == "test"
            assert result["author"] == ""
            assert result["version"] == "1.0"

    def test_clean_data_replaces_none_list_fields_with_empty_list(self):
        """Test that list fields with None are replaced with empty lists."""
        with patch("pyf.aggregator.db.typesense.Client"):
            indexer = PackageIndexer()
            data = {"name": "test", "requires_dist": None, "classifiers": None}
            result = indexer.clean_data(data)

            assert result["requires_dist"] == []
            assert result["classifiers"] == []

    def test_clean_data_preserves_existing_values(self):
        """Test that existing non-None values are preserved."""
        with patch("pyf.aggregator.db.typesense.Client"):
            indexer = PackageIndexer()
            data = {
                "name": "plone.api",
                "requires_dist": ["zope.interface"],
                "classifiers": ["Framework :: Plone"],
            }
            result = indexer.clean_data(data)

            assert result["name"] == "plone.api"
            assert result["requires_dist"] == ["zope.interface"]
            assert result["classifiers"] == ["Framework :: Plone"]

    def test_index_single_calls_upsert(self, mock_typesense_client):
        """Test that index_single uses upsert operation."""
        with patch("pyf.aggregator.db.typesense.Client", return_value=mock_typesense_client):
            indexer = PackageIndexer()
            data = {"id": "test-1.0", "name": "test"}

            result = indexer.index_single(data, "test_collection")

            mock_typesense_client.collections["test_collection"].documents.upsert.assert_called_once_with(data)

    def test_index_single_handles_errors(self, mock_typesense_client):
        """Test that index_single raises errors properly."""
        mock_typesense_client.collections["test_collection"].documents.upsert.side_effect = Exception("Test error")

        with patch("pyf.aggregator.db.typesense.Client", return_value=mock_typesense_client):
            indexer = PackageIndexer()
            data = {"id": "test-1.0", "name": "test"}

            with pytest.raises(Exception, match="Test error"):
                indexer.index_single(data, "test_collection")


# ============================================================================
# inspect_project Task Tests
# ============================================================================

class TestInspectProjectTask:
    """Test the inspect_project Celery task."""

    def test_task_is_registered(self):
        """Test that inspect_project task is registered with Celery."""
        assert "pyf.aggregator.queue.inspect_project" in app.tasks

    def test_skips_when_no_package_id(self, celery_eager_mode):
        """Test that task skips when package_id is missing."""
        result = inspect_project({})
        assert result["status"] == "skipped"
        assert result["reason"] == "no package_id"

    @responses.activate
    def test_skips_non_plone_package(self, celery_eager_mode, sample_pypi_json_non_plone):
        """Test that non-Plone packages are skipped."""
        responses.add(
            responses.GET,
            re.compile(r"https://pypi\.org/+pypi/requests/json"),
            json=sample_pypi_json_non_plone,
            status=200,
        )

        result = inspect_project({"package_id": "requests"})

        assert result["status"] == "skipped"
        assert result["reason"] == "no_plone_classifier"
        assert result["package_id"] == "requests"

    @responses.activate
    def test_indexes_plone_package(self, celery_eager_mode, sample_pypi_json_plone, mock_typesense_client):
        """Test that Plone packages are indexed."""
        responses.add(
            responses.GET,
            re.compile(r"https://pypi\.org/+pypi/plone\.api/json"),
            json=sample_pypi_json_plone,
            status=200,
        )

        with patch("pyf.aggregator.queue.PackageIndexer") as mock_indexer_class:
            mock_indexer = MagicMock()
            mock_indexer.clean_data.side_effect = lambda x: x
            mock_indexer.index_single.return_value = {"success": True}
            mock_indexer_class.return_value = mock_indexer

            result = inspect_project({"package_id": "plone.api"})

            assert result["status"] == "indexed"
            assert result["package_id"] == "plone.api"
            assert "identifier" in result
            mock_indexer.index_single.assert_called_once()

    @responses.activate
    def test_handles_fetch_failure(self, celery_eager_mode):
        """Test that task handles 404 gracefully."""
        responses.add(
            responses.GET,
            re.compile(r"https://pypi\.org/+pypi/nonexistent/json"),
            status=404,
        )

        result = inspect_project({"package_id": "nonexistent"})

        assert result["status"] == "skipped"
        assert result["reason"] == "fetch_failed"

    @responses.activate
    def test_handles_missing_info_section(self, celery_eager_mode):
        """Test that task handles missing 'info' section in JSON."""
        responses.add(
            responses.GET,
            re.compile(r"https://pypi\.org/+pypi/broken-package/json"),
            json={"releases": {}, "urls": []},
            status=200,
        )

        result = inspect_project({"package_id": "broken-package"})

        assert result["status"] == "skipped"
        # Could be fetch_failed or no_info depending on implementation
        assert "reason" in result

    @responses.activate
    def test_uses_release_id_when_provided(self, celery_eager_mode, sample_pypi_json_plone, mock_typesense_client):
        """Test that specific release_id is used when provided."""
        responses.add(
            responses.GET,
            re.compile(r"https://pypi\.org/+pypi/plone\.api/1\.0\.0/json"),
            json=sample_pypi_json_plone,
            status=200,
        )

        with patch("pyf.aggregator.queue.PackageIndexer") as mock_indexer_class:
            mock_indexer = MagicMock()
            mock_indexer.clean_data.side_effect = lambda x: x
            mock_indexer.index_single.return_value = {"success": True}
            mock_indexer_class.return_value = mock_indexer

            result = inspect_project({
                "package_id": "plone.api",
                "release_id": "1.0.0",
            })

            assert result["status"] == "indexed"

    @responses.activate
    def test_removes_downloads_field(self, celery_eager_mode, sample_pypi_json_plone, mock_typesense_client):
        """Test that 'downloads' field is removed from indexed data."""
        sample_with_downloads = sample_pypi_json_plone.copy()
        sample_with_downloads["info"] = sample_with_downloads["info"].copy()
        sample_with_downloads["info"]["downloads"] = {"last_week": 1000}

        responses.add(
            responses.GET,
            re.compile(r"https://pypi\.org/+pypi/plone\.api/json"),
            json=sample_with_downloads,
            status=200,
        )

        with patch("pyf.aggregator.queue.PackageIndexer") as mock_indexer_class:
            mock_indexer = MagicMock()
            indexed_data = None

            def capture_clean_data(data):
                nonlocal indexed_data
                indexed_data = data
                return data

            mock_indexer.clean_data.side_effect = capture_clean_data
            mock_indexer.index_single.return_value = {"success": True}
            mock_indexer_class.return_value = mock_indexer

            inspect_project({"package_id": "plone.api"})

            assert "downloads" not in indexed_data

    @responses.activate
    def test_sets_id_and_identifier(self, celery_eager_mode, sample_pypi_json_plone, mock_typesense_client):
        """Test that id and identifier are set correctly."""
        responses.add(
            responses.GET,
            re.compile(r"https://pypi\.org/+pypi/plone\.api/json"),
            json=sample_pypi_json_plone,
            status=200,
        )

        with patch("pyf.aggregator.queue.PackageIndexer") as mock_indexer_class:
            mock_indexer = MagicMock()
            indexed_data = None

            def capture_clean_data(data):
                nonlocal indexed_data
                indexed_data = data
                return data

            mock_indexer.clean_data.side_effect = capture_clean_data
            mock_indexer.index_single.return_value = {"success": True}
            mock_indexer_class.return_value = mock_indexer

            inspect_project({"package_id": "plone.api"})

            assert indexed_data["id"] == "plone.api-2.0.0"
            assert indexed_data["identifier"] == "plone.api-2.0.0"
            assert indexed_data["name_sortable"] == "plone.api"


# ============================================================================
# update_project Task Tests
# ============================================================================

class TestUpdateProjectTask:
    """Test the update_project Celery task."""

    def test_task_is_registered(self):
        """Test that update_project task is registered with Celery."""
        assert "pyf.aggregator.queue.update_project" in app.tasks

    def test_skips_when_no_package_id(self, celery_eager_mode):
        """Test that task skips when package_id is empty."""
        result = update_project("")
        assert result["status"] == "skipped"
        assert result["reason"] == "no package_id"

    @responses.activate
    def test_indexes_package(self, celery_eager_mode, sample_pypi_json_plone, mock_typesense_client):
        """Test that package is indexed without classifier check."""
        responses.add(
            responses.GET,
            re.compile(r"https://pypi\.org/+pypi/plone\.api/json"),
            json=sample_pypi_json_plone,
            status=200,
        )

        with patch("pyf.aggregator.queue.PackageIndexer") as mock_indexer_class:
            mock_indexer = MagicMock()
            mock_indexer.clean_data.side_effect = lambda x: x
            mock_indexer.index_single.return_value = {"success": True}
            mock_indexer_class.return_value = mock_indexer

            result = update_project("plone.api")

            assert result["status"] == "indexed"
            assert result["package_id"] == "plone.api"
            mock_indexer.index_single.assert_called_once()

    @responses.activate
    def test_does_not_check_plone_classifier(self, celery_eager_mode, sample_pypi_json_non_plone, mock_typesense_client):
        """Test that non-Plone packages are still indexed (no classifier check)."""
        responses.add(
            responses.GET,
            re.compile(r"https://pypi\.org/+pypi/requests/json"),
            json=sample_pypi_json_non_plone,
            status=200,
        )

        with patch("pyf.aggregator.queue.PackageIndexer") as mock_indexer_class:
            mock_indexer = MagicMock()
            mock_indexer.clean_data.side_effect = lambda x: x
            mock_indexer.index_single.return_value = {"success": True}
            mock_indexer_class.return_value = mock_indexer

            result = update_project("requests")

            # update_project doesn't check classifier - should still index
            assert result["status"] == "indexed"

    @responses.activate
    def test_handles_fetch_failure(self, celery_eager_mode):
        """Test that task handles 404 gracefully."""
        responses.add(
            responses.GET,
            re.compile(r"https://pypi\.org/+pypi/nonexistent/json"),
            status=404,
        )

        result = update_project("nonexistent")

        assert result["status"] == "skipped"
        assert result["reason"] == "fetch_failed"


# ============================================================================
# read_rss_new_projects_and_queue Task Tests
# ============================================================================

class TestReadRssNewProjectsAndQueue:
    """Test the read_rss_new_projects_and_queue Celery task."""

    def test_task_is_registered(self):
        """Test that task is registered with Celery."""
        assert "pyf.aggregator.queue.read_rss_new_projects_and_queue" in app.tasks

    def test_queues_packages_from_rss(self, celery_eager_mode):
        """Test that packages from RSS feed are queued."""
        with patch('feedparser.parse') as mock_parse:
            mock_feed = MagicMock()
            mock_feed.bozo = False
            mock_feed.bozo_exception = None
            mock_feed.entries = [
                FeedParserEntry({
                    "title": "new-package 1.0.0",
                    "link": "https://pypi.org/project/new-package/1.0.0/",
                    "summary": "",
                    "published_parsed": time.strptime("2023-06-15", "%Y-%m-%d"),
                }),
                FeedParserEntry({
                    "title": "another-package 2.0.0",
                    "link": "https://pypi.org/project/another-package/2.0.0/",
                    "summary": "",
                    "published_parsed": time.strptime("2023-06-14", "%Y-%m-%d"),
                }),
            ]
            mock_parse.return_value = mock_feed

            with patch("pyf.aggregator.queue.inspect_project.delay") as mock_delay:
                result = read_rss_new_projects_and_queue()

                assert result["status"] == "completed"
                assert result["packages_queued"] == 2
                assert mock_delay.call_count == 2

    def test_returns_zero_when_empty_feed(self, celery_eager_mode):
        """Test that empty feed returns 0 packages queued."""
        with patch('feedparser.parse') as mock_parse:
            mock_feed = MagicMock()
            mock_feed.bozo = False
            mock_feed.bozo_exception = None
            mock_feed.entries = []
            mock_parse.return_value = mock_feed

            result = read_rss_new_projects_and_queue()

            assert result["status"] == "completed"
            assert result["packages_queued"] == 0

    def test_skips_entries_without_package_id(self, celery_eager_mode):
        """Test that entries without valid package_id are skipped."""
        with patch('feedparser.parse') as mock_parse:
            mock_feed = MagicMock()
            mock_feed.bozo = False
            mock_feed.bozo_exception = None
            mock_feed.entries = [
                FeedParserEntry({
                    "title": "",
                    "link": "",
                    "summary": "",
                }),
                FeedParserEntry({
                    "title": "valid-package 1.0.0",
                    "link": "https://pypi.org/project/valid-package/1.0.0/",
                    "summary": "",
                    "published_parsed": time.strptime("2023-06-15", "%Y-%m-%d"),
                }),
            ]
            mock_parse.return_value = mock_feed

            with patch("pyf.aggregator.queue.inspect_project.delay") as mock_delay:
                result = read_rss_new_projects_and_queue()

                # Only valid package should be queued
                assert result["packages_queued"] == 1
                mock_delay.assert_called_once()

    def test_passes_correct_data_to_inspect_project(self, celery_eager_mode):
        """Test that correct package data is passed to inspect_project task."""
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

            with patch("pyf.aggregator.queue.inspect_project.delay") as mock_delay:
                read_rss_new_projects_and_queue()

                # Check the package_data passed to inspect_project
                call_args = mock_delay.call_args[0][0]
                assert call_args["package_id"] == "test-package"
                assert call_args["release_id"] == "1.0.0"

    def test_skips_duplicate_packages(self, celery_eager_mode):
        """Test that dedup skips recently queued packages."""
        with patch('feedparser.parse') as mock_parse:
            mock_feed = MagicMock()
            mock_feed.bozo = False
            mock_feed.bozo_exception = None
            mock_feed.entries = [
                FeedParserEntry({
                    "title": "dup-package 1.0.0",
                    "link": "https://pypi.org/project/dup-package/1.0.0/",
                    "summary": "",
                    "published_parsed": time.strptime("2023-06-15", "%Y-%m-%d"),
                }),
                FeedParserEntry({
                    "title": "new-package 1.0.0",
                    "link": "https://pypi.org/project/new-package/1.0.0/",
                    "summary": "",
                    "published_parsed": time.strptime("2023-06-15", "%Y-%m-%d"),
                }),
            ]
            mock_parse.return_value = mock_feed

            with patch("pyf.aggregator.queue.inspect_project.delay") as mock_delay:
                with patch("pyf.aggregator.queue.is_package_recently_queued") as mock_dedup:
                    # First package is a duplicate, second is new
                    mock_dedup.side_effect = [True, False]

                    result = read_rss_new_projects_and_queue()

                    assert result["packages_queued"] == 1
                    assert result["packages_skipped"] == 1
                    assert mock_delay.call_count == 1

    def test_returns_skipped_count_in_result(self, celery_eager_mode):
        """Test that result includes packages_skipped count."""
        with patch('feedparser.parse') as mock_parse:
            mock_feed = MagicMock()
            mock_feed.bozo = False
            mock_feed.bozo_exception = None
            mock_feed.entries = [
                FeedParserEntry({
                    "title": "dup1 1.0.0",
                    "link": "https://pypi.org/project/dup1/1.0.0/",
                    "summary": "",
                    "published_parsed": time.strptime("2023-06-15", "%Y-%m-%d"),
                }),
                FeedParserEntry({
                    "title": "dup2 1.0.0",
                    "link": "https://pypi.org/project/dup2/1.0.0/",
                    "summary": "",
                    "published_parsed": time.strptime("2023-06-15", "%Y-%m-%d"),
                }),
            ]
            mock_parse.return_value = mock_feed

            with patch("pyf.aggregator.queue.inspect_project.delay"):
                with patch("pyf.aggregator.queue.is_package_recently_queued", return_value=True):
                    result = read_rss_new_projects_and_queue()

                    assert result["packages_skipped"] == 2
                    assert result["packages_queued"] == 0

    def test_dedup_failure_allows_queueing(self, celery_eager_mode):
        """Test that Redis failure during dedup doesn't block queueing."""
        with patch('feedparser.parse') as mock_parse:
            mock_feed = MagicMock()
            mock_feed.bozo = False
            mock_feed.bozo_exception = None
            mock_feed.entries = [
                FeedParserEntry({
                    "title": "pkg1 1.0.0",
                    "link": "https://pypi.org/project/pkg1/1.0.0/",
                    "summary": "",
                    "published_parsed": time.strptime("2023-06-15", "%Y-%m-%d"),
                }),
            ]
            mock_parse.return_value = mock_feed

            with patch("pyf.aggregator.queue.inspect_project.delay") as mock_delay:
                # is_package_recently_queued returns False on error (fail-open)
                with patch("pyf.aggregator.queue.is_package_recently_queued", return_value=False):
                    result = read_rss_new_projects_and_queue()

                    assert result["packages_queued"] == 1
                    assert mock_delay.call_count == 1


# ============================================================================
# read_rss_new_releases_and_queue Task Tests
# ============================================================================

class TestReadRssNewReleasesAndQueue:
    """Test the read_rss_new_releases_and_queue Celery task."""

    def test_task_is_registered(self):
        """Test that task is registered with Celery."""
        assert "pyf.aggregator.queue.read_rss_new_releases_and_queue" in app.tasks

    def test_queues_releases_from_rss(self, celery_eager_mode):
        """Test that releases from RSS feed are queued."""
        with patch('feedparser.parse') as mock_parse:
            mock_feed = MagicMock()
            mock_feed.bozo = False
            mock_feed.bozo_exception = None
            mock_feed.entries = [
                FeedParserEntry({
                    "title": "updated-package 2.0.0",
                    "link": "https://pypi.org/project/updated-package/2.0.0/",
                    "summary": "",
                    "published_parsed": time.strptime("2023-06-15", "%Y-%m-%d"),
                }),
            ]
            mock_parse.return_value = mock_feed

            with patch("pyf.aggregator.queue.inspect_project.delay") as mock_delay:
                result = read_rss_new_releases_and_queue()

                assert result["status"] == "completed"
                assert result["packages_queued"] == 1
                mock_delay.assert_called_once()

    def test_returns_zero_when_empty_feed(self, celery_eager_mode):
        """Test that empty feed returns 0 packages queued."""
        with patch('feedparser.parse') as mock_parse:
            mock_feed = MagicMock()
            mock_feed.bozo = False
            mock_feed.bozo_exception = None
            mock_feed.entries = []
            mock_parse.return_value = mock_feed

            result = read_rss_new_releases_and_queue()

            assert result["status"] == "completed"
            assert result["packages_queued"] == 0

    def test_skips_duplicate_releases(self, celery_eager_mode):
        """Test that dedup skips recently queued releases."""
        with patch('feedparser.parse') as mock_parse:
            mock_feed = MagicMock()
            mock_feed.bozo = False
            mock_feed.bozo_exception = None
            mock_feed.entries = [
                FeedParserEntry({
                    "title": "dup-release 2.0.0",
                    "link": "https://pypi.org/project/dup-release/2.0.0/",
                    "summary": "",
                    "published_parsed": time.strptime("2023-06-15", "%Y-%m-%d"),
                }),
                FeedParserEntry({
                    "title": "new-release 1.0.0",
                    "link": "https://pypi.org/project/new-release/1.0.0/",
                    "summary": "",
                    "published_parsed": time.strptime("2023-06-15", "%Y-%m-%d"),
                }),
            ]
            mock_parse.return_value = mock_feed

            with patch("pyf.aggregator.queue.inspect_project.delay") as mock_delay:
                with patch("pyf.aggregator.queue.is_package_recently_queued") as mock_dedup:
                    mock_dedup.side_effect = [True, False]

                    result = read_rss_new_releases_and_queue()

                    assert result["packages_queued"] == 1
                    assert result["packages_skipped"] == 1
                    assert mock_delay.call_count == 1

    def test_returns_skipped_count_in_result(self, celery_eager_mode):
        """Test that result includes packages_skipped count."""
        with patch('feedparser.parse') as mock_parse:
            mock_feed = MagicMock()
            mock_feed.bozo = False
            mock_feed.bozo_exception = None
            mock_feed.entries = [
                FeedParserEntry({
                    "title": "dup-pkg 1.0.0",
                    "link": "https://pypi.org/project/dup-pkg/1.0.0/",
                    "summary": "",
                    "published_parsed": time.strptime("2023-06-15", "%Y-%m-%d"),
                }),
            ]
            mock_parse.return_value = mock_feed

            with patch("pyf.aggregator.queue.inspect_project.delay"):
                with patch("pyf.aggregator.queue.is_package_recently_queued", return_value=True):
                    result = read_rss_new_releases_and_queue()

                    assert result["packages_skipped"] == 1
                    assert result["packages_queued"] == 0

    def test_dedup_failure_allows_queueing(self, celery_eager_mode):
        """Test that Redis failure during dedup doesn't block queueing."""
        with patch('feedparser.parse') as mock_parse:
            mock_feed = MagicMock()
            mock_feed.bozo = False
            mock_feed.bozo_exception = None
            mock_feed.entries = [
                FeedParserEntry({
                    "title": "pkg1 1.0.0",
                    "link": "https://pypi.org/project/pkg1/1.0.0/",
                    "summary": "",
                    "published_parsed": time.strptime("2023-06-15", "%Y-%m-%d"),
                }),
            ]
            mock_parse.return_value = mock_feed

            with patch("pyf.aggregator.queue.inspect_project.delay") as mock_delay:
                with patch("pyf.aggregator.queue.is_package_recently_queued", return_value=False):
                    result = read_rss_new_releases_and_queue()

                    assert result["packages_queued"] == 1
                    assert mock_delay.call_count == 1


# ============================================================================
# Other Task Tests
# ============================================================================

class TestUpdateGithubTask:
    """Test the update_github Celery task."""

    def test_task_is_registered(self):
        """Test that update_github task is registered with Celery."""
        assert "pyf.aggregator.queue.update_github" in app.tasks

    def test_skips_when_no_package_id(self, celery_eager_mode):
        """Test that task skips when package_id is empty."""
        result = update_github("")
        assert result["status"] == "skipped"
        assert result["reason"] == "no package_id"

    def test_skips_when_package_not_found_in_typesense(self, celery_eager_mode, mock_typesense_client):
        """Test that task skips when package document not found in Typesense."""
        # Configure mock to raise exception when retrieving document
        mock_typesense_client.collections["test_packages"].documents.__getitem__.return_value.retrieve.side_effect = Exception("Document not found")

        with patch("pyf.aggregator.db.typesense.Client", return_value=mock_typesense_client):
            result = update_github("plone.api-2.0.0")

            assert result["status"] == "skipped"
            assert result["reason"] == "fetch_from_typesense_failed"
            assert result["package_id"] == "plone.api-2.0.0"

    def test_skips_when_no_github_url_found(self, celery_eager_mode, mock_typesense_client):
        """Test that task skips when package has no GitHub URL."""
        # Mock document without GitHub URL
        mock_document = {
            "id": "some-package-1.0.0",
            "name": "some-package",
            "version": "1.0.0",
            "home_page": "https://example.com",
            "project_url": "https://pypi.org/project/some-package/",
            "project_urls": {
                "Documentation": "https://docs.example.com",
            },
        }

        mock_typesense_client.collections["test_packages"].documents.__getitem__.return_value.retrieve.return_value = mock_document

        with patch("pyf.aggregator.db.typesense.Client", return_value=mock_typesense_client):
            result = update_github("some-package-1.0.0")

            assert result["status"] == "skipped"
            assert result["reason"] == "no_github_url"
            assert result["package_id"] == "some-package-1.0.0"

    def test_skips_when_github_fetch_fails(self, celery_eager_mode, mock_typesense_client):
        """Test that task skips when GitHub API fetch fails."""
        # Mock document with GitHub URL
        mock_document = {
            "id": "plone.api-2.0.0",
            "name": "plone.api",
            "version": "2.0.0",
            "home_page": "https://github.com/plone/plone.api",
            "project_url": "https://pypi.org/project/plone.api/",
            "project_urls": None,
        }

        mock_typesense_client.collections["test_packages"].documents.__getitem__.return_value.retrieve.return_value = mock_document

        with patch("pyf.aggregator.db.typesense.Client", return_value=mock_typesense_client):
            with patch("pyf.aggregator.queue._get_github_data", return_value={}):
                result = update_github("plone.api-2.0.0")

                assert result["status"] == "skipped"
                assert result["reason"] == "github_fetch_failed"
                assert result["package_id"] == "plone.api-2.0.0"
                assert result["repo"] == "plone/plone.api"

    def test_successfully_updates_github_data(self, celery_eager_mode, mock_typesense_client):
        """Test that GitHub data is successfully fetched and updated."""
        from datetime import datetime

        # Mock document with GitHub URL
        mock_document = {
            "id": "plone.api-2.0.0",
            "name": "plone.api",
            "version": "2.0.0",
            "home_page": "https://github.com/plone/plone.api",
            "project_url": "https://pypi.org/project/plone.api/",
            "project_urls": None,
        }

        mock_typesense_client.collections["test_packages"].documents.__getitem__.return_value.retrieve.return_value = mock_document
        mock_typesense_client.collections["test_packages"].documents.__getitem__.return_value.update.return_value = {"success": True}

        # Mock GitHub data
        mock_gh_data = {
            "github": {
                "stars": 150,
                "watchers": 25,
                "open_issues": 10,
                "updated": datetime(2023, 6, 15, 12, 30, 0),
                "gh_url": "https://github.com/plone/plone.api",
            }
        }

        with patch("pyf.aggregator.db.typesense.Client", return_value=mock_typesense_client):
            with patch("pyf.aggregator.queue._get_github_data", return_value=mock_gh_data):
                result = update_github("plone.api-2.0.0")

                assert result["status"] == "updated"
                assert result["package_id"] == "plone.api-2.0.0"
                assert result["repo"] == "plone/plone.api"

                # Verify update was called with correct data
                update_call = mock_typesense_client.collections["test_packages"].documents.__getitem__.return_value.update
                update_call.assert_called_once()
                update_data = update_call.call_args[0][0]
                assert update_data["github_stars"] == 150
                assert update_data["github_watchers"] == 25
                assert update_data["github_open_issues"] == 10
                assert update_data["github_url"] == "https://github.com/plone/plone.api"
                assert "github_updated" in update_data

    def test_handles_rate_limit_exception(self, celery_eager_mode, mock_typesense_client):
        """Test that rate limit exceptions are handled and retried."""
        from github import RateLimitExceededException

        # Mock document with GitHub URL
        mock_document = {
            "id": "plone.api-2.0.0",
            "name": "plone.api",
            "version": "2.0.0",
            "home_page": "https://github.com/plone/plone.api",
            "project_url": "https://pypi.org/project/plone.api/",
            "project_urls": None,
        }

        mock_typesense_client.collections["test_packages"].documents.__getitem__.return_value.retrieve.return_value = mock_document

        with patch("pyf.aggregator.db.typesense.Client", return_value=mock_typesense_client):
            with patch("pyf.aggregator.queue._get_github_data", side_effect=RateLimitExceededException(429, {}, {})):
                # In eager mode with propagates=True, retry exceptions are raised
                with pytest.raises(Exception):
                    update_github("plone.api-2.0.0")

    def test_handles_general_exception(self, celery_eager_mode, mock_typesense_client):
        """Test that general exceptions trigger retry behavior."""
        # Mock document with GitHub URL
        mock_document = {
            "id": "plone.api-2.0.0",
            "name": "plone.api",
            "version": "2.0.0",
            "home_page": "https://github.com/plone/plone.api",
            "project_url": "https://pypi.org/project/plone.api/",
            "project_urls": None,
        }

        mock_typesense_client.collections["test_packages"].documents.__getitem__.return_value.retrieve.return_value = mock_document

        with patch("pyf.aggregator.db.typesense.Client", return_value=mock_typesense_client):
            with patch("pyf.aggregator.queue._get_github_data", side_effect=Exception("Network error")):
                # In eager mode with propagates=True, retry exceptions are raised
                with pytest.raises(Exception):
                    update_github("plone.api-2.0.0")

    def test_extracts_github_url_from_home_page(self, celery_eager_mode, mock_typesense_client):
        """Test that GitHub URL is extracted from home_page field."""
        from datetime import datetime

        mock_document = {
            "id": "test-pkg-1.0.0",
            "name": "test-pkg",
            "version": "1.0.0",
            "home_page": "https://github.com/testorg/testrepo",
            "project_url": "https://pypi.org/project/test-pkg/",
            "project_urls": None,
        }

        mock_typesense_client.collections["test_packages"].documents.__getitem__.return_value.retrieve.return_value = mock_document
        mock_typesense_client.collections["test_packages"].documents.__getitem__.return_value.update.return_value = {"success": True}

        mock_gh_data = {
            "github": {
                "stars": 50,
                "watchers": 10,
                "open_issues": 5,
                "updated": datetime(2023, 6, 15, 12, 30, 0),
                "gh_url": "https://github.com/testorg/testrepo",
            }
        }

        with patch("pyf.aggregator.db.typesense.Client", return_value=mock_typesense_client):
            with patch("pyf.aggregator.queue._get_github_data", return_value=mock_gh_data):
                result = update_github("test-pkg-1.0.0")

                assert result["status"] == "updated"
                assert result["repo"] == "testorg/testrepo"

    def test_extracts_github_url_from_project_urls(self, celery_eager_mode, mock_typesense_client):
        """Test that GitHub URL is extracted from project_urls field."""
        from datetime import datetime

        mock_document = {
            "id": "test-pkg-1.0.0",
            "name": "test-pkg",
            "version": "1.0.0",
            "home_page": "https://example.com",
            "project_url": "https://pypi.org/project/test-pkg/",
            "project_urls": {
                "Homepage": "https://example.com",
                "Source": "https://github.com/testorg/testrepo",
                "Documentation": "https://docs.example.com",
            },
        }

        mock_typesense_client.collections["test_packages"].documents.__getitem__.return_value.retrieve.return_value = mock_document
        mock_typesense_client.collections["test_packages"].documents.__getitem__.return_value.update.return_value = {"success": True}

        mock_gh_data = {
            "github": {
                "stars": 50,
                "watchers": 10,
                "open_issues": 5,
                "updated": datetime(2023, 6, 15, 12, 30, 0),
                "gh_url": "https://github.com/testorg/testrepo",
            }
        }

        with patch("pyf.aggregator.db.typesense.Client", return_value=mock_typesense_client):
            with patch("pyf.aggregator.queue._get_github_data", return_value=mock_gh_data):
                result = update_github("test-pkg-1.0.0")

                assert result["status"] == "updated"
                assert result["repo"] == "testorg/testrepo"

    def test_has_retry_config(self):
        """Test that update_github has retry configuration."""
        task = app.tasks["pyf.aggregator.queue.update_github"]
        assert task.max_retries == 3
        assert task.default_retry_delay == 60


class TestGetPackageRepoIdentifier:
    """Test the _get_package_repo_identifier helper function."""

    def test_extracts_from_home_page(self):
        """Test extraction of GitHub repo identifier from home_page."""
        from pyf.aggregator.queue import _get_package_repo_identifier

        data = {
            "home_page": "https://github.com/plone/plone.api",
            "project_url": None,
            "project_urls": None,
        }

        result = _get_package_repo_identifier(data)
        assert result == "plone/plone.api"

    def test_extracts_from_project_url(self):
        """Test extraction of GitHub repo identifier from project_url."""
        from pyf.aggregator.queue import _get_package_repo_identifier

        data = {
            "home_page": None,
            "project_url": "https://github.com/django/django",
            "project_urls": None,
        }

        result = _get_package_repo_identifier(data)
        assert result == "django/django"

    def test_extracts_from_project_urls(self):
        """Test extraction of GitHub repo identifier from project_urls dict."""
        from pyf.aggregator.queue import _get_package_repo_identifier

        data = {
            "home_page": "https://example.com",
            "project_url": None,
            "project_urls": {
                "Homepage": "https://example.com",
                "Source": "https://github.com/requests/requests",
                "Documentation": "https://docs.example.com",
            },
        }

        result = _get_package_repo_identifier(data)
        assert result == "requests/requests"

    def test_handles_http_urls(self):
        """Test extraction works with http:// URLs."""
        from pyf.aggregator.queue import _get_package_repo_identifier

        data = {
            "home_page": "http://github.com/testorg/testrepo",
            "project_url": None,
            "project_urls": None,
        }

        result = _get_package_repo_identifier(data)
        assert result == "testorg/testrepo"

    def test_handles_www_prefix(self):
        """Test extraction works with www. prefix."""
        from pyf.aggregator.queue import _get_package_repo_identifier

        data = {
            "home_page": "www.github.com/testorg/testrepo",
            "project_url": None,
            "project_urls": None,
        }

        result = _get_package_repo_identifier(data)
        assert result == "testorg/testrepo"

    def test_returns_none_when_no_github_url(self):
        """Test returns None when no GitHub URL is found."""
        from pyf.aggregator.queue import _get_package_repo_identifier

        data = {
            "home_page": "https://example.com",
            "project_url": "https://pypi.org/project/test/",
            "project_urls": {
                "Homepage": "https://example.com",
                "Documentation": "https://docs.example.com",
            },
        }

        result = _get_package_repo_identifier(data)
        assert result is None

    def test_returns_none_when_all_fields_none(self):
        """Test returns None when all URL fields are None."""
        from pyf.aggregator.queue import _get_package_repo_identifier

        data = {
            "home_page": None,
            "project_url": None,
            "project_urls": None,
        }

        result = _get_package_repo_identifier(data)
        assert result is None

    def test_handles_trailing_slashes_and_paths(self):
        """Test extraction handles trailing slashes and additional path segments."""
        from pyf.aggregator.queue import _get_package_repo_identifier

        data = {
            "home_page": "https://github.com/plone/plone.api/tree/main",
            "project_url": None,
            "project_urls": None,
        }

        result = _get_package_repo_identifier(data)
        assert result == "plone/plone.api"

    def test_handles_empty_project_urls_dict(self):
        """Test handles empty project_urls dictionary."""
        from pyf.aggregator.queue import _get_package_repo_identifier

        data = {
            "home_page": None,
            "project_url": None,
            "project_urls": {},
        }

        result = _get_package_repo_identifier(data)
        assert result is None


class TestGetGithubData:
    """Test the _get_github_data helper function."""

    def test_fetches_github_data_successfully(self):
        """Test successful GitHub data fetching."""
        from pyf.aggregator.queue import _get_github_data
        from datetime import datetime

        mock_repo = MagicMock()
        mock_repo.stargazers_count = 100
        mock_repo.subscribers_count = 20
        mock_repo.open_issues = 15
        mock_repo.archived = False
        mock_repo.updated_at = datetime(2023, 6, 15, 12, 30, 0)
        mock_repo.html_url = "https://github.com/plone/plone.api"

        with patch("pyf.aggregator.queue.Github") as mock_github_class:
            mock_github = MagicMock()
            mock_github.get_repo.return_value = mock_repo
            mock_github_class.return_value = mock_github

            result = _get_github_data("plone/plone.api")

            assert "github" in result
            assert result["github"]["stars"] == 100
            assert result["github"]["watchers"] == 20
            assert result["github"]["open_issues"] == 15
            assert result["github"]["is_archived"] == False
            assert result["github"]["updated"] == datetime(2023, 6, 15, 12, 30, 0)
            assert result["github"]["gh_url"] == "https://github.com/plone/plone.api"

    def test_returns_empty_dict_when_repo_not_found(self):
        """Test returns empty dict when GitHub repository not found."""
        from pyf.aggregator.queue import _get_github_data
        from github import UnknownObjectException

        with patch("pyf.aggregator.queue.Github") as mock_github_class:
            mock_github = MagicMock()
            mock_github.get_repo.side_effect = UnknownObjectException(404, {}, {})
            mock_github_class.return_value = mock_github

            result = _get_github_data("nonexistent/repo")

            assert result == {}

    def test_waits_and_retries_on_rate_limit(self):
        """Test waits and retries when rate limit is exceeded."""
        from pyf.aggregator.queue import _get_github_data
        from github import RateLimitExceededException
        from datetime import datetime
        import time

        mock_repo = MagicMock()
        mock_repo.stargazers_count = 50
        mock_repo.subscribers_count = 10
        mock_repo.open_issues = 5
        mock_repo.archived = False
        mock_repo.updated_at = datetime(2023, 6, 15, 12, 30, 0)
        mock_repo.html_url = "https://github.com/testorg/testrepo"

        with patch("pyf.aggregator.queue.Github") as mock_github_class:
            with patch("time.sleep") as mock_sleep:
                mock_github = MagicMock()
                # First call raises rate limit, second call succeeds
                mock_github.get_repo.side_effect = [
                    RateLimitExceededException(429, {}, {}),
                    mock_repo,
                ]
                mock_github.rate_limiting_resettime = time.time() + 1
                mock_github_class.return_value = mock_github

                result = _get_github_data("testorg/testrepo")

                assert "github" in result
                assert result["github"]["stars"] == 50
                # Verify sleep was called (waiting for rate limit reset)
                mock_sleep.assert_called_once()


class TestQueueAllGithubUpdates:
    """Test the queue_all_github_updates Celery task."""

    def test_task_is_registered(self):
        """Test that queue_all_github_updates task is registered with Celery."""
        assert "pyf.aggregator.queue.queue_all_github_updates" in app.tasks


# ============================================================================
# Periodic Task Setup Tests
# ============================================================================

class TestParseCrontab:
    """Test the parse_crontab helper function."""

    def test_parse_crontab_valid(self):
        """Test parsing a valid crontab string."""
        result = parse_crontab("*/5 * * * *")
        assert result is not None

    def test_parse_crontab_full_schedule(self):
        """Test parsing a full crontab schedule."""
        result = parse_crontab("0 2 * * 0")
        assert result is not None

    def test_parse_crontab_empty_string(self):
        """Test that empty string returns None (disables task)."""
        result = parse_crontab("")
        assert result is None

    def test_parse_crontab_whitespace_only(self):
        """Test that whitespace-only string returns None."""
        result = parse_crontab("   ")
        assert result is None

    def test_parse_crontab_none(self):
        """Test that None returns None."""
        result = parse_crontab(None)
        assert result is None

    def test_parse_crontab_invalid_format(self):
        """Test that invalid format returns None and logs warning."""
        result = parse_crontab("* * *")  # Only 3 parts
        assert result is None

    def test_parse_crontab_too_many_parts(self):
        """Test that too many parts returns None."""
        result = parse_crontab("* * * * * *")  # 6 parts
        assert result is None


class TestPeriodicTaskSetup:
    """Test the periodic task configuration."""

    def test_setup_periodic_tasks_exists(self):
        """Test that setup_periodic_tasks function exists."""
        assert callable(setup_periodic_tasks)

    def test_periodic_tasks_configured(self):
        """Test that periodic tasks are configured correctly with defaults."""
        mock_sender = MagicMock()

        setup_periodic_tasks(mock_sender)

        # Should have added 5 periodic tasks (2 RSS + weekly refresh + monthly full fetch + weekly downloads)
        assert mock_sender.add_periodic_task.call_count == 5

        # Check task names
        call_args_list = mock_sender.add_periodic_task.call_args_list
        task_names = [call[1].get('name', '') for call in call_args_list]

        assert 'read RSS new projects and add to queue' in task_names
        assert 'read RSS new releases and add to queue' in task_names
        assert 'weekly refresh all indexed packages' in task_names
        assert 'monthly full fetch all packages' in task_names
        assert 'weekly download stats enrichment' in task_names

    def test_periodic_task_disabled_with_empty_string(self):
        """Test that tasks can be disabled by setting schedule to empty string."""
        mock_sender = MagicMock()

        with patch('pyf.aggregator.queue.CELERY_SCHEDULE_MONTHLY_FETCH', ''):
            setup_periodic_tasks(mock_sender)

        # Should have added only 4 periodic tasks (monthly disabled)
        assert mock_sender.add_periodic_task.call_count == 4

        # Check that monthly task is not in the list
        call_args_list = mock_sender.add_periodic_task.call_args_list
        task_names = [call[1].get('name', '') for call in call_args_list]

        assert 'monthly full fetch all packages' not in task_names
        assert 'read RSS new projects and add to queue' in task_names

    def test_periodic_task_custom_schedule(self):
        """Test that custom schedules are applied."""
        mock_sender = MagicMock()

        with patch('pyf.aggregator.queue.CELERY_SCHEDULE_RSS_PROJECTS', '*/5 * * * *'):
            setup_periodic_tasks(mock_sender)

        # Should still have 5 tasks
        assert mock_sender.add_periodic_task.call_count == 5


# ============================================================================
# Constants and App Configuration Tests
# ============================================================================

class TestQueueConfiguration:
    """Test queue module configuration."""

    def test_typesense_collection_has_default(self):
        """Test that TYPESENSE_COLLECTION has a default value."""
        # The default is set in the module or from environment
        assert TYPESENSE_COLLECTION is not None
        assert isinstance(TYPESENSE_COLLECTION, str)

    def test_celery_app_name(self):
        """Test that Celery app has correct name."""
        assert app.main == "pyf-aggregator"

    def test_celery_app_has_broker_retry_on_startup(self):
        """Test that Celery app has broker retry on startup enabled."""
        # This is configured in the app initialization
        assert app.conf.broker_connection_retry_on_startup is True


# ============================================================================
# Task Retry Configuration Tests
# ============================================================================

class TestTaskRetryConfiguration:
    """Test that tasks have proper retry configuration."""

    def test_inspect_project_has_retry_config(self):
        """Test that inspect_project has retry configuration."""
        task = app.tasks["pyf.aggregator.queue.inspect_project"]
        assert task.max_retries == 3
        assert task.default_retry_delay == 60

    def test_update_project_has_retry_config(self):
        """Test that update_project has retry configuration."""
        task = app.tasks["pyf.aggregator.queue.update_project"]
        assert task.max_retries == 3
        assert task.default_retry_delay == 60

    def test_rss_new_projects_has_retry_config(self):
        """Test that read_rss_new_projects_and_queue has retry configuration."""
        task = app.tasks["pyf.aggregator.queue.read_rss_new_projects_and_queue"]
        assert task.max_retries == 3
        assert task.default_retry_delay == 120

    def test_rss_new_releases_has_retry_config(self):
        """Test that read_rss_new_releases_and_queue has retry configuration."""
        task = app.tasks["pyf.aggregator.queue.read_rss_new_releases_and_queue"]
        assert task.max_retries == 3
        assert task.default_retry_delay == 120


# ============================================================================
# RSS Deduplication Tests
# ============================================================================

class TestRSSDeduplication:
    """Test the is_package_recently_queued deduplication function."""

    def test_first_check_returns_false(self):
        """Test that a new package returns False (not a duplicate)."""
        mock_redis = MagicMock()
        mock_redis.set.return_value = True  # SET NX succeeded = key was new

        with patch("pyf.aggregator.queue.get_dedup_redis", return_value=mock_redis):
            result = is_package_recently_queued("new-package")

            assert result is False
            mock_redis.set.assert_called_once_with(
                "pyf:dedup:new-package", "1", nx=True, ex=RSS_DEDUP_TTL
            )

    def test_duplicate_check_returns_true(self):
        """Test that a recently queued package returns True."""
        mock_redis = MagicMock()
        mock_redis.set.return_value = False  # SET NX failed = key already existed

        with patch("pyf.aggregator.queue.get_dedup_redis", return_value=mock_redis):
            result = is_package_recently_queued("existing-package")

            assert result is True

    def test_redis_unavailable_returns_false(self):
        """Test fail-open when Redis is unavailable (get_dedup_redis returns None)."""
        with patch("pyf.aggregator.queue.get_dedup_redis", return_value=None):
            result = is_package_recently_queued("any-package")

            assert result is False

    def test_redis_error_returns_false(self):
        """Test fail-open on Redis errors."""
        import redis as redis_lib

        mock_redis = MagicMock()
        mock_redis.set.side_effect = redis_lib.RedisError("Connection lost")

        with patch("pyf.aggregator.queue.get_dedup_redis", return_value=mock_redis):
            result = is_package_recently_queued("any-package")

            assert result is False

    def test_custom_ttl_is_used(self):
        """Test that a custom TTL is passed to Redis."""
        mock_redis = MagicMock()
        mock_redis.set.return_value = True

        with patch("pyf.aggregator.queue.get_dedup_redis", return_value=mock_redis):
            is_package_recently_queued("pkg", ttl=120)

            mock_redis.set.assert_called_once_with(
                "pyf:dedup:pkg", "1", nx=True, ex=120
            )

    def test_ttl_zero_disables_dedup(self):
        """Test that TTL=0 disables dedup entirely (always returns False)."""
        mock_redis = MagicMock()

        with patch("pyf.aggregator.queue.get_dedup_redis", return_value=mock_redis):
            result = is_package_recently_queued("any-package", ttl=0)

            assert result is False
            mock_redis.set.assert_not_called()

    def test_dedup_key_format(self):
        """Test that the Redis key uses the correct format."""
        mock_redis = MagicMock()
        mock_redis.set.return_value = True

        with patch("pyf.aggregator.queue.get_dedup_redis", return_value=mock_redis):
            is_package_recently_queued("plone.api")

            call_args = mock_redis.set.call_args
            assert call_args[0][0] == "pyf:dedup:plone.api"


class TestGetDedupRedis:
    """Test the get_dedup_redis helper function."""

    def test_creates_redis_client(self):
        """Test that a Redis client is created and pinged on first call."""
        import redis as redis_lib

        mock_client = MagicMock()
        mock_client.ping.return_value = True

        with patch("pyf.aggregator.queue._dedup_redis_client", None):
            with patch("redis.Redis", return_value=mock_client) as mock_redis_cls:
                result = get_dedup_redis()

                assert result is mock_client
                mock_redis_cls.assert_called_once()
                mock_client.ping.assert_called_once()

    def test_returns_cached_client_on_second_call(self):
        """Test that the singleton client is reused."""
        mock_client = MagicMock()
        mock_client.ping.return_value = True

        with patch("pyf.aggregator.queue._dedup_redis_client", mock_client):
            result = get_dedup_redis()

            assert result is mock_client

    def test_returns_none_on_connection_error(self):
        """Test graceful failure when Redis is unreachable."""
        import redis as redis_lib

        mock_client = MagicMock()
        mock_client.ping.side_effect = redis_lib.ConnectionError("Connection refused")

        with patch("pyf.aggregator.queue._dedup_redis_client", None):
            with patch("redis.Redis", return_value=mock_client):
                result = get_dedup_redis()

                assert result is None


# ============================================================================
# Edge Case Tests
# ============================================================================

class TestEdgeCases:
    """Test edge cases and error handling."""

    @responses.activate
    def test_inspect_project_handles_empty_package_json(self, celery_eager_mode):
        """Test that empty package JSON is handled."""
        responses.add(
            responses.GET,
            re.compile(r"https://pypi\.org/+pypi/empty-package/json"),
            json={},
            status=200,
        )

        result = inspect_project({"package_id": "empty-package"})

        # Should skip due to no info or no classifier
        assert result["status"] == "skipped"

    @responses.activate
    def test_inspect_project_handles_package_with_no_version(self, celery_eager_mode, mock_typesense_client):
        """Test that packages without version are handled."""
        package_json = {
            "info": {
                "name": "test-package",
                "version": "",
                "classifiers": ["Framework :: Plone"],
            },
            "urls": [],
        }

        responses.add(
            responses.GET,
            re.compile(r"https://pypi\.org/+pypi/test-package/json"),
            json=package_json,
            status=200,
        )

        with patch("pyf.aggregator.queue.PackageIndexer") as mock_indexer_class:
            mock_indexer = MagicMock()
            indexed_data = None

            def capture_clean_data(data):
                nonlocal indexed_data
                indexed_data = data
                return data

            mock_indexer.clean_data.side_effect = capture_clean_data
            mock_indexer.index_single.return_value = {"success": True}
            mock_indexer_class.return_value = mock_indexer

            result = inspect_project({"package_id": "test-package"})

            assert result["status"] == "indexed"
            # Identifier should be just package name when no version
            assert indexed_data["id"] == "test-package"

    @responses.activate
    def test_update_project_handles_network_error(self, celery_eager_mode):
        """Test that network errors trigger retry behavior."""
        from celery.exceptions import Retry

        responses.add(
            responses.GET,
            re.compile(r"https://pypi\.org/+pypi/network-error/json"),
            body=Exception("Network error"),
        )

        # In eager mode with propagates=True, retry exceptions are raised
        # The task should attempt to retry on network errors
        with pytest.raises(Exception):
            update_project("network-error")

    def test_rss_task_handles_feedparser_error(self, celery_eager_mode):
        """Test that feedparser errors are handled."""
        with patch('feedparser.parse') as mock_parse:
            mock_feed = MagicMock()
            mock_feed.bozo = True
            mock_feed.bozo_exception = Exception("Parse error")
            mock_feed.entries = []
            mock_parse.return_value = mock_feed

            # Should handle gracefully
            result = read_rss_new_projects_and_queue()

            # Even with bozo feed, should return a status
            assert "status" in result

    @responses.activate
    def test_inspect_project_with_timestamp(self, celery_eager_mode, sample_pypi_json_plone, mock_typesense_client):
        """Test that upload_timestamp is set when provided."""
        responses.add(
            responses.GET,
            re.compile(r"https://pypi\.org/+pypi/plone\.api/json"),
            json=sample_pypi_json_plone,
            status=200,
        )

        with patch("pyf.aggregator.queue.PackageIndexer") as mock_indexer_class:
            mock_indexer = MagicMock()
            indexed_data = None

            def capture_clean_data(data):
                nonlocal indexed_data
                indexed_data = data
                return data

            mock_indexer.clean_data.side_effect = capture_clean_data
            mock_indexer.index_single.return_value = {"success": True}
            mock_indexer_class.return_value = mock_indexer

            inspect_project({
                "package_id": "plone.api",
                "timestamp": 1686700000.0,
            })

            # upload_timestamp should be an int64 Unix timestamp
            assert indexed_data["upload_timestamp"] == 1686700000


# ============================================================================
# Refresh All Indexed Packages Task Tests
# ============================================================================

class TestRefreshAllIndexedPackagesTask:
    """Test the refresh_all_indexed_packages Celery task."""

    def test_task_is_registered(self):
        """Test that task is registered with Celery."""
        assert "pyf.aggregator.queue.refresh_all_indexed_packages" in app.tasks

    def test_task_has_retry_config(self):
        """Test that task has retry configuration."""
        task = app.tasks["pyf.aggregator.queue.refresh_all_indexed_packages"]
        assert task.max_retries == 2
        assert task.default_retry_delay == 300

    def test_task_handles_empty_collection(self, celery_eager_mode):
        """Test task handles empty collection gracefully."""
        with patch("pyf.aggregator.queue.PackageIndexer") as mock_indexer_class:
            mock_indexer = MagicMock()
            mock_indexer.get_unique_package_names.return_value = set()
            mock_indexer_class.return_value = mock_indexer

            with patch("pyf.aggregator.profiles.ProfileManager") as mock_profile_manager:
                mock_pm = MagicMock()
                mock_pm.get_profile.return_value = {"classifiers": ["Framework :: Plone"]}
                mock_profile_manager.return_value = mock_pm

                result = refresh_all_indexed_packages("test_collection", "plone")

                assert result["status"] == "completed"
                assert result["stats"]["total"] == 0


# ============================================================================
# Full Fetch All Packages Task Tests
# ============================================================================

class TestFullFetchAllPackagesTask:
    """Test the full_fetch_all_packages Celery task."""

    def test_task_is_registered(self):
        """Test that task is registered with Celery."""
        assert "pyf.aggregator.queue.full_fetch_all_packages" in app.tasks

    def test_task_has_retry_config(self):
        """Test that task has retry configuration."""
        task = app.tasks["pyf.aggregator.queue.full_fetch_all_packages"]
        assert task.max_retries == 2
        assert task.default_retry_delay == 600

    def test_task_fails_for_missing_profile(self, celery_eager_mode):
        """Test task fails when profile is not found."""
        with patch("pyf.aggregator.profiles.ProfileManager") as mock_profile_manager:
            mock_pm = MagicMock()
            mock_pm.get_profile.return_value = None
            mock_profile_manager.return_value = mock_pm

            result = full_fetch_all_packages("test_collection", "nonexistent_profile")

            assert result["status"] == "failed"
            assert "profile_not_found" in result["reason"]


# ============================================================================
# Enrich Downloads All Packages Task Tests
# ============================================================================

class TestEnrichDownloadsAllPackagesTask:
    """Test the enrich_downloads_all_packages Celery task."""

    def test_task_is_registered(self):
        """Test that task is registered with Celery."""
        assert "pyf.aggregator.queue.enrich_downloads_all_packages" in app.tasks

    def test_task_has_retry_config(self):
        """Test that task has retry configuration."""
        task = app.tasks["pyf.aggregator.queue.enrich_downloads_all_packages"]
        assert task.max_retries == 3
        assert task.default_retry_delay == 60

    def test_task_enriches_all_profiles(self, celery_eager_mode):
        """Test that task enriches all profiles."""
        with patch("pyf.aggregator.profiles.ProfileManager") as mock_profile_manager:
            mock_pm = MagicMock()
            mock_pm.list_profiles.return_value = ["plone", "django"]
            mock_profile_manager.return_value = mock_pm

            with patch("pyf.aggregator.enrichers.downloads.Enricher") as mock_enricher_class:
                mock_enricher = MagicMock()
                mock_enricher_class.return_value = mock_enricher

                result = enrich_downloads_all_packages()

                assert result["status"] == "completed"
                assert "plone" in result["profiles"]
                assert "django" in result["profiles"]
                assert mock_enricher.run.call_count == 2

    def test_task_handles_enricher_error(self, celery_eager_mode):
        """Test that task handles errors from enricher gracefully."""
        with patch("pyf.aggregator.profiles.ProfileManager") as mock_profile_manager:
            mock_pm = MagicMock()
            mock_pm.list_profiles.return_value = ["plone"]
            mock_profile_manager.return_value = mock_pm

            with patch("pyf.aggregator.enrichers.downloads.Enricher") as mock_enricher_class:
                mock_enricher = MagicMock()
                mock_enricher.run.side_effect = Exception("API error")
                mock_enricher_class.return_value = mock_enricher

                result = enrich_downloads_all_packages()

                assert result["status"] == "completed"
                assert "failed" in result["profiles"]["plone"]


# ============================================================================
# Worker Pool Configuration Tests
# ============================================================================

class TestWorkerPoolConfiguration:
    """Test Celery worker pool and concurrency configuration."""

    def test_celery_app_has_threads_pool(self):
        """Test that Celery app is configured with threads worker pool."""
        assert app.conf.worker_pool == CELERY_WORKER_POOL
        assert CELERY_WORKER_POOL == "threads"

    def test_celery_app_has_concurrency(self):
        """Test that Celery app has worker concurrency configured."""
        assert app.conf.worker_concurrency == CELERY_WORKER_CONCURRENCY
        assert CELERY_WORKER_CONCURRENCY > 0

    def test_celery_app_has_prefetch_multiplier(self):
        """Test that Celery app has prefetch multiplier configured."""
        assert app.conf.worker_prefetch_multiplier == CELERY_WORKER_PREFETCH_MULTIPLIER
        assert CELERY_WORKER_PREFETCH_MULTIPLIER > 0

    def test_celery_app_has_time_limits(self):
        """Test that soft time limit is less than hard time limit."""
        assert app.conf.task_soft_time_limit == CELERY_TASK_SOFT_TIME_LIMIT
        assert app.conf.task_time_limit == CELERY_TASK_TIME_LIMIT
        assert CELERY_TASK_SOFT_TIME_LIMIT < CELERY_TASK_TIME_LIMIT

    def test_celery_app_has_acks_late(self):
        """Test that task_acks_late is enabled."""
        assert app.conf.task_acks_late is True

    def test_celery_app_has_broker_pool_limit(self):
        """Test that broker_pool_limit is configured relative to concurrency."""
        assert app.conf.broker_pool_limit == CELERY_WORKER_CONCURRENCY + 10

    def test_long_running_tasks_have_extended_time_limits(self):
        """Test that refresh and full-fetch tasks override default time limits."""
        refresh_task = app.tasks["pyf.aggregator.queue.refresh_all_indexed_packages"]
        assert refresh_task.soft_time_limit == 3600
        assert refresh_task.time_limit == 3900

        full_fetch_task = app.tasks["pyf.aggregator.queue.full_fetch_all_packages"]
        assert full_fetch_task.soft_time_limit == 7200
        assert full_fetch_task.time_limit == 7500

        downloads_task = app.tasks["pyf.aggregator.queue.enrich_downloads_all_packages"]
        assert downloads_task.soft_time_limit == 3600
        assert downloads_task.time_limit == 3900
