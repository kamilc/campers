"""Provider registry and management.

This module implements a provider registry system that allows campers to support
multiple cloud providers (AWS, GCP, Azure, etc.) through a common interface.
"""

from __future__ import annotations

from typing import Any

from campers.providers.aws import EC2Manager, PricingService
from campers.providers.exceptions import (
    ProviderAPIError,
    ProviderConnectionError,
    ProviderCredentialsError,
    ProviderError,
)

_PROVIDERS: dict[str, dict[str, Any]] = {}


def register_provider(name: str, compute_class: Any, pricing_class: Any) -> None:
    """Register a cloud provider implementation.

    Parameters
    ----------
    name : str
        Provider name (e.g., 'aws', 'gcp', 'azure')
    compute_class : Any
        Compute provider class implementing ComputeProvider protocol
    pricing_class : Any
        Pricing provider class implementing PricingProvider protocol
    """
    _PROVIDERS[name] = {"compute": compute_class, "pricing": pricing_class}


def get_provider(name: str) -> dict[str, Any]:
    """Get a registered provider by name.

    Parameters
    ----------
    name : str
        Provider name

    Returns
    -------
    dict[str, Any]
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


__all__ = [
    "register_provider",
    "get_provider",
    "list_providers",
    "ProviderError",
    "ProviderCredentialsError",
    "ProviderAPIError",
    "ProviderConnectionError",
]

register_provider("aws", EC2Manager, PricingService)
