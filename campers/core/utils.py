"""Utility functions for common patterns across the codebase."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from campers.core.interfaces import ComputeProvider


def get_instance_id(instance_details: dict[str, Any]) -> str | None:
    """Extract instance ID from instance details dictionary.

    Handles both "InstanceId" and "instance_id" keys for compatibility
    with different AWS API responses and local representations.

    Parameters
    ----------
    instance_details : dict[str, Any]
        Instance details dictionary from AWS API

    Returns
    -------
    str or None
        Instance ID if found, None otherwise
    """
    instance_id = instance_details.get("InstanceId")
    if instance_id is not None:
        return instance_id
    return instance_details.get("instance_id")


def get_volume_size_or_default(
    regional_manager: ComputeProvider, instance_id: str, default: int = 0
) -> int:
    """Get volume size with fallback to default value.

    Queries the regional manager for instance volume size and returns
    the configured default if the volume size is not available.

    Parameters
    ----------
    regional_manager : ComputeProvider
        Regional compute provider manager with get_volume_size method
    instance_id : str
        Instance ID to query
    default : int, default=0
        Default value to return if volume size is unavailable

    Returns
    -------
    int
        Volume size in GB or default value
    """
    volume_size = regional_manager.get_volume_size(instance_id)
    return volume_size if volume_size is not None else default
