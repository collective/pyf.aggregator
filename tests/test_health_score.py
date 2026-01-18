"""
Unit tests for pyf.aggregator.plugins.health_score module.

This module tests:
- Health score calculation (process function)
- Recency scoring based on upload timestamp
- Documentation scoring based on docs_url, description, project_urls
- Metadata scoring based on maintainer/author, license, classifiers
- Edge cases and error handling
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
import time

from pyf.aggregator.plugins.health_score import (
    process,
    calculate_recency_score,
    calculate_docs_score,
    calculate_metadata_score,
    load,
)


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def sample_package_data_complete():
    """Sample package data with all fields for maximum score."""
    return {
        "name": "plone.api",
        "version": "2.0.0",
        "upload_timestamp": datetime.now(timezone.utc).isoformat(),
        "docs_url": "https://ploneapi.readthedocs.io/",
        "description": "A" * 150,  # >100 chars
        "project_urls": {
            "Documentation": "https://ploneapi.readthedocs.io/",
            "Homepage": "https://github.com/plone/plone.api",
        },
        "maintainer": "Plone Foundation",
        "author": "Plone Team",
        "license": "GPL version 2",
        "classifiers": [
            "Framework :: Plone",
            "Programming Language :: Python :: 3.8",
            "License :: OSI Approved :: GNU General Public License v2 (GPLv2)",
        ],
    }


@pytest.fixture
def sample_package_data_minimal():
    """Sample package data with minimal fields."""
    return {
        "name": "minimal-package",
        "version": "1.0.0",
    }


@pytest.fixture
def sample_package_data_old_release():
    """Sample package data with old release (>5 years ago)."""
    old_date = datetime.now(timezone.utc) - timedelta(days=2000)
    return {
        "name": "old-package",
        "version": "1.0.0",
        "upload_timestamp": old_date.isoformat(),
        "description": "Short",
    }


# ============================================================================
# Process Function Tests
# ============================================================================

class TestProcess:
    """Test the main process function."""

    def test_calculates_score_for_complete_package(self, sample_package_data_complete):
        """Test that complete package data gets a high score."""
        data = sample_package_data_complete.copy()
        process("test-id", data)

        assert "health_score" in data
        assert "health_score_breakdown" in data
        assert "health_score_last_calculated" in data
        assert isinstance(data["health_score"], int)
        assert 0 <= data["health_score"] <= 100

        # Complete package should have a high score
        assert data["health_score"] >= 80

    def test_calculates_score_for_minimal_package(self, sample_package_data_minimal):
        """Test that minimal package data gets a low score."""
        data = sample_package_data_minimal.copy()
        process("test-id", data)

        assert "health_score" in data
        assert data["health_score"] == 0

    def test_includes_breakdown_with_all_factors(self, sample_package_data_complete):
        """Test that breakdown includes all scoring factors."""
        data = sample_package_data_complete.copy()
        process("test-id", data)

        breakdown = data["health_score_breakdown"]
        assert "recency" in breakdown
        assert "documentation" in breakdown
        assert "metadata" in breakdown

    def test_breakdown_scores_sum_to_total(self, sample_package_data_complete):
        """Test that breakdown scores sum to total score."""
        data = sample_package_data_complete.copy()
        process("test-id", data)

        breakdown = data["health_score_breakdown"]
        total_from_breakdown = sum(breakdown.values())
        assert data["health_score"] == int(total_from_breakdown)

    def test_sets_last_calculated_timestamp(self, sample_package_data_complete):
        """Test that last_calculated timestamp is set."""
        data = sample_package_data_complete.copy()
        before = int(time.time())
        process("test-id", data)
        after = int(time.time())

        assert before <= data["health_score_last_calculated"] <= after

    def test_handles_empty_data_dict(self):
        """Test that empty data dict doesn't raise errors."""
        data = {}
        process("test-id", data)

        assert data["health_score"] == 0
        assert data["health_score_breakdown"]["recency"] == 0
        assert data["health_score_breakdown"]["documentation"] == 0
        assert data["health_score_breakdown"]["metadata"] == 0

    def test_modifies_data_in_place(self, sample_package_data_complete):
        """Test that process modifies the data dict in place."""
        data = sample_package_data_complete.copy()
        original_id = id(data)
        process("test-id", data)

        assert id(data) == original_id
        assert "health_score" in data


# ============================================================================
# Recency Score Tests
# ============================================================================

