"""Tests for Mutagen sync management."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from campers.services.sync import MutagenManager


@pytest.fixture
def mutagen_manager():
    """Fixture to create MutagenManager instance.

    Yields
    ------
    MutagenManager
        Instance of MutagenManager for testing
    """
    return MutagenManager()


@pytest.fixture
def temp_ssh_setup(tmp_path):
    """Fixture to create temporary SSH key and directory for testing.

    Parameters
    ----------
    tmp_path : pathlib.Path
        Pytest temporary directory fixture

    Yields
    ------
    dict
        Dictionary with 'key_file' and 'ssh_dir' paths
    """

    temp_key = tmp_path / "test.pem"
    temp_key.write_text("-----BEGIN RSA PRIVATE KEY-----\ntest\n-----END RSA PRIVATE KEY-----\n")
    temp_key.chmod(0o600)

    temp_ssh_dir = tmp_path / "ssh"
    temp_ssh_dir.mkdir()

    return {
        "key_file": str(temp_key),
        "ssh_dir": str(temp_ssh_dir),
    }


def test_check_mutagen_installed_success(mutagen_manager) -> None:
    """Test successful mutagen installation check."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)

        mutagen_manager.check_mutagen_installed()

        mock_run.assert_called_once_with(
            ["mutagen", "version"], capture_output=True, text=True, timeout=5
        )


def test_check_mutagen_not_installed(mutagen_manager) -> None:
    """Test error when mutagen is not installed."""
    with patch("campers.services.sync.subprocess.run", side_effect=FileNotFoundError):
        with pytest.raises(
            RuntimeError,
            match="Mutagen is not installed locally",
        ):
            mutagen_manager.check_mutagen_installed()


def test_check_mutagen_returns_error(mutagen_manager) -> None:
    """Test error when mutagen command returns non-zero exit code."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1)

        with pytest.raises(
            RuntimeError,
            match="Mutagen is installed but returned an error",
        ):
            mutagen_manager.check_mutagen_installed()


def test_cleanup_orphaned_session_exists(mutagen_manager) -> None:
    """Test cleanup when orphaned session exists."""
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = [
            MagicMock(returncode=0),
            MagicMock(returncode=0),
        ]

        mutagen_manager.cleanup_orphaned_session("campers-123")

        assert mock_run.call_count == 2
        mock_run.assert_any_call(
            ["mutagen", "sync", "list", "campers-123"],
            capture_output=True,
            timeout=5,
        )
        mock_run.assert_any_call(
            ["mutagen", "sync", "terminate", "campers-123"],
            capture_output=True,
            timeout=10,
        )


def test_cleanup_orphaned_session_not_exists(mutagen_manager) -> None:
    """Test cleanup when no orphaned session exists."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1)

        mutagen_manager.cleanup_orphaned_session("campers-123")

        mock_run.assert_called_once_with(
            ["mutagen", "sync", "list", "campers-123"],
            capture_output=True,
            timeout=5,
        )


def test_cleanup_orphaned_session_error_ignored(mutagen_manager) -> None:
    """Test cleanup ignores errors gracefully."""
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("mutagen", 5)):
        mutagen_manager.cleanup_orphaned_session("campers-123")


def test_create_sync_session_minimal(mutagen_manager, temp_ssh_setup) -> None:
    """Test creating sync session with minimal configuration."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)

        mutagen_manager.create_sync_session(
            session_name="campers-123",
            local_path="~/myproject",
            remote_path="~/myproject",
            host="203.0.113.1",
            key_file=temp_ssh_setup["key_file"],
            username="ubuntu",
            ssh_wrapper_dir=temp_ssh_setup["ssh_dir"],
        )

        assert mock_run.called
        call_args_list = [call[0][0] for call in mock_run.call_args_list]

        mutagen_cmd = next((cmd for cmd in call_args_list if cmd[0] == "mutagen"), None)
        assert mutagen_cmd is not None
        assert mutagen_cmd[1] == "sync"
        assert mutagen_cmd[2] == "create"
        assert "--name" in mutagen_cmd
        assert "campers-123" in mutagen_cmd
        assert "--sync-mode" in mutagen_cmd
        assert "two-way-resolved" in mutagen_cmd
        assert "--ignore" in mutagen_cmd
        assert ".git" in mutagen_cmd
        assert ".gitignore" in mutagen_cmd


def test_create_sync_session_with_ignore_patterns(mutagen_manager, temp_ssh_setup) -> None:
    """Test creating sync session with ignore patterns."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)

        mutagen_manager.create_sync_session(
            session_name="campers-123",
            local_path="~/myproject",
            remote_path="~/myproject",
            host="203.0.113.1",
            key_file=temp_ssh_setup["key_file"],
            username="ubuntu",
            ssh_wrapper_dir=temp_ssh_setup["ssh_dir"],
            ignore_patterns=["*.pyc", "__pycache__"],
        )

        call_args_list = [call[0][0] for call in mock_run.call_args_list]
        mutagen_cmd = next((cmd for cmd in call_args_list if cmd[0] == "mutagen"), None)

        assert "*.pyc" in mutagen_cmd
        assert "__pycache__" in mutagen_cmd


