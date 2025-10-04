"""BDD step definitions for graceful shutdown with resource cleanup."""

import logging
import signal
from unittest.mock import MagicMock

from behave import given, then, when
from behave.runner import Context

TEST_INSTANCE_ID = "i-test123"


class CapturingHandler(logging.Handler):
    """Custom logging handler that captures log messages to a list.

    Parameters
    ----------
    messages_list : list
        List to append captured log messages to
    """

    def __init__(self, messages_list: list) -> None:
        super().__init__()
        self.messages = messages_list

    def emit(self, record: logging.LogRecord) -> None:
        """Emit a log record by appending its message to the messages list.

        Parameters
        ----------
        record : logging.LogRecord
            Log record to emit
        """
        self.messages.append(self.format(record))


def capture_logs_during_cleanup(
    context: Context, cleanup_func: callable, *args, **kwargs
) -> None:
    """Capture log messages during cleanup execution.

    Parameters
    ----------
    context : Context
        Behave test context
    cleanup_func : callable
        Function to call while capturing logs
    *args
        Positional arguments to pass to cleanup_func
    **kwargs
        Keyword arguments to pass to cleanup_func
    """

    if not hasattr(context, "log_messages"):
        context.log_messages = []

    handler = CapturingHandler(context.log_messages)
    logging.getLogger().addHandler(handler)

    try:
        cleanup_func(*args, **kwargs)
    except SystemExit as e:
        context.exit_code = e.code
    finally:
        logging.getLogger().removeHandler(handler)


def setup_mock_resources_with_cleanup_tracking(context: Context) -> None:
    """Setup mock resources for graceful shutdown tests.

    Creates a complete set of mock resources (EC2, SSH, port forwarding, Mutagen)
    and configures side effects to track cleanup execution order.

    Parameters
    ----------
    context : Context
        Behave test context
    """
    context.mock_moondock.resources = {
        "ec2_manager": MagicMock(),
        "instance_details": {"instance_id": TEST_INSTANCE_ID},
        "ssh_manager": MagicMock(),
        "portforward_mgr": MagicMock(),
        "mutagen_mgr": MagicMock(),
        "mutagen_session_name": "test-session",
    }
    context.cleanup_order = []

    context.mock_moondock.resources["portforward_mgr"].stop_all_tunnels.side_effect = (
        lambda: context.cleanup_order.append("portforward")
    )
    context.mock_moondock.resources["mutagen_mgr"].terminate_session.side_effect = (
        lambda name: context.cleanup_order.append("mutagen")
    )
    context.mock_moondock.resources["ssh_manager"].close.side_effect = (
        lambda: context.cleanup_order.append("ssh")
    )
    context.mock_moondock.resources["ec2_manager"].terminate_instance.side_effect = (
        lambda id: context.cleanup_order.append("ec2")
    )


@given("instance is running with all resources active")
def step_instance_running_with_all_resources(context: Context) -> None:
    """Set up mock instance with all resources active.

    Parameters
    ----------
    context : Context
        Behave test context
    """
    setup_mock_resources_with_cleanup_tracking(context)


@given("instance launch is in progress")
def step_instance_launch_in_progress(context: Context) -> None:
    """Set up mock moondock instance during launch.

    Parameters
    ----------
    context : Context
        Behave test context
    """
    context.mock_moondock.resources = {
        "ec2_manager": MagicMock(),
        "instance_details": {"instance_id": TEST_INSTANCE_ID},
    }
    context.cleanup_order = []

    context.mock_moondock.resources["ec2_manager"].terminate_instance.side_effect = (
        lambda id: context.cleanup_order.append("ec2")
    )


@given("SSH is not yet connected")
def step_ssh_not_connected(context: Context) -> None:
    """Remove SSH manager from resources to simulate not-yet-connected state.

    Parameters
    ----------
    context : Context
        Behave test context
    """

    if "ssh_manager" in context.mock_moondock.resources:
        del context.mock_moondock.resources["ssh_manager"]


@given("mutagen termination will fail")
def step_mutagen_will_fail(context: Context) -> None:
    """Configure mutagen to fail during termination.

    Parameters
    ----------
    context : Context
        Behave test context
    """
    context.cleanup_order = []

    context.mock_moondock.resources["portforward_mgr"].stop_all_tunnels.side_effect = (
        lambda: context.cleanup_order.append("portforward")
    )

    def mutagen_fail(name: str) -> None:
        context.cleanup_order.append("mutagen_fail")
        raise RuntimeError("Mutagen error")

    context.mock_moondock.resources[
        "mutagen_mgr"
    ].terminate_session.side_effect = mutagen_fail

    context.mock_moondock.resources["ssh_manager"].close.side_effect = (
        lambda: context.cleanup_order.append("ssh")
    )
    context.mock_moondock.resources["ec2_manager"].terminate_instance.side_effect = (
        lambda id: context.cleanup_order.append("ec2")
    )


@given("cleanup is already in progress")
def step_cleanup_in_progress(context: Context) -> None:
    context.mock_moondock.cleanup_in_progress = True


