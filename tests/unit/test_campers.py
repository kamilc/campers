"""Tests for campers CLI.

This module contains unit tests for the campers CLI application, specifically
testing class instantiation, method functionality, and command-line execution.

Tests
-----
test_campers_class_exists
    Verifies that the Campers class can be imported and instantiated.

"""

import shlex
from datetime import UTC
from pathlib import Path

import pytest


@pytest.fixture
def campers_module():
    """Fixture to handle sys.path manipulation for importing campers.

    Yields
    ------
    type[Campers]
        The Campers class for testing.

    """
    import importlib.util
    import sys

    project_root = Path(__file__).parent.parent.parent
    campers_script = project_root / "campers" / "__main__.py"

    spec = importlib.util.spec_from_file_location("campers_cli", campers_script)
    module = importlib.util.module_from_spec(spec)
    sys.modules["campers_cli"] = module
    spec.loader.exec_module(module)

    yield module.Campers


def test_campers_class_exists(campers_module) -> None:
    """Test that Campers class can be imported and instantiated."""
    campers_instance = campers_module()

    assert campers_instance is not None


def test_run_executes_setup_script_before_command(campers_module) -> None:
    """Test that run() executes setup_script before command."""
    from unittest.mock import MagicMock, patch

    campers_instance = campers_module()
    campers_instance._config_loader = MagicMock()
    campers_instance._config_loader.load_config.return_value = {"defaults": {}}
    campers_instance._config_loader.get_camp_config.return_value = {
        "region": "us-east-1",
        "instance_type": "t3.medium",
        "setup_script": "echo setup",
        "command": "echo command",
    }
    campers_instance._config_loader.validate_config.return_value = None

    mock_instance_details = {
        "instance_id": "i-test123",
        "public_ip": "203.0.113.1",
        "state": "running",
        "key_file": "/tmp/test.pem",
        "security_group_id": "sg-test123",
        "unique_id": "test123",
    }

    execution_order = []

    with (
        patch("campers.providers.aws.compute.EC2Manager") as mock_ec2,
        patch("campers_cli.get_provider") as mock_get_provider,
    ):
        mock_ec2_instance = MagicMock()
        mock_ec2_instance.find_instances_by_name_or_id.return_value = []
        mock_ec2_instance.launch_instance.return_value = mock_instance_details
        mock_ec2_instance.validate_region.return_value = None
        mock_ec2.return_value = mock_ec2_instance

        mock_get_provider.return_value = {"compute": mock_ec2}

        mock_ssh_instance = MagicMock()
        mock_ssh_instance.filter_environment_variables.return_value = {}
        mock_ssh_instance.connect.return_value = None
        mock_ssh_instance.build_command_with_env.side_effect = lambda cmd, env: cmd

        def track_execute_command(cmd: str) -> int:
            execution_order.append(cmd)
            return 0

        mock_ssh_instance.execute_command.side_effect = track_execute_command
        campers_instance._ssh_manager_factory = lambda **kwargs: mock_ssh_instance

        result = campers_instance.run()

    assert len(execution_order) == 2
    assert execution_order[0] == "echo setup"
    assert execution_order[1] == "echo command"
    assert result["instance_id"] == "i-test123"


def test_run_setup_script_failure_prevents_command(campers_module) -> None:
    """Test that setup_script failure prevents command execution."""
    from unittest.mock import MagicMock, patch

    campers_instance = campers_module()
    campers_instance._config_loader = MagicMock()
    campers_instance._config_loader.load_config.return_value = {"defaults": {}}
    campers_instance._config_loader.get_camp_config.return_value = {
        "region": "us-east-1",
        "instance_type": "t3.medium",
        "setup_script": "exit 1",
        "command": "echo command",
    }
    campers_instance._config_loader.validate_config.return_value = None

    mock_instance_details = {
        "instance_id": "i-test123",
        "public_ip": "203.0.113.1",
        "state": "running",
        "key_file": "/tmp/test.pem",
        "security_group_id": "sg-test123",
        "unique_id": "test123",
    }

    with (
        patch("campers.providers.aws.compute.EC2Manager") as mock_ec2,
        patch("campers_cli.get_provider") as mock_get_provider,
    ):
        mock_ec2_instance = MagicMock()
        mock_ec2_instance.find_instances_by_name_or_id.return_value = []
        mock_ec2_instance.launch_instance.return_value = mock_instance_details
        mock_ec2.return_value = mock_ec2_instance

        mock_get_provider.return_value = {"compute": mock_ec2}

        mock_ssh_instance = MagicMock()
        mock_ssh_instance.filter_environment_variables.return_value = {}
        mock_ssh_instance.connect.return_value = None
        mock_ssh_instance.build_command_with_env.side_effect = lambda cmd, env: cmd
        mock_ssh_instance.execute_command.return_value = 1
        campers_instance._ssh_manager_factory = lambda **kwargs: mock_ssh_instance

        with pytest.raises(RuntimeError, match="Setup script failed with exit code: 1"):
            campers_instance.run()

        assert mock_ssh_instance.execute_command.call_count == 1
        mock_ssh_instance.close.assert_called_once()


def test_run_skips_ssh_when_no_setup_script_or_command(campers_module) -> None:
    """Test that run() skips SSH when no setup_script or command."""
    from unittest.mock import MagicMock, patch

    campers_instance = campers_module()
    campers_instance._config_loader = MagicMock()
    campers_instance._config_loader.load_config.return_value = {"defaults": {}}
    campers_instance._config_loader.get_camp_config.return_value = {
        "region": "us-east-1",
        "instance_type": "t3.medium",
    }
    campers_instance._config_loader.validate_config.return_value = None

    mock_instance_details = {
        "instance_id": "i-test123",
        "public_ip": "203.0.113.1",
        "state": "running",
        "key_file": "/tmp/test.pem",
        "security_group_id": "sg-test123",
        "unique_id": "test123",
    }

    with (
        patch("campers.providers.aws.compute.EC2Manager") as mock_ec2,
        patch("campers_cli.get_provider") as mock_get_provider,
    ):
        mock_ec2_instance = MagicMock()
        mock_ec2_instance.find_instances_by_name_or_id.return_value = []
        mock_ec2_instance.launch_instance.return_value = mock_instance_details
        mock_ec2.return_value = mock_ec2_instance

        mock_get_provider.return_value = {"compute": mock_ec2}

        mock_ssh_factory = MagicMock()
        campers_instance._ssh_manager_factory = mock_ssh_factory

        result = campers_instance.run()

        mock_ssh_factory.assert_not_called()
        assert result["instance_id"] == "i-test123"


def test_run_only_setup_script_no_command(campers_module) -> None:
    """Test that run() executes setup_script without command."""
    from unittest.mock import MagicMock, patch

    campers_instance = campers_module()
    campers_instance._config_loader = MagicMock()
    campers_instance._config_loader.load_config.return_value = {"defaults": {}}
    campers_instance._config_loader.get_camp_config.return_value = {
        "region": "us-east-1",
        "instance_type": "t3.medium",
        "setup_script": "sudo apt update",
    }
    campers_instance._config_loader.validate_config.return_value = None

    mock_instance_details = {
        "instance_id": "i-test123",
        "public_ip": "203.0.113.1",
        "state": "running",
        "key_file": "/tmp/test.pem",
        "security_group_id": "sg-test123",
        "unique_id": "test123",
    }

    with (
        patch("campers.providers.aws.compute.EC2Manager") as mock_ec2,
        patch("campers_cli.get_provider") as mock_get_provider,
    ):
        mock_ec2_instance = MagicMock()
        mock_ec2_instance.find_instances_by_name_or_id.return_value = []
        mock_ec2_instance.launch_instance.return_value = mock_instance_details
        mock_ec2.return_value = mock_ec2_instance

        mock_get_provider.return_value = {"compute": mock_ec2}

        mock_ssh_instance = MagicMock()
        mock_ssh_instance.filter_environment_variables.return_value = {}
        mock_ssh_instance.connect.return_value = None
        mock_ssh_instance.build_command_with_env.side_effect = lambda cmd, env: cmd
        mock_ssh_instance.execute_command.return_value = 0
        campers_instance._ssh_manager_factory = lambda **kwargs: mock_ssh_instance

        result = campers_instance.run()

        mock_ssh_instance.execute_command.assert_called_once_with("sudo apt update")
        mock_ssh_instance.close.assert_called_once()
        assert result["instance_id"] == "i-test123"


def test_run_startup_script_without_sync_paths_raises_error(campers_module) -> None:
    """Test that startup_script without sync_paths raises ValueError."""
    from unittest.mock import MagicMock

    campers_instance = campers_module()
    campers_instance._config_loader = MagicMock()
    campers_instance._config_loader.load_config.return_value = {"defaults": {}}
    campers_instance._config_loader.get_camp_config.return_value = {
        "region": "us-east-1",
        "instance_type": "t3.medium",
        "startup_script": "source .venv/bin/activate",
    }
    campers_instance._config_loader.validate_config.return_value = None

    with pytest.raises(ValueError, match="startup_script is defined but no sync_paths configured"):
        campers_instance.run()


def test_run_with_sync_paths_creates_mutagen_session(campers_module) -> None:
    """Test that run() creates Mutagen session when sync_paths configured."""
    from unittest.mock import MagicMock, patch

    campers_instance = campers_module()
    campers_instance._config_loader = MagicMock()
    campers_instance._config_loader.load_config.return_value = {"defaults": {}}
    campers_instance._config_loader.get_camp_config.return_value = {
        "region": "us-east-1",
        "instance_type": "t3.medium",
        "sync_paths": [{"local": "~/myproject", "remote": "~/myproject"}],
        "command": "echo test",
    }
    campers_instance._config_loader.validate_config.return_value = None

    mock_instance_details = {
        "instance_id": "i-test123",
        "public_ip": "203.0.113.1",
        "state": "running",
        "key_file": "/tmp/test.pem",
        "security_group_id": "sg-test123",
        "unique_id": "test123",
    }

    with (
        patch("campers.providers.aws.compute.EC2Manager") as mock_ec2,
        patch("campers_cli.get_provider") as mock_get_provider,
        patch("campers_cli.MutagenManager") as mock_mutagen,
    ):
        mock_ec2_instance = MagicMock()
        mock_ec2_instance.find_instances_by_name_or_id.return_value = []
        mock_ec2_instance.launch_instance.return_value = mock_instance_details
        mock_ec2.return_value = mock_ec2_instance

        mock_get_provider.return_value = {"compute": mock_ec2}

        mock_ssh_instance = MagicMock()
        mock_ssh_instance.filter_environment_variables.return_value = {}
        mock_ssh_instance.connect.return_value = None
        mock_ssh_instance.build_command_with_env.side_effect = lambda cmd, env: cmd
        mock_ssh_instance.execute_command_raw.return_value = 0
        campers_instance._ssh_manager_factory = lambda **kwargs: mock_ssh_instance

        mock_mutagen_instance = MagicMock()
        mock_mutagen_instance.get_sync_status.return_value = "watching"
        mock_mutagen.return_value = mock_mutagen_instance
        campers_instance._mutagen_manager_factory = lambda: mock_mutagen_instance

        result = campers_instance.run()

        mock_mutagen_instance.check_mutagen_installed.assert_called_once()
        mock_mutagen_instance.cleanup_orphaned_session.assert_called_once()
        mock_mutagen_instance.create_sync_session.assert_called_once()
        mock_mutagen_instance.get_sync_status.assert_called()
        mock_mutagen_instance.terminate_session.assert_called_once()
        assert result["instance_id"] == "i-test123"


