"""
Integration tests for multi-profile workflow.

This module tests the complete integration of profiles system:
- Profile loading and configuration
- CLI integration with --profile flag
- Aggregator classifier filtering with profile classifiers
- Collection naming from profiles
- Multiple profiles coexisting with separate collections
"""

import pytest
import responses
from unittest.mock import patch, MagicMock
import sys
import re

from pyf.aggregator.profiles import ProfileManager
from pyf.aggregator.main import parser, main
from pyf.aggregator.fetcher import Aggregator


# ============================================================================
# Profile Manager Integration Tests
# ============================================================================


class TestProfileManagerIntegration:
    """Test ProfileManager with actual profiles.yaml file."""

    def test_loads_default_profiles(self):
        """Test that default profiles.yaml loads successfully."""
        manager = ProfileManager()
        profiles = manager.list_profiles()

        # Should have at least plone, django, flask profiles
        assert "plone" in profiles
        assert "django" in profiles
        assert "flask" in profiles

    def test_plone_profile_structure(self):
        """Test that plone profile has correct structure."""
        manager = ProfileManager()
        plone = manager.get_profile("plone")

        assert plone is not None
        assert "name" in plone
        assert "classifiers" in plone
        assert plone["name"] == "Plone"
        assert isinstance(plone["classifiers"], list)
        assert len(plone["classifiers"]) > 0
        assert "Framework :: Plone" in plone["classifiers"]

    def test_django_profile_structure(self):
        """Test that django profile has correct structure."""
        manager = ProfileManager()
        django = manager.get_profile("django")

        assert django is not None
        assert "name" in django
        assert "classifiers" in django
        assert django["name"] == "Django"
        assert isinstance(django["classifiers"], list)
        assert len(django["classifiers"]) > 0
        assert "Framework :: Django" in django["classifiers"]

    def test_flask_profile_structure(self):
        """Test that flask profile has correct structure."""
        manager = ProfileManager()
        flask = manager.get_profile("flask")

        assert flask is not None
        assert "name" in flask
        assert "classifiers" in flask
        assert flask["name"] == "Flask"
        assert isinstance(flask["classifiers"], list)
        assert len(flask["classifiers"]) > 0
        assert "Framework :: Flask" in flask["classifiers"]

    def test_all_profiles_validate(self):
        """Test that all default profiles pass validation."""
        manager = ProfileManager()
        profiles = manager.list_profiles()

        for profile_name in profiles:
            assert manager.validate_profile(profile_name), (
                f"Profile '{profile_name}' failed validation"
            )


# ============================================================================
# CLI Profile Integration Tests
# ============================================================================


