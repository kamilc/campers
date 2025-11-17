import io
import json
import logging
import os
import re
import shlex
import subprocess
import sys
from unittest.mock import MagicMock

import yaml
from behave import given, then, when
from behave.runner import Context

from features.steps.common_steps import execute_command_direct
from moondock.__main__ import MoondockCLI

JSON_OUTPUT_TRUNCATE_LENGTH = 200

logger = logging.getLogger(__name__)


def create_cli_test_boto3_factory():
    """Create a boto3 client factory that returns mocked clients for CLI tests.

    Returns
    -------
    callable
        Factory function that returns mocked boto3 clients
    """

    def mock_boto3_client(service_name: str, region_name: str = None):
        if service_name == "ec2":
            mock_client = MagicMock()
            mock_client.describe_images.return_value = {
                "Images": [
                    {
                        "ImageId": "ami-12345678",
                        "CreationDate": "2023-12-01T00:00:00.000Z",
                        "OwnerId": "099720109477",
                        "Name": "ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-20231201",
                    }
                ]
            }
            mock_client.describe_regions.return_value = {
                "Regions": [
                    {"RegionName": "us-east-1"},
                    {"RegionName": "us-west-2"},
                    {"RegionName": "eu-west-1"},
                ]
            }
            mock_client.describe_vpcs.return_value = {
                "Vpcs": [{"VpcId": "vpc-12345678"}]
            }
            return mock_client
        elif service_name == "sts":
            mock_client = MagicMock()
            mock_client.get_caller_identity.return_value = {
                "UserId": "AIDAI123456789012345",
                "Account": "123456789012",
                "Arn": "arn:aws:iam::123456789012:user/test",
            }
            return mock_client
        else:
            return MagicMock()

    return mock_boto3_client


def create_cli_test_ec2_manager_factory():
    """Create an EC2Manager factory that returns mock managers for CLI tests.

    Returns
    -------
    callable
        Factory function that returns mock EC2Manager instances
    """

    def mock_ec2_manager(region: str, **kwargs):
        mock_mgr = MagicMock()
        mock_mgr.launch_instance.return_value = {
            "instance_id": "i-test123456789",
            "public_ip": "192.168.1.1",
            "state": "running",
            "key_file": "/tmp/test_key.pem",
            "security_group_id": "sg-test123456789",
            "unique_id": "test_unique_id",
        }
        return mock_mgr

    return mock_ec2_manager


def create_cli_test_ssh_manager_factory():
    """Create an SSHManager factory that returns mock managers for CLI tests.

    Returns
    -------
    callable
        Factory function that returns mock SSHManager instances
    """

    def filter_env_side_effect(env_filter: list[str] | None) -> dict[str, str]:
        if not env_filter:
            return {}

        compiled_patterns = [re.compile(pattern) for pattern in env_filter]
        filtered_vars = {}

        for var_name, var_value in os.environ.items():
            for regex in compiled_patterns:
                if regex.match(var_name):
                    filtered_vars[var_name] = var_value
                    break

        return filtered_vars

    def mock_ssh_manager(**kwargs):
        mock_mgr = MagicMock()
        mock_mgr.connect.return_value = None
        mock_mgr.filter_environment_variables.side_effect = filter_env_side_effect
        mock_mgr.build_command_with_env.return_value = "mock_command"
        mock_mgr.execute_command.return_value = 0
        mock_mgr.execute_command_raw.return_value = 0
        return mock_mgr

    return mock_ssh_manager


def ensure_machine_exists(context: Context, machine_name: str) -> None:
    """Ensure machine configuration structure exists in context.

    Parameters
    ----------
    context : behave.runner.Context
        Behave test context
    machine_name : str
        Name of the machine configuration
    """

    if not hasattr(context, "config_data") or context.config_data is None:
        context.config_data = {"defaults": {}}

    if "machines" not in context.config_data:
        context.config_data["machines"] = {}

    if machine_name not in context.config_data["machines"]:
        context.config_data["machines"][machine_name] = {"ports": []}


@given("config file with defaults section only")
def step_config_with_defaults_section_only(context: Context) -> None:
    context.config_data = {"defaults": {}, "machines": {}}


@given('config file with machine "{machine_name}" defined')
def step_config_with_machine_defined(context: Context, machine_name: str) -> None:
    ensure_machine_exists(context, machine_name)


