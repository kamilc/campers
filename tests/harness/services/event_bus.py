"""Thread-safe event bus for harness components."""

from __future__ import annotations

import logging
import queue
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Event:
    """Structured event payload.

    Attributes
    ----------
    type : str
        Event type identifier (e.g., "ssh-ready").
    instance_id : str | None
        Optional instance identifier associated with the event.
    data : dict[str, Any]
        Arbitrary event payload metadata.
    timestamp : float
        Event creation timestamp in seconds.
    thread_id : int
        Thread identifier of the publisher.
    """

    type: str
    instance_id: str | None
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    thread_id: int = field(default_factory=lambda: threading.get_ident())


class EventBusError(Exception):
    """Base exception for event bus failures."""


class EventBusTimeoutError(EventBusError):
    """Raised when waiting for an event exceeds its timeout budget.

    Parameters
    ----------
    message : str
        Human-readable error description.
    event_type : str
        Event channel type that timed out.
    instance_id : str | None
        Instance identifier filter used for the wait operation.
    queue_depth : int
        Depth of the pending event queue when the timeout occurred.
    recent_events : list[Event]
        Recent events published to the bus for diagnostics.
    """

    def __init__(
        self,
        message: str,
        event_type: str,
        instance_id: str | None,
        queue_depth: int,
        recent_events: list[Event],
    ) -> None:
        super().__init__(message)
        self.event_type = event_type
        self.instance_id = instance_id
        self.queue_depth = queue_depth
        self.recent_events = recent_events


@dataclass
class ChannelMetrics:
    """Aggregated diagnostics for an event channel.

    Attributes
    ----------
    last_publish_timestamp : float | None
        Timestamp of the most recent publish operation.
    last_consume_timestamp : float | None
        Timestamp of the most recent consume operation.
    published_count : int
        Total number of events published on the channel.
    consumed_count : int
        Total number of events consumed from the channel.
    max_depth : int
        Maximum observed queue depth.
    """

    last_publish_timestamp: float | None = None
    last_consume_timestamp: float | None = None
    published_count: int = 0
    consumed_count: int = 0
    max_depth: int = 0


class EventBusChannel:
    """Facade exposing typed event bus operations for a specific channel.

    Parameters
    ----------
    name : str
        Channel name associated with the facade.
    bus : EventBus
        Backing event bus instance.
    """

    def __init__(self, name: str, bus: EventBus) -> None:
        self._name = name
        self._bus = bus

    def publish(self, instance_id: str | None, data: dict[str, Any] | None = None) -> Event:
        """Publish an event on the bound channel.

        Parameters
        ----------
        instance_id : str | None
            Optional instance identifier associated with the event.
        data : dict[str, Any] | None
            Optional event payload.

        Returns
        -------
        Event
            Published event instance.
        """
        event = Event(type=self._name, instance_id=instance_id, data=data or {})
        self._bus.publish(event)
        return event

    def wait_for(self, instance_id: str | None, timeout_sec: float) -> Event:
        """Wait for a matching event on the bound channel.

        Parameters
        ----------
        instance_id : str | None
            Optional instance identifier to filter events.
        timeout_sec : float
            Maximum time in seconds to wait for the event.

        Returns
        -------
        Event
            Event that satisfied the wait condition.
        """
        return self._bus.wait_for(self._name, instance_id, timeout_sec)

    def subscribe(self, callback: Callable[[Event], None]) -> Callable[[], None]:
        """Subscribe to events from the bound channel.

        Parameters
        ----------
        callback : Callable[[Event], None]
            Callable invoked for every published event.

        Returns
        -------
        Callable[[], None]
            Unsubscribe callable.
        """
        return self._bus.subscribe(callback, channel=self._name)


