"""Core campers functionality."""

from __future__ import annotations

from campers.core.interfaces import ComputeProvider, PricingProvider, SSHProvider
from campers.core.signals import (
    get_cleanup_instance,
    set_cleanup_instance,
    setup_signal_handlers,
)

__all__ = [
    "ComputeProvider",
    "PricingProvider",
    "SSHProvider",
    "setup_signal_handlers",
    "set_cleanup_instance",
    "get_cleanup_instance",
]
