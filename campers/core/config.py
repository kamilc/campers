import copy
import logging
import os
import re
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from omegaconf import OmegaConf
from omegaconf.errors import InterpolationResolutionError

from campers.constants import DEFAULT_DISK_SIZE, DEFAULT_PROVIDER
from campers.providers import get_default_region, get_provider_defaults, list_providers

logger = logging.getLogger(__name__)


class ConfigLoader:
    """Load and merge YAML configuration with defaults."""

    SSH_USERNAME_PATTERN = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")

    def __init__(self) -> None:
        """Initialize ConfigLoader with provider-specific defaults."""
        provider_defaults = get_provider_defaults(DEFAULT_PROVIDER)
        self.BUILT_IN_DEFAULTS = {
            "provider": DEFAULT_PROVIDER,
            "region": get_default_region(DEFAULT_PROVIDER),
            "instance_type": provider_defaults["instance_type"],
            "disk_size": DEFAULT_DISK_SIZE,
            "ports": [],
            "public_ports": [],
            "public_ports_allowed_cidr": None,
            "include_vcs": False,
            "ignore": ["*.pyc", "__pycache__", "*.log", ".DS_Store"],
            "env_filter": provider_defaults["env_filter"],
            "sync_paths": [],
            "ssh_username": provider_defaults["ssh_username"],
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

        Notes
        -----
        Automatically loads .env file from the config file's directory if present.
        Environment variables from .env are available via ${oc.env:VAR_NAME} syntax.
        """
        if config_path is None:
            config_path = os.environ.get("CAMPERS_CONFIG", "campers.yaml")

        config_file = Path(config_path)
        config_dir = config_file.parent if config_file.parent != Path() else Path.cwd()
        dotenv_path = config_dir / ".env"
        load_dotenv(dotenv_path, override=False)

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
        self._validate_public_ports(config)
        self._validate_sync_paths(config)
        self._validate_ansible_config(config)

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
            if not self.SSH_USERNAME_PATTERN.match(ssh_username):
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

        Notes
        -----
        Ports can be specified as:
        - Integer: same port for remote and local (e.g., 8888)
        - String with colon: remote:local mapping (e.g., "6006:6007")
        """
        if "port" in config and "ports" in config:
            raise ValueError("cannot specify both port and ports")

        if "port" in config:
            if not isinstance(config["port"], int):
                raise ValueError("port must be an integer")

            self._validate_single_port_entry(config["port"], is_port_singular=True)

        if "ports" in config:
            if not isinstance(config["ports"], list):
                raise ValueError("ports must be a list")

            for port in config["ports"]:
                self._validate_single_port_entry(port, is_port_singular=False)

    def _validate_single_port_entry(
        self, port: int | str | tuple[int, int], is_port_singular: bool = True
    ) -> None:
        """Validate a single port entry from configuration.

        Parameters
        ----------
        port : int | str | tuple[int, int]
            Port specification - can be integer, string (e.g., "8888" or "6006:6007"),
            or tuple of two integers
        is_port_singular : bool, optional
            True if validating singular "port" field, False for "ports" list, by default True

        Raises
        ------
        ValueError
            If port is invalid
        """
        if isinstance(port, str):
            if is_port_singular:
                raise ValueError("port must be an integer, got string")
            if ":" in port:
                parts = port.split(":")
                if len(parts) != 2:
                    raise ValueError(
                        f"Invalid port mapping: {port}. Expected format 'remote:local'"
                    )
                try:
                    remote, local = int(parts[0]), int(parts[1])
                    for p in (remote, local):
                        if not (1 <= p <= 65535):
                            raise ValueError("ports entries must be between 1 and 65535")
                except ValueError as e:
                    if "invalid literal" in str(e):
                        raise ValueError(
                            f"Invalid port mapping: {port}. Both ports must be integers"
                        ) from None
                    raise
            else:
                try:
                    p = int(port)
                    if not (1 <= p <= 65535):
                        raise ValueError("ports entries must be between 1 and 65535")
                except ValueError as e:
                    if "invalid literal" in str(e):
                        raise ValueError(
                            f"Invalid port: {port}. Must be an integer or 'remote:local' format"
                        ) from None
                    raise
            return

        if isinstance(port, tuple):
            if not is_port_singular:
                if len(port) != 2:
                    raise ValueError(
                        f"Invalid port mapping: {port}. "
                        f"Expected tuple of two integers (remote, local)"
                    )

                for port_val in port:
                    if not isinstance(port_val, int):
                        raise ValueError(
                            f"Invalid port mapping: {port}. Both ports must be integers"
                        )

                    if not (1 <= port_val <= 65535):
                        raise ValueError("ports entries must be between 1 and 65535")
                return
            else:
                raise ValueError("port must be an integer, got tuple")

        if isinstance(port, int):
            if not (1 <= port <= 65535):
                port_prefix = "ports entries" if not is_port_singular else "port"
                raise ValueError(f"{port_prefix} must be between 1 and 65535")
            return

        port_type = "port" if is_port_singular else "ports entries"
        raise ValueError(f"{port_type} must be integers")

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

    def _validate_public_ports(self, config: dict[str, Any]) -> None:
        """Validate public_ports configuration.

        Parameters
        ----------
        config : dict[str, Any]
            Configuration to validate

        Raises
        ------
        ValueError
            If public_ports configuration is invalid
        """
        from campers.cli.parsing import validate_port_range

        if "public_ports" not in config:
            return

        public_ports = config["public_ports"]
        if not isinstance(public_ports, list):
            raise ValueError("public_ports must be a list")

        for port in public_ports:
            if not isinstance(port, int):
                msg = f"public_ports entries must be integers, got {type(port).__name__}"
                raise ValueError(msg)
            validate_port_range(port)

        if "public_ports_allowed_cidr" in config:
            cidr = config["public_ports_allowed_cidr"]
            if cidr is not None and not isinstance(cidr, str):
                raise ValueError("public_ports_allowed_cidr must be a string or null")
