"""In-memory registry for short-lived events with blocking wait semantics."""

import threading
import time
from typing import Any

from tests.harness.exceptions import HarnessTimeoutError


class SignalRegistry:
    """Thread-safe registry for short-lived events.

    Provides publish/subscribe semantics for signals (e.g., ssh-ready,
    http-ready). Signals are stored in-memory and available for retrieval
    until explicitly drained.

    Attributes
    ----------
    _signals : dict[str, list[Any]]
        Mapping of signal names to lists of published data
    _lock : threading.Lock
        Protects concurrent access to signals dictionary
    _condition : threading.Condition
        Notifies waiting threads when signals are published
    """

    def __init__(self) -> None:
        self._signals: dict[str, list[Any]] = {}
        self._lock = threading.Lock()
        self._condition = threading.Condition(self._lock)

    def publish(self, signal_name: str, data: Any = None) -> None:
        """Publish a signal with optional data.

        Parameters
        ----------
        signal_name : str
            Name of the signal (e.g., "ssh-ready")
        data : Any, optional
            Optional data associated with signal
        """
        with self._condition:
            if signal_name not in self._signals:
                self._signals[signal_name] = []
            self._signals[signal_name].append(data)
            self._condition.notify_all()

    def wait_for(self, signal_name: str, timeout: float) -> Any:
        """Block until signal is published or timeout expires.

        Parameters
        ----------
        signal_name : str
            Name of the signal to wait for
        timeout : float
            Maximum time to wait in seconds

        Returns
        -------
        Any
            Data from the published signal

        Raises
        ------
        HarnessTimeoutError
            If timeout expires before signal is published
        """
        deadline = time.time() + timeout

        with self._condition:
            while signal_name not in self._signals or not self._signals[signal_name]:
                remaining = deadline - time.time()
                if remaining <= 0:
                    raise HarnessTimeoutError(f"Timeout waiting for signal: {signal_name}")

                self._condition.wait(timeout=remaining)

            return self._signals[signal_name].pop(0)

    def drain(self) -> None:
        """Clear all signals."""
        with self._condition:
            self._signals.clear()
