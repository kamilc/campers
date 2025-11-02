"""Tests for moondock CLI.

This module contains unit tests for the moondock CLI application, specifically
testing class instantiation, method functionality, and command-line execution.

Tests
-----
test_moondock_class_exists
    Verifies that the Moondock class can be imported and instantiated.

"""

import shlex
from pathlib import Path

import pytest


@pytest.fixture
def moondock_module():
    """Fixture to handle sys.path manipulation for importing moondock.

    Yields
    ------
    type[Moondock]
        The Moondock class for testing.

    """
    import importlib.util
    import sys

    project_root = Path(__file__).parent.parent
    moondock_script = project_root / "moondock" / "__main__.py"

    spec = importlib.util.spec_from_file_location("moondock_cli", moondock_script)
    module = importlib.util.module_from_spec(spec)
    sys.modules["moondock_cli"] = module
    spec.loader.exec_module(module)

    yield module.Moondock


def test_moondock_class_exists(moondock_module) -> None:
    """Test that Moondock class can be imported and instantiated."""
    moondock_instance = moondock_module()

    assert moondock_instance is not None


def test_run_executes_setup_script_before_command(moondock_module) -> None:
    """Test that run() executes setup_script before command."""
    from unittest.mock import MagicMock, patch

    moondock_instance = moondock_module()
    moondock_instance._config_loader = MagicMock()
    moondock_instance._config_loader.load_config.return_value = {"defaults": {}}
    moondock_instance._config_loader.get_machine_config.return_value = {
        "region": "us-east-1",
        "instance_type": "t3.medium",
        "setup_script": "echo setup",
        "command": "echo command",
    }
    moondock_instance._config_loader.validate_config.return_value = None

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
        patch("moondock_cli.EC2Manager") as mock_ec2,
    ):
        mock_ec2_instance = MagicMock()
        mock_ec2_instance.launch_instance.return_value = mock_instance_details
        mock_ec2.return_value = mock_ec2_instance

        mock_ssh_instance = MagicMock()
        mock_ssh_instance.filter_environment_variables.return_value = {}
        mock_ssh_instance.connect.return_value = None
        mock_ssh_instance.build_command_with_env.side_effect = lambda cmd, env: cmd

        def track_execute_command(cmd: str) -> int:
            execution_order.append(cmd)
            return 0

        mock_ssh_instance.execute_command.side_effect = track_execute_command
        moondock_instance.ssh_manager_factory = lambda **kwargs: mock_ssh_instance

        result = moondock_instance.run()

    assert len(execution_order) == 2
    assert execution_order[0] == "echo setup"
    assert execution_order[1] == "echo command"
    assert result["instance_id"] == "i-test123"


def test_run_setup_script_failure_prevents_command(moondock_module) -> None:
    """Test that setup_script failure prevents command execution."""
    from unittest.mock import MagicMock, patch

    moondock_instance = moondock_module()
    moondock_instance._config_loader = MagicMock()
    moondock_instance._config_loader.load_config.return_value = {"defaults": {}}
    moondock_instance._config_loader.get_machine_config.return_value = {
        "region": "us-east-1",
        "instance_type": "t3.medium",
        "setup_script": "exit 1",
        "command": "echo command",
    }
    moondock_instance._config_loader.validate_config.return_value = None

    mock_instance_details = {
        "instance_id": "i-test123",
        "public_ip": "203.0.113.1",
        "state": "running",
        "key_file": "/tmp/test.pem",
        "security_group_id": "sg-test123",
        "unique_id": "test123",
    }

    with (
        patch("moondock_cli.EC2Manager") as mock_ec2,
    ):
        mock_ec2_instance = MagicMock()
        mock_ec2_instance.launch_instance.return_value = mock_instance_details
        mock_ec2.return_value = mock_ec2_instance

        mock_ssh_instance = MagicMock()
        mock_ssh_instance.filter_environment_variables.return_value = {}
        mock_ssh_instance.connect.return_value = None
        mock_ssh_instance.build_command_with_env.side_effect = lambda cmd, env: cmd
        mock_ssh_instance.execute_command.return_value = 1
        moondock_instance.ssh_manager_factory = lambda **kwargs: mock_ssh_instance

        with pytest.raises(RuntimeError, match="Setup script failed with exit code: 1"):
            moondock_instance.run()

        assert mock_ssh_instance.execute_command.call_count == 1
        mock_ssh_instance.close.assert_called_once()


def test_run_skips_ssh_when_no_setup_script_or_command(moondock_module) -> None:
    """Test that run() skips SSH when no setup_script or command."""
    from unittest.mock import MagicMock, patch

    moondock_instance = moondock_module()
    moondock_instance._config_loader = MagicMock()
    moondock_instance._config_loader.load_config.return_value = {"defaults": {}}
    moondock_instance._config_loader.get_machine_config.return_value = {
        "region": "us-east-1",
        "instance_type": "t3.medium",
    }
    moondock_instance._config_loader.validate_config.return_value = None

    mock_instance_details = {
        "instance_id": "i-test123",
        "public_ip": "203.0.113.1",
        "state": "running",
        "key_file": "/tmp/test.pem",
        "security_group_id": "sg-test123",
        "unique_id": "test123",
    }

    with (
        patch("moondock_cli.EC2Manager") as mock_ec2,
    ):
        mock_ec2_instance = MagicMock()
        mock_ec2_instance.launch_instance.return_value = mock_instance_details
        mock_ec2.return_value = mock_ec2_instance

        mock_ssh_factory = MagicMock()
        moondock_instance.ssh_manager_factory = mock_ssh_factory

        result = moondock_instance.run()

        mock_ssh_factory.assert_not_called()
        assert result["instance_id"] == "i-test123"


def test_run_only_setup_script_no_command(moondock_module) -> None:
    """Test that run() executes setup_script without command."""
    from unittest.mock import MagicMock, patch

    moondock_instance = moondock_module()
    moondock_instance._config_loader = MagicMock()
    moondock_instance._config_loader.load_config.return_value = {"defaults": {}}
    moondock_instance._config_loader.get_machine_config.return_value = {
        "region": "us-east-1",
        "instance_type": "t3.medium",
        "setup_script": "sudo apt update",
    }
    moondock_instance._config_loader.validate_config.return_value = None

    mock_instance_details = {
        "instance_id": "i-test123",
        "public_ip": "203.0.113.1",
        "state": "running",
        "key_file": "/tmp/test.pem",
        "security_group_id": "sg-test123",
        "unique_id": "test123",
    }

    with (
        patch("moondock_cli.EC2Manager") as mock_ec2,
    ):
        mock_ec2_instance = MagicMock()
        mock_ec2_instance.launch_instance.return_value = mock_instance_details
        mock_ec2.return_value = mock_ec2_instance

        mock_ssh_instance = MagicMock()
        mock_ssh_instance.filter_environment_variables.return_value = {}
        mock_ssh_instance.connect.return_value = None
        mock_ssh_instance.build_command_with_env.side_effect = lambda cmd, env: cmd
        mock_ssh_instance.execute_command.return_value = 0
        moondock_instance.ssh_manager_factory = lambda **kwargs: mock_ssh_instance

        result = moondock_instance.run()

        mock_ssh_instance.execute_command.assert_called_once_with("sudo apt update")
        mock_ssh_instance.close.assert_called_once()
        assert result["instance_id"] == "i-test123"


def test_run_startup_script_without_sync_paths_raises_error(moondock_module) -> None:
    """Test that startup_script without sync_paths raises ValueError."""
    from unittest.mock import MagicMock

    moondock_instance = moondock_module()
    moondock_instance._config_loader = MagicMock()
    moondock_instance._config_loader.load_config.return_value = {"defaults": {}}
    moondock_instance._config_loader.get_machine_config.return_value = {
        "region": "us-east-1",
        "instance_type": "t3.medium",
        "startup_script": "source .venv/bin/activate",
    }
    moondock_instance._config_loader.validate_config.return_value = None

    with pytest.raises(
        ValueError, match="startup_script is defined but no sync_paths configured"
    ):
        moondock_instance.run()


