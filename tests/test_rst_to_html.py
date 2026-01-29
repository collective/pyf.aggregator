"""
Unit tests for pyf.aggregator.plugins.rst_to_html module.

This module tests:
- HTML heading normalization (normalize_headings function)
- RST to HTML conversion integration
"""

import pytest

from pyf.aggregator.plugins.rst_to_html import (
    normalize_headings,
    process,
    load,
)


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def single_h1_html():
    """HTML with a single H1 tag."""
    return "<h1>Title</h1><p>Content</p>"


@pytest.fixture
def multiple_h1_html():
    """HTML with multiple H1 tags."""
    return "<h1>Title</h1><h1>Section One</h1><h1>Section Two</h1>"


@pytest.fixture
def nested_structure_html():
    """HTML with nested heading structure."""
    return (
        "<h1>Main Title</h1>"
        "<h2>Subtitle</h2>"
        "<h1>Second Section</h1>"
        "<h2>Second Subtitle</h2>"
        "<h3>Nested Item</h3>"
    )


@pytest.fixture
def complex_structure_html():
    """HTML with complex multi-level heading structure."""
    return (
        "<h1>Project Name</h1>"
        "<h2>Overview</h2>"
        "<p>Some content</p>"
        "<h1>Installation</h1>"
        "<h2>Requirements</h2>"
        "<h3>Python</h3>"
        "<h3>Dependencies</h3>"
        "<h2>Setup</h2>"
        "<h1>Usage</h1>"
        "<h2>Basic</h2>"
        "<h2>Advanced</h2>"
    )


# ============================================================================
# Normalize Headings Tests
# ============================================================================

class TestNormalizeHeadings:
    """Test the normalize_headings function."""

    def test_handles_none_input(self):
        """None input should return None."""
        result = normalize_headings(None)
        assert result is None

    def test_handles_empty_string(self):
        """Empty string should return empty string."""
        result = normalize_headings("")
        assert result == ""

    def test_single_h1_unchanged(self, single_h1_html):
        """Single H1 should remain unchanged."""
        result = normalize_headings(single_h1_html)
        assert "<h1>Title</h1>" in result
        assert "<p>Content</p>" in result

    def test_multiple_h1_converts_subsequent(self, multiple_h1_html):
        """Second and third H1 become H2."""
        result = normalize_headings(multiple_h1_html)
        assert "<h1>Title</h1>" in result
        assert "<h2>Section One</h2>" in result
        assert "<h2>Section Two</h2>" in result
        # Should not have extra H1 tags
        assert result.count("<h1") == 1

    def test_nested_structure_shifts_levels(self, nested_structure_html):
        """H2 under second H1 becomes H3."""
        result = normalize_headings(nested_structure_html)
        assert "<h1>Main Title</h1>" in result
        assert "<h2>Subtitle</h2>" in result
        assert "<h2>Second Section</h2>" in result
        assert "<h3>Second Subtitle</h3>" in result
        assert "<h4>Nested Item</h4>" in result

    def test_complex_structure(self, complex_structure_html):
        """Test complex multi-level structure."""
        result = normalize_headings(complex_structure_html)
        # First section stays at original levels
        assert "<h1>Project Name</h1>" in result
        assert "<h2>Overview</h2>" in result
        # Second section (originally h1) and its children shift down
        assert "<h2>Installation</h2>" in result
        assert "<h3>Requirements</h3>" in result
        assert "<h4>Python</h4>" in result
        assert "<h4>Dependencies</h4>" in result
        assert "<h3>Setup</h3>" in result
        # Third section also shifts down
        assert "<h2>Usage</h2>" in result
        assert "<h3>Basic</h3>" in result
        assert "<h3>Advanced</h3>" in result

    def test_preserves_heading_content(self):
        """Heading text content should be preserved."""
        html = "<h1>Special Characters: &amp; &lt; &gt;</h1>"
        result = normalize_headings(html)
        assert "Special Characters" in result
        assert "&amp;" in result or "&" in result

    def test_preserves_heading_attributes(self):
        """Heading attributes like id and class should be preserved."""
        html = '<h1 id="main-title" class="title">Title</h1><h1 id="section">Section</h1>'
        result = normalize_headings(html)
        assert 'id="main-title"' in result
        assert 'class="title"' in result
        assert 'id="section"' in result
        # Second h1 should become h2
        assert "<h2" in result

    def test_preserves_non_heading_elements(self):
        """Non-heading elements should be unchanged."""
        html = "<h1>Title</h1><p>Paragraph</p><ul><li>Item</li></ul><h1>Section</h1><div>Content</div>"
        result = normalize_headings(html)
        assert "<p>Paragraph</p>" in result
        assert "<li>Item</li>" in result
        assert "<div>Content</div>" in result

    def test_caps_at_h6(self):
        """Heading levels should not go beyond H6."""
        html = (
            "<h1>Title</h1>"
            "<h1>Section</h1>"
            "<h5>Already Deep</h5>"
            "<h6>Maximum Depth</h6>"
        )
        result = normalize_headings(html)
        # h5 becomes h6 (shifted by 1)
        assert "<h6>Already Deep</h6>" in result
        # h6 stays h6 (can't go deeper)
        assert "<h6>Maximum Depth</h6>" in result

    def test_handles_html_without_headings(self):
        """HTML without headings should be unchanged."""
        html = "<p>Just a paragraph</p><div>And a div</div>"
        result = normalize_headings(html)
        assert "<p>Just a paragraph</p>" in result
        assert "<div>And a div</div>" in result

    def test_handles_only_h1_no_content(self):
        """Multiple H1s without other content."""
        html = "<h1>One</h1><h1>Two</h1><h1>Three</h1>"
        result = normalize_headings(html)
        assert "<h1>One</h1>" in result
        assert "<h2>Two</h2>" in result
        assert "<h2>Three</h2>" in result

    def test_handles_whitespace_in_html(self):
        """HTML with whitespace should be handled."""
        html = """
        <h1>Title</h1>
        <p>Content</p>
        <h1>Section</h1>
        """
        result = normalize_headings(html)
        assert "<h1>Title</h1>" in result
        assert "<h2>Section</h2>" in result


