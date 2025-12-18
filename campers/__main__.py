#!/usr/bin/env python3
"""Campers - cloud remote development tool."""

from __future__ import annotations

import logging
import os
import queue
import sys
import threading
import types
from collections.abc import Callable
from pathlib import Path
from typing import Any

from campers.cli.main import main  # noqa: E402
from campers.constants import DEFAULT_PROVIDER, UPDATE_QUEUE_MAX_SIZE
from campers.core.cleanup import CleanupManager
from campers.core.config import ConfigLoader  # noqa: E402
from campers.core.interfaces import ComputeProvider
from campers.core.run_executor import RunExecutor
from campers.core.signals import SignalManager
from campers.lifecycle import LifecycleManager
from campers.providers import get_provider  # noqa: E402
from campers.services.portforward import PortForwardManager  # noqa: E402
from campers.services.ssh import (  # noqa: E402
    SSHConnectionInfo,
    SSHManager,
    get_ssh_connection_info,
)
from campers.services.sync import MutagenManager  # noqa: E402
from campers.session import SessionManager  # noqa: E402
from campers.templates import CONFIG_TEMPLATE  # noqa: E402
from campers.tui import CampersTUI  # noqa: E402
from campers.utils import get_user_identity, truncate_name  # noqa: E402


class Campers:
    """Main CLI interface for campers."""

    def __init__(
        self,
        compute_provider_factory: Callable[[str], ComputeProvider] | None = None,
        ssh_manager_factory: type[SSHManager] | None = None,
    ) -> None:
        """Initialize Campers CLI with optional dependency injection."""
        self._config_loader = ConfigLoader()
        self._cleanup_lock = threading.Lock()
        self._resources_lock = threading.Lock()
        self._cleanup_in_progress = False
        self._abort_requested = False
        self._resources: dict[str, Any] = {}
        self._update_queue: queue.Queue | None = None

        self._compute_provider_factory_override = compute_provider_factory

        self._ssh_manager_factory = ssh_manager_factory or SSHManager

        self._cleanup_manager = CleanupManager(
            resources_dict=self._resources,
            resources_lock=self._resources_lock,
            cleanup_lock=self._cleanup_lock,
            update_queue=self._update_queue,
            config_dict={},
        )

        self._mutagen_manager_factory = MutagenManager
        self._portforward_manager_factory = PortForwardManager

        self._lifecycle_manager: LifecycleManager | None = None

        self._run_executor: RunExecutor | None = None
        self._setup_manager_cache: object | None = None

        self._signal_manager = SignalManager(self)
        if not self._is_test_environment():
            self._signal_manager.register()

    def _is_test_environment(self) -> bool:
        """Check if running in a test environment.

        Returns
        -------
        bool
            True if running under pytest or in test mode, False otherwise
        """
        return "pytest" in sys.modules or os.environ.get("CAMPERS_TEST_MODE") == "1"

    @property
    def _compute_provider_factory(self) -> Callable[[str], ComputeProvider]:
        """Get the compute provider factory."""
        if self._compute_provider_factory_override is not None:
            return self._compute_provider_factory_override
        return self._create_compute_provider

    def _create_compute_provider(self, region: str) -> ComputeProvider:
        """Create a compute provider instance based on configured provider."""
        provider = get_provider("aws")
        compute_class = provider["compute"]
        return compute_class(
            region=region,
        )

    @property
    def _cleanup_in_progress_prop(self) -> bool:
        """Get cleanup in progress status.

        Returns True if cleanup is in progress OR if abort was requested
        (e.g., user pressed Ctrl+C and is viewing the exit modal).
        """
        return self._cleanup_in_progress or self._abort_requested

    @property
    def _run_executor_prop(self) -> RunExecutor:
        """Get the run executor instance."""
        if self._run_executor is None:
            self._run_executor = RunExecutor(
                config_loader=self._config_loader,
                compute_provider_factory=self._compute_provider_factory,
                ssh_manager_factory=self._ssh_manager_factory,
                resources=self._resources,
                resources_lock=self._resources_lock,
                cleanup_in_progress_getter=lambda: self._cleanup_in_progress_prop,
                cleanup_event=self._cleanup_manager.cleanup_event,
                update_queue=self._update_queue,
                mutagen_manager_factory=self._mutagen_manager_factory,
                portforward_manager_factory=self._portforward_manager_factory,
            )
        return self._run_executor

    @property
    def _lifecycle_manager_prop(self) -> LifecycleManager:
        """Get the lifecycle manager instance."""
        if self._lifecycle_manager is None:
            self._lifecycle_manager = LifecycleManager(
                config_loader=self._config_loader,
                compute_provider_factory=self._compute_provider_factory,
                truncate_name=truncate_name,
            )
        return self._lifecycle_manager

    @property
    def _merged_config_prop(self) -> dict[str, Any] | None:
        """Get the merged configuration from the run executor."""
        if self._run_executor is None:
            return None
        return self._run_executor.merged_config

    @_merged_config_prop.setter
    def _merged_config_prop(self, value: dict[str, Any] | None) -> None:
        """Set the merged configuration on the run executor."""
        if self._run_executor is None:
            self._run_executor = RunExecutor(
                config_loader=self._config_loader,
                compute_provider_factory=self._compute_provider_factory,
                ssh_manager_factory=self._ssh_manager_factory,
                resources=self._resources,
                resources_lock=self._resources_lock,
                cleanup_in_progress_getter=lambda: self._cleanup_in_progress_prop,
                cleanup_event=self._cleanup_manager.cleanup_event,
                update_queue=self._update_queue,
                mutagen_manager_factory=self._mutagen_manager_factory,
                portforward_manager_factory=self._portforward_manager_factory,
            )
        self._run_executor.merged_config = value

    @property
    def _setup_manager_prop(self) -> object:
        """Get the setup manager instance (lazy-loaded from provider).

        Returns
        -------
        object
            The cloud setup manager instance for the configured provider

        Notes
        -----
        Uses the DEFAULT_PROVIDER constant to load the appropriate setup manager
        from the provider-specific module. Caches the instance for subsequent accesses.
        """
        if self._setup_manager_cache is None:
            provider = get_provider(DEFAULT_PROVIDER)
            setup_getter = provider["setup"]
            setup_class = setup_getter() if callable(setup_getter) else setup_getter
            self._setup_manager_cache = setup_class(
                config_loader=self._config_loader,
            )
        return self._setup_manager_cache

    def run(
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
        plain: bool = False,
        verbose: bool = False,
    ) -> dict[str, Any] | str:
        """Launch cloud instance with file sync and command execution."""
        is_tty = sys.stdout.isatty()
        use_tui = is_tty and not (plain or json_output)

        if use_tui:
            run_kwargs = {
                "camp_name": camp_name,
                "command": command,
                "instance_type": instance_type,
                "disk_size": disk_size,
                "region": region,
                "port": port,
                "include_vcs": include_vcs,
                "ignore": ignore,
                "json_output": json_output,
            }
            update_queue: queue.Queue = queue.Queue(maxsize=UPDATE_QUEUE_MAX_SIZE)
            app = CampersTUI(
                campers_instance=self, run_kwargs=run_kwargs, update_queue=update_queue
            )

            exit_code = app.run()

            has_instance = bool(self._resources.get("instance_details", {}).get("instance_id"))

            if exit_code == 130 and self._abort_requested and has_instance:
                sys.stderr.write("Stopping instance, please wait...\n")
                sys.stderr.flush()

            if app.fatal_error_message:
                sys.stderr.write(f"\nError: {app.fatal_error_message}\n")
                sys.stderr.flush()

            return {
                "exit_code": exit_code if exit_code is not None else 0,
                "tui_mode": True,
                "message": "TUI session completed",
            }

        return self._execute_run(
            camp_name=camp_name,
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
    ) -> dict[str, Any] | str:
        return self._run_executor_prop.execute(
            camp_name=camp_name,
            command=command,
            instance_type=instance_type,
            disk_size=disk_size,
            region=region,
            port=port,
            include_vcs=include_vcs,
            ignore=ignore,
            json_output=json_output,
            tui_mode=tui_mode,
            update_queue=update_queue,
            verbose=verbose,
            cleanup_resources_callback=self._cleanup_resources,
        )

    def _get_or_create_instance(self, instance_name: str, config: dict[str, Any]) -> dict[str, Any]:
        """Get an existing instance or create a new one if it doesn't exist.

        Parameters
        ----------
        instance_name : str
            Name of the instance to get or create
        config : dict[str, Any]
            Configuration dictionary for instance creation if needed

        Returns
        -------
        dict[str, Any]
            Instance details including ID, IP address, and metadata
        """
        return self._run_executor_prop.get_or_create_instance(instance_name, config)

    def _sync_cleanup_manager_resources(self) -> None:
        """Ensure cleanup manager uses the current resources dictionary.

        Acquires locks in correct order (cleanup_lock before resources_lock)
        to prevent deadlocks and ensure atomicity when updating the reference.
        """
        with self._cleanup_lock, self._resources_lock:
            if self._cleanup_manager.resources is not self._resources:
                self._cleanup_manager.resources = self._resources

    def _stop_instance_cleanup(self, signum: int | None = None) -> None:
        self._sync_cleanup_manager_resources()
        return self._cleanup_manager.stop_instance_cleanup(signum=signum)

    def _terminate_instance_cleanup(self, signum: int | None = None) -> None:
        self._sync_cleanup_manager_resources()
        return self._cleanup_manager.terminate_instance_cleanup(signum=signum)

    def _cleanup_resources(
        self, action: str = "stop", signum: int | None = None, frame: types.FrameType | None = None
    ) -> None:
        """Clean up resources with specified action.

        Parameters
        ----------
        action : str
            Cleanup action: "stop", "terminate", or "detach"
        signum : int | None
            Signal number if triggered by signal handler
        frame : types.FrameType | None
            Stack frame (required by signal handler signature)
        """
        merged_config = None
        if self._run_executor is not None:
            merged_config = self._run_executor.merged_config
        if merged_config:
            self._cleanup_manager.config_dict = merged_config

        self._sync_cleanup_manager_resources()

        with self._cleanup_lock:
            self._cleanup_manager.cleanup_in_progress = self._cleanup_in_progress

        if signum is not None and action == "stop":
            action = "terminate"

        try:
            return self._cleanup_manager.cleanup_resources(
                action=action, signum=signum, _frame=frame
            )
        finally:
            with self._cleanup_lock:
                self._cleanup_in_progress = self._cleanup_manager.cleanup_in_progress

    def _detach_resources(
        self, signum: int | None = None, frame: types.FrameType | None = None
    ) -> None:
        """Detach from instance while keeping it running.

        Parameters
        ----------
        signum : int | None
            Signal number if triggered by signal handler
        frame : types.FrameType | None
            Stack frame (required by signal handler signature)
        """
        return self._cleanup_resources(action="detach", signum=signum, frame=frame)

    def _prompt_exit_action(self) -> str:
        """Prompt user for exit action in plain mode.

        Returns
        -------
        str
            One of: "stop", "detach", "destroy"
        """
        logging.info("\nWhat would you like to do?")
        logging.info("  [s] Stop instance (resume later)")
        logging.info("  [k] Keep running (for client access)")
        logging.info("  [d] Destroy (terminate and delete)")
        logging.info("")

        while True:
            try:
                choice = input("Choice [s/k/d]: ").strip().lower()
                if choice in ("s", "stop"):
                    return "stop"
                elif choice in ("k", "keep", "detach"):
                    return "detach"
                elif choice in ("d", "destroy", "terminate"):
                    return "destroy"
                else:
                    logging.info("Invalid choice. Please enter s, k, or d.")
            except (EOFError, KeyboardInterrupt):
                return "stop"

    def _build_command_in_directory(self, working_dir: str, command: str) -> str:
        """Build a command that executes in the specified working directory.

        Parameters
        ----------
        working_dir : str
            The remote working directory path
        command : str
            The command to execute

        Returns
        -------
        str
            The complete command with directory change prefix
        """
        return self._run_executor_prop.build_command_in_directory(working_dir, command)

    def _truncate_name(self, name: str) -> str:
        """Truncate instance name to maximum allowed length.

        Parameters
        ----------
        name : str
            The instance name to truncate

        Returns
        -------
        str
            The truncated instance name
        """
        return truncate_name(name)

    def _validate_region(self, region: str) -> None:
        """Validate that the provided region is valid for the compute provider.

        Parameters
        ----------
        region : str
            The cloud region identifier to validate

        Raises
        ------
        ProviderError
            If the region is not valid for the provider
        """
        compute_provider = self._compute_provider_factory(region)
        compute_provider.validate_region(region)

    def list(self, region: str | None = None, show_all: bool = False) -> None:
        """List all managed instances."""
        return self._lifecycle_manager_prop.list(region=region, show_all=show_all)

    def stop(self, name_or_id: str, region: str | None = None) -> None:
        """Stop a managed instance."""
        return self._lifecycle_manager_prop.stop(name_or_id=name_or_id, region=region)

    def start(self, name_or_id: str, region: str | None = None) -> None:
        """Start a managed instance."""
        return self._lifecycle_manager_prop.start(name_or_id=name_or_id, region=region)

    def info(self, name_or_id: str, region: str | None = None) -> None:
        """Get information about a managed instance."""
        return self._lifecycle_manager_prop.info(name_or_id=name_or_id, region=region)

    def destroy(self, name_or_id: str, region: str | None = None) -> None:
        """Destroy a managed instance."""
        return self._lifecycle_manager_prop.destroy(name_or_id=name_or_id, region=region)

    def exec(
        self,
        camp_or_instance: str,
        command: str,
        region: str | None = None,
        i: bool = False,
        t: bool = False,
        it: bool = False,
        interactive: bool = False,
        tty: bool = False,
    ) -> int:
        """Execute a command on a running instance.

        Parameters
        ----------
        camp_or_instance : str
            Camp name or instance ID to execute on
        command : str
            Command to execute on the remote instance
        region : str | None
            Optional region to narrow AWS discovery scope
        i : bool
            Short flag for interactive mode (keep stdin open)
        t : bool
            Short flag for TTY allocation
        it : bool
            Combined short flag for interactive mode with TTY (like docker exec -it)
        interactive : bool
            Long flag for interactive mode (keep stdin open)
        tty : bool
            Long flag for TTY allocation

        Returns
        -------
        int
            Exit code from the remote command

        Raises
        ------
        SystemExit
            Exits with code 1 if instance not found, multiple instances found,
            instance is not in running state, or TTY requirements not met
        """
        use_interactive = i or it or interactive
        use_tty = t or it or tty

        if use_interactive and not sys.stdin.isatty():
            logging.error(
                "Cannot use interactive mode: stdin is not a terminal",
                extra={"stream": "stderr"},
            )
            sys.exit(1)

        if use_tty and not sys.stdout.isatty():
            logging.error(
                "Cannot allocate TTY: stdout is not a terminal",
                extra={"stream": "stderr"},
            )
            sys.exit(1)

        if use_interactive and not use_tty:
            logging.warning(
                "Using -i without -t has no effect; use -it for interactive mode",
                extra={"stream": "stderr"},
            )

        default_region = self._config_loader.BUILT_IN_DEFAULTS["region"]

        if region is not None:
            self._validate_region(region)

        session_manager = SessionManager()

        session = session_manager.get_alive_session(camp_or_instance)

        if session:
            ssh_info = SSHConnectionInfo(
                host=session.ssh_host,
                port=session.ssh_port,
                key_file=session.key_file,
                username=session.ssh_user,
            )
        else:
            instance = self._discover_running_instance(camp_or_instance, region, default_region)
            ssh_info = get_ssh_connection_info(
                instance["instance_id"],
                instance["public_ip"],
                instance["key_file"],
            )

        ssh_manager = self._ssh_manager_factory(
            host=ssh_info.host,
            key_file=ssh_info.key_file,
            port=ssh_info.port,
            username=ssh_info.username,
        )
        ssh_manager.connect()

        try:
            if use_tty:
                return ssh_manager.execute_interactive(command)
            else:
                return ssh_manager.execute_command(command)
        finally:
            ssh_manager.close()

    def _discover_running_instance(
        self, camp_or_instance: str, region: str | None, default_region: str
    ) -> dict[str, Any]:
        """Discover a running instance by name or ID.

        Parameters
        ----------
        camp_or_instance : str
            Camp name or instance ID
        region : str | None
            Optional region to narrow search
        default_region : str
            Default region to use if not specified

        Returns
        -------
        dict[str, Any]
            Instance details if found and unique

        Raises
        ------
        SystemExit
            Exits with code 1 if no instance found, multiple found, or not running
        """
        compute_provider = self._compute_provider_factory(region=region or default_region)
        matches = compute_provider.find_instances_by_name_or_id(
            name_or_id=camp_or_instance, region_filter=region
        )

        if not matches:
            logging.error(
                "No running instance found for '%s'. Use 'campers run' to start one.",
                camp_or_instance,
                extra={"stream": "stderr"},
            )
            sys.exit(1)

        if len(matches) > 1:
            logging.error(
                "Multiple instances found for '%s':",
                camp_or_instance,
                extra={"stream": "stderr"},
            )
            for match in matches:
                logging.error(
                    f"  {match['instance_id']} ({match['region']}) "
                    f"- {match.get('state', 'unknown')}",
                    extra={"stream": "stderr"},
                )
            logging.error(
                "Specify instance ID: campers exec %s <command>",
                matches[0]["instance_id"],
                extra={"stream": "stderr"},
            )
            sys.exit(1)

        instance = matches[0]

        if not camp_or_instance.startswith("i-"):
            current_user = get_user_identity()
            if instance.get("owner") != current_user:
                logging.error(
                    "Instance '%s' is owned by '%s', not by you ('%s'). "
                    "Use instance ID to access instances from other users.",
                    camp_or_instance,
                    instance.get("owner"),
                    current_user,
                    extra={"stream": "stderr"},
                )
                sys.exit(1)

        if instance.get("state") != "running":
            logging.error(
                "Instance '%s' is %s. Use 'campers start' first.",
                camp_or_instance,
                instance.get("state", "unknown"),
                extra={"stream": "stderr"},
            )
            sys.exit(1)

        return instance

    def setup(self, region: str | None = None) -> None:
        """Set up cloud environment and validate configuration."""
        return self._setup_manager_prop.setup(region=region)

    def doctor(self, region: str | None = None) -> None:
        """Diagnose cloud environment and configuration issues.

        Parameters
        ----------
        region : str | None
            Cloud region to diagnose, or None for default region
        """
        return self._setup_manager_prop.doctor(region=region)

    def init(self, force: bool = False) -> None:
        """Create a default campers.yaml configuration file."""
        config_path = os.environ.get("CAMPERS_CONFIG", "campers.yaml")
        config_file = Path(config_path)

        if config_file.exists() and not force:
            logging.error(
                "%s already exists. Use --force to overwrite.",
                config_path,
                extra={"stream": "stderr"},
            )
            sys.exit(1)

        config_file.parent.mkdir(parents=True, exist_ok=True)

        with open(config_file, "w") as f:
            f.write(CONFIG_TEMPLATE)

        logging.info(f"Created {config_path} configuration file.", extra={"stream": "stdout"})

    def validate(self, camp_name: str | None = None) -> None:
        """Validate configuration file without running.

        Parameters
        ----------
        camp_name : str | None
            Optional camp name to validate specific camp configuration.
            If not provided, validates all camps in the config.
        """
        try:
            raw_config = self._config_loader.load_config()
        except FileNotFoundError as e:
            logging.error(str(e), extra={"stream": "stderr"})
            sys.exit(1)

        camps = raw_config.get("camps", {})

        if camp_name:
            if camp_name not in camps:
                available = list(camps.keys()) if camps else []
                logging.error(
                    f"Camp '{camp_name}' not found. Available camps: {available}",
                    extra={"stream": "stderr"},
                )
                sys.exit(1)
            camps_to_validate = [camp_name]
        else:
            camps_to_validate = list(camps.keys()) if camps else [None]

        errors = []

        for name in camps_to_validate:
            try:
                merged = self._config_loader.get_camp_config(raw_config, name)
                self._config_loader.validate_config(merged)
                label = f"camp '{name}'" if name else "defaults"
                logging.info(f"✓ {label}", extra={"stream": "stdout"})
            except ValueError as e:
                label = f"camp '{name}'" if name else "defaults"
                errors.append((label, str(e)))
                logging.error(f"✗ {label}: {e}", extra={"stream": "stderr"})

        if errors:
            sys.exit(1)

        logging.info("Configuration valid.", extra={"stream": "stdout"})


if __name__ == "__main__":
    main()
