"""Global constants for campers application.

This module contains application-wide constants that are used across multiple
components. These values are provider-agnostic and suitable for any cloud provider.
"""

SYNC_TIMEOUT = 300
"""Mutagen initial sync timeout in seconds.

Five minutes allows time for large codebases to complete initial sync over SSH.
Timeout prevents indefinite hangs if sync stalls due to network or filesystem issues.
"""
