import os
from vigilance.broker.base import BaseBroker
from vigilance.broker.memory_broker import InMemoryBroker


def create_broker(amqp_url: str | None = None) -> BaseBroker:
    """Return RabbitMQBroker if AMQP_URL is set, else InMemoryBroker."""
    url = amqp_url or os.getenv("AMQP_URL")
    if url:
        from vigilance.broker.rabbitmq_broker import RabbitMQBroker
        return RabbitMQBroker(url)
    return InMemoryBroker()


__all__ = ["BaseBroker", "InMemoryBroker", "create_broker"]
