"""BDD step definitions for startup script execution testing with sync directory simulation."""

import logging

import docker
from behave import given, then, when
from behave.runner import Context

from features.steps.setup_script_steps import exec_in_ssh_container
from features.steps.ssh_steps import get_combined_log_output

logger = logging.getLogger(__name__)


def create_synced_directory(context: Context) -> None:
    """Create synced directory in SSH container via Docker API.

    Parameters
    ----------
    context : Context
        Behave context object with instance_id and sync_directory

    Raises
    ------
    RuntimeError
        If directory creation or ownership change fails
    """
    if not hasattr(context, "instance_id"):
        logger.warning(
            "No instance_id found, directory will be created when instance launches"
        )
        return

    if not hasattr(context, "sync_directory"):
        logger.warning("No sync_directory configured")
        return

    instance_id = context.instance_id
    docker_client = docker.from_env()
    container_name = f"ssh-{instance_id}"

    try:
        container = docker_client.containers.get(container_name)

        exit_code, output = container.exec_run(["mkdir", "-p", context.sync_directory])

        if exit_code != 0:
            raise RuntimeError(f"Failed to create sync directory: {output.decode()}")

        logger.info(f"Created synced directory: {context.sync_directory}")

    except docker.errors.NotFound:
        raise AssertionError(f"SSH container {container_name} not found")


def ensure_sync_directory_context(context: Context) -> None:
    """Ensure sync_directory is set in context based on config.

    Parameters
    ----------
    context : Context
        Behave context object
    """
    if hasattr(context, "sync_directory"):
        return

    if (
        hasattr(context, "config_data")
        and "defaults" in context.config_data
        and "sync_paths" in context.config_data["defaults"]
    ):
        sync_paths = context.config_data["defaults"]["sync_paths"]
        if sync_paths and len(sync_paths) > 0:
            remote_path = sync_paths[0].get("remote", "~/myproject")
            context.sync_directory = remote_path.replace("~", "/home/user")
    else:
        context.sync_directory = "/home/user/myproject"


@given('defaults have command "{command}"')
def step_defaults_have_command(context: Context, command: str) -> None:
    """Configure defaults with command.

    Parameters
    ----------
    context : Context
        Behave context object
    command : str
        Command to execute
    """
    if not hasattr(context, "config_data"):
        context.config_data = {"defaults": {}, "machines": {}}

    if "defaults" not in context.config_data:
        context.config_data["defaults"] = {}

    context.config_data["defaults"]["command"] = command

    logger.info(f"Configured command: {command}")


@then("startup_script creates file in synced directory")
def step_startup_script_creates_file_in_synced_directory(context: Context) -> None:
    """Verify startup_script created file in synced directory.

    Parameters
    ----------
    context : Context
        Behave context object

    Raises
    ------
    AssertionError
        If marker file not found in synced directory
    """
    ensure_sync_directory_context(context)
    sync_path = context.sync_directory
    marker_file = f"{sync_path}/.startup_marker"

    exit_code, output = exec_in_ssh_container(context, ["test", "-f", marker_file])

    if exit_code != 0:
        raise AssertionError(
            f"Startup script marker file not found in synced directory: {marker_file}"
        )

    logger.info(f"Verified marker file exists in synced directory: {marker_file}")


@then('working directory is "{expected_path}"')
def step_verify_working_directory(context: Context, expected_path: str) -> None:
    """Verify command executed from expected working directory.

    Parameters
    ----------
    context : Context
        Behave context object
    expected_path : str
        Expected working directory path or "sync remote path"

    Raises
    ------
    AssertionError
        If working directory not found in output
    """
    if expected_path == "sync remote path":
        ensure_sync_directory_context(context)
        expected_path = context.sync_directory

    log_output = get_combined_log_output(context)

    if expected_path not in log_output:
        raise AssertionError(
            f"Working directory {expected_path} not found in output.\n"
            f"Log output: {log_output[:500]}..."
        )

    logger.info(f"Verified working directory: {expected_path}")


@then("startup_script executes successfully")
def step_startup_script_executes_successfully(context: Context) -> None:
    """Verify startup_script executed successfully.

    Parameters
    ----------
    context : Context
        Behave context object

    Raises
    ------
    AssertionError
        If command did not succeed
    """
    assert context.exit_code == 0, f"Command failed with exit code {context.exit_code}"

    logger.info("Verified startup_script executed successfully")


@when("I simulate running the machine in the TUI")
def step_simulate_running_machine_in_tui(context: Context) -> None:
    """Simulate running the machine in the TUI using Textual Pilot.

    This step uses the machine_name from context if set, otherwise uses default machine.
    It also ensures sync_directory is properly initialized if sync_paths are configured.

    Parameters
    ----------
    context : Context
        Behave context object
    """
    from features.steps.pilot_steps import run_tui_test_with_machine

    machine_name = getattr(context, "machine_name", "default")

    if not hasattr(context, "config_path"):
        raise AssertionError(
            "No config path found. Run 'I launch the Moondock TUI with the config file' step first."
        )

    ensure_sync_directory_context(context)

    max_wait = 180
    logger.info(f"=== STARTING TUI TEST FOR MACHINE: {machine_name} ===")
    result = run_tui_test_with_machine(machine_name, context.config_path, max_wait)
    context.tui_result = result
    logger.info(f"=== TUI TEST COMPLETED FOR MACHINE: {machine_name} ===")
    logger.info(f"TUI result status: {result.get('status', 'UNKNOWN')}")
    logger.info(f"TUI log length: {len(result.get('log_text', ''))} characters")
