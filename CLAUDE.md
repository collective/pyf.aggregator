# project-notes.md

This file provides guidance when working with code in this repository.

## Project Overview

pyf.aggregator is a Python Package Filter Aggregator that aggregates metadata of Python packages from PyPI, filters them by framework classifiers (Plone, Django, Flask, etc.), and stores them in Typesense for search. It enriches package data with GitHub statistics and download counts.

## Commands

### Development Setup

```shell
# Install with test dependencies
uv sync --extra test

# Start required services (Typesense + Redis)
docker-compose up -d
```

### Running Tests

```shell
# Run all tests with coverage
uv run pytest

# Run specific test file
uv run pytest tests/test_fetcher.py -v

# Run without coverage (faster)
uv run pytest --no-cov

# Run single test
uv run pytest tests/test_fetcher.py::test_function_name -v
```

### CLI Commands

**Important:** All CLI commands must be run with `uv run` prefix.

```shell
# Full fetch using a profile (recommended)
uv run pyfaggregator -f -p plone

# Incremental update
uv run pyfaggregator -i -p plone

# Refresh indexed packages from PyPI (fetches ALL versions, updates existing, removes 404s)
uv run pyfaggregator --refresh-from-pypi -p plone

# Enrich with GitHub data
uv run pyfgithub -p plone

# Enrich single package with verbose output (for debugging)
uv run pyfgithub -p plone -n plone.api -v

# Manage Typesense collections
uv run pyfupdater -ls              # List collections
uv run pyfupdater -lsn             # List collection names
uv run pyfupdater --add-alias -s packages -t packages1

# Run Celery worker and beat scheduler
uv run celery -A pyf.aggregator.queue worker --loglevel=info
uv run celery -A pyf.aggregator.queue beat --loglevel=info
```

## Architecture

### Core Flow

```
PyPI API  ->  Aggregator/Fetcher  ->  Plugins  ->  Indexer  ->  Typesense
                                         |
                                    (transforms data)
```

1. **Aggregator** (`fetcher.py`) - Fetches package data from PyPI JSON/Simple/RSS APIs with rate limiting and parallel fetching
2. **Plugins** (`plugins/`) - Transform data before indexing (version parsing, framework detection, health scoring)
3. **Indexer** (`indexer.py`) - Batches and upserts documents into Typesense
4. **Enrichers** (`enrichers/`) - Post-indexing enrichment (GitHub stats, download counts)

### Key Modules

| Module | Purpose |
|--------|---------|
| `main.py` | CLI entry point for `pyfaggregator` command (includes `--refresh-from-pypi` mode) |
| `fetcher.py` | PyPI API client with parallel fetching and rate limiting |
| `indexer.py` | Typesense document indexer with batching |
| `db.py` | Typesense connection, schema management, and package listing/deletion |
| `profiles.py` | Profile configuration for framework classifiers |
| `queue.py` | Celery tasks for async processing and periodic schedules |
| `typesense_util.py` | CLI for collection management (`pyfupdater`) |
| `enrichers/github.py` | GitHub data enricher (`pyfgithub`) |
| `enrichers/downloads.py` | Download statistics enricher (`pyfdownloads`) |

`queue.py` also exposes `get_dedup_redis()` (lazy singleton Redis client for dedup) and `is_package_recently_queued(package_id, release_id=None, feed_type="new", ttl=None)` (atomic SET NX EX check, fail-open). Keys are namespaced by feed type: `pyf:dedup:new:{id}` for new packages, `pyf:dedup:update:{id}:{version}` for releases.

### Plugin System

Plugins are registered in `plugins/__init__.py` and called for each package during aggregation:
- `version_slicer` - Parses semantic version components
- `framework_versions` - Extracts framework version classifiers
- `python_versions` - Extracts Python version classifiers
- `rst_to_html` - Converts RST descriptions to HTML
- `health_score` - Calculates package health metrics

### Profile System

Profiles define framework ecosystems in `profiles.yaml`:
```yaml
profiles:
  plone:
    name: "Plone"
    classifiers:
      - "Framework :: Plone"
      - "Framework :: Plone :: 6.0"
```

Each profile auto-creates its own Typesense collection named after the profile key.

### Celery Tasks

Background tasks in `queue.py`:
- `inspect_project` - Fetch and index a single package if it matches classifiers
- `update_project` - Re-index a known package
- `update_github` - Fetch GitHub stats for a package
- `read_rss_new_projects_and_queue` - Monitor PyPI RSS for new packages
- `read_rss_new_releases_and_queue` - Monitor PyPI RSS for new releases
- `refresh_all_indexed_packages` - Refresh all indexed packages from PyPI, remove 404s
- `full_fetch_all_packages` - Full fetch equivalent to `pyfaggregator -f -p <profile>`
- `enrich_downloads_all_packages` - Enrich all packages with download stats from pypistats.org

**Periodic Schedules:**
| Schedule | Task | Description |
|----------|------|-------------|
| Every minute | RSS tasks | Monitor PyPI for new packages/releases |
| Sunday 2:00 AM UTC | `refresh_all_indexed_packages` | Weekly refresh of all indexed packages |
| Sunday 4:00 AM UTC | `enrich_downloads_all_packages` | Weekly download stats from pypistats.org |
| 1st of month, 3:00 AM UTC | `full_fetch_all_packages` | Monthly complete re-fetch |

### Database Schema

Typesense collection schema includes:
- Package metadata (name, version, author, description, classifiers)
- GitHub enrichment (github_stars, github_watchers, github_open_issues, github_url)
- Download stats (download_last_day, download_last_week, download_last_month)
- Computed fields (version_major/minor/bugfix, health scores)

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

When `DEFAULT_PROFILE` is set, all CLI commands (`pyfaggregator`, `pyfgithub`, `pyfdownloads`, `pyfupdater`) will use it as the default profile. The `-p` CLI argument overrides this environment variable.

## Critical Rules

- Use `RUF` for formating
- Package uses namespace: `pyf.aggregator`
- always write tests first, TDD
- All CLI commands must be run with `uv run` prefix (e.g., `uv run pyfgithub -p plone`)
- run tests in a subagent
- always update README when things change or new features are added
