"""Unit tests for session file infrastructure."""

import errno
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pytest

from campers.session import SessionInfo, SessionManager


@pytest.fixture
def temp_sessions_dir() -> TemporaryDirectory:
    """Create a temporary directory for session files.

    Returns
    -------
    TemporaryDirectory
        Temporary directory context manager
    """
    return TemporaryDirectory()


@pytest.fixture
def session_manager(temp_sessions_dir: TemporaryDirectory) -> SessionManager:
    """Create a SessionManager with a temporary directory.

    Parameters
    ----------
    temp_sessions_dir : TemporaryDirectory
        Temporary directory for session files

    Returns
    -------
    SessionManager
        Configured SessionManager instance
    """
    return SessionManager(sessions_dir=Path(temp_sessions_dir.name))


@pytest.fixture
def session_info() -> SessionInfo:
    """Create a sample SessionInfo dataclass.

    Returns
    -------
    SessionInfo
        Sample session information
    """
    return SessionInfo(
        camp_name="dev",
        pid=os.getpid(),
        instance_id="i-0abc123def456",
        region="us-east-1",
        ssh_host="54.23.45.67",
        ssh_port=22,
        ssh_user="ubuntu",
        key_file="/home/user/.campers/keys/id_rsa",
    )


class TestSessionInfoDataclass:
    """Tests for SessionInfo dataclass."""

    def test_session_info_creation(self) -> None:
        """Test SessionInfo instantiation with all fields."""
        info = SessionInfo(
            camp_name="test",
            pid=12345,
            instance_id="i-test",
            region="us-west-2",
            ssh_host="192.168.1.1",
            ssh_port=2222,
            ssh_user="ec2-user",
            key_file="/path/to/key",
        )

        assert info.camp_name == "test"
        assert info.pid == 12345
        assert info.instance_id == "i-test"
        assert info.region == "us-west-2"
        assert info.ssh_host == "192.168.1.1"
        assert info.ssh_port == 2222
        assert info.ssh_user == "ec2-user"
        assert info.key_file == "/path/to/key"

    def test_session_info_field_types(self) -> None:
        """Test SessionInfo field type validation."""
        info = SessionInfo(
            camp_name="dev",
            pid=99999,
            instance_id="i-xyz",
            region="eu-west-1",
            ssh_host="10.0.0.1",
            ssh_port=22,
            ssh_user="admin",
            key_file="/tmp/key.pem",
        )

        assert isinstance(info.camp_name, str)
        assert isinstance(info.pid, int)
        assert isinstance(info.instance_id, str)
        assert isinstance(info.region, str)
        assert isinstance(info.ssh_host, str)
        assert isinstance(info.ssh_port, int)
        assert isinstance(info.ssh_user, str)
        assert isinstance(info.key_file, str)


class TestSessionManagerInitialization:
    """Tests for SessionManager initialization."""

    def test_session_manager_with_custom_dir(self, temp_sessions_dir: TemporaryDirectory) -> None:
        """Test SessionManager initialization with custom directory."""
        custom_dir = Path(temp_sessions_dir.name)
        manager = SessionManager(sessions_dir=custom_dir)

        assert manager._sessions_dir == custom_dir

    def test_session_manager_default_dir_using_campers_dir_env(self) -> None:
        """Test SessionManager uses CAMPERS_DIR environment variable."""
        with TemporaryDirectory() as temp_dir:
            os.environ["CAMPERS_DIR"] = temp_dir
            try:
                manager = SessionManager()
                assert manager._sessions_dir == Path(temp_dir) / "sessions"
            finally:
                del os.environ["CAMPERS_DIR"]

    def test_session_manager_default_dir_home_fallback(self) -> None:
        """Test SessionManager falls back to ~/.campers/sessions."""
        old_env = os.environ.get("CAMPERS_DIR")
        try:
            if "CAMPERS_DIR" in os.environ:
                del os.environ["CAMPERS_DIR"]

            manager = SessionManager()
            expected_path = Path.home() / ".campers" / "sessions"
            assert manager._sessions_dir == expected_path
        finally:
            if old_env is not None:
                os.environ["CAMPERS_DIR"] = old_env


