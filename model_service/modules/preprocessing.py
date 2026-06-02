"""Image preprocessing module — converts raw image bytes or PIL Image to torch tensor."""

from __future__ import annotations

import io
import logging
from typing import Optional

import torch
import torchvision.transforms as T
import torch.nn.functional as F
from PIL import Image

logger = logging.getLogger(__name__)

_DEFAULT_TRANSFORM = T.Compose([
    T.ToTensor(),
    T.Normalize(mean=[0.5, 0.5, 0.5], std=[0.5, 0.5, 0.5]),
])


class PreprocessingModule:
    """Preprocesses images into torch tensors for model input."""

    @staticmethod
    def bytes_to_pil(image_bytes: bytes) -> Image.Image:
        """Convert raw image bytes to a PIL Image.

        Args:
            image_bytes: Raw image data (JPEG/PNG bytes).

        Returns:
            PIL Image in RGB mode.

        Raises:
            ValueError: If the image data is invalid or cannot be decoded.
        """
        try:
            image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            logger.info("Decoded image: size=%s, mode=%s", image.size, image.mode)
            return image
        except Exception as exc:
            raise ValueError(f"Failed to decode image: {exc}") from exc

    @staticmethod
    def pil_to_tensor(
        image: Image,
        transform: Optional[T.Compose] = None,
    ) -> torch.Tensor:
        """Convert a PIL Image to a torch tensor.

        Args:
            image: PIL Image to convert.
            transform: Optional torchvision transform. Defaults to ToTensor().

        Returns:
            Image tensor in (C, H, W) format with float values in [-1, 1].
        """
        if transform is None:
            transform = _DEFAULT_TRANSFORM
        tensor = transform(image).unsqueeze(dim=0)
        tensor = F.interpolate(tensor, size=256, mode='bilinear', align_corners=True)
        logger.info("Converted to tensor: shape=%s, dtype=%s", tensor.shape, tensor.dtype)
        return tensor
