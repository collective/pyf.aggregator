from pkg_resources import parse_version

from docutils import core
import re


def process(identifier, data):
    """convert package description from RST to HTML"""
    data["description"] = core.publish_parts(
        data["description"],
        writer_name="html",
        settings_overrides={"initial_header_level": 2, "doctitle": False},
    )["html_body"]


def load(settings):
    return process
