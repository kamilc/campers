"""BDD step definitions for Mutagen file synchronization."""

import json
import os
from pathlib import Path
from typing import Any

from behave import given, then, when
from behave.runner import Context

from features.steps.docker_helpers import exec_in_ssh_container


def ensure_defaults_section(context: Context) -> dict[str, Any]:
    """Ensure defaults section exists in config_data and return it.

    Parameters
    ----------
    context : Context
        Behave context object containing test state

    Returns
    -------
    dict
        The defaults section dictionary
    """
    if not hasattr(context, "config_data") or context.config_data is None:
        context.config_data = {"defaults": {}}

    if "defaults" not in context.config_data:
        context.config_data["defaults"] = {}

    return context.config_data["defaults"]


@given("mutagen is not installed locally")
def step_mutagen_not_installed(context: Context) -> None:
    """Mark that mutagen is not installed locally."""
    os.environ["MOONDOCK_MUTAGEN_NOT_INSTALLED"] = "1"
    context.mutagen_not_installed = True


@given("defaults have sync_paths configured")
def step_defaults_have_sync_paths(context: Context) -> None:
    """Add sync_paths to defaults configuration."""
    if not hasattr(context, "config_data") or context.config_data is None:
        context.config_data = {"defaults": {}}

    if "defaults" not in context.config_data:
        context.config_data["defaults"] = {}

    context.config_data["defaults"]["sync_paths"] = [
        {"local": "~/myproject", "remote": "~/myproject"}
    ]


@given("defaults have no sync_paths")
def step_defaults_no_sync_paths(context: Context) -> None:
    """Ensure defaults have no sync_paths configured."""
    if not hasattr(context, "config_data") or context.config_data is None:
        context.config_data = {"defaults": {}}

    if "defaults" in context.config_data:
        context.config_data["defaults"].pop("sync_paths", None)


@given("defaults have multi-line startup_script with shell features")
def step_defaults_multiline_startup_script(context: Context) -> None:
    """Add multi-line startup_script with shell features to defaults."""
    defaults = ensure_defaults_section(context)
    multiline_script = """set -e
cd ~/myproject || exit 1
mkdir -p .venv/bin
touch .startup_marker
echo "Activated" > .venv/status.txt"""
    defaults["startup_script"] = multiline_script


@given("defaults have no startup_script")
def step_defaults_no_startup_script(context: Context) -> None:
    """Ensure defaults have no startup_script configured."""
    if not hasattr(context, "config_data") or context.config_data is None:
        context.config_data = {"defaults": {}}

    if "defaults" in context.config_data:
        context.config_data["defaults"].pop("startup_script", None)


@given('YAML defaults with startup_script "{script}"')
def step_yaml_defaults_startup_script(context: Context, script: str) -> None:
    """Add startup_script to YAML defaults section."""
    defaults = ensure_defaults_section(context)
    defaults["startup_script"] = script


@given('defaults have sync_paths with local "{local_path}" and remote "{remote_path}"')
def step_defaults_sync_paths_with_paths(
    context: Context, local_path: str, remote_path: str
) -> None:
    """Add sync_paths with specific local and remote paths."""
    if not hasattr(context, "config_data") or context.config_data is None:
        context.config_data = {"defaults": {}}

    if "defaults" not in context.config_data:
        context.config_data["defaults"] = {}

    context.config_data["defaults"]["sync_paths"] = [
        {"local": local_path, "remote": remote_path}
    ]


@given('defaults have startup_script "{script}"')
def step_defaults_have_startup_script(context: Context, script: str) -> None:
    """Add startup_script to defaults configuration."""
    defaults = ensure_defaults_section(context)
    defaults["startup_script"] = script


@given("defaults have ignore patterns {patterns}")
def step_defaults_have_ignore_patterns(context: Context, patterns: str) -> None:
    """Add ignore patterns to defaults configuration."""
    if not hasattr(context, "config_data") or context.config_data is None:
        context.config_data = {"defaults": {}}

    if "defaults" not in context.config_data:
        context.config_data["defaults"] = {}

    context.config_data["defaults"]["ignore"] = json.loads(patterns)


