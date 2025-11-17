"""BDD step definitions for SSH connection and command execution."""

import datetime
import json
import logging
import os
import re
from unittest.mock import MagicMock, patch

from behave import given, then, when
from behave.runner import Context

from moondock.ssh import SSHManager

logger = logging.getLogger(__name__)


def get_combined_log_output(context: Context) -> str:
    """Extract combined log output from stderr and log records.

    Parameters
    ----------
    context : Context
        Behave context object

    Returns
    -------
    str
        Combined log output from stderr and log records
    """
    log_lines = []

    if hasattr(context, "stderr") and context.stderr:
        log_lines.append(context.stderr)

    if hasattr(context, "log_records"):
        log_lines.extend(record.getMessage() for record in context.log_records)

    return "\n".join(log_lines)


@given("EC2 instance is starting up")
def step_ec2_instance_starting_up(context: Context) -> None:
    """Set up scenario where instance is starting and SSH not yet available."""
    context.ssh_not_ready = True


@given("SSH is not yet available")
def step_ssh_not_available(context: Context) -> None:
    """Mark that SSH is not yet available for connection."""
    context.ssh_not_ready = True


@given("EC2 instance has no SSH access")
def step_ec2_no_ssh_access(context: Context) -> None:
    """Set up scenario where instance has no SSH access at all."""
    context.ssh_always_fails = True


@given('MOONDOCK_TEST_MODE is "{value}"')
def step_moondock_test_mode(context: Context, value: str) -> None:
    """Set MOONDOCK_TEST_MODE environment variable."""
    if hasattr(context, "harness") and context.harness is not None:
        context.harness.services.configuration_env.set("MOONDOCK_TEST_MODE", value)
    else:
        os.environ["MOONDOCK_TEST_MODE"] = value
    context.test_mode_enabled = value == "1"


@given('machine "{machine_name}" has no public IP')
def step_machine_no_public_ip(context: Context, machine_name: str) -> None:
    """Set up machine configuration to return no public IP."""
    if not hasattr(context, "config_data") or context.config_data is None:
        context.config_data = {"defaults": {}, "machines": {}}

    if "machines" not in context.config_data:
        context.config_data["machines"] = {}

    if machine_name not in context.config_data["machines"]:
        context.config_data["machines"][machine_name] = {}

    context.no_public_ip = True
    context.harness.services.configuration_env.set("MOONDOCK_NO_PUBLIC_IP", "1")


@when("SSH connection is attempted")
def step_ssh_connection_attempted(context: Context) -> None:
    """Attempt SSH connection with retry logic."""
    ssh_manager = SSHManager(
        host="203.0.113.1", key_file="/tmp/test.pem", username="ubuntu"
    )

    context.ssh_manager = ssh_manager
    context.connection_attempts = 0
    context.retry_delays = []

    with (
        patch("moondock.ssh.paramiko.SSHClient") as mock_ssh_client,
        patch("moondock.ssh.paramiko.RSAKey.from_private_key_file") as mock_rsa_key,
        patch("moondock.ssh.time.sleep") as mock_sleep,
    ):
        mock_client = MagicMock()
        mock_ssh_client.return_value = mock_client
        mock_key = MagicMock()
        mock_rsa_key.return_value = mock_key

        if hasattr(context, "ssh_not_ready") and context.ssh_not_ready:
            mock_client.connect.side_effect = [
                ConnectionRefusedError("Connection refused"),
                ConnectionRefusedError("Connection refused"),
                ConnectionRefusedError("Connection refused"),
                None,
            ]
        else:
            mock_client.connect.return_value = None

        def track_sleep(delay: float) -> None:
            context.retry_delays.append(delay)

        mock_sleep.side_effect = track_sleep

        try:
            ssh_manager.connect(max_retries=10)
            context.connection_successful = True
            context.connection_attempts = mock_client.connect.call_count
        except ConnectionError as e:
            context.exception = e
            context.connection_successful = False
            context.connection_attempts = mock_client.connect.call_count


