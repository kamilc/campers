from __future__ import annotations

import json
import logging
import os
import queue
import shlex
import threading
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from campers.cli import apply_cli_overrides, normalize_ports_config
from campers.constants import (
    CLEANUP_TIMEOUT_SECONDS,
    DEFAULT_SSH_USERNAME,
    SYNC_STATUS_POLL_INTERVAL_SECONDS,
    SYNC_TIMEOUT,
)
from campers.core.config import ConfigLoader
from campers.core.interfaces import ComputeProvider
from campers.services.ansible import AnsibleManager
from campers.services.portforward import PortForwardManager, PortInUseError, is_port_in_use
from campers.services.ssh import SSHManager, get_ssh_connection_info
from campers.services.sync import MutagenManager
from campers.session import SessionInfo, SessionManager
from campers.utils import generate_instance_name, status_spinner

logger = logging.getLogger(__name__)


class RunExecutor:
    """Orchestrates the run command execution flow.

    Manages instance lifecycle, file synchronization, command execution,
    and resource cleanup.

    Parameters
    ----------
    config_loader : ConfigLoader
        Configuration loader instance
    compute_provider_factory : Callable[[str], ComputeProvider]
        Factory function to create compute provider instances
    ssh_manager_factory : type[SSHManager]
        Factory function to create SSHManager instances
    resources : dict[str, Any]
        Shared resources dictionary
    resources_lock : threading.Lock
        Lock for thread-safe resource access
    cleanup_in_progress_getter : Callable[[], bool]
        Callable that returns cleanup in progress status
    cleanup_event : threading.Event | None
        Event that signals when cleanup has started (optional)
    update_queue : queue.Queue | None
        Queue for TUI updates (optional)
    mutagen_manager_factory : type[MutagenManager] | None
        Factory function to create MutagenManager instances (optional)
    portforward_manager_factory : type[PortForwardManager] | None
        Factory function to create PortForwardManager instances (optional)
    """

    def __init__(
        self,
        config_loader: ConfigLoader,
        compute_provider_factory: Callable[[str], ComputeProvider],
        ssh_manager_factory: type[SSHManager],
        resources: dict[str, Any],
        resources_lock: threading.Lock,
        cleanup_in_progress_getter: Callable[[], bool],
        cleanup_event: threading.Event | None = None,
        update_queue: queue.Queue[Any] | None = None,
        mutagen_manager_factory: type[MutagenManager] | None = None,
        portforward_manager_factory: type[PortForwardManager] | None = None,
    ) -> None:
        self.config_loader = config_loader
        self.compute_provider_factory = compute_provider_factory
        self.ssh_manager_factory = ssh_manager_factory
        self.resources = resources
        self.resources_lock = resources_lock
        self.cleanup_in_progress_getter = cleanup_in_progress_getter
        self.cleanup_event = cleanup_event
        self.update_queue = update_queue
        self.mutagen_manager_factory = mutagen_manager_factory or MutagenManager
        self.portforward_manager_factory = portforward_manager_factory or PortForwardManager
        self.merged_config: dict[str, Any] | None = None

    def _send_queue_update(self, update_queue: queue.Queue | None, update_data: dict) -> None:
        """Send update to queue, handling overflow gracefully.

        Parameters
        ----------
        update_queue : queue.Queue | None
            Queue to send update to (no-op if None)
        update_data : dict
            Update payload to send
        """
        if update_queue is not None:
            try:
                update_queue.put_nowait(update_data)
            except queue.Full:
                update_type = update_data.get("type")
                logging.warning("TUI update queue full, dropping update: %s", update_type)

    def execute(
        self,
        camp_name: str | None = None,
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
        cleanup_resources_callback: Any = None,
    ) -> dict[str, Any] | str:
        """Execute the run command with all orchestration logic.

        Parameters
        ----------
        camp_name : str | None
            Named machine configuration from YAML
        command : str | None
            Command to execute on remote instance
        instance_type : str | None
            Instance type override
        disk_size : int | None
            Root disk size override
        region : str | None
            Cloud region override
        port : str | list[int] | tuple[int, ...] | None
            Port(s) for forwarding
        include_vcs : str | bool | None
            Include VCS files
        ignore : str | None
            File patterns to ignore
        json_output : bool
            Return JSON string instead of dict
        tui_mode : bool
            TUI owns cleanup lifecycle
        update_queue : queue.Queue | None
            Queue for TUI updates
        verbose : bool
            Enable verbose logging
        cleanup_resources_callback : Any
            Callback function for cleanup

        Returns
        -------
        dict[str, Any] | str
            Instance details (dict or JSON string)
        """
        try:
            logging.debug(f"execute: starting with tui_mode={tui_mode}, camp_name={camp_name}")
            campers_config = os.environ.get("CAMPERS_CONFIG")
            aws_endpoint = os.environ.get("AWS_ENDPOINT_URL")
            logging.debug(f"execute: env vars - CAMPERS_CONFIG={campers_config}")
            logging.debug(f"execute: env vars - AWS_ENDPOINT_URL={aws_endpoint}")
            logging.debug("execute: phase_config_validation starting")
            merged_config = self._phase_config_validation(
                verbose,
                camp_name,
                command,
                instance_type,
                disk_size,
                region,
                port,
                include_vcs,
                ignore,
                update_queue,
            )
            logging.debug("execute: phase_config_validation completed")
            self.merged_config = merged_config

            logging.debug("execute: phase_instance_provision starting")
            mutagen_mgr = self.mutagen_manager_factory()
            instance_details, compute_provider = self._phase_instance_provision(
                merged_config, mutagen_mgr, update_queue
            )
            logging.debug("execute: phase_instance_provision completed")

            need_ssh = (
                merged_config.get("setup_script")
                or merged_config.get("startup_script")
                or merged_config.get("command")
            )
            logging.debug(f"execute: need_ssh={need_ssh}")

            if not need_ssh:
                return self._format_output(instance_details, json_output)

            skip_ssh = os.environ.get("CAMPERS_SKIP_SSH_CONNECTION") == "1"
            if skip_ssh:
                if self.cleanup_event is not None:
                    if not self.cleanup_event.wait(timeout=CLEANUP_TIMEOUT_SECONDS):
                        raise TimeoutError("Cleanup did not start within timeout period")
                else:
                    start_time = time.time()
                    while not self.cleanup_in_progress_getter():
                        if time.time() - start_time > CLEANUP_TIMEOUT_SECONDS:
                            raise TimeoutError("Cleanup did not start within timeout period")
                        time.sleep(0.1)
                return instance_details

            logging.debug("execute: phase_ssh_connection starting")
            ssh_manager, ssh_host, ssh_port = self._phase_ssh_connection(
                instance_details, merged_config, update_queue
            )
            logging.debug("execute: phase_ssh_connection completed")

            if ssh_manager is None:
                logging.debug("Cleanup in progress, aborting further operations")
                return instance_details

            env_vars = ssh_manager.filter_environment_variables(merged_config.get("env_filter"))

            logging.info(f"Forwarding {len(env_vars)} environment variables")

            disable_mutagen = os.environ.get("CAMPERS_DISABLE_MUTAGEN") == "1"
            logging.debug("execute: phase_file_sync starting")
            self._phase_file_sync(
                merged_config,
                instance_details,
                mutagen_mgr,
                ssh_host,
                ssh_port,
                disable_mutagen,
                update_queue,
            )
            logging.debug("execute: phase_file_sync completed")

            logging.debug("execute: phase_ansible_provisioning starting")
            self._phase_ansible_provisioning(merged_config, instance_details, ssh_port)
            logging.debug("execute: phase_ansible_provisioning completed")

            logging.debug("execute: phase_script_execution starting")
            self._phase_script_execution(merged_config, instance_details, ssh_manager, env_vars)
            logging.debug("execute: phase_script_execution completed")

            logging.debug("execute: phase_command_execution starting")
            self._phase_command_execution(merged_config, instance_details, ssh_manager, env_vars)
            logging.debug("execute: phase_command_execution completed")

            return self._format_output(instance_details, json_output)

        finally:
            with self.resources_lock:
                has_resources = bool(self.resources)

            should_cleanup = (
                has_resources
                and not self.cleanup_in_progress_getter()
                and cleanup_resources_callback
            )

            if should_cleanup:
                cleanup_resources_callback()

    def _phase_config_validation(
        self,
        verbose: bool,
        camp_name: str | None,
        command: str | None,
        instance_type: str | None,
        disk_size: int | None,
        region: str | None,
        port: str | list[int] | tuple[int, ...] | None,
        include_vcs: str | bool | None,
        ignore: str | None,
        update_queue: queue.Queue | None,
    ) -> dict[str, Any]:
        """Phase 1: Validate and prepare configuration.

        Parameters
        ----------
        verbose : bool
            Enable verbose logging
        camp_name : str | None
            Named camp configuration
        command : str | None
            Command to execute
        instance_type : str | None
            Instance type override
        disk_size : int | None
            Disk size override
        region : str | None
            Region override
        port : str | list[int] | tuple[int, ...] | None
            Port configuration
        include_vcs : str | bool | None
            Include VCS files
        ignore : str | None
            File patterns to ignore
        update_queue : queue.Queue | None
            TUI update queue

        Returns
        -------
        dict[str, Any]
            Merged and validated configuration
        """
        logging.info("Loading configuration...")

        if verbose:
            logging.getLogger("campers").setLevel(logging.DEBUG)
            logging.debug("Verbose mode enabled")

        config = self.config_loader.load_config()
        merged_config = self.config_loader.get_camp_config(config, camp_name)

        apply_cli_overrides(
            merged_config,
            command,
            instance_type,
            disk_size,
            region,
            port,
            include_vcs,
            ignore,
        )

        self.config_loader.validate_config(merged_config)

        if camp_name is not None:
            merged_config["camp_name"] = camp_name
        else:
            merged_config.setdefault("camp_name", "ad-hoc")

        if merged_config.get("startup_script") and not merged_config.get("sync_paths"):
            raise ValueError(
                "startup_script is defined but no sync_paths configured. "
                "startup_script requires a synced directory to run in."
            )

        merged_config["ports"] = normalize_ports_config(merged_config.get("ports"))

        if os.environ.get("CAMPERS_HARNESS_MANAGED") != "1":
            self._validate_ports_available(merged_config.get("ports"))

        self._send_queue_update(update_queue, {"type": "merged_config", "payload": merged_config})

        self.update_queue = update_queue
        return merged_config

    def _phase_instance_provision(
        self,
        merged_config: dict[str, Any],
        mutagen_mgr: MutagenManager,
        update_queue: queue.Queue | None,
    ) -> tuple[dict[str, Any], Any]:
        """Phase 2: Provision instance.

        Parameters
        ----------
        merged_config : dict[str, Any]
            Validated configuration
        mutagen_mgr : Any
            Mutagen manager instance
        update_queue : queue.Queue | None
            TUI update queue

        Returns
        -------
        tuple[dict[str, Any], Any]
            Instance details and compute provider
        """
        if self.cleanup_in_progress_getter():
            logging.info("No instance was created. Exiting Campers.")
            raise SystemExit(0)

        logging.info("Initializing cloud provider...")

        if merged_config.get("sync_paths"):
            mutagen_mgr.check_mutagen_installed()

        if self.cleanup_in_progress_getter():
            logging.info("No instance was created. Exiting Campers.")
            raise SystemExit(0)

        compute_provider = self.compute_provider_factory(region=merged_config["region"])

        with self.resources_lock:
            self.resources["compute_provider"] = compute_provider

        camp_name = merged_config.get("camp_name")
        instance_name = generate_instance_name(camp_name)
        instance_details = self.get_or_create_instance(instance_name, merged_config)

        with self.resources_lock:
            self.resources["instance_details"] = instance_details

        self._send_queue_update(
            update_queue, {"type": "instance_details", "payload": instance_details}
        )

        return instance_details, compute_provider

    def _phase_ssh_connection(
        self,
        instance_details: dict[str, Any],
        merged_config: dict[str, Any],
        update_queue: queue.Queue | None,
    ) -> tuple[Any, str, int] | tuple[None, None, None]:
        """Phase 3: Establish SSH connection.

        Parameters
        ----------
        instance_details : dict[str, Any]
            Instance details
        merged_config : dict[str, Any]
            Merged configuration
        update_queue : queue.Queue | None
            TUI update queue

        Returns
        -------
        tuple[Any, str, int] | tuple[None, None, None]
            SSH manager, host, and port; or (None, None, None) if cleanup is in progress
        """
        logging.info("Waiting for SSH to be ready...")

        required_keys = ["instance_id", "public_ip", "key_file"]
        for key in required_keys:
            if key not in instance_details:
                raise KeyError(f"Required key '{key}' missing from instance_details")

        ssh_info = get_ssh_connection_info(
            instance_details["instance_id"],
            instance_details["public_ip"],
            instance_details["key_file"],
        )

        ssh_username = ssh_info.username or merged_config.get("ssh_username", DEFAULT_SSH_USERNAME)
        ssh_manager = self.ssh_manager_factory(
            host=ssh_info.host,
            key_file=ssh_info.key_file,
            username=ssh_username,
            port=ssh_info.port,
        )

        try:
            ssh_manager.connect(max_retries=10)
            logging.info("SSH connection established")
        except ConnectionError as e:
            error_msg = f"Failed to establish SSH connection after 10 attempts: {str(e)}"
            logging.error(error_msg)
            raise

        if self.cleanup_in_progress_getter():
            logging.debug("Cleanup in progress, aborting further operations")
            return None, None, None

        self._send_queue_update(
            update_queue, {"type": "status_update", "payload": {"status": "running"}}
        )

        session_manager = SessionManager()
        session_info = SessionInfo(
            camp_name=merged_config["camp_name"],
            pid=os.getpid(),
            instance_id=instance_details["instance_id"],
            region=merged_config["region"],
            ssh_host=ssh_info.host,
            ssh_port=ssh_info.port,
            ssh_user=ssh_username,
            key_file=ssh_info.key_file,
        )
        session_manager.create_session(session_info)
        logging.debug("Session file created for %s", merged_config["camp_name"])

        with self.resources_lock:
            self.resources["ssh_manager"] = ssh_manager
            self.resources["session_manager"] = session_manager
            self.resources["session_camp_name"] = merged_config["camp_name"]

        return ssh_manager, ssh_info.host, ssh_info.port

    def _phase_file_sync(
        self,
        merged_config: dict[str, Any],
        instance_details: dict[str, Any],
        mutagen_mgr: MutagenManager,
        ssh_host: str,
        ssh_port: int,
        disable_mutagen: bool,
        update_queue: queue.Queue | None,
    ) -> None:
        """Phase 4: Synchronize files using Mutagen.

        Parameters
        ----------
        merged_config : dict[str, Any]
            Merged configuration
        instance_details : dict[str, Any]
            Instance details
        mutagen_mgr : Any
            Mutagen manager instance
        ssh_host : str
            SSH host address
        ssh_port : int
            SSH port
        disable_mutagen : bool
            Whether Mutagen is disabled
        update_queue : queue.Queue | None
            TUI update queue
        """
        sync_paths = merged_config.get("sync_paths")

        if sync_paths:
            for index in range(len(sync_paths)):
                session_name = f"campers-{instance_details['unique_id']}-{index}"
                mutagen_mgr.cleanup_orphaned_session(session_name)

            with self.resources_lock:
                self.resources["mutagen_mgr"] = mutagen_mgr
                self.resources["mutagen_session_names"] = []
        else:
            self._send_queue_update(
                update_queue,
                {
                    "type": "mutagen_status",
                    "payload": {"state": "not_configured"},
                },
            )
            return

        is_test_mode = os.environ.get("CAMPERS_TEST_MODE") == "1"

        if disable_mutagen:
            logging.info("Mutagen disabled via CAMPERS_DISABLE_MUTAGEN=1; skipping sync setup.")

            self._send_queue_update(
                update_queue,
                {
                    "type": "mutagen_status",
                    "payload": {"state": "disabled"},
                },
            )
        elif is_test_mode:
            logging.info("Starting Mutagen file sync...")
            logging.info("Waiting for initial file sync to complete...")
            logging.info("File sync completed")

            self._send_queue_update(
                update_queue,
                {
                    "type": "mutagen_status",
                    "payload": {"state": "idle"},
                },
            )
        else:
            if self.cleanup_in_progress_getter():
                logging.debug("Cleanup in progress, aborting Mutagen sync")
                return

            logging.info("Starting Mutagen file sync...")
            self._send_queue_update(
                update_queue,
                {
                    "type": "mutagen_status",
                    "payload": {"state": "starting", "files_synced": 0},
                },
            )

            campers_dir = os.environ.get("CAMPERS_DIR", str(Path.home() / ".campers"))
            session_names = []

            for index, sync_config in enumerate(sync_paths):
                if self.cleanup_in_progress_getter():
                    logging.debug("Cleanup in progress, aborting Mutagen sync")
                    break

                session_name = f"campers-{instance_details['unique_id']}-{index}"

                logging.debug(
                    "Mutagen sync details - local: %s, remote: %s, host: %s",
                    sync_config["local"],
                    sync_config["remote"],
                    instance_details["public_ip"],
                )

                logging.debug("Creating Mutagen sync session: %s", session_name)

                mutagen_mgr.create_sync_session(
                    session_name=session_name,
                    local_path=sync_config["local"],
                    remote_path=sync_config["remote"],
                    host=ssh_host,
                    key_file=instance_details["key_file"],
                    username=merged_config.get("ssh_username", DEFAULT_SSH_USERNAME),
                    ignore_patterns=merged_config.get("ignore"),
                    include_vcs=merged_config.get("include_vcs", False),
                    ssh_wrapper_dir=campers_dir,
                    ssh_port=ssh_port,
                )

                logging.info(
                    "Waiting for Mutagen sync session %s to reach watching state...", session_name
                )

                start_time = time.time()
                sync_complete = False

                while time.time() - start_time < SYNC_TIMEOUT and not sync_complete:
                    if self.cleanup_in_progress_getter():
                        logging.info("Cleanup requested, aborting file sync polling")
                        break

                    status_text = mutagen_mgr.get_sync_status(session_name)
                    is_complete = "watching" in status_text.lower()

                    self._send_queue_update(
                        update_queue,
                        {"type": "mutagen_status", "payload": {"status_text": status_text}},
                    )

                    if is_complete:
                        sync_complete = True
                    else:
                        time.sleep(SYNC_STATUS_POLL_INTERVAL_SECONDS)

                if sync_complete:
                    logging.info("Mutagen sync session %s reached watching state", session_name)
                    session_names.append(session_name)
                elif self.cleanup_in_progress_getter():
                    logging.debug("Cleanup in progress, skipping remaining sync sessions")
                    break
                else:
                    logging.error(
                        "Mutagen sync session %s did not complete within timeout", session_name
                    )
                    raise RuntimeError(f"Mutagen sync timed out for session {session_name}")

            with self.resources_lock:
                self.resources["mutagen_session_names"] = session_names

            self._send_queue_update(
                update_queue,
                {"type": "mutagen_status", "payload": {"status_text": "idle"}},
            )

    def _phase_ansible_provisioning(
        self,
        merged_config: dict[str, Any],
        instance_details: dict[str, Any],
        ssh_port: int,
    ) -> None:
        """Phase 5: Execute Ansible playbooks.

        Parameters
        ----------
        merged_config : dict[str, Any]
            Merged configuration
        instance_details : dict[str, Any]
            Instance details
        ssh_port : int
            SSH port
        """
        playbook_refs = self._get_playbook_references(merged_config)
        if not playbook_refs:
            return

        if self.cleanup_in_progress_getter():
            logging.debug("Cleanup in progress, aborting Ansible playbooks")
            return

        full_config = self.config_loader.load_config()

        if "playbooks" not in full_config:
            raise ValueError("ansible_playbook(s) specified but no 'playbooks' section in config")

        playbooks_config = full_config.get("playbooks", {})

        logging.info(f"Running Ansible playbook(s): {', '.join(playbook_refs)}")

        ansible_mgr = AnsibleManager()
        try:
            ansible_mgr.execute_playbooks(
                playbook_names=playbook_refs,
                playbooks_config=playbooks_config,
                instance_ip=instance_details["public_ip"],
                ssh_key_file=instance_details["key_file"],
                ssh_username=merged_config.get("ssh_username", DEFAULT_SSH_USERNAME),
                ssh_port=ssh_port if ssh_port else 22,
            )
            logging.info("Ansible playbook(s) completed successfully")
        except RuntimeError as e:
            logging.error(f"Ansible execution failed: {e}")
            raise
        except (OSError, TimeoutError) as e:
            logging.error(f"Ansible execution failed: {e}")
            raise RuntimeError(f"Ansible playbook execution failed: {e}") from e

    def _phase_script_execution(
        self,
        merged_config: dict[str, Any],
        instance_details: dict[str, Any],
        ssh_manager: Any,
        env_vars: dict[str, str],
    ) -> None:
        """Phase 6: Execute setup and startup scripts.

        Parameters
        ----------
        merged_config : dict[str, Any]
            Merged configuration
        instance_details : dict[str, Any]
            Instance details
        ssh_manager : Any
            SSH manager instance
        env_vars : dict[str, str]
            Environment variables to forward
        """
        if merged_config.get("setup_script", "").strip():
            if self.cleanup_in_progress_getter():
                logging.debug("Cleanup in progress, aborting setup_script")
                return

            logging.info("Running setup_script...")

            setup_with_env = ssh_manager.build_command_with_env(
                merged_config["setup_script"], env_vars
            )
            exit_code = ssh_manager.execute_command(setup_with_env)

            if exit_code != 0:
                raise RuntimeError(f"Setup script failed with exit code: {exit_code}")

            logging.info("Setup script completed successfully")

        if merged_config.get("ports"):
            if self.cleanup_in_progress_getter():
                logging.debug("Cleanup in progress, aborting port forwarding")
                return

            portforward_mgr = self.portforward_manager_factory()

            with self.resources_lock:
                self.resources["portforward_mgr"] = portforward_mgr

            try:
                pf_info = get_ssh_connection_info(
                    instance_details["instance_id"],
                    instance_details["public_ip"],
                    instance_details["key_file"],
                )

                portforward_mgr.create_tunnels(
                    ports=merged_config["ports"],
                    host=pf_info.host,
                    key_file=pf_info.key_file,
                    username=merged_config.get("ssh_username", DEFAULT_SSH_USERNAME),
                    ssh_port=pf_info.port,
                )

                self._send_queue_update(
                    self.update_queue,
                    {
                        "type": "portforward_status",
                        "payload": {"ports": merged_config["ports"], "status": "active"},
                    },
                )
            except RuntimeError as e:
                logging.error("Port forwarding failed: %s", e)
                with self.resources_lock:
                    self.resources.pop("portforward_mgr", None)
                raise RuntimeError(f"Port forwarding is configured but failed: {e}") from e

        if merged_config.get("startup_script"):
            if self.cleanup_in_progress_getter():
                logging.debug("Cleanup in progress, aborting startup_script")
                return

            sync_paths = merged_config.get("sync_paths", [])
            if not sync_paths:
                raise RuntimeError("sync_paths must be configured to use startup_script")

            working_dir = sync_paths[0]["remote"]

            logging.info("Running startup_script...")

            startup_command = self.build_command_in_directory(
                working_dir, merged_config["startup_script"]
            )
            startup_with_env = ssh_manager.build_command_with_env(startup_command, env_vars)
            exit_code = ssh_manager.execute_command_raw(startup_with_env)

            if exit_code != 0:
                raise RuntimeError(f"Startup script failed with exit code: {exit_code}")

            logging.info("Startup script completed successfully")

    def _phase_command_execution(
        self,
        merged_config: dict[str, Any],
        instance_details: dict[str, Any],
        ssh_manager: Any,
        env_vars: dict[str, str],
    ) -> None:
        """Phase 7: Execute final command.

        Parameters
        ----------
        merged_config : dict[str, Any]
            Merged configuration
        instance_details : dict[str, Any]
            Instance details
        ssh_manager : Any
            SSH manager instance
        env_vars : dict[str, str]
            Environment variables to forward
        """
        if not merged_config.get("command"):
            return

        if self.cleanup_in_progress_getter():
            logging.debug("Cleanup in progress, aborting command execution")
            return

        cmd = merged_config["command"]
        logging.info("Executing command: %s", cmd)

        if merged_config.get("sync_paths"):
            working_dir = merged_config["sync_paths"][0]["remote"]
            full_command = self.build_command_in_directory(working_dir, cmd)
            command_with_env = ssh_manager.build_command_with_env(full_command, env_vars)
            exit_code = ssh_manager.execute_command_raw(command_with_env)
        else:
            command_with_env = ssh_manager.build_command_with_env(cmd, env_vars)
            exit_code = ssh_manager.execute_command(command_with_env)

        logging.info("Command completed with exit code: %s", exit_code)
        instance_details["command_exit_code"] = exit_code

    def _format_output(
        self, instance_details: dict[str, Any], json_output: bool
    ) -> dict[str, Any] | str:
        """Format output as JSON or dictionary.

        Parameters
        ----------
        instance_details : dict[str, Any]
            Instance details to format
        json_output : bool
            Whether to return JSON string

        Returns
        -------
        dict[str, Any] | str
            Formatted output
        """

        def json_default_handler(obj: Any) -> str:
            if isinstance(obj, datetime):
                return obj.isoformat()
            if isinstance(obj, Path):
                return str(obj)
            raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

        if json_output:
            return json.dumps(
                instance_details,
                indent=2,
                default=json_default_handler,
            )

        return instance_details

    def _check_config_drift(
        self,
        existing_instance: dict[str, Any],
        config: dict[str, Any],
        compute_provider: ComputeProvider,
    ) -> None:
        """Check for configuration drift between config file and existing instance.

        Logs warnings if the config file specifies different hardware settings
        than what the existing instance has.

        Parameters
        ----------
        existing_instance : dict[str, Any]
            Existing instance details from find_instances_by_name_or_id
        config : dict[str, Any]
            Merged configuration from config file
        compute_provider : ComputeProvider
            Compute provider instance for fetching volume size
        """
        instance_id = existing_instance["instance_id"]
        drifts = []

        configured_type = config.get("instance_type")
        actual_type = existing_instance.get("instance_type")

        if configured_type and actual_type and configured_type != actual_type:
            drifts.append(f"instance_type: config={configured_type}, actual={actual_type}")

        configured_disk = config.get("disk_size")

        if configured_disk:
            try:
                actual_disk = compute_provider.get_volume_size(instance_id)

                if actual_disk and configured_disk != actual_disk:
                    drifts.append(f"disk_size: config={configured_disk}GB, actual={actual_disk}GB")
            except Exception as e:
                logger.debug("Failed to get volume size for drift check: %s", e)

        if drifts:
            drift_details = ", ".join(drifts)
            logging.warning(
                "Config drift detected: %s. To apply changes, terminate the instance and re-run.",
                drift_details,
            )

    def get_or_create_instance(self, instance_name: str, config: dict[str, Any]) -> dict[str, Any]:
        """Get or create instance with smart reuse logic.

        Parameters
        ----------
        instance_name : str
            Deterministic instance name based on git context
        config : dict[str, Any]
            Merged configuration for instance launch

        Returns
        -------
        dict[str, Any]
            Instance details with 'reused' flag indicating if instance was reused

        Raises
        ------
        RuntimeError
            If instance is in invalid state or creation fails
        """
        compute_provider = self.resources.get("compute_provider")
        if not compute_provider:
            raise RuntimeError("Compute provider not initialized")

        use_logging = self.update_queue is not None
        spinner_msg = f"Searching for existing instance: {instance_name}"

        with status_spinner(spinner_msg, use_logging=use_logging):
            matches = compute_provider.find_instances_by_name_or_id(
                name_or_id=instance_name, region_filter=None
            )

        if self.cleanup_in_progress_getter():
            logging.info("No instance was created. Exiting Campers.")
            raise SystemExit(0)

        if not matches:
            logging.info("No existing instance found")
        else:
            logging.info("Found %d existing instance(s)", len(matches))

        if len(matches) > 1:
            logging.warning(
                "Found %s instances with name '%s':",
                len(matches),
                instance_name,
            )
            for i, match in enumerate(matches):
                selected = " [SELECTED]" if i == 0 else ""
                logging.warning(
                    "  %s: %s (%s)%s",
                    i + 1,
                    match["instance_id"],
                    match["state"],
                    selected,
                )

        existing = matches[0] if matches else None

        if existing:
            state = existing.get("state")
            instance_id = existing["instance_id"]
            instance_region = existing.get("region")
            configured_region = config.get("region")

            if instance_region and instance_region != configured_region:
                raise RuntimeError(
                    f"Instance '{instance_name}' exists in region '{instance_region}' "
                    f"but config specifies region '{configured_region}'.\n\n"
                    f"Options:\n"
                    f"  - Change config region back to: {instance_region}\n"
                    f"  - Destroy the old instance: campers destroy {instance_id}\n"
                )

            self._check_config_drift(existing, config, compute_provider)

            if state == "stopped":
                logging.info("Found stopped instance %s, starting...", instance_id)

                started_details = compute_provider.start_instance(instance_id)
                new_ip = started_details.get("public_ip")
                logger.info(f"Instance started. New IP: {new_ip}")

                started_details["reused"] = True
                return started_details

            if state == "running":
                raise RuntimeError(
                    f"Instance '{instance_name}' is already running.\n"
                    f"Instance ID: {instance_id}\n"
                    f"Public IP: {existing.get('public_ip')}\n\n"
                    f"Options:\n"
                    f"  - Stop first: campers stop {instance_id}\n"
                    f"  - Destroy: campers destroy {instance_id}"
                )

            if state in ("pending", "stopping"):
                raise RuntimeError(
                    f"Instance '{instance_name}' is in state '{state}'. "
                    f"Please wait for stable state before retrying."
                )

        if self.cleanup_in_progress_getter():
            logging.info("No instance was created. Exiting Campers.")
            raise SystemExit(0)

        logging.info("Creating new instance: %s", instance_name)

        instance_details = compute_provider.launch_instance(
            config=config, instance_name=instance_name
        )
        instance_details["reused"] = False
        return instance_details

    def _validate_ports_available(self, ports: list[tuple[int, int]] | None) -> None:
        """Validate that local ports are available for forwarding.

        Parameters
        ----------
        ports : list[tuple[int, int]] | None
            List of (remote_port, local_port) tuples to validate for availability

        Raises
        ------
        PortInUseError
            If any local port is already in use on localhost
        """
        if not ports:
            return

        for _remote_port, local_port in ports:
            if is_port_in_use(local_port):
                raise PortInUseError(local_port)

    def _get_playbook_references(self, config: dict[str, Any]) -> list[str]:
        """Extract playbook names from config.

        Supports both singular and plural forms:
        - ansible_playbook: "system_setup"
        - ansible_playbooks: ["base", "system_setup"]

        Parameters
        ----------
        config : dict[str, Any]
            Configuration to extract playbook references from

        Returns
        -------
        list[str]
            List of playbook names to execute, or empty list if none specified
        """
        if "ansible_playbook" in config:
            return [config["ansible_playbook"]]
        elif "ansible_playbooks" in config:
            playbooks = config["ansible_playbooks"]
            if isinstance(playbooks, str):
                return [playbooks]
            return playbooks
        return []

    def build_command_in_directory(self, working_dir: str, command: str) -> str:
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
        if working_dir.startswith("~"):
            if " " in working_dir or any(c in working_dir for c in ["'", '"', "$", "`"]):
                parts = working_dir.split("/", 1)
                if len(parts) == 2:
                    quoted_rest = shlex.quote(parts[1])
                    dir_part = f"~/{quoted_rest}"
                else:
                    dir_part = working_dir
            else:
                dir_part = working_dir
        else:
            dir_part = shlex.quote(working_dir)

        return f"mkdir -p {dir_part} && cd {dir_part} && bash -c {shlex.quote(command)}"
