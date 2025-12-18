from __future__ import annotations

import logging
import os
import queue
import signal
import subprocess
import sys
import threading
import time
import types
from pathlib import Path
from typing import Any

import paramiko

from campers.constants import TUI_STATUS_UPDATE_PROCESSING_DELAY
from campers.core.interfaces import PricingProvider
from campers.core.utils import get_instance_id, get_volume_size_or_default
from campers.providers.exceptions import ProviderAPIError
from campers.utils import status_spinner


class CleanupManager:
    """Manages graceful cleanup of cloud instances and associated resources.

    Parameters
    ----------
    resources_dict : dict[str, Any]
        Shared resources dictionary containing compute_provider, ssh_manager, etc.
    resources_lock : threading.Lock
        Lock for thread-safe access to resources dictionary
    cleanup_lock : threading.Lock
        Lock for ensuring only one cleanup runs at a time
    update_queue : queue.Queue | None
        Queue for sending cleanup events to TUI (optional)
    config_dict : dict[str, Any] | None
        Configuration dictionary (optional)
    pricing_provider : PricingProvider | None
        Pricing service for getting storage rates (optional)

    Notes
    -----
    Lock Ordering: Always acquire cleanup_lock before resources_lock to prevent deadlocks.
    This ordering is maintained throughout the cleanup operation to ensure consistent
    synchronization semantics.
    """

    def __init__(
        self,
        resources_dict: dict[str, Any],
        resources_lock: threading.Lock,
        cleanup_lock: threading.Lock,
        update_queue: queue.Queue | None = None,
        config_dict: dict[str, Any] | None = None,
        pricing_provider: PricingProvider | None = None,
    ) -> None:
        self.resources = resources_dict
        self.resources_lock = resources_lock
        self.cleanup_lock = cleanup_lock
        self.update_queue = update_queue
        self.config_dict = config_dict or {}
        self.pricing_provider = pricing_provider
        self.cleanup_in_progress = False
        self.cleanup_event = threading.Event()

    def _emit_cleanup_event(self, step: str, status: str) -> None:
        """Emit cleanup event to TUI update queue.

        Parameters
        ----------
        step : str
            Name of the cleanup step
        status : str
            Status of the step (in_progress, completed, or failed)
        """
        if self.update_queue is not None:
            try:
                self.update_queue.put_nowait(
                    {
                        "type": "cleanup_event",
                        "payload": {"step": step, "status": status},
                    }
                )
            except queue.Full:
                logging.warning("TUI update queue full, dropping cleanup event")

    def _get_storage_rate(self, region: str) -> float:
        """Get storage rate for a region using pricing provider.

        Parameters
        ----------
        region : str
            Cloud region code

        Returns
        -------
        float
            Storage rate in USD per GB-month (0.0 if API unavailable or no provider)
        """
        if self.pricing_provider is None:
            logging.debug("No pricing provider available, returning default rate of 0.0")
            return 0.0

        try:
            rate = self.pricing_provider.get_storage_price(region)

            if rate > 0:
                return rate
        except (OSError, ConnectionError, TimeoutError) as e:
            logging.debug("Failed to fetch storage pricing: %s", e)

        return 0.0

    def cleanup_resources(
        self, action: str = "stop", signum: int | None = None, _frame: types.FrameType | None = None
    ) -> None:
        """Perform graceful cleanup of all resources.

        Parameters
        ----------
        action : str
            Cleanup action to perform: "stop", "terminate", or "detach"
        signum : int | None
            Signal number if triggered by signal handler (e.g., signal.SIGINT)
        _frame : types.FrameType | None
            Current stack frame (unused but required by signal handler signature).
            Python's signal.signal() requires handlers to accept (signum, frame).

        Notes
        -----
        Cleanup actions:
        - "stop": Preserves instance and resources for restart
        - "terminate": Removes all resources (full cleanup)
        - "detach": Close local connections but keep instance running

        Exit codes when triggered by signal:
        - 130: SIGINT (Ctrl+C)
        - 143: SIGTERM (kill command)
        - 1: Other signals
        """
        force_exit = False
        exit_code = None

        with self.cleanup_lock:
            if self.cleanup_in_progress:
                logging.info("Cleanup already in progress, please wait...")
                return
            self.cleanup_in_progress = True
            self.cleanup_event.set()

        try:
            if action == "stop":
                self.stop_instance_cleanup(signum=signum)
            elif action == "terminate":
                self.terminate_instance_cleanup(signum=signum)
            elif action == "detach":
                self.detach_cleanup(signum=signum)

        finally:
            with self.cleanup_lock:
                self.cleanup_in_progress = False

            if signum is not None:
                exit_code = (
                    130 if signum == signal.SIGINT else (143 if signum == signal.SIGTERM else 1)
                )
                if os.environ.get("CAMPERS_FORCE_SIGNAL_EXIT") == "1":
                    logging.info(
                        "Forced signal exit enabled; terminating with code %s",
                        exit_code,
                    )
                    force_exit = True
                else:
                    sys.exit(exit_code)

        if force_exit and exit_code is not None:
            sys.exit(exit_code)

    def cleanup_ssh_connections(self, resources: dict[str, Any], errors: list[Exception]) -> None:
        """Close SSH connections and abort any running commands.

        Parameters
        ----------
        resources : dict[str, Any]
            Resources dictionary containing ssh_manager
        errors : list[Exception]
            List to accumulate errors during cleanup

        Notes
        -----
        Errors are logged and added to errors list but do not halt cleanup.
        When running under test harness control, SSH connection closure is skipped
        to allow the harness to manage SSH lifecycle separately.
        """
        if "ssh_manager" not in resources:
            logging.debug("Skipping SSH cleanup - not initialized")
            return

        if os.environ.get("CAMPERS_HARNESS_MANAGED") == "1":
            logging.info("Skipping SSH connection closure - harness will manage SSH lifecycle")
            return

        resources["ssh_manager"].abort_active_command()

        logging.info("Closing SSH connection...")

        self._emit_cleanup_event("close_ssh", "in_progress")

        try:
            resources["ssh_manager"].close()
            logging.info("SSH connection closed successfully")

            self._emit_cleanup_event("close_ssh", "completed")
        except (OSError, paramiko.SSHException, ConnectionError, RuntimeError) as e:
            logging.error("Error closing SSH: %s", e)
            errors.append(e)

            self._emit_cleanup_event("close_ssh", "failed")

    def cleanup_session_file(self, resources: dict[str, Any], errors: list[Exception]) -> None:
        """Delete session file when campers run exits.

        Parameters
        ----------
        resources : dict[str, Any]
            Resources dictionary containing session_manager and session_camp_name
        errors : list[Exception]
            List to accumulate errors during cleanup

        Notes
        -----
        Errors are logged and added to errors list but do not halt cleanup.
        """
        if "session_manager" not in resources or "session_camp_name" not in resources:
            logging.debug("Skipping session file cleanup - not initialized")
            return

        logging.debug("Deleting session file...")

        try:
            resources["session_manager"].delete_session(resources["session_camp_name"])
            logging.debug("Session file deleted successfully")
        except (OSError, ValueError) as e:
            logging.error("Error deleting session file: %s", e)
            errors.append(e)

    def cleanup_port_forwarding(self, resources: dict[str, Any], errors: list[Exception]) -> None:
        """Stop SSH port forwarding tunnels.

        Parameters
        ----------
        resources : dict[str, Any]
            Resources dictionary containing portforward_mgr
        errors : list[Exception]
            List to accumulate errors during cleanup

        Notes
        -----
        Errors are logged and added to errors list but do not halt cleanup.
        When running under test harness control, port forwarding cleanup is skipped
        to allow the harness to manage tunnel lifecycle separately.
        """
        if "portforward_mgr" not in resources:
            logging.debug("Skipping port forwarding cleanup - not initialized")
            return

        if os.environ.get("CAMPERS_HARNESS_MANAGED") == "1":
            logging.info("Skipping port forwarding cleanup - harness will manage tunnel lifecycle")
            return

        logging.info("Stopping port forwarding...")

        self._emit_cleanup_event("stop_tunnels", "in_progress")

        try:
            resources["portforward_mgr"].stop_all_tunnels()
            logging.info("Port forwarding stopped successfully")

            self._emit_cleanup_event("stop_tunnels", "completed")
        except (OSError, RuntimeError, TimeoutError) as e:
            logging.error("Error stopping port forwarding: %s", e)
            errors.append(e)

            self._emit_cleanup_event("stop_tunnels", "failed")

    def cleanup_mutagen_session(self, resources: dict[str, Any], errors: list[Exception]) -> None:
        """Terminate Mutagen sync sessions.

        Parameters
        ----------
        resources : dict[str, Any]
            Resources dictionary containing mutagen_mgr and mutagen_session_names
        errors : list[Exception]
            List to accumulate errors during cleanup

        Notes
        -----
        Errors are logged and added to errors list but do not halt cleanup.
        """
        session_names = resources.get("mutagen_session_names")

        if not session_names:
            if "mutagen_session_name" not in resources:
                logging.debug("Skipping Mutagen cleanup - not initialized")
                return
            session_names = [resources["mutagen_session_name"]]

        logging.info("Stopping Mutagen sessions...")

        self._emit_cleanup_event("terminate_mutagen", "in_progress")

        campers_dir = os.environ.get("CAMPERS_DIR", str(Path.home() / ".campers"))
        instance_details = resources.get("instance_details")
        host = instance_details.get("public_ip") if instance_details else None

        cleanup_errors = []

        for session_name in session_names:
            try:
                resources["mutagen_mgr"].terminate_session(
                    session_name,
                    ssh_wrapper_dir=campers_dir,
                    host=host,
                )
                logging.info("Mutagen session %s stopped successfully", session_name)
            except (OSError, subprocess.SubprocessError, RuntimeError, TimeoutError) as e:
                logging.error("Error stopping Mutagen session %s: %s", session_name, e)
                errors.append(e)
                cleanup_errors.append(e)

        if not cleanup_errors:
            self._emit_cleanup_event("terminate_mutagen", "completed")
        else:
            self._emit_cleanup_event("terminate_mutagen", "failed")

    def _cleanup_instance_helper(
        self,
        resources_to_clean: dict[str, Any],
        errors: list[Exception],
        action: str,
    ) -> tuple[bool, str | None]:
        """Helper method for common cleanup logic between stop and terminate operations.

        Parameters
        ----------
        resources_to_clean : dict[str, Any]
            Dictionary of resources to clean up
        errors : list[Exception]
            List to accumulate errors during cleanup
        action : str
            Action to perform: 'stop' or 'terminate'

        Returns
        -------
        tuple[bool, str | None]
            Tuple of (success, error_message). success is True if cleanup succeeded,
            False otherwise. error_message is a string describing the error if any.

        Notes
        -----
        Handles extraction of instance_id with None checks and emits appropriate
        cleanup events. Common logic for both stop_instance_cleanup and
        terminate_instance_cleanup methods.
        """
        if "instance_details" not in resources_to_clean:
            if action == "stop":
                logging.debug("No instance to stop - launch may not have completed")
            else:
                logging.debug("No instance to terminate - launch may not have completed")
            return (True, None)

        instance_details = resources_to_clean["instance_details"]
        instance_id = get_instance_id(instance_details)

        if instance_id is None:
            error_msg = "instance_id is None"
            logging.warning("Cannot %s instance: %s", action, error_msg)
            return (False, error_msg)

        status_map = {"stop": "stopping", "terminate": "terminating"}
        event_action = f"{action}_instance"
        status_value = status_map.get(action, action)

        logging.info("Cleaning up cloud instance %s...", instance_id)

        if self.update_queue is not None:
            try:
                self.update_queue.put_nowait(
                    {"type": "status_update", "payload": {"status": status_value}}
                )
            except queue.Full:
                logging.warning("TUI update queue full, dropping status update")
            time.sleep(TUI_STATUS_UPDATE_PROCESSING_DELAY)

        self._emit_cleanup_event(event_action, "in_progress")

        try:
            compute_provider = resources_to_clean.get("compute_provider")
            if compute_provider:
                use_logging = self.update_queue is not None

                if action == "stop":
                    spinner_msg = f"Stopping instance {instance_id}"
                    with status_spinner(spinner_msg, use_logging=use_logging):
                        compute_provider.stop_instance(instance_id)
                    logging.info("Cloud instance stopped successfully")
                    volume_size = get_volume_size_or_default(compute_provider, instance_id)
                    storage_rate = self._get_storage_rate(compute_provider.region)
                    storage_cost = float(volume_size) * storage_rate

                    logging.info("\nInstance stopped successfully")
                    logging.info(f"  Instance ID: {instance_id}")
                    logging.info(f"  Estimated storage cost: ~${storage_cost:.2f}/month")
                    logging.info(f"  Restart with: campers start {instance_id}")
                else:
                    spinner_msg = f"Terminating instance {instance_id}"
                    with status_spinner(spinner_msg, use_logging=use_logging):
                        compute_provider.terminate_instance(instance_id)
                    logging.info("Cloud instance terminated successfully")

                self._emit_cleanup_event(event_action, "completed")
                return (True, None)
            else:
                error_msg = "compute_provider is None"
                logging.error("Error %sing instance: %s", action, error_msg)
                self._emit_cleanup_event(event_action, "failed")
                return (False, error_msg)
        except (ProviderAPIError, RuntimeError) as e:
            error_msg = str(e)
            logging.error("Error %sing instance: %s", action, e)
            errors.append(e)
            self._emit_cleanup_event(event_action, "failed")
            return (False, error_msg)

    def stop_instance_cleanup(self, signum: int | None = None) -> None:
        """Stop instance while preserving resources for later restart.

        Parameters
        ----------
        signum : int | None
            Signal number if triggered by signal handler (unused but kept for consistency)

        Notes
        -----
        Thread-safe, idempotent cleanup that preserves instance for restart.
        Cleanup order is critical:
        1. Port forwarding first (releases network resources)
        2. Mutagen session second (stops file synchronization)
        3. SSH connection third (closes remote connection)
        4. Cloud instance fourth (stops instance, preserving data)

        Handles partial initialization gracefully by checking resource existence
        before attempting cleanup. Individual component failures do not halt cleanup.
        """
        try:
            errors = []

            with self.cleanup_lock, self.resources_lock:
                self.cleanup_in_progress = True
                resources_to_clean = dict(self.resources)
                self.resources.clear()

            if not resources_to_clean:
                logging.info("No resources to clean up")
                return

            logging.info("Shutdown requested - stopping instance and preserving resources...")

            if "ssh_manager" in resources_to_clean:
                resources_to_clean["ssh_manager"].abort_active_command()

            self.cleanup_port_forwarding(resources_to_clean, errors)
            self.cleanup_mutagen_session(resources_to_clean, errors)
            self.cleanup_ssh_connections(resources_to_clean, errors)
            self.cleanup_session_file(resources_to_clean, errors)

            success, error_msg = self._cleanup_instance_helper(resources_to_clean, errors, "stop")
            if not success and error_msg:
                logging.warning("Instance cleanup failed: %s", error_msg)

            if errors:
                logging.info("Cleanup completed with %s errors", len(errors))
            else:
                logging.info("Cleanup completed successfully")

        except OSError as e:
            logging.error("Unexpected error during stop cleanup: %s", e)

    def terminate_instance_cleanup(self, signum: int | None = None) -> None:
        """Terminate instance and remove all associated resources.

        Parameters
        ----------
        signum : int | None
            Signal number if triggered by signal handler (unused but kept for consistency)

        Notes
        -----
        Thread-safe, idempotent cleanup that fully removes instance and all resources.
        Cleanup order is critical:
        1. Port forwarding first (releases network resources)
        2. Mutagen session second (stops file synchronization)
        3. SSH connection third (closes remote connection)
        4. Cloud instance fourth (terminates instance, removing all data)

        Handles partial initialization gracefully by checking resource existence
        before attempting cleanup. Individual component failures do not halt cleanup.
        """
        try:
            errors = []

            with self.cleanup_lock, self.resources_lock:
                self.cleanup_in_progress = True
                resources_to_clean = dict(self.resources)
                self.resources.clear()

            if not resources_to_clean:
                logging.info("No resources to clean up")
                return

            logging.info("Shutdown requested - beginning cleanup...")

            if "ssh_manager" in resources_to_clean:
                resources_to_clean["ssh_manager"].abort_active_command()

            self.cleanup_port_forwarding(resources_to_clean, errors)
            self.cleanup_mutagen_session(resources_to_clean, errors)
            self.cleanup_ssh_connections(resources_to_clean, errors)
            self.cleanup_session_file(resources_to_clean, errors)

            success, error_msg = self._cleanup_instance_helper(
                resources_to_clean, errors, "terminate"
            )
            if not success and error_msg:
                logging.warning("Instance cleanup failed: %s", error_msg)

            if errors:
                logging.info("Cleanup completed with %s errors", len(errors))
            else:
                logging.info("Cleanup completed successfully")

        except OSError as e:
            logging.error("Unexpected error during terminate cleanup: %s", e)

    def detach_cleanup(self, signum: int | None = None) -> None:
        """Detach from instance while keeping it running.

        Close local connections and resources but preserve the cloud instance
        for external access. Useful when maintaining instances for demo purposes.

        Parameters
        ----------
        signum : int | None
            Signal number if triggered by signal handler

        Notes
        -----
        Cleanup order for detach:
        1. Port forwarding (releases network resources)
        2. Mutagen session (stops file synchronization)
        3. SSH connection (closes remote connection)
        4. Cloud instance is NOT stopped or terminated

        Handles partial initialization gracefully by checking resource existence
        before attempting cleanup. Individual component failures do not halt cleanup.
        """
        try:
            errors = []

            with self.cleanup_lock, self.resources_lock:
                self.cleanup_in_progress = True
                resources_to_clean = dict(self.resources)
                self.resources.clear()

            if not resources_to_clean:
                logging.info("No resources to clean up")
                return

            logging.info("Detaching from instance (keeping it running)...")

            if "ssh_manager" in resources_to_clean:
                resources_to_clean["ssh_manager"].abort_active_command()

            self.cleanup_port_forwarding(resources_to_clean, errors)
            self.cleanup_mutagen_session(resources_to_clean, errors)
            self.cleanup_ssh_connections(resources_to_clean, errors)
            self.cleanup_session_file(resources_to_clean, errors)

            instance_details = resources_to_clean.get("instance_details", {})
            instance_id = get_instance_id(instance_details)
            public_ip = instance_details.get("public_ip")

            logging.info("\nDetached from instance (still running)")
            logging.info("  Instance ID: %s", instance_id)
            logging.info("  Public IP: %s", public_ip)

            public_ports = self.config_dict.get("public_ports", [])
            if public_ports and public_ip:
                logging.info("  Public access:")
                for port in public_ports:
                    protocol = "https" if port == 443 else "http"
                    logging.info("    %s://%s:%d", protocol, public_ip, port)

            logging.info("  To reconnect: campers run <camp>")
            logging.info("  To stop: campers stop %s", instance_id)
            logging.info("  To destroy: campers destroy %s", instance_id)

            if errors:
                logging.info("Detach completed with %s errors", len(errors))
            else:
                logging.info("Detach completed successfully")

        except OSError as e:
            logging.error("Unexpected error during detach: %s", e)
