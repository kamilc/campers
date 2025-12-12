"""Test harness for sync service."""

from __future__ import annotations

import os


def should_skip_mutagen_installation_check() -> bool:
    """Check if mutagen installation check should be skipped for testing.

    This allows BDD tests to simulate mutagen not being installed without
    needing to mock the subprocess module, which is needed for subprocess-based
    BDD tests where mocking is not possible.

    Returns
    -------
    bool
        True if CAMPERS_MUTAGEN_NOT_INSTALLED environment variable is set to '1'
    """
    return os.environ.get("CAMPERS_MUTAGEN_NOT_INSTALLED") == "1"
