from fastapi import FastAPI, File, UploadFile, HTTPException
from typing import Dict
import structlog
from src.s3 import upload_to_s3
from src.validation import validate_image_quality
import tempfile
import os
import shutil
from pathlib import Path
from prometheus_client import Counter, Histogram, CollectorRegistry, make_asgi_app
import time
import aio_pika
import json
import uuid
import asyncio
from datetime import datetime

app = FastAPI(title="Ingestion Upload Service")
logger = structlog.get_logger()

registry = CollectorRegistry()

images_ingested = Counter(
    'images_ingested_total',
    'Total number of images ingested',
    ['source', 'status', 'method'],
    registry=registry
)

images_rejected = Counter(
    'images_rejected_total',
    'Total number of images rejected by validation',
    ['source', 'reason'],
    registry=registry
)

validation_duration = Histogram(
    'image_validation_duration_seconds',
    'Duration of image validation process',
    registry=registry
)

metrics_app = make_asgi_app(registry=registry)
app.mount("/metrics", metrics_app)

def _get_rabbitmq_connection():
    return aio_pika.connect_robust("amqp://app:secure_password@rabbitmq:5672/")

async def publish_upload_message(s3_key: str, source: str = "upload"):
    correlation_id = str(uuid.uuid4())
    log = logger.bind(correlation_id=correlation_id)

    message = {
        "s3_key": s3_key,
        "source": source,
        "correlation_id": correlation_id,
        "timestamp": datetime.utcnow().isoformat()
    }

    try:
        connection = await _get_rabbitmq_connection()
        async with connection:
            channel = await connection.channel()
            queue = await channel.declare_queue(
                "segmentation_tasks",
                durable=True,
                arguments={
                    "x-dead-letter-exchange": "",
                    "x-dead-letter-routing-key": "segmentation_tasks_dlq"
                }
            )

            message_obj = aio_pika.Message(
                body=json.dumps(message).encode("utf-8"),
                content_type="application/json",
                delivery_mode=2,
                headers={
                    "correlation_id": correlation_id,
                    "source": source
                }
            )

            await channel.default_exchange.publish(
                message_obj,
                routing_key="segmentation_tasks"
            )

            log.info("published_to_queue", s3_key=s3_key)
            return correlation_id

    except Exception as e:
        log.error("publish_failed", error=str(e))
        raise

@app.post("/api/v1/upload", status_code=201, response_model=Dict)
async def upload_image(file: UploadFile = File(...)):
    if file.content_type not in ["image/jpeg", "image/png"]:
        images_rejected.labels(source="upload", reason="invalid_content_type").inc()
        raise HTTPException(status_code=400, detail="Invalid file type. Only JPEG/JPG and PNG allowed.")

    with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename).suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    try:
        start_time = time.time()
        with validation_duration.time():
            is_valid, reject_reason, metrics = validate_image_quality(tmp_path)
        
        if not is_valid:
            images_rejected.labels(source="upload", reason=reject_reason.split(':')[0]).inc()
            raise HTTPException(status_code=400, detail=f"Image validation failed: {reject_reason}")

        s3_key = upload_to_s3(tmp_path)
        images_ingested.labels(source="upload", status="success", method="rest").inc()
        
        correlation_id = await publish_upload_message(s3_key, "upload")

        return {"s3_key": s3_key, "status": "queued", "correlation_id": correlation_id}

    except Exception as e:
        images_ingested.labels(source="upload", status="error", method="rest").inc()
        raise
    finally:
        os.unlink(tmp_path)

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
