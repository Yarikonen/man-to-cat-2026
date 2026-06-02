"""Image postprocessing module — converts tensor back to PIL Image."""

from __future__ import annotations

import logging

import torch
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)


class PostprocessingModule:
    """Postprocesses model output tensor into a final PIL Image.

    This is a stub implementation. Replace with actual postprocessing
    logic (denormalize, resize, format conversion, etc.).
    """

    @staticmethod
    def process(tensor: torch.Tensor) -> Image.Image:
        """Convert model output tensor to a final PIL Image.

        Args:
            tensor: Output tensor from PrimaryModelModule.

        Returns:
            Final processed PIL Image.

        Raises:
            ValueError: If tensor cannot be converted to a valid image.
        """
        logger.info(
            "Postprocessing: tensor shape=%s, dtype=%s",
            tensor.shape,
            tensor.dtype,
        )

        try:
            img = ((tensor[0].detach().numpy().transpose(1, 2, 0) + 1.0) * 127.5).astype(np.uint8)
            return Image.fromarray(img, mode="RGB")

        except Exception as exc:
            raise ValueError(
                f"Failed to postprocess image: {exc}"
            ) from exc