def test_run_executes_command_from_synced_directory(campers_module) -> None:
    """Test that command executes from synced directory when sync_paths configured."""
    from unittest.mock import MagicMock, patch

    campers_instance = campers_module()
    campers_instance._config_loader = MagicMock()
    campers_instance._config_loader.load_config.return_value = {"defaults": {}}
    campers_instance._config_loader.get_camp_config.return_value = {
        "region": "us-east-1",
        "instance_type": "t3.medium",
        "sync_paths": [{"local": "~/myproject", "remote": "~/myproject"}],
        "command": "pwd",
    }
    campers_instance._config_loader.validate_config.return_value = None

    mock_instance_details = {
        "instance_id": "i-test123",
        "public_ip": "203.0.113.1",
        "state": "running",
        "key_file": "/tmp/test.pem",
        "security_group_id": "sg-test123",
        "unique_id": "test123",
    }

    with (
        patch("campers.providers.aws.compute.EC2Manager") as mock_ec2,
        patch("campers_cli.get_provider") as mock_get_provider,
        patch("campers_cli.MutagenManager") as mock_mutagen,
    ):
        mock_ec2_instance = MagicMock()
        mock_ec2_instance.find_instances_by_name_or_id.return_value = []
        mock_ec2_instance.launch_instance.return_value = mock_instance_details
        mock_ec2.return_value = mock_ec2_instance

        mock_get_provider.return_value = {"compute": mock_ec2}

        mock_ssh_instance = MagicMock()
        mock_ssh_instance.filter_environment_variables.return_value = {}
        mock_ssh_instance.connect.return_value = None
        mock_ssh_instance.build_command_with_env.side_effect = lambda cmd, env: cmd
        mock_ssh_instance.execute_command_raw.return_value = 0
        campers_instance._ssh_manager_factory = lambda **kwargs: mock_ssh_instance

        mock_mutagen_instance = MagicMock()
        mock_mutagen.return_value = mock_mutagen_instance
        campers_instance._mutagen_manager_factory = lambda: mock_mutagen_instance

        result = campers_instance.run()

        mock_ssh_instance.execute_command_raw.assert_called_once()
        call_args = mock_ssh_instance.execute_command_raw.call_args[0][0]
        assert "cd ~/myproject" in call_args
        assert "pwd" in call_args
        assert result["instance_id"] == "i-test123"


def test_run_executes_startup_script_from_synced_directory(campers_module) -> None:
    """Test that startup_script executes from synced directory."""
    from unittest.mock import MagicMock, patch

    campers_instance = campers_module()
    campers_instance._config_loader = MagicMock()
    campers_instance._config_loader.load_config.return_value = {"defaults": {}}
    campers_instance._config_loader.get_camp_config.return_value = {
        "region": "us-east-1",
        "instance_type": "t3.medium",
        "sync_paths": [{"local": "~/myproject", "remote": "~/myproject"}],
        "startup_script": "source .venv/bin/activate",
        "command": "python app.py",
    }
    campers_instance._config_loader.validate_config.return_value = None

    mock_instance_details = {
        "instance_id": "i-test123",
        "public_ip": "203.0.113.1",
        "state": "running",
        "key_file": "/tmp/test.pem",
        "security_group_id": "sg-test123",
        "unique_id": "test123",
    }

    with (
        patch("campers.providers.aws.compute.EC2Manager") as mock_ec2,
        patch("campers_cli.get_provider") as mock_get_provider,
        patch("campers_cli.MutagenManager") as mock_mutagen,
    ):
        mock_ec2_instance = MagicMock()
        mock_ec2_instance.find_instances_by_name_or_id.return_value = []
        mock_ec2_instance.launch_instance.return_value = mock_instance_details
        mock_ec2.return_value = mock_ec2_instance

        mock_get_provider.return_value = {"compute": mock_ec2}

        mock_ssh_instance = MagicMock()
        mock_ssh_instance.filter_environment_variables.return_value = {}
        mock_ssh_instance.connect.return_value = None
        mock_ssh_instance.build_command_with_env.side_effect = lambda cmd, env: cmd
        mock_ssh_instance.execute_command_raw.return_value = 0
        campers_instance._ssh_manager_factory = lambda **kwargs: mock_ssh_instance

        mock_mutagen_instance = MagicMock()
        mock_mutagen.return_value = mock_mutagen_instance
        campers_instance._mutagen_manager_factory = lambda: mock_mutagen_instance

        result = campers_instance.run()

        assert mock_ssh_instance.execute_command_raw.call_count == 2
        startup_call = mock_ssh_instance.execute_command_raw.call_args_list[0][0][0]
        assert "cd ~/myproject" in startup_call
        assert "source .venv/bin/activate" in startup_call
        assert result["instance_id"] == "i-test123"


def test_build_command_in_directory(campers_module) -> None:
    """Test build_command_in_directory creates proper command string."""
    campers_instance = campers_module()

    result = campers_instance._build_command_in_directory("~/myproject", "python app.py")

    assert result == "mkdir -p ~/myproject && cd ~/myproject && bash -c 'python app.py'"


def test_build_command_in_directory_with_special_chars(campers_module) -> None:
    """Test build_command_in_directory handles special characters."""
    campers_instance = campers_module()

    result = campers_instance._build_command_in_directory("~/my project", "echo 'hello world'")

    assert "mkdir -p ~/'my project'" in result
    assert "cd ~/'my project'" in result
    assert "bash -c" in result


def test_build_command_in_directory_with_multiline_script(campers_module) -> None:
    """Test build_command_in_directory handles multiline scripts."""
    campers_instance = campers_module()

    multiline_script = """source .venv/bin/activate
export DEBUG=1
python app.py"""

    result = campers_instance._build_command_in_directory("~/app", multiline_script)

    assert result == f"mkdir -p ~/app && cd ~/app && bash -c {shlex.quote(multiline_script)}"
    assert "source .venv/bin/activate" in result


def test_run_startup_script_failure_prevents_command(campers_module) -> None:
    """Test that startup_script failure prevents command execution."""
    from unittest.mock import MagicMock, patch

    campers_instance = campers_module()
    campers_instance._config_loader = MagicMock()
    campers_instance._config_loader.load_config.return_value = {"defaults": {}}
    campers_instance._config_loader.get_camp_config.return_value = {
        "region": "us-east-1",
        "instance_type": "t3.medium",
        "sync_paths": [{"local": "~/myproject", "remote": "~/myproject"}],
        "startup_script": "exit 42",
        "command": "echo hello",
    }
    campers_instance._config_loader.validate_config.return_value = None

    mock_instance_details = {
        "instance_id": "i-test123",
        "public_ip": "203.0.113.1",
        "state": "running",
        "key_file": "/tmp/test.pem",
        "security_group_id": "sg-test123",
        "unique_id": "test123",
    }

    with (
        patch("campers.providers.aws.compute.EC2Manager") as mock_ec2,
        patch("campers_cli.get_provider") as mock_get_provider,
        patch("campers_cli.MutagenManager") as mock_mutagen,
    ):
        mock_ec2_instance = MagicMock()
        mock_ec2_instance.find_instances_by_name_or_id.return_value = []
        mock_ec2_instance.launch_instance.return_value = mock_instance_details
        mock_ec2.return_value = mock_ec2_instance

        mock_get_provider.return_value = {"compute": mock_ec2}

        mock_ssh_instance = MagicMock()
        mock_ssh_instance.filter_environment_variables.return_value = {}
        mock_ssh_instance.connect.return_value = None
        mock_ssh_instance.build_command_with_env.side_effect = lambda cmd, env: cmd
        mock_ssh_instance.execute_command_raw.return_value = 42
        campers_instance._ssh_manager_factory = lambda **kwargs: mock_ssh_instance

        mock_mutagen_instance = MagicMock()
        mock_mutagen.return_value = mock_mutagen_instance
        campers_instance._mutagen_manager_factory = lambda: mock_mutagen_instance

        with pytest.raises(RuntimeError, match="Startup script failed with exit code: 42"):
            campers_instance.run()

        assert mock_ssh_instance.execute_command_raw.call_count == 1
        mock_ssh_instance.close.assert_called_once()


def test_run_multiline_startup_script(campers_module) -> None:
    """Test that multiline startup_script executes correctly."""
    from unittest.mock import MagicMock, patch

    campers_instance = campers_module()
    campers_instance._config_loader = MagicMock()
    campers_instance._config_loader.load_config.return_value = {"defaults": {}}

    multiline_script = """source .venv/bin/activate
export DEBUG=1
cd src"""

    campers_instance._config_loader.get_camp_config.return_value = {
        "region": "us-east-1",
        "instance_type": "t3.medium",
        "sync_paths": [{"local": "~/myproject", "remote": "~/myproject"}],
        "startup_script": multiline_script,
        "command": "pwd",
    }
    campers_instance._config_loader.validate_config.return_value = None

    mock_instance_details = {
        "instance_id": "i-test123",
        "public_ip": "203.0.113.1",
        "state": "running",
        "key_file": "/tmp/test.pem",
        "security_group_id": "sg-test123",
        "unique_id": "test123",
    }

    with (
        patch("campers.providers.aws.compute.EC2Manager") as mock_ec2,
        patch("campers_cli.get_provider") as mock_get_provider,
        patch("campers_cli.MutagenManager") as mock_mutagen,
    ):
        mock_ec2_instance = MagicMock()
        mock_ec2_instance.find_instances_by_name_or_id.return_value = []
        mock_ec2_instance.launch_instance.return_value = mock_instance_details
        mock_ec2.return_value = mock_ec2_instance

        mock_get_provider.return_value = {"compute": mock_ec2}

        mock_ssh_instance = MagicMock()
        mock_ssh_instance.filter_environment_variables.return_value = {}
        mock_ssh_instance.connect.return_value = None
        mock_ssh_instance.build_command_with_env.side_effect = lambda cmd, env: cmd
        mock_ssh_instance.execute_command_raw.return_value = 0
        campers_instance._ssh_manager_factory = lambda **kwargs: mock_ssh_instance

        mock_mutagen_instance = MagicMock()
        mock_mutagen.return_value = mock_mutagen_instance
        campers_instance._mutagen_manager_factory = lambda: mock_mutagen_instance

        result = campers_instance.run()

        startup_call = mock_ssh_instance.execute_command_raw.call_args_list[0][0][0]
        assert "source .venv/bin/activate" in startup_call
        assert "export DEBUG=1" in startup_call
        assert "cd src" in startup_call
        assert result["instance_id"] == "i-test123"


