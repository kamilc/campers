"""Mutagen mocking infrastructure for LocalStack testing."""

import logging
from contextlib import contextmanager
from typing import Generator
from unittest.mock import patch

import docker
from behave.runner import Context

logger = logging.getLogger(__name__)


def create_synced_directory(context: Context) -> None:
    """Create synced directory in SSH container via Docker API.

    Parameters
    ----------
    context : Context
        Behave context object with instance_id and config_data

    Raises
    ------
    RuntimeError
        If directory creation or ownership change fails
    """
    if not hasattr(context, "instance_id"):
        logger.debug("No instance_id found, skipping directory creation")
        return

    instance_id = context.instance_id
    docker_client = docker.from_env()
    container_name = f"ssh-{instance_id}"

    try:
        container = docker_client.containers.get(container_name)

        sync_paths = context.config_data.get("defaults", {}).get("sync_paths", [])
        for sync_path in sync_paths:
            remote_path = sync_path.get("remote", "~/myproject").replace(
                "~", "/home/user"
            )
            logger.debug(f"Creating synced directory: {remote_path}")

            exit_code, output = container.exec_run(["mkdir", "-p", remote_path])
            if exit_code != 0:
                raise RuntimeError(
                    f"Failed to create sync directory {remote_path}: {output.decode()}"
                )

            exit_code, output = container.exec_run(["chmod", "-R", "755", remote_path])
            if exit_code != 0:
                raise RuntimeError(
                    f"Failed to set permissions on {remote_path}: {output.decode()}"
                )

            logger.debug(
                f"Created synced directory with proper permissions: {remote_path}"
            )

    except docker.errors.NotFound:
        raise RuntimeError(f"SSH container {container_name} not found")


@contextmanager
def mutagen_mocked(context: Context) -> Generator[None, None, None]:
    """Mock Mutagen for LocalStack scenarios.

    This context manager patches MutagenManager methods to simulate Mutagen
    sync without actually running Mutagen. It creates synced directories
    via Docker API to provide high-fidelity sync simulation.

    Parameters
    ----------
    context : Context
        Behave context object containing test configuration and state

    Yields
    ------
    None

    Raises
    ------
    RuntimeError
        If synced directory creation fails
    """

    def mock_check_mutagen(self) -> None:
        logger.debug("Mocked: Mutagen installation check skipped")

    def mock_create_sync_session(self, *args, **kwargs):
        logger.debug("Mocked: Creating Mutagen sync session")
        create_synced_directory(context)
        return {"session_id": "mock-session", "status": "synced"}

    def mock_terminate_session(self, *args, **kwargs):
        logger.debug("Mocked: Terminating Mutagen session")
        return True

    def mock_wait_for_sync(self, *args, **kwargs):
        logger.debug("Mocked: Waiting for Mutagen sync")
        return True

    try:
        from moondock.sync import MutagenManager

        with (
            patch.object(MutagenManager, "check_mutagen_installed", mock_check_mutagen),
            patch.object(
                MutagenManager, "create_sync_session", mock_create_sync_session
            ),
            patch.object(MutagenManager, "terminate_session", mock_terminate_session),
            patch.object(MutagenManager, "wait_for_initial_sync", mock_wait_for_sync),
        ):
            yield
    except ImportError as e:
        raise RuntimeError(f"Failed to import MutagenManager: {e}")
