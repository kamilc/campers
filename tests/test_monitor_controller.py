"""Unit tests for MonitorController."""

import threading
import time
from collections import deque

import pytest

from tests.harness.localstack.monitor_controller import (
    MonitorAction,
    MonitorController,
)
from tests.harness.services.diagnostics import DiagnosticsCollector
from tests.harness.services.event_bus import EventBus
from tests.harness.services.resource_registry import ResourceRegistry
from tests.harness.services.ssh_container_pool import SSHContainerPool
from tests.harness.services.timeout_manager import TimeoutManager


class TestMonitorControllerLifecycle:
    """Validate monitor controller lifecycle behaviour."""

    def test_start_pause_resume_shutdown(self) -> None:
        """Test full lifecycle including pause and resume semantics."""
        bus = EventBus()
        registry = ResourceRegistry()
        timeout_manager = TimeoutManager(budget_seconds=30)
        diagnostics = DiagnosticsCollector()
        ssh_pool = SSHContainerPool(base_port=61000, port_probe=lambda port: True)
        actions: deque[list[MonitorAction]] = deque()
        lock = threading.Lock()

        def provider() -> list[MonitorAction]:
            with lock:
                if actions:
                    return actions.popleft()
            return []

        controller = MonitorController(
            event_bus=bus,
            resource_registry=registry,
            timeout_manager=timeout_manager,
            diagnostics=diagnostics,
            ssh_pool=ssh_pool,
            action_provider=provider,
            poll_interval_sec=0.05,
        )

        actions.append([MonitorAction(instance_id="i-1", state="running", metadata={"ami": "ami-123"})])
        controller.start()

        instance_event = bus.wait_for("instance-ready", instance_id="i-1", timeout_sec=1.0)
        assert instance_event.data["port"] == 61000
        ssh_event = bus.wait_for("ssh-ready", instance_id="i-1", timeout_sec=1.0)
        assert ssh_event.data["ami"] == "ami-123"
        heartbeat = bus.wait_for("monitor-heartbeat", instance_id=None, timeout_sec=1.0)
        assert heartbeat.data["iteration"] >= 1

        controller.pause()
        actions.append([MonitorAction(instance_id="i-2", state="running", metadata={})])
        time.sleep(0.2)
        drained = bus.drain_all()
        assert "instance-ready" not in drained or all(
            event.instance_id != "i-2" for event in drained.get("instance-ready", [])
        )

        controller.resume()
        new_instance = bus.wait_for("instance-ready", instance_id="i-2", timeout_sec=1.0)
        assert new_instance.instance_id == "i-2"

        result = controller.shutdown(timeout_sec=1.0)
        assert result.success
        shutdown_event = bus.wait_for("monitor-shutdown", instance_id=None, timeout_sec=1.0)
        assert shutdown_event.type == "monitor-shutdown"
        assert len(registry.resources) >= 1
