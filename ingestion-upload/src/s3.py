import hashlib
from pathlib import Path
import boto3
from config import get_settings

settings = get_settings()


def calculate_file_hash(file_path: str) -> str:
    """Calculate SHA256 hash of file content."""
    hash_sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_sha256.update(chunk)
    return hash_sha256.hexdigest()


def upload_to_s3(file_path: str) -> str:
    """Upload file to MinIO with deterministic key generation."""
    image_hash = calculate_file_hash(file_path)
    s3_key = f"dataset/{image_hash}{Path(file_path).suffix}"

    # Using aioboto3 for async in the FastAPI endpoint,
    # but using boto3 sync for consistency with initial version
    s3_client = boto3.client(
        's3',
        endpoint_url=f"http://{settings.MINIO_ENDPOINT}",
        aws_access_key_id=settings.MINIO_ACCESS_KEY,
        aws_secret_access_key=settings.MINIO_SECRET_KEY,
        region_name='us-east-1'
    )

    s3_client.upload_file(file_path, settings.BUCKET_NAME, s3_key)
    return s3_key


async def upload_to_s3_async(file_path: str) -> str:
    """Async version for use with aio-pika integration."""
    from aioboto3 import Session
    import aioboto3

    image_hash = calculate_file_hash(file_path)
    s3_key = f"dataset/{image_hash}{Path(file_path).suffix}"

    async with aioboto3.Session().client(
        's3',
        endpoint_url=f"http://{settings.MINIO_ENDPOINT}",
        aws_access_key_id=settings.MINIO_ACCESS_KEY,
        aws_secret_access_key=settings.MINIO_SECRET_KEY,
        region_name='us-east-1'
    ) as s3_client:
        await s3_client.upload_file(file_path, settings.BUCKET_NAME, s3_key)

    return s3_key