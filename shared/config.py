"""Application configuration via environment variables."""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Telegram
    telegram_bot_token: str = ""
    hf_token: str = ""

    # model
    model_device: str = "cpu"
    content_encoder_name: str = "content_encoder.pt"
    generator_name: str = "face2cat.pt"
    embedding_hf_model_name: str = "facebook/dinov3-vitb16-pretrain-lvd1689m"
    schrodinger_bridge_params: str = "schrodinger_bridge.npz"
    schrodinger_bridge_cats_paths: str = "cats_paths.txt"

    # MinIO / S3
    minio_endpoint: str = "minio:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket_originals: str = "originals"
    minio_bucket_processed: str = "processed"
    minio_bucket_raw: str = "raw-images"
    minio_bucket_model: str = "model-weights"
    minio_secure: bool = False

    # Redis
    redis_url: str = "redis://redis:6379/0"
    redis_queue_name: str = "image_processing_queue"

    # PostgreSQL
    database_url: str = "postgresql://app:app@postgres:5432/man_to_cat"

    # Monitoring
    prometheus_port: int = 8000

    # Model service
    model_service_port: int = 8002

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    """Return cached Settings instance."""
    return Settings()
