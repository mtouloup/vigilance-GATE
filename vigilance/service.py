"""T5.3 service entrypoint — supports STANDALONE and INTEGRATED modes.

STANDALONE (default):
  Subscribes to pilot.events.raw → full C1→C2→C5→C3→C4 pipeline.

INTEGRATED (VIGILANCE_MODE=INTEGRATED):
  Subscribes to pilot.events.raw → C1 only → publishes CanonicalEvent to
  t53.canonical_events for T5.4.
  Subscribes to t53.action_requests → receives ActionRequest from T5.4 →
  C5→C3→C4 → publishes ExecutionResult to t53.results.
"""
import json
import logging
import os
import sys

from vigilance.broker.rabbitmq_broker import RabbitMQBroker
from vigilance.pipeline import T53Pipeline, TOPIC_ACTION_REQUESTS

logger = logging.getLogger(__name__)

TOPIC_EVENTS_RAW = "pilot.events.raw"


def run() -> None:
    sector = os.getenv("VIGILANCE_SECTOR", "TELECOM")
    mode   = os.getenv("VIGILANCE_MODE", "STANDALONE").upper()
    amqp_url = os.getenv("AMQP_URL", "amqp://vigilance:vigilance@rabbitmq:5672/")

    logger.info(f"Starting T5.3 service: sector={sector} mode={mode} amqp={amqp_url}")

    pipeline = T53Pipeline(sector=sector, mode=mode)
    consumer = RabbitMQBroker(amqp_url)

    # ── pilot.events.raw listener (both modes) ────────────────────────────────
    def handle_raw_event(message: dict) -> None:
        raw = message.get("raw", message)
        logger.info(f"Received raw event: {str(raw)[:120]}")
        try:
            result = pipeline.process_event(raw)
            if result is not None:
                logger.info(f"Processed: overall_success={result.overall_success}")
        except Exception as exc:
            logger.error(f"Pipeline error: {exc}", exc_info=True)

    consumer.subscribe(TOPIC_EVENTS_RAW, handle_raw_event)
    logger.info(f"[{mode}] Listening on: {TOPIC_EVENTS_RAW}")

    # ── t53.action_requests listener (INTEGRATED mode only) ───────────────────
    if mode == "INTEGRATED":
        def handle_action_request(message: dict) -> None:
            logger.info(
                f"Received ActionRequest from T5.4: "
                f"event_id={message.get('event_id')} "
                f"actions={message.get('actions')}"
            )
            try:
                result = pipeline.execute_action_request(message)
                logger.info(f"Executed: overall_success={result.overall_success}")
            except Exception as exc:
                logger.error(f"ActionRequest execution error: {exc}", exc_info=True)

        consumer.subscribe(TOPIC_ACTION_REQUESTS, handle_action_request)
        logger.info(f"[INTEGRATED] Listening on: {TOPIC_ACTION_REQUESTS}")

    consumer.start_consuming()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
        stream=sys.stdout,
    )
    run()
