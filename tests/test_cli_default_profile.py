"""
Unit tests for DEFAULT_PROFILE environment variable support across CLI commands.

This module tests:
- DEFAULT_PROFILE env var fallback when no -p argument is provided
- CLI -p argument overriding DEFAULT_PROFILE env var
- Auto-setting target collection from DEFAULT_PROFILE
- Error messages mentioning DEFAULT_PROFILE option
"""

import pytest
import sys
from unittest.mock import patch, MagicMock


# ============================================================================
# Test pyfdownloads CLI (enrichers/downloads.py)
# ============================================================================

class TestDownloadsDefaultProfile:
    """Test DEFAULT_PROFILE support in pyfdownloads CLI."""

    def test_uses_default_profile_from_env_when_no_p_arg(self, monkeypatch):
        """Test that DEFAULT_PROFILE env var is used when -p is not provided."""
        monkeypatch.setenv("DEFAULT_PROFILE", "plone")

        # Reimport to pick up env var
        import importlib
        import pyf.aggregator.enrichers.downloads as downloads_module
        importlib.reload(downloads_module)

        with patch.object(downloads_module, 'ProfileManager') as mock_pm:
            mock_profile_manager = MagicMock()
            mock_profile_manager.get_profile.return_value = {"classifiers": ["Framework :: Plone"]}
            mock_profile_manager.validate_profile.return_value = True
            mock_pm.return_value = mock_profile_manager

            with patch.object(downloads_module, 'Enricher') as mock_enricher:
                mock_enricher_instance = MagicMock()
                mock_enricher.return_value = mock_enricher_instance

                # Simulate CLI with no args
                with patch.object(sys, 'argv', ['pyfdownloads']):
                    downloads_module.main()

                # Verify profile was loaded from env var
                mock_profile_manager.get_profile.assert_called_with("plone")
                mock_enricher_instance.run.assert_called_once_with(target="plone")

    def test_cli_p_arg_overrides_default_profile_env(self, monkeypatch):
        """Test that -p argument overrides DEFAULT_PROFILE env var."""
        monkeypatch.setenv("DEFAULT_PROFILE", "plone")

        import importlib
        import pyf.aggregator.enrichers.downloads as downloads_module
        importlib.reload(downloads_module)

        with patch.object(downloads_module, 'ProfileManager') as mock_pm:
            mock_profile_manager = MagicMock()
            mock_profile_manager.get_profile.return_value = {"classifiers": ["Framework :: Django"]}
            mock_profile_manager.validate_profile.return_value = True
            mock_pm.return_value = mock_profile_manager

            with patch.object(downloads_module, 'Enricher') as mock_enricher:
                mock_enricher_instance = MagicMock()
                mock_enricher.return_value = mock_enricher_instance

                # Simulate CLI with -p django
                with patch.object(sys, 'argv', ['pyfdownloads', '-p', 'django']):
                    downloads_module.main()

                # Verify django was used, not plone from env
                mock_profile_manager.get_profile.assert_called_with("django")
                mock_enricher_instance.run.assert_called_once_with(target="django")

    def test_error_message_mentions_default_profile(self, monkeypatch):
        """Test that error message mentions DEFAULT_PROFILE option."""
        monkeypatch.delenv("DEFAULT_PROFILE", raising=False)

        import importlib
        import pyf.aggregator.enrichers.downloads as downloads_module
        importlib.reload(downloads_module)

        # Ensure DEFAULT_PROFILE is None (in case of caching)
        downloads_module.DEFAULT_PROFILE = None

        with patch.object(downloads_module, 'Enricher'):
            with patch.object(downloads_module, 'logger') as mock_logger:
                with patch.object(sys, 'argv', ['pyfdownloads']):
                    with pytest.raises(SystemExit) as exc_info:
                        downloads_module.main()

                assert exc_info.value.code == 1
                # Check error message mentions DEFAULT_PROFILE
                error_call = mock_logger.error.call_args[0][0]
                assert "DEFAULT_PROFILE" in error_call


