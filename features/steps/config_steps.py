import tempfile
from pathlib import Path

import yaml
from behave import given, then, when

from moondock.config import ConfigLoader


@given('config file "{path}" with defaults section')
def step_config_file_with_defaults(context, path: str) -> None:
    config_data = {
        "defaults": {
            "region": "us-east-1",
            "instance_type": "t3.medium",
            "disk_size": 50,
        }
    }
    context.config_path = path
    context.config_data = config_data


@given("config file with defaults section")
def step_config_file_with_defaults_no_path(context) -> None:
    context.config_data = {
        "defaults": {
            "region": "us-east-1",
            "instance_type": "t3.medium",
            "disk_size": 50,
            "ports": [],
        }
    }


@given('machine "{machine_name}" with instance_type "{instance_type}"')
def step_machine_with_instance_type(
    context, machine_name: str, instance_type: str
) -> None:
    if "machines" not in context.config_data:
        context.config_data["machines"] = {}
    context.config_data["machines"][machine_name] = {"instance_type": instance_type}


@when("I load configuration without machine name")
def step_load_config_without_machine(context) -> None:
    temp_file = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
    temp_file.write(yaml.dump(context.config_data))
    temp_file.close()
    context.temp_config_file = temp_file.name

    loader = ConfigLoader()
    context.yaml_config = loader.load_config(context.temp_config_file)
    context.merged_config = loader.get_machine_config(context.yaml_config)


@when('I load configuration for machine "{machine_name}"')
def step_load_config_for_machine(context, machine_name: str) -> None:
    temp_file = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
    temp_file.write(yaml.dump(context.config_data))
    temp_file.close()
    context.temp_config_file = temp_file.name

    loader = ConfigLoader()
    context.yaml_config = loader.load_config(context.temp_config_file)
    context.merged_config = loader.get_machine_config(context.yaml_config, machine_name)


@then('config contains region "{expected_region}"')
def step_config_contains_region(context, expected_region: str) -> None:
    assert context.merged_config["region"] == expected_region


@then('config contains instance_type "{expected_instance_type}"')
def step_config_contains_instance_type(context, expected_instance_type: str) -> None:
    assert context.merged_config["instance_type"] == expected_instance_type


@then("config contains disk_size {expected_disk_size:d}")
def step_config_contains_disk_size(context, expected_disk_size: int) -> None:
    assert context.merged_config["disk_size"] == expected_disk_size


@then("config contains region from defaults")
def step_config_contains_region_from_defaults(context) -> None:
    assert context.merged_config["region"] == context.config_data["defaults"]["region"]


@given("no config file exists")
def step_no_config_file_exists(context) -> None:
    context.config_path = "/nonexistent/path/moondock.yaml"


@when("I load configuration")
def step_load_configuration(context) -> None:
    loader = ConfigLoader()
    context.yaml_config = loader.load_config(context.config_path)
    context.merged_config = loader.get_machine_config(context.yaml_config)


@then("built-in defaults are used")
def step_built_in_defaults_are_used(context) -> None:
    assert context.merged_config["region"] == "us-east-1"
    assert context.merged_config["instance_type"] == "t3.medium"
    assert context.merged_config["disk_size"] == 50


@given('config missing "{field}" field')
def step_config_missing_field(context, field: str) -> None:
    context.config_to_validate = {
        "region": "us-east-1",
        "instance_type": "t3.medium",
        "disk_size": 50,
    }
    del context.config_to_validate[field]


@when("I validate configuration")
def step_validate_configuration(context) -> None:
    loader = ConfigLoader()
    try:
        loader.validate_config(context.config_to_validate)
        context.validation_error = None
    except ValueError as e:
        context.validation_error = str(e)


@then('ValueError is raised with "{expected_message}"')
def step_value_error_raised(context, expected_message: str) -> None:
    assert context.validation_error is not None
    assert expected_message in context.validation_error


@given('config with both "port" and "ports"')
def step_config_with_both_port_and_ports(context) -> None:
    context.config_to_validate = {
        "region": "us-east-1",
        "instance_type": "t3.medium",
        "disk_size": 50,
        "port": 8888,
        "ports": [8888, 6006],
    }


@given("built-in defaults exist")
def step_built_in_defaults_exist(context) -> None:
    context.config_data = {"defaults": {}}


@given("YAML defaults override disk_size to {disk_size:d}")
def step_yaml_defaults_override_disk_size(context, disk_size: int) -> None:
    context.config_data["defaults"]["disk_size"] = disk_size


@given('machine "{machine_name}" overrides disk_size to {disk_size:d}')
def step_machine_overrides_disk_size(
    context, machine_name: str, disk_size: int
) -> None:
    if "machines" not in context.config_data:
        context.config_data["machines"] = {}
    context.config_data["machines"][machine_name] = {"disk_size": disk_size}


@given("YAML defaults with ignore {ignore_patterns}")
def step_yaml_defaults_with_ignore(context, ignore_patterns: str) -> None:
    import json

    patterns = json.loads(ignore_patterns)
    context.config_data = {"defaults": {"ignore": patterns}}


@given('machine "{machine_name}" with ignore {ignore_patterns}')
def step_machine_with_ignore(context, machine_name: str, ignore_patterns: str) -> None:
    import json

    patterns = json.loads(ignore_patterns)

    if "machines" not in context.config_data:
        context.config_data["machines"] = {}
    context.config_data["machines"][machine_name] = {"ignore": patterns}


@then("config ignore is {expected_patterns}")
def step_config_ignore_is(context, expected_patterns: str) -> None:
    import json

    expected = json.loads(expected_patterns)
    assert context.merged_config["ignore"] == expected


@given('MOONDOCK_CONFIG is "{path}"')
def step_moondock_config_is(context, path: str) -> None:
    context.env_config_path = path


@given('config file exists at "{path}"')
def step_config_file_exists_at(context, path: str) -> None:
    config_data = {
        "defaults": {
            "region": "us-west-2",
            "instance_type": "t3.large",
            "disk_size": 100,
        }
    }

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(config_data, f)

    context.env_config_file = path


@when("I load configuration without path")
def step_load_configuration_without_path(context) -> None:
    import os

    os.environ["MOONDOCK_CONFIG"] = context.env_config_path

    loader = ConfigLoader()
    context.yaml_config = loader.load_config()
    context.merged_config = loader.get_machine_config(context.yaml_config)


@then('config loaded from "{path}"')
def step_config_loaded_from(context, path: str) -> None:
    assert context.merged_config["region"] == "us-west-2"
    assert context.merged_config["instance_type"] == "t3.large"
    assert context.merged_config["disk_size"] == 100


@given('config with sync_paths missing "remote" key')
def step_config_with_sync_paths_missing_remote(context) -> None:
    context.config_to_validate = {
        "region": "us-east-1",
        "instance_type": "t3.medium",
        "disk_size": 50,
        "sync_paths": [{"local": "~/projects"}],
    }
