"""BDD step definitions for campers exec command."""

import logging
import os
import subprocess
import uuid
from pathlib import Path
from tempfile import TemporaryDirectory

from behave import given, then, when
from behave.runner import Context

from campers.session import SessionInfo, SessionManager
from tests.integration.features.steps.common_steps import execute_command_direct

logger = logging.getLogger(__name__)


def get_test_user_identity() -> str:
    """Get user identity matching what get_user_identity() returns in production.

    Returns git email if available, falls back to $USER, then "unknown".

    Returns
    -------
    str
        User identity string suitable for ownership checks.
    """
    identity = None

    try:
        result = subprocess.run(
            ["git", "config", "user.email"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )

        if result.returncode == 0 and result.stdout.strip():
            identity = result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    if not identity:
        identity = os.environ.get("USER", "unknown")

    return identity[:256]


@given("a session file exists for camp {camp_name_quoted} with valid SSH info")
def step_session_file_with_ssh_info(context: Context, camp_name_quoted: str) -> None:
    """Create a session file with valid SSH connection info."""
    camp_name = camp_name_quoted.strip('"')

    if not hasattr(context, "temp_campers_dir"):
        context.temp_campers_dir = TemporaryDirectory()

    campers_dir = Path(context.temp_campers_dir.name)
    context.sessions_dir = campers_dir / "sessions"
    os.environ["CAMPERS_DIR"] = str(campers_dir)
    context.session_manager = SessionManager(sessions_dir=context.sessions_dir)

    session_info = SessionInfo(
        camp_name=camp_name,
        pid=os.getpid(),
        instance_id="i-0abc123def456",
        region="us-east-1",
        ssh_host="54.23.45.67",
        ssh_port=22,
        ssh_user="ubuntu",
        key_file="/home/user/.campers/keys/id_rsa",
    )
    context.session_manager.create_session(session_info)
    logger.info(f"Created session file for camp '{camp_name}'")


@given("no session file exists for camp {camp_name_quoted}")
def step_no_session_file(context: Context, camp_name_quoted: str) -> None:
    """Ensure no session file exists for the camp."""
    camp_name = camp_name_quoted.strip('"')

    if not hasattr(context, "temp_campers_dir"):
        context.temp_campers_dir = TemporaryDirectory()

    campers_dir = Path(context.temp_campers_dir.name)
    context.sessions_dir = campers_dir / "sessions"
    os.environ["CAMPERS_DIR"] = str(campers_dir)
    context.session_manager = SessionManager(sessions_dir=context.sessions_dir)

    session_file = context.sessions_dir / f"{camp_name}.session.json"
    if session_file.exists():
        session_file.unlink()

    logger.info(f"Ensured no session file for camp '{camp_name}'")


@given("a running instance exists for camp {camp_name_quoted}")
def step_running_instance_for_camp(context: Context, camp_name_quoted: str) -> None:
    """Create a running EC2 instance for the camp."""
    camp_name = camp_name_quoted.strip('"')

    if not hasattr(context, "instances") or context.instances is None:
        context.instances = []

    instance = {
        "instance_id": f"i-{camp_name}001",
        "camp_name": camp_name,
        "camp_config": camp_name,
        "state": "running",
        "region": "us-east-1",
        "public_ip": "54.23.45.67",
        "key_file": "/home/user/.campers/keys/id_rsa",
        "owner": get_test_user_identity(),
        "unique_id": str(uuid.uuid4())[:12],
    }
    context.instances.append(instance)
    logger.info(f"Created running instance for camp '{camp_name}'")


@given("a running instance {instance_id_quoted} exists for exec")
def step_running_instance_by_id(context: Context, instance_id_quoted: str) -> None:
    """Create a running EC2 instance with specific ID."""
    instance_id = instance_id_quoted.strip('"')

    if not hasattr(context, "instances") or context.instances is None:
        context.instances = []

    instance = {
        "instance_id": instance_id,
        "camp_name": "test-camp",
        "camp_config": "test-camp",
        "state": "running",
        "region": "us-east-1",
        "public_ip": "54.23.45.67",
        "key_file": "/home/user/.campers/keys/id_rsa",
        "owner": get_test_user_identity(),
        "unique_id": str(uuid.uuid4())[:12],
    }
    context.instances.append(instance)
    logger.info(f"Created running instance '{instance_id}'")


@given("a stopped instance exists for camp {camp_name_quoted}")
def step_stopped_instance_for_camp(context: Context, camp_name_quoted: str) -> None:
    """Create a stopped EC2 instance for the camp."""
    camp_name = camp_name_quoted.strip('"')

    if not hasattr(context, "instances") or context.instances is None:
        context.instances = []

    instance = {
        "instance_id": f"i-{camp_name}stopped",
        "camp_name": camp_name,
        "camp_config": camp_name,
        "state": "stopped",
        "region": "us-east-1",
        "public_ip": None,
        "key_file": "/home/user/.campers/keys/id_rsa",
        "owner": get_test_user_identity(),
        "unique_id": str(uuid.uuid4())[:12],
    }
    context.instances.append(instance)
    logger.info(f"Created stopped instance for camp '{camp_name}'")


@given("multiple running instances exist for camp {camp_name_quoted}")
def step_multiple_instances_for_camp(context: Context, camp_name_quoted: str) -> None:
    """Create multiple running instances for the camp."""
    camp_name = camp_name_quoted.strip('"')

    if not hasattr(context, "instances") or context.instances is None:
        context.instances = []

    for i in range(2):
        instance = {
            "instance_id": f"i-{camp_name}{i:03d}",
            "camp_name": camp_name,
            "camp_config": camp_name,
            "state": "running",
            "region": "us-east-1",
            "public_ip": f"54.23.45.{67+i}",
            "key_file": "/home/user/.campers/keys/id_rsa",
            "owner": get_test_user_identity(),
            "unique_id": str(uuid.uuid4())[:12],
        }
        context.instances.append(instance)

    logger.info(f"Created {2} running instances for camp '{camp_name}'")


@given("running instances exist for camp {camp_name_quoted} in multiple regions")
def step_instances_multiple_regions(context: Context, camp_name_quoted: str) -> None:
    """Create running instances for the camp in multiple regions."""
    camp_name = camp_name_quoted.strip('"')

    if not hasattr(context, "instances") or context.instances is None:
        context.instances = []

    regions = ["us-east-1", "us-west-2"]
    for region in regions:
        instance = {
            "instance_id": f"i-{camp_name}-{region}",
            "camp_name": camp_name,
            "camp_config": camp_name,
            "state": "running",
            "region": region,
            "public_ip": "54.23.45.67",
            "key_file": "/home/user/.campers/keys/id_rsa",
            "owner": get_test_user_identity(),
            "unique_id": str(uuid.uuid4())[:12],
        }
        context.instances.append(instance)

    logger.info(f"Created instances for camp '{camp_name}' in {len(regions)} regions")


@when(  # noqa: E501
    "I run campers exec {camp_or_id_quoted} with command {command_quoted} and region {region_quoted}"  # noqa: E501
)
def step_run_exec_command_with_region(
    context: Context, camp_or_id_quoted: str, command_quoted: str, region_quoted: str
) -> None:
    """Run campers exec command with camp name or instance ID and region."""
    camp_or_id = camp_or_id_quoted.strip('"')
    command = command_quoted.strip('"')
    region = region_quoted.strip('"')

    context.use_direct_instantiation = True
    context.exec_camp_or_id = camp_or_id
    context.exec_command = command
    context.exec_region = region

    try:
        args = {
            "camp_or_instance": camp_or_id,
            "command": command,
            "region": region,
        }

        execute_command_direct(
            context,
            "exec",
            args=args,
            region=region,
        )
    except Exception as e:
        context.exit_code = 1
        context.error = str(e)
        logger.error(f"Exec command failed: {e}")


@when('I run campers exec {camp_or_id_quoted} with command {command_quoted}')
@when('I run campers exec {camp_or_id_quoted} {flags} with command {command_quoted}')
def step_run_exec_command(
    context: Context, camp_or_id_quoted: str, command_quoted: str, flags: str = None
) -> None:
    """Run campers exec command with camp name or instance ID and optional flags."""
    camp_or_id = camp_or_id_quoted.strip('"')
    command = command_quoted.strip('"')

    context.use_direct_instantiation = True
    context.exec_camp_or_id = camp_or_id
    context.exec_command = command

    if flags:
        context.exec_flags = flags

    try:
        args = {"camp_or_instance": camp_or_id, "command": command}

        if flags and "-t" in flags:
            args["t"] = True
        if flags and "-i" in flags:
            args["i"] = True

        execute_command_direct(
            context,
            "exec",
            args=args,
        )
    except Exception as e:
        context.exit_code = 1
        context.error = str(e)
        logger.error(f"Exec command failed: {e}")


@then("the command should execute successfully")
def step_command_executes_successfully(context: Context) -> None:
    """Verify the exec command executed successfully."""
    assert (
        context.exit_code == 0
    ), f"Expected exit code 0, got {context.exit_code}. stderr: {context.stderr}"


@then("the command should fail")
def step_command_fails(context: Context) -> None:
    """Verify the exec command failed."""
    assert context.exit_code != 0, f"Expected non-zero exit code, got {context.exit_code}"


@then("the exit code should be {exit_code:d}")
def step_exit_code_is_exact(context: Context, exit_code: int) -> None:
    """Verify the exit code matches expected value."""
    assert (
        context.exit_code == exit_code
    ), f"Expected exit code {exit_code}, got {context.exit_code}"


@then("exec output contains {expected_text_quoted}")
def step_output_contains(context: Context, expected_text_quoted: str) -> None:
    """Verify output contains expected text."""
    expected_text = expected_text_quoted.strip('"')
    output = context.stdout + context.stderr

    assert (
        expected_text in output
    ), f"Expected '{expected_text}' in output, got: {output}"


@then("exec error message includes {expected_msg_quoted}")
def step_error_includes(context: Context, expected_msg_quoted: str) -> None:
    """Verify error message includes expected text."""
    expected_msg = expected_msg_quoted.strip('"')
    error_output = context.stderr + getattr(context, "command_error", "")

    assert (
        expected_msg in error_output
    ), f"Expected '{expected_msg}' in error, got: {error_output}"


@then("error message indicates instance is not running")
def step_error_not_running(context: Context) -> None:
    """Verify error message indicates instance is not in running state."""
    error_output = context.stderr + getattr(context, "command_error", "")

    assert (
        "not running" in error_output or "stopped" in error_output
    ), f"Expected 'not running' or 'stopped' in error, got: {error_output}"


@then("the command should execute successfully on the {region} instance")
def step_command_executes_on_region(context: Context, region: str) -> None:
    """Verify the exec command executed on the specified region instance."""
    assert context.exit_code == 0, f"Expected exit code 0, got {context.exit_code}"
    assert hasattr(context, "exec_region")
    assert context.exec_region == region


@given("stdout is redirected to a file")
def step_stdout_redirected(context: Context) -> None:
    """Mark context to simulate stdout redirection."""
    if not hasattr(context, "temp_campers_dir"):
        context.temp_campers_dir = TemporaryDirectory()

    context.redirect_stdout = True
    logger.info("Marked stdout as redirected")


@given("stdin is redirected from a file")
def step_stdin_redirected(context: Context) -> None:
    """Mark context to simulate stdin redirection."""
    if not hasattr(context, "temp_campers_dir"):
        context.temp_campers_dir = TemporaryDirectory()

    context.redirect_stdin = True
    logger.info("Marked stdin as redirected")


@then("a warning was logged containing {expected_msg_quoted}")
def step_warning_was_logged(context: Context, expected_msg_quoted: str) -> None:
    """Verify a warning message was logged."""
    expected_msg = expected_msg_quoted.strip('"')

    if not hasattr(context, "log_capture_handler"):
        context.log_capture_handler = None

    output = context.stdout + context.stderr

    assert (
        expected_msg in output
    ), f"Expected warning '{expected_msg}' in output, got: {output}"
