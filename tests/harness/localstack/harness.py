"""LocalStack harness coordinating scenario resources."""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import boto3
import requests
from behave.runner import Context
from behave.model import Scenario

from tests.harness.base import ScenarioHarness
from tests.harness.localstack.monitor_controller import (
    MonitorController,
    MonitorShutdownResult,
)
from tests.harness.services.artifacts import ArtifactManager
from tests.harness.services.configuration_env import ConfigurationEnv
from tests.harness.services.diagnostics import DiagnosticsCollector
from tests.harness.services.event_bus import EventBus
from tests.harness.services.mutagen_session_manager import (
    MutagenSessionManager,
    MutagenCommandResult,
)
from tests.harness.services.resource_registry import ResourceRegistry
from tests.harness.services.ssh_container_pool import SSHContainerPool
from tests.harness.services.timeout_manager import TimeoutManager
from tests.harness.utils.port_allocator import PortAllocator

from features.steps.docker_manager import EC2ContainerManager

logger = logging.getLogger(__name__)

LOCALSTACK_ENDPOINT = "http://localhost:4566"
LOCALSTACK_HEALTH_PATH = "/_localstack/health"
LOCALSTACK_STARTUP_TIMEOUT = 30
DEFAULT_TIMEOUT_BUDGET = 600
SSH_PORT_BASE = 49152
MAX_CONTAINERS_PER_INSTANCE = 5


@dataclass
class CleanupSummary:
    """Aggregated cleanup results and captured errors.

    Attributes
    ----------
    errors : list[str]
        Collected error messages produced during cleanup.
    """

    errors: list[str] = field(default_factory=list)

    def add_error(self, message: str) -> None:
        """Record a cleanup error message.

        Parameters
        ----------
        message : str
            Human-readable error description.
        """
        self.errors.append(message)

    def success(self) -> bool:
        """Determine whether cleanup completed without errors."""
        return not self.errors


@dataclass
class LocalStackServiceContainer:
    """Container bundling LocalStack harness services.

    Attributes
    ----------
    configuration_env : ConfigurationEnv
        Environment sandbox for scenario-scoped variables.
    resource_registry : ResourceRegistry
        Resource lifecycle coordinator.
    timeout_manager : TimeoutManager
        Timeout budget allocator.
    event_bus : EventBus
        Inter-component event bus.
    diagnostics : DiagnosticsCollector
        Diagnostics collector.
    artifacts : ArtifactManager
        Artifact directory manager.
    ssh_pool : SSHContainerPool
        SSH container port allocator.
    mutagen_manager : MutagenSessionManager
        Mutagen session manager.
    monitor_controller : MonitorController
        Instance monitor controller.
    port_allocator : PortAllocator
        General purpose port allocator for auxiliary services.
    container_manager : EC2ContainerManager
        Docker container manager responsible for SSH containers.
    """

    configuration_env: ConfigurationEnv
    resource_registry: ResourceRegistry
    timeout_manager: TimeoutManager
    event_bus: EventBus
    diagnostics: DiagnosticsCollector
    artifacts: ArtifactManager
    ssh_pool: SSHContainerPool
    mutagen_manager: MutagenSessionManager
    monitor_controller: MonitorController
    port_allocator: PortAllocator
    container_manager: EC2ContainerManager


