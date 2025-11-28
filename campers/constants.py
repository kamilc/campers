"""Global constants for campers application.

This module contains application-wide constants that are used across multiple
components. These values are provider-agnostic and suitable for any cloud provider.
"""

from enum import Enum

SYNC_TIMEOUT = 300
"""Mutagen initial sync timeout in seconds.

Five minutes allows time for large codebases to complete initial sync over SSH.
Timeout prevents indefinite hangs if sync stalls due to network or filesystem issues.
"""

WAITER_DELAY_SECONDS = 15
WAITER_MAX_ATTEMPTS_SHORT = 20
WAITER_MAX_ATTEMPTS_LONG = 40
SSH_IP_RETRY_MAX = 10
SSH_IP_RETRY_DELAY = 0.5

VERSION_CHECK_TIMEOUT_SECONDS = 5
SESSION_TERMINATE_TIMEOUT_SECONDS = 10
SSH_TEST_TIMEOUT_SECONDS = 35
MUTAGEN_CREATE_TIMEOUT_SECONDS = 120

ANSIBLE_PLAYBOOK_TIMEOUT_SECONDS = 3600

UPTIME_UPDATE_INTERVAL_SECONDS = 1.0
CTRL_C_DOUBLE_PRESS_THRESHOLD_SECONDS = 1.5

STATS_REFRESH_INTERVAL_SECONDS = 30

TERMINAL_RESPONSE_TIMEOUT_SECONDS = 0.1

SECONDS_PER_MINUTE = 60
SECONDS_PER_HOUR = 3600
SECONDS_PER_DAY = 86400
DEFAULT_NAME_COLUMN_WIDTH = 19

UPDATE_QUEUE_MAX_SIZE = 100

DEFAULT_REGION = "us-east-1"

EXIT_SUCCESS = 0
EXIT_ERROR = 1
EXIT_CONFIG_ERROR = 2


class InstanceState(str, Enum):
    """Instance state values."""

    RUNNING = "running"
    STOPPED = "stopped"
    STOPPING = "stopping"
    TERMINATED = "terminated"


class OnExitAction(str, Enum):
    """Actions to take on campers exit."""

    STOP = "stop"
    TERMINATE = "terminate"
