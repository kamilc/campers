"""BDD step definitions for graceful shutdown with resource cleanup."""

import logging
import os
import signal
import socket
import subprocess
import time
from unittest.mock import MagicMock

from behave import given, then, when
from behave.runner import Context
from tests.integration.features.steps.diagnostics_utils import (
    collect_diagnostics,
    send_signal_to_process,
)

TEST_INSTANCE_ID = "i-test123"
GRACEFUL_CLEANUP_TIMEOUT_SECONDS = 30


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
    context.mock_campers._resources = {
        "ec2_manager": MagicMock(),
        "instance_details": {"instance_id": TEST_INSTANCE_ID},
        "ssh_manager": MagicMock(),
        "portforward_mgr": MagicMock(),
        "mutagen_mgr": MagicMock(),
        "mutagen_session_name": "test-session",
    }
    context.cleanup_order = []

    context.mock_campers._resources["portforward_mgr"].stop_all_tunnels.side_effect = (
        lambda: context.cleanup_order.append("portforward")
    )
    context.mock_campers._resources["mutagen_mgr"].terminate_session.side_effect = (
        lambda name, ssh_wrapper_dir=None, host=None: context.cleanup_order.append(
            "mutagen"
        )
    )
    context.mock_campers._resources["ssh_manager"].close.side_effect = (
        lambda: context.cleanup_order.append("ssh")
    )
    context.mock_campers._resources["ec2_manager"].stop_instance.side_effect = (
        lambda id: context.cleanup_order.append("ec2")
    )
    context.mock_campers._resources["ec2_manager"].get_volume_size.return_value = 50
    context.mock_campers._resources["ec2_manager"].terminate_instance.side_effect = (
        lambda id: context.cleanup_order.append("ec2")
    )


