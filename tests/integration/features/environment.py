"""Behave environment configuration for moondock tests."""

import importlib.util
import logging
import logging.handlers
import os
import signal
import gc
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Any

from behave.model import Scenario
from behave.runner import Context
from moto import mock_aws
from tests.integration.features.steps.diagnostics_utils import (
    collect_diagnostics,
    send_signal_to_process,
)

logger = logging.getLogger(__name__)

# Test-specific configuration constants
TEST_SSH_TIMEOUT_SECONDS = 3
TEST_SSH_MAX_RETRIES = 6
SCENARIO_TIMEOUT_SECONDS = 180
TIMEOUT_ENFORCER_SIGNAL = getattr(signal, "SIGUSR1", signal.SIGTERM)


class LogCapture(logging.Handler):
    """Custom logging handler for capturing log records in tests."""

    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


class ScenarioTimeoutWatchdog:
    """Enforce per-scenario timeout budgets with diagnostics and signaling.

    Parameters
    ----------
    context : Context
        Behave scenario context containing harness references and metadata.
    timeout_seconds : int
        Maximum allowed runtime in seconds.
    signal_number : int, optional
        Signal used to interrupt the main thread when the timeout elapses.
    """

    def __init__(
        self,
        context: Context,
        timeout_seconds: int,
        signal_number: int = TIMEOUT_ENFORCER_SIGNAL,
    ) -> None:
        self._context = context
        self._timeout_seconds = timeout_seconds
        self._signal_number = signal_number
        self._deadline = time.monotonic() + timeout_seconds
        self._stop_event = threading.Event()
        self._triggered = threading.Event()
        scenario = getattr(context, "scenario", None)
        scenario_name = scenario.name if scenario else "unknown"
        thread_label = scenario_name.replace(" ", "-").replace("/", "-")
        self._thread = threading.Thread(
            target=self._run,
            name=f"scenario-watchdog-{thread_label[:40]}",
            daemon=True,
        )
        self._previous_handler = None

    def start(self) -> None:
        """Activate the watchdog thread and install the timeout signal handler."""

        if self._timeout_seconds <= 0:
            return

        self._previous_handler = signal.getsignal(self._signal_number)
        signal.signal(self._signal_number, self._signal_handler)
        self._thread.start()

    def cancel(self) -> None:
        """Stop the watchdog and restore the prior signal handler."""

        self._stop_event.set()

        if self._thread.is_alive():
            self._thread.join(timeout=1)

        if self._previous_handler is not None:
            signal.signal(self._signal_number, self._previous_handler)
            self._previous_handler = None

    def triggered(self) -> bool:
        """Return True when the timeout has fired."""

        return self._triggered.is_set()

    def _run(self) -> None:
        """Monitor elapsed time and trigger diagnostics on timeout."""

        poll_interval = min(1.0, max(0.1, self._timeout_seconds / 30))

        while not self._stop_event.wait(timeout=poll_interval):
            if time.monotonic() >= self._deadline:
                self._handle_timeout()
                break

    def _handle_timeout(self) -> None:
        """Collect diagnostics and interrupt execution when timeout expires."""

        if self._triggered.is_set():
            return

        self._triggered.set()

        scenario = getattr(self._context, "scenario", None)
        scenario_name = scenario.name if scenario else "unknown-scenario"
        diag_path = None

        diagnostics = self._get_diagnostics_service()

        try:
            diag_path = collect_diagnostics(
                self._context,
                reason="scenario_timeout",
            )
        except Exception as exc:  # pragma: no cover - diagnostics best effort
            logger.error("Scenario watchdog failed to write diagnostics: %s", exc)

        if diagnostics is not None:
            try:
                diagnostics.record(
                    "scenario-watchdog",
                    "timeout",
                    {
                        "scenario": scenario_name,
                        "timeout_seconds": self._timeout_seconds,
                        "artifact": str(diag_path) if diag_path else None,
                    },
                )
                diagnostics.record_system_snapshot(
                    "scenario-watchdog-timeout",
                    include_thread_stacks=True,
                )
            except Exception as exc:  # pragma: no cover - diagnostics best effort
                logger.debug("Failed to record watchdog diagnostics: %s", exc)

        if diag_path is not None:
            setattr(self._context, "watchdog_artifact_path", diag_path)

        logger.error(
            "Scenario '%s' exceeded %ss timeout. Diagnostics: %s",
            scenario_name,
            self._timeout_seconds,
            diag_path if diag_path else "unavailable",
        )

        try:
            os.kill(os.getpid(), self._signal_number)
        except OSError as exc:  # pragma: no cover - process teardown best effort
            logger.error(
                "Failed to signal timeout for scenario '%s': %s", scenario_name, exc
            )

    def _signal_handler(self, signum, frame):  # type: ignore[override]
        """Raise TimeoutError when the watchdog signal is delivered."""

        scenario = getattr(self._context, "scenario", None)
        scenario_name = scenario.name if scenario else "unknown-scenario"
        message = (
            f"Scenario '{scenario_name}' exceeded {self._timeout_seconds}s timeout"
        )
        raise TimeoutError(message)

    def _get_diagnostics_service(self):
        """Return the harness diagnostics collector if available."""

        harness = getattr(self._context, "harness", None)
        services = getattr(harness, "services", None)
        return getattr(services, "diagnostics", None)


