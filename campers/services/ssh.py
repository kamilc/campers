"""SSH connection and command execution management."""

import contextlib
import inspect
import logging
import os
import re
import select
import shlex
import signal
import sys
import termios
import time
import tty
from dataclasses import dataclass

import paramiko
from paramiko.channel import Channel, ChannelFile

from campers.constants import (
    DEFAULT_CHANNEL_TIMEOUT,
    DEFAULT_PROVIDER,
    DEFAULT_SSH_PORT,
    DEFAULT_SSH_USERNAME,
    MAX_COMMAND_LENGTH,
    SENSITIVE_PATTERNS,
    SSH_RETRY_DELAYS,
)
from campers.providers import get_provider

logger = logging.getLogger(__name__)


def get_terminal_size() -> tuple[int, int]:
    """Get current terminal dimensions (width, height).

    Returns
    -------
    tuple[int, int]
        Terminal width and height in characters
    """
    size = os.get_terminal_size()
    return size.columns, size.lines


class InteractiveSession:
    """Manages an interactive SSH session with PTY.

    Parameters
    ----------
    channel : Channel
        SSH channel for the session

    Attributes
    ----------
    _channel : Channel
        SSH channel instance
    _old_tty_attrs : list | None
        Saved terminal attributes
    _original_sigwinch : signal.Handlers | None
        Original SIGWINCH handler
    """

    def __init__(self, channel: "Channel") -> None:
        """Initialize interactive session with SSH channel.

        Parameters
        ----------
        channel : Channel
            SSH channel for interactive communication
        """
        self._channel = channel
        self._old_tty_attrs: list | None = None
        self._original_sigwinch = None

    def _setup_terminal(self) -> None:
        """Switch terminal to raw mode and save original attributes."""
        self._old_tty_attrs = termios.tcgetattr(sys.stdin)
        tty.setraw(sys.stdin.fileno())
        tty.setcbreak(sys.stdin.fileno())

    def _restore_terminal(self) -> None:
        """Restore original terminal attributes."""
        if self._old_tty_attrs is not None:
            termios.tcsetattr(sys.stdin, termios.TCSAFLUSH, self._old_tty_attrs)

    def _setup_sigwinch(self) -> None:
        """Install SIGWINCH handler to forward terminal resize events."""
        self._original_sigwinch = signal.signal(signal.SIGWINCH, self._handle_sigwinch)
        self._resize_pty()

    def _restore_sigwinch(self) -> None:
        """Restore original SIGWINCH handler."""
        if self._original_sigwinch is not None:
            signal.signal(signal.SIGWINCH, self._original_sigwinch)

    def _handle_sigwinch(self, signum: int, frame) -> None:
        """Handle terminal resize signal.

        Parameters
        ----------
        signum : int
            Signal number (always SIGWINCH)
        frame : types.FrameType
            Stack frame
        """
        self._resize_pty()

    def _resize_pty(self) -> None:
        """Send current terminal size to remote PTY."""
        width, height = get_terminal_size()
        with contextlib.suppress(Exception):
            self._channel.resize_pty(width=width, height=height)

    def run(self) -> int:
        """Run the interactive session, return exit code.

        Returns
        -------
        int
            Exit code from remote session

        Raises
        ------
        KeyboardInterrupt
            If user presses Ctrl+C
        """
        self._channel.settimeout(0.0)

        try:
            self._setup_terminal()
            self._setup_sigwinch()

            while True:
                read_ready, _, _ = select.select([self._channel, sys.stdin], [], [])

                if self._channel in read_ready:
                    data = self._channel.recv(1024)
                    if len(data) == 0:
                        break
                    sys.stdout.buffer.write(data)
                    sys.stdout.flush()

                if sys.stdin in read_ready:
                    data = os.read(sys.stdin.fileno(), 1)
                    if len(data) == 0:
                        break
                    self._channel.send(data)

            self._channel.shutdown(2)
            return self._channel.recv_exit_status()

        finally:
            self._restore_sigwinch()
            self._restore_terminal()


@dataclass
class SSHConnectionInfo:
    """SSH connection information.

    Attributes
    ----------
    host : str
        Remote host IP address or hostname
    port : int
        SSH port number
    key_file : str
        SSH private key file path
    username : str | None
        SSH username (optional, defaults to system default)
    tag_key_file : str | None
        SSH key file from harness tags (optional, overrides key_file)
    """

    host: str
    port: int
    key_file: str
    username: str | None = None
    tag_key_file: str | None = None


