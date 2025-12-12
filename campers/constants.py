"""Global constants for campers application.

This module contains application-wide constants that are used across multiple
components. These values are provider-agnostic and suitable for any cloud provider.
"""

SYNC_TIMEOUT = 300
"""Mutagen initial sync timeout in seconds.

Five minutes allows time for large codebases to complete initial sync over SSH.
Timeout prevents indefinite hangs if sync stalls due to network or filesystem issues.
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

PRIVILEGED_PORT_THRESHOLD = 1024
"""Port number threshold for privileged ports.

Ports below this value (0-1023) require elevated privileges on Unix systems.
Used by port forwarding to detect when privilege elevation might be needed.
"""

SYNC_STATUS_POLL_INTERVAL_SECONDS = 2
"""Interval in seconds for polling sync status.

Controls how frequently Mutagen sync status is checked during initial sync.
"""

SYNC_STATUS_CHECK_TIMEOUT_SECONDS = 10
"""Timeout in seconds for sync status check operations.

Prevents indefinite waits when polling Mutagen sync status.
"""

TUI_UPDATE_INTERVAL = 0.1
"""Interval in seconds for TUI update processing.

Controls refresh rate of terminal user interface when processing updates
from background tasks and monitoring instances.
"""

MAX_UPDATES_PER_TICK = 10
"""Maximum number of updates to process per TUI tick.

Limits how many updates are processed in a single event loop iteration
to prevent UI blocking.
"""

TUI_STATUS_UPDATE_PROCESSING_DELAY = 1.0
"""Delay in seconds for status update processing in TUI.

Provides time for status changes to stabilize before updating display
to reduce unnecessary screen refreshes.
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

STATUS_UPDATE_INTERVAL_SECONDS = 10
"""Interval in seconds for CLI spinner status updates.

Controls how often the spinner message updates with elapsed time
during long-running operations like Terraform-style feedback.
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

MAX_COMMAND_LENGTH = 10000
"""Maximum length in characters for commands sent to remote instance.

Prevents extremely long commands that could cause issues with
shell argument parsing or remote system limitations.
"""

DEFAULT_SSH_PORT = 22
"""Default port number for SSH connections.

Standard SSH port used for remote shell access to instances.
"""

DEFAULT_SSH_TIMEOUT = 300.0
"""Default timeout in seconds for SSH operations.

Five minutes allows time for SSH connection establishment,
authentication, and command execution without premature timeouts.
"""

DEFAULT_CHANNEL_TIMEOUT = 1.0
"""Default timeout in seconds for SSH channel operations.

Used for individual SSH channel reads/writes to detect hung connections.
"""

DEFAULT_WAIT_TIMEOUT = 300
"""Default timeout in seconds for resource wait operations.

Five minutes allows time for resource state transitions such as
instance startup, volume attachment, or snapshot completion.
"""

CLEANUP_TIMEOUT_SECONDS = 300
"""Timeout in seconds for waiting for cleanup to start when skipping SSH.

Used by run executor to wait for cleanup manager to begin shutdown
when SSH connection is skipped.
"""

DEFAULT_PROVIDER = "aws"
"""Default cloud provider for resource provisioning.

Used as the default provider when none is specified in configuration,
environment variables, or command-line arguments.
"""

DEFAULT_SSH_USERNAME = "ubuntu"
"""Default SSH username for instances.

Used when connecting to Ubuntu-based instances. Provider-agnostic constant.
"""

SSH_RETRY_DELAYS = [1, 2, 4, 8, 16, 30, 30, 30, 30, 30]
"""Exponential backoff delays in seconds for SSH connection retries.

Provides graduated retry strategy that starts with short delays for
quick recovery from transient issues while allowing longer waits for
persistent problems without excessive retries.
"""

SENSITIVE_PATTERNS = [
    "PASSWORD",
    "SECRET",
    "TOKEN",
    "KEY",
    "PRIVATE",
]
"""Patterns used to identify sensitive data in logs for redaction.

These patterns are matched case-insensitively against log output to
identify environment variables and configuration values that should
be redacted before display to protect credentials and secrets.
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


MIN_VALID_PORT = 1
"""Minimum valid port number.

Port numbers must be >= 1 for valid network socket communication.
"""

MAX_VALID_PORT = 65535
"""Maximum valid port number.

Port numbers must be <= 65535 due to 16-bit port field limitation in TCP/UDP headers.
"""

SAFE_HOSTNAME_PATTERN = r"^[a-zA-Z0-9][a-zA-Z0-9\.\-]*$"
"""Regex pattern for validating hostnames.

Hostnames must start with alphanumeric, followed by alphanumeric, dots, or hyphens.
Prevents shell metacharacters and injection attacks when interpolating into configs.
"""

SAFE_USERNAME_PATTERN = r"^[a-zA-Z_][a-zA-Z0-9_\-]*$"
"""Regex pattern for validating SSH usernames.

Usernames must start with letter or underscore, followed by alphanumeric, underscore, or hyphen.
Prevents shell metacharacters and injection attacks in SSH configuration.
Common usernames like 'ec2-user', 'ubuntu', etc. are supported.
"""

DEFAULT_DISK_SIZE = 50
"""Default root volume size in GB for new instances.

Provides sufficient space for typical development/testing codebases and dependencies.
"""

STATUS_IN_PROGRESS = "in_progress"
"""Status value indicating cleanup operation is in progress."""

STATUS_COMPLETED = "completed"
"""Status value indicating cleanup operation completed successfully."""

STATUS_FAILED = "failed"
"""Status value indicating cleanup operation failed."""

STATUS_STOPPING = "stopping"
"""Status value indicating instance is stopping."""

STATUS_TERMINATING = "terminating"
"""Status value indicating instance is terminating."""

STREAM_TYPE_STDOUT = "stdout"
"""Stream type identifier for standard output."""

STREAM_TYPE_STDERR = "stderr"
"""Stream type identifier for standard error."""

SSH_RETRY_COUNT = 10
"""Number of retry attempts for SSH connections.

Corresponds to the length of SSH_RETRY_DELAYS constant.
"""

SSH_CONFIG_CONNECT_TIMEOUT = 30
"""SSH config ConnectTimeout value in seconds.

Controls how long SSH waits to establish initial connection to remote host.
"""

SSH_CONFIG_SERVER_ALIVE_INTERVAL = 60
"""SSH config ServerAliveInterval value in seconds.

Interval at which SSH sends keepalive messages to prevent connection timeout
due to inactivity on the network.
"""

SSH_CONFIG_SERVER_ALIVE_COUNT = 3
"""SSH config ServerAliveCountMax value.

Number of unanswered keepalive messages allowed before SSH closes the connection.
"""

PUBLIC_PORTS_DEFAULT_CIDR = "0.0.0.0/0"
"""Default CIDR block for public port access.

When public_ports are configured without an explicit CIDR restriction,
this default allows access from anywhere on the internet.
"""
