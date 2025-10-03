"""Unit tests for SSH port forwarding functionality."""

from unittest.mock import MagicMock, call, patch

import paramiko
import pytest
from sshtunnel import BaseSSHTunnelForwarderError

from moondock.portforward import PortForwardManager


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
    """Test PortForwardManager initialization creates empty tunnel list."""
    manager = PortForwardManager()

    assert manager.tunnels == []


@patch("moondock.portforward.PortForwardManager.validate_key_file")
@patch("moondock.portforward.PortForwardManager.validate_port")
@patch("moondock.portforward.SSHTunnelForwarder")
def test_create_tunnel_success(
    mock_tunnel_forwarder: MagicMock,
    mock_validate_port: MagicMock,
    mock_validate_key_file: MagicMock,
    port_forward_manager: PortForwardManager,
) -> None:
    """Test successful creation of a single SSH tunnel."""
    mock_tunnel = MagicMock()
    mock_tunnel.is_active = True
    mock_tunnel_forwarder.return_value = mock_tunnel

    port_forward_manager.create_tunnel(
        port=8888, host="203.0.113.1", key_file="/tmp/test.pem", username="ubuntu"
    )

    mock_validate_port.assert_called_once_with(8888)
    mock_validate_key_file.assert_called_once_with("/tmp/test.pem")
    mock_tunnel_forwarder.assert_called_once_with(
        ssh_address_or_host=("203.0.113.1", 22),
        ssh_username="ubuntu",
        ssh_pkey="/tmp/test.pem",
        remote_bind_address=("localhost", 8888),
        local_bind_address=("localhost", 8888),
    )
    mock_tunnel.start.assert_called_once()
    assert port_forward_manager.tunnels == [(8888, mock_tunnel)]


@patch("moondock.portforward.PortForwardManager.validate_key_file")
@patch("moondock.portforward.PortForwardManager.validate_port")
@patch("moondock.portforward.SSHTunnelForwarder")
def test_create_tunnel_default_username(
    mock_tunnel_forwarder: MagicMock,
    mock_validate_port: MagicMock,
    mock_validate_key_file: MagicMock,
    port_forward_manager: PortForwardManager,
) -> None:
    """Test tunnel creation uses default username when not specified."""
    mock_tunnel = MagicMock()
    mock_tunnel.is_active = True
    mock_tunnel_forwarder.return_value = mock_tunnel

    port_forward_manager.create_tunnel(
        port=8888, host="203.0.113.1", key_file="/tmp/test.pem"
    )

    mock_tunnel_forwarder.assert_called_once_with(
        ssh_address_or_host=("203.0.113.1", 22),
        ssh_username="ubuntu",
        ssh_pkey="/tmp/test.pem",
        remote_bind_address=("localhost", 8888),
        local_bind_address=("localhost", 8888),
    )


@patch("moondock.portforward.PortForwardManager.validate_key_file")
@patch("moondock.portforward.PortForwardManager.validate_port")
@patch("moondock.portforward.SSHTunnelForwarder")
def test_create_tunnel_failure_raises_runtime_error(
    mock_tunnel_forwarder: MagicMock,
    mock_validate_port: MagicMock,
    mock_validate_key_file: MagicMock,
    port_forward_manager: PortForwardManager,
) -> None:
    """Test tunnel creation failure raises RuntimeError with port number."""
    mock_tunnel_forwarder.side_effect = OSError("Port already in use")

    with pytest.raises(
        RuntimeError, match=r"Failed to create SSH tunnel for port 8888"
    ):
        port_forward_manager.create_tunnel(
            port=8888, host="203.0.113.1", key_file="/tmp/test.pem"
        )

    assert port_forward_manager.tunnels == []


