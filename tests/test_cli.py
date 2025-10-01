import pytest


def test_moondock_class_exists(moondock_module) -> None:
    assert moondock_module.Moondock is not None


def test_moondock_run_method_exists(moondock) -> None:
    assert hasattr(moondock, "run")
    assert callable(moondock.run)


def test_run_with_machine_name_only(moondock, write_config) -> None:
    config_data = {
        "defaults": {"region": "us-east-1"},
        "machines": {"jupyter-lab": {"instance_type": "m5.xlarge", "disk_size": 100}},
    }
    write_config(config_data)

    result = moondock.run(machine_name="jupyter-lab")

    assert result["instance_type"] == "m5.xlarge"
    assert result["disk_size"] == 100
    assert result["region"] == "us-east-1"


def test_run_with_cli_overrides(moondock, write_config) -> None:
    config_data = {
        "defaults": {},
        "machines": {
            "dev-workstation": {
                "instance_type": "t3.large",
                "disk_size": 100,
                "region": "us-east-1",
            }
        },
    }
    write_config(config_data)

    result = moondock.run(
        machine_name="dev-workstation",
        instance_type="m5.2xlarge",
        region="us-west-2",
    )

    assert result["instance_type"] == "m5.2xlarge"
    assert result["region"] == "us-west-2"
    assert result["disk_size"] == 100


def test_run_with_defaults_only(moondock, write_config) -> None:
    config_data = {"defaults": {"region": "us-west-1", "disk_size": 80}}
    write_config(config_data)

    result = moondock.run(instance_type="t3.large", disk_size=200, region="us-east-2")

    assert result["instance_type"] == "t3.large"
    assert result["disk_size"] == 200
    assert result["region"] == "us-east-2"


def test_run_with_command_override(moondock, write_config) -> None:
    config_data = {
        "defaults": {},
        "machines": {"jupyter-lab": {"command": "jupyter notebook"}},
    }
    write_config(config_data)

    result = moondock.run(machine_name="jupyter-lab", command="jupyter lab --port=8890")

    assert result["command"] == "jupyter lab --port=8890"


def test_run_with_multiple_ports(moondock, write_config) -> None:
    config_data = {"defaults": {}}
    write_config(config_data)

    result = moondock.run(port="8888,6006,5000")

    assert result["ports"] == [8888, 6006, 5000]
    assert "port" not in result


def test_run_with_single_port(moondock, write_config) -> None:
    config_data = {"defaults": {}}
    write_config(config_data)

    result = moondock.run(port="9999")

    assert result["ports"] == [9999]
    assert "port" not in result


def test_run_with_ignore_patterns(moondock, write_config) -> None:
    config_data = {"defaults": {}}
    write_config(config_data)

    result = moondock.run(ignore="*.pyc,data/,models/,__pycache__")

    assert result["ignore"] == ["*.pyc", "data/", "models/", "__pycache__"]


def test_run_with_include_vcs_true(moondock, write_config) -> None:
    config_data = {"defaults": {}}
    write_config(config_data)

    result = moondock.run(include_vcs="true")

    assert result["include_vcs"] is True


def test_run_with_include_vcs_false(moondock, write_config) -> None:
    config_data = {"defaults": {}}
    write_config(config_data)

    result = moondock.run(include_vcs="false")

    assert result["include_vcs"] is False


def test_run_with_invalid_include_vcs(moondock, write_config) -> None:
    config_data = {"defaults": {}}
    write_config(config_data)

    with pytest.raises(ValueError, match="include_vcs must be 'true' or 'false'"):
        moondock.run(include_vcs="yes")


def test_run_with_invalid_machine_name(moondock, write_config) -> None:
    config_data = {
        "defaults": {},
        "machines": {"dev-workstation": {}, "jupyter-lab": {}},
    }
    write_config(config_data)

    with pytest.raises(ValueError, match="Machine 'nonexistent-machine' not found"):
        moondock.run(machine_name="nonexistent-machine")


def test_config_hierarchy_cli_takes_precedence(moondock, write_config) -> None:
    config_data = {
        "defaults": {"region": "us-west-1"},
        "machines": {"ml-training": {"region": "eu-west-1"}},
    }
    write_config(config_data)

    result = moondock.run(machine_name="ml-training", region="ap-southeast-1")

    assert result["region"] == "ap-southeast-1"


def test_run_with_no_machine_no_options(moondock, write_config) -> None:
    config_data = {"defaults": {"region": "us-west-1"}}
    write_config(config_data)

    result = moondock.run()

    assert result["region"] == "us-west-1"
    assert "instance_type" in result
    assert "disk_size" in result


def test_run_without_command(moondock, write_config) -> None:
    config_data = {"defaults": {}, "machines": {"dev-workstation": {}}}
    write_config(config_data)

    result = moondock.run(machine_name="dev-workstation")

    assert "command" not in result


def test_config_file_only_fields_preserved(moondock, write_config) -> None:
    config_data = {
        "defaults": {},
        "machines": {
            "jupyter-lab": {
                "setup_script": "install.sh",
                "startup_script": "start.sh",
                "env_filter": ["AWS_.*"],
            }
        },
    }
    write_config(config_data)

    result = moondock.run(machine_name="jupyter-lab", instance_type="m5.xlarge")

    assert result["instance_type"] == "m5.xlarge"
    assert result["setup_script"] == "install.sh"
    assert result["startup_script"] == "start.sh"
    assert result["env_filter"] == ["AWS_.*"]


def test_ignore_patterns_with_spaces(moondock, write_config) -> None:
    config_data = {"defaults": {}}
    write_config(config_data)

    result = moondock.run(ignore=" *.pyc , data/ , models/ ")

    assert result["ignore"] == ["*.pyc", "data/", "models/"]


def test_port_replaces_config_ports(moondock, write_config) -> None:
    config_data = {"defaults": {"ports": [8080, 9090]}}
    write_config(config_data)

    result = moondock.run(port="8888,6006")

    assert result["ports"] == [8888, 6006]


def test_run_with_include_vcs_capitalized_true(moondock, write_config) -> None:
    config_data = {"defaults": {}}
    write_config(config_data)

    result = moondock.run(include_vcs=True)

    assert result["include_vcs"] is True


def test_run_with_include_vcs_capitalized_false(moondock, write_config) -> None:
    config_data = {"defaults": {}}
    write_config(config_data)

    result = moondock.run(include_vcs=False)

    assert result["include_vcs"] is False
