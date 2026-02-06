from datetime import datetime, timezone
import re
import time

from pyf.aggregator.plugins.screenshot_detector import detect_screenshots


def count_words(text):
    """Count words in a text string."""
    if not text:
        return 0
    return len(text.split())


def process(identifier, data):
    """Calculate a basic health score (0-100) for a package.

    Scoring factors:
    - Release recency (40 points): Based on upload_timestamp
    - Documentation presence (30 points): Has docs_url, description, project_urls
    - Basic metadata quality (30 points): Has maintainer, license, classifiers

    This is a basic score that will be enhanced by the health_calculator enricher.
    """
    score = 0

    # Factor 1: Release recency (40 points max)
    recency_score, recency_problems, recency_bonuses, recency_max = (
        calculate_recency_score_with_problems(data.get("upload_timestamp"))
    )
    score += recency_score

    # Factor 2: Documentation presence (30 points max)
    docs_score, docs_problems, docs_bonuses, docs_max = (
        calculate_docs_score_with_problems(data)
    )
    score += docs_score

    # Factor 3: Metadata quality (30 points max)
    metadata_score, metadata_problems, metadata_bonuses, metadata_max = (
        calculate_metadata_score_with_problems(data)
    )
    score += metadata_score

    # Build new breakdown structure with points, max_points, problems, and bonuses
    breakdown = {
        "recency": {
            "points": recency_score,
            "max_points": recency_max,
            "problems": recency_problems,
            "bonuses": recency_bonuses,
        },
        "documentation": {
            "points": docs_score,
            "max_points": docs_max,
            "problems": docs_problems,
            "bonuses": docs_bonuses,
        },
        "metadata": {
            "points": metadata_score,
            "max_points": metadata_max,
            "problems": metadata_problems,
            "bonuses": metadata_bonuses,
        },
    }

    # Store results
    data["health_score"] = int(score)
    data["health_score_breakdown"] = breakdown
    data["health_score_last_calculated"] = int(time.time())


MAX_RECENCY_POINTS = 40
MAX_DOCS_POINTS = 18  # Base points only, bonuses are extra credit
MAX_METADATA_POINTS = 30


def calculate_recency_score_with_problems(upload_timestamp):
    """Calculate score based on how recent the release is.

    Returns:
        tuple: (score, problems_list, bonuses_list, max_points)
        Score is 0-40 points based on recency:
        - 40 points: < 6 months old
        - 30 points: 6-12 months old
        - 20 points: 1-2 years old
        - 10 points: 2-3 years old
        - 5 points: 3-5 years old
        - 0 points: > 5 years old
    """
    problems = []
    bonuses = []

    if not upload_timestamp:
        problems.append("no release timestamp")
        return 0, problems, bonuses, MAX_RECENCY_POINTS

    try:
        if isinstance(upload_timestamp, int):
            # Unix timestamp (int64) - 0 means missing timestamp
            if upload_timestamp == 0:
                problems.append("no release timestamp")
                return 0, problems, bonuses, MAX_RECENCY_POINTS
            upload_dt = datetime.fromtimestamp(upload_timestamp, tz=timezone.utc)
        elif isinstance(upload_timestamp, str):
            # ISO format (legacy support): "2024-01-15T10:30:00"
            upload_dt = datetime.fromisoformat(upload_timestamp.replace("Z", "+00:00"))
        else:
            problems.append("no release timestamp")
            return 0, problems, bonuses, MAX_RECENCY_POINTS

        now = datetime.now(timezone.utc)
        age_days = (now - upload_dt).days

        if age_days < 180:  # < 6 months
            return 40, problems, bonuses, MAX_RECENCY_POINTS
        elif age_days < 365:  # 6-12 months
            problems.append("last release over 6 months ago")
            return 30, problems, bonuses, MAX_RECENCY_POINTS
        elif age_days < 730:  # 1-2 years
            problems.append("last release over 1 year ago")
            return 20, problems, bonuses, MAX_RECENCY_POINTS
        elif age_days < 1095:  # 2-3 years
            problems.append("last release over 2 years ago")
            return 10, problems, bonuses, MAX_RECENCY_POINTS
        elif age_days < 1825:  # 3-5 years
            problems.append("last release over 3 years ago")
            return 5, problems, bonuses, MAX_RECENCY_POINTS
        else:  # > 5 years
            problems.append("last release over 5 years ago")
            return 0, problems, bonuses, MAX_RECENCY_POINTS
    except (ValueError, TypeError, AttributeError, OSError):
        problems.append("no release timestamp")
        return 0, problems, bonuses, MAX_RECENCY_POINTS


def calculate_recency_score(upload_timestamp):
    """Calculate score based on how recent the release is.

    Returns:
        0-40 points based on recency (backward compatible wrapper)
    """
    score, _, _, _ = calculate_recency_score_with_problems(upload_timestamp)
    return score