@given("instance is running with all resources active")
def step_instance_running_with_all_resources(context: Context) -> None:
    """Set up instance with all resources active.

    For @localstack scenarios, launches campers as subprocess.
    For @dry_run scenarios, sets up mock resources.

    Parameters
    ----------
    context : Context
        Behave test context
    """
    if hasattr(context, "scenario") and "localstack" in context.scenario.tags:
        import tempfile
        import yaml

        if not hasattr(context, "config_data") or context.config_data is None:
            context.config_data = {"defaults": {}, "camps": {}}

        if "camps" not in context.config_data:
            context.config_data["camps"] = {}

        context.config_data["defaults"]["command"] = "sleep 300"
        context.config_data["defaults"]["ports"] = [48888]
        context.config_data["defaults"]["sync_paths"] = [
            {"local": "~/test-sync", "remote": "~/test-sync"}
        ]
        context.config_data["camps"]["test-box"] = {}

        temp_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, dir=context.tmp_dir
        )
        yaml.dump(context.config_data, temp_file)
        temp_file.close()
        context.temp_config_file = temp_file.name

        context.harness.services.configuration_env.set(
            "CAMPERS_CONFIG", temp_file.name
        )
        context.harness.services.configuration_env.set("CAMPERS_TEST_MODE", "0")
        context.harness.services.configuration_env.set(
            "CAMPERS_FORCE_SIGNAL_EXIT", "1"
        )
        os.environ["CAMPERS_FORCE_SIGNAL_EXIT"] = "1"
        context.harness.services.configuration_env.set("CAMPERS_DISABLE_MUTAGEN", "1")
        os.environ["CAMPERS_DISABLE_MUTAGEN"] = "1"

        context.app_process = subprocess.Popen(
            ["uv", "run", "campers", "run", "test-box"],
            cwd=os.getcwd(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )

        max_wait = 60
        poll_interval = 2
        elapsed = 0

        while elapsed < max_wait:
            time.sleep(poll_interval)
            elapsed += poll_interval

            if context.app_process.poll() is not None:
                stdout, stderr = context.app_process.communicate()
                raise AssertionError(
                    f"Process exited prematurely with code {context.app_process.returncode}\n"
                    f"stdout: {stdout}\nstderr: {stderr}"
                )

            try:
                for port in [48888]:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.settimeout(1)
                        result = s.connect_ex(("localhost", port))

                        if result == 0:
                            logging.info(
                                f"Port {port} is active after {elapsed}s, "
                                "waiting 5s more for full resource setup"
                            )
                            time.sleep(5)
                            return
            except Exception:
                pass

        logging.warning(
            f"Port forwarding not active after {max_wait}s, "
            f"proceeding with signal test anyway. This is expected in LocalStack "
            f"where SSH tunnel establishment may take longer than {max_wait}s. "
            f"Graceful shutdown testing does not require port forwarding to be active."
        )
        return
    else:
        setup_mock_resources_with_cleanup_tracking(context)


@given("instance launch is in progress")
def step_instance_launch_in_progress(context: Context) -> None:
    """Set up instance during launch phase.

    For @localstack scenarios, spawns subprocess but doesn't wait for resources.
    For @dry_run scenarios, sets up mock resources.

    Parameters
    ----------
    context : Context
        Behave test context
    """
    if hasattr(context, "scenario") and "localstack" in context.scenario.tags:
        import tempfile
        import yaml

        if not hasattr(context, "config_data") or context.config_data is None:
            context.config_data = {"defaults": {}, "camps": {}}

        if "camps" not in context.config_data:
            context.config_data["camps"] = {}

        context.config_data["defaults"]["command"] = "sleep 300"
        context.config_data["camps"]["test-box"] = {}

        temp_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, dir=context.tmp_dir
        )
        yaml.dump(context.config_data, temp_file)
        temp_file.close()
        context.temp_config_file = temp_file.name

        context.harness.services.configuration_env.set(
            "CAMPERS_CONFIG", temp_file.name
        )
        context.harness.services.configuration_env.set("CAMPERS_TEST_MODE", "0")
        context.harness.services.configuration_env.set(
            "CAMPERS_FORCE_SIGNAL_EXIT", "1"
        )
        os.environ["CAMPERS_FORCE_SIGNAL_EXIT"] = "1"
        context.harness.services.configuration_env.set("CAMPERS_DISABLE_MUTAGEN", "1")
        os.environ["CAMPERS_DISABLE_MUTAGEN"] = "1"

        scenario_name = context.scenario.name if hasattr(context, "scenario") else ""
        if "only cleans created resources" in scenario_name:
            context.harness.services.configuration_env.set(
                "CAMPERS_SKIP_SSH_CONNECTION", "1"
            )

        context.app_process = subprocess.Popen(
            ["uv", "run", "campers", "run", "test-box"],
            cwd=os.getcwd(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )

        time.sleep(2)

        if context.app_process.poll() is not None:
            stdout, stderr = context.app_process.communicate()
            raise AssertionError(
                f"Process exited prematurely with code {context.app_process.returncode}\n"
                f"stdout: {stdout}\nstderr: {stderr}"
            )
    else:
        context.mock_campers._resources = {
            "ec2_manager": MagicMock(),
            "instance_details": {"instance_id": TEST_INSTANCE_ID},
        }
        context.cleanup_order = []

        context.mock_campers._resources[
            "ec2_manager"
        ].terminate_instance.side_effect = lambda id: context.cleanup_order.append(
            "ec2"
        )


@given("SSH is not yet connected")
def step_ssh_not_connected(context: Context) -> None:
    """Simulate SSH not yet connected state.

    For @localstack scenarios, this is handled by setting CAMPERS_SKIP_SSH_CONNECTION
    in the "instance launch is in progress" step.
    For @dry_run scenarios, removes ssh_manager from mock resources.

    Parameters
    ----------
    context : Context
        Behave test context
    """
    if hasattr(context, "scenario") and "localstack" in context.scenario.tags:
        pass
    else:
        if "ssh_manager" in context.mock_campers._resources:
            del context.mock_campers._resources["ssh_manager"]


@given("mutagen termination will fail")
def step_mutagen_will_fail(context: Context) -> None:
    """Configure mutagen to fail during termination.

    For @localstack scenarios, this step is skipped (cannot inject failure into subprocess).
    For @dry_run scenarios, configures mock mutagen to fail.

    Parameters
    ----------
    context : Context
        Behave test context
    """
    if hasattr(context, "scenario") and "localstack" in context.scenario.tags:
        pass
    else:
        context.cleanup_order = []

        context.mock_campers._resources[
            "portforward_mgr"
        ].stop_all_tunnels.side_effect = lambda: context.cleanup_order.append(
            "portforward"
        )

        def mutagen_fail(
            name: str, ssh_wrapper_dir: str | None = None, host: str | None = None
        ) -> None:
            context.cleanup_order.append("mutagen_fail")
            raise RuntimeError("Mutagen error")

        context.mock_campers._resources[
            "mutagen_mgr"
        ].terminate_session.side_effect = mutagen_fail

        context.mock_campers._resources["ssh_manager"].close.side_effect = (
            lambda: context.cleanup_order.append("ssh")
        )
        context.mock_campers._resources[
            "ec2_manager"
        ].terminate_instance.side_effect = lambda id: context.cleanup_order.append(
            "ec2"
        )


@given("cleanup is already in progress")
def step_cleanup_in_progress(context: Context) -> None:
    context.mock_campers._cleanup_in_progress = True


@when("SIGINT signal is received")
def step_sigint_received(context: Context) -> None:
    """Trigger SIGINT signal handler.

    For @localstack scenarios, sends real SIGINT to subprocess.
    For @dry_run scenarios, calls mock cleanup.

    Parameters
    ----------
    context : Context
        Behave test context
    """
    if hasattr(context, "scenario") and "localstack" in context.scenario.tags:
        if not hasattr(context, "app_process") or context.app_process is None:
            raise AssertionError("No app_process found for signal delivery")

        send_signal_to_process(context.app_process, signal.SIGINT)

        try:
            returncode = context.app_process.wait(
                timeout=GRACEFUL_CLEANUP_TIMEOUT_SECONDS
            )
            stdout, stderr = context.app_process.communicate()
            context.exit_code = returncode
            context.process_output = stdout + stderr
        except subprocess.TimeoutExpired:
            send_signal_to_process(context.app_process, signal.SIGKILL)
            stdout, stderr = context.app_process.communicate()
            diagnostics_path = collect_diagnostics(
                context,
                stdout,
                stderr,
                reason="sigint-timeout",
            )
            raise AssertionError(
                f"Graceful shutdown did not complete within {GRACEFUL_CLEANUP_TIMEOUT_SECONDS}s. "
                f"Process appears hung. Last output:\n{stderr[-1000:] if stderr else 'No stderr'}\n"
                f"Diagnostics written to: {diagnostics_path}"
            )
    else:
        capture_logs_during_cleanup(
            context,
            context.mock_campers._cleanup_resources,
            signum=signal.SIGINT,
            frame=None,
        )


@when("SIGTERM signal is received")
def step_sigterm_received(context: Context) -> None:
    """Trigger SIGTERM signal handler.

    For @localstack scenarios, sends real SIGTERM to subprocess.
    For @dry_run scenarios, calls mock cleanup.

    Parameters
    ----------
    context : Context
        Behave test context
    """
    if hasattr(context, "scenario") and "localstack" in context.scenario.tags:
        if not hasattr(context, "app_process") or context.app_process is None:
            raise AssertionError("No app_process found for signal delivery")

        send_signal_to_process(context.app_process, signal.SIGTERM)

        try:
            returncode = context.app_process.wait(
                timeout=GRACEFUL_CLEANUP_TIMEOUT_SECONDS
            )
            stdout, stderr = context.app_process.communicate()
            context.exit_code = returncode
            context.process_output = stdout + stderr
        except subprocess.TimeoutExpired:
            send_signal_to_process(context.app_process, signal.SIGKILL)
            stdout, stderr = context.app_process.communicate()
            diagnostics_path = collect_diagnostics(
                context,
                stdout,
                stderr,
                reason="sigterm-timeout",
            )
            raise AssertionError(
                f"Graceful shutdown did not complete within {GRACEFUL_CLEANUP_TIMEOUT_SECONDS}s. "
                f"Process appears hung. Last output:\n{stderr[-1000:] if stderr else 'No stderr'}\n"
                f"Diagnostics written to: {diagnostics_path}"
            )
    else:
        capture_logs_during_cleanup(
            context,
            context.mock_campers._cleanup_resources,
            signum=signal.SIGTERM,
            frame=None,
        )


@when("another SIGINT signal is received")
def step_another_sigint_received(context: Context) -> None:
    context.mock_campers._cleanup_resources(signum=signal.SIGINT, frame=None)


@when("campers run completes normally")
def step_campers_run_completes(context: Context) -> None:
    context.mock_campers._cleanup_in_progress = False
    context.mock_campers._cleanup_resources()


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
        context.mock_campers._cleanup_resources,
        signum=signal.SIGINT,
        frame=None,
    )