def test_run_with_sync_paths_creates_mutagen_session(moondock_module) -> None:
    """Test that run() creates Mutagen session when sync_paths configured."""
    from unittest.mock import MagicMock, patch

    moondock_instance = moondock_module()
    moondock_instance._config_loader = MagicMock()
    moondock_instance._config_loader.load_config.return_value = {"defaults": {}}
    moondock_instance._config_loader.get_machine_config.return_value = {
        "region": "us-east-1",
        "instance_type": "t3.medium",
        "sync_paths": [{"local": "~/myproject", "remote": "~/myproject"}],
        "command": "echo test",
    }
    moondock_instance._config_loader.validate_config.return_value = None

    mock_instance_details = {
        "instance_id": "i-test123",
        "public_ip": "203.0.113.1",
        "state": "running",
        "key_file": "/tmp/test.pem",
        "security_group_id": "sg-test123",
        "unique_id": "test123",
    }

    with (
        patch("moondock_cli.EC2Manager") as mock_ec2,
        patch("moondock_cli.MutagenManager") as mock_mutagen,
    ):
        mock_ec2_instance = MagicMock()
        mock_ec2_instance.launch_instance.return_value = mock_instance_details
        mock_ec2.return_value = mock_ec2_instance

        mock_ssh_instance = MagicMock()
        mock_ssh_instance.filter_environment_variables.return_value = {}
        mock_ssh_instance.connect.return_value = None
        mock_ssh_instance.build_command_with_env.side_effect = lambda cmd, env: cmd
        mock_ssh_instance.execute_command_raw.return_value = 0
        moondock_instance.ssh_manager_factory = lambda **kwargs: mock_ssh_instance

        mock_mutagen_instance = MagicMock()
        mock_mutagen.return_value = mock_mutagen_instance

        result = moondock_instance.run()

        mock_mutagen_instance.check_mutagen_installed.assert_called_once()
        mock_mutagen_instance.cleanup_orphaned_session.assert_called_once()
        mock_mutagen_instance.create_sync_session.assert_called_once()
        mock_mutagen_instance.wait_for_initial_sync.assert_called_once()
        mock_mutagen_instance.terminate_session.assert_called_once()
        assert result["instance_id"] == "i-test123"


def test_run_executes_command_from_synced_directory(moondock_module) -> None:
    """Test that command executes from synced directory when sync_paths configured."""
    from unittest.mock import MagicMock, patch

    moondock_instance = moondock_module()
    moondock_instance._config_loader = MagicMock()
    moondock_instance._config_loader.load_config.return_value = {"defaults": {}}
    moondock_instance._config_loader.get_machine_config.return_value = {
        "region": "us-east-1",
        "instance_type": "t3.medium",
        "sync_paths": [{"local": "~/myproject", "remote": "~/myproject"}],
        "command": "pwd",
    }
    moondock_instance._config_loader.validate_config.return_value = None

    mock_instance_details = {
        "instance_id": "i-test123",
        "public_ip": "203.0.113.1",
        "state": "running",
        "key_file": "/tmp/test.pem",
        "security_group_id": "sg-test123",
        "unique_id": "test123",
    }

    with (
        patch("moondock_cli.EC2Manager") as mock_ec2,
        patch("moondock_cli.MutagenManager") as mock_mutagen,
    ):
        mock_ec2_instance = MagicMock()
        mock_ec2_instance.launch_instance.return_value = mock_instance_details
        mock_ec2.return_value = mock_ec2_instance

        mock_ssh_instance = MagicMock()
        mock_ssh_instance.filter_environment_variables.return_value = {}
        mock_ssh_instance.connect.return_value = None
        mock_ssh_instance.build_command_with_env.side_effect = lambda cmd, env: cmd
        mock_ssh_instance.execute_command_raw.return_value = 0
        moondock_instance.ssh_manager_factory = lambda **kwargs: mock_ssh_instance

        mock_mutagen_instance = MagicMock()
        mock_mutagen.return_value = mock_mutagen_instance

        result = moondock_instance.run()

        mock_ssh_instance.execute_command_raw.assert_called_once()
        call_args = mock_ssh_instance.execute_command_raw.call_args[0][0]
        assert "cd ~/myproject" in call_args
        assert "pwd" in call_args
        assert result["instance_id"] == "i-test123"


def test_run_executes_startup_script_from_synced_directory(moondock_module) -> None:
    """Test that startup_script executes from synced directory."""
    from unittest.mock import MagicMock, patch

    moondock_instance = moondock_module()
    moondock_instance._config_loader = MagicMock()
    moondock_instance._config_loader.load_config.return_value = {"defaults": {}}
    moondock_instance._config_loader.get_machine_config.return_value = {
        "region": "us-east-1",
        "instance_type": "t3.medium",
        "sync_paths": [{"local": "~/myproject", "remote": "~/myproject"}],
        "startup_script": "source .venv/bin/activate",
        "command": "python app.py",
    }
    moondock_instance._config_loader.validate_config.return_value = None

    mock_instance_details = {
        "instance_id": "i-test123",
        "public_ip": "203.0.113.1",
        "state": "running",
        "key_file": "/tmp/test.pem",
        "security_group_id": "sg-test123",
        "unique_id": "test123",
    }

    with (
        patch("moondock_cli.EC2Manager") as mock_ec2,
        patch("moondock_cli.MutagenManager") as mock_mutagen,
    ):
        mock_ec2_instance = MagicMock()
        mock_ec2_instance.launch_instance.return_value = mock_instance_details
        mock_ec2.return_value = mock_ec2_instance

        mock_ssh_instance = MagicMock()
        mock_ssh_instance.filter_environment_variables.return_value = {}
        mock_ssh_instance.connect.return_value = None
        mock_ssh_instance.build_command_with_env.side_effect = lambda cmd, env: cmd
        mock_ssh_instance.execute_command_raw.return_value = 0
        moondock_instance.ssh_manager_factory = lambda **kwargs: mock_ssh_instance

        mock_mutagen_instance = MagicMock()
        mock_mutagen.return_value = mock_mutagen_instance

        result = moondock_instance.run()

        assert mock_ssh_instance.execute_command_raw.call_count == 2
        startup_call = mock_ssh_instance.execute_command_raw.call_args_list[0][0][0]
        assert "cd ~/myproject" in startup_call
        assert "source .venv/bin/activate" in startup_call
        assert result["instance_id"] == "i-test123"


def test_build_command_in_directory(moondock_module) -> None:
    """Test build_command_in_directory creates proper command string."""
    moondock_instance = moondock_module()

    result = moondock_instance._build_command_in_directory(
        "~/myproject", "python app.py"
    )

    assert result == "mkdir -p ~/myproject && cd ~/myproject && bash -c 'python app.py'"


def test_build_command_in_directory_with_special_chars(moondock_module) -> None:
    """Test build_command_in_directory handles special characters."""
    moondock_instance = moondock_module()

    result = moondock_instance._build_command_in_directory(
        "~/my project", "echo 'hello world'"
    )

    assert "mkdir -p ~/'my project'" in result
    assert "cd ~/'my project'" in result
    assert "bash -c" in result


def test_build_command_in_directory_with_multiline_script(moondock_module) -> None:
    """Test build_command_in_directory handles multiline scripts."""
    moondock_instance = moondock_module()

    multiline_script = """source .venv/bin/activate
export DEBUG=1
python app.py"""

    result = moondock_instance._build_command_in_directory("~/app", multiline_script)

    assert (
        result
        == f"mkdir -p ~/app && cd ~/app && bash -c {shlex.quote(multiline_script)}"
    )
    assert "source .venv/bin/activate" in result


