# Shaping: HTML Heading Structure Fixer

## Problem

PyPI package descriptions often contain multiple H1 tags because:
- RST titles converted to H1s
- Package READMEs start with their own H1
- Multiple sections using top-level heading syntax

This breaks semantic HTML structure and accessibility.

## Scope

- **In scope**: Normalize heading hierarchy in rendered HTML
- **Out of scope**: Modifying source RST/Markdown, handling non-heading elements

## Decisions

1. **Location**: Add to existing `rst_to_html.py` plugin (no new plugin needed)
2. **Parser**: Use lxml for HTML parsing (already a dependency via readme-renderer)
3. **Strategy**: Offset-based shifting rather than tree reconstruction
4. **Edge cases**: Cap at H6, handle empty/None input gracefully
