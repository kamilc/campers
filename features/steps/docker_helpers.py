"""Docker container helper utilities for BDD testing.

This module provides shared utilities for managing Docker containers
in LocalStack-based high-fidelity tests.
"""

import logging
from typing import Union

import docker
from behave.runner import Context

logger = logging.getLogger(__name__)


def get_ssh_container(context: Context) -> docker.models.containers.Container:
    """Get SSH container for current test instance.

    Parameters
    ----------
    context : Context
        Behave context with instance_id attribute

    Returns
    -------
    Container
        Docker container object

    Raises
    ------
    RuntimeError
        If instance_id not found or container doesn't exist
    """
    if not hasattr(context, "instance_id"):
        raise RuntimeError("No instance_id in context - ensure instance is launched")

    instance_id = context.instance_id
    container_name = f"ssh-{instance_id}"

    docker_client = docker.from_env()
    try:
        return docker_client.containers.get(container_name)
    except docker.errors.NotFound:
        raise RuntimeError(f"SSH container {container_name} not found")


def exec_in_ssh_container(
    context: Context, command: Union[str, list[str]]
) -> tuple[int, bytes]:
    """Execute command in SSH container.

    Parameters
    ----------
    context : Context
        Behave context with instance_id
    command : Union[str, list[str]]
        Command to execute as string or list

    Returns
    -------
    tuple[int, bytes]
        Exit code and output bytes
    """
    container = get_ssh_container(context)
    return container.exec_run(command)


def create_directory_in_container(
    context: Context,
    path: str,
    mode: str = "755",
) -> None:
    """Create directory in SSH container with proper permissions.

    Parameters
    ----------
    context : Context
        Behave context with instance_id
    path : str
        Absolute path to create (e.g., "/home/user/myproject")
    mode : str, optional
        chmod mode string, default "755"

    Raises
    ------
    ValueError
        If path is empty or relative
    RuntimeError
        If directory creation or chmod fails
    """
    if not path or not path.strip():
        raise ValueError("path cannot be empty")
    if not path.startswith("/"):
        raise ValueError(f"path must be absolute, got: {path}")

    logger.debug(
        f"Creating directory {path} for instance {getattr(context, 'instance_id', 'UNKNOWN')}"
    )
    container = get_ssh_container(context)

    exit_code, output = container.exec_run(["mkdir", "-p", path])
    if exit_code != 0:
        logger.error(f"mkdir failed with code {exit_code}: {output.decode()}")
        raise RuntimeError(f"Failed to create directory {path}: {output.decode()}")

    exit_code, output = container.exec_run(["chmod", "-R", mode, path])
    if exit_code != 0:
        logger.error(f"chmod failed with code {exit_code}: {output.decode()}")
        raise RuntimeError(f"Failed to set permissions on {path}: {output.decode()}")

    exit_code, output = container.exec_run(["chown", "-R", "ubuntu:ubuntu", path])
    if exit_code != 0:
        logger.error(f"chown failed with code {exit_code}: {output.decode()}")
        raise RuntimeError(f"Failed to set ownership on {path}: {output.decode()}")

    logger.debug(
        f"Successfully created directory: {path} (mode: {mode}, owner: ubuntu:ubuntu)"
    )


def create_symlink_in_container(
    context: Context,
    target: str,
    link_name: str,
) -> None:
    """Create symbolic link in SSH container.

    Parameters
    ----------
    context : Context
        Behave context with instance_id
    target : str
        Absolute path that the symlink points to (the actual directory)
    link_name : str
        Absolute path for the symlink itself

    Raises
    ------
    ValueError
        If paths are empty or relative
    RuntimeError
        If symlink creation fails
    """
    if not target or not target.strip():
        raise ValueError("target cannot be empty")

    if not link_name or not link_name.strip():
        raise ValueError("link_name cannot be empty")

    if not target.startswith("/"):
        raise ValueError(f"target must be absolute, got: {target}")

    if not link_name.startswith("/"):
        raise ValueError(f"link_name must be absolute, got: {link_name}")

    container = get_ssh_container(context)

    link_parent = "/".join(link_name.split("/")[:-1])

    if link_parent:
        exit_code, output = container.exec_run(["mkdir", "-p", link_parent])

        if exit_code != 0:
            raise RuntimeError(
                f"Failed to create parent directory {link_parent}: {output.decode()}"
            )

    exit_code, output = container.exec_run(["ln", "-sf", target, link_name])

    if exit_code != 0:
        raise RuntimeError(
            f"Failed to create symlink {link_name} -> {target}: {output.decode()}"
        )

    logger.debug(f"Created symlink: {link_name} -> {target}")


def create_synced_directories(context: Context) -> None:
    """Create all synced directories and symlinks from context.config_data.

    Reads sync_paths from context.config_data and for each path:
    1. Creates the remote directory in the SSH container at /config/{path}
    2. Creates symlinks for root user at /root/{path}
    3. Creates directories for ubuntu user at /home/ubuntu/{path}

    This enables ~/myproject paths to work correctly for different users.

    Parameters
    ----------
    context : Context
        Behave context with instance_id and config_data

    Raises
    ------
    RuntimeError
        If instance not launched or directory creation fails
    """
    logger.debug(
        f"create_synced_directories called - has instance_id: {hasattr(context, 'instance_id')}"
    )
    if not hasattr(context, "instance_id") or context.instance_id in (None, ""):
        logger.debug("No instance_id - skipping directory creation")
        return

    logger.debug(
        f"create_synced_directories - has config_data: {hasattr(context, 'config_data')}"
    )
    if not hasattr(context, "config_data"):
        logger.debug("No config_data - skipping directory creation")
        return

    sync_paths = context.config_data.get("defaults", {}).get("sync_paths", [])
    logger.debug(f"Found {len(sync_paths)} sync_paths to create")

    for sync_path in sync_paths:
        remote_path = sync_path.get("remote", "~/myproject").replace("~", "/config")
        logger.debug(f"Creating directory: {remote_path}")
        create_directory_in_container(context, remote_path)

        original_remote = sync_path.get("remote", "~/myproject")

        if original_remote.startswith("~/"):
            root_path = original_remote.replace("~", "/root")
            ubuntu_path = original_remote.replace("~", "/home/ubuntu")

            if root_path != remote_path:
                logger.debug(f"Creating directory for root: {root_path}")
                create_directory_in_container(context, root_path)

            if ubuntu_path != remote_path:
                logger.debug(f"Creating directory for ubuntu: {ubuntu_path}")
                create_directory_in_container(context, ubuntu_path)
