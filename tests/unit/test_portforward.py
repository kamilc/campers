"""Unit tests for SSH port forwarding functionality."""

from unittest.mock import MagicMock, call, patch

import paramiko
import pytest
from sshtunnel import BaseSSHTunnelForwarderError

from campers.services.portforward import PortForwardManager


@pytest.fixture
def port_forward_manager() -> PortForwardManager:
    """Create PortForwardManager instance for testing.

    Returns
    -------
    PortForwardManager
        Fresh port forward manager instance
    """
    return PortForwardManager()


def test_port_forward_manager_initialization() -> None:
    """Test PortForwardManager initialization creates empty tunnel and ports."""
    manager = PortForwardManager()

    assert manager.tunnel is None
    assert manager.ports == []


@patch("campers.services.portforward.PortForwardManager.validate_key_file")
@patch("campers.services.portforward.validate_port")
@patch("campers.services.portforward.logger")
@patch("campers.services.portforward.SSHTunnelForwarder")
def test_create_tunnels_success_single_port(
    mock_tunnel_forwarder: MagicMock,
    mock_logger: MagicMock,
    mock_validate_port: MagicMock,
    mock_validate_key_file: MagicMock,
    port_forward_manager: PortForwardManager,
) -> None:
    """Test successful creation of single SSH tunnel."""
    mock_tunnel = MagicMock()
    mock_tunnel.is_active = True
    mock_tunnel_forwarder.return_value = mock_tunnel

    port_forward_manager.create_tunnels(
        ports=[(8888, 8888)],
        host="203.0.113.1",
        key_file="/tmp/test.pem",
        username="ubuntu",
    )

    assert mock_validate_port.call_count == 2
    mock_validate_key_file.assert_called_once_with("/tmp/test.pem")
    mock_tunnel_forwarder.assert_called_once_with(
        ssh_address_or_host=("203.0.113.1", 22),
        ssh_username="ubuntu",
        ssh_pkey="/tmp/test.pem",
        remote_bind_addresses=[("localhost", 8888)],
        local_bind_addresses=[("localhost", 8888)],
    )
    mock_tunnel.start.assert_called_once()
    assert port_forward_manager.tunnel == mock_tunnel
    assert port_forward_manager.ports == [(8888, 8888)]


@patch("campers.services.portforward.PortForwardManager.validate_key_file")
@patch("campers.services.portforward.validate_port")
@patch("campers.services.portforward.logger")
@patch("campers.services.portforward.SSHTunnelForwarder")
def test_create_tunnels_success_multiple_ports(
    mock_tunnel_forwarder: MagicMock,
    mock_logger: MagicMock,
    mock_validate_port: MagicMock,
    mock_validate_key_file: MagicMock,
    port_forward_manager: PortForwardManager,
) -> None:
    """Test successful creation of multiple SSH tunnels with single forwarder."""
    mock_tunnel = MagicMock()
    mock_tunnel.is_active = True
    mock_tunnel_forwarder.return_value = mock_tunnel

    port_forward_manager.create_tunnels(
        ports=[(8888, 8888), (8889, 8889), (8890, 8890)],
        host="203.0.113.1",
        key_file="/tmp/test.pem",
        username="ubuntu",
    )

    assert mock_validate_port.call_count == 6
    mock_validate_key_file.assert_called_once_with("/tmp/test.pem")

    mock_tunnel_forwarder.assert_called_once()
    call_kwargs = mock_tunnel_forwarder.call_args[1]
    assert call_kwargs["remote_bind_addresses"] == [
        ("localhost", 8888),
        ("localhost", 8889),
        ("localhost", 8890),
    ]
    assert call_kwargs["local_bind_addresses"] == [
        ("localhost", 8888),
        ("localhost", 8889),
        ("localhost", 8890),
    ]

    mock_tunnel.start.assert_called_once()

    assert port_forward_manager.tunnel == mock_tunnel
    assert port_forward_manager.ports == [(8888, 8888), (8889, 8889), (8890, 8890)]

    expected_info_calls = [
        call("Creating SSH tunnel for port %s...", 8888),
        call("Creating SSH tunnel for port %s...", 8889),
        call("Creating SSH tunnel for port %s...", 8890),
        call("SSH tunnel established: localhost:%s -> remote:%s", 8888, 8888),
        call("SSH tunnel established: localhost:%s -> remote:%s", 8889, 8889),
        call("SSH tunnel established: localhost:%s -> remote:%s", 8890, 8890),
    ]
    assert mock_logger.info.call_args_list == expected_info_calls


