"""Shared CLI utilities for the pyfa command."""

from dotenv import load_dotenv
from pyf.aggregator.logger import logger
from pyf.aggregator.profiles import ProfileManager

import json
import os
import sys

load_dotenv()

DEFAULT_PROFILE = os.getenv("DEFAULT_PROFILE")


def add_common_args(parser):
    """Add -t/--target and -p/--profile arguments shared by all subcommands."""
    parser.add_argument(
        "-t",
        "--target",
        help="Target Typesense collection name (auto-set from profile if not specified)",
        nargs="?",
        type=str,
    )
    parser.add_argument(
        "-p",
        "--profile",
        help="Profile name (overrides DEFAULT_PROFILE env var)",
        nargs="?",
        type=str,
    )


def add_limit_arg(parser):
    """Add -l/--limit argument for subcommands that support it."""
    parser.add_argument(
        "-l",
        "--limit",
        help="Limit number of packages to process (useful for testing)",
        nargs="?",
        type=int,
        default=0,
    )


def resolve_profile_and_target(args, require_target=True, validate_npm=False):
    """Resolve profile and target collection from CLI args and env vars.

    Replaces the duplicated 20-30 line profile resolution block in all modules.

    Args:
        args: Parsed argparse Namespace (must have .target and .profile)
        require_target: If True, exit with error when target can't be resolved
        validate_npm: If True, also validate npm config on the profile

    Returns:
        tuple: (effective_profile, profile_data, profile_manager)
        profile_data and profile_manager may be None if no profile is set.
    """
    effective_profile = args.profile or DEFAULT_PROFILE
    profile_source = "from CLI" if args.profile else "from DEFAULT_PROFILE"

    profile_data = None
    profile_manager = None

    if effective_profile:
        profile_manager = ProfileManager()
        profile_data = profile_manager.get_profile(effective_profile)

        if not profile_data:
            available_profiles = profile_manager.list_profiles()
            logger.error(
                f"Profile '{effective_profile}' not found. "
                f"Available profiles: {', '.join(available_profiles)}"
            )
            sys.exit(1)

        if not profile_manager.validate_profile(effective_profile):
            logger.error(f"Profile '{effective_profile}' is invalid")
            sys.exit(1)

        if validate_npm:
            npm_config = profile_manager.get_npm_config(effective_profile)
            if not npm_config:
                logger.error(
                    f"Profile '{effective_profile}' has no npm configuration. "
                    f"Add 'npm:' section with 'keywords:' and/or 'scopes:' to the profile."
                )
                sys.exit(1)
            if not profile_manager.validate_npm_profile(effective_profile):
                logger.error(
                    f"Profile '{effective_profile}' has invalid npm configuration"
                )
                sys.exit(1)

        # Auto-set target collection name from profile if not specified
        if not args.target:
            args.target = effective_profile
            logger.info(f"Auto-setting target collection from profile: {args.target}")

        logger.info(f"Using profile '{effective_profile}' ({profile_source})")

    if require_target and not args.target:
        logger.error(
            "Target collection name is required. "
            "Use -t <collection_name>, -p <profile_name>, or set DEFAULT_PROFILE env var"
        )
        sys.exit(1)

    return effective_profile, profile_data, profile_manager


def resolve_show_target(args):
    """Resolve target collection for --show mode (used by manage subcommand).

    Args:
        args: Parsed argparse Namespace (must have .target and .profile)

    Returns:
        str: The resolved target collection name, or exits with error.
    """
    target = args.target
    effective_profile = args.profile or DEFAULT_PROFILE
    if not target and effective_profile:
        profile_manager = ProfileManager()
        if profile_manager.get_profile(effective_profile):
            target = effective_profile
    if not target:
        logger.error(
            "Target collection name is required. Use -t <collection_name> or -p <profile>"
        )
        sys.exit(1)
    return target


def show_package(package_name, collection_name, all_versions=False):
    """Show indexed data for a package from Typesense."""
    from .db import TypesenceConnection

    conn = TypesenceConnection()

    if not conn.collection_exists(name=collection_name):
        logger.error(f"Collection '{collection_name}' does not exist.")
        sys.exit(1)

    # Search for exact package name, sorted by upload_timestamp descending (newest first)
    result = conn.client.collections[collection_name].documents.search(
        {
            "q": package_name,
            "query_by": "name",
            "filter_by": f"name:={package_name}",
            "sort_by": "upload_timestamp:desc",
            "per_page": 100,
        }
    )

    hits = result.get("hits", [])
    if not hits:
        logger.error(
            f"Package '{package_name}' not found in collection '{collection_name}'."
        )
        sys.exit(1)

    documents = [hit["document"] for hit in hits]

    if all_versions:
        print(json.dumps(documents, indent=2))
    else:
        print(json.dumps(documents[0], indent=2))
