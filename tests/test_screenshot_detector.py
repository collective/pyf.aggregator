"""
Unit tests for pyf.aggregator.plugins.screenshot_detector module.

This module tests:
- Badge URL detection for various badge services
- Width parsing from HTML attributes
- Width parsing from CSS style attributes
- Image fetching with mocked responses
- Full screenshot detection with mixed content
"""

from unittest.mock import patch, MagicMock

from pyf.aggregator.plugins.screenshot_detector import (
    is_badge_url,
    parse_width_from_style,
    parse_width_from_attribute,
    fetch_image_dimensions,
    get_image_width,
    detect_screenshots,
    MIN_SCREENSHOT_WIDTH,
)


# ============================================================================
# Badge URL Detection Tests
# ============================================================================


class TestIsBadgeUrl:
    """Test the is_badge_url function."""

    def test_shields_io_badge(self):
        """Test shields.io badge detection."""
        assert is_badge_url("https://shields.io/badge/foo-bar")
        assert is_badge_url("https://img.shields.io/badge/foo-bar.svg")
        assert is_badge_url("https://img.shields.io/pypi/v/package.svg")

    def test_badge_fury_badge(self):
        """Test badge.fury.io detection."""
        assert is_badge_url("https://badge.fury.io/py/package.svg")

    def test_travis_ci_badge(self):
        """Test Travis CI badge detection."""
        assert is_badge_url("https://travis-ci.org/user/repo.svg")
        assert is_badge_url("https://travis-ci.com/user/repo.svg")

    def test_codecov_badge(self):
        """Test Codecov badge detection."""
        assert is_badge_url(
            "https://codecov.io/gh/user/repo/branch/main/graph/badge.svg"
        )

    def test_coveralls_badge(self):
        """Test Coveralls badge detection."""
        assert is_badge_url("https://coveralls.io/repos/github/user/repo/badge.svg")

    def test_circleci_badge(self):
        """Test CircleCI badge detection."""
        assert is_badge_url("https://circleci.com/gh/user/repo.svg")

    def test_github_actions_badge(self):
        """Test GitHub Actions workflow badge detection."""
        assert is_badge_url("https://github.com/user/repo/workflows/CI/badge.svg")
        assert is_badge_url(
            "https://github.com/user/repo/actions/workflows/test.yml/badge.svg"
        )

    def test_readthedocs_badge(self):
        """Test Read the Docs badge detection."""
        assert is_badge_url("https://readthedocs.org/projects/package/badge/")

    def test_pypi_badge(self):
        """Test PyPI badge detection."""
        assert is_badge_url("https://pypi.org/badges/package/v/1.0.0")
        assert is_badge_url("https://pypi.python.org/static/badge.svg")

    def test_appveyor_badge(self):
        """Test AppVeyor badge detection."""
        assert is_badge_url("https://ci.appveyor.com/api/projects/status/...")

    def test_snyk_badge(self):
        """Test Snyk badge detection."""
        assert is_badge_url("https://snyk.io/test/github/user/repo/badge.svg")

    def test_codacy_badge(self):
        """Test Codacy badge detection."""
        assert is_badge_url("https://codacy.com/project/badge/grade/...")

    def test_sonarcloud_badge(self):
        """Test SonarCloud badge detection."""
        assert is_badge_url("https://sonarcloud.io/api/project_badges/...")

    def test_generic_badge_pattern(self):
        """Test generic badge pattern detection."""
        assert is_badge_url("https://example.com/some-badge.svg")

    def test_not_badge_url(self):
        """Test that regular image URLs are not detected as badges."""
        assert not is_badge_url("https://example.com/screenshot.png")
        assert not is_badge_url("https://example.com/images/demo.jpg")
        assert not is_badge_url(
            "https://github.com/user/repo/raw/main/docs/screenshot.png"
        )

    def test_empty_and_none_url(self):
        """Test handling of empty and None URLs."""
        assert not is_badge_url("")
        assert not is_badge_url(None)


# ============================================================================
# Width Parsing Tests
# ============================================================================


class TestParseWidthFromStyle:
    """Test the parse_width_from_style function."""

    def test_width_with_px(self):
        """Test parsing width with px suffix."""
        assert parse_width_from_style("width: 300px") == 300
        assert parse_width_from_style("width:300px") == 300
        assert parse_width_from_style("width: 300px;") == 300

    def test_width_without_px(self):
        """Test parsing width without px suffix."""
        assert parse_width_from_style("width: 300") == 300
        assert parse_width_from_style("width:300") == 300

    def test_width_in_complex_style(self):
        """Test parsing width from complex style string."""
        assert parse_width_from_style("height: 200px; width: 400px; border: 1px") == 400
        assert parse_width_from_style("margin: 10px; width: 500px") == 500

    def test_case_insensitive(self):
        """Test case insensitive parsing."""
        assert parse_width_from_style("WIDTH: 300px") == 300
        assert parse_width_from_style("Width: 300px") == 300

    def test_empty_and_none_style(self):
        """Test handling of empty and None style."""
        assert parse_width_from_style("") is None
        assert parse_width_from_style(None) is None

    def test_no_width_property(self):
        """Test style without width property."""
        assert parse_width_from_style("height: 200px") is None
        assert parse_width_from_style("color: red") is None