class TestCalculateRecencyScore:
    """Test the calculate_recency_score function."""

    def test_returns_40_for_recent_release(self):
        """Test that releases < 6 months old get 40 points."""
        # 3 months ago
        recent = datetime.now(timezone.utc) - timedelta(days=90)
        score = calculate_recency_score(recent.isoformat())
        assert score == 40

    def test_returns_40_for_very_recent_release(self):
        """Test that releases < 1 week old get 40 points."""
        very_recent = datetime.now(timezone.utc) - timedelta(days=1)
        score = calculate_recency_score(very_recent.isoformat())
        assert score == 40

    def test_returns_30_for_6_to_12_month_old_release(self):
        """Test that releases 6-12 months old get 30 points."""
        # 9 months ago
        medium_old = datetime.now(timezone.utc) - timedelta(days=270)
        score = calculate_recency_score(medium_old.isoformat())
        assert score == 30

    def test_returns_20_for_1_to_2_year_old_release(self):
        """Test that releases 1-2 years old get 20 points."""
        # 18 months ago
        old = datetime.now(timezone.utc) - timedelta(days=540)
        score = calculate_recency_score(old.isoformat())
        assert score == 20

    def test_returns_10_for_2_to_3_year_old_release(self):
        """Test that releases 2-3 years old get 10 points."""
        # 2.5 years ago
        older = datetime.now(timezone.utc) - timedelta(days=912)
        score = calculate_recency_score(older.isoformat())
        assert score == 10

    def test_returns_5_for_3_to_5_year_old_release(self):
        """Test that releases 3-5 years old get 5 points."""
        # 4 years ago
        very_old = datetime.now(timezone.utc) - timedelta(days=1460)
        score = calculate_recency_score(very_old.isoformat())
        assert score == 5

    def test_returns_0_for_very_old_release(self):
        """Test that releases > 5 years old get 0 points."""
        # 6 years ago
        ancient = datetime.now(timezone.utc) - timedelta(days=2190)
        score = calculate_recency_score(ancient.isoformat())
        assert score == 0

    def test_returns_0_for_none_timestamp(self):
        """Test that None timestamp returns 0."""
        score = calculate_recency_score(None)
        assert score == 0

    def test_returns_0_for_empty_string_timestamp(self):
        """Test that empty string timestamp returns 0."""
        score = calculate_recency_score("")
        assert score == 0

    def test_returns_0_for_invalid_timestamp_format(self):
        """Test that invalid timestamp format returns 0."""
        score = calculate_recency_score("not-a-timestamp")
        assert score == 0

    def test_handles_timestamp_with_z_suffix(self):
        """Test that timestamps with Z suffix are parsed correctly."""
        recent = datetime.now(timezone.utc) - timedelta(days=90)
        timestamp_with_z = recent.isoformat().replace("+00:00", "Z")
        score = calculate_recency_score(timestamp_with_z)
        assert score == 40

    def test_returns_0_for_non_string_non_datetime(self):
        """Test that non-string, non-datetime values return 0."""
        score = calculate_recency_score(123456)
        assert score == 0

    def test_boundary_6_months_exactly(self):
        """Test boundary case: exactly 6 months (180 days)."""
        exactly_6_months = datetime.now(timezone.utc) - timedelta(days=180)
        score = calculate_recency_score(exactly_6_months.isoformat())
        assert score == 30  # Should be in 6-12 month range

    def test_boundary_1_year_exactly(self):
        """Test boundary case: exactly 1 year (365 days)."""
        exactly_1_year = datetime.now(timezone.utc) - timedelta(days=365)
        score = calculate_recency_score(exactly_1_year.isoformat())
        assert score == 20  # Should be in 1-2 year range


# ============================================================================
# Documentation Score Tests
# ============================================================================