# ============================================================================
# Test pyfgithub CLI (enrichers/github.py)
# ============================================================================

class TestGithubDefaultProfile:
    """Test DEFAULT_PROFILE support in pyfgithub CLI."""

    def test_uses_default_profile_from_env_when_no_p_arg(self, monkeypatch):
        """Test that DEFAULT_PROFILE env var is used when -p is not provided."""
        monkeypatch.setenv("DEFAULT_PROFILE", "plone")

        import importlib
        import pyf.aggregator.enrichers.github as github_module
        importlib.reload(github_module)

        with patch.object(github_module, 'ProfileManager') as mock_pm:
            mock_profile_manager = MagicMock()
            mock_profile_manager.get_profile.return_value = {"classifiers": ["Framework :: Plone"]}
            mock_profile_manager.validate_profile.return_value = True
            mock_pm.return_value = mock_profile_manager

            with patch.object(github_module, 'Enricher') as mock_enricher:
                mock_enricher_instance = MagicMock()
                mock_enricher.return_value = mock_enricher_instance

                # Simulate CLI with no args
                with patch.object(sys, 'argv', ['pyfgithub']):
                    github_module.main()

                # Verify profile was loaded from env var
                mock_profile_manager.get_profile.assert_called_with("plone")
                mock_enricher_instance.run.assert_called_once_with(
                    target="plone",
                    package_name=None,
                    verbose=False
                )

    def test_cli_p_arg_overrides_default_profile_env(self, monkeypatch):
        """Test that -p argument overrides DEFAULT_PROFILE env var."""
        monkeypatch.setenv("DEFAULT_PROFILE", "plone")

        import importlib
        import pyf.aggregator.enrichers.github as github_module
        importlib.reload(github_module)

        with patch.object(github_module, 'ProfileManager') as mock_pm:
            mock_profile_manager = MagicMock()
            mock_profile_manager.get_profile.return_value = {"classifiers": ["Framework :: Django"]}
            mock_profile_manager.validate_profile.return_value = True
            mock_pm.return_value = mock_profile_manager

            with patch.object(github_module, 'Enricher') as mock_enricher:
                mock_enricher_instance = MagicMock()
                mock_enricher.return_value = mock_enricher_instance

                # Simulate CLI with -p django
                with patch.object(sys, 'argv', ['pyfgithub', '-p', 'django']):
                    github_module.main()

                # Verify django was used, not plone from env
                mock_profile_manager.get_profile.assert_called_with("django")
                mock_enricher_instance.run.assert_called_once_with(
                    target="django",
                    package_name=None,
                    verbose=False
                )

    def test_error_message_mentions_default_profile(self, monkeypatch):
        """Test that error message mentions DEFAULT_PROFILE option."""
        monkeypatch.delenv("DEFAULT_PROFILE", raising=False)

        import importlib
        import pyf.aggregator.enrichers.github as github_module
        importlib.reload(github_module)

        # Ensure DEFAULT_PROFILE is None (in case of caching)
        github_module.DEFAULT_PROFILE = None

        with patch.object(github_module, 'Enricher'):
            with patch.object(github_module, 'logger') as mock_logger:
                with patch.object(sys, 'argv', ['pyfgithub']):
                    with pytest.raises(SystemExit) as exc_info:
                        github_module.main()

                assert exc_info.value.code == 1
                # Check error message mentions DEFAULT_PROFILE
                error_call = mock_logger.error.call_args[0][0]
                assert "DEFAULT_PROFILE" in error_call


# ============================================================================
# Test pyfupdater CLI (typesense_util.py)
# ============================================================================

