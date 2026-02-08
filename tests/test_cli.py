"""
Tests for the unified pyfa CLI parser and cli_utils module.
"""

import argparse
import pytest
from unittest.mock import patch

from pyf.aggregator.cli import build_parser


class TestUnifiedCLIParser:
    """Test that the unified CLI parser routes correctly to subcommands."""

    def test_parser_has_all_subcommands(self):
        """Test that all 6 subcommands are registered."""
        parser = build_parser()
        # Verify each subcommand is recognized by the parser
        for cmd in ["pypi", "npm", "github", "downloads", "health"]:
            args = parser.parse_args([cmd])
            assert args.command == cmd
        # manage needs at least one flag to not trigger an action
        args = parser.parse_args(["manage", "-ls"])
        assert args.command == "manage"

    def test_pypi_subcommand_args(self):
        """Test pypi subcommand has expected arguments."""
        parser = build_parser()
        args = parser.parse_args(["pypi", "-f", "-p", "plone", "-t", "test"])
        assert args.command == "pypi"
        assert args.first is True
        assert args.profile == "plone"
        assert args.target == "test"

    def test_npm_subcommand_args(self):
        """Test npm subcommand has expected arguments."""
        parser = build_parser()
        args = parser.parse_args(["npm", "-f", "-p", "plone", "-l", "10"])
        assert args.command == "npm"
        assert args.first is True
        assert args.profile == "plone"
        assert args.limit == 10

    def test_manage_subcommand_args(self):
        """Test manage subcommand has expected arguments."""
        parser = build_parser()
        args = parser.parse_args(["manage", "-ls"])
        assert args.command == "manage"
        assert args.list_collections is True

    def test_github_subcommand_args(self):
        """Test github subcommand has expected arguments."""
        parser = build_parser()
        args = parser.parse_args(["github", "-p", "plone", "-n", "plone.api"])
        assert args.command == "github"
        assert args.profile == "plone"
        assert args.name == "plone.api"

    def test_downloads_subcommand_args(self):
        """Test downloads subcommand has expected arguments."""
        parser = build_parser()
        args = parser.parse_args(["downloads", "-p", "plone", "-l", "100"])
        assert args.command == "downloads"
        assert args.profile == "plone"
        assert args.limit == 100

    def test_health_subcommand_args(self):
        """Test health subcommand has expected arguments."""
        parser = build_parser()
        args = parser.parse_args(["health", "-p", "plone", "-l", "50"])
        assert args.command == "health"
        assert args.profile == "plone"
        assert args.limit == 50

    def test_no_subcommand_shows_help(self, capsys):
        """Test that no subcommand prints help without error."""
        from pyf.aggregator.cli import main

        with patch("sys.argv", ["pyfa"]):
            main()

        captured = capsys.readouterr()
        assert "pyfa" in captured.out or "usage" in captured.out.lower()


