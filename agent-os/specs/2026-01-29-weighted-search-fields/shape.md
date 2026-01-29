# Shaping Decisions

## Context

PyPI package descriptions contain valuable information but not all sections are equally important for search relevance. A package's title and introduction are typically more relevant to user queries than changelog entries.

## Key Decisions

### 1. Field Structure

**Decision:** Split description into 4 weighted fields rather than using a single description field.

**Rationale:** Different sections have different search value:
- Title is most distinctive (10x weight)
- First chapter is the summary/intro (5x weight)
- Main content contains features/usage (3x weight)
- Changelog is historical (1x weight)

### 2. Heading Level Detection

**Decision:** Use H2 headings as primary section markers.

**Rationale:** After rst_to_html normalizes headings (shifting H1→H2), all top-level sections in package descriptions use H2 tags. This makes detection consistent.

### 3. Changelog Detection Patterns

**Decision:** Match headings case-insensitively against: Changelog, History, Changes, Release Notes, What's New, Version, Versions

**Rationale:** These cover the most common patterns used in Python packages. The list can be extended if needed.

### 4. Plugin Ordering

**Decision:** Run description_splitter AFTER rst_to_html.

**Rationale:** Requires HTML output from rst_to_html to parse headings. Running after ensures consistent HTML structure.

### 5. Empty Field Handling

**Decision:** Use empty strings for missing sections rather than None.

**Rationale:** Typesense handles empty strings better for optional text fields, and it avoids null-checking in consumers.

## Trade-offs

### Approach: HTML Parsing vs. Text Processing

**Chosen:** HTML parsing with lxml

**Alternative:** Regex on raw text

**Why HTML:** More reliable heading detection, handles nested elements, consistent with rst_to_html patterns.

### Weight Values

**Chosen:** 10/5/3/1 ratio

**Rationale:** Provides clear differentiation without extreme disparity. Can be adjusted by consumers via query_by_weights.
