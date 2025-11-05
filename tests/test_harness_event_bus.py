"""Unit tests for the enhanced EventBus service."""

import time
from threading import Event as ThreadEvent
from typing import Any

import pytest

from tests.harness.services.event_bus import (
    Event,
    EventBus,
    EventBusTimeoutError,
)


class TestEventBusPublishAndWait:
    """Validate publish and wait semantics."""

    def test_wait_for_acknowledges_event(self) -> None:
        """Test wait_for consumes a matching event and drains the queue."""
        bus = EventBus()
        channel = bus.channel("ssh-ready")
        channel.publish(instance_id="i-123", data={"port": 22})

        received = bus.wait_for("ssh-ready", instance_id="i-123", timeout_sec=1.0)

        assert isinstance(received, Event)
        assert received.type == "ssh-ready"
        assert received.instance_id == "i-123"
        assert received.data == {"port": 22}
        assert bus.drain_all() == {}

    def test_wait_for_ignores_other_instances(self) -> None:
        """Test wait_for skips events for other instance identifiers."""
        bus = EventBus()
        channel = bus.channel("ssh-ready")
        channel.publish(instance_id="i-111", data={})
        channel.publish(instance_id="i-222", data={})

        received = bus.wait_for("ssh-ready", instance_id="i-222", timeout_sec=1.0)

        assert received.instance_id == "i-222"
        drained = bus.drain_all()
        assert "ssh-ready" in drained
        assert drained["ssh-ready"][0].instance_id == "i-111"

    def test_wait_for_times_out_with_diagnostics(self) -> None:
        """Test timeout raises diagnostic-rich exception."""
        bus = EventBus()
        channel = bus.channel("ssh-ready")
        channel.publish(instance_id="i-000", data={})

        with pytest.raises(EventBusTimeoutError) as exc:
            bus.wait_for("ssh-ready", instance_id="i-999", timeout_sec=0.1)

        error = exc.value
        assert error.event_type == "ssh-ready"
        assert error.instance_id == "i-999"
        assert error.queue_depth >= 1
        assert len(error.recent_events) >= 1


class TestEventBusSubscriptions:
    """Validate callback subscription handling."""

    def test_channel_subscription_receives_events(self) -> None:
        """Test channel-scoped subscriptions receive published events."""
        bus = EventBus()
        received: list[Event] = []
        unsubscribe = bus.channel("monitor-error").subscribe(received.append)

        bus.publish(Event(type="monitor-error", instance_id=None, data={"message": "boom"}))

        assert len(received) == 1
        assert received[0].data["message"] == "boom"

        unsubscribe()
        bus.publish(Event(type="monitor-error", instance_id=None, data={"message": "ignored"}))
        assert len(received) == 1

    def test_global_subscription_receives_all_events(self) -> None:
        """Test global subscription observes events from every channel."""
        bus = EventBus()
        observed: list[str] = []
        bus.subscribe(lambda event: observed.append(event.type))

        bus.publish(Event(type="instance-ready", instance_id="i-a", data={}))
        bus.publish(Event(type="ssh-ready", instance_id="i-a", data={}))

        assert observed == ["instance-ready", "ssh-ready"]

    def test_subscription_does_not_block_publish(self) -> None:
        """Test slow subscriber does not block other subscribers indefinitely."""
        bus = EventBus()
        gate = ThreadEvent()

        def slow_callback(event: Event) -> None:
            gate.wait(timeout=1.0)

        bus.subscribe(slow_callback)
        bus.subscribe(lambda event: gate.set())

        bus.publish(Event(type="heartbeat", instance_id=None, data={}))
        assert gate.wait(timeout=1.0)


class TestEventBusDraining:
    """Validate draining behaviour."""

    def test_drain_all_returns_per_channel_events(self) -> None:
        """Test drain_all returns channel-indexed events."""
        bus = EventBus()
        bus.publish(Event(type="ssh-ready", instance_id="i-1", data={}))
        bus.publish(Event(type="http-ready", instance_id="i-1", data={}))

        drained = bus.drain_all()

        assert set(drained.keys()) == {"ssh-ready", "http-ready"}
        assert all(isinstance(evt, Event) for events in drained.values() for evt in events)
        assert bus.drain_all() == {}

    def test_metrics_snapshot_reflects_publish_consume_counts(self) -> None:
        """Test metrics snapshot captures publish and consume counts."""
        bus = EventBus()
        channel = bus.channel("instance-ready")
        channel.publish(instance_id="i-12", data={})
        bus.wait_for("instance-ready", instance_id="i-12", timeout_sec=1.0)

        metrics = bus.metrics_snapshot()["instance-ready"]

        assert metrics.published_count == 1
        assert metrics.consumed_count == 1
        assert metrics.last_publish_timestamp is not None
        assert metrics.last_consume_timestamp is not None


class TestEventStructure:
    """Validate event structure semantics."""

    def test_event_timestamp_monotonicity(self) -> None:
        """Test later events have increasing timestamps."""
        first = Event(type="tui-update", instance_id=None, data={})
        time.sleep(0.01)
        second = Event(type="tui-update", instance_id=None, data={})
        assert second.timestamp >= first.timestamp

    def test_event_thread_id_defaults_to_current_thread(self) -> None:
        """Test thread identifier recorded on publish."""
        event = Event(type="heartbeat", instance_id=None, data={})
        assert isinstance(event.thread_id, int)
