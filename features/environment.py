"""Behave environment configuration for moondock tests."""

import logging
import os
from pathlib import Path

from behave.model import Scenario
from behave.runner import Context
from moto import mock_aws

logger = logging.getLogger(__name__)


def before_all(context: Context) -> None:
    """Setup executed before all tests."""
    project_root = Path(__file__).parent.parent
    tmp_dir = project_root / "tmp" / "test-artifacts"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    moondock_dir = project_root / "tmp" / "test-moondock"
    moondock_dir.mkdir(parents=True, exist_ok=True)

    keys_dir = moondock_dir / "keys"

    if keys_dir.exists():
        for pem_file in keys_dir.glob("*.pem"):
            try:
                pem_file.unlink()
                logger.debug(f"Cleaned up old key file: {pem_file}")
            except OSError as e:
                logger.warning(f"Failed to clean up {pem_file}: {e}")

    context.project_root = project_root
    context.tmp_dir = tmp_dir

    os.environ["MOONDOCK_DIR"] = str(moondock_dir)
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
    os.environ["MOONDOCK_TEST_MODE"] = "1"


def before_scenario(context: Context, scenario: Scenario) -> None:
    """Setup executed before each scenario.

    Parameters
    ----------
    context : Context
        The Behave context object.
    scenario : Scenario
        The scenario about to run.
    """
    import boto3

    if hasattr(context, "mock_aws_env") and context.mock_aws_env:
        try:
            context.mock_aws_env.stop()
        except (RuntimeError, Exception):
            pass

    if "no_credentials" not in scenario.tags:
        context.mock_aws_env = mock_aws()
        context.mock_aws_env.start()
        os.environ["AWS_ACCESS_KEY_ID"] = "testing"
        os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
        os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
    else:
        context.mock_aws_env = None

    context.ec2_config = None
    context._config = None
    context.instance_details = None
    context.exception = None
    context.unique_id = None
    context.security_group_id = None
    context.instance_id = None
    context.key_file = None
    context.cleanup_key_file = None
    context.ec2_client = None
    context.ec2_manager = None
    context.instance = None

    if "no_credentials" not in scenario.tags:
        ec2_client = boto3.client("ec2", region_name="us-east-1")

        try:
            security_groups = ec2_client.describe_security_groups(
                Filters=[{"Name": "group-name", "Values": ["moondock-*"]}]
            )

            for sg in security_groups.get("SecurityGroups", []):
                if sg["GroupName"].startswith("moondock-"):
                    try:
                        ec2_client.delete_security_group(GroupId=sg["GroupId"])
                        logger.debug(f"Cleaned up security group: {sg['GroupName']}")
                    except Exception as e:
                        logger.debug(
                            f"Could not delete security group {sg['GroupName']}: {e}"
                        )
        except Exception as e:
            logger.debug(f"Error during security group cleanup: {e}")

        try:
            key_pairs = ec2_client.describe_key_pairs()

            for kp in key_pairs.get("KeyPairs", []):
                if kp["KeyName"].startswith("moondock-"):
                    try:
                        ec2_client.delete_key_pair(KeyName=kp["KeyName"])
                        logger.debug(f"Cleaned up key pair: {kp['KeyName']}")
                    except Exception as e:
                        logger.debug(f"Could not delete key pair {kp['KeyName']}: {e}")
        except Exception as e:
            logger.debug(f"Error during key pair cleanup: {e}")

    if "no_ami" not in scenario.tags and "no_credentials" not in scenario.tags:
        ec2_client.register_image(
            Name="ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-20231201",
            Description="Ubuntu 22.04 LTS",
            Architecture="x86_64",
            RootDeviceName="/dev/sda1",
            VirtualizationType="hvm",
        )

        original_describe_images = ec2_client.describe_images

        def mock_describe_images(**kwargs) -> dict:
            response = original_describe_images(**kwargs)

            for image in response.get("Images", []):
                image["OwnerId"] = "099720109477"

            return response

        ec2_client.describe_images = mock_describe_images
        context.patched_ec2_client = ec2_client


