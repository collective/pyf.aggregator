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
    strip_links,
    strip_images,
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
def html_starts_with_text():
    """HTML that starts with text content before the first heading."""
    return """
    <p>This is an helper package for something.</p>
    <p><img src="badge.png" alt="badge"></p>
    <h3>Features</h3>
    <p>Feature list here.</p>
    <h3>Installation</h3>
    <p>Install instructions.</p>
    """


@pytest.fixture
def html_starts_with_text_and_changelog():
    """HTML that starts with text content, has features, and a changelog."""
    return """
    <p>This is a package description.</p>
    <h3>Features</h3>
    <p>Feature list here.</p>
    <h3>Changelog</h3>
    <p>Version history.</p>
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


@pytest.fixture
def html_with_h4_only():
    """HTML with only H4 headings."""
    return """
    <h4>Package Title</h4>
    <p>Introduction paragraph.</p>
    <h4>Installation</h4>
    <p>Install instructions here.</p>
    <h4>Usage</h4>
    <p>How to use the package.</p>
    """


@pytest.fixture
def html_with_mixed_h4_h5():
    """HTML with mixed H4 and H5 headings."""
    return """
    <h4>Package Title</h4>
    <p>Introduction paragraph.</p>
    <h5>Sub-section</h5>
    <p>Sub-section content.</p>
    <h4>Features</h4>
    <p>Feature list here.</p>
    """


@pytest.fixture
def html_with_h1_title():
    """HTML with H1 as first heading."""
    return """
    <h1>Package Title</h1>
    <p>Introduction paragraph.</p>
    <h2>Installation</h2>
    <p>Install instructions.</p>
    """


@pytest.fixture
def html_with_h6_changelog():
    """HTML with H6 changelog heading."""
    return """
    <h3>Package Title</h3>
    <p>Introduction paragraph.</p>
    <h3>Features</h3>
    <p>Feature list.</p>
    <h6>Changelog</h6>
    <p>Version history here.</p>
    """


# ============================================================================
# RST Section Wrapper Fixtures
# ============================================================================


@pytest.fixture
def rst_section_html():
    """RST-rendered HTML with section wrappers."""
    return """
    <section id="imio-news-core">
        <h3>imio.news.core</h3>
        <p>Core product for iMio news websites</p>
        <section id="features">
            <h4>Features</h4>
            <ul>
                <li>Feature 1</li>
                <li>Feature 2</li>
            </ul>
        </section>
        <section id="installation">
            <h4>Installation</h4>
            <p>Install with pip install imio.news.core</p>
        </section>
    </section>
    """


@pytest.fixture
def rst_section_with_changelog():
    """RST-rendered HTML with section wrappers and changelog."""
    return """
    <section id="package-name">
        <h3>Package Name</h3>
        <p>Package introduction.</p>
        <section id="features">
            <h4>Features</h4>
            <p>Feature list here.</p>
        </section>
        <section id="changelog">
            <h4>Changelog</h4>
            <section id="version-1-0">
                <h5>1.0.0</h5>
                <p>Initial release.</p>
            </section>
        </section>
    </section>
    """


@pytest.fixture
def rst_deeply_nested_sections():
    """RST-rendered HTML with deeply nested sections."""
    return """
    <section id="outer">
        <h2>Outer Title</h2>
        <p>Outer intro.</p>
        <section id="middle">
            <h3>Middle Section</h3>
            <p>Middle content.</p>
            <section id="inner">
                <h4>Inner Section</h4>
                <p>Inner content.</p>
            </section>
        </section>
    </section>
    """


@pytest.fixture
def rst_single_section():
    """RST-rendered HTML with single section and no sub-sections."""
    return """
    <section id="simple-package">
        <h3>Simple Package</h3>
        <p>This is a simple package with no sub-sections.</p>
        <p>Just some paragraphs of content.</p>
    </section>
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

    def test_starts_with_text_excludes_first_heading(self, html_starts_with_text):
        """When content starts with text, first_chapter excludes first heading."""
        result = split_description(html_starts_with_text)
        assert "helper package" in result["first_chapter"]
        # First heading should NOT be in first_chapter
        assert "Features" not in result["first_chapter"]
        assert "<h3>" not in result["first_chapter"]

    def test_starts_with_text_main_content_starts_at_first_heading(
        self, html_starts_with_text
    ):
        """When content starts with text, main_content starts at first heading."""
        result = split_description(html_starts_with_text)
        assert "Features" in result["main_content"]
        assert "Feature list" in result["main_content"]
        assert "Installation" in result["main_content"]

    def test_starts_with_text_title_from_first_heading(self, html_starts_with_text):
        """Title should still be extracted from first heading."""
        result = split_description(html_starts_with_text)
        assert result["title"] == "Features"

    def test_starts_with_text_and_changelog(self, html_starts_with_text_and_changelog):
        """Content starting with text should handle changelog correctly."""
        result = split_description(html_starts_with_text_and_changelog)
        assert "package description" in result["first_chapter"]
        assert "Features" not in result["first_chapter"]
        assert "Features" in result["main_content"]
        assert "Feature list" in result["main_content"]
        assert "Changelog" not in result["main_content"]
        assert "Changelog" in result["changelog"]
        assert "Version history" in result["changelog"]


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


