from datetime import datetime, timezone
import time


def process(identifier, data):
    """Calculate a basic health score (0-100) for a package.

    Scoring factors:
    - Release recency (40 points): Based on upload_timestamp
    - Documentation presence (30 points): Has docs_url, description, project_urls
    - Basic metadata quality (30 points): Has maintainer, license, classifiers

    This is a basic score that will be enhanced by the health_calculator enricher.
    """
    score = 0
    breakdown = {}

    # Factor 1: Release recency (40 points max)
    recency_score = calculate_recency_score(data.get("upload_timestamp"))
    score += recency_score
    breakdown["recency"] = recency_score

    # Factor 2: Documentation presence (30 points max)
    docs_score = calculate_docs_score(data)
    score += docs_score
    breakdown["documentation"] = docs_score

    # Factor 3: Metadata quality (30 points max)
    metadata_score = calculate_metadata_score(data)
    score += metadata_score
    breakdown["metadata"] = metadata_score

    # Store results
    data["health_score"] = int(score)
    data["health_score_breakdown"] = breakdown
    data["health_score_last_calculated"] = int(time.time())


def calculate_recency_score(upload_timestamp):
    """Calculate score based on how recent the release is.

    Returns:
        0-40 points based on recency:
        - 40 points: < 6 months old
        - 30 points: 6-12 months old
        - 20 points: 1-2 years old
        - 10 points: 2-3 years old
        - 5 points: 3-5 years old
        - 0 points: > 5 years old
    """
    if not upload_timestamp:
        return 0

    try:
        if isinstance(upload_timestamp, int):
            # Unix timestamp (int64) - 0 means missing timestamp
            if upload_timestamp == 0:
                return 0
            upload_dt = datetime.fromtimestamp(upload_timestamp, tz=timezone.utc)
        elif isinstance(upload_timestamp, str):
            # ISO format (legacy support): "2024-01-15T10:30:00"
            upload_dt = datetime.fromisoformat(upload_timestamp.replace('Z', '+00:00'))
        else:
            return 0

        now = datetime.now(timezone.utc)
        age_days = (now - upload_dt).days

        if age_days < 180:  # < 6 months
            return 40
        elif age_days < 365:  # 6-12 months
            return 30
        elif age_days < 730:  # 1-2 years
            return 20
        elif age_days < 1095:  # 2-3 years
            return 10
        elif age_days < 1825:  # 3-5 years
            return 5
        else:  # > 5 years
            return 0
    except (ValueError, TypeError, AttributeError, OSError):
        return 0


def calculate_docs_score(data):
    """Calculate score based on documentation presence.

    Returns:
        0-30 points:
        - 15 points: Has docs_url
        - 10 points: Has meaningful description (>100 chars)
        - 5 points: Has project_urls with documentation links
    """
    score = 0

    # Check for dedicated docs URL
    if data.get("docs_url"):
        score += 15

    # Check for meaningful description
    description = data.get("description", "")
    if description and len(description) > 100:
        score += 10

    # Check for project URLs (documentation, homepage, etc.)
    project_urls = data.get("project_urls", {})
    if project_urls:
        # Look for documentation-related URLs
        doc_keywords = ["documentation", "docs", "homepage", "home"]
        for key in project_urls.keys():
            if any(kw in key.lower() for kw in doc_keywords):
                score += 5
                break

    return score


def calculate_metadata_score(data):
    """Calculate score based on metadata quality.

    Returns:
        0-30 points:
        - 10 points: Has maintainer or author info
        - 10 points: Has license
        - 10 points: Has classifiers (at least 3)
    """
    score = 0

    # Check for maintainer/author info
    if data.get("maintainer") or data.get("author"):
        score += 10

    # Check for license
    if data.get("license"):
        score += 10

    # Check for classifiers
    classifiers = data.get("classifiers", [])
    if len(classifiers) >= 3:
        score += 10

    return score


def load(settings):
    return process
