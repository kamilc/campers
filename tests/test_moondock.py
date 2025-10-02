"""Tests for moondock CLI skeleton.

This module contains unit tests for the moondock CLI application, specifically
testing the skeleton implementation including class instantiation, method
functionality, and command-line execution.

Tests
-----
test_moondock_class_exists
    Verifies that the Moondock class can be imported and instantiated.
test_hello_method_returns_correct_string
    Validates the hello method returns the correct version string.
test_hello_command_via_uv_run
    Tests end-to-end CLI execution using uv run.

"""

import subprocess
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
    moondock_script = project_root / "moondock.py"

    spec = importlib.util.spec_from_file_location("moondock_cli", moondock_script)
    module = importlib.util.module_from_spec(spec)
    sys.modules["moondock_cli"] = module
    spec.loader.exec_module(module)

    yield module.Moondock


def test_moondock_class_exists(moondock_module) -> None:
    """Test that Moondock class can be imported and instantiated."""
    moondock_instance = moondock_module()

    assert moondock_instance is not None
    assert hasattr(moondock_instance, "hello")


def test_hello_method_returns_correct_string(moondock_module) -> None:
    """Test that hello method returns expected version string."""
    moondock_instance = moondock_module()
    result = moondock_instance.hello()

    assert result == "moondock v0.1.0 - skeleton ready"
    assert isinstance(result, str)


def test_hello_command_via_uv_run() -> None:
    """Test that hello command works via uv run execution."""
    project_root = Path(__file__).parent.parent
    moondock_path = project_root / "moondock.py"

    result = subprocess.run(
        ["uv", "run", str(moondock_path), "hello"],
        cwd=project_root,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, f"Command failed: {result.stderr}"
    assert "moondock v0.1.0 - skeleton ready" in result.stdout


def test_run_test_mode_with_setup_script(moondock_module) -> None:
    """Test that test mode handles setup_script execution."""
    import os
    from unittest.mock import patch

    moondock_instance = moondock_module()

    merged_config = {
        "region": "us-east-1",
        "instance_type": "t3.medium",
        "setup_script": "sudo apt update",
        "command": "echo hello",
    }

    with patch.dict(os.environ, {"MOONDOCK_TEST_MODE": "1"}):
        result = moondock_instance.run_test_mode(merged_config, json_output=False)

    assert result is not None
    assert result["instance_id"] == "i-mock123"
    assert result["public_ip"] == "203.0.113.1"


def test_run_test_mode_setup_script_without_command(moondock_module) -> None:
    """Test that test mode handles setup_script without command."""
    import os
    from unittest.mock import patch

    moondock_instance = moondock_module()

    merged_config = {
        "region": "us-east-1",
        "instance_type": "t3.medium",
        "setup_script": "sudo apt update",
    }

    with patch.dict(os.environ, {"MOONDOCK_TEST_MODE": "1"}):
        result = moondock_instance.run_test_mode(merged_config, json_output=False)

    assert result is not None
    assert result["instance_id"] == "i-mock123"


def test_run_test_mode_no_ssh_operations(moondock_module) -> None:
    """Test that test mode skips SSH when no setup_script or command."""
    import os
    from unittest.mock import patch

    moondock_instance = moondock_module()

    merged_config = {
        "region": "us-east-1",
        "instance_type": "t3.medium",
    }

    with patch.dict(os.environ, {"MOONDOCK_TEST_MODE": "1"}):
        result = moondock_instance.run_test_mode(merged_config, json_output=False)

    assert result is not None
    assert result["instance_id"] == "i-mock123"
    assert "command_exit_code" not in result


def test_run_executes_setup_script_before_command(moondock_module) -> None:
    """Test that run() executes setup_script before command."""
    from unittest.mock import MagicMock, patch

    moondock_instance = moondock_module()
    moondock_instance.config_loader = MagicMock()
    moondock_instance.config_loader.load_config.return_value = {"defaults": {}}
    moondock_instance.config_loader.get_machine_config.return_value = {
        "region": "us-east-1",
        "instance_type": "t3.medium",
        "setup_script": "echo setup",
        "command": "echo command",
    }
    moondock_instance.config_loader.validate_config.return_value = None

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
        patch("moondock_cli.SSHManager") as mock_ssh,
    ):
        mock_ec2_instance = MagicMock()
        mock_ec2_instance.launch_instance.return_value = mock_instance_details
        mock_ec2.return_value = mock_ec2_instance

        mock_ssh_instance = MagicMock()

        def track_execute_command(cmd: str) -> int:
            execution_order.append(cmd)
            return 0

        mock_ssh_instance.execute_command.side_effect = track_execute_command
        mock_ssh.return_value = mock_ssh_instance

        result = moondock_instance.run()

    assert len(execution_order) == 2
    assert execution_order[0] == "echo setup"
    assert execution_order[1] == "echo command"
    assert result["instance_id"] == "i-test123"


