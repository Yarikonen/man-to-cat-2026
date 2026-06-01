"""Image preprocessing module — converts raw image bytes to torch tensor."""

from __future__ import annotations

import io
import logging
from typing import TYPE_CHECKING, Optional

import torch
from PIL import Image

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class PreprocessingModule:
    """Preprocesses raw image bytes into a torch tensor for model input.

    This is a stub implementation. Replace with actual preprocessing
    logic (resize, normalize, to_tensor, etc.).
    """

    @staticmethod
    def process(image_bytes: bytes) -> torch.Tensor:
        """Convert raw image bytes to a preprocessed torch tensor.

        Args:
            image_bytes: Raw image data (JPEG/PNG bytes).

        Returns:
            Preprocessed image as a torch.Tensor (C, H, W).

        Raises:
            ValueError: If the image data is invalid or cannot be decoded.
        """
        try:
            image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            logger.info(
                "Preprocessed image: size=%s, mode=%s",
                image.size,
                image.mode,
            )
            tensor = torch.tensor(
                bytearray(image.tobytes()),
                dtype=torch.uint8,
            ).reshape(image.size[1], image.size[0], 3)
            return tensor

        except Exception as exc:
            raise ValueError(f"Failed to preprocess image: {exc}") from exc
