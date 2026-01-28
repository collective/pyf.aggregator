# Python Package Filter Aggregator

The Python Package Filter Aggregator (`pyf.aggregator`) aggregates the meta
information of all Python packages in the PyPI and enhances it with data from GitHub
and download statistics from pypistats.org.


## Requirements

- Python 3.12+
- [Typesense](https://typesense.org/docs/guide/install-typesense.html) search engine
- Redis (for the queue-based architecture)


## Installation

### Using Docker Compose (Recommended)

The project includes a `docker-compose.yml` to run Typesense and Redis:

```shell
docker-compose up -d
```

This starts:
- **Typesense** on port 8108 - The search engine for storing package data
- **Redis (Valkey)** on port 6379 - Message broker for Celery task queue

### Install the Package

Install using uv tool:

```shell
uv tool install pyf.aggregator
```


## Configuration

copy example.env to .env

or create a `.env` file with the following environment variables:

```ini
# Typesense Configuration
TYPESENSE_HOST=localhost
TYPESENSE_PORT=8108
TYPESENSE_PROTOCOL=http
TYPESENSE_API_KEY=<your_secret_typesense_apikey>
TYPESENSE_TIMEOUT=120

# GitHub Configuration
GITHUB_TOKEN=<your_secret_github_apikey>
# Rate limit: 5000 req/hour authenticated (~1.4/sec), default 0.75s delay
GITHUB_REQUEST_DELAY=0.75

# PyPI Configuration
# PyPI JSON API has no formal rate limit (CDN cached), default 0.001s = ~1000 req/s
PYPI_RATE_LIMIT_DELAY=0.001
PYPI_MAX_RETRIES=3
PYPI_RETRY_BACKOFF=2.0
# Number of parallel threads for fetching (default 20, increase for faster fetching)
PYPI_MAX_WORKERS=20
# Batch size for memory-efficient fetching (default 500)
PYPI_BATCH_SIZE=500

# PyPI Stats Configuration (for download enrichment)
# pypistats.org rate limits: ~30 req/min, default 2.0s delay
PYPISTATS_RATE_LIMIT_DELAY=2.0
PYPISTATS_MAX_RETRIES=3
PYPISTATS_RETRY_BACKOFF=2.0

# Redis Configuration (for Celery task queue)
REDIS_HOST=localhost:6379

# Celery Task Configuration
TYPESENSE_COLLECTION=plone

# Celery Periodic Task Schedules (crontab format: minute hour day_of_month month day_of_week)
# Set to empty string to disable a task
CELERY_SCHEDULE_RSS_PROJECTS=*/1 * * * *    # Check for new projects
CELERY_SCHEDULE_RSS_RELEASES=*/1 * * * *    # Check for new releases
CELERY_SCHEDULE_WEEKLY_REFRESH=0 2 * * 0    # Sunday 2:00 AM UTC
CELERY_SCHEDULE_WEEKLY_DOWNLOADS=0 4 * * 0  # Sunday 4:00 AM UTC
CELERY_SCHEDULE_MONTHLY_FETCH=0 3 1 * *     # 1st of month, 3:00 AM UTC

# RSS Deduplication
# Separate TTLs for new-package vs release-update feeds (default 24h)
RSS_DEDUP_TTL_NEW=86400                    # TTL for new packages feed (0 = disabled)
RSS_DEDUP_TTL_UPDATE=86400                 # TTL for release updates feed (0 = disabled)
# RSS_DEDUP_TTL=86400                      # Legacy fallback for both (overridden by above)

# Celery Worker Pool and Concurrency
CELERY_WORKER_POOL=threads             # Worker pool type (threads for I/O-bound tasks)
CELERY_WORKER_CONCURRENCY=20           # Number of concurrent threads
CELERY_WORKER_PREFETCH_MULTIPLIER=4    # Tasks to prefetch per worker
CELERY_TASK_SOFT_TIME_LIMIT=300        # Soft time limit in seconds (5 min)
CELERY_TASK_TIME_LIMIT=600             # Hard time limit in seconds (10 min)

# Default profile for CLI commands (plone, django, flask)
# When set, pyfaggregator uses this profile automatically without needing -p flag
# CLI -p argument always takes precedence over this setting
# DEFAULT_PROFILE=plone
```

### Profile Configuration

The aggregator supports multiple framework ecosystems through **profiles**. Each profile defines a set of PyPI trove classifiers to track packages from different Python frameworks (Django, Flask, FastAPI, etc.).

Profiles are defined in `src/pyf/aggregator/profiles.yaml`:

```yaml
profiles:
  plone:
    name: "Plone"
    classifiers:
      - "Framework :: Plone"
      - "Framework :: Plone :: 6.0"
      # ... more classifiers

  django:
    name: "Django"
    classifiers:
      - "Framework :: Django"
      - "Framework :: Django :: 5.0"
      # ... more classifiers

  flask:
    name: "Flask"
    classifiers:
      - "Framework :: Flask"
```

**Built-in Profiles:**
- `plone` - Plone CMS packages
- `django` - Django framework packages
- `flask` - Flask framework packages

**Adding Custom Profiles:**

To add a new profile, edit `src/pyf/aggregator/profiles.yaml`:

```yaml
profiles:
  fastapi:
    name: "FastAPI"
    classifiers:
      - "Framework :: FastAPI"
```

Each profile automatically creates its own Typesense collection (using the profile key as the collection name), while sharing the GitHub enrichment cache across all profiles to save API calls.


## CLI Commands

### pyfaggregator

Fetches package information from PyPI and indexes it into Typesense.

```shell
uv run pyfaggregator [options]
```

**Options:**

| Option | Description |
|--------|-------------|
| `-f`, `--first` | First/full fetch from PyPI (fetches all packages) |
| `-i`, `--incremental` | Incremental fetch (only packages updated since last run) |
| `--refresh-from-pypi` | Refresh indexed packages data from PyPI (updates existing packages, removes 404s) |
| `-s`, `--sincefile` | File to store timestamp of last run (default: `.pyaggregator.since`) |
| `-l`, `--limit` | Limit the number of packages to process |
| `-fn`, `--filter-name` | Filter packages by name (substring match) |
| `-ft`, `--filter-troove` | Filter by trove classifier (can be used multiple times). Deprecated: use profiles instead |
| `-p`, `--profile` | Use a predefined profile (loads classifiers and sets collection name). Overrides `DEFAULT_PROFILE` env var |
| `-t`, `--target` | Target Typesense collection name (auto-set from profile if not specified) |
| `--no-plone-filter` | Disable automatic Plone classifier filtering (process all packages) |
| `--show PACKAGE_NAME` | Show indexed data for a package by name (for debugging, shows newest version) |
| `--all-versions` | Show all versions when using --show (default: only newest) |
| `--recreate-collection` | Zero-downtime collection recreation with alias switching (creates versioned collections like `name-1`, `name-2`) |

**Examples:**

```shell
# Full fetch of all Plone packages (using manual classifiers)
uv run pyfaggregator -f -ft "Framework :: Plone" -t packages1

# Full fetch using the Plone profile (recommended)
uv run pyfaggregator -f -p plone

# Full fetch of Django packages using the Django profile
uv run pyfaggregator -f -p django

# Full fetch of Flask packages using the Flask profile
uv run pyfaggregator -f -p flask

# Incremental update for Django profile
uv run pyfaggregator -i -p django

# Refresh existing indexed packages from PyPI (updates data, removes packages no longer on PyPI)
uv run pyfaggregator --refresh-from-pypi -p plone

# Refresh with limit for testing
uv run pyfaggregator --refresh-from-pypi -p plone -l 100

# Fetch with limit for testing
uv run pyfaggregator -f -p plone -l 100

# Profile with custom collection name (overrides auto-naming)
uv run pyfaggregator -f -p django -t django-test

# Show indexed data for a package (newest version, for debugging)
uv run pyfaggregator --show plone -t plone
uv run pyfaggregator --show Django -p django

# Show all versions of a package
uv run pyfaggregator --show plone -p plone --all-versions

# Zero-downtime collection recreation with full reindex
# Creates versioned collection (plone-1) with alias (plone)
uv run pyfaggregator -f -p plone --recreate-collection

# Subsequent runs create new version, migrate data, switch alias, delete old
# plone-1 → plone-2 → plone-3, etc.

# Using DEFAULT_PROFILE environment variable
# When DEFAULT_PROFILE=plone is set in .env, these are equivalent:
uv run pyfaggregator -f              # Uses plone profile from DEFAULT_PROFILE
uv run pyfaggregator -f -p plone     # Explicit profile (same result)
uv run pyfaggregator -f -p django    # CLI -p overrides DEFAULT_PROFILE
```

### pyfgithub

Enriches indexed packages with data from GitHub (stars, watchers, issues, etc.).

```shell
uv run pyfgithub -t <collection_name>
```

**Options:**

| Option | Description |
|--------|-------------|
| `-p`, `--profile` | Use a profile (auto-sets target collection name) |
| `-t`, `--target` | Target Typesense collection name (auto-set from profile if not specified) |
| `-n`, `--name` | Single package name to enrich (enriches only this package) |
| `-v`, `--verbose` | Show raw data from Typesense (PyPI) and GitHub API |

**Examples:**

```shell
# Enrich using profile (recommended)
uv run pyfgithub -p plone

# Enrich Django packages
uv run pyfgithub -p django

# Enrich Flask packages
uv run pyfgithub -p flask

# Enrich a specific collection (manual)
uv run pyfgithub -t packages1

# Enrich only a specific package
uv run pyfgithub -p plone -n plone.api

# Debug a single package with verbose output
uv run pyfgithub -p plone -n plone.api -v
```

This adds the following fields to each package (if a GitHub repository is found):
- `github_stars` - Number of stargazers
- `github_watchers` - Number of watchers
- `github_updated` - Last update timestamp
- `github_open_issues` - Number of open issues
- `github_url` - URL to the GitHub repository

**Note:** GitHub enrichment cache is shared across all profiles to minimize API calls.

### pyfupdater

Utility for managing Typesense collections, aliases, and API keys.

```shell
uv run pyfupdater [options]
```

**Options:**

| Option | Description |
|--------|-------------|
| `-ls`, `--list-collections` | List all collections with full details |
| `-lsn`, `--list-collection-names` | List collection names only |
| `-lsa`, `--list-aliases` | List all collection aliases |
| `-lssoa`, `--list-search-only-apikeys` | List all search-only API keys |
| `--migrate` | Migrate data from source to target collection |
| `--add-alias` | Add a collection alias |
| `--add-search-only-apikey` | Create a search-only API key |
| `--delete-apikey` | Delete an API key by its ID |
| `--delete-collection` | Delete a collection by name (requires confirmation) |
| `-f`, `--force` | Skip confirmation prompts for destructive operations |
| `-p`, `--profile` | Use a profile (auto-sets target collection name) |
| `-s`, `--source` | Source collection name (for migrate/alias) |
| `-t`, `--target` | Target collection name (auto-set from profile if not specified) |
| `-key`, `--key` | Custom API key value (optional, auto-generated if not provided) |
| `--recreate-collection` | Zero-downtime collection recreation with alias switching (requires -p/-t) |
| `--purge-queue` | Purge all pending tasks from the Celery queue |
| `--queue-stats` | Show Celery queue statistics (pending tasks, workers) |

**Examples:**

```shell
# List all collections
uv run pyfupdater -ls

# List collection names only
uv run pyfupdater -lsn

# List aliases
uv run pyfupdater -lsa

# Add an alias (packages -> packages1)
uv run pyfupdater --add-alias -s packages -t packages1

# Migrate data between collections
uv run pyfupdater --migrate -s packages1 -t packages2

# Create a search-only API key
uv run pyfupdater --add-search-only-apikey -t packages

# Create a search-only API key with custom value
uv run pyfupdater --add-search-only-apikey -t packages -key your_custom_key

# Profile-aware operations
uv run pyfupdater --add-search-only-apikey -p django
uv run pyfupdater --add-alias -s django -t django-v2
uv run pyfupdater --add-search-only-apikey -t packages -key your_custom_key

# Delete an API key by ID
uv run pyfupdater --delete-apikey 123

# Zero-downtime collection recreation (creates plone-1, plone-2, etc. with alias)
uv run pyfupdater --recreate-collection -t plone
# First run: creates 'plone-1' collection with alias 'plone' → 'plone-1'
# Subsequent runs: creates 'plone-2', migrates data, switches alias, deletes old

# List aliases to see versioned collections
uv run pyfupdater -lsa  # Shows: plone → plone-1

# View queue statistics
uv run pyfupdater --queue-stats

# Purge all pending tasks from queue
uv run pyfupdater --purge-queue

# Delete a collection (with confirmation prompt)
uv run pyfupdater --delete-collection plone-old

# Delete a collection without confirmation (force)
uv run pyfupdater --delete-collection plone-old --force
uv run pyfupdater --delete-collection plone-old -f
```

### pyfdownloads

Enriches indexed packages with download statistics from pypistats.org.

```shell
uv run pyfdownloads [options]
```

**Options:**

| Option | Description |
|--------|-------------|
| `-p`, `--profile` | Use a profile (auto-sets target collection name) |
| `-t`, `--target` | Target Typesense collection name (auto-set from profile if not specified) |
| `-l`, `--limit` | Limit number of packages to process (useful for testing) |

**Examples:**

```shell
# Enrich using profile (recommended)
uv run pyfdownloads -p plone

# Enrich Django packages
uv run pyfdownloads -p django

# Enrich a specific collection (manual)
uv run pyfdownloads -t packages1

# Test with limited packages
uv run pyfdownloads -p plone -l 100
```

This adds the following fields to each package:
- `download_last_day` - Downloads in the last day
- `download_last_week` - Downloads in the last week
- `download_last_month` - Downloads in the last month
- `download_total` - Total downloads (if available)
- `download_updated` - Timestamp when stats were updated


## Quickstart

### Using Profiles (Recommended)

1. Start the required services:
   ```shell
   docker-compose up -d
   ```

2. Aggregate packages using a profile:
   ```shell
   # For Plone packages
   uv run pyfaggregator -f -p plone

   # For Django packages
   uv run pyfaggregator -f -p django

   # For Flask packages
   uv run pyfaggregator -f -p flask
   ```

3. Enrich with GitHub data:
   ```shell
   # For Plone
   uv run pyfgithub -p plone

   # For Django
   uv run pyfgithub -p django

   # For Flask
   uv run pyfgithub -p flask
   ```

4. Enrich with download statistics:
   ```shell
   # For Plone
   uv run pyfdownloads -p plone

   # For Django
   uv run pyfdownloads -p django

   # For Flask
   uv run pyfdownloads -p flask
   ```

5. Create a search-only API key for clients:
   ```shell
   # For Plone
   uv run pyfupdater --add-search-only-apikey -p plone

   # For Django
   uv run pyfupdater --add-search-only-apikey -p django
   ```

### Manual Configuration (Legacy)

1. Start the required services:
   ```shell
   docker-compose up -d
   ```

2. Aggregate Plone packages from PyPI:
   ```shell
   uv run pyfaggregator -f -ft "Framework :: Plone" -t packages1
   ```

3. Enrich with GitHub data:
   ```shell
   uv run pyfgithub -t packages1
   ```

4. Enrich with download statistics:
   ```shell
   uv run pyfdownloads -t packages1
   ```

5. Create a collection alias (required for client access):
   ```shell
   uv run pyfupdater --add-alias -s packages -t packages1
   ```

6. Create a search-only API key for clients:
   ```shell
   uv run pyfupdater --add-search-only-apikey -t packages
   ```


## Multi-Profile Support

The aggregator supports tracking multiple Python framework ecosystems simultaneously. Each profile represents a different framework (Django, Flask, FastAPI, etc.) and can be managed independently with its own Typesense collection.

### Benefits

- **Ecosystem Independence**: Run separate collections for Django, Flask, Plone, etc.
- **Shared GitHub Cache**: GitHub enrichment data is cached and shared across all profiles, reducing API calls
- **Simplified Configuration**: Pre-defined classifier sets for popular frameworks
- **Collection Auto-Naming**: Collections are automatically named after their profile (e.g., `django`, `flask`, `plone`)

### Working with Multiple Profiles

**Example: Managing both Django and Flask packages**

```shell
# Aggregate Django packages
uv run pyfaggregator -f -p django

# Aggregate Flask packages
uv run pyfaggregator -f -p flask

# Enrich both with GitHub data (cache is shared!)
uv run pyfgithub -p django
uv run pyfgithub -p flask

# Create API keys for each
uv run pyfupdater --add-search-only-apikey -p django
uv run pyfupdater --add-search-only-apikey -p flask
```

**List all profile collections:**

```shell
uv run pyfupdater -lsn
```

This might output:
```
django
flask
plone
```

### Profile vs. Manual Classifier Configuration

**Using Profiles (Recommended):**
```shell
uv run pyfaggregator -f -p django
```
- Automatically loads all Django-related classifiers
- Auto-sets collection name to `django`
- Easier to maintain and update

**Using Manual Classifiers (Legacy):**
```shell
uv run pyfaggregator -f -ft "Framework :: Django" -ft "Framework :: Django :: 5.0" -t django-packages
```
- Requires specifying each classifier individually
- Manual collection name management
- More flexible but more verbose


## Architecture

### Database Schema

The Typesense collection schema includes the following field categories:

**Package Metadata:**
- `name`, `version`, `author`, `description`, `summary`, `license`
- `classifiers`, `keywords`, `requires_dist`, `requires_python`
- `home_page`, `docs_url`, `project_urls`
- `upload_timestamp` - Unix timestamp (int64) of the last release. Packages without a timestamp use `0`, which naturally sorts to the bottom when sorting by "last modified" descending.

**Computed Fields:**
- `version_major`, `version_minor`, `version_bugfix` - Parsed version components
- `version_sortable` - Sortable string for correct version ordering (see below)
- `health_score` - Package health metric (0-100)
- `health_score_breakdown` - Detailed scoring factors (recency, documentation, metadata)

**Version Sorting:**

The `version_sortable` field uses a 6-segment format that ensures stable releases sort above pre-releases, matching PyPI's definition of "latest":

```
Format: STABLE.MAJOR.MINOR.BUGFIX.PRETYPE.PRENUM

Examples:
  2.5.3 (stable)  → 1.0002.0005.0003.0000.0000
  3.0.0a2 (alpha) → 0.0003.0000.0000.0001.0002

Sorting descending: 2.5.3 > 3.0.0a2 (stable first)
```

- **STABLE**: `1` for stable releases, `0` for pre-releases
- **PRETYPE**: `0000`=dev, `0001`=alpha, `0002`=beta, `0003`=rc (for ordering among pre-releases)

This matches PyPI's behavior where `2.5.3` is considered "latest" even though `3.0.0a2` has a higher version number, because pre-releases are not considered production-ready.

To query for the "newest" version of a package, sort by `version_sortable:desc`.

**GitHub Enrichment:**
- `github_stars`, `github_watchers`, `github_open_issues`
- `github_url`, `github_updated`

**Download Statistics:**
- `download_last_day`, `download_last_week`, `download_last_month`
- `download_total`, `download_updated`

### Queue-Based Processing

The project uses a queue-based architecture with Celery for improved scalability and reliability:

- **Redis** serves as the message broker
- **Celery workers** process tasks asynchronously
- **Periodic tasks** handle automated updates on various schedules

**Celery Tasks:**

| Task | Description |
|------|-------------|
| `inspect_project` | Fetch and inspect a project from PyPI, index if it matches classifiers |
| `update_project` | Re-index a known package from PyPI |
| `update_github` | Fetch GitHub repository data and update package in Typesense |
| `read_rss_new_projects_and_queue` | Monitor RSS for new projects and queue inspection |
| `read_rss_new_releases_and_queue` | Monitor RSS for new releases and queue inspection |
| `refresh_all_indexed_packages` | Refresh all indexed packages from PyPI, remove packages returning 404 |
| `full_fetch_all_packages` | Full fetch of all packages (equivalent to `pyfaggregator -f -p <profile>`) |
| `enrich_downloads_all_packages` | Enrich all packages with download stats from pypistats.org |

**Periodic Task Schedules:**

| Task | Schedule | Description |
|------|----------|-------------|
| RSS new projects | Every minute | Monitor PyPI RSS feed for new packages |
| RSS new releases | Every minute | Monitor PyPI RSS feed for package updates |
| Weekly refresh | Sunday 2:00 AM UTC | Refresh all indexed packages from PyPI |
| Weekly downloads | Sunday 4:00 AM UTC | Enrich with download stats from pypistats.org |
| Monthly full fetch | 1st of month, 3:00 AM UTC | Complete re-fetch from PyPI |

**Worker Pool:**

The Celery worker uses a thread pool by default since all tasks are I/O-bound (HTTP requests to PyPI, GitHub, and Typesense). Python's GIL is released during I/O operations, so threads handle HTTP-bound tasks well without requiring monkey-patching.

| Setting | Default | Description |
|---------|---------|-------------|
| `CELERY_WORKER_POOL` | `threads` | Worker pool type |
| `CELERY_WORKER_CONCURRENCY` | `20` | Number of concurrent threads |
| `CELERY_WORKER_PREFETCH_MULTIPLIER` | `4` | Tasks prefetched per worker to keep threads fed during I/O waits |
| `CELERY_TASK_SOFT_TIME_LIMIT` | `300` | Soft time limit (seconds) - raises `SoftTimeLimitExceeded` for graceful cleanup |
| `CELERY_TASK_TIME_LIMIT` | `600` | Hard time limit (seconds) - kills the task |

Long-running tasks (`refresh_all_indexed_packages`, `full_fetch_all_packages`, `enrich_downloads_all_packages`) have extended time limits and handle `SoftTimeLimitExceeded` to return partial results gracefully. Additionally, `task_acks_late` is enabled to prevent task loss on worker crashes.

**RSS Deduplication:**

The RSS tasks run every minute, but the feeds change slowly. To avoid re-queueing the same packages repeatedly, both RSS tasks use Redis-based deduplication. Before queueing an `inspect_project` task, a Redis `SET NX EX` check is performed with a configurable TTL (default 24 hours). The dedup keys are namespaced by feed type:

- **New packages** (`packages.xml`): key = `pyf:dedup:new:{package_name}`, TTL from `RSS_DEDUP_TTL_NEW`
- **New releases** (`updates.xml`): key = `pyf:dedup:update:{package_name}:{version}`, TTL from `RSS_DEDUP_TTL_UPDATE`

This ensures that different versions of the same package are not incorrectly deduplicated in the releases feed, while new packages are deduplicated by name only. The legacy `RSS_DEDUP_TTL` environment variable is still supported as a fallback for both TTLs. The mechanism is fail-open: if Redis is unavailable, all packages proceed normally.

To run a Celery worker:
```shell
uv run celery -A pyf.aggregator.queue worker --loglevel=info
```

To run Celery beat for periodic tasks:
```shell
uv run celery -A pyf.aggregator.queue beat --loglevel=info
```

**Manually Triggering Tasks:**

You can manually trigger refresh tasks from Python:
```python
from pyf.aggregator.queue import refresh_all_indexed_packages, full_fetch_all_packages

# Refresh all indexed packages
refresh_all_indexed_packages.delay()

# Full fetch with specific profile and collection
full_fetch_all_packages.delay(collection_name="plone", profile_name="plone")
```


## Development

### Using Dev Container (Recommended)

The project includes a devcontainer configuration for VS Code / GitHub Codespaces:

1. Open the project in VS Code
2. When prompted, click "Reopen in Container" (or use Command Palette: "Dev Containers: Reopen in Container")
3. The container will automatically install all dependencies including test requirements

### Manual Setup

Install the project with test dependencies using uv:

```shell
uv sync --extra test
```

### Running Tests

```shell
# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/test_fetcher.py -v

# Run without coverage
uv run pytest --no-cov

# Run only integration tests (requires Typesense running)
uv run pytest -m integration -v

# Run excluding integration tests
uv run pytest -m "not integration"
```


## License

The code is open-source and licensed under the Apache License 2.0.


## Credits

- [@jensens](https://github.com/jensens)
- [@veit](https://github.com/veit)
- [@guziel](https://github.com/guziel)
- [@pgrunewald](https://github.com/pgrunewald)
- [@MrTango](https://github.com/MrTango)
- [@pypa](https://github.com/pypa)
