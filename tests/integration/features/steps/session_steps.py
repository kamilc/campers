"""BDD step definitions for session file infrastructure."""

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from behave import given, then, when
from behave.runner import Context

from campers.session import SessionInfo, SessionManager


@given("a SessionManager with temporary sessions directory")
def step_session_manager_with_temp_dir(context: Context) -> None:
    """Create a SessionManager with a temporary sessions directory."""
    if not hasattr(context, "temp_session_dir"):
        context.temp_session_dir = TemporaryDirectory()
    context.sessions_dir = Path(context.temp_session_dir.name)
    context.session_manager = SessionManager(sessions_dir=context.sessions_dir)


@given("SessionInfo for camp {camp_name_quoted} with pid of current process")
def step_session_info_current_pid(context: Context, camp_name_quoted: str) -> None:
    """Create SessionInfo with current process PID."""
    camp_name = camp_name_quoted.strip('"')
    context.session_info = SessionInfo(
        camp_name=camp_name,
        pid=os.getpid(),
        instance_id="i-0abc123def456",
        region="us-east-1",
        ssh_host="54.23.45.67",
        ssh_port=22,
        ssh_user="ubuntu",
        key_file="/home/user/.campers/keys/id_rsa",
    )


def _ensure_session_manager(context: Context) -> None:
    """Ensure session manager is initialized with temp directory."""
    if not hasattr(context, "session_manager"):
        if not hasattr(context, "temp_session_dir"):
            context.temp_session_dir = TemporaryDirectory()
        context.sessions_dir = Path(context.temp_session_dir.name)
        context.session_manager = SessionManager(sessions_dir=context.sessions_dir)


@given("session file exists for camp {camp_name_quoted} with pid of current process")
def step_session_file_exists_current_pid(context: Context, camp_name_quoted: str) -> None:
    """Create an existing session file with current process PID."""
    camp_name = camp_name_quoted.strip('"')
    _ensure_session_manager(context)

    session_info = SessionInfo(
        camp_name=camp_name,
        pid=os.getpid(),
        instance_id="i-0abc123def456",
        region="us-east-1",
        ssh_host="54.23.45.67",
        ssh_port=22,
        ssh_user="ubuntu",
        key_file="/home/user/.campers/keys/id_rsa",
    )
    context.session_manager.create_session(session_info)


@given("session file exists for camp {camp_name_quoted} with pid {pid:d}")
def step_session_file_exists_with_pid(context: Context, camp_name_quoted: str, pid: int) -> None:
    """Create an existing session file with specified PID."""
    camp_name = camp_name_quoted.strip('"')
    _ensure_session_manager(context)

    session_info = SessionInfo(
        camp_name=camp_name,
        pid=pid,
        instance_id="i-0abc123def456",
        region="us-east-1",
        ssh_host="54.23.45.67",
        ssh_port=22,
        ssh_user="ubuntu",
        key_file="/home/user/.campers/keys/id_rsa",
    )
    context.session_manager.create_session(session_info)


@given("session file exists for camp {camp_name_quoted} with invalid JSON")
def step_session_file_invalid_json(context: Context, camp_name_quoted: str) -> None:
    """Create a session file with invalid JSON."""
    camp_name = camp_name_quoted.strip('"')
    _ensure_session_manager(context)

    context.sessions_dir.mkdir(parents=True, exist_ok=True)
    session_file = context.sessions_dir / f"{camp_name}.session.json"
    with open(session_file, "w") as f:
        f.write("{ invalid json }")


@given("session file exists for camp {camp_name_quoted} with valid JSON")
def step_session_file_valid_json(context: Context, camp_name_quoted: str) -> None:
    """Create a session file with valid JSON."""
    camp_name = camp_name_quoted.strip('"')
    _ensure_session_manager(context)

    session_info = SessionInfo(
        camp_name=camp_name,
        pid=os.getpid(),
        instance_id="i-0abc123def456",
        region="us-east-1",
        ssh_host="54.23.45.67",
        ssh_port=22,
        ssh_user="ubuntu",
        key_file="/home/user/.campers/keys/id_rsa",
    )
    context.session_manager.create_session(session_info)


@given("session file exists for camp {camp_name_quoted}")
def step_session_file_exists_basic(context: Context, camp_name_quoted: str) -> None:
    """Create an existing session file with current process PID."""
    camp_name = camp_name_quoted.strip('"')
    _ensure_session_manager(context)

    session_info = SessionInfo(
        camp_name=camp_name,
        pid=os.getpid(),
        instance_id="i-0abc123def456",
        region="us-east-1",
        ssh_host="54.23.45.67",
        ssh_port=22,
        ssh_user="ubuntu",
        key_file="/home/user/.campers/keys/id_rsa",
    )
    context.session_manager.create_session(session_info)


