import json
import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml
from behave import given, then, when


def ensure_machine_exists(context, machine_name: str) -> None:
    """Ensure machine configuration structure exists in context.

    Parameters
    ----------
    context : behave.runner.Context
        Behave test context
    machine_name : str
        Name of the machine configuration
    """

    if not hasattr(context, "config_data"):
        context.config_data = {"defaults": {}}

    if "machines" not in context.config_data:
        context.config_data["machines"] = {}

    if machine_name not in context.config_data["machines"]:
        context.config_data["machines"][machine_name] = {}


@given("config file with defaults section only")
def step_config_with_defaults_section_only(context) -> None:
    context.config_data = {"defaults": {}}


@given('config file with machine "{machine_name}" defined')
def step_config_with_machine_defined(context, machine_name: str) -> None:
    ensure_machine_exists(context, machine_name)


@given('machine "{machine_name}" has instance_type "{instance_type}"')
def step_machine_has_instance_type(
    context, machine_name: str, instance_type: str
) -> None:
    ensure_machine_exists(context, machine_name)
    context.config_data["machines"][machine_name]["instance_type"] = instance_type


@given('machine "{machine_name}" has disk_size {disk_size:d}')
def step_machine_has_disk_size(context, machine_name: str, disk_size: int) -> None:
    ensure_machine_exists(context, machine_name)
    context.config_data["machines"][machine_name]["disk_size"] = disk_size


@given('machine "{machine_name}" has command "{command}"')
def step_machine_has_command(context, machine_name: str, command: str) -> None:
    ensure_machine_exists(context, machine_name)
    context.config_data["machines"][machine_name]["command"] = command


@given('machine "{machine_name}" has no command field')
def step_machine_has_no_command(context, machine_name: str) -> None:
    ensure_machine_exists(context, machine_name)


@given('machine "{machine_name}" has setup_script "{script}"')
def step_machine_has_setup_script(context, machine_name: str, script: str) -> None:
    ensure_machine_exists(context, machine_name)
    context.config_data["machines"][machine_name]["setup_script"] = script


@given('machine "{machine_name}" has startup_script "{script}"')
def step_machine_has_startup_script(context, machine_name: str, script: str) -> None:
    ensure_machine_exists(context, machine_name)
    context.config_data["machines"][machine_name]["startup_script"] = script


@given('machine "{machine_name}" has env_filter "{env_filter}"')
def step_machine_has_env_filter(context, machine_name: str, env_filter: str) -> None:
    ensure_machine_exists(context, machine_name)
    context.config_data["machines"][machine_name]["env_filter"] = [env_filter]


@given("config file with machines {machine_list}")
def step_config_with_machines(context, machine_list: str) -> None:
    machines = json.loads(machine_list)

    context.config_data = {"defaults": {}, "machines": {}}

    for machine in machines:
        context.config_data["machines"][machine] = {}


@given('YAML defaults with region "{region}"')
def step_yaml_defaults_with_region(context, region: str) -> None:
    if not hasattr(context, "config_data"):
        context.config_data = {"defaults": {}}

    context.config_data["defaults"]["region"] = region


@given('defaults section has region "{region}"')
def step_defaults_has_region(context, region: str) -> None:
    if not hasattr(context, "config_data"):
        context.config_data = {"defaults": {}}

    context.config_data["defaults"]["region"] = region


@given('machine "{machine_name}" overrides region to "{region}"')
def step_machine_overrides_region(context, machine_name: str, region: str) -> None:
    ensure_machine_exists(context, machine_name)
    context.config_data["machines"][machine_name]["region"] = region


