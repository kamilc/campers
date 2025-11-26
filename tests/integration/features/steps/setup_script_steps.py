"""BDD step definitions for setup script execution testing."""

import logging

from behave import given, then
from behave.runner import Context

from tests.integration.features.steps.cli_steps import ensure_machine_exists
from tests.integration.features.steps.docker_helpers import exec_in_ssh_container

logger = logging.getLogger(__name__)


@given('machine "{camp_name}" has multi-line setup_script')
def step_machine_has_multi_line_setup_script(
    context: Context, camp_name: str
) -> None:
    """Configure machine with multi-line setup_script with shell features.

    Parameters
    ----------
    context : Context
        Behave context object
    camp_name : str
        Machine name
    """
    ensure_machine_exists(context, camp_name)

    multi_line_script = "set -e; mkdir -p /tmp/workspace; echo 'Ready' > /tmp/workspace/status.txt; if [ -d /tmp/workspace ]; then echo 'Workspace created'; fi"

    context.config_data["camps"][camp_name]["setup_script"] = multi_line_script
    logger.info(f"Configured multi-line setup_script for {camp_name}")


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


@then('file "{filepath}" exists in SSH container')
def step_file_exists_in_ssh_container(context: Context, filepath: str) -> None:
    """Verify file exists in SSH container via Docker API.

    Parameters
    ----------
    context : Context
        Behave context object
    filepath : str
        Path to file in container

    Raises
    ------
    AssertionError
        If file does not exist in container
    """
    exit_code, output = exec_in_ssh_container(context, ["test", "-f", filepath])

    if exit_code != 0:
        raise AssertionError(f"File {filepath} does not exist in SSH container")

    logger.info(f"Verified file exists in SSH container: {filepath}")


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
