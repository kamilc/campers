"""Unit tests for EventBus service."""

import queue

import pytest

from tests.harness.services.event_bus import EventBus


class TestEventBusPublishSubscribe:
    """Test publish/subscribe operations."""

    def test_publish_and_subscribe_single_event(self) -> None:
        """Test publishing and subscribing to an event."""
        bus = EventBus()

        bus.publish("test-channel", "event-data")
        consumer = bus.subscribe("test-channel")

        event = consumer.get_nowait()
        assert event == "event-data"

    def test_publish_multiple_events(self) -> None:
        """Test publishing multiple events to same channel."""
        bus = EventBus()

        bus.publish("test-channel", "event1")
        bus.publish("test-channel", "event2")
        bus.publish("test-channel", "event3")

        consumer = bus.subscribe("test-channel")

        assert consumer.get_nowait() == "event1"
        assert consumer.get_nowait() == "event2"
        assert consumer.get_nowait() == "event3"

    def test_subscribe_multiple_channels(self) -> None:
        """Test subscribing to multiple channels."""
        bus = EventBus()

        bus.publish("channel1", "event1")
        bus.publish("channel2", "event2")
        bus.publish("channel3", "event3")

        consumer1 = bus.subscribe("channel1")
        consumer2 = bus.subscribe("channel2")
        consumer3 = bus.subscribe("channel3")

        assert consumer1.get_nowait() == "event1"
        assert consumer2.get_nowait() == "event2"
        assert consumer3.get_nowait() == "event3"

    def test_subscribe_empty_channel_returns_queue(self) -> None:
        """Test subscribing to empty channel returns queue."""
        bus = EventBus()

        consumer = bus.subscribe("nonexistent-channel")
        assert isinstance(consumer, queue.Queue)

        with pytest.raises(queue.Empty):
            consumer.get_nowait()


class TestEventBusDrain:
    """Test drain operation."""

    def test_drain_clears_all_events(self) -> None:
        """Test drain clears all published events."""
        bus = EventBus()

        bus.publish("channel1", "event1")
        bus.publish("channel2", "event2")

        bus.drain()

        consumer1 = bus.subscribe("channel1")
        consumer2 = bus.subscribe("channel2")

        with pytest.raises(queue.Empty):
            consumer1.get_nowait()

        with pytest.raises(queue.Empty):
            consumer2.get_nowait()

    def test_drain_empty_bus(self) -> None:
        """Test drain on empty bus doesn't raise."""
        bus = EventBus()
        bus.drain()

    def test_drain_multiple_times(self) -> None:
        """Test calling drain multiple times."""
        bus = EventBus()

        bus.publish("channel", "event")
        bus.drain()
        bus.drain()

        consumer = bus.subscribe("channel")
        with pytest.raises(queue.Empty):
            consumer.get_nowait()


class TestEventBusEventTypes:
    """Test various event types."""

    def test_publish_string_event(self) -> None:
        """Test publishing string events."""
        bus = EventBus()
        bus.publish("channel", "string-event")
        consumer = bus.subscribe("channel")
        assert consumer.get_nowait() == "string-event"

    def test_publish_dict_event(self) -> None:
        """Test publishing dict events."""
        bus = EventBus()
        event = {"type": "test", "data": "value"}
        bus.publish("channel", event)
        consumer = bus.subscribe("channel")
        assert consumer.get_nowait() == event

    def test_publish_list_event(self) -> None:
        """Test publishing list events."""
        bus = EventBus()
        event = [1, 2, 3]
        bus.publish("channel", event)
        consumer = bus.subscribe("channel")
        assert consumer.get_nowait() == event

    def test_publish_none_event(self) -> None:
        """Test publishing None events."""
        bus = EventBus()
        bus.publish("channel", None)
        consumer = bus.subscribe("channel")
        assert consumer.get_nowait() is None

    def test_publish_custom_object_event(self) -> None:
        """Test publishing custom object events."""

        class CustomEvent:
            def __init__(self, value: str) -> None:
                self.value = value

        bus = EventBus()
        event = CustomEvent("test")
        bus.publish("channel", event)
        consumer = bus.subscribe("channel")
        result = consumer.get_nowait()
        assert result.value == "test"


class TestEventBusChannelIsolation:
    """Test channel isolation."""

    def test_channels_are_isolated(self) -> None:
        """Test channels don't interfere with each other."""
        bus = EventBus()

        bus.publish("channel1", "event1")
        bus.publish("channel2", "event2")

        consumer1 = bus.subscribe("channel1")
        consumer2 = bus.subscribe("channel2")

        event1 = consumer1.get_nowait()
        assert event1 == "event1"

        event2 = consumer2.get_nowait()
        assert event2 == "event2"

        with pytest.raises(queue.Empty):
            consumer1.get_nowait()
