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
    tunnel : SSHTunnelForwarder | None
        Single SSH tunnel forwarder instance for all ports
    ports : list[int]
        List of ports managed by the forwarder
    """

    def __init__(self) -> None:
        """Initialize PortForwardManager."""
        self.tunnel: SSHTunnelForwarder | None = None
        self.ports: list[int] = []

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

    def create_tunnels(
        self,
        ports: list[int],
        host: str,
        key_file: str,
        username: str = "ubuntu",
        ssh_port: int = 22,
    ) -> None:
        """Create SSH tunnels for multiple ports using single SSHTunnelForwarder.

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
            If tunnel creation fails
        """
        if not ports:
            return

        for port in ports:
            self.validate_port(port)
        self.validate_key_file(key_file)

        if os.getenv("MOONDOCK_TEST_MODE") == "1":
            for port in ports:
                logger.info(f"Creating SSH tunnel for port {port}...")

            for port in ports:
                logger.info(
                    f"SSH tunnel established: localhost:{port} -> remote:{port}"
                )

            self.ports = ports
            return

        remote_binds = [("localhost", port) for port in ports]
        local_binds = [("localhost", port) for port in ports]

        try:
            for port in ports:
                logger.info(f"Creating SSH tunnel for port {port}...")

            tunnel = SSHTunnelForwarder(
                ssh_address_or_host=(host, ssh_port),
                ssh_username=username,
                ssh_pkey=key_file,
                remote_bind_addresses=remote_binds,
                local_bind_addresses=local_binds,
            )
            tunnel.skip_tunnel_checkup = True

            tunnel.start()

            self.tunnel = tunnel
            self.ports = ports

            for port in ports:
                logger.info(
                    f"SSH tunnel established: localhost:{port} -> remote:{port}"
                )

        except (
            BaseSSHTunnelForwarderError,
            paramiko.SSHException,
            OSError,
        ) as e:
            self.stop_all_tunnels()
            raise RuntimeError(f"Failed to create SSH tunnels: {e}") from e

    def stop_all_tunnels(self) -> None:
        """Stop the SSH tunnel forwarder."""
        if self.tunnel:
            for port in self.ports:
                logger.info(f"Stopping SSH tunnel for port {port}...")

            try:
                self.tunnel.stop()
            except (BaseSSHTunnelForwarderError, OSError) as e:
                logger.warning(f"Error stopping tunnels: {e}")

            self.tunnel = None
            self.ports = []