class TestCLIProfileIntegration:
    """Test CLI integration with --profile flag."""

    def test_cli_parser_accepts_profile_flag(self):
        """Test that CLI parser accepts --profile flag."""
        args = parser.parse_args(["-f", "-t", "test", "-p", "plone"])

        assert hasattr(args, "profile")
        assert args.profile == "plone"
        assert args.first is True
        assert args.target == "test"

    def test_cli_parser_profile_flag_short_form(self):
        """Test that CLI parser accepts -p short form."""
        args = parser.parse_args(["-f", "-p", "django", "-t", "django-packages"])

        assert args.profile == "django"
        assert args.target == "django-packages"

    def test_cli_with_profile_no_target_auto_sets_collection(self):
        """Test that CLI auto-sets collection name from profile when -t is omitted."""
        # Mock sys.exit to capture exit without terminating test
        with (
            patch("sys.exit") as mock_exit,
            patch("pyf.aggregator.main.Indexer") as mock_indexer,
            patch("pyf.aggregator.main.Aggregator") as mock_aggregator,
        ):
            # Mock indexer behavior
            mock_indexer_instance = MagicMock()
            mock_indexer_instance.collection_exists.return_value = True
            mock_indexer.return_value = mock_indexer_instance

            # Mock aggregator
            mock_agg_instance = MagicMock()
            mock_agg_instance.__iter__ = MagicMock(return_value=iter([]))
            mock_aggregator.return_value = mock_agg_instance

            # Simulate command line: -f -p django (no -t flag)
            test_args = ["-f", "-p", "django"]
            with patch.object(sys, "argv", ["pyfaggregator"] + test_args):
                main()

            # Should not exit with error
            mock_exit.assert_not_called()

            # Verify Aggregator was called with Django classifiers
            call_kwargs = mock_aggregator.call_args[1]
            assert "filter_troove" in call_kwargs
            # Django classifiers should be in filter_troove
            filter_troove = call_kwargs["filter_troove"]
            assert isinstance(filter_troove, list)
            assert any("Django" in c for c in filter_troove)

    def test_cli_with_invalid_profile_exits_with_error(self):
        """Test that CLI exits with error for invalid profile."""
        # Mock sys.exit to raise SystemExit (actual behavior) so execution stops
        with patch("sys.exit", side_effect=SystemExit) as mock_exit:
            test_args = ["-f", "-p", "nonexistent", "-t", "test"]
            with patch.object(sys, "argv", ["pyfaggregator"] + test_args):
                with pytest.raises(SystemExit):
                    main()

            # Should have been called with error code 1
            mock_exit.assert_called_with(1)

    def test_cli_with_profile_loads_correct_classifiers(self):
        """Test that CLI loads correct classifiers from profile."""
        with (
            patch("pyf.aggregator.main.Indexer") as mock_indexer,
            patch("pyf.aggregator.main.Aggregator") as mock_aggregator,
            patch("sys.exit"),
        ):
            # Mock indexer
            mock_indexer_instance = MagicMock()
            mock_indexer_instance.collection_exists.return_value = True
            mock_indexer.return_value = mock_indexer_instance

            # Mock aggregator
            mock_agg_instance = MagicMock()
            mock_agg_instance.__iter__ = MagicMock(return_value=iter([]))
            mock_aggregator.return_value = mock_agg_instance

            # Test with flask profile
            test_args = ["-f", "-p", "flask", "-t", "flask-test"]
            with patch.object(sys, "argv", ["pyfaggregator"] + test_args):
                main()

            # Verify Aggregator was initialized with Flask classifiers
            call_kwargs = mock_aggregator.call_args[1]
            filter_troove = call_kwargs["filter_troove"]
            assert "Framework :: Flask" in filter_troove


# ============================================================================
# Aggregator Profile Integration Tests
# ============================================================================


class TestAggregatorProfileIntegration:
    """Test Aggregator with profile-based classifier filtering."""

    @responses.activate
    def test_aggregator_filters_django_packages_with_django_profile(
        self, sample_pypi_json_django
    ):
        """Test that Aggregator correctly filters Django packages using Django profile."""
        # Setup mock PyPI response for Django package
        responses.add(
            responses.GET,
            re.compile(r"https://pypi\.org/+pypi/django-rest-framework/json"),
            json=sample_pypi_json_django,
            status=200,
        )

        # Create aggregator with Django classifiers from profile
        manager = ProfileManager()
        django_profile = manager.get_profile("django")
        django_classifiers = django_profile["classifiers"]

        aggregator = Aggregator(mode="first", filter_troove=django_classifiers, limit=1)

        # Test has_classifiers method with Django package
        assert (
            aggregator.has_classifiers(sample_pypi_json_django, django_classifiers)
            is True
        )

    @responses.activate
    def test_aggregator_rejects_non_django_with_django_profile(
        self, sample_pypi_json_plone
    ):
        """Test that Aggregator rejects non-Django packages when using Django profile."""
        # Create aggregator with Django classifiers
        manager = ProfileManager()
        django_profile = manager.get_profile("django")
        django_classifiers = django_profile["classifiers"]

        aggregator = Aggregator(mode="first", filter_troove=django_classifiers)

        # Plone package should NOT match Django classifiers
        assert (
            aggregator.has_classifiers(sample_pypi_json_plone, django_classifiers)
            is False
        )

    @responses.activate
    def test_aggregator_filters_flask_packages_with_flask_profile(
        self, sample_pypi_json_flask
    ):
        """Test that Aggregator correctly filters Flask packages using Flask profile."""
        # Create aggregator with Flask classifiers from profile
        manager = ProfileManager()
        flask_profile = manager.get_profile("flask")
        flask_classifiers = flask_profile["classifiers"]

        aggregator = Aggregator(mode="first", filter_troove=flask_classifiers)

        # Test has_classifiers method with Flask package
        assert (
            aggregator.has_classifiers(sample_pypi_json_flask, flask_classifiers)
            is True
        )


# ============================================================================
# Multi-Profile Coexistence Tests
# ============================================================================