@patch("moondock.portforward.PortForwardManager.validate_key_file")
@patch("moondock.portforward.PortForwardManager.validate_port")
@patch("moondock.portforward.SSHTunnelForwarder")
def test_create_tunnel_start_failure_raises_runtime_error(
    mock_tunnel_forwarder: MagicMock,
    mock_validate_port: MagicMock,
    mock_validate_key_file: MagicMock,
    port_forward_manager: PortForwardManager,
) -> None:
    """Test tunnel start failure raises RuntimeError with port number."""
    mock_tunnel = MagicMock()
    mock_tunnel.start.side_effect = paramiko.SSHException("Connection failed")
    mock_tunnel_forwarder.return_value = mock_tunnel

    with pytest.raises(
        RuntimeError, match=r"Failed to create SSH tunnel for port 8888"
    ):
        port_forward_manager.create_tunnel(
            port=8888, host="203.0.113.1", key_file="/tmp/test.pem"
        )

    assert port_forward_manager.tunnels == []


@patch("moondock.portforward.PortForwardManager.validate_key_file")
@patch("moondock.portforward.PortForwardManager.validate_port")
@patch("moondock.portforward.logger")
@patch("moondock.portforward.SSHTunnelForwarder")
def test_create_tunnels_success_multiple_ports(
    mock_tunnel_forwarder: MagicMock,
    mock_logger: MagicMock,
    mock_validate_port: MagicMock,
    mock_validate_key_file: MagicMock,
    port_forward_manager: PortForwardManager,
) -> None:
    """Test successful creation of multiple SSH tunnels."""
    mock_tunnel_1 = MagicMock()
    mock_tunnel_1.is_active = True
    mock_tunnel_2 = MagicMock()
    mock_tunnel_2.is_active = True
    mock_tunnel_3 = MagicMock()
    mock_tunnel_3.is_active = True
    mock_tunnel_forwarder.side_effect = [mock_tunnel_1, mock_tunnel_2, mock_tunnel_3]

    port_forward_manager.create_tunnels(
        ports=[8888, 6006, 5000],
        host="203.0.113.1",
        key_file="/tmp/test.pem",
        username="ubuntu",
    )

    assert mock_tunnel_forwarder.call_count == 3
    assert mock_tunnel_1.start.call_count == 1
    assert mock_tunnel_2.start.call_count == 1
    assert mock_tunnel_3.start.call_count == 1

    assert port_forward_manager.tunnels == [
        (8888, mock_tunnel_1),
        (6006, mock_tunnel_2),
        (5000, mock_tunnel_3),
    ]

    expected_info_calls = [
        call("Creating SSH tunnel for port 8888..."),
        call("SSH tunnel established: localhost:8888 -> remote:8888"),
        call("Creating SSH tunnel for port 6006..."),
        call("SSH tunnel established: localhost:6006 -> remote:6006"),
        call("Creating SSH tunnel for port 5000..."),
        call("SSH tunnel established: localhost:5000 -> remote:5000"),
    ]
    assert mock_logger.info.call_args_list == expected_info_calls


@patch("moondock.portforward.PortForwardManager.validate_key_file")
@patch("moondock.portforward.PortForwardManager.validate_port")
@patch("moondock.portforward.logger")
@patch("moondock.portforward.SSHTunnelForwarder")
def test_create_tunnels_partial_failure_stops_all(
    mock_tunnel_forwarder: MagicMock,
    mock_logger: MagicMock,
    mock_validate_port: MagicMock,
    mock_validate_key_file: MagicMock,
    port_forward_manager: PortForwardManager,
) -> None:
    """Test that if any tunnel fails, all successfully created tunnels are stopped."""
    mock_tunnel_1 = MagicMock()
    mock_tunnel_1.is_active = True
    mock_tunnel_2 = MagicMock()
    mock_tunnel_2.is_active = True
    mock_tunnel_forwarder.side_effect = [
        mock_tunnel_1,
        mock_tunnel_2,
        OSError("Port 5000 already in use"),
    ]

    with pytest.raises(RuntimeError):
        port_forward_manager.create_tunnels(
            ports=[8888, 6006, 5000],
            host="203.0.113.1",
            key_file="/tmp/test.pem",
            username="ubuntu",
        )

    mock_tunnel_1.stop.assert_called_once()
    mock_tunnel_2.stop.assert_called_once()

    assert port_forward_manager.tunnels == []

    mock_logger.error.assert_called_once()


