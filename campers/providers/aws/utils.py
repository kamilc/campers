"""AWS-specific utility functions for campers."""

from __future__ import annotations

import re
from typing import Any


def extract_instance_from_response(response: dict[str, Any]) -> dict[str, Any]:
    """Extract first instance from AWS describe_instances response.

    Parameters
    ----------
    response : dict[str, Any]
        Response from boto3 describe_instances call

    Returns
    -------
    dict[str, Any]
        The first instance dictionary

    Raises
    ------
    ValueError
        If response has no reservations or instances
    """
    if not response.get("Reservations"):
        raise ValueError("No reservations in response")
    if not response["Reservations"][0].get("Instances"):
        raise ValueError("No instances in reservation")
    return response["Reservations"][0]["Instances"][0]


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


def get_aws_credentials_error_message() -> str:
    """Get standard AWS credentials error message.

    Returns
    -------
    str
        Formatted AWS credentials error message
    """
    return (
        "Cloud credentials not found\n\n"
        "Configure your credentials:\n"
        "  aws configure\n\n"
        "Or set environment variables:\n"
        "  export AWS_ACCESS_KEY_ID=...\n"
        "  export AWS_SECRET_ACCESS_KEY=..."
    )