class TestParseWidthFromAttribute:
    """Test the parse_width_from_attribute function."""

    def test_numeric_value(self):
        """Test parsing numeric width attribute."""
        assert parse_width_from_attribute("300") == 300
        assert parse_width_from_attribute("500") == 500

    def test_value_with_px(self):
        """Test parsing width attribute with px suffix."""
        assert parse_width_from_attribute("300px") == 300
        assert parse_width_from_attribute("500px") == 500

    def test_value_with_whitespace(self):
        """Test parsing width attribute with whitespace."""
        assert parse_width_from_attribute(" 300 ") == 300
        assert parse_width_from_attribute("300 ") == 300

    def test_empty_and_none(self):
        """Test handling of empty and None values."""
        assert parse_width_from_attribute("") is None
        assert parse_width_from_attribute(None) is None

    def test_invalid_value(self):
        """Test handling of invalid values."""
        assert parse_width_from_attribute("auto") is None
        assert parse_width_from_attribute("100%") is None
        assert parse_width_from_attribute("abc") is None


# ============================================================================
# Image Fetching Tests
# ============================================================================


class TestFetchImageDimensions:
    """Test the fetch_image_dimensions function."""

    @patch("pyf.aggregator.plugins.screenshot_detector.requests.get")
    def test_successful_fetch(self, mock_get):
        """Test successful image dimension fetch."""
        # Create a minimal valid PNG (1x1 pixel)
        from PIL import Image
        import io

        img = Image.new("RGB", (400, 300))
        img_bytes = io.BytesIO()
        img.save(img_bytes, format="PNG")
        img_bytes.seek(0)

        mock_response = MagicMock()
        mock_response.content = img_bytes.read()
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        # Clear cache before test
        fetch_image_dimensions.cache_clear()

        result = fetch_image_dimensions("https://example.com/image.png")
        assert result == 400

    @patch("pyf.aggregator.plugins.screenshot_detector.requests.get")
    def test_network_error(self, mock_get):
        """Test handling of network errors."""
        mock_get.side_effect = Exception("Network error")

        # Clear cache before test
        fetch_image_dimensions.cache_clear()

        result = fetch_image_dimensions("https://example.com/image.png")
        assert result is None

    @patch("pyf.aggregator.plugins.screenshot_detector.requests.get")
    def test_invalid_image(self, mock_get):
        """Test handling of invalid image data."""
        mock_response = MagicMock()
        mock_response.content = b"not an image"
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        # Clear cache before test
        fetch_image_dimensions.cache_clear()

        result = fetch_image_dimensions("https://example.com/invalid.png")
        assert result is None


# ============================================================================
# Get Image Width Tests
# ============================================================================


class TestGetImageWidth:
    """Test the get_image_width function."""

    def test_width_from_html_attribute(self):
        """Test getting width from HTML width attribute."""
        from lxml import html as lxml_html

        doc = lxml_html.fromstring('<img src="test.png" width="400">')
        img = doc

        result = get_image_width(img, "test.png")
        assert result == 400

    def test_width_from_style_attribute(self):
        """Test getting width from CSS style attribute."""
        from lxml import html as lxml_html

        doc = lxml_html.fromstring('<img src="test.png" style="width: 500px">')
        img = doc

        result = get_image_width(img, "test.png")
        assert result == 500

    def test_html_attribute_takes_priority(self):
        """Test that HTML width attribute takes priority over style."""
        from lxml import html as lxml_html

        doc = lxml_html.fromstring(
            '<img src="test.png" width="300" style="width: 500px">'
        )
        img = doc

        result = get_image_width(img, "test.png")
        assert result == 300

    @patch("pyf.aggregator.plugins.screenshot_detector.fetch_image_dimensions")
    def test_fallback_to_fetch(self, mock_fetch):
        """Test fallback to fetching image dimensions."""
        from lxml import html as lxml_html

        mock_fetch.return_value = 600

        doc = lxml_html.fromstring('<img src="https://example.com/image.png">')
        img = doc

        result = get_image_width(img, "https://example.com/image.png")
        assert result == 600
        mock_fetch.assert_called_once_with("https://example.com/image.png")

    def test_no_fetch_for_relative_url(self):
        """Test that relative URLs don't trigger fetch."""
        from lxml import html as lxml_html

        doc = lxml_html.fromstring('<img src="images/test.png">')
        img = doc

        result = get_image_width(img, "images/test.png")
        assert result is None


# ============================================================================
# Full Screenshot Detection Tests
# ============================================================================


