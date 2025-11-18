import copy
import os
import re
from pathlib import Path
from typing import Any

from omegaconf import OmegaConf


class ConfigLoader:
    """Load and merge YAML configuration with defaults."""

    BUILT_IN_DEFAULTS = {
        "region": "us-east-1",
        "instance_type": "t3.medium",
        "disk_size": 50,
        "os_flavor": "ubuntu-22.04",
        "ports": [],
        "include_vcs": False,
        "ignore": ["*.pyc", "__pycache__", "*.log", ".DS_Store"],
        "env_filter": ["AWS_.*"],
        "sync_paths": [],
    }

    def load_config(self, config_path: str | None = None) -> dict[str, Any]:
        """Load configuration from YAML file.

        Parameters
        ----------
        config_path : str | None
            Path to YAML config file. If None, checks MOONDOCK_CONFIG env var,
            then falls back to moondock.yaml

        Returns
        -------
        dict[str, Any]
            Parsed configuration with defaults and machines sections,
            with all variable interpolations resolved

        Raises
        ------
        omegaconf.errors.InterpolationResolutionError
            If undefined variables are referenced or circular references exist
        """
        if config_path is None:
            config_path = os.environ.get("MOONDOCK_CONFIG", "moondock.yaml")

        config_file = Path(config_path)

        if not config_file.exists():
            return {"defaults": {}}

        cfg = OmegaConf.load(config_file)

        if cfg is None:
            return {"defaults": {}}

        if "vars" in cfg:
            vars_dict = OmegaConf.to_container(cfg.vars, resolve=False)
            for key, value in vars_dict.items():
                if key not in cfg:
                    cfg[key] = value

        config = OmegaConf.to_container(cfg, resolve=True, throw_on_missing=True)

        return config

    def get_machine_config(
        self, config: dict[str, Any], machine_name: str | None = None
    ) -> dict[str, Any]:
        """Get merged configuration for a specific machine or defaults.

        Parameters
        ----------
        config : dict[str, Any]
            Full configuration from YAML
        machine_name : str | None
            Name of machine configuration to use, or None for defaults only

        Returns
        -------
        dict[str, Any]
            Merged configuration (built-in defaults + YAML defaults + machine settings)
        """
        merged = copy.deepcopy(self.BUILT_IN_DEFAULTS)

        yaml_defaults = config.get("defaults", {})
        for key, value in yaml_defaults.items():
            merged[key] = value

        if machine_name is not None:
            machines = config.get("machines", {})

            if machine_name not in machines:
                available = list(machines.keys())

                if not available:
                    raise ValueError(
                        f"Machine '{machine_name}' not found in configuration. "
                        f"No machines are defined in the config file."
                    )

                raise ValueError(
                    f"Machine '{machine_name}' not found in configuration. "
                    f"Available machines: {available}"
                )

            machine_config = machines[machine_name]
            for key, value in machine_config.items():
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

        optional_validations = {
            "os_flavor": (str, "os_flavor must be a string"),
            "include_vcs": (bool, "include_vcs must be a boolean"),
            "ignore": (list, "ignore must be a list"),
            "env_filter": (list, "env_filter must be a list"),
            "command": (str, "command must be a string"),
            "setup_script": (str, "setup_script must be a string"),
            "startup_script": (str, "startup_script must be a string"),
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
                    )

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

        if "sync_paths" in config:
            if not isinstance(config["sync_paths"], list):
                raise ValueError("sync_paths must be a list")

            for sync_path in config["sync_paths"]:
                if not isinstance(sync_path, dict):
                    raise ValueError("sync_paths entries must be dictionaries")

                if "local" not in sync_path or "remote" not in sync_path:
                    raise ValueError(
                        "sync_paths entry must have both 'local' and 'remote' keys"
                    )