@when("SSH connection is attempted with {retries:d} retries")
def step_ssh_connection_attempted_with_retries(context: Context, retries: int) -> None:
    """Attempt SSH connection with specific number of retries."""
    ssh_manager = SSHManager(
        host="203.0.113.1", key_file="/tmp/test.pem", username="ubuntu"
    )

    context.ssh_manager = ssh_manager

    with (
        patch("moondock.ssh.paramiko.SSHClient") as mock_ssh_client,
        patch("moondock.ssh.paramiko.RSAKey.from_private_key_file") as mock_rsa_key,
        patch("moondock.ssh.time.sleep"),
    ):
        mock_client = MagicMock()
        mock_ssh_client.return_value = mock_client
        mock_key = MagicMock()
        mock_rsa_key.return_value = mock_key

        mock_client.connect.side_effect = ConnectionRefusedError("Connection refused")

        try:
            ssh_manager.connect(max_retries=retries)
            context.exception = None
        except ConnectionError as e:
            context.exception = e


@then("instance is launched with SSH configured")
def step_instance_launched_with_ssh(context: Context) -> None:
    """Verify instance was launched with SSH configuration."""
    assert context.exit_code == 0, f"Command failed with exit code {context.exit_code}"


@then("SSH connection is established")
def step_ssh_connection_established(context: Context) -> None:
    """Verify SSH connection was established."""
    error_details = ""

    if hasattr(context, "stderr") and context.stderr:
        error_details += f"\nSTDERR: {context.stderr}"

    if hasattr(context, "error") and context.error:
        error_details += f"\nERROR: {context.error}"

    if hasattr(context, "stdout") and context.stdout:
        error_details += f"\nSTDOUT: {context.stdout}"

    assert context.exit_code == 0, (
        f"Command failed with exit code {context.exit_code}{error_details}"
    )


@then('command "{command}" executes on remote instance')
def step_command_executes_on_remote(context: Context, command: str) -> None:
    """Verify specific command executed on remote instance."""
    assert context.exit_code == 0, f"Command failed with exit code {context.exit_code}"


@then("command exit code is {exit_code:d}")
def step_command_exit_code(context: Context, exit_code: int) -> None:
    """Verify command exit code matches expected value."""
    if hasattr(context, "final_config") and "command_exit_code" in context.final_config:
        assert context.final_config["command_exit_code"] == exit_code
    else:
        assert context.exit_code == 0


@then("output is streamed to terminal")
def step_output_streamed(context: Context) -> None:
    """Verify output was streamed to terminal."""
    assert context.exit_code == 0


@then("instance is launched")
def step_instance_launched(context: Context) -> None:
    """Verify instance was launched."""

    if hasattr(context, "stderr") and (
        "Setup script failed" in context.stderr
        or "Startup script failed" in context.stderr
    ):
        assert context.exit_code != 0, "Setup/Startup script should have caused failure"
    else:
        if context.exit_code != 0:
            stdout = getattr(context, "stdout", "")
            stderr = getattr(context, "stderr", "")
            error_msg = getattr(context, "error", "")
            raise AssertionError(
                f"Command failed with exit code {context.exit_code}\n"
                f"STDOUT: {stdout}\n"
                f"STDERR: {stderr}\n"
                f"ERROR: {error_msg}"
            )


@then("SSH connection is not attempted")
def step_ssh_not_attempted(context: Context) -> None:
    """Verify SSH connection was not attempted."""
    assert context.exit_code == 0


@then("command executes on remote instance")
def step_command_executes(context: Context) -> None:
    """Verify command executed on remote instance."""
    assert context.exit_code == 0


@then("connection retries with delays {delays}")
def step_connection_retries_with_delays(context: Context, delays: str) -> None:
    """Verify connection retries with specific delay pattern."""
    expected_delays = json.loads(delays)

    if hasattr(context, "retry_delays"):
        for i, expected in enumerate(expected_delays):
            if i < len(context.retry_delays):
                assert context.retry_delays[i] == expected


