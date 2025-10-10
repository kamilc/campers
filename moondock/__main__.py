#!/usr/bin/env python3
# /// script
# dependencies = [
#   "boto3>=1.40.0",
#   "PyYAML>=6.0",
#   "fire>=0.7.0",
#   "textual>=0.47.0",
#   "paramiko>=3.0.0",
#   "sshtunnel>=0.4.0",
# ]
# ///

"""Moondock - EC2 remote development tool."""

from __future__ import annotations

import json
import logging
import os
import queue
import re
import shlex
import signal
import socket
import sys
import threading
import time
import types
from datetime import datetime
from pathlib import Path
from typing import Any

import fire
import paramiko
from botocore.exceptions import ClientError, NoCredentialsError
from textual import events
from textual.app import App, ComposeResult
from textual.containers import Container
from textual.widgets import Header, Footer, Log, Static

from moondock.config import ConfigLoader
from moondock.ec2 import EC2Manager
from moondock.portforward import PortForwardManager
from moondock.ssh import SSHManager
from moondock.sync import MutagenManager
from moondock.utils import format_time_ago

SYNC_TIMEOUT = 300
"""Mutagen initial sync timeout in seconds.

Five minutes allows time for large codebases to complete initial sync over SSH.
Timeout prevents indefinite hangs if sync stalls due to network or filesystem issues.
"""

MAX_NAME_COLUMN_WIDTH = 19
"""Maximum width for machine config name column in list output.

Names exceeding this width are truncated to maintain table alignment.
"""

TUI_UPDATE_INTERVAL = 0.1
"""TUI update check interval in seconds.

Checks the update queue every 100ms for new data from the worker thread.
"""

MAX_UPDATES_PER_TICK = 10
"""Maximum number of queue updates processed per timer tick.

Prevents queue flooding from blocking the UI thread by limiting updates per interval.
"""

CONFIG_TEMPLATE = """# Moondock Configuration File
# This file defines default settings and named machine configurations.
# Location: moondock.yaml (or set MOONDOCK_CONFIG environment variable)

# Required: Default settings used when no machine name is specified
defaults:
  # AWS Configuration (required)
  region: us-east-1              # AWS region (e.g., us-east-1, us-west-2, eu-west-1)
  instance_type: t3.medium       # EC2 instance type (e.g., t3.medium, m5.xlarge, p3.2xlarge)
  disk_size: 50                  # Root disk size in GB
  os_flavor: ubuntu-22.04        # Operating system (ubuntu-22.04, amazon-linux-2)

  # File Synchronization (Mutagen)
  # Single port:
  # port: 8888
  # Multiple ports:
  ports:
    - 8888                       # Local port for port forwarding (e.g., Jupyter, SSH tunnels)

  include_vcs: false             # Include version control files (.git, .gitignore, etc.)
  ignore:                        # File patterns to exclude from sync
    - "*.pyc"
    - "__pycache__"
    - "*.log"
    - ".DS_Store"
    - "node_modules/"

  # Environment Variable Forwarding
  env_filter:                    # Regex patterns to match environment variable names
    - "AWS_.*"                   # Forward all AWS credentials and config
    - "HF_TOKEN"                 # Hugging Face token
    - "WANDB_API_KEY"            # Weights & Biases API key

  # Sync Paths (optional - configure directories to sync)
  # sync_paths:
  #   - local: ~/projects/myproject    # Local directory path
  #     remote: ~/myproject            # Remote directory path (on EC2 instance)

  # Default Command (optional - runs when using 'moondock run' without -c flag)
  # command: bash                # Default shell or command to execute

  # Setup Script (optional - runs once on instance creation)
  # setup_script: |
  #   sudo apt update
  #   sudo apt install -y python3-pip git htop
  #   pip3 install uv

  # Startup Script (optional - runs before each command execution)
  # startup_script: |
  #   cd ~/myproject
  #   source .venv/bin/activate

# Optional: Named machine configurations
# Each machine can override any default setting
# machines:
#   dev-workstation:
#     instance_type: t3.large
#     disk_size: 100
#     setup_script: |
#       sudo apt update
#       sudo apt install -y python3-pip git htop
#       pip3 install uv
#     startup_script: |
#       cd ~/myproject
#       source .venv/bin/activate
#
#   jupyter-lab:
#     instance_type: m5.xlarge
#     disk_size: 200
#     region: us-west-2
#     ports:
#       - 8888                   # Jupyter
#       - 6006                   # TensorBoard
#     include_vcs: true
#     command: jupyter lab --port=8888 --no-browser
#     ignore:
#       - "*.pyc"
#       - "__pycache__"
#       - "data/"
#       - "models/"
#     setup_script: |
#       pip install jupyter pandas numpy scipy matplotlib tensorboard
#     startup_script: |
#       cd ~/myproject
#       export JUPYTER_CONFIG_DIR=~/.jupyter
#
#   ml-training:
#     instance_type: p3.2xlarge
#     disk_size: 200
#     region: us-west-2
#     ports:
#       - 8888                   # Jupyter
#       - 6006                   # TensorBoard
#       - 5000                   # MLflow
#     env_filter:
#       - "AWS_.*"
#       - "HF_.*"
#       - "WANDB_.*"
#       - "MLFLOW_.*"
#     command: jupyter lab --port=8888 --no-browser
#     setup_script: |
#       pip install jupyter tensorboard mlflow torch
#     startup_script: |
#       cd ~/myproject
#       source .venv/bin/activate
#       export CUDA_VISIBLE_DEVICES=0
"""


class StreamFormatter(logging.Formatter):
    """Logging formatter that prepends stream tags based on extra parameter."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record with stream prefix if present.

        Parameters
        ----------
        record : logging.LogRecord
            Log record to format

        Returns
        -------
        str
            Formatted log message with optional stream prefix
        """
        msg = super().format(record)
        stream = getattr(record, "stream", None)

        if stream == "stdout":
            return f"[stdout] {msg}"
        elif stream == "stderr":
            return f"[stderr] {msg}"

        return msg


class StreamRoutingFilter(logging.Filter):
    """Filter that routes log records based on stream extra parameter.

    Parameters
    ----------
    stream_type : str
        Stream type to allow: "stdout" or "stderr"
    """

    def __init__(self, stream_type: str) -> None:
        """Initialize filter.

        Parameters
        ----------
        stream_type : str
            Stream type to allow: "stdout" or "stderr"
        """
        super().__init__()
        self.stream_type = stream_type

    def filter(self, record: logging.LogRecord) -> bool:
        """Filter log records by stream type.

        Parameters
        ----------
        record : logging.LogRecord
            Log record to filter

        Returns
        -------
        bool
            True if record should be emitted by this handler
        """
        record_stream = getattr(record, "stream", None)

        if record_stream is None:
            return self.stream_type == "stderr"

        return record_stream == self.stream_type


class TuiLogHandler(logging.Handler):
    """Logging handler that writes to a Textual Log widget.

    Parameters
    ----------
    app : MoondockTUI
        Textual app instance
    log_widget : Log
        Log widget to write to

    Attributes
    ----------
    app : MoondockTUI
        Textual app instance
    log_widget : Log
        Log widget to write to
    """

    def __init__(self, app: "MoondockTUI", log_widget: Log) -> None:
        """Initialize TuiLogHandler.

        Parameters
        ----------
        app : MoondockTUI
            Textual app instance
        log_widget : Log
            Log widget to write to
        """
        super().__init__()
        self.app = app
        self.log_widget = log_widget

    def emit(self, record: logging.LogRecord) -> None:
        """Emit log record to TUI widget.

        Parameters
        ----------
        record : logging.LogRecord
            Log record to emit
        """
        msg = self.format(record)
        self.app.call_from_thread(self.log_widget.write_line, msg)


