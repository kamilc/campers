"""Fake SSHManager for testing with dependency injection."""

import logging

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
        """Execute a fake command (always returns 0).

        Parameters
        ----------
        command : str
            Command to execute

        Returns
        -------
        int
            Fake exit code (always 0 for success)
        """
        if not self.connected:
            raise RuntimeError("SSH connection not established")

        logger.info("Fake SSH: executing command: %s", command)
        return 0

    def execute_command_raw(self, command: str) -> int:
        """Execute raw fake command (always returns 0).

        Parameters
        ----------
        command : str
            Raw command to execute

        Returns
        -------
        int
            Fake exit code (always 0 for success)
        """
        if not self.connected:
            raise RuntimeError("SSH connection not established")

        logger.info("Fake SSH: executing raw command: %s", command)
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
            Empty dict for fake implementation
        """
        return {}

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
        """Execute command with environment variables (always returns 0 for fake).

        Parameters
        ----------
        command : str
            Command to execute
        env_vars : dict[str, str] | None
            Environment variables to forward

        Returns
        -------
        int
            Fake exit code (always 0 for success)
        """
        full_command = self.build_command_with_env(command, env_vars)
        return self.execute_command(full_command)

    def abort_active_command(self) -> None:
        """Simulate aborting an active command (no-op for fake)."""
        logger.info("Fake SSH: abort_active_command (no-op)")
