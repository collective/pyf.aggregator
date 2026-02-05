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

# npm Registry Configuration
# npm registry: 1000 req/hr unauthenticated, 5000 with token
NPM_RATE_LIMIT_DELAY=0.72              # Default 0.72s for authenticated (~5000 req/hr)
NPM_AUTH_TOKEN=                        # Optional: for 5000 req/hr limit
NPM_MAX_RETRIES=3
NPM_RETRY_BACKOFF=2.0
NPM_MAX_WORKERS=10                     # Parallel threads for fetching
NPM_BATCH_SIZE=100                     # Batch size for memory-efficient fetching

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

### npm Registry Rate Limits

The official npm registry enforces the following rate limits:

| Authentication | Rate Limit | Recommended Delay |
|----------------|------------|-------------------|
| None | 1,000 req/hour | 3.6s (`NPM_RATE_LIMIT_DELAY=3.6`) |
| With token | 5,000 req/hour | 0.72s (default) |

**Default Configuration**: The default delay of `0.72s` is calibrated for authenticated requests (5000 req/hr). If you're fetching without an `NPM_AUTH_TOKEN`, increase the delay to `3.6` to avoid rate limiting.

**HTTP 429 Handling**: If the npm registry returns a 429 (Too Many Requests), the fetcher automatically reads the `Retry-After` header and waits before retrying.

