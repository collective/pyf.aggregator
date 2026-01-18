from pathlib import Path
from pyf.aggregator.logger import logger

import yaml


class ProfileManager:
    """Manages loading and validation of profile configurations.

    Profiles define framework ecosystems to track via PyPI trove classifiers.
    Each profile specifies a name and list of classifiers to filter packages.
    """

    def __init__(self, config_path=None):
        """Initialize ProfileManager.

        Args:
            config_path: Optional path to profiles.yaml. If not provided,
                        uses default path relative to this module.
        """
        if config_path is None:
            # Default to profiles.yaml in same directory as this module
            module_dir = Path(__file__).parent
            config_path = module_dir / "profiles.yaml"

        self.config_path = Path(config_path)
        self._profiles = None
        self._load_profiles()

    def _load_profiles(self):
        """Load profiles from YAML configuration file.

        Raises:
            FileNotFoundError: If config file doesn't exist
            ValueError: If YAML is invalid or missing required structure
        """
        if not self.config_path.exists():
            raise FileNotFoundError(
                f"Profile configuration not found: {self.config_path}"
            )

        try:
            with open(self.config_path, "r") as f:
                config = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in {self.config_path}: {e}")

        if not config or "profiles" not in config:
            raise ValueError(
                f"Invalid profile configuration: missing 'profiles' key in {self.config_path}"
            )

        self._profiles = config["profiles"]
        logger.info(
            f"Loaded {len(self._profiles)} profiles from {self.config_path}"
        )

    def get_profile(self, name):
        """Get profile configuration by name.

        Args:
            name: Profile identifier (e.g., 'plone', 'django', 'flask')

        Returns:
            dict: Profile configuration with 'name' and 'classifiers' keys,
                  or None if profile not found
        """
        if name not in self._profiles:
            logger.warning(f"Profile '{name}' not found in configuration")
            return None

        return self._profiles[name]

    def list_profiles(self):
        """List all available profile names.

        Returns:
            list: Sorted list of profile identifiers
        """
        return sorted(self._profiles.keys())

    def validate_profile(self, name):
        """Validate that a profile exists and has required structure.

        Args:
            name: Profile identifier to validate

        Returns:
            bool: True if profile exists and is valid, False otherwise
        """
        profile = self.get_profile(name)
        if not profile:
            return False

        # Check required fields
        if "name" not in profile:
            logger.error(f"Profile '{name}' missing 'name' field")
            return False

        if "classifiers" not in profile:
            logger.error(f"Profile '{name}' missing 'classifiers' field")
            return False

        if not isinstance(profile["classifiers"], list):
            logger.error(f"Profile '{name}' classifiers must be a list")
            return False

        if len(profile["classifiers"]) == 0:
            logger.error(f"Profile '{name}' has empty classifiers list")
            return False

        return True