def test_create_sync_session_with_include_vcs(mutagen_manager, temp_ssh_setup) -> None:
    """Test creating sync session with VCS included."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)

        mutagen_manager.create_sync_session(
            session_name="campers-123",
            local_path="~/myproject",
            remote_path="~/myproject",
            host="203.0.113.1",
            key_file=temp_ssh_setup["key_file"],
            username="ubuntu",
            ssh_wrapper_dir=temp_ssh_setup["ssh_dir"],
            include_vcs=True,
        )

        call_args_list = [call[0][0] for call in mock_run.call_args_list]
        mutagen_cmd = next((cmd for cmd in call_args_list if cmd[0] == "mutagen"), None)

        assert ".git" not in mutagen_cmd
        assert ".gitignore" not in mutagen_cmd


def test_create_sync_session_failure(mutagen_manager, temp_ssh_setup) -> None:
    """Test creating sync session failure."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stderr="sync session creation failed")

        with pytest.raises(RuntimeError, match="Failed to create Mutagen sync session"):
            mutagen_manager.create_sync_session(
                session_name="campers-123",
                local_path="~/myproject",
                remote_path="~/myproject",
                host="203.0.113.1",
                key_file=temp_ssh_setup["key_file"],
                username="ubuntu",
                ssh_wrapper_dir=temp_ssh_setup["ssh_dir"],
            )


def test_wait_for_initial_sync_success(mutagen_manager) -> None:
    """Test waiting for initial sync completion."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="Status: Watching for changes")

        mutagen_manager.wait_for_initial_sync("campers-123", timeout=10)

        mock_run.assert_called_with(
            ["mutagen", "sync", "list", "campers-123"],
            capture_output=True,
            text=True,
            timeout=10,
        )


def test_wait_for_initial_sync_timeout(mutagen_manager) -> None:
    """Test waiting for initial sync timeout."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="Status: Connecting")

        with patch("time.sleep"):
            with pytest.raises(RuntimeError, match="Mutagen sync timed out"):
                mutagen_manager.wait_for_initial_sync("campers-123", timeout=1)


def test_wait_for_initial_sync_check_failure(mutagen_manager) -> None:
    """Test waiting for initial sync when status check fails."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stderr="session not found", text=True)

        with pytest.raises(RuntimeError, match="Failed to check sync status"):
            mutagen_manager.wait_for_initial_sync("campers-123", timeout=10)


def test_terminate_session_success(mutagen_manager) -> None:
    """Test successful session termination."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)

        mutagen_manager.terminate_session("campers-123")

        mock_run.assert_called_once_with(
            ["mutagen", "sync", "terminate", "campers-123"],
            capture_output=True,
            timeout=10,
        )


def test_terminate_session_error_ignored(mutagen_manager) -> None:
    """Test session termination ignores errors."""
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("mutagen", 10)):
        mutagen_manager.terminate_session("campers-123")


def test_create_sync_session_invalid_username(mutagen_manager) -> None:
    """Test creating sync session with invalid username."""
    with pytest.raises(ValueError, match="Invalid SSH username"):
        mutagen_manager.create_sync_session(
            session_name="campers-123",
            local_path="~/myproject",
            remote_path="~/myproject",
            host="203.0.113.1",
            key_file="/tmp/test.pem",
            username="invalid@user",
        )


def test_create_sync_session_invalid_host(mutagen_manager) -> None:
    """Test creating sync session with invalid host format."""
    with pytest.raises(ValueError, match="Invalid host"):
        mutagen_manager.create_sync_session(
            session_name="campers-123",
            local_path="~/myproject",
            remote_path="~/myproject",
            host="invalid@host",
            key_file="/tmp/test.pem",
            username="ubuntu",
        )