class TestCreateSession:
    """Tests for SessionManager.create_session."""

    def test_create_session_success(
        self,
        session_manager: SessionManager,
        session_info: SessionInfo,
        temp_sessions_dir: TemporaryDirectory,
    ) -> None:
        """Test successful session file creation."""
        session_manager.create_session(session_info)

        session_file = Path(temp_sessions_dir.name) / "dev.session.json"
        assert session_file.exists()

    def test_create_session_creates_directory_if_missing(
        self, temp_sessions_dir: TemporaryDirectory, session_info: SessionInfo
    ) -> None:
        """Test that create_session creates the directory if it doesn't exist."""
        nonexistent_dir = Path(temp_sessions_dir.name) / "nonexistent"
        manager = SessionManager(sessions_dir=nonexistent_dir)

        manager.create_session(session_info)

        assert nonexistent_dir.exists()
        assert (nonexistent_dir / "dev.session.json").exists()

    def test_create_session_writes_valid_json(
        self,
        session_manager: SessionManager,
        session_info: SessionInfo,
        temp_sessions_dir: TemporaryDirectory,
    ) -> None:
        """Test that session file contains valid JSON."""
        session_manager.create_session(session_info)

        session_file = Path(temp_sessions_dir.name) / "dev.session.json"
        with open(session_file) as f:
            data = json.load(f)

        assert data["camp_name"] == "dev"
        assert data["pid"] == os.getpid()
        assert data["instance_id"] == "i-0abc123def456"

    def test_create_session_contains_all_fields(
        self,
        session_manager: SessionManager,
        session_info: SessionInfo,
        temp_sessions_dir: TemporaryDirectory,
    ) -> None:
        """Test that session file contains all required fields."""
        session_manager.create_session(session_info)

        session_file = Path(temp_sessions_dir.name) / "dev.session.json"
        with open(session_file) as f:
            data = json.load(f)

        required_fields = {
            "camp_name",
            "pid",
            "instance_id",
            "region",
            "ssh_host",
            "ssh_port",
            "ssh_user",
            "key_file",
        }
        assert set(data.keys()) == required_fields

    def test_create_session_overwrites_existing(
        self, session_manager: SessionManager, temp_sessions_dir: TemporaryDirectory
    ) -> None:
        """Test that creating session overwrites existing file."""
        info1 = SessionInfo(
            camp_name="dev",
            pid=11111,
            instance_id="i-111",
            region="us-east-1",
            ssh_host="1.1.1.1",
            ssh_port=22,
            ssh_user="ubuntu",
            key_file="/tmp/key1",
        )
        info2 = SessionInfo(
            camp_name="dev",
            pid=22222,
            instance_id="i-222",
            region="us-west-1",
            ssh_host="2.2.2.2",
            ssh_port=2222,
            ssh_user="ec2-user",
            key_file="/tmp/key2",
        )

        session_manager.create_session(info1)
        session_manager.create_session(info2)

        session_file = Path(temp_sessions_dir.name) / "dev.session.json"
        with open(session_file) as f:
            data = json.load(f)

        assert data["pid"] == 22222
        assert data["instance_id"] == "i-222"

    def test_create_session_atomic_write(
        self, session_manager: SessionManager, session_info: SessionInfo
    ) -> None:
        """Test that session file is written atomically using temp file."""
        with patch("campers.session.os.rename") as mock_rename:
            session_manager.create_session(session_info)

            mock_rename.assert_called_once()
            call_args = mock_rename.call_args
            target_path = str(call_args[0][1])
            assert target_path.endswith("dev.session.json")


class TestReadSession:
    """Tests for SessionManager.read_session."""

    def test_read_session_success(
        self, session_manager: SessionManager, session_info: SessionInfo
    ) -> None:
        """Test successful session file read."""
        session_manager.create_session(session_info)
        result = session_manager.read_session("dev")

        assert result is not None
        assert isinstance(result, SessionInfo)
        assert result.camp_name == "dev"
        assert result.pid == os.getpid()

    def test_read_session_missing_file(self, session_manager: SessionManager) -> None:
        """Test read_session returns None for missing file."""
        result = session_manager.read_session("nonexistent")

        assert result is None

    def test_read_session_malformed_json(
        self, session_manager: SessionManager, temp_sessions_dir: TemporaryDirectory
    ) -> None:
        """Test read_session returns None for malformed JSON."""
        session_file = Path(temp_sessions_dir.name) / "bad.session.json"
        session_file.write_text("{ invalid json }")

        result = session_manager.read_session("bad")

        assert result is None

    def test_read_session_missing_fields(
        self, session_manager: SessionManager, temp_sessions_dir: TemporaryDirectory
    ) -> None:
        """Test read_session returns None when required fields are missing."""
        session_file = Path(temp_sessions_dir.name) / "incomplete.session.json"
        incomplete_data = {"camp_name": "test", "pid": 12345}
        session_file.write_text(json.dumps(incomplete_data))

        result = session_manager.read_session("incomplete")

        assert result is None

    def test_read_session_deserializes_all_fields(
        self, session_manager: SessionManager, session_info: SessionInfo
    ) -> None:
        """Test that all fields are correctly deserialized."""
        session_manager.create_session(session_info)
        result = session_manager.read_session("dev")

        assert result.camp_name == session_info.camp_name
        assert result.pid == session_info.pid
        assert result.instance_id == session_info.instance_id
        assert result.region == session_info.region
        assert result.ssh_host == session_info.ssh_host
        assert result.ssh_port == session_info.ssh_port
        assert result.ssh_user == session_info.ssh_user
        assert result.key_file == session_info.key_file


