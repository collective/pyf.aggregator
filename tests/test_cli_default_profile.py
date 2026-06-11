"""
Unit tests for DEFAULT_PROFILE environment variable support across pyfa subcommands.

This module tests:
- DEFAULT_PROFILE env var fallback when no -p argument is provided
- CLI -p argument overriding DEFAULT_PROFILE env var
- Auto-setting target collection from DEFAULT_PROFILE
- Error messages mentioning DEFAULT_PROFILE option
"""

import argparse
import pytest
from unittest.mock import patch, MagicMock


# ============================================================================
# Test pyfa downloads (enrichers/downloads.py)
# ============================================================================


class TestDownloadsDefaultProfile:
    """Test DEFAULT_PROFILE support in pyfa downloads."""

    def test_uses_default_profile_from_env_when_no_p_arg(self, monkeypatch):
        """Test that DEFAULT_PROFILE env var is used when -p is not provided."""
        monkeypatch.setenv("DEFAULT_PROFILE", "plone")

        import importlib
        import pyf.aggregator.cli_utils as cli_utils_module
        import pyf.aggregator.enrichers.downloads as downloads_module

        importlib.reload(cli_utils_module)
        importlib.reload(downloads_module)

        with patch.object(cli_utils_module, "ProfileManager") as mock_pm:
            mock_profile_manager = MagicMock()
            mock_profile_manager.get_profile.return_value = {
                "classifiers": ["Framework :: Plone"]
            }
            mock_profile_manager.validate_profile.return_value = True
            mock_pm.return_value = mock_profile_manager

            with patch.object(downloads_module, "Enricher") as mock_enricher:
                mock_enricher_instance = MagicMock()
                mock_enricher.return_value = mock_enricher_instance

                args = argparse.Namespace(target=None, profile=None, limit=None)
                downloads_module.run_command(args)

                # Verify profile was loaded from env var
                mock_profile_manager.get_profile.assert_called_with("plone")
                mock_enricher_instance.run.assert_called_once_with(target="plone")

    def test_cli_p_arg_overrides_default_profile_env(self, monkeypatch):
        """Test that -p argument overrides DEFAULT_PROFILE env var."""
        monkeypatch.setenv("DEFAULT_PROFILE", "plone")

        import importlib
        import pyf.aggregator.cli_utils as cli_utils_module
        import pyf.aggregator.enrichers.downloads as downloads_module

        importlib.reload(cli_utils_module)
        importlib.reload(downloads_module)

        with patch.object(cli_utils_module, "ProfileManager") as mock_pm:
            mock_profile_manager = MagicMock()
            mock_profile_manager.get_profile.return_value = {
                "classifiers": ["Framework :: Django"]
            }
            mock_profile_manager.validate_profile.return_value = True
            mock_pm.return_value = mock_profile_manager

            with patch.object(downloads_module, "Enricher") as mock_enricher:
                mock_enricher_instance = MagicMock()
                mock_enricher.return_value = mock_enricher_instance

                args = argparse.Namespace(target=None, profile="django", limit=None)
                downloads_module.run_command(args)

                # Verify django was used, not plone from env
                mock_profile_manager.get_profile.assert_called_with("django")
                mock_enricher_instance.run.assert_called_once_with(target="django")

    def test_error_message_mentions_default_profile(self, monkeypatch):
        """Test that error message mentions DEFAULT_PROFILE option."""
        monkeypatch.delenv("DEFAULT_PROFILE", raising=False)

        import importlib
        import pyf.aggregator.cli_utils as cli_utils_module
        import pyf.aggregator.enrichers.downloads as downloads_module

        importlib.reload(cli_utils_module)
        importlib.reload(downloads_module)

        # Ensure DEFAULT_PROFILE is None
        cli_utils_module.DEFAULT_PROFILE = None

        with patch.object(downloads_module, "Enricher"):
            with patch.object(cli_utils_module, "logger") as mock_logger:
                args = argparse.Namespace(target=None, profile=None, limit=None)
                with pytest.raises(SystemExit) as exc_info:
                    downloads_module.run_command(args)

                assert exc_info.value.code == 1
                # Check error message mentions DEFAULT_PROFILE
                error_call = mock_logger.error.call_args[0][0]
                assert "DEFAULT_PROFILE" in error_call


