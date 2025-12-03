"""AWS-specific constants for EC2 and pricing operations.

This module contains constants specific to AWS cloud provider operations,
including EC2 instance management and pricing information.
"""

from enum import Enum

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

TAG_FETCH_RETRY_MAX = 150
"""Maximum number of retry attempts when fetching instance tags.

Used when polling for EC2 instance tags that may not be immediately
available after instance creation, particularly in LocalStack environments.
"""

TAG_FETCH_RETRY_DELAY = 0.1
"""Delay in seconds between tag fetch retry attempts.

Short delay for rapid polling when waiting for tags to propagate.
Combined with TAG_FETCH_RETRY_MAX, provides up to 15 seconds of polling.
"""

DEFAULT_REGION = "us-east-1"
"""Default AWS region for instance provisioning.

Used when no region is specified in configuration, environment,
or command-line arguments.
"""

UUID_SLICE_LENGTH = 8
"""Number of characters from UUID to use in instance names.

When generating instance names from UUIDs, use the first 8 characters
to create a reasonably unique identifier while keeping names reasonably short.
"""

ACTIVE_INSTANCE_STATES = [
    "pending",
    "running",
    "stopping",
    "stopped",
]
"""EC2 instance states considered active (not terminated).

These states represent instances that still exist and can potentially be
reused or modified. Terminated instances are excluded.
"""

VALID_INSTANCE_TYPES = frozenset(
    (
        "t2.micro",
        "t2.small",
        "t2.medium",
        "t2.large",
        "t2.xlarge",
        "t2.2xlarge",
        "t3.micro",
        "t3.small",
        "t3.medium",
        "t3.large",
        "t3.xlarge",
        "t3.2xlarge",
        "t3a.micro",
        "t3a.small",
        "t3a.medium",
        "t3a.large",
        "t3a.xlarge",
        "t3a.2xlarge",
        "m5.large",
        "m5.xlarge",
        "m5.2xlarge",
        "m5.4xlarge",
        "m5.8xlarge",
        "m5.12xlarge",
        "m5.16xlarge",
        "m5.24xlarge",
        "m5a.large",
        "m5a.xlarge",
        "m5a.2xlarge",
        "m5a.4xlarge",
        "m5a.8xlarge",
        "m5a.12xlarge",
        "m5a.16xlarge",
        "m5a.24xlarge",
        "c5.large",
        "c5.xlarge",
        "c5.2xlarge",
        "c5.4xlarge",
        "c5.9xlarge",
        "c5.12xlarge",
        "c5.18xlarge",
        "c5.24xlarge",
        "r5.large",
        "r5.xlarge",
        "r5.2xlarge",
        "r5.4xlarge",
        "r5.8xlarge",
        "r5.12xlarge",
        "r5.16xlarge",
        "r5.24xlarge",
    )
)
"""Supported EC2 instance types.

Includes burstable (t2, t3, t3a) and general-purpose (m5, m5a) instance families,
as well as compute-optimized (c5) and memory-optimized (r5) families.
Only instances tested and approved for use with campers are included.
"""

PRICING_API_REGION = "us-east-1"
"""AWS region where the Pricing API is available.

The AWS Pricing API is only available in us-east-1 region.
Pricing queries for any region must use this endpoint.
"""

REGION_TO_LOCATION = {
    "us-east-1": "US East (N. Virginia)",
    "us-east-2": "US East (Ohio)",
    "us-west-1": "US West (N. California)",
    "us-west-2": "US West (Oregon)",
    "eu-west-1": "EU (Ireland)",
    "eu-west-2": "EU (London)",
    "eu-west-3": "EU (Paris)",
    "eu-central-1": "EU (Frankfurt)",
    "eu-north-1": "EU (Stockholm)",
    "eu-south-1": "EU (Milan)",
    "ap-northeast-1": "Asia Pacific (Tokyo)",
    "ap-northeast-2": "Asia Pacific (Seoul)",
    "ap-northeast-3": "Asia Pacific (Osaka)",
    "ap-southeast-1": "Asia Pacific (Singapore)",
    "ap-southeast-2": "Asia Pacific (Sydney)",
    "ap-south-1": "Asia Pacific (Mumbai)",
    "sa-east-1": "South America (Sao Paulo)",
    "ca-central-1": "Canada (Central)",
    "me-south-1": "Middle East (Bahrain)",
    "af-south-1": "Africa (Cape Town)",
}
"""Mapping of AWS region identifiers to location names.

Maps regional codes (e.g., 'us-east-1') to human-readable location
descriptions used in pricing API responses and user-facing output.
"""


DEFAULT_INSTANCE_TYPE = "t3.medium"
"""Default EC2 instance type for new instances.

Provides good balance between cost and performance for development/testing workloads.
"""

SSH_SECURITY_GROUP_DEFAULT_CIDR = "0.0.0.0/0"
"""Default CIDR block for SSH security group when none specified.

Allows SSH access from any IP address. Warning should be logged when used.
"""


BOTO3_CLIENT_CONNECT_TIMEOUT = 5
"""Timeout in seconds for initial boto3 client connection.

Controls connection timeout when creating boto3 clients for AWS API calls.
"""

BOTO3_CLIENT_READ_TIMEOUT = 30
"""Timeout in seconds for boto3 client read operations.

Controls timeout for reading responses from AWS API calls.
"""

BOTO3_CLIENT_MAX_ATTEMPTS = 3
"""Maximum retry attempts for boto3 client operations.

Controls how many times boto3 will retry failed API calls using adaptive
retry strategy.
"""

BOTO3_PAGINATION_MAX_RESULTS_SMALL = 5
"""Max results for pagination queries returning small result sets.

Used for describe_instances, describe_vpcs, describe_security_groups operations
where result set is typically small.
"""

BOTO3_PAGINATION_MAX_RESULTS_SINGLE = 1
"""Max results for pagination queries expecting single result.

Used for pricing API queries where we only need the first/best result.
"""


class InstanceState(str, Enum):
    """EC2 instance state values."""

    PENDING = "pending"
    RUNNING = "running"
    STOPPED = "stopped"
    STOPPING = "stopping"
    TERMINATED = "terminated"
