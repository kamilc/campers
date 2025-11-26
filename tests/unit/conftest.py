"""Pytest configuration and fixtures for campers tests."""

import importlib.util
import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch
from collections.abc import Generator

import pytest
import yaml

tests_root = Path(__file__).parent.parent
if str(tests_root) not in sys.path:
    sys.path.insert(0, str(tests_root))


@pytest.fixture(autouse=True)
def cleanup_test_mode_env() -> Generator[None, None, None]:
    """Ensure CAMPERS_TEST_MODE is not set for unit tests.

    Yields
    ------
    None
        Control back to test after ensuring clean environment

    Notes
    -----
    This fixture cleans up CAMPERS_TEST_MODE environment variable that may
    have been set by integration tests or harness tests, ensuring unit tests
    run with a clean environment.
    """
    original_test_mode = os.environ.pop("CAMPERS_TEST_MODE", None)

    yield

    if original_test_mode is not None:
        os.environ["CAMPERS_TEST_MODE"] = original_test_mode
    else:
        os.environ.pop("CAMPERS_TEST_MODE", None)


@pytest.fixture(scope="session")
def campers_module() -> Any:
    """Load campers package as a module.

    Returns
    -------
    Any
        The campers module with Campers class available.
    """
    campers_script_path = (
        Path(__file__).parent.parent.parent / "campers" / "__main__.py"
    )
    spec = importlib.util.spec_from_file_location(
        "campers_script", campers_script_path
    )
    campers_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(campers_module)

    return campers_module


@pytest.fixture
def aws_credentials() -> Generator[None, None, None]:
    """Fixture to set AWS credentials for testing with proper cleanup.

    Sets mock AWS credentials in environment variables for the duration of the test,
    then restores the original environment state.

    Yields
    ------
    None
        Control back to test after setting credentials
    """
    old_access_key = os.environ.get("AWS_ACCESS_KEY_ID")
    old_secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY")
    old_region = os.environ.get("AWS_DEFAULT_REGION")

    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"

    yield

    if old_access_key is not None:
        os.environ["AWS_ACCESS_KEY_ID"] = old_access_key
    else:
        os.environ.pop("AWS_ACCESS_KEY_ID", None)

    if old_secret_key is not None:
        os.environ["AWS_SECRET_ACCESS_KEY"] = old_secret_key
    else:
        os.environ.pop("AWS_SECRET_ACCESS_KEY", None)

    if old_region is not None:
        os.environ["AWS_DEFAULT_REGION"] = old_region
    else:
        os.environ.pop("AWS_DEFAULT_REGION", None)


@pytest.fixture
def config_file(tmp_path: Path) -> Generator[Path, None, None]:
    """Create a temporary config file path and clean up environment.

    Parameters
    ----------
    tmp_path : Path
        Pytest temporary directory path

    Yields
    ------
    Path
        Path to temporary config file
    """
    config_path = tmp_path / "campers.yaml"

    original_env = os.environ.get("CAMPERS_CONFIG")
    os.environ["CAMPERS_CONFIG"] = str(config_path)

    yield config_path

    if original_env is not None:
        os.environ["CAMPERS_CONFIG"] = original_env
    elif "CAMPERS_CONFIG" in os.environ:
        del os.environ["CAMPERS_CONFIG"]


@pytest.fixture
def write_config(config_file: Path):
    """Helper fixture to write config data to file.

    Parameters
    ----------
    config_file : Path
        Path to config file from config_file fixture

    Returns
    -------
    callable
        Function that takes config_data dict and writes to file
    """

    def _write(config_data: dict[str, Any]) -> None:
        with open(config_file, "w") as f:
            yaml.dump(config_data, f)

    return _write


@pytest.fixture
def mock_ec2_manager(campers_module):
    """Mock EC2Manager for CLI tests.

    Parameters
    ----------
    campers_module : Any
        The campers module from campers_module fixture

    Returns
    -------
    MagicMock
        Mock EC2Manager with launch_instance returning test instance details
    """
    campers_dir = os.environ.get("CAMPERS_DIR", str(Path.home() / ".campers"))
    mock_instance_details = {
        "instance_id": "i-1234567890abcdef0",
        "public_ip": "1.2.3.4",
        "state": "running",
        "key_file": str(Path(campers_dir) / "keys" / "1234567890.pem"),
        "security_group_id": "sg-1234567890abcdef0",
        "unique_id": "1234567890",
    }

    with patch.object(campers_module, "EC2Manager") as MockEC2Manager:
        mock_manager = MagicMock()
        mock_manager.launch_instance.return_value = mock_instance_details
        MockEC2Manager.return_value = mock_manager
        yield mock_manager


@pytest.fixture
def mock_ssh_manager(campers_module):
    """Mock SSHManager for CLI tests.

    Parameters
    ----------
    campers_module : Any
        The campers module from campers_module fixture

    Returns
    -------
    MagicMock
        Mock SSHManager with connect and execute_command methods
    """
    with patch.object(campers_module, "SSHManager") as MockSSHManager:
        mock_manager = MagicMock()
        mock_manager.connect.return_value = None
        mock_manager.execute_command.return_value = 0
        mock_manager.execute_command_raw.return_value = 0
        mock_manager.close.return_value = None
        MockSSHManager.return_value = mock_manager
        yield mock_manager


@pytest.fixture
def mock_mutagen_manager(campers_module):
    """Mock MutagenManager for CLI tests.

    Parameters
    ----------
    campers_module : Any
        The campers module from campers_module fixture

    Returns
    -------
    MagicMock
        Mock MutagenManager with all Mutagen sync methods
    """
    with patch.object(campers_module, "MutagenManager") as MockMutagenManager:
        mock_manager = MagicMock()
        mock_manager.check_mutagen_installed.return_value = None
        mock_manager.cleanup_orphaned_session.return_value = None
        mock_manager.create_sync_session.return_value = None
        mock_manager.wait_for_initial_sync.return_value = None
        mock_manager.terminate_session.return_value = None
        MockMutagenManager.return_value = mock_manager
        yield mock_manager


@pytest.fixture
def mock_portforward_manager(campers_module):
    """Mock PortForwardManager for CLI tests.

    Parameters
    ----------
    campers_module : Any
        The campers module from campers_module fixture

    Returns
    -------
    MagicMock
        Mock PortForwardManager with all port forwarding methods
    """
    with patch.object(campers_module, "PortForwardManager") as MockPortForwardManager:
        mock_manager = MagicMock()
        mock_manager.create_tunnel.return_value = None
        mock_manager.create_tunnels.return_value = None
        mock_manager.stop_all_tunnels.return_value = None
        MockPortForwardManager.return_value = mock_manager
        yield mock_manager


@pytest.fixture
def campers(
    campers_module: Any,
    mock_ec2_manager: MagicMock,
    mock_ssh_manager: MagicMock,
    mock_mutagen_manager: MagicMock,
    mock_portforward_manager: MagicMock,
) -> Any:
    """Create Campers instance with all managers mocked.

    Parameters
    ----------
    campers_module : Any
        The campers module from campers_module fixture
    mock_ec2_manager : MagicMock
        Mocked EC2Manager from mock_ec2_manager fixture
    mock_ssh_manager : MagicMock
        Mocked SSHManager from mock_ssh_manager fixture
    mock_mutagen_manager : MagicMock
        Mocked MutagenManager from mock_mutagen_manager fixture
    mock_portforward_manager : MagicMock
        Mocked PortForwardManager from mock_portforward_manager fixture

    Returns
    -------
    Any
        Campers instance with all managers mocked
    """
    return campers_module.Campers()
