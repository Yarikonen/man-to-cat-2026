from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    MINIO_ENDPOINT: str = "minio:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    BUCKET_NAME: str = "dataset"
    LOG_LEVEL: str = "INFO"


@lru_cache()
def get_settings():
    return Settings()