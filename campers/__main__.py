#!/usr/bin/env python3
"""Campers - cloud remote development tool."""

from __future__ import annotations

import logging
import os
import queue
import sys
import threading
import types
from pathlib import Path
from typing import Any, Callable

from campers.core.signals import set_cleanup_instance, setup_signal_handlers
from campers.core.cleanup import CleanupManager
from campers.core.run_executor import RunExecutor
from campers.core.setup import SetupManager
from campers.core.interfaces import ComputeProvider
from campers.lifecycle import LifecycleManager

setup_signal_handlers()

import boto3  # noqa: E402

for _boto_module in ["botocore", "boto3", "urllib3"]:
    logging.getLogger(_boto_module).setLevel(logging.WARNING)

from campers.core.config import ConfigLoader  # noqa: E402
from campers.providers.aws.compute import EC2Manager  # noqa: E402, F401
from campers.services.ssh import SSHManager  # noqa: E402
from campers.services.sync import MutagenManager  # noqa: E402, F401
from campers.services.portforward import PortForwardManager  # noqa: E402
from campers.templates import CONFIG_TEMPLATE  # noqa: E402
from campers.tui import CampersTUI  # noqa: E402
from campers.cli.main import main  # noqa: E402
from campers.utils import log_and_print_error, truncate_name  # noqa: E402