def after_scenario(context: Context, scenario: Scenario) -> None:
    """Cleanup executed after each scenario.

    Parameters
    ----------
    context : Context
        The Behave context object.
    scenario : Scenario
        The scenario that just finished.
    """
    try:
        if hasattr(context, "mock_aws_env") and context.mock_aws_env:
            context.mock_aws_env.stop()
    except (RuntimeError, AttributeError) as e:
        logger.debug(f"Expected error stopping mock AWS: {e}")
    except Exception as e:
        logger.error(f"Unexpected error stopping mock AWS: {e}", exc_info=True)

    try:
        if hasattr(context, "cleanup_key_file") and context.cleanup_key_file:
            if (
                hasattr(context.cleanup_key_file, "exists")
                and context.cleanup_key_file.exists()
            ):
                context.cleanup_key_file.unlink()
    except (RuntimeError, AttributeError, OSError) as e:
        logger.debug(f"Expected error cleaning cleanup_key_file: {e}")
    except Exception as e:
        logger.error(f"Unexpected error cleaning cleanup_key_file: {e}", exc_info=True)

    try:
        if hasattr(context, "key_file") and context.key_file:
            if hasattr(context.key_file, "exists") and context.key_file.exists():
                context.key_file.unlink()
    except (RuntimeError, AttributeError, OSError) as e:
        logger.debug(f"Expected error cleaning key_file: {e}")
    except Exception as e:
        logger.error(f"Unexpected error cleaning key_file: {e}", exc_info=True)

    try:
        moondock_dir = os.environ.get("MOONDOCK_DIR", str(Path.home() / ".moondock"))
        keys_dir = Path(moondock_dir) / "keys"

        if keys_dir.exists() and not list(keys_dir.iterdir()):
            keys_dir.rmdir()

            if keys_dir.parent.exists() and not list(keys_dir.parent.iterdir()):
                keys_dir.parent.rmdir()
    except (RuntimeError, AttributeError, OSError) as e:
        logger.debug(f"Expected error removing empty keys directory: {e}")
    except Exception as e:
        logger.error(
            f"Unexpected error removing empty keys directory: {e}", exc_info=True
        )

    try:
        if hasattr(context, "aws_keys_backup"):
            for key, value in context.aws_keys_backup.items():
                if value is not None:
                    os.environ[key] = value
    except (KeyError, AttributeError) as e:
        logger.debug(f"Expected error with AWS credentials restoration: {e}")
    except Exception as e:
        logger.error(
            f"Unexpected error with AWS credentials restoration: {e}", exc_info=True
        )

    try:
        if hasattr(context, "temp_config_file"):
            if os.path.exists(context.temp_config_file):
                os.unlink(context.temp_config_file)
    except (RuntimeError, AttributeError, OSError) as e:
        logger.debug(f"Expected error deleting temp_config_file: {e}")
    except Exception as e:
        logger.error(f"Unexpected error deleting temp_config_file: {e}", exc_info=True)

    try:
        if hasattr(context, "env_config_file"):
            if os.path.exists(context.env_config_file):
                os.unlink(context.env_config_file)
    except (RuntimeError, AttributeError, OSError) as e:
        logger.debug(f"Expected error deleting env_config_file: {e}")
    except Exception as e:
        logger.error(f"Unexpected error deleting env_config_file: {e}", exc_info=True)

    try:
        if "MOONDOCK_CONFIG" in os.environ:
            del os.environ["MOONDOCK_CONFIG"]
    except (KeyError, AttributeError) as e:
        logger.debug(f"Expected error removing MOONDOCK_CONFIG: {e}")
    except Exception as e:
        logger.error(f"Unexpected error removing MOONDOCK_CONFIG: {e}", exc_info=True)


def after_all(context: Context) -> None:
    """Cleanup executed after all tests.

    Parameters
    ----------
    context : Context
        The Behave context object.
    """
    if hasattr(context, "mock_aws_env") and context.mock_aws_env:
        try:
            context.mock_aws_env.stop()
        except RuntimeError:
            pass

    if hasattr(context, "project_root"):
        moondock_dir = context.project_root / "tmp" / "test-moondock"

        if moondock_dir.exists():
            keys_dir = moondock_dir / "keys"

            if keys_dir.exists():
                for pem_file in keys_dir.glob("*.pem"):
                    try:
                        pem_file.unlink()
                        logger.debug(f"Final cleanup: removed {pem_file}")
                    except Exception as e:
                        logger.warning(f"Final cleanup failed for {pem_file}: {e}")

    if "MOONDOCK_DIR" in os.environ:
        del os.environ["MOONDOCK_DIR"]

    for key in [
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_DEFAULT_REGION",
        "MOONDOCK_TEST_MODE",
    ]:
        if key in os.environ:
            del os.environ[key]