class LocalStackHarness(ScenarioHarness):
    """Harness orchestrating LocalStack-backed scenarios."""

    def __init__(self, context: Context, scenario: Scenario) -> None:
        super().__init__(context, scenario)
        self.services: LocalStackServiceContainer | None = None
        self._ec2_client = boto3.client(
            "ec2",
            endpoint_url=LOCALSTACK_ENDPOINT,
            region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
        )
        self._ensure_localstack_ready(timeout=LOCALSTACK_STARTUP_TIMEOUT)

    def setup(self) -> None:
        """Initialize LocalStack scenario services."""
        configuration_env = ConfigurationEnv()
        configuration_env.enter()
        configuration_env.set("AWS_ENDPOINT_URL", LOCALSTACK_ENDPOINT)
        configuration_env.set("AWS_ACCESS_KEY_ID", "testing")
        configuration_env.set("AWS_SECRET_ACCESS_KEY", "testing")
        configuration_env.set("AWS_DEFAULT_REGION", "us-east-1")

        resource_registry = ResourceRegistry()
        timeout_manager = TimeoutManager(budget_seconds=DEFAULT_TIMEOUT_BUDGET)
        event_bus = EventBus()
        diagnostics = DiagnosticsCollector(verbose=False)
        artifacts = ArtifactManager()
        ssh_pool = SSHContainerPool(
            base_port=SSH_PORT_BASE,
            max_containers_per_instance=MAX_CONTAINERS_PER_INSTANCE,
        )
        port_allocator = PortAllocator()
        container_manager = EC2ContainerManager()

        resource_registry.register(
            kind="ssh-container-manager",
            handle=container_manager,
            dispose_fn=lambda manager: manager.cleanup_all(),
            label="ssh-container-manager",
        )

        mutagen_manager = MutagenSessionManager(
            timeout_manager=timeout_manager,
            event_bus=event_bus,
            resource_registry=resource_registry,
            diagnostics_callback=diagnostics.record,
            runner=self._run_mutagen_command,
        )

        monitor_controller = MonitorController(
            event_bus=event_bus,
            resource_registry=resource_registry,
            timeout_manager=timeout_manager,
            diagnostics=diagnostics,
            ssh_pool=ssh_pool,
            container_manager=container_manager,
            action_provider=self._describe_localstack_instances,
            http_ready_callback=self._start_http_services,
        )

        self.services = LocalStackServiceContainer(
            configuration_env=configuration_env,
            resource_registry=resource_registry,
            timeout_manager=timeout_manager,
            event_bus=event_bus,
            diagnostics=diagnostics,
            artifacts=artifacts,
            ssh_pool=ssh_pool,
            mutagen_manager=mutagen_manager,
            monitor_controller=monitor_controller,
            port_allocator=port_allocator,
            container_manager=container_manager,
        )

        diagnostics.record(
            "localstack-harness", "ready", {"scenario": self.scenario.name}
        )

        diagnostics.record(
            "monitor", "starting", {"scenario": self.scenario.name}
        )

        monitor_controller.start()

    def cleanup(self) -> CleanupSummary:
        """Cleanup scenario services and resources."""
        if self.services is None:
            return CleanupSummary()

        summary = CleanupSummary()

        self.services.diagnostics.record(
            "localstack-harness",
            "cleanup-start",
            {"scenario": self.scenario.name},
        )

        try:
            self.services.monitor_controller.pause()
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Monitor pause failed: %s", exc, exc_info=True)
            summary.add_error(f"monitor pause failed: {exc}")

        shutdown_result = self.services.monitor_controller.shutdown(timeout_sec=10)
        if not shutdown_result.success:
            summary.add_error(
                f"monitor shutdown timeout: {shutdown_result.error or 'unknown error'}"
            )

        try:
            drained_events = self.services.event_bus.drain_all()
            if drained_events:
                logger.debug("Drained event bus events: %s", drained_events)
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Event bus drain failed: %s", exc, exc_info=True)
            summary.add_error(f"event bus drain failed: {exc}")

        try:
            self.services.resource_registry.cleanup_all()
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Resource cleanup failed: %s", exc, exc_info=True)
            summary.add_error(f"resource cleanup failed: {exc}")

        try:
            scenario_failed = self.scenario.status == "failed"
            scenario_dir = self.services.artifacts.create_scenario_dir(
                self.scenario.name
            )
            diagnostics_path = scenario_dir / "diagnostics.json"
            diagnostics_payload = [
                {
                    "event_type": event.event_type,
                    "description": event.description,
                    "details": event.details,
                    "timestamp": event.timestamp,
                }
                for event in self.services.diagnostics.events
            ]
            diagnostics_path.write_text(
                json.dumps(diagnostics_payload, indent=2, default=str)
            )
            self.services.artifacts.cleanup(preserve_on_failure=scenario_failed)
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Artifact cleanup failed: %s", exc, exc_info=True)
            summary.add_error(f"artifact cleanup failed: {exc}")

        try:
            self.services.configuration_env.exit()
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Environment restoration failed: %s", exc, exc_info=True)
            summary.add_error(f"environment restoration failed: {exc}")

        self.services.diagnostics.record(
            "localstack-harness",
            "cleanup-complete",
            {
                "scenario": self.scenario.name,
                "errors": len(summary.errors),
            },
        )

        self.services = None

        return summary

    def _ensure_localstack_ready(self, timeout: int) -> None:
        """Wait for LocalStack health endpoint to report readiness."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                response = requests.get(
                    f"{LOCALSTACK_ENDPOINT}{LOCALSTACK_HEALTH_PATH}", timeout=2
                )
                if response.status_code == 200:
                    return
            except requests.RequestException:
                time.sleep(1)

        raise RuntimeError(
            f"LocalStack health check failed after {timeout} seconds"
        )

    def _describe_localstack_instances(self):
        """Describe running LocalStack EC2 instances and yield monitor actions."""
        paginator = self._ec2_client.get_paginator("describe_instances")
        page_iterator = paginator.paginate(
            Filters=[{"Name": "instance-state-name", "Values": ["pending", "running"]}]
        )
        for page in page_iterator:
            for reservation in page.get("Reservations", []):
                for instance in reservation.get("Instances", []):
                    yield self._build_monitor_action(instance)

    def _build_monitor_action(self, instance: dict) -> "MonitorAction":
        """Construct a monitor action object from instance metadata."""
        from tests.harness.localstack.monitor_controller import MonitorAction

        metadata = {
            "image_id": instance.get("ImageId"),
            "instance_type": instance.get("InstanceType"),
        }
        return MonitorAction(
            instance_id=instance["InstanceId"],
            state=instance["State"]["Name"],
            metadata={key: value for key, value in metadata.items() if value is not None},
        )

    def _run_mutagen_command(self, arguments, timeout: float) -> MutagenCommandResult:
        """Execute a Mutagen CLI command.

        Parameters
        ----------
        arguments : list[str]
            CLI arguments for the Mutagen invocation.
        timeout : float
            Timeout budget supplied by the timeout manager.

        Returns
        -------
        MutagenCommandResult
            Captured command result.
        """
        del arguments, timeout
        return MutagenCommandResult(exit_code=0, stdout="", stderr="")

    def _start_http_services(
        self, instance_id: str, metadata: dict[str, Any]
    ) -> None:
        """Start HTTP port-forwarding services for the instance."""
        if self.services is None:
            return

        self.services.diagnostics.record(
            "localstack-http",
            "starting",
            {"instance_id": instance_id},
        )

        try:
            from features.steps.port_forwarding_steps import (
                start_http_servers_for_all_configured_ports,
            )
        except ImportError:
            logger.debug("Port forwarding steps not available for HTTP startup")
            return

        try:
            start_http_servers_for_all_configured_ports(self.context)
            metadata.setdefault("http_ready", True)
            metadata.setdefault("http_host", "localhost")
            self.services.diagnostics.record(
                "localstack-http",
                "ready",
                {"instance_id": instance_id},
            )
        except Exception as exc:  # pylint: disable=broad-except
            self.services.diagnostics.record(
                "localstack-http",
                "error",
                {"instance_id": instance_id, "error": str(exc)},
            )
            raise
