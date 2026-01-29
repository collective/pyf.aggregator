# Tech Stack

## Backend

| Technology | Purpose |
|------------|---------|
| **Python 3.12+** | Core application language |
| **Celery** | Distributed task queue for async processing |
| **Redis/Valkey** | Message broker for Celery, RSS deduplication cache |

## Search Engine

| Technology | Purpose |
|------------|---------|
| **Typesense** | Full-text search with faceting, sorting, and filtering |

## Data Sources

| Source | Data Provided |
|--------|---------------|
| **PyPI JSON API** | Package metadata, version info, classifiers |
| **PyPI Simple API** | Package listing (500k+ packages) |
| **PyPI RSS Feeds** | New packages and releases (real-time updates) |
| **GitHub API** | Stars, watchers, issues, last update |
| **pypistats.org** | Download statistics (day/week/month) |

## Key Libraries

| Library | Purpose |
|---------|---------|
| **httpx** | Async HTTP client for API requests |
| **feedparser** | RSS feed parsing |
| **lxml** | HTML/XML parsing |
| **PyGithub** | GitHub API client |
| **typesense** | Typesense Python client |
| **pyyaml** | Profile configuration |
| **python-dotenv** | Environment variable management |

## Development Tools

| Tool | Purpose |
|------|---------|
| **uv** | Python package manager and virtual environment |
| **pytest** | Test framework with coverage |
| **responses** | HTTP request mocking for tests |
| **ruff** | Code formatting and linting |

## Infrastructure

| Component | Configuration |
|-----------|---------------|
| **Docker Compose** | Local development (Typesense + Redis) |
| **ThreadPoolExecutor** | Parallel I/O processing (20 workers default) |
| **Celery Beat** | Periodic task scheduling |

## Configuration

- **Environment Variables** - All secrets and settings via `.env`
- **YAML Profiles** - Framework classifier definitions in `profiles.yaml`
- **pyproject.toml** - Project metadata and dependencies