@patch("campers.services.portforward.PortForwardManager.validate_key_file")
@patch("campers.services.portforward.validate_port")
@patch("campers.services.portforward.logger")
@patch("campers.services.portforward.SSHTunnelForwarder")
def test_create_tunnels_default_username(
    mock_tunnel_forwarder: MagicMock,
    mock_logger: MagicMock,
    mock_validate_port: MagicMock,
    mock_validate_key_file: MagicMock,
    port_forward_manager: PortForwardManager,
) -> None:
    """Test tunnel creation uses default username when not specified."""
    mock_tunnel = MagicMock()
    mock_tunnel.is_active = True
    mock_tunnel_forwarder.return_value = mock_tunnel

    port_forward_manager.create_tunnels(
        ports=[(8888, 8888)],
        host="203.0.113.1",
        key_file="/tmp/test.pem",
    )

    call_kwargs = mock_tunnel_forwarder.call_args[1]
    assert call_kwargs["ssh_username"] == "ubuntu"


@patch("campers.services.portforward.PortForwardManager.validate_key_file")
@patch("campers.services.portforward.validate_port")
@patch("campers.services.portforward.logger")
@patch("campers.services.portforward.SSHTunnelForwarder")
def test_create_tunnels_failure_raises_runtime_error(
    mock_tunnel_forwarder: MagicMock,
    mock_logger: MagicMock,
    mock_validate_port: MagicMock,
    mock_validate_key_file: MagicMock,
    port_forward_manager: PortForwardManager,
) -> None:
    """Test tunnel creation failure raises RuntimeError."""
    mock_tunnel_forwarder.side_effect = OSError("Port already in use")

    with pytest.raises(RuntimeError, match=r"Failed to create SSH tunnels"):
        port_forward_manager.create_tunnels(
            ports=[(8888, 8888), (8889, 8889)],
            host="203.0.113.1",
            key_file="/tmp/test.pem",
        )

    assert port_forward_manager.tunnel is None
    assert port_forward_manager.ports == []


@patch("campers.services.portforward.PortForwardManager.validate_key_file")
@patch("campers.services.portforward.validate_port")
@patch("campers.services.portforward.logger")
@patch("campers.services.portforward.SSHTunnelForwarder")
def test_create_tunnels_start_failure_raises_runtime_error(
    mock_tunnel_forwarder: MagicMock,
    mock_logger: MagicMock,
    mock_validate_port: MagicMock,
    mock_validate_key_file: MagicMock,
    port_forward_manager: PortForwardManager,
) -> None:
    """Test tunnel start failure raises RuntimeError."""
    mock_tunnel = MagicMock()
    mock_tunnel.start.side_effect = paramiko.SSHException("Connection failed")
    mock_tunnel_forwarder.return_value = mock_tunnel

    with pytest.raises(RuntimeError, match=r"Failed to create SSH tunnels"):
        port_forward_manager.create_tunnels(
            ports=[(8888, 8888), (8889, 8889)],
            host="203.0.113.1",
            key_file="/tmp/test.pem",
        )

    assert port_forward_manager.tunnel is None
    assert port_forward_manager.ports == []


@patch("campers.services.portforward.PortForwardManager.validate_key_file")
@patch("campers.services.portforward.validate_port")
@patch("campers.services.portforward.logger")
@patch("campers.services.portforward.SSHTunnelForwarder")
def test_create_tunnels_empty_port_list(
    mock_tunnel_forwarder: MagicMock,
    mock_logger: MagicMock,
    mock_validate_port: MagicMock,
    mock_validate_key_file: MagicMock,
    port_forward_manager: PortForwardManager,
) -> None:
    """Test that creating tunnels with empty port list returns early."""
    port_forward_manager.create_tunnels(
        ports=[],
        host="203.0.113.1",
        key_file="/tmp/test.pem",
    )

    mock_tunnel_forwarder.assert_not_called()
    assert port_forward_manager.tunnel is None
    assert port_forward_manager.ports == []


@patch("campers.services.portforward.logger")
def test_stop_all_tunnels_success(
    mock_logger: MagicMock, port_forward_manager: PortForwardManager
) -> None:
    """Test stopping all tunnels successfully."""
    mock_tunnel = MagicMock()

    port_forward_manager.tunnel = mock_tunnel
    port_forward_manager.ports = [(8888, 8888), (8889, 8889)]

    port_forward_manager.stop_all_tunnels()

    mock_tunnel.stop.assert_called_once()

    assert port_forward_manager.tunnel is None
    assert port_forward_manager.ports == []

    expected_info_calls = [
        call("Stopping SSH tunnel for port %s...", 8888),
        call("Stopping SSH tunnel for port %s...", 8889),
    ]
    assert mock_logger.info.call_args_list == expected_info_calls


