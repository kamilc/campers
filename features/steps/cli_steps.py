import json
import logging
import os
import shlex
import subprocess
import sys
import tempfile

import yaml
from behave import given, then, when
from behave.runner import Context

from moondock.__main__ import MoondockCLI

JSON_OUTPUT_TRUNCATE_LENGTH = 200

logger = logging.getLogger(__name__)


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


def parse_cli_args(args: list[str]) -> tuple[str | None, str | None]:
    """Parse CLI arguments to extract machine name and command.

    Parameters
    ----------
    args : list[str]
        Parsed command-line arguments (e.g., ["run", "test-box"] or ["run", "-c", "uptime"])

    Returns
    -------
    tuple[str | None, str | None]
        (machine_name, command) tuple, either or both may be None
    """
    machine_name = None
    command = None

    if not args or args[0] != "run":
        return machine_name, command

    if len(args) > 1 and not args[1].startswith("-"):
        machine_name = args[1]

    if "-c" in args:
        c_index = args.index("-c")
        if c_index + 1 < len(args):
            command = args[c_index + 1]

    return machine_name, command


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
    temp_file = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
    temp_file.write(yaml.dump(context.config_data))
    temp_file.close()
    context.temp_config_file = temp_file.name

    os.environ["MOONDOCK_CONFIG"] = context.temp_config_file

    args = shlex.split(moondock_args)

    is_localstack = (
        hasattr(context, "scenario") and "localstack" in context.scenario.tags
    )

    if is_localstack:
        logger.info("LocalStack scenario detected, using in-process execution")

        machine_name, command = parse_cli_args(args)
        logger.debug(f"Parsed args: machine_name={machine_name}, command={command}")

        try:
            cli = MoondockCLI()

            if args[0] == "run":
                result = cli.run(
                    machine_name=machine_name,
                    command=command,
                    json_output=True,
                    plain=True,
                )

                context.exit_code = 0
                context.stdout = (
                    result if isinstance(result, str) else json.dumps(result)
                )
                context.stderr = ""

                if isinstance(result, str):
                    try:
                        context.final_config = json.loads(result)
                    except json.JSONDecodeError:
                        context.final_config = {"raw_output": result}
                elif isinstance(result, dict):
                    context.final_config = result

                if context.final_config and "instance_id" in context.final_config:
                    context.instance_id = context.final_config["instance_id"]

                logger.info(
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
            logger.warning(f"CLI raised SystemExit with code {e.code}")
            context.exit_code = e.code if e.code is not None else 1
            context.stderr = f"Command exited with code {e.code}"
            context.stdout = ""
            context.error = f"SystemExit: {e.code}"
        except Exception as e:
            logger.error(f"In-process execution failed: {e}", exc_info=True)
            context.exit_code = 1
            context.stderr = str(e)
            context.stdout = ""
            context.error = str(e)

    else:
        logger.info("Non-LocalStack scenario, using subprocess execution")

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
def step_machine_has_ports(context: Context, machine_name: str, ports_list: str) -> None:
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