def test_run_startup_script_failure_prevents_command(moondock_module) -> None:
    """Test that startup_script failure prevents command execution."""
    from unittest.mock import MagicMock, patch

    moondock_instance = moondock_module()
    moondock_instance._config_loader = MagicMock()
    moondock_instance._config_loader.load_config.return_value = {"defaults": {}}
    moondock_instance._config_loader.get_machine_config.return_value = {
        "region": "us-east-1",
        "instance_type": "t3.medium",
        "sync_paths": [{"local": "~/myproject", "remote": "~/myproject"}],
        "startup_script": "exit 42",
        "command": "echo hello",
    }
    moondock_instance._config_loader.validate_config.return_value = None

    mock_instance_details = {
        "instance_id": "i-test123",
        "public_ip": "203.0.113.1",
        "state": "running",
        "key_file": "/tmp/test.pem",
        "security_group_id": "sg-test123",
        "unique_id": "test123",
    }

    with (
        patch("moondock_cli.EC2Manager") as mock_ec2,
        patch("moondock_cli.MutagenManager") as mock_mutagen,
    ):
        mock_ec2_instance = MagicMock()
        mock_ec2_instance.launch_instance.return_value = mock_instance_details
        mock_ec2.return_value = mock_ec2_instance

        mock_ssh_instance = MagicMock()
        mock_ssh_instance.filter_environment_variables.return_value = {}
        mock_ssh_instance.connect.return_value = None
        mock_ssh_instance.build_command_with_env.side_effect = lambda cmd, env: cmd
        mock_ssh_instance.execute_command_raw.return_value = 42
        moondock_instance.ssh_manager_factory = lambda **kwargs: mock_ssh_instance

        mock_mutagen_instance = MagicMock()
        mock_mutagen.return_value = mock_mutagen_instance

        with pytest.raises(
            RuntimeError, match="Startup script failed with exit code: 42"
        ):
            moondock_instance.run()

        assert mock_ssh_instance.execute_command_raw.call_count == 1
        mock_ssh_instance.close.assert_called_once()


def test_run_multiline_startup_script(moondock_module) -> None:
    """Test that multiline startup_script executes correctly."""
    from unittest.mock import MagicMock, patch

    moondock_instance = moondock_module()
    moondock_instance._config_loader = MagicMock()
    moondock_instance._config_loader.load_config.return_value = {"defaults": {}}

    multiline_script = """source .venv/bin/activate
export DEBUG=1
cd src"""

    moondock_instance._config_loader.get_machine_config.return_value = {
        "region": "us-east-1",
        "instance_type": "t3.medium",
        "sync_paths": [{"local": "~/myproject", "remote": "~/myproject"}],
        "startup_script": multiline_script,
        "command": "pwd",
    }
    moondock_instance._config_loader.validate_config.return_value = None

    mock_instance_details = {
        "instance_id": "i-test123",
        "public_ip": "203.0.113.1",
        "state": "running",
        "key_file": "/tmp/test.pem",
        "security_group_id": "sg-test123",
        "unique_id": "test123",
    }

    with (
        patch("moondock_cli.EC2Manager") as mock_ec2,
        patch("moondock_cli.MutagenManager") as mock_mutagen,
    ):
        mock_ec2_instance = MagicMock()
        mock_ec2_instance.launch_instance.return_value = mock_instance_details
        mock_ec2.return_value = mock_ec2_instance

        mock_ssh_instance = MagicMock()
        mock_ssh_instance.filter_environment_variables.return_value = {}
        mock_ssh_instance.connect.return_value = None
        mock_ssh_instance.build_command_with_env.side_effect = lambda cmd, env: cmd
        mock_ssh_instance.execute_command_raw.return_value = 0
        moondock_instance.ssh_manager_factory = lambda **kwargs: mock_ssh_instance

        mock_mutagen_instance = MagicMock()
        mock_mutagen.return_value = mock_mutagen_instance

        result = moondock_instance.run()

        startup_call = mock_ssh_instance.execute_command_raw.call_args_list[0][0][0]
        assert "source .venv/bin/activate" in startup_call
        assert "export DEBUG=1" in startup_call
        assert "cd src" in startup_call
        assert result["instance_id"] == "i-test123"


def test_run_with_port_forwarding_creates_tunnels(moondock_module) -> None:
    """Test that run() creates port forwarding tunnels when ports configured."""
    from unittest.mock import MagicMock, patch

    moondock_instance = moondock_module()
    moondock_instance._config_loader = MagicMock()
    moondock_instance._config_loader.load_config.return_value = {"defaults": {}}
    moondock_instance._config_loader.get_machine_config.return_value = {
        "region": "us-east-1",
        "instance_type": "t3.medium",
        "ports": [8888, 8080],
        "command": "echo test",
    }
    moondock_instance._config_loader.validate_config.return_value = None

    mock_instance_details = {
        "instance_id": "i-test123",
        "public_ip": "203.0.113.1",
        "state": "running",
        "key_file": "/tmp/test.pem",
        "security_group_id": "sg-test123",
        "unique_id": "test123",
    }

    with (
        patch("moondock_cli.EC2Manager") as mock_ec2,
        patch("moondock_cli.PortForwardManager") as mock_portforward,
    ):
        mock_ec2_instance = MagicMock()
        mock_ec2_instance.launch_instance.return_value = mock_instance_details
        mock_ec2.return_value = mock_ec2_instance

        mock_ssh_instance = MagicMock()
        mock_ssh_instance.filter_environment_variables.return_value = {}
        mock_ssh_instance.connect.return_value = None
        mock_ssh_instance.build_command_with_env.side_effect = lambda cmd, env: cmd
        mock_ssh_instance.execute_command_raw.return_value = 0
        moondock_instance.ssh_manager_factory = lambda **kwargs: mock_ssh_instance

        mock_portforward_instance = MagicMock()
        mock_portforward.return_value = mock_portforward_instance

        result = moondock_instance.run()

        mock_portforward_instance.create_tunnels.assert_called_once_with(
            ports=[8888, 8080],
            host="203.0.113.1",
            key_file="/tmp/test.pem",
            username="ubuntu",
            ssh_port=22,
        )
        mock_portforward_instance.stop_all_tunnels.assert_called_once()
        assert result["instance_id"] == "i-test123"


def test_run_port_forwarding_cleanup_order(moondock_module) -> None:
    """Test that port forwarding tunnels stop before SSH closes."""
    from unittest.mock import MagicMock, patch

    moondock_instance = moondock_module()
    moondock_instance._config_loader = MagicMock()
    moondock_instance._config_loader.load_config.return_value = {"defaults": {}}
    moondock_instance._config_loader.get_machine_config.return_value = {
        "region": "us-east-1",
        "instance_type": "t3.medium",
        "ports": [8888],
        "command": "echo test",
    }
    moondock_instance._config_loader.validate_config.return_value = None

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
        patch("moondock_cli.EC2Manager") as mock_ec2,
        patch("moondock_cli.PortForwardManager") as mock_portforward,
    ):
        mock_ec2_instance = MagicMock()
        mock_ec2_instance.launch_instance.return_value = mock_instance_details
        mock_ec2.return_value = mock_ec2_instance

        mock_ssh_instance = MagicMock()
        mock_ssh_instance.filter_environment_variables.return_value = {}
        mock_ssh_instance.connect.return_value = None
        mock_ssh_instance.build_command_with_env.side_effect = lambda cmd, env: cmd
        mock_ssh_instance.execute_command_raw.return_value = 0
        mock_ssh_instance.close.side_effect = lambda: cleanup_order.append("ssh_close")
        moondock_instance.ssh_manager_factory = lambda **kwargs: mock_ssh_instance

        mock_portforward_instance = MagicMock()
        mock_portforward_instance.stop_all_tunnels.side_effect = (
            lambda: cleanup_order.append("tunnels_stop")
        )
        mock_portforward.return_value = mock_portforward_instance

        result = moondock_instance.run()

        assert cleanup_order == ["tunnels_stop", "ssh_close"]
        assert result["instance_id"] == "i-test123"


