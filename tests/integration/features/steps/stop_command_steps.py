"""BDD step definitions for stop command."""

import logging
import sys
from datetime import datetime, timezone
from io import StringIO
from unittest.mock import patch

from behave import given, then, when
from behave.runner import Context
from botocore.exceptions import ClientError

from campers.ec2 import ACTIVE_INSTANCE_STATES


@given('running instance "{instance_id}" with CampConfig "{camp_config}"')
def step_running_instance_with_camp_config(
    context: Context, instance_id: str, camp_config: str
) -> None:
    """Create a running instance with specific machine config."""
    if context.instances is None:
        context.instances = []

    instance = {
        "instance_id": instance_id,
        "name": f"campers-{instance_id}",
        "state": "running",
        "region": "us-east-1",
        "instance_type": "t3.medium",
        "launch_time": datetime.now(timezone.utc),
        "camp_config": camp_config,
    }

    context.instances.append(instance)


@given('running instance "{instance_id}" with MachineConfig "{machine_config}"')
def step_running_instance_with_machine_config(
    context: Context, instance_id: str, machine_config: str
) -> None:
    """Create a running instance with specific machine config."""
    if context.instances is None:
        context.instances = []

    instance = {
        "instance_id": instance_id,
        "name": f"campers-{instance_id}",
        "state": "running",
        "region": "us-east-1",
        "instance_type": "t3.medium",
        "launch_time": datetime.now(timezone.utc),
        "camp_config": machine_config,
    }

    context.instances.append(instance)


@given("terminate_instance raises RuntimeError")
def step_terminate_raises_runtime_error(context: Context) -> None:
    """Configure terminate_instance to raise RuntimeError."""
    context.terminate_runtime_error = RuntimeError(
        "Failed to terminate instance: Waiter InstanceTerminated failed"
    )


@given('terminate_instance raises ClientError "{error_code}"')
def step_terminate_raises_client_error(context: Context, error_code: str) -> None:
    """Configure terminate_instance to raise ClientError."""
    context.terminate_client_error = ClientError(
        {
            "Error": {
                "Code": error_code,
                "Message": f"Test error: {error_code}",
            }
        },
        "TerminateInstances",
    )


@given("user has AWS credentials with no EC2 permissions")
def step_user_has_no_ec2_permissions(context: Context) -> None:
    """Mock AWS credentials with no EC2 permissions."""
    if context.instances is None:
        context.instances = []

    context.aws_permission_error = ClientError(
        {
            "Error": {
                "Code": "UnauthorizedOperation",
                "Message": "You are not authorized to perform this operation.",
            }
        },
        "DescribeInstances",
    )


@when('I run stop command with "{name_or_id}"')
def step_run_stop_command(context: Context, name_or_id: str) -> None:
    """Run stop command with name or ID."""
    step_run_stop_command_impl(context, name_or_id, None)


@when('I run stop command with name or id "{name_or_id}" and region "{region}"')
def step_run_stop_command_with_region(
    context: Context, name_or_id: str, region: str
) -> None:
    """Run stop command with name or ID and region."""
    step_run_stop_command_impl(context, name_or_id, region)