class TestTypesenseUtilDefaultProfile:
    """Test DEFAULT_PROFILE support in pyfupdater CLI."""

    def test_uses_default_profile_from_env_when_no_p_arg(self, monkeypatch):
        """Test that DEFAULT_PROFILE env var is used for --recreate-collection."""
        monkeypatch.setenv("DEFAULT_PROFILE", "plone")

        import importlib
        import pyf.aggregator.typesense_util as typesense_util_module
        importlib.reload(typesense_util_module)

        with patch.object(typesense_util_module, 'ProfileManager') as mock_pm:
            mock_profile_manager = MagicMock()
            mock_profile_manager.get_profile.return_value = {"classifiers": ["Framework :: Plone"]}
            mock_profile_manager.validate_profile.return_value = True
            mock_pm.return_value = mock_profile_manager

            with patch.object(typesense_util_module, 'TypesenceUtil') as mock_util:
                mock_util_instance = MagicMock()
                # Return value with old_collection to test deletion flow
                mock_util_instance.recreate_collection.return_value = {"old_collection": "plone-1", "new_collection": "plone-2"}
                mock_util.return_value = mock_util_instance

                # Simulate CLI with --recreate-collection but no -p or -t (use --force to skip prompt)
                with patch.object(sys, 'argv', ['pyfupdater', '--recreate-collection', '--force']):
                    typesense_util_module.main()

                # Verify profile was loaded from env var
                mock_profile_manager.get_profile.assert_called_with("plone")
                # Now calls with delete_old=False, deletion handled after
                mock_util_instance.recreate_collection.assert_called_once_with(name="plone", delete_old=False)
                # With --force, old collection should be deleted
                mock_util_instance.delete_collection.assert_called_once_with(name="plone-1")

    def test_cli_p_arg_overrides_default_profile_env(self, monkeypatch):
        """Test that -p argument overrides DEFAULT_PROFILE env var."""
        monkeypatch.setenv("DEFAULT_PROFILE", "plone")

        import importlib
        import pyf.aggregator.typesense_util as typesense_util_module
        importlib.reload(typesense_util_module)

        with patch.object(typesense_util_module, 'ProfileManager') as mock_pm:
            mock_profile_manager = MagicMock()
            mock_profile_manager.get_profile.return_value = {"classifiers": ["Framework :: Django"]}
            mock_profile_manager.validate_profile.return_value = True
            mock_pm.return_value = mock_profile_manager

            with patch.object(typesense_util_module, 'TypesenceUtil') as mock_util:
                mock_util_instance = MagicMock()
                # Return value with old_collection to test deletion flow
                mock_util_instance.recreate_collection.return_value = {"old_collection": "django-1", "new_collection": "django-2"}
                mock_util.return_value = mock_util_instance

                # Simulate CLI with -p django and --recreate-collection (use --force to skip prompt)
                with patch.object(sys, 'argv', ['pyfupdater', '-p', 'django', '--recreate-collection', '--force']):
                    typesense_util_module.main()

                # Verify django was used, not plone from env
                mock_profile_manager.get_profile.assert_called_with("django")
                # Now calls with delete_old=False, deletion handled after
                mock_util_instance.recreate_collection.assert_called_once_with(name="django", delete_old=False)
                # With --force, old collection should be deleted
                mock_util_instance.delete_collection.assert_called_once_with(name="django-1")

    def test_error_message_mentions_default_profile(self, monkeypatch):
        """Test that error message mentions DEFAULT_PROFILE option for --recreate-collection."""
        monkeypatch.delenv("DEFAULT_PROFILE", raising=False)

        import importlib
        import pyf.aggregator.typesense_util as typesense_util_module
        importlib.reload(typesense_util_module)

        # Ensure DEFAULT_PROFILE is None (in case of caching)
        typesense_util_module.DEFAULT_PROFILE = None

        with patch.object(typesense_util_module, 'TypesenceUtil'):
            with patch.object(typesense_util_module, 'logger') as mock_logger:
                with patch.object(sys, 'argv', ['pyfupdater', '--recreate-collection']):
                    with pytest.raises(SystemExit) as exc_info:
                        typesense_util_module.main()

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
        import pyf.aggregator.enrichers.downloads as downloads_module
        importlib.reload(downloads_module)

        with patch.object(downloads_module, 'ProfileManager') as mock_pm:
            mock_profile_manager = MagicMock()
            mock_profile_manager.get_profile.return_value = {"classifiers": ["Framework :: Plone"]}
            mock_profile_manager.validate_profile.return_value = True
            mock_pm.return_value = mock_profile_manager

            with patch.object(downloads_module, 'Enricher') as mock_enricher:
                mock_enricher_instance = MagicMock()
                mock_enricher.return_value = mock_enricher_instance

                with patch.object(downloads_module, 'logger') as mock_logger:
                    with patch.object(sys, 'argv', ['pyfdownloads']):
                        downloads_module.main()

                    # Check log mentions source
                    info_calls = [str(call) for call in mock_logger.info.call_args_list]
                    assert any("from DEFAULT_PROFILE" in call for call in info_calls)

    def test_downloads_logs_profile_source_from_cli(self, monkeypatch):
        """Test downloads logs 'from CLI' when using -p argument."""
        monkeypatch.setenv("DEFAULT_PROFILE", "plone")

        import importlib
        import pyf.aggregator.enrichers.downloads as downloads_module
        importlib.reload(downloads_module)

        with patch.object(downloads_module, 'ProfileManager') as mock_pm:
            mock_profile_manager = MagicMock()
            mock_profile_manager.get_profile.return_value = {"classifiers": ["Framework :: Django"]}
            mock_profile_manager.validate_profile.return_value = True
            mock_pm.return_value = mock_profile_manager

            with patch.object(downloads_module, 'Enricher') as mock_enricher:
                mock_enricher_instance = MagicMock()
                mock_enricher.return_value = mock_enricher_instance

                with patch.object(downloads_module, 'logger') as mock_logger:
                    with patch.object(sys, 'argv', ['pyfdownloads', '-p', 'django']):
                        downloads_module.main()

                    # Check log mentions source
                    info_calls = [str(call) for call in mock_logger.info.call_args_list]
                    assert any("from CLI" in call for call in info_calls)


