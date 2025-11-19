"""Utility functions for moondock."""

import logging
import os
import re
import subprocess
import time
from datetime import datetime


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


def sanitize_instance_name(name: str) -> str:
    """Sanitize instance name for AWS tag compliance.

    Applies AWS tag value rules:
    - Convert to lowercase
    - Replace forward slashes with dashes
    - Remove invalid characters (keep only a-z, 0-9, dash)
    - Remove consecutive dashes
    - Trim leading/trailing dashes
    - Limit to 256 characters (AWS tag value limit)

    Parameters
    ----------
    name : str
        Instance name to sanitize

    Returns
    -------
    str
        Sanitized instance name
    """
    name = name.lower()
    name = name.replace("/", "-")
    name = re.sub(r"[^a-z0-9\-]", "-", name)
    name = re.sub(r"-+", "-", name)
    name = name.strip("-")
    return name[:256]


def generate_instance_name() -> str:
    """Generate deterministic instance name based on git context.

    Uses format `moondock-{project}-{branch}` when in git repository.
    Falls back to `moondock-{unix_timestamp}` when not in git repository.

    Returns
    -------
    str
        Instance name (sanitized for AWS tag compliance)
    """
    project = get_git_project_name()
    branch = get_git_branch()

    if project and branch:
        raw_name = f"moondock-{project}-{branch}"
        return sanitize_instance_name(raw_name)

    return f"moondock-{int(time.time())}"


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

    if delta.total_seconds() < 60:
        return "just now"
    elif delta.total_seconds() < 3600:
        minutes = int(delta.total_seconds() / 60)
        return f"{minutes}m ago"
    elif delta.total_seconds() < 86400:
        hours = int(delta.total_seconds() / 3600)
        return f"{hours}h ago"
    else:
        days = int(delta.total_seconds() / 86400)
        return f"{days}d ago"