@patch("moondock.portforward.PortForwardManager.validate_key_file")
@patch("moondock.portforward.PortForwardManager.validate_port")
@patch("moondock.portforward.logger")
@patch("moondock.portforward.SSHTunnelForwarder")
def test_create_tunnels_failure_first_port(
    mock_tunnel_forwarder: MagicMock,
    mock_logger: MagicMock,
    mock_validate_port: MagicMock,
    mock_validate_key_file: MagicMock,
    port_forward_manager: PortForwardManager,
) -> None:
    """Test that failure on first port raises exception immediately."""
    mock_tunnel_forwarder.side_effect = paramiko.SSHException("Connection failed")

    with pytest.raises(RuntimeError):
        port_forward_manager.create_tunnels(
            ports=[8888, 6006],
            host="203.0.113.1",
            key_file="/tmp/test.pem",
            username="ubuntu",
        )

    assert port_forward_manager.tunnels == []
    mock_logger.error.assert_called_once()


@patch("moondock.portforward.logger")
def test_stop_all_tunnels_success(
    mock_logger: MagicMock, port_forward_manager: PortForwardManager
) -> None:
    """Test stopping all tunnels successfully."""
    mock_tunnel_1 = MagicMock()
    mock_tunnel_2 = MagicMock()

    port_forward_manager.tunnels = [(8888, mock_tunnel_1), (6006, mock_tunnel_2)]

    port_forward_manager.stop_all_tunnels()

    mock_tunnel_1.stop.assert_called_once()
    mock_tunnel_2.stop.assert_called_once()

    assert port_forward_manager.tunnels == []

    expected_info_calls = [
        call("Stopping SSH tunnel for port 8888..."),
        call("Stopping SSH tunnel for port 6006..."),
    ]
    assert mock_logger.info.call_args_list == expected_info_calls


@patch("moondock.portforward.logger")
def test_stop_all_tunnels_handles_exceptions(
    mock_logger: MagicMock, port_forward_manager: PortForwardManager
) -> None:
    """Test stop_all_tunnels continues even if one tunnel stop fails."""
    mock_tunnel_1 = MagicMock()
    mock_tunnel_2 = MagicMock()
    mock_tunnel_1.stop.side_effect = OSError("Stop failed")

    port_forward_manager.tunnels = [(8888, mock_tunnel_1), (6006, mock_tunnel_2)]

    port_forward_manager.stop_all_tunnels()

    mock_tunnel_1.stop.assert_called_once()
    mock_tunnel_2.stop.assert_called_once()

    assert port_forward_manager.tunnels == []

    mock_logger.warning.assert_called_once_with(
        "Error stopping tunnel for port 8888: Stop failed"
    )


@patch("moondock.portforward.logger")
def test_stop_all_tunnels_empty_list(
    mock_logger: MagicMock, port_forward_manager: PortForwardManager
) -> None:
    """Test stopping all tunnels when no tunnels exist."""
    port_forward_manager.tunnels = []

    port_forward_manager.stop_all_tunnels()

    assert port_forward_manager.tunnels == []
    mock_logger.info.assert_not_called()


@patch("moondock.portforward.PortForwardManager.validate_key_file")
@patch("moondock.portforward.PortForwardManager.validate_port")
@patch("moondock.portforward.SSHTunnelForwarder")
def test_create_tunnel_localhost_binding(
    mock_tunnel_forwarder: MagicMock,
    mock_validate_port: MagicMock,
    mock_validate_key_file: MagicMock,
    port_forward_manager: PortForwardManager,
) -> None:
    """Test tunnel binds to localhost only for security."""
    mock_tunnel = MagicMock()
    mock_tunnel.is_active = True
    mock_tunnel_forwarder.return_value = mock_tunnel

    port_forward_manager.create_tunnel(
        port=8888, host="203.0.113.1", key_file="/tmp/test.pem"
    )

    call_kwargs = mock_tunnel_forwarder.call_args[1]

    assert call_kwargs["local_bind_address"] == ("localhost", 8888)
    assert call_kwargs["remote_bind_address"] == ("localhost", 8888)
    assert call_kwargs["local_bind_address"] != ("0.0.0.0", 8888)


