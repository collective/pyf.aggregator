"""
Unit tests for pyf.aggregator.plugins.description_splitter module.

This module tests:
- Title extraction from first H2 heading
- First chapter extraction (summary + content until 2nd heading)
- Changelog detection and extraction
- Main content extraction (excludes changelog)
- Edge cases (no headings, no changelog, empty description)
"""

import pytest

from pyf.aggregator.plugins.description_splitter import (
    split_description,
    process,
    load,
)


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def simple_html():
    """HTML with a single H2 and content."""
    return """
    <h2>Package Title</h2>
    <p>This is the package description.</p>
    """


@pytest.fixture
def html_with_multiple_sections():
    """HTML with multiple H2 sections."""
    return """
    <h2>Package Title</h2>
    <p>Introduction paragraph.</p>
    <h2>Installation</h2>
    <p>Install with pip.</p>
    <h2>Usage</h2>
    <p>How to use the package.</p>
    """


@pytest.fixture
def html_with_changelog():
    """HTML with a changelog section."""
    return """
    <h2>Package Title</h2>
    <p>Introduction paragraph.</p>
    <h2>Features</h2>
    <p>Feature list here.</p>
    <h2>Changelog</h2>
    <h3>1.0.0</h3>
    <p>Initial release.</p>
    <h3>0.9.0</h3>
    <p>Beta release.</p>
    """


@pytest.fixture
def html_with_history():
    """HTML with a history section (alternative changelog name)."""
    return """
    <h2>My Package</h2>
    <p>Package intro.</p>
    <h2>History</h2>
    <p>Version history here.</p>
    """


@pytest.fixture
def html_with_release_notes():
    """HTML with Release Notes section."""
    return """
    <h2>My Package</h2>
    <p>Package intro.</p>
    <h2>Release Notes</h2>
    <p>Release notes here.</p>
    """


@pytest.fixture
def html_no_headings():
    """HTML without any headings."""
    return """
    <p>Just some content without headings.</p>
    <p>Another paragraph.</p>
    """


@pytest.fixture
def complex_html():
    """Complex HTML with nested elements and multiple sections."""
    return """
    <h2>plone.api</h2>
    <p>A simple API to access Plone functionality.</p>
    <ul>
        <li>Easy to use</li>
        <li>Well documented</li>
    </ul>
    <h2>Installation</h2>
    <p>Run: <code>pip install plone.api</code></p>
    <h2>Usage</h2>
    <pre><code>from plone import api</code></pre>
    <h2>Changelog</h2>
    <h3>2.0.0</h3>
    <ul><li>Major release</li></ul>
    <h3>1.0.0</h3>
    <ul><li>Initial release</li></ul>
    """


# ============================================================================
# Split Description Tests - Title Extraction
# ============================================================================

class TestTitleExtraction:
    """Test title extraction from first H2."""

    def test_extracts_first_h2_as_title(self, simple_html):
        """Title should be the text of the first H2."""
        result = split_description(simple_html)
        assert result["title"] == "Package Title"

    def test_title_is_plain_text(self):
        """Title should be plain text without HTML tags."""
        html = "<h2>Title with <strong>bold</strong> text</h2><p>Content</p>"
        result = split_description(html)
        assert result["title"] == "Title with bold text"
        assert "<" not in result["title"]

    def test_title_strips_whitespace(self):
        """Title should have whitespace stripped."""
        html = "<h2>  Spaced Title  </h2><p>Content</p>"
        result = split_description(html)
        assert result["title"] == "Spaced Title"

    def test_no_headings_empty_title(self, html_no_headings):
        """No headings should result in empty title."""
        result = split_description(html_no_headings)
        assert result["title"] == ""

    def test_multiple_h2_uses_first(self, html_with_multiple_sections):
        """Multiple H2s should use only the first for title."""
        result = split_description(html_with_multiple_sections)
        assert result["title"] == "Package Title"


# ============================================================================
# Split Description Tests - First Chapter
# ============================================================================

