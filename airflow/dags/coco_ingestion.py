from airflow import DAG
from airflow.operators.python import PythonOperator
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
import structlog
from pathlib import Path
import uuid
from prometheus_client import Counter, start_http_server
import threading

logger = structlog.get_logger()

COCO_URL_BASE = "http://images.cocodataset.org/train2017/"
BATCH_SIZE = 100

server_thread = None

def init_metrics_server():
    global server_thread
    if server_thread is None:
        server_thread = threading.Thread(target=start_http_server, args=(9100,))
        server_thread.daemon = True
        server_thread.start()

coco_images_downloaded = Counter(
    'coco_images_downloaded_total',
    'Total images downloaded from COCO dataset'
)

coco_images_rejected = Counter(
    'coco_images_rejected_total',
    'Total images rejected during validation',
    ['reason']
)

coco_images_uploaded = Counter(
    'coco_images_uploaded_total',
    'Total images uploaded to MinIO'
)

rabbitmq_published = Counter(
    'rabbitmq_published_total',
    'Total messages published to RabbitMQ',
    ['status']
)

def download_with_retry(url, target_path, max_retries=3):
    for attempt in range(max_retries):
        try:
            urllib.request.urlretrieve(url, target_path)
            return True
        except HTTPError as e:
            if e.code in [404, 403]:
                logger.error("permanent_error", url=url, code=e.code)
                raise
            if e.code in [500, 502, 503, 504]:
                if attempt < max_retries - 1:
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

def download_coco_images(**context):
    init_metrics_server()
    image_ids = context['dag_run'].conf.get('image_ids', [i for i in range(1, 101)]) if context['dag_run'].conf else [i for i in range(1, 101)]
    downloaded_files = []

    for img in image_ids:
        filename = f"{img:012d}.jpg"
        url = f"{COCO_URL_BASE}{filename}"
        tmp_path = f"/tmp/{filename}"

        logger.info("downloading", url=url)
        download_with_retry(url, tmp_path)
        coco_images_downloaded.inc()
        downloaded_files.append(tmp_path)
        time.sleep(1)

    context['ti'].xcom_push(key='downloaded_files', value=downloaded_files)
    return len(downloaded_files)

def validate_and_upload_to_minio(**context):
    downloaded_files = context['ti'].xcom_pull(task_ids='download_coco_images', key='downloaded_files')
    uploaded_keys = []

    for tmp_path in downloaded_files:
        is_valid, reject_reason, metrics = validate_image_quality(tmp_path)
        if not is_valid:
            logger.warning("image_rejected", path=tmp_path, reason=reject_reason)
            coco_images_rejected.labels(reason=reject_reason.split(':')[0]).inc()
            os.unlink(tmp_path)
            continue

        s3_key = upload_to_minio(tmp_path)
        coco_images_uploaded.inc()
        uploaded_keys.append(s3_key)
        os.unlink(tmp_path)

    context['ti'].xcom_push(key='uploaded_keys', value=uploaded_keys)
    return len(uploaded_keys)

def validate_image_quality(image_path):
    image = cv2.imread(image_path)
    if image is None:
        return False, "corruption", {}

    height, width = image.shape[:2]
    if width < 224 or height < 224:
        return False, f"dimensions: {width}x{height}", {}

    gray = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    laplacian = cv2.Laplacian(gray, cv2.CV_64F)
    variance = laplacian.var()
    if variance < 100.0:
        return False, f"blur: variance={variance}", {}

    return True, None, {"dimensions": (width, height)}

def upload_to_minio(file_path):
    s3_client = boto3.client(
        's3',
        endpoint_url="http://minio:9000",
        aws_access_key_id=os.environ.get('MINIO_ROOT_USER', 'minioadmin'),
        aws_secret_access_key=os.environ.get('MINIO_ROOT_PASSWORD', 'minioadmin'),
        region_name='us-east-1'
    )

    with open(file_path, "rb") as f:
        sha256_hash = hashlib.sha256()
        for chunk in iter(lambda: f.read(4096), b""):
            sha256_hash.update(chunk)
        image_hash = sha256_hash.hexdigest()

    s3_key = f"dataset/{image_hash}{Path(file_path).suffix}"
    s3_client.upload_file(file_path, "dataset", s3_key)
    return s3_key

def publish_message_sync(message):
    asyncio.run(_publish_async(message))

async def _publish_async(message_dict):
    connection = await aio_pika.connect_robust("amqp://app:secure_password@rabbitmq:5672/")
    async with connection:
        channel = await connection.channel()
        queue = await channel.declare_queue("segmentation_tasks", durable=True)

        message = aio_pika.Message(
            body=json.dumps(message_dict).encode("utf-8"),
            content_type="application/json",
            delivery_mode=2,
            headers={"correlation_id": message_dict["correlation_id"], "source": message_dict["source"]}
        )

        await channel.default_exchange.publish(message, routing_key="segmentation_tasks")

def publish_to_queue(**context):
    uploaded_keys = context['ti'].xcom_pull(task_ids='validate_and_upload_to_minio', key='uploaded_keys')

    for s3_key in uploaded_keys:
        message = {
            "s3_key": s3_key,
            "source": "coco_dataset",
            "correlation_id": str(uuid.uuid4()),
            "timestamp": datetime.utcnow().isoformat()
        }
        try:
            publish_message_sync(message)
            rabbitmq_published.labels(status="success").inc()
            logger.info("published_to_queue", s3_key=s3_key)
        except Exception as e:
            rabbitmq_published.labels(status="error").inc()
            raise
    return len(uploaded_keys)

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

    download_task >> validate_upload_task >> publish_task