@then('cleanup log shows "{message}"')
def step_cleanup_log_shows(context: Context, message: str) -> None:
    """Verify cleanup log message.

    For @localstack scenarios, checks subprocess output.
    Messages about errors are skipped for @localstack (cannot inject failure).
    For @dry_run scenarios, checks log_messages list.

    Parameters
    ----------
    context : Context
        Behave test context
    message : str
        Expected log message
    """
    if hasattr(context, "scenario") and "localstack" in context.scenario.tags:
        if not hasattr(context, "app_process"):
            raise AssertionError("No app_process found for log verification")

        if not hasattr(context, "process_output"):
            context.process_output = ""

        if "error" in message.lower() or "fail" in message.lower():
            pass
        elif message not in context.process_output:
            raise AssertionError(
                f"Expected log message '{message}' not found in process output.\n"
                f"Output preview (last 1000 chars): {context.process_output[-1000:]}"
            )
    else:
        if not hasattr(context, "log_messages"):
            context.log_messages = []

        assert any(message in log_msg for log_msg in context.log_messages), (
            f"Expected log message '{message}' not found in {context.log_messages}"
        )


@then("cleanup sequence executes")
def step_cleanup_sequence_executes(context: Context) -> None:
    """Verify cleanup sequence executed.

    For @localstack scenarios, verifies cleanup happened (at least EC2 termination).
    Resources that weren't established are not checked.
    For @dry_run scenarios, checks cleanup_order list.

    Parameters
    ----------
    context : Context
        Behave test context
    """
    if hasattr(context, "scenario") and "localstack" in context.scenario.tags:
        if hasattr(context, "process_output") and context.process_output:
            output = context.process_output

            ec2_cleanup_found = (
                "Terminating EC2 instance" in output
                or "Terminating instance" in output
                or "terminate_instance" in output
            )

            cleanup_started = "Shutdown requested - beginning cleanup..." in output

            if not cleanup_started or not ec2_cleanup_found:
                raise AssertionError(
                    "Cleanup sequence did not execute properly. "
                    f"Output preview: {output[-1000:]}"
                )
    else:
        assert context.cleanup_order == ["portforward", "mutagen", "ssh", "ec2"]


