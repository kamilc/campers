"""Behave environment configuration for moondock tests."""

import os
from pathlib import Path

from moto import mock_aws


def before_all(context) -> None:
    """Setup executed before all tests."""
    project_root = Path(__file__).parent.parent
    tmp_dir = project_root / "tmp" / "test-artifacts"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    context.project_root = project_root
    context.tmp_dir = tmp_dir

    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
    os.environ["MOONDOCK_TEST_MODE"] = "1"


def before_scenario(context, scenario) -> None:
    """Setup executed before each scenario."""
    import boto3

    if hasattr(context, "mock_aws_env") and context.mock_aws_env:
        try:
            context.mock_aws_env.stop()
        except RuntimeError:
            pass

    context.mock_aws_env = mock_aws()
    context.mock_aws_env.start()

    if "AMI not found" not in scenario.name:
        ec2_client = boto3.client("ec2", region_name="us-east-1")

        ec2_client.register_image(
            Name="ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-20231201",
            Description="Ubuntu 22.04 LTS",
            Architecture="x86_64",
            RootDeviceName="/dev/sda1",
            VirtualizationType="hvm",
        )

        original_describe_images = ec2_client.describe_images

        def mock_describe_images(**kwargs):
            response = original_describe_images(**kwargs)

            for image in response.get("Images", []):
                image["OwnerId"] = "099720109477"

            return response

        ec2_client.describe_images = mock_describe_images
        context.patched_ec2_client = ec2_client


def after_scenario(context, scenario) -> None:
    """Cleanup executed after each scenario.

    Parameters
    ----------
    context : behave.runner.Context
        The Behave context object.
    scenario : behave.model.Scenario
        The scenario that just finished.
    """
    if hasattr(context, "mock_aws_env") and context.mock_aws_env:
        try:
            context.mock_aws_env.stop()
        except RuntimeError:
            pass

    if hasattr(context, "cleanup_key_file"):
        if context.cleanup_key_file.exists():
            context.cleanup_key_file.unlink()

    if hasattr(context, "key_file"):
        if context.key_file.exists():
            context.key_file.unlink()

    keys_dir = Path.home() / ".moondock" / "keys"

    if keys_dir.exists() and not list(keys_dir.iterdir()):
        keys_dir.rmdir()

        if keys_dir.parent.exists() and not list(keys_dir.parent.iterdir()):
            keys_dir.parent.rmdir()

    if hasattr(context, "aws_keys_backup"):
        for key, value in context.aws_keys_backup.items():
            if value is not None:
                os.environ[key] = value

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

    Parameters
    ----------
    context : behave.runner.Context
        The Behave context object.

    """
    if hasattr(context, "mock_aws_env") and context.mock_aws_env:
        try:
            context.mock_aws_env.stop()
        except RuntimeError:
            pass

    for key in [
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_DEFAULT_REGION",
        "MOONDOCK_TEST_MODE",
    ]:
        if key in os.environ:
            del os.environ[key]