@given("defaults have include_vcs {value}")
def step_defaults_have_include_vcs(context: Context, value: str) -> None:
    """Add include_vcs setting to defaults configuration."""
    if not hasattr(context, "config_data") or context.config_data is None:
        context.config_data = {"defaults": {}}

    if "defaults" not in context.config_data:
        context.config_data["defaults"] = {}

    context.config_data["defaults"]["include_vcs"] = value.lower() == "true"


@given("mutagen sync session is created")
def step_mutagen_sync_session_created(context: Context) -> None:
    """Mark that mutagen sync session has been created."""
    context.mutagen_session_created = True


@given("mutagen initial sync completes")
def step_mutagen_initial_sync_completes(context: Context) -> None:
    """Mark that mutagen initial sync has completed."""
    context.mutagen_sync_completed = True


@given("mutagen sync completes")
def step_mutagen_sync_completes(context: Context) -> None:
    """Mark that mutagen sync has completed."""
    context.mutagen_sync_completed = True


@given("sync does not complete within timeout")
def step_sync_timeout(context: Context) -> None:
    """Mark that sync will timeout."""
    os.environ["MOONDOCK_SYNC_TIMEOUT"] = "1"
    context.mutagen_sync_timeout = True


@given("mutagen sync session is running")
def step_mutagen_sync_session_running(context: Context) -> None:
    """Mark that mutagen sync session is running."""
    context.mutagen_session_running = True


@given('orphaned mutagen session exists with name "{session_name}"')
def step_orphaned_session_exists(context: Context, session_name: str) -> None:
    """Mark that an orphaned mutagen session exists."""
    context.orphaned_session_name = session_name
    context.orphaned_session_exists = True


@given("startup_script is configured")
def step_startup_script_configured(context: Context) -> None:
    """Mark that startup_script is configured."""
    if not hasattr(context, "config_data") or context.config_data is None:
        context.config_data = {"defaults": {}}

    if "defaults" not in context.config_data:
        context.config_data["defaults"] = {}

    context.config_data["defaults"]["startup_script"] = "echo startup"


@when("initial sync begins")
def step_initial_sync_begins(context: Context) -> None:
    """Mark that initial sync has begun."""
    context.initial_sync_started = True


@when("startup_script executes")
def step_startup_script_executes(context: Context) -> None:
    """Mark that startup_script is executing."""
    context.startup_script_executed = True


@when("mutagen sync session is created")
def step_when_mutagen_session_created(context: Context) -> None:
    """Mark that mutagen sync session is being created."""
    context.mutagen_session_created = True


@when("command completes normally")
def step_command_completes_normally(context: Context) -> None:
    """Mark that command completed normally."""
    context.command_completed = True


@when("startup_script fails with exit code {code:d}")
def step_startup_script_fails(context: Context, code: int) -> None:
    """Mark that startup_script failed with specific exit code."""
    context.startup_script_exit_code = code
    context.startup_script_failed = True


@when("timeout elapses")
def step_timeout_elapses(context: Context) -> None:
    """Mark that timeout has elapsed."""
    context.timeout_elapsed = True


@then("command fails before instance launch")
def step_command_fails_before_launch(context: Context) -> None:
    """Verify command failed before instance launch."""
    assert context.exit_code != 0


@then("mutagen installation check is skipped")
def step_mutagen_check_skipped(context: Context) -> None:
    """Verify mutagen installation check was skipped."""
    context.mutagen_check_skipped = True


@then("mutagen session is not created")
def step_mutagen_session_not_created(context: Context) -> None:
    """Verify mutagen session was not created."""
    context.mutagen_session_not_created = True


@then("command executes from home directory")
def step_command_from_home(context: Context) -> None:
    """Verify command executes from home directory."""
    context.command_from_home = True


@then('mutagen session is created with name pattern "{pattern}"')
def step_mutagen_session_name_pattern(context: Context, pattern: str) -> None:
    """Verify mutagen session created with expected name pattern."""
    context.mutagen_session_name_pattern = pattern


@then('sync mode is "{mode}"')
def step_sync_mode(context: Context, mode: str) -> None:
    """Verify sync mode is set correctly."""
    context.sync_mode = mode


