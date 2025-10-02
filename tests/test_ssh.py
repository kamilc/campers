"""Unit tests for SSH connection and command execution."""

from unittest.mock import MagicMock, call, patch

import paramiko
import pytest

from moondock.ssh import SSHManager


@pytest.fixture
def ssh_manager() -> SSHManager:
    """Create SSHManager instance for testing.

    Returns
    -------
    SSHManager
        Configured SSH manager instance
    """
    return SSHManager(host="203.0.113.1", key_file="/tmp/test.pem", username="ubuntu")


def test_ssh_manager_initialization() -> None:
    """Test SSHManager initialization with correct parameters."""
    manager = SSHManager(
        host="203.0.113.1", key_file="/tmp/test.pem", username="ubuntu"
    )

    assert manager.host == "203.0.113.1"
    assert manager.key_file == "/tmp/test.pem"
    assert manager.username == "ubuntu"
    assert manager.client is None


def test_ssh_manager_default_username() -> None:
    """Test SSHManager uses default username when not specified."""
    manager = SSHManager(host="203.0.113.1", key_file="/tmp/test.pem")

    assert manager.username == "ubuntu"


@patch("moondock.ssh.paramiko.SSHClient")
@patch("moondock.ssh.paramiko.RSAKey.from_private_key_file")
def test_connect_success_first_attempt(
    mock_rsa_key: MagicMock, mock_ssh_client: MagicMock, ssh_manager: SSHManager
) -> None:
    """Test successful SSH connection on first attempt."""
    mock_client = MagicMock()
    mock_ssh_client.return_value = mock_client
    mock_key = MagicMock()
    mock_rsa_key.return_value = mock_key

    ssh_manager.connect()

    mock_ssh_client.assert_called_once()
    mock_client.set_missing_host_key_policy.assert_called_once()
    mock_rsa_key.assert_called_once_with("/tmp/test.pem")
    mock_client.connect.assert_called_once_with(
        hostname="203.0.113.1",
        port=22,
        username="ubuntu",
        pkey=mock_key,
        timeout=30,
        banner_timeout=30,
    )
    assert ssh_manager.client == mock_client


@patch("moondock.ssh.time.sleep")
@patch("moondock.ssh.paramiko.SSHClient")
@patch("moondock.ssh.paramiko.RSAKey.from_private_key_file")
def test_connect_retry_with_exponential_backoff(
    mock_rsa_key: MagicMock,
    mock_ssh_client: MagicMock,
    mock_sleep: MagicMock,
    ssh_manager: SSHManager,
) -> None:
    """Test SSH connection retry with exponential backoff delays."""
    mock_client = MagicMock()
    mock_ssh_client.return_value = mock_client
    mock_key = MagicMock()
    mock_rsa_key.return_value = mock_key

    mock_client.connect.side_effect = [
        ConnectionRefusedError("Connection refused"),
        ConnectionRefusedError("Connection refused"),
        ConnectionRefusedError("Connection refused"),
        None,
    ]

    ssh_manager.connect()

    assert mock_client.connect.call_count == 4

    expected_sleep_calls = [call(1), call(2), call(4)]
    assert mock_sleep.call_args_list == expected_sleep_calls


@patch("moondock.ssh.time.sleep")
@patch("moondock.ssh.paramiko.SSHClient")
@patch("moondock.ssh.paramiko.RSAKey.from_private_key_file")
def test_connect_fails_after_max_retries(
    mock_rsa_key: MagicMock,
    mock_ssh_client: MagicMock,
    mock_sleep: MagicMock,
    ssh_manager: SSHManager,
) -> None:
    """Test SSH connection raises error after max retries exceeded."""
    mock_client = MagicMock()
    mock_ssh_client.return_value = mock_client
    mock_key = MagicMock()
    mock_rsa_key.return_value = mock_key

    mock_client.connect.side_effect = ConnectionRefusedError("Connection refused")

    with pytest.raises(ConnectionError) as exc_info:
        ssh_manager.connect()

    assert "Failed to establish SSH connection after 10 attempts" in str(exc_info.value)
    assert mock_client.connect.call_count == 10