def _start_scenario_watchdog(context: Context, timeout_seconds: int) -> None:
    """Start a scenario watchdog for the given Behave context."""

    if timeout_seconds <= 0:
        return

    if hasattr(context, "scenario_watchdog"):
        context.scenario_watchdog.cancel()

    watchdog = ScenarioTimeoutWatchdog(context, timeout_seconds)
    watchdog.start()
    context.scenario_watchdog = watchdog


def _stop_scenario_watchdog(context: Context) -> None:
    """Stop and remove any active scenario watchdog."""

    if not hasattr(context, "scenario_watchdog"):
        return

    try:
        context.scenario_watchdog.cancel()
    finally:
        delattr(context, "scenario_watchdog")


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


def cleanup_sshtunnel_processes() -> None:
    """Kill any lingering sshtunnel processes with retry logic.

    This function searches for and kills sshtunnel processes using multiple
    patterns and wait strategies to ensure complete cleanup.
    """
    import subprocess
    import time

    max_retries = 3
    retry_delay = 1

    patterns = [
        "sshtunnel",
        "SSHTunnel",
        "python.*sshtunnel",
    ]

    for attempt in range(max_retries):
        all_pids = set()

        for pattern in patterns:
            try:
                result = subprocess.run(
                    ["pgrep", "-f", pattern],
                    capture_output=True,
                    text=True,
                    timeout=3,
                )

                if result.returncode == 0 and result.stdout.strip():
                    pids = result.stdout.strip().split()
                    all_pids.update(pids)

            except FileNotFoundError:
                break
            except Exception as e:
                logger.debug(f"Error searching for sshtunnel processes ({pattern}): {e}")

        if not all_pids:
            logger.debug("No lingering sshtunnel processes found")
            return

        logger.info(
            f"Attempt {attempt + 1}/{max_retries}: "
            f"Found {len(all_pids)} sshtunnel process(es) to kill: {all_pids}"
        )

        for pid in all_pids:
            try:
                subprocess.run(
                    ["kill", "-9", pid],
                    capture_output=True,
                    timeout=1,
                )
                logger.debug(f"Killed sshtunnel process {pid}")
            except Exception as e:
                logger.debug(f"Error killing sshtunnel process {pid}: {e}")

        if attempt < max_retries - 1:
            logger.info(f"Waiting {retry_delay}s for processes to fully terminate...")
            time.sleep(retry_delay)