# ============================================================================
# Test pyfa github (enrichers/github.py)
# ============================================================================


class TestGithubDefaultProfile:
    """Test DEFAULT_PROFILE support in pyfa github."""

    def test_uses_default_profile_from_env_when_no_p_arg(self, monkeypatch):
        """Test that DEFAULT_PROFILE env var is used when -p is not provided."""
        monkeypatch.setenv("DEFAULT_PROFILE", "plone")

        import importlib
        import pyf.aggregator.cli_utils as cli_utils_module
        import pyf.aggregator.enrichers.github as github_module

        importlib.reload(cli_utils_module)
        importlib.reload(github_module)

        with patch.object(cli_utils_module, "ProfileManager") as mock_pm:
            mock_profile_manager = MagicMock()
            mock_profile_manager.get_profile.return_value = {
                "classifiers": ["Framework :: Plone"]
            }
            mock_profile_manager.validate_profile.return_value = True
            mock_pm.return_value = mock_profile_manager

            with patch.object(github_module, "Enricher") as mock_enricher:
                mock_enricher_instance = MagicMock()
                mock_enricher.return_value = mock_enricher_instance

                args = argparse.Namespace(
                    target=None, profile=None, name=None, verbose=False
                )
                github_module.run_command(args)

                # Verify profile was loaded from env var
                mock_profile_manager.get_profile.assert_called_with("plone")
                mock_enricher_instance.run.assert_called_once_with(
                    target="plone", package_name=None, verbose=False, report_dir="."
                )

    def test_cli_p_arg_overrides_default_profile_env(self, monkeypatch):
        """Test that -p argument overrides DEFAULT_PROFILE env var."""
        monkeypatch.setenv("DEFAULT_PROFILE", "plone")

        import importlib
        import pyf.aggregator.cli_utils as cli_utils_module
        import pyf.aggregator.enrichers.github as github_module

        importlib.reload(cli_utils_module)
        importlib.reload(github_module)

        with patch.object(cli_utils_module, "ProfileManager") as mock_pm:
            mock_profile_manager = MagicMock()
            mock_profile_manager.get_profile.return_value = {
                "classifiers": ["Framework :: Django"]
            }
            mock_profile_manager.validate_profile.return_value = True
            mock_pm.return_value = mock_profile_manager

            with patch.object(github_module, "Enricher") as mock_enricher:
                mock_enricher_instance = MagicMock()
                mock_enricher.return_value = mock_enricher_instance

                args = argparse.Namespace(
                    target=None, profile="django", name=None, verbose=False
                )
                github_module.run_command(args)

                # Verify django was used, not plone from env
                mock_profile_manager.get_profile.assert_called_with("django")
                mock_enricher_instance.run.assert_called_once_with(
                    target="django", package_name=None, verbose=False, report_dir="."
                )

    def test_error_message_mentions_default_profile(self, monkeypatch):
        """Test that error message mentions DEFAULT_PROFILE option."""
        monkeypatch.delenv("DEFAULT_PROFILE", raising=False)

        import importlib
        import pyf.aggregator.cli_utils as cli_utils_module
        import pyf.aggregator.enrichers.github as github_module

        importlib.reload(cli_utils_module)
        importlib.reload(github_module)

        # Ensure DEFAULT_PROFILE is None
        cli_utils_module.DEFAULT_PROFILE = None

        with patch.object(github_module, "Enricher"):
            with patch.object(cli_utils_module, "logger") as mock_logger:
                args = argparse.Namespace(
                    target=None, profile=None, name=None, verbose=False
                )
                with pytest.raises(SystemExit) as exc_info:
                    github_module.run_command(args)

                assert exc_info.value.code == 1
                # Check error message mentions DEFAULT_PROFILE
                error_call = mock_logger.error.call_args[0][0]
                assert "DEFAULT_PROFILE" in error_call