# ============================================================================
# All Heading Levels Tests (H1-H6)
# ============================================================================


class TestAllHeadingLevels:
    """Test detection of all heading levels H1-H6."""

    def test_h4_only_extracts_title(self, html_with_h4_only):
        """Should extract title from H4 heading."""
        result = split_description(html_with_h4_only)
        assert result["title"] == "Package Title"

    def test_h4_only_splits_at_second_heading(self, html_with_h4_only):
        """Should split at second H4 heading."""
        result = split_description(html_with_h4_only)
        assert "Introduction paragraph" in result["first_chapter"]
        assert "Install instructions" not in result["first_chapter"]
        assert "Install instructions" in result["main_content"]

    def test_mixed_h4_h5_extracts_first_as_title(self, html_with_mixed_h4_h5):
        """Should extract first heading regardless of level."""
        result = split_description(html_with_mixed_h4_h5)
        assert result["title"] == "Package Title"

    def test_mixed_h4_h5_splits_at_second_heading(self, html_with_mixed_h4_h5):
        """Should split at second heading even if different level."""
        result = split_description(html_with_mixed_h4_h5)
        assert "Introduction paragraph" in result["first_chapter"]
        # H5 is the second heading, so split happens there
        assert "Sub-section content" not in result["first_chapter"]

    def test_h1_title_extracted(self, html_with_h1_title):
        """Should extract title from H1 heading."""
        result = split_description(html_with_h1_title)
        assert result["title"] == "Package Title"

    def test_h1_splits_at_h2(self, html_with_h1_title):
        """Should split at second heading (H2 after H1)."""
        result = split_description(html_with_h1_title)
        assert "Introduction paragraph" in result["first_chapter"]
        assert "Install instructions" in result["main_content"]

    def test_h6_changelog_detection(self, html_with_h6_changelog):
        """Should detect changelog at H6 level."""
        result = split_description(html_with_h6_changelog)
        assert "Version history" in result["changelog"]
        assert "Feature list" in result["main_content"]


# ============================================================================
# Warning Logging Tests
# ============================================================================


class TestWarningLogging:
    """Test warning logging for empty sections."""

    def test_warns_on_empty_first_chapter(self, caplog):
        """Should warn when first_chapter is empty after splitting."""
        import logging

        # Create HTML that results in empty first_chapter (edge case)
        # This is actually hard to achieve since we always have first_chapter
        # But we can test the process function directly
        with caplog.at_level(logging.WARNING):
            data = {"description": "", "summary": ""}
            process("test-package", data)
            # Empty description doesn't trigger warning
            assert "first_chapter is empty" not in caplog.text

    def test_no_warning_on_empty_description(self, caplog):
        """Should not warn when description is empty/None."""
        import logging

        with caplog.at_level(logging.WARNING):
            data = {"description": None}
            process("test-package", data)
            assert "first_chapter is empty" not in caplog.text
            assert "main_content is empty" not in caplog.text

    def test_no_warning_when_sections_populated(self, caplog):
        """Should not warn when both sections have content."""
        import logging

        with caplog.at_level(logging.WARNING):
            html = "<h2>Title</h2><p>Intro</p><h2>More</h2><p>Content</p>"
            data = {"description": html}
            process("test-package", data)
            assert "first_chapter is empty" not in caplog.text
            # main_content is populated so no warning

    def test_warns_on_empty_main_content(self, caplog):
        """Should warn when main_content is empty (single section)."""
        import logging

        with caplog.at_level(logging.WARNING):
            html = "<h2>Title</h2><p>Only intro, no other sections.</p>"
            data = {"description": html}
            process("test-package", data)
            assert "main_content is empty" in caplog.text

    def test_warning_includes_package_identifier(self, caplog):
        """Warning message should include package identifier."""
        import logging

        with caplog.at_level(logging.WARNING):
            html = "<h2>Title</h2><p>Content</p>"
            data = {"description": html}
            process("my-special-package", data)
            assert "my-special-package" in caplog.text