@patch("moondock.ssh.time.sleep")
@patch("moondock.ssh.paramiko.SSHClient")
@patch("moondock.ssh.paramiko.RSAKey.from_private_key_file")
def test_connect_handles_various_exceptions(
    mock_rsa_key: MagicMock,
    mock_ssh_client: MagicMock,
    mock_sleep: MagicMock,
    ssh_manager: SSHManager,
) -> None:
    """Test SSH connection handles different exception types."""
    mock_client = MagicMock()
    mock_ssh_client.return_value = mock_client
    mock_key = MagicMock()
    mock_rsa_key.return_value = mock_key

    exceptions = [
        paramiko.ssh_exception.NoValidConnectionsError(
            {("203.0.113.1", 22): "Connection refused"}
        ),
        paramiko.ssh_exception.SSHException("SSH error"),
        TimeoutError("Timeout"),
        ConnectionResetError("Connection reset"),
        None,
    ]

    mock_client.connect.side_effect = exceptions

    ssh_manager.connect()

    assert mock_client.connect.call_count == 5


@patch("moondock.ssh.paramiko.SSHClient")
@patch("moondock.ssh.paramiko.RSAKey.from_private_key_file")
def test_execute_command_without_connection(
    mock_rsa_key: MagicMock, mock_ssh_client: MagicMock, ssh_manager: SSHManager
) -> None:
    """Test execute_command raises error when not connected."""
    with pytest.raises(RuntimeError) as exc_info:
        ssh_manager.execute_command("echo test")

    assert "SSH connection not established" in str(exc_info.value)


def test_execute_command_empty_string(ssh_manager: SSHManager) -> None:
    """Test execute_command raises ValueError for empty command."""
    ssh_manager.client = MagicMock()

    with pytest.raises(ValueError) as exc_info:
        ssh_manager.execute_command("")

    assert "Command cannot be empty" in str(exc_info.value)


def test_execute_command_whitespace_only(ssh_manager: SSHManager) -> None:
    """Test execute_command raises ValueError for whitespace-only command."""
    ssh_manager.client = MagicMock()

    with pytest.raises(ValueError) as exc_info:
        ssh_manager.execute_command("   ")

    assert "Command cannot be empty" in str(exc_info.value)


def test_execute_command_exceeds_max_length(ssh_manager: SSHManager) -> None:
    """Test execute_command raises ValueError for commands over 10000 chars."""
    ssh_manager.client = MagicMock()
    long_command = "a" * 10001

    with pytest.raises(ValueError) as exc_info:
        ssh_manager.execute_command(long_command)

    assert "exceeds maximum of 10000 characters" in str(exc_info.value)


@patch("moondock.ssh.paramiko.SSHClient")
@patch("moondock.ssh.paramiko.RSAKey.from_private_key_file")
def test_execute_command_success(
    mock_rsa_key: MagicMock, mock_ssh_client: MagicMock, ssh_manager: SSHManager
) -> None:
    """Test successful command execution with output streaming."""
    mock_client = MagicMock()
    mock_ssh_client.return_value = mock_client
    ssh_manager.client = mock_client

    mock_stdin = MagicMock()
    mock_stdout = MagicMock()
    mock_stderr = MagicMock()

    mock_stdout.readline.side_effect = ["line 1\n", "line 2\n", ""]
    mock_stdout.readlines.return_value = []
    mock_stderr.readline.return_value = ""
    mock_stderr.readlines.return_value = []
    mock_stdout.channel.exit_status_ready.side_effect = [False, False, True]
    mock_stdout.channel.recv_exit_status.return_value = 0

    mock_client.exec_command.return_value = (mock_stdin, mock_stdout, mock_stderr)

    exit_code = ssh_manager.execute_command("echo test")

    assert exit_code == 0
    mock_client.exec_command.assert_called_once_with("cd ~ && bash -c 'echo test'")


@patch("moondock.ssh.paramiko.SSHClient")
@patch("moondock.ssh.paramiko.RSAKey.from_private_key_file")
def test_execute_command_with_stderr(
    mock_rsa_key: MagicMock, mock_ssh_client: MagicMock, ssh_manager: SSHManager
) -> None:
    """Test command execution captures stderr output."""
    mock_client = MagicMock()
    mock_ssh_client.return_value = mock_client
    ssh_manager.client = mock_client

    mock_stdin = MagicMock()
    mock_stdout = MagicMock()
    mock_stderr = MagicMock()

    mock_stdout.readline.side_effect = ["stdout line\n", ""]
    mock_stdout.readlines.return_value = []
    mock_stderr.readline.side_effect = ["error line\n", ""]
    mock_stderr.readlines.return_value = []
    mock_stdout.channel.exit_status_ready.side_effect = [False, True]
    mock_stdout.channel.recv_exit_status.return_value = 1

    mock_client.exec_command.return_value = (mock_stdin, mock_stdout, mock_stderr)

    exit_code = ssh_manager.execute_command("exit 1")

    assert exit_code == 1