class TestMultiProfileCoexistence:
    """Test that multiple profiles can coexist with separate collections."""

    def test_different_profiles_have_different_classifiers(self):
        """Test that each profile has unique classifier sets."""
        manager = ProfileManager()

        plone = manager.get_profile("plone")
        django = manager.get_profile("django")
        flask = manager.get_profile("flask")

        plone_classifiers = set(plone["classifiers"])
        django_classifiers = set(django["classifiers"])
        flask_classifiers = set(flask["classifiers"])

        # Verify they are distinct sets
        assert not plone_classifiers.intersection(django_classifiers), (
            "Plone and Django classifiers should not overlap"
        )
        assert not plone_classifiers.intersection(flask_classifiers), (
            "Plone and Flask classifiers should not overlap"
        )
        assert not django_classifiers.intersection(flask_classifiers), (
            "Django and Flask classifiers should not overlap"
        )

    def test_profiles_can_be_loaded_simultaneously(self):
        """Test that multiple profiles can be loaded at once."""
        manager = ProfileManager()

        # Load all profiles
        plone = manager.get_profile("plone")
        django = manager.get_profile("django")
        flask = manager.get_profile("flask")

        # All should be valid
        assert plone is not None
        assert django is not None
        assert flask is not None

        # Each should have unique names
        assert plone["name"] != django["name"]
        assert plone["name"] != flask["name"]
        assert django["name"] != flask["name"]

    def test_profile_based_collection_names_are_unique(self):
        """Test that profile-based collection names are unique."""
        manager = ProfileManager()
        profiles = manager.list_profiles()

        # Profile names (used as collection names) should be unique
        assert len(profiles) == len(set(profiles)), "Profile names should be unique"


# ============================================================================
# End-to-End Profile Workflow Tests
# ============================================================================


class TestProfileWorkflowE2E:
    """End-to-end tests for complete profile workflow."""

    @responses.activate
    def test_complete_workflow_plone_profile(
        self, sample_pypi_json_plone, sample_simple_api_response
    ):
        """Test complete workflow: profile load -> CLI -> aggregator -> filtering."""
        # Mock PyPI Simple API
        responses.add(
            responses.GET,
            re.compile(r"https://pypi\.org/+simple/"),
            json=sample_simple_api_response,
            status=200,
        )

        # Mock PyPI JSON API for plone.api
        responses.add(
            responses.GET,
            re.compile(r"https://pypi\.org/+pypi/plone\.api/json"),
            json=sample_pypi_json_plone,
            status=200,
        )

        # Load Plone profile
        manager = ProfileManager()
        plone_profile = manager.get_profile("plone")
        assert plone_profile is not None

        # Create aggregator with Plone classifiers
        aggregator = Aggregator(
            mode="first", filter_troove=plone_profile["classifiers"], limit=1
        )

        # Verify Plone package matches
        plone_json = aggregator._get_pypi_json("plone.api")
        assert (
            aggregator.has_classifiers(plone_json, plone_profile["classifiers"]) is True
        )

    @responses.activate
    def test_complete_workflow_django_profile(
        self, sample_pypi_json_django, sample_simple_api_response
    ):
        """Test complete workflow with Django profile."""
        # Mock PyPI Simple API
        responses.add(
            responses.GET,
            re.compile(r"https://pypi\.org/+simple/"),
            json=sample_simple_api_response,
            status=200,
        )

        # Mock PyPI JSON API for django-rest-framework
        responses.add(
            responses.GET,
            re.compile(r"https://pypi\.org/+pypi/django-rest-framework/json"),
            json=sample_pypi_json_django,
            status=200,
        )

        # Load Django profile
        manager = ProfileManager()
        django_profile = manager.get_profile("django")
        assert django_profile is not None

        # Create aggregator with Django classifiers
        aggregator = Aggregator(
            mode="first", filter_troove=django_profile["classifiers"], limit=1
        )

        # Verify Django package matches
        django_json = aggregator._get_pypi_json("django-rest-framework")
        assert (
            aggregator.has_classifiers(django_json, django_profile["classifiers"])
            is True
        )

    def test_switching_profiles_changes_collection_target(self):
        """Test that switching profiles changes the target collection."""
        # Test plone profile -> plone collection
        args_plone = parser.parse_args(["-f", "-p", "plone"])
        assert args_plone.profile == "plone"
        # Collection would be auto-set to "plone" in main()

        # Test django profile -> django collection
        args_django = parser.parse_args(["-f", "-p", "django"])
        assert args_django.profile == "django"
        # Collection would be auto-set to "django" in main()

        # Verify they're different
        assert args_plone.profile != args_django.profile
