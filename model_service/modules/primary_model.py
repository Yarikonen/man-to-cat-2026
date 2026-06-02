"""Primary model inference module — applies the ML transformation."""

from __future__ import annotations

import logging
import torch

from shared.config import get_settings
from shared.s3_client import S3Client
from model_service.modules.model.generator import Generator
from model_service.modules.model.content_encoder import ContentEncoder

logger = logging.getLogger(__name__)


class PrimaryModelModule:
    def __init__(self, s3: S3Client):
        self.s3 = s3
        self.settings = get_settings()
        self.device = self.settings.model_device
        self.content_encoder_name = self.settings.content_encoder_name
        self.generator_name = self.settings.generator_name

        self._init_models()

    def _init_models(self):
        self.netEC = ContentEncoder()
        self.netEC.eval()
        self.netG = Generator()
        self.netG.eval()

        encoder_weights = self.s3.get_model_weights(self.content_encoder_name)
        self.netEC.load_state_dict(torch.load(encoder_weights, map_location=lambda storage, loc: storage))

        generator_chpt = self.s3.get_model_weights(self.generator_name)
        self.netG.load_state_dict(torch.load(generator_chpt, map_location=lambda storage, loc: storage)['g_ema'])

        self.netEC = self.netEC.to(self.device)
        self.netG = self.netG.to(self.device)

        logger.info("Encoder and generator models loaded")

    def infer(self, human: torch.Tensor, cat: torch.Tensor) -> torch.Tensor:
        """Run primary model inference on the preprocessed tensor.

        Args:
            human: Preprocessed human image tensor from PreprocessingModule.
            cat: Preprocessed cat style image tensor from PreprocessingModule.

        Returns:
            Transformed image tensor.

        Raises:
            RuntimeError: If model inference fails.
        """
        with torch.no_grad():
            content_feature = self.netEC(human.to(self.device), get_feature=True)
            generated, _ = self.netG(content_feature, cat.to(self.device))

        return generated.cpu()