@given("SessionInfo for camp {camp_name_quoted} with pid {pid} and region {region_quoted}")
def step_session_info_with_pid_region(
    context: Context, camp_name_quoted: str, pid: str, region_quoted: str
) -> None:
    """Create SessionInfo with specific PID and region."""
    camp_name = camp_name_quoted.strip('"')
    region = region_quoted.strip('"')
    context.session_info = SessionInfo(
        camp_name=camp_name,
        pid=int(pid),
        instance_id="i-0abc123def456",
        region=region,
        ssh_host="54.23.45.67",
        ssh_port=22,
        ssh_user="ubuntu",
        key_file="/home/user/.campers/keys/id_rsa",
    )


@given("CAMPERS_DIR is set to a temporary directory")
def step_campers_dir_temp(context: Context) -> None:
    """Set CAMPERS_DIR environment variable to a temporary directory."""
    if hasattr(context, "temp_campers_dir") and context.temp_campers_dir:
        context.temp_campers_dir.cleanup()
    context.temp_campers_dir = TemporaryDirectory()
    context.original_campers_dir = os.environ.get("CAMPERS_DIR")
    os.environ["CAMPERS_DIR"] = context.temp_campers_dir.name


@given("a SessionManager with default initialization")
def step_session_manager_default(context: Context) -> None:
    """Create a SessionManager with default initialization (respecting CAMPERS_DIR)."""
    context.session_manager = SessionManager()


@given("a SessionManager with temporary sessions directory that does not exist")
def step_session_manager_nonexistent_dir(context: Context) -> None:
    """Create a SessionManager with a non-existent temporary directory."""
    context.temp_session_dir = TemporaryDirectory()
    nonexistent_path = Path(context.temp_session_dir.name) / "nonexistent" / "path"
    context.sessions_dir = nonexistent_path
    context.session_manager = SessionManager(sessions_dir=nonexistent_path)


@when("I create a session")
def step_create_session(context: Context) -> None:
    """Create a session using the session manager."""
    context.session_manager.create_session(context.session_info)


@when("I delete the session for {camp_name_quoted}")
def step_delete_session(context: Context, camp_name_quoted: str) -> None:
    """Delete a session."""
    camp_name = camp_name_quoted.strip('"')
    context.session_manager.delete_session(camp_name)


@when("I read the session for {camp_name_quoted}")
def step_read_session(context: Context, camp_name_quoted: str) -> None:
    """Read a session from disk."""
    camp_name = camp_name_quoted.strip('"')
    context.result = context.session_manager.read_session(camp_name)


@when("I check if session is alive for {camp_name_quoted}")
def step_check_is_alive(context: Context, camp_name_quoted: str) -> None:
    """Check if a session is alive."""
    camp_name = camp_name_quoted.strip('"')
    context.result = context.session_manager.is_session_alive(camp_name)


@when("I get alive session for {camp_name_quoted}")
def step_get_alive_session(context: Context, camp_name_quoted: str) -> None:
    """Get an alive session."""
    camp_name = camp_name_quoted.strip('"')
    context.result = context.session_manager.get_alive_session(camp_name)


@then("session file exists at CAMPERS_DIR/sessions/dev.session.json")
def step_session_file_at_campers_dir(context: Context) -> None:
    """Verify that session file exists at CAMPERS_DIR/sessions/dev.session.json."""
    expected_path = Path(os.environ["CAMPERS_DIR"]) / "sessions" / "dev.session.json"
    assert expected_path.exists(), f"Session file {expected_path} does not exist"


@then("session file exists at {filename_quoted}")
def step_session_file_exists_at(context: Context, filename_quoted: str) -> None:
    """Verify that a session file exists."""
    filename = filename_quoted.strip('"')
    session_file = context.sessions_dir / filename
    assert session_file.exists(), f"Session file {session_file} does not exist"


@then("session file does not exist for {camp_name_quoted}")
def step_session_file_not_exists(context: Context, camp_name_quoted: str) -> None:
    """Verify that a session file does not exist."""
    camp_name = camp_name_quoted.strip('"')
    session_file = context.sessions_dir / f"{camp_name}.session.json"
    assert not session_file.exists(), f"Session file {session_file} should not exist"


@then("no error is raised")
def step_no_error_raised(context: Context) -> None:
    """Verify that no error was raised in the previous step."""
    assert not hasattr(context, "error") or context.error is None


@then("session file contains valid JSON")
def step_session_file_valid_json_check(context: Context) -> None:
    """Verify that session file contains valid JSON."""
    session_files = list(context.sessions_dir.glob("*.session.json"))
    assert len(session_files) > 0, "No session files found"
    session_file = session_files[0]
    with open(session_file) as f:
        json.load(f)