# ============================================================================
# Test --recreate-collection confirmation prompts (typesense_util.py)
# ============================================================================

class TestRecreateCollectionConfirmationTypesenseUtil:
    """Test user confirmation prompts for --recreate-collection in pyfupdater.

    New behavior: Migration happens first, then user is asked about deleting old collection.
    Default is Yes (delete), 'n' keeps the old collection.
    """

    def test_confirmation_n_keeps_old_collection(self, monkeypatch):
        """Test that 'n' keeps old collection after migration (doesn't cancel)."""
        monkeypatch.setenv("DEFAULT_PROFILE", "plone")

        import importlib
        import pyf.aggregator.typesense_util as typesense_util_module
        importlib.reload(typesense_util_module)

        with patch.object(typesense_util_module, 'ProfileManager') as mock_pm:
            mock_profile_manager = MagicMock()
            mock_profile_manager.get_profile.return_value = {"classifiers": ["Framework :: Plone"]}
            mock_profile_manager.validate_profile.return_value = True
            mock_pm.return_value = mock_profile_manager

            with patch.object(typesense_util_module, 'TypesenceUtil') as mock_util:
                mock_util_instance = MagicMock()
                mock_util_instance.recreate_collection.return_value = {"old_collection": "plone-1", "new_collection": "plone-2"}
                mock_util.return_value = mock_util_instance

                with patch.object(typesense_util_module, 'logger') as mock_logger:
                    # Mock input to return 'n' (keep old collection)
                    with patch('builtins.input', return_value='n'):
                        with patch.object(sys, 'argv', ['pyfupdater', '--recreate-collection']):
                            # Should NOT exit, migration happens
                            typesense_util_module.main()

                # Verify recreate_collection WAS called (migration happens first)
                mock_util_instance.recreate_collection.assert_called_once_with(name="plone", delete_old=False)
                # Verify delete_collection was NOT called (user said 'n')
                mock_util_instance.delete_collection.assert_not_called()

    def test_confirmation_prompt_deletes_on_yes(self, monkeypatch):
        """Test that 'y' deletes old collection after migration."""
        monkeypatch.setenv("DEFAULT_PROFILE", "plone")

        import importlib
        import pyf.aggregator.typesense_util as typesense_util_module
        importlib.reload(typesense_util_module)

        with patch.object(typesense_util_module, 'ProfileManager') as mock_pm:
            mock_profile_manager = MagicMock()
            mock_profile_manager.get_profile.return_value = {"classifiers": ["Framework :: Plone"]}
            mock_profile_manager.validate_profile.return_value = True
            mock_pm.return_value = mock_profile_manager

            with patch.object(typesense_util_module, 'TypesenceUtil') as mock_util:
                mock_util_instance = MagicMock()
                mock_util_instance.recreate_collection.return_value = {"old_collection": "plone-1", "new_collection": "plone-2"}
                mock_util.return_value = mock_util_instance

                # Mock input to return 'y' (delete old collection)
                with patch('builtins.input', return_value='y'):
                    with patch.object(sys, 'argv', ['pyfupdater', '--recreate-collection']):
                        typesense_util_module.main()

                # Verify recreate_collection WAS called
                mock_util_instance.recreate_collection.assert_called_once_with(name="plone", delete_old=False)
                # Verify delete_collection WAS called (user said 'y')
                mock_util_instance.delete_collection.assert_called_once_with(name="plone-1")

    def test_confirmation_empty_deletes_by_default(self, monkeypatch):
        """Test that empty input (Enter) deletes old collection (default is Yes)."""
        monkeypatch.setenv("DEFAULT_PROFILE", "plone")

        import importlib
        import pyf.aggregator.typesense_util as typesense_util_module
        importlib.reload(typesense_util_module)

        with patch.object(typesense_util_module, 'ProfileManager') as mock_pm:
            mock_profile_manager = MagicMock()
            mock_profile_manager.get_profile.return_value = {"classifiers": ["Framework :: Plone"]}
            mock_profile_manager.validate_profile.return_value = True
            mock_pm.return_value = mock_profile_manager

            with patch.object(typesense_util_module, 'TypesenceUtil') as mock_util:
                mock_util_instance = MagicMock()
                mock_util_instance.recreate_collection.return_value = {"old_collection": "plone-1", "new_collection": "plone-2"}
                mock_util.return_value = mock_util_instance

                # Mock input to return '' (just press Enter - default Yes)
                with patch('builtins.input', return_value=''):
                    with patch.object(sys, 'argv', ['pyfupdater', '--recreate-collection']):
                        typesense_util_module.main()

                # Verify recreate_collection WAS called
                mock_util_instance.recreate_collection.assert_called_once_with(name="plone", delete_old=False)
                # Verify delete_collection WAS called (default is Yes)
                mock_util_instance.delete_collection.assert_called_once_with(name="plone-1")

    def test_force_flag_skips_confirmation_and_deletes(self, monkeypatch):
        """Test that --force flag skips the confirmation prompt and deletes old collection."""
        monkeypatch.setenv("DEFAULT_PROFILE", "plone")

        import importlib
        import pyf.aggregator.typesense_util as typesense_util_module
        importlib.reload(typesense_util_module)

        with patch.object(typesense_util_module, 'ProfileManager') as mock_pm:
            mock_profile_manager = MagicMock()
            mock_profile_manager.get_profile.return_value = {"classifiers": ["Framework :: Plone"]}
            mock_profile_manager.validate_profile.return_value = True
            mock_pm.return_value = mock_profile_manager

            with patch.object(typesense_util_module, 'TypesenceUtil') as mock_util:
                mock_util_instance = MagicMock()
                mock_util_instance.recreate_collection.return_value = {"old_collection": "plone-1", "new_collection": "plone-2"}
                mock_util.return_value = mock_util_instance

                # Mock input - should NOT be called
                with patch('builtins.input') as mock_input:
                    with patch.object(sys, 'argv', ['pyfupdater', '--recreate-collection', '--force']):
                        typesense_util_module.main()

                    # Verify input was NOT called (prompt skipped)
                    mock_input.assert_not_called()

                # Verify recreate_collection WAS called
                mock_util_instance.recreate_collection.assert_called_once_with(name="plone", delete_old=False)
                # Verify delete_collection WAS called (force deletes)
                mock_util_instance.delete_collection.assert_called_once_with(name="plone-1")


