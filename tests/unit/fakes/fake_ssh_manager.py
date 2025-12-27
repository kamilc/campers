"""Fake SSHManager for testing with dependency injection."""

import logging
import os
import re

logger = logging.getLogger(__name__)


class FakeSSHManager:
    """Fake SSHManager that simulates SSH operations for testing.

    This fake implementation matches the SSHManager interface and is designed
    to be injected via dependency injection for fast test execution without
    actual SSH connections.

    Parameters
    ----------
    host : str
        Remote host (ignored for fake)
    key_file : str
        SSH key file path (ignored for fake)
    username : str
        SSH username (default: ubuntu, ignored for fake)
    port : int
        SSH port (default: 22, ignored for fake)
    """

    def __init__(
        self,
        host: str,
        key_file: str,
        username: str = "ubuntu",
        port: int = 22,
    ) -> None:
        """Initialize FakeSSHManager.

        Parameters
        ----------
        host : str
            Remote host IP or hostname
        key_file : str
            Path to SSH private key file
        username : str
            SSH username (default: ubuntu)
        port : int
            SSH port (default: 22)
        """
        self.host = host
        self.key_file = key_file
        self.username = username
        self.port = port
        self.client = None
        self.connected = False

    def connect(self, max_retries: int = 10) -> None:
        """Fake SSH connection (always succeeds).

        Parameters
        ----------
        max_retries : int
            Maximum number of connection attempts (ignored for fake)
        """
        logger.info(
            "Fake SSH connection to %s@%s:%s (fake connection succeeds immediately)",
            self.username,
            self.host,
            self.port,
        )
        self.connected = True

    def execute_command(self, command: str) -> int:
        """Execute a fake command.

        Parameters
        ----------
        command : str
            Command to execute

        Returns
        -------
        int
            Fake exit code parsed from command if it contains 'exit N', otherwise 0
        """
        if not self.connected:
            raise RuntimeError("SSH connection not established")

        logger.info("Fake SSH: executing command: %s", command)

        exit_match = re.search(r"\bexit\s+(\d+)", command)
        if exit_match:
            return int(exit_match.group(1))
        return 0

    def execute_command_raw(self, command: str) -> int:
        """Execute raw fake command.

        Parameters
        ----------
        command : str
            Raw command to execute

        Returns
        -------
        int
            Fake exit code parsed from command if it contains 'exit N', otherwise 0
        """
        if not self.connected:
            raise RuntimeError("SSH connection not established")

        logger.info("Fake SSH: executing raw command: %s", command)

        exit_match = re.search(r"\bexit\s+(\d+)", command)
        if exit_match:
            return int(exit_match.group(1))
        return 0

    def close(self) -> None:
        """Close the fake SSH connection."""
        self.connected = False
        logger.info("Fake SSH connection closed")

    def filter_environment_variables(
        self,
        env_filter: list[str] | None,
    ) -> dict[str, str]:
        """Filter environment variables (returns empty dict for fake).

        Parameters
        ----------
        env_filter : list[str] | None
            List of regex patterns to match environment variable names

        Returns
        -------
        dict[str, str]
            Dictionary of filtered environment variables
        """

        if not env_filter:
            return {}

        compiled_patterns = [re.compile(pattern) for pattern in env_filter]
        filtered_vars: dict[str, str] = {}

        for var_name, var_value in os.environ.items():
            for regex in compiled_patterns:
                if regex.match(var_name):
                    filtered_vars[var_name] = var_value
                    break

        if filtered_vars:
            var_names = ", ".join(sorted(filtered_vars.keys()))
            logger.info(
                "Forwarding %s environment variables: %s",
                len(filtered_vars),
                var_names,
            )

            sensitive_patterns = ["SECRET", "PASSWORD", "TOKEN", "KEY"]
            sensitive_vars = [
                name
                for name in filtered_vars
                if any(pattern in name.upper() for pattern in sensitive_patterns)
            ]

            if sensitive_vars:
                logger.warning(
                    "Forwarding sensitive environment variables: %s",
                    ", ".join(sensitive_vars),
                )

        return filtered_vars

    def build_command_with_env(
        self,
        command: str,
        env_vars: dict[str, str] | None = None,
    ) -> str:
        """Build command with environment variable exports (returns unchanged for fake).

        Parameters
        ----------
        command : str
            Original command to execute
        env_vars : dict[str, str] | None
            Environment variables to export before command

        Returns
        -------
        str
            Command with optional environment exports
        """
        if not env_vars:
            return command

        exports = []
        for var_name, var_value in sorted(env_vars.items()):
            quoted_value = f"'{var_value}'"
            exports.append(f"export {var_name}={quoted_value}")

        export_prefix = " && ".join(exports)
        return f"{export_prefix} && {command}"

    def execute_command_with_env(
        self,
        command: str,
        env_vars: dict[str, str] | None = None,
    ) -> int:
        """Execute command with environment variables.

        Parameters
        ----------
        command : str
            Command to execute
        env_vars : dict[str, str] | None
            Environment variables to forward

        Returns
        -------
        int
            Fake exit code parsed from command if it contains 'exit N', otherwise 0
        """
        full_command = self.build_command_with_env(command, env_vars)
        return self.execute_command(full_command)

    def execute_interactive(self, command: str | None = None) -> int:
        """Execute fake interactive session with PTY allocation.

        Parameters
        ----------
        command : str | None
            Command to execute. If None, simulates opening a shell.

        Returns
        -------
        int
            Fake exit code parsed from command if it contains 'exit N', otherwise 0
        """
        if not self.connected:
            raise RuntimeError("SSH connection not established")

        logger.info("Fake SSH: executing interactive session: %s", command)

        if command:
            if command.strip() == "tty":
                logger.info("/dev/pts/1")

            exit_match = re.search(r"\bexit\s+(\d+)", command)
            if exit_match:
                return int(exit_match.group(1))
        return 0

    def abort_active_command(self) -> None:
        """Simulate aborting an active command (no-op for fake)."""
        logger.info("Fake SSH: abort_active_command (no-op)")
