"""Step definitions for test-production code separation feature."""

import re
from pathlib import Path
from behave import given, when, then
from behave.runner import Context


@given("the moondock codebase has been refactored")
def step_codebase_refactored(context: Context) -> None:
    """Verify the moondock codebase exists and is accessible."""
    moondock_dir = Path(__file__).parent.parent.parent / "moondock"
    if not moondock_dir.exists():
        raise AssertionError(f"Moondock directory not found: {moondock_dir}")
    context.moondock_dir = moondock_dir


@when("I search for test-specific environment variables in production code")
def step_search_env_vars(context: Context) -> None:
    """Search for test-specific patterns in production code."""
    context.search_results = {}


@then('I find zero matches for "{pattern}" in {search_path}')
def step_verify_no_matches(context: Context, pattern: str, search_path: str) -> None:
    """Verify that a pattern has zero matches in the specified path."""
    moondock_dir = Path(__file__).parent.parent.parent / "moondock"

    if not hasattr(context, "search_results"):
        context.search_results = {}

    if search_path == "moondock/":
        search_dir = moondock_dir
    elif search_path.startswith("moondock/"):
        search_file = moondock_dir / search_path.replace("moondock/", "")
        if search_file.is_file():
            search_dir = search_file
        else:
            search_dir = search_file.parent
    else:
        search_dir = moondock_dir

    matches = find_pattern_in_code(search_dir, pattern)

    if matches:
        error_msg = f"Found {len(matches)} matches for '{pattern}' in {search_path}:\n"
        for file_path, line_num, line_content in matches[:5]:
            error_msg += f"  {file_path}:{line_num}: {line_content.strip()}\n"
        if len(matches) > 5:
            error_msg += f"  ... and {len(matches) - 5} more matches\n"
        raise AssertionError(error_msg)

    context.search_results[pattern] = matches


@then('I find zero matches for "AWS_ENDPOINT_URL" detection in moondock/ec2.py')
def step_verify_no_aws_endpoint_url(context: Context) -> None:
    """Verify that AWS_ENDPOINT_URL detection is not in ec2.py."""
    ec2_file = Path(__file__).parent.parent.parent / "moondock" / "ec2.py"

    matches = find_pattern_in_code(ec2_file, "AWS_ENDPOINT_URL")

    if matches:
        error_msg = (
            f"Found {len(matches)} matches for 'AWS_ENDPOINT_URL' in moondock/ec2.py:\n"
        )
        for file_path, line_num, line_content in matches[:5]:
            error_msg += f"  {file_path}:{line_num}: {line_content.strip()}\n"
        raise AssertionError(error_msg)


@when("I examine the get_ssh_connection_details function in moondock/ssh.py")
def step_examine_ssh_function(context: Context) -> None:
    """Examine the get_ssh_connection_details function."""
    ssh_file = Path(__file__).parent.parent.parent / "moondock" / "ssh.py"
    content = ssh_file.read_text()

    match = re.search(
        r"def get_ssh_connection_info\([^)]*\)[^:]*:\s*(.+?)(?=\ndef |\nclass |\Z)",
        content,
        re.DOTALL,
    )

    if not match:
        raise AssertionError("get_ssh_connection_info function not found in ssh.py")

    func_body = match.group(1)
    lines = func_body.split("\n")
    non_docstring_lines = []
    in_docstring = False

    for line in lines:
        if '"""' in line or "'''" in line:
            in_docstring = not in_docstring
        elif not in_docstring and line.strip() and not line.strip().startswith("#"):
            non_docstring_lines.append(line)

    context.ssh_func_lines = non_docstring_lines
    context.ssh_func_body = func_body


@then("the function is less than {line_count} lines of code")
def step_verify_function_lines(context: Context, line_count: str) -> None:
    """Verify function line count is less than specified."""
    max_lines = int(line_count)
    actual_lines = len(context.ssh_func_lines)

    if actual_lines >= max_lines:
        raise AssertionError(
            f"Function has {actual_lines} lines of code, expected less than {max_lines}. "
            f"Lines: {context.ssh_func_lines}"
        )


@then("the function contains no LocalStack logic")
def step_verify_no_localstack_logic(context: Context) -> None:
    """Verify function contains no LocalStack-specific code."""
    localstack_patterns = [
        "AWS_ENDPOINT_URL",
        "os.environ.get",
        "LocalStack",
        "localhost",
        "SSH_PORT_",
        "SSH_KEY_FILE_",
        "SSH_READY_",
    ]

    func_body = context.ssh_func_body.lower()

    for pattern in localstack_patterns:
        if pattern.lower() in func_body:
            raise AssertionError(f"Function contains LocalStack pattern: {pattern}")


@then("the function contains no Docker container logic")
def step_verify_no_docker_logic(context: Context) -> None:
    """Verify function contains no Docker container coordination logic."""
    docker_patterns = [
        "docker",
        "container",
        "HTTP_SERVERS_READY",
        "MONITOR_ERROR",
        "time.time()",
        "while",
    ]

    func_body = context.ssh_func_body.lower()

    for pattern in docker_patterns:
        if pattern.lower() in func_body:
            raise AssertionError(
                f"Function contains Docker/monitoring pattern: {pattern}"
            )