def cleanup_test_ports(port_list: list[int]) -> None:
    """Ensure test ports are free by stopping owners without killing the runner.

    Parameters
    ----------
    port_list : list[int]
        List of ports to clean up.
    """
    import subprocess
    import time

    max_retries = 5
    retry_delay = 1
    current_pid = str(os.getpid())

    for port in port_list:
        for attempt in range(max_retries):
            try:
                result = subprocess.run(
                    ["lsof", "-ti", f":{port}"],
                    capture_output=True,
                    text=True,
                    timeout=3,
                )

                pids = result.stdout.strip().split() if result.stdout.strip() else []
                filtered_pids = [pid for pid in pids if pid != current_pid]

                if filtered_pids:
                    logger.info(
                        f"Attempt {attempt + 1}/{max_retries}: "
                        f"Cleaning up {len(filtered_pids)} process(es) using port {port}: {filtered_pids}"
                    )

                    killed_pids = []
                    for pid in filtered_pids:
                        try:
                            subprocess.run(
                                ["kill", "-9", pid],
                                capture_output=True,
                                timeout=2,
                            )
                            killed_pids.append(pid)
                            logger.debug(f"Killed process {pid} using port {port}")
                        except subprocess.TimeoutExpired:
                            logger.warning(f"Timeout killing process {pid} on port {port}")
                        except Exception as e:
                            logger.warning(
                                f"Failed to kill process {pid} on port {port}: {e}"
                            )

                    if killed_pids and attempt < max_retries - 1:
                        logger.info(
                            f"Waiting {retry_delay}s for OS to release port {port}..."
                        )
                        time.sleep(retry_delay)
                        continue

                if not filtered_pids:
                    if pids and current_pid in pids:
                        logger.debug(
                            f"Attempting to stop portforward managers for port {port} owned by current PID {current_pid}"
                        )
                        _stop_portforward_managers_via_gc()
                    break

            except subprocess.TimeoutExpired:
                logger.warning(f"Timeout checking port {port} with lsof")
                break
            except FileNotFoundError:
                logger.warning("lsof command not found - cannot cleanup stale ports")
                break
            except Exception as e:
                logger.debug(f"Error cleaning up port {port}: {e}")
                break

        if not _port_is_free(port):
            owner_result = subprocess.run(
                ["lsof", "-i", f":{port}"], capture_output=True, text=True
            )
            owner_info = owner_result.stdout.strip() if owner_result.stdout else ""
            message = (
                f"Port {port} remains in use after cleanup attempts. Owner info: {owner_info}"
            )
            logger.error(message)
            raise RuntimeError(message)