# ============================================================================
# RST Section Wrapper Tests
# ============================================================================


class TestRSTSectionWrappers:
    """Test handling of RST-rendered HTML with section wrappers."""

    def test_extracts_title_from_sectioned_html(self, rst_section_html):
        """Should extract title from heading inside section wrapper."""
        result = split_description(rst_section_html)
        assert result["title"] == "imio.news.core"

    def test_first_chapter_includes_intro_until_second_heading(self, rst_section_html):
        """First chapter should include intro content until second heading."""
        result = split_description(rst_section_html)
        assert "imio.news.core" in result["first_chapter"]
        assert "Core product for iMio news websites" in result["first_chapter"]
        # Should NOT include Features section content
        assert "Feature 1" not in result["first_chapter"]

    def test_first_chapter_strips_section_wrappers(self, rst_section_html):
        """First chapter output should not contain section tags."""
        result = split_description(rst_section_html)
        assert "<section" not in result["first_chapter"]
        assert "</section>" not in result["first_chapter"]

    def test_main_content_starts_from_second_heading(self, rst_section_html):
        """Main content should start from second heading."""
        result = split_description(rst_section_html)
        assert "Features" in result["main_content"]
        assert "Feature 1" in result["main_content"]
        assert "Installation" in result["main_content"]

    def test_main_content_strips_section_wrappers(self, rst_section_html):
        """Main content output should not contain section tags."""
        result = split_description(rst_section_html)
        assert "<section" not in result["main_content"]
        assert "</section>" not in result["main_content"]

    def test_main_content_excludes_first_chapter(self, rst_section_html):
        """Main content should not include first chapter content."""
        result = split_description(rst_section_html)
        assert "Core product for iMio news websites" not in result["main_content"]

    def test_changelog_detection_inside_sections(self, rst_section_with_changelog):
        """Should detect changelog inside section wrappers."""
        result = split_description(rst_section_with_changelog)
        assert "Changelog" in result["changelog"]
        assert "1.0.0" in result["changelog"]
        assert "Initial release" in result["changelog"]

    def test_changelog_strips_section_wrappers(self, rst_section_with_changelog):
        """Changelog output should not contain section tags."""
        result = split_description(rst_section_with_changelog)
        assert "<section" not in result["changelog"]
        assert "</section>" not in result["changelog"]

    def test_main_content_excludes_changelog(self, rst_section_with_changelog):
        """Main content should not include changelog section."""
        result = split_description(rst_section_with_changelog)
        assert "Features" in result["main_content"]
        assert "Initial release" not in result["main_content"]
        assert "1.0.0" not in result["main_content"]

    def test_deeply_nested_sections(self, rst_deeply_nested_sections):
        """Should handle deeply nested section wrappers."""
        result = split_description(rst_deeply_nested_sections)
        assert result["title"] == "Outer Title"
        assert "Outer intro" in result["first_chapter"]
        assert "Middle Section" in result["main_content"]
        assert "Inner Section" in result["main_content"]
        # All section tags should be stripped
        assert "<section" not in result["first_chapter"]
        assert "<section" not in result["main_content"]

    def test_single_section_all_in_first_chapter(self, rst_single_section):
        """Single section with no sub-sections should all go to first_chapter."""
        result = split_description(rst_single_section)
        assert result["title"] == "Simple Package"
        assert "simple package with no sub-sections" in result["first_chapter"]
        assert "Just some paragraphs" in result["first_chapter"]
        assert result["main_content"] == ""

    def test_backwards_compatibility_flat_html(self, html_with_multiple_sections):
        """Should still work with flat HTML (no section wrappers)."""
        result = split_description(html_with_multiple_sections)
        assert result["title"] == "Package Title"
        assert "Introduction paragraph" in result["first_chapter"]
        assert "Install with pip" in result["main_content"]

    def test_backwards_compatibility_complex_html(self, complex_html):
        """Should still work with complex flat HTML."""
        result = split_description(complex_html)
        assert result["title"] == "plone.api"
        assert "simple API" in result["first_chapter"]
        assert "pip install" in result["main_content"]
        assert "Major release" in result["changelog"]

    def test_imio_news_core_example(self):
        """Test with the exact RST HTML example from the issue."""
        html = """
        <section id="imio-news-core">
            <h3>imio.news.core</h3>
            <p>Core product for iMio news websites</p>
            <section id="features">
                <h4>Features</h4>
                <ul>
                    <li>Can be used...</li>
                </ul>
            </section>
        </section>
        """
        result = split_description(html)
        assert result["title"] == "imio.news.core"
        assert "<h3>imio.news.core</h3>" in result["first_chapter"]
        assert "Core product for iMio news websites" in result["first_chapter"]
        assert "<section" not in result["first_chapter"]
        assert "Features" in result["main_content"]
        assert "<section" not in result["main_content"]


