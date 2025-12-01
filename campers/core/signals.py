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
    """Thread-safe manager for the cleanup instance.

    Uses a single lock to protect both getting and checking the instance,
    preventing race conditions between signal handlers and cleanup teardown.
    """

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

    def cleanup_with_lock(
        self, signum: int, frame: types.FrameType | None
    ) -> None:
        """Perform cleanup with lock protection against concurrent set(None) calls.

        Parameters
        ----------
        signum : int
            Signal number
        frame : types.FrameType | None
            Signal frame

        Notes
        -----
        This method atomically retrieves the instance and calls cleanup,
        preventing race conditions where the instance might be set to None
        by another thread between get() and the cleanup call.
        """
        with self._lock:
            instance = self._instance
            if instance is not None:
                instance._cleanup_resources(signum=signum, frame=frame)


_cleanup_manager = CleanupInstanceManager()


def setup_signal_handlers() -> None:
    """Register signal handlers at module level before heavy imports.

    This ensures signals like SIGINT are caught even during module
    initialization phase (e.g., during paramiko import).

    Signal handlers delegate cleanup responsibility to the Campers instance,
    which manages resource cleanup in a thread-safe manner using atomic
    check-and-act patterns to prevent race conditions.
    """

    def sigint_handler(signum: int, frame: types.FrameType | None) -> None:
        """Handle SIGINT (Ctrl+C) signal."""
        _cleanup_manager.cleanup_with_lock(signum=signum, frame=frame)

    def sigterm_handler(signum: int, frame: types.FrameType | None) -> None:
        """Handle SIGTERM signal."""
        _cleanup_manager.cleanup_with_lock(signum=signum, frame=frame)

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
