"""Quality gate module — decides whether an image should be processed."""

from __future__ import annotations

import logging
from typing import Optional, Tuple

import torch

logger = logging.getLogger(__name__)


class QualityGateModule:
    """Checks if an image meets quality standards for processing.

    This is a stub implementation. Replace with actual quality gate
    model inference (blur detection, NSFW check, content validation, etc.).
    """

    @staticmethod
    def check(tensor: torch.Tensor) -> Tuple[bool, Optional[str]]:
        """Evaluate whether the image should proceed to processing.

        Args:
            tensor: Preprocessed image tensor (C, H, W) or (H, W, C).

        Returns:
            A tuple of (should_process: bool, reason: str | None).
            If should_process is False, reason describes why it was rejected.
        """
        logger.info(
            "Quality gate check: tensor shape=%s, dtype=%s",
            tensor.shape,
            tensor.dtype,
        )

        # Stub: always approve
        # TODO: Replace with actual quality gate model inference
        return True, None
