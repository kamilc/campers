"""SSH connection and command execution management."""

import logging
import socket
import time

import paramiko

logger = logging.getLogger(__name__)


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

    Attributes
    ----------
    host : str
        Remote host IP address or hostname
    key_file : str
        Path to SSH private key file
    username : str
        SSH username
    client : paramiko.SSHClient | None
        SSH client instance (None when not connected)
    """

    def __init__(self, host: str, key_file: str, username: str = "ubuntu") -> None:
        """Initialize SSHManager with connection parameters.

        Parameters
        ----------
        host : str
            Remote host IP address or hostname
        key_file : str
            Path to SSH private key file
        username : str
            SSH username (default: ubuntu)
        """
        self.host = host
        self.key_file = key_file
        self.username = username
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
                    f"Attempting SSH connection (attempt {attempt + 1}/{max_retries})..."
                )

                self.client = paramiko.SSHClient()
                self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

                key = paramiko.RSAKey.from_private_key_file(self.key_file)

                self.client.connect(
                    hostname=self.host,
                    port=22,
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

    def stream_remaining_output(self, stream, prefix: str) -> None:
        """Stream remaining output from a channel stream.

        Parameters
        ----------
        stream
            Channel stream to read from (stdout or stderr)
        prefix : str
            Prefix to add to output lines (e.g., "[stdout]" or "[stderr]")
        """
        for line in stream.readlines():
            print(f"{prefix} {line}", end="", flush=True)

    def stream_output_realtime(self, stdout, stderr) -> None:
        """Stream stdout and stderr in real-time until command completes.

        Parameters
        ----------
        stdout
            SSH channel stdout stream
        stderr
            SSH channel stderr stream
        """
        while True:
            line = stdout.readline()

            if line:
                print(f"[stdout] {line}", end="", flush=True)

            err_line = stderr.readline()

            if err_line:
                print(f"[stderr] {err_line}", end="", flush=True)

            if stdout.channel.exit_status_ready():
                break

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
        if not self.client:
            raise RuntimeError("SSH connection not established")

        if not command or not command.strip():
            raise ValueError("Command cannot be empty")

        if len(command) > 10000:
            raise ValueError(
                f"Command length ({len(command)}) exceeds maximum of 10000 characters"
            )

        stdin = None
        stdout = None
        stderr = None

        try:
            shell_command = f"cd ~ && bash -c {repr(command)}"
            stdin, stdout, stderr = self.client.exec_command(shell_command)

            self.stream_output_realtime(stdout, stderr)

            self.stream_remaining_output(stdout, "[stdout]")
            self.stream_remaining_output(stderr, "[stderr]")

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

    def close(self) -> None:
        """Close SSH connection and clean up resources."""
        if self.client:
            self.client.close()
            self.client = None