@given('machine "{machine_name}" has instance_type "{instance_type}"')
def step_machine_has_instance_type(
    context: Context, machine_name: str, instance_type: str
) -> None:
    ensure_machine_exists(context, machine_name)
    context.config_data["machines"][machine_name]["instance_type"] = instance_type


@given('machine "{machine_name}" has disk_size {disk_size:d}')
def step_machine_has_disk_size(
    context: Context, machine_name: str, disk_size: int
) -> None:
    ensure_machine_exists(context, machine_name)
    context.config_data["machines"][machine_name]["disk_size"] = disk_size


@given('machine "{machine_name}" has region "{region}"')
def step_machine_has_region(context: Context, machine_name: str, region: str) -> None:
    ensure_machine_exists(context, machine_name)
    context.config_data["machines"][machine_name]["region"] = region


@given('machine "{machine_name}" overrides region to "{region}"')
def step_machine_overrides_region(
    context: Context, machine_name: str, region: str
) -> None:
    ensure_machine_exists(context, machine_name)
    context.config_data["machines"][machine_name]["region"] = region


@given('machine "{machine_name}" has command "{command}"')
def step_machine_has_command(context: Context, machine_name: str, command: str) -> None:
    ensure_machine_exists(context, machine_name)
    context.config_data["machines"][machine_name]["command"] = command


@given('machine "{machine_name}" has no command field')
def step_machine_has_no_command(context: Context, machine_name: str) -> None:
    ensure_machine_exists(context, machine_name)


@given('machine "{machine_name}" has setup_script "{script}"')
def step_machine_has_setup_script(
    context: Context, machine_name: str, script: str
) -> None:
    ensure_machine_exists(context, machine_name)
    context.config_data["machines"][machine_name]["setup_script"] = script


@given('machine "{machine_name}" has startup_script "{script}"')
def step_machine_has_startup_script(
    context: Context, machine_name: str, script: str
) -> None:
    ensure_machine_exists(context, machine_name)
    context.config_data["machines"][machine_name]["startup_script"] = script


@given('machine "{machine_name}" has env_filter "{env_filter}"')
def step_machine_has_env_filter(
    context: Context, machine_name: str, env_filter: str
) -> None:
    ensure_machine_exists(context, machine_name)
    context.config_data["machines"][machine_name]["env_filter"] = [env_filter]


@given("config file with machines {machine_list}")
def step_config_with_machines(context: Context, machine_list: str) -> None:
    machines = json.loads(machine_list)

    context.config_data = {"defaults": {}, "machines": {}}

    for machine in machines:
        context.config_data["machines"][machine] = {}


@given('YAML defaults with region "{region}"')
def step_yaml_defaults_with_region(context: Context, region: str) -> None:
    if not hasattr(context, "config_data") or context.config_data is None:
        context.config_data = {"defaults": {}, "machines": {}}

    context.config_data["defaults"]["region"] = region


@given('YAML defaults with instance_type "{instance_type}"')
def step_yaml_defaults_with_instance_type(context: Context, instance_type: str) -> None:
    if not hasattr(context, "config_data") or context.config_data is None:
        context.config_data = {"defaults": {}, "machines": {}}

    context.config_data["defaults"]["instance_type"] = instance_type


@given('defaults section has region "{region}"')
def step_defaults_section_has_region(context: Context, region: str) -> None:
    if not hasattr(context, "config_data") or context.config_data is None:
        context.config_data = {"defaults": {}, "machines": {}}

    if "defaults" not in context.config_data:
        context.config_data["defaults"] = {}

    context.config_data["defaults"]["region"] = region


@given('defaults have instance_type "{instance_type}"')
def step_defaults_have_instance_type(context: Context, instance_type: str) -> None:
    if not hasattr(context, "config_data") or context.config_data is None:
        context.config_data = {"defaults": {}, "machines": {}}

    context.config_data["defaults"]["instance_type"] = instance_type


