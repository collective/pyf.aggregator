"""
Tests that keep the npm and PyPI data in a shared collection isolated.

Both registries live in one Typesense collection, distinguished by the
``registry`` field. Every maintenance job that deletes documents must scope
its deletes to its own registry, otherwise a PyPI refresh wipes the npm
packages (they 404 on PyPI) and the UI ends up showing PyPI packages only.
"""

import pytest
import responses

from unittest.mock import MagicMock, patch

from pyf.aggregator.db import TypesenceConnection, TypesensePackagesCollection


class Helper(TypesenceConnection, TypesensePackagesCollection):
    """Concrete class combining the connection and collection mixins."""


@pytest.fixture
def helper(mock_typesense):
    """Helper bound to the mocked Typesense client."""
    return Helper()


@pytest.fixture
def collection(mock_typesense):
    """The mocked collection object returned for every collection name."""
    return mock_typesense.collections.__getitem__.return_value


def search_calls(collection):
    """All search parameter dicts passed to the mocked collection."""
    return [call.args[0] for call in collection.documents.search.call_args_list]


def grouped(names):
    """Build a grouped search response for the given package names."""
    return {
        "found": len(names),
        "grouped_hits": [{"hits": [{"document": {"name": name}}]} for name in names],
    }


def hits(documents):
    """Build a flat search response for the given documents."""
    return {"found": len(documents), "hits": [{"document": d} for d in documents]}


# ============================================================================
# Filter escaping
# ============================================================================


class TestFilterValue:
    """Values interpolated into filter_by expressions must be quoted."""

    def test_scoped_npm_name_is_backtick_quoted(self):
        from pyf.aggregator.db import filter_value

        assert filter_value("@plone/volto") == "`@plone/volto`"

    def test_embedded_backticks_are_stripped(self):
        from pyf.aggregator.db import filter_value

        assert filter_value("we`ird") == "`weird`"


# ============================================================================
# Listing package names per registry
# ============================================================================


class TestGetUniquePackageNames:
    def test_registry_filter_is_sent_to_typesense(self, helper, collection):
        collection.documents.search.side_effect = [
            grouped(["@plone/volto"]),
            grouped([]),
        ]

        names = helper.get_unique_package_names("packages", registry="npm")

        assert names == {"@plone/volto"}
        assert search_calls(collection)[0]["filter_by"] == "registry:=`npm`"

    def test_without_registry_no_filter_is_sent(self, helper, collection):
        collection.documents.search.side_effect = [grouped(["plone.api"]), grouped([])]

        names = helper.get_unique_package_names("packages")

        assert names == {"plone.api"}
        assert "filter_by" not in search_calls(collection)[0]

    def test_exclude_registry_drops_npm_only_names(self, helper, collection):
        def fake_search(params):
            filter_by = params.get("filter_by", "")
            if params.get("group_by") and "registry" in filter_by:
                # npm names
                return grouped(["@plone/volto"]) if params["page"] == 1 else grouped([])
            if params.get("group_by"):
                # all names
                return (
                    grouped(["plone.api", "@plone/volto"])
                    if params["page"] == 1
                    else grouped([])
                )
            # per-name lookup for "@plone/volto": only npm documents exist
            return hits([{"id": "@plone--volto-18.0.0", "registry": "npm"}])

        collection.documents.search.side_effect = fake_search

        names = helper.get_unique_package_names("packages", exclude_registry="npm")

        assert names == {"plone.api"}

    def test_exclude_registry_keeps_names_present_in_both_registries(
        self, helper, collection
    ):
        def fake_search(params):
            filter_by = params.get("filter_by", "")
            if params.get("group_by") and "registry" in filter_by:
                return grouped(["volto-slate"]) if params["page"] == 1 else grouped([])
            if params.get("group_by"):
                return grouped(["volto-slate"]) if params["page"] == 1 else grouped([])
            return hits(
                [
                    {"id": "volto-slate-1.0.0", "registry": "npm"},
                    {"id": "volto-slate-2.0.0", "registry": "pypi"},
                ]
            )

        collection.documents.search.side_effect = fake_search

        names = helper.get_unique_package_names("packages", exclude_registry="npm")

        assert names == {"volto-slate"}


