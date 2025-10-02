"""Mutagen bidirectional file synchronization management."""

import logging
import os
import re
import shlex
import subprocess
import time
from pathlib import Path

logger = logging.getLogger(__name__)

SYNC_STATUS_POLL_INTERVAL_SECONDS = 2
SYNC_STATUS_CHECK_TIMEOUT_SECONDS = 10


class MutagenManager:
    """Manages Mutagen bidirectional file synchronization.

    This class provides methods to check for Mutagen installation, create
    sync sessions, monitor sync status, and clean up sessions. It handles
    SSH-based synchronization between local and remote EC2 instances.

    Methods
    -------
    check_mutagen_installed()
        Verify that Mutagen is installed locally
    cleanup_orphaned_session(session_name: str)
        Remove any existing session from crashed previous run
    create_sync_session(...)
        Create new Mutagen sync session with specified configuration
    wait_for_initial_sync(session_name: str, timeout: int = 300)
        Wait for initial sync to complete (reach "watching" state)
    terminate_session(session_name: str)
        Terminate and remove sync session
    """

    def __init__(self) -> None:
        """Initialize MutagenManager."""
        pass

    def check_mutagen_installed(self) -> None:
        """Check if mutagen is installed locally.

        Raises
        ------
        RuntimeError
            If mutagen is not installed or not found in PATH

        Notes
        -----
        Environment variable MOONDOCK_MUTAGEN_NOT_INSTALLED=1 can be set in BDD
        tests to simulate mutagen not being installed (needed for subprocess-based
        BDD tests where mocking is not possible).
        """
        if os.environ.get("MOONDOCK_MUTAGEN_NOT_INSTALLED") == "1":
            raise RuntimeError(
                "Mutagen is not installed locally.\n"
                "Please install Mutagen to use moondock file synchronization.\n"
                "Visit: https://github.com/mutagen-io/mutagen"
            )

        try:
            result = subprocess.run(
                ["mutagen", "version"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode != 0:
                raise RuntimeError(
                    "Mutagen is installed but returned an error. "
                    "Please check your Mutagen installation.\n"
                    "Visit: https://github.com/mutagen-io/mutagen"
                )

        except FileNotFoundError:
            raise RuntimeError(
                "Mutagen is not installed locally.\n"
                "Please install Mutagen to use moondock file synchronization.\n"
                "Visit: https://github.com/mutagen-io/mutagen"
            )

    def cleanup_orphaned_session(self, session_name: str) -> None:
        """Clean up orphaned session if it exists from previous crashed run.

        Parameters
        ----------
        session_name : str
            Name of potentially orphaned session
        """
        try:
            result = subprocess.run(
                ["mutagen", "sync", "list", session_name],
                capture_output=True,
                timeout=5,
            )

            if result.returncode == 0:
                subprocess.run(
                    ["mutagen", "sync", "terminate", session_name],
                    capture_output=True,
                    timeout=10,
                )
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError) as e:
            logger.warning(f"Failed to cleanup orphaned session {session_name}: {e}")

    def create_sync_session(
        self,
        session_name: str,
        local_path: str,
        remote_path: str,
        host: str,
        key_file: str,
        username: str,
        ignore_patterns: list[str] | None = None,
        include_vcs: bool = False,
    ) -> None:
        """Create Mutagen sync session.

        Parameters
        ----------
        session_name : str
            Unique name for sync session (e.g., moondock-1234567890)
        local_path : str
            Local directory path to sync
        remote_path : str
            Remote directory path on EC2 instance
        host : str
            Remote host IP address
        key_file : str
            Path to SSH private key file
        username : str
            SSH username (e.g., ubuntu)
        ignore_patterns : list[str] | None
            File patterns to ignore (e.g., *.pyc, __pycache__)
        include_vcs : bool
            Whether to include version control files (.git, etc.)

        Raises
        ------
        RuntimeError
            If session creation fails
        """
        cmd = [
            "mutagen",
            "sync",
            "create",
            "--name",
            session_name,
            "--sync-mode",
            "two-way-resolved",
        ]

        if ignore_patterns:
            for pattern in ignore_patterns:
                cmd.extend(["--ignore", pattern])

        if not include_vcs:
            cmd.extend(
                [
                    "--ignore",
                    ".git",
                    "--ignore",
                    ".gitignore",
                    "--ignore",
                    ".svn",
                ]
            )

        if not re.match(r"^[a-zA-Z0-9._-]+$", username):
            raise ValueError(f"Invalid SSH username: {username}")

        if not re.match(r"^[\w.-]+$", host):
            raise ValueError(f"Invalid host: {host}")

        local = str(Path(local_path).expanduser())
        remote = f"{username}@{host}:{remote_path}"

        cmd.append(local)
        cmd.append(remote)

        env = os.environ.copy()
        env["SSH_AUTH_SOCK"] = os.environ.get("SSH_AUTH_SOCK", "")

        key_path = str(Path(key_file).expanduser())
        ssh_command = (
            f"ssh -i {shlex.quote(key_path)} -o StrictHostKeyChecking=accept-new"
        )
        env["MUTAGEN_SSH_COMMAND"] = ssh_command

        result = subprocess.run(cmd, capture_output=True, text=True, env=env)

        if result.returncode != 0:
            raise RuntimeError(
                f"Failed to create Mutagen sync session: {result.stderr}"
            )

    def wait_for_initial_sync(self, session_name: str, timeout: int = 300) -> None:
        """Wait for Mutagen initial sync to complete.

        Parameters
        ----------
        session_name : str
            Name of sync session to monitor
        timeout : int
            Timeout in seconds (default: 300 = 5 minutes)

        Raises
        ------
        RuntimeError
            If sync times out or fails
        """
        start_time = time.time()

        while time.time() - start_time < timeout:
            result = subprocess.run(
                ["mutagen", "sync", "list", session_name],
                capture_output=True,
                text=True,
                timeout=SYNC_STATUS_CHECK_TIMEOUT_SECONDS,
            )

            if result.returncode != 0:
                raise RuntimeError(f"Failed to check sync status: {result.stderr}")

            if "watching" in result.stdout.lower():
                return

            time.sleep(SYNC_STATUS_POLL_INTERVAL_SECONDS)

        raise RuntimeError(
            f"Mutagen sync timed out after {timeout} seconds. "
            "Initial sync did not complete."
        )

    def terminate_session(self, session_name: str) -> None:
        """Terminate Mutagen sync session.

        Parameters
        ----------
        session_name : str
            Name of session to terminate
        """
        try:
            subprocess.run(
                ["mutagen", "sync", "terminate", session_name],
                capture_output=True,
                timeout=10,
            )
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError) as e:
            logger.warning(f"Failed to terminate Mutagen session {session_name}: {e}")