def is_meaningful_docs_url(url):
    """Check if a URL points to meaningful external documentation.

    Returns False for:
    - PyPI detail pages (pypi.org/project/*)
    - GitHub/GitLab repo root or README links

    Returns True for:
    - ReadTheDocs URLs
    - GitHub/GitLab wiki or docs pages
    - Other external documentation URLs
    """
    if not url:
        return False

    url_lower = url.lower()

    # Reject PyPI detail pages
    if "pypi.org/project/" in url_lower:
        return False

    # Check GitHub/GitLab patterns
    # Match github.com/user/repo or gitlab.com/user/repo with optional #anchor or trailing slash
    github_gitlab_root = re.match(
        r"^https?://(www\.)?(github|gitlab)\.(com|io)/[^/]+/[^/]+(/?|#.*)$",
        url_lower,
    )
    if github_gitlab_root:
        return False

    return True


def calculate_docs_score_with_problems(data):
    """Calculate score based on documentation presence.

    Returns:
        tuple: (score, problems_list, bonuses_list, max_points)
        Score is 0-30 points:
        - 4 points: Has docs_url (bonus)
        - 18 points: Has meaningful description (>150 chars)
        - 3 points: Has project_urls with documentation links (bonus)
        - 5 points: Has meaningful screenshots in documentation (bonus)

    Documentation link requirement:
        - If README >= 500 words: no external docs needed (comprehensive README)
        - If README < 500 words AND no docs_url AND no documentation links:
          report "not enough documentation" problem
    """
    score = 0
    problems = []
    bonuses = []

    # Check for dedicated docs URL (4 points, bonus)
    docs_url = data.get("docs_url")
    has_docs_url = bool(docs_url) and is_meaningful_docs_url(docs_url)
    if has_docs_url:
        score += 4
        bonuses.append({"reason": "has dedicated docs URL", "points": 4})

    # Check for meaningful description (18 points)
    description = data.get("description", "")
    if description and len(description) > 150:
        score += 18
    else:
        problems.append("description too short (<150 chars)")

    # Check for project URLs (documentation, homepage, etc.) (3 points, bonus)
    project_urls = data.get("project_urls", {})
    has_doc_project_url = False
    if project_urls:
        # Look for documentation-related URLs
        doc_keywords = ["documentation", "docs", "homepage", "home"]
        for key, url in project_urls.items():
            if any(kw in key.lower() for kw in doc_keywords):
                # Validate the URL points to real documentation
                if is_meaningful_docs_url(url):
                    has_doc_project_url = True
                    score += 3
                    bonuses.append(
                        {"reason": "has documentation project URL", "points": 3}
                    )
                    break

    # Combined documentation check: 500-word threshold
    # Count words in first_chapter + main_content (excluding changelog)
    # These fields are set by description_splitter.py for both PyPI and npm packages
    first_chapter = data.get("first_chapter", "")
    main_content = data.get("main_content", "")
    readme_word_count = count_words(first_chapter) + count_words(main_content)

    # If README < 500 words AND no docs_url AND no documentation links: report problem
    if readme_word_count < 500 and not has_docs_url and not has_doc_project_url:
        problems.append(
            "not enough documentation (extend README to 500+ words or add documentation link)"
        )

    # Check for meaningful screenshots (5 points, bonus only - no penalty when missing)
    description_html = data.get("description", "")
    if description_html:
        screenshot_result = detect_screenshots(description_html)
        if screenshot_result["has_screenshots"]:
            score += 5
            bonuses.append({"reason": "has meaningful screenshots", "points": 5})

    return score, problems, bonuses, MAX_DOCS_POINTS


def calculate_docs_score(data):
    """Calculate score based on documentation presence.

    Returns:
        0-30 points (backward compatible wrapper)
    """
    score, _, _, _ = calculate_docs_score_with_problems(data)
    return score


def calculate_metadata_score_with_problems(data):
    """Calculate score based on metadata quality.

    Returns:
        tuple: (score, problems_list, bonuses_list, max_points)
        Score is 0-30 points:
        - 10 points: Has maintainer or author info
        - 10 points: Has license
        - 10 points: Has classifiers (at least 3)
    """
    score = 0
    problems = []
    bonuses = []

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

    # Check for classifiers (PyPI) or keywords (npm)
    registry = data.get("registry", "pypi")
    if registry == "npm":
        keywords = data.get("keywords", [])
        if len(keywords) >= 3:
            score += 10
        else:
            problems.append("fewer than 3 keywords")
    else:
        classifiers = data.get("classifiers", [])
        if len(classifiers) >= 3:
            score += 10
        else:
            problems.append("fewer than 3 classifiers")

    return score, problems, bonuses, MAX_METADATA_POINTS


def calculate_metadata_score(data):
    """Calculate score based on metadata quality.

    Returns:
        0-30 points (backward compatible wrapper)
    """
    score, _, _, _ = calculate_metadata_score_with_problems(data)
    return score


def load(settings):
    return process
