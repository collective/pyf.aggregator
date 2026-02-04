"""Screenshot detection for package documentation health scoring.

This module detects meaningful screenshots in package README HTML content,
filtering out badges and small images to only count documentation-worthy
visuals.
"""

import re
from functools import lru_cache
from io import BytesIO
from typing import Optional

import requests
from lxml import html


# Badge URL patterns to filter out
BADGE_PATTERNS = [
    r"shields\.io",
    r"img\.shields\.io",
    r"badge\.fury\.io",
    r"travis-ci\.(org|com)",
    r"codecov\.io",
    r"coveralls\.io",
    r"circleci\.com",
    r"github\.com/[^/]+/[^/]+/workflows/[^/]+\.svg",
    r"github\.com/[^/]+/[^/]+/actions/workflows/[^/]+/badge",
    r"readthedocs\.org/[^/]+/badge",
    r"pypi\.org/badges",
    r"pypi\.python\.org/[^/]*badge",
    r"ci\.appveyor\.com",
    r"snyk\.io",
    r"codacy\.com",
    r"sonarcloud\.io",
    r"badge",  # Generic badge pattern as fallback
]

# Compile patterns for efficiency
BADGE_REGEX = re.compile("|".join(BADGE_PATTERNS), re.IGNORECASE)

# Minimum width for a screenshot to be considered meaningful
MIN_SCREENSHOT_WIDTH = 200


def is_badge_url(url: str) -> bool:
    """Check if a URL is a badge service URL.

    Args:
        url: The image URL to check

    Returns:
        True if the URL matches known badge patterns
    """
    if not url:
        return False
    return bool(BADGE_REGEX.search(url))


def parse_width_from_style(style: str) -> Optional[int]:
    """Parse width value from CSS style attribute.

    Args:
        style: CSS style string (e.g., "width: 300px; height: 200px")

    Returns:
        Width in pixels if found, None otherwise
    """
    if not style:
        return None

    # Match width property with px value
    width_match = re.search(r"width\s*:\s*(\d+)(?:px)?", style, re.IGNORECASE)
    if width_match:
        return int(width_match.group(1))

    return None


def parse_width_from_attribute(width_attr: str) -> Optional[int]:
    """Parse width from HTML width attribute.

    Args:
        width_attr: Width attribute value (e.g., "300" or "300px")

    Returns:
        Width in pixels if valid, None otherwise
    """
    if not width_attr:
        return None

    # Strip 'px' suffix if present and convert to int
    width_str = width_attr.rstrip("px").strip()
    try:
        return int(width_str)
    except ValueError:
        return None


@lru_cache(maxsize=100)
def fetch_image_dimensions(url: str) -> Optional[int]:
    """Fetch image and return its width.

    Results are cached to avoid repeated fetches for the same URL.

    Args:
        url: The image URL to fetch

    Returns:
        Image width in pixels if successful, None otherwise
    """
    try:
        # Use PIL to get image dimensions
        from PIL import Image

        response = requests.get(url, timeout=5, stream=True)
        response.raise_for_status()

        # Read only the header to get dimensions (more efficient)
        img = Image.open(BytesIO(response.content))
        return img.width
    except Exception:
        # Any error (network, invalid image, etc.) returns None
        return None


def get_image_width(img_element, src: str) -> Optional[int]:
    """Get the width of an image from element attributes or by fetching.

    Tries in order:
    1. HTML width attribute
    2. CSS style attribute
    3. Fetch image and read dimensions

    Args:
        img_element: lxml img element
        src: Image source URL

    Returns:
        Image width in pixels if determinable, None otherwise
    """
    # Try HTML width attribute first
    width_attr = img_element.get("width")
    if width_attr:
        width = parse_width_from_attribute(width_attr)
        if width is not None:
            return width

    # Try CSS style attribute
    style = img_element.get("style")
    if style:
        width = parse_width_from_style(style)
        if width is not None:
            return width

    # Fall back to fetching the image
    if src and src.startswith(("http://", "https://")):
        return fetch_image_dimensions(src)

    return None


def detect_screenshots(html_content: str) -> dict:
    """Detect meaningful screenshots in HTML content.

    Finds images that are:
    - Not from badge services
    - At least MIN_SCREENSHOT_WIDTH pixels wide

    Args:
        html_content: HTML string (e.g., rendered README)

    Returns:
        dict with:
        - has_screenshots: bool indicating if qualifying screenshots found
        - screenshot_count: number of qualifying screenshots
        - screenshots: list of qualifying image URLs
    """
    result = {
        "has_screenshots": False,
        "screenshot_count": 0,
        "screenshots": [],
    }

    if not html_content:
        return result

    try:
        doc = html.fromstring(html_content)
    except Exception:
        return result

    # Find all img elements
    img_elements = doc.xpath("//img")

    for img in img_elements:
        src = img.get("src", "")

        # Skip if no source
        if not src:
            continue

        # Skip badge URLs
        if is_badge_url(src):
            continue

        # Get image width
        width = get_image_width(img, src)

        # Only count if width meets minimum requirement
        if width is not None and width >= MIN_SCREENSHOT_WIDTH:
            result["screenshots"].append(src)

    result["screenshot_count"] = len(result["screenshots"])
    result["has_screenshots"] = result["screenshot_count"] > 0

    return result
