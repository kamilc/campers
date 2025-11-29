"""Diagnostics collection for debugging test scenarios."""

import json
import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class DiagnosticEvent:
    """Single diagnostic event.

    Attributes
    ----------
    event_type : str
        Type of event (e.g., "resource_registration", "timeout_checkpoint")
    description : str
        Event description
    details : dict
        Additional event details
    timestamp : float
        Time when event was recorded
    """

    event_type: str
    description: str
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=lambda: __import__("time").time())


class DiagnosticsCollector:
    """Captures structured events for post-scenario analysis.

    Stores diagnostic events in-memory and optionally outputs to console
    for debugging. When a log path is provided, events are appended to disk
    immediately so that diagnostics remain available even if the scenario
    terminates unexpectedly.

    Attributes
    ----------
    events : list[DiagnosticEvent]
        List of collected diagnostic events
    verbose : bool
        Whether to output to console during collection
    """

    def __init__(self, verbose: bool = False, log_path: Path | None = None) -> None:
        self.events: list[DiagnosticEvent] = []
        self.verbose = verbose
        self._log_path = Path(log_path) if log_path else None
        self._log_lock = threading.Lock()

    def record(
        self, event_type: str, description: str, details: dict[str, Any] | None = None
    ) -> None:
        """Record a diagnostic event.

        Parameters
        ----------
        event_type : str
            Type of event
        description : str
            Event description
        details : dict, optional
            Additional event details
        """
        event = DiagnosticEvent(
            event_type=event_type,
            description=description,
            details=details or {},
        )
        self.events.append(event)

        if self.verbose:
            logger.debug(f"[{event_type}] {description} | details: {event.details}")

        if self._log_path is not None:
            payload = {
                "event_type": event.event_type,
                "description": event.description,
                "details": event.details,
                "timestamp": event.timestamp,
            }
            line = json.dumps(payload, default=str)
            with self._log_lock:
                self._log_path.parent.mkdir(parents=True, exist_ok=True)
                with self._log_path.open("a", encoding="utf-8") as log_file:
                    log_file.write(line + "\n")

    def clear(self) -> None:
        """Clear all recorded events."""
        self.events.clear()

    def get_events_by_type(self, event_type: str) -> list[DiagnosticEvent]:
        """Get all events of a specific type.

        Parameters
        ----------
        event_type : str
            Event type to filter by

        Returns
        -------
        list[DiagnosticEvent]
            Matching events
        """
        return [e for e in self.events if e.event_type == event_type]

    def set_log_path(self, log_path: Path | None) -> None:
        """Update the on-disk log path used for streaming diagnostics."""
        self._log_path = Path(log_path) if log_path else None

    def record_system_snapshot(self, description: str, include_thread_stacks: bool = False) -> None:
        """Capture and record a holistic system snapshot."""
        from tests.harness.utils.system_snapshot import gather_system_snapshot

        snapshot = gather_system_snapshot(include_thread_stacks=include_thread_stacks)
        self.record("system-snapshot", description, snapshot)
