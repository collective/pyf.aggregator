"""
Unit tests for pyf.aggregator.enrichers.maintainers module.

This module tests:
- pypi-data SQLite database downloading and caching
- Maintainer querying from SQLite
- Avatar URL scraping from PyPI user profiles
- Typesense document updates with maintainer data
- Full enrichment flow
"""

import os
import sqlite3
import tempfile
import time
import pytest
import responses
from unittest.mock import patch, MagicMock
from datetime import datetime


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def enricher():
    """Create a MaintainerEnricher instance for testing."""
    with patch('pyf.aggregator.enrichers.maintainers.TypesenceConnection.__init__', return_value=None):
        with patch('pyf.aggregator.enrichers.maintainers.TypesensePackagesCollection.__init__', return_value=None):
            from pyf.aggregator.enrichers.maintainers import MaintainerEnricher
            e = MaintainerEnricher()
            e.client = MagicMock()
            return e


@pytest.fixture
def sample_pypi_data_db(tmp_path):
    """Create a sample pypi-data SQLite database."""
    db_path = tmp_path / "pypi-data.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create maintainers table (matching sethmlarson/pypi-data schema)
    cursor.execute("""
        CREATE TABLE maintainers (
            package_name TEXT,
            name TEXT
        )
    """)

    # Insert sample data
    cursor.executemany(
        "INSERT INTO maintainers (package_name, name) VALUES (?, ?)",
        [
            ("plone.api", "davisagli"),
            ("plone.api", "tisto"),
            ("plone.api", "jensens"),
            ("plone.restapi", "tisto"),
            ("plone.restapi", "sneridagh"),
            ("some-other-package", "someone"),
        ]
    )

    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def sample_pypi_profile_html():
    """Sample PyPI user profile HTML with Gravatar avatar."""
    return """
    <!DOCTYPE html>
    <html>
    <head><title>davisagli - PyPI</title></head>
    <body>
        <div class="avatar">
            <img src="https://pypi-camo.freetls.fastly.net/abc123def456/gravatar.com/avatar/12345?size=200" alt="Avatar">
        </div>
    </body>
    </html>
    """


@pytest.fixture
def sample_pypi_profile_html_no_avatar():
    """Sample PyPI user profile HTML without avatar."""
    return """
    <!DOCTYPE html>
    <html>
    <head><title>newuser - PyPI</title></head>
    <body>
        <div class="profile">
            <p>No avatar available</p>
        </div>
    </body>
    </html>
    """


@pytest.fixture
def sample_typesense_search_results():
    """Sample Typesense search results."""
    return {
        "found": 2,
        "request_params": {
            "per_page": 50
        },
        "grouped_hits": [
            {
                "hits": [
                    {
                        "document": {
                            "id": "plone.api-2.0.0",
                            "name": "plone.api",
                            "version": "2.0.0"
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
                            "version": "8.0.0"
                        }
                    }
                ]
            }
        ]
    }


# ============================================================================
# SQLite Database Download Tests
# ============================================================================

