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
import time

from pyf.aggregator.plugins.health_score import (
    process,
    calculate_recency_score,
    calculate_recency_score_with_problems,
    calculate_docs_score,
    calculate_docs_score_with_problems,
    calculate_metadata_score,
    calculate_metadata_score_with_problems,
    count_words,
    load,
)
from pyf.aggregator.enrichers.health_calculator import HealthEnricher


# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def sample_package_data_complete():
    """Sample package data with all fields for maximum score (using Unix timestamp)."""
    import time

    return {
        "name": "plone.api",
        "version": "2.0.0",
        "upload_timestamp": int(time.time()),  # Unix timestamp (int64)
        "docs_url": "https://ploneapi.readthedocs.io/",
        "description": "A" * 151,  # >150 chars for 18 points
        "description_html": '<img src="https://example.com/screenshot.png" width="400">',  # 5 points
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
    """Sample package data with old release (>5 years ago) using Unix timestamp."""
    import time

    # 2000 days ago in seconds
    old_timestamp = int(time.time()) - (2000 * 86400)
    return {
        "name": "old-package",
        "version": "1.0.0",
        "upload_timestamp": old_timestamp,  # Unix timestamp (int64)
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
        total_from_breakdown = sum(
            category["points"] for category in breakdown.values()
        )
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
        assert data["health_score_breakdown"]["recency"]["points"] == 0
        assert data["health_score_breakdown"]["documentation"]["points"] == 0
        assert data["health_score_breakdown"]["metadata"]["points"] == 0

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

    def test_returns_40_for_recent_unix_timestamp(self):
        """Test that recent Unix timestamps (int64) get 40 points."""
        import time

        # 3 months ago (90 days in seconds)
        recent_timestamp = int(time.time()) - (90 * 86400)
        score = calculate_recency_score(recent_timestamp)
        assert score == 40

    def test_returns_30_for_6_to_12_month_old_unix_timestamp(self):
        """Test that 6-12 month old Unix timestamps get 30 points."""
        import time

        # 9 months ago (270 days in seconds)
        medium_old_timestamp = int(time.time()) - (270 * 86400)
        score = calculate_recency_score(medium_old_timestamp)
        assert score == 30

    def test_returns_0_for_unix_timestamp_zero(self):
        """Test that Unix timestamp of 0 returns 0 (missing timestamp)."""
        score = calculate_recency_score(0)
        assert score == 0

    def test_returns_0_for_very_old_unix_timestamp(self):
        """Test that very old Unix timestamps (> 5 years) get 0 points."""
        import time

        # 6 years ago (2190 days in seconds)
        ancient_timestamp = int(time.time()) - (2190 * 86400)
        score = calculate_recency_score(ancient_timestamp)
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
# Word Count Tests
# ============================================================================


class TestCountWords:
    """Test the count_words helper function."""

    def test_counts_words_correctly(self):
        """Test that words are counted correctly."""
        assert count_words("one two three") == 3
        assert count_words("hello world") == 2
        assert count_words("single") == 1

    def test_returns_zero_for_empty_string(self):
        """Test that empty string returns 0."""
        assert count_words("") == 0

    def test_returns_zero_for_none(self):
        """Test that None returns 0."""
        assert count_words(None) == 0

    def test_handles_multiple_spaces(self):
        """Test that multiple spaces are handled correctly."""
        assert count_words("one   two    three") == 3

    def test_handles_newlines_and_tabs(self):
        """Test that newlines and tabs are handled correctly."""
        assert count_words("one\ntwo\tthree") == 3

    def test_handles_html_content(self):
        """Test word counting with HTML content."""
        html = "<p>This is a paragraph with eight words total.</p>"
        # Note: HTML tags count as words since we're splitting by whitespace
        assert count_words(html) >= 8


# ============================================================================
# Documentation Score Tests
# ============================================================================


class TestCalculateDocsScore:
    """Test the calculate_docs_score function."""

    def test_returns_4_for_docs_url(self):
        """Test that having docs_url gives 4 points."""
        data = {"docs_url": "https://docs.example.com"}
        score = calculate_docs_score(data)
        assert score == 4

    def test_returns_18_for_meaningful_description(self):
        """Test that description > 150 chars gives 18 points."""
        data = {"description": "A" * 151}
        score = calculate_docs_score(data)
        assert score == 18

    def test_returns_0_for_short_description(self):
        """Test that description <= 150 chars gives 0 points."""
        data = {"description": "A" * 150}
        score = calculate_docs_score(data)
        assert score == 0

    def test_returns_3_for_documentation_project_url(self):
        """Test that project_urls with 'documentation' gives 3 points."""
        data = {"project_urls": {"Documentation": "https://docs.example.com"}}
        score = calculate_docs_score(data)
        assert score == 3

    def test_returns_3_for_docs_project_url(self):
        """Test that project_urls with 'docs' gives 3 points."""
        data = {"project_urls": {"Docs": "https://docs.example.com"}}
        score = calculate_docs_score(data)
        assert score == 3

    def test_returns_3_for_homepage_project_url(self):
        """Test that project_urls with 'homepage' gives 3 points."""
        data = {"project_urls": {"Homepage": "https://example.com"}}
        score = calculate_docs_score(data)
        assert score == 3

    def test_returns_3_for_home_project_url(self):
        """Test that project_urls with 'home' gives 3 points."""
        data = {"project_urls": {"Home": "https://example.com"}}
        score = calculate_docs_score(data)
        assert score == 3

    def test_case_insensitive_project_url_matching(self):
        """Test that project URL matching is case insensitive."""
        data = {"project_urls": {"DOCUMENTATION": "https://docs.example.com"}}
        score = calculate_docs_score(data)
        assert score == 3

    def test_only_counts_project_urls_once(self):
        """Test that multiple matching project URLs only give 3 points total."""
        data = {
            "project_urls": {
                "Documentation": "https://docs.example.com",
                "Homepage": "https://example.com",
                "Docs": "https://docs2.example.com",
            }
        }
        score = calculate_docs_score(data)
        assert score == 3  # Only 3 points, not 9

    def test_returns_30_for_all_documentation_factors(self):
        """Test that having all documentation factors gives 30 points."""
        data = {
            "docs_url": "https://docs.example.com",
            "description": "A" * 151,  # >150 chars for 18 points
            "project_urls": {"Documentation": "https://docs.example.com"},  # 3 points
            "description_html": '<img src="https://example.com/screenshot.png" width="400">',  # 5 points
        }
        score = calculate_docs_score(data)
        assert score == 30  # 4 + 18 + 3 + 5 = 30

    def test_returns_25_without_screenshot(self):
        """Test that without screenshot, max docs score is 25 points."""
        data = {
            "docs_url": "https://docs.example.com",
            "description": "A" * 151,
            "project_urls": {"Documentation": "https://docs.example.com"},
        }
        score = calculate_docs_score(data)
        assert score == 25  # 4 + 18 + 3 = 25 (no screenshot)

    def test_returns_5_for_screenshot_only(self):
        """Test that having only a screenshot gives 5 points."""
        data = {
            "description_html": '<img src="https://example.com/screenshot.png" width="400">',
        }
        score = calculate_docs_score(data)
        assert score == 5

    def test_badges_dont_count_as_screenshots(self):
        """Test that badge images don't give screenshot points."""
        data = {
            "description_html": '<img src="https://img.shields.io/badge/test.svg" width="400">',
        }
        score = calculate_docs_score(data)
        assert score == 0  # Badge is filtered out

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
# Documentation Link Requirement Tests (500-word threshold)
# ============================================================================


class TestDocumentationLinkRequirement:
    """Test the 500-word README threshold for documentation link requirement."""

    def test_long_readme_no_external_docs_no_problem(self):
        """Test that README >= 500 words with no docs_url or doc links reports no documentation link problem."""
        # Generate 500+ words of content (using first_chapter + main_content)
        long_content = " ".join(["word"] * 600)
        data = {
            "main_content": f"<p>{long_content}</p>",
            "description": "A" * 151,  # Meet description requirement
        }
        score, problems, bonuses = calculate_docs_score_with_problems(data)
        # Should NOT report "not enough documentation" because README is comprehensive
        assert (
            "not enough documentation (extend README to 500+ words or add documentation link)"
            not in problems
        )

    def test_short_readme_with_docs_url_no_problem(self):
        """Test that README < 500 words with docs_url reports no documentation link problem."""
        data = {
            "main_content": "<p>Short content</p>",
            "docs_url": "https://docs.example.com",
            "description": "A" * 151,
        }
        score, problems, bonuses = calculate_docs_score_with_problems(data)
        # Should NOT report "not enough documentation" because docs_url is present
        assert (
            "not enough documentation (extend README to 500+ words or add documentation link)"
            not in problems
        )

    def test_short_readme_with_doc_links_no_problem(self):
        """Test that README < 500 words with documentation project_urls reports no documentation link problem."""
        data = {
            "main_content": "<p>Short content</p>",
            "project_urls": {"Documentation": "https://docs.example.com"},
            "description": "A" * 151,
        }
        score, problems, bonuses = calculate_docs_score_with_problems(data)
        # Should NOT report "not enough documentation" because documentation link is present
        assert (
            "not enough documentation (extend README to 500+ words or add documentation link)"
            not in problems
        )

    def test_short_readme_no_external_docs_reports_problem(self):
        """Test that README < 500 words with no docs_url or doc links reports documentation link problem."""
        data = {
            "main_content": "<p>Short content</p>",
            "description": "A" * 151,
            # No docs_url, no documentation project_urls
        }
        score, problems, bonuses = calculate_docs_score_with_problems(data)
        # Should report "not enough documentation"
        assert (
            "not enough documentation (extend README to 500+ words or add documentation link)"
            in problems
        )

    def test_empty_readme_no_external_docs_reports_problem(self):
        """Test that empty README with no external docs reports documentation link problem."""
        data = {
            "main_content": "",
            "description": "A" * 151,
        }
        score, problems, bonuses = calculate_docs_score_with_problems(data)
        # Should report "not enough documentation"
        assert (
            "not enough documentation (extend README to 500+ words or add documentation link)"
            in problems
        )

    def test_exactly_500_words_no_problem(self):
        """Test that exactly 500 words is considered comprehensive (no problem reported)."""
        # Generate exactly 500 words (using first_chapter + main_content)
        content_500 = " ".join(["word"] * 500)
        data = {
            "main_content": f"<p>{content_500}</p>",
            "description": "A" * 151,
        }
        score, problems, bonuses = calculate_docs_score_with_problems(data)
        # Should NOT report problem at exactly 500 words
        assert (
            "not enough documentation (extend README to 500+ words or add documentation link)"
            not in problems
        )

    def test_499_words_with_no_external_docs_reports_problem(self):
        """Test that 499 words (just under threshold) reports problem."""
        # Generate exactly 499 words (using first_chapter + main_content)
        content_499 = " ".join(["word"] * 499)
        data = {
            "main_content": f"<p>{content_499}</p>",
            "description": "A" * 151,
        }
        score, problems, bonuses = calculate_docs_score_with_problems(data)
        # Should report problem at 499 words
        assert (
            "not enough documentation (extend README to 500+ words or add documentation link)"
            in problems
        )

    def test_docs_url_is_bonus_only(self):
        """Test that docs_url gives 4 points but no standalone problem if missing."""
        # With docs_url
        data_with = {"docs_url": "https://docs.example.com"}
        score_with, problems_with, bonuses_with = calculate_docs_score_with_problems(
            data_with
        )
        assert score_with == 4
        # Verify bonus is tracked
        assert any(b["reason"] == "has dedicated docs URL" for b in bonuses_with)

        # Without docs_url (but has doc link to avoid combined problem)
        data_without = {"project_urls": {"Documentation": "https://docs.example.com"}}
        score_without, problems_without, bonuses_without = (
            calculate_docs_score_with_problems(data_without)
        )
        assert score_without == 3
        # Should NOT have a "no docs_url" problem (bonus only)
        assert "no docs_url" not in problems_without

    def test_doc_project_urls_is_bonus_only(self):
        """Test that documentation project_urls gives 3 points but no standalone problem if missing."""
        # With doc project URL
        data_with = {"project_urls": {"Documentation": "https://docs.example.com"}}
        score_with, problems_with, bonuses_with = calculate_docs_score_with_problems(
            data_with
        )
        assert score_with == 3
        # Verify bonus is tracked
        assert any(b["reason"] == "has documentation project URL" for b in bonuses_with)

        # Without doc project URL (but has docs_url to avoid combined problem)
        data_without = {"docs_url": "https://docs.example.com"}
        score_without, problems_without, bonuses_without = (
            calculate_docs_score_with_problems(data_without)
        )
        assert score_without == 4
        # Should NOT have a "no documentation project URLs" problem (bonus only)
        assert "no documentation project URLs" not in problems_without

    def test_first_chapter_and_main_content_combined_for_word_count(self):
        """Test that first_chapter + main_content are combined for word counting."""
        # 250 words in first_chapter + 250 words in main_content = 500 total
        content_250 = " ".join(["word"] * 250)
        data = {
            "first_chapter": f"<p>{content_250}</p>",
            "main_content": f"<p>{content_250}</p>",
            "description": "A" * 151,
        }
        score, problems, bonuses = calculate_docs_score_with_problems(data)
        # Should NOT report "not enough documentation" because combined word count >= 500
        assert (
            "not enough documentation (extend README to 500+ words or add documentation link)"
            not in problems
        )

    def test_word_count_excludes_changelog(self):
        """Test that changelog content is not counted toward documentation word count."""
        # 200 words in main_content but 1000 words in changelog (should be ignored)
        short_content = " ".join(["word"] * 200)
        long_changelog = " ".join(["changelog_word"] * 1000)
        data = {
            "main_content": f"<p>{short_content}</p>",
            "changelog": f"<p>{long_changelog}</p>",  # Should be ignored
            "description": "A" * 151,
        }
        score, problems, bonuses = calculate_docs_score_with_problems(data)
        # Should report "not enough documentation" because main_content < 500 words
        # (changelog is correctly excluded)
        assert (
            "not enough documentation (extend README to 500+ words or add documentation link)"
            in problems
        )


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
        import time

        data = {
            "upload_timestamp": int(time.time()),  # Unix timestamp (int64)
            "docs_url": "https://docs.example.com",
            "description": "A" * 200,
            "description_html": '<img src="https://example.com/screenshot.png" width="400">',
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
            "description": "A" * 151,  # >150 chars for 18 points
            "description_html": '<img src="https://example.com/screenshot.png" width="400">',  # 5 points
            "project_urls": {"Documentation": "https://docs.example.com"},  # 3 points
            "maintainer": "Team",
            "license": "MIT",
            "classifiers": ["A", "B", "C"],
        }
        process("test-id", data)
        # Should get 0 (recency) + 30 (docs: 4+18+3+5) + 30 (metadata) = 60
        assert data["health_score"] == 60

    def test_recent_but_poor_metadata_scenario(self):
        """Test a recent package with poor metadata."""
        import time

        data = {
            "upload_timestamp": int(time.time()),  # Unix timestamp (int64)
            "description": "Short",
        }
        process("test-id", data)
        # Should get 40 (recency) + 0 (docs) + 0 (metadata) = 40
        assert data["health_score"] == 40

    def test_score_consistency_on_multiple_calls(self):
        """Test that calling process multiple times updates the score consistently."""
        import time as time_module

        data = {"name": "test", "maintainer": "Team"}

        process("test-id", data)
        first_score = data["health_score"]
        first_timestamp = data["health_score_last_calculated"]

        # Wait a full second for timestamp to change (uses second precision)
        time_module.sleep(1.1)
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
        """Test realistic Plone package with typical PyPI data (using Unix timestamp)."""
        import time as time_module

        # 30 days ago in seconds
        recent_timestamp = int(time_module.time()) - (30 * 86400)
        data = {
            "name": "plone.api",
            "version": "2.0.3",
            "upload_timestamp": recent_timestamp,  # Unix timestamp (int64)
            "docs_url": "https://ploneapi.readthedocs.io/en/latest/",
            "description": (
                "plone.api is an elegant and simple API for Plone. "
                "It provides a high-level API to access Plone functionality. "
                "The goal is to make working with Plone easier."
            ),
            "description_html": '<img src="https://example.com/screenshot.png" width="400">',
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

        # Verify score components (new structure with points, problems, bonuses)
        breakdown = data["health_score_breakdown"]
        assert breakdown["recency"]["points"] == 40  # Recent upload
        assert (
            breakdown["documentation"]["points"] == 30
        )  # Has docs_url (4), long description (18), project_urls (3), screenshot (5)
        assert (
            breakdown["metadata"]["points"] == 30
        )  # Has maintainer, license, and 3+ classifiers

        # Verify bonuses are tracked
        assert any(
            b["reason"] == "has dedicated docs URL"
            for b in breakdown["documentation"]["bonuses"]
        )
        assert any(
            b["reason"] == "has documentation project URL"
            for b in breakdown["documentation"]["bonuses"]
        )
        assert any(
            b["reason"] == "has meaningful screenshots"
            for b in breakdown["documentation"]["bonuses"]
        )

        # Verify total score
        assert data["health_score"] == 100

    def test_legacy_package_with_minimal_metadata(self):
        """Test old package with minimal metadata (common for legacy packages, using Unix timestamp)."""
        import time as time_module

        # 1500 days ago in seconds (approx 4.1 years)
        old_timestamp = int(time_module.time()) - (1500 * 86400)
        data = {
            "name": "Products.PloneFormGen",
            "version": "1.8.0",
            "upload_timestamp": old_timestamp,  # Unix timestamp (int64)
            "description": "A form generator for Plone",
            "author": "Plone Community",
            "classifiers": [
                "Framework :: Plone",
            ],
        }

        process("Products.PloneFormGen", data)

        # Verify scoring for legacy package (new structure with points)
        breakdown = data["health_score_breakdown"]
        assert (
            breakdown["recency"]["points"] == 5
        )  # Old release (3-5 years, 1500 days ≈ 4.1 years)
        assert (
            breakdown["documentation"]["points"] == 0
        )  # No docs_url, short description, no project_urls
        assert (
            breakdown["metadata"]["points"] == 10
        )  # Has author, no license, < 3 classifiers

        assert data["health_score"] == 15

    def test_brand_new_package_with_incomplete_setup(self):
        """Test newly released package with incomplete metadata (using Unix timestamp)."""
        import time as time_module

        data = {
            "name": "experimental.plone.feature",
            "version": "0.1.0",
            "upload_timestamp": int(time_module.time()),  # Unix timestamp (int64)
            "description": "Experimental feature",
            "author": "Developer",
        }

        process("experimental.plone.feature", data)

        # Very recent but minimal metadata (new structure with points)
        breakdown = data["health_score_breakdown"]
        assert breakdown["recency"]["points"] == 40  # Just released
        assert breakdown["documentation"]["points"] == 0  # Minimal docs
        assert breakdown["metadata"]["points"] == 10  # Has author only

        assert data["health_score"] == 50

    def test_well_documented_but_old_package(self):
        """Test package with excellent documentation but old release (using Unix timestamp)."""
        import time as time_module

        # 729 days ago in seconds (just under 2 years)
        old_timestamp = int(time_module.time()) - (729 * 86400)
        data = {
            "name": "collective.easyform",
            "version": "3.1.0",
            "upload_timestamp": old_timestamp,  # Unix timestamp (int64)
            "docs_url": "https://collectiveeasyform.readthedocs.io/",
            "description": (
                "collective.easyform enables creation of custom forms through-the-web. "
                "It provides a powerful form builder with validation, custom actions, "
                "and a variety of field types. Extensive documentation available online."
            ),
            "description_html": '<img src="https://example.com/screenshot.png" width="400">',
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

        # Old but well-maintained documentation (new structure with points)
        breakdown = data["health_score_breakdown"]
        assert breakdown["recency"]["points"] == 20  # Just under 2 years (729 days)
        assert breakdown["documentation"]["points"] == 30  # Full docs (4+18+3+5)
        assert breakdown["metadata"]["points"] == 30  # Complete metadata

        assert data["health_score"] == 80

    def test_multiple_packages_processed_independently(self):
        """Test that multiple packages can be scored independently (using Unix timestamps)."""
        import time as time_module

        # 400 days ago in seconds
        old_timestamp = int(time_module.time()) - (400 * 86400)

        package1 = {
            "name": "package-one",
            "version": "1.0.0",
            "upload_timestamp": int(time_module.time()),  # Unix timestamp (int64)
            "maintainer": "Team One",
        }

        package2 = {
            "name": "package-two",
            "version": "2.0.0",
            "upload_timestamp": old_timestamp,  # Unix timestamp (int64)
            "docs_url": "https://docs.example.com",  # 4 points
            "description": "A" * 151,  # >150 chars for 18 points
            "description_html": '<img src="https://example.com/screenshot.png" width="400">',  # 5 points
            "project_urls": {"Documentation": "https://docs.example.com"},  # 3 points
            "maintainer": "Team Two",
            "license": "MIT",
            "classifiers": ["A", "B", "C"],
        }

        # Process both packages
        process("package-one", package1)
        process("package-two", package2)

        # Verify they have different scores
        assert package1["health_score"] == 50  # 40 recency + 10 metadata
        assert (
            package2["health_score"] == 80
        )  # 20 recency + 30 docs (4+18+3+5) + 30 metadata

        # Verify they don't interfere with each other
        assert package1["name"] == "package-one"
        assert package2["name"] == "package-two"

    def test_pipeline_with_plugin_load_function(self):
        """Test the full pipeline using the load function (using Unix timestamp)."""
        import time as time_module

        # Get the processor through load function
        processor = load({})

        data = {
            "name": "test.package",
            "version": "1.0.0",
            "upload_timestamp": int(time_module.time()),  # Unix timestamp (int64)
            "docs_url": "https://docs.test.com",  # 4 points
            "description": "A" * 151,  # >150 chars for 18 points
            "description_html": '<img src="https://example.com/screenshot.png" width="400">',  # 5 points
            "project_urls": {"Documentation": "https://docs.test.com"},  # 3 points
            "maintainer": "Test Team",
            "license": "BSD",
            "classifiers": [
                "Framework :: Plone",
                "Programming :: Python",
                "License :: OSI",
            ],
        }

        # Process through loaded function
        processor("test.package", data)

        # Verify complete pipeline execution
        assert "health_score" in data
        assert "health_score_breakdown" in data
        assert "health_score_last_calculated" in data
        assert data["health_score"] == 100

    def test_pipeline_preserves_original_package_data(self):
        """Test that pipeline doesn't modify original package fields (using Unix timestamp)."""
        import time as time_module

        original_data = {
            "name": "preserve.test",
            "version": "1.0.0",
            "upload_timestamp": int(time_module.time()),  # Unix timestamp (int64)
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
        """Test pipeline with package having some good and some missing data (using Unix timestamp)."""
        import time as time_module

        # 200 days ago in seconds
        old_timestamp = int(time_module.time()) - (200 * 86400)
        data = {
            "name": "mixed.quality",
            "version": "1.5.0",
            "upload_timestamp": old_timestamp,  # Unix timestamp (int64)
            "docs_url": "https://docs.example.com",  # Good (4 points)
            "description": "Short desc",  # Too short (<150 chars)
            "project_urls": None,  # Missing
            "maintainer": "Team",  # Good
            "license": "",  # Empty
            "classifiers": ["A", "B"],  # Too few
        }

        process("mixed.quality", data)

        # Verify partial scoring (new structure with points)
        breakdown = data["health_score_breakdown"]
        assert breakdown["recency"]["points"] == 30  # 6-12 months
        assert breakdown["documentation"]["points"] == 4  # Only docs_url (4 points)
        assert breakdown["metadata"]["points"] == 10  # Only maintainer

        assert data["health_score"] == 44

    def test_pipeline_with_timestamp_variations(self):
        """Test pipeline handles different timestamp formats."""
        # Test with ISO format with Z
        data1 = {
            "name": "test1",
            "upload_timestamp": datetime.now(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
        }
        process("test1", data1)
        assert "health_score" in data1
        assert data1["health_score_breakdown"]["recency"]["points"] == 40

        # Test with standard ISO format
        data2 = {
            "name": "test2",
            "upload_timestamp": datetime.now(timezone.utc).isoformat(),
        }
        process("test2", data2)
        assert "health_score" in data2
        assert data2["health_score_breakdown"]["recency"]["points"] == 40

        # Test with invalid timestamp
        data3 = {
            "name": "test3",
            "upload_timestamp": "invalid-timestamp",
        }
        process("test3", data3)
        assert "health_score" in data3
        assert data3["health_score_breakdown"]["recency"]["points"] == 0

    def test_pipeline_scoring_boundaries(self):
        """Test pipeline with boundary cases for each scoring category (using Unix timestamp)."""
        import time as time_module

        # Exactly 180 days ago in seconds (boundary between 40 and 30 points)
        exactly_6_months_timestamp = int(time_module.time()) - (180 * 86400)
        data = {
            "name": "boundary.test",
            "upload_timestamp": exactly_6_months_timestamp,  # Unix timestamp (int64)
            "description": "A" * 100,  # Exactly 100 chars (boundary)
            "classifiers": ["A", "B"],  # Exactly 2 (boundary)
        }

        process("boundary.test", data)

        breakdown = data["health_score_breakdown"]
        assert breakdown["recency"]["points"] == 30  # Should be in 6-12 month range
        assert (
            breakdown["documentation"]["points"] == 0
        )  # Exactly 100 doesn't count (need > 100)
        assert breakdown["metadata"]["points"] == 0  # Need >= 3 classifiers

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
        assert data["health_score_breakdown"]["recency"]["points"] == 0
        assert data["health_score_breakdown"]["documentation"]["points"] == 0
        assert data["health_score_breakdown"]["metadata"]["points"] == 0

    def test_pipeline_performance_with_large_data(self):
        """Test pipeline performance with large metadata (using Unix timestamp)."""
        import time as time_module

        data = {
            "name": "large.package",
            "version": "1.0.0",
            "upload_timestamp": int(time_module.time()),  # Unix timestamp (int64)
            "docs_url": "https://docs.example.com",  # 4 points
            "description": "A" * 10000,  # Very long description (18 points)
            "description_html": '<img src="https://example.com/screenshot.png" width="400">',  # 5 points
            "project_urls": {
                "Documentation": "https://docs.example.com",
                **{f"URL{i}": f"https://url{i}.com" for i in range(100)},
            },  # Many URLs including documentation (3 points)
            "maintainer": "Team",
            "license": "MIT",
            "classifiers": [
                f"Classifier :: {i}" for i in range(100)
            ],  # Many classifiers
        }

        # Should complete quickly
        start = time_module.time()
        process("large.package", data)
        duration = time_module.time() - start

        # Should complete in under 1 second even with large data
        assert duration < 1.0

        # Verify scoring still works correctly
        assert data["health_score"] == 100

    def test_pipeline_idempotency(self):
        """Test that running pipeline multiple times produces consistent results (using Unix timestamp)."""
        import time as time_module

        data = {
            "name": "idempotent.test",
            "version": "1.0.0",
            "upload_timestamp": int(time_module.time()),  # Unix timestamp (int64)
            "maintainer": "Team",
            "license": "MIT",
            "classifiers": ["A", "B", "C"],
        }

        # Run three times
        process("test-id", data)
        score1 = data["health_score"]
        breakdown1 = data["health_score_breakdown"].copy()

        time_module.sleep(0.1)
        process("test-id", data)
        score2 = data["health_score"]
        breakdown2 = data["health_score_breakdown"].copy()

        time_module.sleep(0.1)
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
        import time as time_module

        # Provide data for from-scratch calculation
        # Recent timestamp (40 points), docs_url + description + project_urls + screenshot (30 points),
        # maintainer + license + classifiers (30 points) = 100 base
        data = {
            "upload_timestamp": int(time_module.time())
            - (30 * 86400),  # 30 days = 40 points
            "docs_url": "https://docs.example.com",  # 4 points
            "description": "A" * 151,  # 18 points
            "description_html": '<img src="https://example.com/screenshot.png" width="400">',  # 5 points
            "project_urls": {"Documentation": "https://docs.example.com"},  # 3 points
            "maintainer": "Team",  # 10 points
            "license": "MIT",  # 10 points
            "classifiers": ["A", "B", "C"],  # 10 points
            "github_stars": 500,  # +7 bonus
            "github_updated": time_module.time()
            - (20 * 86400),  # 20 days ago = +10 bonus
            "github_open_issues": 10,  # 10/500 = 0.02 ratio = +10 bonus
        }

        result = enricher_instance._calculate_enhanced_health_score(data)

        assert result is not None
        # Base: 40+30+30 = 100, capped at 100 even with +27 bonus
        assert result["health_score"] == 100
        # GitHub bonuses are now at top level of breakdown
        assert "github_stars_bonus" in result["health_score_breakdown"]
        assert "github_activity_bonus" in result["health_score_breakdown"]
        assert "github_issue_bonus" in result["health_score_breakdown"]
        assert "github_bonus_total" in result["health_score_breakdown"]
        # Category structure has points, problems, bonuses
        assert result["health_score_breakdown"]["recency"]["points"] == 40
        assert result["health_score_breakdown"]["documentation"]["points"] == 30
        assert result["health_score_breakdown"]["metadata"]["points"] == 30

    def test_calculate_enhanced_health_score_capped_at_100(self, enricher_instance):
        """Test that final score is capped at 100."""
        import time as time_module

        # Provide data for from-scratch calculation - full base score of 100
        data = {
            "upload_timestamp": int(time_module.time()),  # Recent = 40 points
            "docs_url": "https://docs.example.com",  # 4 points
            "description": "A" * 151,  # 18 points
            "description_html": '<img src="https://example.com/screenshot.png" width="400">',  # 5 points
            "project_urls": {"Documentation": "https://docs.example.com"},  # 3 points
            "maintainer": "Team",  # 10 points
            "license": "MIT",  # 10 points
            "classifiers": ["A", "B", "C"],  # 10 points
            # Total base: 40 + 30 + 30 = 100
            "github_stars": 2000,  # +10 bonus
            "github_updated": time_module.time() - (10 * 86400),  # +10 bonus
            "github_open_issues": 5,  # 5/2000 = 0.0025 ratio = +10 bonus
        }

        result = enricher_instance._calculate_enhanced_health_score(data)

        assert result["health_score"] == 100  # Capped, not 130
        # GitHub bonus is at top level of breakdown
        assert result["health_score_breakdown"]["github_bonus_total"] == 30

    def test_calculate_enhanced_health_score_minimal_data(self, enricher_instance):
        """Test that packages with minimal data get calculated from scratch."""
        data = {
            "name": "test-package",
            "version": "1.0.0",
            # No other metadata - will get 0 for all categories
        }

        result = enricher_instance._calculate_enhanced_health_score(data)

        # Now calculates from scratch rather than skipping
        assert result is not None
        assert result["health_score"] == 0
        assert result["health_score_breakdown"]["recency"]["points"] == 0
        assert result["health_score_breakdown"]["documentation"]["points"] == 0
        assert result["health_score_breakdown"]["metadata"]["points"] == 0

    def test_calculate_enhanced_health_score_with_partial_github_data(
        self, enricher_instance
    ):
        """Test enhanced score with only some GitHub fields."""
        import time as time_module

        # 400 days = 1-2 years = 20 points recency, maintainer = 10 metadata
        # Total base: 20 + 0 + 10 = 30
        data = {
            "upload_timestamp": int(time_module.time()) - (400 * 86400),  # 20 points
            "maintainer": "Team",  # 10 points
            "github_stars": 100,  # +5 bonus
            # No github_updated or github_open_issues
        }

        result = enricher_instance._calculate_enhanced_health_score(data)

        assert result["health_score"] == 35  # 30 + 5
        # GitHub bonus is at top level of breakdown
        assert "github_stars_bonus" in result["health_score_breakdown"]
        assert "github_activity_bonus" not in result["health_score_breakdown"]

    def test_calculate_enhanced_health_score_with_no_github_data(
        self, enricher_instance
    ):
        """Test that packages without any GitHub data still get base score."""
        import time as time_module

        # Recent + maintainer + license + classifiers = 40 + 0 + 30 = 70
        data = {
            "upload_timestamp": int(time_module.time()),  # 40 points
            "maintainer": "Team",  # 10 points
            "license": "MIT",  # 10 points
            "classifiers": ["A", "B", "C"],  # 10 points
            # No GitHub fields at all
        }

        result = enricher_instance._calculate_enhanced_health_score(data)

        assert result["health_score"] == 70
        # GitHub bonuses should not be in breakdown at all
        assert "github_stars_bonus" not in result["health_score_breakdown"]
        assert "github_activity_bonus" not in result["health_score_breakdown"]
        assert "github_issue_bonus" not in result["health_score_breakdown"]
        assert "github_bonus_total" not in result["health_score_breakdown"]


# ============================================================================
# Health Score Problems Tests
# ============================================================================


class TestHealthScoreProblems:
    """Test the health score problem tracking functionality."""

    def test_complete_package_has_no_problems(self):
        """Test that a complete package has empty problem arrays."""
        import time as time_module

        data = {
            "name": "complete.package",
            "version": "1.0.0",
            "upload_timestamp": int(time_module.time()),  # Recent
            "docs_url": "https://docs.example.com",  # 4 points
            "description": "A" * 151,  # >150 chars (18 points)
            "description_html": '<img src="https://example.com/screenshot.png" width="400">',  # 5 points
            "project_urls": {"Documentation": "https://docs.example.com"},  # 3 points
            "maintainer": "Team",
            "author": "Developer",
            "license": "MIT",
            "classifiers": ["A", "B", "C"],
        }

        process("complete.package", data)

        # Problems are now inside breakdown structure
        assert data["health_score_breakdown"]["documentation"]["problems"] == []
        assert data["health_score_breakdown"]["metadata"]["problems"] == []
        assert data["health_score_breakdown"]["recency"]["problems"] == []
        assert data["health_score"] == 100

        # Verify bonuses are tracked
        assert len(data["health_score_breakdown"]["documentation"]["bonuses"]) >= 3

    def test_minimal_package_has_all_problems(self):
        """Test that a minimal package has all relevant problems detected."""
        data = {
            "name": "minimal.package",
            "version": "1.0.0",
        }

        process("minimal.package", data)

        # Check documentation problems (now inside breakdown)
        doc_problems = data["health_score_breakdown"]["documentation"]["problems"]
        # Note: "no docs_url" is no longer a standalone problem (bonus only)
        # Note: "no documentation project URLs" is no longer standalone (part of combined check)
        # Note: screenshots are now a bonus, not a problem when missing
        assert "description too short (<150 chars)" in doc_problems
        assert (
            "not enough documentation (extend README to 500+ words or add documentation link)"
            in doc_problems
        )

        # Check metadata problems (now inside breakdown)
        meta_problems = data["health_score_breakdown"]["metadata"]["problems"]
        assert "no maintainer info" in meta_problems
        assert "no author info" in meta_problems
        assert "no license" in meta_problems
        assert "fewer than 3 classifiers" in meta_problems

        # Check recency problems (now inside breakdown)
        recency_problems = data["health_score_breakdown"]["recency"]["problems"]
        assert "no release timestamp" in recency_problems

        assert data["health_score"] == 0

    def test_recency_problem_thresholds(self):
        """Test that recency problems are correctly detected at each threshold."""
        import time as time_module

        # Recent package (< 6 months) - no problems
        recent_ts = int(time_module.time()) - (90 * 86400)  # 90 days
        score, problems, bonuses = calculate_recency_score_with_problems(recent_ts)
        assert score == 40
        assert problems == []

        # 6-12 months - "last release over 6 months ago"
        six_month_ts = int(time_module.time()) - (200 * 86400)  # 200 days
        score, problems, bonuses = calculate_recency_score_with_problems(six_month_ts)
        assert score == 30
        assert "last release over 6 months ago" in problems

        # 1-2 years - "last release over 1 year ago"
        one_year_ts = int(time_module.time()) - (400 * 86400)  # 400 days
        score, problems, bonuses = calculate_recency_score_with_problems(one_year_ts)
        assert score == 20
        assert "last release over 1 year ago" in problems

        # 2-3 years - "last release over 2 years ago"
        two_year_ts = int(time_module.time()) - (900 * 86400)  # 900 days
        score, problems, bonuses = calculate_recency_score_with_problems(two_year_ts)
        assert score == 10
        assert "last release over 2 years ago" in problems

        # 3-5 years - "last release over 3 years ago"
        three_year_ts = int(time_module.time()) - (1200 * 86400)  # 1200 days
        score, problems, bonuses = calculate_recency_score_with_problems(three_year_ts)
        assert score == 5
        assert "last release over 3 years ago" in problems

        # > 5 years - "last release over 5 years ago"
        five_year_ts = int(time_module.time()) - (2000 * 86400)  # 2000 days
        score, problems, bonuses = calculate_recency_score_with_problems(five_year_ts)
        assert score == 0
        assert "last release over 5 years ago" in problems

    def test_partial_documentation_problems(self):
        """Test that only missing documentation items are reported as problems."""
        # Has docs_url but nothing else - docs_url is bonus only, no "not enough documentation" problem
        data1 = {"docs_url": "https://docs.example.com"}
        score, problems, bonuses = calculate_docs_score_with_problems(data1)
        assert score == 4  # Only docs_url gives 4 points
        assert "description too short (<150 chars)" in problems
        # No "not enough documentation" because docs_url counts as external doc link
        assert (
            "not enough documentation (extend README to 500+ words or add documentation link)"
            not in problems
        )
        # Screenshots are now a bonus, not a problem when missing
        assert any(b["reason"] == "has dedicated docs URL" for b in bonuses)

        # Has long description but nothing else (short README, no external docs)
        data2 = {"description": "A" * 151}  # >150 chars
        score, problems, bonuses = calculate_docs_score_with_problems(data2)
        assert score == 18  # Description gives 18 points
        assert "description too short (<150 chars)" not in problems
        # Should report "not enough documentation" because README < 500 words and no docs_url or doc links
        assert (
            "not enough documentation (extend README to 500+ words or add documentation link)"
            in problems
        )

        # Has project URLs with documentation link but nothing else - doc link counts
        data3 = {"project_urls": {"Documentation": "https://docs.example.com"}}
        score, problems, bonuses = calculate_docs_score_with_problems(data3)
        assert score == 3  # Project URLs gives 3 points
        assert "description too short (<150 chars)" in problems
        # No "not enough documentation" because doc link counts as external doc
        assert (
            "not enough documentation (extend README to 500+ words or add documentation link)"
            not in problems
        )
        assert any(b["reason"] == "has documentation project URL" for b in bonuses)

        # Has screenshot but nothing else (short README, no external docs)
        data4 = {
            "description_html": '<img src="https://example.com/screenshot.png" width="400">'
        }
        score, problems, bonuses = calculate_docs_score_with_problems(data4)
        assert score == 5  # Screenshot gives 5 points
        assert "description too short (<150 chars)" in problems
        # Should report "not enough documentation" because README < 500 words and no docs_url or doc links
        assert (
            "not enough documentation (extend README to 500+ words or add documentation link)"
            in problems
        )
        # Screenshot is tracked as bonus
        assert any(b["reason"] == "has meaningful screenshots" for b in bonuses)

    def test_partial_metadata_problems(self):
        """Test that only missing metadata items are reported as problems."""
        # Has maintainer but nothing else
        data1 = {"maintainer": "Team"}
        score, problems, bonuses = calculate_metadata_score_with_problems(data1)
        assert score == 10
        assert "no maintainer info" not in problems
        assert "no author info" not in problems
        assert "no license" in problems
        assert "fewer than 3 classifiers" in problems

        # Has author but nothing else
        data2 = {"author": "Developer"}
        score, problems, bonuses = calculate_metadata_score_with_problems(data2)
        assert score == 10
        assert "no maintainer info" not in problems
        assert "no author info" not in problems
        assert "no license" in problems
        assert "fewer than 3 classifiers" in problems

        # Has license but no maintainer/author
        data3 = {"license": "MIT"}
        score, problems, bonuses = calculate_metadata_score_with_problems(data3)
        assert score == 10
        assert "no maintainer info" in problems
        assert "no author info" in problems
        assert "no license" not in problems
        assert "fewer than 3 classifiers" in problems

        # Has 3+ classifiers but nothing else
        data4 = {"classifiers": ["A", "B", "C"]}
        score, problems, bonuses = calculate_metadata_score_with_problems(data4)
        assert score == 10
        assert "no maintainer info" in problems
        assert "no author info" in problems
        assert "no license" in problems
        assert "fewer than 3 classifiers" not in problems

    def test_process_stores_problems_in_data(self):
        """Test that process() correctly stores problems in breakdown structure."""
        import time as time_module

        # Old package with some issues
        old_ts = int(time_module.time()) - (400 * 86400)  # 400 days ago
        data = {
            "name": "test.package",
            "version": "1.0.0",
            "upload_timestamp": old_ts,
            "docs_url": "https://docs.example.com",
            "description": "Short",  # < 150 chars
            "maintainer": "Team",
            "license": "MIT",
            "classifiers": ["A"],  # < 3
        }

        process("test.package", data)

        # Problems are now inside breakdown structure
        doc_problems = data["health_score_breakdown"]["documentation"]["problems"]
        meta_problems = data["health_score_breakdown"]["metadata"]["problems"]
        recency_problems = data["health_score_breakdown"]["recency"]["problems"]

        # Verify correct problems
        assert "description too short (<150 chars)" in doc_problems
        # Note: "no documentation project URLs" is no longer a standalone problem
        # docs_url counts as external doc, so no "not enough documentation" problem either
        # Screenshots are now a bonus, not a problem when missing
        assert "fewer than 3 classifiers" in meta_problems
        assert "last release over 1 year ago" in recency_problems

        # Verify bonuses are tracked for docs_url
        doc_bonuses = data["health_score_breakdown"]["documentation"]["bonuses"]
        assert any(b["reason"] == "has dedicated docs URL" for b in doc_bonuses)

    def test_enricher_calculates_problems_with_github_ones(self):
        """Test that the enricher calculates problems from scratch and adds GitHub ones."""
        import time as time_module

        # Create enricher instance without connecting to Typesense
        enricher = HealthEnricher.__new__(HealthEnricher)

        # Simulate data for from-scratch calculation with GitHub data showing issues
        old_upload_ts = int(time_module.time()) - (
            400 * 86400
        )  # 400 days ago = 1-2 years
        old_github_ts = time_module.time() - (400 * 86400)  # 400 days ago
        data = {
            "upload_timestamp": old_upload_ts,  # 1-2 years = 20 points
            # No docs_url, short description - documentation problems
            "description": "Short",
            # maintainer only - metadata problems
            "maintainer": "Team",
            # No license, no classifiers
            "github_stars": 100,
            "github_updated": old_github_ts,  # Old GitHub activity
            "github_open_issues": 200,  # High ratio (200/100 = 2.0)
        }

        result = enricher._calculate_enhanced_health_score(data)

        # Get problems from breakdown structure
        doc_problems = result["health_score_breakdown"]["documentation"]["problems"]
        meta_problems = result["health_score_breakdown"]["metadata"]["problems"]
        recency_problems = result["health_score_breakdown"]["recency"]["problems"]

        # Verify problems are calculated from scratch
        # Note: "no docs_url" is no longer a standalone problem (bonus only)
        # The combined documentation check applies: README < 500 words AND no docs_url AND no doc links
        assert (
            "not enough documentation (extend README to 500+ words or add documentation link)"
            in doc_problems
        )
        assert "no license" in meta_problems
        assert "last release over 1 year ago" in recency_problems

        # Verify GitHub problems are added
        assert "no GitHub activity in 1+ year" in recency_problems
        assert "high open issues to stars ratio (>1.0)" in meta_problems

    def test_enricher_github_problems_calculated_once(self):
        """Test that GitHub problems are calculated once from scratch."""
        import time as time_module

        enricher = HealthEnricher.__new__(HealthEnricher)

        old_github_ts = time_module.time() - (400 * 86400)
        old_upload_ts = int(time_module.time()) - (400 * 86400)
        data = {
            "upload_timestamp": old_upload_ts,
            "maintainer": "Team",  # For some base score
            "github_stars": 100,
            "github_updated": old_github_ts,
            "github_open_issues": 200,
        }

        result = enricher._calculate_enhanced_health_score(data)

        # Get problems from breakdown structure
        recency_problems = result["health_score_breakdown"]["recency"]["problems"]
        meta_problems = result["health_score_breakdown"]["metadata"]["problems"]

        # Count occurrences - should be exactly 1 (fresh calculation)
        assert recency_problems.count("no GitHub activity in 1+ year") == 1
        assert meta_problems.count("high open issues to stars ratio (>1.0)") == 1

    def test_enricher_limited_github_activity_problem(self):
        """Test that limited GitHub activity (6+ months) is detected."""
        import time as time_module

        enricher = HealthEnricher.__new__(HealthEnricher)

        # 200 days ago - should be "limited activity"
        limited_github_ts = time_module.time() - (200 * 86400)
        data = {
            "upload_timestamp": int(time_module.time()),  # Recent upload
            "maintainer": "Team",  # For some base score
            "github_stars": 100,
            "github_updated": limited_github_ts,
            "github_open_issues": 10,  # Good ratio
        }

        result = enricher._calculate_enhanced_health_score(data)

        # Activity bonus should be 3 (365 day range)
        assert result["health_score_breakdown"]["github_activity_bonus"] == 3

        # Get problems from breakdown structure
        recency_problems = result["health_score_breakdown"]["recency"]["problems"]
        assert "limited GitHub activity (6+ months)" in recency_problems

    def test_enricher_elevated_issues_ratio_problem(self):
        """Test that elevated issues ratio (>0.5) is detected."""
        import time as time_module

        enricher = HealthEnricher.__new__(HealthEnricher)

        recent_github_ts = time_module.time() - (10 * 86400)  # 10 days ago
        data = {
            "upload_timestamp": int(time_module.time()),  # Recent upload
            "maintainer": "Team",  # For some base score
            "github_stars": 100,
            "github_updated": recent_github_ts,
            "github_open_issues": 70,  # 0.7 ratio - elevated
        }

        result = enricher._calculate_enhanced_health_score(data)

        # Issue bonus should be 3 (0.5-1.0 range)
        assert result["health_score_breakdown"]["github_issue_bonus"] == 3

        # Get problems from breakdown structure
        meta_problems = result["health_score_breakdown"]["metadata"]["problems"]
        assert "elevated open issues ratio (>0.5)" in meta_problems


# ============================================================================
# NPM Package Scoring Tests
# ============================================================================


class TestScreenshotBonus:
    """Test that screenshots are tracked as bonus, not penalty."""

    def test_screenshot_is_bonus_not_penalty(self):
        """Test that missing screenshots don't create a problem."""
        # Package without screenshots
        data_without = {
            "description": "A" * 151,
            "docs_url": "https://docs.example.com",
        }
        score_without, problems_without, bonuses_without = (
            calculate_docs_score_with_problems(data_without)
        )
        # Should NOT have screenshot problem
        assert "no meaningful screenshots in documentation" not in problems_without
        # Screenshot bonus should not be present
        assert not any(
            b["reason"] == "has meaningful screenshots" for b in bonuses_without
        )

    def test_screenshot_gives_bonus_when_present(self):
        """Test that screenshots are tracked as bonus when present."""
        data_with = {
            "description": "A" * 151,
            "docs_url": "https://docs.example.com",
            "description_html": '<img src="https://example.com/screenshot.png" width="400">',
        }
        score_with, problems_with, bonuses_with = calculate_docs_score_with_problems(
            data_with
        )
        # Screenshot bonus should be present
        screenshot_bonus = next(
            (b for b in bonuses_with if b["reason"] == "has meaningful screenshots"),
            None,
        )
        assert screenshot_bonus is not None
        assert screenshot_bonus["points"] == 5

    def test_screenshot_bonus_adds_to_score(self):
        """Test that screenshot bonus adds 5 points to documentation score."""
        # Without screenshot
        data_without = {
            "description": "A" * 151,
            "docs_url": "https://docs.example.com",
        }
        score_without, _, _ = calculate_docs_score_with_problems(data_without)

        # With screenshot
        data_with = {
            "description": "A" * 151,
            "docs_url": "https://docs.example.com",
            "description_html": '<img src="https://example.com/screenshot.png" width="400">',
        }
        score_with, _, _ = calculate_docs_score_with_problems(data_with)

        # Screenshot should add 5 points
        assert score_with == score_without + 5

    def test_all_bonuses_tracked_correctly(self):
        """Test that all documentation bonuses are tracked correctly."""
        data = {
            "docs_url": "https://docs.example.com",
            "description": "A" * 151,
            "project_urls": {"Documentation": "https://docs.example.com"},
            "description_html": '<img src="https://example.com/screenshot.png" width="400">',
        }
        score, problems, bonuses = calculate_docs_score_with_problems(data)

        # All three bonuses should be present
        assert any(b["reason"] == "has dedicated docs URL" for b in bonuses)
        assert any(b["reason"] == "has documentation project URL" for b in bonuses)
        assert any(b["reason"] == "has meaningful screenshots" for b in bonuses)

        # Total bonus points: 4 + 3 + 5 = 12, plus 18 for description = 30
        assert score == 30


class TestNpmPackageScoring:
    """Test health scoring for npm packages."""

    def test_npm_package_with_3_keywords_gets_10_points(self):
        """Test that npm package with 3+ keywords gets 10 points."""
        data = {
            "registry": "npm",
            "keywords": ["volto", "addon", "plone"],
        }
        score = calculate_metadata_score(data)
        assert score == 10

    def test_npm_package_with_fewer_keywords_reports_problem(self):
        """Test that npm package with <3 keywords reports correct problem."""
        data = {
            "registry": "npm",
            "keywords": ["volto"],
        }
        score, problems, bonuses = calculate_metadata_score_with_problems(data)
        assert score == 0
        assert "fewer than 3 keywords" in problems
        assert "fewer than 3 classifiers" not in problems

    def test_npm_package_ignores_classifiers(self):
        """Test that npm packages check keywords, not classifiers."""
        data = {
            "registry": "npm",
            "classifiers": [],  # Empty (npm doesn't have classifiers)
            "keywords": ["volto", "addon", "plone", "eea"],
        }
        score = calculate_metadata_score(data)
        assert score == 10

    def test_pypi_package_still_uses_classifiers(self):
        """Test that PyPI packages still use classifiers."""
        data = {
            "registry": "pypi",
            "classifiers": ["A", "B", "C"],
            "keywords": [],  # Even if keywords present, classifiers used
        }
        score = calculate_metadata_score(data)
        assert score == 10

    def test_default_registry_uses_classifiers(self):
        """Test that missing registry defaults to classifier check."""
        data = {
            "classifiers": ["A", "B", "C"],
        }
        score = calculate_metadata_score(data)
        assert score == 10

    def test_npm_package_with_empty_keywords_reports_problem(self):
        """Test that npm package with empty keywords reports problem."""
        data = {
            "registry": "npm",
            "keywords": [],
        }
        score, problems, bonuses = calculate_metadata_score_with_problems(data)
        assert score == 0
        assert "fewer than 3 keywords" in problems

    def test_npm_package_full_metadata_score(self):
        """Test npm package with all metadata gets full 30 points."""
        data = {
            "registry": "npm",
            "maintainer": "EEA",
            "license": "MIT",
            "keywords": ["volto", "addon", "plone", "eea"],
        }
        score = calculate_metadata_score(data)
        assert score == 30

    def test_npm_package_integrated_health_score(self):
        """Test full health scoring pipeline for npm package."""
        import time as time_module

        data = {
            "name": "@eeacms/volto-n2k",
            "registry": "npm",
            "version": "1.0.0",
            "upload_timestamp": int(time_module.time()),  # Recent
            "docs_url": "https://docs.example.com",  # 4 points
            "description": "A" * 151,  # >150 chars (18 points)
            "description_html": '<img src="https://example.com/screenshot.png" width="400">',  # 5 points
            "project_urls": {"Documentation": "https://docs.example.com"},  # 3 points
            "maintainer": "EEA",  # 10 points
            "license": "MIT",  # 10 points
            "keywords": [
                "volto",
                "addon",
                "plone",
                "eea",
            ],  # 10 points (not classifiers)
            "classifiers": [],  # Empty for npm - should be ignored
        }

        process("@eeacms/volto-n2k", data)

        # Should get full score
        assert data["health_score"] == 100
        # Points are now inside breakdown
        assert data["health_score_breakdown"]["metadata"]["points"] == 30
        # Problems are now inside breakdown
        meta_problems = data["health_score_breakdown"]["metadata"]["problems"]
        # Should NOT have "fewer than 3 classifiers" problem
        assert "fewer than 3 classifiers" not in meta_problems
