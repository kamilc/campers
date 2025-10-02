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
def moondock(moondock_module: Any, mock_ec2_manager: MagicMock) -> Any:
    """Create Moondock instance with mocked EC2Manager.

    Parameters
    ----------
    moondock_module : Any
        The moondock module from moondock_module fixture
    mock_ec2_manager : MagicMock
        Mocked EC2Manager from mock_ec2_manager fixture

    Returns
    -------
    Any
        Moondock instance with EC2Manager mocked
    """
    return moondock_module.Moondock()
