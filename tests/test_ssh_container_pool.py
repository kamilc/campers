"""Unit tests for SSHContainerPool."""

import pytest

from tests.harness.services.ssh_container_pool import PortExhaustedError, SSHContainerPool


class TestSSHContainerPool:
    """Validate port allocation behaviour."""

    def test_allocate_ports_without_collision(self) -> None:
        """Test sequential allocations produce unique ports and enforce limits."""
        pool = SSHContainerPool(base_port=60000, max_containers_per_instance=5, port_probe=lambda port: True)

        ports = [pool.allocate_port("i-1") for _ in range(5)]
        assert ports == [60000, 60001, 60002, 60003, 60004]

        with pytest.raises(PortExhaustedError):
            pool.allocate_port("i-1")

    def test_release_reuses_port(self) -> None:
        """Test released ports are reused for later allocations."""
        pool = SSHContainerPool(base_port=55000, max_containers_per_instance=2, port_probe=lambda port: True)

        first = pool.allocate_port("i-2")
        second = pool.allocate_port("i-2")
        pool.release_port("i-2", first)
        pool.release_port("i-2", second)

        reused = pool.allocate_port("i-2")
        assert reused in {first, second}

    def test_release_unknown_port_raises(self) -> None:
        """Test releasing unknown ports raises KeyError."""
        pool = SSHContainerPool(port_probe=lambda port: True)

        with pytest.raises(KeyError):
            pool.release_port("i-3", 62000)
