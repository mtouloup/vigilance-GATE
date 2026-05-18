"""T5.3 combined entrypoint — starts the REST API server and the broker consumer.

The REST API (FastAPI/uvicorn) runs on port 8000 in a daemon thread.
The broker consumer (pika) runs in the main thread (or as daemon threads in
INTEGRATED mode). This lets both interfaces be served from a single container,
which is required for T5.6 Agentic ZTA Platform Integration.

Environment variables:
  VIGILANCE_MODE        STANDALONE (default) | INTEGRATED | DIGITAL_TWIN
  VIGILANCE_SIMULATION  dry_run | digital_twin (overrides to simulation mode)
  AMQP_URL              amqp://vigilance:vigilance@rabbitmq:5672/ (default)
  API_HOST              0.0.0.0 (default)
  API_PORT              8000 (default)
"""
import logging
import os
import sys
import threading

import uvicorn

from vigilance.api.app import app, get_pipeline
from vigilance import service

logger = logging.getLogger(__name__)


def _start_api(host: str, port: int) -> None:
    """Run the FastAPI/uvicorn server in this thread (blocking)."""
    uvicorn.run(app, host=host, port=port, log_level="info", access_log=False)


def run() -> None:
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8000"))

    # Warm up the pipeline singleton so the first API request is fast
    get_pipeline()

    # Start REST API in a daemon thread
    api_thread = threading.Thread(
        target=_start_api,
        args=(host, port),
        name="api-server",
        daemon=True,
    )
    api_thread.start()
    logger.info(f"[T5.3] REST API listening on http://{host}:{port}/api/docs")

    # Run broker consumer(s) in the main thread (blocks until shutdown)
    service.run()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
        stream=sys.stdout,
    )
    run()