class TestCLIUtilsResolveProfileAndTarget:
    """Test cli_utils.resolve_profile_and_target function."""

    def test_resolves_profile_from_cli(self):
        """Test profile resolution from -p argument."""
        from pyf.aggregator.cli_utils import resolve_profile_and_target

        args = argparse.Namespace(target=None, profile="plone")

        effective_profile, profile_data, profile_manager = resolve_profile_and_target(
            args
        )

        assert effective_profile == "plone"
        assert profile_data is not None
        assert args.target == "plone"  # Auto-set from profile

    def test_resolves_profile_from_env(self, monkeypatch):
        """Test profile resolution from DEFAULT_PROFILE env var."""
        monkeypatch.setenv("DEFAULT_PROFILE", "django")

        import importlib
        import pyf.aggregator.cli_utils as cli_utils_module

        importlib.reload(cli_utils_module)

        args = argparse.Namespace(target=None, profile=None)

        effective_profile, profile_data, _ = (
            cli_utils_module.resolve_profile_and_target(args)
        )

        assert effective_profile == "django"
        assert profile_data is not None
        assert args.target == "django"

    def test_cli_profile_overrides_env(self, monkeypatch):
        """Test that -p overrides DEFAULT_PROFILE env var."""
        monkeypatch.setenv("DEFAULT_PROFILE", "plone")

        import importlib
        import pyf.aggregator.cli_utils as cli_utils_module

        importlib.reload(cli_utils_module)

        args = argparse.Namespace(target=None, profile="flask")

        effective_profile, profile_data, _ = (
            cli_utils_module.resolve_profile_and_target(args)
        )

        assert effective_profile == "flask"
        assert args.target == "flask"

    def test_exits_when_target_required_and_missing(self, monkeypatch):
        """Test sys.exit when target is required but not resolvable."""
        monkeypatch.delenv("DEFAULT_PROFILE", raising=False)

        import importlib
        import pyf.aggregator.cli_utils as cli_utils_module

        importlib.reload(cli_utils_module)
        cli_utils_module.DEFAULT_PROFILE = None

        args = argparse.Namespace(target=None, profile=None)

        with pytest.raises(SystemExit):
            cli_utils_module.resolve_profile_and_target(args, require_target=True)

    def test_no_exit_when_target_not_required(self, monkeypatch):
        """Test that no exit occurs when require_target=False and no target."""
        monkeypatch.delenv("DEFAULT_PROFILE", raising=False)

        import importlib
        import pyf.aggregator.cli_utils as cli_utils_module

        importlib.reload(cli_utils_module)
        cli_utils_module.DEFAULT_PROFILE = None

        args = argparse.Namespace(target=None, profile=None)

        effective_profile, profile_data, profile_manager = (
            cli_utils_module.resolve_profile_and_target(args, require_target=False)
        )

        assert effective_profile is None
        assert profile_data is None
        assert profile_manager is None

    def test_invalid_profile_exits(self):
        """Test sys.exit when profile doesn't exist."""
        from pyf.aggregator.cli_utils import resolve_profile_and_target

        args = argparse.Namespace(target=None, profile="nonexistent_profile_xyz")

        with pytest.raises(SystemExit):
            resolve_profile_and_target(args)


class TestCLIUtilsResolveShowTarget:
    """Test cli_utils.resolve_show_target function."""

    def test_resolves_from_target_arg(self):
        """Test target resolution from -t argument."""
        from pyf.aggregator.cli_utils import resolve_show_target

        args = argparse.Namespace(target="my-collection", profile=None)
        target = resolve_show_target(args)
        assert target == "my-collection"

    def test_resolves_from_profile(self):
        """Test target resolution from profile name."""
        from pyf.aggregator.cli_utils import resolve_show_target

        args = argparse.Namespace(target=None, profile="plone")
        target = resolve_show_target(args)
        assert target == "plone"

    def test_exits_when_no_target_or_profile(self, monkeypatch):
        """Test sys.exit when neither target nor profile is provided."""
        monkeypatch.delenv("DEFAULT_PROFILE", raising=False)

        import importlib
        import pyf.aggregator.cli_utils as cli_utils_module

        importlib.reload(cli_utils_module)
        cli_utils_module.DEFAULT_PROFILE = None

        args = argparse.Namespace(target=None, profile=None)

        with pytest.raises(SystemExit):
            cli_utils_module.resolve_show_target(args)


class TestManageShowArgs:
    """Test that --show and --all-versions are available on manage subcommand."""

    def test_manage_accepts_show_arg(self):
        """Test that manage subcommand accepts --show."""
        parser = build_parser()
        args = parser.parse_args(["manage", "--show", "plone.api", "-t", "plone"])
        assert args.command == "manage"
        assert args.show == "plone.api"

    def test_manage_accepts_all_versions_arg(self):
        """Test that manage subcommand accepts --all-versions."""
        parser = build_parser()
        args = parser.parse_args(
            ["manage", "--show", "plone.api", "--all-versions", "-t", "plone"]
        )
        assert args.command == "manage"
        assert args.show == "plone.api"
        assert args.all_versions is True

    def test_pypi_rejects_show_arg(self):
        """Test that pypi subcommand no longer accepts --show."""
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["pypi", "--show", "plone.api", "-t", "plone"])

    def test_npm_rejects_show_arg(self):
        """Test that npm subcommand no longer accepts --show."""
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["npm", "--show", "@plone/volto", "-t", "plone"])
