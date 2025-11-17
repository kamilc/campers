"""Unit tests for MutagenSessionManager."""

from collections import deque
from typing import Any

import pytest

from tests.unit.harness.services.event_bus import EventBus
from tests.unit.harness.services.mutagen_session_manager import (
    MutagenCommandResult,
    MutagenError,
    MutagenSessionManager,
    MutagenTimeoutError,
)
from tests.unit.harness.services.resource_registry import ResourceRegistry
from tests.unit.harness.services.timeout_manager import TimeoutManager


class DiagnosticsRecorder:
    """Capture diagnostics calls for assertions."""

    def __init__(self) -> None:
        self.calls: deque[tuple[str, str, dict[str, Any]]] = deque()

    def __call__(self, category: str, status: str, details: dict[str, Any]) -> None:
        self.calls.append((category, status, details))


class TestMutagenSessionManager:
    """Validate session manager behaviour."""

    def test_create_session_timeout(self) -> None:
        """Test timeout raises MutagenTimeoutError and publishes status."""
        timeout_manager = TimeoutManager(budget_seconds=5)
        event_bus = EventBus()
        diagnostics = DiagnosticsRecorder()
        registry = ResourceRegistry()

        def slow_runner(arguments: list[str], timeout: float) -> MutagenCommandResult:
            raise TimeoutError("mutagen cli timeout")

        manager = MutagenSessionManager(
            timeout_manager=timeout_manager,
            event_bus=event_bus,
            resource_registry=registry,
            diagnostics_callback=diagnostics,
            runner=slow_runner,
        )

        with pytest.raises(MutagenTimeoutError):
            manager.create_session(
                session_id="sync-1",
                instance_id="i-123",
                arguments=["mutagen", "create"],
                timeout_sec=1.0,
            )

        status = event_bus.wait_for(
            "mutagen-status", instance_id="sync-1", timeout_sec=1.0
        )
        assert status.data["status"] == "timeout"
        assert "error" in status.data
        assert diagnostics.calls[0][1] == "timeout"

    def test_create_session_success_and_cleanup(self) -> None:
        """Test successful session creation registers cleanup and can terminate."""
        timeout_manager = TimeoutManager(budget_seconds=5)
        event_bus = EventBus()
        diagnostics = DiagnosticsRecorder()
        registry = ResourceRegistry()
        terminator_calls: list[str] = []

        def runner(arguments: list[str], timeout: float) -> MutagenCommandResult:
            return MutagenCommandResult(exit_code=0, stdout="ok", stderr="")

        def terminator(session_id: str) -> None:
            terminator_calls.append(session_id)

        manager = MutagenSessionManager(
            timeout_manager=timeout_manager,
            event_bus=event_bus,
            resource_registry=registry,
            diagnostics_callback=diagnostics,
            runner=runner,
            terminator=terminator,
        )

        session = manager.create_session(
            session_id="sync-2",
            instance_id="i-234",
            arguments=["mutagen", "create"],
            timeout_sec=2.0,
            metadata={"path": "/tmp"},
        )

        assert session.session_id == "sync-2"
        assert manager.list_sessions()[0].session_id == "sync-2"
        created_event = event_bus.wait_for(
            "mutagen-status", instance_id="sync-2", timeout_sec=1.0
        )
        assert created_event.data["status"] == "created"
        registry.cleanup_all()
        assert terminator_calls == ["sync-2"]

        terminated_event = event_bus.wait_for(
            "mutagen-status", instance_id="sync-2", timeout_sec=1.0
        )
        assert terminated_event.data["status"] == "terminated"

    def test_create_session_failure_raises(self) -> None:
        """Test non-zero exit code raises MutagenError."""
        timeout_manager = TimeoutManager(budget_seconds=5)
        event_bus = EventBus()
        diagnostics = DiagnosticsRecorder()
        registry = ResourceRegistry()

        def failing_runner(
            arguments: list[str], timeout: float
        ) -> MutagenCommandResult:
            return MutagenCommandResult(exit_code=1, stdout="", stderr="boom")

        manager = MutagenSessionManager(
            timeout_manager=timeout_manager,
            event_bus=event_bus,
            resource_registry=registry,
            diagnostics_callback=diagnostics,
            runner=failing_runner,
        )

        with pytest.raises(MutagenError):
            manager.create_session(
                session_id="sync-3",
                instance_id="i-345",
                arguments=["mutagen", "create"],
                timeout_sec=1.5,
            )

        event = event_bus.wait_for(
            "mutagen-status", instance_id="sync-3", timeout_sec=1.0
        )
        assert event.data["status"] == "error"
        assert event.data["stderr"] == "boom"

    def test_terminate_all_handles_multiple_sessions(self) -> None:
        """Test terminate_all terminates all tracked sessions."""
        timeout_manager = TimeoutManager(budget_seconds=5)
        event_bus = EventBus()
        diagnostics = DiagnosticsRecorder()
        registry = ResourceRegistry()

        def runner(arguments: list[str], timeout: float) -> MutagenCommandResult:
            return MutagenCommandResult(exit_code=0, stdout="ok", stderr="")

        terminated: list[str] = []

        def terminator(session_id: str) -> None:
            terminated.append(session_id)

        manager = MutagenSessionManager(
            timeout_manager=timeout_manager,
            event_bus=event_bus,
            resource_registry=registry,
            diagnostics_callback=diagnostics,
            runner=runner,
            terminator=terminator,
        )

        manager.create_session(
            session_id="sync-a",
            instance_id="i-1",
            arguments=["mutagen", "sync", "create"],
            timeout_sec=1.0,
        )
        manager.create_session(
            session_id="sync-b",
            instance_id="i-2",
            arguments=["mutagen", "sync", "create"],
            timeout_sec=1.0,
        )

        summary = manager.terminate_all(timeout_sec=5.0)

        assert set(summary.terminated) == {"sync-a", "sync-b"}
        assert summary.failures == {}
        assert set(terminated) == {"sync-a", "sync-b"}
