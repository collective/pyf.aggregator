"""
Pytest configuration and fixtures for pyf.aggregator tests.

This module provides fixtures for:
- Mocking PyPI API responses (JSON API, Simple API, RSS feeds)
- Mocking Typesense client operations
- Sample package data for testing
- Celery task configuration for testing
"""

import os
import pytest
import responses
from unittest.mock import MagicMock, patch


# Set test environment variables before importing modules
os.environ.setdefault("TYPESENSE_HOST", "localhost")
os.environ.setdefault("TYPESENSE_PORT", "8108")
os.environ.setdefault("TYPESENSE_PROTOCOL", "http")
os.environ.setdefault("TYPESENSE_API_KEY", "test-api-key")
os.environ.setdefault("TYPESENSE_TIMEOUT", "30")
os.environ.setdefault("REDIS_HOST", "redis://localhost:6379/0")
os.environ.setdefault("TYPESENSE_COLLECTION", "test_packages")


# ============================================================================
# Sample Data Fixtures
# ============================================================================


@pytest.fixture
def sample_pypi_json_plone():
    """Sample PyPI JSON response for a Plone package."""
    return {
        "info": {
            "name": "plone.api",
            "version": "2.0.0",
            "author": "Plone Foundation",
            "author_email": "foundation@plone.org",
            "bugtrack_url": None,
            "classifiers": [
                "Development Status :: 5 - Production/Stable",
                "Framework :: Plone",
                "Framework :: Plone :: 5.2",
                "Framework :: Plone :: 6.0",
                "License :: OSI Approved :: GNU General Public License v2 (GPLv2)",
                "Programming Language :: Python :: 3.8",
                "Programming Language :: Python :: 3.9",
                "Programming Language :: Python :: 3.10",
                "Programming Language :: Python :: 3.11",
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
            "project_urls": {
                "Homepage": "https://github.com/plone/plone.api",
                "Documentation": "https://ploneapi.readthedocs.io/",
            },
            "release_url": "https://pypi.org/project/plone.api/2.0.0/",
            "requires_dist": ["plone.base", "zope.interface"],
            "summary": "A simple API for Plone",
            "yanked": False,
            "yanked_reason": None,
        },
        "releases": {
            "1.0.0": [{"upload_time": "2020-01-01T00:00:00"}],
            "2.0.0": [{"upload_time": "2023-06-15T12:30:00"}],
        },
        "urls": [
            {
                "comment_text": "",
                "digests": {"sha256": "abc123"},
                "downloads": -1,
                "filename": "plone.api-2.0.0.tar.gz",
                "md5_digest": "def456",
                "packagetype": "sdist",
                "python_requires": ">=3.8",
                "requires_python": ">=3.8",
                "size": 12345,
                "upload_time": "2023-06-15T12:30:00",
                "url": "https://files.pythonhosted.org/packages/plone.api-2.0.0.tar.gz",
                "yanked": False,
            }
        ],
    }


@pytest.fixture
def sample_pypi_json_non_plone():
    """Sample PyPI JSON response for a non-Plone package."""
    return {
        "info": {
            "name": "requests",
            "version": "2.31.0",
            "author": "Kenneth Reitz",
            "author_email": "me@kennethreitz.org",
            "bugtrack_url": None,
            "classifiers": [
                "Development Status :: 5 - Production/Stable",
                "Intended Audience :: Developers",
                "License :: OSI Approved :: Apache Software License",
                "Programming Language :: Python :: 3",
                "Programming Language :: Python :: 3.7",
                "Programming Language :: Python :: 3.8",
            ],
            "description": "Python HTTP for Humans",
            "description_content_type": "",
            "docs_url": None,
            "home_page": "https://requests.readthedocs.io",
            "keywords": [],
            "license": "Apache 2.0",
            "maintainer": "",
            "maintainer_email": "",
            "package_url": "https://pypi.org/project/requests/",
            "platform": "",
            "project_url": "https://pypi.org/project/requests/",
            "project_urls": None,
            "release_url": "https://pypi.org/project/requests/2.31.0/",
            "requires_dist": ["urllib3>=1.21.1"],
            "summary": "Python HTTP for Humans.",
            "yanked": False,
            "yanked_reason": None,
        },
        "releases": {
            "2.30.0": [{"upload_time": "2023-05-01T00:00:00"}],
            "2.31.0": [{"upload_time": "2023-05-22T00:00:00"}],
        },
        "urls": [],
    }


@pytest.fixture
def sample_pypi_json_empty_classifiers():
    """Sample PyPI JSON response with empty classifiers."""
    return {
        "info": {
            "name": "some-package",
            "version": "1.0.0",
            "author": "",
            "author_email": "",
            "bugtrack_url": None,
            "classifiers": [],
            "description": "",
            "description_content_type": "",
            "docs_url": None,
            "home_page": "",
            "keywords": [],
            "license": "",
            "maintainer": "",
            "maintainer_email": "",
            "package_url": "https://pypi.org/project/some-package/",
            "platform": "",
            "project_url": "https://pypi.org/project/some-package/",
            "project_urls": None,
            "release_url": "https://pypi.org/project/some-package/1.0.0/",
            "requires_dist": None,
            "summary": "",
            "yanked": False,
            "yanked_reason": None,
        },
        "releases": {},
        "urls": [],
    }


@pytest.fixture
def sample_pypi_json_no_info():
    """Sample PyPI JSON response with missing info section."""
    return {
        "releases": {},
        "urls": [],
    }


@pytest.fixture
def sample_pypi_json_django():
    """Sample PyPI JSON response for a Django package."""
    return {
        "info": {
            "name": "django-rest-framework",
            "version": "3.14.0",
            "author": "Tom Christie",
            "author_email": "tom@tomchristie.com",
            "bugtrack_url": None,
            "classifiers": [
                "Development Status :: 5 - Production/Stable",
                "Framework :: Django",
                "Framework :: Django :: 4.2",
                "Framework :: Django :: 5.0",
                "License :: OSI Approved :: BSD License",
                "Programming Language :: Python :: 3",
                "Programming Language :: Python :: 3.8",
                "Programming Language :: Python :: 3.9",
                "Programming Language :: Python :: 3.10",
                "Programming Language :: Python :: 3.11",
            ],
            "description": "Web APIs for Django, made easy.",
            "description_content_type": "text/markdown",
            "docs_url": None,
            "home_page": "https://www.django-rest-framework.org/",
            "keywords": ["django", "rest", "api"],
            "license": "BSD",
            "maintainer": "",
            "maintainer_email": "",
            "package_url": "https://pypi.org/project/django-rest-framework/",
            "platform": "",
            "project_url": "https://pypi.org/project/django-rest-framework/",
            "project_urls": {
                "Homepage": "https://www.django-rest-framework.org/",
                "Documentation": "https://www.django-rest-framework.org/",
            },
            "release_url": "https://pypi.org/project/django-rest-framework/3.14.0/",
            "requires_dist": ["django>=3.0"],
            "summary": "Web APIs for Django, made easy.",
            "yanked": False,
            "yanked_reason": None,
        },
        "releases": {
            "3.13.0": [{"upload_time": "2023-01-01T00:00:00"}],
            "3.14.0": [{"upload_time": "2023-06-15T12:30:00"}],
        },
        "urls": [
            {
                "comment_text": "",
                "digests": {"sha256": "abc123"},
                "downloads": -1,
                "filename": "django-rest-framework-3.14.0.tar.gz",
                "md5_digest": "def456",
                "packagetype": "sdist",
                "python_requires": ">=3.8",
                "requires_python": ">=3.8",
                "size": 12345,
                "upload_time": "2023-06-15T12:30:00",
                "url": "https://files.pythonhosted.org/packages/django-rest-framework-3.14.0.tar.gz",
                "yanked": False,
            }
        ],
    }


@pytest.fixture
def sample_pypi_json_flask():
    """Sample PyPI JSON response for a Flask package."""
    return {
        "info": {
            "name": "flask-restful",
            "version": "0.3.10",
            "author": "Kyle Conroy",
            "author_email": "info@twilio.com",
            "bugtrack_url": None,
            "classifiers": [
                "Development Status :: 5 - Production/Stable",
                "Framework :: Flask",
                "License :: OSI Approved :: BSD License",
                "Programming Language :: Python :: 3",
                "Programming Language :: Python :: 3.7",
                "Programming Language :: Python :: 3.8",
                "Programming Language :: Python :: 3.9",
                "Programming Language :: Python :: 3.10",
            ],
            "description": "Simple framework for creating REST APIs",
            "description_content_type": "text/x-rst",
            "docs_url": None,
            "home_page": "https://flask-restful.readthedocs.io/",
            "keywords": ["flask", "rest", "api"],
            "license": "BSD",
            "maintainer": "",
            "maintainer_email": "",
            "package_url": "https://pypi.org/project/flask-restful/",
            "platform": "",
            "project_url": "https://pypi.org/project/flask-restful/",
            "project_urls": {
                "Homepage": "https://flask-restful.readthedocs.io/",
                "Documentation": "https://flask-restful.readthedocs.io/",
            },
            "release_url": "https://pypi.org/project/flask-restful/0.3.10/",
            "requires_dist": ["flask>=0.8"],
            "summary": "Simple framework for creating REST APIs",
            "yanked": False,
            "yanked_reason": None,
        },
        "releases": {
            "0.3.9": [{"upload_time": "2022-01-01T00:00:00"}],
            "0.3.10": [{"upload_time": "2023-03-15T12:30:00"}],
        },
        "urls": [
            {
                "comment_text": "",
                "digests": {"sha256": "xyz789"},
                "downloads": -1,
                "filename": "flask-restful-0.3.10.tar.gz",
                "md5_digest": "uvw012",
                "packagetype": "sdist",
                "python_requires": ">=3.7",
                "requires_python": ">=3.7",
                "size": 9876,
                "upload_time": "2023-03-15T12:30:00",
                "url": "https://files.pythonhosted.org/packages/flask-restful-0.3.10.tar.gz",
                "yanked": False,
            }
        ],
    }


@pytest.fixture
def sample_simple_api_response():
    """Sample PyPI Simple API JSON response."""
    return {
        "meta": {"api-version": "1.0"},
        "projects": [
            {"name": "plone.api"},
            {"name": "plone.app.contenttypes"},
            {"name": "requests"},
            {"name": "django"},
        ],
    }


@pytest.fixture
def sample_rss_feed_xml():
    """Sample PyPI RSS feed XML content."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>PyPI updates</title>
    <link>https://pypi.org/</link>
    <description>Latest updates on PyPI</description>
    <item>
      <title>plone.api 2.0.0</title>
      <link>https://pypi.org/project/plone.api/2.0.0/</link>
      <description>A simple API for Plone</description>
      <pubDate>Thu, 15 Jun 2023 12:30:00 GMT</pubDate>
    </item>
    <item>
      <title>requests 2.31.0</title>
      <link>https://pypi.org/project/requests/2.31.0/</link>
      <description>Python HTTP for Humans</description>
      <pubDate>Mon, 22 May 2023 10:00:00 GMT</pubDate>
    </item>
    <item>
      <title>plone.restapi 8.0.0</title>
      <link>https://pypi.org/project/plone.restapi/8.0.0/</link>
      <description>RESTful API for Plone</description>
      <pubDate>Wed, 14 Jun 2023 08:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>"""


# ============================================================================
# Mock Fixtures
# ============================================================================


@pytest.fixture
def mock_typesense_client():
    """Mock Typesense client for testing without a real Typesense server."""
    mock_client = MagicMock()

    # Mock collections access
    mock_collection = MagicMock()
    mock_collection.retrieve.return_value = {"name": "test_packages"}
    mock_collection.documents.upsert.return_value = {"id": "test-id"}
    mock_collection.documents.import_.return_value = [{"success": True}]
    mock_collection.documents.search.return_value = {
        "found": 1,
        "hits": [{"document": {"name": "plone.api"}}],
    }

    mock_client.collections.__getitem__.return_value = mock_collection
    mock_client.collections.create.return_value = {"name": "test_packages"}
    mock_client.collections.retrieve.return_value = []

    return mock_client


@pytest.fixture
def mock_typesense(mock_typesense_client):
    """Patch TypesenseConnection to use mock client."""
    with patch(
        "pyf.aggregator.db.typesense.Client", return_value=mock_typesense_client
    ):
        yield mock_typesense_client


@pytest.fixture
def mock_queue_typesense(mock_typesense_client):
    """Patch Typesense in queue.py for task testing."""
    with patch("pyf.aggregator.queue.PackageIndexer") as mock_indexer_class:
        mock_indexer = MagicMock()
        mock_indexer.clean_data.side_effect = lambda x: x
        mock_indexer.index_single.return_value = {"success": True}
        mock_indexer_class.return_value = mock_indexer
        yield mock_indexer


@pytest.fixture
def mocked_responses():
    """Activate responses mock for HTTP requests."""
    with responses.RequestsMock() as rsps:
        yield rsps


# ============================================================================
# Aggregator Fixtures
# ============================================================================


@pytest.fixture
def aggregator_first_mode():
    """Create an Aggregator instance in 'first' (full download) mode."""
    from pyf.aggregator.fetcher import Aggregator

    return Aggregator(
        mode="first",
        sincefile=".test_sincefile",
        limit=10,
    )


@pytest.fixture
def aggregator_incremental_mode(tmp_path):
    """Create an Aggregator instance in 'incremental' mode with a sincefile."""
    from pyf.aggregator.fetcher import Aggregator

    # Create a sincefile with a past timestamp
    sincefile = tmp_path / ".pyfaggregator"
    sincefile.write_text("1686700000")  # June 14, 2023

    return Aggregator(
        mode="incremental",
        sincefile=str(sincefile),
        limit=10,
    )


@pytest.fixture
def aggregator_with_plone_filter():
    """Create an Aggregator with Plone classifier filter enabled."""
    from pyf.aggregator.fetcher import Aggregator

    return Aggregator(
        mode="first",
        sincefile=".test_sincefile",
        filter_troove="Framework :: Plone",
        limit=10,
    )


# ============================================================================
# Celery Test Configuration
# ============================================================================


@pytest.fixture(scope="session")
def celery_config():
    """Configure Celery for testing (use eager mode)."""
    return {
        "broker_url": "memory://",
        "result_backend": "cache+memory://",
        "task_always_eager": True,
        "task_eager_propagates": True,
    }


@pytest.fixture
def celery_eager_mode():
    """Enable Celery eager mode for synchronous task execution in tests."""
    from pyf.aggregator.queue import app

    original_eager = app.conf.task_always_eager
    original_propagates = app.conf.task_eager_propagates

    app.conf.task_always_eager = True
    app.conf.task_eager_propagates = True

    yield app

    app.conf.task_always_eager = original_eager
    app.conf.task_eager_propagates = original_propagates


# ============================================================================
# Response Mocking Helpers
# ============================================================================


@pytest.fixture
def mock_pypi_json_api(
    mocked_responses, sample_pypi_json_plone, sample_pypi_json_non_plone
):
    """Setup mock responses for PyPI JSON API endpoints."""
    # Mock plone.api
    mocked_responses.add(
        responses.GET,
        "https://pypi.org/pypi/plone.api/json",
        json=sample_pypi_json_plone,
        status=200,
    )

    # Mock requests (non-Plone package)
    mocked_responses.add(
        responses.GET,
        "https://pypi.org/pypi/requests/json",
        json=sample_pypi_json_non_plone,
        status=200,
    )

    # Mock 404 for nonexistent package
    mocked_responses.add(
        responses.GET,
        "https://pypi.org/pypi/nonexistent-package/json",
        status=404,
    )

    return mocked_responses


@pytest.fixture
def mock_pypi_simple_api(mocked_responses, sample_simple_api_response):
    """Setup mock response for PyPI Simple API."""
    mocked_responses.add(
        responses.GET,
        "https://pypi.org/simple",
        json=sample_simple_api_response,
        status=200,
    )
    mocked_responses.add(
        responses.GET,
        "https://pypi.org//simple",
        json=sample_simple_api_response,
        status=200,
    )
    return mocked_responses


@pytest.fixture
def mock_pypi_rss_feeds(mocked_responses, sample_rss_feed_xml):
    """Setup mock responses for PyPI RSS feeds."""
    mocked_responses.add(
        responses.GET,
        "https://pypi.org/rss/updates.xml",
        body=sample_rss_feed_xml,
        status=200,
        content_type="application/rss+xml",
    )
    mocked_responses.add(
        responses.GET,
        "https://pypi.org/rss/packages.xml",
        body=sample_rss_feed_xml,
        status=200,
        content_type="application/rss+xml",
    )
    return mocked_responses


# ============================================================================
# Deduplication Fixtures
# ============================================================================


@pytest.fixture(autouse=True)
def disable_rss_dedup():
    """Disable RSS deduplication in all tests by default.

    This ensures existing tests pass unchanged. Tests that need to verify
    dedup behavior should patch is_package_recently_queued explicitly.
    """
    with patch("pyf.aggregator.queue.is_package_recently_queued", return_value=False):
        yield


# ============================================================================
# Cleanup Fixtures
# ============================================================================


@pytest.fixture(autouse=True)
def cleanup_sincefile():
    """Clean up any sincefile created during tests."""
    yield
    import os

    for f in [".test_sincefile", ".pyfaggregator"]:
        if os.path.exists(f):
            os.remove(f)
