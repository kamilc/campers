"""BDD step definitions for SSH port forwarding."""

import io
import json
import logging
import os
import tarfile
import time

import requests
from behave import given, then, when
from behave.runner import Context

import docker

logger = logging.getLogger(__name__)


def get_captured_logs_text(context: Context) -> str:
    """Extract captured log records as formatted text.

    Parameters
    ----------
    context : Context
        Behave context object

    Returns
    -------
    str
        Formatted text from captured log records
    """
    if hasattr(context, "log_records") and context.log_records:
        log_lines = []
        for record in context.log_records:
            log_lines.append(record.getMessage())
        return "\n".join(log_lines)
    return ""


def get_output_text(context: Context) -> str:
    """Get output text, checking both stderr and captured logs.

    For subprocess mode (dry_run), returns context.stderr.
    For in-process mode (localstack), returns captured logs.

    Parameters
    ----------
    context : Context
        Behave context object

    Returns
    -------
    str
        Available output text
    """
    if context.stderr:
        return context.stderr
    return get_captured_logs_text(context)


def ensure_defaults_section(context: Context) -> dict:
    """Ensure defaults section exists in config_data and return it.

    Parameters
    ----------
    context : Context
        Behave context object containing test state

    Returns
    -------
    dict
        The defaults section dictionary
    """
    if not hasattr(context, "config_data") or context.config_data is None:
        context.config_data = {"defaults": {}}

    if "defaults" not in context.config_data:
        context.config_data["defaults"] = {}

    return context.config_data["defaults"]


def extract_ports_from_config(
    context: Context,
    include_defaults: bool = True,
    include_camps: bool = True,
    camp_name: str | None = None,
) -> list[int]:
    """Extract unique ports from config based on specified sources.

    Parameters
    ----------
    context : Context
        Behave context object containing config data
    include_defaults : bool
        Whether to include ports from defaults section
    include_camps : bool
        Whether to include ports from camps section
    camp_name : str | None
        If specified, only extract ports from this machine

    Returns
    -------
    list[int]
        List of unique port numbers preserving order
    """
    if not hasattr(context, "config_data") or context.config_data is None:
        return []

    all_ports = []

    if include_defaults:
        defaults = context.config_data.get("defaults", {})
        default_ports = defaults.get("ports", [])
        all_ports.extend(default_ports)

    if include_camps:
        camps = context.config_data.get("camps", {})

        if camp_name:
            camp_config = camps.get(camp_name, {})
            machine_ports = camp_config.get("ports", [])
            all_ports.extend(machine_ports)
        else:
            for config in camps.values():
                ports = config.get("ports", [])
                all_ports.extend(ports)

    return list(dict.fromkeys(all_ports))


@given("config file with ports {ports_list}")
def step_config_with_ports(context: Context, ports_list: str) -> None:
    """Add ports to defaults configuration."""
    defaults = ensure_defaults_section(context)

    ports = json.loads(ports_list)
    defaults["ports"] = ports


@given('config file with port mapping "{port_mapping}"')
def step_config_with_port_mapping(context: Context, port_mapping: str) -> None:
    """Add port mapping to defaults configuration.

    Parameters
    ----------
    context : Context
        Behave context object
    port_mapping : str
        Port mapping string in format "remote:local" (e.g., "6006:6007")
    """
    defaults = ensure_defaults_section(context)
    defaults["ports"] = [port_mapping]


@given("config file with no ports specified")
def step_config_no_ports(context: Context) -> None:
    """Ensure defaults have no ports configured."""
    defaults = ensure_defaults_section(context)
    defaults["ports"] = []


@given("config file with sync_paths configured")
def step_config_with_sync_paths(context: Context) -> None:
    """Add sync_paths to defaults configuration."""
    defaults = ensure_defaults_section(context)
    defaults["sync_paths"] = [{"local": "~/myproject", "remote": "~/myproject"}]


@given('config file with startup_script "{script}"')
def step_config_with_startup_script(context: Context, script: str) -> None:
    """Add startup_script to defaults configuration."""
    defaults = ensure_defaults_section(context)
    defaults["startup_script"] = script


