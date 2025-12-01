import copy
import logging
import os
import re
from pathlib import Path
from typing import Any

import yaml
from omegaconf import OmegaConf
from omegaconf.errors import InterpolationResolutionError

from campers.constants import DEFAULT_PROVIDER, OnExitAction
from campers.providers import get_default_region, list_providers

logger = logging.getLogger(__name__)


class ConfigLoader:
    """Load and merge YAML configuration with defaults."""

    def __init__(self) -> None:
        """Initialize ConfigLoader with provider-specific defaults."""
        self.BUILT_IN_DEFAULTS = {
            "provider": DEFAULT_PROVIDER,
            "region": get_default_region(DEFAULT_PROVIDER),
            "instance_type": "t3.medium",
            "disk_size": 50,
            "ports": [],
            "include_vcs": False,
            "ignore": ["*.pyc", "__pycache__", "*.log", ".DS_Store"],
            "env_filter": ["AWS_.*"],
            "sync_paths": [],
            "ssh_username": "ubuntu",
            "on_exit": OnExitAction.STOP.value,
            "ssh_allowed_cidr": None,
        }

    def load_config(self, config_path: str | None = None) -> dict[str, Any]:
        """Load configuration from YAML file.

        Parameters
        ----------
        config_path : str | None
            Path to YAML config file. If None, checks CAMPERS_CONFIG env var,
            then falls back to campers.yaml

        Returns
        -------
        dict[str, Any]
            Parsed configuration with defaults and camps sections,
            with all variable interpolations resolved

        Raises
        ------
        omegaconf.errors.InterpolationResolutionError
            If undefined variables are referenced or circular references exist
        """
        if config_path is None:
            config_path = os.environ.get("CAMPERS_CONFIG", "campers.yaml")

        config_file = Path(config_path)

        if not config_file.exists():
            return {"defaults": {}}

        try:
            cfg = OmegaConf.load(config_file)
        except yaml.YAMLError as e:
            logger.error("Failed to parse YAML config file %s: %s", config_file, e)
            raise ValueError(f"Invalid YAML in {config_file}: {e}") from e
        except OSError as e:
            logger.error("Failed to read config file %s: %s", config_file, e)
            raise RuntimeError(f"Failed to read config file {config_file}: {e}") from e

        if cfg is None:
            return {"defaults": {}}

        if "vars" in cfg:
            vars_dict = OmegaConf.to_container(cfg.vars, resolve=False)
            for key, value in vars_dict.items():
                if key not in cfg:
                    cfg[key] = value

        try:
            config = OmegaConf.to_container(cfg, resolve=True, throw_on_missing=True)
        except InterpolationResolutionError as e:
            logger.error("Failed to resolve configuration variables: %s", e)
            raise
        except (ValueError, KeyError, AttributeError) as e:
            logger.error("Failed to resolve configuration variables: %s", e)
            raise ValueError(f"Configuration variable resolution error: {e}") from e

        return config

    def get_camp_config(
        self, config: dict[str, Any], camp_name: str | None = None
    ) -> dict[str, Any]:
        """Get merged configuration for a specific camp or defaults.

        Parameters
        ----------
        config : dict[str, Any]
            Full configuration from YAML
        camp_name : str | None
            Name of camp configuration to use, or None for defaults only

        Returns
        -------
        dict[str, Any]
            Merged configuration (built-in defaults + YAML defaults + camp settings)
        """
        merged = copy.deepcopy(self.BUILT_IN_DEFAULTS)

        yaml_defaults = config.get("defaults", {})
        for key, value in yaml_defaults.items():
            merged[key] = value

        if camp_name is not None:
            camps = config.get("camps", {})

            if camp_name not in camps:
                available = list(camps.keys())

                if not available:
                    raise ValueError(
                        f"Camp '{camp_name}' not found in configuration. "
                        f"No camps are defined in the config file."
                    )

                raise ValueError(
                    f"Camp '{camp_name}' not found in configuration. Available camps: {available}"
                )

            camp_config = camps[camp_name]
            for key, value in camp_config.items():
                merged[key] = value

        return merged

    def validate_config(self, config: dict[str, Any]) -> None:
        """Validate configuration has required fields and correct types.

        Parameters
        ----------
        config : dict[str, Any]
            Configuration to validate

        Raises
        ------
        ValueError
            If configuration is invalid
        """
        provider = config.get("provider", "aws")
        available_providers = list_providers()
        if provider not in available_providers:
            raise ValueError(
                f"Unknown provider: {provider}. Available providers: {available_providers}"
            )

        self._validate_required_fields(config)
        self._validate_optional_fields(config)
        self._validate_ports(config)
        self._validate_sync_paths(config)
        self._validate_ansible_config(config)
        self._validate_on_exit(config)

    def _validate_required_fields(self, config: dict[str, Any]) -> None:
        """Validate required configuration fields.

        Parameters
        ----------
        config : dict[str, Any]
            Configuration to validate

        Raises
        ------
        ValueError
            If required fields are missing or invalid
        """
        required_validations = {
            "region": (str, "region is required", "region must be a string"),
            "instance_type": (
                str,
                "instance_type is required",
                "instance_type must be a string",
            ),
            "disk_size": (
                int,
                "disk_size is required",
                "disk_size must be an integer",
            ),
        }

        for field, (
            expected_type,
            required_msg,
            type_msg,
        ) in required_validations.items():
            if field not in config or config[field] == "":
                raise ValueError(required_msg)

            if not isinstance(config[field], expected_type):
                raise ValueError(type_msg)

    def _validate_optional_fields(self, config: dict[str, Any]) -> None:
        """Validate optional configuration fields.

        Parameters
        ----------
        config : dict[str, Any]
            Configuration to validate

        Raises
        ------
        ValueError
            If optional fields are invalid
        """
        optional_validations = {
            "include_vcs": (bool, "include_vcs must be a boolean"),
            "ignore": (list, "ignore must be a list"),
            "env_filter": (list, "env_filter must be a list"),
            "command": (str, "command must be a string"),
            "setup_script": (str, "setup_script must be a string"),
            "startup_script": (str, "startup_script must be a string"),
            "ssh_username": (str, "ssh_username must be a string"),
            "ansible_playbook": (str, "ansible_playbook must be a string"),
        }

        for field, (expected_type, type_msg) in optional_validations.items():
            if field in config and not isinstance(config[field], expected_type):
                raise ValueError(type_msg)

        if "ignore" in config and isinstance(config["ignore"], list):
            for item in config["ignore"]:
                if not isinstance(item, str):
                    raise ValueError("ignore entries must be strings")

        if "env_filter" in config and isinstance(config["env_filter"], list):
            for item in config["env_filter"]:
                if not isinstance(item, str):
                    raise ValueError("env_filter entries must be strings")

            for pattern in config["env_filter"]:
                try:
                    re.compile(pattern)
                except re.error as e:
                    raise ValueError(
                        f"Invalid regex pattern in env_filter: '{pattern}' - {e}"
                    ) from e

        if "ssh_username" in config:
            ssh_username = config["ssh_username"]
            pattern: str = r"^[a-z_][a-z0-9_-]{0,31}$"
            if not re.match(pattern, ssh_username):
                raise ValueError(
                    f"Invalid ssh_username '{ssh_username}'. "
                    f"Must start with lowercase letter or underscore, "
                    f"contain only lowercase letters, numbers, underscores, "
                    f"and hyphens, and be 1-32 characters long."
                )

    def _validate_ports(self, config: dict[str, Any]) -> None:
        """Validate port configuration.

        Parameters
        ----------
        config : dict[str, Any]
            Configuration to validate

        Raises
        ------
        ValueError
            If port configuration is invalid
        """
        if "port" in config and "ports" in config:
            raise ValueError("cannot specify both port and ports")

        if "port" in config:
            if not isinstance(config["port"], int):
                raise ValueError("port must be an integer")

            if not (1 <= config["port"] <= 65535):
                raise ValueError("port must be between 1 and 65535")

        if "ports" in config:
            if not isinstance(config["ports"], list):
                raise ValueError("ports must be a list")

            for port in config["ports"]:
                if not isinstance(port, int):
                    raise ValueError("ports entries must be integers")

                if not (1 <= port <= 65535):
                    raise ValueError("ports entries must be between 1 and 65535")

    def _validate_sync_paths(self, config: dict[str, Any]) -> None:
        """Validate sync_paths configuration.

        Parameters
        ----------
        config : dict[str, Any]
            Configuration to validate

        Raises
        ------
        ValueError
            If sync_paths configuration is invalid
        """
        if "sync_paths" not in config:
            return

        if not isinstance(config["sync_paths"], list):
            raise ValueError("sync_paths must be a list")

        for sync_path in config["sync_paths"]:
            if not isinstance(sync_path, dict):
                raise ValueError("sync_paths entries must be dictionaries")

            if "local" not in sync_path or "remote" not in sync_path:
                raise ValueError("sync_paths entry must have both 'local' and 'remote' keys")

    def _validate_ansible_config(self, config: dict[str, Any]) -> None:
        """Validate Ansible configuration.

        Parameters
        ----------
        config : dict[str, Any]
            Configuration to validate

        Raises
        ------
        ValueError
            If Ansible configuration is invalid
        """
        if "ansible_playbook" in config and "ansible_playbooks" in config:
            raise ValueError(
                "Cannot specify both 'ansible_playbook' and 'ansible_playbooks'. "
                "These fields are mutually exclusive."
            )

        if "ansible_playbooks" in config and not isinstance(config["ansible_playbooks"], list):
            raise ValueError("ansible_playbooks must be a list")

        if "playbooks" not in config:
            return

        if not isinstance(config["playbooks"], dict):
            raise ValueError("playbooks must be a dictionary")

        for playbook_name, playbook_content in config["playbooks"].items():
            if not isinstance(playbook_name, str):
                raise ValueError("playbook names must be strings")

            if not isinstance(playbook_content, list):
                raise ValueError(
                    f"playbook '{playbook_name}' content must be a list of tasks, "
                    f"got {type(playbook_content).__name__}"
                )

    def _validate_on_exit(self, config: dict[str, Any]) -> None:
        """Validate on_exit configuration.

        Parameters
        ----------
        config : dict[str, Any]
            Configuration to validate

        Raises
        ------
        ValueError
            If on_exit configuration is invalid
        """
        if "on_exit" not in config:
            return

        if not isinstance(config["on_exit"], str):
            raise ValueError("on_exit must be a string")

        if config["on_exit"] not in ("stop", "terminate"):
            raise ValueError(f"on_exit must be 'stop' or 'terminate', got '{config['on_exit']}'")
