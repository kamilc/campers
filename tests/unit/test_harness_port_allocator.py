"""Unit tests for PortAllocator utility."""

import pytest

from tests.unit.harness.utils.port_allocator import PortAllocator


class TestPortAllocatorBasic:
    """Test basic port allocation."""

    def test_allocate_port(self) -> None:
        """Test allocating a port."""
        allocator = PortAllocator()
        port = allocator.allocate()

        assert isinstance(port, int)
        assert port > 0

    def test_allocate_different_ports(self) -> None:
        """Test allocating different ports."""
        allocator = PortAllocator()

        port_a = allocator.allocate()
        port_b = allocator.allocate()

        assert port_a != port_b

    def test_allocate_within_range(self) -> None:
        """Test allocated ports are within configured range."""
        allocator = PortAllocator(start_port=20000, end_port=20010)

        for _ in range(5):
            port = allocator.allocate()
            assert 20000 <= port <= 20010


class TestPortAllocatorDeallocate:
    """Test deallocating ports."""

    def test_deallocate_port(self) -> None:
        """Test deallocating a port."""
        allocator = PortAllocator()

        port = allocator.allocate()
        assert port in allocator.allocated_ports

        allocator.deallocate(port)
        assert port not in allocator.allocated_ports

    def test_deallocate_unallocated_port_safe(self) -> None:
        """Test deallocating unallocated port doesn't raise."""
        allocator = PortAllocator()
        allocator.deallocate(25000)

    def test_allocate_after_deallocate(self) -> None:
        """Test port can be reallocated after deallocation."""
        allocator = PortAllocator(start_port=20000, end_port=20002)

        port1 = allocator.allocate()
        allocator.deallocate(port1)

        port2 = allocator.allocate()
        assert port1 == port2


class TestPortAllocatorReset:
    """Test reset functionality."""

    def test_reset_clears_allocations(self) -> None:
        """Test reset clears all allocations."""
        allocator = PortAllocator()

        _ = allocator.allocate()
        _ = allocator.allocate()

        allocator.reset()

        assert len(allocator.allocated_ports) == 0

    def test_reset_restores_available_pool(self) -> None:
        """Test reset restores available ports."""
        allocator = PortAllocator(start_port=20000, end_port=20010)

        initial_available = len(allocator.available_ports)

        _ = allocator.allocate()
        assert len(allocator.available_ports) < initial_available

        allocator.reset()
        assert len(allocator.available_ports) == initial_available


class TestPortAllocatorConfiguration:
    """Test configuration options."""

    def test_custom_port_range(self) -> None:
        """Test custom port range."""
        allocator = PortAllocator(start_port=30000, end_port=30100)

        port = allocator.allocate()
        assert 30000 <= port <= 30100

    def test_single_port_range(self) -> None:
        """Test range with single port."""
        allocator = PortAllocator(start_port=25000, end_port=25000)
        port = allocator.allocate()
        assert port == 25000

    def test_default_range(self) -> None:
        """Test default port range."""
        allocator = PortAllocator()
        assert allocator.start_port == 20000
        assert allocator.end_port == 30000


class TestPortAllocatorThreadSafety:
    """Test thread safety."""

    def test_concurrent_allocations(self) -> None:
        """Test concurrent allocations don't cause conflicts."""
        import threading

        allocator = PortAllocator(start_port=20000, end_port=20100)
        allocated_ports = []
        lock = threading.Lock()

        def allocate_port() -> None:
            port = allocator.allocate()
            with lock:
                allocated_ports.append(port)

        threads = []
        for _ in range(10):
            thread = threading.Thread(target=allocate_port)
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        assert len(allocated_ports) == 10
        assert len(set(allocated_ports)) == 10

    def test_concurrent_deallocations(self) -> None:
        """Test concurrent deallocations are safe."""
        import threading

        allocator = PortAllocator()

        ports = []
        for _ in range(10):
            ports.append(allocator.allocate())

        def deallocate_port(port: int) -> None:
            allocator.deallocate(port)

        threads = []
        for port in ports:
            thread = threading.Thread(target=deallocate_port, args=(port,))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        assert len(allocator.allocated_ports) == 0


class TestPortAllocatorExhaustion:
    """Test behavior when ports are exhausted."""

    def test_allocate_exhausts_small_range(self) -> None:
        """Test allocating from exhausted pool raises error."""
        allocator = PortAllocator(start_port=20000, end_port=20002)

        allocator.allocate()
        allocator.allocate()
        allocator.allocate()

        with pytest.raises(RuntimeError):
            allocator.allocate()