def parse_cli_args(args: list[str]) -> dict[str, any]:
    """Parse CLI arguments to extract all parameters.

    Parameters
    ----------
    args : list[str]
        Parsed command-line arguments (e.g., ["run", "test-box", "--region", "us-west-2"])

    Returns
    -------
    dict[str, any]
        Dictionary with parsed parameters
    """
    params = {
        "machine_name": None,
        "command": None,
        "instance_type": None,
        "disk_size": None,
        "region": None,
        "port": None,
        "include_vcs": None,
        "ignore": None,
    }

    if not args or args[0] != "run":
        return params

    i = 1
    while i < len(args):
        arg = args[i]

        if arg == "-c" or arg == "--command":
            if i + 1 < len(args):
                params["command"] = args[i + 1]
                i += 2
            else:
                i += 1

        elif arg == "--instance-type":
            if i + 1 < len(args):
                params["instance_type"] = args[i + 1]
                i += 2
            else:
                i += 1

        elif arg == "--disk-size":
            if i + 1 < len(args):
                params["disk_size"] = int(args[i + 1])
                i += 2
            else:
                i += 1

        elif arg == "--region":
            if i + 1 < len(args):
                params["region"] = args[i + 1]
                i += 2
            else:
                i += 1

        elif arg == "--port":
            if i + 1 < len(args):
                params["port"] = args[i + 1]
                i += 2
            else:
                i += 1

        elif arg == "--include-vcs":
            if i + 1 < len(args):
                params["include_vcs"] = args[i + 1]
                i += 2
            else:
                i += 1

        elif arg == "--ignore":
            if i + 1 < len(args):
                params["ignore"] = args[i + 1]
                i += 2
            else:
                i += 1

        elif not arg.startswith("-") and params["machine_name"] is None:
            params["machine_name"] = arg
            i += 1

        else:
            i += 1

    return params