class MoondockTUI(App):
    """Textual TUI application for moondock.

    Parameters
    ----------
    moondock_instance : Moondock
        Moondock instance to run
    run_kwargs : dict[str, Any]
        Keyword arguments for run method
    update_queue : queue.Queue
        Queue for receiving updates from worker thread

    Attributes
    ----------
    moondock : Moondock
        Moondock instance to run
    run_kwargs : dict[str, Any]
        Keyword arguments for run method
    update_queue : queue.Queue
        Queue for receiving updates from worker thread
    original_handlers : list[logging.Handler]
        Original logging handlers to restore on exit
    worker_exit_code : int
        Exit code from worker thread
    """

    CSS = """
    #status-panel {
        height: 1fr;
        border: heavy white;
    }
    #log-panel {
        height: 2fr;
    }
    """

    def __init__(
        self,
        moondock_instance: "Moondock",
        run_kwargs: dict[str, Any],
        update_queue: queue.Queue,
    ) -> None:
        """Initialize MoondockTUI.

        Parameters
        ----------
        moondock_instance : Moondock
            Moondock instance to run
        run_kwargs : dict[str, Any]
            Keyword arguments for run method
        update_queue : queue.Queue
            Queue for receiving updates from worker thread
        """
        super().__init__()
        self.moondock = moondock_instance
        self.run_kwargs = run_kwargs
        self._update_queue = update_queue
        self.original_handlers: list[logging.Handler] = []
        self.worker_exit_code = 0
        self.instance_start_time: datetime | None = None
        self.last_ctrl_c_time: float = 0.0

    def compose(self) -> ComposeResult:
        """Compose TUI layout.

        Yields
        ------
        Header
            Header widget
        Container
            Status panel container with static widgets
        Container
            Log panel container with log widget
        Footer
            Footer widget
        """
        yield Header()
        with Container(id="status-panel"):
            yield Static("Instance ID: loading...", id="instance-id-widget")
            yield Static("Instance Type: loading...", id="instance-type-widget")
            yield Static("Region: loading...", id="region-widget")
            yield Static("Status: launching...", id="status-widget")
            yield Static("Uptime: 0s", id="uptime-widget")
            yield Static("Mutagen: Not syncing", id="mutagen-widget")
            yield Static("Machine Name: loading...", id="machine-name-widget")
            yield Static("Command: loading...", id="command-widget")
            yield Static("Forwarded Ports: loading...", id="ports-widget")
            yield Static("SSH: loading...", id="ssh-widget")
        with Container(id="log-panel"):
            yield Log()
        yield Footer()

    def on_mount(self) -> None:
        """Handle mount event - setup logging, start worker, and timer."""
        root_logger = logging.getLogger()
        self.original_handlers = root_logger.handlers[:]

        log_widget = self.query_one(Log)
        tui_handler = TuiLogHandler(self, log_widget)
        tui_handler.setFormatter(StreamFormatter("%(message)s"))

        root_logger.handlers = [tui_handler]

        self.instance_start_time = datetime.now()
        self.set_interval(TUI_UPDATE_INTERVAL, self.check_for_updates)
        self.set_interval(1.0, self.update_uptime, name="uptime-timer")
        self.run_worker(self.run_moondock_logic, exit_on_error=False, thread=True)

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
        """Update uptime widget with elapsed time since instance start."""
        if self.instance_start_time is None:
            return

        elapsed = datetime.now() - self.instance_start_time
        total_seconds = int(elapsed.total_seconds())
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
            self.query_one("#uptime-widget").update(f"Uptime: {uptime_str}")
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
            try:
                self.query_one("#status-widget").update(f"Status: {payload['status']}")
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
            self.query_one("#mutagen-widget").update(display_text)
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
                self.query_one("#instance-type-widget").update(
                    f"Instance Type: {config['instance_type']}"
                )
            except Exception as e:
                logging.error("Failed to update instance type widget: %s", e)

        if "region" in config:
            try:
                self.query_one("#region-widget").update(f"Region: {config['region']}")
            except Exception as e:
                logging.error("Failed to update region widget: %s", e)

        machine_name = config.get("machine_name", "ad-hoc")

        try:
            self.query_one("#machine-name-widget").update(
                f"Machine Name: {machine_name}"
            )
        except Exception as e:
            logging.error("Failed to update machine name widget: %s", e)

        if "command" in config:
            try:
                self.query_one("#command-widget").update(
                    f"Command: {config['command']}"
                )
            except Exception as e:
                logging.error("Failed to update command widget: %s", e)

        if "ports" in config and config["ports"]:
            try:
                ports_display = ", ".join(
                    f"localhost:{port}" for port in config["ports"]
                )
                self.query_one("#ports-widget").update(
                    f"Forwarded Ports: {ports_display}"
                )
            except Exception as e:
                logging.error("Failed to update ports widget: %s", e)

    def update_from_instance_details(self, details: dict[str, Any]) -> None:
        """Update widgets from instance details data.

        Parameters
        ----------
        details : dict[str, Any]
            Instance details data
        """
        if "instance_id" in details:
            try:
                self.query_one("#instance-id-widget").update(
                    f"Instance ID: {details['instance_id']}"
                )
            except Exception as e:
                logging.error("Failed to update instance ID widget: %s", e)

        if "state" in details:
            try:
                self.query_one("#status-widget").update(f"Status: {details['state']}")
            except Exception as e:
                logging.error("Failed to update status widget: %s", e)

        if "public_ip" in details and details["public_ip"]:
            try:
                ssh_string = f"ssh -o IdentitiesOnly=yes -i {details.get('key_file', 'key.pem')} ubuntu@{details['public_ip']}"
                self.query_one("#ssh-widget").update(f"SSH: {ssh_string}")
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

        if not self.moondock._cleanup_in_progress:
            self.moondock._cleanup_resources()

    def run_moondock_logic(self) -> None:
        """Run moondock logic in worker thread."""
        try:
            result = self.moondock._execute_run(
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
        except ValueError as e:
            logging.error("Configuration error: %s", e)
            self.worker_exit_code = 2
        except RuntimeError as e:
            logging.error("Runtime error: %s", e)
            self.worker_exit_code = 3
        except Exception:
            logging.exception("Unexpected error during command execution")
            self.worker_exit_code = 1
        finally:
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
                and (current_time - self.last_ctrl_c_time) < 1.5
            ):
                logging.info("Force exit requested")
                self.exit(130)
            else:
                self.last_ctrl_c_time = current_time
                self.action_quit()

    def action_quit(self) -> None:
        """Handle quit action (q key or first Ctrl+C)."""
        if not self.moondock._cleanup_in_progress:
            self.moondock._cleanup_resources()
        self.exit(130)


