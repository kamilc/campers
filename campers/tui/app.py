"""Textual TUI application for campers."""

from __future__ import annotations

import logging
import os
import queue
import sys
import threading
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from textual import events
from textual.app import App, ComposeResult
from textual.containers import Container
from textual.widgets import Static

from campers.constants import (
    CTRL_C_DOUBLE_PRESS_THRESHOLD_SECONDS,
    DEFAULT_SSH_USERNAME,
    MAX_UPDATES_PER_TICK,
    TUI_STATUS_UPDATE_PROCESSING_DELAY,
    TUI_UPDATE_INTERVAL,
    UPTIME_UPDATE_INTERVAL_SECONDS,
)
from campers.logging import StreamFormatter, TuiLogHandler, TuiLogMessage
from campers.providers.exceptions import ProviderCredentialsError
from campers.tui import widgets
from campers.tui.exit_modal import ExitModal
from campers.tui.instance_overview_widget import InstanceOverviewWidget
from campers.tui.styling import TUI_CSS
from campers.tui.terminal import detect_terminal_background
from campers.tui.widgets.context_menu import ContextMenu
from campers.tui.widgets.labeled_value import LabeledValue
from campers.tui.widgets.search_input import SearchClosed, SearchInput, SearchQueryChanged
from campers.tui.widgets.selectable_log import SelectableLog