def test_run_port_forwarding_error_triggers_cleanup(moondock_module) -> None:
    """Test that port forwarding error triggers full cleanup."""
    from unittest.mock import MagicMock, patch

    moondock_instance = moondock_module()
    moondock_instance._config_loader = MagicMock()
    moondock_instance._config_loader.load_config.return_value = {"defaults": {}}
    moondock_instance._config_loader.get_machine_config.return_value = {
        "region": "us-east-1",
        "instance_type": "t3.medium",
        "ports": [8888],
        "command": "echo test",
    }
    moondock_instance._config_loader.validate_config.return_value = None

    mock_instance_details = {
        "instance_id": "i-test123",
        "public_ip": "203.0.113.1",
        "state": "running",
        "key_file": "/tmp/test.pem",
        "security_group_id": "sg-test123",
        "unique_id": "test123",
    }

    with (
        patch("moondock_cli.EC2Manager") as mock_ec2,
        patch("moondock_cli.PortForwardManager") as mock_portforward,
    ):
        mock_ec2_instance = MagicMock()
        mock_ec2_instance.launch_instance.return_value = mock_instance_details
        mock_ec2.return_value = mock_ec2_instance

        mock_ssh_instance = MagicMock()
        mock_ssh_instance.filter_environment_variables.return_value = {}
        mock_ssh_instance.connect.return_value = None
        mock_ssh_instance.build_command_with_env.side_effect = lambda cmd, env: cmd
        moondock_instance.ssh_manager_factory = lambda **kwargs: mock_ssh_instance

        mock_portforward_instance = MagicMock()
        mock_portforward_instance.create_tunnels.side_effect = RuntimeError(
            "Port 8888 already in use"
        )
        mock_portforward.return_value = mock_portforward_instance

        with pytest.raises(RuntimeError, match="Port 8888 already in use"):
            moondock_instance.run()

        mock_portforward_instance.stop_all_tunnels.assert_called_once()
        mock_ssh_instance.close.assert_called_once()


def test_run_port_forwarding_with_sync_paths(moondock_module) -> None:
    """Test that port forwarding works with sync_paths enabled."""
    from unittest.mock import MagicMock, patch

    moondock_instance = moondock_module()
    moondock_instance._config_loader = MagicMock()
    moondock_instance._config_loader.load_config.return_value = {"defaults": {}}
    moondock_instance._config_loader.get_machine_config.return_value = {
        "region": "us-east-1",
        "instance_type": "t3.medium",
        "ports": [8888],
        "sync_paths": [{"local": "~/myproject", "remote": "~/myproject"}],
        "command": "echo test",
    }
    moondock_instance._config_loader.validate_config.return_value = None

    mock_instance_details = {
        "instance_id": "i-test123",
        "public_ip": "203.0.113.1",
        "state": "running",
        "key_file": "/tmp/test.pem",
        "security_group_id": "sg-test123",
        "unique_id": "test123",
    }

    with (
        patch("moondock_cli.EC2Manager") as mock_ec2,
        patch("moondock_cli.MutagenManager") as mock_mutagen,
        patch("moondock_cli.PortForwardManager") as mock_portforward,
    ):
        mock_ec2_instance = MagicMock()
        mock_ec2_instance.launch_instance.return_value = mock_instance_details
        mock_ec2.return_value = mock_ec2_instance

        mock_ssh_instance = MagicMock()
        mock_ssh_instance.filter_environment_variables.return_value = {}
        mock_ssh_instance.connect.return_value = None
        mock_ssh_instance.build_command_with_env.side_effect = lambda cmd, env: cmd
        mock_ssh_instance.execute_command_raw.return_value = 0
        moondock_instance.ssh_manager_factory = lambda **kwargs: mock_ssh_instance

        mock_mutagen_instance = MagicMock()
        mock_mutagen.return_value = mock_mutagen_instance

        mock_portforward_instance = MagicMock()
        mock_portforward.return_value = mock_portforward_instance

        result = moondock_instance.run()

        mock_portforward_instance.create_tunnels.assert_called_once()
        mock_mutagen_instance.create_sync_session.assert_called_once()
        assert result["instance_id"] == "i-test123"


def test_run_port_forwarding_with_startup_script(moondock_module) -> None:
    """Test that port forwarding establishes before startup_script runs."""
    from unittest.mock import MagicMock, patch

    moondock_instance = moondock_module()
    moondock_instance._config_loader = MagicMock()
    moondock_instance._config_loader.load_config.return_value = {"defaults": {}}
    moondock_instance._config_loader.get_machine_config.return_value = {
        "region": "us-east-1",
        "instance_type": "t3.medium",
        "ports": [8888],
        "sync_paths": [{"local": "~/myproject", "remote": "~/myproject"}],
        "startup_script": "echo startup",
        "command": "echo command",
    }
    moondock_instance._config_loader.validate_config.return_value = None

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
        patch("moondock_cli.EC2Manager") as mock_ec2,
        patch("moondock_cli.MutagenManager") as mock_mutagen,
        patch("moondock_cli.PortForwardManager") as mock_portforward,
    ):
        mock_ec2_instance = MagicMock()
        mock_ec2_instance.launch_instance.return_value = mock_instance_details
        mock_ec2.return_value = mock_ec2_instance

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
        moondock_instance.ssh_manager_factory = lambda **kwargs: mock_ssh_instance

        mock_mutagen_instance = MagicMock()
        mock_mutagen.return_value = mock_mutagen_instance

        mock_portforward_instance = MagicMock()
        mock_portforward_instance.create_tunnels.side_effect = (
            lambda **kwargs: execution_order.append("port_forward")
        )
        mock_portforward.return_value = mock_portforward_instance

        result = moondock_instance.run()

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
    moondock_module, env_filter, expected_error
) -> None:
    """Test that invalid regex patterns in env_filter are caught during validation."""
    from moondock.config import ConfigLoader

    moondock_instance = moondock_module()
    moondock_instance._config_loader = ConfigLoader()

    config_data = {
        "defaults": {
            "region": "us-east-1",
            "instance_type": "t3.medium",
            "disk_size": 50,
            "env_filter": env_filter,
        }
    }

    with pytest.raises(ValueError) as exc_info:
        moondock_instance._config_loader.validate_config(config_data["defaults"])

    assert expected_error in str(exc_info.value)


def test_run_filters_environment_variables_after_ssh_connection(
    moondock_module,
) -> None:
    """Test that environment variables are filtered after SSH connection."""
    from unittest.mock import MagicMock, patch

    moondock_instance = moondock_module()
    moondock_instance._config_loader = MagicMock()
    moondock_instance._config_loader.load_config.return_value = {"defaults": {}}
    moondock_instance._config_loader.get_machine_config.return_value = {
        "region": "us-east-1",
        "instance_type": "t3.medium",
        "env_filter": ["AWS_.*"],
        "command": "aws s3 ls",
    }
    moondock_instance._config_loader.validate_config.return_value = None

    mock_instance_details = {
        "instance_id": "i-test123",
        "public_ip": "203.0.113.1",
        "state": "running",
        "key_file": "/tmp/test.pem",
        "security_group_id": "sg-test123",
        "unique_id": "test123",
    }

    with (
        patch("moondock_cli.EC2Manager") as mock_ec2,
    ):
        mock_ec2_instance = MagicMock()
        mock_ec2_instance.launch_instance.return_value = mock_instance_details
        mock_ec2.return_value = mock_ec2_instance

        mock_ssh_instance = MagicMock()
        mock_ssh_instance.filter_environment_variables.return_value = {
            "AWS_REGION": "us-west-2"
        }
        mock_ssh_instance.build_command_with_env.return_value = (
            "export AWS_REGION='us-west-2' && aws s3 ls"
        )
        mock_ssh_instance.execute_command.return_value = 0
        moondock_instance.ssh_manager_factory = lambda **kwargs: mock_ssh_instance

        moondock_instance.run()

        mock_ssh_instance.connect.assert_called_once()
        mock_ssh_instance.filter_environment_variables.assert_called_once_with(
            ["AWS_.*"]
        )
        mock_ssh_instance.build_command_with_env.assert_called()