class TestFirstChapterExtraction:
    """Test first_chapter extraction."""

    def test_first_chapter_includes_content_until_second_heading(
        self, html_with_multiple_sections
    ):
        """First chapter should include content until the 2nd H2."""
        result = split_description(html_with_multiple_sections)
        assert "Introduction paragraph" in result["first_chapter"]
        assert "Install with pip" not in result["first_chapter"]

    def test_first_chapter_includes_first_heading(self, simple_html):
        """First chapter should include the first H2."""
        result = split_description(simple_html)
        assert "Package Title" in result["first_chapter"]
        assert "package description" in result["first_chapter"]

    def test_no_headings_all_content_in_first_chapter(self, html_no_headings):
        """No headings should put all content in first_chapter."""
        result = split_description(html_no_headings)
        assert "Just some content" in result["first_chapter"]
        assert "Another paragraph" in result["first_chapter"]

    def test_single_heading_all_content_in_first_chapter(self, simple_html):
        """Single heading should put all content in first_chapter."""
        result = split_description(simple_html)
        assert "Package Title" in result["first_chapter"]
        assert "package description" in result["first_chapter"]


# ============================================================================
# Split Description Tests - Main Content
# ============================================================================

class TestMainContentExtraction:
    """Test main_content extraction."""

    def test_main_content_excludes_first_chapter(self, html_with_multiple_sections):
        """Main content should not include first chapter content."""
        result = split_description(html_with_multiple_sections)
        assert "Introduction paragraph" not in result["main_content"]

    def test_main_content_includes_middle_sections(self, html_with_multiple_sections):
        """Main content should include sections between first chapter and changelog."""
        result = split_description(html_with_multiple_sections)
        assert "Install with pip" in result["main_content"]
        assert "How to use" in result["main_content"]

    def test_main_content_excludes_changelog(self, html_with_changelog):
        """Main content should not include changelog section."""
        result = split_description(html_with_changelog)
        assert "Feature list" in result["main_content"]
        assert "Initial release" not in result["main_content"]
        assert "Beta release" not in result["main_content"]

    def test_no_middle_sections_empty_main_content(self, simple_html):
        """Single section should result in empty main_content."""
        result = split_description(simple_html)
        assert result["main_content"] == ""

    def test_no_changelog_all_middle_in_main_content(self, html_with_multiple_sections):
        """Without changelog, all middle sections go to main_content."""
        result = split_description(html_with_multiple_sections)
        assert "Installation" in result["main_content"]
        assert "Usage" in result["main_content"]


# ============================================================================
# Split Description Tests - Changelog Detection
# ============================================================================

class TestChangelogDetection:
    """Test changelog section detection."""

    def test_detects_changelog_heading(self, html_with_changelog):
        """Should detect 'Changelog' heading."""
        result = split_description(html_with_changelog)
        assert "Initial release" in result["changelog"]
        assert "Beta release" in result["changelog"]

    def test_detects_history_heading(self, html_with_history):
        """Should detect 'History' heading."""
        result = split_description(html_with_history)
        assert "Version history" in result["changelog"]

    def test_detects_release_notes_heading(self, html_with_release_notes):
        """Should detect 'Release Notes' heading."""
        result = split_description(html_with_release_notes)
        assert "Release notes" in result["changelog"]

    def test_detects_changes_heading(self):
        """Should detect 'Changes' heading."""
        html = "<h2>Title</h2><p>Intro</p><h2>Changes</h2><p>Change log</p>"
        result = split_description(html)
        assert "Change log" in result["changelog"]

    def test_detects_whats_new_heading(self):
        """Should detect 'What's New' heading."""
        html = "<h2>Title</h2><p>Intro</p><h2>What's New</h2><p>New features</p>"
        result = split_description(html)
        assert "New features" in result["changelog"]

    def test_detects_versions_heading(self):
        """Should detect 'Versions' heading."""
        html = "<h2>Title</h2><p>Intro</p><h2>Versions</h2><p>Version list</p>"
        result = split_description(html)
        assert "Version list" in result["changelog"]

    def test_case_insensitive_detection(self):
        """Should detect changelog headings case-insensitively."""
        html = "<h2>Title</h2><p>Intro</p><h2>CHANGELOG</h2><p>Changes</p>"
        result = split_description(html)
        assert "Changes" in result["changelog"]

    def test_no_changelog_empty_string(self, html_with_multiple_sections):
        """No changelog heading should result in empty changelog."""
        result = split_description(html_with_multiple_sections)
        assert result["changelog"] == ""

    def test_changelog_includes_subsections(self, html_with_changelog):
        """Changelog should include H3 subsections."""
        result = split_description(html_with_changelog)
        assert "1.0.0" in result["changelog"]
        assert "0.9.0" in result["changelog"]


