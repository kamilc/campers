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
"""Delay between waiter polling attempts in seconds.

Used by AWS waiters when polling for resource state changes
(e.g., waiting for instance to reach 'running' state).
"""

WAITER_MAX_ATTEMPTS_SHORT = 20
"""Maximum number of attempts for short-duration waiter operations.

Used for operations that typically complete quickly, such as
checking instance metadata availability or early-stage state transitions.
"""

WAITER_MAX_ATTEMPTS_LONG = 40
"""Maximum number of attempts for long-duration waiter operations.

Used for operations that may take longer to complete, such as
instance startup, SSH readiness, or Mutagen synchronization initialization.
"""

SSH_IP_RETRY_MAX = 10
"""Maximum number of retry attempts when fetching SSH connection details.

Retries are used when instance tags containing SSH configuration
are not immediately available, particularly in LocalStack environments.
"""

SSH_IP_RETRY_DELAY = 0.5
"""Delay in seconds between SSH connection detail retry attempts.

Provides time for instance metadata to propagate while avoiding
excessive API calls to EC2 describe operations.
"""

VERSION_CHECK_TIMEOUT_SECONDS = 5
"""Timeout in seconds for version check operations.

Prevents indefinite waits when checking tool versions (Mutagen, Ansible)
on the remote instance or local system.
"""

SESSION_TERMINATE_TIMEOUT_SECONDS = 10
"""Timeout in seconds for session termination operations.

Used when gracefully terminating SSH sessions or cleanup operations
to prevent indefinite waits on hung connections.
"""

SSH_TEST_TIMEOUT_SECONDS = 35
"""Timeout in seconds for SSH connection test operations.

Allows sufficient time for initial SSH connection establishment,
authentication, and basic command execution tests.
"""

MUTAGEN_CREATE_TIMEOUT_SECONDS = 120
"""Timeout in seconds for Mutagen session creation.

Two minutes allows time for Mutagen to establish connections and
perform initial configuration without timing out on slower networks.
"""

ANSIBLE_PLAYBOOK_TIMEOUT_SECONDS = 3600
"""Timeout in seconds for Ansible playbook execution.

One hour allows sufficient time for complex provisioning playbooks
involving software installation, compilation, and configuration.
"""

UPTIME_UPDATE_INTERVAL_SECONDS = 1.0
"""Interval in seconds for uptime update polling in TUI.

Controls refresh rate of instance uptime display in the terminal
user interface during active monitoring.
"""

CTRL_C_DOUBLE_PRESS_THRESHOLD_SECONDS = 1.5
"""Threshold in seconds for detecting double CTRL+C press.

Allows users to terminate the application by pressing CTRL+C twice
within this window, enabling graceful shutdown triggers.
"""

STATS_REFRESH_INTERVAL_SECONDS = 30
"""Interval in seconds for refreshing instance statistics.

Controls how often the TUI queries and displays updated instance
information, cost estimates, and connection status.
"""

TERMINAL_RESPONSE_TIMEOUT_SECONDS = 0.1
"""Timeout in seconds for terminal input/output operations.

Used for non-blocking reads of terminal input in the TUI to maintain
responsiveness without blocking on I/O operations.
"""

SECONDS_PER_MINUTE = 60
"""Number of seconds in one minute.

Used for time conversion and duration calculations throughout the application.
"""

SECONDS_PER_HOUR = 3600
"""Number of seconds in one hour.

Used for time conversion and duration calculations throughout the application.
"""

SECONDS_PER_DAY = 86400
"""Number of seconds in one day.

Used for time conversion and uptime calculations throughout the application.
"""

DEFAULT_NAME_COLUMN_WIDTH = 19
"""Default width in characters for instance name column in TUI.

Provides readable display of instance names in terminal output
without excessive wrapping on standard 80-column terminals.
"""

UPDATE_QUEUE_MAX_SIZE = 100
"""Maximum size of the update queue for TUI communication.

Limits memory usage and prevents unbounded queue growth when
the TUI processes updates at varying rates.
"""

DEFAULT_REGION = "us-east-1"
"""Default cloud provider region for instance provisioning.

Used when no region is specified in configuration, environment,
or command-line arguments. Standard AWS default region.
"""

MAX_COMMAND_LENGTH = 10000
"""Maximum length in characters for commands sent to remote instance.

Prevents extremely long commands that could cause issues with
shell argument parsing or remote system limitations.
"""

EXIT_SUCCESS = 0
"""Exit code indicating successful program completion.

Standard POSIX exit code returned when the application terminates
without errors.
"""

EXIT_ERROR = 1
"""Exit code indicating a general application error.

Standard POSIX exit code returned when the application encounters
an unexpected error during execution.
"""

EXIT_CONFIG_ERROR = 2
"""Exit code indicating a configuration error.

Used when the application terminates due to invalid configuration,
missing required settings, or configuration validation failures.
"""


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
