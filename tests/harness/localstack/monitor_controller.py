"""Monitor controller orchestrating LocalStack instance provisioning."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List

from tests.harness.exceptions import HarnessTimeoutError
from tests.harness.services.diagnostics import DiagnosticsCollector
from tests.harness.services.event_bus import Event, EventBus
from tests.harness.services.resource_registry import ResourceRegistry
from tests.harness.services.ssh_container_pool import SSHContainerPool
from tests.harness.services.timeout_manager import TimeoutManager

logger = logging.getLogger(__name__)


@dataclass
class MonitorAction:
    """Instruction describing discovered instance state.

    Attributes
    ----------
    instance_id : str
        EC2 instance identifier.
    state : str
        Instance lifecycle state (e.g., "running").
    metadata : dict[str, Any]
        Additional attributes supplied by the provider.
    """

    instance_id: str
    state: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MonitorStatistics:
    """Aggregated statistics for diagnostics.

    Attributes
    ----------
    instances_detected : int
        Number of unique instances detected.
    provisioning_failures : int
        Number of provisioning failures encountered.
    poll_iterations : int
        Number of polling iterations executed.
    """

    instances_detected: int = 0
    provisioning_failures: int = 0
    poll_iterations: int = 0


@dataclass
class MonitorShutdownResult:
    """Result returned by shutdown operations.

    Attributes
    ----------
    success : bool
        Indicates whether the shutdown completed successfully.
    error : str | None
        Optional error message on failure.
    """

    success: bool
    error: str | None = None


ActionProvider = Callable[[], Iterable[MonitorAction]]


class MonitorController:
    """Manage polling lifecycle for LocalStack instance detection.

    Attributes
    ----------
    _event_bus : EventBus
        Event bus used to publish lifecycle events.
    _resource_registry : ResourceRegistry
        Registry coordinating cleanup callbacks.
    _timeout_manager : TimeoutManager
        Timeout budget manager for watchdog enforcement.
    _diagnostics : DiagnosticsCollector
        Diagnostics sink for telemetry events.
    _ssh_pool : SSHContainerPool
        Pool handling SSH container port allocations.
    _container_manager : Any
        Manager responsible for provisioning SSH containers.
    _action_provider : ActionProvider
        Callable supplying discovered instance actions.
    _poll_interval_sec : float
        Delay between polling iterations.
    _watchdog_budget_sec : float
        Maximum allowed duration per poll iteration.
    _force_terminate : Callable[[], None] | None
        Optional callback invoked when forced termination required.
    _http_ready_callback : Callable[[str, dict[str, Any]], None] | None
        Optional callback for HTTP readiness handling.
    _thread : threading.Thread | None
        Worker thread executing monitor loop.
    _stop_event : threading.Event
        Event flagging monitor termination.
    _pause_event : threading.Event
        Event controlling pause and resume behaviour.
    _statistics : MonitorStatistics
        Aggregated diagnostic counters.
    _seen_instances : set[str]
        Track of provisioned instance identifiers.
    _state_lock : threading.RLock
        Synchronization primitive guarding start lifecycle.
    """

    def __init__(
        self,
        event_bus: EventBus,
        resource_registry: ResourceRegistry,
        timeout_manager: TimeoutManager,
        diagnostics: DiagnosticsCollector,
        ssh_pool: SSHContainerPool,
        container_manager: Any,
        action_provider: ActionProvider,
        poll_interval_sec: float = 0.5,
        watchdog_budget_sec: float = 10.0,
        force_terminate: Callable[[], None] | None = None,
        http_ready_callback: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> None:
        """Initialize controller dependencies.

        Parameters
        ----------
        event_bus : EventBus
            Event bus for publishing lifecycle events.
        resource_registry : ResourceRegistry
            Registry used to register controller cleanup.
        timeout_manager : TimeoutManager
            Timeout manager for watchdog enforcement.
        diagnostics : DiagnosticsCollector
            Diagnostics collector for telemetry.
        ssh_pool : SSHContainerPool
            Pool managing SSH container allocations.
        container_manager : Any
            Manager responsible for provisioning SSH containers.
        action_provider : ActionProvider
            Callable returning discovered instance actions.
        poll_interval_sec : float, optional
            Interval between polls in seconds.
        watchdog_budget_sec : float, optional
            Maximum allowed duration per poll iteration.
        force_terminate : Callable[[], None] | None, optional
            Callback invoked if shutdown exceeds timeout.
        http_ready_callback : Callable[[str, dict[str, Any]], None] | None, optional
            Optional callback invoked when HTTP services should be initialised.
        """
        self._event_bus = event_bus
        self._resource_registry = resource_registry
        self._timeout_manager = timeout_manager
        self._diagnostics = diagnostics
        self._ssh_pool = ssh_pool
        self._container_manager = container_manager
        self._action_provider = action_provider
        self._poll_interval_sec = poll_interval_sec
        self._watchdog_budget_sec = watchdog_budget_sec
        self._force_terminate = force_terminate
        self._http_ready_callback = http_ready_callback

        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()
        self._statistics = MonitorStatistics()
        self._seen_instances: set[str] = set()
        self._state_lock = threading.RLock()

    def start(self) -> None:
        """Start the monitor thread if it is not already running.

        Notes
        -----
        Subsequent invocations while the thread is alive are no-ops.
        """
        with self._state_lock:
            if self._thread and self._thread.is_alive():
                return

            self._stop_event.clear()
            self._pause_event.set()
            self._thread = threading.Thread(target=self._run, name="LocalStackMonitor")
            self._thread.daemon = False
            self._thread.start()
            self._resource_registry.register(
                kind="thread",
                handle=self._thread,
                dispose_fn=lambda _: self.shutdown(timeout_sec=5.0),
                label="localstack-monitor",
            )

    def pause(self) -> None:
        """Pause polling iterations.

        Notes
        -----
        Polling remains paused until :meth:`resume` is called.
        """
        self._pause_event.clear()
        self._diagnostics.record(
            "monitor", "paused", {"thread": threading.get_ident()}
        )

    def resume(self) -> None:
        """Resume polling iterations.

        Notes
        -----
        Clears a prior pause request and allows polling to continue.
        """
        self._pause_event.set()
        self._diagnostics.record(
            "monitor", "resumed", {"thread": threading.get_ident()}
        )

    def shutdown(self, timeout_sec: float) -> MonitorShutdownResult:
        """Shutdown the monitor thread and return status.

        Parameters
        ----------
        timeout_sec : float
            Maximum time to wait for thread termination.

        Returns
        -------
        MonitorShutdownResult
            Result summarising shutdown outcome.
        """
        self._stop_event.set()
        self._pause_event.set()
        thread = self._thread

        if thread is None:
            return MonitorShutdownResult(success=True)

        thread.join(timeout=timeout_sec)
        if thread.is_alive():
            if self._force_terminate is not None:
                self._force_terminate()
            return MonitorShutdownResult(
                success=False,
                error="monitor thread did not terminate",
            )

        self._event_bus.publish(
            Event(type="monitor-shutdown", instance_id=None, data={})
        )
        return MonitorShutdownResult(success=True)

    def statistics(self) -> MonitorStatistics:
        """Return a snapshot of statistics.

        Returns
        -------
        MonitorStatistics
            Current diagnostic counters.
        """
        return self._statistics

    def _run(self) -> None:
        """Execute the monitoring loop until shutdown is requested."""
        while not self._stop_event.is_set():
            if not self._pause_event.is_set():
                time.sleep(0.05)
                continue

            try:
                with self._timeout_manager.sub_budget(
                    name="monitor-poll", max_seconds=self._watchdog_budget_sec
                ):
                    self._poll_once()
            except HarnessTimeoutError as exc:
                self._diagnostics.record(
                    "monitor",
                    "watchdog-timeout",
                    {"error": str(exc)},
                )
                logger.warning("Monitor poll exceeded watchdog budget: %s", exc)
            except Exception as exc:  # pylint: disable=broad-except
                self._diagnostics.record(
                    "monitor",
                    "poll-error",
                    {"error": str(exc)},
                )
                self._event_bus.publish(
                    Event(
                        type="monitor-error",
                        instance_id=None,
                        data={"error": str(exc)},
                    )
                )
                logger.exception("Exception in monitor polling loop")

            self._statistics.poll_iterations += 1
            self._diagnostics.record(
                "monitor",
                "heartbeat",
                {"iteration": self._statistics.poll_iterations},
            )
            self._event_bus.publish(
                Event(
                    type="monitor-heartbeat",
                    instance_id=None,
                    data={"iteration": self._statistics.poll_iterations},
                )
            )
            time.sleep(self._poll_interval_sec)

    def _poll_once(self) -> None:
        """Execute a single polling iteration."""
        for action in self._action_provider():
            if action.state not in {"pending", "running"}:
                continue
            if action.instance_id in self._seen_instances:
                continue

            self._diagnostics.record(
                "monitor",
                "instance-detected",
                {"instance_id": action.instance_id, **action.metadata},
            )
            self._publish_event(
                "instance-ready",
                action.instance_id,
                {"state": action.state, **action.metadata},
            )

            try:
                metadata = self._provision_instance(action)
            except PortExhaustedError as exc:
                self._statistics.provisioning_failures += 1
                self._diagnostics.record(
                    "monitor",
                    "port-exhausted",
                    {"instance_id": action.instance_id, "error": str(exc)},
                )
                self._publish_error(action.instance_id, exc)
                continue
            except Exception as exc:  # pylint: disable=broad-except
                self._statistics.provisioning_failures += 1
                self._diagnostics.record(
                    "monitor",
                    "provision-error",
                    {"instance_id": action.instance_id, "error": str(exc)},
                )
                self._publish_error(action.instance_id, exc)
                continue

            self._seen_instances.add(action.instance_id)
            self._statistics.instances_detected += 1
            self._emit_sequence(action.instance_id, metadata)

    def _emit_sequence(self, instance_id: str, metadata: dict[str, Any]) -> None:
        """Emit event sequence for a newly provisioned instance.

        Parameters
        ----------
        instance_id : str
            Instance identifier associated with the events.
        metadata : dict[str, Any]
            Event payload metadata.
        """
        ssh_metadata = dict(metadata)
        ssh_metadata.setdefault("ssh_ready_ts", time.time())
        self._publish_event("ssh-ready", instance_id, ssh_metadata)

        http_metadata = dict(ssh_metadata)
        if self._http_ready_callback is not None:
            try:
                self._http_ready_callback(instance_id, http_metadata)
            except Exception as exc:  # pylint: disable=broad-except
                self._diagnostics.record(
                    "monitor",
                    "http-start-error",
                    {"instance_id": instance_id, "error": str(exc)},
                )
                self._publish_error(instance_id, exc)
                return

        http_metadata.setdefault("http_ready_ts", time.time())
        self._publish_event("http-ready", instance_id, http_metadata)

    def _provision_instance(self, action: MonitorAction) -> dict[str, Any]:
        """Provision SSH container and return metadata for events."""
        port: int | None = None
        allocated = False
        try:
            port = self._ssh_pool.allocate_port(action.instance_id)
            allocated = True
        except PortExhaustedError:
            raise

        key_file: Path | None = None
        try:
            port_result, key_file = self._container_manager.create_instance_container(
                action.instance_id,
                host_port=port,
            )
        except Exception:
            if allocated and port is not None:
                try:
                    self._ssh_pool.release_port(action.instance_id, port)
                except Exception:  # pragma: no cover - defensive cleanup
                    logger.debug("Failed to release port after provisioning error")
            raise

        if port_result is None and allocated and port is not None:
            try:
                self._ssh_pool.release_port(action.instance_id, port)
            except Exception:  # pragma: no cover
                logger.debug("Failed to release unused port")
        else:
            port = port_result

        container, _, _ = self._container_manager.instance_map.get(
            action.instance_id,
            (None, None, None),
        )
        container_id = getattr(container, "id", action.instance_id)

        record_metadata = {
            "key_file": str(key_file) if key_file else None,
            "image_id": action.metadata.get("image_id"),
        }
        self._ssh_pool.track_container(
            container_id=container_id,
            instance_id=action.instance_id,
            port=port,
            metadata={k: v for k, v in record_metadata.items() if v is not None},
        )

        metadata: dict[str, Any] = {
            **action.metadata,
            "port": port,
            "key_file": str(key_file) if key_file else None,
            "container_id": container_id,
        }
        return metadata

    def _publish_event(
        self, event_type: str, instance_id: str, data: dict[str, Any]
    ) -> None:
        """Publish typed event with diagnostics side effects."""
        event = Event(type=event_type, instance_id=instance_id, data=data)
        self._event_bus.publish(event)
        diag_payload = {"instance_id": instance_id, **data}
        self._diagnostics.record("monitor-event", event_type, diag_payload)

    def _publish_error(self, instance_id: str, exc: Exception) -> None:
        """Publish monitor-error event for a failure."""
        self._event_bus.publish(
            Event(
                type="monitor-error",
                instance_id=instance_id,
                data={"error": str(exc)},
            )
        )
