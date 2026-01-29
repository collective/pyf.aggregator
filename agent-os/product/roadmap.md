# Product Roadmap

## Phase 1: MVP (Current)

The following features are complete and operational:

### Data Ingestion
- [x] Full fetch of 500k+ PyPI packages with parallel processing (20 workers)
- [x] Incremental RSS-based updates (new packages and releases)
- [x] Refresh mode for updating all versions of indexed packages
- [x] Classifier-based filtering with profile system (Plone, Django, Flask)
- [x] Rate limiting and retry logic on all external APIs

### Data Processing
- [x] Version parsing plugin (major/minor/bugfix, sortable format)
- [x] Framework version extraction from classifiers
- [x] Python version extraction from classifiers
- [x] RST to HTML description conversion
- [x] Health score calculation (recency, documentation, metadata)

### Search & Indexing
- [x] Typesense integration with 60+ fields
- [x] Faceting on classifiers, framework versions, Python versions
- [x] Version sorting (stable versions before pre-releases)
- [x] Zero-downtime collection recreation with alias switching

### Enrichment
- [x] GitHub enricher (stars, watchers, open issues, last update)
- [x] Download statistics from pypistats.org
- [x] Memoization for cross-profile GitHub cache

### Operations
- [x] 4 CLI commands (pyfaggregator, pyfgithub, pyfdownloads, pyfupdater)
- [x] Celery task queue with 8 task types
- [x] 5 periodic schedules (RSS monitoring, weekly refresh, monthly fetch)
- [x] Redis-based RSS deduplication
- [x] DEFAULT_PROFILE environment variable

## Phase 2: GitLab Support

Add support for packages hosted on GitLab.com alongside existing GitHub integration.

### Features
- [ ] GitLab URL detection in package metadata (home_page, project_urls)
- [ ] GitLab API integration for repository statistics
- [ ] New `pyfgitlab` CLI command mirroring `pyfgithub` functionality
- [ ] New fields: `repo_platform` (github/gitlab/other)
- [ ] New fields: `gitlab_stars`, `gitlab_watchers`, `gitlab_open_issues`, `gitlab_updated`, `gitlab_url`
- [ ] Rate limiting for GitLab API (similar to GitHub)
- [ ] Celery task for GitLab enrichment
- [ ] Update health score to consider GitLab activity when GitHub not available

### Technical Considerations
- GitLab API uses different terminology (stars = "star_count", watchers = "forks_count" or similar)
- Authentication via GitLab personal access token
- Handle both gitlab.com and self-hosted GitLab instances (future)

## Phase 3: npm Package Support

Extend the platform to index npm packages used by frontend frameworks.

### Features
- [ ] npm registry API integration (registry.npmjs.org)
- [ ] New profile type for npm packages (e.g., "plone-npm" for Plone frontend packages)
- [ ] npm-specific metadata fields (dependencies, devDependencies, peerDependencies)
- [ ] `pyfnpm` CLI command for npm aggregation
- [ ] npm download statistics from npm-stat.com or bundlephobia
- [ ] Cross-reference npm packages with their Python counterparts
- [ ] Keyword-based filtering (e.g., "plone", "volto") since npm lacks classifier system
- [ ] Separate Typesense collection for npm packages with appropriate schema

### Technical Considerations
- npm uses different versioning semantics (semver with ranges)
- npm packages reference GitHub/GitLab repos (reuse existing enrichers)
- Consider bundlephobia integration for bundle size metrics
- npm registry has different rate limits than PyPI

## Future Considerations

- Security vulnerability integration (OSV, Snyk)
- Analytics dashboard for ecosystem health trends
- REST API for programmatic access
