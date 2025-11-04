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
    """Custom logging handler for capturing log records in tests."""

    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def cleanup_env_var(var_name: str, logger: logging.Logger) -> None:
    """Remove environment variable with error handling."""
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
    """Run mutagen command with retry logic."""
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
    """Terminate Mutagen session with retry logic."""
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
    """List Mutagen sessions with retry logic."""
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
    """Check if Mutagen daemon is responsive."""
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


SSH_BLOCK_START = "# MOONDOCK_TEST_BLOCK_START"
SSH_BLOCK_END = "# MOONDOCK_TEST_BLOCK_END"


def get_localhost_config_block() -> str:
    """Return SSH localhost config block with test markers."""
    return (
        f"\n{SSH_BLOCK_START}\n"
        "Host localhost\n"
        "    StrictHostKeyChecking no\n"
        "    UserKnownHostsFile=/dev/null\n"
        f"{SSH_BLOCK_END}\n"
    )


def remove_test_ssh_block(config_path: Path) -> None:
    """Remove test markers and their content from SSH config."""
    import re

    if not config_path.exists():
        return

    config = config_path.read_text()
    config = re.sub(
        rf"\n?{SSH_BLOCK_START}.*?{SSH_BLOCK_END}\n?",
        "",
        config,
        flags=re.DOTALL,
    )
    config_path.write_text(config)


def append_test_ssh_block(config_path: Path) -> None:
    """Idempotently add test SSH config block, removing any existing block first."""
    import re

    config_path.parent.mkdir(parents=True, exist_ok=True)

    if config_path.exists():
        config = config_path.read_text()
    else:
        config = ""

    config = re.sub(
        rf"\n?{SSH_BLOCK_START}.*?{SSH_BLOCK_END}\n?",
        "",
        config,
        flags=re.DOTALL,
    )
    config_path.write_text(config + get_localhost_config_block())


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

    is_healthy = check_mutagen_daemon_health()
    if not is_healthy:
        logger.error("Mutagen daemon is not healthy - @localstack tests will fail")
    else:
        logger.info("Mutagen daemon is healthy")