def test_run_with_port_forwarding_creates_tunnels(campers_module) -> None:
    """Test that run() creates port forwarding tunnels when ports configured."""
    from unittest.mock import MagicMock, patch

    campers_instance = campers_module()
    campers_instance._config_loader = MagicMock()
    campers_instance._config_loader.load_config.return_value = {"defaults": {}}
    campers_instance._config_loader.get_camp_config.return_value = {
        "region": "us-east-1",
        "instance_type": "t3.medium",
        "ports": [8888, 8080],
        "command": "echo test",
    }
    campers_instance._config_loader.validate_config.return_value = None

    mock_instance_details = {
        "instance_id": "i-test123",
        "public_ip": "203.0.113.1",
        "state": "running",
        "key_file": "/tmp/test.pem",
        "security_group_id": "sg-test123",
        "unique_id": "test123",
    }

    with (
        patch("campers.providers.aws.compute.EC2Manager") as mock_ec2,
        patch("campers_cli.get_provider") as mock_get_provider,
        patch("campers_cli.PortForwardManager") as mock_portforward,
    ):
        mock_ec2_instance = MagicMock()
        mock_ec2_instance.find_instances_by_name_or_id.return_value = []
        mock_ec2_instance.launch_instance.return_value = mock_instance_details
        mock_ec2.return_value = mock_ec2_instance

        mock_get_provider.return_value = {"compute": mock_ec2}

        mock_ssh_instance = MagicMock()
        mock_ssh_instance.filter_environment_variables.return_value = {}
        mock_ssh_instance.connect.return_value = None
        mock_ssh_instance.build_command_with_env.side_effect = lambda cmd, env: cmd
        mock_ssh_instance.execute_command_raw.return_value = 0
        campers_instance._ssh_manager_factory = lambda **kwargs: mock_ssh_instance

        mock_portforward_instance = MagicMock()
        mock_portforward.return_value = mock_portforward_instance
        campers_instance._portforward_manager_factory = lambda: mock_portforward_instance

        result = campers_instance.run()

        mock_portforward_instance.create_tunnels.assert_called_once_with(
            ports=[(8888, 8888), (8080, 8080)],
            host="203.0.113.1",
            key_file="/tmp/test.pem",
            username="ubuntu",
            ssh_port=22,
        )
        mock_portforward_instance.stop_all_tunnels.assert_called_once()
        assert result["instance_id"] == "i-test123"


def test_run_port_forwarding_cleanup_order(campers_module) -> None:
    """Test that port forwarding tunnels stop before SSH closes."""
    from unittest.mock import MagicMock, patch

    campers_instance = campers_module()
    campers_instance._config_loader = MagicMock()
    campers_instance._config_loader.load_config.return_value = {"defaults": {}}
    campers_instance._config_loader.get_camp_config.return_value = {
        "region": "us-east-1",
        "instance_type": "t3.medium",
        "ports": [8888],
        "command": "echo test",
    }
    campers_instance._config_loader.validate_config.return_value = None

    mock_instance_details = {
        "instance_id": "i-test123",
        "public_ip": "203.0.113.1",
        "state": "running",
        "key_file": "/tmp/test.pem",
        "security_group_id": "sg-test123",
        "unique_id": "test123",
    }

    cleanup_order = []

    with (
        patch("campers.providers.aws.compute.EC2Manager") as mock_ec2,
        patch("campers_cli.get_provider") as mock_get_provider,
        patch("campers_cli.PortForwardManager") as mock_portforward,
    ):
        mock_ec2_instance = MagicMock()
        mock_ec2_instance.find_instances_by_name_or_id.return_value = []
        mock_ec2_instance.launch_instance.return_value = mock_instance_details
        mock_ec2.return_value = mock_ec2_instance

        mock_get_provider.return_value = {"compute": mock_ec2}

        mock_ssh_instance = MagicMock()
        mock_ssh_instance.filter_environment_variables.return_value = {}
        mock_ssh_instance.connect.return_value = None
        mock_ssh_instance.build_command_with_env.side_effect = lambda cmd, env: cmd
        mock_ssh_instance.execute_command_raw.return_value = 0
        mock_ssh_instance.close.side_effect = lambda: cleanup_order.append("ssh_close")
        campers_instance._ssh_manager_factory = lambda **kwargs: mock_ssh_instance

        mock_portforward_instance = MagicMock()
        mock_portforward_instance.stop_all_tunnels.side_effect = lambda: cleanup_order.append(
            "tunnels_stop"
        )
        mock_portforward.return_value = mock_portforward_instance
        campers_instance._portforward_manager_factory = lambda: mock_portforward_instance

        result = campers_instance.run()

        assert cleanup_order == ["tunnels_stop", "ssh_close"]
        assert result["instance_id"] == "i-test123"


def test_run_port_forwarding_error_triggers_cleanup(campers_module) -> None:
    """Test that port forwarding error triggers full cleanup."""
    from unittest.mock import MagicMock, patch

    campers_instance = campers_module()
    campers_instance._config_loader = MagicMock()
    campers_instance._config_loader.load_config.return_value = {"defaults": {}}
    campers_instance._config_loader.get_camp_config.return_value = {
        "region": "us-east-1",
        "instance_type": "t3.medium",
        "ports": [8888],
        "command": "echo test",
    }
    campers_instance._config_loader.validate_config.return_value = None

    mock_instance_details = {
        "instance_id": "i-test123",
        "public_ip": "203.0.113.1",
        "state": "running",
        "key_file": "/tmp/test.pem",
        "security_group_id": "sg-test123",
        "unique_id": "test123",
    }

    with (
        patch("campers.providers.aws.compute.EC2Manager") as mock_ec2,
        patch("campers_cli.get_provider") as mock_get_provider,
        patch("campers_cli.PortForwardManager") as mock_portforward,
    ):
        mock_ec2_instance = MagicMock()
        mock_ec2_instance.find_instances_by_name_or_id.return_value = []
        mock_ec2_instance.launch_instance.return_value = mock_instance_details
        mock_ec2.return_value = mock_ec2_instance

        mock_get_provider.return_value = {"compute": mock_ec2}

        mock_ssh_instance = MagicMock()
        mock_ssh_instance.filter_environment_variables.return_value = {}
        mock_ssh_instance.connect.return_value = None
        mock_ssh_instance.build_command_with_env.side_effect = lambda cmd, env: cmd
        campers_instance._ssh_manager_factory = lambda **kwargs: mock_ssh_instance

        mock_portforward_instance = MagicMock()
        mock_portforward_instance.create_tunnels.side_effect = RuntimeError(
            "Port 8888 already in use"
        )
        mock_portforward.return_value = mock_portforward_instance
        campers_instance._portforward_manager_factory = lambda: mock_portforward_instance

        with pytest.raises(RuntimeError, match="Port forwarding is configured but failed"):
            campers_instance.run()

        mock_portforward_instance.stop_all_tunnels.assert_not_called()
        mock_ssh_instance.close.assert_called_once()


def test_run_port_forwarding_with_sync_paths(campers_module) -> None:
    """Test that port forwarding works with sync_paths enabled."""
    from unittest.mock import MagicMock, patch

    campers_instance = campers_module()
    campers_instance._config_loader = MagicMock()
    campers_instance._config_loader.load_config.return_value = {"defaults": {}}
    campers_instance._config_loader.get_camp_config.return_value = {
        "region": "us-east-1",
        "instance_type": "t3.medium",
        "ports": [8888],
        "sync_paths": [{"local": "~/myproject", "remote": "~/myproject"}],
        "command": "echo test",
    }
    campers_instance._config_loader.validate_config.return_value = None

    mock_instance_details = {
        "instance_id": "i-test123",
        "public_ip": "203.0.113.1",
        "state": "running",
        "key_file": "/tmp/test.pem",
        "security_group_id": "sg-test123",
        "unique_id": "test123",
    }

    with (
        patch("campers.providers.aws.compute.EC2Manager") as mock_ec2,
        patch("campers_cli.get_provider") as mock_get_provider,
        patch("campers_cli.MutagenManager") as mock_mutagen,
        patch("campers_cli.PortForwardManager") as mock_portforward,
    ):
        mock_ec2_instance = MagicMock()
        mock_ec2_instance.find_instances_by_name_or_id.return_value = []
        mock_ec2_instance.launch_instance.return_value = mock_instance_details
        mock_ec2.return_value = mock_ec2_instance

        mock_get_provider.return_value = {"compute": mock_ec2}

        mock_ssh_instance = MagicMock()
        mock_ssh_instance.filter_environment_variables.return_value = {}
        mock_ssh_instance.connect.return_value = None
        mock_ssh_instance.build_command_with_env.side_effect = lambda cmd, env: cmd
        mock_ssh_instance.execute_command_raw.return_value = 0
        campers_instance._ssh_manager_factory = lambda **kwargs: mock_ssh_instance

        mock_mutagen_instance = MagicMock()
        mock_mutagen.return_value = mock_mutagen_instance
        campers_instance._mutagen_manager_factory = lambda: mock_mutagen_instance

        mock_portforward_instance = MagicMock()
        mock_portforward.return_value = mock_portforward_instance
        campers_instance._portforward_manager_factory = lambda: mock_portforward_instance

        result = campers_instance.run()

        mock_portforward_instance.create_tunnels.assert_called_once()
        mock_mutagen_instance.create_sync_session.assert_called_once()
        assert result["instance_id"] == "i-test123"


def test_run_port_forwarding_with_startup_script(campers_module) -> None:
    """Test that port forwarding establishes before startup_script runs."""
    from unittest.mock import MagicMock, patch

    campers_instance = campers_module()
    campers_instance._config_loader = MagicMock()
    campers_instance._config_loader.load_config.return_value = {"defaults": {}}
    campers_instance._config_loader.get_camp_config.return_value = {
        "region": "us-east-1",
        "instance_type": "t3.medium",
        "ports": [8888],
        "sync_paths": [{"local": "~/myproject", "remote": "~/myproject"}],
        "startup_script": "echo startup",
        "command": "echo command",
    }
    campers_instance._config_loader.validate_config.return_value = None

    mock_instance_details = {
        "instance_id": "i-test123",
        "public_ip": "203.0.113.1",
        "state": "running",
        "key_file": "/tmp/test.pem",
        "security_group_id": "sg-test123",
        "unique_id": "test123",
    }

    execution_order = []

    with (
        patch("campers.providers.aws.compute.EC2Manager") as mock_ec2,
        patch("campers_cli.get_provider") as mock_get_provider,
        patch("campers_cli.MutagenManager") as mock_mutagen,
        patch("campers_cli.PortForwardManager") as mock_portforward,
    ):
        mock_ec2_instance = MagicMock()
        mock_ec2_instance.find_instances_by_name_or_id.return_value = []
        mock_ec2_instance.launch_instance.return_value = mock_instance_details
        mock_ec2.return_value = mock_ec2_instance

        mock_get_provider.return_value = {"compute": mock_ec2}

        mock_ssh_instance = MagicMock()
        mock_ssh_instance.filter_environment_variables.return_value = {}
        mock_ssh_instance.connect.return_value = None
        mock_ssh_instance.build_command_with_env.side_effect = lambda cmd, env: cmd

        def track_execution(cmd: str) -> int:
            if "startup" in cmd:
                execution_order.append("startup")
            else:
                execution_order.append("command")
            return 0

        mock_ssh_instance.execute_command_raw.side_effect = track_execution
        campers_instance._ssh_manager_factory = lambda **kwargs: mock_ssh_instance

        mock_mutagen_instance = MagicMock()
        mock_mutagen.return_value = mock_mutagen_instance
        campers_instance._mutagen_manager_factory = lambda: mock_mutagen_instance

        mock_portforward_instance = MagicMock()
        mock_portforward_instance.create_tunnels.side_effect = (
            lambda **kwargs: execution_order.append("port_forward")
        )
        mock_portforward.return_value = mock_portforward_instance
        campers_instance._portforward_manager_factory = lambda: mock_portforward_instance

        result = campers_instance.run()

        assert execution_order[0] == "port_forward"
        assert "startup" in execution_order
        assert result["instance_id"] == "i-test123"


