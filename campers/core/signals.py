"""Signal handling for graceful cleanup and shutdown."""

from __future__ import annotations

import signal
import threading
import types
from typing import Protocol


class CleanupHandler(Protocol):
    """Protocol for cleanup handler (Campers instance)."""

    def _cleanup_resources(
        self, signum: int | None = None, frame: types.FrameType | None = None
    ) -> None:
        """Handle cleanup resources."""
        ...


class SignalManager:
    """Manages signal registration for a single cleanup handler instance.

    Stores previous signal handlers and restores them when the instance is destroyed.
    Ensures only one active signal handler at a time.
    """

    def __init__(self, handler: CleanupHandler) -> None:
        """Initialize the signal manager.

        Parameters
        ----------
        handler : CleanupHandler
            The cleanup handler instance (typically Campers)
        """
        self._handler = handler
        self._lock = threading.Lock()
        self._previous_sigint_handler: signal.Handlers | None = None
        self._previous_sigterm_handler: signal.Handlers | None = None
        self._is_registered = False

    def register(self) -> None:
        """Register signal handlers for this instance.

        Thread-safe registration that stores previous handlers for restoration.
        """
        with self._lock:
            if self._is_registered:
                return

            def sigint_handler(signum: int, frame: types.FrameType | None) -> None:
                self._handler._cleanup_resources(signum=signum, frame=frame)

            def sigterm_handler(signum: int, frame: types.FrameType | None) -> None:
                self._handler._cleanup_resources(signum=signum, frame=frame)

            self._previous_sigint_handler = signal.signal(signal.SIGINT, sigint_handler)
            self._previous_sigterm_handler = signal.signal(signal.SIGTERM, sigterm_handler)
            self._is_registered = True

    def restore(self) -> None:
        """Restore previous signal handlers.

        Thread-safe restoration of original signal handlers.
        """
        with self._lock:
            if not self._is_registered:
                return

            if self._previous_sigint_handler is not None:
                signal.signal(signal.SIGINT, self._previous_sigint_handler)
            if self._previous_sigterm_handler is not None:
                signal.signal(signal.SIGTERM, self._previous_sigterm_handler)
            self._is_registered = False

    def __del__(self) -> None:
        """Ensure signal handlers are restored on cleanup."""
        self.restore()
