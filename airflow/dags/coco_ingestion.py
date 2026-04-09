from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.models import Variable
from datetime import datetime, timedelta
import urllib.request
import time
from urllib.error import HTTPError, URLError
import os
import cv2
import hashlib
import boto3
import json
import aio_pika
import asyncio
import uuid
import structlog
from pathlib import Path

logger = structlog.get_logger()

# Configuration
COCO_URL_BASE = "http://images.cocodataset.org/train2017/"
COCO_URL_VAL = "http://images.cocodataset.org/val2017/"
MAX_IMAGES = int(Variable.get("max_images_per_run", default_var=100))
BATCH_SIZE = 10


# Metrics setup
try:
    from prometheus_client import Counter, start_http_server
    import threading

    prometheus_initialized = False

    def init_metrics_server():
        global prometheus_initialized
        if not prometheus_initialized:
            metrics_thread = threading.Thread(target=start_http_server, args=(9100,))
            metrics_thread.daemon = True
            metrics_thread.start()
            prometheus_initialized = True

    # Metrics
    coco_images_downloaded = Counter('coco_images_downloaded_total', 'Total images downloaded from COCO dataset')
    coco_images_rejected = Counter('coco_images_rejected_total', 'Total images rejected during validation', ['reason'])
    coco_images_uploaded = Counter('coco_images_uploaded_total', 'Total images uploaded to MinIO')
   rabbitmq_published = Counter('rabbitmq_published_total', 'Total messages published to RabbitMQ', ['status', 'source'])

except ImportError:
    # Fallback if prometheus not available
    init_metrics_server = lambda: None
    coco_images_downloaded = coco_images_rejected = coco_images_uploaded = rabbitmq_published = type('', (), {'inc': lambda self, **kwargs: None, 'labels': lambda self, **kwargs: self})()


def download_with_retry(url, target_path, max_retries=3):
    """Download file with exponential backoff and retry logic."""
    for attempt in range(max_retries):
        try:
            urllib.request.urlretrieve(url, target_path)
            return True
        except HTTPError as e:
            if e.code in [404, 403]:
                logger.error("permanent_error", url=url, code=e.code)
                raise
            if e.code in [500, 502, 503, 504] and attempt < max_retries - 1:
                logger.warning("transient_error", url=url, code=e.code, attempt=attempt, backoff=2**attempt)
                time.sleep(2 ** attempt)
                continue
            else:
                raise
        except URLError as e:
            if attempt < max_retries - 1:
                logger.warning("network_error", url=url, error=str(e), attempt=attempt, backoff=2**attempt)
                time.sleep(2 ** attempt)
                continue
            else:
                raise
    return False


def detect_corruption(image_path):
    """Check if image is corrupted."""
    try:
        image = cv2.imread(image_path)
        if image is None:
            return True, "cv2.imread returned None"
        return False, None
    except Exception as e:
        return True, f"Exception during read: {str(e)}"


def validate_dimensions(image_path, min_width=224, min_height=224):
    """Validate image dimensions."""
    image = cv2.imread(image_path)
    if image is None:
        return False, (0, 0)

    height, width = image.shape[:2]
    is_valid = width >= min_width and height >= min_height
    return is_valid, (width, height)


def detect_blur(image_path, threshold=100.0):
    """Detect blur using Laplacian variance."""
    try:
        gray = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
        if gray is None:
            return True, 0.0
        laplacian = cv2.Laplacian(gray, cv2.CV_64F)
        variance = laplacian.var()
        return variance < threshold, variance
    except Exception as e:
        return True, 0.0


def validate_image_quality(image_path):
    """Complete image validation pipeline."""
    metrics = {}

    # Corruption check
    is_corrupt, corrupt_reason = detect_corruption(image_path)
    if is_corrupt:
        coco_images_rejected.labels(reason="corruption").inc()
        return False, f"corruption: {corrupt_reason}", metrics

    # Dimension validation
    is_valid_dims, dimensions = validate_dimensions(image_path, 224, 224)
    metrics["dimensions"] = dimensions
    if not is_valid_dims:
        w, h = dimensions
        coco_images_rejected.labels(reason="dimensions").inc()
        return False, f"dimensions: {w}x{h} < 224x224", metrics

    # Blur detection
    is_blurry, variance = detect_blur(image_path, threshold=100.0)
    metrics["blur_variance"] = variance
    if is_blurry:
        coco_images_rejected.labels(reason="blur").inc()
        return False, f"blur: variance={variance:.2f} < 100.0", metrics

    return True, None, metrics


def upload_to_minio(file_path):
    """Upload file to MinIO with deterministic key."""
    s3_client = boto3.client(
        's3',
        endpoint_url=f"http://minio:9000",
        aws_access_key_id=os.environ.get('MINIO_ROOT_USER', 'minioadmin'),
        aws_secret_access_key=os.environ.get('MINIO_ROOT_PASSWORD', 'minioadmin'),
        region_name='us-east-1'
    )

    # Generate deterministic key
    with open(file_path, "rb") as f:
        sha256_hash = hashlib.sha256()
        for chunk in iter(lambda: f.read(4096), b""):
            sha256_hash.update(chunk)
        image_hash = sha256_hash.hexdigest()

    s3_key = f"dataset/{image_hash}{Path(file_path).suffix}"
    s3_client.upload_file(file_path, "dataset", s3_key)
    return s3_key