class EventBus:
    """Thread-safe event bus supporting typed channels and diagnostics."""

    def __init__(self, history_limit: int = 50) -> None:
        self._queues: dict[str, queue.Queue[Event]] = {}
        self._backlogs: dict[str, list[Event]] = {}
        self._metrics: dict[str, ChannelMetrics] = {}
        self._history: deque[Event] = deque(maxlen=history_limit)
        self._lock = threading.RLock()
        self._global_subscribers: set[Callable[[Event], None]] = set()
        self._channel_subscribers: dict[str, set[Callable[[Event], None]]] = {}

    def publish(self, event: Event) -> None:
        """Publish an event to its channel.

        Parameters
        ----------
        event : Event
            Event to publish.
        """
        with self._lock:
            channel_queue = self._ensure_channel(event.type)
            channel_queue.put(event)
            metrics = self._metrics[event.type]
            metrics.published_count += 1
            metrics.last_publish_timestamp = event.timestamp
            depth = channel_queue.qsize() + len(self._backlogs[event.type])
            metrics.max_depth = max(metrics.max_depth, depth)
            self._history.append(event)
            global_callbacks = list(self._global_subscribers)
            channel_callbacks = list(self._channel_subscribers.get(event.type, set()))

        for callback in channel_callbacks + global_callbacks:
            try:
                callback(event)
            except Exception:
                logger.exception("Event subscriber %r raised an exception", callback)

        logger.debug(
            "Event published",
            extra={
                "event_type": event.type,
                "instance_id": event.instance_id,
                "queue_depth": depth,
                "thread_id": event.thread_id,
            },
        )

    def wait_for(
        self,
        event_type: str,
        instance_id: str | None,
        timeout_sec: float,
    ) -> Event:
        """Wait for an event matching the provided criteria.

        Parameters
        ----------
        event_type : str
            Channel identifier to wait on.
        instance_id : str | None
            Optional instance identifier filter.
        timeout_sec : float
            Maximum number of seconds to wait.

        Returns
        -------
        Event
            Event matching the wait criteria.

        Raises
        ------
        EventBusTimeoutError
            If no matching event arrives before timeout.
        """
        deadline = time.monotonic() + timeout_sec
        self._ensure_channel(event_type)

        while True:
            with self._lock:
                backlog = self._backlogs[event_type]
                for index, event in enumerate(list(backlog)):
                    if instance_id is None or event.instance_id == instance_id:
                        backlog.pop(index)
                        self._record_consume(event)
                        return event

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise self._timeout_error(event_type, instance_id)

            try:
                event = self._queues[event_type].get(timeout=remaining)
            except queue.Empty as err:
                raise self._timeout_error(event_type, instance_id) from err

            if instance_id is None or event.instance_id == instance_id:
                with self._lock:
                    self._record_consume(event)
                return event

            with self._lock:
                self._backlogs[event_type].append(event)

    def subscribe(
        self,
        callback: Callable[[Event], None],
        channel: str | None = None,
    ) -> Callable[[], None]:
        """Subscribe a callback to channel or bus-wide events.

        Parameters
        ----------
        callback : Callable[[Event], None]
            Callable invoked with each published event.
        channel : str | None, optional
            Channel to subscribe to, or all channels if None.

        Returns
        -------
        Callable[[], None]
            Callable that removes the subscription when invoked.
        """
        with self._lock:
            if channel is None:
                self._global_subscribers.add(callback)
            else:
                self._ensure_channel(channel)
                subscribers = self._channel_subscribers.setdefault(channel, set())
                subscribers.add(callback)

        def _unsubscribe() -> None:
            with self._lock:
                if channel is None:
                    self._global_subscribers.discard(callback)
                else:
                    subscribers = self._channel_subscribers.get(channel)
                    if subscribers is not None:
                        subscribers.discard(callback)

        return _unsubscribe

    def channel(self, name: str) -> EventBusChannel:
        """Create a typed channel facade.

        Parameters
        ----------
        name : str
            Channel name to bind.

        Returns
        -------
        EventBusChannel
            Channel-specific facade instance.
        """
        self._ensure_channel(name)
        return EventBusChannel(name=name, bus=self)

    def drain_all(self) -> dict[str, list[Event]]:
        """Drain all queues and return collected events.

        Returns
        -------
        dict[str, list[Event]]
            Mapping of channel names to drained events.
        """
        drained: dict[str, list[Event]] = {}

        with self._lock:
            for channel, backlog in self._backlogs.items():
                if backlog:
                    drained[channel] = list(backlog)
                    backlog.clear()

            for channel, queue_obj in self._queues.items():
                drained.setdefault(channel, [])
                while True:
                    try:
                        event = queue_obj.get_nowait()
                    except queue.Empty:
                        break
                    drained[channel].append(event)
                    self._record_consume(event)

        return {channel: events for channel, events in drained.items() if events}

    def drain(self) -> None:
        """Drain all events without returning them."""
        self.drain_all()

    def metrics_snapshot(self) -> dict[str, ChannelMetrics]:
        """Retrieve a snapshot of channel metrics.

        Returns
        -------
        dict[str, ChannelMetrics]
            Copy of channel metrics keyed by channel.
        """
        with self._lock:
            return {
                channel: ChannelMetrics(**vars(metrics))
                for channel, metrics in self._metrics.items()
            }

    def _ensure_channel(self, name: str) -> queue.Queue[Event]:
        if name not in self._queues:
            self._queues[name] = queue.Queue()
            self._backlogs[name] = []
            self._metrics[name] = ChannelMetrics()
        return self._queues[name]

    def _record_consume(self, event: Event) -> None:
        metrics = self._metrics[event.type]
        now = time.time()
        metrics.consumed_count += 1
        metrics.last_consume_timestamp = now
        latency = now - event.timestamp
        logger.debug(
            "Event consumed",
            extra={
                "event_type": event.type,
                "instance_id": event.instance_id,
                "latency_sec": latency,
                "queue_depth": self._queues[event.type].qsize() + len(self._backlogs[event.type]),
            },
        )

    def _timeout_error(self, event_type: str, instance_id: str | None) -> EventBusTimeoutError:
        with self._lock:
            depth = self._queues[event_type].qsize() + len(self._backlogs[event_type])
            recent_events = list(self._history)[-5:]
        message = f"Timed out waiting for event '{event_type}'" + (
            f" for '{instance_id}'" if instance_id is not None else ""
        )
        return EventBusTimeoutError(
            message=message,
            event_type=event_type,
            instance_id=instance_id,
            queue_depth=depth,
            recent_events=recent_events,
        )
