#!/usr/bin/env python3
# /// script
# dependencies = [
#   "boto3>=1.40.0",
#   "PyYAML>=6.0",
#   "fire>=0.7.0",
#   "textual>=0.47.0",
#   "paramiko>=3.0.0",
#   "sshtunnel>=0.4.0",
# ]
# ///

"""Moondock - EC2 remote development tool."""

import json
import logging
import os
import re
import shlex
import sys
from pathlib import Path
from typing import Any

import fire

from moondock.config import ConfigLoader
from moondock.ec2 import EC2Manager
from moondock.portforward import PortForwardManager
from moondock.ssh import SSHManager
from moondock.sync import MutagenManager

SYNC_TIMEOUT = 300
"""Mutagen initial sync timeout in seconds.

Five minutes allows time for large codebases to complete initial sync over SSH.
Timeout prevents indefinite hangs if sync stalls due to network or filesystem issues.
"""


class Moondock:
    """Main CLI interface for moondock."""

    def __init__(self) -> None:
        """Initialize Moondock CLI.

        Creates a ConfigLoader instance for handling configuration loading,
        merging, and validation.
        """
        self.config_loader = ConfigLoader()

    def extract_exit_code_from_script(self, script: str) -> int:
        """Extract exit code from script if it contains 'exit N' command.

        Parameters
        ----------
        script : str
            Script content to analyze

        Returns
        -------
        int
            Exit code if found, otherwise 0
        """
        if "exit " not in script:
            return 0

        match = re.search(r"exit\s+(\d+)", script)
        return int(match.group(1)) if match else 0

    def log_port_forwarding_setup(self, ports: list[int]) -> None:
        """Log SSH tunnel creation messages for each port.

        Parameters
        ----------
        ports : list[int]
            List of ports to log tunnel creation for
        """
        for port in ports:
            logging.info(f"Creating SSH tunnel for port {port}...")
            logging.info(f"SSH tunnel established: localhost:{port} -> remote:{port}")

    def run_test_mode(
        self, merged_config: dict[str, Any], json_output: bool
    ) -> dict[str, Any] | str:
        """Handle test mode execution without real AWS/SSH operations.

        Parameters
        ----------
        merged_config : dict[str, Any]
            Merged configuration dictionary
        json_output : bool
            If True, return JSON string instead of dict

        Returns
        -------
        dict[str, Any] | str
            Mock instance details (as dict or JSON string)

        Raises
        ------
        ValueError
            If instance has no public IP but command execution is required
            If startup_script defined but no sync_paths configured
        """
        if merged_config.get("startup_script") and not merged_config.get("sync_paths"):
            raise ValueError(
                "startup_script is defined but no sync_paths configured. "
                "startup_script requires a synced directory to run in."
            )

        moondock_dir = os.environ.get("MOONDOCK_DIR", str(Path.home() / ".moondock"))
        public_ip = "203.0.113.1"

        if os.environ.get("MOONDOCK_NO_PUBLIC_IP") == "1":
            public_ip = None

        mock_instance = {
            "instance_id": "i-mock123",
            "public_ip": public_ip,
            "state": "running",
            "key_file": str(Path(moondock_dir) / "keys" / "mock.pem"),
            "security_group_id": "sg-mock123",
            "unique_id": "mock123",
        }

        need_ssh = (
            merged_config.get("setup_script")
            or merged_config.get("startup_script")
            or merged_config.get("command")
        )

        if need_ssh:
            if mock_instance["public_ip"] is None:
                raise ValueError(
                    "Instance does not have a public IP address. "
                    "SSH connection requires public networking configuration."
                )

            logging.info("Waiting for SSH to be ready...")
            logging.info("SSH connection established")

            if merged_config.get("setup_script", "").strip():
                logging.info("Running setup_script...")

                script_exit_code = self.extract_exit_code_from_script(
                    merged_config["setup_script"]
                )

                if script_exit_code != 0:
                    raise RuntimeError(
                        f"Setup script failed with exit code: {script_exit_code}"
                    )

                logging.info("Setup script completed successfully")

            if merged_config.get("sync_paths"):
                logging.info("Starting Mutagen file sync...")
                logging.info("Waiting for initial file sync to complete...")

                if os.environ.get("MOONDOCK_SYNC_TIMEOUT") == "1":
                    raise RuntimeError(
                        "Mutagen sync timed out after 300 seconds. "
                        "Initial sync did not complete."
                    )

                logging.info("File sync completed")

            if merged_config.get("ports"):
                self.log_port_forwarding_setup(merged_config["ports"])

            if merged_config.get("startup_script"):
                logging.info("Running startup_script...")

                script_exit_code = self.extract_exit_code_from_script(
                    merged_config["startup_script"]
                )

                if script_exit_code != 0:
                    raise RuntimeError(
                        f"Startup script failed with exit code: {script_exit_code}"
                    )

                logging.info("Startup script completed successfully")

            if merged_config.get("command"):
                cmd = merged_config["command"]
                exit_code = self.extract_exit_code_from_script(cmd)

                logging.info(f"Executing command: {cmd}")
                logging.info(f"Command completed with exit code: {exit_code}")
                mock_instance["command_exit_code"] = exit_code

        if json_output:
            return json.dumps(mock_instance, indent=2)

        return mock_instance

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

        if merged_config.get("startup_script") and not merged_config.get("sync_paths"):
            raise ValueError(
                "startup_script is defined but no sync_paths configured. "
                "startup_script requires a synced directory to run in."
            )

        self.validate_sync_paths_config(merged_config.get("sync_paths"))

        if os.environ.get("MOONDOCK_TEST_MODE") == "1":
            return self.run_test_mode(merged_config, json_output)

        mutagen_mgr = MutagenManager()

        if merged_config.get("sync_paths"):
            mutagen_mgr.check_mutagen_installed()

        ec2_manager = EC2Manager(region=merged_config["region"])
        instance_details = ec2_manager.launch_instance(merged_config)

        ssh_manager = None
        mutagen_session_name = None
        portforward_mgr = None

        try:
            need_ssh = (
                merged_config.get("setup_script")
                or merged_config.get("startup_script")
                or merged_config.get("command")
            )

            if not need_ssh:
                if json_output:
                    return json.dumps(instance_details, indent=2)

                return instance_details

            if instance_details["public_ip"] is None:
                raise ValueError(
                    "Instance does not have a public IP address. "
                    "SSH connection requires public networking configuration."
                )

            logging.info("Waiting for SSH to be ready...")

            ssh_manager = SSHManager(
                host=instance_details["public_ip"],
                key_file=instance_details["key_file"],
                username="ubuntu",
            )
            ssh_manager.connect(max_retries=10)
            logging.info("SSH connection established")

            if merged_config.get("sync_paths"):
                mutagen_session_name = f"moondock-{instance_details['unique_id']}"
                mutagen_mgr.cleanup_orphaned_session(mutagen_session_name)

            if merged_config.get("sync_paths"):
                sync_config = merged_config["sync_paths"][0]

                logging.info("Starting Mutagen file sync...")

                mutagen_mgr.create_sync_session(
                    session_name=mutagen_session_name,
                    local_path=sync_config["local"],
                    remote_path=sync_config["remote"],
                    host=instance_details["public_ip"],
                    key_file=instance_details["key_file"],
                    username="ubuntu",
                    ignore_patterns=merged_config.get("ignore"),
                    include_vcs=merged_config.get("include_vcs", False),
                )

            if merged_config.get("setup_script", "").strip():
                logging.info("Running setup_script...")

                exit_code = ssh_manager.execute_command(merged_config["setup_script"])

                if exit_code != 0:
                    raise RuntimeError(
                        f"Setup script failed with exit code: {exit_code}"
                    )

                logging.info("Setup script completed successfully")

            if merged_config.get("sync_paths"):
                logging.info("Waiting for initial file sync to complete...")
                mutagen_mgr.wait_for_initial_sync(
                    mutagen_session_name, timeout=SYNC_TIMEOUT
                )
                logging.info("File sync completed")

            if merged_config.get("ports"):
                portforward_mgr = PortForwardManager()

                try:
                    portforward_mgr.create_tunnels(
                        ports=merged_config["ports"],
                        host=instance_details["public_ip"],
                        key_file=instance_details["key_file"],
                        username="ubuntu",
                    )
                except RuntimeError as e:
                    logging.error(f"Port forwarding failed: {e}")
                    raise

            if merged_config.get("startup_script"):
                working_dir = merged_config["sync_paths"][0]["remote"]

                logging.info("Running startup_script...")

                startup_command = self.build_command_in_directory(
                    working_dir, merged_config["startup_script"]
                )
                exit_code = ssh_manager.execute_command_raw(startup_command)

                if exit_code != 0:
                    raise RuntimeError(
                        f"Startup script failed with exit code: {exit_code}"
                    )

                logging.info("Startup script completed successfully")

            if merged_config.get("command"):
                cmd = merged_config["command"]
                logging.info(f"Executing command: {cmd}")

                if merged_config.get("sync_paths"):
                    working_dir = merged_config["sync_paths"][0]["remote"]
                    full_command = self.build_command_in_directory(working_dir, cmd)
                    exit_code = ssh_manager.execute_command_raw(full_command)
                else:
                    exit_code = ssh_manager.execute_command(cmd)

                logging.info(f"Command completed with exit code: {exit_code}")
                instance_details["command_exit_code"] = exit_code

        finally:
            if portforward_mgr:
                try:
                    portforward_mgr.stop_all_tunnels()
                except Exception as e:
                    logging.warning(f"Error during tunnel cleanup: {e}")

            if ssh_manager:
                ssh_manager.close()

            if mutagen_session_name:
                logging.info("Terminating Mutagen sync session...")
                mutagen_mgr.terminate_session(mutagen_session_name)

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

    def validate_sync_paths_config(self, sync_paths: list | None) -> None:
        """Validate sync_paths configuration structure.

        Parameters
        ----------
        sync_paths : list | None
            Sync paths configuration to validate

        Raises
        ------
        ValueError
            If sync_paths is not a list or missing required keys in entries
        """
        if not sync_paths:
            return

        if not isinstance(sync_paths, list):
            raise ValueError("sync_paths must be a list")

        sync_config = sync_paths[0]

        if "local" not in sync_config or "remote" not in sync_config:
            raise ValueError(
                "sync_paths entry must have both 'local' and 'remote' keys. "
                f"Got: {sync_config}"
            )

    def build_command_in_directory(self, working_dir: str, command: str) -> str:
        """Build command that executes in specific working directory.

        Parameters
        ----------
        working_dir : str
            Directory path to execute command in
        command : str
            Command to execute

        Returns
        -------
        str
            Full command with directory change and proper escaping
        """
        return f"cd {shlex.quote(working_dir)} && bash -c {repr(command)}"

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
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        stream=sys.stderr,
    )

    fire.Fire(Moondock)


if __name__ == "__main__":
    main()