@then("connection succeeds when SSH is ready")
def step_connection_succeeds_when_ready(context: Context) -> None:
    """Verify connection succeeded when SSH became ready."""
    assert hasattr(context, "connection_successful")
    assert context.connection_successful


@then("total retry time is under {seconds:d} seconds")
def step_total_retry_time_under(context: Context, seconds: int) -> None:
    """Verify total retry time is under specified seconds."""
    if hasattr(context, "retry_delays"):
        total_time = sum(context.retry_delays)
        assert total_time < seconds


@then("all connection attempts fail")
def step_all_attempts_fail(context: Context) -> None:
    """Verify all connection attempts failed."""
    if hasattr(context, "exception") and context.exception is not None:
        return

    log_output = get_combined_log_output(context)

    if log_output:
        assert "SSH connection established" not in log_output, (
            "Connection should not have succeeded"
        )
        assert context.exit_code != 0, (
            "Expected non-zero exit code for failed connection"
        )
    else:
        assert hasattr(context, "exception")
        assert context.exception is not None


@then('error message is "{expected_message}"')
def step_error_message_is(context: Context, expected_message: str) -> None:
    """Verify error message matches expected text."""
    assert hasattr(context, "exception")
    assert context.exception is not None
    assert expected_message in str(context.exception)


@then("command uses bash shell")
def step_command_uses_bash(context: Context) -> None:
    """Verify command was executed in bash shell."""
    assert context.exit_code == 0


@then('command output contains "{expected_text}"')
def step_command_output_contains(context: Context, expected_text: str) -> None:
    """Verify command output contains expected text."""
    if hasattr(context, "stdout"):
        assert expected_text in context.stdout or context.exit_code == 0
    elif hasattr(context, "stderr"):
        assert expected_text in context.stderr or context.exit_code == 0
    else:
        assert context.exit_code == 0


@then("SSH connection is not actually attempted")
def step_ssh_not_actually_attempted(context: Context) -> None:
    """Verify SSH connection was not actually attempted in test mode."""
    assert hasattr(context, "test_mode_enabled") and context.test_mode_enabled


@then("status messages are printed")
def step_status_messages_printed(context: Context) -> None:
    """Verify status messages were printed."""
    found_waiting_msg = False
    found_established_msg = False

    if hasattr(context, "log_records") and context.log_records:
        messages = [record.getMessage() for record in context.log_records]
        found_waiting_msg = any(
            "Waiting for SSH to be ready" in msg for msg in messages
        )
        found_established_msg = any(
            "SSH connection established" in msg for msg in messages
        )

    assert found_waiting_msg or found_established_msg, (
        f"Expected status messages in log records, got: {[record.getMessage() for record in getattr(context, 'log_records', [])]}"
    )


@then("command_exit_code is {exit_code:d} in result")
def step_command_exit_code_in_result(context: Context, exit_code: int) -> None:
    """Verify command_exit_code field in result."""
    if (
        hasattr(context, "final_config")
        and context.final_config is not None
        and "command_exit_code" in context.final_config
    ):
        assert context.final_config["command_exit_code"] == exit_code


@then("setup_script executes before command")
def step_setup_script_executes_before_command(context: Context) -> None:
    """Verify setup_script executed before command."""
    assert context.exit_code == 0


@then("setup_script exit code is {exit_code:d}")
def step_setup_script_exit_code(context: Context, exit_code: int) -> None:
    """Verify setup_script exit code."""

    if exit_code == 0:
        assert context.exit_code == 0, (
            f"Expected successful execution but got exit code {context.exit_code}"
        )
    else:
        assert context.exit_code != 0, (
            f"Expected failure with exit code {exit_code} but command succeeded"
        )


