"""T5.3 service entrypoint — supports STANDALONE and INTEGRATED modes.

STANDALONE (default):
  Subscribes to pilot.events.raw → full C1→C2→C5→C3→C4 pipeline.

INTEGRATED (VIGILANCE_MODE=INTEGRATED):
  Two independent consumer threads, each with their own pika connection:
  - Thread 1: pilot.events.raw → C1 only → publishes CanonicalEvent to
    t53.canonical_events for T5.4.
  - Thread 2: t53.action_requests → receives ActionRequest from T5.4 →
    C5→C3→C4 → publishes ExecutionResult to t53.results.

  Running on separate threads ensures that a long LLM call in C1 (thread 1)
  does not block T5.4's ActionRequest from being consumed (thread 2). Each
  thread has its own BlockingConnection so pika concurrency rules are respected.
"""
import logging
import os
import sys
import threading

from vigilance.broker.rabbitmq_broker import RabbitMQBroker
from vigilance.pipeline import T53Pipeline, TOPIC_ACTION_REQUESTS

logger = logging.getLogger(__name__)

TOPIC_EVENTS_RAW = "pilot.events.raw"


def _make_consumer(amqp_url: str) -> RabbitMQBroker:
    """Create a dedicated RabbitMQ connection for one consumer thread."""
    return RabbitMQBroker(amqp_url)


def run() -> None:
    sector   = os.getenv("VIGILANCE_SECTOR", "TELECOM")
    mode     = os.getenv("VIGILANCE_MODE", "STANDALONE").upper()
    amqp_url = os.getenv("AMQP_URL", "amqp://vigilance:vigilance@rabbitmq:5672/")

    logger.info(f"Starting T5.3 service: sector={sector} mode={mode} amqp={amqp_url}")

    pipeline = T53Pipeline(sector=sector, mode=mode)

    # ── Raw-event handler ─────────────────────────────────────────────────────
    def handle_raw_event(message: dict) -> None:
        raw = message.get("raw", message)
        logger.info(f"Received raw event: {str(raw)[:120]}")
        try:
            result = pipeline.process_event(raw)
            if result is not None:
                logger.info(f"Processed: overall_success={result.overall_success}")
        except Exception as exc:
            logger.error(f"Pipeline error: {exc}", exc_info=True)

    # ── ActionRequest handler (INTEGRATED only) ───────────────────────────────
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

    if mode == "INTEGRATED":
        # Two independent pika connections so a long C1 LLM call on the raw-event
        # thread never delays consumption of ActionRequests on the action thread.
        raw_consumer    = _make_consumer(amqp_url)
        action_consumer = _make_consumer(amqp_url)

        raw_consumer.subscribe(TOPIC_EVENTS_RAW, handle_raw_event)
        action_consumer.subscribe(TOPIC_ACTION_REQUESTS, handle_action_request)

        logger.info(f"[INTEGRATED] Listening on: {TOPIC_EVENTS_RAW} (thread-1)")
        logger.info(f"[INTEGRATED] Listening on: {TOPIC_ACTION_REQUESTS} (thread-2)")

        t_raw = threading.Thread(
            target=raw_consumer.start_consuming,
            name="consumer-raw-events",
            daemon=True,
        )
        t_action = threading.Thread(
            target=action_consumer.start_consuming,
            name="consumer-action-requests",
            daemon=True,
        )
        t_raw.start()
        t_action.start()

        # Block the main thread until either consumer thread dies (error/shutdown)
        t_raw.join()
        t_action.join()

    else:
        # STANDALONE: single consumer, single thread is fine
        consumer = _make_consumer(amqp_url)
        consumer.subscribe(TOPIC_EVENTS_RAW, handle_raw_event)
        logger.info(f"[STANDALONE] Listening on: {TOPIC_EVENTS_RAW}")
        consumer.start_consuming()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
        stream=sys.stdout,
    )
    run()
