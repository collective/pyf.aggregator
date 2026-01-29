# Weighted Search Fields for PyPI Content Sections

Split PyPI package descriptions into multiple Typesense fields with different search priorities to improve relevance.

## Summary

- **title** (10x weight): First H2 heading from description
- **first_chapter** (5x weight): Summary + content until 2nd heading
- **main_content** (3x weight): All content above changelog sections
- **changelog** (1x weight): Content in changelog/history sections

## Implementation Tasks

### Task 1: Create description_splitter Plugin

**File:** `src/pyf/aggregator/plugins/description_splitter.py`

New plugin that runs AFTER rst_to_html to parse HTML and extract:
- `title`: First H2 heading text (plain text, stripped of HTML)
- `first_chapter`: Summary field + content from start until 2nd heading
- `main_content`: Content between first_chapter and changelog
- `changelog`: Content under changelog headings

**Changelog Detection** - H2/H3 headings matching (case-insensitive):
- Changelog, History, Changes, Release Notes, What's New, Version(s)

**Edge Cases:**
- No headings → all content in first_chapter
- No changelog heading → all content after first_chapter in main_content
- Empty/None description → all fields empty strings

Uses `lxml` (already in dependencies) following rst_to_html.py patterns.

### Task 2: Register Plugin

**File:** `src/pyf/aggregator/plugins/__init__.py`

Add import and register `description_splitter` AFTER `rst_to_html`.

### Task 3: Update Typesense Schema

**File:** `src/pyf/aggregator/db.py`

Add 4 new fields after `description` field:
```python
{"name": "title", "type": "string", "optional": True},
{"name": "first_chapter", "type": "string", "optional": True},
{"name": "main_content", "type": "string", "optional": True},
{"name": "changelog", "type": "string", "optional": True},
```

### Task 4: Write Tests

**File:** `tests/test_description_splitter.py`

Core tests (TDD - write first):
- Title extraction from first H2
- First chapter includes summary + content until 2nd heading
- Changelog detection and extraction
- Main content excludes changelog
- Edge cases: no headings, no changelog, empty description

### Task 5: Update Documentation

**File:** `AGENTS.md`

Document:
- New plugin purpose and configuration
- New Typesense fields
- Recommended search query configuration for consumers:
  ```
  query_by: "name,title,first_chapter,main_content,changelog"
  query_by_weights: "10,10,5,3,1"
  ```

## Verification

1. Run tests: `uv run pytest tests/test_description_splitter.py -v`
2. Run full test suite: `uv run pytest`
3. Recreate collection: `uv run pyfupdater --recreate-collection -p plone`
4. Re-index sample packages: `uv run pyfaggregator -f -p plone --package plone.api`
5. Verify in Typesense that new fields are populated

## Critical Files

- `src/pyf/aggregator/plugins/description_splitter.py` (CREATE)
- `src/pyf/aggregator/plugins/__init__.py` (MODIFY)
- `src/pyf/aggregator/db.py` (MODIFY)
- `tests/test_description_splitter.py` (CREATE)
- `AGENTS.md` (MODIFY)
- `src/pyf/aggregator/plugins/rst_to_html.py` (REFERENCE - patterns to follow)