@patch("moondock.portforward.PortForwardManager.validate_key_file")
@patch("moondock.portforward.PortForwardManager.validate_port")
@patch("moondock.portforward.SSHTunnelForwarder")
def test_create_tunnel_same_port_local_and_remote(
    mock_tunnel_forwarder: MagicMock,
    mock_validate_port: MagicMock,
    mock_validate_key_file: MagicMock,
    port_forward_manager: PortForwardManager,
) -> None:
    """Test tunnel forwards from same local port to same remote port."""
    mock_tunnel = MagicMock()
    mock_tunnel.is_active = True
    mock_tunnel_forwarder.return_value = mock_tunnel

    port_forward_manager.create_tunnel(
        port=8888, host="203.0.113.1", key_file="/tmp/test.pem"
    )

    call_kwargs = mock_tunnel_forwarder.call_args[1]

    local_port = call_kwargs["local_bind_address"][1]
    remote_port = call_kwargs["remote_bind_address"][1]

    assert local_port == remote_port == 8888


@patch("moondock.portforward.PortForwardManager.validate_key_file")
@patch("moondock.portforward.PortForwardManager.validate_port")
@patch("moondock.portforward.SSHTunnelForwarder")
def test_port_already_in_use_error(
    mock_tunnel_forwarder: MagicMock,
    mock_validate_port: MagicMock,
    mock_validate_key_file: MagicMock,
    port_forward_manager: PortForwardManager,
) -> None:
    """Test port already in use error handling."""
    mock_tunnel_forwarder.side_effect = OSError("Address already in use")

    with pytest.raises(
        RuntimeError, match=r"Failed to create SSH tunnel for port 8888"
    ):
        port_forward_manager.create_tunnel(
            port=8888, host="203.0.113.1", key_file="/tmp/test.pem"
        )

    assert port_forward_manager.tunnels == []


@patch("moondock.portforward.PortForwardManager.validate_key_file")
@patch("moondock.portforward.PortForwardManager.validate_port")
@patch("moondock.portforward.SSHTunnelForwarder")
def test_authentication_failure_invalid_key(
    mock_tunnel_forwarder: MagicMock,
    mock_validate_port: MagicMock,
    mock_validate_key_file: MagicMock,
    port_forward_manager: PortForwardManager,
) -> None:
    """Test authentication failure with invalid key file."""
    mock_tunnel_forwarder.side_effect = paramiko.SSHException("Authentication failed")

    with pytest.raises(
        RuntimeError, match=r"Failed to create SSH tunnel for port 8888"
    ):
        port_forward_manager.create_tunnel(
            port=8888, host="203.0.113.1", key_file="/tmp/test.pem"
        )

    assert port_forward_manager.tunnels == []


@patch("moondock.portforward.logger")
def test_stop_all_tunnels_multiple_times_idempotent(
    mock_logger: MagicMock, port_forward_manager: PortForwardManager
) -> None:
    """Test calling stop_all_tunnels() multiple times is idempotent."""
    mock_tunnel = MagicMock()
    port_forward_manager.tunnels = [(8888, mock_tunnel)]

    port_forward_manager.stop_all_tunnels()
    assert port_forward_manager.tunnels == []

    port_forward_manager.stop_all_tunnels()
    assert port_forward_manager.tunnels == []

    mock_tunnel.stop.assert_called_once()


@patch("moondock.portforward.PortForwardManager.validate_key_file")
@patch("moondock.portforward.PortForwardManager.validate_port")
@patch("moondock.portforward.SSHTunnelForwarder")
def test_sshtunnel_base_error_handling(
    mock_tunnel_forwarder: MagicMock,
    mock_validate_port: MagicMock,
    mock_validate_key_file: MagicMock,
    port_forward_manager: PortForwardManager,
) -> None:
    """Test handling of BaseSSHTunnelForwarderError."""
    mock_tunnel_forwarder.side_effect = BaseSSHTunnelForwarderError("SSH tunnel error")

    with pytest.raises(
        RuntimeError, match=r"Failed to create SSH tunnel for port 8888"
    ):
        port_forward_manager.create_tunnel(
            port=8888, host="203.0.113.1", key_file="/tmp/test.pem"
        )
