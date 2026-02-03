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

    # Initialize problems dict
    problems = {
        "documentation": [],
        "metadata": [],
        "recency": [],
    }

    # Factor 1: Release recency (40 points max)
    recency_score, recency_problems = calculate_recency_score_with_problems(
        data.get("upload_timestamp")
    )
    score += recency_score
    breakdown["recency"] = recency_score
    problems["recency"] = recency_problems

    # Factor 2: Documentation presence (30 points max)
    docs_score, docs_problems = calculate_docs_score_with_problems(data)
    score += docs_score
    breakdown["documentation"] = docs_score
    problems["documentation"] = docs_problems

    # Factor 3: Metadata quality (30 points max)
    metadata_score, metadata_problems = calculate_metadata_score_with_problems(data)
    score += metadata_score
    breakdown["metadata"] = metadata_score
    problems["metadata"] = metadata_problems

    # Store results
    data["health_score"] = int(score)
    data["health_score_breakdown"] = breakdown
    data["health_score_last_calculated"] = int(time.time())

    # Store problems as separate arrays
    data["health_problems_documentation"] = problems["documentation"]
    data["health_problems_metadata"] = problems["metadata"]
    data["health_problems_recency"] = problems["recency"]


def calculate_recency_score_with_problems(upload_timestamp):
    """Calculate score based on how recent the release is.

    Returns:
        tuple: (score, problems_list)
        Score is 0-40 points based on recency:
        - 40 points: < 6 months old
        - 30 points: 6-12 months old
        - 20 points: 1-2 years old
        - 10 points: 2-3 years old
        - 5 points: 3-5 years old
        - 0 points: > 5 years old
    """
    problems = []

    if not upload_timestamp:
        problems.append("no release timestamp")
        return 0, problems

    try:
        if isinstance(upload_timestamp, int):
            # Unix timestamp (int64) - 0 means missing timestamp
            if upload_timestamp == 0:
                problems.append("no release timestamp")
                return 0, problems
            upload_dt = datetime.fromtimestamp(upload_timestamp, tz=timezone.utc)
        elif isinstance(upload_timestamp, str):
            # ISO format (legacy support): "2024-01-15T10:30:00"
            upload_dt = datetime.fromisoformat(upload_timestamp.replace("Z", "+00:00"))
        else:
            problems.append("no release timestamp")
            return 0, problems

        now = datetime.now(timezone.utc)
        age_days = (now - upload_dt).days

        if age_days < 180:  # < 6 months
            return 40, problems
        elif age_days < 365:  # 6-12 months
            problems.append("last release over 6 months ago")
            return 30, problems
        elif age_days < 730:  # 1-2 years
            problems.append("last release over 1 year ago")
            return 20, problems
        elif age_days < 1095:  # 2-3 years
            problems.append("last release over 2 years ago")
            return 10, problems
        elif age_days < 1825:  # 3-5 years
            problems.append("last release over 3 years ago")
            return 5, problems
        else:  # > 5 years
            problems.append("last release over 5 years ago")
            return 0, problems
    except (ValueError, TypeError, AttributeError, OSError):
        problems.append("no release timestamp")
        return 0, problems


def calculate_recency_score(upload_timestamp):
    """Calculate score based on how recent the release is.

    Returns:
        0-40 points based on recency (backward compatible wrapper)
    """
    score, _ = calculate_recency_score_with_problems(upload_timestamp)
    return score


def calculate_docs_score_with_problems(data):
    """Calculate score based on documentation presence.

    Returns:
        tuple: (score, problems_list)
        Score is 0-30 points:
        - 5 points: Has docs_url
        - 20 points: Has meaningful description (>150 chars)
        - 5 points: Has project_urls with documentation links
    """
    score = 0
    problems = []

    # Check for dedicated docs URL
    if data.get("docs_url"):
        score += 5
    else:
        problems.append("no docs_url")

    # Check for meaningful description
    description = data.get("description", "")
    if description and len(description) > 150:
        score += 20
    else:
        problems.append("description too short (<150 chars)")

    # Check for project URLs (documentation, homepage, etc.)
    project_urls = data.get("project_urls", {})
    has_doc_url = False
    if project_urls:
        # Look for documentation-related URLs
        doc_keywords = ["documentation", "docs", "homepage", "home"]
        for key in project_urls.keys():
            if any(kw in key.lower() for kw in doc_keywords):
                has_doc_url = True
                score += 5
                break

    if not has_doc_url:
        problems.append("no documentation project URLs")

    return score, problems


def calculate_docs_score(data):
    """Calculate score based on documentation presence.

    Returns:
        0-30 points (backward compatible wrapper)
    """
    score, _ = calculate_docs_score_with_problems(data)
    return score


def calculate_metadata_score_with_problems(data):
    """Calculate score based on metadata quality.

    Returns:
        tuple: (score, problems_list)
        Score is 0-30 points:
        - 10 points: Has maintainer or author info
        - 10 points: Has license
        - 10 points: Has classifiers (at least 3)
    """
    score = 0
    problems = []

    # Check for maintainer/author info
    has_maintainer = bool(data.get("maintainer"))
    has_author = bool(data.get("author"))

    if has_maintainer or has_author:
        score += 10
    else:
        # Both missing - report both problems
        problems.append("no maintainer info")
        problems.append("no author info")

    # Check for license
    if data.get("license"):
        score += 10
    else:
        problems.append("no license")

    # Check for classifiers
    classifiers = data.get("classifiers", [])
    if len(classifiers) >= 3:
        score += 10
    else:
        problems.append("fewer than 3 classifiers")

    return score, problems


def calculate_metadata_score(data):
    """Calculate score based on metadata quality.

    Returns:
        0-30 points (backward compatible wrapper)
    """
    score, _ = calculate_metadata_score_with_problems(data)
    return score


def load(settings):
    return process
