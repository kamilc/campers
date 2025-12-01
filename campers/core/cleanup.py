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
        Configuration dictionary containing on_exit setting (optional)
    pricing_provider : PricingProvider | None
        Pricing service for getting storage rates (optional)
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
            self.update_queue.put(
                {
                    "type": "cleanup_event",
                    "payload": {"step": step, "status": status},
                }
            )

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
        self, signum: int | None = None, _frame: types.FrameType | None = None
    ) -> None:
        """Perform graceful cleanup of all resources.

        Parameters
        ----------
        signum : int | None
            Signal number if triggered by signal handler (e.g., signal.SIGINT)
        _frame : types.FrameType | None
            Current stack frame (unused but required by signal handler signature).
            Python's signal.signal() requires handlers to accept (signum, frame).

        Notes
        -----
        Routes cleanup based on on_exit configuration:
        - on_exit="stop": Preserves instance and resources for restart
        - on_exit="terminate": Removes all resources (full cleanup)

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

        try:
            on_exit_action = self.config_dict.get("on_exit", "stop")

            if on_exit_action == "stop":
                self.stop_instance_cleanup(signum=signum)
            else:
                self.terminate_instance_cleanup(signum=signum)

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
        """Terminate Mutagen sync session.

        Parameters
        ----------
        resources : dict[str, Any]
            Resources dictionary containing mutagen_mgr and mutagen_session_name
        errors : list[Exception]
            List to accumulate errors during cleanup

        Notes
        -----
        Errors are logged and added to errors list but do not halt cleanup.
        """
        if "mutagen_session_name" not in resources:
            logging.debug("Skipping Mutagen cleanup - not initialized")
            return

        logging.info("Stopping Mutagen session...")

        self._emit_cleanup_event("terminate_mutagen", "in_progress")

        try:
            campers_dir = os.environ.get("CAMPERS_DIR", str(Path.home() / ".campers"))
            instance_details = resources.get("instance_details")
            host = instance_details.get("public_ip") if instance_details else None
            resources["mutagen_mgr"].terminate_session(
                resources["mutagen_session_name"],
                ssh_wrapper_dir=campers_dir,
                host=host,
            )
            logging.info("Mutagen session stopped successfully")

            self._emit_cleanup_event("terminate_mutagen", "completed")
        except (OSError, subprocess.SubprocessError, RuntimeError, TimeoutError) as e:
            logging.error("Error stopping Mutagen session: %s", e)
            errors.append(e)

            self._emit_cleanup_event("terminate_mutagen", "failed")

    def _cleanup_instance_helper(
        self,
        resources_to_clean: dict[str, Any],
        errors: list[Exception],
        action: str,
    ) -> None:
        """Helper method for common cleanup logic between stop and terminate operations.

        Parameters
        ----------
        resources_to_clean : dict[str, Any]
            Dictionary of resources to clean up
        errors : list[Exception]
            List to accumulate errors during cleanup
        action : str
            Action to perform: 'stop' or 'terminate'

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
            return

        instance_details = resources_to_clean["instance_details"]
        instance_id = get_instance_id(instance_details)

        if instance_id is None:
            logging.warning("Cannot %s instance: instance_id is None", action)
            return

        status_map = {"stop": "stopping", "terminate": "terminating"}
        event_action = f"{action}_instance"
        status_value = status_map.get(action, action)

        logging.info("Cleaning up cloud instance %s...", instance_id)

        if self.update_queue is not None:
            self.update_queue.put({"type": "status_update", "payload": {"status": status_value}})
            time.sleep(TUI_STATUS_UPDATE_PROCESSING_DELAY)

        self._emit_cleanup_event(event_action, "in_progress")

        try:
            compute_provider = resources_to_clean.get("compute_provider")
            if compute_provider:
                if action == "stop":
                    compute_provider.stop_instance(instance_id)
                    logging.info("Cloud instance stopped successfully")
                    volume_size = get_volume_size_or_default(compute_provider, instance_id)
                    storage_rate = self._get_storage_rate(compute_provider.region)
                    storage_cost = float(volume_size) * storage_rate

                    print("\nInstance stopped successfully")
                    print(f"  Instance ID: {instance_id}")
                    print(f"  Estimated storage cost: ~${storage_cost:.2f}/month")
                    print(f"  Restart with: campers start {instance_id}")
                else:
                    compute_provider.terminate_instance(instance_id)
                    logging.info("Cloud instance terminated successfully")

                self._emit_cleanup_event(event_action, "completed")
        except (ProviderAPIError, RuntimeError) as e:
            logging.error("Error %sing instance: %s", action, e)
            errors.append(e)
            self._emit_cleanup_event(event_action, "failed")

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

            with self.resources_lock:
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

            self._cleanup_instance_helper(resources_to_clean, errors, "stop")

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

            with self.resources_lock:
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

            self._cleanup_instance_helper(resources_to_clean, errors, "terminate")

            if errors:
                logging.info("Cleanup completed with %s errors", len(errors))
            else:
                logging.info("Cleanup completed successfully")

        except OSError as e:
            logging.error("Unexpected error during terminate cleanup: %s", e)
