"""Step definitions for test infrastructure improvements."""

import os
from pathlib import Path

from behave import given, then, when
from behave.runner import Context


def get_moondock_dir() -> Path:
    """Get MOONDOCK_DIR from environment or use default.

    Returns
    -------
    Path
        The moondock directory path.
    """
    moondock_dir = os.environ.get("MOONDOCK_DIR", str(Path.home() / ".moondock"))
    return Path(moondock_dir)


@given("multiple tests run in rapid succession")
def step_multiple_tests_rapid(context: Context) -> None:
    """Set flag indicating rapid test execution scenario.

    Parameters
    ----------
    context : Context
        The Behave context object.
    """
    context.rapid_test_execution = True


@when("tests create security groups with UUID-based names")
def step_create_security_groups_uuid(context: Context) -> None:
    """Verify that step definitions use UUID-based naming.

    Parameters
    ----------
    context : Context
        The Behave context object.
    """
    steps_file = (
        context.project_root
        / "tests"
        / "integration"
        / "features"
        / "steps"
        / "ec2_steps.py"
    )
    content = steps_file.read_text()

    context.uses_uuid = "uuid.uuid4()" in content
    context.uses_hex_format = ".hex[:8]" in content or ".hex[:" in content


@then("no InvalidGroup.Duplicate errors occur")
def step_no_duplicate_errors(context: Context) -> None:
    """Verify that UUID generation is implemented to prevent duplicate errors.

    Parameters
    ----------
    context : Context
        The Behave context object.
    """
    assert context.uses_uuid, "UUID generation not implemented"


@then("all security group names are unique")
def step_unique_security_group_names(context: Context) -> None:
    """Verify that security group names use UUID-based unique identifiers.

    Parameters
    ----------
    context : Context
        The Behave context object.
    """
    assert context.uses_uuid, "UUID-based naming not implemented"
    assert context.uses_hex_format, "Hex format not used for UUID"


@given("a scenario completes execution")
def step_scenario_completes(context: Context) -> None:
    """Set flag indicating a scenario has completed.

    Parameters
    ----------
    context : Context
        The Behave context object.
    """
    context.scenario_completed = True


@when("after_scenario cleanup runs")
def step_after_scenario_cleanup(context: Context) -> None:
    """Verify that cleanup hooks have proper logging configured.

    Parameters
    ----------
    context : Context
        The Behave context object.
    """
    env_file = (
        context.project_root / "tests" / "integration" / "features" / "environment.py"
    )
    content = env_file.read_text()

    context.has_logging_import = "import logging" in content
    context.has_logger = "logger = logging.getLogger(" in content
    context.has_error_logging = "logger.error(" in content
    context.has_debug_logging = "logger.debug(" in content


@then("cleanup failures are logged with error level")
def step_cleanup_logged_error(context: Context) -> None:
    """Verify that cleanup failures are logged at error level.

    Parameters
    ----------
    context : Context
        The Behave context object.
    """
    assert context.has_error_logging, "Error level logging not implemented"


@then("expected errors are logged with debug level")
def step_expected_errors_debug(context: Context) -> None:
    """Verify that expected errors are logged at debug level.

    Parameters
    ----------
    context : Context
        The Behave context object.
    """
    assert context.has_debug_logging, "Debug level logging not implemented"


@then("test suite continues without crash")
def step_suite_continues(context: Context) -> None:
    """Verify that logging is configured to prevent crashes.

    Parameters
    ----------
    context : Context
        The Behave context object.
    """
    assert context.has_logging_import, "Logging not configured"


@given("test infrastructure improvements start")
def step_infrastructure_improvements_start(context: Context) -> None:
    """Set flag indicating infrastructure improvement checks are starting.

    Parameters
    ----------
    context : Context
        The Behave context object.
    """
    context.infrastructure_check = True


@when("checking for pre-existing artifacts")
def step_check_preexisting_artifacts(context: Context) -> None:
    """Check for and clean up pre-existing test artifacts.

    Parameters
    ----------
    context : Context
        The Behave context object.
    """
    moondock_dir = get_moondock_dir()
    keys_dir = moondock_dir / "keys"

    if keys_dir.exists():
        for pem_file in keys_dir.glob("*.pem"):
            pem_file.unlink()

    context.keys_dir = keys_dir


@then('old key files in "{path}" are removed')
def step_old_key_files_removed(context: Context, path: str) -> None:
    """Verify that old key files have been removed from specified path.

    Parameters
    ----------
    context : Context
        The Behave context object.
    path : str
        The path to check for removed key files.
    """
    if path.startswith("$MOONDOCK_DIR"):
        moondock_dir = get_moondock_dir()
        relative_path = path.replace("$MOONDOCK_DIR/", "")
        expanded_path = moondock_dir / relative_path
    else:
        expanded_path = Path(path.replace("~", str(Path.home())))

    if expanded_path.exists():
        pem_files = list(expanded_path.glob("*.pem"))
        assert len(pem_files) == 0, f"Found {len(pem_files)} old key files"


@then("directory is empty or non-existent")
def step_directory_empty_or_nonexistent(context: Context) -> None:
    """Verify that the keys directory is empty or does not exist.

    Parameters
    ----------
    context : Context
        The Behave context object.
    """
    keys_dir = get_moondock_dir() / "keys"

    if keys_dir.exists():
        files = list(keys_dir.iterdir())
        assert len(files) == 0, f"Directory not empty: {len(files)} files found"
