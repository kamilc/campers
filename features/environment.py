"""Behave environment configuration for moondock tests."""

import importlib.util
import logging
import logging.handlers
import os
import sys
from pathlib import Path

from behave.model import Scenario
from behave.runner import Context
from moto import mock_aws

logger = logging.getLogger(__name__)

# Test-specific configuration constants
TEST_SSH_TIMEOUT_SECONDS = 3
TEST_SSH_MAX_RETRIES = 6
SCENARIO_TIMEOUT_SECONDS = 180


class LogCapture(logging.Handler):
    """Custom logging handler for capturing log records in tests.

    Attributes
    ----------
    records : list[logging.LogRecord]
        List of captured log records
    """

    def __init__(self) -> None:
        """Initialize LogCapture handler with empty records list."""
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        """Capture log record.

        Parameters
        ----------
        record : logging.LogRecord
            Log record to capture
        """
        self.records.append(record)


def cleanup_env_var(var_name: str, logger: logging.Logger) -> None:
    """Remove environment variable with error handling.

    Parameters
    ----------
    var_name : str
        Name of the environment variable to remove
    logger : logging.Logger
        Logger instance for error reporting
    """
    try:
        if var_name in os.environ:
            del os.environ[var_name]
    except KeyError as e:
        logger.debug(f"Expected error removing {var_name}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error removing {var_name}: {e}", exc_info=True)


def run_mutagen_command_with_retry(
    args: list[str],
    timeout: int = 10,
    max_attempts: int = 3,
    text_output: bool = False,
) -> str | bool:
    """Run mutagen command with retry logic.

    Parameters
    ----------
    args : list[str]
        Command arguments after 'mutagen'
    timeout : int
        Timeout in seconds for command execution
    max_attempts : int
        Maximum number of retry attempts
    text_output : bool
        If True, returns command output as string; if False, returns bool

    Returns
    -------
    str | bool
        Command output if text_output is True, success status otherwise
    """
    import subprocess
    import time

    for attempt in range(max_attempts):
        try:
            result = subprocess.run(
                ["mutagen"] + args,
                capture_output=True,
                text=text_output,
                timeout=timeout,
            )

            if result.returncode == 0:
                return result.stdout if text_output else True

            logger.warning(
                f"Mutagen command failed with returncode={result.returncode}: "
                f"{' '.join(args)}"
            )
        except subprocess.TimeoutExpired:
            logger.warning(f"Mutagen command timed out after {timeout}s")
        except Exception as e:
            logger.warning(f"Mutagen command error: {e}")

        if attempt < max_attempts - 1:
            time.sleep(2)

    error_msg = (
        f"Mutagen command failed after {max_attempts} attempts: {' '.join(args)}"
    )
    logger.error(error_msg)
    return "" if text_output else False


def terminate_mutagen_with_retry(session_name: str, max_attempts: int = 3) -> bool:
    """Terminate Mutagen session with retry logic.

    Parameters
    ----------
    session_name : str
        Name of the Mutagen session to terminate
    max_attempts : int
        Maximum number of retry attempts

    Returns
    -------
    bool
        True if termination succeeded, False if all retries exhausted
    """
    result = run_mutagen_command_with_retry(
        ["sync", "terminate", session_name],
        timeout=10,
        max_attempts=max_attempts,
        text_output=False,
    )

    if result:
        logger.debug(f"Successfully terminated {session_name}")

    return bool(result)


def list_mutagen_sessions_with_retry(max_attempts: int = 3) -> str:
    """List Mutagen sessions with retry logic.

    Parameters
    ----------
    max_attempts : int
        Maximum number of retry attempts

    Returns
    -------
    str
        Output from mutagen sync list command, empty string if failed
    """
    result = run_mutagen_command_with_retry(
        ["sync", "list"],
        timeout=10,
        max_attempts=max_attempts,
        text_output=True,
    )

    if result:
        logger.debug("Successfully listed Mutagen sessions")

    return str(result) if result else ""


