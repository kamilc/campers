"""Behave environment configuration for moondock tests."""

import os
from pathlib import Path


def before_all(context) -> None:
    """Setup executed before all tests."""
    project_root = Path(__file__).parent.parent
    tmp_dir = project_root / "tmp" / "test-artifacts"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    context.project_root = project_root
    context.tmp_dir = tmp_dir


def after_scenario(context, scenario) -> None:
    """Cleanup executed after each scenario.

    Parameters
    ----------
    context : behave.runner.Context
        The Behave context object.
    scenario : behave.model.Scenario
        The scenario that just finished.
    """
    if hasattr(context, "temp_config_file"):
        if os.path.exists(context.temp_config_file):
            os.unlink(context.temp_config_file)

    if hasattr(context, "env_config_file"):
        if os.path.exists(context.env_config_file):
            os.unlink(context.env_config_file)

    if "MOONDOCK_CONFIG" in os.environ:
        del os.environ["MOONDOCK_CONFIG"]


def after_all(context) -> None:
    """Cleanup executed after all tests.

    Currently no cleanup is required for skeleton tests as no persistent
    resources are created. Future implementations may need to clean up:
    - AWS resources (EC2 instances, security groups, key pairs)
    - Temporary SSH keys
    - Test artifacts beyond tmp/ directory

    Parameters
    ----------
    context : behave.runner.Context
        The Behave context object.

    """
    pass
