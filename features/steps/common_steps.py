"""Common step definitions shared across features."""

import io
import logging
import os
import signal
import subprocess
import sys
import unittest.mock
from pathlib import Path

from behave import given, then, when
from behave.runner import Context
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


def execute_command_direct(
    context: Context, command: str, args: dict | None = None, region: str | None = None
) -> None:
    """Execute moondock command via direct instantiation with mocked dependencies.

    Parameters
    ----------
    context : Context
        Behave context with patched_ec2_client and other test fixtures
    command : str
        Command name: doctor, setup, list, stop, run
    args : dict | None
        Additional command arguments (for commands like stop that take parameters)
    region : str | None
        AWS region to use (default: us-east-1)
    """
    from moondock.__main__ import Moondock
    from tests.fakes.fake_ec2_manager import FakeEC2Manager
    from tests.fakes.fake_ssh_manager import FakeSSHManager

    if region is None:
        region = "us-east-1"

    old_stdout, old_stderr = sys.stdout, sys.stderr
    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()
    sys.stdout = stdout_capture
    sys.stderr = stderr_capture

    root_logger = logging.getLogger()
    original_log_level = root_logger.level
    root_logger.setLevel(logging.INFO)

    def timeout_handler(signum, frame):
        raise TimeoutError(f"Command '{command}' execution timed out after 180 seconds")

    timeout_seconds = getattr(context, "scenario_timeout", 180)
    old_handler = signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(timeout_seconds)

    def mock_boto3_client_factory(service_name: str, region_name: str | None = None):
        ec2_client = getattr(context, "patched_ec2_client", None)
        if service_name == "ec2" and ec2_client is not None:
            return ec2_client
        elif service_name == "sts":
            import boto3

            return boto3.client(service_name, region_name=region_name)
        else:
            import boto3

            return boto3.client(service_name, region_name=region_name)

    try:
        moondock = Moondock(
            ec2_manager_factory=FakeEC2Manager,
            ssh_manager_factory=FakeSSHManager,
            boto3_client_factory=mock_boto3_client_factory,
        )

        ec2_client = getattr(context, "patched_ec2_client", None)

        if command == "doctor":
            moondock.doctor(region=region, ec2_client=ec2_client)
            context.exit_code = 0

        elif command == "setup":
            user_input = getattr(context, "setup_user_input", "n")

            def mocked_input(prompt: str = "") -> str:
                print(prompt, end="")
                return user_input

            with unittest.mock.patch("builtins.input", side_effect=mocked_input):
                moondock.setup(region=region, ec2_client=ec2_client)
            context.exit_code = 0

        elif command == "list":
            region = args.get("region") if args else None
            moondock.list(region=region)
            context.exit_code = 0

        elif command == "stop":
            if not args or "name_or_id" not in args:
                raise ValueError("stop command requires name_or_id argument")
            name_or_id = args["name_or_id"]
            region = args.get("region")
            moondock.stop(name_or_id=name_or_id, region=region)
            context.exit_code = 0

        elif command == "run":
            result = moondock.run(
                machine_name=args.get("machine_name") if args else None,
                command=args.get("command", "echo test") if args else "echo test",
                json_output=True,
                plain=True,
            )
            context.exit_code = 0
            if isinstance(result, dict) and "command_exit_code" in result:
                context.exit_code = result["command_exit_code"]

        elif command == "init":
            force = args.get("force", False) if args else False
            moondock.init(force=force)
            context.exit_code = 0

        else:
            raise ValueError(f"Unknown command: {command}")

    except SystemExit as e:
        context.exit_code = e.code if e.code is not None else 0
        if e.code not in (None, 0):
            stderr_capture.write(f"SystemExit: {e}\n")

    except KeyboardInterrupt:
        raise

    except (ValueError, RuntimeError, ClientError, TypeError, AttributeError) as e:
        context.exit_code = 1
        stderr_capture.write(f"Error: {str(e)}\n")
        context.error = str(e)
        context.exception = e
        logger.error("Command execution failed: %s", e, exc_info=True)

    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)
        sys.stdout = old_stdout
        sys.stderr = old_stderr
        root_logger.setLevel(original_log_level)
        context.stdout = stdout_capture.getvalue()
        context.stderr = stderr_capture.getvalue()
        stdout_capture.close()
        stderr_capture.close()


@given("AWS credentials are configured")
def step_aws_credentials_configured(context: Context) -> None:
    """AWS credentials are configured (handled by environment.py)."""
    pass


@given("running in real AWS mode")
def step_real_aws_mode(context: Context) -> None:
    """Disable test mode to test real AWS operations with moto.

    Parameters
    ----------
    context : Context
        Behave context
    """
    context.saved_env = os.environ.copy()


@given("AWS credentials are not configured")
def step_aws_credentials_not_configured(context: Context) -> None:
    """Remove AWS credentials from environment.

    Parameters
    ----------
    context : Context
        Behave context
    """
    context.saved_env = os.environ.copy()

    for key in ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"]:
        if key in os.environ:
            del os.environ[key]


@when('I run setup with input "{user_input}"')
def step_run_setup_with_input(context: Context, user_input: str) -> None:
    """Run moondock setup command with user input.

    Parameters
    ----------
    context : Context
        Behave context
    user_input : str
        User input to provide
    """
    if getattr(context, "use_direct_instantiation", False):
        context.setup_user_input = user_input
        return execute_command_direct(context, "setup")

    import boto3

    project_root = Path(__file__).parent.parent.parent

    env = os.environ.copy()

    ec2_client = boto3.client("ec2", region_name="us-east-1")
    vpcs = ec2_client.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}])
    vpc_exists = bool(vpcs.get("Vpcs", []))
    vpc_env_value = "true" if vpc_exists else "false"

    context.harness.services.configuration_env.set(
        "MOONDOCK_TEST_VPC_EXISTS", vpc_env_value
    )

    result = subprocess.run(
        ["uv", "run", "python", "-m", "moondock", "setup"],
        env=env,
        capture_output=True,
        text=True,
        input=f"{user_input}\n",
        cwd=project_root,
    )

    context.exit_code = result.returncode
    context.stdout = result.stdout
    context.stderr = result.stderr


