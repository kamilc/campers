"""Signal handling for graceful cleanup and shutdown."""

from __future__ import annotations

import signal
import threading
import types
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    pass


class CleanupHandler(Protocol):
    """Protocol for cleanup handler (Campers instance)."""

    def _cleanup_resources(
        self, signum: int | None = None, frame: types.FrameType | None = None
    ) -> None:
        """Handle cleanup resources."""
        ...


class CleanupInstanceManager:
    """Thread-safe manager for the cleanup instance."""

    def __init__(self) -> None:
        """Initialize the cleanup instance manager."""
        self._lock = threading.Lock()
        self._instance: CleanupHandler | None = None

    def set(self, instance: CleanupHandler | None) -> None:
        """Set the cleanup instance.

        Parameters
        ----------
        instance : CleanupHandler | None
            The Campers instance that will handle cleanup
        """
        with self._lock:
            self._instance = instance

    def get(self) -> CleanupHandler | None:
        """Get the current cleanup instance.

        Returns
        -------
        CleanupHandler | None
            The Campers instance handling cleanup, or None if not set
        """
        with self._lock:
            return self._instance


_cleanup_manager = CleanupInstanceManager()


def setup_signal_handlers() -> None:
    """Register signal handlers at module level before heavy imports.

    This ensures signals like SIGINT are caught even during module
    initialization phase (e.g., during paramiko import).

    Signal handlers delegate cleanup responsibility to the Campers instance,
    which manages resource cleanup in a thread-safe manner.
    """

    def sigint_handler(signum: int, frame: types.FrameType | None) -> None:
        """Handle SIGINT (Ctrl+C) signal."""
        instance = _cleanup_manager.get()
        if instance is not None:
            instance._cleanup_resources(signum=signum, frame=frame)

    def sigterm_handler(signum: int, frame: types.FrameType | None) -> None:
        """Handle SIGTERM signal."""
        instance = _cleanup_manager.get()
        if instance is not None:
            instance._cleanup_resources(signum=signum, frame=frame)

    signal.signal(signal.SIGINT, sigint_handler)
    signal.signal(signal.SIGTERM, sigterm_handler)


def set_cleanup_instance(instance: CleanupHandler | None) -> None:
    """Set the instance to handle cleanup for signal handlers.

    Parameters
    ----------
    instance : CleanupHandler | None
        The Campers instance that will handle cleanup
    """
    _cleanup_manager.set(instance)


def get_cleanup_instance() -> CleanupHandler | None:
    """Get the current cleanup instance.

    Returns
    -------
    CleanupHandler | None
        The Campers instance handling cleanup, or None if not set
    """
    return _cleanup_manager.get()
