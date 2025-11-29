"""Textual TUI application for campers."""

from __future__ import annotations

import logging
import queue
import sys
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from botocore.exceptions import ClientError, NoCredentialsError
from textual import events
from textual.app import App, ComposeResult
from textual.containers import Container
from textual.widgets import Log, Static

from campers.constants import (
    CTRL_C_DOUBLE_PRESS_THRESHOLD_SECONDS,
    UPTIME_UPDATE_INTERVAL_SECONDS,
)
from campers.logging import StreamFormatter, TuiLogHandler, TuiLogMessage
from campers.tui.instance_overview_widget import InstanceOverviewWidget
from campers.tui.styling import TUI_CSS
from campers.tui.terminal import detect_terminal_background
from campers.tui.widgets import WidgetID
from campers.utils import get_aws_credentials_error_message

if TYPE_CHECKING:
    from campers import Campers

TUI_UPDATE_INTERVAL = 0.1
MAX_UPDATES_PER_TICK = 10
TUI_STATUS_UPDATE_PROCESSING_DELAY = 1.0

logger = logging.getLogger(__name__)


class CampersTUI(App):
    """Textual TUI application for campers.

    Parameters
    ----------
    campers_instance : Campers
        Campers instance to run
    run_kwargs : dict[str, Any]
        Keyword arguments for run method
    update_queue : queue.Queue
        Queue for receiving updates from worker thread

    Attributes
    ----------
    campers : Campers
        Campers instance to run
    run_kwargs : dict[str, Any]
        Keyword arguments for run method
    update_queue : queue.Queue
        Queue for receiving updates from worker thread
    original_handlers : list[logging.Handler]
        Original logging handlers to restore on exit
    worker_exit_code : int
        Exit code from worker thread
    """

    CSS = TUI_CSS

    def __init__(
        self,
        campers_instance: Campers,
        run_kwargs: dict[str, Any],
        update_queue: queue.Queue,
        start_worker: bool = True,
    ) -> None:
        """Initialize CampersTUI.

        Parameters
        ----------
        campers_instance : Campers
            Campers instance to run
        run_kwargs : dict[str, Any]
            Keyword arguments for run method
        update_queue : queue.Queue
            Queue for receiving updates from worker thread
        start_worker : bool
            Whether to start the worker thread on mount (default: True)
            Set to False for tests that verify initial placeholder state
        """
        self.terminal_bg, self.is_light_theme = detect_terminal_background()
        super().__init__()
        self.campers = campers_instance
        self.run_kwargs = run_kwargs
        self._update_queue = update_queue
        self._start_worker = start_worker
        self.original_handlers: list[logging.Handler] = []
        self.worker_exit_code = 0
        self.instance_start_time: datetime | None = None
        self.last_ctrl_c_time: float = 0.0
        self.log_widget: Log | None = None
        self.styles.background = self.terminal_bg

    def compose(self) -> ComposeResult:
        """Compose TUI layout.

        Yields
        ------
        Container
            Status panel container with static widgets
        Container
            Log panel container with log widget
        """
        with Container(id="status-panel"):
            yield InstanceOverviewWidget(self.campers)
            yield Static("SSH: loading...", id=WidgetID.SSH)
            yield Static("Status: launching...", id=WidgetID.STATUS)
            yield Static("Uptime: 0s", id=WidgetID.UPTIME)
            yield Static("Instance Type: loading...", id=WidgetID.INSTANCE_TYPE)
            yield Static("Region: loading...", id=WidgetID.REGION)
            yield Static("Camp Name: loading...", id=WidgetID.CAMP_NAME)
            yield Static("Command: loading...", id=WidgetID.COMMAND)
            yield Static("Mutagen: Not syncing", id=WidgetID.MUTAGEN)
        with Container(id="log-panel"):
            yield Log()

    def on_mount(self) -> None:
        """Handle mount event - setup logging, start worker, and timer."""
        root_logger = logging.getLogger()
        self.original_handlers = root_logger.handlers[:]

        log_widget = self.query_one(Log)
        self.log_widget = log_widget
        tui_handler = TuiLogHandler(self, log_widget)
        tui_handler.setFormatter(StreamFormatter("%(message)s"))

        root_logger.handlers = [tui_handler]
        root_logger.setLevel(logging.INFO)

        for module in ["portforward", "ssh", "sync", "ec2"]:
            module_logger = logging.getLogger(f"campers.{module}")
            module_logger.propagate = True
            module_logger.setLevel(logging.INFO)

        for boto_module in ["botocore", "boto3", "urllib3"]:
            logging.getLogger(boto_module).setLevel(logging.WARNING)

        self.instance_start_time = datetime.now()
        self.set_interval(TUI_UPDATE_INTERVAL, self.check_for_updates)
        self.set_interval(UPTIME_UPDATE_INTERVAL_SECONDS, self.update_uptime, name="uptime-timer")

        if self._start_worker:
            self.run_worker(self.run_campers_logic, exit_on_error=False, thread=True)

    async def on_tui_log_message(self, message: TuiLogMessage) -> None:
        """Append log messages emitted from worker threads to the log widget."""

        if self.log_widget is None:
            return

        self.log_widget.write_line(message.text)

    def check_for_updates(self) -> None:
        """Check queue for updates and update widgets accordingly.

        Processes up to MAX_UPDATES_PER_TICK updates per call to prevent
        unbounded processing that could block the UI thread.
        """
        updates_processed = 0

        while updates_processed < MAX_UPDATES_PER_TICK:
            try:
                data = self._update_queue.get_nowait()
                logging.debug("Processing update from queue: type=%s", data.get("type"))
                update_type = data.get("type")
                payload = data.get("payload", {})

                if update_type == "merged_config":
                    self.update_from_config(payload)
                elif update_type == "instance_details":
                    self.update_from_instance_details(payload)
                elif update_type == "status_update":
                    self.update_status(payload)
                elif update_type == "mutagen_status":
                    self.update_mutagen_status(payload)
                elif update_type == "cleanup_event":
                    self.handle_cleanup_event(payload)

                updates_processed += 1
            except queue.Empty:
                break

    def update_uptime(self) -> None:
        """Update uptime widget with elapsed time since instance launch."""
        if self.instance_start_time is None:
            return

        now_utc = datetime.now(UTC).replace(tzinfo=None)
        elapsed = now_utc - self.instance_start_time
        total_seconds = int(elapsed.total_seconds())

        if total_seconds < 0:
            total_seconds = 0

        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60

        if hours > 0:
            uptime_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        elif minutes > 0:
            uptime_str = f"{minutes:02d}:{seconds:02d}"
        else:
            uptime_str = f"{seconds}s"

        try:
            self.query_one(f"#{WidgetID.UPTIME}").update(f"Uptime: {uptime_str}")
        except Exception as e:
            logging.error("Failed to update uptime widget: %s", e)

    def update_status(self, payload: dict[str, Any]) -> None:
        """Update status widget from status update event.

        Parameters
        ----------
        payload : dict[str, Any]
            Status update payload containing 'status' field
        """
        if "status" in payload:
            status = payload["status"]

            try:
                self.query_one(f"#{WidgetID.STATUS}").update(f"Status: {status}")
            except Exception as e:
                logging.error("Failed to update status widget: %s", e)

    def update_mutagen_status(self, payload: dict[str, Any]) -> None:
        """Update mutagen widget from mutagen status event.

        Parameters
        ----------
        payload : dict[str, Any]
            Mutagen status payload containing 'state' and optionally 'files_synced'
        """
        state = payload.get("state", "unknown")
        files_synced = payload.get("files_synced")

        if state == "not_configured":
            display_text = "Mutagen: Not syncing"
        elif files_synced is not None:
            display_text = f"Mutagen: {state} ({files_synced} files)"
        else:
            display_text = f"Mutagen: {state}"

        try:
            self.query_one(f"#{WidgetID.MUTAGEN}").update(display_text)
        except Exception as e:
            logging.error("Failed to update mutagen widget: %s", e)

    def handle_cleanup_event(self, payload: dict[str, Any]) -> None:
        """Handle cleanup event by logging to the log panel.

        Parameters
        ----------
        payload : dict[str, Any]
            Cleanup event payload containing 'step' and 'status'
        """
        step = payload.get("step", "unknown")
        status = payload.get("status", "unknown")
        logging.info("Cleanup: %s - %s", step, status)

    def update_from_config(self, config: dict[str, Any]) -> None:
        """Update widgets from merged config data.

        Parameters
        ----------
        config : dict[str, Any]
            Merged configuration data
        """
        if "instance_type" in config:
            try:
                self.query_one(f"#{WidgetID.INSTANCE_TYPE}").update(
                    f"Instance Type: {config['instance_type']}"
                )
            except Exception as e:
                logging.error("Failed to update instance type widget: %s", e)

        if "region" in config:
            try:
                self.query_one(f"#{WidgetID.REGION}").update(f"Region: {config['region']}")
            except Exception as e:
                logging.error("Failed to update region widget: %s", e)

        camp_name = config.get("camp_name", "ad-hoc")

        try:
            self.query_one(f"#{WidgetID.CAMP_NAME}").update(f"Camp Name: {camp_name}")
        except Exception as e:
            logging.error("Failed to update camp name widget: %s", e)

        if "command" in config:
            try:
                self.query_one(f"#{WidgetID.COMMAND}").update(f"Command: {config['command']}")
            except Exception as e:
                logging.error("Failed to update command widget: %s", e)

    def update_from_instance_details(self, details: dict[str, Any]) -> None:
        """Update widgets from instance details data.

        Parameters
        ----------
        details : dict[str, Any]
            Instance details data
        """
        if "state" in details:
            try:
                self.query_one(f"#{WidgetID.STATUS}").update(f"Status: {details['state']}")
            except Exception as e:
                logging.error("Failed to update status widget: %s", e)

        if "launch_time" in details and details["launch_time"]:
            launch_time = details["launch_time"]

            if hasattr(launch_time, "replace"):
                self.instance_start_time = launch_time.replace(tzinfo=None)

        if "public_ip" in details and details["public_ip"]:
            try:
                ssh_username = details.get("ssh_username", "ubuntu")
                key_file = details.get("key_file", "key.pem")
                public_ip = details["public_ip"]
                ssh_string = f"ssh -o IdentitiesOnly=yes -i {key_file} {ssh_username}@{public_ip}"
                self.query_one(f"#{WidgetID.SSH}").update(f"SSH: {ssh_string}")
            except Exception as e:
                logging.error("Failed to update SSH widget: %s", e)

    def on_unmount(self) -> None:
        """Handle unmount event - restore logging and cleanup resources."""
        root_logger = logging.getLogger()
        root_logger.handlers = self.original_handlers

        while not self._update_queue.empty():
            try:
                self._update_queue.get_nowait()
            except queue.Empty:
                break

        if not self.campers._abort_requested and not self.campers._cleanup_in_progress:
            self.campers._cleanup_resources()

    def run_campers_logic(self) -> None:
        """Run campers logic in worker thread."""
        error_message = None

        try:
            result = self.campers._execute_run(
                tui_mode=True, update_queue=self._update_queue, **self.run_kwargs
            )
            self.worker_exit_code = 0

            if isinstance(result, dict) and "command_exit_code" in result:
                self.worker_exit_code = result["command_exit_code"]

            if self.worker_exit_code == 0:
                logging.info("Command completed successfully")
        except KeyboardInterrupt:
            logging.info("Operation cancelled by user")
            self.worker_exit_code = 130
        except NoCredentialsError:
            error_message = get_aws_credentials_error_message()
            logging.error("AWS credentials not found")
            self.worker_exit_code = 1
        except ClientError as e:
            error_response = e.response.get("Error") if e.response else None
            error_code = error_response.get("Code", "") if error_response else ""
            error_msg = error_response.get("Message", str(e)) if error_response else str(e)

            if error_code in [
                "ExpiredToken",
                "RequestExpired",
                "ExpiredTokenException",
            ]:
                error_message = (
                    "AWS credentials have expired\n\n"
                    "This usually means:\n"
                    "  - Your temporary credentials (STS) have expired\n"
                    "  - Your session token needs to be refreshed\n\n"
                    "Fix it:\n"
                    "  aws sso login           # If using AWS SSO\n"
                    "  aws configure           # Re-configure credentials\n"
                    "  # Or refresh your temporary credentials"
                )
                logging.error("AWS credentials have expired")
            elif error_code == "UnauthorizedOperation":
                error_message = (
                    "Insufficient IAM permissions\n\n"
                    "Your AWS credentials don't have the required permissions.\n"
                    "Contact your AWS administrator to grant:\n"
                    "  - EC2 permissions (DescribeInstances, RunInstances, TerminateInstances)\n"
                    "  - VPC permissions (DescribeVpcs, CreateDefaultVpc)\n"
                    "  - Key Pair permissions (CreateKeyPair, DeleteKeyPair, DescribeKeyPairs)\n"
                    "  - Security Group permissions"
                )
                logging.error("Insufficient IAM permissions")
            else:
                error_message = f"AWS API error: {error_msg}"
                logging.error("AWS API error: %s", error_msg)
            self.worker_exit_code = 1
        except ValueError as e:
            error_message = f"Configuration error: {e}"
            logging.error(error_message)
            self.worker_exit_code = 2
        except RuntimeError as e:
            error_message = f"Runtime error: {e}"
            logging.error(error_message)
            self.worker_exit_code = 3
        except Exception as e:
            error_message = f"Unexpected error: {e}"
            logging.exception("Unexpected error during command execution")
            self.worker_exit_code = 1
        finally:
            if error_message:
                logging.error(error_message)

                if self._update_queue is not None:
                    self._update_queue.put(
                        {"type": "status_update", "payload": {"status": "error"}}
                    )
                    time.sleep(TUI_STATUS_UPDATE_PROCESSING_DELAY)

            if self.campers._abort_requested:
                self.worker_exit_code = 130
            elif not self.campers._cleanup_in_progress:
                self.campers._cleanup_resources()

            self.call_from_thread(self.exit, self.worker_exit_code)

    def on_key(self, event: events.Key) -> None:
        """Handle key press events.

        Parameters
        ----------
        event : events.Key
            Key event
        """
        if event.key == "q":
            self.action_quit()
        elif event.key == "ctrl+c":
            current_time = time.time()

            if (
                self.last_ctrl_c_time > 0
                and (current_time - self.last_ctrl_c_time) < CTRL_C_DOUBLE_PRESS_THRESHOLD_SECONDS
            ):
                try:
                    log_widget = self.query_one(Log)
                    log_widget.write_line("Force exit - skipping cleanup!")
                except Exception as e:
                    logger.debug("Failed to write to log widget during force exit: %s", e)

                if hasattr(self, "_driver") and self._driver is not None:
                    self.exit(130)
                else:
                    sys.exit(130)
            else:
                self.last_ctrl_c_time = current_time
                self.action_quit()

    def action_quit(self) -> None:
        """Handle quit action (q key or first Ctrl+C)."""
        self.campers._abort_requested = True

        try:
            self.query_one(f"#{WidgetID.STATUS}").update("Status: shutting down")
        except Exception as e:
            logger.debug("Failed to update status widget during quit: %s", e)

        try:
            log_widget = self.query_one(Log)
            log_widget.write_line("Graceful shutdown initiated (press Ctrl+C again to force exit)")
        except Exception as e:
            logger.debug("Failed to write shutdown message to log widget: %s", e)

        self.refresh()

        self.run_worker(self._run_cleanup, thread=True, exit_on_error=False)

    def _run_cleanup(self) -> None:
        """Run cleanup in worker thread to keep TUI responsive."""
        if hasattr(self.campers, "_resources") and "ssh_manager" in self.campers._resources:
            self.campers._resources["ssh_manager"].abort_active_command()

        if not self.campers._cleanup_in_progress:
            self.campers._cleanup_resources()

        self.call_from_thread(self.exit, 130)