class TestDetectScreenshots:
    """Test the detect_screenshots function."""

    def test_no_images(self):
        """Test HTML with no images."""
        html_content = "<div><p>Hello World</p></div>"
        result = detect_screenshots(html_content)

        assert result["has_screenshots"] is False
        assert result["screenshot_count"] == 0
        assert result["screenshots"] == []

    def test_only_badges(self):
        """Test HTML with only badge images."""
        html_content = """
        <div>
            <img src="https://img.shields.io/badge/python-3.9-blue.svg" width="100">
            <img src="https://codecov.io/gh/user/repo/badge.svg" width="150">
        </div>
        """
        result = detect_screenshots(html_content)

        assert result["has_screenshots"] is False
        assert result["screenshot_count"] == 0

    def test_screenshot_with_width_attribute(self):
        """Test detection of screenshot with width attribute."""
        html_content = """
        <div>
            <img src="https://example.com/screenshot.png" width="400">
        </div>
        """
        result = detect_screenshots(html_content)

        assert result["has_screenshots"] is True
        assert result["screenshot_count"] == 1
        assert "https://example.com/screenshot.png" in result["screenshots"]

    def test_screenshot_with_style_width(self):
        """Test detection of screenshot with style width."""
        html_content = """
        <div>
            <img src="https://example.com/screenshot.png" style="width: 500px">
        </div>
        """
        result = detect_screenshots(html_content)

        assert result["has_screenshots"] is True
        assert result["screenshot_count"] == 1

    def test_small_image_filtered(self):
        """Test that small images are filtered out."""
        html_content = """
        <div>
            <img src="https://example.com/icon.png" width="50">
            <img src="https://example.com/thumb.png" width="100">
        </div>
        """
        result = detect_screenshots(html_content)

        assert result["has_screenshots"] is False
        assert result["screenshot_count"] == 0

    def test_mixed_content(self):
        """Test HTML with mixed badges, small images, and screenshots."""
        html_content = """
        <div>
            <img src="https://img.shields.io/badge/test-passing.svg" width="100">
            <img src="https://example.com/icon.png" width="32">
            <img src="https://example.com/screenshot1.png" width="400">
            <img src="https://example.com/screenshot2.png" width="600">
            <img src="https://codecov.io/badge.svg" width="80">
        </div>
        """
        result = detect_screenshots(html_content)

        assert result["has_screenshots"] is True
        assert result["screenshot_count"] == 2
        assert "https://example.com/screenshot1.png" in result["screenshots"]
        assert "https://example.com/screenshot2.png" in result["screenshots"]

    def test_empty_html(self):
        """Test handling of empty HTML content."""
        result = detect_screenshots("")

        assert result["has_screenshots"] is False
        assert result["screenshot_count"] == 0

    def test_none_html(self):
        """Test handling of None HTML content."""
        result = detect_screenshots(None)

        assert result["has_screenshots"] is False
        assert result["screenshot_count"] == 0

    def test_invalid_html(self):
        """Test handling of invalid HTML."""
        # lxml is quite tolerant, but test anyway
        result = detect_screenshots("<not valid xml")

        # Should return default result without crashing
        assert "has_screenshots" in result
        assert "screenshot_count" in result

    def test_image_without_src(self):
        """Test handling of img element without src."""
        html_content = '<img width="400">'
        result = detect_screenshots(html_content)

        assert result["has_screenshots"] is False

    def test_image_with_empty_src(self):
        """Test handling of img element with empty src."""
        html_content = '<img src="" width="400">'
        result = detect_screenshots(html_content)

        assert result["has_screenshots"] is False

    def test_boundary_width_exactly_min(self):
        """Test image with width exactly at minimum threshold."""
        html_content = f'''
        <div>
            <img src="https://example.com/image.png" width="{MIN_SCREENSHOT_WIDTH}">
        </div>
        '''
        result = detect_screenshots(html_content)

        assert result["has_screenshots"] is True
        assert result["screenshot_count"] == 1

    def test_boundary_width_below_min(self):
        """Test image with width just below minimum threshold."""
        html_content = f'''
        <div>
            <img src="https://example.com/image.png" width="{MIN_SCREENSHOT_WIDTH - 1}">
        </div>
        '''
        result = detect_screenshots(html_content)

        assert result["has_screenshots"] is False
        assert result["screenshot_count"] == 0


# ============================================================================
# Integration Tests
# ============================================================================


class TestScreenshotDetectorIntegration:
    """Integration tests for screenshot detection."""

    def test_real_readme_scenario(self):
        """Test with HTML similar to real README."""
        html_content = """
        <h1>My Package</h1>
        <p>
            <a href="https://pypi.org/project/mypackage">
                <img src="https://img.shields.io/pypi/v/mypackage.svg" alt="PyPI version">
            </a>
            <a href="https://github.com/user/mypackage/actions">
                <img src="https://github.com/user/mypackage/workflows/CI/badge.svg" alt="CI">
            </a>
        </p>
        <h2>Screenshots</h2>
        <p>
            <img src="https://raw.githubusercontent.com/user/mypackage/main/docs/screenshot.png"
                 alt="Screenshot" width="800">
        </p>
        <h2>Demo</h2>
        <p>
            <img src="https://example.com/demo.gif" style="width: 600px; border: 1px solid #ccc">
        </p>
        """

        result = detect_screenshots(html_content)

        assert result["has_screenshots"] is True
        assert result["screenshot_count"] == 2
        # Badges should be filtered out
        assert not any("shields.io" in url for url in result["screenshots"])
        assert not any("badge.svg" in url for url in result["screenshots"])
