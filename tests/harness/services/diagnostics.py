"""Diagnostics collection for debugging test scenarios."""

import logging
from dataclasses import dataclass, field
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
    for debugging.

    Attributes
    ----------
    events : list[DiagnosticEvent]
        List of collected diagnostic events
    verbose : bool
        Whether to output to console during collection
    """

    def __init__(self, verbose: bool = False) -> None:
        self.events: list[DiagnosticEvent] = []
        self.verbose = verbose

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
