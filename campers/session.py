"""Session file infrastructure for caching instance SSH connection details.

This module provides fast instance discovery via session files with PID-based
liveness checking, eliminating the need for AWS API calls on subsequent attempts
to connect to a running instance.
"""

import contextlib
import errno
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class SessionInfo:
    """Information about a running campers session.

    This dataclass stores SSH connection details for a running instance
    along with the process ID of the campers run process that created it.

    Attributes
    ----------
    camp_name : str
        Name of the camp configuration.
    pid : int
        Process ID of the campers run process managing this instance.
    instance_id : str
        AWS EC2 instance ID.
    region : str
        AWS region where the instance runs.
    ssh_host : str
        IP address or hostname for SSH connection.
    ssh_port : int
        SSH port number.
    ssh_user : str
        SSH username for remote authentication.
    key_file : str
        Path to SSH private key file.
    """

    camp_name: str
    pid: int
    instance_id: str
    region: str
    ssh_host: str
    ssh_port: int
    ssh_user: str
    key_file: str


class SessionManager:
    """Manages session files for running instances.

    Provides methods to create, read, delete, and check the liveness of
    session files. Uses PID-based checking to determine if a session is
    still valid and auto-cleans stale session files.
    """

    def __init__(self, sessions_dir: Path | None = None) -> None:
        """Initialize SessionManager with optional custom sessions directory.

        Parameters
        ----------
        sessions_dir : Path | None
            Custom directory for session files. If None, uses
            $CAMPERS_DIR/sessions/ or ~/.campers/sessions/
        """
        if sessions_dir is None:
            campers_dir = Path(os.environ.get("CAMPERS_DIR", str(Path.home() / ".campers")))
            sessions_dir = campers_dir / "sessions"
        self._sessions_dir = sessions_dir

    def create_session(self, session_info: SessionInfo) -> None:
        """Create a new session file.

        Writes the session file atomically using a temporary file and rename
        to prevent partial reads by other processes.

        Parameters
        ----------
        session_info : SessionInfo
            Session information to persist.

        Raises
        ------
        OSError
            If the session directory cannot be created or file cannot be written.
        """
        self._sessions_dir.mkdir(parents=True, exist_ok=True)
        session_file = self._sessions_dir / f"{session_info.camp_name}.session.json"

        data = asdict(session_info)

        fd, temp_path = tempfile.mkstemp(dir=self._sessions_dir, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, indent=2)
            os.rename(temp_path, session_file)
        except Exception:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise

    def read_session(self, camp_name: str) -> SessionInfo | None:
        """Read a session file and return SessionInfo.

        Parameters
        ----------
        camp_name : str
            Name of the camp configuration.

        Returns
        -------
        SessionInfo | None
            SessionInfo if file exists and is valid, None otherwise.
        """
        session_file = self._sessions_dir / f"{camp_name}.session.json"
        if not session_file.exists():
            return None
        try:
            with open(session_file) as f:
                data = json.load(f)
            return SessionInfo(**data)
        except (json.JSONDecodeError, TypeError, KeyError, ValueError):
            return None

    def delete_session(self, camp_name: str) -> None:
        """Delete a session file.

        Parameters
        ----------
        camp_name : str
            Name of the camp configuration.
        """
        session_file = self._sessions_dir / f"{camp_name}.session.json"
        with contextlib.suppress(FileNotFoundError):
            session_file.unlink()

    def is_session_alive(self, camp_name: str) -> bool:
        """Check if a session is alive by verifying the PID is still running.

        Automatically deletes stale session files when the process is found
        to be no longer running.

        Parameters
        ----------
        camp_name : str
            Name of the camp configuration.

        Returns
        -------
        bool
            True if session file exists and process is alive, False otherwise.
        """
        session = self.read_session(camp_name)
        if session is None:
            return False
        if not self._is_process_alive(session.pid):
            self.delete_session(camp_name)
            return False
        return True

    def get_alive_session(self, camp_name: str) -> SessionInfo | None:
        """Get a session if it exists and the process is alive.

        Automatically deletes stale session files when the process is found
        to be no longer running.

        Parameters
        ----------
        camp_name : str
            Name of the camp configuration.

        Returns
        -------
        SessionInfo | None
            SessionInfo if session exists and process is alive, None otherwise.
        """
        session = self.read_session(camp_name)
        if session is None:
            return None
        if not self._is_process_alive(session.pid):
            self.delete_session(camp_name)
            return None
        return session

    def _is_process_alive(self, pid: int) -> bool:
        """Check if a process with the given PID is running.

        Uses os.kill(pid, 0) to check process existence without sending a signal.

        Parameters
        ----------
        pid : int
            Process ID to check.

        Returns
        -------
        bool
            True if process exists, False otherwise.

        Raises
        ------
        OSError
            If os.kill raises an unexpected OSError.
        """
        try:
            os.kill(pid, 0)
            return True
        except OSError as err:
            if err.errno == errno.ESRCH:
                return False
            elif err.errno == errno.EPERM:
                return True
            raise
