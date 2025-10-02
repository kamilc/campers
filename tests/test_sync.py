"""Tests for Mutagen sync management."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from moondock.sync import MutagenManager


@pytest.fixture
def mutagen_manager():
    """Fixture to create MutagenManager instance.

    Yields
    ------
    MutagenManager
        Instance of MutagenManager for testing
    """
    return MutagenManager()


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
    with patch("moondock.sync.subprocess.run", side_effect=FileNotFoundError):
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

        mutagen_manager.cleanup_orphaned_session("moondock-123")

        assert mock_run.call_count == 2
        mock_run.assert_any_call(
            ["mutagen", "sync", "list", "moondock-123"],
            capture_output=True,
            timeout=5,
        )
        mock_run.assert_any_call(
            ["mutagen", "sync", "terminate", "moondock-123"],
            capture_output=True,
            timeout=10,
        )


def test_cleanup_orphaned_session_not_exists(mutagen_manager) -> None:
    """Test cleanup when no orphaned session exists."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1)

        mutagen_manager.cleanup_orphaned_session("moondock-123")

        mock_run.assert_called_once_with(
            ["mutagen", "sync", "list", "moondock-123"],
            capture_output=True,
            timeout=5,
        )


def test_cleanup_orphaned_session_error_ignored(mutagen_manager) -> None:
    """Test cleanup ignores errors gracefully."""
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("mutagen", 5)):
        mutagen_manager.cleanup_orphaned_session("moondock-123")


def test_create_sync_session_minimal(mutagen_manager) -> None:
    """Test creating sync session with minimal configuration."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)

        mutagen_manager.create_sync_session(
            session_name="moondock-123",
            local_path="~/myproject",
            remote_path="~/myproject",
            host="203.0.113.1",
            key_file="/tmp/test.pem",
            username="ubuntu",
        )

        mock_run.assert_called_once()
        call_args = mock_run.call_args
        cmd = call_args[0][0]

        assert cmd[0] == "mutagen"
        assert cmd[1] == "sync"
        assert cmd[2] == "create"
        assert "--name" in cmd
        assert "moondock-123" in cmd
        assert "--sync-mode" in cmd
        assert "two-way-resolved" in cmd
        assert "--ignore" in cmd
        assert ".git" in cmd
        assert ".gitignore" in cmd


def test_create_sync_session_with_ignore_patterns(mutagen_manager) -> None:
    """Test creating sync session with ignore patterns."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)

        mutagen_manager.create_sync_session(
            session_name="moondock-123",
            local_path="~/myproject",
            remote_path="~/myproject",
            host="203.0.113.1",
            key_file="/tmp/test.pem",
            username="ubuntu",
            ignore_patterns=["*.pyc", "__pycache__"],
        )

        call_args = mock_run.call_args
        cmd = call_args[0][0]

        assert "*.pyc" in cmd
        assert "__pycache__" in cmd


def test_create_sync_session_with_include_vcs(mutagen_manager) -> None:
    """Test creating sync session with VCS included."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)

        mutagen_manager.create_sync_session(
            session_name="moondock-123",
            local_path="~/myproject",
            remote_path="~/myproject",
            host="203.0.113.1",
            key_file="/tmp/test.pem",
            username="ubuntu",
            include_vcs=True,
        )

        call_args = mock_run.call_args
        cmd = call_args[0][0]

        assert ".git" not in cmd
        assert ".gitignore" not in cmd


def test_create_sync_session_failure(mutagen_manager) -> None:
    """Test creating sync session failure."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=1, stderr="sync session creation failed"
        )

        with pytest.raises(RuntimeError, match="Failed to create Mutagen sync session"):
            mutagen_manager.create_sync_session(
                session_name="moondock-123",
                local_path="~/myproject",
                remote_path="~/myproject",
                host="203.0.113.1",
                key_file="/tmp/test.pem",
                username="ubuntu",
            )


def test_wait_for_initial_sync_success(mutagen_manager) -> None:
    """Test waiting for initial sync completion."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0, stdout="Status: Watching for changes"
        )

        mutagen_manager.wait_for_initial_sync("moondock-123", timeout=10)

        mock_run.assert_called_with(
            ["mutagen", "sync", "list", "moondock-123"],
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
                mutagen_manager.wait_for_initial_sync("moondock-123", timeout=1)


def test_wait_for_initial_sync_check_failure(mutagen_manager) -> None:
    """Test waiting for initial sync when status check fails."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=1, stderr="session not found", text=True
        )

        with pytest.raises(RuntimeError, match="Failed to check sync status"):
            mutagen_manager.wait_for_initial_sync("moondock-123", timeout=10)


def test_terminate_session_success(mutagen_manager) -> None:
    """Test successful session termination."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)

        mutagen_manager.terminate_session("moondock-123")

        mock_run.assert_called_once_with(
            ["mutagen", "sync", "terminate", "moondock-123"],
            capture_output=True,
            timeout=10,
        )


def test_terminate_session_error_ignored(mutagen_manager) -> None:
    """Test session termination ignores errors."""
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("mutagen", 10)):
        mutagen_manager.terminate_session("moondock-123")


def test_create_sync_session_invalid_username(mutagen_manager) -> None:
    """Test creating sync session with invalid username."""
    with pytest.raises(ValueError, match="Invalid SSH username"):
        mutagen_manager.create_sync_session(
            session_name="moondock-123",
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
            session_name="moondock-123",
            local_path="~/myproject",
            remote_path="~/myproject",
            host="invalid@host",
            key_file="/tmp/test.pem",
            username="ubuntu",
        )