class TestDeleteSession:
    """Tests for SessionManager.delete_session."""

    def test_delete_session_success(
        self,
        session_manager: SessionManager,
        session_info: SessionInfo,
        temp_sessions_dir: TemporaryDirectory,
    ) -> None:
        """Test successful session file deletion."""
        session_manager.create_session(session_info)
        session_manager.delete_session("dev")

        session_file = Path(temp_sessions_dir.name) / "dev.session.json"
        assert not session_file.exists()

    def test_delete_session_nonexistent_file(self, session_manager: SessionManager) -> None:
        """Test delete_session doesn't raise error for missing file."""
        session_manager.delete_session("nonexistent")

    def test_delete_session_handles_race_condition(
        self, session_manager: SessionManager, session_info: SessionInfo
    ) -> None:
        """Test delete_session handles TOCTOU race condition."""
        session_manager.create_session(session_info)

        with patch.object(Path, "unlink") as mock_unlink:
            mock_unlink.side_effect = FileNotFoundError()
            session_manager.delete_session("dev")


class TestIsSessionAlive:
    """Tests for SessionManager.is_session_alive."""

    def test_is_session_alive_with_running_process(
        self, session_manager: SessionManager, session_info: SessionInfo
    ) -> None:
        """Test is_session_alive returns True for running process."""
        session_manager.create_session(session_info)
        result = session_manager.is_session_alive("dev")

        assert result is True

    def test_is_session_alive_missing_file(self, session_manager: SessionManager) -> None:
        """Test is_session_alive returns False for missing session file."""
        result = session_manager.is_session_alive("nonexistent")

        assert result is False

    def test_is_session_alive_dead_pid(
        self, session_manager: SessionManager, session_info: SessionInfo
    ) -> None:
        """Test is_session_alive returns False for dead process."""
        info = SessionInfo(
            camp_name="dev",
            pid=99999,
            instance_id="i-test",
            region="us-east-1",
            ssh_host="1.1.1.1",
            ssh_port=22,
            ssh_user="ubuntu",
            key_file="/tmp/key",
        )
        session_manager.create_session(info)

        result = session_manager.is_session_alive("dev")

        assert result is False

    def test_is_session_alive_deletes_stale_file(
        self, session_manager: SessionManager, temp_sessions_dir: TemporaryDirectory
    ) -> None:
        """Test is_session_alive deletes stale session file when process is dead."""
        info = SessionInfo(
            camp_name="dev",
            pid=99999,
            instance_id="i-test",
            region="us-east-1",
            ssh_host="1.1.1.1",
            ssh_port=22,
            ssh_user="ubuntu",
            key_file="/tmp/key",
        )
        session_manager.create_session(info)

        session_manager.is_session_alive("dev")

        session_file = Path(temp_sessions_dir.name) / "dev.session.json"
        assert not session_file.exists()


