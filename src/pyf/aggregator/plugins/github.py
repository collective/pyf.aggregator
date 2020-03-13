from github import Github
from github import RateLimitExceededException
from pyf.aggregator.logger import logger

import datetime
import functools
import re
import time


PREFIX = "github_"
github_regex = re.compile(r"^(http[s]{0,1}:\/\/|www\.)github\.com/(.+/.+)")


def memoize(obj):
    cache = obj.cache = {}

    @functools.wraps(obj)
    def memoizer(*args, **kwargs):
        key = args[1].split("-")[0]
        if key not in cache:
            cache[key] = obj(*args, **kwargs)
        return cache[key]

    return memoizer


class load_github_stats:
    def __init__(self, settings):
        self.token = settings.get("github_token")
        self.github = Github(self.token or None)

    @memoize
    def __call__(self, identifier, data):
        urls = [data.get("home_page"), data.get("project_url")] + list((data.get("project_urls") or {}).values())

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

        keys_mapping = {
            "stars": "stargazers_count",
            "open_issues": "open_issues",
            "is_archived": "archived",
            "watchers": "watchers_count",
            "updated": "updated_at",
        }

        while True:
            try:
                repo = self.github.get_repo(repo_identifier)
                for key, key_github in keys_mapping.items():
                    data[PREFIX + key] = getattr(repo, key_github)
                break
            except RateLimitExceededException:
                reset_time = self.github.rate_limiting_resettime
                delta = reset_time - time.time()
                logger.info(
                    "Waiting until {0} (UTC) reset time to perform more Github requests.".format(
                        datetime.datetime.utcfromtimestamp(reset_time).strftime("%Y-%m-%d %H:%M:%S")
                    )
                )
                time.sleep(delta)
