from dotenv import load_dotenv
from argparse import ArgumentParser
from datetime import datetime
from pyf.aggregator.db import TypesenceConnection, TypesensePackagesCollection
from pyf.aggregator.logger import logger
from pprint import pprint
from github import Github
from github import RateLimitExceededException
from github import UnknownObjectException
from pyf.aggregator.logger import logger

import functools
import re
import time
import os

load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_COOLOFFTIME = os.getenv("GITHUB_COOLOFFTIME", 5)

parser = ArgumentParser(
    description="updates/migrates typesense collections and export/import documents"
)
parser.add_argument("-t", "--target", nargs="?", type=str)
# parser.add_argument("command", help="")

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


class Enricher(TypesenceConnection, TypesensePackagesCollection):
    """
    Enrich pyf data with data from Github
    """

    def run(self, target=None):
        search_parameters = {
            "q": "*",
            "query_by": "name",
            "group_by": "name_sortable",
            "group_limit": 1,
            "per_page": 250,
        }
        results = self.ts_search(target, search_parameters)

        per_page = results["request_params"]["per_page"]
        found = results["found"]
        logger.info(f"[{datetime.now()}][found] Start enriching data from github...")
        enrich_counter = 0
        page = 1
        for p in range(1, found, per_page):
            page +=1
            results = self.ts_search(target, search_parameters, page)
            for group in results["grouped_hits"]:
                for item in group["hits"]:
                    data = item["document"]
                    package_repo_identifier = self.get_package_repo_identifier(data)
                    if not package_repo_identifier:
                        continue
                    # print(package_repo_identifier)
                    gh_data = self._get_github_data(package_repo_identifier)
                    # pprint(gh_data)
                    if not gh_data:
                        continue
                    enrich_counter +=1
                    self.update_doc(target, data['id'], gh_data, page, enrich_counter)
        logger.info(f"[{datetime.now()}] done")

    # def update_collection_schema(self, fields):
    #     update_schema = {
    #         'fields': [
    #             {"name": "github_stars", "type": "int32", "sort": True, "facet": True},
    #             {"name": "github_watchers", "type": "int32", "sort": True, "facet": True},
    #         ]
    #     }
    #     self.client.collections['companies'].update(update_schema)

    def update_doc(self, target, id, data, page, enrich_counter):
        document = {
            'github_stars': data["github"]["stars"],
            'github_watchers': data["github"]["watchers"],
            'github_updated': data["github"]["updated"].timestamp(),
            'github_open_issues': data["github"]["open_issues"],
        }
        doc = self.client.collections[target].documents[id].update(document)
        logger.info(f"[{page}/{enrich_counter}] Updated document {id}")

    def ts_search(self, target, search_parameters, page=1):
        search_parameters['page'] = page
        return self.client.collections[target].documents.search(search_parameters)

    def get_package_repo_identifier(self, data):
        urls = [data.get("home_page"), data.get("project_url")] + list(
            (data.get("project_urls") or {}).values()
        )
        for url in urls:
            if not url:
                continue
            match = github_regex.match(url)
            if match:
                repo_identifier_parts = match.groups()[-1].split("/")
                repo_identifier = "/".join(repo_identifier_parts[0:2])
                return repo_identifier
        else:
            logger.info(f"no github url repository found for {data.get('name')}")
            return

    @memoize
    def _get_github_data(self, repo_identifier):
        """Return stats from a given Github repository (e.g. Owner/repo)."""
        github = Github(GITHUB_TOKEN or None)
        while True:
            try:
                repo = github.get_repo(repo_identifier)
            except UnknownObjectException:
                return {}
            except RateLimitExceededException:
                reset_time = self.github.rate_limiting_resettime
                delta = reset_time - time.time()
                logger.info(
                    "Waiting until {} (UTC) reset time to perform more Github requests.".format(
                        datetime.utcfromtimestamp(reset_time).strftime(
                            "%Y-%m-%d %H:%M:%S"
                        )
                    )
                )
                time.sleep(delta)
            else:
                data = {"github": {}}
                for key, key_github in GH_KEYS_MAP.items():
                    data["github"][key] = getattr(repo, key_github)
                return data


def main():
    args = parser.parse_args()
    enricher = Enricher()
    enricher.run(target=args.target)