@patch("moondock.ssh.paramiko.SSHClient")
@patch("moondock.ssh.paramiko.RSAKey.from_private_key_file")
def test_execute_command_with_keyboard_interrupt(
    mock_rsa_key: MagicMock, mock_ssh_client: MagicMock, ssh_manager: SSHManager
) -> None:
    """Test command execution handles Ctrl+C gracefully."""
    mock_client = MagicMock()
    mock_ssh_client.return_value = mock_client
    ssh_manager.client = mock_client

    mock_stdin = MagicMock()
    mock_stdout = MagicMock()
    mock_stderr = MagicMock()

    mock_stdout.readline.side_effect = KeyboardInterrupt()
    mock_client.exec_command.return_value = (mock_stdin, mock_stdout, mock_stderr)

    with pytest.raises(KeyboardInterrupt):
        ssh_manager.execute_command("sleep 300")

    mock_client.close.assert_called_once()
    assert ssh_manager.client is None


@patch("moondock.ssh.paramiko.SSHClient")
@patch("moondock.ssh.paramiko.RSAKey.from_private_key_file")
def test_execute_command_shell_features(
    mock_rsa_key: MagicMock, mock_ssh_client: MagicMock, ssh_manager: SSHManager
) -> None:
    """Test command execution supports shell features like pipes."""
    mock_client = MagicMock()
    mock_ssh_client.return_value = mock_client
    ssh_manager.client = mock_client

    mock_stdin = MagicMock()
    mock_stdout = MagicMock()
    mock_stderr = MagicMock()

    mock_stdout.readline.return_value = ""
    mock_stdout.readlines.return_value = []
    mock_stderr.readline.return_value = ""
    mock_stderr.readlines.return_value = []
    mock_stdout.channel.exit_status_ready.return_value = True
    mock_stdout.channel.recv_exit_status.return_value = 0

    mock_client.exec_command.return_value = (mock_stdin, mock_stdout, mock_stderr)

    ssh_manager.execute_command("echo hello | grep ll")

    mock_client.exec_command.assert_called_once_with(
        "cd ~ && bash -c 'echo hello | grep ll'"
    )


@patch("moondock.ssh.paramiko.SSHClient")
@patch("moondock.ssh.paramiko.RSAKey.from_private_key_file")
def test_close_connection(
    mock_rsa_key: MagicMock, mock_ssh_client: MagicMock, ssh_manager: SSHManager
) -> None:
    """Test close properly cleans up SSH connection."""
    mock_client = MagicMock()
    mock_ssh_client.return_value = mock_client
    ssh_manager.client = mock_client

    ssh_manager.close()

    mock_client.close.assert_called_once()
    assert ssh_manager.client is None


def test_close_without_connection(ssh_manager: SSHManager) -> None:
    """Test close handles case when no connection exists."""
    ssh_manager.close()

    assert ssh_manager.client is None


@patch("moondock.ssh.paramiko.SSHClient")
@patch("moondock.ssh.paramiko.RSAKey.from_private_key_file")
def test_execute_command_with_multiline_output(
    mock_rsa_key: MagicMock, mock_ssh_client: MagicMock, ssh_manager: SSHManager
) -> None:
    """Test command execution handles multi-line output correctly."""
    mock_client = MagicMock()
    mock_ssh_client.return_value = mock_client
    ssh_manager.client = mock_client

    mock_stdin = MagicMock()
    mock_stdout = MagicMock()
    mock_stderr = MagicMock()

    mock_stdout.readline.side_effect = ["line 1\n", "line 2\n", "line 3\n", ""]
    mock_stdout.readlines.return_value = []
    mock_stderr.readline.return_value = ""
    mock_stderr.readlines.return_value = []
    mock_stdout.channel.exit_status_ready.side_effect = [False, False, False, True]
    mock_stdout.channel.recv_exit_status.return_value = 0

    mock_client.exec_command.return_value = (mock_stdin, mock_stdout, mock_stderr)

    exit_code = ssh_manager.execute_command("echo -e 'line 1\\nline 2\\nline 3'")

    assert exit_code == 0


