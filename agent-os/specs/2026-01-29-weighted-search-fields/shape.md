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

**Decision:** Use all heading levels (H1-H6) as section markers.

**Update (2026-02-02):** Originally used only H2/H3 headings. Updated to detect all levels (H1-H6) for broader compatibility with packages that have unconventional heading structures after rst_to_html normalization. Some packages may only have H4 or H5 headings.

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

### 6. RST Section Wrapper Handling

**Decision:** Flatten section wrappers when processing RST-rendered HTML.

**Update (2026-02-02):** RST-rendered HTML wraps content in `<section>` elements, causing headings to not be direct children of the wrapper. The splitter now:

1. Recursively flattens section structure for boundary detection
2. Strips section wrapper tags from output to produce clean HTML
3. Uses the first heading (any level H1-H6) to separate first_chapter from main_content

**Example RST HTML:**
```html
<section id="package-name">
    <h3>Package Name</h3>
    <p>Introduction paragraph.</p>
    <section id="features">
        <h4>Features</h4>
        <ul>...</ul>
    </section>
</section>
```

**Expected first_chapter output:**
```html
<h3>Package Name</h3><p>Introduction paragraph.</p>
```

**Rationale:**
- RST uses `<section id="...">` elements to wrap content under each heading
- Markdown renders headings as direct children (flat structure)
- The splitter must handle both formats for compatibility
- Section wrappers are stripped from output to produce clean, consistent HTML
