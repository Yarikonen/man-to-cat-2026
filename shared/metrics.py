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

# ─── Data-level metrics ─────────────────────────────────────────────
# Images rejected by the quality gate, by reason (data quality signal).
QUALITY_REJECTIONS = Counter(
    "quality_gate_rejections_total",
    "Total number of images rejected by the quality gate, by reason",
    labelnames=["reason"],
)

# Resolution (megapixels) of incoming images — data freshness/quality &
# input distribution drift signal.
INPUT_MEGAPIXELS = Histogram(
    "input_image_megapixels",
    "Resolution of incoming images in megapixels",
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0),
)

# ─── Model-level metrics ────────────────────────────────────────────
# CLIP cosine similarity between the input face and the selected nearest
# cat. Doubles as a model-confidence proxy and an input-drift detector:
# low values mean the input looks unlike anything in the cat gallery.
MODEL_CLIP_SIMILARITY = Histogram(
    "model_clip_similarity",
    "CLIP cosine similarity between input face and selected nearest cat",
    buckets=(0.0, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.7, 1.0),
)


def start_metrics_server(port: int) -> None:
    """Start the Prometheus HTTP metrics server on the given port."""
    start_http_server(port)
