from __future__ import annotations
from collections import defaultdict
from typing import Callable


class MessageBroker:
    """Simple in-memory synchronous pub/sub message broker.

    Topics used by the framework:
    - pilot.events.raw          — incoming raw events
    - t53.results               — outgoing ExecutionResults
    - dt.events.synthetic       — digital twin synthetic events
    """

    def __init__(self) -> None:
        self._messages: dict[str, list[dict]] = defaultdict(list)
        self._subscribers: dict[str, list[Callable]] = defaultdict(list)

    def publish(self, topic: str, message: dict) -> None:
        """Publish a message to a topic and notify all subscribers."""
        self._messages[topic].append(message)
        for handler in self._subscribers[topic]:
            handler(message)

    def subscribe(self, topic: str, handler: Callable) -> None:
        """Subscribe a handler function to a topic."""
        self._subscribers[topic].append(handler)

    def get_messages(self, topic: str) -> list[dict]:
        """Return all messages published to a topic."""
        return list(self._messages[topic])

    def clear(self, topic: str | None = None) -> None:
        """Clear messages (optionally for a specific topic)."""
        if topic is None:
            self._messages.clear()
        else:
            self._messages[topic].clear()