def test_run_setup_script_failure_prevents_command(moondock_module) -> None:
    """Test that setup_script failure prevents command execution."""
    from unittest.mock import MagicMock, patch

    moondock_instance = moondock_module()
    moondock_instance.config_loader = MagicMock()
    moondock_instance.config_loader.load_config.return_value = {"defaults": {}}
    moondock_instance.config_loader.get_machine_config.return_value = {
        "region": "us-east-1",
        "instance_type": "t3.medium",
        "setup_script": "exit 1",
        "command": "echo command",
    }
    moondock_instance.config_loader.validate_config.return_value = None

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
        patch("moondock_cli.SSHManager") as mock_ssh,
    ):
        mock_ec2_instance = MagicMock()
        mock_ec2_instance.launch_instance.return_value = mock_instance_details
        mock_ec2.return_value = mock_ec2_instance

        mock_ssh_instance = MagicMock()
        mock_ssh_instance.execute_command.return_value = 1
        mock_ssh.return_value = mock_ssh_instance

        with pytest.raises(RuntimeError, match="Setup script failed with exit code: 1"):
            moondock_instance.run()

        assert mock_ssh_instance.execute_command.call_count == 1
        mock_ssh_instance.close.assert_called_once()


def test_run_skips_ssh_when_no_setup_script_or_command(moondock_module) -> None:
    """Test that run() skips SSH when no setup_script or command."""
    from unittest.mock import MagicMock, patch

    moondock_instance = moondock_module()
    moondock_instance.config_loader = MagicMock()
    moondock_instance.config_loader.load_config.return_value = {"defaults": {}}
    moondock_instance.config_loader.get_machine_config.return_value = {
        "region": "us-east-1",
        "instance_type": "t3.medium",
    }
    moondock_instance.config_loader.validate_config.return_value = None

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
        patch("moondock_cli.SSHManager") as mock_ssh,
    ):
        mock_ec2_instance = MagicMock()
        mock_ec2_instance.launch_instance.return_value = mock_instance_details
        mock_ec2.return_value = mock_ec2_instance

        result = moondock_instance.run()

        mock_ssh.assert_not_called()
        assert result["instance_id"] == "i-test123"


def test_run_only_setup_script_no_command(moondock_module) -> None:
    """Test that run() executes setup_script without command."""
    from unittest.mock import MagicMock, patch

    moondock_instance = moondock_module()
    moondock_instance.config_loader = MagicMock()
    moondock_instance.config_loader.load_config.return_value = {"defaults": {}}
    moondock_instance.config_loader.get_machine_config.return_value = {
        "region": "us-east-1",
        "instance_type": "t3.medium",
        "setup_script": "sudo apt update",
    }
    moondock_instance.config_loader.validate_config.return_value = None

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
        patch("moondock_cli.SSHManager") as mock_ssh,
    ):
        mock_ec2_instance = MagicMock()
        mock_ec2_instance.launch_instance.return_value = mock_instance_details
        mock_ec2.return_value = mock_ec2_instance

        mock_ssh_instance = MagicMock()
        mock_ssh_instance.execute_command.return_value = 0
        mock_ssh.return_value = mock_ssh_instance

        result = moondock_instance.run()

        mock_ssh_instance.execute_command.assert_called_once_with("sudo apt update")
        mock_ssh_instance.close.assert_called_once()
        assert result["instance_id"] == "i-test123"


