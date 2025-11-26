from pathlib import Path

import pytest
import yaml
from omegaconf.errors import InterpolationResolutionError

from campers.config import ConfigLoader


class TestConfigLoader:
    def test_load_config_with_defaults_only(self, tmp_path: Path) -> None:
        config_file = tmp_path / "campers.yaml"
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
        config_file = tmp_path / "campers.yaml"
        config_data = {
            "defaults": {
                "region": "us-east-1",
                "instance_type": "t3.medium",
                "disk_size": 50,
            },
            "camps": {
                "jupyter-lab": {
                    "instance_type": "m5.xlarge",
                    "disk_size": 200,
                }
            },
        }
        config_file.write_text(yaml.dump(config_data))

        loader = ConfigLoader()
        config = loader.load_config(str(config_file))

        assert "camps" in config
        assert "jupyter-lab" in config["camps"]
        assert config["camps"]["jupyter-lab"]["instance_type"] == "m5.xlarge"

    def test_load_config_missing_file_uses_built_in_defaults(self) -> None:
        loader = ConfigLoader()
        config = loader.load_config("/nonexistent/path/campers.yaml")

        assert "defaults" in config
        assert config["defaults"] == {}

        merged = loader.get_camp_config(config)
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

        monkeypatch.setenv("CAMPERS_CONFIG", str(config_file))

        loader = ConfigLoader()
        config = loader.load_config()

        assert config["defaults"]["region"] == "eu-west-1"
        assert config["defaults"]["instance_type"] == "t3.small"

    def test_get_camp_config_defaults_only(self) -> None:
        config = {
            "defaults": {
                "region": "us-east-1",
                "instance_type": "t3.medium",
                "disk_size": 50,
            }
        }

        loader = ConfigLoader()
        merged = loader.get_camp_config(config)

        assert merged["region"] == "us-east-1"
        assert merged["instance_type"] == "t3.medium"
        assert merged["disk_size"] == 50

    def test_get_camp_config_with_machine_override(self) -> None:
        config = {
            "defaults": {
                "region": "us-east-1",
                "instance_type": "t3.medium",
                "disk_size": 50,
            },
            "camps": {
                "jupyter-lab": {
                    "instance_type": "m5.xlarge",
                    "disk_size": 200,
                }
            },
        }

        loader = ConfigLoader()
        merged = loader.get_camp_config(config, "jupyter-lab")

        assert merged["instance_type"] == "m5.xlarge"
        assert merged["disk_size"] == 200
        assert merged["region"] == "us-east-1"

    def test_get_camp_config_hierarchy_merging(self) -> None:
        config = {
            "defaults": {
                "region": "us-east-1",
                "instance_type": "t3.medium",
                "disk_size": 100,
            },
            "camps": {
                "ml-training": {
                    "disk_size": 200,
                }
            },
        }

        loader = ConfigLoader()
        merged = loader.get_camp_config(config, "ml-training")

        assert merged["disk_size"] == 200
        assert merged["region"] == "us-east-1"
        assert merged["instance_type"] == "t3.medium"

    def test_get_camp_config_list_replacement_not_merge(self) -> None:
        config = {
            "defaults": {
                "region": "us-east-1",
                "instance_type": "t3.medium",
                "disk_size": 50,
                "ignore": ["*.pyc", "__pycache__"],
            },
            "camps": {
                "jupyter-lab": {
                    "ignore": ["*.pyc", "data/", "models/"],
                }
            },
        }

        loader = ConfigLoader()
        merged = loader.get_camp_config(config, "jupyter-lab")

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

    def test_get_camp_config_with_built_in_defaults(self) -> None:
        config = {"defaults": {}}

        loader = ConfigLoader()
        merged = loader.get_camp_config(config)

        assert merged["region"] == "us-east-1"
        assert merged["instance_type"] == "t3.medium"
        assert merged["disk_size"] == 50
        assert merged["ports"] == []
        assert merged["include_vcs"] is False

    def test_get_camp_config_env_filter_list_replacement(self) -> None:
        config = {
            "defaults": {
                "region": "us-east-1",
                "instance_type": "t3.medium",
                "disk_size": 50,
                "env_filter": ["AWS_.*"],
            },
            "camps": {
                "ml-training": {
                    "env_filter": ["HF_.*", "OPENAI_.*"],
                }
            },
        }

        loader = ConfigLoader()
        merged = loader.get_camp_config(config, "ml-training")

        assert merged["env_filter"] == ["HF_.*", "OPENAI_.*"]
        assert "AWS_.*" not in merged["env_filter"]

    def test_get_camp_config_sync_paths_list_replacement(self) -> None:
        config = {
            "defaults": {
                "region": "us-east-1",
                "instance_type": "t3.medium",
                "disk_size": 50,
                "sync_paths": [{"local": "~/default", "remote": "~/default"}],
            },
            "camps": {
                "jupyter-lab": {
                    "sync_paths": [
                        {"local": "~/projects/app", "remote": "~/app"},
                        {"local": "~/data", "remote": "~/data"},
                    ],
                }
            },
        }

        loader = ConfigLoader()
        merged = loader.get_camp_config(config, "jupyter-lab")

        assert len(merged["sync_paths"]) == 2
        assert merged["sync_paths"][0]["local"] == "~/projects/app"
        assert merged["sync_paths"][1]["local"] == "~/data"

    def test_get_camp_config_script_replacement(self) -> None:
        config = {
            "defaults": {
                "region": "us-east-1",
                "instance_type": "t3.medium",
                "disk_size": 50,
                "setup_script": "echo 'default setup'",
                "startup_script": "echo 'default startup'",
            },
            "camps": {
                "jupyter-lab": {
                    "setup_script": "pip install jupyter",
                    "startup_script": "jupyter lab --no-browser",
                }
            },
        }

        loader = ConfigLoader()
        merged = loader.get_camp_config(config, "jupyter-lab")

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

    def test_get_camp_config_no_state_corruption(self) -> None:
        loader = ConfigLoader()
        config = {"defaults": {}}

        merged = loader.get_camp_config(config)
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

    def test_get_camp_config_machine_not_found_lists_available(self) -> None:
        """Verify error message lists available camps when machine not found."""
        config = {
            "defaults": {
                "region": "us-east-1",
                "instance_type": "t3.medium",
                "disk_size": 50,
            },
            "camps": {
                "jupyter-lab": {},
                "ml-training": {},
            },
        }

        loader = ConfigLoader()

        with pytest.raises(ValueError, match="Camp 'nonexistent' not found"):
            loader.get_camp_config(config, "nonexistent")

        with pytest.raises(ValueError, match="Available camps"):
            loader.get_camp_config(config, "nonexistent")

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