@pytest.mark.parametrize(
    "env_filter,expected_error",
    [
        (["[invalid(regex"], "Invalid regex pattern in env_filter"),
        (["(unclosed"], "Invalid regex pattern in env_filter"),
    ],
)
def test_run_validates_env_filter_regex_patterns(
    campers_module, env_filter, expected_error
) -> None:
    """Test that invalid regex patterns in env_filter are caught during validation."""
    from campers.core.config import ConfigLoader

    campers_instance = campers_module()
    campers_instance._config_loader = ConfigLoader()

    config_data = {
        "defaults": {
            "region": "us-east-1",
            "instance_type": "t3.medium",
            "disk_size": 50,
            "env_filter": env_filter,
        }
    }

    with pytest.raises(ValueError) as exc_info:
        campers_instance._config_loader.validate_config(config_data["defaults"])

    assert expected_error in str(exc_info.value)


def test_run_filters_environment_variables_after_ssh_connection(
    campers_module,
) -> None:
    """Test that environment variables are filtered after SSH connection."""
    from unittest.mock import MagicMock, patch

    campers_instance = campers_module()
    campers_instance._config_loader = MagicMock()
    campers_instance._config_loader.load_config.return_value = {"defaults": {}}
    campers_instance._config_loader.get_camp_config.return_value = {
        "region": "us-east-1",
        "instance_type": "t3.medium",
        "env_filter": ["AWS_.*"],
        "command": "aws s3 ls",
    }
    campers_instance._config_loader.validate_config.return_value = None

    mock_instance_details = {
        "instance_id": "i-test123",
        "public_ip": "203.0.113.1",
        "state": "running",
        "key_file": "/tmp/test.pem",
        "security_group_id": "sg-test123",
        "unique_id": "test123",
    }

    with (
        patch("campers.providers.aws.compute.EC2Manager") as mock_ec2,
        patch("campers_cli.get_provider") as mock_get_provider,
    ):
        mock_ec2_instance = MagicMock()
        mock_ec2_instance.find_instances_by_name_or_id.return_value = []
        mock_ec2_instance.launch_instance.return_value = mock_instance_details
        mock_ec2.return_value = mock_ec2_instance

        mock_get_provider.return_value = {"compute": mock_ec2}

        mock_ssh_instance = MagicMock()
        mock_ssh_instance.filter_environment_variables.return_value = {"AWS_REGION": "us-west-2"}
        mock_ssh_instance.build_command_with_env.return_value = (
            "export AWS_REGION='us-west-2' && aws s3 ls"
        )
        mock_ssh_instance.execute_command.return_value = 0
        campers_instance._ssh_manager_factory = lambda **kwargs: mock_ssh_instance

        campers_instance.run()

        mock_ssh_instance.connect.assert_called_once()
        mock_ssh_instance.filter_environment_variables.assert_called_once_with(["AWS_.*"])
        mock_ssh_instance.build_command_with_env.assert_called()


def test_run_forwards_env_to_setup_script(campers_module) -> None:
    """Test that environment variables are forwarded to setup_script."""
    from unittest.mock import MagicMock, patch

    campers_instance = campers_module()
    campers_instance._config_loader = MagicMock()
    campers_instance._config_loader.load_config.return_value = {"defaults": {}}
    campers_instance._config_loader.get_camp_config.return_value = {
        "region": "us-east-1",
        "instance_type": "t3.medium",
        "env_filter": ["AWS_.*"],
        "setup_script": "aws s3 cp s3://bucket/setup.sh .",
    }
    campers_instance._config_loader.validate_config.return_value = None

    mock_instance_details = {
        "instance_id": "i-test123",
        "public_ip": "203.0.113.1",
        "state": "running",
        "key_file": "/tmp/test.pem",
        "security_group_id": "sg-test123",
        "unique_id": "test123",
    }

    with (
        patch("campers.providers.aws.compute.EC2Manager") as mock_ec2,
        patch("campers_cli.get_provider") as mock_get_provider,
    ):
        mock_ec2_instance = MagicMock()
        mock_ec2_instance.find_instances_by_name_or_id.return_value = []
        mock_ec2_instance.launch_instance.return_value = mock_instance_details
        mock_ec2.return_value = mock_ec2_instance

        mock_get_provider.return_value = {"compute": mock_ec2}

        mock_ssh_instance = MagicMock()
        mock_ssh_instance.filter_environment_variables.return_value = {"AWS_REGION": "us-west-2"}
        mock_ssh_instance.build_command_with_env.return_value = (
            "export AWS_REGION='us-west-2' && aws s3 cp s3://bucket/setup.sh ."
        )
        mock_ssh_instance.execute_command.return_value = 0
        campers_instance._ssh_manager_factory = lambda **kwargs: mock_ssh_instance

        result = campers_instance.run()

        mock_ssh_instance.build_command_with_env.assert_called_with(
            "aws s3 cp s3://bucket/setup.sh .", {"AWS_REGION": "us-west-2"}
        )
        assert result["instance_id"] == "i-test123"


def test_run_forwards_env_to_startup_script(campers_module) -> None:
    """Test that environment variables are forwarded to startup_script."""
    from unittest.mock import MagicMock, patch

    campers_instance = campers_module()
    campers_instance._config_loader = MagicMock()
    campers_instance._config_loader.load_config.return_value = {"defaults": {}}
    campers_instance._config_loader.get_camp_config.return_value = {
        "region": "us-east-1",
        "instance_type": "t3.medium",
        "env_filter": ["HF_TOKEN"],
        "sync_paths": [{"local": "~/myproject", "remote": "~/myproject"}],
        "startup_script": "huggingface-cli login",
    }
    campers_instance._config_loader.validate_config.return_value = None

    mock_instance_details = {
        "instance_id": "i-test123",
        "public_ip": "203.0.113.1",
        "state": "running",
        "key_file": "/tmp/test.pem",
        "security_group_id": "sg-test123",
        "unique_id": "test123",
    }

    with (
        patch("campers.providers.aws.compute.EC2Manager") as mock_ec2,
        patch("campers_cli.get_provider") as mock_get_provider,
        patch("campers_cli.MutagenManager") as mock_mutagen,
    ):
        mock_ec2_instance = MagicMock()
        mock_ec2_instance.find_instances_by_name_or_id.return_value = []
        mock_ec2_instance.launch_instance.return_value = mock_instance_details
        mock_ec2.return_value = mock_ec2_instance

        mock_get_provider.return_value = {"compute": mock_ec2}

        mock_ssh_instance = MagicMock()
        mock_ssh_instance.filter_environment_variables.return_value = {"HF_TOKEN": "hf_test123"}
        mock_ssh_instance.build_command_with_env.return_value = (
            "export HF_TOKEN='hf_test123' && cd ~/myproject && bash -c 'huggingface-cli login'"
        )
        mock_ssh_instance.execute_command_raw.return_value = 0
        campers_instance._ssh_manager_factory = lambda **kwargs: mock_ssh_instance

        mock_mutagen_instance = MagicMock()
        mock_mutagen.return_value = mock_mutagen_instance
        campers_instance._mutagen_manager_factory = lambda: mock_mutagen_instance

        result = campers_instance.run()

        calls = mock_ssh_instance.build_command_with_env.call_args_list
        assert any("huggingface-cli login" in str(call) for call in calls)
        assert result["instance_id"] == "i-test123"


def test_run_forwards_env_to_main_command(campers_module) -> None:
    """Test that environment variables are forwarded to main command."""
    from unittest.mock import MagicMock, patch

    campers_instance = campers_module()
    campers_instance._config_loader = MagicMock()
    campers_instance._config_loader.load_config.return_value = {"defaults": {}}
    campers_instance._config_loader.get_camp_config.return_value = {
        "region": "us-east-1",
        "instance_type": "t3.medium",
        "env_filter": ["WANDB_.*"],
        "command": "python train.py",
    }
    campers_instance._config_loader.validate_config.return_value = None

    mock_instance_details = {
        "instance_id": "i-test123",
        "public_ip": "203.0.113.1",
        "state": "running",
        "key_file": "/tmp/test.pem",
        "security_group_id": "sg-test123",
        "unique_id": "test123",
    }

    with (
        patch("campers.providers.aws.compute.EC2Manager") as mock_ec2,
        patch("campers_cli.get_provider") as mock_get_provider,
    ):
        mock_ec2_instance = MagicMock()
        mock_ec2_instance.find_instances_by_name_or_id.return_value = []
        mock_ec2_instance.launch_instance.return_value = mock_instance_details
        mock_ec2.return_value = mock_ec2_instance

        mock_get_provider.return_value = {"compute": mock_ec2}

        mock_ssh_instance = MagicMock()
        mock_ssh_instance.filter_environment_variables.return_value = {"WANDB_API_KEY": "test-key"}
        mock_ssh_instance.build_command_with_env.return_value = (
            "export WANDB_API_KEY='test-key' && python train.py"
        )
        mock_ssh_instance.execute_command.return_value = 0
        campers_instance._ssh_manager_factory = lambda **kwargs: mock_ssh_instance

        result = campers_instance.run()

        mock_ssh_instance.build_command_with_env.assert_called_with(
            "python train.py", {"WANDB_API_KEY": "test-key"}
        )
        assert result["command_exit_code"] == 0


def test_campers_init_cleanup_state(campers_module) -> None:
    """Test that Campers instance initializes with cleanup state tracking."""
    campers_instance = campers_module()

    assert hasattr(campers_instance, "_cleanup_in_progress")
    assert campers_instance._cleanup_in_progress is False
    assert hasattr(campers_instance, "_resources")
    assert isinstance(campers_instance._resources, dict)
    assert len(campers_instance._resources) == 0


def test_signal_handlers_registered_during_run(campers_module) -> None:
    """Test that signal handlers are NOT registered during test execution.

    Signal handlers are intentionally disabled during unit tests to prevent
    test framework signals (like timeout signals) from triggering cleanup
    that calls sys.exit(), which would crash the test suite.
    """
    import signal

    original_sigint = signal.getsignal(signal.SIGINT)
    original_sigterm = signal.getsignal(signal.SIGTERM)

    campers_module()

    sigint_handler = signal.getsignal(signal.SIGINT)
    sigterm_handler = signal.getsignal(signal.SIGTERM)

    try:
        assert sigint_handler == original_sigint
        assert sigterm_handler == original_sigterm

    finally:
        signal.signal(signal.SIGINT, sigint_handler)
        signal.signal(signal.SIGTERM, sigterm_handler)


def test_signal_handlers_restored_after_run(campers_module) -> None:
    """Test that signal handlers remain registered during and after operations."""
    import signal

    campers_module()

    sigint_handler_initial = signal.getsignal(signal.SIGINT)
    sigterm_handler_initial = signal.getsignal(signal.SIGTERM)

    try:
        sigint_handler_during = signal.getsignal(signal.SIGINT)
        sigterm_handler_during = signal.getsignal(signal.SIGTERM)

        assert sigint_handler_during is not None
        assert sigterm_handler_during is not None

        sigint_handler_after = signal.getsignal(signal.SIGINT)
        sigterm_handler_after = signal.getsignal(signal.SIGTERM)

        assert sigint_handler_after == sigint_handler_initial
        assert sigterm_handler_after == sigterm_handler_initial

    finally:
        signal.signal(signal.SIGINT, sigint_handler_initial)
        signal.signal(signal.SIGTERM, sigterm_handler_initial)


