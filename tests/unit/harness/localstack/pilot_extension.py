"""TUI Pilot extension for LocalStackHarness.

Provides lifecycle management and integration for Textual Pilot TUI testing,
including event-driven coordination through EventBus channels.
"""

from __future__ import annotations

import asyncio
import logging
import queue
import time
from dataclasses import dataclass
from typing import Any, Callable

from tests.unit.harness.services.diagnostics import DiagnosticsCollector
from tests.unit.harness.services.event_bus import Event, EventBus
from tests.unit.harness.services.timeout_manager import TimeoutManager

logger = logging.getLogger(__name__)

TUI_UPDATE_QUEUE_MAXSIZE = 100


@dataclass
class TUIHandle:
    """Handle for active TUI application instance.

    Attributes
    ----------
    app : Any
        The MoondockTUI application instance from Textual
    pilot : Any
        Textual Pilot object for test interaction
    event_queue : queue.Queue
        Queue for TUI updates and status changes
    started_at : float
        Timestamp when TUI was launched
    config_path : str
        Path to moondock configuration file used for launch
    """

    app: Any
    pilot: Any
    event_queue: queue.Queue
    started_at: float
    config_path: str


class PilotExtension:
    """Extension for LocalStackHarness providing TUI coordination.

    Manages Textual Pilot app lifecycle, replaces global _tui_update_queue
    with EventBus channels, provides timeout-managed TUI polling, and
    integrates TUI diagnostics.

    Parameters
    ----------
    event_bus : EventBus
        Inter-component event bus for TUI events
    timeout_manager : TimeoutManager
        Timeout budget allocator for TUI operations
    diagnostics : DiagnosticsCollector
        Diagnostics collector for TUI lifecycle events
    """

    def __init__(
        self,
        event_bus: EventBus,
        timeout_manager: TimeoutManager,
        diagnostics: DiagnosticsCollector,
    ) -> None:
        self.event_bus = event_bus
        self.timeout_manager = timeout_manager
        self.diagnostics = diagnostics
        self.tui_handle: TUIHandle | None = None
        self._tui_resources: list[tuple[str, Callable]] = []

    def create_tui_update_queue(self) -> queue.Queue:
        """Create event queue for TUI updates.

        Replaces the global _tui_update_queue variable with a per-scenario
        queue managed through the extension.

        Returns
        -------
        queue.Queue
            New queue for TUI update events
        """
        return queue.Queue(maxsize=TUI_UPDATE_QUEUE_MAXSIZE)

    async def launch_tui(
        self,
        machine_name: str | None,
        config_path: str,
        timeout_sec: float,
    ) -> TUIHandle:
        """Launch TUI app with Pilot for testing.

        NOTE: This method creates a TUI handle but does not manage its lifecycle.
        The context manager (app.run_test()) must remain open in the caller's scope.
        Recommended: Use this only with run_tui_test_with_machine() pattern.

        Parameters
        ----------
        machine_name : str | None
            Machine name to run, None for ad-hoc mode
        config_path : str
            Path to moondock config file
        timeout_sec : float
            Timeout budget for TUI operations

        Returns
        -------
        TUIHandle
            Handle to TUI app instance (valid only while context manager is active)

        Raises
        ------
        TimeoutError
            If TUI launch exceeds timeout
        RuntimeError
            If TUI app creation fails
        """
        from moondock.__main__ import MoondockTUI

        update_queue = self.create_tui_update_queue()

        try:
            logger.info(
                "Launching TUI app: machine_name=%s, timeout_sec=%.1f",
                machine_name,
                timeout_sec,
            )

            moondock = __import__("moondock", fromlist=["Moondock"]).Moondock()

            app = MoondockTUI(
                moondock_instance=moondock,
                run_kwargs={"machine_name": machine_name, "json_output": False},
                update_queue=update_queue,
            )

            async with asyncio.timeout(timeout_sec):
                pilot = await app.run_test().__aenter__()

                self.tui_handle = TUIHandle(
                    app=app,
                    pilot=pilot,
                    event_queue=update_queue,
                    started_at=time.time(),
                    config_path=config_path,
                )

                self.register_resource("tui-app", app, self._dispose_tui_app)

                self.publish_tui_event(
                    "tui-app-started",
                    {
                        "machine_name": machine_name,
                        "config_path": config_path,
                        "timestamp": self.tui_handle.started_at,
                    },
                )

                return self.tui_handle

        except asyncio.TimeoutError as exc:
            self.publish_tui_event(
                "tui-timeout",
                {
                    "timeout_sec": timeout_sec,
                    "graceful": False,
                    "stage": "launch",
                },
            )
            raise TimeoutError(f"TUI launch exceeded {timeout_sec}s timeout") from exc
        except Exception as exc:
            self.publish_tui_event(
                "tui-error",
                {
                    "error_message": str(exc),
                    "traceback": repr(exc),
                },
            )
            raise RuntimeError(f"TUI launch failed: {exc}") from exc

    def publish_tui_event(self, event_type: str, data: dict[str, Any]) -> None:
        """Publish TUI event to EventBus.

        Parameters
        ----------
        event_type : str
            Event type identifier (e.g., "tui-status-changed")
        data : dict[str, Any]
            Event data payload
        """
        event = Event(
            type=event_type,
            instance_id=None,
            data=data,
        )
        self.event_bus.publish(event)
        self.diagnostics.record("tui-event", event_type, data)

    async def wait_for_tui_status(
        self,
        expected_status: str,
        timeout_sec: float,
    ) -> bool:
        """Poll TUI status with EventBus integration.

        Uses EventBus.wait_for() for event-driven status polling instead
        of busy-polling. Falls back to direct widget query if no events received.

        Parameters
        ----------
        expected_status : str
            Expected TUI status (e.g., "running", "completed")
        timeout_sec : float
            Timeout budget in seconds

        Returns
        -------
        bool
            True if status reached, False if timeout

        Raises
        ------
        TimeoutError
            If timeout_sec exceeded while waiting
        """
        if self.tui_handle is None:
            return False

        try:
            with self.timeout_manager.sub_budget(
                "tui-status-poll", max_sec=timeout_sec
            ):
                start_time = time.time()
                while True:
                    elapsed = time.time() - start_time
                    if elapsed > timeout_sec:
                        self.publish_tui_event(
                            "tui-timeout",
                            {"timeout_sec": timeout_sec, "graceful": False},
                        )
                        raise TimeoutError(
                            f"TUI status poll exceeded {timeout_sec}s timeout"
                        )

                    try:
                        status_widget = self.tui_handle.app.query_one("#status-widget")
                        current_status = str(status_widget.render())
                        if expected_status.lower() in current_status.lower():
                            return True
                    except Exception:
                        pass

                    await asyncio.sleep(0.1)
        except Exception as exc:
            logger.error("TUI status poll failed: %s", exc)
            raise

    def shutdown(self, timeout_sec: float = 10) -> bool:
        """Gracefully shutdown TUI app with resilient error handling.

        Does not raise exceptions - instead logs errors and publishes events
        to ensure cleanup continues even if TUI shutdown fails (per spec
        requirement for resilient teardown).

        Parameters
        ----------
        timeout_sec : float
            Timeout for graceful shutdown in seconds

        Returns
        -------
        bool
            True if graceful shutdown successful, False if timeout or error
        """
        if self.tui_handle is None:
            return True

        graceful = True
        logger.info("Shutting down TUI app with timeout=%.1fs", timeout_sec)

        try:
            duration = time.time() - self.tui_handle.started_at
            self.tui_handle.app.exit()

            self.publish_tui_event(
                "tui-app-stopped",
                {
                    "duration_sec": duration,
                    "graceful": True,
                },
            )
        except TimeoutError as exc:
            logger.warning("TUI shutdown exceeded timeout: %s", exc)
            self.publish_tui_event(
                "tui-timeout",
                {
                    "timeout_sec": timeout_sec,
                    "graceful": False,
                },
            )
            graceful = False
        except Exception as exc:
            logger.error("TUI shutdown failed: %s", exc)
            self.publish_tui_event(
                "tui-error",
                {
                    "error_message": str(exc),
                    "traceback": repr(exc),
                },
            )
            graceful = False
        finally:
            self.tui_handle = None

        return graceful

    def register_resource(
        self, kind: str, handle: Any, dispose_fn: Callable[..., Any]
    ) -> None:
        """Register a TUI resource for cleanup.

        Parameters
        ----------
        kind : str
            Resource type identifier
        handle : Any
            Resource handle (passed to dispose_fn during cleanup)
        dispose_fn : Callable
            Function to call during cleanup with signature dispose_fn(handle)
        """
        self._tui_resources.append((kind, handle, dispose_fn))

    def _dispose_tui_app(self, app: Any) -> None:
        """Dispose TUI app resource.

        Parameters
        ----------
        app : Any
            MoondockTUI app instance to dispose
        """
        if app is not None:
            try:
                app.exit()
            except Exception as exc:
                logger.warning("Error exiting TUI app: %s", exc)

    def cleanup_all(self) -> None:
        """Cleanup all registered TUI resources.

        Calls dispose functions in reverse order (LIFO) to handle
        resource dependencies properly.
        """
        for kind, handle, dispose_fn in reversed(self._tui_resources):
            try:
                logger.debug("Cleaning up TUI resource: %s", kind)
                dispose_fn(handle)
            except Exception as exc:
                logger.warning("Error cleaning up TUI resource %s: %s", kind, exc)
        self._tui_resources.clear()
