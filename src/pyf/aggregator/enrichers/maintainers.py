"""
Maintainers enricher - Enrich package data with PyPI maintainer information.

This module fetches maintainer data from the pypi-data SQLite database
and enriches Typesense documents with maintainer usernames and avatar URLs.

The pypi-data database is downloaded from:
https://github.com/pypi-data/data/releases/latest/download/roles.db.zip

Avatar URLs are scraped from PyPI user profile pages.
"""

from argparse import ArgumentParser
from datetime import datetime
from dotenv import load_dotenv
from pyf.aggregator.db import TypesenceConnection, TypesensePackagesCollection
from pyf.aggregator.logger import logger
from pyf.aggregator.profiles import ProfileManager

import functools
import os
import re
import requests
import sqlite3
import sys
import tempfile
import time
import zipfile


load_dotenv()

DEFAULT_PROFILE = os.getenv("DEFAULT_PROFILE")

# Rate limiting configuration for PyPI profile scraping
PYPI_PROFILE_RATE_LIMIT_DELAY = float(os.getenv("PYPI_PROFILE_RATE_LIMIT_DELAY", 0.5))
PYPI_PROFILE_MAX_RETRIES = int(os.getenv("PYPI_PROFILE_MAX_RETRIES", 3))
PYPI_PROFILE_RETRY_BACKOFF = float(os.getenv("PYPI_PROFILE_RETRY_BACKOFF", 2.0))

# Cache configuration
PYPI_DATA_CACHE_DIR = os.getenv("PYPI_DATA_CACHE_DIR", tempfile.gettempdir())
PYPI_DATA_CACHE_TTL = int(os.getenv("PYPI_DATA_CACHE_TTL", 86400))  # 24 hours

# pypi-data download URL
PYPI_DATA_URL = "https://github.com/pypi-data/data/releases/latest/download/roles.db.zip"

# Avatar URL regex pattern (matches PyPI's camo proxy and gravatar URLs)
AVATAR_PATTERN = re.compile(
    r'<img[^>]+src=["\']([^"\']*(?:pypi-camo|gravatar)[^"\']*)["\']',
    re.IGNORECASE
)

