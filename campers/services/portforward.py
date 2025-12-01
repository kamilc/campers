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

from campers.constants import DEFAULT_SSH_PORT, DEFAULT_SSH_USERNAME, PRIVILEGED_PORT_THRESHOLD
from campers.services.validation import validate_port

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
        """Initialize PortForwardManager.

        Initializes the port forward manager with no active tunnels.
        Tunnels are created and managed through the create_tunnels() method.
        """
        self.tunnel: SSHTunnelForwarder | None = None
        self.ports: list[int] = []

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
        username: str = DEFAULT_SSH_USERNAME,
        ssh_port: int = DEFAULT_SSH_PORT,
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

        Notes
        -----
        When CAMPERS_TEST_MODE environment variable is set to "1", tunnels are
        created in mock mode for testing purposes. No actual SSH connections are
        established; instead, tunnel creation is simulated for test harness integration.
        """
        if not ports:
            return

        for port in ports:
            validate_port(port)
            if port < PRIVILEGED_PORT_THRESHOLD:
                logger.warning(
                    "Port %s is a privileged port (< %s). "
                    "Root privileges may be required on the local machine.",
                    port,
                    PRIVILEGED_PORT_THRESHOLD,
                )
        self.validate_key_file(key_file)

        if os.getenv("CAMPERS_TEST_MODE") == "1":
            for port in ports:
                logger.info("Creating SSH tunnel for port %s...", port)

            for port in ports:
                logger.info("SSH tunnel established: localhost:%s -> remote:%s", port, port)

            self.ports = ports
            return

        remote_binds = [("localhost", port) for port in ports]
        local_binds = [("localhost", port) for port in ports]

        try:
            for port in ports:
                logger.info("Creating SSH tunnel for port %s...", port)

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
                logger.info("SSH tunnel established: localhost:%s -> remote:%s", port, port)

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
                logger.info("Stopping SSH tunnel for port %s...", port)

            try:
                self.tunnel.stop()
            except (BaseSSHTunnelForwarderError, OSError) as e:
                logger.warning("Error stopping tunnels: %s", e)

            self.tunnel = None
            self.ports = []