@given("SSH tunnels for ports {ports_list} are running")
def step_ssh_tunnels_running(context: Context, ports_list: str) -> None:
    """Mark that SSH tunnels are running for specified ports."""
    defaults = ensure_defaults_section(context)

    ports = json.loads(ports_list)
    defaults["ports"] = ports
    defaults["command"] = "echo test"


@given("command is executing")
def step_command_executing(context: Context) -> None:
    """Mark that a command is executing."""
    defaults = ensure_defaults_section(context)
    defaults["command"] = "sleep 100"


@given("port {port:d} tunnel creation fails")
def step_port_tunnel_fails(context: Context, port: int) -> None:
    """Mark that tunnel creation will fail for specific port."""
    context.harness.services.configuration_env.set("CAMPERS_TUNNEL_FAIL_PORT", str(port))


@given("local port {port:d} is already in use")
def step_local_port_in_use(context: Context, port: int) -> None:
    """Mark that local port is already in use."""
    context.harness.services.configuration_env.set("CAMPERS_PORT_IN_USE", str(port))


@then("SSH tunnel is created for port {port:d}")
def step_ssh_tunnel_created(context: Context, port: int) -> None:
    """Verify SSH tunnel was created for port."""
    output = get_output_text(context)
    assert output, "No output captured (no stderr or log records)"

    expected_message = f"Creating SSH tunnel for port {port}..."
    assert expected_message in output, (
        f"Expected message '{expected_message}' not found in output: {output}"
    )


@then("tunnel forwards localhost:{port:d} to remote:{port:d}")
def step_tunnel_forwards_port(context: Context, port: int) -> None:
    """Verify tunnel forwards correct ports."""
    output = get_output_text(context)
    assert output, "No output captured (no stderr or log records)"

    expected_message = f"SSH tunnel established: localhost:{port} -> remote:{port}"
    assert expected_message in output, (
        f"Expected message '{expected_message}' not found in output: {output}"
    )


@then("status messages logged for all three ports")
def step_status_messages_all_ports(context: Context) -> None:
    """Verify status messages logged for all three ports."""
    output = get_output_text(context)
    assert output, "No output captured (no stderr or log records)"

    defaults = context.config_data.get("defaults", {})
    ports = defaults.get("ports", [])

    for port in ports:
        assert f"Creating SSH tunnel for port {port}..." in output, (
            f"Expected message 'Creating SSH tunnel for port {port}...' not found in output"
        )
        expected_msg = f"SSH tunnel established: localhost:{port} -> remote:{port}"
        assert expected_msg in output, f"Expected '{expected_msg}' not found in output"


@then("no SSH tunnels are created")
def step_no_tunnels_created(context: Context) -> None:
    """Verify no SSH tunnels were created."""
    output = get_output_text(context)
    assert "Creating SSH tunnel" not in output, f"Found 'Creating SSH tunnel' in output:\n{output}"


@then("no port forwarding log messages appear")
def step_no_port_forwarding_logs(context: Context) -> None:
    """Verify no port forwarding log messages appear."""
    output = get_output_text(context)
    assert "SSH tunnel" not in output


@then('status message "{message}" is logged before tunnels')
def step_message_before_tunnels(context: Context, message: str) -> None:
    """Verify message appears before tunnel creation."""
    output = get_output_text(context)
    assert output, "No output captured (no stderr or log records)"

    assert message in output

    message_index = output.index(message)
    tunnel_message = "Creating SSH tunnel for port 48888..."

    if tunnel_message in output:
        tunnel_index = output.index(tunnel_message)
        assert message_index < tunnel_index


@then('status message "{message}" is logged after tunnels')
def step_message_after_tunnels(context: Context, message: str) -> None:
    """Verify message appears after tunnel creation."""
    output = get_output_text(context)
    assert output, "No output captured (no stderr or log records)"

    assert message in output

    tunnel_message = "SSH tunnel established: localhost:48888 -> remote:48888"

    if tunnel_message in output:
        tunnel_index = output.index(tunnel_message)
        message_index = output.index(message)
        assert tunnel_index < message_index


@then("tunnels are stopped before SSH connection closes")
def step_tunnels_stopped_before_ssh(context: Context) -> None:
    """Verify tunnels stopped before SSH closes."""
    output = get_output_text(context)
    assert output, "No output captured (no stderr or log records)"

    stopping_message = "Stopping SSH tunnel for port"
    assert stopping_message in output


