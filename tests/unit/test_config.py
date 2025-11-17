from pathlib import Path

import pytest
import yaml

from moondock.config import ConfigLoader


class TestConfigLoader:
    def test_load_config_with_defaults_only(self, tmp_path: Path) -> None:
        config_file = tmp_path / "moondock.yaml"
        config_data = {
            "defaults": {
                "region": "us-west-2",
                "instance_type": "t3.large",
                "disk_size": 100,
            }
        }
        config_file.write_text(yaml.dump(config_data))

        loader = ConfigLoader()
        config = loader.load_config(str(config_file))

        assert "defaults" in config
        assert config["defaults"]["region"] == "us-west-2"
        assert config["defaults"]["instance_type"] == "t3.large"
        assert config["defaults"]["disk_size"] == 100

    def test_load_config_with_machine_section(self, tmp_path: Path) -> None:
        config_file = tmp_path / "moondock.yaml"
        config_data = {
            "defaults": {
                "region": "us-east-1",
                "instance_type": "t3.medium",
                "disk_size": 50,
            },
            "machines": {
                "jupyter-lab": {
                    "instance_type": "m5.xlarge",
                    "disk_size": 200,
                }
            },
        }
        config_file.write_text(yaml.dump(config_data))

        loader = ConfigLoader()
        config = loader.load_config(str(config_file))

        assert "machines" in config
        assert "jupyter-lab" in config["machines"]
        assert config["machines"]["jupyter-lab"]["instance_type"] == "m5.xlarge"

    def test_load_config_missing_file_uses_built_in_defaults(self) -> None:
        loader = ConfigLoader()
        config = loader.load_config("/nonexistent/path/moondock.yaml")

        assert "defaults" in config
        assert config["defaults"] == {}

        merged = loader.get_machine_config(config)
        assert merged["region"] == "us-east-1"
        assert merged["instance_type"] == "t3.medium"
        assert merged["disk_size"] == 50

    def test_load_config_from_env_variable(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        config_file = tmp_path / "custom-config.yaml"
        config_data = {
            "defaults": {
                "region": "eu-west-1",
                "instance_type": "t3.small",
                "disk_size": 30,
            }
        }
        config_file.write_text(yaml.dump(config_data))

        monkeypatch.setenv("MOONDOCK_CONFIG", str(config_file))

        loader = ConfigLoader()
        config = loader.load_config()

        assert config["defaults"]["region"] == "eu-west-1"
        assert config["defaults"]["instance_type"] == "t3.small"

    def test_get_machine_config_defaults_only(self) -> None:
        config = {
            "defaults": {
                "region": "us-east-1",
                "instance_type": "t3.medium",
                "disk_size": 50,
            }
        }

        loader = ConfigLoader()
        merged = loader.get_machine_config(config)

        assert merged["region"] == "us-east-1"
        assert merged["instance_type"] == "t3.medium"
        assert merged["disk_size"] == 50

    def test_get_machine_config_with_machine_override(self) -> None:
        config = {
            "defaults": {
                "region": "us-east-1",
                "instance_type": "t3.medium",
                "disk_size": 50,
                "os_flavor": "ubuntu-22.04",
            },
            "machines": {
                "jupyter-lab": {
                    "instance_type": "m5.xlarge",
                    "disk_size": 200,
                }
            },
        }

        loader = ConfigLoader()
        merged = loader.get_machine_config(config, "jupyter-lab")

        assert merged["instance_type"] == "m5.xlarge"
        assert merged["disk_size"] == 200
        assert merged["region"] == "us-east-1"
        assert merged["os_flavor"] == "ubuntu-22.04"

    def test_get_machine_config_hierarchy_merging(self) -> None:
        config = {
            "defaults": {
                "region": "us-east-1",
                "instance_type": "t3.medium",
                "disk_size": 100,
            },
            "machines": {
                "ml-training": {
                    "disk_size": 200,
                }
            },
        }

        loader = ConfigLoader()
        merged = loader.get_machine_config(config, "ml-training")

        assert merged["disk_size"] == 200
        assert merged["region"] == "us-east-1"
        assert merged["instance_type"] == "t3.medium"

    def test_get_machine_config_list_replacement_not_merge(self) -> None:
        config = {
            "defaults": {
                "region": "us-east-1",
                "instance_type": "t3.medium",
                "disk_size": 50,
                "ignore": ["*.pyc", "__pycache__"],
            },
            "machines": {
                "jupyter-lab": {
                    "ignore": ["*.pyc", "data/", "models/"],
                }
            },
        }

        loader = ConfigLoader()
        merged = loader.get_machine_config(config, "jupyter-lab")

        assert merged["ignore"] == ["*.pyc", "data/", "models/"]
        assert "__pycache__" not in merged["ignore"]

    def test_validate_config_valid(self) -> None:
        config = {
            "region": "us-east-1",
            "instance_type": "t3.medium",
            "disk_size": 50,
            "port": 8888,
        }

        loader = ConfigLoader()
        loader.validate_config(config)

    def test_validate_config_missing_region(self) -> None:
        config = {
            "instance_type": "t3.medium",
            "disk_size": 50,
        }

        loader = ConfigLoader()

        with pytest.raises(ValueError, match="region is required"):
            loader.validate_config(config)

    def test_validate_config_missing_instance_type(self) -> None:
        config = {
            "region": "us-east-1",
            "disk_size": 50,
        }

        loader = ConfigLoader()

        with pytest.raises(ValueError, match="instance_type is required"):
            loader.validate_config(config)

    def test_validate_config_missing_disk_size(self) -> None:
        config = {
            "region": "us-east-1",
            "instance_type": "t3.medium",
        }

        loader = ConfigLoader()

        with pytest.raises(ValueError, match="disk_size is required"):
            loader.validate_config(config)

    def test_validate_config_both_port_and_ports(self) -> None:
        config = {
            "region": "us-east-1",
            "instance_type": "t3.medium",
            "disk_size": 50,
            "port": 8888,
            "ports": [8888, 6006],
        }

        loader = ConfigLoader()

        with pytest.raises(ValueError, match="cannot specify both port and ports"):
            loader.validate_config(config)

    def test_validate_config_invalid_region_type(self) -> None:
        config = {
            "region": 123,
            "instance_type": "t3.medium",
            "disk_size": 50,
        }

        loader = ConfigLoader()

        with pytest.raises(ValueError, match="region must be a string"):
            loader.validate_config(config)

    def test_validate_config_invalid_instance_type_type(self) -> None:
        config = {
            "region": "us-east-1",
            "instance_type": 123,
            "disk_size": 50,
        }

        loader = ConfigLoader()

        with pytest.raises(ValueError, match="instance_type must be a string"):
            loader.validate_config(config)

    def test_validate_config_invalid_disk_size_type(self) -> None:
        config = {
            "region": "us-east-1",
            "instance_type": "t3.medium",
            "disk_size": "50",
        }

        loader = ConfigLoader()

        with pytest.raises(ValueError, match="disk_size must be an integer"):
            loader.validate_config(config)

    def test_validate_config_sync_paths_missing_remote(self) -> None:
        config = {
            "region": "us-east-1",
            "instance_type": "t3.medium",
            "disk_size": 50,
            "sync_paths": [{"local": "~/projects"}],
        }

        loader = ConfigLoader()

        with pytest.raises(
            ValueError,
            match="sync_paths entry must have both 'local' and 'remote' keys",
        ):
            loader.validate_config(config)

    def test_validate_config_sync_paths_missing_local(self) -> None:
        config = {
            "region": "us-east-1",
            "instance_type": "t3.medium",
            "disk_size": 50,
            "sync_paths": [{"remote": "~/projects"}],
        }

        loader = ConfigLoader()

        with pytest.raises(
            ValueError,
            match="sync_paths entry must have both 'local' and 'remote' keys",
        ):
            loader.validate_config(config)

    def test_validate_config_sync_paths_valid(self) -> None:
        config = {
            "region": "us-east-1",
            "instance_type": "t3.medium",
            "disk_size": 50,
            "sync_paths": [{"local": "~/projects", "remote": "~/remote"}],
        }

        loader = ConfigLoader()
        loader.validate_config(config)

    def test_get_machine_config_with_built_in_defaults(self) -> None:
        config = {"defaults": {}}

        loader = ConfigLoader()
        merged = loader.get_machine_config(config)

        assert merged["region"] == "us-east-1"
        assert merged["instance_type"] == "t3.medium"
        assert merged["disk_size"] == 50
        assert merged["os_flavor"] == "ubuntu-22.04"
        assert merged["ports"] == []
        assert merged["include_vcs"] is False

    def test_get_machine_config_env_filter_list_replacement(self) -> None:
        config = {
            "defaults": {
                "region": "us-east-1",
                "instance_type": "t3.medium",
                "disk_size": 50,
                "env_filter": ["AWS_.*"],
            },
            "machines": {
                "ml-training": {
                    "env_filter": ["HF_.*", "OPENAI_.*"],
                }
            },
        }

        loader = ConfigLoader()
        merged = loader.get_machine_config(config, "ml-training")

        assert merged["env_filter"] == ["HF_.*", "OPENAI_.*"]
        assert "AWS_.*" not in merged["env_filter"]

    def test_get_machine_config_sync_paths_list_replacement(self) -> None:
        config = {
            "defaults": {
                "region": "us-east-1",
                "instance_type": "t3.medium",
                "disk_size": 50,
                "sync_paths": [{"local": "~/default", "remote": "~/default"}],
            },
            "machines": {
                "jupyter-lab": {
                    "sync_paths": [
                        {"local": "~/projects/app", "remote": "~/app"},
                        {"local": "~/data", "remote": "~/data"},
                    ],
                }
            },
        }

        loader = ConfigLoader()
        merged = loader.get_machine_config(config, "jupyter-lab")

        assert len(merged["sync_paths"]) == 2
        assert merged["sync_paths"][0]["local"] == "~/projects/app"
        assert merged["sync_paths"][1]["local"] == "~/data"

    def test_get_machine_config_script_replacement(self) -> None:
        config = {
            "defaults": {
                "region": "us-east-1",
                "instance_type": "t3.medium",
                "disk_size": 50,
                "setup_script": "echo 'default setup'",
                "startup_script": "echo 'default startup'",
            },
            "machines": {
                "jupyter-lab": {
                    "setup_script": "pip install jupyter",
                    "startup_script": "jupyter lab --no-browser",
                }
            },
        }

        loader = ConfigLoader()
        merged = loader.get_machine_config(config, "jupyter-lab")

        assert merged["setup_script"] == "pip install jupyter"
        assert merged["startup_script"] == "jupyter lab --no-browser"

    def test_validate_config_empty_region(self) -> None:
        config = {
            "region": "",
            "instance_type": "t3.medium",
            "disk_size": 50,
        }

        loader = ConfigLoader()

        with pytest.raises(ValueError, match="region is required"):
            loader.validate_config(config)

    def test_validate_config_empty_instance_type(self) -> None:
        config = {
            "region": "us-east-1",
            "instance_type": "",
            "disk_size": 50,
        }

        loader = ConfigLoader()

        with pytest.raises(ValueError, match="instance_type is required"):
            loader.validate_config(config)

    def test_get_machine_config_no_state_corruption(self) -> None:
        loader = ConfigLoader()
        config = {"defaults": {}}

        merged = loader.get_machine_config(config)
        original_ignore = loader.BUILT_IN_DEFAULTS["ignore"].copy()
        merged["ignore"].append("new_pattern.tmp")

        assert loader.BUILT_IN_DEFAULTS["ignore"] == original_ignore

    def test_validate_config_port_invalid_type_string(self) -> None:
        config = {
            "region": "us-east-1",
            "instance_type": "t3.medium",
            "disk_size": 50,
            "port": "8888",
        }

        loader = ConfigLoader()

        with pytest.raises(ValueError, match="port must be an integer"):
            loader.validate_config(config)

    def test_validate_config_port_invalid_type_float(self) -> None:
        config = {
            "region": "us-east-1",
            "instance_type": "t3.medium",
            "disk_size": 50,
            "port": 8888.5,
        }

        loader = ConfigLoader()

        with pytest.raises(ValueError, match="port must be an integer"):
            loader.validate_config(config)

    def test_validate_config_port_out_of_range_zero(self) -> None:
        config = {
            "region": "us-east-1",
            "instance_type": "t3.medium",
            "disk_size": 50,
            "port": 0,
        }

        loader = ConfigLoader()

        with pytest.raises(ValueError, match="port must be between 1 and 65535"):
            loader.validate_config(config)

    def test_validate_config_port_out_of_range_high(self) -> None:
        config = {
            "region": "us-east-1",
            "instance_type": "t3.medium",
            "disk_size": 50,
            "port": 70000,
        }

        loader = ConfigLoader()

        with pytest.raises(ValueError, match="port must be between 1 and 65535"):
            loader.validate_config(config)

    def test_validate_config_ports_invalid_type(self) -> None:
        config = {
            "region": "us-east-1",
            "instance_type": "t3.medium",
            "disk_size": 50,
            "ports": "8888",
        }

        loader = ConfigLoader()

        with pytest.raises(ValueError, match="ports must be a list"):
            loader.validate_config(config)

    def test_validate_config_ports_non_integer_elements(self) -> None:
        config = {
            "region": "us-east-1",
            "instance_type": "t3.medium",
            "disk_size": 50,
            "ports": [8888, "6006"],
        }

        loader = ConfigLoader()

        with pytest.raises(ValueError, match="ports entries must be integers"):
            loader.validate_config(config)

    def test_validate_config_ports_out_of_range(self) -> None:
        config = {
            "region": "us-east-1",
            "instance_type": "t3.medium",
            "disk_size": 50,
            "ports": [8888, 70000],
        }

        loader = ConfigLoader()

        with pytest.raises(
            ValueError, match="ports entries must be between 1 and 65535"
        ):
            loader.validate_config(config)

    def test_validate_config_ports_empty_list(self) -> None:
        config = {
            "region": "us-east-1",
            "instance_type": "t3.medium",
            "disk_size": 50,
            "ports": [],
        }

        loader = ConfigLoader()
        loader.validate_config(config)

    def test_validate_config_invalid_include_vcs_type(self) -> None:
        config = {
            "region": "us-east-1",
            "instance_type": "t3.medium",
            "disk_size": 50,
            "include_vcs": "true",
        }

        loader = ConfigLoader()

        with pytest.raises(ValueError, match="include_vcs must be a boolean"):
            loader.validate_config(config)

    def test_validate_config_invalid_ignore_type(self) -> None:
        config = {
            "region": "us-east-1",
            "instance_type": "t3.medium",
            "disk_size": 50,
            "ignore": {"*.pyc": True},
        }

        loader = ConfigLoader()

        with pytest.raises(ValueError, match="ignore must be a list"):
            loader.validate_config(config)

    def test_validate_config_invalid_env_filter_elements(self) -> None:
        config = {
            "region": "us-east-1",
            "instance_type": "t3.medium",
            "disk_size": 50,
            "env_filter": ["AWS_.*", 123],
        }

        loader = ConfigLoader()

        with pytest.raises(ValueError, match="env_filter entries must be strings"):
            loader.validate_config(config)

    def test_validate_config_invalid_os_flavor_type(self) -> None:
        config = {
            "region": "us-east-1",
            "instance_type": "t3.medium",
            "disk_size": 50,
            "os_flavor": 123,
        }

        loader = ConfigLoader()

        with pytest.raises(ValueError, match="os_flavor must be a string"):
            loader.validate_config(config)

    def test_validate_config_invalid_command_type(self) -> None:
        config = {
            "region": "us-east-1",
            "instance_type": "t3.medium",
            "disk_size": 50,
            "command": ["jupyter", "lab"],
        }

        loader = ConfigLoader()

        with pytest.raises(ValueError, match="command must be a string"):
            loader.validate_config(config)

    def test_validate_config_invalid_setup_script_type(self) -> None:
        config = {
            "region": "us-east-1",
            "instance_type": "t3.medium",
            "disk_size": 50,
            "setup_script": 123,
        }

        loader = ConfigLoader()

        with pytest.raises(ValueError, match="setup_script must be a string"):
            loader.validate_config(config)

    def test_validate_config_invalid_startup_script_type(self) -> None:
        config = {
            "region": "us-east-1",
            "instance_type": "t3.medium",
            "disk_size": 50,
            "startup_script": ["echo", "hello"],
        }

        loader = ConfigLoader()

        with pytest.raises(ValueError, match="startup_script must be a string"):
            loader.validate_config(config)

    def test_get_machine_config_machine_not_found_lists_available(self) -> None:
        """Verify error message lists available machines when machine not found."""
        config = {
            "defaults": {
                "region": "us-east-1",
                "instance_type": "t3.medium",
                "disk_size": 50,
            },
            "machines": {
                "jupyter-lab": {},
                "ml-training": {},
            },
        }

        loader = ConfigLoader()

        with pytest.raises(ValueError, match="Machine 'nonexistent' not found"):
            loader.get_machine_config(config, "nonexistent")

        with pytest.raises(ValueError, match="Available machines"):
            loader.get_machine_config(config, "nonexistent")

    def test_validate_config_invalid_ignore_list_entries(self) -> None:
        """Verify validation fails when ignore list contains non-string entries."""
        config = {
            "region": "us-east-1",
            "instance_type": "t3.medium",
            "disk_size": 50,
            "ignore": ["*.pyc", 123, "*.log"],
        }

        loader = ConfigLoader()

        with pytest.raises(ValueError, match="ignore entries must be strings"):
            loader.validate_config(config)

    def test_validate_config_invalid_env_filter_regex_pattern(self) -> None:
        """Verify validation fails when env_filter contains invalid regex pattern."""
        config = {
            "region": "us-east-1",
            "instance_type": "t3.medium",
            "disk_size": 50,
            "env_filter": ["AWS_.*", "[invalid(regex"],
        }

        loader = ConfigLoader()

        with pytest.raises(ValueError, match="Invalid regex pattern in env_filter"):
            loader.validate_config(config)
