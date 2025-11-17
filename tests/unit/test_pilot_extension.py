"""Unit tests for PilotExtension."""

import time
from unittest.mock import Mock, MagicMock

from tests.unit.harness.localstack.pilot_extension import (
    PilotExtension,
    TUIHandle,
)
from tests.unit.harness.services.diagnostics import DiagnosticsCollector
from tests.unit.harness.services.event_bus import EventBus
from tests.unit.harness.services.timeout_manager import TimeoutManager


class TestTUIHandle:
    """Validate TUIHandle dataclass."""

    def test_tui_handle_creation(self) -> None:
        """Test TUIHandle can be created with required fields."""
        app = Mock()
        pilot = Mock()
        queue = Mock()
        timestamp = time.time()

        handle = TUIHandle(
            app=app,
            pilot=pilot,
            event_queue=queue,
            started_at=timestamp,
            config_path="/path/to/config.yaml",
        )

        assert handle.app is app
        assert handle.pilot is pilot
        assert handle.event_queue is queue
        assert handle.started_at == timestamp
        assert handle.config_path == "/path/to/config.yaml"


class TestPilotExtensionInitialization:
    """Validate PilotExtension initialization and setup."""

    def test_pilot_extension_init(self) -> None:
        """Test PilotExtension initializes with required services."""
        event_bus = EventBus()
        timeout_manager = TimeoutManager(budget_seconds=60)
        diagnostics = DiagnosticsCollector()

        ext = PilotExtension(
            event_bus=event_bus,
            timeout_manager=timeout_manager,
            diagnostics=diagnostics,
        )

        assert ext.event_bus is event_bus
        assert ext.timeout_manager is timeout_manager
        assert ext.diagnostics is diagnostics
        assert ext.tui_handle is None
        assert ext._tui_resources == []

    def test_create_tui_update_queue(self) -> None:
        """Test create_tui_update_queue creates valid queue."""
        event_bus = EventBus()
        timeout_manager = TimeoutManager(budget_seconds=60)
        diagnostics = DiagnosticsCollector()

        ext = PilotExtension(event_bus, timeout_manager, diagnostics)
        queue = ext.create_tui_update_queue()

        assert queue is not None
        assert queue.maxsize == 100
        queue.put_nowait({"type": "test"})
        assert queue.get_nowait() == {"type": "test"}


class TestPilotExtensionEventPublishing:
    """Validate TUI event publishing through EventBus."""

    def test_publish_tui_event(self) -> None:
        """Test publish_tui_event publishes to EventBus."""
        event_bus = EventBus()
        timeout_manager = TimeoutManager(budget_seconds=60)
        diagnostics = DiagnosticsCollector()

        ext = PilotExtension(event_bus, timeout_manager, diagnostics)

        ext.publish_tui_event(
            "tui-status-changed",
            {"status": "running", "machine_name": "test-machine"},
        )

        event = event_bus.wait_for(
            "tui-status-changed", instance_id=None, timeout_sec=1.0
        )
        assert event.type == "tui-status-changed"
        assert event.instance_id is None
        assert event.data["status"] == "running"
        assert event.data["machine_name"] == "test-machine"

    def test_publish_tui_app_started_event(self) -> None:
        """Test tui-app-started event contains correct data."""
        event_bus = EventBus()
        timeout_manager = TimeoutManager(budget_seconds=60)
        diagnostics = DiagnosticsCollector()

        ext = PilotExtension(event_bus, timeout_manager, diagnostics)
        timestamp = time.time()

        ext.publish_tui_event(
            "tui-app-started",
            {
                "machine_name": "jupyter-lab",
                "config_path": "/tmp/config.yaml",
                "timestamp": timestamp,
            },
        )

        event = event_bus.wait_for("tui-app-started", instance_id=None, timeout_sec=1.0)
        assert event.data["machine_name"] == "jupyter-lab"
        assert event.data["config_path"] == "/tmp/config.yaml"
        assert event.data["timestamp"] == timestamp

    def test_publish_tui_app_stopped_event(self) -> None:
        """Test tui-app-stopped event contains correct data."""
        event_bus = EventBus()
        timeout_manager = TimeoutManager(budget_seconds=60)
        diagnostics = DiagnosticsCollector()

        ext = PilotExtension(event_bus, timeout_manager, diagnostics)

        ext.publish_tui_event(
            "tui-app-stopped",
            {"duration_sec": 15.5, "graceful": True},
        )

        event = event_bus.wait_for("tui-app-stopped", instance_id=None, timeout_sec=1.0)
        assert event.data["duration_sec"] == 15.5
        assert event.data["graceful"] is True

    def test_publish_tui_error_event(self) -> None:
        """Test tui-error event contains error details."""
        event_bus = EventBus()
        timeout_manager = TimeoutManager(budget_seconds=60)
        diagnostics = DiagnosticsCollector()

        ext = PilotExtension(event_bus, timeout_manager, diagnostics)

        ext.publish_tui_event(
            "tui-error",
            {
                "error_message": "App crashed",
                "traceback": "Traceback...",
            },
        )

        event = event_bus.wait_for("tui-error", instance_id=None, timeout_sec=1.0)
        assert event.data["error_message"] == "App crashed"
        assert "Traceback" in event.data["traceback"]

    def test_publish_tui_timeout_event(self) -> None:
        """Test tui-timeout event contains timeout details."""
        event_bus = EventBus()
        timeout_manager = TimeoutManager(budget_seconds=60)
        diagnostics = DiagnosticsCollector()

        ext = PilotExtension(event_bus, timeout_manager, diagnostics)

        ext.publish_tui_event(
            "tui-timeout",
            {"timeout_sec": 30.0, "graceful": False},
        )

        event = event_bus.wait_for("tui-timeout", instance_id=None, timeout_sec=1.0)
        assert event.data["timeout_sec"] == 30.0
        assert event.data["graceful"] is False


