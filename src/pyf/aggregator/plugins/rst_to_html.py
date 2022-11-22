from docutils import core
from pkg_resources import parse_version
from pyf.aggregator.logger import logger

import re


def process(identifier, data):
    """convert package description from RST to HTML"""
    try:
        data["description"] = core.publish_parts(
            data["description"],
            writer_name="html",
            settings_overrides={"initial_header_level": 2, "doctitle": False},
        )["html_body"]
    except Exception as e:
        logger.warn(f"Could not convert RST to HTML for {data['name']}: \n\n{e}")



def load(settings):
    return process