def check_mutagen_daemon_health() -> bool:
    """Check if Mutagen daemon is responsive before scenario execution.

    Returns
    -------
    bool
        True if daemon is responsive, False otherwise
    """
    import subprocess
    import time

    max_health_checks = 5

    for attempt in range(max_health_checks):
        try:
            result = subprocess.run(
                ["mutagen", "daemon", "status"],
                capture_output=True,
                text=True,
                timeout=3,
            )

            if result.returncode == 0:
                logger.debug("Mutagen daemon is responsive")
                return True

            logger.warning(
                f"Mutagen daemon check failed "
                f"(attempt {attempt + 1}/{max_health_checks}), "
                f"returncode={result.returncode}"
            )
        except subprocess.TimeoutExpired:
            logger.warning(
                f"Mutagen daemon check timed out "
                f"(attempt {attempt + 1}/{max_health_checks})"
            )
        except FileNotFoundError:
            logger.warning("Mutagen command not found - Mutagen may not be installed")
            return False
        except Exception as e:
            logger.debug(f"Mutagen daemon check error: {e}")

        if attempt < max_health_checks - 1:
            time.sleep(2)

    logger.warning(
        "Mutagen daemon not responsive after all attempts - test may be unstable"
    )
    return False


def before_all(context: Context) -> None:
    """Setup executed before all tests.

    Parameters
    ----------
    context : Context
        The Behave context object
    """
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

    moondock_script = project_root / "moondock" / "__main__.py"
    spec = importlib.util.spec_from_file_location("moondock_module", moondock_script)
    moondock_module = importlib.util.module_from_spec(spec)
    sys.modules["moondock_module"] = moondock_module
    spec.loader.exec_module(moondock_module)

    context.moondock_module = moondock_module

    import subprocess

    logging.info("Installing moondock in editable mode...")
    result = subprocess.run(
        ["uv", "pip", "install", "-e", "."],
        capture_output=True,
        text=True,
        timeout=30,
    )

    if result.returncode != 0:
        error_msg = (
            "Failed to install moondock in editable mode. "
            "This is required for @localstack graceful shutdown tests.\n"
            f"stderr: {result.stderr}\n"
            f"stdout: {result.stdout}"
        )
        logging.error(error_msg)
        raise RuntimeError(error_msg)

    logging.info("Moondock installed successfully in editable mode")


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

    timeout_seconds = SCENARIO_TIMEOUT_SECONDS
    for tag in scenario.tags:
        if tag.startswith("timeout_"):
            try:
                timeout_seconds = int(tag.split("_")[1])
                logger.info(f"Using custom timeout from tag: {timeout_seconds}s")
            except (ValueError, IndexError):
                logger.warning(f"Invalid timeout tag format: {tag}, using default")

    context.scenario_timeout = timeout_seconds
    logger.info(f"Scenario timeout stored as {timeout_seconds}s for: {scenario.name}")

    if hasattr(context, "mock_aws_env") and context.mock_aws_env:
        try:
            context.mock_aws_env.stop()
        except (RuntimeError, Exception):
            pass

    is_localstack_scenario = "localstack" in scenario.tags
    is_pilot_scenario = "pilot" in scenario.tags

    if is_localstack_scenario or is_pilot_scenario:
        import socket
        import time

        common_test_ports = [48888, 48889, 48890]
        max_wait_seconds = 5

        for port in common_test_ports:
            port_released = False

            for attempt in range(max_wait_seconds * 2):
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                        sock.bind(("localhost", port))
                        port_released = True
                        logger.debug(f"Port {port} is available")
                        break
                except OSError:
                    if attempt == 0:
                        logger.warning(
                            f"Port {port} in use, waiting {max_wait_seconds}s..."
                        )

                    time.sleep(0.5)

            if not port_released:
                logger.error(f"Port {port} still in use after {max_wait_seconds}s")

    if is_localstack_scenario or is_pilot_scenario:
        try:
            import docker

            docker_client = docker.from_env()
            orphaned_containers = docker_client.containers.list(
                all=True, filters={"name": "ssh-"}
            )

            for container in orphaned_containers:
                try:
                    logger.info(f"Cleaning up orphaned container: {container.name}")
                    container.remove(force=True)
                except Exception as e:
                    logger.debug(f"Error removing container {container.name}: {e}")
        except Exception as e:
            logger.debug(f"Error during pre-scenario Docker cleanup: {e}")

        if "localstack" in scenario.tags:
            check_mutagen_daemon_health()

        try:
            known_hosts_path = Path.home() / ".ssh" / "known_hosts"
            if known_hosts_path.exists():
                known_hosts_content = known_hosts_path.read_text()
                lines = known_hosts_content.split("\n")
                filtered_lines = [
                    line
                    for line in lines
                    if not line.startswith("[localhost]:2222") and line.strip()
                ]
                if len(filtered_lines) < len(lines):
                    known_hosts_path.write_text("\n".join(filtered_lines) + "\n")
                    logger.debug("Cleaned up localhost:2222 from ~/.ssh/known_hosts")
        except Exception as e:
            logger.debug(f"Error cleaning known_hosts: {e}")

        try:
            ssh_dir = Path.home() / ".ssh"
            ssh_dir.mkdir(parents=True, exist_ok=True)
            ssh_config_path = ssh_dir / "config"
            localhost_config = (
                "\nHost localhost\n"
                "    StrictHostKeyChecking no\n"
                "    UserKnownHostsFile=/dev/null\n"
            )
            if ssh_config_path.exists():
                config_content = ssh_config_path.read_text()
                if "Host localhost" not in config_content:
                    ssh_config_path.write_text(config_content + localhost_config)
                    logger.debug("Added localhost SSH config")
            else:
                ssh_config_path.write_text(localhost_config)
                logger.debug("Created SSH config with localhost entry")
        except Exception as e:
            logger.debug(f"Error setting up SSH config: {e}")

    if "no_credentials" not in scenario.tags and not is_localstack_scenario:
        context.mock_aws_env = mock_aws()
        context.mock_aws_env.start()
        os.environ["AWS_ACCESS_KEY_ID"] = "testing"
        os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
        os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
    else:
        context.mock_aws_env = None

    if is_localstack_scenario:
        os.environ["AWS_ENDPOINT_URL"] = "http://localhost:4566"
        os.environ["AWS_ACCESS_KEY_ID"] = "testing"
        os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
        os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
        os.environ["MOONDOCK_SSH_TIMEOUT"] = str(TEST_SSH_TIMEOUT_SECONDS)
        os.environ["MOONDOCK_SSH_MAX_RETRIES"] = str(TEST_SSH_MAX_RETRIES)

        if "error" in scenario.tags:
            os.environ["MOONDOCK_SSH_TIMEOUT"] = "2"
            os.environ["MOONDOCK_SSH_MAX_RETRIES"] = "3"
            logger.info("Using reduced SSH retry config for @error scenario")

    if is_localstack_scenario or is_pilot_scenario:
        os.environ["MOONDOCK_TEST_MODE"] = "0"

    log_handler = LogCapture()
    log_handler.setLevel(logging.DEBUG)
    context.log_handler = log_handler
    context.log_records = log_handler.records

    moondock_ec2_logger = logging.getLogger("moondock.ec2")
    moondock_ec2_logger.addHandler(log_handler)
    moondock_ec2_logger.setLevel(logging.DEBUG)

    moondock_ssh_logger = logging.getLogger("moondock.ssh")
    moondock_ssh_logger.addHandler(log_handler)
    moondock_ssh_logger.setLevel(logging.DEBUG)

    if is_localstack_scenario or "dry_run" in scenario.tags:
        moondock_portforward_logger = logging.getLogger("moondock.portforward")
        moondock_portforward_logger.addHandler(log_handler)
        moondock_portforward_logger.setLevel(logging.INFO)
        moondock_portforward_logger.propagate = True

        moondock_sync_logger = logging.getLogger("moondock.sync")
        moondock_sync_logger.addHandler(log_handler)
        moondock_sync_logger.setLevel(logging.INFO)
        moondock_sync_logger.propagate = True

    root_logger = logging.getLogger()
    root_logger.addHandler(log_handler)
    root_logger.setLevel(logging.DEBUG)

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
    context.exit_code = None
    context.stdout = None
    context.stderr = None
    context.final_config = None
    context.error = None
    context.config_data = None
    context.temp_config_file = None
    context.env_config_file = None
    context.env_config_path = None
    context.validation_error = None
    context.config_path = None
    context.config_to_validate = None
    context.yaml_config = None
    context.merged_config = None
    context.test_mode_enabled = None
    context.no_public_ip = None
    context.ssh_always_fails = None
    context.patched_ec2_client = None
    context.ami_id = None
    context.connection_attempts = None
    context.connection_successful = None
    context.existing_key_name = None
    context.existing_sg_id = None
    context.found_ami_id = None
    context.has_debug_logging = None
    context.has_error_logging = None
    context.has_logger = None
    context.has_logging_import = None
    context.infrastructure_check = None
    context.initial_sg_ids = None
    context.keys_dir = None
    context.machine_name = None
    context.moondock_path = None
    context.no_ami_found = None
    context.rapid_test_execution = None
    context.region = None
    context.result = None
    context.retry_delays = None
    context.scenario_completed = None
    context.ssh_manager = None
    context.ssh_not_ready = None
    context.termination_timeout = None
    context.timeout_scenario = None
    context.uses_hex_format = None
    context.uses_uuid = None

    context.instances = None
    context.aws_permission_error = None
    context.state_test_instances = None
    context.mock_terminate = None
    context.time_test_instances = None
    context.test_instance_id_mapping = None
    context.long_machine_config = None
    context.filter_region = None
    context.region_patches = None
    context.patches = []
    context.mock_time_instances = None
    context.terminate_runtime_error = None
    context.terminate_client_error = None

    context.mock_moondock = context.moondock_module.Moondock()
    context.cleanup_order = []

    if "no_credentials" not in scenario.tags and not is_localstack_scenario:
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

    if (
        "no_ami" not in scenario.tags
        and "no_credentials" not in scenario.tags
        and not is_localstack_scenario
    ):
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
        if "localstack" in scenario.tags and hasattr(context, "app_process"):
            if context.app_process and context.app_process.poll() is None:
                logger.info("Killing orphaned app_process from graceful shutdown test")
                context.app_process.kill()
                try:
                    context.app_process.wait(timeout=5)
                except Exception as e:
                    logger.warning(f"Error waiting for app_process to terminate: {e}")
    except Exception as e:
        logger.debug(f"Error cleaning up app_process: {e}")

    try:
        if hasattr(context, "log_handler") and context.log_handler:
            moondock_ec2_logger = logging.getLogger("moondock.ec2")
            moondock_ec2_logger.removeHandler(context.log_handler)

            moondock_ssh_logger = logging.getLogger("moondock.ssh")
            moondock_ssh_logger.removeHandler(context.log_handler)

            moondock_portforward_logger = logging.getLogger("moondock.portforward")
            moondock_portforward_logger.removeHandler(context.log_handler)

            moondock_sync_logger = logging.getLogger("moondock.sync")
            moondock_sync_logger.removeHandler(context.log_handler)

            root_logger = logging.getLogger()
            root_logger.removeHandler(context.log_handler)
    except Exception as e:
        logger.debug(f"Error removing log handler: {e}")

    try:
        if hasattr(context, "patches"):
            for patch_obj in context.patches:
                patch_obj.stop()
    except Exception as e:
        logger.debug(f"Error stopping patches: {e}")

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
    except AttributeError as e:
        logger.debug(f"Expected error with AWS credentials restoration: {e}")
    except Exception as e:
        logger.error(
            f"Unexpected error with AWS credentials restoration: {e}", exc_info=True
        )

    try:
        if hasattr(context, "temp_config_file") and context.temp_config_file:
            if os.path.exists(context.temp_config_file):
                os.unlink(context.temp_config_file)
    except (RuntimeError, AttributeError, OSError) as e:
        logger.debug(f"Expected error deleting temp_config_file: {e}")
    except Exception as e:
        logger.error(f"Unexpected error deleting temp_config_file: {e}", exc_info=True)

    try:
        if hasattr(context, "env_config_file") and context.env_config_file:
            if os.path.exists(context.env_config_file):
                os.unlink(context.env_config_file)
    except (RuntimeError, AttributeError, OSError) as e:
        logger.debug(f"Expected error deleting env_config_file: {e}")
    except Exception as e:
        logger.error(f"Unexpected error deleting env_config_file: {e}", exc_info=True)

    try:
        if "MOONDOCK_CONFIG" in os.environ:
            del os.environ["MOONDOCK_CONFIG"]
    except KeyError as e:
        logger.debug(f"Expected error removing MOONDOCK_CONFIG: {e}")
    except Exception as e:
        logger.error(f"Unexpected error removing MOONDOCK_CONFIG: {e}", exc_info=True)

    try:
        if "MOONDOCK_NO_PUBLIC_IP" in os.environ:
            del os.environ["MOONDOCK_NO_PUBLIC_IP"]
    except KeyError as e:
        logger.debug(f"Expected error removing MOONDOCK_NO_PUBLIC_IP: {e}")
    except Exception as e:
        logger.error(
            f"Unexpected error removing MOONDOCK_NO_PUBLIC_IP: {e}", exc_info=True
        )

    try:
        if "MOONDOCK_TEST_MODE" in os.environ:
            if os.environ.get("MOONDOCK_TEST_MODE") != "1":
                os.environ["MOONDOCK_TEST_MODE"] = "1"
    except KeyError as e:
        logger.debug(f"Expected error restoring MOONDOCK_TEST_MODE: {e}")
    except Exception as e:
        logger.error(
            f"Unexpected error restoring MOONDOCK_TEST_MODE: {e}", exc_info=True
        )

    try:
        if "MOONDOCK_SYNC_TIMEOUT" in os.environ:
            del os.environ["MOONDOCK_SYNC_TIMEOUT"]
    except KeyError as e:
        logger.debug(f"Expected error removing MOONDOCK_SYNC_TIMEOUT: {e}")
    except Exception as e:
        logger.error(
            f"Unexpected error removing MOONDOCK_SYNC_TIMEOUT: {e}", exc_info=True
        )

    cleanup_env_var("MOONDOCK_MUTAGEN_NOT_INSTALLED", logger)
    cleanup_env_var("MOONDOCK_TUNNEL_FAIL_PORT", logger)
    cleanup_env_var("MOONDOCK_PORT_IN_USE", logger)
    cleanup_env_var("MOONDOCK_SIMULATE_INTERRUPT", logger)
    cleanup_env_var("AWS_ENDPOINT_URL", logger)
    cleanup_env_var("MOONDOCK_SSH_DELAY_SECONDS", logger)
    cleanup_env_var("MOONDOCK_SSH_BLOCK_CONNECTIONS", logger)
    cleanup_env_var("MOONDOCK_SSH_TIMEOUT", logger)
    cleanup_env_var("MOONDOCK_SSH_MAX_RETRIES", logger)

    try:
        if hasattr(context, "port_forward_manager") and context.port_forward_manager:
            try:
                context.port_forward_manager.stop_all_tunnels()
                logger.debug("Stopped port forwarding tunnels from test scenario")
            except Exception as e:
                logger.debug(f"Error stopping port forwarding tunnels: {e}")
    except Exception as e:
        logger.debug(f"Error during port forwarding cleanup: {e}")

    try:
        if hasattr(context, "monitor_stop_event") and context.monitor_stop_event:
            context.monitor_stop_event.set()
            logger.debug("Signaled LocalStack monitor thread to stop")
        if hasattr(context, "monitor_thread") and context.monitor_thread:
            context.monitor_thread.join(timeout=5)
            logger.debug("LocalStack monitor thread stopped")
    except Exception as e:
        logger.debug(f"Error stopping monitor thread: {e}")

    try:
        if hasattr(context, "container_manager") and context.container_manager:
            context.container_manager.cleanup_all()
            logger.debug("Cleaned up all Docker SSH containers")
    except Exception as e:
        logger.debug(f"Error cleaning up Docker containers: {e}")

    ssh_port_vars = [k for k in os.environ.keys() if k.startswith("SSH_PORT_")]
    for var in ssh_port_vars:
        cleanup_env_var(var, logger)

    ssh_key_file_vars = [k for k in os.environ.keys() if k.startswith("SSH_KEY_FILE_")]
    for var in ssh_key_file_vars:
        cleanup_env_var(var, logger)

    ssh_ready_vars = [k for k in os.environ.keys() if k.startswith("SSH_READY_")]
    for var in ssh_ready_vars:
        cleanup_env_var(var, logger)

    monitor_error_vars = [
        k for k in os.environ.keys() if k.startswith("MONITOR_ERROR_")
    ]
    for var in monitor_error_vars:
        cleanup_env_var(var, logger)

    is_localstack_scenario = "localstack" in scenario.tags

    if is_localstack_scenario and hasattr(context, "config_data"):
        try:
            import shutil

            config_data = getattr(context, "config_data", None) or {}
            if "sync_paths" in config_data.get("defaults", {}):
                logger.debug("Cleaning up Mutagen sessions for @localstack test")

                sessions_output = list_mutagen_sessions_with_retry(max_attempts=3)
                if sessions_output:
                    for line in sessions_output.split("\n"):
                        if "moondock-" in line:
                            parts = line.split()
                            if parts:
                                session_name = parts[0]
                                msg = f"Terminating Mutagen session: {session_name}"
                                logger.info(msg)
                                terminate_mutagen_with_retry(
                                    session_name, max_attempts=3
                                )
                else:
                    logger.warning("Could not list Mutagen sessions, skipping cleanup")

                moondock_dir = os.environ.get("MOONDOCK_DIR")
                if moondock_dir and "tmp/test-moondock" in moondock_dir:
                    test_dir = Path(moondock_dir)
                    if test_dir.exists():
                        shutil.rmtree(test_dir, ignore_errors=True)
                        logger.debug(f"Cleaned up test MOONDOCK_DIR: {test_dir}")

            if hasattr(context, "orphaned_temp_dir") and context.orphaned_temp_dir:
                orphan_dir = Path(context.orphaned_temp_dir)
                if orphan_dir.exists():
                    shutil.rmtree(orphan_dir, ignore_errors=True)
                    logger.debug(f"Cleaned up orphaned temp directory: {orphan_dir}")
        except Exception as e:
            logger.debug(f"Error during Mutagen cleanup: {e}")

    if is_localstack_scenario:
        try:
            known_hosts_path = Path.home() / ".ssh" / "known_hosts"
            if known_hosts_path.exists():
                known_hosts_content = known_hosts_path.read_text()
                lines = known_hosts_content.split("\n")
                filtered_lines = [
                    line
                    for line in lines
                    if not line.startswith("[localhost]:2222") and line.strip()
                ]
                if len(filtered_lines) < len(lines):
                    known_hosts_path.write_text("\n".join(filtered_lines) + "\n")
                    logger.debug(
                        "Cleaned up localhost:2222 entries from ~/.ssh/known_hosts after scenario"
                    )
        except Exception as e:
            logger.debug(f"Error cleaning known_hosts after scenario: {e}")

    try:
        if hasattr(context, "saved_env") and context.saved_env:
            os.environ.clear()
            os.environ.update(context.saved_env)
            delattr(context, "saved_env")
    except Exception as e:
        logger.error(f"Error restoring environment: {e}", exc_info=True)


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