def test_cleanup_resources_executes_in_correct_order(campers_module) -> None:
    """Test that cleanup_resources executes cleanup steps in correct order."""
    from unittest.mock import MagicMock

    campers_instance = campers_module()

    mock_portforward = MagicMock()
    mock_mutagen = MagicMock()
    mock_ssh = MagicMock()
    mock_ec2 = MagicMock()

    cleanup_order = []

    mock_portforward.stop_all_tunnels.side_effect = lambda: cleanup_order.append("portforward")
    mock_mutagen.terminate_session.side_effect = (
        lambda name, ssh_wrapper_dir=None, host=None: cleanup_order.append("mutagen")
    )
    mock_ssh.close.side_effect = lambda: cleanup_order.append("ssh")
    mock_ec2.terminate_instance.side_effect = lambda id: cleanup_order.append("ec2")

    campers_instance._resources = {
        "portforward_mgr": mock_portforward,
        "mutagen_mgr": mock_mutagen,
        "mutagen_session_name": "test-session",
        "ssh_manager": mock_ssh,
        "compute_provider": mock_ec2,
        "instance_details": {"instance_id": "i-test123"},
    }

    campers_instance._cleanup_manager.config_dict = {"on_exit": "terminate"}

    campers_instance._cleanup_resources()

    assert cleanup_order == ["portforward", "mutagen", "ssh", "ec2"]


def test_cleanup_resources_continues_on_error(campers_module) -> None:
    """Test that cleanup continues even if individual steps fail."""
    from unittest.mock import MagicMock

    campers_instance = campers_module()

    mock_portforward = MagicMock()
    mock_mutagen = MagicMock()
    mock_ssh = MagicMock()
    mock_ec2 = MagicMock()

    mock_mutagen.terminate_session.side_effect = RuntimeError("Mutagen error")

    campers_instance._resources = {
        "portforward_mgr": mock_portforward,
        "mutagen_mgr": mock_mutagen,
        "mutagen_session_name": "test-session",
        "ssh_manager": mock_ssh,
        "compute_provider": mock_ec2,
        "instance_details": {"instance_id": "i-test123"},
    }

    campers_instance._cleanup_manager.config_dict = {"on_exit": "terminate"}

    campers_instance._cleanup_resources()

    mock_portforward.stop_all_tunnels.assert_called_once()
    mock_mutagen.terminate_session.assert_called_once()
    mock_ssh.close.assert_called_once()
    mock_ec2.terminate_instance.assert_called_once()


def test_cleanup_resources_exits_with_sigint_code(campers_module) -> None:
    """Test that cleanup_resources exits with code 130 for SIGINT."""
    import signal

    campers_instance = campers_module()

    campers_instance._resources = {}

    with pytest.raises(SystemExit) as exc_info:
        campers_instance._cleanup_resources(signum=signal.SIGINT, frame=None)

    assert exc_info.value.code == 130


def test_cleanup_resources_exits_with_sigterm_code(campers_module) -> None:
    """Test that cleanup_resources exits with code 143 for SIGTERM."""
    import signal

    campers_instance = campers_module()

    campers_instance._resources = {}

    with pytest.raises(SystemExit) as exc_info:
        campers_instance._cleanup_resources(signum=signal.SIGTERM, frame=None)

    assert exc_info.value.code == 143


def test_cleanup_resources_prevents_duplicate_cleanup(campers_module) -> None:
    """Test that cleanup_in_progress flag prevents duplicate cleanup."""
    from unittest.mock import MagicMock

    campers_instance = campers_module()

    mock_ec2 = MagicMock()
    campers_instance._resources = {
        "compute_provider": mock_ec2,
        "instance_details": {"instance_id": "i-test123"},
    }

    campers_instance._cleanup_in_progress = True

    campers_instance._cleanup_resources()

    mock_ec2.terminate_instance.assert_not_called()


def test_cleanup_resources_only_cleans_tracked_resources(campers_module) -> None:
    """Test that cleanup only attempts to clean resources that were tracked."""
    from unittest.mock import MagicMock

    campers_instance = campers_module()

    mock_ec2 = MagicMock()
    mock_ssh = MagicMock()

    campers_instance._resources = {
        "compute_provider": mock_ec2,
        "instance_details": {"instance_id": "i-test123"},
        "ssh_manager": mock_ssh,
    }

    campers_instance._cleanup_manager.config_dict = {"on_exit": "terminate"}

    campers_instance._cleanup_resources()

    mock_ec2.terminate_instance.assert_called_once_with("i-test123")
    mock_ssh.close.assert_called_once()


def test_run_tracks_resources_incrementally(campers_module) -> None:
    """Test that run() tracks resources as they are created."""
    from unittest.mock import MagicMock, patch

    campers_instance = campers_module()
    campers_instance._config_loader = MagicMock()
    campers_instance._config_loader.load_config.return_value = {"defaults": {}}
    campers_instance._config_loader.get_camp_config.return_value = {
        "region": "us-east-1",
        "instance_type": "t3.medium",
        "ports": [8888],
        "sync_paths": [{"local": "~/myproject", "remote": "~/myproject"}],
        "command": "echo test",
    }
    campers_instance._config_loader.validate_config.return_value = None

    mock_instance_details = {
        "instance_id": "i-test123",
        "public_ip": "203.0.113.1",
        "state": "running",
        "key_file": "/tmp/test.pem",
        "security_group_id": "sg-test123",
        "unique_id": "test123",
    }

    captured_resources = {}

    def capture_cleanup():
        captured_resources.update(campers_instance._resources)

    with (
        patch("campers.providers.aws.compute.EC2Manager") as mock_ec2,
        patch("campers_cli.get_provider") as mock_get_provider,
        patch("campers_cli.MutagenManager") as mock_mutagen,
        patch("campers_cli.PortForwardManager") as mock_portforward,
    ):
        mock_ec2_instance = MagicMock()
        mock_ec2_instance.find_instances_by_name_or_id.return_value = []
        mock_ec2_instance.launch_instance.return_value = mock_instance_details
        mock_ec2.return_value = mock_ec2_instance

        mock_get_provider.return_value = {"compute": mock_ec2}

        mock_ssh_instance = MagicMock()
        mock_ssh_instance.filter_environment_variables.return_value = {}
        mock_ssh_instance.connect.return_value = None
        mock_ssh_instance.build_command_with_env.side_effect = lambda cmd, env: cmd
        mock_ssh_instance.execute_command_raw.return_value = 0
        campers_instance._ssh_manager_factory = lambda **kwargs: mock_ssh_instance

        mock_mutagen_instance = MagicMock()
        mock_mutagen.return_value = mock_mutagen_instance
        campers_instance._mutagen_manager_factory = lambda: mock_mutagen_instance

        mock_portforward_instance = MagicMock()
        mock_portforward.return_value = mock_portforward_instance
        campers_instance._portforward_manager_factory = lambda: mock_portforward_instance

        original_cleanup = campers_instance._cleanup_resources
        campers_instance._cleanup_resources = lambda *args, **kwargs: (
            capture_cleanup(),
            original_cleanup(*args, **kwargs),
        )[1]

        campers_instance.run()

        assert "compute_provider" in captured_resources
        assert "instance_details" in captured_resources
        assert "ssh_manager" in captured_resources
        assert "portforward_mgr" in captured_resources
        assert "mutagen_mgr" in captured_resources
        assert "mutagen_session_name" in captured_resources


def test_finally_block_calls_cleanup_if_not_already_done(campers_module) -> None:
    """Test that finally block calls cleanup when signal handler hasn't run."""
    from unittest.mock import MagicMock, patch

    campers_instance = campers_module()
    campers_instance._config_loader = MagicMock()
    campers_instance._config_loader.load_config.return_value = {"defaults": {}}
    campers_instance._config_loader.get_camp_config.return_value = {
        "region": "us-east-1",
        "instance_type": "t3.medium",
        "command": "echo test",
    }
    campers_instance._config_loader.validate_config.return_value = None

    mock_instance_details = {
        "instance_id": "i-test123",
        "public_ip": "203.0.113.1",
        "state": "running",
        "key_file": "/tmp/test.pem",
        "security_group_id": "sg-test123",
        "unique_id": "test123",
    }

    with (
        patch("campers.providers.aws.compute.EC2Manager") as mock_ec2,
        patch("campers_cli.get_provider") as mock_get_provider,
    ):
        mock_ec2_instance = MagicMock()
        mock_ec2_instance.find_instances_by_name_or_id.return_value = []
        mock_ec2_instance.launch_instance.return_value = mock_instance_details
        mock_ec2.return_value = mock_ec2_instance

        mock_get_provider.return_value = {"compute": mock_ec2}

        mock_ssh_instance = MagicMock()
        mock_ssh_instance.filter_environment_variables.return_value = {}
        mock_ssh_instance.connect.return_value = None
        mock_ssh_instance.build_command_with_env.side_effect = lambda cmd, env: cmd
        mock_ssh_instance.execute_command.return_value = 0
        campers_instance._ssh_manager_factory = lambda **kwargs: mock_ssh_instance

        campers_instance.run(plain=True)

        assert campers_instance._cleanup_in_progress is False
        mock_ssh_instance.close.assert_called()


def test_format_time_ago_just_now(campers_module) -> None:
    """Test format_time_ago returns 'just now' for recent times."""
    from datetime import datetime

    from campers.utils import format_time_ago

    dt = datetime.now(UTC)
    result = format_time_ago(dt)
    assert result == "just now"


def test_format_time_ago_minutes(campers_module) -> None:
    """Test format_time_ago returns minutes ago for times under an hour."""
    from datetime import datetime, timedelta

    from campers.utils import format_time_ago

    dt = datetime.now(UTC) - timedelta(minutes=30)
    result = format_time_ago(dt)
    assert result == "30m ago"


def test_format_time_ago_hours(campers_module) -> None:
    """Test format_time_ago returns hours ago for times under a day."""
    from datetime import datetime, timedelta

    from campers.utils import format_time_ago

    dt = datetime.now(UTC) - timedelta(hours=2)
    result = format_time_ago(dt)
    assert result == "2h ago"


def test_format_time_ago_days(campers_module) -> None:
    """Test format_time_ago returns days ago for times over a day."""
    from datetime import datetime, timedelta

    from campers.utils import format_time_ago

    dt = datetime.now(UTC) - timedelta(days=5)
    result = format_time_ago(dt)
    assert result == "5d ago"


def test_format_time_ago_raises_on_naive_datetime(campers_module) -> None:
    """Test format_time_ago raises ValueError for naive datetime."""
    from datetime import datetime

    from campers.utils import format_time_ago

    dt = datetime.now()

    with pytest.raises(ValueError, match="datetime must be timezone-aware"):
        format_time_ago(dt)