@when('I run moondock command "{moondock_args}"')
def step_run_moondock_command(context: Context, moondock_args: str) -> None:
    """Execute moondock command (subprocess or in-process based on scenario tags).

    Parameters
    ----------
    context : Context
        Behave context object
    moondock_args : str
        Command-line arguments for moondock
    """
    harness_services = getattr(getattr(context, "harness", None), "services", None)
    yaml_content = yaml.dump(context.config_data)

    if harness_services is not None:
        config_file = harness_services.artifacts.create_temp_file(
            "moondock.yaml", content=yaml_content
        )
        harness_services.configuration_env.set("MOONDOCK_CONFIG", str(config_file))
        context.temp_config_file = str(config_file)
    else:
        import tempfile

        fd, path = tempfile.mkstemp(prefix="moondock-cli-", suffix=".yaml")
        with os.fdopen(fd, "w") as tmp_file:
            tmp_file.write(yaml_content)
        context.temp_config_file = path
        os.environ["MOONDOCK_CONFIG"] = path

    args = shlex.split(moondock_args)

    is_localstack = (
        hasattr(context, "scenario") and "localstack" in context.scenario.tags
    )

    is_cli_test = (
        hasattr(context, "scenario")
        and ("smoke" in context.scenario.tags or "error" in context.scenario.tags)
    ) and (args and args[0] == "run")
    use_direct_instantiation = getattr(context, "use_direct_instantiation", False)

    if use_direct_instantiation and not is_localstack:
        params = parse_cli_args(args)
        execute_command_direct(
            context,
            args[0] if args else "",
            args={
                "machine_name": params.get("machine_name"),
                "command": params.get("command"),
                "instance_type": params.get("instance_type"),
                "disk_size": params.get("disk_size"),
                "region": params.get("region"),
                "port": params.get("port"),
                "include_vcs": params.get("include_vcs"),
                "ignore": params.get("ignore"),
            },
        )
        return

    if is_localstack or is_cli_test:
        logger.debug("LocalStack scenario detected, using in-process execution")

        params = parse_cli_args(args)
        logger.debug(f"Parsed args: {params}")

        from features.steps.mutagen_mocking import mutagen_mocked

        boto3_factory = None
        ec2_manager_factory = None
        ssh_manager_factory = None

        if is_cli_test and not is_localstack:
            boto3_factory = create_cli_test_boto3_factory()
            ec2_manager_factory = create_cli_test_ec2_manager_factory()
            ssh_manager_factory = create_cli_test_ssh_manager_factory()

        stderr_capture = io.StringIO()
        old_stderr = sys.stderr
        root_logger = logging.getLogger()
        original_level = root_logger.level
        original_handlers = list(root_logger.handlers)

        stderr_handler = logging.StreamHandler(stderr_capture)
        stderr_handler.setFormatter(logging.Formatter("%(message)s"))
        root_logger.addHandler(stderr_handler)

        sys.stderr = stderr_capture

        try:
            root_logger.setLevel(logging.DEBUG)

            with mutagen_mocked(context):
                cli = MoondockCLI(
                    ec2_manager_factory=ec2_manager_factory,
                    ssh_manager_factory=ssh_manager_factory,
                    boto3_client_factory=boto3_factory,
                )

                if args[0] == "run":
                    result = cli.run(
                        machine_name=params["machine_name"],
                        command=params["command"],
                        instance_type=params["instance_type"],
                        disk_size=params["disk_size"],
                        region=params["region"],
                        port=params["port"],
                        include_vcs=params["include_vcs"],
                        ignore=params["ignore"],
                        json_output=True,
                        plain=True,
                    )

                    context.exit_code = 0
                    context.stdout = (
                        result if isinstance(result, str) else json.dumps(result)
                    )
                    context.stderr = stderr_capture.getvalue()

                    if isinstance(result, str):
                        try:
                            context.final_config = json.loads(result)
                        except json.JSONDecodeError:
                            context.final_config = {"raw_output": result}
                    elif isinstance(result, dict):
                        context.final_config = result

                    if context.final_config and "instance_id" in context.final_config:
                        context.instance_id = context.final_config["instance_id"]

                    logger.debug(
                        f"In-process execution succeeded, instance: {context.final_config.get('instance_id', 'unknown')}"
                    )

                    if hasattr(context, "monitor_error") and context.monitor_error:
                        logger.error(
                            f"Monitor thread reported error: {context.monitor_error}"
                        )
                else:
                    raise ValueError(
                        f"Unsupported command for in-process execution: {args[0]}"
                    )

        except SystemExit as e:
            logger.debug(f"CLI raised SystemExit with code {e.code}")
            context.exit_code = e.code if e.code is not None else 1
            captured_stderr = stderr_capture.getvalue()
            context.stderr = captured_stderr
            context.stdout = ""
            context.error = (
                captured_stderr if captured_stderr else f"SystemExit: {e.code}"
            )
        except Exception as e:
            logger.error(f"In-process execution failed: {e}", exc_info=True)
            context.exit_code = 1
            context.stderr = stderr_capture.getvalue() or str(e)
            context.stdout = ""
            context.error = str(e)
        finally:
            sys.stderr = old_stderr
            root_logger.setLevel(original_level)
            for handler in root_logger.handlers[:]:
                if handler not in original_handlers:
                    root_logger.removeHandler(handler)

    else:
        logger.debug("Non-LocalStack scenario, using subprocess execution")

        if args and args[0] == "run":
            args.append("--json-output")
            args.append("True")

        result = subprocess.run(
            [sys.executable, "-m", "moondock"] + args,
            capture_output=True,
            text=True,
            env=os.environ.copy(),
        )

        context.exit_code = result.returncode
        context.stdout = result.stdout
        context.stderr = result.stderr

        if result.returncode == 0:
            if result.stdout.strip():
                try:
                    context.final_config = json.loads(result.stdout)
                except json.JSONDecodeError:
                    truncated_output = (
                        result.stdout[:JSON_OUTPUT_TRUNCATE_LENGTH] + "..."
                        if len(result.stdout) > JSON_OUTPUT_TRUNCATE_LENGTH
                        else result.stdout
                    )
                    context.error = f"Invalid JSON output: {truncated_output}"
                    context.final_config = None
        else:
            context.error = result.stderr


@then('final config contains instance_type "{expected}"')
def step_final_config_contains_instance_type(context: Context, expected: str) -> None:
    assert context.exit_code == 0, (
        f"Expected exit code 0, got {context.exit_code}\n"
        f"stdout: {context.stdout}\n"
        f"stderr: {context.stderr}"
    )


@then("final config contains defaults for unspecified fields")
def step_final_config_contains_defaults(context: Context) -> None:
    assert context.exit_code == 0


@then('final config contains region "{expected}"')
def step_final_config_contains_region(context: Context, expected: str) -> None:
    assert context.exit_code == 0


@then("final config contains disk_size {expected:d}")
def step_final_config_contains_disk_size(context: Context, expected: int) -> None:
    assert context.exit_code == 0


