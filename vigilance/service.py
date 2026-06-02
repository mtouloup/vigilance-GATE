"""T5.3 service entrypoint — INTEGRATED mode broker consumer.

Two independent consumer threads, each with their own pika connection:
  Thread 1: pilot.events.raw → C1 normalize → publish CanonicalEvent
            to t53.canonical_events for T5.4.
  Thread 2: t53.action_requests → receive ActionRequest from T5.4
            → C5 guardrail → C3 policy → C4 dispatch
            → t53.policy_updates (T5.5) + t53.actions.dispatch (pilot tools)
            → t53.results

Two separate pika BlockingConnections are required so that a long C1 LLM
call on thread 1 never delays consumption of ActionRequests on thread 2.
"""
import logging
import os
import sys
import threading

from vigilance.broker.rabbitmq_broker import RabbitMQBroker
from vigilance.pipeline import T53Pipeline, TOPIC_ACTION_REQUESTS

logger = logging.getLogger(__name__)

TOPIC_EVENTS_RAW = "pilot.events.raw"


def run() -> None:
    amqp_url = os.getenv("AMQP_URL", "amqp://vigilance:vigilance@rabbitmq:5672/")
    dry_run  = os.getenv("VIGILANCE_DRY_RUN", "").lower() in ("1", "true", "yes")

    logger.info(f"Starting T5.3 service: pilots=ALL dry_run={dry_run} amqp={amqp_url}")

    pipeline = T53Pipeline(dry_run=dry_run)

    def handle_raw_event(message: dict) -> None:
        raw = message.get("raw", message)
        logger.info(f"[Thread-1] Raw event received: {str(raw)[:120]}")
        try:
            pipeline.ingest_event(raw)
        except Exception as exc:
            logger.error(f"[Thread-1] Ingest error: {exc}", exc_info=True)

    def handle_action_request(message: dict) -> None:
        logger.info(
            f"[Thread-2] ActionRequest from T5.4: "
            f"event_id={message.get('event_id')} actions={message.get('actions')}"
        )
        try:
            result = pipeline.execute_action_request(message)
            logger.info(f"[Thread-2] Executed: overall_success={result.overall_success}")
        except Exception as exc:
            logger.error(f"[Thread-2] Execution error: {exc}", exc_info=True)

    raw_consumer    = RabbitMQBroker(amqp_url)
    action_consumer = RabbitMQBroker(amqp_url)

    raw_consumer.subscribe(TOPIC_EVENTS_RAW, handle_raw_event)
    action_consumer.subscribe(TOPIC_ACTION_REQUESTS, handle_action_request)

    logger.info(f"Listening on: {TOPIC_EVENTS_RAW} (thread-1)")
    logger.info(f"Listening on: {TOPIC_ACTION_REQUESTS} (thread-2)")

    t_raw = threading.Thread(target=raw_consumer.start_consuming,
                             name="consumer-raw-events", daemon=True)
    t_action = threading.Thread(target=action_consumer.start_consuming,
                                name="consumer-action-requests", daemon=True)
    t_raw.start()
    t_action.start()
    t_raw.join()
    t_action.join()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
        stream=sys.stdout,
    )
    run()
