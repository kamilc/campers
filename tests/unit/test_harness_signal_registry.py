"""Unit tests for SignalRegistry service."""

import threading
import time

import pytest

from tests.unit.harness.exceptions import HarnessTimeoutError
from tests.unit.harness.services.signal_registry import SignalRegistry


class TestSignalRegistryPublishWait:
    """Test publish/wait operations."""

    def test_publish_and_wait_for_signal(self) -> None:
        """Test publishing and waiting for a signal."""
        registry = SignalRegistry()

        def publish_delayed() -> None:
            time.sleep(0.1)
            registry.publish("test-signal", "data")

        thread = threading.Thread(target=publish_delayed)
        thread.start()

        result = registry.wait_for("test-signal", timeout=1.0)
        thread.join()

        assert result == "data"

    def test_wait_timeout_raises_error(self) -> None:
        """Test wait_for raises HarnessTimeoutError when signal not published."""
        registry = SignalRegistry()

        with pytest.raises(HarnessTimeoutError):
            registry.wait_for("nonexistent-signal", timeout=0.1)

    def test_publish_without_data(self) -> None:
        """Test publishing signal without data."""
        registry = SignalRegistry()

        def publish_delayed() -> None:
            time.sleep(0.1)
            registry.publish("test-signal")

        thread = threading.Thread(target=publish_delayed)
        thread.start()

        result = registry.wait_for("test-signal", timeout=1.0)
        thread.join()

        assert result is None

    def test_multiple_signals(self) -> None:
        """Test publishing and waiting for multiple signals."""
        registry = SignalRegistry()

        registry.publish("signal1", "data1")
        registry.publish("signal2", "data2")

        result1 = registry.wait_for("signal1", timeout=0.1)
        result2 = registry.wait_for("signal2", timeout=0.1)

        assert result1 == "data1"
        assert result2 == "data2"

    def test_multiple_publishes_fifo_order(self) -> None:
        """Test multiple publishes are retrieved in FIFO order."""
        registry = SignalRegistry()

        registry.publish("signal", "first")
        registry.publish("signal", "second")
        registry.publish("signal", "third")

        assert registry.wait_for("signal", timeout=0.1) == "first"
        assert registry.wait_for("signal", timeout=0.1) == "second"
        assert registry.wait_for("signal", timeout=0.1) == "third"


class TestSignalRegistryDrain:
    """Test drain operation."""

    def test_drain_clears_all_signals(self) -> None:
        """Test drain clears all published signals."""
        registry = SignalRegistry()

        registry.publish("signal1", "data1")
        registry.publish("signal2", "data2")

        registry.drain()

        with pytest.raises(HarnessTimeoutError):
            registry.wait_for("signal1", timeout=0.1)

        with pytest.raises(HarnessTimeoutError):
            registry.wait_for("signal2", timeout=0.1)

    def test_drain_on_empty_registry(self) -> None:
        """Test drain on empty registry doesn't raise."""
        registry = SignalRegistry()
        registry.drain()


class TestSignalRegistryThreadSafety:
    """Test thread-safety operations."""

    def test_concurrent_publishes(self) -> None:
        """Test concurrent publishes from multiple threads."""
        registry = SignalRegistry()
        results = []

        def publish_signal(signal_name: str, data: str) -> None:
            registry.publish(signal_name, data)

        threads = []
        for i in range(10):
            thread = threading.Thread(
                target=publish_signal, args=(f"signal-{i}", f"data-{i}")
            )
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        for i in range(10):
            result = registry.wait_for(f"signal-{i}", timeout=0.1)
            results.append(result)

        assert len(results) == 10