**Getting an npm Token**: Generate a token at [npmjs.com/settings/tokens](https://www.npmjs.com/settings/tokens) with read-only access.

### Profile Configuration

The aggregator supports multiple framework ecosystems through **profiles**. Each profile defines a set of PyPI trove classifiers to track packages from different Python frameworks (Django, Flask, FastAPI, etc.). Profiles can also include npm registry configuration for frontend packages.

Profiles are defined in `src/pyf/aggregator/profiles.yaml`:

```yaml
profiles:
  plone:
    name: "Plone"
    classifiers:
      - "Framework :: Plone"
      - "Framework :: Plone :: 6.0"
      # ... more classifiers
    npm:
      keywords:
        - plone
      scopes:
        - "@plone"
        - "@plone-collective"
        - "@eeacms"

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
- `plone` - Plone CMS packages (includes npm configuration for @plone/* packages)
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

**Adding npm Support to a Profile:**

To include npm packages in a profile, add an `npm` section with keywords and/or scopes:

```yaml
profiles:
  myprofile:
    name: "My Profile"
    classifiers:
      - "Framework :: MyFramework"
    npm:
      keywords:
        - myframework          # Search for packages with this keyword
      scopes:
        - "@myframework"       # Search for scoped packages
        - "@myorg"
```

Each profile automatically creates its own Typesense collection (using the profile key as the collection name), while sharing the GitHub enrichment cache across all profiles to save API calls. npm and PyPI packages are stored in the same collection with a `registry` field to distinguish them.


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
| `--refresh-from-pypi` | Refresh indexed packages data from PyPI - fetches ALL versions of each package (updates existing, removes 404s) |
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

# Refresh existing indexed packages from PyPI (fetches ALL versions, updates data, removes 404s)
uv run pyfaggregator --refresh-from-pypi -p plone

# Refresh with limit for testing (processes only first N packages, but all their versions)
uv run pyfaggregator --refresh-from-pypi -p plone -l 100

# Refresh a specific package (all versions)
uv run pyfaggregator --refresh-from-pypi -p plone -fn plone.api

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

### pyfnpm

Fetches package information from the npm registry and indexes it into Typesense. npm packages are stored in the same collection as PyPI packages, distinguished by a `registry` field.

```shell
uv run pyfnpm [options]
```

**Options:**

| Option | Description |
|--------|-------------|
| `-f`, `--first` | Full download: fetch all npm packages matching profile |
| `-i`, `--incremental` | Incremental update: fetch recent package updates |
| `--refresh-from-npm` | Refresh indexed npm packages from npm registry (updates existing, removes 404s and non-matching) |
| `-l`, `--limit` | Limit the number of packages to process |
| `-fn`, `--filter-name` | Filter packages by name (substring match) |
| `-p`, `--profile` | Profile name for npm filtering (required, must have npm config) |
| `-t`, `--target` | Target Typesense collection name (auto-set from profile if not specified) |
| `--show PACKAGE_NAME` | Show indexed data for an npm package by name (for debugging) |
| `--all-versions` | Show all versions when using --show (default: only newest) |
| `--recreate-collection` | Zero-downtime collection recreation with alias switching |
| `--force` | Skip confirmation prompts for destructive operations |

**Examples:**

```shell
# Full fetch of npm packages using the Plone profile
uv run pyfnpm -f -p plone

# Full fetch with limit (for testing)
uv run pyfnpm -f -p plone -l 10

# Show indexed data for an npm package
uv run pyfnpm --show @plone/volto -p plone

# Show all versions of an npm package
uv run pyfnpm --show @plone/volto -p plone --all-versions

# Incremental update
uv run pyfnpm -i -p plone

# Full fetch with custom collection name
uv run pyfnpm -f -p plone -t plone-test

# Refresh existing indexed npm packages (fetches fresh data, removes 404s)
uv run pyfnpm --refresh-from-npm -p plone

# Refresh with limit for testing
uv run pyfnpm --refresh-from-npm -p plone -l 100

# Refresh specific packages by name filter
uv run pyfnpm --refresh-from-npm -p plone -fn volto
```

**Refresh Mode:**

The `--refresh-from-npm` option iterates over all indexed npm packages and:
1. Fetches fresh metadata from npm registry for each package
2. Validates packages still match profile keywords/scopes
3. Removes packages that return 404 or no longer match filters
4. Preserves GitHub enrichment fields (stars, watchers, etc.) during refresh

This is useful for keeping indexed data up-to-date and cleaning up packages that have been removed from npm or renamed.

**npm Search Criteria:**

The `pyfnpm` command searches the npm registry based on the profile's npm configuration:

- **Keywords**: Packages with matching keywords (e.g., `plone`)
- **Scopes**: Scoped packages like `@plone/*`, `@plone-collective/*`

**npm-Specific Fields:**

npm packages include additional fields:
- `registry` - Set to `"npm"` to distinguish from PyPI packages
- `npm_scope` - The package scope (e.g., `"plone"` for `@plone/volto`)
- `npm_quality_score` - npm quality score (0-1)
- `npm_popularity_score` - npm popularity score (0-1)
- `npm_maintenance_score` - npm maintenance score (0-1)
- `npm_final_score` - Combined npm score (0-1)
- `repository_url` - Git repository URL (handles various formats)

### pyfgithub

Enriches indexed packages with data from GitHub (stars, watchers, issues, contributors, etc.).

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
- `contributors` - Array of top 5 contributors with `username`, `avatar_url`, and `contributions` count

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

### pyfhealth

Calculates comprehensive health scores for indexed packages, including GitHub bonuses.

```shell
uv run pyfhealth [options]
```

**Options:**

| Option | Description |
|--------|-------------|
| `-p`, `--profile` | Use a profile (auto-sets target collection name) |
| `-t`, `--target` | Target Typesense collection name (auto-set from profile if not specified) |
| `-l`, `--limit` | Limit number of packages to process (useful for testing) |

**Examples:**

```shell
# Calculate health scores using profile (recommended)
uv run pyfhealth -p plone

# Calculate for Django packages
uv run pyfhealth -p django

# Test with limited packages
uv run pyfhealth -p plone -l 100
```

This calculates health scores based on:
- **Base score (0-100)**: Release recency, documentation, metadata quality
- **GitHub bonuses (+30 max)**: Stars, activity, issue management

Run this command AFTER `pyfgithub` to include GitHub bonuses in the score breakdown.

## Quickstart

### Using Profiles (Recommended)

1. Start the required services:
   ```shell
   docker-compose up -d
   ```

2. Aggregate packages using a profile:
   ```shell
   # For Plone packages (PyPI)
   uv run pyfaggregator -f -p plone

   # For Django packages
   uv run pyfaggregator -f -p django

   # For Flask packages
   uv run pyfaggregator -f -p flask
   ```

3. (Optional) Aggregate npm packages:
   ```shell
   # For Plone npm packages (@plone/*, @plone-collective/*, etc.)
   uv run pyfnpm -f -p plone
   ```

4. Enrich with GitHub data (includes contributors):
   ```shell
   # For Plone (works for both PyPI and npm packages)
   uv run pyfgithub -p plone

   # For Django
   uv run pyfgithub -p django

   # For Flask
   uv run pyfgithub -p flask
   ```

5. Enrich with download statistics (PyPI only):
   ```shell
   # For Plone
   uv run pyfdownloads -p plone

   # For Django
   uv run pyfdownloads -p django

   # For Flask
   uv run pyfdownloads -p flask
   ```

6. Calculate comprehensive health scores (after GitHub data is available):
   ```shell
   # For Plone
   uv run pyfhealth -p plone

   # For Django
   uv run pyfhealth -p django

   # For Flask
   uv run pyfhealth -p flask
   ```

7. Create a search-only API key for clients:
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
- **Multi-Registry Support**: Combine PyPI and npm packages in the same collection (e.g., Plone backend and @plone/* frontend packages)

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

### Working with PyPI and npm Packages

Profiles that include npm configuration can aggregate packages from both registries into the same collection:

**Example: Full Plone ecosystem (backend + frontend)**

```shell
# Aggregate Plone PyPI packages (backend, add-ons)
uv run pyfaggregator -f -p plone

# Aggregate Plone npm packages (@plone/*, @plone-collective/*, @eeacms/*)
uv run pyfnpm -f -p plone

# Enrich all packages with GitHub data (works for both registries)
uv run pyfgithub -p plone

# Enrich PyPI packages with download stats
uv run pyfdownloads -p plone
```

**Querying by Registry:**

In Typesense, you can filter packages by their registry:

```json
{
  "q": "volto",
  "query_by": "name,summary",
  "filter_by": "registry:=npm"
}
```

Or get all packages regardless of registry:

```json
{
  "q": "plone",
  "query_by": "name,summary"
}
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
- `health_score_breakdown` - Detailed scoring with points, problems, and bonuses per category (see Health Score section)
- `health_score_last_calculated` - Unix timestamp of when the health score was last calculated

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
- `contributors` - Array of objects with `username`, `avatar_url`, `contributions`

**Download Statistics:**
- `download_last_day`, `download_last_week`, `download_last_month`
- `download_total`, `download_updated`

**npm-Specific Fields:**
- `registry` - Package registry source: `"pypi"` or `"npm"`
- `npm_scope` - npm package scope (e.g., `"plone"` for `@plone/volto`)
- `npm_quality_score`, `npm_popularity_score`, `npm_maintenance_score`, `npm_final_score` - npm registry scores (0-1)
- `repository_url` - Git repository URL (handles git+https://, git://, ssh:// formats)

### Health Score Calculation

The health score is a 0-100 metric that indicates package quality and maintenance status. It's calculated by the `pyfhealth` command, which should be run after `pyfgithub` to include GitHub bonuses.

**Recommended workflow:**
```shell
pyfaggregator -f -p plone    # Index packages
pyfgithub -p plone           # Fetch GitHub data
pyfdownloads -p plone        # Fetch download stats
pyfhealth -p plone           # Calculate health scores (with GitHub bonuses)
```

#### Base Score (100 points max)

**Release Recency (40 points max):**

| Age | Points |
|-----|--------|
| < 6 months | 40 |
| 6-12 months | 30 |
| 1-2 years | 20 |
| 2-3 years | 10 |
| 3-5 years | 5 |
| > 5 years | 0 |

**Documentation Presence (30 points max):**

| Criterion | Points |
|-----------|--------|
| Has meaningful description (>150 chars) | 18 |
| Has `docs_url` | +4 (bonus) |
| Has documentation links in `project_urls` | +3 (bonus) |
| Has meaningful screenshots in documentation | +5 (bonus) |

*Documentation Link Requirement:* If the README has fewer than 500 words, at least one external documentation link (`docs_url` or a documentation URL in `project_urls`) is recommended. Packages with comprehensive READMEs (500+ words) don't require external documentation links.

*Screenshot Detection:* Images in the package description HTML are analyzed to find documentation-worthy visuals. Badge images (from shields.io, codecov.io, etc.) are filtered out, and only images with a width of at least 200 pixels are counted as meaningful screenshots.

**Metadata Quality (30 points max):**

| Criterion | Points |
|-----------|--------|
| Has maintainer or author info | 10 |
| Has license | 10 |
| Has at least 3 classifiers | 10 |

#### GitHub Bonus (up to +30 points)

When GitHub data is available, bonus points are added. The final score is capped at 100.

**Stars Bonus (up to +10 points):**

| Stars | Bonus |
|-------|-------|
| 1000+ | +10 |
| 500-999 | +7 |
| 100-499 | +5 |
| 50-99 | +3 |
| 10-49 | +1 |
| < 10 | 0 |

**Activity Bonus (up to +10 points):**

| Last GitHub Update | Bonus |
|--------------------|-------|
| Within 30 days | +10 |
| Within 90 days | +7 |
| Within 180 days | +5 |
| Within 365 days | +3 |
| > 1 year | 0 |

**Issue Management Bonus (up to +10 points):**

Based on the ratio of open issues to stars (lower is better):

| Issues/Stars Ratio | Bonus |
|--------------------|-------|
| < 0.1 (Excellent) | +10 |
| 0.1-0.3 (Good) | +7 |
| 0.3-0.5 (Fair) | +5 |
| 0.5-1.0 (Poor) | +3 |
| > 1.0 (Very poor) | 0 |

#### Score Breakdown Structure

The `health_score_breakdown` field contains detailed scoring information organized by category. Each category includes points earned, problems found, and bonuses applied:

```json
{
  "recency": {
    "points": 40,
    "problems": [],
    "bonuses": []
  },
  "documentation": {
    "points": 25,
    "problems": [],
    "bonuses": [
      {"reason": "has dedicated docs URL", "points": 4},
      {"reason": "has documentation project URL", "points": 3}
    ]
  },
  "metadata": {
    "points": 30,
    "problems": [],
    "bonuses": []
  },
  "github_stars_bonus": 5,
  "github_activity_bonus": 10,
  "github_issue_bonus": 7,
  "github_bonus_total": 22
}
```

**Category Fields:**
- `recency.points` - Points from release recency (0-40)
- `recency.problems` - Issues like "last release over 1 year ago", "no release timestamp"
- `recency.bonuses` - Currently empty (no recency bonuses defined)
- `documentation.points` - Points from documentation presence (0-30)
- `documentation.problems` - Issues like "description too short (<150 chars)", "not enough documentation (extend README to 500+ words or add documentation link)"
- `documentation.bonuses` - Array of `{reason, points}` objects for bonuses: "has dedicated docs URL" (+4), "has documentation project URL" (+3), "has meaningful screenshots" (+5)
- `metadata.points` - Points from metadata quality (0-30)
- `metadata.problems` - Issues like "no license", "fewer than 3 classifiers", "no author info"
- `metadata.bonuses` - Currently empty (metadata criteria are requirements, not bonuses)

**GitHub Bonus Fields (only present when GitHub data is available):**
- `github_stars_bonus` - Bonus from GitHub stars (0-10)
- `github_activity_bonus` - Bonus from GitHub activity (0-10)
- `github_issue_bonus` - Bonus from issue management (0-10)
- `github_bonus_total` - Total GitHub bonus applied

The problems arrays can be used by frontends to show users actionable feedback on how to improve their package's health score.

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

### Continuous Integration

The project uses GitHub Actions for CI, running on every push and pull request to the `master` branch.

**CI Jobs:**

| Job | Description |
|-----|-------------|
| `lint` | Runs ruff linter and format checker on `src` and `tests` |
| `test` | Runs pytest with Python 3.12 |

**Running Locally:**

```shell
# Lint check
uv tool run ruff check src tests

# Format check
uv tool run ruff format --check src tests

# Run tests
uv run --extra test pytest
```


## GUI

We have a GUI which we use for the Plone addon gallery (PAG).
This is a reference implemetation build with SvelteKit.

https://github.com/collective/pyf-gui


## License

The code is open-source and licensed under the Apache License 2.0.


## Credits

- [@jensens](https://github.com/jensens)
- [@veit](https://github.com/veit)
- [@guziel](https://github.com/guziel)
- [@pgrunewald](https://github.com/pgrunewald)
- [@MrTango](https://github.com/MrTango)
- [@pypa](https://github.com/pypa)
