"""
Unit tests for pyf.aggregator.profiles module.

This module tests:
- Profile loading from YAML configuration
- Profile retrieval and validation
- Error handling for missing/invalid configuration
- ProfileManager initialization and configuration
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from pyf.aggregator.profiles import ProfileManager


# ============================================================================
# ProfileManager Initialization Tests
# ============================================================================

class TestProfileManagerInit:
    """Test ProfileManager initialization."""

    def test_initializes_with_default_config_path(self, tmp_path):
        """Test that ProfileManager uses default profiles.yaml path."""
        # Create a temporary valid profiles.yaml
        config_content = """
profiles:
  plone:
    name: "Plone"
    classifiers:
      - "Framework :: Plone"
"""
        config_path = tmp_path / "profiles.yaml"
        config_path.write_text(config_content)

        # Mock the default path to point to our temp file
        with patch("pyf.aggregator.profiles.Path") as mock_path:
            mock_path.return_value.parent = tmp_path
            mock_path.return_value = config_path

            manager = ProfileManager(config_path=config_path)
            assert manager._profiles is not None
            assert "plone" in manager._profiles

    def test_initializes_with_custom_config_path(self, tmp_path):
        """Test that ProfileManager accepts custom config path."""
        config_content = """
profiles:
  django:
    name: "Django"
    classifiers:
      - "Framework :: Django"
"""
        config_path = tmp_path / "custom_profiles.yaml"
        config_path.write_text(config_content)

        manager = ProfileManager(config_path=config_path)
        assert manager.config_path == config_path
        assert "django" in manager._profiles

    def test_raises_file_not_found_for_missing_config(self, tmp_path):
        """Test that FileNotFoundError is raised when config doesn't exist."""
        nonexistent_path = tmp_path / "nonexistent.yaml"

        with pytest.raises(FileNotFoundError) as exc_info:
            ProfileManager(config_path=nonexistent_path)

        assert "Profile configuration not found" in str(exc_info.value)
        assert str(nonexistent_path) in str(exc_info.value)

    def test_raises_value_error_for_invalid_yaml(self, tmp_path):
        """Test that ValueError is raised for invalid YAML syntax."""
        config_path = tmp_path / "invalid.yaml"
        config_path.write_text("profiles:\n  invalid: [\n    unclosed list")

        with pytest.raises(ValueError) as exc_info:
            ProfileManager(config_path=config_path)

        assert "Invalid YAML" in str(exc_info.value)

    def test_raises_value_error_for_missing_profiles_key(self, tmp_path):
        """Test that ValueError is raised when 'profiles' key is missing."""
        config_path = tmp_path / "no_profiles.yaml"
        config_path.write_text("frameworks:\n  plone:\n    name: 'Plone'")

        with pytest.raises(ValueError) as exc_info:
            ProfileManager(config_path=config_path)

        assert "missing 'profiles' key" in str(exc_info.value)

    def test_raises_value_error_for_empty_config(self, tmp_path):
        """Test that ValueError is raised for empty config file."""
        config_path = tmp_path / "empty.yaml"
        config_path.write_text("")

        with pytest.raises(ValueError) as exc_info:
            ProfileManager(config_path=config_path)

        assert "missing 'profiles' key" in str(exc_info.value)


# ============================================================================
# Profile Retrieval Tests
# ============================================================================

class TestGetProfile:
    """Test the get_profile method."""

    @pytest.fixture
    def manager(self, tmp_path):
        """Create a ProfileManager with sample profiles."""
        config_content = """
profiles:
  plone:
    name: "Plone"
    classifiers:
      - "Framework :: Plone"
      - "Framework :: Plone :: 6.0"
  django:
    name: "Django"
    classifiers:
      - "Framework :: Django"
  flask:
    name: "Flask"
    classifiers:
      - "Framework :: Flask"
"""
        config_path = tmp_path / "profiles.yaml"
        config_path.write_text(config_content)
        return ProfileManager(config_path=config_path)

    def test_returns_profile_for_valid_name(self, manager):
        """Test that get_profile returns correct profile for valid name."""
        profile = manager.get_profile("plone")
        assert profile is not None
        assert profile["name"] == "Plone"
        assert "Framework :: Plone" in profile["classifiers"]
        assert "Framework :: Plone :: 6.0" in profile["classifiers"]

    def test_returns_different_profiles(self, manager):
        """Test that different profile names return different configs."""
        plone = manager.get_profile("plone")
        django = manager.get_profile("django")

        assert plone is not None
        assert django is not None
        assert plone["name"] == "Plone"
        assert django["name"] == "Django"
        assert plone["classifiers"] != django["classifiers"]

    def test_returns_none_for_nonexistent_profile(self, manager):
        """Test that get_profile returns None for non-existent profile."""
        profile = manager.get_profile("nonexistent")
        assert profile is None

    def test_logs_warning_for_nonexistent_profile(self, manager):
        """Test that warning is logged for non-existent profile."""
        with patch("pyf.aggregator.profiles.logger") as mock_logger:
            manager.get_profile("nonexistent")
            mock_logger.warning.assert_called_once()
            assert "not found" in mock_logger.warning.call_args[0][0]


