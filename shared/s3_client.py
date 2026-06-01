"""MinIO / S3 client wrapper for image storage."""

from __future__ import annotations

import io
import logging
from typing import Optional

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from shared.config import get_settings

logger = logging.getLogger(__name__)


class S3Client:
    """Wrapper around boto3 S3 client for MinIO operations."""

    def __init__(self) -> None:
        settings = get_settings()
        self._client = boto3.client(
            "s3",
            endpoint_url=(
                f"{'https' if settings.minio_secure else 'http'}://"
                f"{settings.minio_endpoint}"
            ),
            aws_access_key_id=settings.minio_access_key,
            aws_secret_access_key=settings.minio_secret_key,
            config=Config(signature_version="s3v4"),
            region_name="us-east-1",
        )
        self._bucket_originals = settings.minio_bucket_originals
        self._bucket_processed = settings.minio_bucket_processed

    def ensure_buckets(self) -> None:
        """Create required buckets if they don't exist."""
        for bucket in (self._bucket_originals, self._bucket_processed):
            try:
                self._client.head_bucket(Bucket=bucket)
            except ClientError:
                self._client.create_bucket(Bucket=bucket)
                logger.info("Created bucket: %s", bucket)

    def upload_image(
        self, key: str, image_data: bytes, processed: bool = False
    ) -> None:
        """Upload image bytes to S3."""
        bucket = (
            self._bucket_processed if processed else self._bucket_originals
        )
        self._client.put_object(
            Bucket=bucket,
            Key=key,
            Body=image_data,
            ContentType="image/jpeg",
        )
        logger.info("Uploaded to s3://%s/%s", bucket, key)

    def download_image(
        self, key: str, processed: bool = False
    ) -> bytes:
        """Download image bytes from S3."""
        bucket = (
            self._bucket_processed if processed else self._bucket_originals
        )
        response = self._client.get_object(Bucket=bucket, Key=key)
        return response["Body"].read()

    def get_presigned_url(
        self, key: str, processed: bool = False, expires_in: int = 3600
    ) -> str:
        """Generate a presigned URL for accessing an image."""
        bucket = (
            self._bucket_processed if processed else self._bucket_originals
        )
        url = self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expires_in,
        )
        return url

    @property
    def bucket_originals(self) -> str:
        return self._bucket_originals

    @property
    def bucket_processed(self) -> str:
        return self._bucket_processed