@then("session file contains all required fields")
def step_session_file_all_fields(context: Context) -> None:
    """Verify that session file contains all required fields."""
    session_files = list(context.sessions_dir.glob("*.session.json"))
    assert len(session_files) > 0, "No session files found"
    session_file = session_files[0]

    with open(session_file) as f:
        data = json.load(f)

    required_fields = {
        "camp_name",
        "pid",
        "instance_id",
        "region",
        "ssh_host",
        "ssh_port",
        "ssh_user",
        "key_file",
    }
    missing = required_fields - set(data.keys())
    assert set(data.keys()) == required_fields, f"Missing fields: {missing}"


@then("result is a SessionInfo object")
def step_result_is_session_info(context: Context) -> None:
    """Verify that the result is a SessionInfo object."""
    result_type = type(context.result)
    assert isinstance(context.result, SessionInfo), f"Result is not SessionInfo: {result_type}"


@then("result is None")
def step_result_is_none(context: Context) -> None:
    """Verify that the result is None."""
    assert context.result is None, f"Result should be None but is {context.result}"


@then("result is True")
def step_result_is_true(context: Context) -> None:
    """Verify that the result is True."""
    assert context.result is True, f"Result should be True but is {context.result}"


@then("result is False")
def step_result_is_false(context: Context) -> None:
    """Verify that the result is False."""
    assert context.result is False, f"Result should be False but is {context.result}"


@then("SessionInfo has correct camp_name {camp_name_quoted}")
def step_session_info_correct_name(context: Context, camp_name_quoted: str) -> None:
    """Verify that SessionInfo has the correct camp_name."""
    camp_name = camp_name_quoted.strip('"')
    assert context.result.camp_name == camp_name, (
        f"camp_name should be {camp_name} but is {context.result.camp_name}"
    )


@then("result contains camp_name {camp_name_quoted}")
def step_result_contains_camp_name(context: Context, camp_name_quoted: str) -> None:
    """Verify that result contains correct camp_name."""
    camp_name = camp_name_quoted.strip('"')
    assert context.result.camp_name == camp_name


@then("result contains pid {pid}")
def step_result_contains_pid(context: Context, pid: str) -> None:
    """Verify that result contains correct pid."""
    assert context.result.pid == int(pid)


@then("result contains region {region_quoted}")
def step_result_contains_region(context: Context, region_quoted: str) -> None:
    """Verify that result contains correct region."""
    region = region_quoted.strip('"')
    assert context.result.region == region


@then("result contains instance_id")
def step_result_contains_instance_id(context: Context) -> None:
    """Verify that result contains instance_id."""
    assert hasattr(context.result, "instance_id")
    assert context.result.instance_id is not None


@then("result contains ssh_host")
def step_result_contains_ssh_host(context: Context) -> None:
    """Verify that result contains ssh_host."""
    assert hasattr(context.result, "ssh_host")
    assert context.result.ssh_host is not None


@then("result contains ssh_port")
def step_result_contains_ssh_port(context: Context) -> None:
    """Verify that result contains ssh_port."""
    assert hasattr(context.result, "ssh_port")
    assert context.result.ssh_port is not None


@then("result contains ssh_user")
def step_result_contains_ssh_user(context: Context) -> None:
    """Verify that result contains ssh_user."""
    assert hasattr(context.result, "ssh_user")
    assert context.result.ssh_user is not None


@then("result contains key_file")
def step_result_contains_key_file(context: Context) -> None:
    """Verify that result contains key_file."""
    assert hasattr(context.result, "key_file")
    assert context.result.key_file is not None


@then("stale session file does not exist for {camp_name_quoted}")
def step_stale_session_cleaned(context: Context, camp_name_quoted: str) -> None:
    """Verify that stale session file was automatically deleted."""
    camp_name = camp_name_quoted.strip('"')
    session_file = context.sessions_dir / f"{camp_name}.session.json"
    assert not session_file.exists(), f"Stale session file {session_file} should have been deleted"


@then("stale session file should be automatically deleted")
def step_stale_session_auto_deleted(context: Context) -> None:
    """Verify that stale session file should be automatically deleted."""
    session_files = list(context.sessions_dir.glob("*.session.json"))
    assert len(session_files) == 0, f"Expected no session files but found {len(session_files)}"


@then("sessions directory is created")
def step_sessions_directory_created(context: Context) -> None:
    """Verify that the sessions directory was created."""
    assert context.sessions_dir.exists(), (
        f"Sessions directory {context.sessions_dir} was not created"
    )
