import hashlib
from pathlib import Path
import boto3
from config.settings import get_settings
import logging

settings = get_settings()
s3_client = boto3.client(
    's3',
    endpoint_url=f"http://{settings.MINIO_ENDPOINT}",
    aws_access_key_id=settings.MINIO_ACCESS_KEY,
    aws_secret_access_key=settings.MINIO_SECRET_KEY,
    region_name='us-east-1'
)

def calculate_file_hash(file_path: str) -> str:
    """Calculates the SHA256 hash of a file."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def upload_to_s3(file_path: str) -> str:
    """Uploads a file to S3 and returns the S3 key."""
    file_hash = calculate_file_hash(file_path)
    file_extension = Path(file_path).suffix
    s3_key = f"dataset/{file_hash}{file_extension}"
    
    try:
        s3_client.upload_file(file_path, settings.BUCKET_NAME, s3_key)
        logging.info(f"Successfully uploaded {file_path} to s3://{settings.BUCKET_NAME}/{s3_key}")
        return s3_key
    except Exception as e:
        logging.error(f"Failed to upload {file_path} to S3: {e}")
        raise
