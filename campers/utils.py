"""Utility functions for campers."""

import fcntl
import logging
import os
import subprocess
import threading
import time
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from rich.console import Console

from campers.constants import (
    DEFAULT_NAME_COLUMN_WIDTH,
    SECONDS_PER_DAY,
    SECONDS_PER_HOUR,
    SECONDS_PER_MINUTE,
    STATUS_UPDATE_INTERVAL_SECONDS,
)

logger = logging.getLogger(__name__)


def get_git_project_name() -> str | None:
    """Detect project name from git remote URL or directory name.

    Attempts to extract project name from git remote.origin.url.
    Falls back to directory name if git remote unavailable.
    Returns None if not in a git repository.

    Returns
    -------
    str | None
        Project name extracted from git remote, directory name, or None
    """
    try:
        result = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )

        if result.returncode == 0:
            url = result.stdout.strip()
            if url:
                project = url.split("/")[-1]
                if project.endswith(".git"):
                    project = project[:-4]

                if not project:
                    logging.debug(
                        "Could not extract project name from git remote, using directory name"
                    )
                    return os.path.basename(os.getcwd())

                return project
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError) as e:
        logging.debug("Could not detect git project name: %s", e)

    return os.path.basename(os.getcwd())


def get_git_branch() -> str | None:
    """Detect current git branch.

    Returns None for detached HEAD state or if not in a git repository.

    Returns
    -------
    str | None
        Current branch name, or None for detached HEAD or non-git directory
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )

        if result.returncode == 0:
            branch = result.stdout.strip()
            if branch and branch != "HEAD":
                return branch
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError) as e:
        logging.debug("Could not detect git branch: %s", e)

    return None


def get_user_identity() -> str:
    """Get user identity for ownership tagging.

    Returns git email if available, falls back to $USER, then "unknown".
    Result is sanitized for AWS tag compliance (max 256 chars).

    Returns
    -------
    str
        User identity string suitable for AWS tags.
    """
    identity = None

    try:
        result = subprocess.run(
            ["git", "config", "user.email"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )

        if result.returncode == 0 and result.stdout.strip():
            identity = result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    if not identity:
        identity = os.environ.get("USER", "unknown")

    return identity[:256]


def generate_instance_name(camp_name: str | None = None) -> str:
    """Generate deterministic instance name based on git context.

    Uses format `campers-{project}-{branch}-{camp_name}` when in git repository
    and camp_name is provided. Uses format `campers-{project}-{branch}` when in
    git repository but camp_name is not provided. Falls back to `campers-{unix_timestamp}`
    when not in git repository.

    Parameters
    ----------
    camp_name : str | None
        Optional camp name to include in the instance name

    Returns
    -------
    str
        Instance name (sanitized for cloud provider tag compliance)
    """
    from campers.providers.aws.utils import sanitize_instance_name

    project = get_git_project_name()
    branch = get_git_branch()

    if project and branch:
        if camp_name:
            raw_name = f"campers-{project}-{branch}-{camp_name}"
        else:
            raw_name = f"campers-{project}-{branch}"
        return sanitize_instance_name(raw_name)

    return f"campers-{int(time.time() * 1000000)}"


def format_time_ago(dt: datetime) -> str:
    """Format datetime as human-readable time ago.

    Parameters
    ----------
    dt : datetime
        Datetime to format (timezone-aware)

    Returns
    -------
    str
        Human-readable time string (e.g., "2h ago", "30m ago", "5d ago")

    Raises
    ------
    ValueError
        If dt is not timezone-aware or if dt is in the future
    """
    if dt.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")

    now = datetime.now(dt.tzinfo)
    delta = now - dt

    if delta.total_seconds() < 0:
        raise ValueError("datetime cannot be in the future")

    if delta.total_seconds() < SECONDS_PER_MINUTE:
        return "just now"
    elif delta.total_seconds() < SECONDS_PER_HOUR:
        minutes = int(delta.total_seconds() / SECONDS_PER_MINUTE)
        return f"{minutes}m ago"
    elif delta.total_seconds() < SECONDS_PER_DAY:
        hours = int(delta.total_seconds() / SECONDS_PER_HOUR)
        return f"{hours}h ago"
    else:
        days = int(delta.total_seconds() / SECONDS_PER_DAY)
        return f"{days}d ago"


def truncate_name(name: str, max_width: int = DEFAULT_NAME_COLUMN_WIDTH) -> str:
    """Truncate name to fit in column width.

    Parameters
    ----------
    name : str
        Name to truncate
    max_width : int
        Maximum width for name (default: DEFAULT_NAME_COLUMN_WIDTH)

    Returns
    -------
    str
        Truncated name with ellipsis if exceeds max_width, otherwise original name
    """
    if len(name) > max_width:
        return name[: max_width - 3] + "..."

    return name


def atomic_file_write(path: Path, content: str) -> None:
    """Write file atomically using temp file and rename with file locking.

    Uses exclusive file locking to prevent concurrent access during write.
    Writes to temporary file and renames to target atomically.

    Parameters
    ----------
    path : Path
        Target file path
    content : str
        File content to write

    Raises
    ------
    Exception
        Propagates any exception from write operation after cleanup
    """
    temp_path = path.with_suffix(".tmp")
    lock_path = path.with_suffix(".lock")

    try:
        with open(lock_path, "w") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                with open(temp_path, "w") as f:
                    f.write(content)
                temp_path.rename(path)
            except OSError:
                if temp_path.exists():
                    temp_path.unlink()
                raise
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    finally:
        try:
            lock_path.unlink()
        except FileNotFoundError:
            logger.debug("Lock file already deleted: %s", lock_path)
        except OSError as e:
            logger.debug("Failed to delete lock file %s: %s", lock_path, e)


@contextmanager
def status_spinner(
    message: str,
    use_logging: bool = False,
) -> Generator[None, None, None]:
    """Context manager for CLI status with Terraform-style elapsed time updates.

    Shows immediate feedback and updates the message every
    STATUS_UPDATE_INTERVAL_SECONDS with elapsed time.

    Parameters
    ----------
    message : str
        Initial status message to display (e.g., "Finding instance")
    use_logging : bool
        If True, use logging.info() for status updates (for TUI mode).
        If False (default), use Rich spinner (for CLI mode).

    Yields
    ------
    None
        Control returns to caller while status runs.

    Examples
    --------
    >>> with status_spinner("Finding instance"):
    ...     slow_operation()
    # CLI mode shows: ⠋ Finding instance...
    # After 10s: ⠙ Still finding instance... (10s)

    >>> with status_spinner("Finding instance", use_logging=True):
    ...     slow_operation()
    # TUI mode logs: Finding instance...
    # After 10s logs: Still finding instance... (10s)
    """
    start_time = time.time()
    stop_event = threading.Event()

    if use_logging:
        logging.info("%s...", message)

        def log_updates() -> None:
            while not stop_event.wait(STATUS_UPDATE_INTERVAL_SECONDS):
                elapsed = int(time.time() - start_time)
                logging.info("Still %s... (%ds)", message.lower(), elapsed)

        update_thread = threading.Thread(target=log_updates, daemon=True)

        try:
            update_thread.start()
            yield
        finally:
            stop_event.set()
            update_thread.join(timeout=1.0)
    else:
        console = Console()
        status_handle = console.status(f"{message}...", spinner="dots")

        def update_spinner() -> None:
            while not stop_event.wait(STATUS_UPDATE_INTERVAL_SECONDS):
                elapsed = int(time.time() - start_time)
                status_handle.update(f"Still {message.lower()}... ({elapsed}s)")

        update_thread = threading.Thread(target=update_spinner, daemon=True)

        try:
            status_handle.start()
            update_thread.start()
            yield
        finally:
            stop_event.set()
            status_handle.stop()
            update_thread.join(timeout=1.0)
