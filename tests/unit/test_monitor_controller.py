"""Unit tests for MonitorController."""

import threading
import time
from collections import deque
from pathlib import Path

from tests.unit.harness.localstack.monitor_controller import (
    MonitorAction,
    MonitorController,
)
from tests.unit.harness.services.diagnostics import DiagnosticsCollector
from tests.unit.harness.services.event_bus import EventBus
from tests.unit.harness.services.resource_registry import ResourceRegistry
from tests.unit.harness.services.ssh_container_pool import SSHContainerPool
from tests.unit.harness.services.timeout_manager import TimeoutManager


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

        class DummyContainer:
            def __init__(self, identifier: str) -> None:
                self.id = identifier
                self.short_id = identifier[:12]
                self.status = "created"

            def reload(self) -> None:
                self.status = "running"

        class DummyContainerManager:
            def __init__(self) -> None:
                self.instance_map: dict[
                    str, tuple[DummyContainer, int | None, Path]
                ] = {}

            def create_instance_container(
                self, instance_id: str, host_port: int | None = None
            ) -> tuple[int | None, Path]:
                container = DummyContainer(f"container-{instance_id}")
                container.reload()
                key_path = Path(f"/tmp/{instance_id}.pem")
                self.instance_map[instance_id] = (container, host_port, key_path)
                return host_port, key_path

        container_manager = DummyContainerManager()

        class DummyEC2Client:
            def __init__(self) -> None:
                self.tags: list[dict[str, str]] = []

            def create_tags(self, Resources, Tags):  # noqa: N803 - boto style
                self.tags.append({"resource": Resources[0], "tags": Tags})

        ec2_client = DummyEC2Client()
        http_calls: list[tuple[str, dict]] = []

        def http_callback(instance_id: str, metadata: dict[str, object]) -> None:
            http_calls.append((instance_id, metadata))

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
            ec2_client=ec2_client,
            container_manager=container_manager,
            action_provider=provider,
            poll_interval_sec=0.05,
            http_ready_callback=http_callback,
        )

        actions.append(
            [
                MonitorAction(
                    instance_id="i-1", state="running", metadata={"ami": "ami-123"}
                )
            ]
        )
        controller.start()

        instance_event = bus.wait_for(
            "instance-ready", instance_id="i-1", timeout_sec=1.0
        )
        assert instance_event.data["state"] == "running"
        ssh_event = bus.wait_for("ssh-ready", instance_id="i-1", timeout_sec=1.0)
        assert ssh_event.data["ami"] == "ami-123"
        assert ssh_event.data["port"] == 61000
        http_event = bus.wait_for("http-ready", instance_id="i-1", timeout_sec=1.0)
        assert http_event.data["container_id"].startswith("container-i-1")
        assert http_calls and http_calls[0][0] == "i-1"
        assert any(tag_entry["resource"] == "i-1" for tag_entry in ec2_client.tags)
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
        new_instance = bus.wait_for(
            "instance-ready", instance_id="i-2", timeout_sec=1.0
        )
        assert new_instance.instance_id == "i-2"
        ssh_second = bus.wait_for("ssh-ready", instance_id="i-2", timeout_sec=1.0)
        assert ssh_second.data["port"] == 61001

        result = controller.shutdown(timeout_sec=1.0)
        assert result.success
        shutdown_event = bus.wait_for(
            "monitor-shutdown", instance_id=None, timeout_sec=1.0
        )
        assert shutdown_event.type == "monitor-shutdown"
        assert len(registry.resources) >= 1
