"""SSH connection and command execution management."""

import logging
import os
import re
import shlex
import socket
import time

import paramiko
from paramiko.channel import Channel, ChannelFile

from campers.constants import MAX_COMMAND_LENGTH
from campers.providers.aws.ssh import get_aws_ssh_connection_info

logger = logging.getLogger(__name__)


def get_ssh_connection_info(
    instance_id: str, public_ip: str, key_file: str
) -> tuple[str, int, str]:
    """Determine SSH connection host, port, and key file.

    Delegates to provider-specific SSH resolution. Currently only AWS is
    supported, but this interface allows for multi-cloud support in the future.

    Parameters
    ----------
    instance_id : str
        Instance ID
    public_ip : str
        Instance public IP address
    key_file : str
        SSH private key file path

    Returns
    -------
    tuple[str, int, str]
        (host, port, key_file) tuple for SSH connection

    Raises
    ------
    ValueError
        If SSH connection details cannot be determined
    """
    return get_aws_ssh_connection_info(instance_id, public_ip, key_file)


class SSHManager:
    """Manages SSH connections and command execution on cloud instances.

    Parameters
    ----------
    host : str
        Remote host IP address or hostname
    key_file : str
        Path to SSH private key file
    username : str
        SSH username (default: ubuntu)
    port : int
        SSH port (default: 22)

    Attributes
    ----------
    host : str
        Remote host IP address or hostname
    key_file : str
        Path to SSH private key file
    username : str
        SSH username
    port : int
        SSH port
    client : paramiko.SSHClient | None
        SSH client instance (None when not connected)
    """

    def __init__(
        self, host: str, key_file: str, username: str = "ubuntu", port: int = 22
    ) -> None:
        """Initialize SSHManager with connection parameters.

        Parameters
        ----------
        host : str
            Remote host IP address or hostname
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
        self.client: paramiko.SSHClient | None = None
        self._active_channel: Channel | None = None

    def connect(self, max_retries: int = 10) -> None:
        """Establish SSH connection with retry logic.

        Implements exponential backoff with delays:
        1s, 2s, 4s, 8s, 16s, 30s, 30s, 30s, 30s, 30s
        Total time: approximately 2 minutes

        Parameters
        ----------
        max_retries : int
            Maximum number of connection attempts (default: 10)

        Raises
        ------
        ConnectionError
            If connection fails after all retry attempts
        IOError
            If SSH key file cannot be read
        PermissionError
            If SSH key file has incorrect permissions or cannot be accessed
        """
        delays = [1, 2, 4, 8, 16, 30, 30, 30, 30, 30]
        timeout_seconds = int(os.environ.get("CAMPERS_SSH_TIMEOUT", "30"))
        effective_max_retries = int(
            os.environ.get("CAMPERS_SSH_MAX_RETRIES", str(max_retries))
        )

        for attempt in range(effective_max_retries):
            try:
                logger.info(
                    "Attempting SSH connection (attempt %s/%s)...",
                    attempt + 1,
                    effective_max_retries,
                )

                self.client = paramiko.SSHClient()
                self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

                key = paramiko.RSAKey.from_private_key_file(self.key_file)

                self.client.connect(
                    hostname=self.host,
                    port=self.port,
                    username=self.username,
                    pkey=key,
                    timeout=timeout_seconds,
                    auth_timeout=30,
                    banner_timeout=timeout_seconds,
                )
                return

            except (
                paramiko.ssh_exception.NoValidConnectionsError,
                paramiko.ssh_exception.SSHException,
                TimeoutError,
                ConnectionRefusedError,
                ConnectionResetError,
                socket.timeout,
            ) as e:
                if attempt < effective_max_retries - 1:
                    delay = delays[attempt]
                    time.sleep(delay)
                    continue
                else:
                    raise ConnectionError(
                        f"Failed to establish SSH connection after {effective_max_retries} attempts"
                    ) from e

    def stream_remaining_output(self, stream: ChannelFile, stream_type: str) -> None:
        """Stream remaining output from a channel stream.

        Parameters
        ----------
        stream : ChannelFile
            Channel stream to read from (stdout or stderr)
        stream_type : str
            Stream type identifier: "stdout" or "stderr"
        """
        for line in stream.readlines():
            logging.info(line.rstrip("\n"))

    def stream_output_realtime(self, stdout: ChannelFile, stderr: ChannelFile) -> None:
        """Stream stdout and stderr in real-time until command completes.

        Parameters
        ----------
        stdout : ChannelFile
            SSH channel stdout stream
        stderr : ChannelFile
            SSH channel stderr stream
        """
        while True:
            line = stdout.readline()

            if line:
                logging.info(line.rstrip("\n"))

            if stderr.channel.recv_stderr_ready():
                err_line = stderr.readline()
                if err_line:
                    logging.info(err_line.rstrip("\n"))

            if stdout.channel.exit_status_ready():
                break

    def _execute_with_streaming(self, command: str) -> int:
        """Execute command with streaming output (common logic).

        Parameters
        ----------
        command : str
            Command to execute on remote host

        Returns
        -------
        int
            Command exit code

        Raises
        ------
        RuntimeError
            If SSH connection is not established
        KeyboardInterrupt
            If user interrupts execution
        """
        if not self.client:
            raise RuntimeError("SSH connection not established")

        stdin = None
        stdout = None
        stderr = None

        try:
            stdin, stdout, stderr = self.client.exec_command(command, get_pty=True)
            self._active_channel = stdout.channel

            self.stream_output_realtime(stdout, stderr)

            self.stream_remaining_output(stdout, "stdout")
            self.stream_remaining_output(stderr, "stderr")

            exit_code = stdout.channel.recv_exit_status()
            return exit_code

        except KeyboardInterrupt:
            self.close()
            raise

        finally:
            if stdin:
                stdin.close()

            if stdout:
                stdout.close()

            if stderr:
                stderr.close()

            self._active_channel = None

    def execute_command(self, command: str) -> int:
        """Execute command and stream output in real-time.

        Parameters
        ----------
        command : str
            Shell command to execute (will be run in bash shell)

        Returns
        -------
        int
            Command exit code (0 = success, non-zero = failure)

        Raises
        ------
        RuntimeError
            If SSH connection is not established
        ValueError
            If command is empty or exceeds maximum length
        KeyboardInterrupt
            If user presses Ctrl+C during command execution
        """
        if not command or not command.strip():
            raise ValueError("Command cannot be empty")

        if len(command) > MAX_COMMAND_LENGTH:
            raise ValueError(
                f"Command length ({len(command)}) exceeds maximum of {MAX_COMMAND_LENGTH} characters"
            )

        shell_command = f"cd ~ && bash -c {shlex.quote(command)}"
        return self._execute_with_streaming(shell_command)

    def execute_command_raw(self, command: str) -> int:
        """Execute raw command without cd ~ && bash -c wrapping.

        Used for commands that need custom working directory.

        Parameters
        ----------
        command : str
            Raw command to execute (caller handles working directory and shell)

        Returns
        -------
        int
            Command exit code (0 = success, non-zero = failure)

        Raises
        ------
        RuntimeError
            If SSH connection is not established
        ValueError
            If command is empty or exceeds maximum length
        KeyboardInterrupt
            If user presses Ctrl+C during command execution
        """
        if not command or not command.strip():
            raise ValueError("Command cannot be empty")

        if len(command) > MAX_COMMAND_LENGTH:
            raise ValueError(
                f"Command length ({len(command)}) exceeds maximum of {MAX_COMMAND_LENGTH} characters"
            )

        return self._execute_with_streaming(command)

    def filter_environment_variables(
        self,
        env_filter: list[str] | None,
    ) -> dict[str, str]:
        """Filter local environment variables using regex patterns.

        Patterns are pre-validated during config loading, so no validation
        is performed here.

        Parameters
        ----------
        env_filter : list[str] | None
            List of regex patterns to match environment variable names.
            Variables matching any pattern will be included.
            Patterns must be pre-validated (already checked by ConfigLoader).

        Returns
        -------
        dict[str, str]
            Dictionary of filtered environment variables (name -> value)
        """
        if not env_filter:
            return {}

        compiled_patterns = [re.compile(pattern) for pattern in env_filter]
        filtered_vars = {}

        for var_name, var_value in os.environ.items():
            for regex in compiled_patterns:
                if regex.match(var_name):
                    filtered_vars[var_name] = var_value
                    break

        if filtered_vars:
            var_names = ", ".join(sorted(filtered_vars.keys()))
            logger.info(
                "Forwarding %s environment variables: %s", len(filtered_vars), var_names
            )

            sensitive_patterns = ["SECRET", "PASSWORD", "TOKEN", "KEY"]
            sensitive_vars = [
                name
                for name in filtered_vars.keys()
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
        """Build command with environment variable exports.

        Parameters
        ----------
        command : str
            Original command to execute
        env_vars : dict[str, str] | None
            Environment variables to export before command

        Returns
        -------
        str
            Command with environment variable exports prepended

        Raises
        ------
        ValueError
            If resulting command exceeds maximum length
        """
        if not env_vars:
            return command

        exports = []

        for var_name, var_value in sorted(env_vars.items()):
            quoted_value = shlex.quote(var_value)
            exports.append(f"export {var_name}={quoted_value}")

        export_prefix = " && ".join(exports)
        full_command = f"{export_prefix} && {command}"

        if len(full_command) > MAX_COMMAND_LENGTH:
            raise ValueError(
                f"Command with environment variables ({len(full_command)} chars) "
                f"exceeds maximum of {MAX_COMMAND_LENGTH} characters. "
                f"Consider: 1) reducing environment variables, 2) using shorter values, or 3) simplifying the command."
            )

        return full_command

    def execute_command_with_env(
        self,
        command: str,
        env_vars: dict[str, str] | None = None,
    ) -> int:
        """Execute command with environment variables forwarded.

        Parameters
        ----------
        command : str
            Command to execute
        env_vars : dict[str, str] | None
            Environment variables to forward

        Returns
        -------
        int
            Exit code from command execution
        """
        full_command = self.build_command_with_env(command, env_vars)
        return self.execute_command(full_command)

    def close(self) -> None:
        """Close SSH connection and clean up resources."""
        self.abort_active_command()

        if self.client:
            self.client.close()
            self.client = None

    def abort_active_command(self) -> None:
        """Abort in-flight command execution.

        Notes
        -----
        Closes the active SSH channel, if present, so blocking output reads
        terminate promptly during cleanup.
        """
        if self._active_channel is None:
            return

        try:
            self._active_channel.close()
        except Exception as exc:  # pragma: no cover
            logging.debug("Failed to close active SSH channel: %s", exc)
        finally:
            self._active_channel = None
