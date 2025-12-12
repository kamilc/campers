"""Provider-agnostic protocol definitions for compute and pricing services."""

from __future__ import annotations

from typing import Any, Protocol


class ComputeProvider(Protocol):
    """Protocol for cloud compute provider implementations.

    Defines the interface that all compute providers (AWS EC2, GCP, Azure, etc.)
    must implement to work with campers.
    """

    @property
    def region(self) -> str:
        """Get the region for this provider.

        Returns
        -------
        str
            Region identifier
        """
        ...

    def launch_instance(self, config: dict[str, Any], instance_name: str) -> dict[str, Any]:
        """Launch a new compute instance.

        Parameters
        ----------
        config : dict[str, Any]
            Configuration dictionary containing instance specifications
            (instance type, AMI/image ID, security groups, etc.)
        instance_name : str
            Name to assign to the new instance

        Returns
        -------
        dict[str, Any]
            Instance details including instance ID, IP address, and other metadata
        """
        ...

    def terminate_instance(self, instance_id: str) -> None:
        """Terminate a running compute instance permanently.

        Parameters
        ----------
        instance_id : str
            ID of the instance to terminate
        """
        ...

    def stop_instance(self, instance_id: str) -> None:
        """Stop a running compute instance without terminating it.

        Parameters
        ----------
        instance_id : str
            ID of the instance to stop
        """
        ...

    def start_instance(self, instance_id: str) -> dict[str, Any]:
        """Start a stopped compute instance.

        Parameters
        ----------
        instance_id : str
            ID of the instance to start

        Returns
        -------
        dict[str, Any]
            Updated instance details
        """
        ...

    def list_instances(self, region_filter: str | None = None) -> list[dict[str, Any]]:
        """List all compute instances.

        Parameters
        ----------
        region_filter : str | None
            Optional region filter to list instances in specific region(s)

        Returns
        -------
        list[dict[str, Any]]
            List of instance details
        """
        ...

    def find_instances_by_name_or_id(
        self, name_or_id: str, region_filter: str | None = None
    ) -> list[dict[str, Any]]:
        """Find instances by name or ID.

        Parameters
        ----------
        name_or_id : str
            Instance name or ID to search for
        region_filter : str | None
            Optional region filter

        Returns
        -------
        list[dict[str, Any]]
            List of matching instances
        """
        ...

    def get_volume_size(self, instance_id: str) -> int | None:
        """Get the root volume size of an instance in GB.

        Parameters
        ----------
        instance_id : str
            ID of the instance

        Returns
        -------
        int | None
            Volume size in GB, or None if not available
        """
        ...

    def get_instance_tags(self, instance_id: str) -> dict[str, str]:
        """Get tags for an instance.

        Parameters
        ----------
        instance_id : str
            ID of the instance

        Returns
        -------
        dict[str, str]
            Dictionary of tag keys and values
        """
        ...

    def validate_region(self, region: str) -> bool:
        """Validate if a region is available for this provider.

        Parameters
        ----------
        region : str
            Region identifier to validate

        Returns
        -------
        bool
            True if region is valid, False otherwise
        """
        ...

    def sanitize_instance_name(self, name: str) -> str:
        """Sanitize instance name to meet provider requirements.

        Parameters
        ----------
        name : str
            Original instance name

        Returns
        -------
        str
            Sanitized instance name that meets provider requirements
        """
        ...


class PricingProvider(Protocol):
    """Protocol for cloud pricing information providers.

    Defines the interface for retrieving pricing information for
    compute instances and storage.
    """

    @property
    def pricing_available(self) -> bool:
        """Check if pricing data is available.

        Returns
        -------
        bool
            True if pricing service is available and functional
        """
        ...

    def get_instance_price(self, instance_type: str, region: str) -> float | None:
        """Get hourly price for an instance type in a region.

        Parameters
        ----------
        instance_type : str
            Instance type identifier (e.g., 't3.micro')
        region : str
            Region identifier

        Returns
        -------
        float | None
            Hourly price in USD, or None if not available
        """
        ...

    def get_storage_price(self, region: str) -> float:
        """Get monthly price per GB for storage in a region.

        Parameters
        ----------
        region : str
            Region identifier

        Returns
        -------
        float
            Monthly price per GB in USD
        """
        ...


class SSHProvider(Protocol):
    """Protocol for SSH connection information from a compute instance.

    Defines the interface for retrieving SSH connection details needed
    to connect to a compute instance.
    """

    def get_connection_info(self, instance_id: str) -> dict[str, Any]:
        """Get SSH connection information for an instance.

        Parameters
        ----------
        instance_id : str
            ID of the instance

        Returns
        -------
        dict[str, Any]
            Connection details including hostname, username, key path, etc.
        """
        ...

    def abort_active_command(self) -> None:
        """Abort any active command execution.

        Terminates the currently running command if one exists.
        """
        ...

    def close(self) -> None:
        """Close the SSH connection.

        Ensures all resources are properly released.
        """
        ...
