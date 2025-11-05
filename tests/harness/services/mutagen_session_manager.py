"""Mutagen session management for LocalStack harness."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List

from tests.harness.services.event_bus import Event, EventBus
from tests.harness.services.resource_registry import ResourceRegistry
from tests.harness.services.timeout_manager import TimeoutManager


class MutagenError(Exception):
    """Base exception for Mutagen session failures."""


class MutagenTimeoutError(MutagenError):
    """Raised when a Mutagen CLI invocation exceeds its timeout budget."""


@dataclass
class MutagenCommandResult:
    """Command execution result returned by the CLI runner.

    Attributes
    ----------
    exit_code : int
        CLI exit status.
    stdout : str
        Captured standard output.
    stderr : str
        Captured standard error.
    """

    exit_code: int
    stdout: str
    stderr: str


@dataclass
class MutagenSession:
    """Tracked Mutagen synchronization session metadata.

    Attributes
    ----------
    session_id : str
        Unique Mutagen session identifier.
    instance_id : str
        Associated instance identifier.
    created_at : float
        Session creation timestamp.
    metadata : dict[str, Any]
        Additional metadata supplied by the caller.
    """

    session_id: str
    instance_id: str
    created_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


RunnerCallable = Callable[[List[str], float], MutagenCommandResult]
TerminatorCallable = Callable[[str], None]


@dataclass
class MutagenTerminationSummary:
    """Summary of terminated Mutagen sessions."""

    terminated: list[str] = field(default_factory=list)
    failures: dict[str, str] = field(default_factory=dict)


class MutagenSessionManager:
    """Manage Mutagen session lifecycle with timeout enforcement.

    Attributes
    ----------
    _timeout_manager : TimeoutManager
        Timeout budget allocator.
    _event_bus : EventBus
        Event bus for publishing session status updates.
    _resource_registry : ResourceRegistry
        Registry for cleanup orchestration.
    _diagnostics : Callable[[str, str, dict[str, Any]], None] | None
        Optional diagnostics hook.
    _runner : RunnerCallable
        Callable that executes the Mutagen CLI command.
    _terminator : TerminatorCallable | None
        Callable that terminates a session during cleanup.
    _sessions : dict[str, MutagenSession]
        Tracked active sessions.
    _lock : threading.RLock
        Synchronization primitive guarding session state.
    """

    def __init__(
        self,
        timeout_manager: TimeoutManager,
        event_bus: EventBus,
        resource_registry: ResourceRegistry,
        diagnostics_callback: Callable[[str, str, dict[str, Any]], None] | None,
        runner: RunnerCallable,
        terminator: TerminatorCallable | None = None,
    ) -> None:
        """Initialize the manager with dependencies.

        Parameters
        ----------
        timeout_manager : TimeoutManager
            Timeout budget allocator.
        event_bus : EventBus
            Event bus for publishing status updates.
        resource_registry : ResourceRegistry
            Registry for cleanup orchestration.
        diagnostics_callback : Callable[[str, str, dict[str, Any]], None] | None
            Optional diagnostics hook to record events.
        runner : RunnerCallable
            Callable executing the Mutagen CLI.
        terminator : TerminatorCallable | None, optional
            Callable terminating sessions during cleanup.
        """
        self._timeout_manager = timeout_manager
        self._event_bus = event_bus
        self._resource_registry = resource_registry
        self._diagnostics = diagnostics_callback
        self._runner = runner
        self._terminator = terminator
        self._sessions: Dict[str, MutagenSession] = {}
        self._lock = threading.RLock()

    def create_session(
        self,
        session_id: str,
        instance_id: str,
        arguments: List[str],
        timeout_sec: float,
        metadata: dict[str, Any] | None = None,
    ) -> MutagenSession:
        """Create and track a Mutagen session.

        Parameters
        ----------
        session_id : str
            Target Mutagen session identifier.
        instance_id : str
            Associated instance identifier.
        arguments : list[str]
            CLI arguments for session creation.
        timeout_sec : float
            Timeout budget for the CLI invocation.
        metadata : dict[str, Any] | None, optional
            Additional metadata to associate with the session.

        Returns
        -------
        MutagenSession
            Recorded session metadata on success.

        Raises
        ------
        MutagenTimeoutError
            If the CLI call exceeds the timeout budget.
        MutagenError
            If the CLI returns a non-zero exit code.
        """
        with self._timeout_manager.sub_budget(
            name=f"mutagen-create-{session_id}",
            max_seconds=timeout_sec,
        ) as budget:
            try:
                result = self._runner(arguments, budget)
            except TimeoutError as exc:  # pylint: disable=broad-except
                self._publish_status(
                    session_id=session_id,
                    instance_id=instance_id,
                    status="timeout",
                    details={"error": str(exc)},
                )
                raise MutagenTimeoutError(str(exc)) from exc

        if result.exit_code != 0:
            self._publish_status(
                session_id=session_id,
                instance_id=instance_id,
                status="error",
                details={"stderr": result.stderr},
            )
            raise MutagenError(result.stderr)

        session = MutagenSession(
            session_id=session_id,
            instance_id=instance_id,
            metadata=metadata or {},
        )

        with self._lock:
            self._sessions[session_id] = session

        self._resource_registry.register(
            kind="mutagen-session",
            handle=session_id,
            dispose_fn=lambda sid: self.terminate_session(sid),
            label=session_id,
        )

        self._publish_status(
            session_id=session_id,
            instance_id=instance_id,
            status="created",
            details={"stdout": result.stdout},
        )
        return session

    def terminate_session(self, session_id: str) -> None:
        """Terminate a tracked session if it exists.

        Parameters
        ----------
        session_id : str
            Identifer of the session to terminate.
        """
        with self._lock:
            session = self._sessions.pop(session_id, None)
        if session is None:
            return

        if self._terminator is not None:
            self._terminator(session_id)

        self._publish_status(
            session_id=session_id,
            instance_id=session.instance_id,
            status="terminated",
            details={},
        )

    def terminate_all(self, timeout_sec: float | None = None) -> MutagenTerminationSummary:
        """Terminate all tracked Mutagen sessions.

        Parameters
        ----------
        timeout_sec : float | None, optional
            Maximum time in seconds to allocate for all terminations.

        Returns
        -------
        MutagenTerminationSummary
            Summary describing terminated sessions and failures.
        """

        summary = MutagenTerminationSummary()

        with self._lock:
            remaining_sessions = list(self._sessions.keys())

        if not remaining_sessions:
            return summary

        if timeout_sec is not None and timeout_sec > 0:
            per_session_budget = max(timeout_sec / len(remaining_sessions), 0.1)
        else:
            per_session_budget = 5.0

        for session_id in remaining_sessions:
            budget = per_session_budget

            try:
                with self._timeout_manager.sub_budget(
                    name=f"mutagen-terminate-{session_id}",
                    max_seconds=budget,
                ):
                    self.terminate_session(session_id)
                    summary.terminated.append(session_id)
            except Exception as exc:  # pylint: disable=broad-except
                summary.failures[session_id] = str(exc)

        return summary

    def list_sessions(self) -> list[MutagenSession]:
        """Return tracked sessions for diagnostics.

        Returns
        -------
        list[MutagenSession]
            Snapshot of tracked sessions.
        """
        with self._lock:
            return list(self._sessions.values())

    def _publish_status(
        self,
        session_id: str,
        instance_id: str,
        status: str,
        details: dict[str, Any],
    ) -> None:
        """Publish a session status event and optional diagnostics entry.

        Parameters
        ----------
        session_id : str
            Target session identifier.
        instance_id : str
            Associated instance identifier.
        status : str
            Status string describing the state transition.
        details : dict[str, Any]
            Structured event payload details.
        """
        if self._diagnostics is not None:
            self._diagnostics(
                "mutagen-session",
                status,
                {"session_id": session_id, "instance_id": instance_id, **details},
            )

        self._event_bus.publish(
            Event(
                type="mutagen-status",
                instance_id=session_id,
                data={"status": status, "instance_id": instance_id, **details},
            )
        )
