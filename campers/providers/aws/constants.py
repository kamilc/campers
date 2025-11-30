"""AWS-specific constants for EC2 and pricing operations.

This module contains constants specific to AWS cloud provider operations,
including EC2 instance management and pricing information.
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
