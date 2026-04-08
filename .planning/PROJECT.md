# Man-to-Cat AI Translation - Data Engineering

## What This Is

An AI service for man-to-cat image translation, currently focused on building the data engineering pipeline. Three containerized Python services process images: an Airflow orchestration layer for data collection, a YOLO-based segmentation service for extracting object masks and bounding boxes (persons and cats), and a preprocessing pipeline that prepares images for model training/inference with augmentation support.

## Core Value

All three data pipeline services integrated and working end-to-end. Everything else can be complex or deferred, but the full pipeline—from data collection through segmentation to preprocessed output—must flow reliably. Without this, there's nothing to train a model on.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Build Airflow DAGs for data collection from public datasets and user uploads
- [ ] Create segmentation service with YOLO model for mask/bbox extraction
- [ ] Develop preprocessing pipeline with augmentation for training data
- [ ] Integrate all services via RabbitMQ message queue
- [ ] Deploy and configure services via Docker Compose for local development
- [ ] Implement structured logging with correlation IDs
- [ ] Add Prometheus metrics for monitoring pipeline performance

### Out of Scope

- Complex ML model architecture (for now, pretrained YOLO only)
- Real-time camera feed processing (focus on batch processing first)
- Multi-region deployment (Docker Compose is local/dev only)
- OAuth/login (internal data pipelines)
- Model training/inference (only data prep now)

## Context

**Technical Decisions Made:**
- Message queue: RabbitMQ (async, reliable for task queuing)
- APIs: gRPC for internal services, REST for debug/external
- Storage: MinIO (S3-compatible) for images and metadata
- Orchestration: Airflow workflows
- Containerization: Docker Compose locally
- Observability: Prometheus metrics + structured JSON logging

**Workflow:**
1. Airflow collects images from public datasets or user uploads → saves to MinIO
2. Airflow publishes segmentation tasks to RabbitMQ
3. Segmentation service consumes tasks, runs YOLO inference, extracts masks/bboxes → saves to MinIO
4. Airflow polls queue for completion, triggers preprocessing DAG
5. Preprocessing service augments/normalizes images → ready for model training

**Scale Expectations:**
Near real-time processing (seconds, not minutes). Gigabyte-scale datasets initially. Pipeline must handle both batch dataset ingestion and sporadic user uploads.

## Constraints

- **Tech Stack**: Python-only services
- **Deployment**: Docker Compose locally (dev environment)
- **Communication**: Async via message queue (RabbitMQ)
- **Latency**: Near real-time targets (seconds)
- **Protocol**: Both gRPC (internal) and REST (debug)

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| RabbitMQ for task queuing | Reliable, mature, supports callbacks | — Pending |
| gRPC + REST APIs | gRPC for speed, REST for debugging | — Pending |
| Prometheus + structured logging | Observable pipelines catch failures early | — Pending |
| Docker Compose (not k8s) | Local dev first, simpler setup | — Pending |

---
*Last updated: 2026-04-08 after initialization* 
