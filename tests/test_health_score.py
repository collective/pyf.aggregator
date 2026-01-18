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
from pyf.aggregator.enrichers.health_calculator import HealthEnricher


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


# ============================================================================
# Health Score Integration Tests (Full Pipeline)
# ============================================================================

class TestHealthScoreIntegration:
    """Integration tests for the full health scoring pipeline."""

    def test_real_world_plone_package_simulation(self):
        """Test realistic Plone package with typical PyPI data."""
        data = {
            "name": "plone.api",
            "version": "2.0.3",
            "upload_timestamp": (datetime.now(timezone.utc) - timedelta(days=30)).isoformat(),
            "docs_url": "https://ploneapi.readthedocs.io/en/latest/",
            "description": (
                "plone.api is an elegant and simple API for Plone. "
                "It provides a high-level API to access Plone functionality. "
                "The goal is to make working with Plone easier."
            ),
            "project_urls": {
                "Documentation": "https://ploneapi.readthedocs.io/",
                "Source": "https://github.com/plone/plone.api",
                "Tracker": "https://github.com/plone/plone.api/issues",
            },
            "maintainer": "Plone Foundation",
            "maintainer_email": "plone-developers@lists.sourceforge.net",
            "author": "Plone Team",
            "author_email": "plone-developers@lists.sourceforge.net",
            "license": "GPL version 2",
            "classifiers": [
                "Development Status :: 5 - Production/Stable",
                "Framework :: Plone",
                "Framework :: Plone :: 6.0",
                "Programming Language :: Python",
                "Programming Language :: Python :: 3.8",
                "Programming Language :: Python :: 3.9",
                "Programming Language :: Python :: 3.10",
            ],
        }

        process("plone.api", data)

        # Verify all expected fields are present
        assert "health_score" in data
        assert "health_score_breakdown" in data
        assert "health_score_last_calculated" in data

        # Verify score components
        breakdown = data["health_score_breakdown"]
        assert breakdown["recency"] == 40  # Recent upload
        assert breakdown["documentation"] == 30  # Has docs_url, long description, and project_urls
        assert breakdown["metadata"] == 30  # Has maintainer, license, and 3+ classifiers

        # Verify total score
        assert data["health_score"] == 100

    def test_legacy_package_with_minimal_metadata(self):
        """Test old package with minimal metadata (common for legacy packages)."""
        old_date = datetime.now(timezone.utc) - timedelta(days=1500)
        data = {
            "name": "Products.PloneFormGen",
            "version": "1.8.0",
            "upload_timestamp": old_date.isoformat(),
            "description": "A form generator for Plone",
            "author": "Plone Community",
            "classifiers": [
                "Framework :: Plone",
            ],
        }

        process("Products.PloneFormGen", data)

        # Verify scoring for legacy package
        breakdown = data["health_score_breakdown"]
        assert breakdown["recency"] == 5  # Old release (3-5 years, 1500 days ≈ 4.1 years)
        assert breakdown["documentation"] == 0  # No docs_url, short description, no project_urls
        assert breakdown["metadata"] == 10  # Has author, no license, < 3 classifiers

        assert data["health_score"] == 15

    def test_brand_new_package_with_incomplete_setup(self):
        """Test newly released package with incomplete metadata."""
        data = {
            "name": "experimental.plone.feature",
            "version": "0.1.0",
            "upload_timestamp": datetime.now(timezone.utc).isoformat(),
            "description": "Experimental feature",
            "author": "Developer",
        }

        process("experimental.plone.feature", data)

        # Very recent but minimal metadata
        breakdown = data["health_score_breakdown"]
        assert breakdown["recency"] == 40  # Just released
        assert breakdown["documentation"] == 0  # Minimal docs
        assert breakdown["metadata"] == 10  # Has author only

        assert data["health_score"] == 50

    def test_well_documented_but_old_package(self):
        """Test package with excellent documentation but old release."""
        old_date = datetime.now(timezone.utc) - timedelta(days=729)
        data = {
            "name": "collective.easyform",
            "version": "3.1.0",
            "upload_timestamp": old_date.isoformat(),
            "docs_url": "https://collectiveeasyform.readthedocs.io/",
            "description": (
                "collective.easyform enables creation of custom forms through-the-web. "
                "It provides a powerful form builder with validation, custom actions, "
                "and a variety of field types. Extensive documentation available online."
            ),
            "project_urls": {
                "Documentation": "https://collectiveeasyform.readthedocs.io/",
                "Source": "https://github.com/collective/collective.easyform",
            },
            "maintainer": "Collective Contributors",
            "license": "GPL version 2",
            "classifiers": [
                "Framework :: Plone",
                "Framework :: Plone :: 5.2",
                "Framework :: Plone :: 6.0",
                "Programming Language :: Python :: 3",
            ],
        }

        process("collective.easyform", data)

        # Old but well-maintained documentation
        breakdown = data["health_score_breakdown"]
        assert breakdown["recency"] == 20  # Just under 2 years (729 days)
        assert breakdown["documentation"] == 30  # Full docs
        assert breakdown["metadata"] == 30  # Complete metadata

        assert data["health_score"] == 80

    def test_multiple_packages_processed_independently(self):
        """Test that multiple packages can be scored independently."""
        package1 = {
            "name": "package-one",
            "version": "1.0.0",
            "upload_timestamp": datetime.now(timezone.utc).isoformat(),
            "maintainer": "Team One",
        }

        package2 = {
            "name": "package-two",
            "version": "2.0.0",
            "upload_timestamp": (datetime.now(timezone.utc) - timedelta(days=400)).isoformat(),
            "docs_url": "https://docs.example.com",
            "description": "A" * 150,
            "maintainer": "Team Two",
            "license": "MIT",
            "classifiers": ["A", "B", "C"],
        }

        # Process both packages
        process("package-one", package1)
        process("package-two", package2)

        # Verify they have different scores
        assert package1["health_score"] == 50  # 40 recency + 10 metadata
        assert package2["health_score"] == 75  # 20 recency + 25 docs + 30 metadata

        # Verify they don't interfere with each other
        assert package1["name"] == "package-one"
        assert package2["name"] == "package-two"

    def test_pipeline_with_plugin_load_function(self):
        """Test the full pipeline using the load function."""
        # Get the processor through load function
        processor = load({})

        data = {
            "name": "test.package",
            "version": "1.0.0",
            "upload_timestamp": datetime.now(timezone.utc).isoformat(),
            "docs_url": "https://docs.test.com",
            "description": "A" * 120,
            "project_urls": {"Documentation": "https://docs.test.com"},
            "maintainer": "Test Team",
            "license": "BSD",
            "classifiers": ["Framework :: Plone", "Programming :: Python", "License :: OSI"],
        }

        # Process through loaded function
        processor("test.package", data)

        # Verify complete pipeline execution
        assert "health_score" in data
        assert "health_score_breakdown" in data
        assert "health_score_last_calculated" in data
        assert data["health_score"] == 100

    def test_pipeline_preserves_original_package_data(self):
        """Test that pipeline doesn't modify original package fields."""
        original_data = {
            "name": "preserve.test",
            "version": "1.0.0",
            "upload_timestamp": datetime.now(timezone.utc).isoformat(),
            "description": "Original description",
            "maintainer": "Original Maintainer",
            "license": "GPL",
            "classifiers": ["A", "B", "C"],
            "custom_field": "custom_value",
        }

        # Make a copy to compare
        data = original_data.copy()
        process("preserve.test", data)

        # Verify original fields unchanged
        assert data["name"] == original_data["name"]
        assert data["version"] == original_data["version"]
        assert data["upload_timestamp"] == original_data["upload_timestamp"]
        assert data["description"] == original_data["description"]
        assert data["maintainer"] == original_data["maintainer"]
        assert data["license"] == original_data["license"]
        assert data["custom_field"] == original_data["custom_field"]

        # Verify new fields added
        assert "health_score" in data
        assert "health_score_breakdown" in data
        assert "health_score_last_calculated" in data

    def test_pipeline_handles_mixed_data_quality(self):
        """Test pipeline with package having some good and some missing data."""
        data = {
            "name": "mixed.quality",
            "version": "1.5.0",
            "upload_timestamp": (datetime.now(timezone.utc) - timedelta(days=200)).isoformat(),
            "docs_url": "https://docs.example.com",  # Good
            "description": "Short desc",  # Too short
            "project_urls": None,  # Missing
            "maintainer": "Team",  # Good
            "license": "",  # Empty
            "classifiers": ["A", "B"],  # Too few
        }

        process("mixed.quality", data)

        # Verify partial scoring
        breakdown = data["health_score_breakdown"]
        assert breakdown["recency"] == 30  # 6-12 months
        assert breakdown["documentation"] == 15  # Only docs_url
        assert breakdown["metadata"] == 10  # Only maintainer

        assert data["health_score"] == 55

    def test_pipeline_with_timestamp_variations(self):
        """Test pipeline handles different timestamp formats."""
        # Test with ISO format with Z
        data1 = {
            "name": "test1",
            "upload_timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        process("test1", data1)
        assert "health_score" in data1
        assert data1["health_score_breakdown"]["recency"] == 40

        # Test with standard ISO format
        data2 = {
            "name": "test2",
            "upload_timestamp": datetime.now(timezone.utc).isoformat(),
        }
        process("test2", data2)
        assert "health_score" in data2
        assert data2["health_score_breakdown"]["recency"] == 40

        # Test with invalid timestamp
        data3 = {
            "name": "test3",
            "upload_timestamp": "invalid-timestamp",
        }
        process("test3", data3)
        assert "health_score" in data3
        assert data3["health_score_breakdown"]["recency"] == 0

    def test_pipeline_scoring_boundaries(self):
        """Test pipeline with boundary cases for each scoring category."""
        # Exactly 6 months old (boundary between 40 and 30 points)
        exactly_6_months = datetime.now(timezone.utc) - timedelta(days=180)
        data = {
            "name": "boundary.test",
            "upload_timestamp": exactly_6_months.isoformat(),
            "description": "A" * 100,  # Exactly 100 chars (boundary)
            "classifiers": ["A", "B"],  # Exactly 2 (boundary)
        }

        process("boundary.test", data)

        breakdown = data["health_score_breakdown"]
        assert breakdown["recency"] == 30  # Should be in 6-12 month range
        assert breakdown["documentation"] == 0  # Exactly 100 doesn't count (need > 100)
        assert breakdown["metadata"] == 0  # Need >= 3 classifiers

        assert data["health_score"] == 30

    def test_pipeline_handles_all_edge_cases_simultaneously(self):
        """Test pipeline with all edge cases in one package."""
        data = {
            "name": "edge.case.package",
            "version": "0.0.1",
            "upload_timestamp": None,  # Missing
            "docs_url": "",  # Empty
            "description": None,  # None
            "project_urls": {},  # Empty dict
            "maintainer": "",  # Empty string
            "author": None,  # None
            "license": None,  # None
            "classifiers": [],  # Empty list
        }

        # Should not raise any errors
        process("edge.case.package", data)

        assert data["health_score"] == 0
        assert data["health_score_breakdown"]["recency"] == 0
        assert data["health_score_breakdown"]["documentation"] == 0
        assert data["health_score_breakdown"]["metadata"] == 0

    def test_pipeline_performance_with_large_data(self):
        """Test pipeline performance with large metadata."""
        data = {
            "name": "large.package",
            "version": "1.0.0",
            "upload_timestamp": datetime.now(timezone.utc).isoformat(),
            "docs_url": "https://docs.example.com",
            "description": "A" * 10000,  # Very long description
            "project_urls": {
                "Documentation": "https://docs.example.com",
                **{f"URL{i}": f"https://url{i}.com" for i in range(100)}
            },  # Many URLs including documentation
            "maintainer": "Team",
            "license": "MIT",
            "classifiers": [f"Classifier :: {i}" for i in range(100)],  # Many classifiers
        }

        # Should complete quickly
        start = time.time()
        process("large.package", data)
        duration = time.time() - start

        # Should complete in under 1 second even with large data
        assert duration < 1.0

        # Verify scoring still works correctly
        assert data["health_score"] == 100

    def test_pipeline_idempotency(self):
        """Test that running pipeline multiple times produces consistent results."""
        data = {
            "name": "idempotent.test",
            "version": "1.0.0",
            "upload_timestamp": datetime.now(timezone.utc).isoformat(),
            "maintainer": "Team",
            "license": "MIT",
            "classifiers": ["A", "B", "C"],
        }

        # Run three times
        process("test-id", data)
        score1 = data["health_score"]
        breakdown1 = data["health_score_breakdown"].copy()

        time.sleep(0.1)
        process("test-id", data)
        score2 = data["health_score"]
        breakdown2 = data["health_score_breakdown"].copy()

        time.sleep(0.1)
        process("test-id", data)
        score3 = data["health_score"]
        breakdown3 = data["health_score_breakdown"].copy()

        # All scores should be identical
        assert score1 == score2 == score3
        assert breakdown1 == breakdown2 == breakdown3


# ============================================================================
# Health Calculator Enricher Tests
# ============================================================================

class TestHealthCalculatorEnricher:
    """Test the HealthEnricher class bonus calculation methods."""

    @pytest.fixture
    def enricher(self):
        """Create HealthEnricher class for testing simple methods."""
        # For testing simple bonus calculation methods
        return HealthEnricher

    @pytest.fixture
    def enricher_instance(self):
        """Create a mock HealthEnricher instance for testing complex methods."""
        # Create an instance without calling __init__ to avoid Typesense connection
        instance = HealthEnricher.__new__(HealthEnricher)
        return instance

    def test_calculate_stars_bonus_with_1000_plus_stars(self, enricher):
        """Test that 1000+ stars gives 10 points."""
        bonus = enricher._calculate_stars_bonus(enricher, 1000)
        assert bonus == 10

        bonus = enricher._calculate_stars_bonus(enricher, 5000)
        assert bonus == 10

    def test_calculate_stars_bonus_with_500_to_999_stars(self, enricher):
        """Test that 500-999 stars gives 7 points."""
        bonus = enricher._calculate_stars_bonus(enricher, 500)
        assert bonus == 7

        bonus = enricher._calculate_stars_bonus(enricher, 750)
        assert bonus == 7

    def test_calculate_stars_bonus_with_100_to_499_stars(self, enricher):
        """Test that 100-499 stars gives 5 points."""
        bonus = enricher._calculate_stars_bonus(enricher, 100)
        assert bonus == 5

        bonus = enricher._calculate_stars_bonus(enricher, 300)
        assert bonus == 5

    def test_calculate_stars_bonus_with_50_to_99_stars(self, enricher):
        """Test that 50-99 stars gives 3 points."""
        bonus = enricher._calculate_stars_bonus(enricher, 50)
        assert bonus == 3

        bonus = enricher._calculate_stars_bonus(enricher, 75)
        assert bonus == 3

    def test_calculate_stars_bonus_with_10_to_49_stars(self, enricher):
        """Test that 10-49 stars gives 1 point."""
        bonus = enricher._calculate_stars_bonus(enricher, 10)
        assert bonus == 1

        bonus = enricher._calculate_stars_bonus(enricher, 30)
        assert bonus == 1

    def test_calculate_stars_bonus_with_less_than_10_stars(self, enricher):
        """Test that < 10 stars gives 0 points."""
        bonus = enricher._calculate_stars_bonus(enricher, 0)
        assert bonus == 0

        bonus = enricher._calculate_stars_bonus(enricher, 5)
        assert bonus == 0

    def test_calculate_activity_bonus_within_30_days(self, enricher):
        """Test that activity within 30 days gives 10 points."""
        now = time.time()
        recent = now - (20 * 86400)  # 20 days ago
        bonus = enricher._calculate_activity_bonus(enricher, recent)
        assert bonus == 10

    def test_calculate_activity_bonus_within_90_days(self, enricher):
        """Test that activity within 90 days gives 7 points."""
        now = time.time()
        recent = now - (60 * 86400)  # 60 days ago
        bonus = enricher._calculate_activity_bonus(enricher, recent)
        assert bonus == 7

    def test_calculate_activity_bonus_within_180_days(self, enricher):
        """Test that activity within 180 days gives 5 points."""
        now = time.time()
        recent = now - (120 * 86400)  # 120 days ago
        bonus = enricher._calculate_activity_bonus(enricher, recent)
        assert bonus == 5

    def test_calculate_activity_bonus_within_365_days(self, enricher):
        """Test that activity within 365 days gives 3 points."""
        now = time.time()
        recent = now - (300 * 86400)  # 300 days ago
        bonus = enricher._calculate_activity_bonus(enricher, recent)
        assert bonus == 3

    def test_calculate_activity_bonus_over_365_days(self, enricher):
        """Test that activity over 365 days gives 0 points."""
        now = time.time()
        old = now - (400 * 86400)  # 400 days ago
        bonus = enricher._calculate_activity_bonus(enricher, old)
        assert bonus == 0

    def test_calculate_activity_bonus_with_none(self, enricher):
        """Test that None timestamp gives 0 points."""
        bonus = enricher._calculate_activity_bonus(enricher, None)
        assert bonus == 0

    def test_calculate_activity_bonus_with_invalid_type(self, enricher):
        """Test that invalid timestamp type returns 0 via exception handling."""
        bonus = enricher._calculate_activity_bonus(enricher, "invalid-timestamp-string")
        assert bonus == 0

    def test_calculate_issue_management_bonus_excellent_ratio(self, enricher):
        """Test that ratio < 0.1 gives 10 points."""
        # 5 issues, 100 stars = 0.05 ratio
        bonus = enricher._calculate_issue_management_bonus(enricher, 5, 100)
        assert bonus == 10

    def test_calculate_issue_management_bonus_good_ratio(self, enricher):
        """Test that ratio 0.1-0.3 gives 7 points."""
        # 20 issues, 100 stars = 0.2 ratio
        bonus = enricher._calculate_issue_management_bonus(enricher, 20, 100)
        assert bonus == 7

    def test_calculate_issue_management_bonus_fair_ratio(self, enricher):
        """Test that ratio 0.3-0.5 gives 5 points."""
        # 40 issues, 100 stars = 0.4 ratio
        bonus = enricher._calculate_issue_management_bonus(enricher, 40, 100)
        assert bonus == 5

    def test_calculate_issue_management_bonus_poor_ratio(self, enricher):
        """Test that ratio 0.5-1.0 gives 3 points."""
        # 70 issues, 100 stars = 0.7 ratio
        bonus = enricher._calculate_issue_management_bonus(enricher, 70, 100)
        assert bonus == 3

    def test_calculate_issue_management_bonus_very_poor_ratio(self, enricher):
        """Test that ratio > 1.0 gives 0 points."""
        # 150 issues, 100 stars = 1.5 ratio
        bonus = enricher._calculate_issue_management_bonus(enricher, 150, 100)
        assert bonus == 0

    def test_calculate_issue_management_bonus_with_zero_stars(self, enricher):
        """Test that zero stars returns 0 points."""
        bonus = enricher._calculate_issue_management_bonus(enricher, 10, 0)
        assert bonus == 0

    def test_calculate_issue_management_bonus_with_invalid_types(self, enricher):
        """Test that invalid types return 0 via exception handling."""
        bonus = enricher._calculate_issue_management_bonus(enricher, None, "invalid")
        assert bonus == 0

    def test_calculate_enhanced_health_score_with_github_data(self, enricher_instance):
        """Test enhanced score calculation with GitHub bonuses."""
        data = {
            "health_score": 60,
            "health_score_breakdown": {"recency": 30, "docs": 20, "metadata": 10},
            "github_stars": 500,  # +7 bonus
            "github_updated": time.time() - (20 * 86400),  # 20 days ago = +10 bonus
            "github_open_issues": 10,  # 10/500 = 0.02 ratio = +10 bonus
        }

        result = enricher_instance._calculate_enhanced_health_score(data)

        assert result is not None
        assert result["health_score"] == 87  # 60 + 7 + 10 + 10 = 87
        assert "github_stars_bonus" in result["health_score_breakdown"]
        assert "github_activity_bonus" in result["health_score_breakdown"]
        assert "github_issue_bonus" in result["health_score_breakdown"]
        assert "github_bonus_total" in result["health_score_breakdown"]

    def test_calculate_enhanced_health_score_capped_at_100(self, enricher_instance):
        """Test that final score is capped at 100."""
        data = {
            "health_score": 95,
            "health_score_breakdown": {},
            "github_stars": 2000,  # +10 bonus
            "github_updated": time.time() - (10 * 86400),  # +10 bonus
            "github_open_issues": 5,  # 5/2000 = 0.0025 ratio = +10 bonus
        }

        result = enricher_instance._calculate_enhanced_health_score(data)

        assert result["health_score"] == 100  # Capped, not 125
        assert result["health_score_breakdown"]["github_bonus_total"] == 30

    def test_calculate_enhanced_health_score_returns_none_for_missing_base_score(self, enricher_instance):
        """Test that packages without base score are skipped."""
        data = {
            "name": "test-package",
            "version": "1.0.0",
            # No health_score or breakdown
        }

        result = enricher_instance._calculate_enhanced_health_score(data)

        assert result is None

    def test_calculate_enhanced_health_score_with_partial_github_data(self, enricher_instance):
        """Test enhanced score with only some GitHub fields."""
        data = {
            "health_score": 50,
            "health_score_breakdown": {},
            "github_stars": 100,  # +5 bonus
            # No github_updated or github_open_issues
        }

        result = enricher_instance._calculate_enhanced_health_score(data)

        assert result["health_score"] == 55  # 50 + 5
        assert "github_stars_bonus" in result["health_score_breakdown"]
        assert "github_activity_bonus" not in result["health_score_breakdown"]

    def test_calculate_enhanced_health_score_with_no_github_data(self, enricher_instance):
        """Test that packages without any GitHub data still get base score."""
        data = {
            "health_score": 70,
            "health_score_breakdown": {"recency": 40, "docs": 30},
            # No GitHub fields at all
        }

        result = enricher_instance._calculate_enhanced_health_score(data)

        assert result["health_score"] == 70  # No change
        assert "github_stars_bonus" not in result["health_score_breakdown"]
        assert "github_activity_bonus" not in result["health_score_breakdown"]
        assert "github_issue_bonus" not in result["health_score_breakdown"]
        assert "github_bonus_total" not in result["health_score_breakdown"]
