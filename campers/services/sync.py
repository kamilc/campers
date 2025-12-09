"""Mutagen bidirectional file synchronization management."""

import contextlib
import fcntl
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from campers.constants import (
    SSH_CONFIG_CONNECT_TIMEOUT,
    SSH_CONFIG_SERVER_ALIVE_COUNT,
    SSH_CONFIG_SERVER_ALIVE_INTERVAL,
    SYNC_STATUS_CHECK_TIMEOUT_SECONDS,
    SYNC_STATUS_POLL_INTERVAL_SECONDS,
)
from campers.services.validation import validate_port

logger = logging.getLogger(__name__)


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

    def _update_ssh_config_atomic(self, config_path: Path, include_line: str) -> None:
        """Atomically update SSH config with file locking.

        Prevents race conditions when multiple processes update SSH config
        concurrently by using file-level locking.

        Parameters
        ----------
        config_path : Path
            Path to SSH config file to update
        include_line : str
            Include directive line to add to config
        """
        lock_path = config_path.with_suffix(".lock")

        with open(lock_path, "w") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                if config_path.exists():
                    content = config_path.read_text()
                    if include_line not in content:
                        config_path.write_text(f"{include_line}\n\n{content}")
                        logger.debug("Added Include to %s", config_path)
                    else:
                        logger.debug("Include line already present in %s", config_path)
                else:
                    config_path.write_text(f"{include_line}\n")
                    logger.debug("Created SSH config at %s", config_path)
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

        with contextlib.suppress(OSError):
            lock_path.unlink()

    def _remove_ssh_config_include_atomic(self, config_path: Path, include_line: str) -> None:
        """Atomically remove an Include directive from SSH config with file locking.

        Parameters
        ----------
        config_path : Path
            Path to SSH config file to update
        include_line : str
            Include directive line to remove from config
        """
        if not config_path.exists():
            return

        lock_path = config_path.with_suffix(".lock")

        with open(lock_path, "w") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                content = config_path.read_text()
                if include_line in content:
                    updated_content = content.replace(f"{include_line}\n\n", "")
                    updated_content = updated_content.replace(f"{include_line}\n", "")
                    updated_content = updated_content.replace(include_line, "")
                    config_path.write_text(updated_content)
                    logger.debug("Removed Include from %s", config_path)
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

        with contextlib.suppress(OSError):
            lock_path.unlink()

    def _add_host_to_ssh_config(self, config_path: Path, host: str, host_config: str) -> None:
        """Atomically add a host entry to SSH config with file locking.

        Parameters
        ----------
        config_path : Path
            Path to SSH config file to update
        host : str
            Hostname to add (used to check if already present)
        host_config : str
            Full host configuration block to add
        """
        lock_path = config_path.with_suffix(".lock")

        with open(lock_path, "w") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                if config_path.exists():
                    content = config_path.read_text()
                    if f"Host {host}" not in content:
                        config_path.write_text(content + host_config)
                        logger.debug("Added host %s to %s", host, config_path)
                    else:
                        logger.debug("Host %s already present in %s", host, config_path)
                else:
                    config_path.write_text(host_config)
                    logger.debug("Created SSH config at %s with host %s", config_path, host)
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

        with contextlib.suppress(OSError):
            lock_path.unlink()

    def _remove_host_from_ssh_config(self, config_path: Path, host: str) -> None:
        """Atomically remove a host entry from SSH config with file locking.

        Parameters
        ----------
        config_path : Path
            Path to SSH config file to update
        host : str
            Hostname to remove
        """
        if not config_path.exists():
            return

        lock_path = config_path.with_suffix(".lock")

        with open(lock_path, "w") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                content = config_path.read_text()
                if f"Host {host}" in content:
                    updated_content = re.sub(
                        rf"\nHost {re.escape(host)}\n(    [^\n]+\n)*",
                        "",
                        content,
                    )
                    config_path.write_text(updated_content)
                    logger.debug("Removed host %s from %s", host, config_path)
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

        with contextlib.suppress(OSError):
            lock_path.unlink()

    def check_mutagen_installed(self) -> None:
        """Check if mutagen is installed locally.

        Raises
        ------
        RuntimeError
            If mutagen is not installed or not found in PATH

        Notes
        -----
        Test harness can set CAMPERS_MUTAGEN_NOT_INSTALLED=1 to simulate
        mutagen not being installed (needed for subprocess-based BDD tests
        where mocking is not possible).
        """
        try:
            from tests.harness.services.sync import should_skip_mutagen_installation_check

            if should_skip_mutagen_installation_check():
                raise RuntimeError(
                    "Mutagen is not installed locally.\n"
                    "Please install Mutagen to use campers file synchronization.\n"
                    "Visit: https://github.com/mutagen-io/mutagen"
                )
        except ImportError:
            pass

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

        except FileNotFoundError as e:
            raise RuntimeError(
                "Mutagen is not installed locally.\n"
                "Please install Mutagen to use campers file synchronization.\n"
                "Visit: https://github.com/mutagen-io/mutagen"
            ) from e

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
            logger.warning("Failed to cleanup orphaned session %s: %s", session_name, e)

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
        ssh_port: int = 22,
    ) -> None:
        """Create Mutagen sync session.

        Parameters
        ----------
        session_name : str
            Unique name for sync session (e.g., campers-1234567890)
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
        ssh_port : int
            SSH port for remote host (default: 22)

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

        local = str(Path(local_path).expanduser().resolve())
        remote = f"{username}@{host}:{remote_path}"

        cmd.append(local)
        cmd.append(remote)

        key_path = str(Path(key_file).expanduser().resolve())

        try:
            with open(key_path) as f:
                key_content = f.read()
        except (OSError, FileNotFoundError, PermissionError) as e:
            logger.error("Failed to read SSH key file: %s", e)
            raise RuntimeError(f"Failed to read SSH key file {key_path}: {e}") from e

        validate_port(ssh_port)

        if ssh_wrapper_dir is None:
            ssh_wrapper_dir = tempfile.gettempdir()

        campers_ssh_dir = Path(ssh_wrapper_dir).resolve()
        campers_ssh_dir.mkdir(parents=True, exist_ok=True)

        temp_key_path = campers_ssh_dir / f"campers-key-{session_name}.pem"

        try:
            fd = os.open(
                str(temp_key_path),
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
        except FileExistsError:
            temp_key_path.unlink()
            fd = os.open(
                str(temp_key_path),
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
        with os.fdopen(fd, "w") as f:
            f.write(key_content)

        host_config = f"""
