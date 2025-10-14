"""SSH connection and command execution management."""

import logging
import os
import re
import shlex
import socket
import time

import paramiko
from paramiko.channel import ChannelFile

logger = logging.getLogger(__name__)

MAX_COMMAND_LENGTH = 10000


def get_ssh_connection_info(
    instance_id: str, public_ip: str, key_file: str
) -> tuple[str, int, str]:
    """Determine SSH connection host, port, and key file.

    For LocalStack scenarios, redirects to Docker container.
    For real AWS, uses actual instance public IP.

    Parameters
    ----------
    instance_id : str
        EC2 instance ID
    public_ip : str
        Instance public IP address
    key_file : str
        Original key file path from instance details

    Returns
    -------
    tuple[str, int, str]
        (host, port, key_file) tuple for SSH connection
    """
    if os.environ.get("AWS_ENDPOINT_URL"):
        port_env_var = f"SSH_PORT_{instance_id}"
        key_file_env_var = f"SSH_KEY_FILE_{instance_id}"

        max_wait = 120
        start = time.time()
        logger.info(
            f"LocalStack mode: waiting for SSH container for {instance_id} (max {max_wait}s)..."
        )

        while time.time() - start < max_wait:
            if port_env_var in os.environ and key_file_env_var in os.environ:
                port = int(os.environ[port_env_var])
                actual_key_file = os.environ[key_file_env_var]
                elapsed = time.time() - start
                logger.info(
                    f"LocalStack mode: SSH container ready after {elapsed:.1f}s - connecting to localhost:{port} with key {actual_key_file}"
                )
                logger.debug(f"SSH key file path: {actual_key_file}")
                logger.debug(f"SSH key file exists: {os.path.exists(actual_key_file)}")
                return "localhost", port, actual_key_file
            time.sleep(0.5)

        logger.error(
            f"SSH container not ready for {instance_id} after {max_wait}s, using fallback (this will likely fail)"
        )

    return public_ip, 22, key_file


class SSHManager:
    """Manages SSH connections and command execution on EC2 instances.

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

        for attempt in range(max_retries):
            try:
                logger.info(
                    "Attempting SSH connection (attempt %s/%s)...",
                    attempt + 1,
                    max_retries,
                )

                self.client = paramiko.SSHClient()
                self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

                key = paramiko.RSAKey.from_private_key_file(self.key_file)

                self.client.connect(
                    hostname=self.host,
                    port=self.port,
                    username=self.username,
                    pkey=key,
                    timeout=30,
                    banner_timeout=30,
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
                if attempt < max_retries - 1:
                    delay = delays[attempt]
                    time.sleep(delay)
                    continue
                else:
                    raise ConnectionError(
                        f"Failed to establish SSH connection after {max_retries} attempts"
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
            logging.info(line.rstrip("\n"), extra={"stream": stream_type})

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
                logging.info(line.rstrip("\n"), extra={"stream": "stdout"})

            err_line = stderr.readline()

            if err_line:
                logging.info(err_line.rstrip("\n"), extra={"stream": "stderr"})

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
            stdin, stdout, stderr = self.client.exec_command(command)

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

        shell_command = f"cd ~ && bash -c {repr(command)}"
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
        if self.client:
            self.client.close()
            self.client = None
