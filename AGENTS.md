# CRITICAL RULES

## typesense

### Weighted Search Fields

The `description_splitter` plugin extracts weighted search fields from package descriptions:

| Field | Weight | Description |
|-------|--------|-------------|
| `title` | 10x | First H2 heading text (plain text) |
| `first_chapter` | 5x | Summary + content until 2nd heading |
| `main_content` | 3x | Content between first_chapter and changelog |
| `changelog` | 1x | Content under changelog/history headings |

**Recommended search configuration for consumers:**
```
query_by: "name,title,first_chapter,main_content,changelog"
query_by_weights: "10,10,5,3,1"
```

## Testing Patterns

- Use `responses` library to mock HTTP requests
- Use `pytest` fixtures from `conftest.py` for sample data
- Celery tasks use eager mode (`task_always_eager=True`) in tests
- Mock Typesense client for unit tests without real server

## Environment Variables

Required in `.env`:
```ini
TYPESENSE_HOST=localhost
TYPESENSE_PORT=8108
TYPESENSE_PROTOCOL=http
TYPESENSE_API_KEY=<secret>
TYPESENSE_TIMEOUT=120
GITHUB_TOKEN=<github_token>
REDIS_HOST=localhost:6379

# Optional: Default profile for all CLI commands
DEFAULT_PROFILE=plone
```

When `DEFAULT_PROFILE` is set, all `pyfa` subcommands (`pypi`, `github`, `downloads`, `manage`) will use it as the default profile. The `-p` CLI argument overrides this environment variable.

## Critical Rules

- Use `RUF` for formating
- Package uses namespace: `pyf.aggregator`
- always write tests first, TDD
- All CLI commands must be run with `uv run` prefix (e.g., `uv run pyfa github -p plone`)
- run tests in a subagent
- always update README when things change or new features are added
- documentation is written in the README not in doc strings!
- prefer using skills over web search or perplexity mcp

## Stop Hook Behavior (MANDATORY)

A stop hook runs `ruff format`, `ruff check --fix`, and `pytest` before allowing you to stop.

When the stop hook blocks you:
1. **DO NOT ask the user for permission** - fix issues immediately
2. **DO NOT stop** until all checks pass
3. **Automatically continue fixing** and retry stopping after each fix
4. **Loop until clean** - treat a blocked stop as a command to fix and retry
5. After 3+ failed attempts, provide a status update but **keep fixing**