"""Pytest configuration and fixtures for moondock tests."""

import importlib.util
import os
from pathlib import Path
from typing import Any, Generator
from unittest.mock import MagicMock, patch

import pytest
import yaml


@pytest.fixture(scope="session")
def moondock_module() -> Any:
    """Load moondock.py as a module.

    Returns
    -------
    Any
        The moondock module with Moondock class available.
    """
    moondock_script_path = Path(__file__).parent.parent / "moondock.py"
    spec = importlib.util.spec_from_file_location(
        "moondock_script", moondock_script_path
    )
    moondock_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(moondock_module)

    return moondock_module


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
    config_path = tmp_path / "moondock.yaml"

    original_env = os.environ.get("MOONDOCK_CONFIG")
    os.environ["MOONDOCK_CONFIG"] = str(config_path)

    yield config_path

    if original_env is not None:
        os.environ["MOONDOCK_CONFIG"] = original_env
    elif "MOONDOCK_CONFIG" in os.environ:
        del os.environ["MOONDOCK_CONFIG"]


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
def mock_ec2_manager(moondock_module):
    """Mock EC2Manager for CLI tests.

    Parameters
    ----------
    moondock_module : Any
        The moondock module from moondock_module fixture

    Returns
    -------
    MagicMock
        Mock EC2Manager with launch_instance returning test instance details
    """
    moondock_dir = os.environ.get("MOONDOCK_DIR", str(Path.home() / ".moondock"))
    mock_instance_details = {
        "instance_id": "i-1234567890abcdef0",
        "public_ip": "1.2.3.4",
        "state": "running",
        "key_file": str(Path(moondock_dir) / "keys" / "1234567890.pem"),
        "security_group_id": "sg-1234567890abcdef0",
        "unique_id": "1234567890",
    }

    with patch.object(moondock_module, "EC2Manager") as MockEC2Manager:
        mock_manager = MagicMock()
        mock_manager.launch_instance.return_value = mock_instance_details
        MockEC2Manager.return_value = mock_manager
        yield mock_manager


@pytest.fixture
def mock_ssh_manager(moondock_module):
    """Mock SSHManager for CLI tests.

    Parameters
    ----------
    moondock_module : Any
        The moondock module from moondock_module fixture

    Returns
    -------
    MagicMock
        Mock SSHManager with connect and execute_command methods
    """
    with patch.object(moondock_module, "SSHManager") as MockSSHManager:
        mock_manager = MagicMock()
        mock_manager.connect.return_value = None
        mock_manager.execute_command.return_value = 0
        mock_manager.execute_command_raw.return_value = 0
        mock_manager.close.return_value = None
        MockSSHManager.return_value = mock_manager
        yield mock_manager


@pytest.fixture
def mock_mutagen_manager(moondock_module):
    """Mock MutagenManager for CLI tests.

    Parameters
    ----------
    moondock_module : Any
        The moondock module from moondock_module fixture

    Returns
    -------
    MagicMock
        Mock MutagenManager with all Mutagen sync methods
    """
    with patch.object(moondock_module, "MutagenManager") as MockMutagenManager:
        mock_manager = MagicMock()
        mock_manager.check_mutagen_installed.return_value = None
        mock_manager.cleanup_orphaned_session.return_value = None
        mock_manager.create_sync_session.return_value = None
        mock_manager.wait_for_initial_sync.return_value = None
        mock_manager.terminate_session.return_value = None
        MockMutagenManager.return_value = mock_manager
        yield mock_manager


@pytest.fixture
def mock_portforward_manager(moondock_module):
    """Mock PortForwardManager for CLI tests.

    Parameters
    ----------
    moondock_module : Any
        The moondock module from moondock_module fixture

    Returns
    -------
    MagicMock
        Mock PortForwardManager with all port forwarding methods
    """
    with patch.object(moondock_module, "PortForwardManager") as MockPortForwardManager:
        mock_manager = MagicMock()
        mock_manager.create_tunnel.return_value = None
        mock_manager.create_tunnels.return_value = None
        mock_manager.stop_all_tunnels.return_value = None
        MockPortForwardManager.return_value = mock_manager
        yield mock_manager


@pytest.fixture
def moondock(
    moondock_module: Any,
    mock_ec2_manager: MagicMock,
    mock_ssh_manager: MagicMock,
    mock_mutagen_manager: MagicMock,
    mock_portforward_manager: MagicMock,
) -> Any:
    """Create Moondock instance with all managers mocked.

    Parameters
    ----------
    moondock_module : Any
        The moondock module from moondock_module fixture
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
        Moondock instance with all managers mocked
    """
    return moondock_module.Moondock()