@when('I run moondock command "{moondock_args}"')
def step_run_moondock_command(context, moondock_args: str) -> None:
    temp_file = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
    temp_file.write(yaml.dump(context.config_data))
    temp_file.close()
    context.temp_config_file = temp_file.name

    os.environ["MOONDOCK_CONFIG"] = context.temp_config_file

    moondock_path = Path(__file__).parent.parent.parent / "moondock.py"

    args = shlex.split(moondock_args)

    if args and args[0] == "run":
        args.append("--json-output")
        args.append("True")

    result = subprocess.run(
        [sys.executable, str(moondock_path)] + args,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )

    context.exit_code = result.returncode
    context.stdout = result.stdout
    context.stderr = result.stderr

    if result.returncode == 0:
        if result.stdout.strip():
            context.final_config = json.loads(result.stdout)
    else:
        context.error = result.stderr


@then('final config contains instance_type "{expected}"')
def step_final_config_contains_instance_type(context, expected: str) -> None:
    assert context.final_config is not None
    assert context.final_config["instance_type"] == expected


@then("final config contains defaults for unspecified fields")
def step_final_config_contains_defaults(context) -> None:
    assert context.final_config is not None
    assert "region" in context.final_config
    assert "disk_size" in context.final_config


@then('final config contains region "{expected}"')
def step_final_config_contains_region(context, expected: str) -> None:
    assert context.final_config is not None
    assert context.final_config["region"] == expected


@then("final config contains disk_size {expected:d}")
def step_final_config_contains_disk_size(context, expected: int) -> None:
    assert context.final_config is not None
    assert context.final_config["disk_size"] == expected


@then('final config contains command "{expected}"')
def step_final_config_contains_command(context, expected: str) -> None:
    assert context.final_config is not None
    assert context.final_config["command"] == expected


@then("final config contains ports {expected_ports}")
def step_final_config_contains_ports(context, expected_ports: str) -> None:
    expected = json.loads(expected_ports)

    assert context.final_config is not None
    assert context.final_config["ports"] == expected


@then('final config does not contain "port" field')
def step_final_config_no_port_field(context) -> None:
    assert context.final_config is not None
    assert "port" not in context.final_config


@then("final config contains ignore {expected_ignore}")
def step_final_config_contains_ignore(context, expected_ignore: str) -> None:
    expected = json.loads(expected_ignore)

    assert context.final_config is not None
    assert context.final_config["ignore"] == expected


@then("final config contains include_vcs True")
def step_final_config_contains_include_vcs_true(context) -> None:
    assert context.final_config is not None
    assert context.final_config["include_vcs"] is True


@then("final config contains include_vcs False")
def step_final_config_contains_include_vcs_false(context) -> None:
    assert context.final_config is not None
    assert context.final_config["include_vcs"] is False


@then("command fails with ValueError")
def step_command_fails_with_value_error(context) -> None:
    assert context.exit_code != 0
    assert "ValueError" in context.stderr


@then('error message contains "{expected}"')
def step_error_message_contains(context, expected: str) -> None:
    assert hasattr(context, "error") or hasattr(context, "stderr")

    error_text = context.error if hasattr(context, "error") else context.stderr
    assert expected in error_text


@then("final config contains built-in defaults for other fields")
def step_final_config_contains_built_in_defaults(context) -> None:
    assert context.final_config is not None
    assert "instance_type" in context.final_config
    assert "disk_size" in context.final_config


@then("final config does not contain command field")
def step_final_config_no_command_field(context) -> None:
    assert context.final_config is not None
    assert "command" not in context.final_config


@then("validation passes")
def step_validation_passes(context) -> None:
    assert context.exit_code == 0


@then('final config contains setup_script "{expected}"')
def step_final_config_contains_setup_script(context, expected: str) -> None:
    assert context.final_config is not None
    assert context.final_config["setup_script"] == expected


@then('final config contains startup_script "{expected}"')
def step_final_config_contains_startup_script(context, expected: str) -> None:
    assert context.final_config is not None
    assert context.final_config["startup_script"] == expected


@then('final config contains env_filter "{expected}"')
def step_final_config_contains_env_filter(context, expected: str) -> None:
    assert context.final_config is not None
    assert context.final_config["env_filter"] == [expected]
