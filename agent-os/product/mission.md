# Product Mission

## Problem

Framework ecosystems (Plone, Django, Flask) span multiple package registries - Python packages on PyPI and frontend packages on npm. Discovering quality packages across these registries is difficult. Developers struggle to find well-maintained, actively developed packages that match their framework version. Native registry searches lack filtering by framework classifiers, repository activity (GitHub/GitLab), download trends, and package health metrics.

## Target Users

- **Framework developers** looking for add-ons/plugins compatible with their framework version
- **Frontend developers** finding npm packages for framework-specific UIs (e.g., Volto for Plone)
- **Package maintainers** wanting visibility into their ecosystem's health
- **DevOps/Security teams** needing to audit package dependencies across registries
- **Community managers** tracking ecosystem growth and adoption

## Solution

pyf.aggregator provides a unified package discovery platform that:

1. **Aggregates** metadata from multiple registries (PyPI, npm) with framework filtering
2. **Enriches** packages with repository statistics from GitHub and GitLab (stars, activity, issues) plus download trends
3. **Indexes** everything in Typesense for fast, faceted search
4. **Automates** continuous updates via RSS monitoring and scheduled refreshes
5. **Scores** package health based on maintenance, documentation, and activity

The multi-profile architecture allows independent ecosystems (Plone, Django, Flask) to have their own curated collections while sharing infrastructure and enrichment pipelines.