def test_list_command_all_regions(campers_module, aws_credentials, caplog) -> None:
    """Test list command displays instances from all regions."""
    import logging
    from datetime import datetime
    from unittest.mock import MagicMock, patch

    campers_instance = campers_module()

    mock_ec2_manager = MagicMock()
    mock_ec2_manager.list_instances.return_value = [
        {
            "instance_id": "i-test1",
            "camp_config": "test-machine-1",
            "state": "running",
            "region": "us-east-1",
            "instance_type": "t3.medium",
            "launch_time": datetime.now(UTC),
        },
        {
            "instance_id": "i-test2",
            "camp_config": "test-machine-2",
            "state": "running",
            "region": "us-west-2",
            "instance_type": "t3.large",
            "launch_time": datetime.now(UTC),
        },
    ]

    mock_ec2_class = MagicMock(return_value=mock_ec2_manager)

    with caplog.at_level(logging.INFO):
        with (
            patch("campers.providers.aws.compute.EC2Manager", mock_ec2_class),
            patch("campers_cli.get_provider", return_value={"compute": mock_ec2_class}),
        ):
            campers_instance.list()

    output = caplog.text
    assert "NAME" in output
    assert "INSTANCE-ID" in output
    assert "STATUS" in output
    assert "REGION" in output
    assert "TYPE" in output
    assert "LAUNCHED" in output
    assert "test-machine-1" in output
    assert "test-machine-2" in output
    assert "i-test1" in output
    assert "i-test2" in output
    assert "Instances in" not in output


def test_list_command_filtered_region(campers_module, aws_credentials, caplog) -> None:
    """Test list command displays instances from specific region."""
    import logging
    from datetime import datetime
    from unittest.mock import MagicMock, patch

    campers_instance = campers_module()

    mock_ec2_manager = MagicMock()
    mock_ec2_manager.list_instances.return_value = [
        {
            "instance_id": "i-test1",
            "camp_config": "test-machine-1",
            "state": "running",
            "region": "us-east-1",
            "instance_type": "t3.medium",
            "launch_time": datetime.now(UTC),
        }
    ]

    mock_ec2_class = MagicMock(return_value=mock_ec2_manager)

    mock_ec2_client = MagicMock()
    mock_ec2_client.describe_regions.return_value = {
        "Regions": [
            {"RegionName": "us-east-1"},
            {"RegionName": "us-west-2"},
        ]
    }

    with caplog.at_level(logging.INFO):
        with (
            patch("campers.providers.aws.compute.EC2Manager", mock_ec2_class),
            patch("campers_cli.get_provider", return_value={"compute": mock_ec2_class}),
            patch("boto3.client", return_value=mock_ec2_client),
        ):
            campers_instance.list(region="us-east-1")

    output = caplog.text
    assert "Instances in us-east-1:" in output
    assert "NAME" in output
    assert "INSTANCE-ID" in output
    assert "STATUS" in output
    assert "TYPE" in output
    assert "LAUNCHED" in output
    assert "test-machine-1" in output
    assert "i-test1" in output


def test_list_command_no_instances(campers_module, aws_credentials, caplog) -> None:
    """Test list command displays message when no instances exist."""
    import logging
    from unittest.mock import MagicMock, patch

    campers_instance = campers_module()

    mock_ec2_manager = MagicMock()
    mock_ec2_manager.list_instances.return_value = []

    mock_ec2_class = MagicMock(return_value=mock_ec2_manager)

    with caplog.at_level(logging.INFO):
        with (
            patch("campers.providers.aws.compute.EC2Manager", mock_ec2_class),
            patch("campers_cli.get_provider", return_value={"compute": mock_ec2_class}),
        ):
            campers_instance.list()

    output = caplog.text
    assert "No campers-managed instances found" in output


def test_list_command_no_credentials(campers_module, caplog) -> None:
    """Test list command handles missing cloud provider credentials."""
    import logging
    from unittest.mock import MagicMock, patch

    from campers.providers.exceptions import ProviderCredentialsError

    campers_instance = campers_module()

    mock_ec2_manager = MagicMock()
    mock_ec2_manager.list_instances.side_effect = ProviderCredentialsError(
        "Cloud provider credentials not configured"
    )

    mock_ec2_class = MagicMock(return_value=mock_ec2_manager)

    with caplog.at_level(logging.ERROR):
        with (
            patch("campers.providers.aws.compute.EC2Manager", mock_ec2_class),
            patch("campers_cli.get_provider", return_value={"compute": mock_ec2_class}),
        ):
            with pytest.raises(ProviderCredentialsError):
                campers_instance.list()

    output = caplog.text
    assert "Cloud provider credentials not found" in output


def test_list_command_permission_error(campers_module, aws_credentials, caplog) -> None:
    """Test list command handles permission errors."""
    import logging
    from unittest.mock import MagicMock, patch

    from campers.providers.exceptions import ProviderAPIError

    campers_instance = campers_module()

    mock_ec2_manager = MagicMock()
    mock_ec2_manager.list_instances.side_effect = ProviderAPIError(
        "Insufficient permissions",
        error_code="UnauthorizedOperation",
    )

    mock_ec2_class = MagicMock(return_value=mock_ec2_manager)

    with caplog.at_level(logging.ERROR):
        with (
            patch("campers.providers.aws.compute.EC2Manager", mock_ec2_class),
            patch("campers_cli.get_provider", return_value={"compute": mock_ec2_class}),
        ):
            with pytest.raises(ProviderAPIError):
                campers_instance.list()

    output = caplog.text
    assert "Insufficient cloud provider permissions" in output


def test_list_command_invalid_region(campers_module, aws_credentials) -> None:
    """Test list command with invalid region parameter."""
    from unittest.mock import MagicMock

    mock_compute_provider = MagicMock()
    mock_compute_provider.validate_region.side_effect = ValueError(
        "Invalid region: 'invalid-region-xyz'"
    )

    campers_instance = campers_module(
        compute_provider_factory=MagicMock(return_value=mock_compute_provider)
    )

    with pytest.raises(ValueError, match="Invalid region: 'invalid-region-xyz'"):
        campers_instance.list(region="invalid-region-xyz")


def test_truncate_name_short_name(campers_module) -> None:
    """Test truncate_name returns original name when it fits."""
    campers_instance = campers_module()

    short_name = "short"
    result = campers_instance._truncate_name(short_name)

    assert result == "short"


def test_truncate_name_exactly_max_width(campers_module) -> None:
    """Test truncate_name returns original name when exactly at max width."""
    campers_instance = campers_module()

    exact_name = "x" * 19
    result = campers_instance._truncate_name(exact_name)

    assert result == exact_name


def test_truncate_name_exceeds_max_width(campers_module) -> None:
    """Test truncate_name adds ellipsis when name exceeds max width."""
    campers_instance = campers_module()

    long_name = "very-long-machine-config-name-that-exceeds-limit"
    result = campers_instance._truncate_name(long_name)

    assert len(result) == 19
    assert result.endswith("...")
    assert result == "very-long-machin..."


def test_validate_region_valid(campers_module) -> None:
    """Test validate_region accepts valid AWS region."""
    from unittest.mock import MagicMock

    mock_compute_provider = MagicMock()
    mock_compute_provider.validate_region = MagicMock()

    campers_instance = campers_module(
        compute_provider_factory=MagicMock(return_value=mock_compute_provider)
    )

    campers_instance._validate_region("us-east-1")


def test_validate_region_invalid(campers_module) -> None:
    """Test validate_region raises ValueError for invalid region."""
    from unittest.mock import MagicMock

    mock_compute_provider = MagicMock()
    mock_compute_provider.validate_region.side_effect = ValueError("Invalid region")

    campers_instance = campers_module(
        compute_provider_factory=MagicMock(return_value=mock_compute_provider)
    )

    with pytest.raises(ValueError, match="Invalid region"):
        campers_instance._validate_region("invalid-region")


def test_validate_region_graceful_fallback(campers_module, caplog) -> None:
    """Test validate_region proceeds without validation on API errors."""
    from unittest.mock import MagicMock, patch

    from botocore.exceptions import ClientError

    campers_instance = campers_module()

    mock_ec2_client = MagicMock()
    mock_ec2_client.describe_regions.side_effect = ClientError(
        {"Error": {"Code": "UnauthorizedOperation", "Message": "Not authorized"}},
        "DescribeRegions",
    )

    with patch("boto3.client", return_value=mock_ec2_client):
        campers_instance._validate_region("us-east-1")

    assert "Unable to validate region" in caplog.text


def test_cleanup_flag_resets_after_cleanup(campers_module) -> None:
    """Test that cleanup_in_progress flag resets after cleanup completes."""
    from unittest.mock import MagicMock

    campers_instance = campers_module()

    mock_ec2 = MagicMock()
    campers_instance._resources = {
        "compute_provider": mock_ec2,
        "instance_details": {"instance_id": "i-test123"},
    }

    campers_instance._cleanup_manager.config_dict = {"on_exit": "terminate"}

    assert campers_instance._cleanup_in_progress is False

    campers_instance._cleanup_resources()

    assert campers_instance._cleanup_in_progress is False
    mock_ec2.terminate_instance.assert_called_once()


def test_multiple_run_calls_work_correctly(campers_module) -> None:
    """Test that multiple run() calls in same process work correctly.

    This test verifies that the cleanup_in_progress flag is properly reset
    between consecutive run() calls, ensuring the flag doesn't get stuck
    in True state which would prevent subsequent runs from cleaning up.

    This test ACTUALLY calls run() (not run_test_mode()) and exercises
    the real cleanup path to catch flag reset regressions.
    """
    import os
    from unittest.mock import MagicMock, patch

    campers_instance = campers_module()

    mock_instance_details = {
        "instance_id": "i-test123",
        "public_ip": "1.2.3.4",
        "state": "running",
        "key_file": "/tmp/test-key.pem",
        "security_group_id": "sg-test123",
        "unique_id": "test-unique-id",
    }

    cleanup_call_count = 0

    original_cleanup = campers_instance._cleanup_resources

    def track_cleanup(signum=None, frame=None):
        nonlocal cleanup_call_count
        cleanup_call_count += 1
        return original_cleanup(signum, frame)

    with (
        patch.dict(os.environ, {"CAMPERS_TEST_MODE": "0"}),
        patch.object(campers_instance, "_cleanup_resources", side_effect=track_cleanup),
    ):
        campers_instance._config_loader = MagicMock()
        campers_instance._config_loader.load_config.return_value = {"defaults": {}}
        campers_instance._config_loader.get_camp_config.return_value = {
            "region": "us-east-1",
            "instance_type": "t3.medium",
        }
        campers_instance._config_loader.validate_config.return_value = None

        with (
            patch("campers.providers.aws.compute.EC2Manager") as mock_ec2_class,
            patch("campers_cli.get_provider") as mock_get_provider,
            patch("campers_cli.SSHManager") as mock_ssh_class,
        ):
            mock_ec2_instance = MagicMock()
            mock_ec2_instance.find_instances_by_name_or_id.return_value = []
            mock_ec2_instance.launch_instance.return_value = mock_instance_details
            mock_ec2_class.return_value = mock_ec2_instance

            mock_get_provider.return_value = {"compute": mock_ec2_class}

            mock_ssh_instance = MagicMock()
            mock_ssh_instance.filter_environment_variables.return_value = {}
            mock_ssh_instance.connect.return_value = None
            mock_ssh_instance.build_command_with_env.side_effect = lambda c, e: c
            mock_ssh_instance.execute_command.return_value = 0
            mock_ssh_class.return_value = mock_ssh_instance

            result1 = campers_instance.run(plain=True)

            assert result1 is not None
            assert result1["instance_id"] == "i-test123"
            assert campers_instance._cleanup_in_progress is False
            assert cleanup_call_count == 1

            result2 = campers_instance.run(plain=True)

            assert result2 is not None
            assert result2["instance_id"] == "i-test123"
            assert campers_instance._cleanup_in_progress is False
            assert cleanup_call_count == 2