def test_run_forwards_env_to_setup_script(moondock_module) -> None:
    """Test that environment variables are forwarded to setup_script."""
    from unittest.mock import MagicMock, patch

    moondock_instance = moondock_module()
    moondock_instance._config_loader = MagicMock()
    moondock_instance._config_loader.load_config.return_value = {"defaults": {}}
    moondock_instance._config_loader.get_machine_config.return_value = {
        "region": "us-east-1",
        "instance_type": "t3.medium",
        "env_filter": ["AWS_.*"],
        "setup_script": "aws s3 cp s3://bucket/setup.sh .",
    }
    moondock_instance._config_loader.validate_config.return_value = None

    mock_instance_details = {
        "instance_id": "i-test123",
        "public_ip": "203.0.113.1",
        "state": "running",
        "key_file": "/tmp/test.pem",
        "security_group_id": "sg-test123",
        "unique_id": "test123",
    }

    with (
        patch("moondock_cli.EC2Manager") as mock_ec2,
    ):
        mock_ec2_instance = MagicMock()
        mock_ec2_instance.launch_instance.return_value = mock_instance_details
        mock_ec2.return_value = mock_ec2_instance

        mock_ssh_instance = MagicMock()
        mock_ssh_instance.filter_environment_variables.return_value = {
            "AWS_REGION": "us-west-2"
        }
        mock_ssh_instance.build_command_with_env.return_value = (
            "export AWS_REGION='us-west-2' && aws s3 cp s3://bucket/setup.sh ."
        )
        mock_ssh_instance.execute_command.return_value = 0
        moondock_instance.ssh_manager_factory = lambda **kwargs: mock_ssh_instance

        result = moondock_instance.run()

        mock_ssh_instance.build_command_with_env.assert_called_with(
            "aws s3 cp s3://bucket/setup.sh .", {"AWS_REGION": "us-west-2"}
        )
        assert result["instance_id"] == "i-test123"


def test_run_forwards_env_to_startup_script(moondock_module) -> None:
    """Test that environment variables are forwarded to startup_script."""
    from unittest.mock import MagicMock, patch

    moondock_instance = moondock_module()
    moondock_instance._config_loader = MagicMock()
    moondock_instance._config_loader.load_config.return_value = {"defaults": {}}
    moondock_instance._config_loader.get_machine_config.return_value = {
        "region": "us-east-1",
        "instance_type": "t3.medium",
        "env_filter": ["HF_TOKEN"],
        "sync_paths": [{"local": "~/myproject", "remote": "~/myproject"}],
        "startup_script": "huggingface-cli login",
    }
    moondock_instance._config_loader.validate_config.return_value = None

    mock_instance_details = {
        "instance_id": "i-test123",
        "public_ip": "203.0.113.1",
        "state": "running",
        "key_file": "/tmp/test.pem",
        "security_group_id": "sg-test123",
        "unique_id": "test123",
    }

    with (
        patch("moondock_cli.EC2Manager") as mock_ec2,
        patch("moondock_cli.MutagenManager") as mock_mutagen,
    ):
        mock_ec2_instance = MagicMock()
        mock_ec2_instance.launch_instance.return_value = mock_instance_details
        mock_ec2.return_value = mock_ec2_instance

        mock_ssh_instance = MagicMock()
        mock_ssh_instance.filter_environment_variables.return_value = {
            "HF_TOKEN": "hf_test123"
        }
        mock_ssh_instance.build_command_with_env.return_value = "export HF_TOKEN='hf_test123' && cd ~/myproject && bash -c 'huggingface-cli login'"
        mock_ssh_instance.execute_command_raw.return_value = 0
        moondock_instance.ssh_manager_factory = lambda **kwargs: mock_ssh_instance

        mock_mutagen_instance = MagicMock()
        mock_mutagen.return_value = mock_mutagen_instance

        result = moondock_instance.run()

        calls = mock_ssh_instance.build_command_with_env.call_args_list
        assert any("huggingface-cli login" in str(call) for call in calls)
        assert result["instance_id"] == "i-test123"


def test_run_forwards_env_to_main_command(moondock_module) -> None:
    """Test that environment variables are forwarded to main command."""
    from unittest.mock import MagicMock, patch

    moondock_instance = moondock_module()
    moondock_instance._config_loader = MagicMock()
    moondock_instance._config_loader.load_config.return_value = {"defaults": {}}
    moondock_instance._config_loader.get_machine_config.return_value = {
        "region": "us-east-1",
        "instance_type": "t3.medium",
        "env_filter": ["WANDB_.*"],
        "command": "python train.py",
    }
    moondock_instance._config_loader.validate_config.return_value = None

    mock_instance_details = {
        "instance_id": "i-test123",
        "public_ip": "203.0.113.1",
        "state": "running",
        "key_file": "/tmp/test.pem",
        "security_group_id": "sg-test123",
        "unique_id": "test123",
    }

    with (
        patch("moondock_cli.EC2Manager") as mock_ec2,
    ):
        mock_ec2_instance = MagicMock()
        mock_ec2_instance.launch_instance.return_value = mock_instance_details
        mock_ec2.return_value = mock_ec2_instance

        mock_ssh_instance = MagicMock()
        mock_ssh_instance.filter_environment_variables.return_value = {
            "WANDB_API_KEY": "test-key"
        }
        mock_ssh_instance.build_command_with_env.return_value = (
            "export WANDB_API_KEY='test-key' && python train.py"
        )
        mock_ssh_instance.execute_command.return_value = 0
        moondock_instance.ssh_manager_factory = lambda **kwargs: mock_ssh_instance

        result = moondock_instance.run()

        mock_ssh_instance.build_command_with_env.assert_called_with(
            "python train.py", {"WANDB_API_KEY": "test-key"}
        )
        assert result["command_exit_code"] == 0


def test_moondock_init_cleanup_state(moondock_module) -> None:
    """Test that Moondock instance initializes with cleanup state tracking."""
    moondock_instance = moondock_module()

    assert hasattr(moondock_instance, "_cleanup_in_progress")
    assert moondock_instance._cleanup_in_progress is False
    assert hasattr(moondock_instance, "_resources")
    assert isinstance(moondock_instance._resources, dict)
    assert len(moondock_instance._resources) == 0


def test_signal_handlers_registered_during_run(moondock_module) -> None:
    """Test that SIGINT and SIGTERM handlers are registered during run()."""
    import signal
    from unittest.mock import MagicMock, patch

    moondock_instance = moondock_module()
    moondock_instance._config_loader = MagicMock()
    moondock_instance._config_loader.load_config.return_value = {"defaults": {}}
    moondock_instance._config_loader.get_machine_config.return_value = {
        "region": "us-east-1",
        "instance_type": "t3.medium",
    }
    moondock_instance._config_loader.validate_config.return_value = None

    mock_instance_details = {
        "instance_id": "i-test123",
        "public_ip": "203.0.113.1",
        "state": "running",
        "key_file": "/tmp/test.pem",
        "security_group_id": "sg-test123",
        "unique_id": "test123",
    }

    with (
        patch("moondock_cli.EC2Manager") as mock_ec2,
        patch("moondock_cli.signal.signal") as mock_signal,
    ):
        mock_ec2_instance = MagicMock()
        mock_ec2_instance.launch_instance.return_value = mock_instance_details
        mock_ec2.return_value = mock_ec2_instance

        moondock_instance.run()

        signal_calls = [call[0] for call in mock_signal.call_args_list]
        assert (signal.SIGINT, moondock_instance._cleanup_resources) in signal_calls
        assert (signal.SIGTERM, moondock_instance._cleanup_resources) in signal_calls