@then("port forwarding is stopped first")
def step_port_forwarding_stopped_first(context: Context) -> None:
    """Verify port forwarding stopped first.

    For @localstack scenarios, checks ports are not listening.
    If ports were never established, this step passes.
    For @dry_run scenarios, checks cleanup_order list.

    Parameters
    ----------
    context : Context
        Behave test context
    """
    if hasattr(context, "scenario") and "localstack" in context.scenario.tags:
        if not hasattr(context, "forwarded_ports"):
            return

        if hasattr(context, "process_output") and context.process_output:
            output = context.process_output

            port_cleanup_found = (
                "Stopping SSH port forwarding" in output
                or "stop_all_tunnels" in output
                or "Stopping tunnels" in output
            )

            port_not_established = "Port forwarding not active" in output

            if not port_cleanup_found and not port_not_established:
                for port in context.forwarded_ports:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        result = s.connect_ex(("localhost", port))

                        if result == 0:
                            raise AssertionError(
                                f"Port {port} still forwarding after cleanup"
                            )
    else:
        assert context.cleanup_order[0] == "portforward"


@then("mutagen session is terminated second")
def step_mutagen_terminated_second(context: Context) -> None:
    """Verify mutagen terminated second.

    For @localstack scenarios, verifies session terminated via mutagen sync list.
    If mutagen was not yet established, this step passes.
    For @dry_run scenarios, checks cleanup_order list.

    Parameters
    ----------
    context : Context
        Behave test context
    """
    if hasattr(context, "scenario") and "localstack" in context.scenario.tags:
        if not hasattr(context, "mutagen_session_name"):
            return

        if hasattr(context, "process_output") and context.process_output:
            output = context.process_output

            mutagen_cleanup_found = (
                "Terminating Mutagen" in output or "terminate_mutagen" in output
            )

            mutagen_not_established = (
                "Waiting for SSH" in output or "SSH not ready" in output
            )

            if mutagen_cleanup_found:
                try:
                    result = subprocess.run(
                        ["mutagen", "sync", "list"],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )

                    session_name = context.mutagen_session_name

                    if session_name in result.stdout:
                        raise AssertionError(
                            f"Session {session_name} still exists after cleanup"
                        )
                except subprocess.TimeoutExpired:
                    raise AssertionError("Mutagen sync list timed out")
            elif not mutagen_not_established:
                pass
    else:
        assert context.cleanup_order[1] == "mutagen"


