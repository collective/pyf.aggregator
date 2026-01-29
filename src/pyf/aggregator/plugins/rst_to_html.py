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
    Shift all headings down by one level for proper document hierarchy.

    The UI provides the H1 tag for the project/page title, so article
    content should start at H2 to maintain semantic heading structure.

    Args:
        html_content: HTML string to normalize

    Returns:
        Normalized HTML string with all headings shifted down one level,
        or original value if None/empty
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

        for heading in headings:
            current_level = int(heading.tag[1])
            new_level = min(current_level + 1, 6)
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