# ============================================================================
# Registry-scoped deletes
# ============================================================================


class TestDeletePackageByName:
    def test_registry_scoped_delete_filters_on_registry(self, helper, collection):
        helper.delete_package_by_name("packages", "@plone/volto", registry="npm")

        collection.documents.delete.assert_called_once_with(
            {"filter_by": "name:=`@plone/volto` && registry:=`npm`"}
        )

    def test_unscoped_delete_quotes_the_name(self, helper, collection):
        helper.delete_package_by_name("packages", "plone.api")

        collection.documents.delete.assert_called_once_with(
            {"filter_by": "name:=`plone.api`"}
        )

    def test_exclude_registry_never_deletes_by_name_filter(self, helper, collection):
        collection.documents.search.side_effect = [
            hits([{"id": "@plone--volto-18.0.0", "registry": "npm"}]),
            hits([]),
        ]

        helper.delete_package_by_name(
            "packages", "@plone/volto", exclude_registry="npm"
        )

        # No bulk delete may be issued - that would take the npm documents with it.
        collection.documents.delete.assert_not_called()
        collection.documents.__getitem__.assert_not_called()

    def test_exclude_registry_deletes_only_foreign_documents(self, helper, collection):
        collection.documents.search.side_effect = [
            hits(
                [
                    {"id": "volto-slate-1.0.0", "registry": "npm"},
                    {"id": "volto-slate-2.0.0", "registry": "pypi"},
                    {"id": "volto-slate-3.0.0"},  # legacy document without registry
                ]
            ),
            hits([]),
        ]

        helper.delete_package_by_name("packages", "volto-slate", exclude_registry="npm")

        deleted = [c.args[0] for c in collection.documents.__getitem__.call_args_list]
        assert deleted == ["volto-slate-2.0.0", "volto-slate-3.0.0"]
        collection.documents.delete.assert_not_called()


# ============================================================================
# PyPI refresh must not touch npm documents
# ============================================================================


class TestPypiRefreshLeavesNpmAlone:
    @responses.activate
    def test_npm_only_package_is_not_deleted(self, mock_typesense, collection):
        """A package that only exists on npm 404s on PyPI - it must survive."""
        from pyf.aggregator.main import run_refresh_mode

        responses.add(
            responses.GET,
            "https://pypi.org/pypi/@plone/volto/json",
            status=404,
        )

        def fake_search(params):
            filter_by = params.get("filter_by", "")
            if params.get("group_by") and "registry" in filter_by:
                return grouped(["@plone/volto"]) if params["page"] == 1 else grouped([])
            if params.get("group_by"):
                return grouped(["@plone/volto"]) if params["page"] == 1 else grouped([])
            return hits([{"id": "@plone--volto-18.0.0", "registry": "npm"}])

        collection.documents.search.side_effect = fake_search

        run_refresh_mode(
            {
                "target": "packages",
                "limit": 0,
                "filter_name": "",
                "filter_troove": ["Framework :: Plone"],
            }
        )

        collection.documents.delete.assert_not_called()


class TestNpmRefreshDeletesOnlyNpm:
    def test_unpublished_package_deletes_npm_documents_only(
        self, mock_typesense, collection
    ):
        """A package gone from npm must not take a PyPI namesake with it."""
        from pyf.aggregator import npm_main

        def fake_search(params):
            if params.get("group_by"):
                return grouped(["volto-slate"]) if params["page"] == 1 else grouped([])
            return hits([])

        collection.documents.search.side_effect = fake_search

        with patch.object(npm_main.NpmAggregator, "_get_npm_json", return_value=None):
            npm_main.run_npm_refresh_mode(
                {
                    "target": "packages",
                    "limit": 0,
                    "filter_name": "",
                    "filter_keywords": ["plone"],
                    "filter_scopes": ["@plone"],
                }
            )

        collection.documents.delete.assert_called_once_with(
            {"filter_by": "name:=`volto-slate` && registry:=`npm`"}
        )


