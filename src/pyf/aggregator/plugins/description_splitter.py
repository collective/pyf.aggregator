"""
Description splitter plugin for weighted search fields.

Splits HTML package descriptions into multiple fields with different search
priorities:
- title: First heading text (plain text, any level h1-h6)
- first_chapter: Content from start until first excluded heading (links/images stripped)
- main_content: Content between first_chapter and changelog
- changelog: Content under changelog/history headings

First chapter extraction rules:
- If content starts with a heading: include that heading + text until 2nd heading
- If content starts with text (no heading): include text until 1st heading (exclude it)

Detects all heading levels (H1-H6) as section markers to support packages
with varying heading structures after rst_to_html normalization.

Runs AFTER rst_to_html plugin which converts descriptions to HTML.
"""

from pyf.aggregator.logger import logger
from lxml import html as lxml_html
from lxml import etree
import re

# Changelog heading patterns (case-insensitive)
CHANGELOG_PATTERNS = [
    r"^changelog$",
    r"^history$",
    r"^changes$",
    r"^release\s*notes$",
    r"^what'?s\s*new$",
    r"^versions?$",
]

CHANGELOG_REGEX = re.compile("|".join(CHANGELOG_PATTERNS), re.IGNORECASE)

# All heading tags to detect as section markers
HEADING_TAGS = ("h1", "h2", "h3", "h4", "h5", "h6")


def flatten_sections(element):
    """
    Flatten section wrappers to create a linear content list.

    RST-rendered HTML wraps content in <section> elements. This function
    recursively extracts all content elements, skipping section wrappers,
    to create a flat list for boundary detection.

    Returns list of (element, is_heading) tuples.
    """
    result = []

    def process_children(parent):
        for child in parent:
            if child.tag == "section":
                # Recurse into section, skipping the wrapper
                process_children(child)
            else:
                is_heading = child.tag in HEADING_TAGS
                result.append((child, is_heading))

    process_children(element)
    return result


def serialize_flat_content(flat_content, start_idx, end_idx=None):
    """
    Serialize a range of flattened content to HTML string.

    Args:
        flat_content: List of (element, is_heading) tuples
        start_idx: Starting index (inclusive)
        end_idx: Ending index (exclusive), None for end of list

    Returns:
        HTML string of serialized elements
    """
    if end_idx is None:
        end_idx = len(flat_content)

    if start_idx >= len(flat_content) or start_idx >= end_idx:
        return ""

    parts = []
    for elem, _ in flat_content[start_idx:end_idx]:
        parts.append(etree.tostring(elem, encoding="unicode", method="html"))
    return "".join(parts)


def is_changelog_heading(text):
    """Check if heading text matches a changelog pattern."""
    if not text:
        return False
    return bool(CHANGELOG_REGEX.match(text.strip()))


def get_element_text(elem):
    """Get plain text content from an element, stripping HTML tags."""
    return "".join(elem.itertext()).strip()


def strip_links(html_string):
    """
    Remove <a> tags from HTML while preserving their text content.

    Example: '<a href="...">Click here</a>' becomes 'Click here'
    """
    if not html_string:
        return html_string
    doc = lxml_html.fragment_fromstring(html_string, create_parent="div")
    for link in doc.iter("a"):
        # Replace link with its text content
        link.drop_tag()
    # Serialize back, removing wrapper div
    return etree.tostring(doc, encoding="unicode", method="html")[5:-6]


def strip_images(html_string):
    """Remove <img> tags from HTML."""
    if not html_string:
        return html_string
    doc = lxml_html.fragment_fromstring(html_string, create_parent="div")
    for img in doc.iter("img"):
        img.drop_tree()  # Remove completely
    return etree.tostring(doc, encoding="unicode", method="html")[5:-6]


