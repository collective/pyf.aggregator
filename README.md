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

Git clone the package and install it in a virtual environment:

```shell
git clone https://github.com/collective/pyf.aggregator.git
cd pyf.aggregator
python -m venv venv
./venv/bin/pip install -e .
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


## CLI Commands

### pyfaggregator

Fetches package information from PyPI and indexes it into Typesense.

```shell
./venv/bin/pyfaggregator [options]
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
| `-t`, `--target` | Target Typesense collection name |

**Examples:**

```shell
# Full fetch of all Plone packages
./venv/bin/pyfaggregator -f -ft "Framework :: Plone" -t packages1

# Incremental update
./venv/bin/pyfaggregator -i -ft "Framework :: Plone" -t packages1

# Fetch with limit for testing
./venv/bin/pyfaggregator -f -ft "Framework :: Plone" -t packages1 -l 100
```

### pyfgithub

Enriches indexed packages with data from GitHub (stars, watchers, issues, etc.).

```shell
./venv/bin/pyfgithub -t <collection_name>
```

**Example:**

```shell
./venv/bin/pyfgithub -t packages1
```

This adds the following fields to each package (if a GitHub repository is found):
- `github_stars` - Number of stargazers
- `github_watchers` - Number of watchers
- `github_updated` - Last update timestamp
- `github_open_issues` - Number of open issues
- `github_url` - URL to the GitHub repository

### pyfupdater

Utility for managing Typesense collections, aliases, and API keys.

```shell
./venv/bin/pyfupdater [options]
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
| `-s`, `--source` | Source collection name (for migrate/alias) |
| `-t`, `--target` | Target collection name |
| `-key`, `--key` | Custom API key value (optional, auto-generated if not provided) |

**Examples:**

```shell
# List all collections
./venv/bin/pyfupdater -ls

# List collection names only
./venv/bin/pyfupdater -lsn

# List aliases
./venv/bin/pyfupdater -lsa

# Add an alias (packages -> packages1)
./venv/bin/pyfupdater --add-alias -s packages -t packages1

# Migrate data between collections
./venv/bin/pyfupdater --migrate -s packages1 -t packages2

# Create a search-only API key
./venv/bin/pyfupdater --add-search-only-apikey -t packages

# Create a search-only API key with custom value
./venv/bin/pyfupdater --add-search-only-apikey -t packages -key your_custom_key
```


## Quickstart

1. Start the required services:
   ```shell
   docker-compose up -d
   ```

2. Aggregate Plone packages from PyPI:
   ```shell
   ./venv/bin/pyfaggregator -f -ft "Framework :: Plone" -t packages1
   ```

3. Enrich with GitHub data:
   ```shell
   ./venv/bin/pyfgithub -t packages1
   ```

4. Create a collection alias (required for client access):
   ```shell
   ./venv/bin/pyfupdater --add-alias -s packages -t packages1
   ```

5. Create a search-only API key for clients:
   ```shell
   ./venv/bin/pyfupdater --add-search-only-apikey -t packages
   ```


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
