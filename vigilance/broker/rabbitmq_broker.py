from __future__ import annotations
import json
import logging
import time
from collections import defaultdict
from typing import Callable

from vigilance.broker.base import BaseBroker

logger = logging.getLogger(__name__)


class RabbitMQBroker(BaseBroker):
    """RabbitMQ-backed broker using pika (BlockingConnection).

    Topics map to durable queues. Published messages are also buffered
    locally in self._buffer so get_messages() works for observability.
    """

    def __init__(self, amqp_url: str, connection_retries: int = 5) -> None:
        try:
            import pika
        except ImportError:
            raise RuntimeError(
                "pika is required for RabbitMQ broker. Install with: pip install pika>=1.3"
            )

        self._pika = pika
        self._buffer: dict[str, list[dict]] = defaultdict(list)
        self._connection = None
        self._channel = None

        last_exc = None
        for attempt in range(1, connection_retries + 1):
            try:
                logger.info(f"Connecting to RabbitMQ (attempt {attempt}/{connection_retries}): {amqp_url}")
                params = pika.URLParameters(amqp_url)
                self._connection = pika.BlockingConnection(params)
                self._channel = self._connection.channel()
                logger.info("Connected to RabbitMQ successfully.")
                break
            except pika.exceptions.AMQPConnectionError as exc:
                last_exc = exc
                logger.warning(f"Connection attempt {attempt} failed: {exc}")
                if attempt < connection_retries:
                    time.sleep(2)
        else:
            raise RuntimeError(
                f"Failed to connect to RabbitMQ after {connection_retries} attempts"
            ) from last_exc

    def _declare_queue(self, topic: str) -> None:
        """Declare a durable queue for the given topic."""
        self._channel.queue_declare(queue=topic, durable=True)

    def publish(self, topic: str, message: dict) -> None:
        """Declare queue (idempotent), publish JSON-encoded message.
        Also append to self._buffer[topic] for get_messages().
        """
        self._declare_queue(topic)
        body = json.dumps(message).encode("utf-8")
        self._channel.basic_publish(
            exchange="",
            routing_key=topic,
            body=body,
            properties=self._pika.BasicProperties(
                delivery_mode=2,  # persistent
                content_type="application/json",
            ),
        )
        self._buffer[topic].append(message)

    def subscribe(self, topic: str, handler: Callable) -> None:
        """Declare queue, start basic_consume.
        Call handler(message_dict) for each delivery.
        """
        self._declare_queue(topic)

        def _callback(ch, method, properties, body):
            try:
                message = json.loads(body.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                logger.error(f"Failed to decode message body: {exc}")
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
                return
            self._buffer[topic].append(message)
            try:
                handler(message)
            except Exception as exc:
                logger.error(f"Handler error for topic {topic!r}: {exc}", exc_info=True)
            ch.basic_ack(delivery_tag=method.delivery_tag)

        self._channel.basic_qos(prefetch_count=1)
        self._channel.basic_consume(queue=topic, on_message_callback=_callback)

    def get_messages(self, topic: str) -> list[dict]:
        """Return locally buffered messages."""
        return list(self._buffer.get(topic, []))

    def start_consuming(self) -> None:
        """Start blocking consume loop."""
        self._channel.start_consuming()

    def close(self) -> None:
        """Gracefully close connection."""
        try:
            if self._connection and not self._connection.is_closed:
                self._connection.close()
                logger.info("RabbitMQ connection closed.")
        except Exception as exc:
            logger.warning(f"Error closing RabbitMQ connection: {exc}")