@when("I run {command:w}")
def step_run_simple_command(context: Context, command: str) -> None:
    """Run moondock command without input.

    Parameters
    ----------
    context : Context
        Behave context
    command : str
        Command to run (e.g., "setup", "doctor", "run")
    """
    if getattr(context, "use_direct_instantiation", False):
        return execute_command_direct(context, command)

    project_root = Path(__file__).parent.parent.parent

    env = os.environ.copy()

    if hasattr(context, "saved_env"):
        for key in [
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "AWS_SESSION_TOKEN",
            "MOONDOCK_TEST_MODE",
        ]:
            env.pop(key, None)

    if command in ["setup", "doctor"] and "saved_env" not in dir(context):
        import boto3

        try:
            ec2_client = boto3.client("ec2", region_name="us-east-1")
            vpcs = ec2_client.describe_vpcs(
                Filters=[{"Name": "isDefault", "Values": ["true"]}]
            )
            vpc_exists = bool(vpcs.get("Vpcs", []))
            vpc_env_value = "true" if vpc_exists else "false"

            context.harness.services.configuration_env.set(
                "MOONDOCK_TEST_VPC_EXISTS", vpc_env_value
            )
        except Exception:
            vpc_env_value = "false"
            context.harness.services.configuration_env.set(
                "MOONDOCK_TEST_VPC_EXISTS", vpc_env_value
            )

    result = subprocess.run(
        ["uv", "run", "python", "-m", "moondock", command],
        env=env,
        capture_output=True,
        text=True,
        cwd=project_root,
    )

    context.exit_code = result.returncode
    context.stdout = result.stdout
    context.stderr = result.stderr


@when('I run with environment "{env_and_command}"')
def step_run_with_environment(context: Context, env_and_command: str) -> None:
    """Run command with environment variable (e.g., 'MOONDOCK_DEBUG=1 moondock run').

    Parameters
    ----------
    context : Context
        Behave context
    env_and_command : str
        Command with environment variable prefix
    """
    project_root = Path(__file__).parent.parent.parent

    parts = env_and_command.split()

    env = os.environ.copy()

    if hasattr(context, "saved_env"):
        for key in [
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "AWS_SESSION_TOKEN",
            "MOONDOCK_TEST_MODE",
        ]:
            env.pop(key, None)

    command_parts = []

    for part in parts:
        if "=" in part:
            key, value = part.split("=", 1)
            env[key] = value
        else:
            command_parts.append(part)

    if command_parts and command_parts[0] == "moondock":
        command_parts = command_parts[1:]

    result = subprocess.run(
        ["uv", "run", "python", "-m", "moondock"] + command_parts,
        env=env,
        capture_output=True,
        text=True,
        cwd=project_root,
    )

    context.exit_code = result.returncode
    context.stdout = result.stdout
    context.stderr = result.stderr


@then("exit code is {expected_code:d}")
def step_exit_code_is(context: Context, expected_code: int) -> None:
    """Verify exit code.

    Parameters
    ----------
    context : Context
        Behave context
    expected_code : int
        Expected exit code
    """
    assert context.exit_code == expected_code, (
        f"Expected exit code {expected_code}, got {context.exit_code}\n"
        f"stdout: {context.stdout}\n"
        f"stderr: {context.stderr}"
    )


@then("exit code is not {expected_code:d}")
def step_exit_code_is_not(context: Context, expected_code: int) -> None:
    """Verify exit code is not the specified value.

    Parameters
    ----------
    context : Context
        Behave context
    expected_code : int
        Value exit code should not be
    """
    assert context.exit_code != expected_code, (
        f"Expected exit code to not be {expected_code}, but it was\n"
        f"stdout: {context.stdout}\n"
        f"stderr: {context.stderr}"
    )


@then('stdout contains "{text}"')
def step_stdout_contains(context: Context, text: str) -> None:
    """Verify stdout contains text.

    Parameters
    ----------
    context : Context
        Behave context
    text : str
        Text to search for
    """
    assert text in context.stdout, (
        f"Expected stdout to contain: {text}\nActual stdout: {context.stdout}"
    )


@then('stdout does not contain "{text}"')
def step_stdout_does_not_contain(context: Context, text: str) -> None:
    """Verify stdout does not contain text.

    Parameters
    ----------
    context : Context
        Behave context
    text : str
        Text that should not be present
    """
    assert text not in context.stdout, (
        f"Expected stdout to not contain: {text}\nActual stdout: {context.stdout}"
    )


@then('stderr contains "{text}"')
def step_stderr_contains(context: Context, text: str) -> None:
    """Verify stderr contains text.

    Parameters
    ----------
    context : Context
        Behave context
    text : str
        Text to search for
    """
    assert text in context.stderr, (
        f"Expected stderr to contain: {text}\nActual stderr: {context.stderr}"
    )


@then('stderr does not contain "{text}"')
def step_stderr_does_not_contain(context: Context, text: str) -> None:
    """Verify stderr does not contain text.

    Parameters
    ----------
    context : Context
        Behave context
    text : str
        Text to search for
    """
    assert text not in context.stderr, (
        f"Expected stderr to not contain: {text}\nActual stderr: {context.stderr}"
    )
