from pyf.aggregator.logger import logger
import typesense


class TypesenceConnection:

    def __init__(self):
        self.client = typesense.Client(
            {
                "nodes": [
                    {
                        "host": "localhost",  # For Typesense Cloud use xxx.a1.typesense.net
                        "port": "8108",  # For Typesense Cloud use 443
                        "protocol": "http",  # For Typesense Cloud use https
                    }
                ],
                "api_key": "OGBPyJWlzA2dSdt9b8ZxAs8wFOVb0eNG7lSctnzbyBLc8SWR",
                "connection_timeout_seconds": 300,
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
                {"name": "id", "type": "string"},
                {"name": "author", "type": "string"},
                {"name": "author_email", "type": "string"},
                {"name": "bugtrack_url", "type": "string"},
                {"name": "classifiers", "type": "string[]", "facet": True},
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
                {"name": "version_bugfix", "type": "int32"},
                {"name": "version_major", "type": "int32"},
                {"name": "version_minor", "type": "int32"},
                {"name": "version_postfix", "type": "string"},
                {"name": "version_raw", "type": "string", "sort": True, "facet": True},
                {"name": "yanked", "type": "bool"},
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