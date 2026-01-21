from dotenv import load_dotenv
from pyf.aggregator.logger import logger

import os
import typesense


load_dotenv()

TYPESENSE_HOST = os.getenv('TYPESENSE_HOST')
TYPESENSE_PORT = os.getenv('TYPESENSE_PORT')
TYPESENSE_PROTOCOL = os.getenv('TYPESENSE_PROTOCOL')
TYPESENSE_API_KEY = os.getenv('TYPESENSE_API_KEY')
TYPESENSE_TIMEOUT = os.getenv('TYPESENSE_TIMEOUT')


class TypesenceConnection:

    def __init__(self):
        self.client = typesense.Client(
            {
                "nodes": [
                    {
                        "host": TYPESENSE_HOST,  # For Typesense Cloud use xxx.a1.typesense.net
                        "port": TYPESENSE_PORT,  # For Typesense Cloud use 443
                        "protocol": TYPESENSE_PROTOCOL,  # For Typesense Cloud use https
                    }
                ],
                "api_key": TYPESENSE_API_KEY,
                "connection_timeout_seconds": int(TYPESENSE_TIMEOUT) or 300,
            }
        )

    def collection_exists(self, name=None):
        try:
            self.client.collections[name].retrieve()
            return True
        except typesense.exceptions.ObjectNotFound:
            return False

    def get_search_only_apikeys(self):
        return self.client.keys.retrieve()

    def delete_apikey(self, key_id):
        return self.client.keys[key_id].delete()

    def get_aliases(self):
        return self.client.aliases.retrieve()

    def get_collections(self):
        return self.client.collections.retrieve()

    def get_collection_names(self):
        return [i.get('name') for i in self.client.collections.retrieve()]


class TypesensePackagesCollection:

    def create_collection(self, name=None):
        schema = {
            "name": name,
            "fields": [
                {"name": "identifier", "type": "string", "facet": True},
                {"name": "author", "type": "string"},
                {"name": "author_email", "type": "string"},
                {"name": "bugtrack_url", "type": "string"},
                {"name": "classifiers", "type": "string[]", "facet": True},
                {"name": "framework_versions", "type": "string[]", "facet": True},
                {"name": "python_versions", "type": "string[]", "facet": True},
                {"name": "description", "type": "string"},
                {"name": "description_content_type", "type": "string"},
                {
                    "name": "docs_url",
                    "type": "string",
                    "index": False,
                    "optional": True,
                },
                {
                    "name": "home_page",
                    "type": "string",
                    "index": False,
                    "optional": True,
                },
                {"name": "keywords", "type": "string"},
                {"name": "license", "type": "string"},
                {"name": "maintainer", "type": "string"},
                {"name": "maintainer_email", "type": "string"},
                {"name": "name", "type": "string", "facet": True},
                {
                    "name": "name_sortable",
                    "type": "string",
                    "sort": True,
                    "facet": True,
                },
                {
                    "name": "package_url",
                    "type": "string",
                    "index": False,
                    "optional": True,
                },
                {"name": "platform", "type": "string"},
                {
                    "name": "project_url",
                    "type": "string",
                    "index": False,
                    "optional": True,
                },
                {
                    "name": "project_urls",
                    "type": "auto",
                    "index": False,
                    "optional": True,
                },
                {"name": "release_url", "type": "string"},
                {"name": "requires_dist", "type": "string[]"},
                {"name": "summary", "type": "string"},
                {"name": "urls", "type": "auto", "index": False, "optional": True},
                {"name": "version", "type": "string"},
                {"name": "upload_timestamp", "type": "string", "sort": True, "optional": True},
                {"name": "version_bugfix", "type": "int32", "sort": True},
                {"name": "version_major", "type": "int32", "sort": True},
                {"name": "version_minor", "type": "int32", "sort": True},
                {"name": "version_postfix", "type": "string", "sort": True},
                {"name": "version_sortable", "type": "string", "sort": True, "facet": True},
                {"name": "version_raw", "type": "string", "sort": True, "facet": True},
                {"name": "yanked", "type": "bool"},
                {"name": "github_stars", "type": "auto", "facet": True},
                {"name": "github_watchers", "type": "auto", "facet": True},
                {"name": "github_updated", "type": "auto", "facet": True},
                {"name": "github_open_issues", "type": "auto", "facet": True},
                {"name": "download_last_day", "type": "auto", "facet": True},
                {"name": "download_last_week", "type": "auto", "facet": True},
                {"name": "download_last_month", "type": "auto", "facet": True},
                {"name": "download_total", "type": "auto", "facet": True},
                {"name": "download_updated", "type": "float", "sort": True, "optional": True},
                {
                    "name": "yanked_reason",
                    "type": "string",
                    "index": False,
                    "optional": True,
                },
            ],
            "token_separators": [".", "-", "_"],
            "default_sorting_field": "name_sortable",
        }
        self.client.collections.create(schema)

    def get_unique_package_names(self, collection_name):
        """Get all unique package names from a collection using grouped search."""
        unique_names = set()
        page = 1
        per_page = 250

        while True:
            result = self.client.collections[collection_name].documents.search({
                "q": "*",
                "query_by": "name",
                "include_fields": "name",
                "per_page": per_page,
                "page": page,
                "group_by": "name",
                "group_limit": 1,
            })

            for group in result.get("grouped_hits", []):
                for hit in group.get("hits", []):
                    name = hit.get("document", {}).get("name")
                    if name:
                        unique_names.add(name)

            if len(result.get("grouped_hits", [])) < per_page:
                break
            page += 1

        return unique_names

    def delete_package_by_name(self, collection_name, package_name):
        """Delete all versions of a package by name."""
        return self.client.collections[collection_name].documents.delete(
            {'filter_by': f'name:={package_name}'}
        )