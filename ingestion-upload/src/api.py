from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
from typing import Dict
from pathlib import Path
import tempfile
import shutil
import structlog
import aio_pika
import uuid
import json
from datetime import datetime

from .s3 import upload_to_s3_async
from .validation import validate_image_quality
from config import get_settings

settings = get_settings()
logger = structlog.get_logger()

app = FastAPI(title="Ingestion Upload Service")


async def publish_upload_message(s3_key: str, source: str = "upload") -> str:
    """Publish message to RabbitMQ segmentation queue."""
    correlation_id = str(uuid.uuid4())
    log = logger.bind(correlation_id=correlation_id)

    message = {
        "s3_key": s3_key,
        "source": source,
        "correlation_id": correlation_id,
        "timestamp": datetime.utcnow().isoformat()
    }

    try:
        connection = await aio_pika.connect_robust(f"amqp://app:secure_password@rabbitmq:5672/")
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

            await channel.default_exchange.publish(message_obj, routing_key="segmentation_tasks")
            log.info("published_to_queue", s3_key=s3_key)
            return correlation_id

    except Exception as e:
        log.error("publish_failed", error=str(e))
        raise


@app.post("/api/v1/upload", status_code=201)
async def upload_image(file: UploadFile) -> Dict[str, str]:
    """Upload and validate image, then enqueue for segmentation."""
    log = logger.bind(correlation_id=str(uuid.uuid4()))

    if file.content_type not in ["image/jpeg", "image/png"]:
        log.warning("rejected_upload", reason="invalid_content_type", filename=file.filename)
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Only JPEG/JPG and PNG allowed."
        )

    with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename).suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    try:
        is_valid, reject_reason, metrics = validate_image_quality(tmp_path)
        if not is_valid:
            log.warning("rejected_image", filename=file.filename, reason=reject_reason)
            raise HTTPException(
                status_code=400,
                detail=f"Image validation failed: {reject_reason}"
            )

        log.info("image_validated", filename=file.filename, metrics=metrics)

        s3_key = await upload_to_s3_async(tmp_path)
        correlation_id = await publish_upload_message(s3_key, "upload")

        log.info("upload_complete", filename=file.filename, s3_key=s3_key, correlation_id=correlation_id)

        return {
            "s3_key": s3_key,
            "status": "queued",
            "correlation_id": correlation_id
        }

    finally:
        import os
        try:
            os.unlink(tmp_path)
        except (FileNotFoundError, OSError):
            pass


@app.get("/health")
async def health_check() -> Dict[str, str]:
    """Service health check endpoint."""
    return {"status": "healthy"}


@app.get("/")
async def root() -> Dict[str, str]:
    """Root endpoint with welcome message."""
    return {
        "service": "man2cat-ingestion-upload",
        "version": "1.0.0",
        "endpoints": {
            "upload": "/api/v1/upload",
            "health": "/health"
        }
    }