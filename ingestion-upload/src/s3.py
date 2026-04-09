import hashlib
from pathlib import Path
import aioboto3
from config import get_settings

class S3Client:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(S3Client, cls).__new__(cls)
            settings = get_settings()
            session = aioboto3.Session()
            cls._instance.client = session.client(
                's3',
                endpoint_url=f"http://{settings.MINIO_ENDPOINT}",
                aws_access_key_id=settings.MINIO_ACCESS_KEY,
                aws_secret_access_key=settings.MINIO_SECRET_KEY,
            )
            cls._instance.bucket_name = settings.BUCKET_NAME
        return cls._instance

    async def upload_file(self, file_path: str, s3_key: str):
        await self.client.upload_file(file_path, self.bucket_name, s3_key)


async def calculate_file_hash(file_path: str) -> str:
    hash_sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_sha256.update(chunk)
    return hash_sha256.hexdigest()

async def upload_to_s3(file_path: str) -> str:
    s3_client = S3Client()
    image_hash = await calculate_file_hash(file_path)
    file_extension = Path(file_path).suffix
    s3_key = f"dataset/{image_hash}{file_extension}"
    
    await s3_client.upload_file(file_path, s3_key)
    return s3_key