@patch("campers.services.portforward.logger")
def test_stop_all_tunnels_handles_exceptions(
    mock_logger: MagicMock, port_forward_manager: PortForwardManager
) -> None:
    """Test stop_all_tunnels continues even if tunnel stop fails."""
    mock_tunnel = MagicMock()
    mock_tunnel.stop.side_effect = OSError("Stop failed")

    port_forward_manager.tunnel = mock_tunnel
    port_forward_manager.ports = [(8888, 8888)]

    port_forward_manager.stop_all_tunnels()

    mock_tunnel.stop.assert_called_once()

    assert port_forward_manager.tunnel is None
    assert port_forward_manager.ports == []

    mock_logger.warning.assert_called_once()
    args, kwargs = mock_logger.warning.call_args
    assert args[0] == "Error stopping tunnels: %s"
    assert isinstance(args[1], OSError)


@patch("campers.services.portforward.logger")
def test_stop_all_tunnels_empty_state(
    mock_logger: MagicMock, port_forward_manager: PortForwardManager
) -> None:
    """Test stopping all tunnels when no tunnels exist."""
    port_forward_manager.tunnel = None
    port_forward_manager.ports = []

    port_forward_manager.stop_all_tunnels()

    assert port_forward_manager.tunnel is None
    assert port_forward_manager.ports == []
    mock_logger.info.assert_not_called()


@patch("campers.services.portforward.PortForwardManager.validate_key_file")
@patch("campers.services.portforward.validate_port")
@patch("campers.services.portforward.logger")
@patch("campers.services.portforward.SSHTunnelForwarder")
def test_create_tunnels_localhost_binding(
    mock_tunnel_forwarder: MagicMock,
    mock_logger: MagicMock,
    mock_validate_port: MagicMock,
    mock_validate_key_file: MagicMock,
    port_forward_manager: PortForwardManager,
) -> None:
    """Test tunnel binds to localhost only for security."""
    mock_tunnel = MagicMock()
    mock_tunnel.is_active = True
    mock_tunnel_forwarder.return_value = mock_tunnel

    port_forward_manager.create_tunnels(
        ports=[(8888, 8888)],
        host="203.0.113.1",
        key_file="/tmp/test.pem",
    )

    call_kwargs = mock_tunnel_forwarder.call_args[1]

    assert call_kwargs["local_bind_addresses"] == [("localhost", 8888)]
    assert call_kwargs["remote_bind_addresses"] == [("localhost", 8888)]


@patch("campers.services.portforward.PortForwardManager.validate_key_file")
@patch("campers.services.portforward.validate_port")
@patch("campers.services.portforward.logger")
@patch("campers.services.portforward.SSHTunnelForwarder")
def test_create_tunnels_custom_ssh_port(
    mock_tunnel_forwarder: MagicMock,
    mock_logger: MagicMock,
    mock_validate_port: MagicMock,
    mock_validate_key_file: MagicMock,
    port_forward_manager: PortForwardManager,
) -> None:
    """Test tunnel creation with custom SSH port."""
    mock_tunnel = MagicMock()
    mock_tunnel.is_active = True
    mock_tunnel_forwarder.return_value = mock_tunnel

    port_forward_manager.create_tunnels(
        ports=[(8888, 8888)],
        host="203.0.113.1",
        key_file="/tmp/test.pem",
        ssh_port=2222,
    )

    call_kwargs = mock_tunnel_forwarder.call_args[1]
    assert call_kwargs["ssh_address_or_host"] == ("203.0.113.1", 2222)


@patch("campers.services.portforward.logger")
def test_stop_all_tunnels_multiple_times_idempotent(
    mock_logger: MagicMock, port_forward_manager: PortForwardManager
) -> None:
    """Test calling stop_all_tunnels() multiple times is idempotent."""
    mock_tunnel = MagicMock()
    port_forward_manager.tunnel = mock_tunnel
    port_forward_manager.ports = [(8888, 8888)]

    port_forward_manager.stop_all_tunnels()
    assert port_forward_manager.tunnel is None
    assert port_forward_manager.ports == []

    port_forward_manager.stop_all_tunnels()
    assert port_forward_manager.tunnel is None
    assert port_forward_manager.ports == []

    mock_tunnel.stop.assert_called_once()