# ============================================================================
# Test --recreate-collection confirmation prompts (main.py)
# ============================================================================

class TestRecreateCollectionConfirmationMain:
    """Test user confirmation prompts for --recreate-collection in pyfaggregator.

    New behavior: Migration happens first, then user is asked about deleting old collection.
    Default is Yes (delete), 'n' keeps the old collection.
    """

    def test_confirmation_n_keeps_old_collection(self, monkeypatch):
        """Test that 'n' keeps old collection after migration (doesn't cancel)."""
        monkeypatch.setenv("DEFAULT_PROFILE", "plone")

        import importlib
        import pyf.aggregator.main as main_module
        importlib.reload(main_module)

        with patch.object(main_module, 'ProfileManager') as mock_pm:
            mock_profile_manager = MagicMock()
            mock_profile_manager.get_profile.return_value = {"classifiers": ["Framework :: Plone"]}
            mock_profile_manager.validate_profile.return_value = True
            mock_pm.return_value = mock_profile_manager

            mock_ts_util_instance = MagicMock()
            mock_ts_util_instance.recreate_collection.return_value = {"old_collection": "plone-1", "new_collection": "plone-2"}
            mock_ts_util_class = MagicMock(return_value=mock_ts_util_instance)

            with patch.object(main_module, 'Indexer') as mock_indexer:
                mock_indexer_instance = MagicMock()
                mock_indexer_instance.collection_exists.return_value = True
                mock_indexer.return_value = mock_indexer_instance

                with patch.object(main_module, 'Aggregator') as mock_aggregator:
                    mock_agg_instance = MagicMock()
                    mock_aggregator.return_value = mock_agg_instance

                    # Mock input to return 'n' (keep old collection)
                    with patch('builtins.input', return_value='n'):
                        with patch.object(sys, 'argv', ['pyfaggregator', '-f', '--recreate-collection']):
                            import builtins
                            original_import = builtins.__import__

                            def mock_import(name, *args, **kwargs):
                                if name == 'pyf.aggregator.typesense_util':
                                    mock_module = MagicMock()
                                    mock_module.TypesenceUtil = mock_ts_util_class
                                    return mock_module
                                return original_import(name, *args, **kwargs)

                            with patch.object(builtins, '__import__', side_effect=mock_import):
                                # Should NOT exit, migration happens
                                main_module.main()

                    # Verify recreate_collection WAS called (migration happens first)
                    mock_ts_util_instance.recreate_collection.assert_called_once_with(name="plone", delete_old=False)
                    # Verify delete_collection was NOT called (user said 'n')
                    mock_ts_util_instance.delete_collection.assert_not_called()

    def test_confirmation_prompt_deletes_on_yes(self, monkeypatch):
        """Test that 'y' deletes old collection after migration."""
        monkeypatch.setenv("DEFAULT_PROFILE", "plone")

        import importlib
        import pyf.aggregator.main as main_module
        importlib.reload(main_module)

        with patch.object(main_module, 'ProfileManager') as mock_pm:
            mock_profile_manager = MagicMock()
            mock_profile_manager.get_profile.return_value = {"classifiers": ["Framework :: Plone"]}
            mock_profile_manager.validate_profile.return_value = True
            mock_pm.return_value = mock_profile_manager

            mock_ts_util_instance = MagicMock()
            mock_ts_util_instance.recreate_collection.return_value = {"old_collection": "plone-1", "new_collection": "plone-2"}
            mock_ts_util_class = MagicMock(return_value=mock_ts_util_instance)

            with patch.object(main_module, 'Indexer') as mock_indexer:
                mock_indexer_instance = MagicMock()
                mock_indexer_instance.collection_exists.return_value = True
                mock_indexer.return_value = mock_indexer_instance

                with patch.object(main_module, 'Aggregator') as mock_aggregator:
                    mock_agg_instance = MagicMock()
                    mock_aggregator.return_value = mock_agg_instance

                    # Mock input to return 'y' (delete old collection)
                    with patch('builtins.input', return_value='y'):
                        with patch.object(sys, 'argv', ['pyfaggregator', '-f', '--recreate-collection']):
                            import builtins
                            original_import = builtins.__import__

                            def mock_import(name, *args, **kwargs):
                                if name == 'pyf.aggregator.typesense_util':
                                    mock_module = MagicMock()
                                    mock_module.TypesenceUtil = mock_ts_util_class
                                    return mock_module
                                return original_import(name, *args, **kwargs)

                            with patch.object(builtins, '__import__', side_effect=mock_import):
                                main_module.main()

                    # Verify recreate_collection WAS called
                    mock_ts_util_instance.recreate_collection.assert_called_once_with(name="plone", delete_old=False)
                    # Verify delete_collection WAS called (user said 'y')
                    mock_ts_util_instance.delete_collection.assert_called_once_with(name="plone-1")

    def test_force_flag_skips_confirmation_and_deletes(self, monkeypatch):
        """Test that --force flag skips the confirmation prompt and deletes old collection."""
        monkeypatch.setenv("DEFAULT_PROFILE", "plone")

        import importlib
        import pyf.aggregator.main as main_module
        importlib.reload(main_module)

        with patch.object(main_module, 'ProfileManager') as mock_pm:
            mock_profile_manager = MagicMock()
            mock_profile_manager.get_profile.return_value = {"classifiers": ["Framework :: Plone"]}
            mock_profile_manager.validate_profile.return_value = True
            mock_pm.return_value = mock_profile_manager

            mock_ts_util_instance = MagicMock()
            mock_ts_util_instance.recreate_collection.return_value = {"old_collection": "plone-1", "new_collection": "plone-2"}
            mock_ts_util_class = MagicMock(return_value=mock_ts_util_instance)

            with patch.object(main_module, 'Indexer') as mock_indexer:
                mock_indexer_instance = MagicMock()
                mock_indexer_instance.collection_exists.return_value = True
                mock_indexer.return_value = mock_indexer_instance

                with patch.object(main_module, 'Aggregator') as mock_aggregator:
                    mock_agg_instance = MagicMock()
                    mock_aggregator.return_value = mock_agg_instance

                    # Mock input - should NOT be called
                    with patch('builtins.input') as mock_input:
                        with patch.object(sys, 'argv', ['pyfaggregator', '-f', '--recreate-collection', '--force']):
                            import builtins
                            original_import = builtins.__import__

                            def mock_import(name, *args, **kwargs):
                                if name == 'pyf.aggregator.typesense_util':
                                    mock_module = MagicMock()
                                    mock_module.TypesenceUtil = mock_ts_util_class
                                    return mock_module
                                return original_import(name, *args, **kwargs)

                            with patch.object(builtins, '__import__', side_effect=mock_import):
                                main_module.main()

                        # Verify input was NOT called (prompt skipped)
                        mock_input.assert_not_called()

                    # Verify recreate_collection WAS called
                    mock_ts_util_instance.recreate_collection.assert_called_once_with(name="plone", delete_old=False)
                    # Verify delete_collection WAS called (force deletes)
                    mock_ts_util_instance.delete_collection.assert_called_once_with(name="plone-1")