class TestWeeklyRefreshTaskLeavesNpmAlone:
    def test_refresh_task_lists_only_non_npm_names(self):
        """The Celery weekly refresh must exclude npm-only packages."""
        from pyf.aggregator import queue

        with patch.object(queue, "PackageIndexer") as indexer_cls:
            indexer = indexer_cls.return_value
            indexer.get_unique_package_names.return_value = set()

            queue.refresh_all_indexed_packages("packages", "plone")

        indexer.get_unique_package_names.assert_called_once_with(
            "packages", exclude_registry="npm"
        )

    def test_refresh_task_deletes_without_npm_documents(self):
        from pyf.aggregator import queue

        with (
            patch.object(queue, "PackageIndexer") as indexer_cls,
            patch.object(queue, "Aggregator") as aggregator_cls,
        ):
            indexer = indexer_cls.return_value
            indexer.get_unique_package_names.return_value = {"gone.package"}
            aggregator_cls.return_value._get_pypi_json.return_value = None

            queue.refresh_all_indexed_packages("packages", "plone")

        indexer.delete_package_by_name.assert_called_once_with(
            "packages", "gone.package", exclude_registry="npm"
        )


# ============================================================================
# Every indexed document carries its registry
# ============================================================================


class TestRegistryFieldIsAlwaysSet:
    def test_queue_indexer_defaults_to_pypi(self):
        from pyf.aggregator.queue import PackageIndexer

        with patch("pyf.aggregator.db.typesense.Client", MagicMock()):
            data = PackageIndexer().clean_data({"name": "plone.api"})

        assert data["registry"] == "pypi"

    def test_queue_indexer_normalizes_keyword_strings(self):
        """PyPI serves keywords as a string; the schema declares string[]."""
        from pyf.aggregator.queue import PackageIndexer

        with patch("pyf.aggregator.db.typesense.Client", MagicMock()):
            data = PackageIndexer().clean_data(
                {"name": "plone.api", "keywords": "plone, api"}
            )

        assert data["keywords"] == ["plone", "api"]

    def test_queue_indexer_keeps_an_existing_registry(self):
        from pyf.aggregator.queue import PackageIndexer

        with patch("pyf.aggregator.db.typesense.Client", MagicMock()):
            data = PackageIndexer().clean_data(
                {"name": "@plone/volto", "registry": "npm"}
            )

        assert data["registry"] == "npm"


# ============================================================================
# npm document ids are built in exactly one place
# ============================================================================


class TestNpmIdentifier:
    def test_scoped_name_is_sanitized(self):
        from pyf.aggregator.npm_fetcher import npm_identifier

        assert npm_identifier("@plone/volto", "18.0.0") == "@plone--volto-18.0.0"

    def test_fetcher_uses_the_shared_identifier(self):
        from pyf.aggregator.npm_fetcher import NpmAggregator, npm_identifier

        agg = NpmAggregator(mode="first")
        package_json = {
            "versions": {"18.0.0": {"version": "18.0.0", "description": "Volto"}},
            "time": {"18.0.0": "2024-01-15T10:30:00.000Z"},
            "readme": "# Volto",
        }
        with patch.object(agg, "_get_npm_json", return_value=package_json):
            records = agg._build_version_records("@plone/volto", None)

        assert [r["identifier"] for r in records] == [
            npm_identifier("@plone/volto", "18.0.0")
        ]

    def test_refresh_builds_the_same_ids_as_a_full_fetch(self):
        """A refresh must update the documents a full fetch wrote, not add new ones."""
        from pyf.aggregator.npm_fetcher import NpmAggregator, npm_identifier
        from pyf.aggregator.npm_indexer import NpmIndexer
        from pyf.aggregator.npm_main import build_refresh_batch

        agg = NpmAggregator(mode="first")
        package_json = {
            "versions": {"18.0.0": {"version": "18.0.0", "description": "Volto"}},
            "time": {"18.0.0": "2024-01-15T10:30:00.000Z"},
            "readme": "# Volto",
        }

        with patch("pyf.aggregator.db.typesense.Client", MagicMock()):
            batch = build_refresh_batch(
                agg,
                NpmIndexer(),
                "@plone/volto",
                package_json,
                preserved_fields={"github_stars": 42},
                readmes={"18.0.0": "# Volto 18"},
            )

        assert [d["id"] for d in batch] == [npm_identifier("@plone/volto", "18.0.0")]
        assert batch[0]["identifier"] == npm_identifier("@plone/volto", "18.0.0")
        assert batch[0]["description"] == "# Volto 18"
        assert batch[0]["github_stars"] == 42
        assert batch[0]["registry"] == "npm"

    def test_refresh_preserves_enrichment_fields(self):
        """An upsert replaces the document - enrichment-only fields must survive."""
        from pyf.aggregator.npm_main import PRESERVED_FIELDS

        assert "github_stars" in PRESERVED_FIELDS
        assert "npm_final_score" in PRESERVED_FIELDS
        assert "npm_quality_score" in PRESERVED_FIELDS

    def test_refresh_carries_over_npm_scores(self, mock_typesense, collection):
        """The npm scores come from the search API, which a refresh does not call."""
        from pyf.aggregator.npm_main import collect_preserved_fields

        collection.documents.search.return_value = hits(
            [
                {
                    "id": "@plone--volto-18.0.0",
                    "registry": "npm",
                    "npm_final_score": 0.85,
                    "github_stars": 42,
                }
            ]
        )

        preserved = collect_preserved_fields(Helper(), "packages", "@plone/volto")

        assert preserved["npm_final_score"] == 0.85
        assert preserved["github_stars"] == 42