def test_signal_handlers_restored_after_run(moondock_module) -> None:
    """Test that original signal handlers are restored after run() completes."""
    import signal
    from unittest.mock import MagicMock, patch

    moondock_instance = moondock_module()
    moondock_instance._config_loader = MagicMock()
    moondock_instance._config_loader.load_config.return_value = {"defaults": {}}
    moondock_instance._config_loader.get_machine_config.return_value = {
        "region": "us-east-1",
        "instance_type": "t3.medium",
    }
    moondock_instance._config_loader.validate_config.return_value = None

    mock_instance_details = {
        "instance_id": "i-test123",
        "public_ip": "203.0.113.1",
        "state": "running",
        "key_file": "/tmp/test.pem",
        "security_group_id": "sg-test123",
        "unique_id": "test123",
    }

    original_sigint = MagicMock()
    original_sigterm = MagicMock()

    with (
        patch("moondock_cli.EC2Manager") as mock_ec2,
        patch("moondock_cli.signal.signal") as mock_signal,
    ):
        mock_ec2_instance = MagicMock()
        mock_ec2_instance.launch_instance.return_value = mock_instance_details
        mock_ec2.return_value = mock_ec2_instance

        mock_signal.side_effect = [
            original_sigint,
            original_sigterm,
            None,
            None,
        ]

        moondock_instance.run()

        signal_calls = mock_signal.call_args_list
        assert (signal.SIGINT, original_sigint) in [
            call[0] for call in signal_calls[-2:]
        ]
        assert (signal.SIGTERM, original_sigterm) in [
            call[0] for call in signal_calls[-2:]
        ]


def test_cleanup_resources_executes_in_correct_order(moondock_module) -> None:
    """Test that cleanup_resources executes cleanup steps in correct order."""
    from unittest.mock import MagicMock

    moondock_instance = moondock_module()

    mock_portforward = MagicMock()
    mock_mutagen = MagicMock()
    mock_ssh = MagicMock()
    mock_ec2 = MagicMock()

    cleanup_order = []

    mock_portforward.stop_all_tunnels.side_effect = lambda: cleanup_order.append(
        "portforward"
    )
    mock_mutagen.terminate_session.side_effect = (
        lambda name, ssh_wrapper_dir=None, host=None: cleanup_order.append("mutagen")
    )
    mock_ssh.close.side_effect = lambda: cleanup_order.append("ssh")
    mock_ec2.terminate_instance.side_effect = lambda id: cleanup_order.append("ec2")

    moondock_instance._resources = {
        "portforward_mgr": mock_portforward,
        "mutagen_mgr": mock_mutagen,
        "mutagen_session_name": "test-session",
        "ssh_manager": mock_ssh,
        "ec2_manager": mock_ec2,
        "instance_details": {"instance_id": "i-test123"},
    }

    moondock_instance._cleanup_resources()

    assert cleanup_order == ["portforward", "mutagen", "ssh", "ec2"]


def test_cleanup_resources_continues_on_error(moondock_module) -> None:
    """Test that cleanup continues even if individual steps fail."""
    from unittest.mock import MagicMock

    moondock_instance = moondock_module()

    mock_portforward = MagicMock()
    mock_mutagen = MagicMock()
    mock_ssh = MagicMock()
    mock_ec2 = MagicMock()

    mock_mutagen.terminate_session.side_effect = RuntimeError("Mutagen error")

    moondock_instance._resources = {
        "portforward_mgr": mock_portforward,
        "mutagen_mgr": mock_mutagen,
        "mutagen_session_name": "test-session",
        "ssh_manager": mock_ssh,
        "ec2_manager": mock_ec2,
        "instance_details": {"instance_id": "i-test123"},
    }

    moondock_instance._cleanup_resources()

    mock_portforward.stop_all_tunnels.assert_called_once()
    mock_mutagen.terminate_session.assert_called_once()
    mock_ssh.close.assert_called_once()
    mock_ec2.terminate_instance.assert_called_once()


def test_cleanup_resources_exits_with_sigint_code(moondock_module) -> None:
    """Test that cleanup_resources exits with code 130 for SIGINT."""
    import signal

    moondock_instance = moondock_module()

    moondock_instance._resources = {}

    with pytest.raises(SystemExit) as exc_info:
        moondock_instance._cleanup_resources(signum=signal.SIGINT, frame=None)

    assert exc_info.value.code == 130


def test_cleanup_resources_exits_with_sigterm_code(moondock_module) -> None:
    """Test that cleanup_resources exits with code 143 for SIGTERM."""
    import signal

    moondock_instance = moondock_module()

    moondock_instance._resources = {}

    with pytest.raises(SystemExit) as exc_info:
        moondock_instance._cleanup_resources(signum=signal.SIGTERM, frame=None)

    assert exc_info.value.code == 143


def test_cleanup_resources_prevents_duplicate_cleanup(moondock_module) -> None:
    """Test that cleanup_in_progress flag prevents duplicate cleanup."""
    from unittest.mock import MagicMock

    moondock_instance = moondock_module()

    mock_ec2 = MagicMock()
    moondock_instance._resources = {
        "ec2_manager": mock_ec2,
        "instance_details": {"instance_id": "i-test123"},
    }

    moondock_instance._cleanup_in_progress = True

    moondock_instance._cleanup_resources()

    mock_ec2.terminate_instance.assert_not_called()


def test_cleanup_resources_only_cleans_tracked_resources(moondock_module) -> None:
    """Test that cleanup only attempts to clean resources that were tracked."""
    from unittest.mock import MagicMock

    moondock_instance = moondock_module()

    mock_ec2 = MagicMock()
    mock_ssh = MagicMock()

    moondock_instance._resources = {
        "ec2_manager": mock_ec2,
        "instance_details": {"instance_id": "i-test123"},
        "ssh_manager": mock_ssh,
    }

    moondock_instance._cleanup_resources()

    mock_ec2.terminate_instance.assert_called_once_with("i-test123")
    mock_ssh.close.assert_called_once()


def test_run_tracks_resources_incrementally(moondock_module) -> None:
    """Test that run() tracks resources as they are created."""
    from unittest.mock import MagicMock, patch

    moondock_instance = moondock_module()
    moondock_instance._config_loader = MagicMock()
    moondock_instance._config_loader.load_config.return_value = {"defaults": {}}
    moondock_instance._config_loader.get_machine_config.return_value = {
        "region": "us-east-1",
        "instance_type": "t3.medium",
        "ports": [8888],
        "sync_paths": [{"local": "~/myproject", "remote": "~/myproject"}],
        "command": "echo test",
    }
    moondock_instance._config_loader.validate_config.return_value = None

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
        captured_resources.update(moondock_instance._resources)

    with (
        patch("moondock_cli.EC2Manager") as mock_ec2,
        patch("moondock_cli.MutagenManager") as mock_mutagen,
        patch("moondock_cli.PortForwardManager") as mock_portforward,
    ):
        mock_ec2_instance = MagicMock()
        mock_ec2_instance.launch_instance.return_value = mock_instance_details
        mock_ec2.return_value = mock_ec2_instance

        mock_ssh_instance = MagicMock()
        mock_ssh_instance.filter_environment_variables.return_value = {}
        mock_ssh_instance.connect.return_value = None
        mock_ssh_instance.build_command_with_env.side_effect = lambda cmd, env: cmd
        mock_ssh_instance.execute_command_raw.return_value = 0
        moondock_instance.ssh_manager_factory = lambda **kwargs: mock_ssh_instance

        mock_mutagen_instance = MagicMock()
        mock_mutagen.return_value = mock_mutagen_instance

        mock_portforward_instance = MagicMock()
        mock_portforward.return_value = mock_portforward_instance

        original_cleanup = moondock_instance._cleanup_resources
        moondock_instance._cleanup_resources = lambda *args, **kwargs: (
            capture_cleanup(),
            original_cleanup(*args, **kwargs),
        )[1]

        moondock_instance.run()

        assert "ec2_manager" in captured_resources
        assert "instance_details" in captured_resources
        assert "ssh_manager" in captured_resources
        assert "portforward_mgr" in captured_resources
        assert "mutagen_mgr" in captured_resources
        assert "mutagen_session_name" in captured_resources