class TestDownloadPypiData:
    """Test the _download_pypi_data method."""

    @responses.activate
    def test_downloads_and_extracts_database(self, enricher, tmp_path):
        """Test successful database download and extraction."""
        import gzip
        import io

        # Create a valid SQLite database file first
        db_path_temp = tmp_path / "temp.db"
        conn = sqlite3.connect(db_path_temp)
        conn.execute("CREATE TABLE maintainers (package_name TEXT, name TEXT)")
        conn.execute("INSERT INTO maintainers VALUES ('test', 'user')")
        conn.commit()
        conn.close()

        # Create GZIP file containing the SQLite database
        with open(db_path_temp, 'rb') as f:
            db_bytes = f.read()

        gz_buffer = io.BytesIO()
        with gzip.GzipFile(fileobj=gz_buffer, mode='wb') as gz:
            gz.write(db_bytes)

        responses.add(
            responses.GET,
            "https://github.com/sethmlarson/pypi-data/releases/latest/download/pypi.db.gz",
            body=gz_buffer.getvalue(),
            status=200,
            content_type="application/gzip",
        )

        with patch.dict(os.environ, {"PYPI_DATA_CACHE_DIR": str(tmp_path)}):
            result = enricher._download_pypi_data()

        assert result is not None
        assert os.path.exists(result)

    @responses.activate
    def test_uses_cached_database_when_fresh(self, enricher, tmp_path, sample_pypi_data_db):
        """Test that cached database is used when it's fresh."""
        import shutil
        import pyf.aggregator.enrichers.maintainers as maintainers_module

        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        cached_db = cache_dir / "pypi.db"
        shutil.copy(sample_pypi_data_db, cached_db)

        # Patch the module-level constants
        original_cache_dir = maintainers_module.PYPI_DATA_CACHE_DIR
        original_cache_ttl = maintainers_module.PYPI_DATA_CACHE_TTL

        try:
            maintainers_module.PYPI_DATA_CACHE_DIR = str(cache_dir)
            maintainers_module.PYPI_DATA_CACHE_TTL = 86400

            result = enricher._download_pypi_data()

            assert result == str(cached_db)
            assert len(responses.calls) == 0
        finally:
            maintainers_module.PYPI_DATA_CACHE_DIR = original_cache_dir
            maintainers_module.PYPI_DATA_CACHE_TTL = original_cache_ttl

    @responses.activate
    def test_returns_none_on_download_error(self, enricher, tmp_path):
        """Test that None is returned on download error."""
        import pyf.aggregator.enrichers.maintainers as maintainers_module

        # Use a clean tmp directory with no existing cache
        cache_dir = tmp_path / "empty_cache"
        cache_dir.mkdir()

        responses.add(
            responses.GET,
            "https://github.com/sethmlarson/pypi-data/releases/latest/download/pypi.db.gz",
            status=404,
        )

        original_cache_dir = maintainers_module.PYPI_DATA_CACHE_DIR

        try:
            maintainers_module.PYPI_DATA_CACHE_DIR = str(cache_dir)
            result = enricher._download_pypi_data()
            assert result is None
        finally:
            maintainers_module.PYPI_DATA_CACHE_DIR = original_cache_dir


# ============================================================================
# Maintainer Querying Tests
# ============================================================================

class TestGetMaintainersForPackage:
    """Test the _get_maintainers_for_package method."""

    def test_returns_maintainers_for_existing_package(self, enricher, sample_pypi_data_db):
        """Test querying maintainers for an existing package."""
        result = enricher._get_maintainers_for_package(str(sample_pypi_data_db), "plone.api")

        assert len(result) == 3
        usernames = [m["username"] for m in result]
        assert "davisagli" in usernames
        assert "tisto" in usernames
        assert "jensens" in usernames

    def test_returns_empty_list_for_nonexistent_package(self, enricher, sample_pypi_data_db):
        """Test querying maintainers for a non-existent package."""
        result = enricher._get_maintainers_for_package(str(sample_pypi_data_db), "nonexistent-package")

        assert result == []

    def test_handles_database_error(self, enricher, tmp_path):
        """Test handling of database errors."""
        # Create an invalid database file
        invalid_db = tmp_path / "invalid.db"
        invalid_db.write_text("not a database")

        result = enricher._get_maintainers_for_package(str(invalid_db), "plone.api")

        assert result == []


# ============================================================================
# Avatar Scraping Tests
# ============================================================================