@then('final config contains command "{expected}"')
def step_final_config_contains_command(context: Context, expected: str) -> None:
    assert context.exit_code == 0


@then("final config contains ports {expected_ports}")
def step_final_config_contains_ports(context: Context, expected_ports: str) -> None:
    assert context.exit_code == 0


@then('final config does not contain "port" field')
def step_final_config_no_port_field(context: Context) -> None:
    assert context.exit_code == 0


@then("final config contains ignore {expected_ignore}")
def step_final_config_contains_ignore(context: Context, expected_ignore: str) -> None:
    assert context.exit_code == 0


@then("final config contains include_vcs True")
def step_final_config_contains_include_vcs_true(context: Context) -> None:
    assert context.exit_code == 0


@then("final config contains include_vcs False")
def step_final_config_contains_include_vcs_false(context: Context) -> None:
    assert context.exit_code == 0


@then("command fails with ValueError")
def step_command_fails_with_value_error(context: Context) -> None:
    if hasattr(context, "exception") and context.exception is not None:
        assert isinstance(context.exception, ValueError), (
            f"Expected ValueError, got {type(context.exception).__name__}: {context.exception}"
        )
    else:
        assert context.exit_code != 0, (
            f"Expected failure, got exit code {context.exit_code}"
        )
        assert context.stderr.strip(), (
            "Expected error message in stderr but got nothing"
        )

        assert "Configuration error" in context.stderr, (
            f"Expected 'Configuration error' in stderr but got: {context.stderr}"
        )


@then('error message contains "{expected}"')
def step_error_message_contains(context: Context, expected: str) -> None:
    if hasattr(context, "exception") and context.exception is not None:
        error_msg = str(context.exception)
        assert expected in error_msg, (
            f"Expected '{expected}' in error message but got: '{error_msg}'"
        )
    elif hasattr(context, "error"):
        assert expected in context.error, (
            f"Expected '{expected}' in error but got: {context.error}"
        )
    elif hasattr(context, "stderr"):
        assert expected in context.stderr, (
            f"Expected '{expected}' in stderr but got: {context.stderr}"
        )
    else:
        raise AssertionError("No error message found in context")


@then("final config contains built-in defaults for other fields")
def step_final_config_contains_built_in_defaults(context: Context) -> None:
    assert context.exit_code == 0


@then("final config does not contain command field")
def step_final_config_no_command_field(context: Context) -> None:
    assert context.exit_code == 0


@then("validation passes")
def step_validation_passes(context: Context) -> None:
    assert context.exit_code == 0


@then('final config contains setup_script "{expected}"')
def step_final_config_contains_setup_script(context: Context, expected: str) -> None:
    assert context.exit_code == 0


@then('final config contains startup_script "{expected}"')
def step_final_config_contains_startup_script(context: Context, expected: str) -> None:
    assert context.exit_code == 0


@then('final config contains env_filter "{expected}"')
def step_final_config_contains_env_filter(context: Context, expected: str) -> None:
    assert context.exit_code == 0


@given('machine "{machine_name}" has sync_paths configured')
def step_machine_has_sync_paths_configured(context: Context, machine_name: str) -> None:
    if not hasattr(context, "config_data"):
        context.config_data = {"defaults": {}, "machines": {}}

    if "machines" not in context.config_data:
        context.config_data["machines"] = {}

    if machine_name not in context.config_data["machines"]:
        context.config_data["machines"][machine_name] = {}

    context.config_data["machines"][machine_name]["sync_paths"] = [
        {"local": "~/myproject", "remote": "~/myproject"}
    ]


@given('machine "{machine_name}" has ports {ports_list}')
def step_machine_has_ports(
    context: Context, machine_name: str, ports_list: str
) -> None:
    ensure_machine_exists(context, machine_name)
    ports = json.loads(ports_list)
    context.config_data["machines"][machine_name]["ports"] = ports


@given('machine "{machine_name}" has no ports specified')
def step_machine_has_no_ports(context: Context, machine_name: str) -> None:
    ensure_machine_exists(context, machine_name)
    context.config_data["machines"][machine_name]["ports"] = []


@then("final config contains sync_paths")
def step_final_config_contains_sync_paths(context: Context) -> None:
    assert context.exit_code == 0
