"""Image postprocessing module — converts tensor back to PIL Image."""

from __future__ import annotations

import logging
from typing import Optional

import torch
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
            # Handle different tensor layouts
            if tensor.dim() == 3:
                if tensor.shape[0] in (1, 3, 4):
                    # (C, H, W) -> (H, W, C)
                    tensor = tensor.permute(1, 2, 0)
                array = tensor.cpu().numpy().astype("uint8")
            else:
                raise ValueError(
                    f"Unexpected tensor dimensions: {tensor.dim()}"
                )

            if array.shape[2] == 1:
                array = array.squeeze(axis=2)
                mode = "L"
            elif array.shape[2] == 3:
                mode = "RGB"
            elif array.shape[2] == 4:
                mode = "RGBA"
            else:
                mode = "RGB"
                array = array[:, :, :3]

            return Image.fromarray(array, mode=mode)

        except Exception as exc:
            raise ValueError(
                f"Failed to postprocess image: {exc}"
            ) from exc