class TestScrapeAvatarUrl:
    """Test the _scrape_avatar_url method."""

    @responses.activate
    def test_scrapes_avatar_from_profile(self, enricher, sample_pypi_profile_html):
        """Test successful avatar URL scraping."""
        # Clear the memoization cache before test
        if hasattr(enricher._scrape_avatar_url, 'cache'):
            enricher._scrape_avatar_url.cache.clear()

        responses.add(
            responses.GET,
            "https://pypi.org/user/davisagli/",
            body=sample_pypi_profile_html,
            status=200,
        )

        result = enricher._scrape_avatar_url("davisagli")

        assert result is not None
        assert "pypi-camo" in result or "gravatar" in result

    @responses.activate
    def test_returns_none_for_user_without_avatar(self, enricher, sample_pypi_profile_html_no_avatar):
        """Test handling of profiles without avatars."""
        # Clear the memoization cache before test
        if hasattr(enricher._scrape_avatar_url, 'cache'):
            enricher._scrape_avatar_url.cache.clear()

        responses.add(
            responses.GET,
            "https://pypi.org/user/newuser/",
            body=sample_pypi_profile_html_no_avatar,
            status=200,
        )

        result = enricher._scrape_avatar_url("newuser")

        assert result is None

    @responses.activate
    def test_returns_none_for_404(self, enricher):
        """Test handling of 404 errors."""
        # Clear the memoization cache before test
        if hasattr(enricher._scrape_avatar_url, 'cache'):
            enricher._scrape_avatar_url.cache.clear()

        responses.add(
            responses.GET,
            "https://pypi.org/user/nonexistent/",
            status=404,
        )

        result = enricher._scrape_avatar_url("nonexistent")

        assert result is None

    @responses.activate
    def test_handles_rate_limiting(self, enricher, sample_pypi_profile_html):
        """Test handling of rate limiting with retry."""
        # Clear the memoization cache before test
        if hasattr(enricher._scrape_avatar_url, 'cache'):
            enricher._scrape_avatar_url.cache.clear()

        responses.add(
            responses.GET,
            "https://pypi.org/user/davisagli/",
            status=429,
            headers={"Retry-After": "0.1"},
        )
        responses.add(
            responses.GET,
            "https://pypi.org/user/davisagli/",
            body=sample_pypi_profile_html,
            status=200,
        )

        result = enricher._scrape_avatar_url("davisagli")

        assert result is not None

    @responses.activate
    def test_caches_avatar_urls(self, enricher, sample_pypi_profile_html):
        """Test that avatar URLs are cached."""
        # Clear the memoization cache before test
        if hasattr(enricher._scrape_avatar_url, 'cache'):
            enricher._scrape_avatar_url.cache.clear()

        responses.add(
            responses.GET,
            "https://pypi.org/user/davisagli/",
            body=sample_pypi_profile_html,
            status=200,
        )

        # First call
        result1 = enricher._scrape_avatar_url("davisagli")
        # Second call should use cache
        result2 = enricher._scrape_avatar_url("davisagli")

        assert result1 == result2
        # Only one HTTP request should have been made
        assert len(responses.calls) == 1


# ============================================================================
# Rate Limiting Tests
# ============================================================================

class TestRateLimiting:
    """Test the _apply_rate_limit method."""

    def test_applies_delay_between_requests(self, enricher):
        """Test that rate limiting applies delay."""
        import pyf.aggregator.enrichers.maintainers as maintainers_module

        original_delay = maintainers_module.PYPI_PROFILE_RATE_LIMIT_DELAY

        try:
            maintainers_module.PYPI_PROFILE_RATE_LIMIT_DELAY = 0.1
            enricher._last_request_time = time.time()

            start = time.time()
            enricher._apply_rate_limit()
            elapsed = time.time() - start

            assert elapsed >= 0.05
        finally:
            maintainers_module.PYPI_PROFILE_RATE_LIMIT_DELAY = original_delay


# ============================================================================
# Document Update Tests
# ============================================================================

class TestUpdateDoc:
    """Test the update_doc method."""

    def test_updates_document_with_maintainers(self, enricher):
        """Test updating a document with maintainer data."""
        mock_doc = MagicMock()
        enricher.client.collections = {
            "test_collection": MagicMock(
                documents={
                    "plone.api-2.0.0": mock_doc
                }
            )
        }

        maintainers = [
            {"username": "davisagli", "avatar_url": "https://example.com/avatar1.png"},
            {"username": "tisto", "avatar_url": "https://example.com/avatar2.png"},
        ]

        enricher.update_doc("test_collection", "plone.api-2.0.0", maintainers, page=1, enrich_counter=1)

        mock_doc.update.assert_called_once()
        call_args = mock_doc.update.call_args[0][0]
        assert call_args["maintainers"] == maintainers


