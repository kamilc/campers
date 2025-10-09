"""Common step definitions shared across features."""

import os
import subprocess
from pathlib import Path

from behave import given, then, when
from behave.runner import Context


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
    import boto3

    project_root = Path(__file__).parent.parent.parent

    env = os.environ.copy()

    ec2_client = boto3.client("ec2", region_name="us-east-1")
    vpcs = ec2_client.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}])
    vpc_exists = bool(vpcs.get("Vpcs", []))
    env["MOONDOCK_TEST_VPC_EXISTS"] = "true" if vpc_exists else "false"

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
            env["MOONDOCK_TEST_VPC_EXISTS"] = "true" if vpc_exists else "false"
        except Exception:
            env["MOONDOCK_TEST_VPC_EXISTS"] = "false"

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