class Moondock:
    """Main CLI interface for moondock."""

    def __init__(self) -> None:
        """Initialize Moondock CLI.

        Creates a ConfigLoader instance for handling configuration loading,
        merging, and validation. Also initializes cleanup tracking state.
        """
        self._config_loader = ConfigLoader()
        self._cleanup_lock = threading.Lock()
        self._resources_lock = threading.Lock()
        self._cleanup_in_progress = False
        self._resources: dict[str, Any] = {}
        self._update_queue: queue.Queue | None = None

    def _log_and_print_error(self, message: str, *args: Any) -> None:
        """Log error message and print to stderr.

        Parameters
        ----------
        message : str
            Error message with optional format placeholders
        *args : Any
            Format arguments for message
        """
        logging.error(message, *args)
        formatted_msg = message % args if args else message
        print(f"Error: {formatted_msg}", file=sys.stderr)

    def _extract_exit_code_from_script(self, script: str) -> int:
        """Extract exit code from script if it contains 'exit N' command.

        Parameters
        ----------
        script : str
            Script content to analyze

        Returns
        -------
        int
            Exit code if found, otherwise 0
        """
        if "exit " not in script:
            return 0

        match = re.search(r"exit\s+(\d+)", script)
        return int(match.group(1)) if match else 0

    def _log_port_forwarding_setup(self, ports: list[int]) -> None:
        """Log SSH tunnel creation messages for each port.

        Parameters
        ----------
        ports : list[int]
            List of ports to log tunnel creation for
        """
        for port in ports:
            logging.info("Creating SSH tunnel for port %s...", port)
            logging.info(
                "SSH tunnel established: localhost:%s -> remote:%s", port, port
            )

    def _cleanup_resources(
        self, signum: int | None = None, frame: types.FrameType | None = None
    ) -> None:
        """Perform graceful cleanup of all resources.

        Parameters
        ----------
        signum : int | None
            Signal number if triggered by signal handler (e.g., signal.SIGINT)
        frame : types.FrameType | None
            Current stack frame (unused but required by signal handler signature).
            Python's signal.signal() requires handlers to accept (signum, frame).

        Notes
        -----
        The cleanup_in_progress flag is set at the start to prevent duplicate
        cleanup if signal handler invokes this method before finally block.
        Thread safety is ensured using cleanup_lock to prevent race conditions.
        """
        with self._cleanup_lock:
            if self._cleanup_in_progress:
                logging.info("Cleanup already in progress, please wait...")
                return
            self._cleanup_in_progress = True

        try:
            errors = []

            with self._resources_lock:
                resources_to_clean = dict(self._resources)
                self._resources.clear()

            if resources_to_clean:
                logging.info("Shutdown requested - beginning cleanup...")

            try:
                if "portforward_mgr" in resources_to_clean:
                    logging.info("Stopping SSH port forwarding tunnels...")

                    if self._update_queue is not None:
                        self._update_queue.put(
                            {
                                "type": "cleanup_event",
                                "payload": {
                                    "step": "stop_tunnels",
                                    "status": "in_progress",
                                },
                            }
                        )

                    try:
                        resources_to_clean["portforward_mgr"].stop_all_tunnels()

                        if self._update_queue is not None:
                            self._update_queue.put(
                                {
                                    "type": "cleanup_event",
                                    "payload": {
                                        "step": "stop_tunnels",
                                        "status": "completed",
                                    },
                                }
                            )
                    except Exception as e:
                        logging.error("Error stopping tunnels: %s", e)
                        errors.append(e)

                        if self._update_queue is not None:
                            self._update_queue.put(
                                {
                                    "type": "cleanup_event",
                                    "payload": {
                                        "step": "stop_tunnels",
                                        "status": "failed",
                                    },
                                }
                            )

                if "mutagen_session_name" in resources_to_clean:
                    logging.info("Terminating Mutagen sync session...")

                    if self._update_queue is not None:
                        self._update_queue.put(
                            {
                                "type": "cleanup_event",
                                "payload": {
                                    "step": "terminate_mutagen",
                                    "status": "in_progress",
                                },
                            }
                        )

                    try:
                        moondock_dir = os.environ.get(
                            "MOONDOCK_DIR", str(Path.home() / ".moondock")
                        )
                        host = resources_to_clean.get("instance_details", {}).get("public_ip")
                        resources_to_clean["mutagen_mgr"].terminate_session(
                            resources_to_clean["mutagen_session_name"],
                            ssh_wrapper_dir=moondock_dir,
                            host=host,
                        )

                        if self._update_queue is not None:
                            self._update_queue.put(
                                {
                                    "type": "cleanup_event",
                                    "payload": {
                                        "step": "terminate_mutagen",
                                        "status": "completed",
                                    },
                                }
                            )
                    except Exception as e:
                        logging.error("Error terminating Mutagen session: %s", e)
                        errors.append(e)

                        if self._update_queue is not None:
                            self._update_queue.put(
                                {
                                    "type": "cleanup_event",
                                    "payload": {
                                        "step": "terminate_mutagen",
                                        "status": "failed",
                                    },
                                }
                            )

                if "ssh_manager" in resources_to_clean:
                    logging.info("Closing SSH connection...")

                    if self._update_queue is not None:
                        self._update_queue.put(
                            {
                                "type": "cleanup_event",
                                "payload": {
                                    "step": "close_ssh",
                                    "status": "in_progress",
                                },
                            }
                        )

                    try:
                        resources_to_clean["ssh_manager"].close()

                        if self._update_queue is not None:
                            self._update_queue.put(
                                {
                                    "type": "cleanup_event",
                                    "payload": {
                                        "step": "close_ssh",
                                        "status": "completed",
                                    },
                                }
                            )
                    except Exception as e:
                        logging.error("Error closing SSH: %s", e)
                        errors.append(e)

                        if self._update_queue is not None:
                            self._update_queue.put(
                                {
                                    "type": "cleanup_event",
                                    "payload": {
                                        "step": "close_ssh",
                                        "status": "failed",
                                    },
                                }
                            )

                if "instance_details" in resources_to_clean:
                    instance_id = resources_to_clean["instance_details"]["instance_id"]
                    logging.info("Terminating EC2 instance %s...", instance_id)

                    if self._update_queue is not None:
                        self._update_queue.put(
                            {
                                "type": "status_update",
                                "payload": {"status": "terminating"},
                            }
                        )
                        self._update_queue.put(
                            {
                                "type": "cleanup_event",
                                "payload": {
                                    "step": "terminate_instance",
                                    "status": "in_progress",
                                },
                            }
                        )

                    try:
                        resources_to_clean["ec2_manager"].terminate_instance(
                            instance_id
                        )

                        if self._update_queue is not None:
                            self._update_queue.put(
                                {
                                    "type": "cleanup_event",
                                    "payload": {
                                        "step": "terminate_instance",
                                        "status": "completed",
                                    },
                                }
                            )
                    except Exception as e:
                        logging.error("Error terminating instance: %s", e)
                        errors.append(e)

                        if self._update_queue is not None:
                            self._update_queue.put(
                                {
                                    "type": "cleanup_event",
                                    "payload": {
                                        "step": "terminate_instance",
                                        "status": "failed",
                                    },
                                }
                            )

                if errors:
                    logging.info("Cleanup completed with %s errors", len(errors))
                else:
                    logging.info("Cleanup completed successfully")

            finally:
                if signum is not None:
                    exit_code = (
                        130
                        if signum == signal.SIGINT
                        else (143 if signum == signal.SIGTERM else 1)
                    )
                    sys.exit(exit_code)

        finally:
            with self._cleanup_lock:
                self._cleanup_in_progress = False

    def _run_test_mode(
        self, merged_config: dict[str, Any], json_output: bool
    ) -> dict[str, Any] | str:
        """Handle test mode execution without real AWS/SSH operations.

        Parameters
        ----------
        merged_config : dict[str, Any]
            Merged configuration dictionary
        json_output : bool
            If True, return JSON string instead of dict

        Returns
        -------
        dict[str, Any] | str
            Mock instance details (as dict or JSON string)

        Raises
        ------
        ValueError
            If instance has no public IP but command execution is required
            If startup_script defined but no sync_paths configured
        """
        if merged_config.get("startup_script") and not merged_config.get("sync_paths"):
            raise ValueError(
                "startup_script is defined but no sync_paths configured. "
                "startup_script requires a synced directory to run in."
            )

        moondock_dir = os.environ.get("MOONDOCK_DIR", str(Path.home() / ".moondock"))
        public_ip = "203.0.113.1"

        if os.environ.get("MOONDOCK_NO_PUBLIC_IP") == "1":
            public_ip = None

        mock_instance = {
            "instance_id": "i-mock123",
            "public_ip": public_ip,
            "state": "running",
            "key_file": str(Path(moondock_dir) / "keys" / "mock.pem"),
            "security_group_id": "sg-mock123",
            "unique_id": "mock123",
        }

        need_ssh = (
            merged_config.get("setup_script")
            or merged_config.get("startup_script")
            or merged_config.get("command")
        )

        if need_ssh:
            if mock_instance["public_ip"] is None:
                raise ValueError(
                    "Instance does not have a public IP address. "
                    "SSH connection requires public networking configuration."
                )

            logging.info("Waiting for SSH to be ready...")
            logging.info("SSH connection established")

            if merged_config.get("env_filter"):
                from moondock.ssh import SSHManager

                mock_ssh = SSHManager(
                    host="203.0.113.1", key_file="/tmp/mock.pem", username="ubuntu"
                )
                mock_ssh.filter_environment_variables(merged_config["env_filter"])

            if merged_config.get("setup_script", "").strip():
                logging.info("Running setup_script...")

                script_exit_code = self._extract_exit_code_from_script(
                    merged_config["setup_script"]
                )

                if script_exit_code != 0:
                    raise RuntimeError(
                        f"Setup script failed with exit code: {script_exit_code}"
                    )

                logging.info("Setup script completed successfully")

            if merged_config.get("sync_paths"):
                logging.info("Starting Mutagen file sync...")
                logging.info("Waiting for initial file sync to complete...")

                if os.environ.get("MOONDOCK_SYNC_TIMEOUT") == "1":
                    raise RuntimeError(
                        "Mutagen sync timed out after 300 seconds. "
                        "Initial sync did not complete."
                    )

                logging.info("File sync completed")

            if merged_config.get("ports"):
                self._log_port_forwarding_setup(merged_config["ports"])

            if merged_config.get("startup_script"):
                logging.info("Running startup_script...")

                script_exit_code = self._extract_exit_code_from_script(
                    merged_config["startup_script"]
                )

                if script_exit_code != 0:
                    raise RuntimeError(
                        f"Startup script failed with exit code: {script_exit_code}"
                    )

                logging.info("Startup script completed successfully")

            if merged_config.get("command"):
                cmd = merged_config["command"]
                exit_code = self._extract_exit_code_from_script(cmd)

                logging.info("Executing command: %s", cmd)
                logging.info("Command completed with exit code: %s", exit_code)
                mock_instance["command_exit_code"] = exit_code

        if json_output:
            return json.dumps(mock_instance, indent=2)

        return mock_instance

    def run(
        self,
        machine_name: str | None = None,
        command: str | None = None,
        instance_type: str | None = None,
        disk_size: int | None = None,
        region: str | None = None,
        port: str | list[int] | tuple[int, ...] | None = None,
        include_vcs: str | bool | None = None,
        ignore: str | None = None,
        json_output: bool = False,
        plain: bool = False,
        verbose: bool = False,
    ) -> dict[str, Any] | str:
        """Launch EC2 instance with file sync and command execution.

        Parameters
        ----------
        machine_name : str | None
            Named machine configuration from YAML, or None to use defaults
        command : str | None
            Command to execute on remote instance (overrides config)
        instance_type : str | None
            EC2 instance type (overrides config)
        disk_size : int | None
            Root disk size in GB (overrides config)
        region : str | None
            AWS region (overrides config)
        port : str | list[int] | tuple[int, ...] | None
            Local port(s) for forwarding - can be single port, comma-separated string,
            list of integers, or tuple of integers (overrides config)
        include_vcs : str | bool | None
            Include VCS files: "true"/"false" strings or True/False booleans (overrides config)
        ignore : str | None
            Comma-separated file patterns to exclude (overrides config)
        json_output : bool
            If True, return JSON string instead of dict (default: False)
        plain : bool
            If True, use plain text logging to stderr instead of TUI (default: False)

        Returns
        -------
        dict[str, Any] | str
            Instance details with fields: instance_id, public_ip, state, key_file,
            security_group_id, unique_id (as dict for testing or JSON string for CLI).
            In TUI mode, returns dict with exit_code and tui_mode=True.

        Raises
        ------
        ValueError
            If include_vcs is not "true" or "false", or if machine name is invalid
        """
        is_tty = sys.stdout.isatty()
        is_test = os.environ.get("MOONDOCK_TEST_MODE") == "1"

        use_tui = not (plain or json_output or is_test or not is_tty)

        if use_tui:
            run_kwargs = {
                "machine_name": machine_name,
                "command": command,
                "instance_type": instance_type,
                "disk_size": disk_size,
                "region": region,
                "port": port,
                "include_vcs": include_vcs,
                "ignore": ignore,
                "json_output": json_output,
            }
            update_queue: queue.Queue = queue.Queue(maxsize=100)
            app = MoondockTUI(
                moondock_instance=self, run_kwargs=run_kwargs, update_queue=update_queue
            )

            original_sigint = signal.signal(signal.SIGINT, self._cleanup_resources)
            original_sigterm = signal.signal(signal.SIGTERM, self._cleanup_resources)

            try:
                exit_code = app.run()
            finally:
                signal.signal(signal.SIGINT, original_sigint)
                signal.signal(signal.SIGTERM, original_sigterm)

            return {
                "exit_code": exit_code if exit_code is not None else 0,
                "tui_mode": True,
                "message": "TUI session completed",
            }

        return self._execute_run(
            machine_name=machine_name,
            command=command,
            instance_type=instance_type,
            disk_size=disk_size,
            region=region,
            port=port,
            include_vcs=include_vcs,
            ignore=ignore,
            json_output=json_output,
            verbose=verbose,
        )

    def _execute_run(
        self,
        machine_name: str | None = None,
        command: str | None = None,
        instance_type: str | None = None,
        disk_size: int | None = None,
        region: str | None = None,
        port: str | list[int] | tuple[int, ...] | None = None,
        include_vcs: str | bool | None = None,
        ignore: str | None = None,
        json_output: bool = False,
        tui_mode: bool = False,
        update_queue: queue.Queue | None = None,
        verbose: bool = False,
    ) -> dict[str, Any] | str:
        """Execute moondock run logic.

        Parameters
        ----------
        machine_name : str | None
            Named machine configuration from YAML, or None to use defaults
        command : str | None
            Command to execute on remote instance (overrides config)
        instance_type : str | None
            EC2 instance type (overrides config)
        disk_size : int | None
            Root disk size in GB (overrides config)
        region : str | None
            AWS region (overrides config)
        port : str | list[int] | tuple[int, ...] | None
            Local port(s) for forwarding - can be single port, comma-separated string,
            list of integers, or tuple of integers (overrides config)
        include_vcs : str | bool | None
            Include VCS files: "true"/"false" strings or True/False booleans (overrides config)
        ignore : str | None
            Comma-separated file patterns to exclude (overrides config)
        json_output : bool
            If True, return JSON string instead of dict (default: False)
        tui_mode : bool
            If True, TUI owns cleanup lifecycle (default: False)
        update_queue : queue.Queue | None
            Queue for sending updates to TUI (default: None)

        Returns
        -------
        dict[str, Any] | str
            Instance details with fields: instance_id, public_ip, state, key_file,
            security_group_id, unique_id (as dict for testing or JSON string for CLI)

        Raises
        ------
        ValueError
            If include_vcs is not "true" or "false", or if machine name is invalid
        """
        if verbose:
            logging.getLogger().setLevel(logging.DEBUG)
            logging.debug("Verbose mode enabled")

        config = self._config_loader.load_config()

        merged_config = self._config_loader.get_machine_config(config, machine_name)

        self._apply_cli_overrides(
            merged_config,
            command,
            instance_type,
            disk_size,
            region,
            port,
            include_vcs,
            ignore,
        )

        self._config_loader.validate_config(merged_config)

        if machine_name is not None:
            merged_config["machine_name"] = machine_name
        else:
            merged_config.setdefault("machine_name", "ad-hoc")

        if merged_config.get("startup_script") and not merged_config.get("sync_paths"):
            raise ValueError(
                "startup_script is defined but no sync_paths configured. "
                "startup_script requires a synced directory to run in."
            )

        self._validate_sync_paths_config(merged_config.get("sync_paths"))

        if update_queue is not None:
            logging.debug("Sending merged_config to TUI queue")
            update_queue.put({"type": "merged_config", "payload": merged_config})

        if os.environ.get("MOONDOCK_TEST_MODE") == "1":
            return self._run_test_mode(merged_config, json_output)

        self._update_queue = update_queue

        if not tui_mode:
            original_sigint = signal.signal(signal.SIGINT, self._cleanup_resources)
            original_sigterm = signal.signal(signal.SIGTERM, self._cleanup_resources)

        try:
            mutagen_mgr = MutagenManager()

            if merged_config.get("sync_paths"):
                mutagen_mgr.check_mutagen_installed()

            ec2_manager = EC2Manager(region=merged_config["region"])

            with self._resources_lock:
                self._resources["ec2_manager"] = ec2_manager

            instance_details = ec2_manager.launch_instance(merged_config)

            with self._resources_lock:
                self._resources["instance_details"] = instance_details

            if update_queue is not None:
                logging.debug("Sending instance_details to TUI queue")
                update_queue.put(
                    {"type": "instance_details", "payload": instance_details}
                )

            ssh_manager = None
            mutagen_session_name = None
            portforward_mgr = None
            need_ssh = (
                merged_config.get("setup_script")
                or merged_config.get("startup_script")
                or merged_config.get("command")
            )

            if not need_ssh:
                if json_output:
                    return json.dumps(instance_details, indent=2)

                return instance_details

            if instance_details["public_ip"] is None:
                raise ValueError(
                    "Instance does not have a public IP address. "
                    "SSH connection requires public networking configuration."
                )

            logging.info("Waiting for SSH to be ready...")

            ssh_manager = SSHManager(
                host=instance_details["public_ip"],
                key_file=instance_details["key_file"],
                username="ubuntu",
            )
            ssh_manager.connect(max_retries=10)
            logging.info("SSH connection established")

            logging.debug("Waiting 10 seconds for instance to fully initialize...")
            time.sleep(10)

            if update_queue is not None:
                update_queue.put(
                    {"type": "status_update", "payload": {"status": "running"}}
                )

            with self._resources_lock:
                self._resources["ssh_manager"] = ssh_manager

            env_vars = ssh_manager.filter_environment_variables(
                merged_config.get("env_filter")
            )

            if merged_config.get("sync_paths"):
                mutagen_session_name = f"moondock-{instance_details['unique_id']}"
                mutagen_mgr.cleanup_orphaned_session(mutagen_session_name)

                with self._resources_lock:
                    self._resources["mutagen_mgr"] = mutagen_mgr
                    self._resources["mutagen_session_name"] = mutagen_session_name
            else:
                if update_queue is not None:
                    update_queue.put(
                        {
                            "type": "mutagen_status",
                            "payload": {"state": "not_configured"},
                        }
                    )

            if merged_config.get("sync_paths"):
                sync_config = merged_config["sync_paths"][0]

                logging.info("Starting Mutagen file sync...")
                logging.debug(
                    "Mutagen sync details - local: %s, remote: %s, host: %s",
                    sync_config["local"],
                    sync_config["remote"],
                    instance_details["public_ip"],
                )

                if update_queue is not None:
                    update_queue.put(
                        {
                            "type": "mutagen_status",
                            "payload": {"state": "starting", "files_synced": 0},
                        }
                    )

                moondock_dir = os.environ.get(
                    "MOONDOCK_DIR", str(Path.home() / ".moondock")
                )

                logging.debug("Creating Mutagen sync session: %s", mutagen_session_name)
                mutagen_mgr.create_sync_session(
                    session_name=mutagen_session_name,
                    local_path=sync_config["local"],
                    remote_path=sync_config["remote"],
                    host=instance_details["public_ip"],
                    key_file=instance_details["key_file"],
                    username="ubuntu",
                    ignore_patterns=merged_config.get("ignore"),
                    include_vcs=merged_config.get("include_vcs", False),
                    ssh_wrapper_dir=moondock_dir,
                )

            if merged_config.get("setup_script", "").strip():
                logging.info("Running setup_script...")

                setup_with_env = ssh_manager.build_command_with_env(
                    merged_config["setup_script"], env_vars
                )
                exit_code = ssh_manager.execute_command(setup_with_env)

                if exit_code != 0:
                    raise RuntimeError(
                        f"Setup script failed with exit code: {exit_code}"
                    )

                logging.info("Setup script completed successfully")

            if merged_config.get("sync_paths"):
                logging.info("Waiting for initial file sync to complete...")

                if update_queue is not None:
                    update_queue.put(
                        {
                            "type": "mutagen_status",
                            "payload": {"state": "syncing", "files_synced": 0},
                        }
                    )

                mutagen_mgr.wait_for_initial_sync(
                    mutagen_session_name, timeout=SYNC_TIMEOUT
                )
                logging.info("File sync completed")

                if update_queue is not None:
                    update_queue.put(
                        {
                            "type": "mutagen_status",
                            "payload": {"state": "idle"},
                        }
                    )

            if merged_config.get("ports"):
                portforward_mgr = PortForwardManager()

                with self._resources_lock:
                    self._resources["portforward_mgr"] = portforward_mgr

                try:
                    portforward_mgr.create_tunnels(
                        ports=merged_config["ports"],
                        host=instance_details["public_ip"],
                        key_file=instance_details["key_file"],
                        username="ubuntu",
                    )
                except RuntimeError as e:
                    logging.error("Port forwarding failed: %s", e)
                    raise

            if merged_config.get("startup_script"):
                working_dir = merged_config["sync_paths"][0]["remote"]

                logging.info("Running startup_script...")

                startup_command = self._build_command_in_directory(
                    working_dir, merged_config["startup_script"]
                )
                startup_with_env = ssh_manager.build_command_with_env(
                    startup_command, env_vars
                )
                exit_code = ssh_manager.execute_command_raw(startup_with_env)

                if exit_code != 0:
                    raise RuntimeError(
                        f"Startup script failed with exit code: {exit_code}"
                    )

                logging.info("Startup script completed successfully")

            if merged_config.get("command"):
                cmd = merged_config["command"]
                logging.info("Executing command: %s", cmd)

                if merged_config.get("sync_paths"):
                    working_dir = merged_config["sync_paths"][0]["remote"]
                    full_command = self._build_command_in_directory(working_dir, cmd)
                    command_with_env = ssh_manager.build_command_with_env(
                        full_command, env_vars
                    )
                    exit_code = ssh_manager.execute_command_raw(command_with_env)
                else:
                    command_with_env = ssh_manager.build_command_with_env(cmd, env_vars)
                    exit_code = ssh_manager.execute_command(command_with_env)

                logging.info("Command completed with exit code: %s", exit_code)
                instance_details["command_exit_code"] = exit_code

            if json_output:
                return json.dumps(instance_details, indent=2)

            return instance_details

        finally:
            if not tui_mode and not self._cleanup_in_progress:
                self._cleanup_resources()

            if not tui_mode:
                signal.signal(signal.SIGINT, original_sigint)
                signal.signal(signal.SIGTERM, original_sigterm)

    def _apply_cli_overrides(
        self,
        config: dict[str, Any],
        command: str | None,
        instance_type: str | None,
        disk_size: int | None,
        region: str | None,
        port: str | list[int] | tuple[int, ...] | None,
        include_vcs: str | bool | None,
        ignore: str | None,
    ) -> None:
        """Apply CLI option overrides to merged configuration.

        Parameters
        ----------
        config : dict[str, Any]
            Configuration dictionary to modify in-place
        command : str | None
            Command to execute on remote instance
        instance_type : str | None
            EC2 instance type
        disk_size : int | None
            Root disk size in GB
        region : str | None
            AWS region
        port : str | list[int] | tuple[int, ...] | None
            Local port(s) for forwarding
        include_vcs : str | bool | None
            Include VCS files
        ignore : str | None
            Comma-separated file patterns to exclude
        """

        if command is not None:
            config["command"] = command

        if instance_type is not None:
            config["instance_type"] = instance_type

        if disk_size is not None:
            config["disk_size"] = disk_size

        if region is not None:
            config["region"] = region

        if port is not None:
            config["ports"] = self._parse_port_parameter(port)
            config.pop("port", None)

        if include_vcs is not None:
            config["include_vcs"] = self._parse_include_vcs(include_vcs)

        if ignore is not None:
            config["ignore"] = self._parse_ignore_patterns(ignore)

    def _parse_port_parameter(
        self, port: str | list[int] | tuple[int, ...]
    ) -> list[int]:
        """Parse port parameter into list of integers.

        Parameters
        ----------
        port : str | list[int] | tuple[int, ...]
            Port specification - can be single value, comma-separated string, list, or tuple

        Returns
        -------
        list[int]
            List of port numbers as integers
        """

        if isinstance(port, (tuple, list)):
            return [int(p) for p in port]

        return [int(p.strip()) for p in str(port).split(",") if p.strip()]

    def _parse_include_vcs(self, include_vcs: str | bool) -> bool:
        """Parse include_vcs parameter into boolean.

        Parameters
        ----------
        include_vcs : str | bool
            VCS inclusion flag - can be boolean or "true"/"false" string

        Returns
        -------
        bool
            Boolean value for VCS inclusion

        Raises
        ------
        ValueError
            If string value is not "true" or "false"
        """

        if isinstance(include_vcs, bool):
            return include_vcs

        if isinstance(include_vcs, str):
            vcs_lower = include_vcs.lower()

            if vcs_lower not in ("true", "false"):
                raise ValueError(
                    f"include_vcs must be 'true' or 'false', got: {include_vcs}"
                )

            return vcs_lower == "true"

        raise ValueError(f"Unexpected type for include_vcs: {type(include_vcs)}")

    def _parse_ignore_patterns(self, ignore: str) -> list[str]:
        """Parse comma-separated ignore patterns into list.

        Parameters
        ----------
        ignore : str
            Comma-separated file patterns to exclude

        Returns
        -------
        list[str]
            List of ignore patterns
        """
        return [pattern.strip() for pattern in ignore.split(",") if pattern.strip()]

    def _validate_sync_paths_config(self, sync_paths: list | None) -> None:
        """Validate sync_paths configuration structure.

        Parameters
        ----------
        sync_paths : list | None
            Sync paths configuration to validate

        Raises
        ------
        ValueError
            If sync_paths is not a list or missing required keys in entries
        """
        if not sync_paths:
            return

        if not isinstance(sync_paths, list):
            raise ValueError("sync_paths must be a list")

        sync_config = sync_paths[0]

        if "local" not in sync_config or "remote" not in sync_config:
            raise ValueError(
                "sync_paths entry must have both 'local' and 'remote' keys. "
                f"Got: {sync_config}"
            )

    def _build_command_in_directory(self, working_dir: str, command: str) -> str:
        """Build command that executes in specific working directory.

        Parameters
        ----------
        working_dir : str
            Directory path to execute command in
        command : str
            Command to execute

        Returns
        -------
        str
            Full command with directory change and proper escaping
        """
        return f"mkdir -p {shlex.quote(working_dir)} && cd {shlex.quote(working_dir)} && bash -c {repr(command)}"

    def _truncate_name(self, name: str) -> str:
        """Truncate machine config name to fit in column width.

        Parameters
        ----------
        name : str
            Machine config name to truncate

        Returns
        -------
        str
            Truncated name with ellipsis if exceeds MAX_NAME_COLUMN_WIDTH, otherwise original name
        """
        if len(name) > MAX_NAME_COLUMN_WIDTH:
            return name[: MAX_NAME_COLUMN_WIDTH - 3] + "..."

        return name

    def _validate_region(self, region: str) -> None:
        """Validate that a region string is a valid AWS region.

        Parameters
        ----------
        region : str
            AWS region string to validate

        Raises
        ------
        ValueError
            If region is not a valid AWS region
        """
        import boto3

        try:
            ec2_client = boto3.client("ec2", region_name="us-east-1")
            regions_response = ec2_client.describe_regions()
            valid_regions = {r["RegionName"] for r in regions_response["Regions"]}

            if region not in valid_regions:
                raise ValueError(
                    f"Invalid AWS region: '{region}'. "
                    f"Valid regions: {', '.join(sorted(valid_regions))}"
                )
        except (NoCredentialsError, ClientError) as e:
            logging.warning(
                "Unable to validate region '%s' (%s). Proceeding without validation.",
                region,
                e.__class__.__name__,
            )

    def list(self, region: str | None = None) -> None:
        """List all moondock-managed EC2 instances.

        Parameters
        ----------
        region : str | None
            Optional AWS region to filter results

        Raises
        ------
        NoCredentialsError
            If AWS credentials are not configured
        ClientError
            If AWS API calls fail
        ValueError
            If provided region is not a valid AWS region
        """
        default_region = self._config_loader.BUILT_IN_DEFAULTS["region"]

        if region is not None:
            self._validate_region(region)

        try:
            ec2_manager = EC2Manager(region=region or default_region)
            instances = ec2_manager.list_instances(region_filter=region)

            if not instances:
                print("No moondock-managed instances found")
                return

            if region:
                print(f"Instances in {region}:")
                print(
                    f"{'NAME':<20} {'INSTANCE-ID':<20} {'STATUS':<12} {'TYPE':<15} {'LAUNCHED':<12}"
                )
                print("-" * 79)

                for inst in instances:
                    name = self._truncate_name(inst["machine_config"])
                    launched = format_time_ago(inst["launch_time"])
                    print(
                        f"{name:<20} {inst['instance_id']:<20} {inst['state']:<12} {inst['instance_type']:<15} {launched:<12}"
                    )
            else:
                print(
                    f"{'NAME':<20} {'INSTANCE-ID':<20} {'STATUS':<12} {'REGION':<15} {'TYPE':<15} {'LAUNCHED':<12}"
                )
                print("-" * 94)

                for inst in instances:
                    name = self._truncate_name(inst["machine_config"])
                    launched = format_time_ago(inst["launch_time"])
                    print(
                        f"{name:<20} {inst['instance_id']:<20} {inst['state']:<12} {inst['region']:<15} {inst['instance_type']:<15} {launched:<12}"
                    )

        except NoCredentialsError:
            print("Error: AWS credentials not found. Please configure AWS credentials.")
            raise
        except ClientError as e:
            if "UnauthorizedOperation" in str(e):
                print("Error: Insufficient AWS permissions to list instances.")
                raise

            raise

    def stop(self, name_or_id: str, region: str | None = None) -> None:
        """Terminate a moondock-managed EC2 instance by MachineConfig or ID.

        Parameters
        ----------
        name_or_id : str
            EC2 instance ID or MachineConfig name to terminate
        region : str | None
            Optional AWS region to narrow search scope

        Raises
        ------
        SystemExit
            Exits with code 1 if no instance matches, multiple instances match,
            or AWS errors occur. Returns normally on successful termination.
        """
        default_region = self._config_loader.BUILT_IN_DEFAULTS["region"]

        if region:
            self._validate_region(region)

        target: dict[str, Any] | None = None

        try:
            search_manager = EC2Manager(region=region or default_region)
            matches = search_manager.find_instances_by_name_or_id(
                name_or_id=name_or_id, region_filter=region
            )

            if not matches:
                self._log_and_print_error(
                    "No moondock-managed instances matched '%s'.", name_or_id
                )
                sys.exit(1)

            if len(matches) > 1:
                logging.error(
                    "Ambiguous machine config '%s'; matches multiple instances.",
                    name_or_id,
                )
                print(
                    "Multiple instances found. Please use a specific instance ID to stop:",
                    file=sys.stderr,
                )

                for match in matches:
                    print(
                        f"  {match['instance_id']} ({match['region']})", file=sys.stderr
                    )

                sys.exit(1)

            target = matches[0]
            logging.info(
                "Terminating instance %s (%s) in %s...",
                target["instance_id"],
                target["machine_config"],
                target["region"],
            )

            regional_manager = EC2Manager(region=target["region"])
            regional_manager.terminate_instance(target["instance_id"])

            print(f"Instance {target['instance_id']} has been successfully terminated.")
        except RuntimeError as e:
            if target is not None:
                self._log_and_print_error(
                    "Failed to terminate instance %s: %s",
                    target["instance_id"],
                    str(e),
                )
            else:
                self._log_and_print_error("Failed to terminate instance: %s", str(e))

            sys.exit(1)
        except NoCredentialsError:
            self._log_and_print_error(
                "AWS credentials not configured. Please set up AWS credentials."
            )
            sys.exit(1)
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")

            if error_code == "UnauthorizedOperation":
                self._log_and_print_error(
                    "Insufficient AWS permissions to perform this operation."
                )
                sys.exit(1)

            self._log_and_print_error("AWS API error: %s", e)
            sys.exit(1)

    def init(self, force: bool = False) -> None:
        """Create a default moondock.yaml configuration file.

        Parameters
        ----------
        force : bool
            If True, overwrite an existing configuration file (default: False)

        Raises
        ------
        SystemExit
            Exits with code 1 if file exists and force is False
        """
        config_path = os.environ.get("MOONDOCK_CONFIG", "moondock.yaml")
        config_file = Path(config_path)

        if config_file.exists() and not force:
            self._log_and_print_error(
                "%s already exists. Use --force to overwrite.",
                config_path,
            )
            sys.exit(1)

        config_file.parent.mkdir(parents=True, exist_ok=True)

        with open(config_file, "w") as f:
            f.write(CONFIG_TEMPLATE)

        print(f"Created {config_path} configuration file.")

    def _get_effective_region(self, region: str | None) -> str:
        """Get effective region from parameter or config.

        Parameters
        ----------
        region : str | None
            Region parameter from command line

        Returns
        -------
        str
            Effective region to use
        """
        effective_region = region or self._config_loader.BUILT_IN_DEFAULTS["region"]

        config = self._config_loader.load_config()

        if config.get("defaults", {}).get("region") and not region:
            effective_region = config["defaults"]["region"]

        return effective_region

    def _check_aws_credentials(self, effective_region: str) -> bool:
        """Check if AWS credentials are configured and functional.

        Parameters
        ----------
        effective_region : str
            AWS region to check

        Returns
        -------
        bool
            True if credentials are valid, False otherwise
        """
        import boto3
        from botocore.exceptions import ClientError, NoCredentialsError

        try:
            sts_client = boto3.client("sts", region_name=effective_region)
            sts_client.get_caller_identity()
            print("AWS credentials found")
            return True
        except NoCredentialsError:
            print("AWS credentials not found\n")
            print("Fix it:")
            print("  aws configure")
            return False
        except ClientError:
            print("AWS credentials found")
            return True

    def _check_vpc_status(self, ec2_client: Any, effective_region: str) -> bool:
        """Check if default VPC exists in region.

        Parameters
        ----------
        ec2_client : Any
            boto3 EC2 client
        effective_region : str
            AWS region to check

        Returns
        -------
        bool
            True if default VPC exists, False otherwise
        """
        vpcs = ec2_client.describe_vpcs(
            Filters=[{"Name": "isDefault", "Values": ["true"]}]
        )

        return bool(vpcs["Vpcs"])

    def _check_iam_permissions(self, ec2_client: Any) -> list[str]:
        """Check IAM permissions for moondock operations.

        Parameters
        ----------
        ec2_client : Any
            boto3 EC2 client

        Returns
        -------
        list[str]
            List of missing permissions
        """
        from botocore.exceptions import ClientError

        missing = []

        read_checks = [
            ("DescribeInstances", lambda: ec2_client.describe_instances(MaxResults=5)),
            ("DescribeVpcs", lambda: ec2_client.describe_vpcs(MaxResults=5)),
            ("DescribeKeyPairs", lambda: ec2_client.describe_key_pairs()),
            (
                "DescribeSecurityGroups",
                lambda: ec2_client.describe_security_groups(MaxResults=5),
            ),
        ]

        for perm_name, check_func in read_checks:
            try:
                check_func()
            except ClientError as e:
                if "UnauthorizedOperation" in str(e) or "AccessDenied" in str(e):
                    missing.append(perm_name)

        write_checks = [
            (
                "RunInstances",
                lambda: ec2_client.run_instances(
                    ImageId="ami-12345678",
                    InstanceType="t2.micro",
                    MinCount=1,
                    MaxCount=1,
                    DryRun=True,
                ),
            ),
            (
                "TerminateInstances",
                lambda: ec2_client.terminate_instances(
                    InstanceIds=["i-12345678"], DryRun=True
                ),
            ),
            (
                "CreateDefaultVpc",
                lambda: ec2_client.create_default_vpc(DryRun=True),
            ),
            (
                "CreateKeyPair",
                lambda: ec2_client.create_key_pair(
                    KeyName="test-key-dry-run", DryRun=True
                ),
            ),
            (
                "DeleteKeyPair",
                lambda: ec2_client.delete_key_pair(
                    KeyName="test-key-dry-run", DryRun=True
                ),
            ),
        ]

        for perm_name, check_func in write_checks:
            try:
                check_func()
            except ClientError as e:
                error_code = e.response.get("Error", {}).get("Code", "")

                if error_code == "DryRunOperation":
                    pass
                elif error_code in ["UnauthorizedOperation", "AccessDenied"]:
                    missing.append(perm_name)

        return missing

    def _check_service_quotas(self, ec2_client: Any, effective_region: str) -> None:
        """Check EC2 service quotas for instance limits.

        Parameters
        ----------
        ec2_client : Any
            boto3 EC2 client
        effective_region : str
            AWS region to check
        """
        try:
            response = ec2_client.describe_account_attributes(
                AttributeNames=["max-instances"]
            )

            for attr in response.get("AccountAttributes", []):
                if attr["AttributeName"] == "max-instances":
                    max_instances = attr["AttributeValues"][0]["AttributeValue"]
                    print(f"EC2 instance limit: {max_instances} instances")

            instances = ec2_client.describe_instances()
            running_count = sum(
                1
                for r in instances["Reservations"]
                for inst in r["Instances"]
                if inst["State"]["Name"] in ["running", "pending"]
            )
            print(f"Currently running: {running_count} instances")

        except ClientError as e:
            logging.warning("Could not check service quotas: %s", e)

    def _check_regional_availability(
        self, ec2_client: Any, effective_region: str
    ) -> None:
        """Check if region is available and operational.

        Parameters
        ----------
        ec2_client : Any
            boto3 EC2 client
        effective_region : str
            AWS region to check
        """
        try:
            response = ec2_client.describe_availability_zones()
            zones = response.get("AvailabilityZones", [])

            print(f"\nRegional availability in {effective_region}:")
            for zone in zones:
                status = zone["State"]
                zone_name = zone["ZoneName"]
                print(f"  {zone_name}: {status}")

        except ClientError as e:
            logging.warning("Could not check regional availability: %s", e)

    def _check_infrastructure(
        self, ec2_client: Any, effective_region: str
    ) -> tuple[bool, list[str]]:
        """Check AWS infrastructure status.

        Parameters
        ----------
        ec2_client : Any
            boto3 EC2 client
        effective_region : str
            AWS region to check

        Returns
        -------
        tuple[bool, list[str]]
            Tuple of (vpc_exists, missing_permissions)
        """
        vpc_exists = self._check_vpc_status(ec2_client, effective_region)
        missing_perms = self._check_iam_permissions(ec2_client)

        return vpc_exists, missing_perms

    def setup(self, region: str | None = None, ec2_client: Any = None) -> None:
        """Validate and prepare AWS infrastructure prerequisites.

        Parameters
        ----------
        region : str | None
            AWS region to check (defaults to config or us-east-1)
        ec2_client : Any
            boto3 EC2 client (for testing purposes)

        Raises
        ------
        SystemExit
            Exits with code 1 if AWS credentials are not found
        """
        import os

        import boto3

        effective_region = self._get_effective_region(region)

        print(f"Checking AWS prerequisites for {effective_region}...\n")

        if not self._check_aws_credentials(effective_region):
            sys.exit(1)

        is_test_mode = os.environ.get("MOONDOCK_TEST_MODE") == "1"

        if ec2_client is None and not is_test_mode:
            ec2_client = boto3.client("ec2", region_name=effective_region)

        if not is_test_mode:
            vpc_exists, missing_perms = self._check_infrastructure(
                ec2_client, effective_region
            )
        else:
            vpc_exists = os.environ.get("MOONDOCK_TEST_VPC_EXISTS") == "true"
            missing_perms = []

        if not vpc_exists:
            print(f"No default VPC found in {effective_region}\n")

            response = input("Create default VPC now? (y/n): ")

            if response.lower() == "y":
                try:
                    if not is_test_mode:
                        ec2_client.create_default_vpc()
                    print(f"Default VPC created in {effective_region}")
                except ClientError as e:
                    print(f"\nFailed to create VPC: {e}")
                    print("\nManual creation:")
                    print(f"  aws ec2 create-default-vpc --region {effective_region}")
                    sys.exit(1)
            else:
                print("\nSkipping VPC creation.")
                print("You can create it later with:")
                print(f"  aws ec2 create-default-vpc --region {effective_region}")
                return
        else:
            print(f"Default VPC exists in {effective_region}")

        if missing_perms:
            print(f"Missing IAM permissions: {', '.join(missing_perms)}")
            print("\nSome operations may fail without these permissions.")
        else:
            print("IAM permissions verified")

        print("\nSetup complete! Run: moondock run")

    def doctor(self, region: str | None = None, ec2_client: Any = None) -> None:
        """Diagnose AWS environment and report status.

        Parameters
        ----------
        region : str | None
            AWS region to check (defaults to config or us-east-1)
        ec2_client : Any
            boto3 EC2 client (for testing purposes)

        Raises
        ------
        SystemExit
            Exits with code 1 if AWS credentials are not found
        """
        import os

        import boto3

        effective_region = self._get_effective_region(region)

        print(f"Running diagnostics for {effective_region}...\n")

        if not self._check_aws_credentials(effective_region):
            sys.exit(1)

        is_test_mode = os.environ.get("MOONDOCK_TEST_MODE") == "1"

        if ec2_client is None and not is_test_mode:
            ec2_client = boto3.client("ec2", region_name=effective_region)

        if not is_test_mode:
            vpc_exists, missing_perms = self._check_infrastructure(
                ec2_client, effective_region
            )
        else:
            vpc_exists = os.environ.get("MOONDOCK_TEST_VPC_EXISTS") == "true"
            missing_perms = []

            if ec2_client is None:
                ec2_client = boto3.client("ec2", region_name=effective_region)

        if not vpc_exists:
            print(f"No default VPC in {effective_region}\n")
            print("Fix it:")
            print("  moondock setup")
            print("Or manually:")
            print(f"  aws ec2 create-default-vpc --region {effective_region}")
        else:
            print(f"Default VPC exists in {effective_region}")

        if missing_perms:
            print(f"Missing IAM permissions: {', '.join(missing_perms)}")
            print("\nRequired permissions:")
            for perm in missing_perms:
                print(f"  - {perm}")
        else:
            print("IAM permissions verified")

        if ec2_client is not None:
            print()
            self._check_service_quotas(ec2_client, effective_region)
            self._check_regional_availability(ec2_client, effective_region)

        print("\nDiagnostics complete.")


