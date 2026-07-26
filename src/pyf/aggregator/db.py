from dotenv import load_dotenv

import os
import typesense


load_dotenv()

TYPESENSE_HOST = os.getenv("TYPESENSE_HOST")
TYPESENSE_PORT = os.getenv("TYPESENSE_PORT")
TYPESENSE_PROTOCOL = os.getenv("TYPESENSE_PROTOCOL")
TYPESENSE_API_KEY = os.getenv("TYPESENSE_API_KEY")
TYPESENSE_TIMEOUT = os.getenv("TYPESENSE_TIMEOUT")


def filter_value(value):
    """Quote a value for use in a Typesense ``filter_by`` expression.

    npm package names carry characters that are meaningful to the filter
    parser (``@plone/volto``), so values are always backtick-quoted.
    """
    return "`{}`".format(str(value).replace("`", ""))


def parse_versioned_name(collection_name):
    """Parse 'name-N' into ('name', N). Returns (name, None) if no version suffix."""
    if "-" in collection_name:
        base, suffix = collection_name.rsplit("-", 1)
        if suffix.isdigit():
            return base, int(suffix)
    return collection_name, None


def get_next_version(base_name, current_version):
    """Get next versioned collection name."""
    next_version = (current_version or 0) + 1
    return f"{base_name}-{next_version}", next_version


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

    def get_alias(self, alias_name):
        """Get the collection name an alias points to, or None if alias doesn't exist."""
        try:
            alias = self.client.aliases[alias_name].retrieve()
            return alias.get("collection_name")
        except typesense.exceptions.ObjectNotFound:
            return None

    def delete_alias(self, alias_name):
        """Delete an alias."""
        return self.client.aliases[alias_name].delete()

    def get_collections(self):
        return self.client.collections.retrieve()

    def get_collection_names(self):
        return [i.get("name") for i in self.client.collections.retrieve()]


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
                {"name": "title", "type": "string", "optional": True},
                {"name": "first_chapter", "type": "string", "optional": True},
                {"name": "main_content", "type": "string", "optional": True},
                {"name": "changelog", "type": "string", "optional": True},
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
                {"name": "keywords", "type": "string[]", "facet": True},
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
                {
                    "name": "upload_timestamp",
                    "type": "int64",
                    "sort": True,
                    "optional": True,
                },
                {"name": "version_bugfix", "type": "int32", "sort": True},
                {"name": "version_major", "type": "int32", "sort": True},
                {"name": "version_minor", "type": "int32", "sort": True},
                {"name": "version_postfix", "type": "string", "sort": True},
                {
                    "name": "version_sortable",
                    "type": "string",
                    "sort": True,
                    "facet": True,
                },
                {"name": "version_raw", "type": "string", "sort": True, "facet": True},
                {"name": "yanked", "type": "bool"},
                # Registry identification (pypi or npm)
                {"name": "registry", "type": "string", "facet": True, "optional": True},
                # npm-specific fields
                {
                    "name": "npm_scope",
                    "type": "string",
                    "facet": True,
                    "optional": True,
                },
                {
                    "name": "npm_quality_score",
                    "type": "float",
                    "sort": True,
                    "optional": True,
                },
                {
                    "name": "npm_popularity_score",
                    "type": "float",
                    "sort": True,
                    "optional": True,
                },
                {
                    "name": "npm_maintenance_score",
                    "type": "float",
                    "sort": True,
                    "optional": True,
                },
                {
                    "name": "npm_final_score",
                    "type": "float",
                    "sort": True,
                    "optional": True,
                },
                {
                    "name": "repository_url",
                    "type": "string",
                    "index": False,
                    "optional": True,
                },
                {"name": "github_stars", "type": "auto", "facet": True},
                {"name": "github_watchers", "type": "auto", "facet": True},
                {"name": "github_updated", "type": "auto", "facet": True},
                {"name": "github_open_issues", "type": "auto", "facet": True},
                {"name": "download_last_day", "type": "auto", "facet": True},
                {"name": "download_last_week", "type": "auto", "facet": True},
                {"name": "download_last_month", "type": "auto", "facet": True},
                {"name": "download_total", "type": "auto", "facet": True},
                {
                    "name": "download_updated",
                    "type": "float",
                    "sort": True,
                    "optional": True,
                },
                {
                    "name": "yanked_reason",
                    "type": "string",
                    "index": False,
                    "optional": True,
                },
                {
                    "name": "contributors",
                    "type": "object[]",
                    "optional": True,
                    "index": False,
                },
            ],
            "enable_nested_fields": True,
            "token_separators": [".", "-", "_", "@", "/"],
            "default_sorting_field": "name_sortable",
        }
        self.client.collections.create(schema)

    def delete_collection(self, name):
        """Delete a collection by name."""
        return self.client.collections[name].delete()

    def get_unique_package_names(
        self, collection_name, registry=None, exclude_registry=None
    ):
        """Get all unique package names from a collection using grouped search.

        Args:
            collection_name: Collection to list.
            registry: Only names that have documents in this registry.
            exclude_registry: Drop names whose documents *all* belong to this
                registry. A name indexed from both registries is kept, because
                its documents from the other registry still need maintenance.
        """
        unique_names = set()
        page = 1
        per_page = 250

        while True:
            search_parameters = {
                "q": "*",
                "query_by": "name",
                "include_fields": "name",
                "per_page": per_page,
                "page": page,
                "group_by": "name",
                "group_limit": 1,
            }
            if registry:
                search_parameters["filter_by"] = f"registry:={filter_value(registry)}"
            result = self.client.collections[collection_name].documents.search(
                search_parameters
            )

            for group in result.get("grouped_hits", []):
                for hit in group.get("hits", []):
                    name = hit.get("document", {}).get("name")
                    if name:
                        unique_names.add(name)

            if len(result.get("grouped_hits", [])) < per_page:
                break
            page += 1

        if exclude_registry:
            excluded = self.get_unique_package_names(
                collection_name, registry=exclude_registry
            )
            unique_names = {
                name
                for name in unique_names
                if name not in excluded
                or self.get_package_document_ids(
                    collection_name, name, exclude_registry=exclude_registry
                )
            }

        return unique_names

    def get_package_document_ids(
        self, collection_name, package_name, registry=None, exclude_registry=None
    ):
        """Get the document ids of a package, optionally restricted by registry.

        ``exclude_registry`` is applied on the documents themselves rather than
        as a ``!=`` filter, so legacy documents without a ``registry`` field are
        treated as belonging to every other registry instead of being skipped.
        """
        filter_by = f"name:={filter_value(package_name)}"
        if registry:
            filter_by += f" && registry:={filter_value(registry)}"

        ids = []
        page = 1
        per_page = 250
        while True:
            result = self.client.collections[collection_name].documents.search(
                {
                    "q": "*",
                    "query_by": "name",
                    "filter_by": filter_by,
                    "include_fields": "id,registry",
                    "per_page": per_page,
                    "page": page,
                }
            )
            hits = result.get("hits", [])
            if not hits:
                break
            for hit in hits:
                document = hit.get("document", {})
                if exclude_registry and document.get("registry") == exclude_registry:
                    continue
                if document.get("id"):
                    ids.append(document["id"])
            if len(hits) < per_page:
                break
            page += 1

        return ids

    def delete_package_by_name(
        self, collection_name, package_name, registry=None, exclude_registry=None
    ):
        """Delete versions of a package by name.

        Args:
            collection_name: Collection to delete from.
            package_name: Package to delete.
            registry: Only delete documents of this registry.
            exclude_registry: Keep this registry's documents and delete the
                rest. npm and PyPI share one collection, so a maintenance job
                for one registry must never delete the other one's documents.
        """
        collection = self.client.collections[collection_name]

        if exclude_registry:
            ids = self.get_package_document_ids(
                collection_name, package_name, exclude_registry=exclude_registry
            )
            for document_id in ids:
                collection.documents[document_id].delete()
            return {"num_deleted": len(ids)}

        filter_by = f"name:={filter_value(package_name)}"
        if registry:
            filter_by += f" && registry:={filter_value(registry)}"
        return collection.documents.delete({"filter_by": filter_by})

    def get_all_document_ids(self, collection_name):
        """Get all document IDs from a collection."""
        ids = []
        page = 1
        per_page = 250

        while True:
            result = self.client.collections[collection_name].documents.search(
                {
                    "q": "*",
                    "query_by": "name",
                    "per_page": per_page,
                    "page": page,
                    "include_fields": "id",
                }
            )

            hits = result.get("hits", [])
            if not hits:
                break

            ids.extend([h["document"]["id"] for h in hits])
            page += 1

        return ids

    def get_documents_by_name(
        self, collection_name, package_name, registry=None, exclude_registry=None
    ):
        """Get all documents for a package by name, sorted by upload_timestamp desc.

        ``registry``/``exclude_registry`` narrow the result to one registry, so
        callers do not read npm values off a PyPI package of the same name.
        """
        filter_by = f"name:={filter_value(package_name)}"
        if registry:
            filter_by += f" && registry:={filter_value(registry)}"
        result = self.client.collections[collection_name].documents.search(
            {
                "q": package_name,
                "query_by": "name",
                "filter_by": filter_by,
                "sort_by": "upload_timestamp:desc",
                "per_page": 100,
            }
        )
        documents = [hit["document"] for hit in result.get("hits", [])]
        if exclude_registry:
            documents = [d for d in documents if d.get("registry") != exclude_registry]
        return documents