@when("I search for imports of test fakes in production code")
def step_search_fake_imports(context: Context) -> None:
    """Search for imports of test fakes in production code."""
    context.fake_imports = {}


@then('I find zero imports of "{fake_name}" in moondock/')
def step_verify_no_fake_imports(context: Context, fake_name: str) -> None:
    """Verify that test fakes are not imported in production code."""
    moondock_dir = Path(__file__).parent.parent.parent / "moondock"

    matches = find_pattern_in_code(moondock_dir, f"from tests.fakes import {fake_name}")
    matches.extend(
        find_pattern_in_code(moondock_dir, "from tests.fakes.fake_ec2_manager import")
    )
    matches.extend(
        find_pattern_in_code(moondock_dir, "from tests.fakes.fake_ssh_manager import")
    )

    if matches:
        error_msg = (
            f"Found {len(matches)} imports of '{fake_name}' in production code:\n"
        )
        for file_path, line_num, line_content in matches:
            error_msg += f"  {file_path}:{line_num}: {line_content.strip()}\n"
        raise AssertionError(error_msg)

    context.fake_imports[fake_name] = matches


@then("all test infrastructure code is in tests/ or features/ directories")
def step_verify_test_code_location(context: Context) -> None:
    """Verify test infrastructure code is only in tests/ or features/ directories."""
    moondock_dir = Path(__file__).parent.parent.parent / "moondock"

    test_code_patterns = [
        r"class Fake",
        r"@mock_aws",
        r"from moto import",
        r"TestDouble",
    ]

    for pattern in test_code_patterns:
        matches = find_pattern_in_code(moondock_dir, pattern)

        if matches:
            error_msg = f"Found test code pattern '{pattern}' in production code:\n"
            for file_path, line_num, line_content in matches[:5]:
                error_msg += f"  {file_path}:{line_num}: {line_content.strip()}\n"
            raise AssertionError(error_msg)


@when("I search for LocalStack detection in moondock/ec2.py")
def step_search_localstack_detection(context: Context) -> None:
    """Search for LocalStack detection functions in ec2.py."""
    ec2_file = Path(__file__).parent.parent.parent / "moondock" / "ec2.py"
    content = ec2_file.read_text()
    context.ec2_content = content


@then('I find zero matches for "{pattern}"')
def step_verify_specific_pattern(context: Context, pattern: str) -> None:
    """Verify a specific pattern is not found."""
    if pattern in context.ec2_content:
        lines = context.ec2_content.split("\n")
        for i, line in enumerate(lines, 1):
            if pattern in line:
                raise AssertionError(
                    f"Found pattern '{pattern}' in ec2.py at line {i}: {line.strip()}"
                )


@when("I verify CLI does not contain test-specific arguments")
def step_verify_cli_args(context: Context) -> None:
    """Verify CLI code does not contain test-specific arguments."""
    main_file = Path(__file__).parent.parent.parent / "moondock" / "__main__.py"
    content = main_file.read_text()

    context.cli_content = content


@then("no new test-mode command-line arguments are added")
def step_verify_no_test_mode_args(context: Context) -> None:
    """Verify no test mode arguments in CLI."""
    if "MOONDOCK_TEST_MODE" in context.cli_content:
        raise AssertionError("Test mode argument found in CLI code (should be removed)")

    if "_run_test_mode" in context.cli_content:
        raise AssertionError(
            "Test mode execution method found in CLI code (should be removed)"
        )


@then("SSH connection functions are properly defined")
def step_verify_ssh_functions(context: Context) -> None:
    """Verify SSH connection functions are properly defined."""
    ssh_file = Path(__file__).parent.parent.parent / "moondock" / "ssh.py"
    content = ssh_file.read_text()

    required_patterns = [
        "def get_ssh_connection_info",
        "public_ip",
        "return",
    ]

    for pattern in required_patterns:
        if pattern not in content:
            raise AssertionError(f"SSH file missing expected pattern: {pattern}")


def find_pattern_in_code(search_path: Path, pattern: str) -> list[tuple[str, int, str]]:
    """Find a pattern in Python code files.

    Parameters
    ----------
    search_path : Path
        Directory or file to search in
    pattern : str
        Pattern or string to search for

    Returns
    -------
    list[tuple[str, int, str]]
        List of (file_path, line_number, line_content) tuples
    """
    matches = []

    if search_path.is_file():
        files = [search_path]
    else:
        files = list(search_path.glob("**/*.py"))

    for file_path in files:
        if "__pycache__" in str(file_path):
            continue

        try:
            content = file_path.read_text()
            lines = content.split("\n")

            for line_num, line in enumerate(lines, 1):
                if pattern in line:
                    matches.append((str(file_path), line_num, line))
        except Exception:
            continue

    return matches