# ============================================================================
# Refreshed npm documents must satisfy the collection schema
# ============================================================================


def required_schema_fields():
    """Fields the collection schema demands in every document.

    ``auto`` fields are left out: they are filled in later by the enrichers.
    """
    client = MagicMock()
    with patch("pyf.aggregator.db.typesense.Client", return_value=client):
        Helper().create_collection(name="packages")
    schema = client.collections.create.call_args.args[0]
    return {
        field["name"]
        for field in schema["fields"]
        if not field.get("optional") and field["type"] != "auto"
    }


class TestRefreshedNpmDocumentsAreComplete:
    @pytest.fixture(autouse=True)
    def plugins(self):
        """Register the npm plugins the way a refresh run does."""
        from pyf.aggregator.npm_main import register_npm_plugins

        register_npm_plugins({})
        yield

    def test_refresh_document_has_every_required_field(self):
        """A document missing a required field is rejected by Typesense."""
        from pyf.aggregator.npm_fetcher import NpmAggregator
        from pyf.aggregator.npm_indexer import NpmIndexer
        from pyf.aggregator.npm_main import build_refresh_batch

        agg = NpmAggregator(mode="first")
        package_json = {
            "versions": {"18.0.0": {"version": "18.0.0", "description": "Volto"}},
            "time": {"18.0.0": "2024-01-15T10:30:00.000Z"},
            "readme": "## Volto\n\nThe frontend.",
        }

        with patch("pyf.aggregator.db.typesense.Client", MagicMock()):
            batch = build_refresh_batch(
                agg, NpmIndexer(), "@plone/volto", package_json, {}, {}
            )

        missing = required_schema_fields() - set(batch[0])
        assert not missing, f"refreshed document is missing {sorted(missing)}"

    def test_refresh_document_keeps_the_upload_timestamp(self):
        from pyf.aggregator.npm_fetcher import NpmAggregator
        from pyf.aggregator.npm_indexer import NpmIndexer
        from pyf.aggregator.npm_main import build_refresh_batch

        agg = NpmAggregator(mode="first")
        package_json = {
            "versions": {"18.0.0": {"version": "18.0.0"}},
            "time": {"18.0.0": "2024-01-15T10:30:00.000Z"},
        }

        with patch("pyf.aggregator.db.typesense.Client", MagicMock()):
            batch = build_refresh_batch(
                agg, NpmIndexer(), "@plone/volto", package_json, {}, {}
            )

        assert batch[0]["upload_timestamp"] == 1705314600

    def test_rejected_documents_are_reported_with_a_count(self, mock_typesense, caplog):
        """A silent batch failure is what let broken refreshes go unnoticed."""
        from pyf.aggregator.npm_indexer import NpmIndexer

        collection = mock_typesense.collections.__getitem__.return_value
        collection.documents.import_.return_value = [
            {"success": False, "error": "Field `version_sortable` not found"},
            {"success": True},
        ]

        with caplog.at_level("WARNING"):
            NpmIndexer().index_data([{"id": "a"}, {"id": "b"}], 2, "packages")

        assert "1/2 documents rejected" in caplog.text

    def test_refresh_mode_registers_the_plugins(self):
        """run_command must register plugins before entering refresh mode."""
        from pyf.aggregator import npm_main
        from pyf.aggregator.npm_fetcher import NPM_PLUGINS

        NPM_PLUGINS.clear()
        args = MagicMock(
            first=False,
            incremental=False,
            refresh_from_npm=True,
            limit=0,
            filter_name="",
            target="packages",
        )

        with (
            patch.object(npm_main, "run_npm_refresh_mode") as refresh,
            patch("pyf.aggregator.cli_utils.resolve_profile_and_target") as resolve,
        ):
            manager = MagicMock()
            manager.get_npm_config.return_value = {"keywords": ["plone"], "scopes": []}
            resolve.return_value = ("plone", {}, manager)
            npm_main.run_command(args)

        assert refresh.called
        assert NPM_PLUGINS, "no plugins registered for refresh mode"


