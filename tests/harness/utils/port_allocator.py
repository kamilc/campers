"""Thread-safe port allocation for testing."""

import logging
import socket
import threading

logger = logging.getLogger(__name__)


class PortAllocator:
    """Thread-safe port allocator for SSH forwarding and testing.

    Maintains a pool of available ports and allocates/deallocates them
    with verification to avoid conflicts.

    Attributes
    ----------
    start_port : int
        Starting port number in range
    end_port : int
        Ending port number in range (inclusive)
    available_ports : set[int]
        Set of ports available for allocation
    allocated_ports : set[int]
        Set of currently allocated ports
    _lock : threading.Lock
        Protects concurrent access to port sets
    """

    def __init__(self, start_port: int = 20000, end_port: int = 30000) -> None:
        self.start_port = start_port
        self.end_port = end_port
        self.available_ports = set(range(start_port, end_port + 1))
        self.allocated_ports: set[int] = set()
        self._lock = threading.Lock()

    def is_port_available(self, port: int) -> bool:
        """Check if a port is available for binding.

        Parameters
        ----------
        port : int
            Port number to check

        Returns
        -------
        bool
            True if port can be bound, False otherwise
        """
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("127.0.0.1", port))
            sock.close()
            return True
        except OSError:
            return False

    def allocate(self) -> int:
        """Allocate an available port.

        Returns
        -------
        int
            Allocated port number

        Raises
        ------
        RuntimeError
            If no ports available
        """
        with self._lock:
            for port in list(self.available_ports):
                if self.is_port_available(port):
                    self.available_ports.discard(port)
                    self.allocated_ports.add(port)
                    logger.debug(f"Allocated port {port}")
                    return port

            raise RuntimeError(
                f"No available ports in range {self.start_port}-{self.end_port}"
            )

    def deallocate(self, port: int) -> None:
        """Return a port to the available pool.

        Parameters
        ----------
        port : int
            Port number to deallocate
        """
        with self._lock:
            if port in self.allocated_ports:
                self.allocated_ports.discard(port)
                self.available_ports.add(port)
                logger.debug(f"Deallocated port {port}")

    def reset(self) -> None:
        """Reset all ports back to available pool."""
        with self._lock:
            self.available_ports = set(range(self.start_port, self.end_port + 1))
            self.allocated_ports.clear()
            logger.debug("Reset port allocator")
