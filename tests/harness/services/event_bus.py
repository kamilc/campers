"""Thread-safe event bus for inter-component communication."""

import queue
from typing import Any


class EventBus:
    """Thread-safe event bus using queue.Queue for message passing.

    Provides publish/subscribe semantics for arbitrary events. Each channel
    has its own queue for event buffering.

    Attributes
    ----------
    _channels : dict[str, queue.Queue]
        Mapping of channel names to their queues
    """

    def __init__(self) -> None:
        self._channels: dict[str, queue.Queue[Any]] = {}

    def publish(self, channel: str, event: Any) -> None:
        """Publish an event to a channel.

        Creates channel queue if it doesn't exist.

        Parameters
        ----------
        channel : str
            Channel name (e.g., "resource-registration")
        event : Any
            Event object to publish
        """
        if channel not in self._channels:
            self._channels[channel] = queue.Queue()

        self._channels[channel].put(event)

    def subscribe(self, channel: str) -> queue.Queue[Any]:
        """Subscribe to a channel, returning the queue consumer.

        Creates channel queue if it doesn't exist.

        Parameters
        ----------
        channel : str
            Channel name to subscribe to

        Returns
        -------
        queue.Queue
            Queue consumer for reading events
        """
        if channel not in self._channels:
            self._channels[channel] = queue.Queue()

        return self._channels[channel]

    def drain(self) -> None:
        """Clear all events from all channels."""
        for queue_obj in self._channels.values():
            try:
                while not queue_obj.empty():
                    queue_obj.get_nowait()
            except queue.Empty:
                pass
