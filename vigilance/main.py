"""T5.3 combined entrypoint — REST API server + broker consumer.

The FastAPI/uvicorn REST API (port 8000) runs in a daemon thread.
The broker consumer runs in the main thread (two pika threads internally).

Environment variables:
  AMQP_URL           amqp://vigilance:vigilance@rabbitmq:5672/ (default)
  VIGILANCE_DRY_RUN  1 | true — skip broker dispatch (dev/test only)
  API_HOST           0.0.0.0 (default)
  API_PORT           8000 (default)
"""
import logging
import os
import sys
import threading

import uvicorn

from vigilance.api.app import app, get_pipeline
from vigilance import service

logger = logging.getLogger(__name__)


def run() -> None:
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8000"))

    get_pipeline()  # warm up pipeline singleton before first request

    api_thread = threading.Thread(
        target=lambda: uvicorn.run(app, host=host, port=port,
                                   log_level="info", access_log=False),
        name="api-server",
        daemon=True,
    )
    api_thread.start()
    logger.info(f"[T5.3] REST API → http://{host}:{port}/api/docs")

    service.run()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
        stream=sys.stdout,
    )
    run()