class TestPilotExtensionShutdown:
    """Validate TUI shutdown operations."""

    def test_shutdown_when_no_tui_handle(self) -> None:
        """Test shutdown gracefully handles None tui_handle."""
        event_bus = EventBus()
        timeout_manager = TimeoutManager(budget_seconds=60)
        diagnostics = DiagnosticsCollector()

        ext = PilotExtension(event_bus, timeout_manager, diagnostics)
        ext.tui_handle = None

        ext.shutdown(timeout_sec=10)

    def test_shutdown_publishes_stopped_event(self) -> None:
        """Test shutdown publishes tui-app-stopped event."""
        event_bus = EventBus()
        timeout_manager = TimeoutManager(budget_seconds=60)
        diagnostics = DiagnosticsCollector()

        ext = PilotExtension(event_bus, timeout_manager, diagnostics)

        mock_app = MagicMock()
        mock_app.exit = MagicMock()
        ext.tui_handle = TUIHandle(
            app=mock_app,
            pilot=Mock(),
            event_queue=Mock(),
            started_at=time.time(),
            config_path="/tmp/config.yaml",
        )

        result = ext.shutdown(timeout_sec=10)

        assert result is True
        event = event_bus.wait_for("tui-app-stopped", instance_id=None, timeout_sec=1.0)
        assert event.data["graceful"] is True
        assert isinstance(event.data["duration_sec"], float)

    def test_shutdown_clears_tui_handle(self) -> None:
        """Test shutdown sets tui_handle to None."""
        event_bus = EventBus()
        timeout_manager = TimeoutManager(budget_seconds=60)
        diagnostics = DiagnosticsCollector()

        ext = PilotExtension(event_bus, timeout_manager, diagnostics)

        mock_app = MagicMock()
        mock_app.exit = MagicMock()
        ext.tui_handle = TUIHandle(
            app=mock_app,
            pilot=Mock(),
            event_queue=Mock(),
            started_at=time.time(),
            config_path="/tmp/config.yaml",
        )

        result = ext.shutdown()

        assert result is True
        assert ext.tui_handle is None

    def test_shutdown_handles_app_exit_error(self) -> None:
        """Test shutdown gracefully handles exceptions without raising."""
        event_bus = EventBus()
        timeout_manager = TimeoutManager(budget_seconds=60)
        diagnostics = DiagnosticsCollector()

        ext = PilotExtension(event_bus, timeout_manager, diagnostics)

        mock_app = MagicMock()
        mock_app.exit = MagicMock(side_effect=RuntimeError("Exit failed"))
        ext.tui_handle = TUIHandle(
            app=mock_app,
            pilot=Mock(),
            event_queue=Mock(),
            started_at=time.time(),
            config_path="/tmp/config.yaml",
        )

        result = ext.shutdown()

        assert result is False
        event = event_bus.wait_for("tui-error", instance_id=None, timeout_sec=1.0)
        assert "Exit failed" in event.data["error_message"]


class TestPilotExtensionResourceManagement:
    """Validate resource registration and cleanup."""

    def test_register_resource(self) -> None:
        """Test register_resource tracks resources."""
        event_bus = EventBus()
        timeout_manager = TimeoutManager(budget_seconds=60)
        diagnostics = DiagnosticsCollector()

        ext = PilotExtension(event_bus, timeout_manager, diagnostics)

        dispose_fn = Mock()
        handle = "test-handle"
        ext.register_resource("test-resource", handle, dispose_fn)

        assert len(ext._tui_resources) == 1
        assert ext._tui_resources[0] == ("test-resource", handle, dispose_fn)

    def test_cleanup_all_calls_dispose_functions(self) -> None:
        """Test cleanup_all calls all registered dispose functions."""
        event_bus = EventBus()
        timeout_manager = TimeoutManager(budget_seconds=60)
        diagnostics = DiagnosticsCollector()

        ext = PilotExtension(event_bus, timeout_manager, diagnostics)

        dispose_fn1 = Mock()
        dispose_fn2 = Mock()
        ext.register_resource("resource1", "handle1", dispose_fn1)
        ext.register_resource("resource2", "handle2", dispose_fn2)

        ext.cleanup_all()

        dispose_fn1.assert_called_once_with("handle1")
        dispose_fn2.assert_called_once_with("handle2")
        assert len(ext._tui_resources) == 0

    def test_cleanup_all_handles_dispose_errors(self) -> None:
        """Test cleanup_all continues despite dispose errors."""
        event_bus = EventBus()
        timeout_manager = TimeoutManager(budget_seconds=60)
        diagnostics = DiagnosticsCollector()

        ext = PilotExtension(event_bus, timeout_manager, diagnostics)

        dispose_fn1 = Mock(side_effect=RuntimeError("Dispose failed"))
        dispose_fn2 = Mock()
        ext.register_resource("resource1", "handle1", dispose_fn1)
        ext.register_resource("resource2", "handle2", dispose_fn2)

        ext.cleanup_all()

        dispose_fn1.assert_called_once_with("handle1")
        dispose_fn2.assert_called_once_with("handle2")

    def test_cleanup_all_clears_resources(self) -> None:
        """Test cleanup_all clears resource list."""
        event_bus = EventBus()
        timeout_manager = TimeoutManager(budget_seconds=60)
        diagnostics = DiagnosticsCollector()

        ext = PilotExtension(event_bus, timeout_manager, diagnostics)

        dispose_fn = Mock()
        ext.register_resource("resource", "handle", dispose_fn)

        assert len(ext._tui_resources) == 1
        ext.cleanup_all()
        assert len(ext._tui_resources) == 0