def test_finally_block_calls_cleanup_if_not_already_done(moondock_module) -> None:
    """Test that finally block calls cleanup when signal handler hasn't run."""
    from unittest.mock import MagicMock, patch

    moondock_instance = moondock_module()
    moondock_instance._config_loader = MagicMock()
    moondock_instance._config_loader.load_config.return_value = {"defaults": {}}
    moondock_instance._config_loader.get_machine_config.return_value = {
        "region": "us-east-1",
        "instance_type": "t3.medium",
        "command": "echo test",
    }
    moondock_instance._config_loader.validate_config.return_value = None

    mock_instance_details = {
        "instance_id": "i-test123",
        "public_ip": "203.0.113.1",
        "state": "running",
        "key_file": "/tmp/test.pem",
        "security_group_id": "sg-test123",
        "unique_id": "test123",
    }

    with (
        patch("moondock_cli.EC2Manager") as mock_ec2,
    ):
        mock_ec2_instance = MagicMock()
        mock_ec2_instance.launch_instance.return_value = mock_instance_details
        mock_ec2.return_value = mock_ec2_instance

        mock_ssh_instance = MagicMock()
        mock_ssh_instance.filter_environment_variables.return_value = {}
        mock_ssh_instance.connect.return_value = None
        mock_ssh_instance.build_command_with_env.side_effect = lambda cmd, env: cmd
        mock_ssh_instance.execute_command.return_value = 0
        moondock_instance.ssh_manager_factory = lambda **kwargs: mock_ssh_instance

        moondock_instance.run()

        assert moondock_instance._cleanup_in_progress is False
        mock_ssh_instance.close.assert_called()


def test_format_time_ago_just_now(moondock_module) -> None:
    """Test format_time_ago returns 'just now' for recent times."""
    from datetime import datetime, timezone

    from moondock.utils import format_time_ago

    dt = datetime.now(timezone.utc)
    result = format_time_ago(dt)
    assert result == "just now"


def test_format_time_ago_minutes(moondock_module) -> None:
    """Test format_time_ago returns minutes ago for times under an hour."""
    from datetime import datetime, timedelta, timezone

    from moondock.utils import format_time_ago

    dt = datetime.now(timezone.utc) - timedelta(minutes=30)
    result = format_time_ago(dt)
    assert result == "30m ago"


def test_format_time_ago_hours(moondock_module) -> None:
    """Test format_time_ago returns hours ago for times under a day."""
    from datetime import datetime, timedelta, timezone

    from moondock.utils import format_time_ago

    dt = datetime.now(timezone.utc) - timedelta(hours=2)
    result = format_time_ago(dt)
    assert result == "2h ago"


def test_format_time_ago_days(moondock_module) -> None:
    """Test format_time_ago returns days ago for times over a day."""
    from datetime import datetime, timedelta, timezone

    from moondock.utils import format_time_ago

    dt = datetime.now(timezone.utc) - timedelta(days=5)
    result = format_time_ago(dt)
    assert result == "5d ago"


def test_format_time_ago_raises_on_naive_datetime(moondock_module) -> None:
    """Test format_time_ago raises ValueError for naive datetime."""
    from datetime import datetime

    from moondock.utils import format_time_ago

    dt = datetime.now()

    with pytest.raises(ValueError, match="datetime must be timezone-aware"):
        format_time_ago(dt)


def test_list_command_all_regions(moondock_module, aws_credentials) -> None:
    """Test list command displays instances from all regions."""
    from datetime import datetime, timezone
    from io import StringIO
    from unittest.mock import MagicMock, patch

    moondock_instance = moondock_module()

    mock_ec2_manager = MagicMock()
    mock_ec2_manager.list_instances.return_value = [
        {
            "instance_id": "i-test1",
            "machine_config": "test-machine-1",
            "state": "running",
            "region": "us-east-1",
            "instance_type": "t3.medium",
            "launch_time": datetime.now(timezone.utc),
        },
        {
            "instance_id": "i-test2",
            "machine_config": "test-machine-2",
            "state": "running",
            "region": "us-west-2",
            "instance_type": "t3.large",
            "launch_time": datetime.now(timezone.utc),
        },
    ]

    captured_output = StringIO()

    with patch("sys.stdout", captured_output):
        with patch("moondock_cli.EC2Manager", return_value=mock_ec2_manager):
            moondock_instance.list()

    output = captured_output.getvalue()
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


def test_list_command_filtered_region(moondock_module, aws_credentials) -> None:
    """Test list command displays instances from specific region."""
    from datetime import datetime, timezone
    from io import StringIO
    from unittest.mock import MagicMock, patch

    moondock_instance = moondock_module()

    mock_ec2_manager = MagicMock()
    mock_ec2_manager.list_instances.return_value = [
        {
            "instance_id": "i-test1",
            "machine_config": "test-machine-1",
            "state": "running",
            "region": "us-east-1",
            "instance_type": "t3.medium",
            "launch_time": datetime.now(timezone.utc),
        }
    ]

    mock_ec2_client = MagicMock()
    mock_ec2_client.describe_regions.return_value = {
        "Regions": [
            {"RegionName": "us-east-1"},
            {"RegionName": "us-west-2"},
        ]
    }

    captured_output = StringIO()

    with patch("sys.stdout", captured_output):
        with patch("moondock_cli.EC2Manager", return_value=mock_ec2_manager):
            with patch("boto3.client", return_value=mock_ec2_client):
                moondock_instance.list(region="us-east-1")

    output = captured_output.getvalue()
    assert "Instances in us-east-1:" in output
    assert "NAME" in output
    assert "INSTANCE-ID" in output
    assert "STATUS" in output
    assert "TYPE" in output
    assert "LAUNCHED" in output
    assert "test-machine-1" in output
    assert "i-test1" in output


def test_list_command_no_instances(moondock_module, aws_credentials) -> None:
    """Test list command displays message when no instances exist."""
    from io import StringIO
    from unittest.mock import MagicMock, patch

    moondock_instance = moondock_module()

    mock_ec2_manager = MagicMock()
    mock_ec2_manager.list_instances.return_value = []

    captured_output = StringIO()

    with patch("sys.stdout", captured_output):
        with patch("moondock_cli.EC2Manager", return_value=mock_ec2_manager):
            moondock_instance.list()

    output = captured_output.getvalue()
    assert "No moondock-managed instances found" in output


def test_list_command_no_credentials(moondock_module) -> None:
    """Test list command handles missing AWS credentials."""
    from io import StringIO
    from unittest.mock import MagicMock, patch

    from botocore.exceptions import NoCredentialsError

    moondock_instance = moondock_module()

    mock_ec2_manager = MagicMock()
    mock_ec2_manager.list_instances.side_effect = NoCredentialsError()

    captured_output = StringIO()

    with patch("sys.stdout", captured_output):
        with patch("moondock_cli.EC2Manager", return_value=mock_ec2_manager):
            with pytest.raises(NoCredentialsError):
                moondock_instance.list()

    output = captured_output.getvalue()
    assert "Error: AWS credentials not found" in output


