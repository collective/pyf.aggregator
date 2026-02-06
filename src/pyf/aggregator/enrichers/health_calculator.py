from argparse import ArgumentParser
from datetime import datetime
from dotenv import load_dotenv
import os
import sys
import time

import typesense.exceptions

from pyf.aggregator.db import TypesenceConnection, TypesensePackagesCollection
from pyf.aggregator.logger import logger
from pyf.aggregator.plugins.health_score import (
    calculate_recency_score_with_problems,
    calculate_docs_score_with_problems,
    calculate_metadata_score_with_problems,
)
from pyf.aggregator.profiles import ProfileManager

load_dotenv()

DEFAULT_PROFILE = os.getenv("DEFAULT_PROFILE")

parser = ArgumentParser(
    description="Calculates comprehensive health scores for packages (base + GitHub bonuses)"
)
parser.add_argument("-t", "--target", nargs="?", type=str)
parser.add_argument(
    "-p",
    "--profile",
    help="Profile name (overrides DEFAULT_PROFILE env var)",
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


class HealthEnricher(TypesenceConnection, TypesensePackagesCollection):
    """
    Calculate comprehensive health scores for packages.

    Calculates the complete health score from scratch:
    - Base score (100 points max): recency, documentation, metadata
    - GitHub bonuses (up to +30 points): stars, activity, issue management

    This is the standalone command for health score calculation,
    replacing the plugin-based approach to ensure GitHub data is available.
    """

    def __init__(self, limit=None):
        super().__init__()
        self.limit = limit

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
        logger.info(f"[{datetime.now()}][found] Start recalculating health scores...")
        enrich_counter = 0
        page = 0
        for p in range(0, found, per_page):
            page += 1
            results = self.ts_search(target, search_parameters, page)
            for group in results["grouped_hits"]:
                for item in group["hits"]:
                    data = item["document"]

                    # Check limit if set
                    if self.limit and enrich_counter >= self.limit:
                        logger.info(f"Reached limit of {self.limit} packages")
                        return

                    # Calculate complete health score (base + GitHub bonuses)
                    health_data = self._calculate_enhanced_health_score(data)

                    if health_data:
                        enrich_counter += 1
                        self.update_doc(
                            target, data["id"], health_data, page, enrich_counter
                        )
        logger.info(f"[{datetime.now()}] done - updated {enrich_counter} documents")

    def update_doc(self, target, id, data, page, enrich_counter):
        document = {
            "health_score": data["health_score"],
            "health_score_breakdown": data["health_score_breakdown"],
            "health_score_last_calculated": data["health_score_last_calculated"],
            # Clear old redundant fields (now stored in health_score_breakdown)
            "health_problems_documentation": [],
            "health_problems_metadata": [],
            "health_problems_recency": [],
        }
        try:
            self.client.collections[target].documents[id].update(document)
            logger.info(
                f"[{page}/{enrich_counter}] Updated health score for document {id}: {data['health_score']}"
            )
        except typesense.exceptions.ObjectNotFound:
            logger.warning(
                f"[{page}/{enrich_counter}] Document {id} not found, skipping health score update"
            )

    def ts_search(self, target, search_parameters, page=1):
        search_parameters["page"] = page
        return self.client.collections[target].documents.search(search_parameters)

    def _calculate_enhanced_health_score(self, data):
        """Calculate complete health score from scratch including GitHub bonuses.

        The basic score (0-100) comes from:
        - Release recency (40 points)
        - Documentation (30 points)
        - Metadata quality (30 points)

        GitHub enhancement adds bonus points (up to +30):
        - GitHub stars bonus (up to +10)
        - GitHub activity bonus (up to +10)
        - Issue management bonus (up to +10)

        Final score is capped at 100.

        Also tracks problems and bonuses for each category.
        """
        # Always calculate base score from scratch to ensure consistency
        base_score = 0

        # Factor 1: Release recency (40 points max)
        recency_score, problems_recency, bonuses_recency, max_recency = (
            calculate_recency_score_with_problems(data.get("upload_timestamp"))
        )
        base_score += recency_score

        # Factor 2: Documentation presence (30 points max)
        docs_score, problems_documentation, bonuses_documentation, max_docs = (
            calculate_docs_score_with_problems(data)
        )
        base_score += docs_score

        # Factor 3: Metadata quality (30 points max)
        metadata_score, problems_metadata, bonuses_metadata, max_metadata = (
            calculate_metadata_score_with_problems(data)
        )
        base_score += metadata_score

        # Calculate GitHub enhancement bonuses
        github_bonus = 0

        # Bonus 1: Stars (popularity indicator, up to +10 points)
        stars = data.get("github_stars", 0)
        stars_bonus = 0
        if stars:
            stars_bonus = self._calculate_stars_bonus(stars)
            github_bonus += stars_bonus

        # Bonus 2: Recent activity (up to +10 points)
        github_updated = data.get("github_updated")
        activity_bonus = 0
        if github_updated:
            activity_bonus = self._calculate_activity_bonus(github_updated)
            github_bonus += activity_bonus

            # Add GitHub activity problems
            if activity_bonus == 0:
                if "no GitHub activity in 1+ year" not in problems_recency:
                    problems_recency.append("no GitHub activity in 1+ year")
            elif activity_bonus <= 3:
                if "limited GitHub activity (6+ months)" not in problems_recency:
                    problems_recency.append("limited GitHub activity (6+ months)")

        # Bonus 3: Issue management (up to +10 points)
        # Only calculate if we have both stars and open_issues data
        issue_bonus = 0
        if "github_open_issues" in data and "github_stars" in data:
            open_issues = data.get("github_open_issues", 0)
            stars_for_ratio = data.get("github_stars", 0)
            if stars_for_ratio > 0:  # Only meaningful for projects with some stars
                issue_bonus = self._calculate_issue_management_bonus(
                    open_issues, stars_for_ratio
                )
                github_bonus += issue_bonus

                # Add issue ratio bonus (only when bonus applies)
                if issue_bonus >= 5:
                    if "good issue management" not in bonuses_metadata:
                        bonuses_metadata.append("good issue management")

        # Build new breakdown structure with points, max_points, problems, and bonuses
        breakdown = {
            "recency": {
                "points": recency_score,
                "max_points": max_recency,
                "problems": problems_recency,
                "bonuses": bonuses_recency,
            },
            "documentation": {
                "points": docs_score,
                "max_points": max_docs,
                "problems": problems_documentation,
                "bonuses": bonuses_documentation,
            },
            "metadata": {
                "points": metadata_score,
                "max_points": max_metadata,
                "problems": problems_metadata,
                "bonuses": bonuses_metadata,
            },
        }

        # Add GitHub bonuses to breakdown at top level
        if stars_bonus > 0:
            breakdown["github_stars_bonus"] = stars_bonus
        if activity_bonus > 0:
            breakdown["github_activity_bonus"] = activity_bonus
        if issue_bonus > 0:
            breakdown["github_issue_bonus"] = issue_bonus
        if github_bonus > 0:
            breakdown["github_bonus_total"] = github_bonus

        # Calculate final score (capped at 100)
        final_score = min(100, base_score + github_bonus)

        return {
            "health_score": int(final_score),
            "health_score_breakdown": breakdown,
            "health_score_last_calculated": int(time.time()),
        }

    def _calculate_stars_bonus(self, stars):
        """Calculate bonus points based on GitHub stars.

        Returns:
            0-10 points:
            - 10 points: 1000+ stars
            - 7 points: 500-999 stars
            - 5 points: 100-499 stars
            - 3 points: 50-99 stars
            - 1 point: 10-49 stars
            - 0 points: < 10 stars
        """
        if stars >= 1000:
            return 10
        elif stars >= 500:
            return 7
        elif stars >= 100:
            return 5
        elif stars >= 50:
            return 3
        elif stars >= 10:
            return 1
        else:
            return 0

    def _calculate_activity_bonus(self, github_updated_timestamp):
        """Calculate bonus based on recent GitHub activity.

        Args:
            github_updated_timestamp: Unix timestamp of last GitHub update

        Returns:
            0-10 points:
            - 10 points: Updated within 30 days
            - 7 points: Updated within 90 days
            - 5 points: Updated within 180 days
            - 3 points: Updated within 365 days
            - 0 points: > 1 year since update
        """
        if not github_updated_timestamp:
            return 0

        try:
            now = time.time()
            age_days = (
                now - github_updated_timestamp
            ) / 86400  # Convert seconds to days

            if age_days < 30:
                return 10
            elif age_days < 90:
                return 7
            elif age_days < 180:
                return 5
            elif age_days < 365:
                return 3
            else:
                return 0
        except (ValueError, TypeError):
            return 0

    def _calculate_issue_management_bonus(self, open_issues, stars):
        """Calculate bonus based on issue management quality.

        Good issue management = low ratio of open issues to stars.
        This indicates the maintainer is responsive and keeps issues under control.

        Args:
            open_issues: Number of open issues
            stars: Number of GitHub stars (for normalization)

        Returns:
            0-10 points based on issues-to-stars ratio:
            - 10 points: Excellent (ratio < 0.1)
            - 7 points: Good (ratio 0.1-0.3)
            - 5 points: Fair (ratio 0.3-0.5)
            - 3 points: Poor (ratio 0.5-1.0)
            - 0 points: Very poor (ratio > 1.0)
        """
        if stars == 0:
            return 0

        try:
            ratio = open_issues / stars

            if ratio < 0.1:
                return 10
            elif ratio < 0.3:
                return 7
            elif ratio < 0.5:
                return 5
            elif ratio < 1.0:
                return 3
            else:
                return 0
        except (ValueError, TypeError, ZeroDivisionError):
            return 0


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

    enricher = HealthEnricher(limit=args.limit)
    enricher.run(target=args.target)
