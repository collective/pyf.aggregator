from argparse import ArgumentParser
from datetime import datetime
from pyf.aggregator.db import TypesenceConnection, TypesensePackagesCollection
from pyf.aggregator.logger import logger
import time

parser = ArgumentParser(
    description="Recalculates package health scores with GitHub activity data"
)
parser.add_argument("-t", "--target", nargs="?", type=str)


class HealthEnricher(TypesenceConnection, TypesensePackagesCollection):
    """
    Enrich health scores with GitHub activity data.

    Enhances the basic health score (calculated by the health_score plugin)
    with additional GitHub metrics:
    - GitHub activity (commit recency, stars)
    - Issue management (open issues ratio)
    """

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

                    # Recalculate health score with GitHub data
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
        }
        self.client.collections[target].documents[id].update(document)
        logger.info(
            f"[{page}/{enrich_counter}] Updated health score for document {id}: {data['health_score']}"
        )

    def ts_search(self, target, search_parameters, page=1):
        search_parameters["page"] = page
        return self.client.collections[target].documents.search(search_parameters)

    def _calculate_enhanced_health_score(self, data):
        """Calculate enhanced health score using GitHub data.

        The basic score (0-100) comes from:
        - Release recency (40 points)
        - Documentation (30 points)
        - Metadata quality (30 points)

        GitHub enhancement adds bonus points (up to +30):
        - GitHub stars bonus (up to +10)
        - GitHub activity bonus (up to +10)
        - Issue management bonus (up to +10)

        Final score is capped at 100.
        """
        # Start with existing basic score, or calculate from scratch if missing
        base_score = data.get("health_score", 0)
        breakdown = data.get("health_score_breakdown", {})

        # If there's no basic score, we can't enhance it meaningfully
        # (The plugin should have set this during indexing)
        if base_score == 0 and not breakdown:
            # Return None to skip this document
            return None

        # Calculate GitHub enhancement bonuses
        github_bonus = 0

        # Bonus 1: Stars (popularity indicator, up to +10 points)
        stars = data.get("github_stars", 0)
        if stars:
            stars_bonus = self._calculate_stars_bonus(stars)
            github_bonus += stars_bonus
            breakdown["github_stars_bonus"] = stars_bonus

        # Bonus 2: Recent activity (up to +10 points)
        github_updated = data.get("github_updated")
        if github_updated:
            activity_bonus = self._calculate_activity_bonus(github_updated)
            github_bonus += activity_bonus
            breakdown["github_activity_bonus"] = activity_bonus

        # Bonus 3: Issue management (up to +10 points)
        # Only calculate if we have both stars and open_issues data
        if "github_open_issues" in data and "github_stars" in data:
            open_issues = data.get("github_open_issues", 0)
            stars_for_ratio = data.get("github_stars", 0)
            if stars_for_ratio > 0:  # Only meaningful for projects with some stars
                issue_bonus = self._calculate_issue_management_bonus(
                    open_issues, stars_for_ratio
                )
                github_bonus += issue_bonus
                breakdown["github_issue_bonus"] = issue_bonus

        # Add GitHub bonus to breakdown
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
    enricher = HealthEnricher()
    enricher.run(target=args.target)
