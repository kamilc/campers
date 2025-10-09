"""Step definitions for user-friendly error messages feature."""

import os
import subprocess
from pathlib import Path

from behave import given, when
from behave.runner import Context


@given('instance type "{instance_type}" is not available')
def step_instance_type_not_available(context: Context, instance_type: str) -> None:
    """Mark instance type as unavailable for testing.

    Parameters
    ----------
    context : Context
        Behave context
    instance_type : str
        Instance type that should fail
    """
    context.invalid_instance_type = instance_type


@given("EC2 instance quota is exceeded")
def step_ec2_quota_exceeded(context: Context) -> None:
    """Mark EC2 quota as exceeded for testing.

    Parameters
    ----------
    context : Context
        Behave context
    """
    context.quota_exceeded = True


@given("SSH connection fails")
def step_ssh_connection_fails(context: Context) -> None:
    """Mark SSH connection as failing for testing.

    Parameters
    ----------
    context : Context
        Behave context
    """
    context.ssh_fails = True


@when('I run run with instance type "{instance_type}"')
def step_run_with_instance_type(context: Context, instance_type: str) -> None:
    """Run moondock run command with instance type override.

    Parameters
    ----------
    context : Context
        Behave context
    instance_type : str
        Instance type to use
    """
    project_root = Path(__file__).parent.parent.parent

    env = os.environ.copy()

    result = subprocess.run(
        [
            "uv",
            "run",
            "python",
            "-m",
            "moondock",
            "run",
            "--instance-type",
            instance_type,
        ],
        env=env,
        capture_output=True,
        text=True,
        cwd=project_root,
    )

    context.exit_code = result.returncode
    context.stdout = result.stdout
    context.stderr = result.stderr


@when('I run run with command "{command}"')
def step_run_with_command(context: Context, command: str) -> None:
    """Run moondock run command with a command to execute.

    Parameters
    ----------
    context : Context
        Behave context
    command : str
        Command to execute on remote instance
    """
    project_root = Path(__file__).parent.parent.parent

    env = os.environ.copy()

    result = subprocess.run(
        ["uv", "run", "python", "-m", "moondock", "run", "-c", command],
        env=env,
        capture_output=True,
        text=True,
        cwd=project_root,
    )

    context.exit_code = result.returncode
    context.stdout = result.stdout
    context.stderr = result.stderr
