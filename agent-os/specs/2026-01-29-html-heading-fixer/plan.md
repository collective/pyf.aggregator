# Plan: HTML Heading Structure Fixer

## Summary

Integrate a heading normalization function into the existing `rst_to_html` plugin to fix HTML heading structure from PyPI descriptions. The function will convert multiple H1 tags to a proper heading hierarchy (first H1 stays H1, subsequent H1s become H2, their subheadings become H3, etc.).

**Location:** `src/pyf/aggregator/plugins/rst_to_html.py`

## Implementation Tasks

1. Write tests for heading normalization (TDD)
2. Implement `normalize_headings` function
3. Integrate into `process` function

## Algorithm

1. Parse HTML with lxml
2. Find all heading elements (h1-h6) in document order
3. Track `offset = 0`
4. When encountering the first H1: do nothing
5. When encountering a subsequent H1: set `offset = 1`, convert to H2
6. For all following headings while `offset > 0`:
   - Shift heading level down by offset (h2->h3, h3->h4, etc.)
   - If new H1 encountered, increment offset
7. Cap heading levels at H6 (don't go beyond)
8. Return modified HTML

## Files Modified

| File | Changes |
|------|---------|
| `src/pyf/aggregator/plugins/rst_to_html.py` | Add `normalize_headings()` function, update `process()` |
| `tests/test_rst_to_html.py` | New test file for heading normalization |