class Campers:
    """Main CLI interface for campers."""

    def __init__(
        self,
        compute_provider_factory: Callable[[str], ComputeProvider] | None = None,
        ssh_manager_factory: type | None = None,
        boto3_client_factory: Callable | None = None,
        boto3_resource_factory: Callable | None = None,
    ) -> None:
        """Initialize Campers CLI with optional dependency injection."""
        self._config_loader = ConfigLoader()
        self._cleanup_lock = threading.Lock()
        self._resources_lock = threading.Lock()
        self._cleanup_in_progress = False
        self._abort_requested = False
        self._resources: dict[str, Any] = {}
        self._update_queue: queue.Queue | None = None
        self._boto3_client_factory = boto3_client_factory or boto3.client
        self._boto3_resource_factory = boto3_resource_factory or boto3.resource

        self._compute_provider_factory_override = compute_provider_factory

        self._ssh_manager_factory = ssh_manager_factory or SSHManager

        self._cleanup_manager = CleanupManager(
            resources_dict=self._resources,
            resources_lock=self._resources_lock,
            cleanup_lock=self._cleanup_lock,
            update_queue=self._update_queue,
            config_dict={},
        )

        self._mutagen_manager_factory = lambda: MutagenManager()
        self._portforward_manager_factory = lambda: PortForwardManager()

        self._lifecycle_manager: LifecycleManager | None = None

        self._setup_manager = SetupManager(
            config_loader=self._config_loader,
            boto3_client_factory=self._boto3_client_factory,
        )

        self._run_executor: RunExecutor | None = None

        set_cleanup_instance(self)

    @property
    def compute_provider_factory(self) -> Callable[[str], ComputeProvider]:
        """Get the compute provider factory."""
        if self._compute_provider_factory_override is not None:
            return self._compute_provider_factory_override
        return self._create_compute_provider

    def _create_compute_provider(self, region: str) -> ComputeProvider:
        """Create a compute provider instance based on configured provider."""
        return EC2Manager(
            region=region,
            boto3_client_factory=self._boto3_client_factory,
            boto3_resource_factory=self._boto3_resource_factory,
        )

    @property
    def cleanup_in_progress(self) -> bool:
        """Get cleanup in progress status."""
        return self._cleanup_in_progress

    @property
    def run_executor(self) -> RunExecutor:
        """Get the run executor instance."""
        if self._run_executor is None:
            self._run_executor = RunExecutor(
                config_loader=self._config_loader,
                compute_provider_factory=self.compute_provider_factory,
                ssh_manager_factory=self._ssh_manager_factory,
                resources=self._resources,
                resources_lock=self._resources_lock,
                cleanup_in_progress_getter=lambda: self.cleanup_in_progress,
                update_queue=self._update_queue,
                mutagen_manager_factory=self._mutagen_manager_factory,
                portforward_manager_factory=self._portforward_manager_factory,
            )
        return self._run_executor

    def _validate_region_wrapper(self, region: str) -> None:
        compute_provider = self._create_compute_provider(region)
        compute_provider.validate_region(region)

    @property
    def lifecycle_manager(self) -> LifecycleManager:
        """Get the lifecycle manager instance."""
        if self._lifecycle_manager is None:
            self._lifecycle_manager = LifecycleManager(
                config_loader=self._config_loader,
                compute_provider_factory=self.compute_provider_factory,
                log_and_print_error=log_and_print_error,
                truncate_name=truncate_name,
            )
        return self._lifecycle_manager

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
            update_queue: queue.Queue = queue.Queue(maxsize=100)
            app = CampersTUI(
                campers_instance=self, run_kwargs=run_kwargs, update_queue=update_queue
            )

            exit_code = app.run()

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
        return self.run_executor.execute(
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

    def _get_or_create_instance(
        self, instance_name: str, config: dict[str, Any]
    ) -> dict[str, Any]:
        return self.run_executor._get_or_create_instance(instance_name, config)

    def _stop_instance_cleanup(self, signum: int | None = None) -> None:
        if self._cleanup_manager.resources is not self._resources:
            self._cleanup_manager.resources = self._resources
        return self._cleanup_manager.stop_instance_cleanup(signum=signum)

    def _terminate_instance_cleanup(self, signum: int | None = None) -> None:
        if self._cleanup_manager.resources is not self._resources:
            self._cleanup_manager.resources = self._resources
        return self._cleanup_manager.terminate_instance_cleanup(signum=signum)

    def _cleanup_resources(
        self, signum: int | None = None, frame: types.FrameType | None = None
    ) -> None:
        merged_config = getattr(self, "merged_config", None)
        if merged_config:
            self._cleanup_manager.config_dict = merged_config

        if self._cleanup_manager.resources is not self._resources:
            self._cleanup_manager.resources = self._resources

        self._cleanup_manager.cleanup_in_progress = self._cleanup_in_progress

        old_harness = os.environ.pop("CAMPERS_HARNESS_MANAGED", None)
        try:
            return self._cleanup_manager.cleanup_resources(signum=signum, frame=frame)
        finally:
            if old_harness is not None:
                os.environ["CAMPERS_HARNESS_MANAGED"] = old_harness
            self._cleanup_in_progress = self._cleanup_manager.cleanup_in_progress

    def _build_command_in_directory(self, working_dir: str, command: str) -> str:
        return self.run_executor._build_command_in_directory(working_dir, command)

    def _truncate_name(self, name: str) -> str:
        return truncate_name(name)

    def _validate_region(self, region: str) -> None:
        compute_provider = self._create_compute_provider(region)
        compute_provider.validate_region(region)

    def list(self, region: str | None = None) -> None:
        """List all managed instances."""
        return self.lifecycle_manager.list(region=region)

    def stop(self, name_or_id: str, region: str | None = None) -> None:
        """Stop a managed instance."""
        return self.lifecycle_manager.stop(name_or_id=name_or_id, region=region)

    def start(self, name_or_id: str, region: str | None = None) -> None:
        """Start a managed instance."""
        return self.lifecycle_manager.start(name_or_id=name_or_id, region=region)

    def info(self, name_or_id: str, region: str | None = None) -> None:
        """Get information about a managed instance."""
        return self.lifecycle_manager.info(name_or_id=name_or_id, region=region)

    def destroy(self, name_or_id: str, region: str | None = None) -> None:
        """Destroy a managed instance."""
        return self.lifecycle_manager.destroy(name_or_id=name_or_id, region=region)

    def setup(self, region: str | None = None, ec2_client: Any = None) -> None:
        """Set up AWS environment and validate configuration."""
        return self._setup_manager.setup(region=region, ec2_client=ec2_client)

    def doctor(self, region: str | None = None, ec2_client: Any = None) -> None:
        """Diagnose AWS environment and configuration issues.

        Parameters
        ----------
        region : str | None
            AWS region to diagnose, or None for default region
        ec2_client : Any
            Optional boto3 EC2 client (for testing/mocking)
        """
        return self._setup_manager.doctor(region=region, ec2_client=ec2_client)

    def init(self, force: bool = False) -> None:
        """Create a default campers.yaml configuration file."""
        config_path = os.environ.get("CAMPERS_CONFIG", "campers.yaml")
        config_file = Path(config_path)

        if config_file.exists() and not force:
            log_and_print_error(
                "%s already exists. Use --force to overwrite.",
                config_path,
            )
            sys.exit(1)

        config_file.parent.mkdir(parents=True, exist_ok=True)

        with open(config_file, "w") as f:
            f.write(CONFIG_TEMPLATE)

        print(f"Created {config_path} configuration file.")


if __name__ == "__main__":
    main()