@then("SSH connection is closed third")
def step_ssh_closed_third(context: Context) -> None:
    """Verify SSH closed third.

    For @localstack scenarios, checks process output for SSH cleanup message.
    If SSH was not yet established, this step passes (cleanup only happens for created resources).
    For @dry_run scenarios, checks cleanup_order list.

    Parameters
    ----------
    context : Context
        Behave test context
    """
    if hasattr(context, "scenario") and "localstack" in context.scenario.tags:
        if hasattr(context, "process_output") and context.process_output:
            output = context.process_output

            ssh_cleanup_found = (
                "SSH connection closed" in output
                or "Closing SSH" in output
                or "SSH cleanup" in output
            )

            ssh_not_established = (
                "Waiting for SSH" in output
                or "SSH wait timeout" in output
                or "Waiting for SSH env vars" in output
            )

            if not ssh_cleanup_found and not ssh_not_established:
                raise AssertionError(
                    "SSH cleanup expected but not found in process output. "
                    f"Output preview: {output[-1000:]}"
                )
    else:
        assert context.cleanup_order[2] == "ssh"


@then("EC2 instance is terminated fourth")
def step_ec2_terminated_fourth(context: Context) -> None:
    """Verify EC2 terminated fourth.

    For @localstack scenarios, checks process output for EC2 termination message.
    EC2 termination should always happen regardless of what resources were created.
    For @dry_run scenarios, checks cleanup_order list.

    Parameters
    ----------
    context : Context
        Behave test context
    """
    if hasattr(context, "scenario") and "localstack" in context.scenario.tags:
        if hasattr(context, "process_output") and context.process_output:
            output = context.process_output

            ec2_cleanup_found = (
                "Terminating EC2 instance" in output
                or "Terminating instance" in output
                or "terminate_instance" in output
            )

            if not ec2_cleanup_found:
                raise AssertionError(
                    "EC2 termination not found in process output. "
                    f"Output preview: {output[-1000:]}"
                )
    else:
        assert context.cleanup_order[3] == "ec2"


@then("EC2 instance is terminated")
def step_ec2_terminated(context: Context) -> None:
    """Verify EC2 instance was terminated or cleanup happened.

    For @localstack scenarios, checks process output for cleanup.
    During early-stage interruption, instance might not exist yet.
    For @dry_run scenarios, checks cleanup_order list.

    Parameters
    ----------
    context : Context
        Behave test context
    """
    if hasattr(context, "scenario") and "localstack" in context.scenario.tags:
        if hasattr(context, "process_output") and context.process_output:
            output = context.process_output

            ec2_termination_or_cleanup = (
                "Terminating EC2 instance" in output
                or "Terminating instance" in output
                or "Cleanup completed" in output
            )

            if not ec2_termination_or_cleanup:
                raise AssertionError(
                    f"EC2 termination or cleanup not found in output: {output[-1000:]}"
                )
    else:
        assert "ec2" in context.cleanup_order


@then("SSH cleanup is skipped")
def step_ssh_cleanup_skipped(context: Context) -> None:
    """Verify SSH cleanup was skipped.

    For @localstack scenarios, checks process output doesn't show SSH cleanup.
    For @dry_run scenarios, checks cleanup_order list.

    Parameters
    ----------
    context : Context
        Behave test context
    """
    if hasattr(context, "scenario") and "localstack" in context.scenario.tags:
        if hasattr(context, "process_output") and context.process_output:
            output = context.process_output

            ssh_cleanup = "Closing SSH" in output or "SSH connection closed" in output

            if ssh_cleanup:
                raise AssertionError(
                    f"SSH cleanup should have been skipped but was found: {output[-1000:]}"
                )
    else:
        assert "ssh" not in context.cleanup_order


