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
