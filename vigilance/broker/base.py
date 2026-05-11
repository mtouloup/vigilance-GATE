from abc import ABC, abstractmethod
from typing import Callable


class BaseBroker(ABC):
    @abstractmethod
    def publish(self, topic: str, message: dict) -> None: ...

    @abstractmethod
    def subscribe(self, topic: str, handler: Callable) -> None: ...

    @abstractmethod
    def get_messages(self, topic: str) -> list[dict]: ...

    def clear(self, topic: str | None = None) -> None:  # optional, default no-op
        pass
