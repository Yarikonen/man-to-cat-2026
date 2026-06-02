"""Quality gate module — validates image quality and detects humans with YOLO.

Checks performed in order:
1. Minimum size: image must be at least 128x128 pixels.
2. Blur detection: Laplacian variance must exceed the blur threshold.
3. Human detection: YOLO must find exactly one person with confidence >= 80%.
4. Bounding box size: the person's bbox must cover at least 50% of the image area.

If all checks pass, the image is cropped to the human bounding box and returned.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np
from PIL import Image
from ultralytics import YOLO

logger = logging.getLogger(__name__)

# COCO class index for "person"
_PERSON_CLASS = 0

# Thresholds
_MIN_SIDE = 128
_BLUR_THRESHOLD = 100.0  # Laplacian variance — lower = blurrier
_MIN_PERSON_CONFIDENCE = 0.80
_MIN_BBOX_AREA_RATIO = 0.50


@dataclass
class QualityGateResult:
    """Result of the quality gate check."""
    passed: bool
    reason: Optional[str] = None
    cropped_image: Optional[Image] = None


class QualityGateModule:
    """Validates images and extracts human crops using YOLO person detection."""

    def __init__(self, model_name: str = "yolo11n.pt") -> None:
        """Load the YOLO model once at startup.

        Args:
            model_name: Ultralytics YOLO model name or path to .pt file.
        """
        self._model = YOLO(model_name)
        logger.info("YOLO model loaded: %s", model_name)

    def check(self, image: Image) -> QualityGateResult:
        """Run all quality checks and return a cropped image if passed.

        Args:
            image: PIL Image in RGB mode.

        Returns:
            QualityGateResult with pass/fail status, optional rejection reason,
            and the cropped PIL Image (if all checks passed).
        """
        # 1. Size check
        w, h = image.size
        if w < _MIN_SIDE or h < _MIN_SIDE:
            reason = (
                f"Image too small: {w}x{h}, minimum is {_MIN_SIDE}x{_MIN_SIDE}"
            )
            logger.info("Quality gate rejected: %s", reason)
            return QualityGateResult(passed=False, reason=reason)

        # 2. Blur check
        blur_score = self._laplacian_variance(image)
        if blur_score < _BLUR_THRESHOLD:
            reason = (
                f"Image too blurry: Laplacian variance={blur_score:.1f}, "
                f"threshold={_BLUR_THRESHOLD}"
            )
            logger.info("Quality gate rejected: %s", reason)
            return QualityGateResult(passed=False, reason=reason)

        # 3. Human detection with YOLO
        results = self._model(image, verbose=False)
        detections = results[0]

        # Filter for person class with sufficient confidence
        person_boxes = []
        for box in detections.boxes:
            cls_id = int(box.cls.item())
            conf = float(box.conf.item())
            if cls_id == _PERSON_CLASS and conf >= _MIN_PERSON_CONFIDENCE:
                person_boxes.append((box, conf))

        if len(person_boxes) == 0:
            reason = (
                f"No person detected with confidence >= {_MIN_PERSON_CONFIDENCE:.0%}"
            )
            logger.info("Quality gate rejected: %s", reason)
            return QualityGateResult(passed=False, reason=reason)

        if len(person_boxes) > 1:
            reason = (
                f"Too many persons detected: {len(person_boxes)}, expected exactly 1"
            )
            logger.info("Quality gate rejected: %s", reason)
            return QualityGateResult(passed=False, reason=reason)

        # 4. Bounding box size check
        box, conf = person_boxes[0]
        x1, y1, x2, y2 = box.xyxy[0].tolist()
        bbox_area = (x2 - x1) * (y2 - y1)
        image_area = w * h
        bbox_ratio = bbox_area / image_area

        if bbox_ratio < _MIN_BBOX_AREA_RATIO:
            reason = (
                f"Person bounding box too small: {bbox_ratio:.1%} of image, "
                f"minimum is {_MIN_BBOX_AREA_RATIO:.0%}"
            )
            logger.info("Quality gate rejected: %s", reason)
            return QualityGateResult(passed=False, reason=reason)

        # All checks passed — crop to bounding box
        # Clamp coordinates to image bounds
        x1_i = max(0, int(round(x1)))
        y1_i = max(0, int(round(y1)))
        x2_i = min(w, int(round(x2)))
        y2_i = min(h, int(round(y2)))

        cropped = image.crop((x1_i, y1_i, x2_i, y2_i))
        logger.info(
            "Quality gate passed: person conf=%.2f, bbox_ratio=%.1f%%, "
            "cropped_size=%s",
            conf,
            bbox_ratio * 100,
            cropped.size,
        )
        return QualityGateResult(passed=True, cropped_image=cropped)

    @staticmethod
    def _laplacian_variance(image: Image.Image) -> float:
        """Compute the Laplacian variance of an image as a blur metric.

        Higher values indicate sharper images. Typical thresholds:
        - < 50: very blurry
        - 50-100: moderately blurry
        - > 100: sharp enough

        Args:
            image: PIL Image in any mode.

        Returns:
            Laplacian variance (float).
        """
        import cv2

        gray = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2GRAY)
        return float(cv2.Laplacian(gray, cv2.CV_64F).var())
