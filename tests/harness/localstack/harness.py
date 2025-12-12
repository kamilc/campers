"""LocalStack harness coordinating scenario resources."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC
from pathlib import Path
from typing import Any

import boto3
import requests
from behave.model import Scenario
from behave.runner import Context
from botocore.exceptions import ClientError

from campers.services.sync import MutagenManager
from tests.harness.base import ScenarioHarness
from tests.harness.localstack.extensions import Extensions
from tests.harness.localstack.monitor_controller import (
    MonitorAction,
    MonitorController,
)
from tests.harness.services.artifacts import ArtifactManager
from tests.harness.services.configuration_env import ConfigurationEnv
from tests.harness.services.diagnostics import DiagnosticsCollector
from tests.harness.services.event_bus import Event, EventBus
from tests.harness.services.mutagen_session_manager import (
    MutagenCommandResult,
    MutagenError,
    MutagenSessionManager,
    MutagenTimeoutError,
)
from tests.harness.services.resource_registry import ResourceRegistry
from tests.harness.services.ssh_container_pool import SSHContainerPool
from tests.harness.services.timeout_manager import TimeoutManager
from tests.harness.utils.port_allocator import PortAllocator
from tests.integration.features.steps.docker_manager import EC2ContainerManager

logger = logging.getLogger(__name__)

LOCALSTACK_ENDPOINT = "http://localhost:4566"
LOCALSTACK_HEALTH_PATH = "/_localstack/health"
LOCALSTACK_STARTUP_TIMEOUT = 30
DEFAULT_TIMEOUT_BUDGET = 600
SSH_PORT_BASE = 49152
MAX_CONTAINERS_PER_INSTANCE = 5
LOCALSTACK_CONTAINER_NAME = "campers-localstack"
LOCALSTACK_IMAGE = os.environ.get(
    "LOCALSTACK_IMAGE",
    "localstack/localstack:latest",
)


@dataclass
class CleanupSummary:
    """Aggregated cleanup results and captured errors.

    Attributes
    ----------
    errors : list[str]
        Collected error messages produced during cleanup.
    step_results : list[dict[str, Any]]
        Per-step teardown diagnostics including status and duration.
    """

    errors: list[str] = field(default_factory=list)
    step_results: list[dict[str, Any]] = field(default_factory=list)

    def add_error(self, message: str) -> None:
        """Record a cleanup error message.

        Parameters
        ----------
        message : str
            Human-readable error description.
        """
        self.errors.append(message)

    def add_step_result(self, result: dict[str, Any]) -> None:
        """Append step diagnostics to the summary."""

        self.step_results.append(result)

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

    _container_started: bool = False

    def __init__(self, context: Context, scenario: Scenario) -> None:
        super().__init__(context, scenario)
        self.services: LocalStackServiceContainer | None = None
        self.extensions: Extensions | None = None
        self._ec2_client = boto3.client(
            "ec2",
            endpoint_url=LOCALSTACK_ENDPOINT,
            region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
        )
        self._event_unsubscribe: Callable[[], None] | None = None
        self._latest_instance_id: str | None = None
        self._event_cache: dict[str, dict[str, Event]] = {}
        self._mutagen_manager = MutagenManager()
        self._mutagen_sessions: dict[str, list[str]] = {}
        self._ensure_localstack_container_running()
        self._ensure_localstack_ready(timeout=LOCALSTACK_STARTUP_TIMEOUT)

    def _ensure_default_vpc_exists(self) -> None:
        """Ensure a default VPC exists in LocalStack.

        LocalStack doesn't automatically create a default VPC like AWS does.
        This method creates one if it doesn't exist, allowing tests that depend
        on a default VPC to function properly.
        """
        try:
            vpcs = self._ec2_client.describe_vpcs(
                Filters=[{"Name": "isDefault", "Values": ["true"]}]
            )

            if vpcs["Vpcs"]:
                logger.debug("Default VPC already exists in LocalStack")
                return

            logger.info("Creating default VPC in LocalStack")
            self._ec2_client.create_default_vpc()
            logger.info("Default VPC created successfully")
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "")
            if error_code == "DefaultVpcAlreadyExists":
                logger.debug("Default VPC already exists (another test created it)")
                return
            if "DefaultSubnetAlreadyExistsInAvailabilityZone" in error_code or \
               "DefaultSubnetAlreadyExistsInAvailabilityZone" in str(exc):
                logger.debug("Default VPC and subnets already exist from previous test")
                return
            logger.error("Failed to ensure default VPC exists: %s", exc)
            raise RuntimeError(f"Failed to ensure default VPC exists: {exc}") from exc
        except Exception as exc:
            logger.error("Failed to ensure default VPC exists: %s", exc)
            raise RuntimeError(f"Failed to ensure default VPC exists: {exc}") from exc

    def setup(self) -> None:
        """Initialize LocalStack scenario services."""
        self._ensure_default_vpc_exists()

        configuration_env = ConfigurationEnv()
        configuration_env.enter()
        configuration_env.set("AWS_ENDPOINT_URL", LOCALSTACK_ENDPOINT)
        configuration_env.set("AWS_ACCESS_KEY_ID", "testing")
        configuration_env.set("AWS_SECRET_ACCESS_KEY", "testing")
        configuration_env.set("AWS_DEFAULT_REGION", "us-east-1")
        configuration_env.set("CAMPERS_TEST_MODE", "0")

        resource_registry = ResourceRegistry()
        scenario_timeout = getattr(self.context, "scenario_timeout", DEFAULT_TIMEOUT_BUDGET)
        is_tui_scenario = self._should_initialize_pilot_extension()
        if is_tui_scenario:
            timeout_budget = scenario_timeout * 1.5
        else:
            timeout_budget = min(scenario_timeout, DEFAULT_TIMEOUT_BUDGET)
        timeout_manager = TimeoutManager(budget_seconds=timeout_budget)
        event_bus = EventBus()
        artifacts = ArtifactManager()
        scenario_dir = artifacts.create_scenario_dir(self.scenario.name)
        diagnostics_log_path = scenario_dir / "diagnostics.log"
        diagnostics = DiagnosticsCollector(verbose=False, log_path=diagnostics_log_path)
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
            runner=self._mutagen_runner,
            terminator=self._mutagen_terminate,
        )

        poll_interval = self._get_monitor_poll_interval()
        watchdog_budget = float(scenario_timeout) if is_tui_scenario else 10.0

        monitor_controller = MonitorController(
            event_bus=event_bus,
            resource_registry=resource_registry,
            timeout_manager=timeout_manager,
            diagnostics=diagnostics,
            ssh_pool=ssh_pool,
            ec2_client=self._ec2_client,
            container_manager=container_manager,
            action_provider=self._describe_localstack_instances,
            http_ready_callback=self._start_http_services,
            poll_interval_sec=poll_interval,
            watchdog_budget_sec=watchdog_budget,
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

        self.extensions = Extensions()
        if self._should_initialize_pilot_extension():
            from tests.harness.localstack.pilot_extension import PilotExtension

            pilot_ext = PilotExtension(
                event_bus=event_bus,
                timeout_manager=timeout_manager,
                diagnostics=diagnostics,
            )
            self.extensions.pilot = pilot_ext

        diagnostics.record("localstack-harness", "ready", {"scenario": self.scenario.name})
        diagnostics.record_system_snapshot("setup-initial-state", include_thread_stacks=False)

        diagnostics.record("monitor", "starting", {"scenario": self.scenario.name})

        self._event_unsubscribe = event_bus.subscribe(self._record_event)
        self.context.container_manager = container_manager
        self.context.harness_event_bus = event_bus

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
        self.services.diagnostics.record_system_snapshot(
            "cleanup-start", include_thread_stacks=False
        )

        teardown_steps = [
            ("monitor-pause", self._teardown_pause_monitor),
            ("tui-shutdown", self._teardown_tui_shutdown),
            ("cli-terminate", self._teardown_terminate_cli_process),
            ("monitor-shutdown", self._teardown_shutdown_monitor),
            ("eventbus-drain", self._teardown_drain_event_bus),
            ("resource-cleanup", self._teardown_resource_registry),
            ("mutagen-terminate", self._teardown_terminate_mutagen_sessions),
            ("ssh-cleanup", self._teardown_cleanup_ssh_resources),
            ("env-restore", self._teardown_restore_environment),
            ("artifact-cleanup", self._teardown_cleanup_artifacts),
            ("diagnostics-export", lambda: self._teardown_export_diagnostics(summary)),
        ]

        for step_name, step_fn in teardown_steps:
            self._run_teardown_step(summary, step_name, step_fn)

        if self._event_unsubscribe is not None:
            try:
                self._event_unsubscribe()
            except Exception:  # pragma: no cover - best effort
                logger.debug("Error unsubscribing event listener", exc_info=True)
            self._event_unsubscribe = None

        if hasattr(self.context, "harness_event_bus"):
            delattr(self.context, "harness_event_bus")

        if hasattr(self.context, "container_manager"):
            delattr(self.context, "container_manager")

        if hasattr(self.context, "monitor_error"):
            delattr(self.context, "monitor_error")

        self.services.diagnostics.record(
            "localstack-harness",
            "cleanup-complete",
            {
                "scenario": self.scenario.name,
                "errors": len(summary.errors),
            },
        )
        self.services.diagnostics.record_system_snapshot(
            "cleanup-complete", include_thread_stacks=False
        )

        self.services = None

        return summary

    def _run_teardown_step(
        self,
        summary: CleanupSummary,
        step_name: str,
        func: Callable[[], Any],
    ) -> None:
        """Execute a teardown step with diagnostics and error handling."""

        start = time.perf_counter()
        status = "success"
        details: dict[str, Any] = {}

        try:
            result = func()
            if isinstance(result, tuple) and len(result) == 2:
                status_candidate, payload = result
                if status_candidate:
                    status = status_candidate
                if isinstance(payload, dict):
                    details = payload
            elif isinstance(result, dict):
                details = result
            elif result is not None:
                details = {"result": result}
        except Exception as exc:  # pylint: disable=broad-except
            status = "error"
            details = {"error": str(exc)}
            summary.add_error(f"{step_name} failed: {exc}")
            logger.warning("Teardown step '%s' failed", step_name, exc_info=True)

        if status == "warning" and "error" in details:
            summary.add_error(f"{step_name} warning: {details['error']}")

        duration = time.perf_counter() - start

        step_result = {
            "step": step_name,
            "status": status,
            "duration_sec": duration,
            "details": details,
        }
        summary.add_step_result(step_result)

        self.services.diagnostics.record(
            "teardown",
            step_name,
            {"status": status, "duration_sec": duration, **details},
        )

    def _teardown_pause_monitor(self) -> dict[str, Any]:
        self.services.monitor_controller.pause()
        return {"paused": True}

    def _teardown_tui_shutdown(self) -> tuple[str, dict[str, Any]]:
        if self.extensions is None or self.extensions.pilot is None:
            return "skip", {"reason": "pilot-extension-not-initialized"}

        if self.extensions.pilot.tui_handle is None:
            return "success", {"tui_was_running": False}

        try:
            self.extensions.pilot.shutdown(timeout_sec=20)
            return "success", {"tui_was_running": True, "shutdown": "graceful"}
        except TimeoutError:
            return "error", {
                "reason": "tui-shutdown-timeout",
                "timeout_sec": 20,
            }
        except Exception as exc:
            return "error", {
                "reason": f"tui-shutdown-error: {exc}",
                "error_type": type(exc).__name__,
            }

    def _teardown_terminate_cli_process(self) -> dict[str, Any]:
        proc = getattr(self.context, "app_process", None)
        if proc is None:
            return {"process_found": False}

        details: dict[str, Any] = {"process_found": True}
        try:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
                    details["forced"] = True
            details["returncode"] = proc.poll()
        finally:
            self.context.app_process = None

        return details

    def _teardown_shutdown_monitor(self) -> tuple[str, dict[str, Any]]:
        result = self.services.monitor_controller.shutdown(timeout_sec=10)
        if result.success:
            return "success", {"shutdown": True}
        return "error", {"error": result.error or "monitor shutdown timeout"}

    def _teardown_drain_event_bus(self) -> dict[str, Any]:
        drained = self.services.event_bus.drain_all()
        events = sum(len(items) for items in drained.values())
        return {"channels": len(drained), "events_drained": events}

    def _teardown_resource_registry(self) -> dict[str, Any]:
        self.services.resource_registry.cleanup_all()
        return {"resources_cleaned": True}

    def _teardown_terminate_mutagen_sessions(self) -> tuple[str, dict[str, Any]]:
        summary = self.services.mutagen_manager.terminate_all(timeout_sec=30)
        status = "success"
        details: dict[str, Any] = {
            "terminated": len(summary.terminated),
            "failures": len(summary.failures),
        }
        if summary.failures:
            status = "warning"
            details["error"] = "mutagen termination failures"
            details["failures_detail"] = summary.failures
        self._mutagen_sessions.clear()
        return status, details

    def _teardown_cleanup_ssh_resources(self) -> dict[str, Any]:
        self.services.container_manager.cleanup_all()
        pool_summary = self.services.ssh_pool.cleanup_all()
        self.services.resource_registry.resources.clear()
        return {
            "containers_tracked": pool_summary.get("containers", 0),
            "instances": pool_summary.get("instances", 0),
        }

    def _teardown_restore_environment(self) -> dict[str, Any]:
        self.services.configuration_env.exit()
        return {"restored": True}

    def _teardown_cleanup_artifacts(self) -> dict[str, Any]:
        scenario_failed = self.scenario.status == "failed"
        if not scenario_failed:
            self.services.diagnostics.set_log_path(None)
        self.services.artifacts.cleanup(preserve_on_failure=scenario_failed)
        return {"preserved": scenario_failed}

    def _teardown_export_diagnostics(self, summary: CleanupSummary) -> dict[str, Any]:
        from datetime import datetime

        artifacts = self.services.artifacts
        scenario_slug = getattr(artifacts, "scenario_slug", None)
        if not scenario_slug:
            scenario_slug = self.scenario.name.lower().replace(" ", "-").replace("/", "-")
        run_id = getattr(artifacts, "run_id", None)
        if not run_id:
            run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")

        diagnostics_dir = artifacts.base_dir / "_diagnostics" / scenario_slug
        diagnostics_dir.mkdir(parents=True, exist_ok=True)

        diagnostics_path = diagnostics_dir / f"{run_id}.json"
        live_log_path = None
        if artifacts.scenario_dir is not None:
            candidate = artifacts.scenario_dir / "diagnostics.log"
            if candidate.exists():
                live_log_path = str(candidate)

        payload = {
            "scenario": self.scenario.name,
            "status": self.scenario.status,
            "errors": summary.errors,
            "steps": summary.step_results,
            "events": [
                {
                    "event_type": event.event_type,
                    "description": event.description,
                    "details": event.details,
                    "timestamp": event.timestamp,
                }
                for event in self.services.diagnostics.events
            ],
        }

        if live_log_path:
            payload["event_log_path"] = live_log_path

        diagnostics_path.write_text(json.dumps(payload, indent=2, default=str))
        return {"path": str(diagnostics_path)}

    @classmethod
    def stop_localstack_container(cls) -> bool:
        """Stop the shared LocalStack container if running."""

        if not cls._container_started:
            logger.debug("LocalStack container stop skipped; not started by harness")
            return True

        try:
            cls._stop_localstack_container()
            cls._container_started = False
            return True
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Failed to stop LocalStack container: %s", exc)
            return False

    def _ensure_localstack_ready(self, timeout: int) -> None:
        """Wait for LocalStack health endpoint to report readiness."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                response = requests.get(f"{LOCALSTACK_ENDPOINT}{LOCALSTACK_HEALTH_PATH}", timeout=2)
                if response.status_code == 200:
                    return
            except requests.RequestException:
                time.sleep(1)

        raise RuntimeError(f"LocalStack health check failed after {timeout} seconds")

    def _get_monitor_poll_interval(self) -> float:
        """Determine the monitor polling interval based on scenario type.

        For TUI/pilot scenarios, uses faster polling (50ms instead of 500ms)
        to minimize SSH tag race conditions where production code queries tags before
        the monitor has provisioned and tagged instances, while still respecting
        scenario timeouts and avoiding API rate limiting.

        Returns
        -------
        float
            Polling interval in seconds
        """
        if self._should_initialize_pilot_extension():
            logger.info("TUI scenario detected; using faster monitor polling (50ms)")
            return 0.05
        return 0.5

    def _should_initialize_pilot_extension(self) -> bool:
        """Determine if PilotExtension should be initialized for this scenario.

        Returns
        -------
        bool
            True if scenario has @pilot or @tui tags, False otherwise
        """
        if not self.scenario.tags:
            return False

        pilot_tags = {"pilot", "tui"}
        return any(tag in pilot_tags for tag in self.scenario.tags)

    def wait_for_event(self, event_type: str, instance_id: str | None, timeout_sec: float) -> Event:
        """Wait for a typed event from the LocalStack event bus.

        Parameters
        ----------
        event_type : str
            Target event type to wait for (e.g., ``"ssh-ready"``).
        instance_id : str | None
            Optional instance identifier filter.
        timeout_sec : float
            Maximum time to wait for the event in seconds.

        Returns
        -------
        Event
            Event that satisfied the wait condition.
        """
        if self.services is None:
            raise RuntimeError("Harness services not initialised")

        event = self.services.event_bus.wait_for(
            event_type=event_type,
            instance_id=instance_id,
            timeout_sec=timeout_sec,
        )
        return event

    def current_instance_id(self) -> str | None:
        """Return the most recently observed instance identifier."""

        return self._latest_instance_id

    def get_ssh_details(self, instance_id: str) -> tuple[str | None, int | None, Path | None]:
        """Retrieve SSH connection details for an instance.

        Parameters
        ----------
        instance_id : str
            Instance identifier whose SSH information is requested.

        Returns
        -------
        tuple[str | None, int | None, Path | None]
            Tuple of host, port, and key path if known.
        """

        if self.services is None:
            raise RuntimeError("Harness services not initialised")

        return self.services.container_manager.get_instance_ssh_config(instance_id)

    def _record_event(self, event: Event) -> None:
        """Track published events for quick lookup and diagnostics."""

        if event.instance_id:
            self._latest_instance_id = event.instance_id
            per_instance = self._event_cache.setdefault(event.instance_id, {})
            per_instance[event.type] = event
            if event.type == "ssh-ready":
                self._maybe_start_mutagen_sync(event.instance_id, event.data)
        if event.type == "monitor-error":
            self.context.monitor_error = event.data.get("error")

    def _ensure_localstack_container_running(self) -> None:
        """Ensure LocalStack container is running for the scenario."""

        try:
            started = self._start_localstack_container()
            if started:
                logger.info("LocalStack container started by harness")
            else:
                logger.debug("LocalStack container already running")
        except Exception as exc:  # pylint: disable=broad-except
            raise RuntimeError(f"Failed to start LocalStack container: {exc}") from exc

    @classmethod
    def _start_localstack_container(cls) -> bool:
        """Start LocalStack container if not already running."""

        try:
            import docker

            docker_client = docker.from_env()

            try:
                container = docker_client.containers.get(LOCALSTACK_CONTAINER_NAME)
                container.reload()
                if container.status != "running":
                    container.start()
                    cls._container_started = True
                    return True
                cls._container_started = True
                return False
            except docker.errors.NotFound:
                pass

            cmd = [
                "docker",
                "run",
                "-d",
                "--rm",
                "--name",
                LOCALSTACK_CONTAINER_NAME,
                "-p",
                "4566:4566",
                "-p",
                "4510-4559:4510-4559",
                "-v",
                "/var/run/docker.sock:/var/run/docker.sock",
                LOCALSTACK_IMAGE,
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                raise RuntimeError(result.stderr.strip())

            cls._container_started = True
            return True

        except Exception:
            raise

    @classmethod
    def _stop_localstack_container(cls) -> None:
        """Stop LocalStack container if running."""

        try:
            import docker

            docker_client = docker.from_env()
            try:
                container = docker_client.containers.get(LOCALSTACK_CONTAINER_NAME)
            except docker.errors.NotFound:
                return

            container.stop(timeout=10)
        except Exception:
            raise

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

    def _build_monitor_action(self, instance: dict) -> MonitorAction:
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

    def _mutagen_runner(self, arguments: list[str], timeout: float) -> MutagenCommandResult:
        """Execute Mutagen operations via MutagenManager."""

        if not arguments:
            return MutagenCommandResult(exit_code=1, stdout="", stderr="no command")

        command = arguments[0]

        if command == "create" and len(arguments) > 1:
            payload = json.loads(arguments[1])
            session_name = payload["session_name"]
            self._mutagen_manager.cleanup_orphaned_session(session_name)
            self._mutagen_manager.create_sync_session(
                session_name=session_name,
                local_path=payload["local_path"],
                remote_path=payload["remote_path"],
                host=payload["host"],
                key_file=payload["key_file"],
                username=payload["username"],
                ignore_patterns=payload.get("ignore_patterns", []),
                include_vcs=payload.get("include_vcs", False),
                ssh_wrapper_dir=payload.get("ssh_wrapper_dir"),
                ssh_port=payload.get("ssh_port", 22),
            )
            return MutagenCommandResult(exit_code=0, stdout="", stderr="")

        if command == "wait" and len(arguments) > 1:
            payload = json.loads(arguments[1])
            session_name = payload["session_name"]
            timeout_budget = payload.get("timeout", timeout)
            try:
                self._mutagen_manager.wait_for_initial_sync(
                    session_name=session_name,
                    timeout=int(timeout_budget),
                )
                return MutagenCommandResult(exit_code=0, stdout="", stderr="")
            except RuntimeError as exc:  # MutagenManager raises RuntimeError on timeout
                return MutagenCommandResult(exit_code=1, stdout="", stderr=str(exc))

        cmd = ["mutagen", *arguments]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            return MutagenCommandResult(
                exit_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
            )
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError(f"Mutagen command timed out: {' '.join(cmd)}") from exc

    def _mutagen_terminate(self, session_id: str) -> None:
        """Terminate a Mutagen session via MutagenManager."""

        try:
            self._mutagen_manager.terminate_session(session_id)
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Mutagen termination failed for %s: %s", session_id, exc)

    def _maybe_start_mutagen_sync(self, instance_id: str, metadata: dict[str, Any]) -> None:
        """Start Mutagen synchronization if configured for the scenario."""

        if self.services is None:
            return

        if os.environ.get("CAMPERS_DISABLE_MUTAGEN") == "1":
            logger.info(
                "Mutagen disabled via CAMPERS_DISABLE_MUTAGEN=1; skipping harness sync setup"
            )
            return

        config_data = getattr(self.context, "config_data", None)
        defaults = (config_data or {}).get("defaults", {})
        sync_paths: list[dict[str, Any]] = defaults.get("sync_paths", [])

        if not sync_paths:
            return

        ssh_port = metadata.get("port")
        key_file = metadata.get("key_file")
        host = metadata.get("host", "localhost")

        if not ssh_port or not key_file:
            logger.debug("Skipping Mutagen start due to missing SSH details")
            return

        if shutil.which("mutagen") is None:
            message = "Mutagen executable not found"
            self.services.event_bus.publish(
                Event(
                    type="mutagen-status",
                    instance_id=instance_id,
                    data={"status": "error", "error": message},
                )
            )
            self.context.mutagen_error = message
            return

        test_mode = os.environ.get("CAMPERS_TEST_MODE") == "1"
        ignore_patterns = defaults.get("ignore", [])
        include_vcs = defaults.get("include_vcs", False)
        ssh_wrapper_dir = os.environ.get("CAMPERS_DIR", str(Path.home() / ".campers"))

        sessions_for_instance = self._mutagen_sessions.setdefault(instance_id, [])

        for index, sync_config in enumerate(sync_paths):
            session_id = f"campers-{instance_id}-{index}"
            if session_id in sessions_for_instance:
                continue

            local_path = sync_config.get("local")
            remote_path = sync_config.get("remote")
            if not local_path or not remote_path:
                logger.warning(
                    "Skipping Mutagen sync due to missing paths: local=%s remote=%s",
                    local_path,
                    remote_path,
                )
                continue

            payload = {
                "session_name": session_id,
                "local_path": local_path,
                "remote_path": remote_path,
                "host": host,
                "key_file": str(key_file),
                "username": "ubuntu",
                "ignore_patterns": ignore_patterns,
                "include_vcs": include_vcs,
                "ssh_wrapper_dir": ssh_wrapper_dir,
                "ssh_port": int(ssh_port),
            }

            self.services.diagnostics.record(
                "mutagen",
                "create",
                {"instance_id": instance_id, "session": session_id},
            )

            if test_mode:
                self.services.event_bus.publish(
                    Event(
                        type="mutagen-status",
                        instance_id=session_id,
                        data={"status": "simulated", "instance_id": instance_id},
                    )
                )
                sessions_for_instance.append(session_id)
                continue

            try:
                self.services.mutagen_manager.create_session(
                    session_id=session_id,
                    instance_id=instance_id,
                    arguments=["create", json.dumps(payload)],
                    timeout_sec=60,
                    metadata={"local_path": local_path, "remote_path": remote_path},
                )
                sessions_for_instance.append(session_id)
                self.services.event_bus.publish(
                    Event(
                        type="mutagen-status",
                        instance_id=session_id,
                        data={"status": "starting"},
                    )
                )
                self._wait_for_initial_sync(session_id)
            except MutagenTimeoutError as exc:
                self.services.event_bus.publish(
                    Event(
                        type="mutagen-status",
                        instance_id=session_id,
                        data={"status": "timeout", "error": str(exc)},
                    )
                )
                self.context.mutagen_error = str(exc)
            except MutagenError as exc:
                self.services.event_bus.publish(
                    Event(
                        type="mutagen-status",
                        instance_id=session_id,
                        data={"status": "error", "error": str(exc)},
                    )
                )
                self.context.mutagen_error = str(exc)
            except Exception as exc:  # pylint: disable=broad-except
                self.services.event_bus.publish(
                    Event(
                        type="mutagen-status",
                        instance_id=session_id,
                        data={"status": "error", "error": str(exc)},
                    )
                )
                self.context.mutagen_error = str(exc)

    def _wait_for_initial_sync(self, session_id: str) -> None:
        """Wait for Mutagen initial sync and publish status events."""

        if os.environ.get("CAMPERS_SYNC_TIMEOUT") == "1":
            raise MutagenTimeoutError("Mutagen sync timed out after 1 seconds")

        wait_result = self._mutagen_runner(
            [
                "wait",
                json.dumps({"session_name": session_id, "timeout": 300}),
            ],
            timeout=300,
        )

        if wait_result.exit_code != 0:
            raise MutagenError(wait_result.stderr or "mutagen wait failed")

        self.services.event_bus.publish(
            Event(
                type="mutagen-status",
                instance_id=session_id,
                data={"status": "watching"},
            )
        )

    def _start_http_services(self, instance_id: str, metadata: dict[str, Any]) -> None:
        """Start HTTP port-forwarding services for the instance."""
        if self.services is None:
            return

        self.services.diagnostics.record(
            "localstack-http",
            "starting",
            {"instance_id": instance_id},
        )

        try:
            from tests.integration.features.steps.port_forwarding_steps import (
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