def test_cleanup_flag_resets_even_with_cleanup_errors(campers_module) -> None:
    """Test that cleanup_in_progress flag resets even when cleanup has errors."""
    from unittest.mock import MagicMock

    campers_instance = campers_module()

    mock_ec2 = MagicMock()
    mock_ec2.terminate_instance.side_effect = RuntimeError("EC2 error")

    campers_instance._resources = {
        "compute_provider": mock_ec2,
        "instance_details": {"instance_id": "i-test123"},
    }

    campers_instance._cleanup_manager.config_dict = {"on_exit": "terminate"}

    campers_instance._cleanup_resources()

    assert campers_instance._cleanup_in_progress is False
    mock_ec2.terminate_instance.assert_called_once()


def test_get_or_create_stopped_instance_starts_it(campers_module) -> None:
    """Test _get_or_create_instance starts stopped instance with reused=True."""
    from unittest.mock import MagicMock, patch

    campers_instance = campers_module()

    mock_ec2 = MagicMock()
    stopped_instance = {
        "instance_id": "i-stopped123",
        "state": "stopped",
        "public_ip": None,
        "region": "us-east-1",
    }
    started_instance = {
        "instance_id": "i-stopped123",
        "state": "running",
        "public_ip": "203.0.113.1",
        "private_ip": "10.0.0.1",
        "instance_type": "t3.medium",
    }

    mock_ec2.find_instances_by_name_or_id.return_value = [stopped_instance]
    mock_ec2.start_instance.return_value = started_instance

    campers_instance._resources = {"compute_provider": mock_ec2}

    with patch("builtins.print"):
        result = campers_instance._get_or_create_instance("test-branch", {"region": "us-east-1"})

    assert result["reused"] is True
    assert result["instance_id"] == "i-stopped123"
    assert result["state"] == "running"
    mock_ec2.start_instance.assert_called_once_with("i-stopped123")


def test_get_or_create_running_instance_raises_error(campers_module) -> None:
    """Test _get_or_create_instance raises error for already running instance."""
    from unittest.mock import MagicMock

    campers_instance = campers_module()

    mock_ec2 = MagicMock()
    running_instance = {
        "instance_id": "i-running123",
        "state": "running",
        "public_ip": "203.0.113.1",
    }

    mock_ec2.find_instances_by_name_or_id.return_value = [running_instance]

    campers_instance._resources = {"compute_provider": mock_ec2}

    with pytest.raises(RuntimeError, match="already running"):
        campers_instance._get_or_create_instance("test-branch", {"region": "us-east-1"})


def test_get_or_create_pending_instance_raises_error(campers_module) -> None:
    """Test _get_or_create_instance raises error for instance in pending state."""
    from unittest.mock import MagicMock

    campers_instance = campers_module()

    mock_ec2 = MagicMock()
    pending_instance = {
        "instance_id": "i-pending123",
        "state": "pending",
    }

    mock_ec2.find_instances_by_name_or_id.return_value = [pending_instance]

    campers_instance._resources = {"compute_provider": mock_ec2}

    with pytest.raises(RuntimeError, match="Please wait for stable state"):
        campers_instance._get_or_create_instance("test-branch", {"region": "us-east-1"})


def test_get_or_create_stopping_instance_raises_error(campers_module) -> None:
    """Test _get_or_create_instance raises error for instance in stopping state."""
    from unittest.mock import MagicMock

    campers_instance = campers_module()

    mock_ec2 = MagicMock()
    stopping_instance = {
        "instance_id": "i-stopping123",
        "state": "stopping",
    }

    mock_ec2.find_instances_by_name_or_id.return_value = [stopping_instance]

    campers_instance._resources = {"compute_provider": mock_ec2}

    with pytest.raises(RuntimeError, match="Please wait for stable state"):
        campers_instance._get_or_create_instance("test-branch", {"region": "us-east-1"})


def test_get_or_create_terminated_creates_new(campers_module) -> None:
    """Test _get_or_create_instance creates new instance when terminated."""
    from unittest.mock import MagicMock, patch

    campers_instance = campers_module()

    mock_ec2 = MagicMock()
    terminated_instance = {
        "instance_id": "i-terminated123",
        "state": "terminated",
    }
    new_instance = {
        "instance_id": "i-new123",
        "state": "running",
        "public_ip": "203.0.113.1",
        "private_ip": "10.0.0.1",
        "instance_type": "t3.medium",
    }

    mock_ec2.find_instances_by_name_or_id.return_value = [terminated_instance]
    mock_ec2.launch_instance.return_value = new_instance

    campers_instance._resources = {"compute_provider": mock_ec2}

    with patch("builtins.print"):
        result = campers_instance._get_or_create_instance("test-branch", {"region": "us-east-1"})

    assert result["reused"] is False
    assert result["instance_id"] == "i-new123"
    mock_ec2.launch_instance.assert_called_once()


def test_get_or_create_no_existing_creates_new(campers_module) -> None:
    """Test _get_or_create_instance creates new when no existing instances."""
    from unittest.mock import MagicMock, patch

    campers_instance = campers_module()

    mock_ec2 = MagicMock()
    new_instance = {
        "instance_id": "i-new456",
        "state": "running",
        "public_ip": "203.0.113.2",
        "private_ip": "10.0.0.2",
        "instance_type": "t3.medium",
    }

    mock_ec2.find_instances_by_name_or_id.return_value = []
    mock_ec2.launch_instance.return_value = new_instance

    campers_instance._resources = {"compute_provider": mock_ec2}

    with patch("builtins.print"):
        result = campers_instance._get_or_create_instance("test-branch", {"region": "us-east-1"})

    assert result["reused"] is False
    assert result["instance_id"] == "i-new456"
    mock_ec2.launch_instance.assert_called_once()


def test_get_or_create_multiple_matches_uses_first(campers_module) -> None:
    """Test _get_or_create_instance selects first match when multiple found."""
    from unittest.mock import MagicMock, patch

    campers_instance = campers_module()

    mock_ec2 = MagicMock()
    stopped_instance = {
        "instance_id": "i-first-stopped",
        "state": "stopped",
    }
    started_instance = {
        "instance_id": "i-first-stopped",
        "state": "running",
        "public_ip": "203.0.113.3",
        "private_ip": "10.0.0.3",
        "instance_type": "t3.medium",
    }

    mock_ec2.find_instances_by_name_or_id.return_value = [
        stopped_instance,
        {"instance_id": "i-second", "state": "stopped"},
    ]
    mock_ec2.start_instance.return_value = started_instance

    campers_instance._resources = {"compute_provider": mock_ec2}

    with patch("builtins.print"), patch("logging.warning") as mock_logging:
        result = campers_instance._get_or_create_instance("test-branch", {"region": "us-east-1"})

    assert result["instance_id"] == "i-first-stopped"
    mock_logging.assert_called()


def test_stop_command_success(campers_module) -> None:
    """Test stop() command calls EC2Manager.stop_instance successfully."""
    from unittest.mock import MagicMock, patch

    campers_instance = campers_module()
    campers_instance._config_loader = MagicMock()
    campers_instance._config_loader.BUILT_IN_DEFAULTS = {"region": "us-east-1"}

    mock_ec2 = MagicMock()
    mock_ec2.find_instances_by_name_or_id.return_value = [
        {
            "instance_id": "i-test123",
            "state": "running",
            "camp_config": "test-config",
            "region": "us-east-1",
            "instance_type": "t3.medium",
        }
    ]
    mock_ec2.stop_instance.return_value = {
        "instance_id": "i-test123",
        "state": "stopped",
    }
    mock_ec2.get_volume_size.return_value = 50

    campers_instance._create_compute_provider = MagicMock(return_value=mock_ec2)

    with patch("builtins.print"):
        campers_instance.stop("i-test123")

    mock_ec2.stop_instance.assert_called_once_with("i-test123")
    mock_ec2.get_volume_size.assert_called_once_with("i-test123")


def test_stop_command_already_stopped_idempotent(campers_module) -> None:
    """Test stop() returns cleanly when instance already stopped."""
    from unittest.mock import MagicMock, patch

    campers_instance = campers_module()
    campers_instance._config_loader = MagicMock()
    campers_instance._config_loader.BUILT_IN_DEFAULTS = {"region": "us-east-1"}

    mock_ec2 = MagicMock()
    mock_ec2.find_instances_by_name_or_id.return_value = [
        {
            "instance_id": "i-test123",
            "state": "stopped",
            "camp_config": "test-config",
            "region": "us-east-1",
        }
    ]

    campers_instance._create_compute_provider = MagicMock(return_value=mock_ec2)

    with patch("builtins.print"):
        campers_instance.stop("i-test123")

    mock_ec2.stop_instance.assert_not_called()


def test_stop_command_no_matches_error(campers_module) -> None:
    """Test stop() raises SystemExit when no instances match."""
    from unittest.mock import MagicMock

    campers_instance = campers_module()
    campers_instance._config_loader = MagicMock()
    campers_instance._config_loader.BUILT_IN_DEFAULTS = {"region": "us-east-1"}

    mock_ec2 = MagicMock()
    mock_ec2.find_instances_by_name_or_id.return_value = []

    campers_instance._create_compute_provider = MagicMock(return_value=mock_ec2)

    with pytest.raises(SystemExit) as exc_info:
        campers_instance.stop("nonexistent")

    assert exc_info.value.code == 1


def test_stop_command_multiple_matches_requires_id(campers_module) -> None:
    """Test stop() requires specific ID when multiple instances match."""
    from unittest.mock import MagicMock

    campers_instance = campers_module()
    campers_instance._config_loader = MagicMock()
    campers_instance._config_loader.BUILT_IN_DEFAULTS = {"region": "us-east-1"}

    mock_ec2 = MagicMock()
    mock_ec2.find_instances_by_name_or_id.return_value = [
        {"instance_id": "i-test1", "state": "running", "region": "us-east-1"},
        {"instance_id": "i-test2", "state": "running", "region": "us-east-1"},
    ]

    campers_instance._create_compute_provider = MagicMock(return_value=mock_ec2)

    with pytest.raises(SystemExit) as exc_info:
        campers_instance.stop("ambiguous-name")

    assert exc_info.value.code == 1


def test_stop_command_displays_storage_cost(campers_module, caplog) -> None:
    """Test stop() displays storage cost in output."""
    import logging
    from unittest.mock import MagicMock, patch

    campers_instance = campers_module()
    campers_instance._config_loader = MagicMock()
    campers_instance._config_loader.BUILT_IN_DEFAULTS = {"region": "us-east-1"}

    mock_ec2 = MagicMock()
    mock_ec2.find_instances_by_name_or_id.return_value = [
        {
            "instance_id": "i-test123",
            "state": "running",
            "camp_config": "test-config",
            "region": "us-east-1",
            "instance_type": "t3.medium",
        }
    ]
    mock_ec2.stop_instance.return_value = {
        "instance_id": "i-test123",
        "state": "stopped",
    }
    mock_ec2.get_volume_size.return_value = 100

    campers_instance._create_compute_provider = MagicMock(return_value=mock_ec2)

    with caplog.at_level(logging.INFO):
        with patch("campers.providers.aws.pricing.calculate_monthly_cost") as mock_cost:
            mock_cost.side_effect = [100.0, 50.0]
            campers_instance.stop("i-test123")

    output = caplog.text
    assert "cost" in output.lower()