def split_description(html_content):
    """
    Split HTML description into weighted search fields.

    Handles both flat HTML (from Markdown) and section-wrapped HTML (from RST).
    RST-rendered HTML wraps content in <section> elements which are flattened
    for boundary detection and stripped from output.

    Args:
        html_content: HTML string (output from rst_to_html plugin)

    Returns:
        dict with keys: title, first_chapter, main_content, changelog
    """
    result = {
        "title": "",
        "first_chapter": "",
        "main_content": "",
        "changelog": "",
    }

    if not html_content or not html_content.strip():
        return result

    try:
        # Parse HTML - wrap in div to handle fragments
        doc = lxml_html.fragment_fromstring(html_content, create_parent="div")

        # Flatten section wrappers to create linear content list
        flat_content = flatten_sections(doc)

        # No content after flattening
        if not flat_content:
            result["first_chapter"] = html_content
            return result

        # Find all heading positions in flattened content
        heading_positions = []
        for i, (elem, is_heading) in enumerate(flat_content):
            if is_heading:
                heading_positions.append(i)

        # No headings - all content goes to first_chapter
        if not heading_positions:
            result["first_chapter"] = serialize_flat_content(flat_content, 0)
            return result

        # Extract title from first heading
        first_heading_idx = heading_positions[0]
        first_heading_elem, _ = flat_content[first_heading_idx]
        result["title"] = get_element_text(first_heading_elem)

        # Find changelog heading position in flat content
        changelog_flat_idx = None
        for pos in heading_positions:
            elem, _ = flat_content[pos]
            if is_changelog_heading(get_element_text(elem)):
                changelog_flat_idx = pos
                break

        # Check if content starts with a heading (first element is a heading)
        starts_with_heading = heading_positions and heading_positions[0] == 0

        if starts_with_heading:
            # Content starts with heading - include it, stop at second heading
            if len(heading_positions) > 1:
                result["first_chapter"] = serialize_flat_content(
                    flat_content, 0, heading_positions[1]
                )
            else:
                # Only one heading at start, include everything
                result["first_chapter"] = serialize_flat_content(flat_content, 0)
        else:
            # Content starts with text - stop at first heading
            if heading_positions:
                result["first_chapter"] = serialize_flat_content(
                    flat_content, 0, heading_positions[0]
                )
            else:
                # No headings, include everything
                result["first_chapter"] = serialize_flat_content(flat_content, 0)

        # Main content: from first excluded heading to changelog (or end)
        if starts_with_heading:
            # Started with heading, main_content starts at second heading
            if len(heading_positions) > 1:
                main_start = heading_positions[1]
                if changelog_flat_idx is not None:
                    result["main_content"] = serialize_flat_content(
                        flat_content, main_start, changelog_flat_idx
                    )
                else:
                    result["main_content"] = serialize_flat_content(
                        flat_content, main_start
                    )
        else:
            # Started with text, main_content starts at first heading
            if heading_positions:
                main_start = heading_positions[0]
                if changelog_flat_idx is not None:
                    result["main_content"] = serialize_flat_content(
                        flat_content, main_start, changelog_flat_idx
                    )
                else:
                    result["main_content"] = serialize_flat_content(
                        flat_content, main_start
                    )

        # Changelog: from changelog heading to end
        if changelog_flat_idx is not None:
            result["changelog"] = serialize_flat_content(
                flat_content, changelog_flat_idx
            )

    except Exception as e:
        logger.warning(f"Failed to split description: {e}")
        # On error, put everything in first_chapter
        result["first_chapter"] = html_content

    # Strip links from first_chapter (keep text, remove <a> tags)
    result["first_chapter"] = strip_links(result["first_chapter"])
    # Strip images from first_chapter
    result["first_chapter"] = strip_images(result["first_chapter"])

    return result


def process(identifier, data):
    """
    Split package description into weighted search fields.

    Adds title, first_chapter, main_content, changelog fields to data dict.
    """
    description = data.get("description")
    summary = data.get("summary", "")

    # Split the HTML description
    sections = split_description(description)

    # Log warnings for empty sections (only if description was provided)
    if description and description.strip():
        if not sections["first_chapter"]:
            logger.warning(
                f"Package '{identifier}': first_chapter is empty after splitting"
            )
        if not sections["main_content"]:
            logger.warning(
                f"Package '{identifier}': main_content is empty after splitting"
            )

    # Add summary to first_chapter
    if summary:
        if sections["first_chapter"]:
            sections["first_chapter"] = f"{summary}\n\n{sections['first_chapter']}"
        else:
            sections["first_chapter"] = summary

    # Update data with sections
    data["title"] = sections["title"]
    data["first_chapter"] = sections["first_chapter"]
    data["main_content"] = sections["main_content"]
    data["changelog"] = sections["changelog"]


def load(settings):
    return process
