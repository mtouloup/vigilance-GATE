"""T5.3 service entrypoint — subscribes to pilot.events.raw and runs the pipeline."""
import json
import logging
import os
import sys

from vigilance.broker.rabbitmq_broker import RabbitMQBroker
from vigilance.pipeline import T53Pipeline

logger = logging.getLogger(__name__)

TOPIC_EVENTS_RAW = "pilot.events.raw"


def run() -> None:
    sector = os.getenv("VIGILANCE_SECTOR", "TELECOM")
    amqp_url = os.getenv("AMQP_URL", "amqp://vigilance:vigilance@rabbitmq:5672/")

    logger.info(f"Starting T5.3 service: sector={sector} amqp={amqp_url}")

    pipeline = T53Pipeline(sector=sector)
    consumer = RabbitMQBroker(amqp_url)

    def handle_event(message: dict) -> None:
        raw = message.get("raw", message)
        logger.info(f"Received event: {str(raw)[:120]}")
        try:
            result = pipeline.process_event(raw)
            logger.info(f"Processed: overall_success={result.overall_success}")
        except Exception as exc:
            logger.error(f"Pipeline error: {exc}", exc_info=True)

    consumer.subscribe(TOPIC_EVENTS_RAW, handle_event)
    logger.info(f"Listening on queue: {TOPIC_EVENTS_RAW}")
    consumer.start_consuming()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
        stream=sys.stdout,
    )
    run()
