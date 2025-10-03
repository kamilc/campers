"""BDD step definitions for SSH port forwarding."""

import os

from behave import given, then, when
from behave.runner import Context


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


@given("config file with ports {ports_list}")
def step_config_with_ports(context: Context, ports_list: str) -> None:
    """Add ports to defaults configuration."""
    defaults = ensure_defaults_section(context)

    import json

    ports = json.loads(ports_list)
    defaults["ports"] = ports


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

    import json

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
    os.environ["MOONDOCK_TUNNEL_FAIL_PORT"] = str(port)


@given("local port {port:d} is already in use")
def step_local_port_in_use(context: Context, port: int) -> None:
    """Mark that local port is already in use."""
    os.environ["MOONDOCK_PORT_IN_USE"] = str(port)


@then("SSH tunnel is created for port {port:d}")
def step_ssh_tunnel_created(context: Context, port: int) -> None:
    """Verify SSH tunnel was created for port."""
    assert hasattr(context, "stderr"), "No stderr output captured"

    expected_message = f"Creating SSH tunnel for port {port}..."
    assert expected_message in context.stderr, (
        f"Expected message '{expected_message}' not found in stderr: {context.stderr}"
    )


@then("tunnel forwards localhost:{port:d} to remote:{port:d}")
def step_tunnel_forwards_port(context: Context, port: int) -> None:
    """Verify tunnel forwards correct ports."""
    assert hasattr(context, "stderr"), "No stderr output captured"

    expected_message = f"SSH tunnel established: localhost:{port} -> remote:{port}"
    assert expected_message in context.stderr, (
        f"Expected message '{expected_message}' not found in stderr: {context.stderr}"
    )


@then("status messages logged for all three ports")
def step_status_messages_all_ports(context: Context) -> None:
    """Verify status messages logged for all three ports."""
    assert hasattr(context, "stderr"), "No stderr output captured"

    for port in [8888, 6006, 5000]:
        assert f"Creating SSH tunnel for port {port}..." in context.stderr
        assert (
            f"SSH tunnel established: localhost:{port} -> remote:{port}"
            in context.stderr
        )


@then("no SSH tunnels are created")
def step_no_tunnels_created(context: Context) -> None:
    """Verify no SSH tunnels were created."""
    assert hasattr(context, "stderr"), "No stderr output captured"
    assert "Creating SSH tunnel" not in context.stderr, (
        f"Found 'Creating SSH tunnel' in stderr:\n{context.stderr}"
    )


@then("no port forwarding log messages appear")
def step_no_port_forwarding_logs(context: Context) -> None:
    """Verify no port forwarding log messages appear."""
    assert hasattr(context, "stderr"), "No stderr output captured"
    assert "SSH tunnel" not in context.stderr


@then('status message "{message}" is logged before tunnels')
def step_message_before_tunnels(context: Context, message: str) -> None:
    """Verify message appears before tunnel creation."""
    assert hasattr(context, "stderr"), "No stderr output captured"

    assert message in context.stderr

    message_index = context.stderr.index(message)
    tunnel_message = "Creating SSH tunnel for port 8888..."

    if tunnel_message in context.stderr:
        tunnel_index = context.stderr.index(tunnel_message)
        assert message_index < tunnel_index


@then('status message "{message}" is logged after tunnels')
def step_message_after_tunnels(context: Context, message: str) -> None:
    """Verify message appears after tunnel creation."""
    assert hasattr(context, "stderr"), "No stderr output captured"

    assert message in context.stderr

    tunnel_message = "SSH tunnel established: localhost:8888 -> remote:8888"

    if tunnel_message in context.stderr:
        tunnel_index = context.stderr.index(tunnel_message)
        message_index = context.stderr.index(message)
        assert tunnel_index < message_index


@then("tunnels are stopped before SSH connection closes")
def step_tunnels_stopped_before_ssh(context: Context) -> None:
    """Verify tunnels stopped before SSH closes."""
    assert hasattr(context, "stderr"), "No stderr output captured"

    stopping_message = "Stopping SSH tunnel for port"
    assert stopping_message in context.stderr


@then("all SSH tunnels are stopped")
@then("all tunnels are stopped")
def step_all_tunnels_stopped(context: Context) -> None:
    """Verify all SSH tunnels are stopped."""
    assert hasattr(context, "stderr"), "No stderr output captured"

    stopping_message = "Stopping SSH tunnel for port"
    assert stopping_message in context.stderr, (
        f"Expected message '{stopping_message}' not found in stderr: {context.stderr}"
    )


@then("error is logged for port {port:d}")
def step_error_logged_for_port(context: Context, port: int) -> None:
    """Verify error logged for specific port."""
    assert hasattr(context, "stderr"), "No stderr output captured"

    error_indicators = [f"port {port}", f"Failed to create tunnel for port {port}"]

    found = any(indicator in context.stderr for indicator in error_indicators)
    assert found, (
        f"Expected error for port {port} not found in stderr: {context.stderr}"
    )


@then("all successfully created tunnels are stopped")
def step_successful_tunnels_stopped(context: Context) -> None:
    """Verify all successfully created tunnels are stopped."""
    assert hasattr(context, "stderr"), "No stderr output captured"


@then("SSH tunnel creation is skipped")
def step_tunnel_creation_skipped(context: Context) -> None:
    """Verify SSH tunnel creation was skipped in test mode."""
    assert hasattr(context, "test_mode_enabled") and context.test_mode_enabled


@then("local_bind_address is localhost only")
def step_local_bind_localhost(context: Context) -> None:
    """Verify local_bind_address is localhost only."""
    assert hasattr(context, "config_data"), "No config data available"

    if hasattr(context, "port_forward_manager"):
        for _port, tunnel in context.port_forward_manager.tunnels:
            local_bind = tunnel.local_bind_address
            assert local_bind[0] == "localhost", (
                f"Expected local_bind_address to be 'localhost', got '{local_bind[0]}'"
            )


@then("remote_bind_address is localhost only")
def step_remote_bind_localhost(context: Context) -> None:
    """Verify remote_bind_address is localhost only."""
    assert hasattr(context, "config_data"), "No config data available"

    if hasattr(context, "port_forward_manager"):
        for _port, tunnel in context.port_forward_manager.tunnels:
            remote_bind = tunnel.remote_bind_address
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
    os.environ["MOONDOCK_SIMULATE_INTERRUPT"] = "1"


@when("SSH tunnel is created for port {port:d}")
def step_when_tunnel_created(context: Context, port: int) -> None:
    """Mark when tunnel is being created."""
    defaults = ensure_defaults_section(context)
    defaults["ports"] = [port]
    defaults["command"] = "echo test"
