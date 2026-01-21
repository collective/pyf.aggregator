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
pyfaggregator [options]
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
| `-p`, `--profile` | Use a predefined profile (loads classifiers and sets collection name) |
| `-t`, `--target` | Target Typesense collection name (auto-set from profile if not specified) |
| `--no-plone-filter` | Disable automatic Plone classifier filtering (process all packages) |

**Examples:**

```shell
# Full fetch of all Plone packages (using manual classifiers)
pyfaggregator -f -ft "Framework :: Plone" -t packages1

# Full fetch using the Plone profile (recommended)
pyfaggregator -f -p plone

# Full fetch of Django packages using the Django profile
pyfaggregator -f -p django

# Full fetch of Flask packages using the Flask profile
pyfaggregator -f -p flask

# Incremental update for Django profile
pyfaggregator -i -p django

# Refresh existing indexed packages from PyPI (updates data, removes packages no longer on PyPI)
pyfaggregator --refresh-from-pypi -p plone

# Refresh with limit for testing
pyfaggregator --refresh-from-pypi -p plone -l 100

# Fetch with limit for testing
pyfaggregator -f -p plone -l 100

# Profile with custom collection name (overrides auto-naming)
pyfaggregator -f -p django -t django-test
```

### pyfgithub

Enriches indexed packages with data from GitHub (stars, watchers, issues, etc.).

```shell
pyfgithub -t <collection_name>
```

**Options:**

| Option | Description |
|--------|-------------|
| `-p`, `--profile` | Use a profile (auto-sets target collection name) |
| `-t`, `--target` | Target Typesense collection name (auto-set from profile if not specified) |

**Examples:**

```shell
# Enrich using profile (recommended)
pyfgithub -p plone

# Enrich Django packages
pyfgithub -p django

# Enrich Flask packages
pyfgithub -p flask

# Enrich a specific collection (manual)
pyfgithub -t packages1
pyfgithub -t packages1
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
pyfupdater [options]
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
| `-p`, `--profile` | Use a profile (auto-sets target collection name) |
| `-s`, `--source` | Source collection name (for migrate/alias) |
| `-t`, `--target` | Target collection name (auto-set from profile if not specified) |
| `-key`, `--key` | Custom API key value (optional, auto-generated if not provided) |

**Examples:**

```shell
# List all collections
pyfupdater -ls

# List collection names only
pyfupdater -lsn

# List aliases
pyfupdater -lsa

# Add an alias (packages -> packages1)
pyfupdater --add-alias -s packages -t packages1

# Migrate data between collections
pyfupdater --migrate -s packages1 -t packages2

# Create a search-only API key
pyfupdater --add-search-only-apikey -t packages

# Create a search-only API key with custom value
pyfupdater --add-search-only-apikey -t packages -key your_custom_key

# Profile-aware operations
pyfupdater --add-search-only-apikey -p django
pyfupdater --add-alias -s django -t django-v2
pyfupdater --add-search-only-apikey -t packages -key your_custom_key

# Delete an API key by ID
pyfupdater --delete-apikey 123
```

### pyfdownloads

Enriches indexed packages with download statistics from pypistats.org.

```shell
pyfdownloads [options]
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
pyfdownloads -p plone

# Enrich Django packages
pyfdownloads -p django

# Enrich a specific collection (manual)
pyfdownloads -t packages1

# Test with limited packages
pyfdownloads -p plone -l 100
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
   pyfaggregator -f -p plone

   # For Django packages
   pyfaggregator -f -p django

   # For Flask packages
   pyfaggregator -f -p flask
   ```

3. Enrich with GitHub data:
   ```shell
   # For Plone
   pyfgithub -p plone

   # For Django
   pyfgithub -p django

   # For Flask
   pyfgithub -p flask
   ```

4. Enrich with download statistics:
   ```shell
   # For Plone
   pyfdownloads -p plone

   # For Django
   pyfdownloads -p django

   # For Flask
   pyfdownloads -p flask
   ```

5. Create a search-only API key for clients:
   ```shell
   # For Plone
   pyfupdater --add-search-only-apikey -p plone

   # For Django
   pyfupdater --add-search-only-apikey -p django
   ```

### Manual Configuration (Legacy)

1. Start the required services:
   ```shell
   docker-compose up -d
   ```

2. Aggregate Plone packages from PyPI:
   ```shell
   pyfaggregator -f -ft "Framework :: Plone" -t packages1
   ```

3. Enrich with GitHub data:
   ```shell
   pyfgithub -t packages1
   ```

4. Enrich with download statistics:
   ```shell
   pyfdownloads -t packages1
   ```

5. Create a collection alias (required for client access):
   ```shell
   pyfupdater --add-alias -s packages -t packages1
   ```

6. Create a search-only API key for clients:
   ```shell
   pyfupdater --add-search-only-apikey -t packages
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
pyfaggregator -f -p django

# Aggregate Flask packages
pyfaggregator -f -p flask

# Enrich both with GitHub data (cache is shared!)
pyfgithub -p django
pyfgithub -p flask

# Create API keys for each
pyfupdater --add-search-only-apikey -p django
pyfupdater --add-search-only-apikey -p flask
```

**List all profile collections:**

```shell
pyfupdater -lsn
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
pyfaggregator -f -p django
```
- Automatically loads all Django-related classifiers
- Auto-sets collection name to `django`
- Easier to maintain and update

**Using Manual Classifiers (Legacy):**
```shell
pyfaggregator -f -ft "Framework :: Django" -ft "Framework :: Django :: 5.0" -t django-packages
```
- Requires specifying each classifier individually
- Manual collection name management
- More flexible but more verbose


## Architecture

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

**Periodic Task Schedules:**

| Task | Schedule | Description |
|------|----------|-------------|
| RSS new projects | Every minute | Monitor PyPI RSS feed for new packages |
| RSS new releases | Every minute | Monitor PyPI RSS feed for package updates |
| Weekly refresh | Sunday 2:00 AM UTC | Refresh all indexed packages from PyPI |
| Monthly full fetch | 1st of month, 3:00 AM UTC | Complete re-fetch from PyPI |

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

Use the project's virtual environment pytest (not global uv tools):

```shell
# Run all tests
.venv/bin/pytest

# Run specific test file
.venv/bin/pytest tests/test_fetcher.py -v

# Run without coverage
.venv/bin/pytest --no-cov
```

**Note:** Do not use globally installed pytest (via `uv tool install pytest`) as it runs in an isolated environment without access to the project's dependencies.


## License

The code is open-source and licensed under the Apache License 2.0.


## Credits

- [@jensens](https://github.com/jensens)
- [@veit](https://github.com/veit)
- [@guziel](https://github.com/guziel)
- [@pgrunewald](https://github.com/pgrunewald)
- [@MrTango](https://github.com/MrTango)
- [@pypa](https://github.com/pypa)