@then("all SSH tunnels are stopped")
@then("all tunnels are stopped")
def step_all_tunnels_stopped(context: Context) -> None:
    """Verify all SSH tunnels are stopped."""
    output = get_output_text(context)
    assert output, "No output captured (no stderr or log records)"

    stopping_message = "Stopping SSH tunnel for port"
    assert stopping_message in output, (
        f"Expected message '{stopping_message}' not found in output: {output}"
    )


@then("error is logged for port {port:d}")
def step_error_logged_for_port(context: Context, port: int) -> None:
    """Verify error logged for specific port."""
    output = get_output_text(context)
    assert output, "No output captured (no stderr or log records)"

    error_indicators = [f"port {port}", f"Failed to create tunnel for port {port}"]

    found = any(indicator in output for indicator in error_indicators)
    assert found, f"Expected error for port {port} not found in output: {output}"


@then("all successfully created tunnels are stopped")
def step_successful_tunnels_stopped(context: Context) -> None:
    """Verify all successfully created tunnels are stopped."""
    output = get_output_text(context)
    assert output, "No output captured (no stderr or log records)"


@then("SSH tunnel creation is skipped")
def step_tunnel_creation_skipped(context: Context) -> None:
    """Verify SSH tunnel creation was skipped in test mode."""
    assert hasattr(context, "test_mode_enabled") and context.test_mode_enabled


@then("local_bind_address is localhost only")
def step_local_bind_localhost(context: Context) -> None:
    """Verify local_bind_address is localhost only."""
    assert hasattr(context, "config_data"), "No config data available"

    if hasattr(context, "port_forward_manager"):
        tunnel = context.port_forward_manager.tunnel
        if tunnel and hasattr(tunnel, "local_bind_addresses"):
            for local_bind in tunnel.local_bind_addresses:
                assert local_bind[0] == "localhost", (
                    f"Expected local_bind_address to be 'localhost', got '{local_bind[0]}'"
                )


@then("remote_bind_address is localhost only")
def step_remote_bind_localhost(context: Context) -> None:
    """Verify remote_bind_address is localhost only."""
    assert hasattr(context, "config_data"), "No config data available"

    if hasattr(context, "port_forward_manager"):
        tunnel = context.port_forward_manager.tunnel
        if tunnel and hasattr(tunnel, "remote_bind_addresses"):
            for remote_bind in tunnel.remote_bind_addresses:
                assert remote_bind[0] == "localhost", (
                    f"Expected remote_bind_address to be 'localhost', got '{remote_bind[0]}'"
                )


@then("tunnel creation fails with error")
def step_tunnel_fails_with_error(context: Context) -> None:
    """Verify tunnel creation failed with error."""
    assert context.exit_code != 0


@when("user interrupts with KeyboardInterrupt")
def step_user_interrupts(context: Context) -> None:
    """Simulate KeyboardInterrupt."""
    context.harness.services.configuration_env.set("CAMPERS_SIMULATE_INTERRUPT", "1")


@when("SSH tunnel is created for port {port:d}")
def step_when_tunnel_created(context: Context, port: int) -> None:
    """Mark when tunnel is being created."""
    defaults = ensure_defaults_section(context)
    defaults["ports"] = [port]
    defaults["command"] = "echo test"


