from __future__ import annotations

import json
import logging
import os
import queue
import shlex
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from campers.cli import apply_cli_overrides
from campers.services.ansible import AnsibleManager
from campers.services.portforward import PortForwardManager
from campers.services.ssh import get_ssh_connection_info
from campers.services.sync import MutagenManager
from campers.utils import generate_instance_name

SYNC_TIMEOUT = 300


class RunExecutor:
    """Orchestrates the run command execution flow.

    Manages instance lifecycle, file synchronization, command execution, and resource cleanup.

    Parameters
    ----------
    config_loader : Any
        Configuration loader instance
    ec2_manager_factory : Any
        Factory function to create EC2Manager instances
    ssh_manager_factory : Any
        Factory function to create SSHManager instances
    resources : dict[str, Any]
        Shared resources dictionary
    resources_lock : threading.Lock
        Lock for thread-safe resource access
    cleanup_in_progress_getter : Any
        Callable that returns cleanup in progress status
    update_queue : queue.Queue | None
        Queue for TUI updates (optional)
    mutagen_manager_factory : Any
        Factory function to create MutagenManager instances (optional)
    portforward_manager_factory : Any
        Factory function to create PortForwardManager instances (optional)
    """

    def __init__(
        self,
        config_loader: Any,
        ec2_manager_factory: Any,
        ssh_manager_factory: Any,
        resources: dict[str, Any],
        resources_lock: threading.Lock,
        cleanup_in_progress_getter: Any,
        update_queue: queue.Queue | None = None,
        mutagen_manager_factory: Any | None = None,
        portforward_manager_factory: Any | None = None,
    ) -> None:
        self.config_loader = config_loader
        self.ec2_manager_factory = ec2_manager_factory
        self.ssh_manager_factory = ssh_manager_factory
        self.resources = resources
        self.resources_lock = resources_lock
        self.cleanup_in_progress_getter = cleanup_in_progress_getter
        self.update_queue = update_queue
        self.mutagen_manager_factory = mutagen_manager_factory or MutagenManager
        self.portforward_manager_factory = (
            portforward_manager_factory or PortForwardManager
        )

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
            EC2 instance type override
        disk_size : int | None
            Root disk size override
        region : str | None
            AWS region override
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
        if verbose:
            logging.getLogger().setLevel(logging.DEBUG)
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

        self._validate_sync_paths_config(merged_config.get("sync_paths"))

        disable_mutagen = os.environ.get("CAMPERS_DISABLE_MUTAGEN") == "1"

        if update_queue is not None:
            logging.debug("Sending merged_config to TUI queue")
            update_queue.put({"type": "merged_config", "payload": merged_config})

        self.update_queue = update_queue

        try:
            mutagen_mgr = self.mutagen_manager_factory()

            if merged_config.get("sync_paths") and not disable_mutagen:
                mutagen_mgr.check_mutagen_installed()

            ec2_manager = self.ec2_manager_factory(region=merged_config["region"])

            with self.resources_lock:
                self.resources["ec2_manager"] = ec2_manager

            instance_name = generate_instance_name()
            instance_details = self._get_or_create_instance(
                instance_name, merged_config
            )

            with self.resources_lock:
                self.resources["instance_details"] = instance_details

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
                    return json.dumps(
                        instance_details,
                        indent=2,
                        default=lambda obj: obj.isoformat()
                        if isinstance(obj, datetime)
                        else obj,
                    )

                return instance_details

            skip_ssh = os.environ.get("CAMPERS_SKIP_SSH_CONNECTION") == "1"
            if skip_ssh:
                with self.resources_lock:
                    self.resources["instance_details"] = instance_details

                while not self.cleanup_in_progress_getter():
                    time.sleep(0.1)

                return instance_details

            logging.info("Waiting for SSH to be ready...")

            ssh_host, ssh_port, ssh_key_file = get_ssh_connection_info(
                instance_details["instance_id"],
                instance_details["public_ip"],
                instance_details["key_file"],
            )

            ssh_manager = self.ssh_manager_factory(
                host=ssh_host,
                key_file=ssh_key_file,
                username=merged_config.get("ssh_username", "ubuntu"),
                port=ssh_port,
            )

            try:
                ssh_manager.connect(max_retries=10)
                logging.info("SSH connection established")
            except ConnectionError as e:
                error_msg = (
                    f"Failed to establish SSH connection after 10 attempts: {str(e)}"
                )
                logging.error(error_msg)
                raise

            if self.cleanup_in_progress_getter():
                logging.debug("Cleanup in progress, aborting further operations")
                return {}

            if update_queue is not None:
                update_queue.put(
                    {"type": "status_update", "payload": {"status": "running"}}
                )

            with self.resources_lock:
                self.resources["ssh_manager"] = ssh_manager

            env_vars = ssh_manager.filter_environment_variables(
                merged_config.get("env_filter")
            )

            logging.info(f"Forwarding {len(env_vars)} environment variables")

            sync_paths = merged_config.get("sync_paths")

            if sync_paths:
                mutagen_session_name = f"campers-{instance_details['unique_id']}"
                mutagen_mgr.cleanup_orphaned_session(mutagen_session_name)

                with self.resources_lock:
                    self.resources["mutagen_mgr"] = mutagen_mgr
                    self.resources["mutagen_session_name"] = mutagen_session_name
            else:
                if update_queue is not None:
                    update_queue.put(
                        {
                            "type": "mutagen_status",
                            "payload": {"state": "not_configured"},
                        }
                    )

            if sync_paths:
                if disable_mutagen:
                    logging.info(
                        "Mutagen disabled via CAMPERS_DISABLE_MUTAGEN=1; skipping sync setup."
                    )

                    if update_queue is not None:
                        update_queue.put(
                            {
                                "type": "mutagen_status",
                                "payload": {"state": "disabled"},
                            }
                        )
                else:
                    if self.cleanup_in_progress_getter():
                        logging.debug("Cleanup in progress, aborting Mutagen sync")
                        return {}

                    sync_config = sync_paths[0]

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

                    campers_dir = os.environ.get(
                        "CAMPERS_DIR", str(Path.home() / ".campers")
                    )

                    logging.debug(
                        "Creating Mutagen sync session: %s", mutagen_session_name
                    )

                    mutagen_mgr.create_sync_session(
                        session_name=mutagen_session_name,
                        local_path=sync_config["local"],
                        remote_path=sync_config["remote"],
                        host=ssh_host,
                        key_file=ssh_key_file,
                        username=merged_config.get("ssh_username", "ubuntu"),
                        ignore_patterns=merged_config.get("ignore"),
                        include_vcs=merged_config.get("include_vcs", False),
                        ssh_wrapper_dir=campers_dir,
                        ssh_port=ssh_port,
                    )

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

            playbook_refs = self._get_playbook_references(merged_config)
            if playbook_refs:
                if self.cleanup_in_progress_getter():
                    logging.debug("Cleanup in progress, aborting Ansible playbooks")
                    return {}

                full_config = self.config_loader.load_config()

                if "playbooks" not in full_config:
                    raise ValueError(
                        "ansible_playbook(s) specified but no 'playbooks' section in config"
                    )

                playbooks_config = full_config.get("playbooks", {})

                logging.info(f"Running Ansible playbook(s): {', '.join(playbook_refs)}")

                ansible_mgr = AnsibleManager()
                try:
                    ansible_mgr.execute_playbooks(
                        playbook_names=playbook_refs,
                        playbooks_config=playbooks_config,
                        instance_ip=instance_details["public_ip"],
                        ssh_key_file=instance_details["key_file"],
                        ssh_username=merged_config.get("ssh_username", "ubuntu"),
                        ssh_port=ssh_port if ssh_port else 22,
                    )
                    logging.info("Ansible playbook(s) completed successfully")
                except Exception as e:
                    logging.error(f"Ansible execution failed: {e}")
                    raise

            if merged_config.get("setup_script", "").strip():
                if self.cleanup_in_progress_getter():
                    logging.debug("Cleanup in progress, aborting setup_script")
                    return {}

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

            if merged_config.get("ports"):
                if self.cleanup_in_progress_getter():
                    logging.debug("Cleanup in progress, aborting port forwarding")
                    return {}

                portforward_mgr = self.portforward_manager_factory()

                with self.resources_lock:
                    self.resources["portforward_mgr"] = portforward_mgr

                try:
                    pf_host, pf_port, pf_key_file = get_ssh_connection_info(
                        instance_details["instance_id"],
                        instance_details["public_ip"],
                        instance_details["key_file"],
                    )

                    portforward_mgr.create_tunnels(
                        ports=merged_config["ports"],
                        host=pf_host,
                        key_file=pf_key_file,
                        username=merged_config.get("ssh_username", "ubuntu"),
                        ssh_port=pf_port,
                    )
                except RuntimeError as e:
                    logging.error("Port forwarding failed: %s", e)
                    with self.resources_lock:
                        self.resources.pop("portforward_mgr", None)
                    portforward_mgr = None

            if merged_config.get("startup_script"):
                if self.cleanup_in_progress_getter():
                    logging.debug("Cleanup in progress, aborting startup_script")
                    return {}

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
                if self.cleanup_in_progress_getter():
                    logging.debug("Cleanup in progress, aborting command execution")
                    return {}

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
                return json.dumps(
                    instance_details,
                    indent=2,
                    default=lambda obj: obj.isoformat()
                    if isinstance(obj, datetime)
                    else obj,
                )

            return instance_details

        finally:
            if not tui_mode and not self.cleanup_in_progress_getter():
                if cleanup_resources_callback:
                    cleanup_resources_callback()

    def _get_or_create_instance(
        self, instance_name: str, config: dict[str, Any]
    ) -> dict[str, Any]:
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
        ec2_manager = self.resources.get("ec2_manager")
        if not ec2_manager:
            raise RuntimeError("EC2 manager not initialized")

        matches = ec2_manager.find_instances_by_name_or_id(
            name_or_id=instance_name, region_filter=None
        )

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

            if state == "stopped":
                logging.info("Found stopped instance %s, starting...", instance_id)
                print("Found stopped instance for this branch, starting...")

                started_details = ec2_manager.start_instance(instance_id)
                new_ip = started_details.get("public_ip")
                print(f"Instance started. New IP: {new_ip}")

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

        logging.info("Creating new instance: %s", instance_name)
        print("Creating new instance...")

        instance_details = ec2_manager.launch_instance(
            config=config, instance_name=instance_name
        )
        instance_details["reused"] = False
        return instance_details

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
        if working_dir.startswith("~"):
            if " " in working_dir or any(
                c in working_dir for c in ["'", '"', "$", "`"]
            ):
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
