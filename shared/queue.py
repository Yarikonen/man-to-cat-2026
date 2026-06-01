"""Redis queue manager for image processing jobs."""

from __future__ import annotations

import logging
from typing import Optional

import redis

from shared.config import get_settings

logger = logging.getLogger(__name__)

QUEUE_NAME_CONFIG = "redis_queue_name"


class QueueManager:
    """Manages the Redis-based image processing queue."""

    def __init__(self) -> None:
        settings = get_settings()
        self._host = settings.redis_url
        self._queue_name = settings.redis_queue_name
        self._client: Optional[redis.Redis] = None

    def connect(self) -> None:
        """Initialize Redis connection."""
        self._client = redis.Redis.from_url(
            self._host,
            decode_responses=True,
        )
        self._client.ping()
        logger.info("Connected to Redis at %s", self._host)

    def disconnect(self) -> None:
        """Close Redis connection."""
        if self._client:
            self._client.close()
            self._client = None

    def enqueue(self, image_id: str) -> None:
        """Add an image ID to the processing queue."""
        assert self._client is not None
        self._client.lpush(self._queue_name, image_id)
        logger.info("Enqueued image_id=%s", image_id)

    def dequeue(self, timeout: int = 5) -> Optional[str]:
        """Block and wait for next image ID from the queue.

        Returns None if timeout is reached.
        """
        assert self._client is not None
        result = self._client.brpop(self._queue_name, timeout=timeout)
        if result is None:
            return None
        _, image_id = result
        logger.info("Dequeued image_id=%s", image_id)
        return image_id

    def queue_length(self) -> int:
        """Return the current length of the processing queue."""
        assert self._client is not None
        return self._client.llen(self._queue_name)
