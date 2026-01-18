# Python Package Filter Aggregator

The Python Package Filter Aggregator (`pyf.aggregator`) aggregates the meta
information of all Python packages in the PyPI and enhances it with data from GitHub.


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
GITHUB_COOLOFFTIME=2

# Redis Configuration (for Celery task queue)
REDIS_HOST=localhost:6379
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
| `-s`, `--sincefile` | File to store timestamp of last run (default: `.pyaggregator.since`) |
| `-l`, `--limit` | Limit the number of packages to process |
| `-fn`, `--filter-name` | Filter packages by name (substring match) |
| `-ft`, `--filter-troove` | Filter by trove classifier (can be used multiple times) |
| `-p`, `--profile` | Use a predefined profile (loads classifiers and sets collection name) |
| `-t`, `--target` | Target Typesense collection name (auto-set from profile if not specified) |

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
```


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

4. Create a search-only API key for clients:
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

4. Create a collection alias (required for client access):
   ```shell
   pyfupdater --add-alias -s packages -t packages1
   ```

5. Create a search-only API key for clients:
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

### Queue-Based Processing (Planned)

The project is being refactored to use a queue-based architecture with Celery for improved scalability and reliability:

- **Redis** serves as the message broker
- **Celery workers** process tasks asynchronously
- **Periodic tasks** monitor PyPI RSS feeds for new packages and releases

Planned Celery tasks:
- `inspect_project` - Fetch and inspect a project from PyPI
- `update_project` - Process package release data
- `update_github` - Update GitHub metadata for a package
- `read_rss_new_projects_and_queue` - Monitor RSS for new projects
- `read_rss_new_releases_and_queue` - Monitor RSS for new releases
- `queue_all_github_updates` - Queue GitHub updates for all packages

To run a Celery worker (once fully implemented):
```shell
celery -A pyf.aggregator.queue worker --loglevel=info
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
