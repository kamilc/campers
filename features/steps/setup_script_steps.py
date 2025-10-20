"""BDD step definitions for setup script execution testing."""

import logging
from typing import Union

import docker
from behave import given, then
from behave.runner import Context

from features.steps.cli_steps import ensure_machine_exists

logger = logging.getLogger(__name__)


def exec_in_ssh_container(
    context: Context, command: Union[str, list[str]]
) -> tuple[int, bytes]:
    """Execute command in SSH container via Docker API.

    Parameters
    ----------
    context : Context
        Behave context object with instance_id
    command : str | list[str]
        Command to execute in container

    Returns
    -------
    tuple[int, bytes]
        Exit code and output from container.exec_run()

    Raises
    ------
    AssertionError
        If instance_id not found or container not found
    """
    if not hasattr(context, "instance_id"):
        raise AssertionError("No instance_id found. Launch instance first.")

    instance_id = context.instance_id
    docker_client = docker.from_env()
    container_name = f"ssh-{instance_id}"

    try:
        container = docker_client.containers.get(container_name)
        return container.exec_run(command)
    except docker.errors.NotFound:
        raise AssertionError(f"SSH container {container_name} not found")


@given('machine "{machine_name}" has multi-line setup_script')
def step_machine_has_multi_line_setup_script(
    context: Context, machine_name: str
) -> None:
    """Configure machine with multi-line setup_script with shell features.

    Parameters
    ----------
    context : Context
        Behave context object
    machine_name : str
        Machine name
    """
    ensure_machine_exists(context, machine_name)

    multi_line_script = "set -e; mkdir -p /tmp/workspace; echo 'Ready' > /tmp/workspace/status.txt; if [ -d /tmp/workspace ]; then echo 'Workspace created'; fi"

    context.config_data["machines"][machine_name]["setup_script"] = multi_line_script
    logger.info(f"Configured multi-line setup_script for {machine_name}")


@then('marker file "{filename}" exists in SSH container')
def step_marker_file_exists(context: Context, filename: str) -> None:
    """Verify marker file exists in SSH container via Docker API.

    Parameters
    ----------
    context : Context
        Behave context object
    filename : str
        Path to file in container
    """
    exit_code, output = exec_in_ssh_container(context, ["test", "-f", filename])

    if exit_code != 0:
        raise AssertionError(f"Marker file {filename} does not exist in container")

    logger.info(f"Verified marker file exists: {filename}")


@then('directory "{dirpath}" exists in SSH container')
def step_directory_exists(context: Context, dirpath: str) -> None:
    """Verify directory exists in SSH container via Docker API.

    Parameters
    ----------
    context : Context
        Behave context object
    dirpath : str
        Path to directory in container
    """
    exit_code, output = exec_in_ssh_container(context, ["test", "-d", dirpath])

    if exit_code != 0:
        raise AssertionError(f"Directory {dirpath} does not exist in container")

    logger.info(f"Verified directory exists: {dirpath}")


@then('file "{filepath}" contains "{content}"')
def step_file_contains(context: Context, filepath: str, content: str) -> None:
    """Verify file contains expected content via Docker API.

    Parameters
    ----------
    context : Context
        Behave context object
    filepath : str
        Path to file in container
    content : str
        Expected content substring
    """
    exit_code, output = exec_in_ssh_container(context, ["cat", filepath])

    if exit_code != 0:
        raise AssertionError(f"Failed to read file {filepath} in container")

    file_content = output.decode("utf-8")

    if content not in file_content:
        raise AssertionError(
            f"File {filepath} does not contain expected content.\n"
            f"Expected substring: {content}\n"
            f"Actual content: {file_content}"
        )

    logger.info(f"Verified file {filepath} contains: {content}")
