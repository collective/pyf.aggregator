"""
Tests for pyf.aggregator.typesense_util module.

Tests migration functionality including export, import, and collection recreation.
"""

import json
import pytest
from unittest.mock import MagicMock, patch, call


class TestTypesenceUtilExport:
    """Tests for export_data method."""

    def test_export_data_returns_jsonl(self, mock_typesense):
        """Verify export_data returns JSONL format from Typesense."""
        from pyf.aggregator.typesense_util import TypesenceUtil

        # Setup mock to return JSONL data (newline-delimited JSON)
        sample_jsonl = '{"id":"pkg1","name":"plone.api"}\n{"id":"pkg2","name":"plone.restapi"}'
        mock_typesense.collections.__getitem__.return_value.documents.export.return_value = sample_jsonl

        ts_util = TypesenceUtil()
        result = ts_util.export_data(collection_name="test-collection")

        assert result == sample_jsonl
        mock_typesense.collections.__getitem__.return_value.documents.export.assert_called_once()


class TestTypesenceUtilImport:
    """Tests for import_data method."""

    def test_import_data_with_jsonl(self, mock_typesense):
        """Verify import_data works with JSONL string (no encoding)."""
        from pyf.aggregator.typesense_util import TypesenceUtil

        sample_jsonl = '{"id":"pkg1","name":"plone.api"}\n{"id":"pkg2","name":"plone.restapi"}'
        mock_typesense.collections.__getitem__.return_value.documents.import_.return_value = [
            {"success": True},
            {"success": True},
        ]

        ts_util = TypesenceUtil()
        ts_util.import_data(collection_name="test-collection", data=sample_jsonl)

        # Verify import was called with raw string (not encoded bytes)
        mock_typesense.collections.__getitem__.return_value.documents.import_.assert_called_once_with(
            sample_jsonl, {"action": "upsert"}
        )

    def test_import_data_uses_upsert_action(self, mock_typesense):
        """Verify import_data uses 'upsert' action for robustness."""
        from pyf.aggregator.typesense_util import TypesenceUtil

        sample_jsonl = '{"id":"pkg1","name":"plone.api"}'
        mock_typesense.collections.__getitem__.return_value.documents.import_.return_value = [
            {"success": True}
        ]

        ts_util = TypesenceUtil()
        ts_util.import_data(collection_name="test-collection", data=sample_jsonl)

        call_args = mock_typesense.collections.__getitem__.return_value.documents.import_.call_args
        assert call_args[0][1] == {"action": "upsert"}

    def test_import_data_logs_errors(self, mock_typesense, caplog):
        """Verify import_data logs warnings for failed documents."""
        from pyf.aggregator.typesense_util import TypesenceUtil
        import logging

        sample_jsonl = '{"id":"pkg1","name":"plone.api"}\n{"id":"pkg2","name":"invalid"}'
        mock_typesense.collections.__getitem__.return_value.documents.import_.return_value = [
            {"success": True},
            {"success": False, "error": "Schema validation failed"},
        ]

        ts_util = TypesenceUtil()
        with caplog.at_level(logging.WARNING):
            ts_util.import_data(collection_name="test-collection", data=sample_jsonl)

        assert "Import had 1 failed documents" in caplog.text

    def test_import_data_logs_first_five_errors(self, mock_typesense, caplog):
        """Verify import_data only logs the first 5 errors."""
        from pyf.aggregator.typesense_util import TypesenceUtil
        import logging

        sample_jsonl = "\n".join([f'{{"id":"pkg{i}","name":"invalid{i}"}}' for i in range(10)])
        mock_typesense.collections.__getitem__.return_value.documents.import_.return_value = [
            {"success": False, "error": f"Error {i}"} for i in range(10)
        ]

        ts_util = TypesenceUtil()
        with caplog.at_level(logging.WARNING):
            ts_util.import_data(collection_name="test-collection", data=sample_jsonl)

        assert "Import had 10 failed documents" in caplog.text
        # Count error detail lines (should be 5)
        error_detail_count = caplog.text.count("  - {")
        assert error_detail_count == 5


class TestTypesenceUtilMigrate:
    """Tests for migrate method."""

    def test_migrate_preserves_documents(self, mock_typesense):
        """Verify migrate exports from source and imports to target."""
        from pyf.aggregator.typesense_util import TypesenceUtil

        sample_jsonl = '{"id":"pkg1","name":"plone.api"}\n{"id":"pkg2","name":"plone.restapi"}'
        mock_typesense.collections.__getitem__.return_value.documents.export.return_value = sample_jsonl
        mock_typesense.collections.__getitem__.return_value.documents.import_.return_value = [
            {"success": True},
            {"success": True},
        ]
        # Mock collection_exists to return True
        mock_typesense.collections.__getitem__.return_value.retrieve.return_value = {"name": "target-collection"}

        ts_util = TypesenceUtil()

        # Patch collection_exists to return True
        with patch.object(ts_util, "collection_exists", return_value=True):
            ts_util.migrate(source="source-collection", target="target-collection")

        # Verify export was called on source
        mock_typesense.collections.__getitem__.assert_any_call("source-collection")
        # Verify import was called with the exported data
        mock_typesense.collections.__getitem__.return_value.documents.import_.assert_called_once_with(
            sample_jsonl, {"action": "upsert"}
        )

    def test_migrate_creates_target_if_not_exists(self, mock_typesense):
        """Verify migrate creates target collection if it doesn't exist."""
        from pyf.aggregator.typesense_util import TypesenceUtil

        sample_jsonl = '{"id":"pkg1","name":"plone.api"}'
        mock_typesense.collections.__getitem__.return_value.documents.export.return_value = sample_jsonl
        mock_typesense.collections.__getitem__.return_value.documents.import_.return_value = [{"success": True}]

        ts_util = TypesenceUtil()

        with patch.object(ts_util, "collection_exists", return_value=False), \
             patch.object(ts_util, "create_collection") as mock_create:
            ts_util.migrate(source="source-collection", target="new-target")

        mock_create.assert_called_once_with(name="new-target")


