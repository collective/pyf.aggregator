from dotenv import load_dotenv
from argparse import ArgumentParser
from datetime import datetime
from pyf.aggregator.db import TypesenceConnection, TypesensePackagesCollection
from pyf.aggregator.logger import logger
from pyf.aggregator.profiles import ProfileManager

import functools
import requests
import sys
import time
import os

load_dotenv()

DEFAULT_PROFILE = os.getenv("DEFAULT_PROFILE")

# Rate limiting configuration
PYPISTATS_RATE_LIMIT_DELAY = float(os.getenv("PYPISTATS_RATE_LIMIT_DELAY", 2.0))
PYPISTATS_MAX_RETRIES = int(os.getenv("PYPISTATS_MAX_RETRIES", 3))
PYPISTATS_RETRY_BACKOFF = float(os.getenv("PYPISTATS_RETRY_BACKOFF", 2.0))

parser = ArgumentParser(
    description="Enrich package data with download statistics from pypistats.org"
)
parser.add_argument("-t", "--target", nargs="?", type=str)
parser.add_argument(
    "-p",
    "--profile",
    help="Profile name for classifier filtering (overrides DEFAULT_PROFILE env var)",
    nargs="?",
    type=str,
)
parser.add_argument(
    "-l",
    "--limit",
    help="Limit number of packages to process (for testing)",
    nargs="?",
    type=int,
)


def memoize(obj):
    """Decorator for memoizing the return value."""
    cache = obj.cache = {}

    @functools.wraps(obj)
    def memoizer(*args, **kwargs):
        key = args[1]
        if key not in cache:
            cache[key] = obj(*args, **kwargs)
        return cache[key]

    return memoizer