# ============================================================================
# Test pyfa manage (typesense_util.py)
# ============================================================================


class TestTypesenseUtilDefaultProfile:
    """Test DEFAULT_PROFILE support in pyfa manage."""

    def _make_manage_args(self, **overrides):
        """Create default manage args namespace."""
        defaults = dict(
            target=None,
            profile=None,
            source="",
            force=False,
            migrate=False,
            add_alias=False,
            list_collections=False,
            list_collection_names=False,
            list_aliases=False,
            list_search_only_apikeys=False,
            add_search_only_apikey=False,
            delete_apikey=None,
            key="gen",
            purge_queue=False,
            queue_stats=False,
            recreate_collection=False,
            delete_collection=None,
            show=None,
            all_versions=False,
        )
        defaults.update(overrides)
        return argparse.Namespace(**defaults)

    def test_uses_default_profile_from_env_when_no_p_arg(self, monkeypatch):
        """Test that DEFAULT_PROFILE env var is used for --recreate-collection."""
        monkeypatch.setenv("DEFAULT_PROFILE", "plone")

        import importlib
        import pyf.aggregator.cli_utils as cli_utils_module
        import pyf.aggregator.typesense_util as typesense_util_module

        importlib.reload(cli_utils_module)
        importlib.reload(typesense_util_module)

        with patch.object(cli_utils_module, "ProfileManager") as mock_pm:
            mock_profile_manager = MagicMock()
            mock_profile_manager.get_profile.return_value = {
                "classifiers": ["Framework :: Plone"]
            }
            mock_profile_manager.validate_profile.return_value = True
            mock_pm.return_value = mock_profile_manager

            with patch.object(typesense_util_module, "TypesenceUtil") as mock_util:
                mock_util_instance = MagicMock()
                mock_util_instance.recreate_collection.return_value = {
                    "old_collection": "plone-1",
                    "new_collection": "plone-2",
                }
                mock_util.return_value = mock_util_instance

                args = self._make_manage_args(recreate_collection=True, force=True)
                typesense_util_module.run_command(args)

                # Verify profile was loaded from env var
                mock_profile_manager.get_profile.assert_called_with("plone")
                mock_util_instance.recreate_collection.assert_called_once_with(
                    name="plone", delete_old=False
                )
                # With --force, old collection should be deleted
                mock_util_instance.delete_collection.assert_called_once_with(
                    name="plone-1"
                )

    def test_cli_p_arg_overrides_default_profile_env(self, monkeypatch):
        """Test that -p argument overrides DEFAULT_PROFILE env var."""
        monkeypatch.setenv("DEFAULT_PROFILE", "plone")

        import importlib
        import pyf.aggregator.cli_utils as cli_utils_module
        import pyf.aggregator.typesense_util as typesense_util_module

        importlib.reload(cli_utils_module)
        importlib.reload(typesense_util_module)

        with patch.object(cli_utils_module, "ProfileManager") as mock_pm:
            mock_profile_manager = MagicMock()
            mock_profile_manager.get_profile.return_value = {
                "classifiers": ["Framework :: Django"]
            }
            mock_profile_manager.validate_profile.return_value = True
            mock_pm.return_value = mock_profile_manager

            with patch.object(typesense_util_module, "TypesenceUtil") as mock_util:
                mock_util_instance = MagicMock()
                mock_util_instance.recreate_collection.return_value = {
                    "old_collection": "django-1",
                    "new_collection": "django-2",
                }
                mock_util.return_value = mock_util_instance

                args = self._make_manage_args(
                    profile="django", recreate_collection=True, force=True
                )
                typesense_util_module.run_command(args)

                # Verify django was used, not plone from env
                mock_profile_manager.get_profile.assert_called_with("django")
                mock_util_instance.recreate_collection.assert_called_once_with(
                    name="django", delete_old=False
                )
                mock_util_instance.delete_collection.assert_called_once_with(
                    name="django-1"
                )

    def test_error_message_mentions_default_profile(self, monkeypatch):
        """Test that error message mentions DEFAULT_PROFILE option for --recreate-collection."""
        monkeypatch.delenv("DEFAULT_PROFILE", raising=False)

        import importlib
        import pyf.aggregator.cli_utils as cli_utils_module
        import pyf.aggregator.typesense_util as typesense_util_module

        importlib.reload(cli_utils_module)
        importlib.reload(typesense_util_module)

        # Ensure DEFAULT_PROFILE is None
        cli_utils_module.DEFAULT_PROFILE = None

        with patch.object(typesense_util_module, "TypesenceUtil"):
            with patch.object(typesense_util_module, "logger") as mock_logger:
                args = self._make_manage_args(recreate_collection=True)
                with pytest.raises(SystemExit) as exc_info:
                    typesense_util_module.run_command(args)

                assert exc_info.value.code == 1
                # Check error message mentions DEFAULT_PROFILE
                error_call = mock_logger.error.call_args[0][0]
                assert "DEFAULT_PROFILE" in error_call


