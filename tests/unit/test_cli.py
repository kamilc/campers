import pytest


def test_campers_class_exists(campers_module) -> None:
    assert campers_module.Campers is not None


def test_campers_run_method_exists(campers) -> None:
    assert hasattr(campers, "run")
    assert callable(campers.run)


def test_run_with_camp_name_only(campers, write_config, mock_ec2_manager) -> None:
    config_data = {
        "defaults": {"region": "us-east-1"},
        "camps": {"jupyter-lab": {"instance_type": "m5.xlarge", "disk_size": 100}},
    }
    write_config(config_data)

    result = campers.run(camp_name="jupyter-lab")

    assert result["instance_id"] == "i-1234567890abcdef0"
    assert result["state"] == "running"
    assert mock_ec2_manager.launch_instance.called


def test_run_with_cli_overrides(campers, write_config, mock_ec2_manager) -> None:
    config_data = {
        "defaults": {},
        "camps": {
            "dev-workstation": {
                "instance_type": "t3.large",
                "disk_size": 100,
                "region": "us-east-1",
            }
        },
    }
    write_config(config_data)

    result = campers.run(
        camp_name="dev-workstation",
        instance_type="m5.2xlarge",
        region="us-west-2",
    )

    assert result["instance_id"] == "i-1234567890abcdef0"
    assert result["state"] == "running"
    assert mock_ec2_manager.launch_instance.called


def test_run_with_defaults_only(campers, write_config, mock_ec2_manager) -> None:
    config_data = {"defaults": {"region": "us-west-1", "disk_size": 80}}
    write_config(config_data)

    result = campers.run(instance_type="t3.large", disk_size=200, region="us-east-2")

    assert result["instance_id"] == "i-1234567890abcdef0"
    assert result["state"] == "running"
    assert mock_ec2_manager.launch_instance.called


def test_run_with_command_override(campers, write_config, mock_ec2_manager) -> None:
    config_data = {
        "defaults": {},
        "camps": {"jupyter-lab": {"command": "jupyter notebook"}},
    }
    write_config(config_data)

    result = campers.run(camp_name="jupyter-lab", command="jupyter lab --port=8890")

    assert result["instance_id"] == "i-1234567890abcdef0"
    assert result["state"] == "running"


def test_run_with_multiple_ports(campers, write_config, mock_ec2_manager) -> None:
    config_data = {"defaults": {}}
    write_config(config_data)

    result = campers.run(port="8888,6006,5000")

    assert result["instance_id"] == "i-1234567890abcdef0"
    assert result["state"] == "running"


def test_run_with_single_port(campers, write_config, mock_ec2_manager) -> None:
    config_data = {"defaults": {}}
    write_config(config_data)

    result = campers.run(port="9999")

    assert result["instance_id"] == "i-1234567890abcdef0"
    assert result["state"] == "running"


def test_run_with_ignore_patterns(campers, write_config, mock_ec2_manager) -> None:
    config_data = {"defaults": {}}
    write_config(config_data)

    result = campers.run(ignore="*.pyc,data/,models/,__pycache__")

    assert result["instance_id"] == "i-1234567890abcdef0"
    assert result["state"] == "running"


def test_run_with_include_vcs_true(campers, write_config, mock_ec2_manager) -> None:
    config_data = {"defaults": {}}
    write_config(config_data)

    result = campers.run(include_vcs="true")

    assert result["instance_id"] == "i-1234567890abcdef0"
    assert result["state"] == "running"


def test_run_with_include_vcs_false(campers, write_config, mock_ec2_manager) -> None:
    config_data = {"defaults": {}}
    write_config(config_data)

    result = campers.run(include_vcs="false")

    assert result["instance_id"] == "i-1234567890abcdef0"
    assert result["state"] == "running"


def test_run_with_invalid_include_vcs(campers, write_config) -> None:
    config_data = {"defaults": {}}
    write_config(config_data)

    with pytest.raises(ValueError, match="include_vcs must be 'true' or 'false'"):
        campers.run(include_vcs="yes")


def test_run_with_invalid_camp_name(campers, write_config) -> None:
    config_data = {
        "defaults": {},
        "camps": {"dev-workstation": {}, "jupyter-lab": {}},
    }
    write_config(config_data)

    with pytest.raises(ValueError, match="Camp 'nonexistent-machine' not found"):
        campers.run(camp_name="nonexistent-machine")


def test_config_hierarchy_cli_takes_precedence(campers, write_config, mock_ec2_manager) -> None:
    config_data = {
        "defaults": {"region": "us-west-1"},
        "camps": {"ml-training": {"region": "eu-west-1"}},
    }
    write_config(config_data)

    result = campers.run(camp_name="ml-training", region="ap-southeast-1")

    assert result["instance_id"] == "i-1234567890abcdef0"
    assert result["state"] == "running"


def test_run_with_no_machine_no_options(campers, write_config, mock_ec2_manager) -> None:
    config_data = {"defaults": {"region": "us-west-1"}}
    write_config(config_data)

    result = campers.run()

    assert result["instance_id"] == "i-1234567890abcdef0"
    assert result["state"] == "running"


def test_run_without_command(campers, write_config, mock_ec2_manager) -> None:
    config_data = {"defaults": {}, "camps": {"dev-workstation": {}}}
    write_config(config_data)

    result = campers.run(camp_name="dev-workstation")

    assert result["instance_id"] == "i-1234567890abcdef0"
    assert result["state"] == "running"


def test_config_file_only_fields_preserved(campers, write_config, mock_ec2_manager) -> None:
    config_data = {
        "defaults": {},
        "camps": {
            "jupyter-lab": {
                "setup_script": "install.sh",
                "startup_script": "start.sh",
                "sync_paths": [{"local": "~/myproject", "remote": "~/myproject"}],
                "env_filter": ["AWS_.*"],
            }
        },
    }
    write_config(config_data)

    result = campers.run(camp_name="jupyter-lab", instance_type="m5.xlarge")

    assert result["instance_id"] == "i-1234567890abcdef0"
    assert result["state"] == "running"


def test_ignore_patterns_with_spaces(campers, write_config, mock_ec2_manager) -> None:
    config_data = {"defaults": {}}
    write_config(config_data)

    result = campers.run(ignore=" *.pyc , data/ , models/ ")

    assert result["instance_id"] == "i-1234567890abcdef0"
    assert result["state"] == "running"


def test_port_replaces_config_ports(campers, write_config, mock_ec2_manager) -> None:
    config_data = {"defaults": {"ports": [8080, 9090]}}
    write_config(config_data)

    result = campers.run(port="8888,6006")

    assert result["instance_id"] == "i-1234567890abcdef0"
    assert result["state"] == "running"


def test_run_with_include_vcs_capitalized_true(campers, write_config, mock_ec2_manager) -> None:
    config_data = {"defaults": {}}
    write_config(config_data)

    result = campers.run(include_vcs=True)

    assert result["instance_id"] == "i-1234567890abcdef0"
    assert result["state"] == "running"


def test_run_with_include_vcs_capitalized_false(campers, write_config, mock_ec2_manager) -> None:
    config_data = {"defaults": {}}
    write_config(config_data)

    result = campers.run(include_vcs=False)

    assert result["instance_id"] == "i-1234567890abcdef0"
    assert result["state"] == "running"
