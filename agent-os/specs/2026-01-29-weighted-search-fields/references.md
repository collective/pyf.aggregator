# Code References

## Files to Create

- `src/pyf/aggregator/plugins/description_splitter.py` - New plugin
- `tests/test_description_splitter.py` - Tests for new plugin

## Files to Modify

- `src/pyf/aggregator/plugins/__init__.py:14` - Register plugin after rst_to_html
- `src/pyf/aggregator/db.py:97-98` - Add new schema fields after description
- `AGENTS.md` - Document new functionality

## Reference Files (Patterns to Follow)

- `src/pyf/aggregator/plugins/rst_to_html.py` - Plugin structure, lxml usage
- `tests/test_rst_to_html.py` - Test patterns for plugin testing

## Key Dependencies

- `lxml` - Already in project dependencies, used for HTML parsing
- `readme_renderer` - Used by rst_to_html for RST→HTML conversion

## Typesense Documentation

- [Search Parameters](https://typesense.org/docs/0.25.0/api/search.html#query-parameters)
- [query_by_weights](https://typesense.org/docs/0.25.0/api/search.html#query-parameters) - Controls field weighting