# ============================================================================
# Test profile source logging
# ============================================================================


class TestProfileSourceLogging:
    """Test that profile source (CLI vs env var) is logged correctly."""

    def test_downloads_logs_profile_source_from_env(self, monkeypatch):
        """Test downloads logs 'from DEFAULT_PROFILE' when using env var."""
        monkeypatch.setenv("DEFAULT_PROFILE", "plone")

        import importlib
        import pyf.aggregator.cli_utils as cli_utils_module
        import pyf.aggregator.enrichers.downloads as downloads_module

        importlib.reload(cli_utils_module)
        importlib.reload(downloads_module)

        with patch.object(cli_utils_module, "ProfileManager") as mock_pm:
            mock_profile_manager = MagicMock()
            mock_profile_manager.get_profile.return_value = {
                "classifiers": ["Framework :: Plone"]
            }
            mock_profile_manager.validate_profile.return_value = True
            mock_pm.return_value = mock_profile_manager

            with patch.object(downloads_module, "Enricher") as mock_enricher:
                mock_enricher_instance = MagicMock()
                mock_enricher.return_value = mock_enricher_instance

                with patch.object(cli_utils_module, "logger") as mock_logger:
                    args = argparse.Namespace(target=None, profile=None, limit=None)
                    downloads_module.run_command(args)

                    # Check log mentions source
                    info_calls = [str(call) for call in mock_logger.info.call_args_list]
                    assert any("from DEFAULT_PROFILE" in call for call in info_calls)

    def test_downloads_logs_profile_source_from_cli(self, monkeypatch):
        """Test downloads logs 'from CLI' when using -p argument."""
        monkeypatch.setenv("DEFAULT_PROFILE", "plone")

        import importlib
        import pyf.aggregator.cli_utils as cli_utils_module
        import pyf.aggregator.enrichers.downloads as downloads_module

        importlib.reload(cli_utils_module)
        importlib.reload(downloads_module)

        with patch.object(cli_utils_module, "ProfileManager") as mock_pm:
            mock_profile_manager = MagicMock()
            mock_profile_manager.get_profile.return_value = {
                "classifiers": ["Framework :: Django"]
            }
            mock_profile_manager.validate_profile.return_value = True
            mock_pm.return_value = mock_profile_manager

            with patch.object(downloads_module, "Enricher") as mock_enricher:
                mock_enricher_instance = MagicMock()
                mock_enricher.return_value = mock_enricher_instance

                with patch.object(cli_utils_module, "logger") as mock_logger:
                    args = argparse.Namespace(target=None, profile="django", limit=None)
                    downloads_module.run_command(args)

                    # Check log mentions source
                    info_calls = [str(call) for call in mock_logger.info.call_args_list]
                    assert any("from CLI" in call for call in info_calls)