class TestTypesenceUtilRecreateCollection:
    """Tests for recreate_collection method."""

    def test_recreate_collection_with_alias(self, mock_typesense):
        """Verify recreate_collection performs zero-downtime migration with alias."""
        from pyf.aggregator.typesense_util import TypesenceUtil

        sample_jsonl = '{"id":"pkg1","name":"plone.api"}'
        mock_typesense.collections.__getitem__.return_value.documents.export.return_value = sample_jsonl
        mock_typesense.collections.__getitem__.return_value.documents.import_.return_value = [{"success": True}]

        ts_util = TypesenceUtil()

        with patch.object(ts_util, "get_alias", return_value="packages-1"), \
             patch.object(ts_util, "create_collection") as mock_create, \
             patch.object(ts_util, "migrate") as mock_migrate, \
             patch.object(ts_util, "add_alias") as mock_alias, \
             patch.object(ts_util, "delete_collection") as mock_delete:

            ts_util.recreate_collection(name="packages")

        # Verify new collection created with incremented version
        mock_create.assert_called_once_with(name="packages-2")
        # Verify migration from old to new
        mock_migrate.assert_called_once_with(source="packages-1", target="packages-2")
        # Verify alias switched
        mock_alias.assert_called_once_with(source="packages", target="packages-2")
        # Verify old collection deleted
        mock_delete.assert_called_once_with(name="packages-1")

    def test_recreate_collection_without_alias(self, mock_typesense):
        """Verify recreate_collection converts non-aliased collection to versioned scheme."""
        from pyf.aggregator.typesense_util import TypesenceUtil

        sample_jsonl = '{"id":"pkg1","name":"plone.api"}'
        mock_typesense.collections.__getitem__.return_value.documents.export.return_value = sample_jsonl
        mock_typesense.collections.__getitem__.return_value.documents.import_.return_value = [{"success": True}]

        ts_util = TypesenceUtil()

        with patch.object(ts_util, "get_alias", return_value=None), \
             patch.object(ts_util, "collection_exists", return_value=True), \
             patch.object(ts_util, "create_collection") as mock_create, \
             patch.object(ts_util, "migrate") as mock_migrate, \
             patch.object(ts_util, "add_alias") as mock_alias, \
             patch.object(ts_util, "delete_collection") as mock_delete:

            ts_util.recreate_collection(name="packages")

        # Verify new versioned collection created
        mock_create.assert_called_once_with(name="packages-1")
        # Verify migration
        mock_migrate.assert_called_once_with(source="packages", target="packages-1")
        # Verify alias created
        mock_alias.assert_called_once_with(source="packages", target="packages-1")
        # Verify old collection deleted
        mock_delete.assert_called_once_with(name="packages")

    def test_recreate_collection_fresh_start(self, mock_typesense):
        """Verify recreate_collection creates new versioned collection when nothing exists."""
        from pyf.aggregator.typesense_util import TypesenceUtil

        ts_util = TypesenceUtil()

        with patch.object(ts_util, "get_alias", return_value=None), \
             patch.object(ts_util, "collection_exists", return_value=False), \
             patch.object(ts_util, "create_collection") as mock_create, \
             patch.object(ts_util, "add_alias") as mock_alias:

            ts_util.recreate_collection(name="packages")

        # Verify new versioned collection created
        mock_create.assert_called_once_with(name="packages-1")
        # Verify alias created
        mock_alias.assert_called_once_with(source="packages", target="packages-1")


class TestImportDataNotEncoded:
    """Regression test: ensure import_data doesn't encode data."""

    def test_import_data_passes_string_not_bytes(self, mock_typesense):
        """Verify import_data passes string data, not bytes."""
        from pyf.aggregator.typesense_util import TypesenceUtil

        sample_jsonl = '{"id":"pkg1","name":"plone.api"}'
        mock_typesense.collections.__getitem__.return_value.documents.import_.return_value = [{"success": True}]

        ts_util = TypesenceUtil()
        ts_util.import_data(collection_name="test-collection", data=sample_jsonl)

        call_args = mock_typesense.collections.__getitem__.return_value.documents.import_.call_args
        passed_data = call_args[0][0]

        # Verify data is string, not bytes
        assert isinstance(passed_data, str), f"Expected str, got {type(passed_data)}"
        assert passed_data == sample_jsonl
