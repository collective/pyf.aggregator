from github import Github
from github import RateLimitExceededException
from github import UnknownObjectException
from pyf.aggregator.logger import logger

import datetime
import functools
import re
import time


github_regex = re.compile(r"^(http[s]{0,1}:\/\/|www\.)github\.com/(.+/.+)")

GH_KEYS_MAP = {
    "stars": "stargazers_count",
    "open_issues": "open_issues",
    "is_archived": "archived",
    "watchers": "subscribers_count",
    "updated": "updated_at",
}


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


class GithubStats:
    """Helper to retrieve Github data."""

    def __init__(self, settings):
        self.token = settings.get("github_token")
        self.github = Github(self.token or None)

    @memoize
    def _get_github_data(self, repo_identifier):
        """Return stats from a given Github repository (e.g. Owner/repo)."""
        while True:
            try:
                repo = self.github.get_repo(repo_identifier)
            except UnknownObjectException:
                return data
            except RateLimitExceededException:
                reset_time = self.github.rate_limiting_resettime
                delta = reset_time - time.time()
                logger.info(
                    "Waiting until {0} (UTC) reset time to perform more Github requests.".format(
                        datetime.datetime.utcfromtimestamp(reset_time).strftime(
                            "%Y-%m-%d %H:%M:%S"
                        )
                    )
                )
                time.sleep(delta)
        data = {"github": {}}
        for key, key_github in GH_KEYS_MAP.items():
            data["github"][key] = getattr(repo, key_github)
        return data

    def __call__(self, identifier, data):
        """Search for a referenced Github repository from pypi package information and if present, add those relevant
        Github stats.
        """
        urls = [data.get("home_page"), data.get("project_url")] + list(
            (data.get("project_urls") or {}).values()
        )
        for url in urls:
            if not url:
                continue
            match = github_regex.match(url)
            if match:
                repo_identifier = match.groups()[-1]
                break
        else:
            logger.debug("no github url repository found for {0}".format(identifier))
            return
        data.update(self._get_github_data(repo_identifier))


def load_github_stats(settings):
    """Return a callable to add Github stats."""
    return GithubStats(settings)
