"""Image processing pipeline orchestrator."""

from __future__ import annotations

import io
import logging
from contextlib import contextmanager
from typing import TYPE_CHECKING

from shared.db import DatabaseManager
from shared.s3_client import S3Client
from shared.metrics import (
    PROCESSING_DURATION,
    PROCESSED_TOTAL,
    QUALITY_REJECTIONS,
    INPUT_MEGAPIXELS,
)
from model_service.modules.preprocessing import PreprocessingModule
from model_service.modules.quality_gate import QualityGateModule
from model_service.modules.style_selector import StyleSelectorModule
from model_service.modules.primary_model import PrimaryModelModule
from model_service.modules.postprocessing import PostprocessingModule

if TYPE_CHECKING:
    from shared.queue import QueueManager

logger = logging.getLogger(__name__)


@contextmanager
def _stage_timer(stage: str):
    """Context manager to time a processing stage."""
    import time

    start = time.monotonic()
    try:
        yield
    finally:
        duration = time.monotonic() - start
        PROCESSING_DURATION.labels(stage=stage).observe(duration)


class Pipeline:
    """Orchestrates the 4-stage image processing pipeline."""

    def __init__(self, db: DatabaseManager, s3: S3Client) -> None:
        self._db = db
        self._s3 = s3
        self._preprocessing = PreprocessingModule()
        self._quality_gate = QualityGateModule()
        self._style_selector = StyleSelectorModule(s3)
        self._primary_model = PrimaryModelModule(s3)
        self._postprocessing = PostprocessingModule()

    async def process(self, image_id: str) -> None:
        """Process a single image through the full pipeline.

        Args:
            image_id: UUID of the image record.
        """
        logger.info("Starting pipeline for image %s", image_id)

        try:
            image_record = await self._db.get_image(image_id)
            if image_record is None:
                logger.error("Image %s not found in database", image_id)
                return

            original_key: str = image_record["original_s3_key"]

            # Stage 1: Preprocessing — decode bytes to PIL Image
            await self._db.update_status(image_id, "quality_check")
            with _stage_timer("quality_check"):
                image_bytes = self._s3.download_image(original_key)
                pil_image = self._preprocessing.bytes_to_pil(image_bytes)

                logger.info("Stage 1 complete: preprocessing for %s", image_id)

                # Stage 2: Quality Gate — size, blur, YOLO person detection, crop

                result = self._quality_gate.check(pil_image)

            if not result.passed:
                reason_text = result.reason or "Image did not pass quality check"
                await self._db.update_status(
                    image_id, "failed", error_reason=reason_text
                )
                PROCESSED_TOTAL.labels(status="failed").inc()
                QUALITY_REJECTIONS.labels(reason=reason_text or "unspecified").inc()
                logger.info(
                    "Image %s rejected by quality gate: %s",
                    image_id,
                    reason_text,
                )
                return

            cropped_image = result.cropped_image
            logger.info("Stage 2 complete: quality check for %s", image_id)

            # Stage 3: Style select
            await self._db.update_status(image_id, "style_select")
            with _stage_timer("style_select"):
                cat_path = self._style_selector.get_style(cropped_image)

                cat_bytes = self._s3.download_image(cat_path, raw=True)
                cat_image = self._preprocessing.bytes_to_pil(cat_bytes)

            logger.info("Stage 3 complete: style select model for %s, selected cat %s", image_id, cat_path)

            # Stage 4: Primary Model Inference — convert cropped image to tensor, run model
            await self._db.update_status(image_id, "processing")
            with _stage_timer("processing"):
                human_tensor = self._preprocessing.pil_to_tensor(cropped_image)
                cat_tensor = self._preprocessing.pil_to_tensor(cat_image)
                output_tensor = self._primary_model.infer(human_tensor, cat_tensor)

            logger.info("Stage 4 complete: primary model for %s", image_id)

            # Stage 5: Postprocessing — convert tensor back to PIL Image
            await self._db.update_status(image_id, "postprocessing")
            with _stage_timer("postprocessing"):
                final_image = self._postprocessing.process(output_tensor)
            logger.info("Stage 4 complete: postprocessing for %s", image_id)

            # Save processed image
            buffer = io.BytesIO()
            final_image.save(buffer, format="JPEG", quality=95)
            buffer.seek(0)

            processed_key = original_key  # Same UUID-based naming
            self._s3.upload_image(processed_key, buffer.read(), processed=True)

            # Mark as done
            await self._db.update_status(
                image_id,
                "done",
                processed_s3_key=processed_key,
            )
            PROCESSED_TOTAL.labels(status="done").inc()
            logger.info("Pipeline complete: image %s done", image_id)

        except Exception as exc:
            error_msg = str(exc)
            logger.exception("Pipeline failed for image %s", image_id)
            try:
                await self._db.update_status(
                    image_id, "failed", error_reason=error_msg
                )
                PROCESSED_TOTAL.labels(status="failed").inc()
            except Exception:
                logger.exception(
                    "Failed to update error status for %s", image_id
                )
