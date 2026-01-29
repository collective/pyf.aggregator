from pyf.aggregator.logger import logger

import readme_renderer.markdown
import readme_renderer.rst
import readme_renderer.txt
from lxml import html as lxml_html
from lxml import etree


_RENDERERS = {
    None: readme_renderer.rst,  # Default if description_content_type is None
    "": readme_renderer.rst,  # Default if description_content_type is None
    "text/plain": readme_renderer.txt,
    "text/x-rst": readme_renderer.rst,
    "text/markdown": readme_renderer.markdown,
}

HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}


def normalize_headings(html_content):
    """
    Normalize heading structure so only one H1 exists.

    Subsequent H1 tags are converted to H2, and all headings
    that follow them are shifted down by one level.

    Args:
        html_content: HTML string to normalize

    Returns:
        Normalized HTML string, or original value if None/empty
    """
    if not html_content:
        return html_content

    try:
        # Parse HTML - wrap in div to handle fragments
        doc = lxml_html.fragment_fromstring(
            html_content, create_parent="div"
        )

        # Find all heading elements in document order
        headings = []
        for elem in doc.iter():
            if elem.tag in HEADING_TAGS:
                headings.append(elem)

        if not headings:
            return html_content

        # Track offset: 0 until we see second H1, then 1
        seen_first_h1 = False
        offset = 0

        for heading in headings:
            current_level = int(heading.tag[1])

            if heading.tag == "h1":
                if not seen_first_h1:
                    # First H1 - keep as is
                    seen_first_h1 = True
                else:
                    # Subsequent H1 - convert to H2
                    offset = 1
                    heading.tag = "h2"
            elif offset > 0:
                # Shift other headings down by offset
                new_level = min(current_level + offset, 6)
                heading.tag = f"h{new_level}"

        # Serialize back to HTML string
        result_parts = []
        for child in doc:
            result_parts.append(
                etree.tostring(child, encoding="unicode", method="html")
            )
        # Also include text directly in the wrapper div
        if doc.text:
            result_parts.insert(0, doc.text)

        return "".join(result_parts)

    except Exception as e:
        logger.warning(f"Failed to normalize headings: {e}")
        return html_content


def process(identifier, data):
    """Convert package description from RST to HTML and normalize headings."""
    description = data.get('description')
    if description is None:
        return

    renderer = _RENDERERS.get(data.get('description_content_type'), readme_renderer.rst)
    html_output = renderer.render(description)
    data["description"] = normalize_headings(html_output)


def load(settings):
    return process
