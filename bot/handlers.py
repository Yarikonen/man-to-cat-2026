"""Telegram bot command and message handlers."""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message

from shared.s3_client import S3Client

if TYPE_CHECKING:
    from shared.db import DatabaseManager
    from shared.queue import QueueManager

logger = logging.getLogger(__name__)

router = Router()

STATUS_EMOJI = {
    "received": "📥",
    "preprocessing": "⚙️",
    "quality_check": "🔍",
    "processing": "🧠",
    "postprocessing": "🎨",
    "done": "✅",
    "failed": "❌",
}


def _format_status(status: str) -> str:
    """Format a status string with emoji."""
    emoji = STATUS_EMOJI.get(status, "❓")
    return f"{emoji} <b>{status.upper()}</b>"


def _register(
    router: Router,
    db: DatabaseManager,
    s3: S3Client,
    queue: QueueManager,
) -> None:
    """Register all handlers on the given router."""

    @router.message(Command("start"))
    async def cmd_start(message: Message) -> None:
        """Handle /start command."""
        await message.answer(
            "👋 <b>Welcome to Man-to-Cat Bot!</b>\n\n"
            "Send me a photo and I'll transform it using AI.\n"
            "Use /help for more info."
        )

    @router.message(Command("help"))
    async def cmd_help(message: Message) -> None:
        """Handle /help command."""
        await message.answer(
            "📖 <b>How to use:</b>\n\n"
            "1. Send me a photo\n"
            "2. I'll save it and start processing\n"
            "3. Watch the status update in real-time\n"
            "4. Get your transformed photo!\n\n"
            "⚡ You can only process one image at a time.\n"
            "Use /status to check your current image status."
        )

    @router.message(Command("status"))
    async def cmd_status(message: Message) -> None:
        """Handle /status command — show current image status."""
        image = await db.get_user_active_image(message.from_user.id)
        if image is None:
            await message.answer(
                "📭 You don't have any active images. "
                "Send me a photo to start!"
            )
            return

        text = (
            f"📊 <b>Current Image Status</b>\n\n"
            f"ID: <code>{image['id'][:8]}...</code>\n"
            f"Status: {_format_status(image['status'])}\n"
            f"Created: {image['created_at']}"
        )
        if image.get("error_reason"):
            text += f"\nError: {image['error_reason']}"
        await message.answer(text)

    @router.message(F.photo)
    async def handle_photo(message: Message) -> None:
        """Handle incoming photo messages."""
        user_id = message.from_user.id

        # Check for active images
        active = await db.get_user_active_image(user_id)
        if active is not None:
            await message.answer(
                "⏳ You already have an image being processed.\n"
                "Please wait for it to finish before sending a new one.\n"
                f"Current status: {_format_status(active['status'])}"
            )
            return

        # Use the largest photo size
        photo = message.photo[-1]
        file_id = photo.file_id

        await message.answer("⬇️ Downloading your image...")

        try:
            # Download the image from Telegram
            file = await message.bot.get_file(file_id)
            image_data = await message.bot.download_file(file.file_path)

            # Generate unique key and upload to S3
            image_id = str(uuid.uuid4())
            s3_key = f"{image_id}.jpg"
            s3.upload_image(s3_key, image_data.read())

            # Create DB record with the same UUID
            # Override the auto-generated id in create_image_record
            # by directly inserting with our UUID
            await db.create_image_record_with_id(
                image_id=image_id,
                user_id=user_id,
                original_s3_key=s3_key,
            )

            # Push to queue
            queue.enqueue(image_id)

            # Send acknowledgment
            sent = await message.answer(
                f"✅ <b>Image accepted!</b>\n\n"
                f"ID: <code>{image_id[:8]}...</code>\n"
                f"Status: {_format_status('received')}"
            )

            # Store message ID for status updates
            await db.update_status(
                image_id=image_id,
                status="received",
                telegram_message_id=sent.message_id,
            )

            logger.info(
                "Image %s accepted from user %d", image_id, user_id
            )

        except Exception:
            logger.exception("Error processing photo from user %d", user_id)
            await message.answer(
                "❌ <b>Error processing your image.</b>\n"
                "Please try again later."
            )


def register_handlers(
    dp,
    db: DatabaseManager,
    s3: S3Client,
    queue: QueueManager,
) -> None:
    """Register all bot handlers on the dispatcher."""
    _register(router, db, s3, queue)
    dp.include_router(router)