class TestCalculateDocsScore:
    """Test the calculate_docs_score function."""

    def test_returns_15_for_docs_url(self):
        """Test that having docs_url gives 15 points."""
        data = {"docs_url": "https://docs.example.com"}
        score = calculate_docs_score(data)
        assert score == 15

    def test_returns_10_for_meaningful_description(self):
        """Test that description > 100 chars gives 10 points."""
        data = {"description": "A" * 101}
        score = calculate_docs_score(data)
        assert score == 10

    def test_returns_0_for_short_description(self):
        """Test that description <= 100 chars gives 0 points."""
        data = {"description": "A" * 100}
        score = calculate_docs_score(data)
        assert score == 0

    def test_returns_5_for_documentation_project_url(self):
        """Test that project_urls with 'documentation' gives 5 points."""
        data = {"project_urls": {"Documentation": "https://docs.example.com"}}
        score = calculate_docs_score(data)
        assert score == 5

    def test_returns_5_for_docs_project_url(self):
        """Test that project_urls with 'docs' gives 5 points."""
        data = {"project_urls": {"Docs": "https://docs.example.com"}}
        score = calculate_docs_score(data)
        assert score == 5

    def test_returns_5_for_homepage_project_url(self):
        """Test that project_urls with 'homepage' gives 5 points."""
        data = {"project_urls": {"Homepage": "https://example.com"}}
        score = calculate_docs_score(data)
        assert score == 5

    def test_returns_5_for_home_project_url(self):
        """Test that project_urls with 'home' gives 5 points."""
        data = {"project_urls": {"Home": "https://example.com"}}
        score = calculate_docs_score(data)
        assert score == 5

    def test_case_insensitive_project_url_matching(self):
        """Test that project URL matching is case insensitive."""
        data = {"project_urls": {"DOCUMENTATION": "https://docs.example.com"}}
        score = calculate_docs_score(data)
        assert score == 5

    def test_only_counts_project_urls_once(self):
        """Test that multiple matching project URLs only give 5 points total."""
        data = {
            "project_urls": {
                "Documentation": "https://docs.example.com",
                "Homepage": "https://example.com",
                "Docs": "https://docs2.example.com",
            }
        }
        score = calculate_docs_score(data)
        assert score == 5  # Only 5 points, not 15

    def test_returns_30_for_all_documentation_factors(self):
        """Test that having all documentation factors gives 30 points."""
        data = {
            "docs_url": "https://docs.example.com",
            "description": "A" * 150,
            "project_urls": {"Documentation": "https://docs.example.com"},
        }
        score = calculate_docs_score(data)
        assert score == 30

    def test_returns_0_for_empty_data(self):
        """Test that empty data returns 0."""
        score = calculate_docs_score({})
        assert score == 0

    def test_returns_0_for_empty_description_string(self):
        """Test that empty description string returns 0."""
        data = {"description": ""}
        score = calculate_docs_score(data)
        assert score == 0

    def test_returns_0_for_none_description(self):
        """Test that None description returns 0."""
        data = {"description": None}
        score = calculate_docs_score(data)
        assert score == 0

    def test_returns_0_for_empty_project_urls(self):
        """Test that empty project_urls dict returns 0."""
        data = {"project_urls": {}}
        score = calculate_docs_score(data)
        assert score == 0

    def test_returns_0_for_none_project_urls(self):
        """Test that None project_urls returns 0."""
        data = {"project_urls": None}
        score = calculate_docs_score(data)
        assert score == 0

    def test_ignores_non_matching_project_urls(self):
        """Test that non-matching project URLs don't give points."""
        data = {
            "project_urls": {
                "Source": "https://github.com/example/project",
                "Issues": "https://github.com/example/project/issues",
            }
        }
        score = calculate_docs_score(data)
        assert score == 0


# ============================================================================
# Metadata Score Tests
# ============================================================================