parser = ArgumentParser(
    description="Enrich package data with maintainer information from pypi-data"
)
parser.add_argument("-t", "--target", nargs="?", type=str)
parser.add_argument(
    "-p", "--profile",
    help="Profile name for classifier filtering (overrides DEFAULT_PROFILE env var)",
    nargs="?",
    type=str
)
parser.add_argument(
    "-n", "--name",
    help="Single package name to enrich (enriches only this package)",
    type=str
)
parser.add_argument(
    "-v", "--verbose",
    help="Show detailed output",
    action="store_true"
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


class MaintainerEnricher(TypesenceConnection, TypesensePackagesCollection):
    """
    Enrich pyf data with maintainer information from pypi-data.
    """

    def __init__(self):
        super().__init__()
        self._last_request_time = 0
        self._avatar_cache = {}

    def run(self, target=None, package_name=None, verbose=False):
        """Run the maintainer enrichment process.

        Args:
            target: Target Typesense collection name
            package_name: Optional single package name to enrich
            verbose: Whether to output detailed information
        """
        # Download/get cached pypi-data database
        db_path = self._download_pypi_data()
        if not db_path:
            logger.error("Failed to download pypi-data database")
            return

        logger.info(f"Using pypi-data database: {db_path}")

        search_parameters = {
            "q": "*",
            "query_by": "name",
            "group_by": "name_sortable",
            "group_limit": 1,
            "per_page": 50,
        }
        if package_name:
            search_parameters["filter_by"] = f"name:={package_name}"
            logger.info(f"Filtering for single package: {package_name}")

        results = self.ts_search(target, search_parameters)

        per_page = results["request_params"]["per_page"]
        found = results["found"]

        if package_name and found == 0:
            logger.error(f"Package '{package_name}' not found in collection '{target}'")
            return

        logger.info(f"[{datetime.now()}][found {found}] Start enriching with maintainer data...")
        enrich_counter = 0
        page = 0

        for p in range(0, found, per_page):
            page += 1
            results = self.ts_search(target, search_parameters, page)
            for group in results["grouped_hits"]:
                for item in group["hits"]:
                    data = item["document"]
                    pkg_name = data.get("name")
                    if not pkg_name:
                        continue

                    if verbose:
                        print(f"\n{'='*60}")
                        print(f"=== Processing package: {pkg_name} ===")
                        print(f"{'='*60}")

                    # Get maintainers from pypi-data database
                    maintainers = self._get_maintainers_for_package(db_path, pkg_name)

                    if not maintainers:
                        if verbose:
                            print(f"No maintainers found for {pkg_name}")
                        continue

                    if verbose:
                        print(f"Found {len(maintainers)} maintainers: {[m['username'] for m in maintainers]}")

                    # Enrich with avatar URLs
                    for maintainer in maintainers:
                        avatar_url = self._scrape_avatar_url(maintainer["username"])
                        maintainer["avatar_url"] = avatar_url

                    if verbose:
                        print(f"Enriched maintainers with avatars:")
                        for m in maintainers:
                            print(f"  - {m['username']}: {m.get('avatar_url', 'None')}")

                    enrich_counter += 1
                    self.update_doc(target, data['id'], maintainers, page, enrich_counter)

        logger.info(f"[{datetime.now()}] done - enriched {enrich_counter} packages")

    def _validate_sqlite_db(self, db_path):
        """Validate that a file is a valid SQLite database with required schema.

        Args:
            db_path: Path to the database file

        Returns:
            True if valid SQLite database with 'roles' table, False otherwise
        """
        if not os.path.exists(db_path):
            return False
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='roles'"
            )
            result = cursor.fetchone()
            conn.close()
            return result is not None
        except sqlite3.DatabaseError:
            return False
        except Exception:
            return False

    def _download_pypi_data(self):
        """Download and cache the pypi-data SQLite database.

        Returns:
            Path to the database file, or None on error
        """
        cache_dir = PYPI_DATA_CACHE_DIR
        os.makedirs(cache_dir, exist_ok=True)
        db_path = os.path.join(cache_dir, "roles.db")

        # Check if cached database is fresh and valid
        if os.path.exists(db_path):
            age = time.time() - os.path.getmtime(db_path)
            if age < PYPI_DATA_CACHE_TTL:
                if self._validate_sqlite_db(db_path):
                    logger.debug(f"Using cached pypi-data database (age: {age:.0f}s)")
                    return db_path
                else:
                    logger.warning(
                        "Cached pypi-data database is corrupted or invalid, re-downloading"
                    )
                    try:
                        os.remove(db_path)
                    except OSError as e:
                        logger.error(f"Failed to remove corrupted cache file: {e}")

        # Download fresh database
        logger.info("Downloading pypi-data database...")
        zip_path = os.path.join(cache_dir, "roles.db.zip")

        try:
            response = requests.get(PYPI_DATA_URL, timeout=120, stream=True)
            if response.status_code != 200:
                logger.error(f"Failed to download pypi-data: HTTP {response.status_code}")
                return None

            # Save ZIP file
            with open(zip_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            # Extract database
            with zipfile.ZipFile(zip_path, 'r') as zf:
                # Find the database file in the archive
                db_names = [n for n in zf.namelist() if n.endswith('.db')]
                if not db_names:
                    logger.error("No .db file found in pypi-data archive")
                    return None

                # Extract the first .db file
                with zf.open(db_names[0]) as src:
                    with open(db_path, 'wb') as dst:
                        dst.write(src.read())

            # Clean up ZIP file
            os.remove(zip_path)

            logger.info(f"Downloaded and extracted pypi-data database to {db_path}")
            return db_path

        except Exception as e:
            logger.error(f"Error downloading pypi-data: {e}")
            return None

    def _get_maintainers_for_package(self, db_path, package_name):
        """Query maintainers for a package from the pypi-data database.

        Args:
            db_path: Path to the pypi-data SQLite database
            package_name: Name of the package

        Returns:
            List of dicts with username key
        """
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # Query roles table for this package
            cursor.execute(
                "SELECT DISTINCT user_name FROM roles WHERE package_name = ?",
                (package_name,)
            )

            maintainers = []
            for row in cursor.fetchall():
                maintainers.append({"username": row[0]})

            conn.close()
            return maintainers

        except Exception as e:
            logger.warning(f"Error querying maintainers for {package_name}: {e}")
            return []

    def _apply_rate_limit(self):
        """Apply rate limiting between PyPI profile requests."""
        current_time = time.time()
        time_since_last_request = current_time - self._last_request_time

        if time_since_last_request < PYPI_PROFILE_RATE_LIMIT_DELAY:
            sleep_time = PYPI_PROFILE_RATE_LIMIT_DELAY - time_since_last_request
            time.sleep(sleep_time)

        self._last_request_time = time.time()

    @memoize
    def _scrape_avatar_url(self, username):
        """Scrape avatar URL from PyPI user profile page.

        Args:
            username: PyPI username

        Returns:
            Avatar URL string or None if not found
        """
        url = f"https://pypi.org/user/{username}/"

        for attempt in range(PYPI_PROFILE_MAX_RETRIES):
            try:
                self._apply_rate_limit()

                response = requests.get(url, timeout=10)

                # Handle 404 - user not found
                if response.status_code == 404:
                    logger.debug(f"PyPI user {username} not found")
                    return None

                # Handle 429 - rate limiting
                if response.status_code == 429:
                    retry_after = response.headers.get('Retry-After')
                    if retry_after:
                        try:
                            wait_time = float(retry_after)
                        except ValueError:
                            wait_time = PYPI_PROFILE_RETRY_BACKOFF * (2 ** attempt)
                    else:
                        wait_time = PYPI_PROFILE_RETRY_BACKOFF * (2 ** attempt)

                    logger.warning(
                        f"Rate limited by PyPI for {username}. "
                        f"Waiting {wait_time}s before retry {attempt + 1}/{PYPI_PROFILE_MAX_RETRIES}"
                    )
                    time.sleep(wait_time)
                    continue

                # Handle other errors
                if response.status_code != 200:
                    logger.warning(f"Unexpected status {response.status_code} for {username}")
                    return None

                # Parse HTML for avatar URL
                html = response.text
                match = AVATAR_PATTERN.search(html)
                if match:
                    return match.group(1)

                return None

            except requests.exceptions.Timeout:
                logger.warning(
                    f"Timeout fetching profile for {username}. "
                    f"Retry {attempt + 1}/{PYPI_PROFILE_MAX_RETRIES}"
                )
                if attempt < PYPI_PROFILE_MAX_RETRIES - 1:
                    time.sleep(PYPI_PROFILE_RETRY_BACKOFF * (2 ** attempt))
                    continue
                return None

            except requests.exceptions.RequestException as e:
                logger.error(f"Error fetching profile for {username}: {e}")
                return None

        # All retries exhausted
        logger.error(f"Failed to fetch profile for {username} after {PYPI_PROFILE_MAX_RETRIES} retries")
        return None

    def update_doc(self, target, id, maintainers, page, enrich_counter):
        """Update a Typesense document with maintainer data.

        Args:
            target: Target collection name
            id: Document ID
            maintainers: List of maintainer dicts
            page: Current page number (for logging)
            enrich_counter: Current enrichment count (for logging)
        """
        document = {
            'maintainers': maintainers,
        }
        doc = self.client.collections[target].documents[id].update(document)
        logger.info(f"[{page}/{enrich_counter}] Updated document {id} with {len(maintainers)} maintainers")

    def ts_search(self, target, search_parameters, page=1):
        """Execute a Typesense search.

        Args:
            target: Target collection name
            search_parameters: Search parameters dict
            page: Page number

        Returns:
            Search results dict
        """
        search_parameters['page'] = page
        return self.client.collections[target].documents.search(search_parameters)


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

        logger.info(f"Using profile '{effective_profile}' ({profile_source}) for target collection '{args.target}'")

    # Validate target is specified
    if not args.target:
        logger.error(
            "Target collection name is required. "
            "Use -t <collection_name>, -p <profile_name>, or set DEFAULT_PROFILE env var"
        )
        sys.exit(1)

    enricher = MaintainerEnricher()
    enricher.run(target=args.target, package_name=args.name, verbose=args.verbose)


if __name__ == "__main__":
    main()