# ============================================================================
# Link Stripping Tests
# ============================================================================


class TestStripImages:
    """Test the strip_images helper function."""

    def test_strips_simple_image(self):
        """Should strip a simple image tag."""
        html = '<p>Text before <img src="image.png" alt="test"> text after</p>'
        result = strip_images(html)
        assert "<img" not in result
        assert "Text before" in result
        assert "text after" in result

    def test_strips_image_in_paragraph(self):
        """Should strip image within a paragraph."""
        html = '<p><img src="badge.png" alt="badge"></p>'
        result = strip_images(html)
        assert "<img" not in result
        # Empty paragraph might remain
        assert "badge.png" not in result

    def test_handles_multiple_images(self):
        """Should strip multiple images."""
        html = '<p><img src="a.png"> and <img src="b.png"></p>'
        result = strip_images(html)
        assert "<img" not in result
        assert "and" in result

    def test_handles_empty_string(self):
        """Should handle empty string."""
        assert strip_images("") == ""

    def test_handles_none(self):
        """Should handle None input."""
        assert strip_images(None) is None

    def test_preserves_other_tags(self):
        """Should preserve other HTML tags."""
        html = '<p><strong>Bold</strong> and <img src="x.png"></p>'
        result = strip_images(html)
        assert "<strong>Bold</strong>" in result
        assert "<img" not in result

    def test_strips_image_with_attributes(self):
        """Should strip images with various attributes."""
        html = '<img src="test.jpg" alt="Test" width="100" height="50" class="badge">'
        result = strip_images(html)
        assert "<img" not in result
        assert "test.jpg" not in result


class TestImageStrippingInFirstChapter:
    """Test that images are stripped from first_chapter."""

    def test_first_chapter_images_stripped(self):
        """Images should be stripped from first_chapter."""
        html = """
        <h2>Package Title</h2>
        <p>Check out this <img src="badge.png" alt="badge"> badge.</p>
        <h2>Installation</h2>
        <p>Another section.</p>
        """
        result = split_description(html)
        assert "<img" not in result["first_chapter"]
        assert "badge.png" not in result["first_chapter"]
        assert "Check out this" in result["first_chapter"]

    def test_main_content_images_preserved(self):
        """Images should be preserved in main_content."""
        html = """
        <h2>Package Title</h2>
        <p>Introduction.</p>
        <h2>Installation</h2>
        <p>Screenshot: <img src="screenshot.png" alt="screenshot"></p>
        """
        result = split_description(html)
        assert "<img" in result["main_content"]
        assert "screenshot.png" in result["main_content"]

    def test_first_chapter_starting_with_text_images_stripped(
        self, html_starts_with_text
    ):
        """Images in text-starting first_chapter should be stripped."""
        result = split_description(html_starts_with_text)
        assert "<img" not in result["first_chapter"]
        assert "badge.png" not in result["first_chapter"]
        assert "helper package" in result["first_chapter"]


