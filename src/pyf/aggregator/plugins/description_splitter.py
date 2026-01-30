"""
Description splitter plugin for weighted search fields.

Splits HTML package descriptions into multiple fields with different search
priorities:
- title: First H2 heading text (plain text)
- first_chapter: Content from start until 2nd heading
- main_content: Content between first_chapter and changelog
- changelog: Content under changelog/history headings

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


def is_changelog_heading(text):
    """Check if heading text matches a changelog pattern."""
    if not text:
        return False
    return bool(CHANGELOG_REGEX.match(text.strip()))


def get_element_text(elem):
    """Get plain text content from an element, stripping HTML tags."""
    return "".join(elem.itertext()).strip()


def serialize_elements(elements):
    """Serialize a list of elements to HTML string."""
    if not elements:
        return ""
    parts = []
    for elem in elements:
        parts.append(etree.tostring(elem, encoding="unicode", method="html"))
    return "".join(parts)


def split_description(html_content):
    """
    Split HTML description into weighted search fields.

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

        # Find all H2 and H3 headings in document order
        headings = []
        heading_elements = []
        for elem in doc.iter():
            if elem.tag in ("h2", "h3"):
                headings.append((elem, get_element_text(elem)))
                heading_elements.append(elem)

        # No headings - all content goes to first_chapter
        if not headings:
            result["first_chapter"] = html_content
            return result

        # Extract title from first heading
        first_heading, first_text = headings[0]
        result["title"] = first_text

        # Find changelog heading index
        changelog_idx = None
        for i, (elem, text) in enumerate(headings):
            if is_changelog_heading(text):
                changelog_idx = i
                break

        # Collect all direct children of the wrapper div
        children = list(doc)

        # Find positions of headings in children
        heading_positions = []
        for i, child in enumerate(children):
            if child in heading_elements:
                heading_positions.append(i)

        # Determine section boundaries
        if len(heading_positions) == 0:
            # No headings found in direct children (shouldn't happen)
            result["first_chapter"] = html_content
            return result

        # First chapter: from start to second heading (or end if only one heading)
        if len(heading_positions) > 1:
            second_heading_pos = heading_positions[1]
            first_chapter_elements = children[:second_heading_pos]
        else:
            first_chapter_elements = children[:]

        result["first_chapter"] = serialize_elements(first_chapter_elements)

        # Determine changelog boundary if exists
        changelog_start_pos = None
        if changelog_idx is not None:
            # Find the position of the changelog heading in children
            changelog_heading = headings[changelog_idx][0]
            for i, child in enumerate(children):
                if child == changelog_heading:
                    changelog_start_pos = i
                    break

        # Main content: from second heading to changelog (or end)
        if len(heading_positions) > 1:
            second_heading_pos = heading_positions[1]

            if changelog_start_pos is not None:
                # Main content is between first chapter and changelog
                main_content_elements = children[second_heading_pos:changelog_start_pos]
            else:
                # No changelog, main content is everything after first chapter
                main_content_elements = children[second_heading_pos:]

            result["main_content"] = serialize_elements(main_content_elements)

        # Changelog: from changelog heading to end
        if changelog_start_pos is not None:
            changelog_elements = children[changelog_start_pos:]
            result["changelog"] = serialize_elements(changelog_elements)

    except Exception as e:
        logger.warning(f"Failed to split description: {e}")
        # On error, put everything in first_chapter
        result["first_chapter"] = html_content

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