def test_run_startup_script_without_sync_paths_raises_error(moondock_module) -> None:
    """Test that startup_script without sync_paths raises ValueError."""
    from unittest.mock import MagicMock

    moondock_instance = moondock_module()
    moondock_instance.config_loader = MagicMock()
    moondock_instance.config_loader.load_config.return_value = {"defaults": {}}
    moondock_instance.config_loader.get_machine_config.return_value = {
        "region": "us-east-1",
        "instance_type": "t3.medium",
        "startup_script": "source .venv/bin/activate",
    }
    moondock_instance.config_loader.validate_config.return_value = None

    with pytest.raises(
        ValueError, match="startup_script is defined but no sync_paths configured"
    ):
        moondock_instance.run()


def test_run_with_sync_paths_creates_mutagen_session(moondock_module) -> None:
    """Test that run() creates Mutagen session when sync_paths configured."""
    from unittest.mock import MagicMock, patch

    moondock_instance = moondock_module()
    moondock_instance.config_loader = MagicMock()
    moondock_instance.config_loader.load_config.return_value = {"defaults": {}}
    moondock_instance.config_loader.get_machine_config.return_value = {
        "region": "us-east-1",
        "instance_type": "t3.medium",
        "sync_paths": [{"local": "~/myproject", "remote": "~/myproject"}],
        "command": "echo test",
    }
    moondock_instance.config_loader.validate_config.return_value = None

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
        patch("moondock_cli.SSHManager") as mock_ssh,
        patch("moondock_cli.MutagenManager") as mock_mutagen,
    ):
        mock_ec2_instance = MagicMock()
        mock_ec2_instance.launch_instance.return_value = mock_instance_details
        mock_ec2.return_value = mock_ec2_instance

        mock_ssh_instance = MagicMock()
        mock_ssh_instance.execute_command_raw.return_value = 0
        mock_ssh.return_value = mock_ssh_instance

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
    moondock_instance.config_loader = MagicMock()
    moondock_instance.config_loader.load_config.return_value = {"defaults": {}}
    moondock_instance.config_loader.get_machine_config.return_value = {
        "region": "us-east-1",
        "instance_type": "t3.medium",
        "sync_paths": [{"local": "~/myproject", "remote": "~/myproject"}],
        "command": "pwd",
    }
    moondock_instance.config_loader.validate_config.return_value = None

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
        patch("moondock_cli.SSHManager") as mock_ssh,
        patch("moondock_cli.MutagenManager") as mock_mutagen,
    ):
        mock_ec2_instance = MagicMock()
        mock_ec2_instance.launch_instance.return_value = mock_instance_details
        mock_ec2.return_value = mock_ec2_instance

        mock_ssh_instance = MagicMock()
        mock_ssh_instance.execute_command_raw.return_value = 0
        mock_ssh.return_value = mock_ssh_instance

        mock_mutagen_instance = MagicMock()
        mock_mutagen.return_value = mock_mutagen_instance

        result = moondock_instance.run()

        mock_ssh_instance.execute_command_raw.assert_called_once()
        call_args = mock_ssh_instance.execute_command_raw.call_args[0][0]
        assert "cd '~/myproject'" in call_args
        assert "pwd" in call_args
        assert result["instance_id"] == "i-test123"


