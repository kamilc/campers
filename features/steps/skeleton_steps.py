"""Step definitions for moondock skeleton feature tests."""

import subprocess
from pathlib import Path

from behave import given, then, when


@given("moondock.py exists in project root")
def step_moondock_exists(context) -> None:
    """Verify moondock.py file exists in project root."""
    project_root = Path(__file__).parent.parent.parent
    moondock_path = project_root / "moondock.py"

    assert moondock_path.exists(), f"moondock.py not found at {moondock_path}"
    context.moondock_path = moondock_path


@given("moondock.py contains PEP 723 dependencies")
def step_contains_pep723(context) -> None:
    """Verify moondock.py contains PEP 723 dependency specification."""
    content = context.moondock_path.read_text()

    assert "# /// script" in content, "Missing PEP 723 script marker"
    assert "# dependencies = [" in content, "Missing dependencies array"
    assert "# ///" in content, "Missing PEP 723 closing marker"


@given('moondock.py contains dependency "{dependency}"')
def step_contains_dependency(context, dependency: str) -> None:
    """Verify moondock.py contains specific dependency."""
    content = context.moondock_path.read_text()

    assert dependency in content, f"Dependency {dependency} not found in moondock.py"


@given("moondock.py defines Moondock class")
def step_defines_moondock_class(context) -> None:
    """Verify moondock.py defines Moondock class."""
    content = context.moondock_path.read_text()

    assert "class Moondock" in content, "Moondock class not defined"


@given("Moondock class has hello method")
def step_has_hello_method(context) -> None:
    """Verify Moondock class has hello method."""
    content = context.moondock_path.read_text()

    assert "def hello(" in content, "hello method not defined in Moondock class"


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
    project_root = Path(__file__).parent.parent.parent

    result = subprocess.run(
        command,
        shell=True,
        cwd=project_root,
        capture_output=True,
        text=True,
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
    """Verify command output contains expected text."""
    combined_output = context.stdout + context.stderr

    assert expected_text in combined_output, (
        f"Expected output to contain '{expected_text}'\n"
        f"stdout: {context.stdout}\n"
        f"stderr: {context.stderr}"
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


@then("Fire routes to hello method")
def step_fire_routes(context) -> None:
    """Verify Fire successfully routed to hello method."""
    assert context.exit_code == 0, "Fire routing failed with non-zero exit code"
    assert "moondock v0.1.0 - skeleton ready" in context.stdout, (
        "hello method output not found in stdout"
    )