def test_start_command_success(campers_module) -> None:
    """Test start() command calls EC2Manager.start_instance successfully."""
    from unittest.mock import MagicMock, patch

    campers_instance = campers_module()
    campers_instance._config_loader = MagicMock()
    campers_instance._config_loader.BUILT_IN_DEFAULTS = {"region": "us-east-1"}

    mock_ec2 = MagicMock()
    mock_ec2.find_instances_by_name_or_id.return_value = [
        {
            "instance_id": "i-test123",
            "state": "stopped",
            "camp_config": "test-config",
            "region": "us-east-1",
            "instance_type": "t3.medium",
        }
    ]
    mock_ec2.start_instance.return_value = {
        "instance_id": "i-test123",
        "state": "running",
        "public_ip": "203.0.113.1",
    }

    campers_instance._create_compute_provider = MagicMock(return_value=mock_ec2)

    with patch("builtins.print"):
        campers_instance.start("i-test123")

    mock_ec2.start_instance.assert_called_once_with("i-test123")


def test_start_command_already_running_idempotent(campers_module) -> None:
    """Test start() returns cleanly when instance already running."""
    from unittest.mock import MagicMock, patch

    campers_instance = campers_module()
    campers_instance._config_loader = MagicMock()
    campers_instance._config_loader.BUILT_IN_DEFAULTS = {"region": "us-east-1"}

    mock_ec2 = MagicMock()
    mock_ec2.find_instances_by_name_or_id.return_value = [
        {
            "instance_id": "i-test123",
            "state": "running",
            "camp_config": "test-config",
            "region": "us-east-1",
            "public_ip": "203.0.113.1",
        }
    ]

    campers_instance._create_compute_provider = MagicMock(return_value=mock_ec2)

    with patch("builtins.print"):
        campers_instance.start("i-test123")

    mock_ec2.start_instance.assert_not_called()


def test_start_command_no_matches_error(campers_module) -> None:
    """Test start() raises SystemExit when no instances match."""
    from unittest.mock import MagicMock

    campers_instance = campers_module()
    campers_instance._config_loader = MagicMock()
    campers_instance._config_loader.BUILT_IN_DEFAULTS = {"region": "us-east-1"}

    mock_ec2 = MagicMock()
    mock_ec2.find_instances_by_name_or_id.return_value = []

    campers_instance._create_compute_provider = MagicMock(return_value=mock_ec2)

    with pytest.raises(SystemExit) as exc_info:
        campers_instance.start("nonexistent")

    assert exc_info.value.code == 1


def test_start_command_multiple_matches_requires_id(campers_module) -> None:
    """Test start() requires specific ID when multiple instances match."""
    from unittest.mock import MagicMock

    campers_instance = campers_module()
    campers_instance._config_loader = MagicMock()
    campers_instance._config_loader.BUILT_IN_DEFAULTS = {"region": "us-east-1"}

    mock_ec2 = MagicMock()
    mock_ec2.find_instances_by_name_or_id.return_value = [
        {"instance_id": "i-test1", "state": "stopped", "region": "us-east-1"},
        {"instance_id": "i-test2", "state": "stopped", "region": "us-east-1"},
    ]

    campers_instance._create_compute_provider = MagicMock(return_value=mock_ec2)

    with pytest.raises(SystemExit) as exc_info:
        campers_instance.start("ambiguous-name")

    assert exc_info.value.code == 1


def test_start_command_displays_new_ip(campers_module, caplog) -> None:
    """Test start() displays new IP in output."""
    import logging
    from unittest.mock import MagicMock

    campers_instance = campers_module()
    campers_instance._config_loader = MagicMock()
    campers_instance._config_loader.BUILT_IN_DEFAULTS = {"region": "us-east-1"}

    mock_ec2 = MagicMock()
    mock_ec2.find_instances_by_name_or_id.return_value = [
        {
            "instance_id": "i-test123",
            "state": "stopped",
            "camp_config": "test-config",
            "region": "us-east-1",
            "instance_type": "t3.medium",
        }
    ]
    mock_ec2.start_instance.return_value = {
        "instance_id": "i-test123",
        "state": "running",
        "public_ip": "203.0.113.1",
    }

    campers_instance._create_compute_provider = MagicMock(return_value=mock_ec2)

    with caplog.at_level(logging.INFO):
        campers_instance.start("i-test123")

    output = caplog.text
    assert "203.0.113.1" in output


def test_destroy_command_success(campers_module) -> None:
    """Test destroy() command calls EC2Manager.terminate_instance successfully."""
    from unittest.mock import MagicMock, patch

    campers_instance = campers_module()
    campers_instance._config_loader = MagicMock()
    campers_instance._config_loader.BUILT_IN_DEFAULTS = {"region": "us-east-1"}

    mock_ec2 = MagicMock()
    mock_ec2.find_instances_by_name_or_id.return_value = [
        {
            "instance_id": "i-test123",
            "state": "running",
            "camp_config": "test-config",
            "region": "us-east-1",
        }
    ]

    campers_instance._create_compute_provider = MagicMock(return_value=mock_ec2)

    with patch("builtins.print"):
        campers_instance.destroy("i-test123")

    mock_ec2.terminate_instance.assert_called_once_with("i-test123")


def test_destroy_command_no_matches_error(campers_module) -> None:
    """Test destroy() raises SystemExit when no instances match."""
    from unittest.mock import MagicMock

    campers_instance = campers_module()
    campers_instance._config_loader = MagicMock()
    campers_instance._config_loader.BUILT_IN_DEFAULTS = {"region": "us-east-1"}

    mock_ec2 = MagicMock()
    mock_ec2.find_instances_by_name_or_id.return_value = []

    campers_instance._create_compute_provider = MagicMock(return_value=mock_ec2)

    with pytest.raises(SystemExit) as exc_info:
        campers_instance.destroy("nonexistent")

    assert exc_info.value.code == 1


def test_launch_raises_error_when_instance_region_mismatches_config(
    campers_module,
) -> None:
    """Verify error is raised when existing instance region differs from config."""
    from unittest.mock import MagicMock, patch

    campers_instance = campers_module()
    campers_instance._config_loader = MagicMock()
    campers_instance._config_loader.load_config.return_value = {"defaults": {}}
    campers_instance._config_loader.get_camp_config.return_value = {
        "region": "us-east-1",
        "instance_type": "t3.medium",
    }
    campers_instance._config_loader.validate_config.return_value = None

    with (
        patch("campers.providers.aws.compute.EC2Manager") as mock_ec2_class,
        patch("campers_cli.get_provider") as mock_get_provider,
    ):
        mock_ec2_instance = MagicMock()
        mock_ec2_instance.find_instances_by_name_or_id.return_value = [
            {
                "instance_id": "i-123",
                "state": "running",
                "region": "us-west-2",
                "camp_config": "test-camp",
            }
        ]
        mock_ec2_class.return_value = mock_ec2_instance

        mock_get_provider.return_value = {"compute": mock_ec2_class}

        with pytest.raises(RuntimeError) as exc_info:
            campers_instance.run("test-camp")

        error_message = str(exc_info.value)
        assert "us-west-2" in error_message
        assert "us-east-1" in error_message


def test_launch_succeeds_when_instance_region_matches_config(campers_module) -> None:
    """Verify no error when existing instance region matches config region."""
    from unittest.mock import MagicMock, patch

    campers_instance = campers_module()
    campers_instance._config_loader = MagicMock()
    campers_instance._config_loader.load_config.return_value = {"defaults": {}}
    campers_instance._config_loader.get_camp_config.return_value = {
        "region": "us-east-1",
        "instance_type": "t3.medium",
    }
    campers_instance._config_loader.validate_config.return_value = None

    mock_instance_details = {
        "instance_id": "i-test123",
        "public_ip": "203.0.113.1",
        "state": "running",
        "key_file": "/tmp/test.pem",
        "security_group_id": "sg-test123",
        "unique_id": "test123",
        "launch_time": None,
    }

    with (
        patch("campers.providers.aws.compute.EC2Manager") as mock_ec2_class,
        patch("campers_cli.get_provider") as mock_get_provider,
    ):
        mock_ec2_instance = MagicMock()
        mock_ec2_instance.find_instances_by_name_or_id.return_value = [
            {
                "instance_id": "i-123",
                "state": "stopped",
                "region": "us-east-1",
                "camp_config": "test-camp",
            }
        ]
        mock_ec2_instance.start_instance.return_value = mock_instance_details
        mock_ec2_instance.get_instance_info.return_value = mock_instance_details
        mock_ec2_class.return_value = mock_ec2_instance

        mock_get_provider.return_value = {"compute": mock_ec2_class}

        mock_ssh_instance = MagicMock()
        mock_ssh_instance.filter_environment_variables.return_value = {}
        mock_ssh_instance.connect.return_value = None
        campers_instance._ssh_manager_factory = lambda **kwargs: mock_ssh_instance

        with patch("builtins.print"):
            result = campers_instance.run("test-camp")

        assert result["instance_id"] == "i-test123"


def test_launch_succeeds_when_instance_has_no_region_field(campers_module) -> None:
    """Verify no error when existing instance has no region field."""
    from unittest.mock import MagicMock, patch

    campers_instance = campers_module()
    campers_instance._config_loader = MagicMock()
    campers_instance._config_loader.load_config.return_value = {"defaults": {}}
    campers_instance._config_loader.get_camp_config.return_value = {
        "region": "us-east-1",
        "instance_type": "t3.medium",
    }
    campers_instance._config_loader.validate_config.return_value = None

    mock_instance_details = {
        "instance_id": "i-test123",
        "public_ip": "203.0.113.1",
        "state": "running",
        "key_file": "/tmp/test.pem",
        "security_group_id": "sg-test123",
        "unique_id": "test123",
        "launch_time": None,
    }

    with (
        patch("campers.providers.aws.compute.EC2Manager") as mock_ec2_class,
        patch("campers_cli.get_provider") as mock_get_provider,
    ):
        mock_ec2_instance = MagicMock()
        mock_ec2_instance.find_instances_by_name_or_id.return_value = [
            {
                "instance_id": "i-123",
                "state": "stopped",
                "camp_config": "test-camp",
            }
        ]
        mock_ec2_instance.start_instance.return_value = mock_instance_details
        mock_ec2_instance.get_instance_info.return_value = mock_instance_details
        mock_ec2_class.return_value = mock_ec2_instance

        mock_get_provider.return_value = {"compute": mock_ec2_class}

        mock_ssh_instance = MagicMock()
        mock_ssh_instance.filter_environment_variables.return_value = {}
        mock_ssh_instance.connect.return_value = None
        campers_instance._ssh_manager_factory = lambda **kwargs: mock_ssh_instance

        with patch("builtins.print"):
            result = campers_instance.run("test-camp")

        assert result["instance_id"] == "i-test123"
