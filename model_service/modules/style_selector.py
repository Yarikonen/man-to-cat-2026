import torch
import numpy as np
from PIL import Image
from transformers import AutoImageProcessor, AutoModel

from shared.config import get_settings
from shared.s3_client import S3Client
from model_service.modules.bridge.schrodinger_bridge import SchrodingerBridgeMapper


class StyleSelectorModule:
    def __init__(self, s3: S3Client):
        self.s3 = s3
        self.settings = get_settings()
        self.device = self.settings.model_device

        self.processor = AutoImageProcessor.from_pretrained(self.settings.embedding_hf_model_name)
        self.embedding_model = AutoModel.from_pretrained(
            self.settings.embedding_hf_model_name, device_map="auto"
        )

        self._load_schrodinger_bridge()
        self._load_cats_paths()

    def _load_schrodinger_bridge(self):
        bridge_params = self.s3.get_model_weights(self.settings.schrodinger_bridge_params)
        bridge_params = np.load(bridge_params)

        self.schrodinger_bridge = SchrodingerBridgeMapper()
        self.schrodinger_bridge.cats = bridge_params["cat_embs"]
        self.schrodinger_bridge.v_ = bridge_params["v"]
        self.schrodinger_bridge.epsilon_used_ = bridge_params["epsilon_used"]

    def _load_cats_paths(self):
        cats_paths_raw = self.s3.get_model_weights(self.settings.schrodinger_bridge_cats_paths)
        cats_paths = cats_paths_raw.getvalue().decode('utf-8')
        self.cats_paths = cats_paths.split(";")

    def get_style(self, human: Image):
        inputs = self.processor([human], return_tensors="pt").to(self.device)

        with torch.inference_mode():
            outputs = self.embedding_model(**inputs)
            human_emb = outputs.pooler_output.cpu().numpy()

        cat_emb = self.schrodinger_bridge.transform(human_emb)
        closest_cat_idx = self.schrodinger_bridge.find_closest(cat_emb)[0]

        cat_path = self.cats_paths[closest_cat_idx]
        return cat_path