class TestConfigLoaderVariableSubstitution:
    """Test variable substitution functionality using OmegaConf."""

    def test_simple_variable_substitution(self, tmp_path: Path) -> None:
        config_file = tmp_path / "campers.yaml"
        config_data = {
            "vars": {
                "project_name": "ml-training",
                "base_path": "/home/ubuntu",
            },
            "defaults": {
                "region": "us-east-1",
                "instance_type": "t3.medium",
                "disk_size": 50,
            },
            "camps": {
                "dev": {
                    "command": "cd ${base_path}/${project_name} && python train.py",
                }
            },
        }
        config_file.write_text(yaml.dump(config_data))

        loader = ConfigLoader()
        config = loader.load_config(str(config_file))

        assert "vars" in config
        assert config["vars"]["project_name"] == "ml-training"
        assert config["vars"]["base_path"] == "/home/ubuntu"
        assert (
            config["camps"]["dev"]["command"]
            == "cd /home/ubuntu/ml-training && python train.py"
        )

    def test_nested_variable_expansion(self, tmp_path: Path) -> None:
        config_file = tmp_path / "campers.yaml"
        config_data = {
            "vars": {
                "base_path": "/home/ubuntu",
                "project_name": "ml-training",
                "project_path": "${base_path}/${project_name}",
            },
            "defaults": {
                "region": "us-east-1",
                "instance_type": "t3.medium",
                "disk_size": 50,
            },
        }
        config_file.write_text(yaml.dump(config_data))

        loader = ConfigLoader()
        config = loader.load_config(str(config_file))

        assert config["vars"]["project_path"] == "/home/ubuntu/ml-training"

    def test_variable_reference_in_camp_config(self, tmp_path: Path) -> None:
        config_file = tmp_path / "campers.yaml"
        config_data = {
            "vars": {
                "aws_region": "us-west-2",
                "project_path": "/home/ubuntu/ml-training",
                "gpu_count": 4,
            },
            "defaults": {
                "region": "us-east-1",
                "instance_type": "t3.medium",
                "disk_size": 50,
            },
            "camps": {
                "gpu-machine": {
                    "region": "${aws_region}",
                    "command": "cd ${project_path} && python train.py --gpus ${gpu_count}",
                }
            },
        }
        config_file.write_text(yaml.dump(config_data))

        loader = ConfigLoader()
        config = loader.load_config(str(config_file))

        assert config["camps"]["gpu-machine"]["region"] == "us-west-2"
        assert (
            config["camps"]["gpu-machine"]["command"]
            == "cd /home/ubuntu/ml-training && python train.py --gpus 4"
        )

    def test_environment_variable_access(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("TEST_USER", "testuser")
        config_file = tmp_path / "campers.yaml"
        config_data = {
            "vars": {
                "user_home": "/home/${oc.env:TEST_USER}",
            },
            "defaults": {
                "region": "us-east-1",
                "instance_type": "t3.medium",
                "disk_size": 50,
            },
        }
        config_file.write_text(yaml.dump(config_data))

        loader = ConfigLoader()
        config = loader.load_config(str(config_file))

        assert config["vars"]["user_home"] == "/home/testuser"

    def test_environment_variable_with_default(self, tmp_path: Path) -> None:
        config_file = tmp_path / "campers.yaml"
        config_data = {
            "vars": {
                "db_password": "${oc.env:MISSING_DB_PASSWORD,default_password}",
            },
            "defaults": {
                "region": "us-east-1",
                "instance_type": "t3.medium",
                "disk_size": 50,
            },
        }
        config_file.write_text(yaml.dump(config_data))

        loader = ConfigLoader()
        config = loader.load_config(str(config_file))

        assert config["vars"]["db_password"] == "default_password"

    def test_environment_variable_with_default_numeric(self, tmp_path: Path) -> None:
        config_file = tmp_path / "campers.yaml"
        config_data = {
            "vars": {
                "port": "${oc.env:MISSING_PORT,8080}",
            },
            "defaults": {
                "region": "us-east-1",
                "instance_type": "t3.medium",
                "disk_size": 50,
            },
        }
        config_file.write_text(yaml.dump(config_data))

        loader = ConfigLoader()
        config = loader.load_config(str(config_file))

        assert config["vars"]["port"] == "8080"

    def test_undefined_variable_raises_error(self, tmp_path: Path) -> None:
        config_file = tmp_path / "campers.yaml"
        config_data = {
            "vars": {
                "base_path": "/home/ubuntu",
            },
            "defaults": {
                "region": "us-east-1",
                "instance_type": "t3.medium",
                "disk_size": 50,
            },
            "camps": {
                "dev": {
                    "command": "cd ${undefined_variable} && python train.py",
                }
            },
        }
        config_file.write_text(yaml.dump(config_data))

        loader = ConfigLoader()

        with pytest.raises(InterpolationResolutionError) as exc_info:
            loader.load_config(str(config_file))

        assert (
            "undefined_variable" in str(exc_info.value)
            or "missing" in str(exc_info.value).lower()
        )

    def test_circular_reference_handling(self, tmp_path: Path) -> None:
        config_file = tmp_path / "campers.yaml"
        config_data = {
            "vars": {
                "var_a": "${var_b}",
                "var_b": "${var_a}",
            },
            "defaults": {
                "region": "us-east-1",
                "instance_type": "t3.medium",
                "disk_size": 50,
            },
        }
        config_file.write_text(yaml.dump(config_data))

        loader = ConfigLoader()

        with pytest.raises(InterpolationResolutionError):
            loader.load_config(str(config_file))

    def test_escaped_literal_dollar_sign(self, tmp_path: Path) -> None:
        config_file = tmp_path / "campers.yaml"
        config_data = {
            "vars": {
                "literal": r"\${not_a_variable}",
            },
            "defaults": {
                "region": "us-east-1",
                "instance_type": "t3.medium",
                "disk_size": 50,
            },
        }
        config_file.write_text(yaml.dump(config_data))

        loader = ConfigLoader()
        config = loader.load_config(str(config_file))

        assert config["vars"]["literal"] == "${not_a_variable}"

    def test_type_preservation_integer(self, tmp_path: Path) -> None:
        config_file = tmp_path / "campers.yaml"
        config_data = {
            "vars": {
                "port": 8080,
                "server_port": "${port}",
            },
            "defaults": {
                "region": "us-east-1",
                "instance_type": "t3.medium",
                "disk_size": 50,
            },
        }
        config_file.write_text(yaml.dump(config_data))

        loader = ConfigLoader()
        config = loader.load_config(str(config_file))

        assert config["vars"]["server_port"] == 8080
        assert isinstance(config["vars"]["server_port"], int)

    def test_type_preservation_boolean(self, tmp_path: Path) -> None:
        config_file = tmp_path / "campers.yaml"
        config_data = {
            "vars": {
                "debug_enabled": True,
                "enable_feature": "${debug_enabled}",
            },
            "defaults": {
                "region": "us-east-1",
                "instance_type": "t3.medium",
                "disk_size": 50,
            },
        }
        config_file.write_text(yaml.dump(config_data))

        loader = ConfigLoader()
        config = loader.load_config(str(config_file))

        assert config["vars"]["enable_feature"] is True
        assert isinstance(config["vars"]["enable_feature"], bool)

    def test_type_preservation_float(self, tmp_path: Path) -> None:
        config_file = tmp_path / "campers.yaml"
        config_data = {
            "vars": {
                "timeout": 3.14,
                "request_timeout": "${timeout}",
            },
            "defaults": {
                "region": "us-east-1",
                "instance_type": "t3.medium",
                "disk_size": 50,
            },
        }
        config_file.write_text(yaml.dump(config_data))

        loader = ConfigLoader()
        config = loader.load_config(str(config_file))

        assert config["vars"]["request_timeout"] == 3.14
        assert isinstance(config["vars"]["request_timeout"], float)

    def test_type_preservation_list(self, tmp_path: Path) -> None:
        config_file = tmp_path / "campers.yaml"
        config_data = {
            "vars": {
                "packages": ["tensorflow", "pytorch"],
                "installed_packages": "${packages}",
            },
            "defaults": {
                "region": "us-east-1",
                "instance_type": "t3.medium",
                "disk_size": 50,
            },
        }
        config_file.write_text(yaml.dump(config_data))

        loader = ConfigLoader()
        config = loader.load_config(str(config_file))

        assert config["vars"]["installed_packages"] == ["tensorflow", "pytorch"]
        assert isinstance(config["vars"]["installed_packages"], list)

    def test_type_preservation_dict(self, tmp_path: Path) -> None:
        config_file = tmp_path / "campers.yaml"
        config_data = {
            "vars": {
                "settings": {"key": "value", "debug": True},
                "app_settings": "${settings}",
            },
            "defaults": {
                "region": "us-east-1",
                "instance_type": "t3.medium",
                "disk_size": 50,
            },
        }
        config_file.write_text(yaml.dump(config_data))

        loader = ConfigLoader()
        config = loader.load_config(str(config_file))

        assert config["vars"]["app_settings"] == {"key": "value", "debug": True}
        assert isinstance(config["vars"]["app_settings"], dict)

    def test_backwards_compatibility_no_vars_section(self, tmp_path: Path) -> None:
        config_file = tmp_path / "campers.yaml"
        config_data = {
            "defaults": {
                "region": "us-east-1",
                "instance_type": "t3.medium",
                "disk_size": 50,
            },
            "camps": {
                "dev": {
                    "command": "python train.py",
                }
            },
        }
        config_file.write_text(yaml.dump(config_data))

        loader = ConfigLoader()
        config = loader.load_config(str(config_file))

        assert "vars" not in config or config.get("vars") is None
        assert config["defaults"]["region"] == "us-east-1"
        assert config["camps"]["dev"]["command"] == "python train.py"

    def test_variable_in_nested_dict(self, tmp_path: Path) -> None:
        config_file = tmp_path / "campers.yaml"
        config_data = {
            "vars": {
                "project_path": "/home/ubuntu/project",
            },
            "defaults": {
                "region": "us-east-1",
                "instance_type": "t3.medium",
                "disk_size": 50,
            },
            "camps": {
                "dev": {
                    "env": {
                        "PROJECT_ROOT": "${project_path}",
                        "DEBUG": "true",
                    }
                }
            },
        }
        config_file.write_text(yaml.dump(config_data))

        loader = ConfigLoader()
        config = loader.load_config(str(config_file))

        assert (
            config["camps"]["dev"]["env"]["PROJECT_ROOT"] == "/home/ubuntu/project"
        )

    def test_variable_in_list(self, tmp_path: Path) -> None:
        config_file = tmp_path / "campers.yaml"
        config_data = {
            "vars": {
                "port": 8080,
            },
            "defaults": {
                "region": "us-east-1",
                "instance_type": "t3.medium",
                "disk_size": 50,
                "ports": ["${port}", 9000],
            },
        }
        config_file.write_text(yaml.dump(config_data))

        loader = ConfigLoader()
        config = loader.load_config(str(config_file))

        assert config["defaults"]["ports"][0] == 8080
        assert config["defaults"]["ports"][1] == 9000

    def test_multiple_variables_in_string(self, tmp_path: Path) -> None:
        config_file = tmp_path / "campers.yaml"
        config_data = {
            "vars": {
                "user": "testuser",
                "host": "localhost",
                "port": 8080,
            },
            "defaults": {
                "region": "us-east-1",
                "instance_type": "t3.medium",
                "disk_size": 50,
            },
            "camps": {
                "dev": {
                    "url": "http://${user}:${port}@${host}",
                }
            },
        }
        config_file.write_text(yaml.dump(config_data))

        loader = ConfigLoader()
        config = loader.load_config(str(config_file))

        assert config["camps"]["dev"]["url"] == "http://testuser:8080@localhost"

    def test_empty_vars_section(self, tmp_path: Path) -> None:
        config_file = tmp_path / "campers.yaml"
        config_data = {
            "vars": {},
            "defaults": {
                "region": "us-east-1",
                "instance_type": "t3.medium",
                "disk_size": 50,
            },
        }
        config_file.write_text(yaml.dump(config_data))

        loader = ConfigLoader()
        config = loader.load_config(str(config_file))

        assert config["vars"] == {}

    def test_complex_nested_variable_expansion(self, tmp_path: Path) -> None:
        config_file = tmp_path / "campers.yaml"
        config_data = {
            "vars": {
                "org": "myorg",
                "project": "myproject",
                "env": "prod",
                "base_path": "/opt/${org}/${project}",
                "config_path": "${base_path}/${env}",
                "log_path": "${config_path}/logs",
            },
            "defaults": {
                "region": "us-east-1",
                "instance_type": "t3.medium",
                "disk_size": 50,
            },
        }
        config_file.write_text(yaml.dump(config_data))

        loader = ConfigLoader()
        config = loader.load_config(str(config_file))

        assert config["vars"]["log_path"] == "/opt/myorg/myproject/prod/logs"

    def test_variable_with_special_characters(self, tmp_path: Path) -> None:
        config_file = tmp_path / "campers.yaml"
        config_data = {
            "vars": {
                "special_path": "/path-with-dash_and_underscore",
            },
            "defaults": {
                "region": "us-east-1",
                "instance_type": "t3.medium",
                "disk_size": 50,
            },
            "camps": {
                "dev": {
                    "working_dir": "${special_path}",
                }
            },
        }
        config_file.write_text(yaml.dump(config_data))

        loader = ConfigLoader()
        config = loader.load_config(str(config_file))

        assert (
            config["camps"]["dev"]["working_dir"] == "/path-with-dash_and_underscore"
        )

    def test_variable_reference_within_vars_section(self, tmp_path: Path) -> None:
        config_file = tmp_path / "campers.yaml"
        config_data = {
            "vars": {
                "version": "1.0",
                "image_tag": "myimage:${version}",
            },
            "defaults": {
                "region": "us-east-1",
                "instance_type": "t3.medium",
                "disk_size": 50,
            },
        }
        config_file.write_text(yaml.dump(config_data))

        loader = ConfigLoader()
        config = loader.load_config(str(config_file))

        assert config["vars"]["image_tag"] == "myimage:1.0"

    def test_variable_name_with_underscore(self, tmp_path: Path) -> None:
        config_file = tmp_path / "campers.yaml"
        config_data = {
            "vars": {
                "project_name": "ml-training",
                "working_directory": "/home/ubuntu",
            },
            "defaults": {
                "region": "us-east-1",
                "instance_type": "t3.medium",
                "disk_size": 50,
            },
            "camps": {
                "dev": {
                    "command": "cd ${working_directory}/${project_name}",
                }
            },
        }
        config_file.write_text(yaml.dump(config_data))

        loader = ConfigLoader()
        config = loader.load_config(str(config_file))

        assert config["camps"]["dev"]["command"] == "cd /home/ubuntu/ml-training"

    def test_string_interpolation_with_literal_dollar(self, tmp_path: Path) -> None:
        config_file = tmp_path / "campers.yaml"
        config_data = {
            "vars": {
                "currency": "USD",
                "amount": "100",
            },
            "defaults": {
                "region": "us-east-1",
                "instance_type": "t3.medium",
                "disk_size": 50,
            },
            "camps": {
                "dev": {
                    "display": "${amount} ${currency}",
                }
            },
        }
        config_file.write_text(yaml.dump(config_data))

        loader = ConfigLoader()
        config = loader.load_config(str(config_file))

        assert config["camps"]["dev"]["display"] == "100 USD"

    def test_relative_path_interpolation(self, tmp_path: Path) -> None:
        config_file = tmp_path / "campers.yaml"
        config_data = {
            "defaults": {
                "region": "us-east-1",
            },
            "camps": {
                "dev": {
                    "region": "${...defaults.region}",
                }
            },
        }
        config_file.write_text(yaml.dump(config_data))

        loader = ConfigLoader()
        config = loader.load_config(str(config_file))

        assert config["camps"]["dev"]["region"] == "us-east-1"

    def test_ssh_username_validation_valid_ubuntu(self, tmp_path: Path) -> None:
        config_file = tmp_path / "campers.yaml"
        config_data = {
            "defaults": {
                "region": "us-east-1",
                "instance_type": "t3.medium",
                "disk_size": 50,
                "ssh_username": "ubuntu",
            }
        }
        config_file.write_text(yaml.dump(config_data))

        loader = ConfigLoader()
        config = loader.load_config(str(config_file))
        merged = loader.get_camp_config(config)

        loader.validate_config(merged)
        assert merged["ssh_username"] == "ubuntu"

    def test_ssh_username_validation_valid_ec2_user(self, tmp_path: Path) -> None:
        config_file = tmp_path / "campers.yaml"
        config_data = {
            "defaults": {
                "region": "us-east-1",
                "instance_type": "t3.medium",
                "disk_size": 50,
                "ssh_username": "ec2-user",
            }
        }
        config_file.write_text(yaml.dump(config_data))

        loader = ConfigLoader()
        config = loader.load_config(str(config_file))
        merged = loader.get_camp_config(config)

        loader.validate_config(merged)
        assert merged["ssh_username"] == "ec2-user"

    def test_ssh_username_validation_invalid_uppercase(self, tmp_path: Path) -> None:
        config = {
            "defaults": {
                "region": "us-east-1",
                "instance_type": "t3.medium",
                "disk_size": 50,
                "ssh_username": "Ubuntu",
            }
        }

        loader = ConfigLoader()
        with pytest.raises(ValueError) as exc_info:
            loader.validate_config(config["defaults"])

        assert "Invalid ssh_username" in str(exc_info.value)

    def test_ssh_username_validation_invalid_special_chars(
        self, tmp_path: Path
    ) -> None:
        config = {
            "defaults": {
                "region": "us-east-1",
                "instance_type": "t3.medium",
                "disk_size": 50,
                "ssh_username": "user@host",
            }
        }

        loader = ConfigLoader()
        with pytest.raises(ValueError) as exc_info:
            loader.validate_config(config["defaults"])

        assert "Invalid ssh_username" in str(exc_info.value)

    def test_ssh_username_validation_valid_underscore_start(
        self, tmp_path: Path
    ) -> None:
        config = {
            "defaults": {
                "region": "us-east-1",
                "instance_type": "t3.medium",
                "disk_size": 50,
                "ssh_username": "_sys_user",
            }
        }

        loader = ConfigLoader()
        loader.validate_config(config["defaults"])

    def test_ssh_username_validation_valid_with_numbers(self, tmp_path: Path) -> None:
        config = {
            "defaults": {
                "region": "us-east-1",
                "instance_type": "t3.medium",
                "disk_size": 50,
                "ssh_username": "user123",
            }
        }

        loader = ConfigLoader()
        loader.validate_config(config["defaults"])

    def test_ansible_playbook_and_playbooks_mutual_exclusivity(self) -> None:
        config = {
            "region": "us-east-1",
            "instance_type": "t3.medium",
            "disk_size": 50,
            "ansible_playbook": "setup",
            "ansible_playbooks": ["setup", "deploy"],
        }

        loader = ConfigLoader()
        with pytest.raises(ValueError) as exc_info:
            loader.validate_config(config)

        error_msg = str(exc_info.value)
        assert "mutually exclusive" in error_msg.lower()

    def test_ansible_playbooks_must_be_list(self) -> None:
        config = {
            "region": "us-east-1",
            "instance_type": "t3.medium",
            "disk_size": 50,
            "ansible_playbooks": "single_playbook",
        }

        loader = ConfigLoader()
        with pytest.raises(ValueError) as exc_info:
            loader.validate_config(config)

        assert "ansible_playbooks must be a list" in str(exc_info.value)

    def test_ansible_playbook_is_valid_string(self) -> None:
        config = {
            "region": "us-east-1",
            "instance_type": "t3.medium",
            "disk_size": 50,
            "ansible_playbook": "setup",
        }

        loader = ConfigLoader()
        loader.validate_config(config)

    def test_ansible_playbook_invalid_type(self) -> None:
        config = {
            "region": "us-east-1",
            "instance_type": "t3.medium",
            "disk_size": 50,
            "ansible_playbook": ["setup"],
        }

        loader = ConfigLoader()
        with pytest.raises(ValueError) as exc_info:
            loader.validate_config(config)

        assert "ansible_playbook must be a string" in str(exc_info.value)

    def test_on_exit_default_value_is_stop(self) -> None:
        loader = ConfigLoader()
        config = loader.load_config("/nonexistent/path/campers.yaml")

        merged = loader.get_camp_config(config)
        assert merged.get("on_exit", "stop") == "stop"

    def test_on_exit_stop_valid(self) -> None:
        config = {
            "region": "us-east-1",
            "instance_type": "t3.medium",
            "disk_size": 50,
            "on_exit": "stop",
        }

        loader = ConfigLoader()
        loader.validate_config(config)

    def test_on_exit_terminate_valid(self) -> None:
        config = {
            "region": "us-east-1",
            "instance_type": "t3.medium",
            "disk_size": 50,
            "on_exit": "terminate",
        }

        loader = ConfigLoader()
        loader.validate_config(config)

    def test_on_exit_invalid_value_rejected(self) -> None:
        config = {
            "region": "us-east-1",
            "instance_type": "t3.medium",
            "disk_size": 50,
            "on_exit": "invalid",
        }

        loader = ConfigLoader()
        with pytest.raises(ValueError) as exc_info:
            loader.validate_config(config)

        assert "on_exit must be 'stop' or 'terminate'" in str(exc_info.value)

    def test_on_exit_per_machine_override(self, tmp_path: Path) -> None:
        config_file = tmp_path / "campers.yaml"
        config_data = {
            "defaults": {
                "region": "us-east-1",
                "instance_type": "t3.medium",
                "disk_size": 50,
                "on_exit": "stop",
            },
            "camps": {
                "test-machine": {
                    "on_exit": "terminate",
                }
            },
        }
        config_file.write_text(yaml.dump(config_data))

        loader = ConfigLoader()
        full_config = loader.load_config(str(config_file))

        defaults = full_config.get("defaults", {})
        assert defaults.get("on_exit") == "stop"

        camps = full_config.get("camps", {})
        assert camps.get("test-machine", {}).get("on_exit") == "terminate"
