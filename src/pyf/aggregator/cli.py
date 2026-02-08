"""Unified CLI entry point for pyfa (Python Package Filter Aggregator).

Provides subcommands:
    pyfa pypi       - Aggregate PyPI packages
    pyfa npm        - Aggregate npm packages
    pyfa manage     - Manage Typesense collections, aliases, API keys
    pyfa github     - Enrich packages with GitHub data
    pyfa downloads  - Enrich packages with download statistics
    pyfa health     - Calculate health scores
"""

from argparse import ArgumentParser


def build_parser():
    """Build the unified CLI parser with all subcommands."""
    parser = ArgumentParser(
        prog="pyfa",
        description="Python Package Filter Aggregator - unified CLI for package aggregation and enrichment",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # pyfa pypi
    pypi_parser = subparsers.add_parser(
        "pypi",
        help="Aggregate PyPI packages into Typesense",
    )
    from pyf.aggregator.main import add_subcommand_args as pypi_args

    pypi_args(pypi_parser)

    # pyfa npm
    npm_parser = subparsers.add_parser(
        "npm",
        help="Aggregate npm packages into Typesense",
    )
    from pyf.aggregator.npm_main import add_subcommand_args as npm_args

    npm_args(npm_parser)

    # pyfa manage
    manage_parser = subparsers.add_parser(
        "manage",
        help="Manage Typesense collections, aliases, API keys, and queue",
    )
    from pyf.aggregator.typesense_util import add_subcommand_args as manage_args

    manage_args(manage_parser)

    # pyfa github
    github_parser = subparsers.add_parser(
        "github",
        help="Enrich packages with GitHub data (stars, watchers, issues, contributors)",
    )
    from pyf.aggregator.enrichers.github import add_subcommand_args as github_args

    github_args(github_parser)

    # pyfa downloads
    downloads_parser = subparsers.add_parser(
        "downloads",
        help="Enrich packages with download statistics from pypistats.org",
    )
    from pyf.aggregator.enrichers.downloads import (
        add_subcommand_args as downloads_args,
    )

    downloads_args(downloads_parser)

    # pyfa health
    health_parser = subparsers.add_parser(
        "health",
        help="Calculate comprehensive health scores for packages",
    )
    from pyf.aggregator.enrichers.health_calculator import (
        add_subcommand_args as health_args,
    )

    health_args(health_parser)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    if args.command == "pypi":
        from pyf.aggregator.main import run_command

        run_command(args)
    elif args.command == "npm":
        from pyf.aggregator.npm_main import run_command

        run_command(args)
    elif args.command == "manage":
        from pyf.aggregator.typesense_util import run_command

        run_command(args)
    elif args.command == "github":
        from pyf.aggregator.enrichers.github import run_command

        run_command(args)
    elif args.command == "downloads":
        from pyf.aggregator.enrichers.downloads import run_command

        run_command(args)
    elif args.command == "health":
        from pyf.aggregator.enrichers.health_calculator import run_command

        run_command(args)


if __name__ == "__main__":
    main()