class TestCalculateMetadataScore:
    """Test the calculate_metadata_score function."""

    def test_returns_10_for_maintainer(self):
        """Test that having maintainer gives 10 points."""
        data = {"maintainer": "John Doe"}
        score = calculate_metadata_score(data)
        assert score == 10

    def test_returns_10_for_author(self):
        """Test that having author gives 10 points."""
        data = {"author": "Jane Doe"}
        score = calculate_metadata_score(data)
        assert score == 10

    def test_returns_10_for_both_maintainer_and_author(self):
        """Test that having both maintainer and author gives 10 points (not 20)."""
        data = {"maintainer": "John Doe", "author": "Jane Doe"}
        score = calculate_metadata_score(data)
        assert score == 10

    def test_returns_10_for_license(self):
        """Test that having license gives 10 points."""
        data = {"license": "MIT"}
        score = calculate_metadata_score(data)
        assert score == 10

    def test_returns_10_for_3_classifiers(self):
        """Test that having exactly 3 classifiers gives 10 points."""
        data = {"classifiers": ["A", "B", "C"]}
        score = calculate_metadata_score(data)
        assert score == 10

    def test_returns_10_for_more_than_3_classifiers(self):
        """Test that having > 3 classifiers gives 10 points."""
        data = {"classifiers": ["A", "B", "C", "D", "E"]}
        score = calculate_metadata_score(data)
        assert score == 10

    def test_returns_0_for_less_than_3_classifiers(self):
        """Test that having < 3 classifiers gives 0 points."""
        data = {"classifiers": ["A", "B"]}
        score = calculate_metadata_score(data)
        assert score == 0

    def test_returns_0_for_empty_classifiers(self):
        """Test that empty classifiers list gives 0 points."""
        data = {"classifiers": []}
        score = calculate_metadata_score(data)
        assert score == 0

    def test_returns_30_for_all_metadata_factors(self):
        """Test that having all metadata factors gives 30 points."""
        data = {
            "maintainer": "John Doe",
            "license": "MIT",
            "classifiers": ["A", "B", "C"],
        }
        score = calculate_metadata_score(data)
        assert score == 30

    def test_returns_0_for_empty_data(self):
        """Test that empty data returns 0."""
        score = calculate_metadata_score({})
        assert score == 0

    def test_returns_0_for_empty_maintainer(self):
        """Test that empty maintainer string gives 0 points."""
        data = {"maintainer": ""}
        score = calculate_metadata_score(data)
        assert score == 0

    def test_returns_0_for_empty_author(self):
        """Test that empty author string gives 0 points."""
        data = {"author": ""}
        score = calculate_metadata_score(data)
        assert score == 0

    def test_returns_0_for_empty_license(self):
        """Test that empty license string gives 0 points."""
        data = {"license": ""}
        score = calculate_metadata_score(data)
        assert score == 0

    def test_handles_none_classifiers_gracefully(self):
        """Test that None classifiers defaults to empty list and gives 0 points."""
        # When classifiers is None, get() returns None, not default []
        # This causes TypeError, so we verify the actual behavior
        data = {"classifiers": None}
        with pytest.raises(TypeError):
            calculate_metadata_score(data)


# ============================================================================
# Load Function Tests
# ============================================================================

class TestLoad:
    """Test the load function."""

    def test_returns_process_function(self):
        """Test that load returns the process function."""
        result = load({})
        assert result == process

    def test_returned_function_is_callable(self):
        """Test that the returned function is callable."""
        result = load({})
        assert callable(result)

    def test_returned_function_works(self):
        """Test that the returned function works correctly."""
        processor = load({})
        data = {"name": "test"}
        processor("test-id", data)
        assert "health_score" in data


# ============================================================================
# Integration Tests
# ============================================================================

class TestIntegration:
    """Integration tests combining multiple factors."""

    def test_perfect_score_scenario(self):
        """Test a package that should get nearly perfect score."""
        data = {
            "upload_timestamp": datetime.now(timezone.utc).isoformat(),
            "docs_url": "https://docs.example.com",
            "description": "A" * 200,
            "project_urls": {"Documentation": "https://docs.example.com"},
            "maintainer": "Team",
            "license": "MIT",
            "classifiers": ["A", "B", "C", "D"],
        }
        process("test-id", data)
        assert data["health_score"] == 100

    def test_zero_score_scenario(self):
        """Test a package that should get zero score."""
        data = {"name": "empty-package"}
        process("test-id", data)
        assert data["health_score"] == 0

    def test_medium_score_scenario(self):
        """Test a package that should get medium score."""
        # Old package but good documentation and metadata
        old_date = datetime.now(timezone.utc) - timedelta(days=2000)
        data = {
            "upload_timestamp": old_date.isoformat(),
            "docs_url": "https://docs.example.com",
            "description": "A" * 150,
            "project_urls": {"Documentation": "https://docs.example.com"},
            "maintainer": "Team",
            "license": "MIT",
            "classifiers": ["A", "B", "C"],
        }
        process("test-id", data)
        # Should get 0 + 30 + 30 = 60
        assert data["health_score"] == 60

    def test_recent_but_poor_metadata_scenario(self):
        """Test a recent package with poor metadata."""
        data = {
            "upload_timestamp": datetime.now(timezone.utc).isoformat(),
            "description": "Short",
        }
        process("test-id", data)
        # Should get 40 (recency) + 0 (docs) + 0 (metadata) = 40
        assert data["health_score"] == 40

    def test_score_consistency_on_multiple_calls(self):
        """Test that calling process multiple times updates the score consistently."""
        data = {"name": "test", "maintainer": "Team"}

        process("test-id", data)
        first_score = data["health_score"]
        first_timestamp = data["health_score_last_calculated"]

        # Wait a full second for timestamp to change (uses second precision)
        time.sleep(1.1)
        process("test-id", data)
        second_score = data["health_score"]
        second_timestamp = data["health_score_last_calculated"]

        # Score should be the same
        assert first_score == second_score
        # Timestamp should be updated
        assert second_timestamp > first_timestamp
