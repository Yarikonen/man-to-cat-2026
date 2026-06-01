"""Telegram bot entrypoint."""

import asyncio
import logging
import sys
import os

# Ensure shared package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from shared.config import get_settings
from shared.db import DatabaseManager
from shared.s3_client import S3Client
from shared.queue import QueueManager
from shared.metrics import start_metrics_server
from bot.handlers import register_handlers
from bot.poller import StatusPoller

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    """Initialize and run the Telegram bot."""
    settings = get_settings()

    # Start Prometheus metrics server
    start_metrics_server(settings.prometheus_port)
    logger.info("Metrics server started on port %d", settings.prometheus_port)

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

    # Initialize bot
    bot = Bot(token=settings.telegram_bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    # Register handlers
    register_handlers(dp, db, s3, queue)

    # Start status poller
    poller = StatusPoller(bot, db)

    logger.info("Bot starting polling...")
    try:
        await asyncio.gather(dp.start_polling(bot), poller.run())
    finally:
        queue.disconnect()
        await db.close()
        logger.info("Bot shut down gracefully")


if __name__ == "__main__":
    asyncio.run(main())