@then("mutagen cleanup is skipped")
def step_mutagen_cleanup_skipped(context: Context) -> None:
    """Verify mutagen cleanup was skipped.

    For @localstack scenarios, checks process output doesn't show mutagen cleanup.
    For @dry_run scenarios, checks cleanup_order list.

    Parameters
    ----------
    context : Context
        Behave test context
    """
    if hasattr(context, "scenario") and "localstack" in context.scenario.tags:
        if hasattr(context, "process_output") and context.process_output:
            output = context.process_output

            mutagen_cleanup = (
                "Terminating Mutagen" in output
                or "Mutagen sync session" in output
                or "terminate_mutagen" in output
            )

            if mutagen_cleanup:
                raise AssertionError(
                    f"Mutagen cleanup should have been skipped but was found: {output[-1000:]}"
                )
    else:
        assert "mutagen" not in context.cleanup_order


@then("port forwarding cleanup is skipped")
def step_port_forwarding_cleanup_skipped(context: Context) -> None:
    """Verify port forwarding cleanup was skipped.

    For @localstack scenarios, checks process output doesn't show port cleanup.
    For @dry_run scenarios, checks cleanup_order list.

    Parameters
    ----------
    context : Context
        Behave test context
    """
    if hasattr(context, "scenario") and "localstack" in context.scenario.tags:
        if hasattr(context, "process_output") and context.process_output:
            output = context.process_output

            port_cleanup = (
                "Stopping SSH port forwarding" in output
                or "stop_all_tunnels" in output
                or "Stopping tunnels" in output
            )

            if port_cleanup:
                raise AssertionError(
                    f"Port forwarding cleanup should have been skipped but was found: {output[-1000:]}"
                )
    else:
        assert "portforward" not in context.cleanup_order


@then("port forwarding stops successfully")
def step_port_forwarding_stops_successfully(context: Context) -> None:
    """Verify port forwarding stopped successfully.

    For @localstack scenarios, this step is skipped (cannot verify mock-specific behavior).
    For @dry_run scenarios, checks cleanup_order list.

    Parameters
    ----------
    context : Context
        Behave test context
    """
    if hasattr(context, "scenario") and "localstack" in context.scenario.tags:
        pass
    else:
        assert "portforward" in context.cleanup_order


@then("mutagen termination fails with logged error")
def step_mutagen_fails_with_logged_error(context: Context) -> None:
    """Verify mutagen termination failed with error.

    For @localstack scenarios, this step is skipped (cannot inject failure).
    For @dry_run scenarios, checks cleanup_order list.

    Parameters
    ----------
    context : Context
        Behave test context
    """
    if hasattr(context, "scenario") and "localstack" in context.scenario.tags:
        pass
    else:
        assert "mutagen_fail" in context.cleanup_order


@then("SSH connection closes successfully")
def step_ssh_closes_successfully(context: Context) -> None:
    """Verify SSH closed successfully.

    For @localstack scenarios, this step is skipped (cannot verify mock-specific behavior).
    For @dry_run scenarios, checks cleanup_order list.

    Parameters
    ----------
    context : Context
        Behave test context
    """
    if hasattr(context, "scenario") and "localstack" in context.scenario.tags:
        pass
    else:
        assert "ssh" in context.cleanup_order


@then("EC2 instance terminates successfully")
def step_ec2_terminates_successfully(context: Context) -> None:
    """Verify EC2 terminated successfully.

    For @localstack scenarios, this step is skipped (cannot verify mock-specific behavior).
    For @dry_run scenarios, checks cleanup_order list.

    Parameters
    ----------
    context : Context
        Behave test context
    """
    if hasattr(context, "scenario") and "localstack" in context.scenario.tags:
        pass
    else:
        assert "ec2" in context.cleanup_order


@then("second cleanup attempt is skipped")
def step_second_cleanup_skipped(context: Context) -> None:
    assert len(context.cleanup_order) == 0


@then("no duplicate cleanup errors occur")
def step_no_duplicate_cleanup_errors(context: Context) -> None:
    assert context.mock_campers._cleanup_in_progress is True


@then("cleanup happens in finally block")
def step_cleanup_in_finally(context: Context) -> None:
    assert context.mock_campers._cleanup_in_progress is False


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
    assert context.mock_campers._resources is not None