class TestGetAliveSession:
    """Tests for SessionManager.get_alive_session."""

    def test_get_alive_session_running_process(
        self, session_manager: SessionManager, session_info: SessionInfo
    ) -> None:
        """Test get_alive_session returns SessionInfo for running process."""
        session_manager.create_session(session_info)
        result = session_manager.get_alive_session("dev")

        assert result is not None
        assert isinstance(result, SessionInfo)
        assert result.camp_name == "dev"
        assert result.pid == os.getpid()

    def test_get_alive_session_missing_file(self, session_manager: SessionManager) -> None:
        """Test get_alive_session returns None for missing file."""
        result = session_manager.get_alive_session("nonexistent")

        assert result is None

    def test_get_alive_session_dead_pid(
        self, session_manager: SessionManager, session_info: SessionInfo
    ) -> None:
        """Test get_alive_session returns None for dead process."""
        info = SessionInfo(
            camp_name="dev",
            pid=99999,
            instance_id="i-test",
            region="us-east-1",
            ssh_host="1.1.1.1",
            ssh_port=22,
            ssh_user="ubuntu",
            key_file="/tmp/key",
        )
        session_manager.create_session(info)

        result = session_manager.get_alive_session("dev")

        assert result is None

    def test_get_alive_session_deletes_stale_file(
        self, session_manager: SessionManager, temp_sessions_dir: TemporaryDirectory
    ) -> None:
        """Test get_alive_session deletes stale file when process is dead."""
        info = SessionInfo(
            camp_name="dev",
            pid=99999,
            instance_id="i-test",
            region="us-east-1",
            ssh_host="1.1.1.1",
            ssh_port=22,
            ssh_user="ubuntu",
            key_file="/tmp/key",
        )
        session_manager.create_session(info)

        session_manager.get_alive_session("dev")

        session_file = Path(temp_sessions_dir.name) / "dev.session.json"
        assert not session_file.exists()


class TestIsProcessAlive:
    """Tests for SessionManager._is_process_alive."""

    def test_is_process_alive_current_process(self, session_manager: SessionManager) -> None:
        """Test _is_process_alive returns True for current process."""
        result = session_manager._is_process_alive(os.getpid())

        assert result is True

    def test_is_process_alive_invalid_pid(self, session_manager: SessionManager) -> None:
        """Test _is_process_alive returns False for non-existent PID."""
        result = session_manager._is_process_alive(99999)

        assert result is False

    def test_is_process_alive_esrch_error(self, session_manager: SessionManager) -> None:
        """Test _is_process_alive handles ESRCH error (no such process)."""
        with patch("campers.session.os.kill") as mock_kill:
            err = OSError()
            err.errno = errno.ESRCH
            mock_kill.side_effect = err

            result = session_manager._is_process_alive(99999)

            assert result is False

    def test_is_process_alive_eperm_error(self, session_manager: SessionManager) -> None:
        """Test _is_process_alive handles EPERM error (permission denied)."""
        with patch("campers.session.os.kill") as mock_kill:
            err = OSError()
            err.errno = errno.EPERM
            mock_kill.side_effect = err

            result = session_manager._is_process_alive(1)

            assert result is True

    def test_is_process_alive_reraises_unknown_error(self, session_manager: SessionManager) -> None:
        """Test _is_process_alive re-raises unknown OSError."""
        with patch("campers.session.os.kill") as mock_kill:
            err = OSError()
            err.errno = errno.EIO
            mock_kill.side_effect = err

            with pytest.raises(OSError):
                session_manager._is_process_alive(1)


class TestCAMPERS_DIREnvironmentVariable:
    """Tests for CAMPERS_DIR environment variable handling."""

    def test_respects_campers_dir_env_variable(self) -> None:
        """Test that SessionManager respects CAMPERS_DIR environment variable."""
        with TemporaryDirectory() as temp_dir:
            os.environ["CAMPERS_DIR"] = temp_dir
            try:
                manager = SessionManager()
                expected_path = Path(temp_dir) / "sessions"
                assert manager._sessions_dir == expected_path
            finally:
                del os.environ["CAMPERS_DIR"]

    def test_creates_session_in_campers_dir(self) -> None:
        """Test that session file is created in CAMPERS_DIR/sessions."""
        with TemporaryDirectory() as temp_dir:
            os.environ["CAMPERS_DIR"] = temp_dir
            try:
                manager = SessionManager()
                info = SessionInfo(
                    camp_name="test",
                    pid=os.getpid(),
                    instance_id="i-test",
                    region="us-east-1",
                    ssh_host="1.1.1.1",
                    ssh_port=22,
                    ssh_user="ubuntu",
                    key_file="/tmp/key",
                )
                manager.create_session(info)

                expected_file = Path(temp_dir) / "sessions" / "test.session.json"
                assert expected_file.exists()
            finally:
                del os.environ["CAMPERS_DIR"]