def test_run_executes_startup_script_from_synced_directory(moondock_module) -> None:
    """Test that startup_script executes from synced directory."""
    from unittest.mock import MagicMock, patch

    moondock_instance = moondock_module()
    moondock_instance.config_loader = MagicMock()
    moondock_instance.config_loader.load_config.return_value = {"defaults": {}}
    moondock_instance.config_loader.get_machine_config.return_value = {
        "region": "us-east-1",
        "instance_type": "t3.medium",
        "sync_paths": [{"local": "~/myproject", "remote": "~/myproject"}],
        "startup_script": "source .venv/bin/activate",
        "command": "python app.py",
    }
    moondock_instance.config_loader.validate_config.return_value = None

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
        patch("moondock_cli.SSHManager") as mock_ssh,
        patch("moondock_cli.MutagenManager") as mock_mutagen,
    ):
        mock_ec2_instance = MagicMock()
        mock_ec2_instance.launch_instance.return_value = mock_instance_details
        mock_ec2.return_value = mock_ec2_instance

        mock_ssh_instance = MagicMock()
        mock_ssh_instance.execute_command_raw.return_value = 0
        mock_ssh.return_value = mock_ssh_instance

        mock_mutagen_instance = MagicMock()
        mock_mutagen.return_value = mock_mutagen_instance

        result = moondock_instance.run()

        assert mock_ssh_instance.execute_command_raw.call_count == 2
        startup_call = mock_ssh_instance.execute_command_raw.call_args_list[0][0][0]
        assert "cd '~/myproject'" in startup_call
        assert "source .venv/bin/activate" in startup_call
        assert result["instance_id"] == "i-test123"


def test_test_mode_bypasses_mutagen_check_with_sync_paths(moondock_module) -> None:
    """Test that test mode skips mutagen installation check even with sync_paths."""
    import os
    from unittest.mock import MagicMock, patch

    moondock_instance = moondock_module()
    moondock_instance.config_loader = MagicMock()
    moondock_instance.config_loader.load_config.return_value = {"defaults": {}}
    moondock_instance.config_loader.get_machine_config.return_value = {
        "region": "us-east-1",
        "instance_type": "t3.medium",
        "sync_paths": [{"local": "~/myproject", "remote": "~/myproject"}],
        "command": "echo test",
    }
    moondock_instance.config_loader.validate_config.return_value = None

    with patch.dict(os.environ, {"MOONDOCK_TEST_MODE": "1"}):
        with patch("moondock_cli.MutagenManager") as mock_mutagen:
            mock_mutagen_instance = MagicMock()
            mock_mutagen.return_value = mock_mutagen_instance

            result = moondock_instance.run()

            mock_mutagen_instance.check_mutagen_installed.assert_not_called()

            assert result is not None
            assert result["instance_id"] == "i-mock123"
            assert result["public_ip"] == "203.0.113.1"


def test_build_command_in_directory(moondock_module) -> None:
    """Test build_command_in_directory creates proper command string."""
    moondock_instance = moondock_module()

    result = moondock_instance.build_command_in_directory(
        "~/myproject", "python app.py"
    )

    assert result == "cd '~/myproject' && bash -c 'python app.py'"


def test_build_command_in_directory_with_special_chars(moondock_module) -> None:
    """Test build_command_in_directory handles special characters."""
    moondock_instance = moondock_module()

    result = moondock_instance.build_command_in_directory(
        "~/my project", "echo 'hello world'"
    )

    assert "cd '~/my project'" in result
    assert "bash -c" in result


def test_build_command_in_directory_with_multiline_script(moondock_module) -> None:
    """Test build_command_in_directory handles multiline scripts."""
    moondock_instance = moondock_module()

    multiline_script = """source .venv/bin/activate
export DEBUG=1
python app.py"""

    result = moondock_instance.build_command_in_directory("~/app", multiline_script)

    assert result == f"cd '~/app' && bash -c {repr(multiline_script)}"
    assert "source .venv/bin/activate" in result