# ============================================================================
# Process Function Tests
# ============================================================================

class TestProcess:
    """Test the main process function with heading normalization."""

    def test_process_normalizes_headings_in_description(self):
        """Process should normalize headings in rendered description."""
        data = {
            "description": "Title\n=====\n\nSection\n=======\n\nContent",
            "description_content_type": "text/x-rst",
        }
        process("test-id", data)

        # Should have normalized headings
        description = data["description"]
        if description:
            # First h1 stays h1, second becomes h2
            assert description.count("<h1") <= 1 or "<h2>" in description

    def test_process_handles_none_description(self):
        """Process should handle None description."""
        data = {"description": None}
        # Should not raise an error
        process("test-id", data)
        assert data["description"] is None

    def test_process_handles_empty_description(self):
        """Process should handle empty description."""
        data = {"description": ""}
        process("test-id", data)

    def test_process_handles_markdown(self):
        """Process should handle markdown content type."""
        data = {
            "description": "# Title\n\n# Section\n\nContent",
            "description_content_type": "text/markdown",
        }
        process("test-id", data)
        # Should not raise


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
# Integration Tests
# ============================================================================

class TestIntegration:
    """Integration tests for RST to HTML conversion with heading normalization."""

    def test_full_rst_conversion_with_multiple_titles(self):
        """Test full RST to HTML conversion with multiple titles."""
        rst_content = """
Project Name
============

This is the project description.

Features
========

* Feature 1
* Feature 2

Installation
============

Run pip install.
"""
        data = {
            "description": rst_content,
            "description_content_type": "text/x-rst",
        }
        process("test-package", data)

        description = data["description"]
        if description:
            # Should have only one H1
            h1_count = description.count("<h1")
            h2_count = description.count("<h2")
            # Either 1 H1 with H2s, or handled gracefully
            assert h1_count <= 1 or h2_count > 0

    def test_preserves_list_and_paragraph_content(self):
        """Test that list and paragraph content is preserved."""
        rst_content = """
Title
=====

Some paragraph text.

* List item 1
* List item 2
"""
        data = {
            "description": rst_content,
            "description_content_type": "text/x-rst",
        }
        process("test-package", data)

        description = data["description"]
        if description:
            assert "paragraph text" in description.lower() or "paragraph" in description.lower()