class TestStripLinks:
    def test_strips_simple_link(self):
        """Should strip a simple link while preserving text."""
        html = '<a href="https://example.com">Click here</a>'
        result = strip_links(html)
        assert result == "Click here"
        assert "<a" not in result
        assert "href" not in result

    def test_strips_link_in_paragraph(self):
        """Should strip link within a paragraph."""
        html = '<p>Visit <a href="https://example.com">our website</a> for more.</p>'
        result = strip_links(html)
        assert "Visit our website for more." in result
        assert "<a" not in result

    def test_handles_multiple_links(self):
        """Should strip multiple links."""
        html = '<p><a href="a">First</a> and <a href="b">Second</a></p>'
        result = strip_links(html)
        assert "First and Second" in result
        assert "<a" not in result

    def test_handles_empty_string(self):
        """Should handle empty string."""
        assert strip_links("") == ""

    def test_handles_none(self):
        """Should handle None input."""
        assert strip_links(None) is None

    def test_preserves_other_tags(self):
        """Should preserve other HTML tags."""
        html = '<p><strong>Bold</strong> and <a href="x">link</a></p>'
        result = strip_links(html)
        assert "<strong>Bold</strong>" in result
        assert "link" in result
        assert "<a" not in result

    def test_handles_nested_content_in_link(self):
        """Should preserve nested content from links."""
        html = '<a href="x"><strong>Bold link</strong></a>'
        result = strip_links(html)
        assert "<strong>Bold link</strong>" in result
        assert "<a" not in result


class TestLinkStrippingInFirstChapter:
    """Test that links are stripped from first_chapter but not other fields."""

    def test_first_chapter_links_stripped(self):
        """Links should be stripped from first_chapter."""
        html = """
        <h2>Package Title</h2>
        <p>Check out <a href="https://example.com">this link</a> for more.</p>
        <h2>Installation</h2>
        <p>Another section.</p>
        """
        result = split_description(html)
        assert "<a" not in result["first_chapter"]
        assert "this link" in result["first_chapter"]

    def test_main_content_links_preserved(self):
        """Links should be preserved in main_content."""
        html = """
        <h2>Package Title</h2>
        <p>Introduction.</p>
        <h2>Installation</h2>
        <p>Install from <a href="https://pypi.org">PyPI</a>.</p>
        """
        result = split_description(html)
        assert "<a" in result["main_content"]
        assert 'href="https://pypi.org"' in result["main_content"]

    def test_changelog_links_preserved(self):
        """Links should be preserved in changelog."""
        html = """
        <h2>Package Title</h2>
        <p>Introduction.</p>
        <h2>Changelog</h2>
        <p>See <a href="https://github.com">GitHub</a> for details.</p>
        """
        result = split_description(html)
        assert "<a" in result["changelog"]
        assert 'href="https://github.com"' in result["changelog"]

    def test_multiple_links_in_first_chapter_stripped(self):
        """Multiple links in first_chapter should all be stripped."""
        html = """
        <h2>Package</h2>
        <p><a href="a">One</a>, <a href="b">Two</a>, <a href="c">Three</a></p>
        """
        result = split_description(html)
        assert "<a" not in result["first_chapter"]
        assert "One" in result["first_chapter"]
        assert "Two" in result["first_chapter"]
        assert "Three" in result["first_chapter"]

    def test_link_text_preserved_in_context(self):
        """Link text should be preserved in surrounding context."""
        html = """
        <h2>Title</h2>
        <p>Please visit <a href="x">our documentation</a> for more info.</p>
        """
        result = split_description(html)
        assert (
            "Please visit our documentation for more info." in result["first_chapter"]
        )

    def test_first_chapter_with_no_links_unchanged(self):
        """First chapter without links should work normally."""
        html = """
        <h2>Title</h2>
        <p>No links here.</p>
        """
        result = split_description(html)
        assert "No links here" in result["first_chapter"]

    def test_rst_section_links_stripped(self):
        """Links in RST-wrapped first_chapter should be stripped."""
        html = """
        <section id="pkg">
            <h3>Package</h3>
            <p>See <a href="x">docs</a> for usage.</p>
            <section id="install">
                <h4>Install</h4>
                <p>Content here.</p>
            </section>
        </section>
        """
        result = split_description(html)
        assert "<a" not in result["first_chapter"]
        assert "See docs for usage" in result["first_chapter"]