@patch("campers.services.portforward.PortForwardManager.validate_key_file")
@patch("campers.services.portforward.validate_port")
@patch("campers.services.portforward.logger")
@patch("campers.services.portforward.SSHTunnelForwarder")
def test_port_already_in_use_error(
    mock_tunnel_forwarder: MagicMock,
    mock_logger: MagicMock,
    mock_validate_port: MagicMock,
    mock_validate_key_file: MagicMock,
    port_forward_manager: PortForwardManager,
) -> None:
    """Test port already in use error handling."""
    mock_tunnel_forwarder.side_effect = OSError("Address already in use")

    with pytest.raises(RuntimeError, match=r"Failed to create SSH tunnels"):
        port_forward_manager.create_tunnels(
            ports=[(8888, 8888)],
            host="203.0.113.1",
            key_file="/tmp/test.pem",
        )

    assert port_forward_manager.tunnel is None
    assert port_forward_manager.ports == []


@patch("campers.services.portforward.PortForwardManager.validate_key_file")
@patch("campers.services.portforward.validate_port")
@patch("campers.services.portforward.logger")
@patch("campers.services.portforward.SSHTunnelForwarder")
def test_authentication_failure_invalid_key(
    mock_tunnel_forwarder: MagicMock,
    mock_logger: MagicMock,
    mock_validate_port: MagicMock,
    mock_validate_key_file: MagicMock,
    port_forward_manager: PortForwardManager,
) -> None:
    """Test authentication failure with invalid key file."""
    mock_tunnel_forwarder.side_effect = paramiko.SSHException("Authentication failed")

    with pytest.raises(RuntimeError, match=r"Failed to create SSH tunnels"):
        port_forward_manager.create_tunnels(
            ports=[(8888, 8888)],
            host="203.0.113.1",
            key_file="/tmp/test.pem",
        )

    assert port_forward_manager.tunnel is None
    assert port_forward_manager.ports == []


@patch("campers.services.portforward.PortForwardManager.validate_key_file")
@patch("campers.services.portforward.validate_port")
@patch("campers.services.portforward.logger")
@patch("campers.services.portforward.SSHTunnelForwarder")
def test_sshtunnel_base_error_handling(
    mock_tunnel_forwarder: MagicMock,
    mock_logger: MagicMock,
    mock_validate_port: MagicMock,
    mock_validate_key_file: MagicMock,
    port_forward_manager: PortForwardManager,
) -> None:
    """Test handling of BaseSSHTunnelForwarderError."""
    mock_tunnel_forwarder.side_effect = BaseSSHTunnelForwarderError("SSH tunnel error")

    with pytest.raises(RuntimeError, match=r"Failed to create SSH tunnels"):
        port_forward_manager.create_tunnels(
            ports=[(8888, 8888)],
            host="203.0.113.1",
            key_file="/tmp/test.pem",
        )

    assert port_forward_manager.tunnel is None
    assert port_forward_manager.ports == []


@patch("campers.services.portforward.is_port_in_use", return_value=False)
@patch("campers.services.portforward.PortForwardManager.validate_key_file")
@patch("campers.services.portforward.validate_port")
@patch("campers.services.portforward.logger")
@patch("campers.services.portforward.SSHTunnelForwarder")
def test_create_tunnels_multiple_ports_different_values(
    mock_tunnel_forwarder: MagicMock,
    mock_logger: MagicMock,
    mock_validate_port: MagicMock,
    mock_validate_key_file: MagicMock,
    mock_is_port_in_use: MagicMock,
    port_forward_manager: PortForwardManager,
) -> None:
    """Test creating tunnels with different port values."""
    mock_tunnel = MagicMock()
    mock_tunnel.is_active = True
    mock_tunnel_forwarder.return_value = mock_tunnel

    port_forward_manager.create_tunnels(
        ports=[(8080, 8080), (5000, 5000), (9000, 9000)],
        host="203.0.113.1",
        key_file="/tmp/test.pem",
    )

    call_kwargs = mock_tunnel_forwarder.call_args[1]
    assert call_kwargs["remote_bind_addresses"] == [
        ("localhost", 8080),
        ("localhost", 5000),
        ("localhost", 9000),
    ]
    assert call_kwargs["local_bind_addresses"] == [
        ("localhost", 8080),
        ("localhost", 5000),
        ("localhost", 9000),
    ]

    assert port_forward_manager.ports == [(8080, 8080), (5000, 5000), (9000, 9000)]
