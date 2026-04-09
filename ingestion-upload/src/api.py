from fastapi import FastAPI, File, UploadFile, HTTPException
from typing import Dict
import structlog
from src.s3 import upload_to_s3
from src.validation import validate_image_quality
import tempfile
import os
import shutil
from pathlib import Path

app = FastAPI(title="Ingestion Upload Service")
logger = structlog.get_logger()

@app.on_event("startup")
async def startup_event():
    logger.info("ingestion-upload service ready", correlation_id="upload_start")

@app.post("/api/v1/upload", status_code=201, response_model=Dict)
async def upload_image(file: UploadFile = File(...)):
    if file.content_type not in ["image/jpeg", "image/png"]:
        raise HTTPException(status_code=400, detail="Invalid file type. Only JPEG/JPG and PNG allowed.")

    try:
        suffix = Path(file.filename).suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            shutil.copyfileobj(file.file, tmp)
            tmp_path = tmp.name
    finally:
        file.file.close()

    try:
        is_valid, reject_reason, metrics = validate_image_quality(tmp_path)
        if not is_valid:
            logger.warning("Image validation failed", reason=reject_reason, filename=file.filename)
            raise HTTPException(status_code=400, detail=f"Image validation failed: {reject_reason}")

        s3_key = await upload_to_s3(tmp_path)
        logger.info("Image uploaded successfully", s3_key=s3_key, filename=file.filename)

        return {"s3_key": s3_key, "status": "queued"}

    finally:
        os.unlink(tmp_path)

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