def test_list_command_permission_error(moondock_module, aws_credentials) -> None:
    """Test list command handles permission errors."""
    from io import StringIO
    from unittest.mock import MagicMock, patch

    from botocore.exceptions import ClientError

    moondock_instance = moondock_module()

    mock_ec2_manager = MagicMock()
    mock_ec2_manager.list_instances.side_effect = ClientError(
        {"Error": {"Code": "UnauthorizedOperation", "Message": "Not authorized"}},
        "DescribeInstances",
    )

    captured_output = StringIO()

    with patch("sys.stdout", captured_output):
        with patch("moondock_cli.EC2Manager", return_value=mock_ec2_manager):
            with pytest.raises(ClientError):
                moondock_instance.list()

    output = captured_output.getvalue()
    assert "Error: Insufficient AWS permissions" in output


def test_list_command_invalid_region(moondock_module, aws_credentials) -> None:
    """Test list command with invalid region parameter."""
    from unittest.mock import MagicMock

    moondock_instance = moondock_module()

    mock_ec2_client = MagicMock()
    mock_ec2_client.describe_regions.return_value = {
        "Regions": [
            {"RegionName": "us-east-1"},
            {"RegionName": "us-west-2"},
            {"RegionName": "eu-west-1"},
        ]
    }

    moondock_instance.boto3_client_factory = MagicMock(return_value=mock_ec2_client)
    with pytest.raises(
        ValueError, match="Invalid AWS region: 'invalid-region-xyz'"
    ):
        moondock_instance.list(region="invalid-region-xyz")


def test_truncate_name_short_name(moondock_module) -> None:
    """Test truncate_name returns original name when it fits."""
    moondock_instance = moondock_module()

    short_name = "short"
    result = moondock_instance._truncate_name(short_name)

    assert result == "short"


def test_truncate_name_exactly_max_width(moondock_module) -> None:
    """Test truncate_name returns original name when exactly at max width."""
    moondock_instance = moondock_module()

    exact_name = "x" * 19
    result = moondock_instance._truncate_name(exact_name)

    assert result == exact_name


def test_truncate_name_exceeds_max_width(moondock_module) -> None:
    """Test truncate_name adds ellipsis when name exceeds max width."""
    moondock_instance = moondock_module()

    long_name = "very-long-machine-config-name-that-exceeds-limit"
    result = moondock_instance._truncate_name(long_name)

    assert len(result) == 19
    assert result.endswith("...")
    assert result == "very-long-machin..."


def test_validate_region_valid(moondock_module) -> None:
    """Test validate_region accepts valid AWS region."""
    from unittest.mock import MagicMock

    moondock_instance = moondock_module()

    mock_ec2_client = MagicMock()
    mock_ec2_client.describe_regions.return_value = {
        "Regions": [
            {"RegionName": "us-east-1"},
            {"RegionName": "us-west-2"},
        ]
    }

    moondock_instance.boto3_client_factory = MagicMock(return_value=mock_ec2_client)
    moondock_instance._validate_region("us-east-1")


def test_validate_region_invalid(moondock_module) -> None:
    """Test validate_region raises ValueError for invalid region."""
    from unittest.mock import MagicMock

    moondock_instance = moondock_module()

    mock_ec2_client = MagicMock()
    mock_ec2_client.describe_regions.return_value = {
        "Regions": [
            {"RegionName": "us-east-1"},
            {"RegionName": "us-west-2"},
        ]
    }

    moondock_instance.boto3_client_factory = MagicMock(return_value=mock_ec2_client)
    with pytest.raises(ValueError, match="Invalid AWS region"):
        moondock_instance._validate_region("invalid-region")


def test_validate_region_graceful_fallback(moondock_module, caplog) -> None:
    """Test validate_region proceeds without validation on API errors."""
    from unittest.mock import MagicMock, patch

    from botocore.exceptions import ClientError

    moondock_instance = moondock_module()

    mock_ec2_client = MagicMock()
    mock_ec2_client.describe_regions.side_effect = ClientError(
        {"Error": {"Code": "UnauthorizedOperation", "Message": "Not authorized"}},
        "DescribeRegions",
    )

    with patch("boto3.client", return_value=mock_ec2_client):
        moondock_instance._validate_region("us-east-1")

    assert "Unable to validate region" in caplog.text


def test_cleanup_flag_resets_after_cleanup(moondock_module) -> None:
    """Test that cleanup_in_progress flag resets after cleanup completes."""
    from unittest.mock import MagicMock

    moondock_instance = moondock_module()

    mock_ec2 = MagicMock()
    moondock_instance._resources = {
        "ec2_manager": mock_ec2,
        "instance_details": {"instance_id": "i-test123"},
    }

    assert moondock_instance._cleanup_in_progress is False

    moondock_instance._cleanup_resources()

    assert moondock_instance._cleanup_in_progress is False
    mock_ec2.terminate_instance.assert_called_once()


def test_multiple_run_calls_work_correctly(moondock_module) -> None:
    """Test that multiple run() calls in same process work correctly.

    This test verifies that the cleanup_in_progress flag is properly reset
    between consecutive run() calls, ensuring the flag doesn't get stuck
    in True state which would prevent subsequent runs from cleaning up.

    This test ACTUALLY calls run() (not run_test_mode()) and exercises
    the real cleanup path to catch flag reset regressions.
    """
    import os
    from unittest.mock import MagicMock, patch

    moondock_instance = moondock_module()

    mock_instance_details = {
        "instance_id": "i-test123",
        "public_ip": "1.2.3.4",
        "state": "running",
        "key_file": "/tmp/test-key.pem",
        "security_group_id": "sg-test123",
        "unique_id": "test-unique-id",
    }

    cleanup_call_count = 0

    original_cleanup = moondock_instance._cleanup_resources

    def track_cleanup(signum=None, frame=None):
        nonlocal cleanup_call_count
        cleanup_call_count += 1
        return original_cleanup(signum, frame)

    with (
        patch.dict(os.environ, {"MOONDOCK_TEST_MODE": "0"}),
        patch.object(
            moondock_instance, "_cleanup_resources", side_effect=track_cleanup
        ),
    ):
        moondock_instance._config_loader = MagicMock()
        moondock_instance._config_loader.load_config.return_value = {"defaults": {}}
        moondock_instance._config_loader.get_machine_config.return_value = {
            "region": "us-east-1",
            "instance_type": "t3.medium",
        }
        moondock_instance._config_loader.validate_config.return_value = None

        with (
            patch("moondock_cli.EC2Manager") as mock_ec2_class,
            patch("moondock_cli.SSHManager") as mock_ssh_class,
        ):
            mock_ec2_instance = MagicMock()
            mock_ec2_instance.launch_instance.return_value = mock_instance_details
            mock_ec2_class.return_value = mock_ec2_instance

            mock_ssh_instance = MagicMock()
            mock_ssh_instance.filter_environment_variables.return_value = {}
            mock_ssh_instance.connect.return_value = None
            mock_ssh_instance.build_command_with_env.side_effect = lambda c, e: c
            mock_ssh_instance.execute_command.return_value = 0
            mock_ssh_class.return_value = mock_ssh_instance

            result1 = moondock_instance.run(plain=True)

            assert result1 is not None
            assert result1["instance_id"] == "i-test123"
            assert moondock_instance._cleanup_in_progress is False
            assert cleanup_call_count == 1

            result2 = moondock_instance.run(plain=True)

            assert result2 is not None
            assert result2["instance_id"] == "i-test123"
            assert moondock_instance._cleanup_in_progress is False
            assert cleanup_call_count == 2


def test_cleanup_flag_resets_even_with_cleanup_errors(moondock_module) -> None:
    """Test that cleanup_in_progress flag resets even when cleanup has errors."""
    from unittest.mock import MagicMock

    moondock_instance = moondock_module()

    mock_ec2 = MagicMock()
    mock_ec2.terminate_instance.side_effect = RuntimeError("EC2 error")

    moondock_instance._resources = {
        "ec2_manager": mock_ec2,
        "instance_details": {"instance_id": "i-test123"},
    }

    moondock_instance._cleanup_resources()

    assert moondock_instance._cleanup_in_progress is False
    mock_ec2.terminate_instance.assert_called_once()
