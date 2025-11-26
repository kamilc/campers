"""Step definitions for campers skeleton feature tests."""

import subprocess
from pathlib import Path

from behave import given, then, when


@given("campers.py exists in project root")
def step_campers_exists(context) -> None:
    """Verify campers package exists in project root."""
    project_root = Path(__file__).parent.parent.parent.parent.parent

    campers_path = project_root / "campers" / "__main__.py"

    assert campers_path.exists(), f"campers/__main__.py not found at {campers_path}"
    context.campers_path = campers_path


@given("campers.py contains PEP 723 dependencies")
def step_contains_pep723(context) -> None:
    """Verify campers.py contains PEP 723 dependency specification."""
    content = context.campers_path.read_text()

    assert "# /// script" in content, "Missing PEP 723 script marker"
    assert "# dependencies = [" in content, "Missing dependencies array"
    assert "# ///" in content, "Missing PEP 723 closing marker"


@given('campers.py contains dependency "{dependency}"')
def step_contains_dependency(context, dependency: str) -> None:
    """Verify campers.py contains specific dependency."""
    content = context.campers_path.read_text()

    assert dependency in content, f"Dependency {dependency} not found in campers.py"


@given("campers.py defines Campers class")
def step_defines_campers_class(context) -> None:
    """Verify campers.py defines Campers class."""
    content = context.campers_path.read_text()

    assert "class Campers" in content, "Campers class not defined"


@when('I run "{command}"')
def step_run_command(context, command: str) -> None:
    """Execute command and capture output.

    Parameters
    ----------
    context : behave.runner.Context
        The Behave context object.
    command : str
        The command string to execute.

    Notes
    -----
    Commands are executed using subprocess.run with shell=True for simplicity
    in test scenarios. All commands originate from controlled feature files,
    not user input, so the security risk is minimal.

    """
    import os

    if getattr(context, "use_direct_instantiation", False) and "campers" in command:
        from tests.integration.features.steps.common_steps import execute_command_direct

        parts = command.replace("campers", "").strip().split()
        if parts:
            cmd_name = parts[0]
            region = None
            if "--region" in parts:
                idx = parts.index("--region")
                if idx + 1 < len(parts):
                    region = parts[idx + 1]
            execute_command_direct(context, cmd_name, region=region)
            return

    project_root = Path(__file__).parent.parent.parent.parent.parent

    env = os.environ.copy()

    if "campers" in command and ("setup" in command or "doctor" in command):
        import boto3

        try:
            ec2_client = boto3.client("ec2", region_name="us-east-1")
            vpcs = ec2_client.describe_vpcs(
                Filters=[{"Name": "isDefault", "Values": ["true"]}]
            )
            vpc_exists = bool(vpcs.get("Vpcs", []))
            env["CAMPERS_TEST_VPC_EXISTS"] = "true" if vpc_exists else "false"
        except Exception:
            env["CAMPERS_TEST_VPC_EXISTS"] = "false"

        command = command.replace("campers", "uv run python -m campers")

    result = subprocess.run(
        command,
        shell=True,
        cwd=project_root,
        capture_output=True,
        text=True,
        env=env,
    )

    context.result = result
    context.exit_code = result.returncode
    context.stdout = result.stdout
    context.stderr = result.stderr


@then("exit code is {code:d}")
def step_exit_code(context, code: int) -> None:
    """Verify command exit code."""
    assert context.exit_code == code, (
        f"Expected exit code {code}, got {context.exit_code}\n"
        f"stdout: {context.stdout}\n"
        f"stderr: {context.stderr}"
    )


@then('output contains "{expected_text}"')
def step_output_contains(context, expected_text: str) -> None:
    """Verify command output contains expected text.

    Works for both subprocess mode and in-process mode (LocalStack/TUI).
    """
    from tests.integration.features.steps.ssh_steps import get_combined_log_output

    log_output = get_combined_log_output(context)
    combined_output = context.stdout + context.stderr + log_output

    assert expected_text in combined_output, (
        f"Expected output to contain '{expected_text}'\n"
        f"stdout: {context.stdout}\n"
        f"stderr: {context.stderr}\n"
        f"logs: {log_output}"
    )


@then("no installation errors occur")
def step_no_installation_errors(context) -> None:
    """Verify no installation errors in command output."""
    combined_output = context.stdout + context.stderr
    error_indicators = ["error:", "ERROR:", "failed", "FAILED", "Could not install"]

    for indicator in error_indicators:
        assert indicator.lower() not in combined_output.lower(), (
            f"Installation error detected: {indicator}\n"
            f"stdout: {context.stdout}\n"
            f"stderr: {context.stderr}"
        )


@then("Fire routes to CLI commands")
def step_fire_routes(context) -> None:
    """Verify Fire successfully routes to CLI commands."""
    assert context.exit_code == 0, "Fire routing failed with non-zero exit code"
    combined_output = context.stdout + context.stderr
    assert "campers" in combined_output.lower(), (
        "CLI command routing not found in output"
    )
