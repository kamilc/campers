"""Utility functions for campers."""

import fcntl
import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from campers.constants import (
    SECONDS_PER_MINUTE,
    SECONDS_PER_HOUR,
    SECONDS_PER_DAY,
    DEFAULT_NAME_COLUMN_WIDTH,
)


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
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
        pass

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
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
        pass

    return None


def generate_instance_name() -> str:
    """Generate deterministic instance name based on git context.

    Uses format `campers-{project}-{branch}` when in git repository.
    Falls back to `campers-{unix_timestamp}` when not in git repository.

    Returns
    -------
    str
        Instance name (sanitized for cloud provider tag compliance)
    """
    from campers.providers.aws.utils import sanitize_instance_name

    project = get_git_project_name()
    branch = get_git_branch()

    if project and branch:
        raw_name = f"campers-{project}-{branch}"
        return sanitize_instance_name(raw_name)

    return f"campers-{int(time.time())}"


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


def log_and_print_error(message: str, *args: Any) -> None:
    """Log error message and print to stderr.

    Parameters
    ----------
    message : str
        Error message with optional format placeholders
    *args : Any
        Format arguments for message
    """
    logging.error(message, *args)
    formatted_msg = message % args if args else message
    print(f"Error: {formatted_msg}", file=sys.stderr)


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


def validate_port(port: int) -> None:
    """Validate port number is in valid range.

    Parameters
    ----------
    port : int
        Port number to validate

    Raises
    ------
    ValueError
        If port is not in valid range 1-65535
    """
    if not isinstance(port, int) or port < 1 or port > 65535:
        raise ValueError(f"Port must be between 1-65535, got {port}")


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
            except Exception:
                if temp_path.exists():
                    temp_path.unlink()
                raise
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    finally:
        try:
            lock_path.unlink()
        except OSError:
            pass
