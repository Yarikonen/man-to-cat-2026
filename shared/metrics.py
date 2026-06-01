"""Prometheus metrics for the image processing service."""

from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    start_http_server,
)

# Processing duration by stage (seconds)
PROCESSING_DURATION = Histogram(
    "image_processing_duration_seconds",
    "Time spent processing images by stage",
    labelnames=["stage"],
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0),
)

# Current number of images in the Redis queue
QUEUE_SIZE = Gauge(
    "images_in_queue",
    "Number of images waiting in the processing queue",
)

# Current count of images in each status
IMAGES_BY_STATUS = Gauge(
    "images_in_status",
    "Number of images currently in each status",
    labelnames=["status"],
)

# Total images processed (counter, incremented on final status)
PROCESSED_TOTAL = Counter(
    "images_processed_total",
    "Total number of images processed by final status",
    labelnames=["status"],
)


def start_metrics_server(port: int) -> None:
    """Start the Prometheus HTTP metrics server on the given port."""
    start_http_server(port)