if TYPE_CHECKING:
    from campers import Campers

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
    fatal_error_message : str | None
        Error message to display after TUI exits, if any fatal error occurred
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
        terminal_bg_info = detect_terminal_background()
        self.terminal_bg = terminal_bg_info.color_hex
        self.is_light_theme = terminal_bg_info.is_light
        super().__init__()
        self.campers = campers_instance
        self.run_kwargs = run_kwargs
        self._update_queue = update_queue
        self._start_worker = start_worker
        self.original_handlers: list[logging.Handler] = []
        self.worker_exit_code = 0
        self.instance_start_time: datetime | None = None
        self.last_ctrl_c_time: float = 0.0
        self.log_widget: SelectableLog | None = None
        self.fatal_error_message: str | None = None
        self._running = True
        self._thread_id = threading.get_ident()
        self.styles.background = self.terminal_bg

    def compose(self) -> ComposeResult:
        """Compose TUI layout.

        Yields
        ------
        Container
            Status panel container with static widgets
        Container
            Log panel container with log widget and search input
        ContextMenu
            Context menu for SelectableLog actions
        """
        with Container(id="status-panel"):
            yield InstanceOverviewWidget(self.campers)
            yield LabeledValue("SSH", "loading...", id=widgets.WidgetID.SSH)
            yield LabeledValue("Status", "launching...", id=widgets.WidgetID.STATUS)
            yield LabeledValue("Uptime", "0s", id=widgets.WidgetID.UPTIME)
            yield LabeledValue("Instance Type", "loading...", id=widgets.WidgetID.INSTANCE_TYPE)
            yield LabeledValue("Region", "loading...", id=widgets.WidgetID.REGION)
            yield LabeledValue("Camp Name", "loading...", id=widgets.WidgetID.CAMP_NAME)
            yield LabeledValue("Command", "loading...", id=widgets.WidgetID.COMMAND)
            yield LabeledValue("File sync", "Not syncing", id=widgets.WidgetID.MUTAGEN)
            yield LabeledValue("Port forwarding", "none", id=widgets.WidgetID.PORTFORWARD)
            yield Static("", id=widgets.WidgetID.PUBLIC_PORTS, classes="hidden")
        with Container(id="log-panel"):
            yield SelectableLog()
            yield SearchInput()
        yield ContextMenu(items=["Copy"])

    def on_mount(self) -> None:
        """Handle mount event - setup logging, start worker, and timer."""
        root_logger = logging.getLogger()
        self.original_handlers = root_logger.handlers[:]

        log_widget = self.query_one(SelectableLog)
        self.log_widget = log_widget
        tui_handler = TuiLogHandler(self, log_widget)
        tui_handler.setFormatter(StreamFormatter("%(message)s"))
        tui_handler.setLevel(logging.INFO)

        root_logger.handlers = [tui_handler]
        root_logger.setLevel(logging.DEBUG)

        logging.debug("TUI handler installed and root logger configured")

        for module in ["portforward", "ssh", "sync", "ec2"]:
            module_logger = logging.getLogger(f"campers.{module}")
            module_logger.propagate = True
            module_logger.setLevel(logging.INFO)

        for boto_module in ["botocore", "boto3", "urllib3"]:
            logging.getLogger(boto_module).setLevel(logging.WARNING)

        self.instance_start_time = datetime.now()
        self.set_interval(TUI_UPDATE_INTERVAL, self.check_for_updates)
        self.set_interval(UPTIME_UPDATE_INTERVAL_SECONDS, self.update_uptime, name="uptime-timer")

        logging.debug(f"on_mount: _start_worker={self._start_worker}")
        if self._start_worker:
            logging.debug("on_mount: starting worker thread")
            try:
                self.run_worker(self.run_campers_logic, exit_on_error=False, thread=True)
                logging.debug("on_mount: worker thread started")
            except Exception as e:
                logging.error(f"on_mount: failed to start worker: {e}", exc_info=True)

    async def on_tui_log_message(self, message: TuiLogMessage) -> None:
        """Append log messages emitted from worker threads to the log widget."""
        if self.log_widget is None:
            return

        self.log_widget.write(message.text)

    async def on_context_menu_item_selected(self, message: ContextMenu.ItemSelected) -> None:
        """Handle context menu item selection.

        Parameters
        ----------
        message : ContextMenu.ItemSelected
            Message containing the selected action
        """
        target = message.target_widget

        if message.action == "copy" and hasattr(target, "action_copy"):
            target.action_copy()
        elif message.action == "search":
            search_input = self.query_one(SearchInput)
            search_input.show()
        elif message.action == "clear" and hasattr(target, "clear"):
            target.clear()

    async def on_search_query_changed(self, message: SearchQueryChanged) -> None:
        """Handle search query change.

        Updates the log widget with the new search results and updates
        the match count display.

        Parameters
        ----------
        message : SearchQueryChanged
            Message containing the new search query
        """
        log_widget = self.query_one(SelectableLog)
        log_widget.start_search(message.query)

        search_input = self.query_one(SearchInput)
        search_input.update_match_count(
            log_widget.current_match_index, len(log_widget.search_matches)
        )

    async def on_search_closed(self, message: SearchClosed) -> None:
        """Handle search input closed.

        Clears search if keep_matches is False, otherwise preserves matches
        for continued navigation. Returns focus to the log widget.

        Parameters
        ----------
        message : SearchClosed
            Message indicating whether to keep matches
        """
        log_widget = self.query_one(SelectableLog)

        if not message.keep_matches:
            log_widget.clear_search()

        log_widget.focus()

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
                elif update_type == "portforward_status":
                    self.update_portforward_status(payload)
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
            self.query_one(f"#{widgets.WidgetID.UPTIME}", LabeledValue).value = uptime_str
        except (ValueError, AttributeError) as e:
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
                self.query_one(f"#{widgets.WidgetID.STATUS}", LabeledValue).value = status
            except (ValueError, AttributeError) as e:
                logging.error("Failed to update status widget: %s", e)

    def update_mutagen_status(self, payload: dict[str, Any]) -> None:
        """Update mutagen widget from mutagen status event.

        Parameters
        ----------
        payload : dict[str, Any]
            Mutagen status payload containing 'status_text' or legacy 'state' and 'files_synced'
        """
        status_text = payload.get("status_text")

        if status_text is not None:
            value = status_text
        else:
            state = payload.get("state", "unknown")
            files_synced = payload.get("files_synced")

            if state == "not_configured":
                value = "Not syncing"
            elif files_synced is not None:
                value = f"{state} ({files_synced} files)"
            else:
                value = state

        try:
            self.query_one(f"#{widgets.WidgetID.MUTAGEN}", LabeledValue).value = value
        except (ValueError, AttributeError) as e:
            logging.error("Failed to update mutagen widget: %s", e)

    def update_portforward_status(self, payload: dict[str, Any]) -> None:
        """Update port forwarding status widget.

        Parameters
        ----------
        payload : dict[str, Any]
            Dictionary containing 'ports' list of (remote, local) tuples and 'status' string
        """
        ports = payload.get("ports", [])
        if ports:
            port_strings = []
            for p in ports:
                if isinstance(p, (list, tuple)) and len(p) == 2:
                    remote_port, local_port = p
                    port_strings.append(f"{remote_port} -> {local_port}")
                else:
                    port_strings.append(f"{p} -> {p}")
            port_str = ", ".join(port_strings)
            text = f"Port forwarding: {port_str}"
        else:
            text = "Port forwarding: none"

        try:
            self.query_one(f"#{widgets.WidgetID.PORTFORWARD}").update(text)
        except (ValueError, AttributeError) as e:
            logging.error("Failed to update portforward widget: %s", e)

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
        self.campers._merged_config_prop = config

        if "instance_type" in config:
            try:
                widget = self.query_one(
                    f"#{widgets.WidgetID.INSTANCE_TYPE}", LabeledValue
                )
                widget.value = config['instance_type']
            except (ValueError, AttributeError, RuntimeError) as e:
                logging.error("Failed to update instance type widget: %s", e)

        if "region" in config:
            try:
                widget = self.query_one(
                    f"#{widgets.WidgetID.REGION}", LabeledValue
                )
                widget.value = config['region']
            except (ValueError, AttributeError, RuntimeError) as e:
                logging.error("Failed to update region widget: %s", e)

        camp_name = config.get("camp_name", "ad-hoc")

        try:
            widget = self.query_one(
                f"#{widgets.WidgetID.CAMP_NAME}", LabeledValue
            )
            widget.value = camp_name
        except (ValueError, AttributeError, RuntimeError) as e:
            logging.error("Failed to update camp name widget: %s", e)

        if "command" in config:
            try:
                cmd = config["command"]
                widget = self.query_one(
                    f"#{widgets.WidgetID.COMMAND}", LabeledValue
                )
                widget.value = cmd
            except (ValueError, AttributeError, RuntimeError) as e:
                logging.error("Failed to update command widget: %s", e)

        public_ports = config.get("public_ports", [])
        try:
            public_ports_widget = self.query_one(f"#{widgets.WidgetID.PUBLIC_PORTS}")
            if public_ports:
                instance_details = self.campers._resources.get("instance_details", {})
                public_ip = instance_details.get("public_ip")
                if public_ip:
                    urls = []
                    for port in public_ports:
                        protocol = "https" if port == 443 else "http"
                        urls.append(f"{protocol}://{public_ip}:{port}")
                    public_ports_text = f"Public IP: {public_ip} | URLs: " + ", ".join(urls)
                    public_ports_widget.update(public_ports_text)
                    public_ports_widget.remove_class("hidden")
            else:
                public_ports_widget.add_class("hidden")
        except (ValueError, AttributeError, RuntimeError) as e:
            logging.error("Failed to update public ports widget: %s", e)

    def update_from_instance_details(self, details: dict[str, Any]) -> None:
        """Update widgets from instance details data.

        Parameters
        ----------
        details : dict[str, Any]
            Instance details data
        """
        if "state" in details:
            try:
                self.query_one(f"#{widgets.WidgetID.STATUS}", LabeledValue).value = details['state']
            except (ValueError, AttributeError, RuntimeError) as e:
                logging.error("Failed to update status widget: %s", e)

        if "launch_time" in details and details["launch_time"]:
            launch_time = details["launch_time"]

            if hasattr(launch_time, "replace"):
                self.instance_start_time = launch_time.replace(tzinfo=None)

        if "public_ip" in details and details["public_ip"]:
            public_ip = details["public_ip"]
            try:
                ssh_username = details.get("ssh_username", DEFAULT_SSH_USERNAME)
                key_file = details.get("key_file", "key.pem")
                ssh_string = f"ssh -o IdentitiesOnly=yes -i {key_file} {ssh_username}@{public_ip}"
                self.query_one(f"#{widgets.WidgetID.SSH}", LabeledValue).value = ssh_string
            except (ValueError, AttributeError, RuntimeError) as e:
                logging.error("Failed to update SSH widget: %s", e)

            public_ports = getattr(self.campers, "_merged_config_prop", {}).get("public_ports", [])
            if public_ports:
                try:
                    urls = []
                    for port in public_ports:
                        protocol = "https" if port == 443 else "http"
                        urls.append(f"{protocol}://{public_ip}:{port}")
                    public_ports_text = f"Public IP: {public_ip} | URLs: " + ", ".join(urls)
                    public_ports_widget = self.query_one(f"#{widgets.WidgetID.PUBLIC_PORTS}")
                    public_ports_widget.update(public_ports_text)
                    public_ports_widget.remove_class("hidden")
                except (ValueError, AttributeError, RuntimeError) as e:
                    logging.error("Failed to update public ports widget: %s", e)

    def on_unmount(self) -> None:
        """Handle unmount event - restore logging and cleanup resources."""
        self._running = False
        root_logger = logging.getLogger()
        root_logger.handlers = self.original_handlers

        while not self._update_queue.empty():
            try:
                self._update_queue.get_nowait()
            except queue.Empty:
                break

        if (
            not self.campers._abort_requested
            and not self.campers._cleanup_in_progress
            and self.campers._resources
        ):
            self.campers._cleanup_resources()

    def run_campers_logic(self) -> None:
        """Run campers logic in worker thread."""
        error_message = None

        logging.debug("Worker thread starting")

        try:
            logging.debug(f"Executing campers run with kwargs: {self.run_kwargs}")
            result = self.campers._execute_run(
                tui_mode=True, update_queue=self._update_queue, **self.run_kwargs
            )
            self.worker_exit_code = 0
            logging.debug(f"Campers execution completed, result: {result}")

            if isinstance(result, dict) and "command_exit_code" in result:
                self.worker_exit_code = result["command_exit_code"]

            if self.worker_exit_code == 0:
                logging.info("Command completed successfully")

            if self._update_queue is not None:
                try:
                    self._update_queue.put_nowait(
                        {"type": "status_update", "payload": {"status": "terminating"}}
                    )
                except queue.Full:
                    logging.warning("TUI update queue full, dropping terminating status")

            logging.info("Cleanup completed successfully")
        except KeyboardInterrupt:
            logging.info("Operation cancelled by user")
            self.worker_exit_code = 130
        except ProviderCredentialsError:
            error_message = (
                "Cloud provider credentials not found\n\n"
                "This usually means:\n"
                "  - AWS credentials are not configured\n"
                "  - AWS_PROFILE is not set or invalid\n"
                "  - Credentials have expired\n\n"
                "Fix it:\n"
                "  aws sso login           # If using AWS SSO\n"
                "  aws configure           # Configure credentials\n"
                "  export AWS_PROFILE=your-profile  # Set profile"
            )
            logging.error("Cloud provider credentials not found")
            self.worker_exit_code = 1
        except (ValueError, AttributeError, RuntimeError) as e:
            error_code = getattr(e, "error_code", None)
            error_message = str(e)

            if error_code in [
                "ExpiredToken",
                "RequestExpired",
                "ExpiredTokenException",
            ]:
                error_message = (
                    "Cloud provider credentials have expired\n\n"
                    "This usually means:\n"
                    "  - Your temporary credentials (STS) have expired\n"
                    "  - Your session token needs to be refreshed\n\n"
                    "Fix it:\n"
                    "  aws sso login           # If using AWS SSO\n"
                    "  aws configure           # Re-configure credentials\n"
                    "  # Or refresh your temporary credentials"
                )
                logging.error("Cloud provider credentials have expired")
            elif error_code == "UnauthorizedOperation":
                error_message = (
                    "Insufficient cloud provider permissions\n\n"
                    "Your cloud provider credentials don't have the required "
                    "permissions.\n"
                    "Contact your administrator to grant:\n"
                    "  - Compute permissions (DescribeInstances, RunInstances,\n"
                    "    TerminateInstances)\n"
                    "  - Network permissions (DescribeVpcs, CreateDefaultVpc)\n"
                    "  - Key Pair permissions (CreateKeyPair, DeleteKeyPair,\n"
                    "    DescribeKeyPairs)\n"
                    "  - Security Group permissions"
                )
                logging.error("Insufficient cloud provider permissions")
            else:
                logging.error("Provider error: %s", error_message)
            self.worker_exit_code = 1
        except Exception as e:
            logging.error("Unexpected error during execution: %s", str(e), exc_info=True)
            exc_type = type(e).__name__
            exc_msg = str(e)
            if exc_msg:
                error_message = f"{exc_type}: {exc_msg}"
            else:
                error_message = f"{exc_type} (run with -v for details)"
            self.worker_exit_code = 1
        finally:
            has_resources = bool(self.campers._resources)

            if error_message:
                self.fatal_error_message = error_message
                logging.error(error_message)

                if self._update_queue is not None:
                    try:
                        self._update_queue.put_nowait(
                            {"type": "status_update", "payload": {"status": "error"}}
                        )
                    except queue.Full:
                        logging.warning("TUI update queue full, dropping error status update")

                    if has_resources:
                        time.sleep(TUI_STATUS_UPDATE_PROCESSING_DELAY)

            if self.campers._abort_requested:
                self.worker_exit_code = 130
            elif not self.campers._cleanup_in_progress and has_resources:
                self.campers._cleanup_resources()

            if has_resources:
                time.sleep(0.5)

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
                    log_widget = self.query_one(SelectableLog)
                    log_widget.write("[red]Force exit - skipping cleanup![/red]")
                except (ValueError, AttributeError, RuntimeError) as e:
                    logger.debug("Failed to write to log widget during force exit: %s", e)

                if hasattr(self, "_driver") and self._driver is not None:
                    self.exit(130)
                else:
                    sys.exit(130)
            else:
                self.last_ctrl_c_time = current_time
                self.action_quit()

    def action_quit(self) -> None:
        """Handle quit action (q key or first Ctrl+C) - show exit modal."""
        instance_details = {}
        has_instance = False

        if hasattr(self.campers, "_resources"):
            instance_details = self.campers._resources.get("instance_details", {})
            has_instance = bool(instance_details.get("instance_id"))

        if not has_instance:
            self.campers._abort_requested = True
            sys.stdout.write("\x1b[?1000l\x1b[?1003l\x1b[?1006l")
            sys.stdout.write("\x1b[?1049l")
            sys.stdout.write("\x1b[0m\x1b[?25h\n")
            sys.stdout.flush()
            import subprocess

            subprocess.run(["stty", "sane"], stderr=subprocess.DEVNULL)
            os._exit(0)

        public_ip = instance_details.get("public_ip")
        public_ports = []
        hourly_cost = None

        if hasattr(self.campers, "_merged_config_prop"):
            public_ports = self.campers._merged_config_prop.get("public_ports", [])

        try:
            from campers.constants import DEFAULT_PROVIDER
            from campers.registry import get_provider

            instance_type = instance_details.get("instance_type")
            region = self.campers._merged_config_prop.get("region")

            if instance_type and region:
                provider = get_provider(DEFAULT_PROVIDER)
                pricing_service_class = provider["pricing_service"]
                pricing_service = pricing_service_class()

                try:
                    if pricing_service.pricing_available:
                        hourly_cost = pricing_service.get_instance_price(instance_type, region)
                finally:
                    pricing_service.close()
        except Exception as e:
            logger.debug("Failed to calculate hourly cost: %s", e)

        def handle_exit_choice(action: str | None) -> None:
            if action == "cancel":
                self.campers._abort_requested = False
                return

            self._selected_exit_action = action

            try:
                self.query_one(f"#{widgets.WidgetID.STATUS}", LabeledValue).value = "shutting down"
            except (ValueError, AttributeError, RuntimeError) as e:
                logger.debug("Failed to update status widget during quit: %s", e)

            try:
                log_widget = self.query_one(SelectableLog)
                msg = "Graceful shutdown initiated (press Ctrl+C again to force exit)"
                log_widget.write(msg)
            except (ValueError, AttributeError, RuntimeError) as e:
                logger.debug("Failed to write shutdown message to log widget: %s", e)

            self.refresh()
            self.run_worker(self._run_cleanup, thread=True, exit_on_error=False)

        self.campers._abort_requested = True
        self.push_screen(
            ExitModal(
                public_ip=public_ip,
                public_ports=public_ports,
                hourly_cost=hourly_cost,
            ),
            handle_exit_choice,
        )

    def _run_cleanup(self) -> None:
        """Run cleanup in worker thread to keep TUI responsive."""
        if hasattr(self.campers, "_resources") and "ssh_manager" in self.campers._resources:
            self.campers._resources["ssh_manager"].abort_active_command()

        if not self.campers._cleanup_in_progress:
            action = getattr(self, "_selected_exit_action", "stop")
            self.campers._cleanup_resources(action=action)

        exit_code = 0 if getattr(self, "_selected_exit_action", "stop") == "detach" else 130
        self.call_from_thread(self.exit, exit_code)