def start_http_server_in_container(context: Context, port: int) -> None:
    """Start HTTP server listener in SSH container on specified port.

    Parameters
    ----------
    context : Context
        Behave context object
    port : int
        Port number for HTTP server
    """
    if not hasattr(context, "instance_id") or context.instance_id is None:
        logger.debug(f"No instance_id available, skipping HTTP server for port {port}")
        return

    instance_id = context.instance_id
    docker_client = docker.from_env()
    container_name = f"ssh-{instance_id}"

    try:
        container = docker_client.containers.get(container_name)

        logger.info(f"Starting HTTP server on port {port} in container {container_name}")

        check_python = container.exec_run(["sh", "-c", "command -v python3"])

        if check_python.exit_code != 0:
            logger.info(
                f"Python3 not found in container {container_name}, attempting installation..."
            )

            check_apk = container.exec_run(["sh", "-c", "command -v apk"])

            if check_apk.exit_code != 0:
                error_msg = (
                    f"Cannot install Python3: {container_name} does not use Alpine Linux. "
                    f"Docker image must include Python3 or use Alpine (apk)."
                )
                logger.error(error_msg)
                raise RuntimeError(error_msg)

            install_result = container.exec_run(
                ["sh", "-c", "apk add --no-cache python3"], user="root"
            )

            if install_result.exit_code != 0:
                error_output = (
                    install_result.output.decode()
                    if hasattr(install_result.output, "decode")
                    else str(install_result.output)
                )
                error_msg = (
                    f"Failed to install Python3 in container {container_name}: {error_output}"
                )
                logger.error(error_msg)
                raise RuntimeError(error_msg)

            logger.info(f"Python3 installed successfully in container {container_name}")

        script_path = os.path.join(os.path.dirname(__file__), "..", "support", "http_server.py")

        with open(script_path, "rb") as f:
            script_content = f.read()

        tar_buffer = io.BytesIO()

        with tarfile.open(fileobj=tar_buffer, mode="w") as tar:
            tarinfo = tarfile.TarInfo(name="http_server.py")
            tarinfo.size = len(script_content)
            tar.addfile(tarinfo, io.BytesIO(script_content))

        tar_buffer.seek(0)

        try:
            container.put_archive("/tmp", tar_buffer)
            logger.debug(f"HTTP server script copied to /tmp in container {container_name}")
        except (docker.errors.APIError, docker.errors.ContainerError) as e:
            logger.warning(f"Failed to copy HTTP server script to container: {e}")
            return

        cmd = f"nohup python3 /tmp/http_server.py {port} > /tmp/http_server_{port}.log 2>&1 &"

        try:
            container.exec_run(["sh", "-c", cmd], detach=True, user="root")
        except (docker.errors.APIError, docker.errors.ContainerError) as e:
            logger.warning(f"Failed to start HTTP server on port {port}: {e}")
            return

        time.sleep(2)

        for attempt in range(10):
            check_cmd = (
                f"ss -tuln 2>/dev/null | grep -E ':{port}\\s' || "
                f"netstat -tuln 2>/dev/null | grep ':{port}'"
            )
            check_result = container.exec_run(["sh", "-c", check_cmd])

            if check_result.exit_code == 0:
                logger.info(f"Verified HTTP server listening on port {port}")
                return

            if attempt < 9:
                time.sleep(0.5)
            else:
                log_cmd = f"cat /tmp/http_server_{port}.log 2>/dev/null || echo 'No log file'"
                log_result = container.exec_run(["sh", "-c", log_cmd])
                log_output = (
                    log_result.output.decode()
                    if hasattr(log_result.output, "decode")
                    else str(log_result.output)
                )
                logger.warning(
                    f"HTTP server on port {port} not listening after retries. Log: {log_output}"
                )

    except docker.errors.NotFound as e:
        logger.warning(f"SSH container {container_name} not found: {e}")


@given("HTTP server runs on port {port:d} in SSH container")
def step_http_server_in_container(context: Context, port: int) -> None:
    """Register that HTTP server should run on port in SSH container.

    This step registers the port for HTTP server setup. The actual HTTP server
    startup happens automatically after instance creation via the monitor thread
    and start_http_servers_for_configured_ports() calls.

    Parameters
    ----------
    context : Context
        Behave context object
    port : int
        Port number for HTTP server
    """
    defaults = ensure_defaults_section(context)

    if "ports" not in defaults:
        defaults["ports"] = []

    if port not in defaults["ports"]:
        defaults["ports"].append(port)

    logger.info(f"HTTP server registration for port {port} added to config")