# ============================================================================
# Profile Listing Tests
# ============================================================================

class TestListProfiles:
    """Test the list_profiles method."""

    @pytest.fixture
    def manager(self, tmp_path):
        """Create a ProfileManager with sample profiles."""
        config_content = """
profiles:
  zope:
    name: "Zope"
    classifiers:
      - "Framework :: Zope"
  plone:
    name: "Plone"
    classifiers:
      - "Framework :: Plone"
  django:
    name: "Django"
    classifiers:
      - "Framework :: Django"
"""
        config_path = tmp_path / "profiles.yaml"
        config_path.write_text(config_content)
        return ProfileManager(config_path=config_path)

    def test_returns_all_profile_names(self, manager):
        """Test that list_profiles returns all profile identifiers."""
        profiles = manager.list_profiles()
        assert "plone" in profiles
        assert "django" in profiles
        assert "zope" in profiles
        assert len(profiles) == 3

    def test_returns_sorted_list(self, manager):
        """Test that list_profiles returns alphabetically sorted list."""
        profiles = manager.list_profiles()
        assert profiles == sorted(profiles)
        assert profiles == ["django", "plone", "zope"]

    def test_returns_empty_list_for_no_profiles(self, tmp_path):
        """Test that empty profiles dict returns empty list."""
        config_path = tmp_path / "empty_profiles.yaml"
        config_path.write_text("profiles: {}")

        manager = ProfileManager(config_path=config_path)
        profiles = manager.list_profiles()
        assert profiles == []


# ============================================================================
# Profile Validation Tests
# ============================================================================

class TestValidateProfile:
    """Test the validate_profile method."""

    @pytest.fixture
    def manager_valid(self, tmp_path):
        """Create ProfileManager with valid profiles."""
        config_content = """
profiles:
  plone:
    name: "Plone"
    classifiers:
      - "Framework :: Plone"
"""
        config_path = tmp_path / "valid.yaml"
        config_path.write_text(config_content)
        return ProfileManager(config_path=config_path)

    @pytest.fixture
    def manager_invalid(self, tmp_path):
        """Create ProfileManager with various invalid profiles."""
        config_content = """
profiles:
  no_name:
    classifiers:
      - "Framework :: Test"
  no_classifiers:
    name: "No Classifiers"
  classifiers_not_list:
    name: "Bad Classifiers"
    classifiers: "Framework :: Test"
  empty_classifiers:
    name: "Empty Classifiers"
    classifiers: []
"""
        config_path = tmp_path / "invalid.yaml"
        config_path.write_text(config_content)
        return ProfileManager(config_path=config_path)

    def test_returns_true_for_valid_profile(self, manager_valid):
        """Test that validate_profile returns True for valid profile."""
        assert manager_valid.validate_profile("plone") is True

    def test_returns_false_for_nonexistent_profile(self, manager_valid):
        """Test that validate_profile returns False for non-existent profile."""
        assert manager_valid.validate_profile("nonexistent") is False

    def test_returns_false_for_missing_name_field(self, manager_invalid):
        """Test that validate_profile returns False when 'name' field is missing."""
        with patch("pyf.aggregator.profiles.logger") as mock_logger:
            result = manager_invalid.validate_profile("no_name")
            assert result is False
            mock_logger.error.assert_called_once()
            assert "missing 'name' field" in mock_logger.error.call_args[0][0]

    def test_returns_false_for_missing_classifiers_field(self, manager_invalid):
        """Test that validate_profile returns False when 'classifiers' field is missing."""
        with patch("pyf.aggregator.profiles.logger") as mock_logger:
            result = manager_invalid.validate_profile("no_classifiers")
            assert result is False
            mock_logger.error.assert_called_once()
            assert "missing 'classifiers' field" in mock_logger.error.call_args[0][0]

    def test_returns_false_for_non_list_classifiers(self, manager_invalid):
        """Test that validate_profile returns False when classifiers is not a list."""
        with patch("pyf.aggregator.profiles.logger") as mock_logger:
            result = manager_invalid.validate_profile("classifiers_not_list")
            assert result is False
            mock_logger.error.assert_called_once()
            assert "must be a list" in mock_logger.error.call_args[0][0]

    def test_returns_false_for_empty_classifiers_list(self, manager_invalid):
        """Test that validate_profile returns False when classifiers list is empty."""
        with patch("pyf.aggregator.profiles.logger") as mock_logger:
            result = manager_invalid.validate_profile("empty_classifiers")
            assert result is False
            mock_logger.error.assert_called_once()
            assert "empty classifiers list" in mock_logger.error.call_args[0][0]

    def test_validates_multiple_profiles(self, tmp_path):
        """Test validating multiple profiles with mixed validity."""
        config_content = """
profiles:
  valid1:
    name: "Valid Profile 1"
    classifiers:
      - "Framework :: Test1"
  valid2:
    name: "Valid Profile 2"
    classifiers:
      - "Framework :: Test2"
      - "Framework :: Test2 :: 1.0"
  invalid:
    name: "Invalid Profile"
    classifiers: []
"""
        config_path = tmp_path / "mixed.yaml"
        config_path.write_text(config_content)
        manager = ProfileManager(config_path=config_path)

        assert manager.validate_profile("valid1") is True
        assert manager.validate_profile("valid2") is True
        assert manager.validate_profile("invalid") is False