def get_ssh_connection_info(instance_id: str, public_ip: str, key_file: str) -> SSHConnectionInfo:
    """Determine SSH connection host, port, and key file.

    Delegates to provider-specific SSH resolution through the provider registry.
    Currently only AWS is supported, but this interface allows for multi-cloud
    support in the future.

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
    SSHConnectionInfo
        SSH connection information with host, port, and key file

    Raises
    ------
    ValueError
        If SSH connection details cannot be determined
    """
    provider = get_provider(DEFAULT_PROVIDER)
    get_ssh_info_func = provider.get("get_ssh_connection_info")

    if get_ssh_info_func is None:
        raise ValueError("SSH connection info function not registered for the provider")

    if callable(get_ssh_info_func):
        sig = inspect.signature(get_ssh_info_func)
        if len(sig.parameters) == 0:
            get_ssh_info_func = get_ssh_info_func()

    return get_ssh_info_func(instance_id, public_ip, key_file)


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
        self,
        host: str,
        key_file: str,
        username: str = DEFAULT_SSH_USERNAME,
        port: int = DEFAULT_SSH_PORT,
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
        timeout_seconds = int(os.environ.get("CAMPERS_SSH_TIMEOUT", "30"))
        effective_max_retries = int(os.environ.get("CAMPERS_SSH_MAX_RETRIES", str(max_retries)))

        for attempt in range(effective_max_retries):
            old_client = self.client
            try:
                logger.info(
                    "Attempting SSH connection (attempt %s/%s)...",
                    attempt + 1,
                    effective_max_retries,
                )

                if old_client is not None:
                    try:
                        old_client.close()
                    except (OSError, paramiko.SSHException) as e:
                        logger.warning("Failed to close previous SSH connection: %s", e)

                self.client = paramiko.SSHClient()

                if os.environ.get("CAMPERS_STRICT_HOST_KEY", "0") == "1":
                    self.client.load_system_host_keys()
                    self.client.set_missing_host_key_policy(paramiko.RejectPolicy())
                else:
                    self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

                try:
                    key = paramiko.Ed25519Key.from_private_key_file(self.key_file)
                except (paramiko.SSHException, ValueError):
                    try:
                        key = paramiko.RSAKey.from_private_key_file(self.key_file)
                    except (paramiko.SSHException, ValueError):
                        try:
                            key = paramiko.ECDSAKey.from_private_key_file(self.key_file)
                        except (paramiko.SSHException, ValueError):
                            key = paramiko.DSSKey.from_private_key_file(self.key_file)

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

            except (TimeoutError, paramiko.SSHException, OSError) as e:
                if attempt < effective_max_retries - 1:
                    delay_index = min(attempt, len(SSH_RETRY_DELAYS) - 1)
                    delay = SSH_RETRY_DELAYS[delay_index]
                    time.sleep(delay)
                    continue
                else:
                    raise ConnectionError(
                        f"Failed to establish SSH connection after {effective_max_retries} attempts"
                    ) from e

    def stream_remaining_output(self, stream: ChannelFile) -> None:
        """Stream remaining output from a channel stream.

        Parameters
        ----------
        stream : ChannelFile
            Channel stream to read from (stdout or stderr)
        """
        for line in stream.readlines():
            logging.info(line.rstrip("\n"))

    def stream_output_realtime(
        self, stdout: ChannelFile, stderr: ChannelFile, timeout: float | None = None
    ) -> None:
        """Stream stdout and stderr in real-time until command completes.

        Parameters
        ----------
        stdout : ChannelFile
            SSH channel stdout stream
        stderr : ChannelFile
            SSH channel stderr stream
        timeout : float | None, optional
            Maximum total time in seconds to wait for command completion.
            Default is None (no timeout).

        Raises
        ------
        TimeoutError
            If command does not complete within the timeout period
        """
        start_time = time.monotonic()

        while True:
            if timeout is not None and time.monotonic() - start_time > timeout:
                raise TimeoutError(f"Stream output timed out after {timeout} seconds")

            stdout.channel.settimeout(DEFAULT_CHANNEL_TIMEOUT)

            try:
                line = stdout.readline()
            except TimeoutError:
                if stdout.channel.exit_status_ready():
                    break
                continue

            if line:
                logging.info(line.rstrip("\n"))

            if stderr.channel.recv_stderr_ready():
                err_line = stderr.readline()
                if err_line:
                    logging.info(err_line.rstrip("\n"))

            if stdout.channel.exit_status_ready() and not line:
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

            self.stream_remaining_output(stdout)
            self.stream_remaining_output(stderr)

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

    def validate_command_length(self, command: str) -> None:
        """Validate that command does not exceed maximum length.

        Parameters
        ----------
        command : str
            Command to validate

        Raises
        ------
        ValueError
            If command is empty or exceeds maximum length
        """
        if not command or not command.strip():
            raise ValueError("Command cannot be empty")

        if len(command) > MAX_COMMAND_LENGTH:
            msg = (
                f"Command length ({len(command)}) exceeds maximum of "
                f"{MAX_COMMAND_LENGTH} characters"
            )
            raise ValueError(msg)

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
        self.validate_command_length(command)
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
        self.validate_command_length(command)
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
            logger.info("Forwarding %s environment variables: %s", len(filtered_vars), var_names)

            sensitive_vars = [
                name
                for name in filtered_vars
                if any(pattern in name.upper() for pattern in SENSITIVE_PATTERNS)
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
            msg = (
                f"Command with environment variables ({len(full_command)} chars) "
                f"exceeds maximum of {MAX_COMMAND_LENGTH} characters. "
                f"Consider: 1) reducing environment variables, "
                f"2) using shorter values, or 3) simplifying the command."
            )
            raise ValueError(msg)

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
        except (OSError, paramiko.SSHException) as exc:
            logger.warning("Failed to close active SSH channel: %s", exc)
        finally:
            self._active_channel = None

    def execute_interactive(self, command: str | None = None) -> int:
        """Execute interactive session with PTY allocation.

        Parameters
        ----------
        command : str | None
            Command to execute. If None, opens a shell.

        Returns
        -------
        int
            Exit code from the remote session

        Raises
        ------
        RuntimeError
            If SSH connection is not established
        """
        if not self.client:
            raise RuntimeError("SSH connection not established")

        transport = self.client.get_transport()

        if command:
            channel = transport.open_session()
            width, height = get_terminal_size()
            channel.get_pty(width=width, height=height)
            channel.exec_command(command)
        else:
            channel = self.client.invoke_shell()

        session = InteractiveSession(channel)
        return session.run()