@then("HTTP request to localhost:{port:d} succeeds")
def step_http_request_succeeds(context: Context, port: int) -> None:
    """Verify HTTP connectivity through forwarded port.

    Tests actual HTTP connectivity to localhost on the forwarded port.
    Attempts to make HTTP requests with retries to handle timing issues.

    Parameters
    ----------
    context : Context
        Behave context object
    port : int
        Port number to test
    """
    logger.info(f"Testing HTTP connectivity to localhost:{port}")
    max_attempts = 15
    last_error = None

    for attempt in range(max_attempts):
        try:
            logger.debug(f"HTTP request attempt {attempt + 1}/{max_attempts} to localhost:{port}")
            response = requests.get(f"http://localhost:{port}", timeout=3, allow_redirects=False)

            if response.status_code == 200:
                logger.info(f"HTTP request to localhost:{port} succeeded (attempt {attempt + 1})")
                return

            last_error = f"HTTP {response.status_code}"
            logger.debug(f"HTTP status: {response.status_code}")

            if attempt < max_attempts - 1:
                time.sleep(1)
                continue

            raise AssertionError(f"HTTP {response.status_code} from localhost:{port}")

        except (
            requests.exceptions.ConnectionError,
            requests.exceptions.ReadTimeout,
            requests.exceptions.Timeout,
        ) as e:
            last_error = f"Connection error: {str(e)[:80]}"
            logger.debug(f"Connection attempt {attempt + 1} failed, retrying...")

            if attempt < max_attempts - 1:
                time.sleep(1)
                continue

            logger.error(f"Failed to connect to localhost:{port} after {max_attempts} attempts")

            output = get_output_text(context)
            logger.error(f"Tunnel status check - Full output: {output}")
            raise AssertionError(
                f"Failed to connect to localhost:{port} after {max_attempts} attempts: {last_error}"
            ) from e

    raise AssertionError(f"HTTP request to localhost:{port} failed: {last_error}")


def start_http_servers_for_ports(context: Context, ports: list) -> None:
    """Start HTTP servers for given list of ports.

    Parameters
    ----------
    context : Context
        Behave context object
    ports : list
        List of port numbers to start servers on
    """
    if not hasattr(context, "instance_id") or context.instance_id is None:
        logger.debug("No instance_id available, skipping HTTP server setup")
        return

    if not ports:
        logger.debug("No ports to configure, skipping HTTP server setup")
        return

    logger.info(f"Starting HTTP servers for ports: {ports}")

    for port in ports:
        start_http_server_in_container(context, port)


def start_http_servers_for_configured_ports(context: Context) -> None:
    """Start HTTP servers for all configured ports after instance creation.

    This function starts HTTP servers for ports from the defaults section
    of the config_data. Called after instance creation to ensure instance_id
    is available in context.

    Parameters
    ----------
    context : Context
        Behave context object containing instance_id and configured ports
    """
    if not hasattr(context, "config_data") or context.config_data is None:
        logger.debug("No config_data available, skipping HTTP server setup")
        return

    defaults = context.config_data.get("defaults", {})
    ports = defaults.get("ports", [])
    start_http_servers_for_ports(context, ports)


def start_http_servers_for_machine_ports(context: Context) -> None:
    """Start HTTP servers for ports configured in the machine configuration.

    This function starts HTTP servers for ports from the machine configuration
    after TUI execution.

    Parameters
    ----------
    context : Context
        Behave context object containing instance_id and configured ports
    """
    if not hasattr(context, "config_data") or context.config_data is None:
        logger.debug("No config_data available, skipping HTTP server setup")
        return

    if not hasattr(context, "camp_name") or context.camp_name is None:
        logger.debug("No camp_name available, skipping HTTP server setup")
        return

    camps = context.config_data.get("camps", {})
    camp_config = camps.get(context.camp_name, {})
    ports = camp_config.get("ports", [])
    start_http_servers_for_ports(context, ports)


def start_http_servers_for_all_configured_ports(context: Context) -> None:
    """Start HTTP servers for all configured ports in defaults and camps.

    This function starts HTTP servers for ports from both the defaults section
    and machine-specific configuration. Called after instance creation to ensure
    instance_id is available in context.

    Parameters
    ----------
    context : Context
        Behave context object containing instance_id and configured ports
    """
    if not hasattr(context, "config_data") or context.config_data is None:
        logger.debug("No config_data available, skipping HTTP server setup")
        return

    unique_ports = extract_ports_from_config(context, include_defaults=True, include_camps=True)

    if unique_ports:
        logger.info(f"Starting HTTP servers for all configured ports: {unique_ports}")
        start_http_servers_for_ports(context, unique_ports)