def step_run_stop_command_impl(
    context: Context, name_or_id: str, region: str | None
) -> None:
    """Run stop command with name or ID and optional region."""
    campers = context.mock_campers

    actual_name_or_id = name_or_id

    if (
        context.state_test_instances is not None
        and name_or_id in context.state_test_instances
    ):
        actual_name_or_id = context.state_test_instances[name_or_id]["actual_id"]

    root_logger = logging.getLogger()
    root_logger.addHandler(context.log_handler)

    filtered_instances = [
        inst
        for inst in context.instances
        if inst.get("state") in ACTIVE_INSTANCE_STATES
    ]

    def mock_stop_instance_impl(instance_id: str):
        instance = next(
            (inst for inst in filtered_instances if inst["instance_id"] == instance_id),
            None,
        )
        if instance is None:
            return {}
        return {
            "instance_id": instance_id,
            "public_ip": None,
            "private_ip": None,
            "state": "stopped",
            "instance_type": instance.get("instance_type", "t3.medium"),
        }

    with patch("campers.ec2.EC2Manager.list_instances") as mock_list:
        if context.aws_permission_error is not None:
            mock_list.side_effect = context.aws_permission_error
        else:
            mock_list.return_value = filtered_instances

        with patch("campers.ec2.EC2Manager.stop_instance") as mock_stop:
            with patch("campers.ec2.EC2Manager.get_volume_size") as mock_get_volume:
                if context.terminate_runtime_error is not None:
                    mock_stop.side_effect = context.terminate_runtime_error
                elif context.terminate_client_error is not None:
                    mock_stop.side_effect = context.terminate_client_error
                else:
                    mock_stop.side_effect = mock_stop_instance_impl

                mock_get_volume.return_value = 50

                context.mock_terminate = mock_stop

                captured_stdout = StringIO()
                captured_stderr = StringIO()
                original_stdout = sys.stdout
                original_stderr = sys.stderr
                sys.stdout = captured_stdout
                sys.stderr = captured_stderr

                try:
                    if region:
                        campers.stop(actual_name_or_id, region=region)
                    else:
                        campers.stop(actual_name_or_id)

                    context.exit_code = 0
                except SystemExit as e:
                    context.exit_code = e.code
                except Exception as e:
                    context.exception = e
                    context.exit_code = 1
                finally:
                    sys.stdout = original_stdout
                    sys.stderr = original_stderr
                    context.stdout = captured_stdout.getvalue()
                    context.stderr = captured_stderr.getvalue()

                    log_messages = [
                        record.getMessage()
                        for record in context.log_records
                        if record.levelname in ("ERROR", "WARNING")
                    ]

                    error_parts = []
                    if log_messages:
                        error_parts.append("\n".join(log_messages))
                    if context.stderr:
                        error_parts.append(context.stderr)

                    if error_parts:
                        context.error = "\n".join(error_parts)

    root_logger.removeHandler(context.log_handler)


@then('instance "{instance_id}" is terminated')
def step_instance_is_terminated(context: Context, instance_id: str) -> None:
    """Verify stop command was called for the instance."""
    assert context.mock_terminate is not None
    assert context.mock_terminate.called

    call_args = context.mock_terminate.call_args
    assert call_args is not None

    called_instance_id = call_args[0][0]

    expected_instance_id = instance_id

    if (
        context.state_test_instances is not None
        and instance_id in context.state_test_instances
    ):
        expected_instance_id = context.state_test_instances[instance_id]["actual_id"]

    assert called_instance_id == expected_instance_id


@then("success message is printed to stdout")
def step_success_message_printed(context: Context) -> None:
    """Verify success message was printed to stdout."""
    assert "has been successfully stopped" in context.stdout


@then("command exits with status {expected_code:d}")
@then("command fails with exit code {expected_code:d}")
def step_command_exits_with_status(context: Context, expected_code: int) -> None:
    """Verify command exit code."""
    assert context.exit_code == expected_code


@then("error is printed to stderr")
def step_error_printed_to_stderr(context: Context) -> None:
    """Verify error was printed to stderr."""
    assert context.stderr.strip()


@then('disambiguation help lists instance IDs "{first_id}" and "{second_id}"')
def step_disambiguation_help_lists_ids(
    context: Context, first_id: str, second_id: str
) -> None:
    """Verify disambiguation help lists both instance IDs."""
    combined_output = context.stdout + context.stderr

    assert first_id in combined_output
    assert second_id in combined_output


@then("terminate_instance was not called")
def step_terminate_not_called(context: Context) -> None:
    """Verify terminate_instance was not called."""
    assert context.mock_terminate is not None
    assert not context.mock_terminate.called