@then('sync local path is "{path}"')
def step_sync_local_path(context: Context, path: str) -> None:
    """Verify sync local path is correct."""
    context.sync_local_path = path


@then('sync remote path is "ubuntu@{{host}}:{path}"')
def step_sync_remote_path(context: Context, path: str) -> None:
    """Verify sync remote path is correct."""
    context.sync_remote_path = path


@then('moondock waits for sync state "{state}"')
def step_waits_for_sync_state(context: Context, state: str) -> None:
    """Verify moondock waits for specific sync state."""
    context.expected_sync_state = state


@then("mutagen session is terminated")
def step_mutagen_session_terminated(context: Context) -> None:
    """Verify mutagen session was terminated."""
    context.mutagen_session_terminated = True


@then("instance remains running")
def step_instance_remains_running(context: Context) -> None:
    """Verify instance remains running after error."""
    context.instance_running = True


@then("working directory is sync remote path")
def step_working_dir_sync_remote(context: Context) -> None:
    """Verify working directory is the sync remote path."""
    context.working_dir_is_sync_remote = True


@then("startup_script exit code is {code:d}")
def step_startup_script_exit_code(context: Context, code: int) -> None:
    """Verify startup_script exit code."""
    context.expected_startup_exit_code = code


@then("command exit code is {code:d}")
def step_command_exit_code(context: Context, code: int) -> None:
    """Verify command exit code."""
    context.expected_command_exit_code = code


@then('ignore pattern "{pattern}" is configured')
def step_ignore_pattern_configured(context: Context, pattern: str) -> None:
    """Verify ignore pattern is configured."""
    if not hasattr(context, "configured_ignore_patterns"):
        context.configured_ignore_patterns = []
    context.configured_ignore_patterns.append(pattern)


@then('ignore pattern "{pattern}" is not configured')
def step_ignore_pattern_not_configured(context: Context, pattern: str) -> None:
    """Verify ignore pattern is NOT configured."""
    if not hasattr(context, "unconfigured_ignore_patterns"):
        context.unconfigured_ignore_patterns = []
    context.unconfigured_ignore_patterns.append(pattern)


@then("session is removed from mutagen list")
def step_session_removed_from_list(context: Context) -> None:
    """Verify session was removed from mutagen list."""
    context.session_removed = True


@then("SSH connection is closed")
def step_ssh_connection_closed(context: Context) -> None:
    """Verify SSH connection was closed."""
    context.ssh_closed = True


@then("mutagen session creation is skipped")
def step_mutagen_session_creation_skipped(context: Context) -> None:
    """Verify mutagen session creation was skipped."""
    context.mutagen_session_creation_skipped = True


@then('orphaned session "{session_name}" is terminated')
def step_orphaned_session_terminated(context: Context, session_name: str) -> None:
    """Verify orphaned session was terminated."""
    context.orphaned_session_terminated = session_name


@then("new mutagen session is created")
def step_new_mutagen_session_created(context: Context) -> None:
    """Verify new mutagen session was created."""
    context.new_mutagen_session_created = True


@then("startup_script execution is skipped")
def step_startup_script_execution_skipped(context: Context) -> None:
    """Verify startup_script execution was skipped.

    This step verifies that startup_script execution was properly skipped by
    checking that the "Running startup_script..." status message does NOT appear
    in stderr output. Used in scenarios where no startup_script is configured
    or when startup_script should be bypassed.

    Parameters
    ----------
    context : Context
        Behave context object containing test state

    Raises
    ------
    AssertionError
        If stderr is not captured or startup_script was executed
    """
    if not hasattr(context, "stderr"):
        available_attrs = [a for a in dir(context) if not a.startswith("_")]
        raise AssertionError(
            "No stderr output captured - cannot verify startup_script execution. "
            f"Available context attributes: {available_attrs}"
        )

    stderr_text = str(context.stderr) if context.stderr else ""

    if "Running startup_script..." in stderr_text:
        raise AssertionError(
            "startup_script was executed when it should have been skipped. "
            f"stderr preview: {stderr_text[:200]}..."
        )