# ============================================================================
# Full Enrichment Flow Tests
# ============================================================================

class TestRun:
    """Test the run method (full enrichment flow)."""

    @responses.activate
    def test_enriches_packages(self, enricher, sample_pypi_data_db, sample_pypi_profile_html, sample_typesense_search_results):
        """Test full enrichment flow."""
        # Mock avatar scraping for all users
        for username in ["davisagli", "tisto", "jensens", "sneridagh"]:
            responses.add(
                responses.GET,
                f"https://pypi.org/user/{username}/",
                body=sample_pypi_profile_html.replace("davisagli", username),
                status=200,
            )

        enricher.ts_search = MagicMock(return_value=sample_typesense_search_results)
        enricher.update_doc = MagicMock()
        enricher._download_pypi_data = MagicMock(return_value=str(sample_pypi_data_db))

        enricher.run("test_collection")

        # Should have updated both packages
        assert enricher.update_doc.call_count == 2

    def test_skips_packages_without_maintainers(self, enricher, sample_pypi_data_db, sample_typesense_search_results):
        """Test that packages without maintainers are skipped."""
        # Modify search results to include a package not in the DB
        modified_results = sample_typesense_search_results.copy()
        modified_results["grouped_hits"] = [
            {
                "hits": [
                    {
                        "document": {
                            "id": "unknown-package-1.0.0",
                            "name": "unknown-package",
                            "version": "1.0.0"
                        }
                    }
                ]
            }
        ]

        enricher.ts_search = MagicMock(return_value=modified_results)
        enricher.update_doc = MagicMock()
        enricher._download_pypi_data = MagicMock(return_value=str(sample_pypi_data_db))

        enricher.run("test_collection")

        # Should not have updated any packages
        assert enricher.update_doc.call_count == 0

    def test_handles_missing_database(self, enricher, sample_typesense_search_results):
        """Test handling when database download fails."""
        enricher.ts_search = MagicMock(return_value=sample_typesense_search_results)
        enricher.update_doc = MagicMock()
        enricher._download_pypi_data = MagicMock(return_value=None)

        # Should not raise, just return early
        enricher.run("test_collection")

        # Should not have updated any packages
        assert enricher.update_doc.call_count == 0


# ============================================================================
# CLI Tests
# ============================================================================

class TestMain:
    """Test the main CLI entry point."""

    def test_main_with_profile(self):
        """Test main function with profile argument."""
        from pyf.aggregator.enrichers.maintainers import main

        with patch('pyf.aggregator.enrichers.maintainers.MaintainerEnricher') as mock_enricher_class:
            mock_enricher = MagicMock()
            mock_enricher_class.return_value = mock_enricher

            with patch('sys.argv', ['pyfmaintainers', '-p', 'plone']):
                with patch('pyf.aggregator.enrichers.maintainers.ProfileManager') as mock_pm:
                    mock_pm.return_value.get_profile.return_value = {"classifiers": ["Framework :: Plone"]}
                    mock_pm.return_value.validate_profile.return_value = True
                    main()

            mock_enricher.run.assert_called_once()

    def test_main_with_single_package(self):
        """Test main function with single package name."""
        from pyf.aggregator.enrichers.maintainers import main

        with patch('pyf.aggregator.enrichers.maintainers.MaintainerEnricher') as mock_enricher_class:
            mock_enricher = MagicMock()
            mock_enricher_class.return_value = mock_enricher

            with patch('sys.argv', ['pyfmaintainers', '-p', 'plone', '-n', 'plone.api']):
                with patch('pyf.aggregator.enrichers.maintainers.ProfileManager') as mock_pm:
                    mock_pm.return_value.get_profile.return_value = {"classifiers": ["Framework :: Plone"]}
                    mock_pm.return_value.validate_profile.return_value = True
                    main()

            mock_enricher.run.assert_called_once()
            call_kwargs = mock_enricher.run.call_args
            assert call_kwargs[1].get('package_name') == 'plone.api' or \
                   (len(call_kwargs[0]) > 1 and call_kwargs[0][1] == 'plone.api')