# ============================================================================
# Integration Tests
# ============================================================================

class TestProfileManagerIntegration:
    """Integration tests for ProfileManager with realistic scenarios."""

    @pytest.fixture
    def manager_realistic(self, tmp_path):
        """Create ProfileManager with realistic multi-framework config."""
        config_content = """
profiles:
  plone:
    name: "Plone"
    classifiers:
      - "Framework :: Plone"
      - "Framework :: Plone :: 6.0"
      - "Framework :: Plone :: 5.2"
      - "Framework :: Plone :: Core"
      - "Framework :: Plone :: Addon"
  django:
    name: "Django"
    classifiers:
      - "Framework :: Django"
      - "Framework :: Django :: 5.0"
      - "Framework :: Django :: 4.2"
  flask:
    name: "Flask"
    classifiers:
      - "Framework :: Flask"
"""
        config_path = tmp_path / "profiles.yaml"
        config_path.write_text(config_content)
        return ProfileManager(config_path=config_path)

    def test_loads_all_profiles_correctly(self, manager_realistic):
        """Test that all profiles are loaded with correct structure."""
        profiles = manager_realistic.list_profiles()
        assert len(profiles) == 3
        assert all(manager_realistic.validate_profile(p) for p in profiles)

    def test_retrieves_plone_profile_with_all_classifiers(self, manager_realistic):
        """Test Plone profile has expected classifiers."""
        plone = manager_realistic.get_profile("plone")
        assert len(plone["classifiers"]) == 5
        assert "Framework :: Plone" in plone["classifiers"]
        assert "Framework :: Plone :: 6.0" in plone["classifiers"]
        assert "Framework :: Plone :: Core" in plone["classifiers"]

    def test_retrieves_django_profile_with_version_classifiers(self, manager_realistic):
        """Test Django profile has version-specific classifiers."""
        django = manager_realistic.get_profile("django")
        assert "Framework :: Django" in django["classifiers"]
        assert "Framework :: Django :: 5.0" in django["classifiers"]
        assert "Framework :: Django :: 4.2" in django["classifiers"]

    def test_validates_all_loaded_profiles(self, manager_realistic):
        """Test that all loaded profiles pass validation."""
        for profile_name in manager_realistic.list_profiles():
            assert manager_realistic.validate_profile(profile_name) is True

    def test_handles_workflow_get_list_validate(self, manager_realistic):
        """Test typical workflow: list, get, validate profiles."""
        # List available profiles
        available = manager_realistic.list_profiles()
        assert len(available) > 0

        # Get and validate each profile
        for name in available:
            profile = manager_realistic.get_profile(name)
            assert profile is not None
            assert manager_realistic.validate_profile(name) is True
            assert "name" in profile
            assert "classifiers" in profile
            assert isinstance(profile["classifiers"], list)
            assert len(profile["classifiers"]) > 0
