#!/usr/bin/env python3
# /// script
# dependencies = [
#   "boto3>=1.40.0",
#   "PyYAML>=6.0",
#   "fire>=0.7.0",
#   "textual>=0.47.0",
# ]
# ///

"""Moondock - EC2 remote development tool."""

import json
import os
from pathlib import Path
from typing import Any

import fire

from moondock.config import ConfigLoader
from moondock.ec2 import EC2Manager


class Moondock:
    """Main CLI interface for moondock."""

    def __init__(self) -> None:
        """Initialize Moondock CLI.

        Creates a ConfigLoader instance for handling configuration loading,
        merging, and validation.
        """
        self.config_loader = ConfigLoader()

    def run(
        self,
        machine_name: str | None = None,
        command: str | None = None,
        instance_type: str | None = None,
        disk_size: int | None = None,
        region: str | None = None,
        port: str | list[int] | tuple[int, ...] | None = None,
        include_vcs: str | bool | None = None,
        ignore: str | None = None,
        json_output: bool = False,
    ) -> dict[str, Any] | str:
        """Launch EC2 instance with file sync and command execution.

        Parameters
        ----------
        machine_name : str | None
            Named machine configuration from YAML, or None to use defaults
        command : str | None
            Command to execute on remote instance (overrides config)
        instance_type : str | None
            EC2 instance type (overrides config)
        disk_size : int | None
            Root disk size in GB (overrides config)
        region : str | None
            AWS region (overrides config)
        port : str | list[int] | tuple[int, ...] | None
            Local port(s) for forwarding - can be single port, comma-separated string,
            list of integers, or tuple of integers (overrides config)
        include_vcs : str | bool | None
            Include VCS files: "true"/"false" strings or True/False booleans (overrides config)
        ignore : str | None
            Comma-separated file patterns to exclude (overrides config)
        json_output : bool
            If True, return JSON string instead of dict (default: False)

        Returns
        -------
        dict[str, Any] | str
            Instance details with fields: instance_id, public_ip, state, key_file,
            security_group_id, unique_id (as dict for testing or JSON string for CLI)

        Raises
        ------
        ValueError
            If include_vcs is not "true" or "false", or if machine name is invalid
        """
        config = self.config_loader.load_config()

        merged_config = self.config_loader.get_machine_config(config, machine_name)

        self.apply_cli_overrides(
            merged_config,
            command,
            instance_type,
            disk_size,
            region,
            port,
            include_vcs,
            ignore,
        )

        self.config_loader.validate_config(merged_config)

        if machine_name is not None:
            merged_config["machine_name"] = machine_name

        if os.environ.get("MOONDOCK_TEST_MODE") == "1":
            mock_instance = {
                "instance_id": "i-mock123",
                "public_ip": "203.0.113.1",
                "state": "running",
                "key_file": str(Path.home() / ".moondock" / "keys" / "mock.pem"),
                "security_group_id": "sg-mock123",
                "unique_id": "mock123",
            }

            if json_output:
                return json.dumps(mock_instance, indent=2)

            return mock_instance

        ec2_manager = EC2Manager(region=merged_config["region"])
        instance_details = ec2_manager.launch_instance(merged_config)

        # TODO (next spec): Setup Mutagen file sync
        # TODO (next spec): Setup port forwarding
        # TODO (next spec): Execute setup_script if defined
        # TODO (next spec): Execute startup_script if defined
        # TODO (next spec): Execute command if defined
        # TODO (next spec): Add automatic cleanup on Ctrl+C

        if json_output:
            return json.dumps(instance_details, indent=2)

        return instance_details

    def apply_cli_overrides(
        self,
        config: dict[str, Any],
        command: str | None,
        instance_type: str | None,
        disk_size: int | None,
        region: str | None,
        port: str | list[int] | tuple[int, ...] | None,
        include_vcs: str | bool | None,
        ignore: str | None,
    ) -> None:
        """Apply CLI option overrides to merged configuration.

        Parameters
        ----------
        config : dict[str, Any]
            Configuration dictionary to modify in-place
        command : str | None
            Command to execute on remote instance
        instance_type : str | None
            EC2 instance type
        disk_size : int | None
            Root disk size in GB
        region : str | None
            AWS region
        port : str | list[int] | tuple[int, ...] | None
            Local port(s) for forwarding
        include_vcs : str | bool | None
            Include VCS files
        ignore : str | None
            Comma-separated file patterns to exclude
        """

        if command is not None:
            config["command"] = command

        if instance_type is not None:
            config["instance_type"] = instance_type

        if disk_size is not None:
            config["disk_size"] = disk_size

        if region is not None:
            config["region"] = region

        if port is not None:
            config["ports"] = self.parse_port_parameter(port)
            config.pop("port", None)

        if include_vcs is not None:
            config["include_vcs"] = self.parse_include_vcs(include_vcs)

        if ignore is not None:
            config["ignore"] = self.parse_ignore_patterns(ignore)

    def parse_port_parameter(
        self, port: str | list[int] | tuple[int, ...]
    ) -> list[int]:
        """Parse port parameter into list of integers.

        Parameters
        ----------
        port : str | list[int] | tuple[int, ...]
            Port specification - can be single value, comma-separated string, list, or tuple

        Returns
        -------
        list[int]
            List of port numbers as integers
        """

        if isinstance(port, (tuple, list)):
            return [int(p) for p in port]

        return [int(p.strip()) for p in str(port).split(",") if p.strip()]

    def parse_include_vcs(self, include_vcs: str | bool) -> bool:
        """Parse include_vcs parameter into boolean.

        Parameters
        ----------
        include_vcs : str | bool
            VCS inclusion flag - can be boolean or "true"/"false" string

        Returns
        -------
        bool
            Boolean value for VCS inclusion

        Raises
        ------
        ValueError
            If string value is not "true" or "false"
        """

        if isinstance(include_vcs, bool):
            return include_vcs

        if isinstance(include_vcs, str):
            vcs_lower = include_vcs.lower()

            if vcs_lower not in ("true", "false"):
                raise ValueError(
                    f"include_vcs must be 'true' or 'false', got: {include_vcs}"
                )

            return vcs_lower == "true"

        raise ValueError(f"Unexpected type for include_vcs: {type(include_vcs)}")

    def parse_ignore_patterns(self, ignore: str) -> list[str]:
        """Parse comma-separated ignore patterns into list.

        Parameters
        ----------
        ignore : str
            Comma-separated file patterns to exclude

        Returns
        -------
        list[str]
            List of ignore patterns
        """
        return [pattern.strip() for pattern in ignore.split(",") if pattern.strip()]

    def hello(self) -> str:
        """Test command to validate Fire CLI works.

        Returns
        -------
        str
            Version and status message confirming skeleton is ready.
        """
        return "moondock v0.1.0 - skeleton ready"


def main() -> None:
    """Entry point for Fire CLI.

    This function initializes the Fire CLI interface by passing the Moondock
    class to Fire, which automatically generates CLI commands from the class
    methods. The function should be called when the script is executed directly.

    Notes
    -----
    Fire automatically maps class methods to CLI commands and handles argument
    parsing, help text generation, and command routing.
    """
    fire.Fire(Moondock)


if __name__ == "__main__":
    main()