def publish_message_sync(message):
    """Synchronous wrapper for aio-pika publishing."""
    asyncio.run(_publish_async(message))


async def _publish_async(message):
    """Async implementation of message publishing."""
    connection = await aio_pika.connect_robust(f"amqp://app:secure_password@rabbitmq:5672/")
    async with connection:
        channel = await connection.channel()
        queue = await channel.declare_queue("segmentation_tasks", durable=True)

        message_obj = aio_pika.Message(
            body=json.dumps(message).encode("utf-8"),
            content_type="application/json",
            delivery_mode=2,
            headers={
                "correlation_id": message["correlation_id"],
                "source": message["source"]
            }
        )

        await channel.default_exchange.publish(message_obj, routing_key="segmentation_tasks")


def download_coco_images(**context):
    """Download images from COCO dataset."""
    init_metrics_server()

    # Get image IDs from DAG config or use default range
    image_ids = context.get(' dag_run', {}).get('conf', {}).get('image_ids', [i for i in range(1, 1001)] if 'max_images_per_run' not in context else slice(0, MAX_IMAGES))
    if not isinstance(image_ids, list):
        image_ids = list(range(1, MAX_IMAGES + 1))

    downloaded_files = []
    base_urls = [COCO_URL_BASE, COCO_URL_VAL]

    for i, img_id in enumerate(image_ids):
        if i >= MAX_IMAGES:
            break

        # Try both train and val URLs
        filename = f"{img_id:012d}.jpg"
        found_url = None
        tmp_path = None

        for base_url in base_urls:
            url = f"{base_url}{filename}"
            tmp_path = f"/tmp/{filename}"

            try:
                logger.info("downloading", url=url, image_id=img_id)
                download_with_retry(url, tmp_path)
                downloaded_files.append(tmp_path)
                coco_images_downloaded.inc()

                # Rate limiting
                if (i + 1) % 10 == 0:  # Every 10 images
                    time.sleep(1)

                break
            except Exception as e:
                logger.warning("download_failed", url=url, error=str(e))
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
        else:
            logger.error("image_not_found", filename=filename)

    context['ti'].xcom_push(key='downloaded_files', value=downloaded_files)
    return len(downloaded_files)


def validate_and_upload_to_minio(**context):
    """Validate images and upload to MinIO."""
    downloaded_files = context['ti'].xcom_pull(task_ids='download_coco_images', key='downloaded_files')
    uploaded_keys = []

    for tmp_path in downloaded_files:
        try:
            is_valid, reject_reason, metrics = validate_image_quality(tmp_path)
            if not is_valid:
                logger.warning("image_rejected", path=tmp_path, reason=reject_reason)
                os.unlink(tmp_path)
                continue

            s3_key = upload_to_minio(tmp_path)
            uploaded_keys.append(s3_key)
            coco_images_uploaded.inc()
            logger.info("uploaded_to_s3", s3_key=s3_key, metrics=metrics)

        except Exception as e:
            logger.error("upload_failed", path=tmp_path, error=str(e))

        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    context['ti'].xcom_push(key='uploaded_keys', value=uploaded_keys)
    return len(uploaded_keys)


def publish_to_queue(**context):
    """Publish segmentation tasks to RabbitMQ."""
    uploaded_keys = context['ti'].xcom_pull(task_ids='validate_and_upload_to_minio', key='uploaded_keys')
    published_count = 0

    for s3_key in uploaded_keys:
        try:
            message = {
                "s3_key": s3_key,
                "source": "coco_dataset",
                "correlation_id": str(uuid.uuid4()),
                "timestamp": datetime.utcnow().isoformat()
            }

            publish_message_sync(message)
            rabbitmq_published.labels(status="success", source="coco").inc()
            published_count += 1
            logger.info("published_to_queue", s3_key=s3_key, source="coco_dataset")

        except Exception as e:
            rabbitmq_published.labels(status="error", source="coco").inc()
            logger.error("publish_failed", s3_key=s3_key, error=str(e))
            raise  # Let Airflow retry

    return published_count


# DAG Configuration
with DAG(
    dag_id='coco_ingestion',
    default_args={
        'owner': 'data-engineering',
        'depends_on_past': False,
        'email_on_failure': False,
        'email_on_retry': False,
        'retries': 3,
        'retry_delay': timedelta(seconds=30),
    },
    description='Download COCO dataset images and trigger segmentation',
    schedule_interval=timedelta(days=1),
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=['ingestion', 'coco'],
) as dag:

    download_task = PythonOperator(
        task_id='download_coco_images',
        python_callable=download_coco_images,
        provide_context=True
    )

    validate_upload_task = PythonOperator(
        task_id='validate_and_upload_to_minio',
        python_callable=validate_and_upload_to_minio,
        provide_context=True
    )

    publish_task = PythonOperator(
        task_id='publish_to_queue',
        python_callable=publish_to_queue,
        provide_context=True
    )

    # Task dependencies
    download_task >> validate_upload_task >> publish_task