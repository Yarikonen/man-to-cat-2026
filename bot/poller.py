"""Background status poller — monitors DB and updates Telegram messages."""

from __future__ import annotations

import asyncio
import io
import logging
from typing import TYPE_CHECKING, Any, Dict, Optional

from aiogram.types import BufferedInputFile

from shared.db import DatabaseManager
from shared.metrics import IMAGES_BY_STATUS
from shared.s3_client import S3Client

if TYPE_CHECKING:
    from aiogram import Bot

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 0.5


class StatusPoller:
    """Polls the database for status changes and updates Telegram messages."""

    def __init__(self, bot: Bot, db: DatabaseManager) -> None:
        self._bot = bot
        self._db = db
        self._s3 = S3Client()
        self._tracked: Dict[str, str] = {}  # image_id -> last_known_status

    async def run(self) -> None:
        """Main polling loop."""
        logger.info("Status poller started")
        try:
            while True:
                try:
                    await self._poll_once()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("Error in poller loop")
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            logger.info("Status poller stopped")

    async def _poll_once(self) -> None:
        """Single polling iteration."""
        # Update status gauges
        stats = await self._db.get_processing_stats()
        for status_name, count in stats.items():
            IMAGES_BY_STATUS.labels(status=status_name).set(count)

        # Get all active (non-final) images plus recently completed ones
        active_images = await self._db.get_active_images()

        for image in active_images:
            image_id: str = image["id"]
            current_status: str = image["status"]
            user_id: int = image["user_id"]
            message_id: Optional[int] = image.get("telegram_message_id")

            last_status = self._tracked.get(image_id)

            if last_status != current_status:
                self._tracked[image_id] = current_status
                if current_status != 'received':
                    await self._notify_status_change(
                        user_id=user_id,
                        message_id=message_id,
                        image=image,
                        new_status=current_status,
                    )

        # Check for images that transitioned to final status
        finished_images = await self._db.get_not_sent_final_images()
        for image in finished_images:
            if image:
                if image["status"] == "done":
                    await self._send_done(image)
                elif image["status"] == "failed":
                    await self._send_failed(image)

                await self._db.update_final_image_sent(image_id=image['id'])

            if image['id'] in self._tracked:
                del self._tracked[image['id']]

    async def _notify_status_change(
        self,
        user_id: int,
        message_id: Optional[int],
        image: dict[str, Any],
        new_status: str,
    ) -> None:
        """Edit the status message when status changes."""
        if message_id is None:
            return

        text = (
            f"📊 <b>Image Status Update</b>\n\n"
            f"ID: <code>{str(image['id'])[:8]}...</code>\n"
            f"Status: {self._format_status(new_status)}"
        )

        try:
            await self._bot.edit_message_text(
                chat_id=user_id,
                message_id=message_id,
                text=text,
            )
        except Exception:
            logger.exception(
                "Failed to edit message %d for user %d",
                message_id,
                user_id,
            )

    async def _send_done(self, image: dict[str, Any]) -> None:
        """Delete status message and send the processed photo."""
        user_id: int = image["user_id"]
        message_id: Optional[int] = image.get("telegram_message_id")

        # Delete the status message first
        if message_id is not None:
            try:
                await self._bot.delete_message(
                    chat_id=user_id,
                    message_id=message_id,
                )
            except Exception:
                logger.exception("Failed to delete status message")

        # Download processed image and send it
        try:
            s3_key: str = image["processed_s3_key"]
            image_bytes = self._s3.download_image(s3_key, processed=True)
            input_file = BufferedInputFile(
                file=image_bytes, filename="result.jpg"
            )
            await self._bot.send_photo(
                chat_id=user_id,
                photo=input_file,
                caption="🎉 <b>Your transformed image is ready!</b>",
            )
        except Exception:
            logger.exception("Failed to send processed image %s", image["id"])
            await self._bot.send_message(
                chat_id=user_id,
                text="❌ Error sending your processed image. "
                "Please try again.",
            )

    async def _send_failed(self, image: dict[str, Any]) -> None:
        """Notify user of processing failure with reason."""
        user_id: int = image["user_id"]
        message_id: Optional[int] = image.get("telegram_message_id")
        error_reason: str = image.get("error_reason", "Unknown error")

        text = (
            f"❌ <b>Processing Failed</b>\n\n"
            f"ID: <code>{image['id'][:8]}...</code>\n"
            f"Reason: <i>{error_reason}</i>\n\n"
            f"Please try again with a different image."
        )

        if message_id is not None:
            try:
                await self._bot.edit_message_text(
                    chat_id=user_id,
                    message_id=message_id,
                    text=text,
                )
                return
            except Exception:
                logger.exception("Failed to edit message %d", message_id)

        try:
            await self._bot.send_message(chat_id=user_id, text=text)
        except Exception:
            logger.exception("Failed to send failure message to user %d", user_id)

    @staticmethod
    def _format_status(status: str) -> str:
        """Format status with emoji."""
        emojis = {
            "received": "📥",
            "preprocessing": "⚙️",
            "quality_check": "🔍",
            "processing": "🧠",
            "postprocessing": "🎨",
            "done": "✅",
            "failed": "❌",
        }
        emoji = emojis.get(status, "❓")
        return f"{emoji} <b>{status.upper()}</b>"