class MoondockCLI(Moondock):
    """CLI wrapper that handles process exit codes."""

    def run(
        self,
        machine_name: str | None = None,
        command: str | None = None,
        instance_type: str | None = None,
        disk_size: int | None = None,
        region: str | None = None,
        port: str | list[int] | tuple[int, ...] | None = None,
        include_vcs: str | bool | None = None,
        ignore: str | None = None,
        json_output: bool = False,
        plain: bool = False,
        verbose: bool = False,
    ) -> dict[str, Any] | str:
        """Run Moondock and handle TUI exit codes for CLI context.

        Parameters
        ----------
        machine_name : str | None
            Name of machine configuration from YAML
        command : str | None
            Command to execute on remote instance
        instance_type : str | None
            EC2 instance type override
        disk_size : int | None
            Root disk size in GB override
        region : str | None
            AWS region override
        port : str | list[int] | tuple[int, ...] | None
            Port(s) to forward
        include_vcs : str | bool | None
            Include VCS files in sync
        ignore : str | None
            Comma-separated ignore patterns
        json_output : bool
            Output result as JSON
        plain : bool
            Disable TUI, use plain stderr logging

        Returns
        -------
        dict[str, Any] | str
            Instance metadata dict or JSON string (never returns in TUI mode, exits instead)
        """
        result = super().run(
            machine_name=machine_name,
            command=command,
            instance_type=instance_type,
            disk_size=disk_size,
            region=region,
            port=port,
            include_vcs=include_vcs,
            ignore=ignore,
            json_output=json_output,
            plain=plain,
            verbose=verbose,
        )

        if isinstance(result, dict) and result.get("tui_mode"):
            sys.exit(result.get("exit_code", 0))

        return result