def start_localstack_container() -> bool:
    """Start LocalStack Docker container if not already running."""
    import subprocess

    container_name = "moondock-localstack"

    try:
        import docker

        docker_client = docker.from_env()

        try:
            existing_container = docker_client.containers.get(container_name)
            logger.info(f"LocalStack container '{container_name}' already exists")

            if existing_container.status == "running":
                logger.info("LocalStack container is already running")
                return True

            logger.info("Found stopped LocalStack container, attempting to start it")
            existing_container.start()
            logger.info("Successfully started existing LocalStack container")
            return True
        except docker.errors.NotFound:
            logger.info("No existing LocalStack container found, starting new one")

        result = subprocess.run(
            [
                "docker",
                "run",
                "-d",
                "--rm",
                "--name",
                container_name,
                "-p",
                "4566:4566",
                "-p",
                "4510-4559:4510-4559",
                "-v",
                "/var/run/docker.sock:/var/run/docker.sock",
                "localstack/localstack:latest",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode == 0:
            logger.info(
                f"Successfully started LocalStack container: {result.stdout.strip()}"
            )
            return True

        error_msg = f"Failed to start LocalStack: {result.stderr}"
        logger.error(error_msg)
        return False

    except Exception as e:
        error_msg = f"Exception while starting LocalStack: {e}"
        logger.error(error_msg)
        return False


def stop_localstack_container() -> bool:
    """Stop LocalStack Docker container."""
    container_name = "moondock-localstack"

    try:
        import docker

        docker_client = docker.from_env()

        try:
            container = docker_client.containers.get(container_name)
            container.stop(timeout=10)
            logger.info("Successfully stopped LocalStack container")
            return True
        except docker.errors.NotFound:
            logger.debug("No LocalStack container found to stop")
            return True

    except Exception as e:
        logger.warning(f"Error stopping LocalStack container: {e}")
        return False


def before_scenario(context: Context, scenario: Scenario) -> None:
    """Setup executed before each scenario."""
    import boto3

    USE_NEW_HARNESS = os.getenv("MOONDOCK_NEW_HARNESS", "false").lower() == "true"

    if USE_NEW_HARNESS and "dry_run" in scenario.tags:
        from tests.harness.dry_run import DryRunHarness

        context.harness = DryRunHarness(context, scenario)
        context.harness.setup()
        logger.info(f"Initialized new harness for dry-run scenario: {scenario.name}")

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
    is_dry_run = "dry_run" in scenario.tags

    if is_localstack_scenario:
        logger.info("Starting LocalStack container for @localstack scenario")
        if not start_localstack_container():
            raise RuntimeError(
                "Failed to start LocalStack container. Please ensure Docker is running."
            )

        from features.steps.localstack_steps import wait_for_localstack_health

        try:
            wait_for_localstack_health(timeout=60, interval=2)
            logger.info("LocalStack health check passed, scenario can proceed")
        except TimeoutError as e:
            raise RuntimeError(f"LocalStack failed health check: {e}")

    if is_dry_run and not is_localstack_scenario:
        context.use_direct_instantiation = True
    else:
        context.use_direct_instantiation = False

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
            ssh_config_path = Path.home() / ".ssh" / "config"
            append_test_ssh_block(ssh_config_path)
            logger.debug("SSH config block added idempotently")
        except Exception as e:
            logger.debug(f"Error setting up SSH config: {e}")

    if "no_credentials" not in scenario.tags and not is_localstack_scenario:
        context.mock_aws_env = mock_aws()
        context.mock_aws_env.start()
        os.environ["AWS_ACCESS_KEY_ID"] = "testing"
        os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
        os.environ["AWS_DEFAULT_REGION"] = "us-east-1"

        if is_dry_run:
            ec2_client = boto3.client("ec2", region_name="us-east-1")

            vpcs = ec2_client.describe_vpcs()
            for vpc in vpcs.get("Vpcs", []):
                if vpc.get("IsDefault"):
                    vpc_id = vpc["VpcId"]
                    try:
                        subnets = ec2_client.describe_subnets(
                            Filters=[{"Name": "vpc-id", "Values": [vpc_id]}]
                        )
                        for subnet in subnets.get("Subnets", []):
                            try:
                                ec2_client.delete_subnet(SubnetId=subnet["SubnetId"])
                            except Exception as e:
                                logger.debug(
                                    f"Could not delete subnet {subnet['SubnetId']}: {e}"
                                )

                        igws = ec2_client.describe_internet_gateways(
                            Filters=[{"Name": "attachment.vpc-id", "Values": [vpc_id]}]
                        )
                        for igw in igws.get("InternetGateways", []):
                            try:
                                ec2_client.detach_internet_gateway(
                                    InternetGatewayId=igw["InternetGatewayId"],
                                    VpcId=vpc_id,
                                )
                                ec2_client.delete_internet_gateway(
                                    InternetGatewayId=igw["InternetGatewayId"]
                                )
                            except Exception as e:
                                igw_id = igw["InternetGatewayId"]
                                logger.debug(
                                    f"Could not delete internet gateway {igw_id}: {e}"
                                )

                        ec2_client.delete_vpc(VpcId=vpc_id)
                    except Exception as e:
                        logger.debug(f"Could not delete VPC {vpc_id}: {e}")

            vpc_response = ec2_client.create_vpc(CidrBlock="10.0.0.0/16")
            vpc_id = vpc_response["Vpc"]["VpcId"]
            logger.debug(f"Created test VPC: {vpc_id}")

            subnet_response = ec2_client.create_subnet(
                VpcId=vpc_id, CidrBlock="10.0.1.0/24"
            )
            subnet_id = subnet_response["Subnet"]["SubnetId"]
            logger.debug(f"Created test subnet: {subnet_id}")

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
    """Cleanup executed after each scenario."""
    if hasattr(context, "harness"):
        context.harness.cleanup()
        logger.info(f"Cleaned up new harness for scenario: {scenario.name}")

    is_localstack_scenario = "localstack" in scenario.tags

    if is_localstack_scenario:
        try:
            if hasattr(context, "monitor_stop_event") and context.monitor_stop_event:
                logger.info(
                    "Stopping LocalStack instance monitor thread after scenario"
                )
                context.monitor_stop_event.set()

                if hasattr(context, "monitor_thread") and context.monitor_thread:
                    context.monitor_thread.join(timeout=5)
                    logger.debug("Monitor thread stopped successfully")
        except Exception as e:
            logger.warning(f"Error stopping monitor thread: {e}")

        logger.info(
            "LocalStack container kept running for next @localstack scenario in feature"
        )

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
                    msg = "Cleaned up localhost:2222 entries from ~/.ssh/known_hosts after scenario"
                    logger.debug(msg)
        except Exception as e:
            logger.debug(f"Error cleaning known_hosts after scenario: {e}")

    try:
        if hasattr(context, "saved_env") and context.saved_env:
            os.environ.clear()
            os.environ.update(context.saved_env)
            delattr(context, "saved_env")
    except Exception as e:
        logger.error(f"Error restoring environment: {e}", exc_info=True)


def after_feature(context: Context, feature) -> None:
    """Cleanup executed after all scenarios in a feature complete."""
    has_localstack_scenarios = any(
        "localstack" in scenario.tags for scenario in feature.scenarios
    )

    if has_localstack_scenarios:
        logger.info(
            f"Feature '{feature.name}' had @localstack scenarios, stopping LocalStack container"
        )
        stop_localstack_container()

        if hasattr(context, "container_manager"):
            logger.info("Cleaning up SSH containers and keys")
            try:
                context.container_manager.cleanup_all()
                logger.debug("SSH container cleanup completed successfully")
            except Exception as e:
                logger.warning(f"SSH container cleanup failed: {e}", exc_info=True)


def after_all(context: Context) -> None:
    """Cleanup executed after all tests."""
    if hasattr(context, "mock_aws_env") and context.mock_aws_env:
        try:
            context.mock_aws_env.stop()
        except RuntimeError:
            pass

    try:
        ssh_config_path = Path.home() / ".ssh" / "config"
        remove_test_ssh_block(ssh_config_path)
        logger.debug("Test SSH config block removed successfully")
    except Exception as e:
        logger.warning(f"Failed to remove test SSH config block: {e}")

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
    ]:
        if key in os.environ:
            del os.environ[key]
