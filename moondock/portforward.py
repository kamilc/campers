"""SSH port forwarding management using sshtunnel library.

This module provides a manager class for creating and managing SSH port forwarding
tunnels using the sshtunnel library. It handles multiple concurrent tunnels and
ensures proper cleanup on errors.

Classes
-------
PortForwardManager
    Manager for SSH port forwarding tunnels

Examples
--------
>>> manager = PortForwardManager()
>>> manager.create_tunnels([8888, 8080], "10.0.1.50", "/path/to/key.pem")
>>> manager.stop_all_tunnels()

Notes
-----
Uses sshtunnel.BaseSSHTunnelForwarderError and paramiko.SSHException for
specific exception handling. Falls back to OSError for port binding issues.
"""

import logging
import os
from pathlib import Path

import paramiko
from sshtunnel import BaseSSHTunnelForwarderError, SSHTunnelForwarder

logger = logging.getLogger(__name__)


class PortForwardManager:
    """Manages SSH port forwarding tunnels using sshtunnel library.

    Attributes
    ----------
    tunnels : list[tuple[int, SSHTunnelForwarder]]
        List of (port, tunnel) tuples for active tunnels
    """

    def __init__(self) -> None:
        """Initialize PortForwardManager."""
        self.tunnels: list[tuple[int, SSHTunnelForwarder]] = []

    def validate_port(self, port: int) -> None:
        """Validate port number is in valid range.

        Parameters
        ----------
        port : int
            Port number to validate

        Raises
        ------
        ValueError
            If port is not in range 1-65535
        """
        if not 1 <= port <= 65535:
            raise ValueError(f"Port {port} is not in valid range 1-65535")

        if port < 1024:
            logger.warning(
                f"Port {port} is a privileged port (< 1024). "
                "Root privileges may be required on the local machine."
            )

    def validate_key_file(self, key_file: str) -> None:
        """Validate SSH key file exists and is accessible.

        Parameters
        ----------
        key_file : str
            Path to SSH private key file

        Raises
        ------
        FileNotFoundError
            If key file does not exist
        PermissionError
            If key file is not readable
        """
        key_path = Path(key_file)

        if not key_path.exists():
            raise FileNotFoundError(f"SSH key file not found: {key_file}")

        if not key_path.is_file():
            raise ValueError(f"SSH key path is not a file: {key_file}")

        if not os.access(key_file, os.R_OK):
            raise PermissionError(f"SSH key file is not readable: {key_file}")

    def create_tunnel(
        self,
        port: int,
        host: str,
        key_file: str,
        username: str = "ubuntu",
        ssh_port: int = 22,
    ) -> None:
        """Create SSH tunnel for a single port.

        Parameters
        ----------
        port : int
            Port to forward (same local and remote)
        host : str
            Remote host IP address
        key_file : str
            Path to SSH private key file
        username : str
            SSH username (default: ubuntu)
        ssh_port : int
            SSH port on remote host (default: 22)

        Raises
        ------
        RuntimeError
            If tunnel creation or start fails
        ValueError
            If port is not in valid range
        FileNotFoundError
            If key file does not exist
        PermissionError
            If key file is not readable
        """
        self.validate_port(port)
        self.validate_key_file(key_file)

        try:
            tunnel = SSHTunnelForwarder(
                ssh_address_or_host=(host, ssh_port),
                ssh_username=username,
                ssh_pkey=key_file,
                remote_bind_address=("localhost", port),
                local_bind_address=("localhost", port),
            )

            tunnel.start()

            if not tunnel.is_active:
                raise RuntimeError(
                    f"SSH tunnel for port {port} failed to start - tunnel is not active"
                )

            self.tunnels.append((port, tunnel))

        except (
            BaseSSHTunnelForwarderError,
            paramiko.SSHException,
            OSError,
        ) as e:
            raise RuntimeError(
                f"Failed to create SSH tunnel for port {port}: {e}"
            ) from e

    def create_tunnels(
        self,
        ports: list[int],
        host: str,
        key_file: str,
        username: str = "ubuntu",
        ssh_port: int = 22,
    ) -> None:
        """Create SSH tunnels for multiple ports.

        If any tunnel fails, stops all successfully created tunnels and raises.

        Parameters
        ----------
        ports : list[int]
            List of ports to forward
        host : str
            Remote host IP address
        key_file : str
            Path to SSH private key file
        username : str
            SSH username (default: ubuntu)
        ssh_port : int
            SSH port on remote host (default: 22)

        Raises
        ------
        RuntimeError
            If any tunnel creation fails
        """
        for port in ports:
            try:
                logger.info(f"Creating SSH tunnel for port {port}...")
                self.create_tunnel(port, host, key_file, username, ssh_port)
                logger.info(
                    f"SSH tunnel established: localhost:{port} -> remote:{port}"
                )
            except RuntimeError as e:
                logger.error(f"Failed to create tunnel for port {port}: {e}")
                self.stop_all_tunnels()
                raise

    def stop_all_tunnels(self) -> None:
        """Stop all active SSH tunnels."""
        for port, tunnel in self.tunnels:
            try:
                logger.info(f"Stopping SSH tunnel for port {port}...")
                tunnel.stop()
            except (BaseSSHTunnelForwarderError, OSError) as e:
                logger.warning(f"Error stopping tunnel for port {port}: {e}")

        self.tunnels.clear()