# ============================================================================
# RSS-indexed PyPI documents must satisfy the collection schema too
# ============================================================================


class TestRssTasksProduceCompleteDocuments:
    """The RSS tasks write into the same collection as a full fetch."""

    def indexed_document(self, task, argument, package_json):
        from pyf.aggregator import queue

        with (
            patch("pyf.aggregator.db.typesense.Client", MagicMock()),
            patch.object(queue.PackageIndexer, "index_single") as index_single,
            patch.object(queue, "Aggregator") as aggregator_cls,
        ):
            aggregator = aggregator_cls.return_value
            aggregator._get_pypi_json.return_value = package_json
            aggregator.has_plone_classifier.return_value = True
            task(argument)

        return index_single.call_args.args[0]

    def test_registering_twice_does_not_stack_plugins(self):
        """Celery workers are long-lived - a task must not re-add the chain."""
        from pyf.aggregator.plugins import register_plugins

        plugins = []
        register_plugins(plugins, {})
        count = len(plugins)
        register_plugins(plugins, {})

        assert len(plugins) == count

    def test_inspect_project_document_is_complete(self, sample_pypi_json_plone):
        from pyf.aggregator.queue import inspect_project

        document = self.indexed_document(
            inspect_project,
            {"package_id": "plone.api", "release_id": "2.0.0"},
            sample_pypi_json_plone,
        )

        missing = required_schema_fields() - set(document)
        assert not missing, f"indexed document is missing {sorted(missing)}"

    def test_update_project_document_is_complete(self, sample_pypi_json_plone):
        from pyf.aggregator.queue import update_project

        document = self.indexed_document(
            update_project, "plone.api", sample_pypi_json_plone
        )

        missing = required_schema_fields() - set(document)
        assert not missing, f"indexed document is missing {sorted(missing)}"


# ============================================================================
# Download stats are a PyPI-only signal
# ============================================================================


class TestDownloadsEnricherSkipsNpm:
    def test_npm_documents_are_not_enriched_with_pypistats(
        self, mock_typesense, collection
    ):
        from pyf.aggregator.enrichers.downloads import Enricher

        collection.documents.search.return_value = {
            "found": 1,
            "request_params": {"per_page": 50},
            "grouped_hits": [
                {
                    "hits": [
                        {
                            "document": {
                                "id": "@plone--volto-18.0.0",
                                "name": "@plone/volto",
                                "registry": "npm",
                            }
                        }
                    ]
                }
            ],
        }

        enricher = Enricher()
        with patch.object(enricher, "_get_pypistats_data") as get_stats:
            enricher.run(target="packages")

        get_stats.assert_not_called()