# ============================================================================
# Test --recreate-collection confirmation prompts (typesense_util.py)
# ============================================================================


class TestRecreateCollectionConfirmationTypesenseUtil:
    """Test user confirmation prompts for --recreate-collection in pyfa manage.

    New behavior: Migration happens first, then user is asked about deleting old collection.
    Default is Yes (delete), 'n' keeps the old collection.
    """

    def _make_manage_args(self, **overrides):
        """Create default manage args namespace."""
        defaults = dict(
            target=None,
            profile=None,
            source="",
            force=False,
            migrate=False,
            add_alias=False,
            list_collections=False,
            list_collection_names=False,
            list_aliases=False,
            list_search_only_apikeys=False,
            add_search_only_apikey=False,
            delete_apikey=None,
            key="gen",
            purge_queue=False,
            queue_stats=False,
            recreate_collection=False,
            delete_collection=None,
            show=None,
            all_versions=False,
        )
        defaults.update(overrides)
        return argparse.Namespace(**defaults)

    def test_confirmation_n_keeps_old_collection(self, monkeypatch):
        """Test that 'n' keeps old collection after migration (doesn't cancel)."""
        monkeypatch.setenv("DEFAULT_PROFILE", "plone")

        import importlib
        import pyf.aggregator.cli_utils as cli_utils_module
        import pyf.aggregator.typesense_util as typesense_util_module

        importlib.reload(cli_utils_module)
        importlib.reload(typesense_util_module)

        with patch.object(cli_utils_module, "ProfileManager") as mock_pm:
            mock_profile_manager = MagicMock()
            mock_profile_manager.get_profile.return_value = {
                "classifiers": ["Framework :: Plone"]
            }
            mock_profile_manager.validate_profile.return_value = True
            mock_pm.return_value = mock_profile_manager

            with patch.object(typesense_util_module, "TypesenceUtil") as mock_util:
                mock_util_instance = MagicMock()
                mock_util_instance.recreate_collection.return_value = {
                    "old_collection": "plone-1",
                    "new_collection": "plone-2",
                }
                mock_util.return_value = mock_util_instance

                with patch.object(typesense_util_module, "logger"):
                    # Mock input to return 'n' (keep old collection)
                    with patch("builtins.input", return_value="n"):
                        args = self._make_manage_args(recreate_collection=True)
                        typesense_util_module.run_command(args)

                # Verify recreate_collection WAS called (migration happens first)
                mock_util_instance.recreate_collection.assert_called_once_with(
                    name="plone", delete_old=False
                )
                # Verify delete_collection was NOT called (user said 'n')
                mock_util_instance.delete_collection.assert_not_called()

    def test_confirmation_prompt_deletes_on_yes(self, monkeypatch):
        """Test that 'y' deletes old collection after migration."""
        monkeypatch.setenv("DEFAULT_PROFILE", "plone")

        import importlib
        import pyf.aggregator.cli_utils as cli_utils_module
        import pyf.aggregator.typesense_util as typesense_util_module

        importlib.reload(cli_utils_module)
        importlib.reload(typesense_util_module)

        with patch.object(cli_utils_module, "ProfileManager") as mock_pm:
            mock_profile_manager = MagicMock()
            mock_profile_manager.get_profile.return_value = {
                "classifiers": ["Framework :: Plone"]
            }
            mock_profile_manager.validate_profile.return_value = True
            mock_pm.return_value = mock_profile_manager

            with patch.object(typesense_util_module, "TypesenceUtil") as mock_util:
                mock_util_instance = MagicMock()
                mock_util_instance.recreate_collection.return_value = {
                    "old_collection": "plone-1",
                    "new_collection": "plone-2",
                }
                mock_util.return_value = mock_util_instance

                # Mock input to return 'y' (delete old collection)
                with patch("builtins.input", return_value="y"):
                    args = self._make_manage_args(recreate_collection=True)
                    typesense_util_module.run_command(args)

                # Verify recreate_collection WAS called
                mock_util_instance.recreate_collection.assert_called_once_with(
                    name="plone", delete_old=False
                )
                # Verify delete_collection WAS called (user said 'y')
                mock_util_instance.delete_collection.assert_called_once_with(
                    name="plone-1"
                )

    def test_confirmation_empty_deletes_by_default(self, monkeypatch):
        """Test that empty input (Enter) deletes old collection (default is Yes)."""
        monkeypatch.setenv("DEFAULT_PROFILE", "plone")

        import importlib
        import pyf.aggregator.cli_utils as cli_utils_module
        import pyf.aggregator.typesense_util as typesense_util_module

        importlib.reload(cli_utils_module)
        importlib.reload(typesense_util_module)

        with patch.object(cli_utils_module, "ProfileManager") as mock_pm:
            mock_profile_manager = MagicMock()
            mock_profile_manager.get_profile.return_value = {
                "classifiers": ["Framework :: Plone"]
            }
            mock_profile_manager.validate_profile.return_value = True
            mock_pm.return_value = mock_profile_manager

            with patch.object(typesense_util_module, "TypesenceUtil") as mock_util:
                mock_util_instance = MagicMock()
                mock_util_instance.recreate_collection.return_value = {
                    "old_collection": "plone-1",
                    "new_collection": "plone-2",
                }
                mock_util.return_value = mock_util_instance

                # Mock input to return '' (just press Enter - default Yes)
                with patch("builtins.input", return_value=""):
                    args = self._make_manage_args(recreate_collection=True)
                    typesense_util_module.run_command(args)

                # Verify recreate_collection WAS called
                mock_util_instance.recreate_collection.assert_called_once_with(
                    name="plone", delete_old=False
                )
                # Verify delete_collection WAS called (default is Yes)
                mock_util_instance.delete_collection.assert_called_once_with(
                    name="plone-1"
                )

    def test_force_flag_skips_confirmation_and_deletes(self, monkeypatch):
        """Test that --force flag skips the confirmation prompt and deletes old collection."""
        monkeypatch.setenv("DEFAULT_PROFILE", "plone")

        import importlib
        import pyf.aggregator.cli_utils as cli_utils_module
        import pyf.aggregator.typesense_util as typesense_util_module

        importlib.reload(cli_utils_module)
        importlib.reload(typesense_util_module)

        with patch.object(cli_utils_module, "ProfileManager") as mock_pm:
            mock_profile_manager = MagicMock()
            mock_profile_manager.get_profile.return_value = {
                "classifiers": ["Framework :: Plone"]
            }
            mock_profile_manager.validate_profile.return_value = True
            mock_pm.return_value = mock_profile_manager

            with patch.object(typesense_util_module, "TypesenceUtil") as mock_util:
                mock_util_instance = MagicMock()
                mock_util_instance.recreate_collection.return_value = {
                    "old_collection": "plone-1",
                    "new_collection": "plone-2",
                }
                mock_util.return_value = mock_util_instance

                # Mock input - should NOT be called
                with patch("builtins.input") as mock_input:
                    args = self._make_manage_args(recreate_collection=True, force=True)
                    typesense_util_module.run_command(args)

                    # Verify input was NOT called (prompt skipped)
                    mock_input.assert_not_called()

                # Verify recreate_collection WAS called
                mock_util_instance.recreate_collection.assert_called_once_with(
                    name="plone", delete_old=False
                )
                # Verify delete_collection WAS called (force deletes)
                mock_util_instance.delete_collection.assert_called_once_with(
                    name="plone-1"
                )


## TestRecreateCollectionConfirmationMain was removed because
## --recreate-collection was removed from pyfa pypi CLI.
## Use pyfa manage --recreate-collection instead.
## See TestRecreateCollectionConfirmationTypesenseUtil for equivalent tests.
