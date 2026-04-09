import uvicorn
import structlog
import logging
from uuid import uuid4

def setup_logging():
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer()
        ],
        wrapper_class=structlog.make_filtering_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True
    )
    logger = structlog.get_logger()
    correlation_id = str(uuid4())
    structlog.contextvars.bind_contextvars(correlation_id=correlation_id)
    logger.info("ingestion-upload service ready")

if __name__ == "__main__":
    setup_logging()
    uvicorn.run("src.api:app", host="0.0.0.0", port=8000, reload=True)
