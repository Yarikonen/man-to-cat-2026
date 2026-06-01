"""Model service entrypoint — worker that processes images from the queue."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys

# Ensure shared package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.config import get_settings
from shared.db import DatabaseManager
from shared.s3_client import S3Client
from shared.queue import QueueManager
from shared.metrics import start_metrics_server, QUEUE_SIZE
from model_service.pipeline import Pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

_shutdown_event = asyncio.Event()


def _handle_signal(sig: int) -> None:
    """Handle shutdown signals gracefully."""
    logger.info("Received signal %d, shutting down...", sig)
    _shutdown_event.set()


async def _update_queue_gauge(queue: QueueManager) -> None:
    """Periodically update the queue size gauge."""
    while not _shutdown_event.is_set():
        try:
            QUEUE_SIZE.set(queue.queue_length())
        except Exception:
            logger.exception("Failed to update queue gauge")
        await asyncio.sleep(5)


async def main() -> None:
    """Main worker loop."""
    settings = get_settings()

    # Start Prometheus metrics server
    start_metrics_server(settings.model_service_port)
    logger.info(
        "Metrics server started on port %d", settings.model_service_port
    )

    # Initialize services
    db = DatabaseManager(settings.database_url)
    await db.connect()
    logger.info("Database initialized at %s", settings.database_url)

    s3 = S3Client()
    s3.ensure_buckets()
    logger.info("S3 buckets verified")

    queue = QueueManager()
    queue.connect()
    logger.info("Redis queue connected")

    pipeline = Pipeline(db, s3)

    # Register signal handlers
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _handle_signal, sig)

    # Start queue gauge updater
    gauge_task = asyncio.create_task(_update_queue_gauge(queue))

    logger.info("Model service worker started, waiting for jobs...")

    try:
        while not _shutdown_event.is_set():
            # Non-blocking dequeue with timeout for graceful shutdown
            image_id = queue.dequeue(timeout=1)
            if image_id is None:
                continue

            await pipeline.process(image_id)

    except asyncio.CancelledError:
        pass
    finally:
        gauge_task.cancel()
        queue.disconnect()
        await db.close()
        logger.info("Model service shut down gracefully")


if __name__ == "__main__":
    asyncio.run(main())