def main() -> None:
    """Entry point for Fire CLI with graceful error handling.

    This function initializes the Fire CLI interface by passing the MoondockCLI
    class to Fire, which automatically generates CLI commands from the class
    methods. The function should be called when the script is executed directly.

    Notes
    -----
    Fire automatically maps class methods to CLI commands and handles argument
    parsing, help text generation, and command routing.
    """
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(StreamFormatter("%(message)s"))
    stdout_handler.addFilter(StreamRoutingFilter("stdout"))

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(StreamFormatter("%(message)s"))
    stderr_handler.addFilter(StreamRoutingFilter("stderr"))

    logging.basicConfig(
        level=logging.INFO,
        handlers=[stdout_handler, stderr_handler],
    )

    debug_mode = os.environ.get("MOONDOCK_DEBUG") == "1"

    try:
        fire.Fire(MoondockCLI())
    except NoCredentialsError:
        if debug_mode:
            raise

        print("AWS credentials not found\n", file=sys.stderr)
        print("Configure your credentials:", file=sys.stderr)
        print("  aws configure\n", file=sys.stderr)
        print("Or set environment variables:", file=sys.stderr)
        print("  export AWS_ACCESS_KEY_ID=...", file=sys.stderr)
        print("  export AWS_SECRET_ACCESS_KEY=...", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        if debug_mode:
            raise

        error_msg = str(e)

        if "No default VPC" in error_msg:
            import re

            match = re.search(r"in\s+region\s+(\S+)", error_msg)
            region = match.group(1) if match else "us-east-1"

            print(f"No default VPC in {region}\n", file=sys.stderr)
            print("Fix it:", file=sys.stderr)
            print("  moondock setup\n", file=sys.stderr)
            print("Or manually:", file=sys.stderr)
            print(f"  aws ec2 create-default-vpc --region {region}\n", file=sys.stderr)
            print("Or use different region:", file=sys.stderr)
            print("  moondock run --region us-west-2", file=sys.stderr)
            sys.exit(1)
        elif "startup_script" in error_msg and "sync_paths" in error_msg:
            print("Configuration error\n", file=sys.stderr)
            print("startup_script requires sync_paths to be configured\n", file=sys.stderr)
            print("Add sync_paths to your configuration:", file=sys.stderr)
            print("  sync_paths:", file=sys.stderr)
            print("    - local: ./src", file=sys.stderr)
            print("      remote: /home/ubuntu/src", file=sys.stderr)
            sys.exit(1)
        else:
            raise
    except ClientError as e:
        if debug_mode:
            raise

        error_code = e.response.get("Error", {}).get("Code", "")
        error_msg = e.response.get("Error", {}).get("Message", str(e))

        if error_code == "UnauthorizedOperation":
            print("Insufficient IAM permissions\n", file=sys.stderr)
            print("Your AWS credentials don't have the required permissions.", file=sys.stderr)
            print("Contact your AWS administrator to grant:", file=sys.stderr)
            print(
                "  - EC2 permissions (DescribeInstances, RunInstances, TerminateInstances)", file=sys.stderr
            )
            print("  - VPC permissions (DescribeVpcs, CreateDefaultVpc)", file=sys.stderr)
            print(
                "  - Key Pair permissions (CreateKeyPair, DeleteKeyPair, DescribeKeyPairs)", file=sys.stderr
            )
            print("  - Security Group permissions", file=sys.stderr)
        elif (
            error_code == "InvalidParameterValue"
            and "instance type" in error_msg.lower()
        ):
            print("Invalid instance type\n", file=sys.stderr)
            print("This usually means:", file=sys.stderr)
            print("  - Instance type not available in this region", file=sys.stderr)
            print("  - Typo in instance type name\n", file=sys.stderr)
            print("Fix it:", file=sys.stderr)
            print("  moondock doctor", file=sys.stderr)
            print("  moondock run --instance-type t3.medium", file=sys.stderr)
        elif error_code in ["InstanceLimitExceeded", "RequestLimitExceeded"]:
            print("AWS quota exceeded\n", file=sys.stderr)
            print("This usually means:", file=sys.stderr)
            print("  - Too many instances running", file=sys.stderr)
            print("  - Need to request quota increase\n", file=sys.stderr)
            print("Fix it:", file=sys.stderr)
            print("  https://console.aws.amazon.com/servicequotas/", file=sys.stderr)
            print("  moondock list", file=sys.stderr)
        elif error_code in ["ExpiredToken", "RequestExpired", "ExpiredTokenException"]:
            print("AWS credentials have expired\n", file=sys.stderr)
            print("This usually means:", file=sys.stderr)
            print("  - Your temporary credentials (STS) have expired", file=sys.stderr)
            print("  - Your session token needs to be refreshed\n", file=sys.stderr)
            print("Fix it:", file=sys.stderr)
            print("  aws sso login           # If using AWS SSO", file=sys.stderr)
            print("  aws configure           # Re-configure credentials", file=sys.stderr)
            print("  # Or refresh your temporary credentials", file=sys.stderr)
        else:
            print(f"AWS API error: {error_msg}", file=sys.stderr)

        sys.exit(1)
    except (paramiko.SSHException, paramiko.AuthenticationException, socket.error):
        if debug_mode:
            raise

        print("SSH connectivity error\n", file=sys.stderr)
        print("This usually means:", file=sys.stderr)
        print("  - Instance not yet ready", file=sys.stderr)
        print("  - Security group blocking SSH", file=sys.stderr)
        print("  - Network connectivity issues\n", file=sys.stderr)
        print("Debugging steps:", file=sys.stderr)
        print("  1. Wait 30-60 seconds and try again", file=sys.stderr)
        print("  2. Check security group allows port 22", file=sys.stderr)
        print("  3. Verify instance is running: moondock list", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        if debug_mode:
            raise

        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