def test_run_startup_script_failure_prevents_command(moondock_module) -> None:
    """Test that startup_script failure prevents command execution."""
    from unittest.mock import MagicMock, patch

    moondock_instance = moondock_module()
    moondock_instance.config_loader = MagicMock()
    moondock_instance.config_loader.load_config.return_value = {"defaults": {}}
    moondock_instance.config_loader.get_machine_config.return_value = {
        "region": "us-east-1",
        "instance_type": "t3.medium",
        "sync_paths": [{"local": "~/myproject", "remote": "~/myproject"}],
        "startup_script": "exit 42",
        "command": "echo hello",
    }
    moondock_instance.config_loader.validate_config.return_value = None

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
        patch("moondock_cli.SSHManager") as mock_ssh,
        patch("moondock_cli.MutagenManager") as mock_mutagen,
    ):
        mock_ec2_instance = MagicMock()
        mock_ec2_instance.launch_instance.return_value = mock_instance_details
        mock_ec2.return_value = mock_ec2_instance

        mock_ssh_instance = MagicMock()
        mock_ssh_instance.execute_command_raw.return_value = 42
        mock_ssh.return_value = mock_ssh_instance

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
    moondock_instance.config_loader = MagicMock()
    moondock_instance.config_loader.load_config.return_value = {"defaults": {}}

    multiline_script = """source .venv/bin/activate
export DEBUG=1
cd src"""

    moondock_instance.config_loader.get_machine_config.return_value = {
        "region": "us-east-1",
        "instance_type": "t3.medium",
        "sync_paths": [{"local": "~/myproject", "remote": "~/myproject"}],
        "startup_script": multiline_script,
        "command": "pwd",
    }
    moondock_instance.config_loader.validate_config.return_value = None

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
        patch("moondock_cli.SSHManager") as mock_ssh,
        patch("moondock_cli.MutagenManager") as mock_mutagen,
    ):
        mock_ec2_instance = MagicMock()
        mock_ec2_instance.launch_instance.return_value = mock_instance_details
        mock_ec2.return_value = mock_ec2_instance

        mock_ssh_instance = MagicMock()
        mock_ssh_instance.execute_command_raw.return_value = 0
        mock_ssh.return_value = mock_ssh_instance

        mock_mutagen_instance = MagicMock()
        mock_mutagen.return_value = mock_mutagen_instance

        result = moondock_instance.run()

        startup_call = mock_ssh_instance.execute_command_raw.call_args_list[0][0][0]
        assert "source .venv/bin/activate" in startup_call
        assert "export DEBUG=1" in startup_call
        assert "cd src" in startup_call
        assert result["instance_id"] == "i-test123"


def test_run_test_mode_with_startup_script_failure(moondock_module) -> None:
    """Test that test mode simulates startup_script failure."""
    import os
    from unittest.mock import patch

    moondock_instance = moondock_module()

    merged_config = {
        "region": "us-east-1",
        "instance_type": "t3.medium",
        "sync_paths": [{"local": "~/myproject", "remote": "~/myproject"}],
        "startup_script": "exit 42",
        "command": "echo hello",
    }

    with patch.dict(os.environ, {"MOONDOCK_TEST_MODE": "1"}):
        with pytest.raises(
            RuntimeError, match="Startup script failed with exit code: 42"
        ):
            moondock_instance.run_test_mode(merged_config, json_output=False)


def test_run_test_mode_with_startup_script_success(moondock_module) -> None:
    """Test that test mode simulates startup_script success."""
    import os
    from unittest.mock import patch

    moondock_instance = moondock_module()

    merged_config = {
        "region": "us-east-1",
        "instance_type": "t3.medium",
        "sync_paths": [{"local": "~/myproject", "remote": "~/myproject"}],
        "startup_script": "source .venv/bin/activate",
        "command": "python --version",
    }

    with patch.dict(os.environ, {"MOONDOCK_TEST_MODE": "1"}):
        result = moondock_instance.run_test_mode(merged_config, json_output=False)

    assert result is not None
    assert result["instance_id"] == "i-mock123"