Host {host}
    HostName {host}
    Port {ssh_port}
    User {username}
    IdentityFile {str(temp_key_path.resolve())}
    IdentitiesOnly yes
    StrictHostKeyChecking accept-new
    ConnectTimeout {SSH_CONFIG_CONNECT_TIMEOUT}
    ServerAliveInterval {SSH_CONFIG_SERVER_ALIVE_INTERVAL}
    ServerAliveCountMax {SSH_CONFIG_SERVER_ALIVE_COUNT}
"""

        user_ssh_config = Path.home() / ".ssh" / "config"
        user_ssh_config.parent.mkdir(parents=True, exist_ok=True)

        campers_dir = Path(os.environ.get("CAMPERS_DIR", str(Path.home() / ".campers")))
        campers_ssh_config = campers_dir / "ssh" / "config"
        campers_ssh_config.parent.mkdir(parents=True, exist_ok=True)

        master_include_line = f"Include {campers_ssh_config}"

        try:
            try:
                self._update_ssh_config_atomic(user_ssh_config, master_include_line)
                self._add_host_to_ssh_config(campers_ssh_config, host, host_config)
            except (PermissionError, OSError) as e:
                logger.error("Failed to update SSH config: %s", e)
                raise RuntimeError(f"Failed to update SSH config at {user_ssh_config}: {e}") from e

            logger.debug("SSH config for host %s:\n%s", host, host_config.strip())

            ssh_path = shutil.which("ssh")
            if not ssh_path:
                raise RuntimeError("ssh not found. Please install OpenSSH or add it to your PATH.")

            add_host_cmd = [
                ssh_path,
                "-F",
                str(campers_ssh_config),
                "-o",
                "IdentitiesOnly=yes",
                "-i",
                str(temp_key_path.resolve()),
                f"{username}@{host}",
                "echo",
                "SSH_OK",
            ]
            logger.debug("Testing SSH connection: %s", " ".join(add_host_cmd))

            ssh_env = os.environ.copy()
            ssh_env.pop("SSH_AUTH_SOCK", None)
            ssh_env["MUTAGEN_SSH_CONFIG"] = str(campers_ssh_config)
            ssh_env["MUTAGEN_SSH_ARGS"] = (
                "-oIdentitiesOnly=yes "
                "-oStrictHostKeyChecking=accept-new "
                "-oUserKnownHostsFile=/dev/null "
                f"-i {str(temp_key_path.resolve())}"
            )

            try:
                host_result = subprocess.run(
                    add_host_cmd,
                    capture_output=True,
                    text=True,
                    timeout=35,
                    env=ssh_env,
                )
                logger.debug("SSH test exit code: %d", host_result.returncode)

                if host_result.returncode == 0:
                    logger.debug("SSH connection verified successfully")
                else:
                    logger.warning(
                        "SSH test failed (exit %d): %s",
                        host_result.returncode,
                        host_result.stderr,
                    )
            except subprocess.TimeoutExpired:
                logger.warning("SSH connection test timed out")
            except (FileNotFoundError, subprocess.SubprocessError) as e:
                logger.warning("SSH connection test failed: %s", e)

            logger.debug("Mutagen create command: %s", " ".join(cmd))

            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=120,
                    env=ssh_env,
                )
            except subprocess.TimeoutExpired as e:
                logger.error("Mutagen sync create timed out after 120 seconds")
                if hasattr(e, "stdout") and e.stdout:
                    logger.error("Partial stdout: %s", e.stdout)
                if hasattr(e, "stderr") and e.stderr:
                    logger.error("Partial stderr: %s", e.stderr)
                raise RuntimeError(
                    "Mutagen sync create timed out after 120 seconds. "
                    "The remote instance may not be ready or there may be network issues."
                ) from e

            logger.debug("Mutagen create exit code: %d", result.returncode)
            if result.stdout:
                logger.debug("Mutagen stdout: %s", result.stdout)
            if result.stderr:
                logger.debug("Mutagen stderr: %s", result.stderr)

            if result.returncode != 0:
                raise RuntimeError(f"Failed to create Mutagen sync session: {result.stderr}")
        except (
            RuntimeError,
            subprocess.TimeoutExpired,
            FileNotFoundError,
            subprocess.SubprocessError,
        ):
            with contextlib.suppress(OSError):
                temp_key_path.unlink()
            raise

    def get_sync_status(self, session_name: str) -> str:
        """Get the current sync status from Mutagen.

        Extracts the "Status:" line from mutagen sync list output and
        combines it with "Staged entries:" information if available.

        Parameters
        ----------
        session_name : str
            Name of sync session to query

        Returns
        -------
        str
            Formatted status string (e.g., "Watching for changes" or
            "Staging files on beta (Staged entries (alpha): 45)")
            Returns "Unknown" if the status cannot be determined.
        """
        try:
            result = subprocess.run(
                ["mutagen", "sync", "list", session_name],
                capture_output=True,
                text=True,
                timeout=SYNC_STATUS_CHECK_TIMEOUT_SECONDS,
            )

            if result.returncode != 0:
                return "Unknown"

            status_line = None
            entries_line = None

            for line in result.stdout.split("\n"):
                stripped = line.strip()
                if stripped.startswith("Status:"):
                    status_line = stripped.replace("Status:", "").strip()
                elif stripped.startswith("Staged entries") and entries_line is None:
                    entries_line = stripped

            if status_line:
                if entries_line:
                    return f"{status_line} ({entries_line})"
                return status_line

            return "Unknown"

        except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError):
            return "Unknown"

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
            f"Mutagen sync timed out after {timeout} seconds. Initial sync did not complete."
        )

    def terminate_session(
        self,
        session_name: str,
        ssh_wrapper_dir: str | None = None,
        host: str | None = None,
    ) -> None:
        """Terminate Mutagen sync session.

        Parameters
        ----------
        session_name : str
            Name of session to terminate
        ssh_wrapper_dir : str | None
            Directory where SSH key was created
        host : str | None
            Remote host to remove from SSH config
        """

        try:
            subprocess.run(
                ["mutagen", "sync", "terminate", session_name],
                capture_output=True,
                timeout=10,
            )
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError) as e:
            logger.warning("Failed to terminate Mutagen session %s: %s", session_name, e)

        if ssh_wrapper_dir is None:
            ssh_wrapper_dir = tempfile.gettempdir()

        campers_ssh_dir = Path(ssh_wrapper_dir)
        temp_key_path = campers_ssh_dir / f"campers-key-{session_name}.pem"

        try:
            if temp_key_path.exists():
                temp_key_path.unlink()
                logger.debug("Removed SSH key file: %s", temp_key_path)
        except OSError as e:
            logger.warning("Failed to remove SSH key file: %s", e)

        campers_dir = Path(os.environ.get("CAMPERS_DIR", str(Path.home() / ".campers")))
        campers_ssh_config = campers_dir / "ssh" / "config"

        if host:
            try:
                self._remove_host_from_ssh_config(campers_ssh_config, host)
            except OSError as e:
                logger.warning("Failed to cleanup SSH config: %s", e)

        self._cleanup_ssh_include_if_empty(campers_ssh_config)

    def _cleanup_ssh_include_if_empty(self, campers_ssh_config: Path) -> None:
        """Clean up empty campers SSH config file.

        The master Include line in ~/.ssh/config is kept permanent.
        This method only removes the campers SSH config file if it's empty.

        Parameters
        ----------
        campers_ssh_config : Path
            Path to the campers SSH config file (~/.campers/ssh/config)
        """
        if not campers_ssh_config.exists():
            return

        try:
            content = campers_ssh_config.read_text().strip()

            if not content or "Host " not in content:
                with contextlib.suppress(OSError):
                    campers_ssh_config.unlink()
                    logger.debug("Removed empty campers SSH config: %s", campers_ssh_config)
        except OSError:
            pass