# ============================================================================
# Split Description Tests - Edge Cases
# ============================================================================

class TestEdgeCases:
    """Test edge cases."""

    def test_none_description(self):
        """None description should return all empty strings."""
        result = split_description(None)
        assert result["title"] == ""
        assert result["first_chapter"] == ""
        assert result["main_content"] == ""
        assert result["changelog"] == ""

    def test_empty_description(self):
        """Empty description should return all empty strings."""
        result = split_description("")
        assert result["title"] == ""
        assert result["first_chapter"] == ""
        assert result["main_content"] == ""
        assert result["changelog"] == ""

    def test_whitespace_only(self):
        """Whitespace-only description should return all empty strings."""
        result = split_description("   \n\t  ")
        assert result["title"] == ""
        assert result["first_chapter"] == ""
        assert result["main_content"] == ""
        assert result["changelog"] == ""

    def test_complex_html_structure(self, complex_html):
        """Complex HTML should be parsed correctly."""
        result = split_description(complex_html)
        assert result["title"] == "plone.api"
        assert "simple API" in result["first_chapter"]
        assert "pip install" in result["main_content"]
        assert "Major release" in result["changelog"]

    def test_h3_changelog_detection(self):
        """Should detect changelog at H3 level."""
        html = "<h2>Title</h2><p>Intro</p><h2>More</h2><h3>Changelog</h3><p>Changes</p>"
        result = split_description(html)
        assert "Changes" in result["changelog"]

    def test_only_changelog_section(self):
        """Description with only changelog should have empty main_content."""
        html = "<h2>Title</h2><p>Intro</p><h2>Changelog</h2><p>Changes</p>"
        result = split_description(html)
        assert result["title"] == "Title"
        assert "Intro" in result["first_chapter"]
        assert result["main_content"] == ""
        assert "Changes" in result["changelog"]


# ============================================================================
# Process Function Tests
# ============================================================================

class TestProcess:
    """Test the main process function."""

    def test_adds_fields_to_data(self):
        """Process should add all four fields to data."""
        data = {
            "description": "<h2>Title</h2><p>Content</p>",
            "summary": "Package summary",
        }
        process("test-id", data)

        assert "title" in data
        assert "first_chapter" in data
        assert "main_content" in data
        assert "changelog" in data

    def test_handles_none_description(self):
        """Process should handle None description."""
        data = {"description": None}
        process("test-id", data)

        assert data["title"] == ""
        assert data["first_chapter"] == ""
        assert data["main_content"] == ""
        assert data["changelog"] == ""

    def test_includes_summary_in_first_chapter(self):
        """Process should prepend summary to first_chapter."""
        data = {
            "description": "<h2>Title</h2><p>Content</p>",
            "summary": "Package summary",
        }
        process("test-id", data)

        assert "Package summary" in data["first_chapter"]
        assert "Content" in data["first_chapter"]

    def test_summary_comes_before_content(self):
        """Summary should appear before description content in first_chapter."""
        data = {
            "description": "<h2>Title</h2><p>Description content</p>",
            "summary": "Summary text",
        }
        process("test-id", data)

        first_chapter = data["first_chapter"]
        summary_pos = first_chapter.find("Summary text")
        content_pos = first_chapter.find("Description content")
        assert summary_pos < content_pos


# ============================================================================
# Load Function Tests
# ============================================================================

class TestLoad:
    """Test the load function."""

    def test_returns_process_function(self):
        """Load should return the process function."""
        result = load({})
        assert result == process

    def test_returned_function_is_callable(self):
        """The returned function should be callable."""
        result = load({})
        assert callable(result)
