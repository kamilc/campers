"""Provider registry and management.

This module implements a provider registry system that allows campers to support
multiple cloud providers (AWS, GCP, Azure, etc.) through a common interface.
"""

from __future__ import annotations

from campers.constants import DEFAULT_SSH_USERNAME
from campers.core.interfaces import ComputeProvider, PricingProvider
from campers.providers.aws import EC2Manager, PricingService
from campers.providers.aws.constants import (
    DEFAULT_INSTANCE_TYPE,
    DEFAULT_REGION,
)
from campers.providers.aws.pricing import (
    calculate_monthly_cost,
    format_cost,
)
from campers.providers.exceptions import (
    ProviderAPIError,
    ProviderConnectionError,
    ProviderCredentialsError,
    ProviderError,
)

_PROVIDERS: dict[str, dict[str, object]] = {}


def register_provider(
    name: str,
    compute_class: type[ComputeProvider],
    pricing_class: type[PricingProvider],
    default_region: str | None = None,
) -> None:
    """Register a cloud provider implementation.

    Parameters
    ----------
    name : str
        Provider name (e.g., 'aws', 'gcp', 'azure')
    compute_class : type[ComputeProvider]
        Compute provider class implementing ComputeProvider protocol
    pricing_class : type[PricingProvider]
        Pricing provider class implementing PricingProvider protocol
    default_region : str | None
        Default region for this provider
    """
    _PROVIDERS[name] = {
        "compute": compute_class,
        "pricing": pricing_class,
        "default_region": default_region,
    }


def get_provider(name: str) -> dict[str, type[ComputeProvider] | type[PricingProvider]]:
    """Get a registered provider by name.

    Parameters
    ----------
    name : str
        Provider name

    Returns
    -------
    dict[str, type[ComputeProvider] | type[PricingProvider]]
        Dictionary with 'compute' and 'pricing' keys containing provider classes

    Raises
    ------
    ValueError
        If provider is not registered
    """
    if name not in _PROVIDERS:
        raise ValueError(f"Unknown provider: {name}")
    return _PROVIDERS[name]


def list_providers() -> list[str]:
    """List all registered provider names.

    Returns
    -------
    list[str]
        List of provider names
    """
    return list(_PROVIDERS.keys())


def get_default_region(provider_name: str) -> str:
    """Get the default region for a provider.

    Parameters
    ----------
    provider_name : str
        Provider name

    Returns
    -------
    str
        Default region for the provider

    Raises
    ------
    ValueError
        If provider is not registered or has no default region
    """
    if provider_name not in _PROVIDERS:
        raise ValueError(f"Unknown provider: {provider_name}")

    provider_info = _PROVIDERS[provider_name]
    default_region = provider_info.get("default_region")

    if default_region is None:
        raise ValueError(f"No default region defined for provider: {provider_name}")

    return default_region


def get_provider_defaults(provider_name: str) -> dict[str, object]:
    """Get provider-specific defaults (instance_type, ssh_username, env_filter).

    Parameters
    ----------
    provider_name : str
        Provider name

    Returns
    -------
    dict[str, object]
        Dictionary with keys: instance_type, ssh_username, env_filter

    Raises
    ------
    ValueError
        If provider is not registered
    """
    if provider_name not in _PROVIDERS:
        raise ValueError(f"Unknown provider: {provider_name}")

    provider_info = _PROVIDERS[provider_name]
    return {
        "instance_type": provider_info.get("default_instance_type", "t3.medium"),
        "ssh_username": provider_info.get("default_ssh_username", DEFAULT_SSH_USERNAME),
        "env_filter": provider_info.get("env_filter", []),
    }


__all__ = [
    "register_provider",
    "get_provider",
    "list_providers",
    "get_default_region",
    "get_provider_defaults",
    "ProviderError",
    "ProviderCredentialsError",
    "ProviderAPIError",
    "ProviderConnectionError",
]


def _get_setup_manager() -> type:
    """Lazily import SetupManager to avoid circular imports."""
    from campers.providers.aws.setup import SetupManager as AWSSetupManager

    return AWSSetupManager


def _get_ssh_connection_info_func() -> object:
    """Lazily import AWS SSH connection function to avoid circular imports."""
    from campers.providers.aws.ssh import get_aws_ssh_connection_info

    return get_aws_ssh_connection_info


_PROVIDERS["aws"] = {
    "compute": EC2Manager,
    "pricing": PricingService,
    "pricing_service": PricingService,
    "setup": _get_setup_manager,
    "get_ssh_connection_info": _get_ssh_connection_info_func,
    "calculate_monthly_cost": calculate_monthly_cost,
    "format_cost": format_cost,
    "default_region": DEFAULT_REGION,
    "default_instance_type": DEFAULT_INSTANCE_TYPE,
    "default_ssh_username": DEFAULT_SSH_USERNAME,
    "env_filter": ["AWS_.*"],
}
