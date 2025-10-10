"""Mutagen bidirectional file synchronization management."""

import logging
import os
import re
import shlex
import shutil
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
        ssh_wrapper_dir: str | None = None,
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
        ssh_wrapper_dir : str | None
            Directory to create SSH wrapper script in

        Raises
        ------
        RuntimeError
            If session creation fails
        """
        import tempfile
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

        local = str(Path(local_path).expanduser().resolve())
        remote = f"{username}@{host}:{remote_path}"

        cmd.append(local)
        cmd.append(remote)

        key_path = str(Path(key_file).expanduser())

        with open(key_path, "r") as f:
            key_content = f.read()

        if ssh_wrapper_dir is None:
            ssh_wrapper_dir = tempfile.gettempdir()

        moondock_ssh_dir = Path(ssh_wrapper_dir)
        moondock_ssh_dir.mkdir(parents=True, exist_ok=True)

        temp_key_path = moondock_ssh_dir / f"moondock-key-{session_name}.pem"
        with open(temp_key_path, "w") as f:
            f.write(key_content)
        os.chmod(temp_key_path, 0o600)

        moondock_config_path = moondock_ssh_dir / "moondock-ssh-config"

        host_config = f"""
Host {host}
    HostName {host}
    User {username}
    IdentityFile {temp_key_path}
    IdentitiesOnly yes
    StrictHostKeyChecking accept-new
    ConnectTimeout 30
    ServerAliveInterval 60
    ServerAliveCountMax 3
"""

        if moondock_config_path.exists():
            with open(moondock_config_path, "r") as f:
                existing_config = f.read()
            if f"Host {host}" not in existing_config:
                with open(moondock_config_path, "a") as f:
                    f.write(host_config)
                logger.debug("Appended host config to %s", moondock_config_path)
            else:
                logger.debug("Host %s already in config", host)
        else:
            with open(moondock_config_path, "w") as f:
                f.write(host_config)
            logger.debug("Created SSH config at %s", moondock_config_path)

        user_ssh_config = Path.home() / ".ssh" / "config"
        user_ssh_config.parent.mkdir(parents=True, exist_ok=True)
        include_line = f"Include {moondock_config_path}"

        if user_ssh_config.exists():
            with open(user_ssh_config, "r") as f:
                user_config_content = f.read()
        else:
            user_config_content = ""

        if include_line not in user_config_content:
            with open(user_ssh_config, "w") as f:
                f.write(f"{include_line}\n\n{user_config_content}")
            logger.debug("Added Include to %s", user_ssh_config)

        logger.debug("SSH config for host %s:\n%s", host, host_config.strip())

        ssh_path = shutil.which("ssh")
        if not ssh_path:
            raise RuntimeError("ssh not found. Please install OpenSSH or add it to your PATH.")

        add_host_cmd = [ssh_path, f"{username}@{host}", "echo", "SSH_OK"]
        logger.debug("Testing SSH connection: %s", " ".join(add_host_cmd))

        try:
            host_result = subprocess.run(
                add_host_cmd, capture_output=True, text=True, timeout=35
            )
            logger.debug("SSH test exit code: %d", host_result.returncode)

            if host_result.returncode == 0:
                logger.debug("SSH connection verified successfully")
            else:
                logger.warning("SSH test failed (exit %d): %s", host_result.returncode, host_result.stderr)
        except subprocess.TimeoutExpired:
            logger.warning("SSH connection test timed out")

        logger.debug("Mutagen create command: %s", " ".join(cmd))

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120
            )
        except subprocess.TimeoutExpired as e:
            logger.error("Mutagen sync create timed out after 120 seconds")
            if hasattr(e, 'stdout') and e.stdout:
                logger.error("Partial stdout: %s", e.stdout)
            if hasattr(e, 'stderr') and e.stderr:
                logger.error("Partial stderr: %s", e.stderr)
            raise RuntimeError(
                "Mutagen sync create timed out after 120 seconds. "
                "The remote instance may not be ready or there may be network issues."
            )

        logger.debug("Mutagen create exit code: %d", result.returncode)
        if result.stdout:
            logger.debug("Mutagen stdout: %s", result.stdout)
        if result.stderr:
            logger.debug("Mutagen stderr: %s", result.stderr)

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

    def terminate_session(
        self, session_name: str, ssh_wrapper_dir: str | None = None, host: str | None = None
    ) -> None:
        """Terminate Mutagen sync session.

        Parameters
        ----------
        session_name : str
            Name of session to terminate
        ssh_wrapper_dir : str | None
            Directory where SSH config was created
        host : str | None
            Remote host to remove from SSH config
        """
        import re
        import tempfile
        try:
            subprocess.run(
                ["mutagen", "sync", "terminate", session_name],
                capture_output=True,
                timeout=10,
            )
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError) as e:
            logger.warning(f"Failed to terminate Mutagen session {session_name}: {e}")

        if ssh_wrapper_dir is None:
            ssh_wrapper_dir = tempfile.gettempdir()

        moondock_ssh_dir = Path(ssh_wrapper_dir)
        temp_key_path = moondock_ssh_dir / f"moondock-key-{session_name}.pem"
        moondock_config_path = moondock_ssh_dir / "moondock-ssh-config"

        try:
            if temp_key_path.exists():
                temp_key_path.unlink()
                logger.debug("Removed SSH key file: %s", temp_key_path)
        except OSError as e:
            logger.warning(f"Failed to remove SSH key file: {e}")

        if host and moondock_config_path.exists():
            try:
                with open(moondock_config_path, "r") as f:
                    config_content = f.read()

                if f"Host {host}" in config_content:
                    updated_config = re.sub(
                        rf"\nHost {re.escape(host)}\n(    [^\n]+\n)*",
                        "",
                        config_content
                    )
                    with open(moondock_config_path, "w") as f:
                        f.write(updated_config)
                    logger.debug("Removed host %s from SSH config", host)
            except OSError as e:
                logger.warning(f"Failed to cleanup SSH config: {e}")
