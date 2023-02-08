from docutils import core
from pkg_resources import parse_version
from pyf.aggregator.logger import logger

import readme_renderer.markdown
import readme_renderer.rst
import readme_renderer.txt
import re


_RENDERERS = {
    None: readme_renderer.rst,  # Default if description_content_type is None
    "": readme_renderer.rst,  # Default if description_content_type is None
    "text/plain": readme_renderer.txt,
    "text/x-rst": readme_renderer.rst,
    "text/markdown": readme_renderer.markdown,
}


def process(identifier, data):
    """convert package description from RST to HTML"""
    renderer = _RENDERERS.get(data.get('description_content_type'),  readme_renderer.rst)
    data["description"] = renderer.render(data.get('description'))
    # try:
    #     data["description"] = core.publish_parts(
    #         data["description"],
    #         writer_name="html",
    #         settings_overrides={"initial_header_level": 2, "doctitle": False},
    #     )["html_body"]
    # except Exception as e:
    #     logger.warn(f"Could not convert RST to HTML for {data['name']}: \n\n{e}")



def load(settings):
    return process
