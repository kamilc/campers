"""Thread-safe pool managing SSH container allocations."""

from __future__ import annotations

import socket
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List


class PortExhaustedError(Exception):
    """Raised when no additional ports are available for allocation."""


@dataclass
class SSHContainerRecord:
    """Metadata describing a tracked SSH container.

    Attributes
    ----------
    instance_id : str
        EC2 instance identifier associated with the container.
    container_id : str
        Docker container identifier.
    port : int | None
        Forwarded SSH port on the host machine (``None`` when SSH is blocked).
    created_at : float
        Creation timestamp in seconds since the epoch.
    metadata : dict[str, Any]
        Arbitrary metadata captured during provisioning.
    """

    instance_id: str
    container_id: str
    port: int | None
    created_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


class SSHContainerPool:
    """Manage SSH container lifecycle and port allocation.

    Attributes
    ----------
    _base_port : int
        Starting host port for allocation sequence.
    _max_containers_per_instance : int
        Maximum number of containers allowed per instance.
    _port_probe : Callable[[int], bool]
        Callable used to verify port availability.
    _lock : threading.RLock
        Synchronization primitive guarding internal state.
    _next_port : int
        Next candidate port for allocation.
    _allocated_ports : dict[str, list[int]]
        Mapping of instance identifiers to allocated ports.
    _in_use_ports : set[int]
        Set of ports currently allocated.
    _recycled_ports : list[int]
        Stack of ports available for reuse.
    _containers : dict[str, SSHContainerRecord]
        Tracked container metadata keyed by container identifier.
    """

    def __init__(
        self,
        base_port: int = 49152,
        max_containers_per_instance: int = 5,
        port_probe: Callable[[int], bool] | None = None,
    ) -> None:
        """Initialize pool configuration.

        Parameters
        ----------
        base_port : int, optional
            Starting host port for allocations.
        max_containers_per_instance : int, optional
            Maximum number of containers allowed per instance.
        port_probe : Callable[[int], bool] | None, optional
            Callable used to verify port availability.
        """
        self._base_port = base_port
        self._max_containers_per_instance = max_containers_per_instance
        self._port_probe = port_probe or self._probe_port
        self._lock = threading.RLock()
        self._next_port = base_port
        self._allocated_ports: Dict[str, List[int]] = {}
        self._in_use_ports: set[int] = set()
        self._recycled_ports: List[int] = []
        self._containers: Dict[str, SSHContainerRecord] = {}

    def allocate_port(self, instance_id: str) -> int:
        """Allocate a unique port for the provided instance.

        Parameters
        ----------
        instance_id : str
            Instance identifier requesting the port.

        Returns
        -------
        int
            Allocated host port number.

        Raises
        ------
        PortExhaustedError
            If the instance has reached the allocation limit.
        RuntimeError
            If no free ports are available on the host.
        """
        with self._lock:
            ports = self._allocated_ports.setdefault(instance_id, [])
            if len(ports) >= self._max_containers_per_instance:
                raise PortExhaustedError(
                    f"Instance '{instance_id}' reached allocation limit"
                )

            port = self._next_available_port()
            ports.append(port)
            self._in_use_ports.add(port)
            return port

    def release_port(self, instance_id: str, port: int) -> None:
        """Release a previously allocated port.

        Parameters
        ----------
        instance_id : str
            Instance identifier associated with the port.
        port : int
            Port to release.

        Raises
        ------
        KeyError
            If the port is not tracked for the instance.
        """
        with self._lock:
            ports = self._allocated_ports.get(instance_id)
            if ports is None or port not in ports:
                raise KeyError(f"Port {port} not tracked for instance '{instance_id}'")

            ports.remove(port)
            self._in_use_ports.discard(port)
            self._recycled_ports.append(port)

    def track_container(
        self,
        container_id: str,
        instance_id: str,
        port: int | None,
        metadata: dict[str, Any] | None = None,
    ) -> SSHContainerRecord:
        """Track container metadata for diagnostics and cleanup.

        Parameters
        ----------
        container_id : str
            Docker container identifier.
        instance_id : str
            Associated instance identifier.
        port : int
            Allocated host port.
        metadata : dict[str, Any] | None, optional
            Additional metadata provided by the caller.

        Returns
        -------
        SSHContainerRecord
            Recorded container metadata.
        """
        record = SSHContainerRecord(
            instance_id=instance_id,
            container_id=container_id,
            port=port,
            metadata=metadata or {},
        )
        with self._lock:
            self._containers[container_id] = record
        return record

    def release_container(self, container_id: str) -> None:
        """Release container metadata and associated port.

        Parameters
        ----------
        container_id : str
            Docker container identifier to remove from tracking.
        """
        with self._lock:
            record = self._containers.pop(container_id, None)
            if record is None:
                return
            if record.port is not None:
                self.release_port(record.instance_id, record.port)

    def list_containers(self) -> list[SSHContainerRecord]:
        """Return a snapshot of tracked container metadata.

        Returns
        -------
        list[SSHContainerRecord]
            Current container records.
        """
        with self._lock:
            return list(self._containers.values())

    def allocated_ports(self, instance_id: str) -> list[int]:
        """Return allocated ports for the provided instance.

        Parameters
        ----------
        instance_id : str
            Instance identifier whose allocations are requested.

        Returns
        -------
        list[int]
            Allocated ports for the instance.
        """
        with self._lock:
            return list(self._allocated_ports.get(instance_id, []))

    def _next_available_port(self) -> int:
        """Find the next available host port."""
        if self._recycled_ports:
            return self._recycled_ports.pop()

        while True:
            port = self._next_port
            self._next_port += 1
            if port in self._in_use_ports:
                continue
            if self._port_probe(port):
                return port

    @staticmethod
    def _probe_port(port: int) -> bool:
        """Probe a host port for availability.

        Parameters
        ----------
        port : int
            Host port to probe.

        Returns
        -------
        bool
            True if the port is available for binding.
        """
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                return False
        return True

    def cleanup_all(self) -> dict[str, Any]:
        """Release all tracked ports and container records."""

        with self._lock:
            instance_count = len(self._allocated_ports)
            container_count = len(self._containers)
            self._allocated_ports.clear()
            self._in_use_ports.clear()
            self._recycled_ports.clear()
            self._containers.clear()

        return {"instances": instance_count, "containers": container_count}
