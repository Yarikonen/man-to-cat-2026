import uvicorn
import structlog
from fastapi import FastAPI
import aio_pika
import asyncio
import signal
import sys

from src.api import app
from config import get_settings

settings = get_settings()

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(sort_keys=True)
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    app.state.correlation_id = str(structlog.get_logger().bind().__dict__.get('correlation_id', uuid.uuid4()))
    logger.bind(correlation_id=app.state.correlation_id).info("ingestion-upload service starting")
    yield
    # Shutdown
    logger.bind(correlation_id=app.state.correlation_id).info("ingestion-upload service shutting down")


app = FastAPI(
    title="Ingestion Upload Service",
    version="1.0.0",
    lifespan=lifespan
)

# Import the API routes
from src.api import *


def setup_signal_handlers():
    """Setup graceful shutdown handlers."""
    def signal_handler(sig, frame):
        logger.info("received_shutdown_signal", signal=sig)
        sys.exit(0)

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)


if __name__ == "__main__":
    import uuid
    setup_signal_handlers()

    log = logger.bind(correlation_id=str(uuid.uuid4()))
    log.info("ingestion-upload service ready")

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level=settings.LOG_LEVEL.lower()
    )