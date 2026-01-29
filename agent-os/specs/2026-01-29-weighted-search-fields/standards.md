# Applicable Standards

## Code Standards

### Python Style
- Follow existing plugin patterns in `rst_to_html.py`
- Use type hints where appropriate
- Use docstrings for public functions

### Testing
- TDD: Write tests before implementation
- Use pytest fixtures for test data
- Follow existing test patterns in `test_rst_to_html.py`

### Logging
- Use `pyf.aggregator.logger` for all logging
- Log warnings for parsing failures
- Don't log on successful processing

## Typesense Standards

### Field Configuration
- New text fields should be `optional: True`
- Search fields should be indexed (default)
- Use `type: "string"` for text content

### Schema Evolution
- New fields are additive (backwards compatible)
- Existing data will have empty values for new fields until re-indexed

## Plugin System Standards

### Registration Order
- Plugins that depend on others must be registered after their dependencies
- `description_splitter` depends on `rst_to_html` (requires HTML input)

### Plugin Interface
- Must export `load(settings)` function
- Must return a callable `process(identifier, data)` function
- Process function modifies `data` dict in place