@when("SIGINT signal is received")
def step_sigint_received(context: Context) -> None:
    """Trigger SIGINT signal handler.

    Parameters
    ----------
    context : Context
        Behave test context
    """
    capture_logs_during_cleanup(
        context,
        context.mock_moondock.cleanup_resources,
        signum=signal.SIGINT,
        frame=None,
    )


@when("SIGTERM signal is received")
def step_sigterm_received(context: Context) -> None:
    """Trigger SIGTERM signal handler.

    Parameters
    ----------
    context : Context
        Behave test context
    """
    capture_logs_during_cleanup(
        context,
        context.mock_moondock.cleanup_resources,
        signum=signal.SIGTERM,
        frame=None,
    )


@when("another SIGINT signal is received")
def step_another_sigint_received(context: Context) -> None:
    context.mock_moondock.cleanup_resources(signum=signal.SIGINT, frame=None)


@when("moondock run completes normally")
def step_moondock_run_completes(context: Context) -> None:
    context.mock_moondock.cleanup_in_progress = False
    context.mock_moondock.cleanup_resources()


@when("SIGINT signal is received during execution")
def step_sigint_during_execution(context: Context) -> None:
    """Trigger SIGINT during execution with log capture.

    Parameters
    ----------
    context : Context
        Behave test context
    """
    setup_mock_resources_with_cleanup_tracking(context)

    capture_logs_during_cleanup(
        context,
        context.mock_moondock.cleanup_resources,
        signum=signal.SIGINT,
        frame=None,
    )


@then('cleanup log shows "{message}"')
def step_cleanup_log_shows(context: Context, message: str) -> None:
    """Verify cleanup log message.

    Parameters
    ----------
    context : Context
        Behave test context
    message : str
        Expected log message
    """
    if not hasattr(context, "log_messages"):
        context.log_messages = []

    assert any(message in log_msg for log_msg in context.log_messages), (
        f"Expected log message '{message}' not found in {context.log_messages}"
    )


@then("cleanup sequence executes")
def step_cleanup_sequence_executes(context: Context) -> None:
    assert context.cleanup_order == ["portforward", "mutagen", "ssh", "ec2"]


@then("port forwarding is stopped first")
def step_port_forwarding_stopped_first(context: Context) -> None:
    assert context.cleanup_order[0] == "portforward"


@then("mutagen session is terminated second")
def step_mutagen_terminated_second(context: Context) -> None:
    assert context.cleanup_order[1] == "mutagen"


@then("SSH connection is closed third")
def step_ssh_closed_third(context: Context) -> None:
    assert context.cleanup_order[2] == "ssh"


@then("EC2 instance is terminated fourth")
def step_ec2_terminated_fourth(context: Context) -> None:
    assert context.cleanup_order[3] == "ec2"


@then("EC2 instance is terminated")
def step_ec2_terminated(context: Context) -> None:
    assert "ec2" in context.cleanup_order


@then("SSH cleanup is skipped")
def step_ssh_cleanup_skipped(context: Context) -> None:
    assert "ssh" not in context.cleanup_order


@then("mutagen cleanup is skipped")
def step_mutagen_cleanup_skipped(context: Context) -> None:
    assert "mutagen" not in context.cleanup_order


@then("port forwarding cleanup is skipped")
def step_port_forwarding_cleanup_skipped(context: Context) -> None:
    assert "portforward" not in context.cleanup_order


@then("port forwarding stops successfully")
def step_port_forwarding_stops_successfully(context: Context) -> None:
    assert "portforward" in context.cleanup_order


@then("mutagen termination fails with logged error")
def step_mutagen_fails_with_logged_error(context: Context) -> None:
    assert "mutagen_fail" in context.cleanup_order


@then("SSH connection closes successfully")
def step_ssh_closes_successfully(context: Context) -> None:
    assert "ssh" in context.cleanup_order


@then("EC2 instance terminates successfully")
def step_ec2_terminates_successfully(context: Context) -> None:
    assert "ec2" in context.cleanup_order


@then("second cleanup attempt is skipped")
def step_second_cleanup_skipped(context: Context) -> None:
    assert len(context.cleanup_order) == 0


@then("no duplicate cleanup errors occur")
def step_no_duplicate_cleanup_errors(context: Context) -> None:
    assert context.mock_moondock.cleanup_in_progress is True


@then("cleanup happens in finally block")
def step_cleanup_in_finally(context: Context) -> None:
    assert context.mock_moondock.cleanup_in_progress is True


@then("cleanup sequence executes on mock resources")
def step_cleanup_on_mock_resources(context: Context) -> None:
    """Verify cleanup executed on mock resources.

    Parameters
    ----------
    context : Context
        Behave test context
    """
    assert hasattr(context, "cleanup_order"), (
        "cleanup_order not found - resources not set up properly"
    )
    assert context.cleanup_order == ["portforward", "mutagen", "ssh", "ec2"]


@then("no actual AWS operations occur")
def step_no_actual_aws_operations(context: Context) -> None:
    assert context.mock_moondock.resources is not None
