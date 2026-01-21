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
.venv/bin/pytest

# Run specific test file
.venv/bin/pytest tests/test_fetcher.py -v

# Run without coverage (faster)
.venv/bin/pytest --no-cov

# Run single test
.venv/bin/pytest tests/test_fetcher.py::test_function_name -v
```

**Important**: Use `.venv/bin/pytest`, not globally installed pytest, as it needs access to project dependencies.

### CLI Commands

```shell
# Full fetch using a profile (recommended)
pyfaggregator -f -p plone

# Incremental update
pyfaggregator -i -p plone

# Refresh indexed packages from PyPI (updates existing, removes 404s)
pyfaggregator --refresh-from-pypi -p plone

# Enrich with GitHub data
pyfgithub -p plone

# Manage Typesense collections
pyfupdater -ls              # List collections
pyfupdater -lsn             # List collection names
pyfupdater --add-alias -s packages -t packages1

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

**Periodic Schedules:**
| Schedule | Task | Description |
|----------|------|-------------|
| Every minute | RSS tasks | Monitor PyPI for new packages/releases |
| Sunday 2:00 AM UTC | `refresh_all_indexed_packages` | Weekly refresh of all indexed packages |
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
```

## Code Style

- Uses `isort` with Plone profile
- Uses `black` targeting Python 3.12
- Package uses namespace: `pyf.aggregator`
