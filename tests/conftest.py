"""Pytest configuration and fixtures for moondock tests."""

import importlib.util
import os
from pathlib import Path
from typing import Any, Generator

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
def moondock(moondock_module: Any) -> Any:
    """Create Moondock instance.

    Parameters
    ----------
    moondock_module : Any
        The moondock module from moondock_module fixture

    Returns
    -------
    Any
        Moondock instance
    """
    return moondock_module.Moondock()