class Enricher(TypesenceConnection, TypesensePackagesCollection):
    """
    Enrich pyf data with download statistics from pypistats.org
    """

    def __init__(self, limit=None):
        super().__init__()
        self.limit = limit
        self._last_request_time = 0

    def run(self, target=None):
        search_parameters = {
            "q": "*",
            "query_by": "name",
            "group_by": "name_sortable",
            "group_limit": 1,
            "per_page": 50,
        }
        results = self.ts_search(target, search_parameters)

        per_page = results["request_params"]["per_page"]
        found = results["found"]
        logger.info(f"[{datetime.now()}][found] Start enriching data from pypistats...")
        enrich_counter = 0
        page = 0

        for p in range(0, found, per_page):
            page += 1
            results = self.ts_search(target, search_parameters, page)
            for group in results["grouped_hits"]:
                for item in group["hits"]:
                    data = item["document"]
                    package_name = data.get("name")
                    if not package_name:
                        continue

                    # Check limit if set
                    if self.limit and enrich_counter >= self.limit:
                        logger.info(f"Reached limit of {self.limit} packages")
                        return

                    pypistats_data = self._get_pypistats_data(package_name)
                    if not pypistats_data:
                        continue

                    enrich_counter += 1
                    self.update_doc(
                        target, data["id"], pypistats_data, page, enrich_counter
                    )

        logger.info(f"[{datetime.now()}] done")

    def update_doc(self, target, id, data, page, enrich_counter):
        document = {
            "download_last_day": data["downloads"]["last_day"],
            "download_last_week": data["downloads"]["last_week"],
            "download_last_month": data["downloads"]["last_month"],
            "download_updated": data["downloads"]["updated"].timestamp(),
        }

        # Add total if available
        if data["downloads"].get("total") is not None:
            document["download_total"] = data["downloads"]["total"]

        self.client.collections[target].documents[id].update(document)
        logger.info(f"[{page}/{enrich_counter}] Updated document {id}")

    def ts_search(self, target, search_parameters, page=1):
        search_parameters["page"] = page
        return self.client.collections[target].documents.search(search_parameters)

    def _apply_rate_limit(self):
        """Apply rate limiting between API requests."""
        current_time = time.time()
        time_since_last_request = current_time - self._last_request_time

        if time_since_last_request < PYPISTATS_RATE_LIMIT_DELAY:
            sleep_time = PYPISTATS_RATE_LIMIT_DELAY - time_since_last_request
            time.sleep(sleep_time)

        self._last_request_time = time.time()

    @memoize
    def _get_pypistats_data(self, package_name):
        """Return download statistics from pypistats.org API.

        Args:
            package_name: Name of the package to fetch stats for

        Returns:
            dict with structure: {"downloads": {"last_day": int, "last_week": int,
                                               "last_month": int, "total": int or None,
                                               "updated": datetime}}
            or empty dict if package not found or error occurred
        """
        url = f"https://pypistats.org/api/packages/{package_name}/recent"

        for attempt in range(PYPISTATS_MAX_RETRIES):
            try:
                # Apply rate limiting
                self._apply_rate_limit()

                response = requests.get(url, timeout=10)

                # Handle 404 - package not found
                if response.status_code == 404:
                    logger.debug(f"Package {package_name} not found on pypistats")
                    return {}

                # Handle 429 - rate limiting
                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After")
                    if retry_after:
                        try:
                            wait_time = float(retry_after)
                        except ValueError:
                            wait_time = PYPISTATS_RETRY_BACKOFF * (2**attempt)
                    else:
                        wait_time = PYPISTATS_RETRY_BACKOFF * (2**attempt)

                    logger.warning(
                        f"Rate limited by pypistats for {package_name}. "
                        f"Waiting {wait_time}s before retry {attempt + 1}/{PYPISTATS_MAX_RETRIES}"
                    )
                    time.sleep(wait_time)
                    continue

                # Handle other errors
                if response.status_code != 200:
                    logger.warning(
                        f"Unexpected status {response.status_code} for {package_name}"
                    )
                    return {}

                # Parse JSON response
                try:
                    data = response.json()
                except ValueError:
                    logger.error(f"Invalid JSON response for {package_name}")
                    return {}

                # Extract download stats
                stats_data = data.get("data", {})

                result = {
                    "downloads": {
                        "last_day": stats_data.get("last_day", 0) or 0,
                        "last_week": stats_data.get("last_week", 0) or 0,
                        "last_month": stats_data.get("last_month", 0) or 0,
                        "total": None,  # pypistats recent API doesn't provide total
                        "updated": datetime.now(),
                    }
                }

                return result

            except requests.exceptions.Timeout:
                logger.warning(
                    f"Timeout fetching stats for {package_name}. "
                    f"Retry {attempt + 1}/{PYPISTATS_MAX_RETRIES}"
                )
                if attempt < PYPISTATS_MAX_RETRIES - 1:
                    time.sleep(PYPISTATS_RETRY_BACKOFF * (2**attempt))
                    continue
                return {}

            except requests.exceptions.RequestException as e:
                logger.error(f"Error fetching stats for {package_name}: {e}")
                return {}

        # All retries exhausted
        logger.error(
            f"Failed to fetch stats for {package_name} after {PYPISTATS_MAX_RETRIES} retries"
        )
        return {}


def main():
    args = parser.parse_args()

    # Handle profile (CLI argument or DEFAULT_PROFILE env var)
    effective_profile = args.profile or DEFAULT_PROFILE
    profile_source = "from CLI" if args.profile else "from DEFAULT_PROFILE"

    if effective_profile:
        profile_manager = ProfileManager()
        profile = profile_manager.get_profile(effective_profile)

        if not profile:
            available_profiles = profile_manager.list_profiles()
            logger.error(
                f"Profile '{effective_profile}' not found. "
                f"Available profiles: {', '.join(available_profiles)}"
            )
            sys.exit(1)

        if not profile_manager.validate_profile(effective_profile):
            logger.error(f"Profile '{effective_profile}' is invalid")
            sys.exit(1)

        # Auto-set collection name from profile if not specified
        if not args.target:
            args.target = effective_profile
            logger.info(f"Auto-setting target collection from profile: {args.target}")

        logger.info(
            f"Using profile '{effective_profile}' ({profile_source}) for target collection '{args.target}'"
        )

    # Validate target is specified
    if not args.target:
        logger.error(
            "Target collection name is required. "
            "Use -t <collection_name>, -p <profile_name>, or set DEFAULT_PROFILE env var"
        )
        sys.exit(1)

    enricher = Enricher(limit=args.limit)
    enricher.run(target=args.target)