def _port_is_free(port: int) -> bool:
    """Check whether a TCP port is free to bind on localhost.

    Parameters
    ----------
    port : int
        Port number to check.

    Returns
    -------
    bool
        True if the port can be bound, False otherwise.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def _stop_portforward_managers_via_gc() -> None:
    """Best-effort stop of any PortForwardManager instances reachable via GC."""
    try:
        from moondock.portforward import PortForwardManager
    except Exception:  # pragma: no cover - defensive import
        return

    stopped = 0
    for obj in gc.get_objects():
        try:
            if isinstance(obj, PortForwardManager):
                obj.stop_all_tunnels()
                stopped += 1
        except Exception:
            continue

    if stopped:
        logger.info(f"Stopped {stopped} PortForwardManager instance(s) via GC scan")


def before_all(context: Context) -> None:
    """Setup executed before all tests."""
    import subprocess

    test_ports = [48888, 48889, 48890, 48891, 6006]
    logger.info("Performing forceful cleanup of test ports before all tests...")
    cleanup_test_ports(test_ports)

    import time
    logger.info("Waiting 2 seconds for OS to release ports...")
    time.sleep(2)

    logger.info("Killing any lingering sshtunnel processes before all tests...")
    cleanup_sshtunnel_processes()

    project_root = Path(__file__).parent.parent.parent.parent
    tmp_dir = project_root / "tmp" / "test-artifacts"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    moondock_dir = project_root / "tmp" / "test-moondock"
    moondock_dir.mkdir(parents=True, exist_ok=True)

    try:
        import boto3

        logger.info("Cleaning up any stale instances from LocalStack...")
        from tests.integration.features.steps.instance_lifecycle_steps import (
            EC2Manager,
        )

        def localstack_client_factory(service: str, **kwargs: Any) -> Any:
            kwargs.setdefault("endpoint_url", "http://localhost:4566")
            return boto3.client(service, **kwargs)

        try:
            ec2_manager = EC2Manager(
                region="us-east-1", boto3_client_factory=localstack_client_factory
            )
            all_instances = ec2_manager.list_instances(region_filter=None)
            if all_instances:
                logger.info(f"Cleaning up {len(all_instances)} stale instances from LocalStack")
                for instance in all_instances:
                    try:
                        ec2_manager.terminate_instance(instance["instance_id"])
                        logger.info(f"Terminated stale instance: {instance['instance_id']}")
                    except Exception as e:
                        logger.warning(f"Failed to terminate stale instance: {e}")
            else:
                logger.info("LocalStack is clean - no stale instances found")
        except Exception as e:
            logger.debug(f"Could not connect to LocalStack yet (may not be running): {e}")
    except Exception as e:
        logger.warning(f"Failed to clean up LocalStack before tests: {e}")

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


def before_scenario(context: Context, scenario: Scenario) -> None:
    """Setup executed before each scenario."""
    context.diagnostic_artifacts = []
    context.scenario = scenario
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
    is_dry_run = "dry_run" in scenario.tags

    if is_localstack_scenario:
        from tests.harness.localstack import LocalStackHarness

        context.harness = LocalStackHarness(context, scenario)
        context.harness.setup()
        logger.info(f"Initialized LocalStackHarness for scenario: {scenario.name}")

        import time
        time.sleep(0.5)

        try:
            from tests.integration.features.steps.instance_lifecycle_steps import (
                setup_ec2_manager,
            )

            context.ec2_manager = None
            ec2_manager = setup_ec2_manager(context)
            all_instances = ec2_manager.list_instances(region_filter=None)
            if all_instances:
                logger.info(
                    f"Cleaning up {len(all_instances)} stale instances from LocalStack"
                )
                for instance in all_instances:
                    try:
                        ec2_manager.terminate_instance(instance["instance_id"])
                        logger.info(f"Terminated stale instance: {instance['instance_id']}")
                    except Exception as e:
                        logger.warning(f"Failed to terminate stale instance: {e}")
            else:
                logger.info("LocalStack is clean - no stale instances found")
        except Exception as e:
            logger.error(f"Error during stale instance cleanup: {e}", exc_info=True)

    elif is_dry_run:
        from tests.harness.dry_run import DryRunHarness

        context.harness = DryRunHarness(context, scenario)
        context.harness.setup()
        logger.info(f"Initialized DryRunHarness for scenario: {scenario.name}")

    if is_dry_run and not is_localstack_scenario:
        context.use_direct_instantiation = True
    else:
        context.use_direct_instantiation = False

    if is_localstack_scenario or is_pilot_scenario:
        try:
            from tests.integration.features.steps.cli_steps import (
                stop_registered_portforward_managers,
            )

            stop_registered_portforward_managers()
            logger.debug("Stopped registered port-forward managers before port cleanup")
        except Exception as e:
            logger.debug(f"Error stopping registered port-forward managers: {e}")

        if hasattr(context, "port_forward_manager") and context.port_forward_manager:
            try:
                context.port_forward_manager.stop_all_tunnels()
                logger.debug("Stopped port forwarding tunnels before port cleanup")
            except Exception as e:
                logger.debug(f"Error stopping tunnels before cleanup: {e}")

        import time

        common_test_ports = [48888, 48889, 48890, 48891, 6006]
        logger.info("Forcefully cleaning up test ports before scenario...")
        cleanup_test_ports(common_test_ports)

        logger.info("Killing any lingering sshtunnel processes before scenario...")
        cleanup_sshtunnel_processes()

        time.sleep(0.5)

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
                    if line.strip() and not line.startswith("[localhost]:")
                ]
                if len(filtered_lines) < len(lines):
                    known_hosts_path.write_text("\n".join(filtered_lines) + "\n")
                    logger.debug("Cleaned up localhost entries from ~/.ssh/known_hosts")
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

    _start_scenario_watchdog(context, timeout_seconds)
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

    context.running_instances = []
    context.stopped_instances = []
    context.created_instance_ids = []

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
    _stop_scenario_watchdog(context)

    is_localstack_or_pilot = "localstack" in scenario.tags or "pilot" in scenario.tags
    if is_localstack_or_pilot:
        logger.info("Killing lingering sshtunnel processes after scenario...")
        cleanup_sshtunnel_processes()

    diagnostics_paths = getattr(context, "diagnostic_artifacts", [])

    if scenario.status == "failed":
        if not diagnostics_paths:
            collect_diagnostics(context, reason="scenario-failure")
            diagnostics_paths = getattr(context, "diagnostic_artifacts", [])

        for artifact_path in diagnostics_paths:
            logger.info(
                "Diagnostics collected for failed scenario '%s': %s",
                scenario.name,
                artifact_path,
            )

    context.diagnostic_artifacts = []

    if hasattr(context, "pricing_client_patch"):
        context.pricing_client_patch.stop()
        delattr(context, "pricing_client_patch")

    if hasattr(context, "harness"):
        context.harness.cleanup()
        logger.info(f"Cleaned up new harness for scenario: {scenario.name}")

    is_localstack_scenario = "localstack" in scenario.tags

    if is_localstack_scenario:
        logger.info(
            "LocalStack container kept running for next @localstack scenario in feature"
        )

    try:
        instance_ids_to_terminate = []
        if hasattr(context, "state_test_instance_id") and context.state_test_instance_id:
            instance_ids_to_terminate.append(context.state_test_instance_id)

        if hasattr(context, "test_instance_id") and context.test_instance_id:
            instance_ids_to_terminate.append(context.test_instance_id)

        if hasattr(context, "existing_instance_id") and context.existing_instance_id:
            instance_ids_to_terminate.append(context.existing_instance_id)

        if hasattr(context, "started_instance_id") and context.started_instance_id:
            instance_ids_to_terminate.append(context.started_instance_id)

        if hasattr(context, "created_instance_ids") and context.created_instance_ids:
            instance_ids_to_terminate.extend(context.created_instance_ids)

        instance_ids_to_terminate = list(set(instance_ids_to_terminate))

        if instance_ids_to_terminate:
            if is_localstack_scenario and hasattr(context, "ec2_manager"):
                for instance_id in instance_ids_to_terminate:
                    logger.info(f"Terminating instance: {instance_id}")
                    try:
                        context.ec2_manager.ec2_client.terminate_instances(
                            InstanceIds=[instance_id]
                        )
                    except Exception as e:
                        logger.warning(f"Failed to terminate instance {instance_id}: {e}")

        if hasattr(context, "state_test_instance_name"):
            delattr(context, "state_test_instance_name")
        if hasattr(context, "expected_instance_state"):
            delattr(context, "expected_instance_state")
        if hasattr(context, "instance_current_state"):
            delattr(context, "instance_current_state")
        if hasattr(context, "state_test_instance_id"):
            delattr(context, "state_test_instance_id")
        if hasattr(context, "test_instance_id"):
            delattr(context, "test_instance_id")
        if hasattr(context, "test_instance_name"):
            delattr(context, "test_instance_name")
        if hasattr(context, "existing_instance_id"):
            delattr(context, "existing_instance_id")
        if hasattr(context, "existing_instance_name"):
            delattr(context, "existing_instance_name")
        if hasattr(context, "started_instance_id"):
            delattr(context, "started_instance_id")
        if hasattr(context, "existing_instance_stopped"):
            delattr(context, "existing_instance_stopped")
    except Exception as e:
        logger.debug(f"Error cleaning up instances: {e}")

    try:
        if "localstack" in scenario.tags and hasattr(context, "app_process"):
            if context.app_process and context.app_process.poll() is None:
                logger.info("Killing orphaned app_process from graceful shutdown test")
                send_signal_to_process(context.app_process, signal.SIGKILL)
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
    cleanup_env_var("MOONDOCK_TEST_MODE", logger)
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
        try:
            from tests.integration.features.steps.cli_steps import (
                stop_registered_portforward_managers,
            )

            stop_registered_portforward_managers()
        except Exception as e:
            logger.debug(f"Error stopping registered port-forward managers: {e}")
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

    harness = getattr(context, "harness", None)
    harness_managed = False
    try:
        from tests.harness.localstack import LocalStackHarness

        harness_managed = isinstance(harness, LocalStackHarness)
    except ImportError:
        harness_managed = False

    if (
        is_localstack_scenario
        and hasattr(context, "config_data")
        and not harness_managed
    ):
        try:
            import shutil

            config_data = getattr(context, "config_data", None) or {}
            if "sync_paths" in config_data.get("defaults", {}):
                logger.debug("Cleaning up Mutagen sessions for test")

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
                    if line.strip() and not line.startswith("[localhost]:")
                ]
                if len(filtered_lines) < len(lines):
                    known_hosts_path.write_text("\n".join(filtered_lines) + "\n")
                    msg = "Cleaned up localhost entries from ~/.ssh/known_hosts after scenario"
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


def before_feature(context: Context, feature) -> None:
    """Cleanup stale LocalStack instances before feature starts."""
    scenarios = getattr(feature, "scenarios", [])
    has_localstack_scenario = any(
        "localstack" in getattr(scenario, "tags", []) for scenario in scenarios
    )

    print(f"DEBUG: before_feature - has_localstack_scenario={has_localstack_scenario}")

    if not has_localstack_scenario:
        print("DEBUG: skipping before_feature - no localstack scenarios")
        return

    try:
        import time
        import boto3

        print("DEBUG: before_feature - starting cleanup")
        time.sleep(1)

        logger.info("Cleaning up stale instances before feature starts...")
        from tests.integration.features.steps.instance_lifecycle_steps import (
            EC2Manager,
        )

        def localstack_client_factory(service: str, **kwargs: Any) -> Any:
            kwargs.setdefault("endpoint_url", "http://localhost:4566")
            return boto3.client(service, **kwargs)

        try:
            print("DEBUG: creating EC2Manager")
            ec2_manager = EC2Manager(
                region="us-east-1", boto3_client_factory=localstack_client_factory
            )
            print("DEBUG: listing instances")
            all_instances = ec2_manager.list_instances(region_filter=None)
            print(f"DEBUG: found {len(all_instances)} instances")
            if all_instances:
                logger.info(
                    f"Cleaning up {len(all_instances)} stale instances from LocalStack before feature"
                )
                for instance in all_instances:
                    try:
                        ec2_manager.terminate_instance(instance["instance_id"])
                        logger.info(f"Terminated stale instance: {instance['instance_id']}")
                    except Exception as e:
                        logger.warning(f"Failed to terminate stale instance: {e}")
            else:
                logger.info("LocalStack is clean - no stale instances found at feature start")
        except Exception as e:
            print(f"DEBUG: exception in cleanup: {e}")
            logger.debug(f"Could not connect to LocalStack: {e}")
    except Exception as e:
        logger.warning(f"Error in before_feature cleanup: {e}", exc_info=True)


def after_feature(context: Context, feature) -> None:
    """Cleanup executed after all scenarios in a feature complete."""
    pass


def after_all(context: Context) -> None:
    """Cleanup executed after all tests."""

    test_ports = [48888, 48889, 48890, 48891, 6006]
    logger.info("Performing forceful cleanup of test ports after all tests...")
    cleanup_test_ports(test_ports)

    logger.info("Killing any lingering sshtunnel processes after all tests...")
    cleanup_sshtunnel_processes()

    from tests.harness.localstack import LocalStackHarness

    LocalStackHarness.stop_localstack_container()
    logger.info("Stopped LocalStack container after all tests complete")

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