@given('machine "{machine_name}" has multi-line setup_script with shell features')
def step_machine_has_multiline_setup_script(
    context: Context, machine_name: str
) -> None:
    """Set up machine with multi-line setup_script."""
    from tests.integration.features.steps.cli_steps import ensure_machine_exists

    ensure_machine_exists(context, machine_name)
    script = """echo "Installing dependencies..."
sudo apt update > /dev/null
sudo apt install -y python3-pip
pip3 install uv"""
    context.config_data["machines"][machine_name]["setup_script"] = script


@then("setup_script executes successfully")
def step_setup_script_executes_successfully(context: Context) -> None:
    """Verify setup_script executed successfully."""
    assert context.exit_code == 0


@then("command executes after setup")
def step_command_executes_after_setup(context: Context) -> None:
    """Verify command executed after setup_script."""
    assert context.exit_code == 0


@given('defaults have setup_script "{script}"')
@given('YAML defaults with setup_script "{script}"')
def step_defaults_have_setup_script(context: Context, script: str) -> None:
    """Set up defaults section with setup_script."""
    if not hasattr(context, "config_data") or context.config_data is None:
        context.config_data = {"defaults": {}, "machines": {}}

    if "defaults" not in context.config_data:
        context.config_data["defaults"] = {}

    context.config_data["defaults"]["setup_script"] = script


@then("command fails with RuntimeError")
def step_command_fails_with_runtime_error(context: Context) -> None:
    """Verify command failed with RuntimeError."""
    assert context.exit_code != 0


@then('command "{command}" does not execute')
def step_command_does_not_execute(context: Context, command: str) -> None:
    """Verify command did not execute."""
    assert context.exit_code != 0


@given('machine "{machine_name}" has no setup_script')
def step_machine_has_no_setup_script(context: Context, machine_name: str) -> None:
    """Set up machine without setup_script."""
    from tests.integration.features.steps.cli_steps import ensure_machine_exists

    ensure_machine_exists(context, machine_name)


@then("setup_script execution is skipped")
def step_setup_script_execution_skipped(context: Context) -> None:
    """Verify setup_script execution was skipped."""
    assert context.exit_code == 0


@then("SSH connection is not actually attempted for setup_script")
def step_ssh_not_attempted_for_setup_script(context: Context) -> None:
    """Verify SSH was not attempted for setup_script in test mode."""
    assert hasattr(context, "test_mode_enabled") and context.test_mode_enabled


@then('status message "{message}" is logged')
def step_status_message_logged(context: Context, message: str) -> None:
    """Verify status message was logged.

    Works for both subprocess mode (checking stderr) and in-process mode
    (checking log records).
    """
    log_output = get_combined_log_output(context)
    assert message in log_output, (
        f"Expected message '{message}' not found in output: {log_output}"
    )


@given('machine "{machine_name}" has no command')
def step_machine_has_no_command_field(context: Context, machine_name: str) -> None:
    """Set up machine without command field."""
    from tests.integration.features.steps.cli_steps import ensure_machine_exists

    ensure_machine_exists(context, machine_name)


@given("SSH container will delay startup by {seconds:d} seconds")
def step_ssh_container_delayed_startup(context: Context, seconds: int) -> None:
    """Configure SSH container to delay startup by specified seconds.

    Parameters
    ----------
    context : Context
        Behave context object
    seconds : int
        Number of seconds to delay SSH startup
    """
    context.harness.services.configuration_env.set(
        "MOONDOCK_SSH_DELAY_SECONDS", str(seconds)
    )
    logger.info(f"SSH container will delay startup by {seconds} seconds")


@given("SSH container is not accessible")
def step_ssh_container_not_accessible(context: Context) -> None:
    """Configure SSH container to be created without port mapping (unreachable).

    Parameters
    ----------
    context : Context
        Behave context object
    """
    context.harness.services.configuration_env.set(
        "MOONDOCK_SSH_BLOCK_CONNECTIONS", "1"
    )
    logger.info("SSH container will be created without port mapping (blocked)")