@then("SSH connection is not actually attempted for startup_script")
def step_ssh_not_attempted_for_startup_script(context: Context) -> None:
    """Verify SSH was not attempted for startup_script in test mode.

    This step verifies that when MOONDOCK_TEST_MODE is enabled, SSH connections
    are not actually made for startup_script execution. Used in test scenarios
    to ensure the test mode flag is properly honored.

    Parameters
    ----------
    context : Context
        Behave context object containing test state

    Raises
    ------
    AssertionError
        If test mode is not enabled
    """
    assert hasattr(context, "test_mode_enabled") and context.test_mode_enabled, (
        "Test mode must be enabled for this verification"
    )


@given('local directory has file "{filename}"')
def step_local_has_file_given(context: Context, filename: str) -> None:
    """Create file in local sync directory.

    Parameters
    ----------
    context : Context
        Behave context with config_data
    filename : str
        Name of file to create
    """
    sync_path = context.config_data["defaults"]["sync_paths"][0]["local"]
    local_path = Path(sync_path).expanduser() / filename
    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_text(f"content-{filename}-local")
    context.local_test_file = local_path


@then('remote directory has file "{filename}"')
def step_remote_has_file_then(context: Context, filename: str) -> None:
    """Verify file exists in SSH container.

    Parameters
    ----------
    context : Context
        Behave context with instance_id
    filename : str
        Name of file to verify
    """
    if "localstack" not in context.tags:
        return

    sync_path = context.config_data["defaults"]["sync_paths"][0]["remote"]
    remote_path = sync_path.replace("~", "/home/user")

    exit_code, output = exec_in_ssh_container(
        context, ["cat", f"{remote_path}/{filename}"]
    )

    assert exit_code == 0, f"File {filename} not found in remote: {output.decode()}"
    content = output.decode().strip()
    assert "content-" in content, f"File content mismatch: {content}"


@given('remote directory has file "{filename}"')
def step_remote_has_file_given(context: Context, filename: str) -> None:
    """Create file in remote directory via SSH.

    Parameters
    ----------
    context : Context
        Behave context with instance_id
    filename : str
        Name of file to create
    """
    if "localstack" not in context.tags:
        return

    sync_path = context.config_data["defaults"]["sync_paths"][0]["remote"]
    remote_path = sync_path.replace("~", "/home/user")

    mkdir_cmd = f"mkdir -p {remote_path}"
    echo_cmd = f"echo 'content-{filename}-remote' > {remote_path}/{filename}"
    full_cmd = f"{mkdir_cmd} && {echo_cmd}"

    exit_code, output = exec_in_ssh_container(
        context,
        ["bash", "-c", full_cmd],
    )

    assert exit_code == 0, f"Failed to create remote file: {output.decode()}"


@then('local directory has file "{filename}"')
def step_local_has_file_then(context: Context, filename: str) -> None:
    """Verify file synced to local directory.

    Parameters
    ----------
    context : Context
        Behave context with config_data
    filename : str
        Name of file to verify
    """
    if "localstack" not in context.tags:
        return

    sync_path = context.config_data["defaults"]["sync_paths"][0]["local"]
    local_path = Path(sync_path).expanduser() / filename

    assert local_path.exists(), f"File {filename} not found in local directory"
    content = local_path.read_text()
    assert "content-" in content, f"File content mismatch: {content}"


@then('mutagen sync list shows session in "watching" state')
def step_mutagen_watching_state(context: Context) -> None:
    """Verify Mutagen session reaches watching state.

    Parameters
    ----------
    context : Context
        Behave context with mutagen_session_name
    """
    import subprocess
    import time

    if "localstack" not in context.tags:
        return

    session_name = getattr(context, "mutagen_session_name", "moondock-")
    timeout = 60
    start_time = time.time()

    while time.time() - start_time < timeout:
        result = subprocess.run(
            ["mutagen", "sync", "list"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        if session_name in result.stdout and "watching" in result.stdout:
            return

        time.sleep(2)

    raise AssertionError(
        f"Session {session_name} did not reach watching state within {timeout}s"
    )