# ============================================================================
# SQLite Validation Tests
# ============================================================================

class TestValidateSqliteDb:
    """Test the _validate_sqlite_db method."""

    def test_validates_correct_database(self, enricher, sample_pypi_data_db):
        """Valid db with maintainers table returns True."""
        result = enricher._validate_sqlite_db(str(sample_pypi_data_db))
        assert result is True

    def test_rejects_corrupted_file(self, enricher, tmp_path):
        """Corrupted file returns False."""
        corrupted_db = tmp_path / "corrupted.db"
        corrupted_db.write_text("garbage data not a database")

        result = enricher._validate_sqlite_db(str(corrupted_db))
        assert result is False

    def test_rejects_database_without_maintainers_table(self, enricher, tmp_path):
        """Valid SQLite but missing maintainers table returns False."""
        db_path = tmp_path / "no_maintainers.db"
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE other_table (id INTEGER PRIMARY KEY)")
        conn.commit()
        conn.close()

        result = enricher._validate_sqlite_db(str(db_path))
        assert result is False

    def test_rejects_nonexistent_file(self, enricher, tmp_path):
        """Missing file returns False."""
        nonexistent = tmp_path / "nonexistent.db"

        result = enricher._validate_sqlite_db(str(nonexistent))
        assert result is False


class TestDownloadPypiDataWithValidation:
    """Test the _download_pypi_data method with validation."""

    @responses.activate
    def test_redownloads_corrupted_cached_database(self, enricher, tmp_path):
        """Verify corrupted cache triggers re-download."""
        import gzip
        import io
        import pyf.aggregator.enrichers.maintainers as maintainers_module

        # Create a corrupted cached database
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        corrupted_db = cache_dir / "pypi.db"
        corrupted_db.write_text("garbage data not a database")

        # Create a valid SQLite database with maintainers table
        db_path_temp = tmp_path / "temp.db"
        conn = sqlite3.connect(db_path_temp)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE maintainers (
                package_name TEXT,
                name TEXT
            )
        """)
        cursor.execute("INSERT INTO maintainers VALUES ('test', 'user')")
        conn.commit()
        conn.close()

        # Create GZIP file containing the SQLite database
        with open(db_path_temp, 'rb') as f:
            db_bytes = f.read()

        gz_buffer = io.BytesIO()
        with gzip.GzipFile(fileobj=gz_buffer, mode='wb') as gz:
            gz.write(db_bytes)

        responses.add(
            responses.GET,
            "https://github.com/sethmlarson/pypi-data/releases/latest/download/pypi.db.gz",
            body=gz_buffer.getvalue(),
            status=200,
            content_type="application/gzip",
        )

        original_cache_dir = maintainers_module.PYPI_DATA_CACHE_DIR
        original_cache_ttl = maintainers_module.PYPI_DATA_CACHE_TTL

        try:
            maintainers_module.PYPI_DATA_CACHE_DIR = str(cache_dir)
            maintainers_module.PYPI_DATA_CACHE_TTL = 86400  # 24 hours - cache is "fresh"

            result = enricher._download_pypi_data()

            # Should have re-downloaded and returned a valid path
            assert result is not None
            assert os.path.exists(result)

            # Verify the new file is a valid database with maintainers table
            assert enricher._validate_sqlite_db(result) is True

            # Verify a download was made (corrupted cache was replaced)
            assert len(responses.calls) == 1
        finally:
            maintainers_module.PYPI_DATA_CACHE_DIR = original_cache_dir
            maintainers_module.PYPI_DATA_CACHE_TTL = original_cache_ttl