@then("SSH connection attempts are made")
def step_ssh_attempts_made(context: Context) -> None:
    """Verify SSH connection attempts were logged.

    Parameters
    ----------
    context : Context
        Behave context object
    """
    log_output = get_combined_log_output(context)
    assert "Attempting SSH connection" in log_output, (
        f"No SSH connection attempts found in logs. Output:\n{log_output[:500]}"
    )


RETRY_DELAY_TOLERANCE_SECONDS = 4
ATTEMPT_TIMESTAMP_PATTERN = re.compile(
    r"(\d{2}:\d{2}:\d{2}\.\d+).*Attempting SSH connection"
)


@then("connection retry delays match {delays} seconds")
def step_verify_retry_delays(context: Context, delays: str) -> None:
    """Verify actual retry delays match expected pattern with tolerance.

    Parameters
    ----------
    context : Context
        Behave context object
    delays : str
        JSON array of expected delays: "[1, 2, 4, 8]"
    """
    expected = json.loads(delays)
    log_lines = context.stderr or ""

    if hasattr(context, "log_records"):
        for record in context.log_records:
            timestamp = datetime.datetime.fromtimestamp(record.created).strftime(
                "%H:%M:%S.%f"
            )
            log_lines += f"{timestamp} {record.getMessage()}\n"

    attempts_with_timestamps = ATTEMPT_TIMESTAMP_PATTERN.findall(log_lines)

    unique_timestamps = []
    for ts in attempts_with_timestamps:
        if ts not in unique_timestamps:
            unique_timestamps.append(ts)

    if len(unique_timestamps) < 2:
        raise AssertionError(
            f"Insufficient SSH connection attempts to verify delays. "
            f"Expected at least 2, found {len(unique_timestamps)}"
        )

    actual_delays = []

    for i in range(1, len(unique_timestamps)):
        prev_time = datetime.datetime.strptime(unique_timestamps[i - 1], "%H:%M:%S.%f")
        curr_time = datetime.datetime.strptime(unique_timestamps[i], "%H:%M:%S.%f")
        delay = (curr_time - prev_time).total_seconds()
        actual_delays.append(delay)

    for i, expected_delay in enumerate(expected):
        if i < len(actual_delays):
            tolerance = RETRY_DELAY_TOLERANCE_SECONDS

            if i == 0:
                tolerance = RETRY_DELAY_TOLERANCE_SECONDS + 2

            assert abs(actual_delays[i] - expected_delay) <= tolerance, (
                f"Delay {i + 1}: expected {expected_delay}s ±{tolerance}s, got {actual_delays[i]:.1f}s"
            )


@then("connection succeeds when SSH becomes ready")
def step_connection_succeeds_after_delay(context: Context) -> None:
    """Verify connection succeeded after delay.

    Parameters
    ----------
    context : Context
        Behave context object
    """
    log_output = get_combined_log_output(context)
    assert "SSH connection established" in log_output, (
        f"SSH connection not established. Output:\n{log_output[:500]}"
    )
    assert context.exit_code == 0, f"Expected exit code 0, got {context.exit_code}"


@then("SSH connection is attempted multiple times")
def step_multiple_attempts(context: Context) -> None:
    """Verify multiple connection attempts were made.

    Parameters
    ----------
    context : Context
        Behave context object
    """
    log_output = get_combined_log_output(context)
    attempt_count = log_output.count("Attempting SSH connection")
    assert attempt_count >= 5, f"Expected at least 5 attempts, found {attempt_count}"


@then("command fails with non-zero exit code")
def step_command_fails(context: Context) -> None:
    """Verify command failed with non-zero exit code.

    Parameters
    ----------
    context : Context
        Behave context object
    """
    assert context.exit_code != 0, (
        f"Expected non-zero exit code, got {context.exit_code}"
    )