@patch("moondock.ssh.paramiko.SSHClient")
@patch("moondock.ssh.paramiko.RSAKey.from_private_key_file")
def test_execute_command_remaining_output(
    mock_rsa_key: MagicMock, mock_ssh_client: MagicMock, ssh_manager: SSHManager
) -> None:
    """Test command execution captures remaining output after exit ready."""
    mock_client = MagicMock()
    mock_ssh_client.return_value = mock_client
    ssh_manager.client = mock_client

    mock_stdin = MagicMock()
    mock_stdout = MagicMock()
    mock_stderr = MagicMock()

    mock_stdout.readline.side_effect = ["line 1\n", ""]
    mock_stdout.readlines.return_value = ["line 2\n", "line 3\n"]
    mock_stderr.readline.return_value = ""
    mock_stderr.readlines.return_value = ["error at end\n"]
    mock_stdout.channel.exit_status_ready.side_effect = [False, True]
    mock_stdout.channel.recv_exit_status.return_value = 0

    mock_client.exec_command.return_value = (mock_stdin, mock_stdout, mock_stderr)

    exit_code = ssh_manager.execute_command("echo test")

    assert exit_code == 0
    assert mock_stdout.readlines.call_count == 1
    assert mock_stderr.readlines.call_count == 1


@patch("moondock.ssh.paramiko.SSHClient")
@patch("moondock.ssh.paramiko.RSAKey.from_private_key_file")
def test_execute_command_raw_without_connection(
    mock_rsa_key: MagicMock, mock_ssh_client: MagicMock, ssh_manager: SSHManager
) -> None:
    """Test execute_command_raw raises error when not connected."""
    with pytest.raises(RuntimeError) as exc_info:
        ssh_manager.execute_command_raw("cd /tmp && ls")

    assert "SSH connection not established" in str(exc_info.value)


@patch("moondock.ssh.paramiko.SSHClient")
@patch("moondock.ssh.paramiko.RSAKey.from_private_key_file")
def test_execute_command_raw_success(
    mock_rsa_key: MagicMock, mock_ssh_client: MagicMock, ssh_manager: SSHManager
) -> None:
    """Test execute_command_raw executes command without wrapping."""
    mock_client = MagicMock()
    mock_ssh_client.return_value = mock_client
    ssh_manager.client = mock_client

    mock_stdin = MagicMock()
    mock_stdout = MagicMock()
    mock_stderr = MagicMock()

    mock_stdout.readline.side_effect = ["output line\n", ""]
    mock_stdout.readlines.return_value = []
    mock_stderr.readline.return_value = ""
    mock_stderr.readlines.return_value = []
    mock_stdout.channel.exit_status_ready.side_effect = [False, True]
    mock_stdout.channel.recv_exit_status.return_value = 0

    mock_client.exec_command.return_value = (mock_stdin, mock_stdout, mock_stderr)

    exit_code = ssh_manager.execute_command_raw("cd /tmp && ls -la")

    assert exit_code == 0
    mock_client.exec_command.assert_called_once_with("cd /tmp && ls -la")


@patch("moondock.ssh.paramiko.SSHClient")
@patch("moondock.ssh.paramiko.RSAKey.from_private_key_file")
def test_execute_command_raw_with_keyboard_interrupt(
    mock_rsa_key: MagicMock, mock_ssh_client: MagicMock, ssh_manager: SSHManager
) -> None:
    """Test execute_command_raw handles Ctrl+C gracefully."""
    mock_client = MagicMock()
    mock_ssh_client.return_value = mock_client
    ssh_manager.client = mock_client

    mock_stdin = MagicMock()
    mock_stdout = MagicMock()
    mock_stderr = MagicMock()

    mock_stdout.readline.side_effect = KeyboardInterrupt()
    mock_client.exec_command.return_value = (mock_stdin, mock_stdout, mock_stderr)

    with pytest.raises(KeyboardInterrupt):
        ssh_manager.execute_command_raw("sleep 300")

    mock_client.close.assert_called_once()
    assert ssh_manager.client is None


def test_execute_command_raw_empty_command(ssh_manager: SSHManager) -> None:
    """Test execute_command_raw raises ValueError for empty command."""
    ssh_manager.client = MagicMock()

    with pytest.raises(ValueError) as exc_info:
        ssh_manager.execute_command_raw("")

    assert "Command cannot be empty" in str(exc_info.value)


def test_execute_command_raw_whitespace_only(ssh_manager: SSHManager) -> None:
    """Test execute_command_raw raises ValueError for whitespace-only command."""
    ssh_manager.client = MagicMock()

    with pytest.raises(ValueError) as exc_info:
        ssh_manager.execute_command_raw("   ")

    assert "Command cannot be empty" in str(exc_info.value)


def test_execute_command_raw_exceeds_max_length(ssh_manager: SSHManager) -> None:
    """Test execute_command_raw raises ValueError for commands over 10000 chars."""
    ssh_manager.client = MagicMock()
    long_command = "a" * 10001

    with pytest.raises(ValueError) as exc_info:
        ssh_manager.execute_command_raw(long_command)

    assert "exceeds maximum of 10000 characters" in str(exc_info.value)
