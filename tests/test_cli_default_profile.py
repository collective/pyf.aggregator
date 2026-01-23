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
                mock_util.return_value = mock_util_instance

                # Simulate CLI with --recreate-collection but no -p or -t
                with patch.object(sys, 'argv', ['pyfupdater', '--recreate-collection']):
                    typesense_util_module.main()

                # Verify profile was loaded from env var
                mock_profile_manager.get_profile.assert_called_with("plone")
                mock_util_instance.recreate_collection.assert_called_once_with(name="plone")

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
                mock_util.return_value = mock_util_instance

                # Simulate CLI with -p django and --recreate-collection
                with patch.object(sys, 'argv', ['pyfupdater', '-p', 'django', '--recreate-collection']):
                    typesense_util_module.main()

                # Verify django was used, not plone from env
                mock_profile_manager.get_profile.assert_called_with("django")
                mock_util_instance.recreate_collection.assert_called_once_with(name="django")

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
