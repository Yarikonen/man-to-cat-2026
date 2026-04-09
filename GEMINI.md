<!-- GSD:project-start source:PROJECT.md -->
## Project

**Man-to-Cat AI Translation - Data Engineering**

An AI service for man-to-cat image translation, currently focused on building the data engineering pipeline. Three containerized Python services process images: an Airflow orchestration layer for data collection, a YOLO-based segmentation service for extracting object masks and bounding boxes (persons and cats), and a preprocessing pipeline that prepares images for model training/inference with augmentation support.

**Core Value:** All three data pipeline services integrated and working end-to-end. Everything else can be complex or deferred, but the full pipeline—from data collection through segmentation to preprocessed output—must flow reliably. Without this, there's nothing to train a model on.

### Constraints

- **Tech Stack**: Python-only services
- **Deployment**: Docker Compose locally (dev environment)
- **Communication**: Async via message queue (RabbitMQ)
- **Latency**: Near real-time targets (seconds)
- **Protocol**: Both gRPC (internal) and REST (debug)
<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->
## Technology Stack

## Overview
## Core Framework
| Technology | Version | Purpose | Rationale |
|------------|---------|---------|-----------|
| **Python** | 3.12.7 | Runtime | Python 3.12 offers significant performance improvements, improved error messages, and better type hints. 3.12 is the current LTS recommendation for data pipelines. |
| **FastAPI** | 0.115.6 | REST API framework | Async-native, automatic OpenAPI docs, runtime type validation via Pydantic. 3-5x faster than Flask/Django for I/O-bound workloads. Built-in dependency injection simplifies testing. |
| **Uvicorn** | 0.33.0 | ASGI server | Production-grade ASGI server with async support. Standard for FastAPI deployments. Supports both development (--reload) and production modes. |
| **Pydantic** | 2.10.4 | Data validation | Enforces schema at runtime, generates type hints, provides excellent error messages. FastAPI's native validation layer. v2.x is 5-17x faster than v1.x. |
- **Flask**: Synchronous by default, requires extensions for async and OpenAPI
- **Django**: Heavyweight ORM and admin interface overkill for microservices
- **Sanic**: Smaller ecosystem, fewer ecosystem integrations
## Message Queue (RabbitMQ)
| Technology | Version | Purpose | When to Use |
|------------|---------|---------|-------------|
| **aio-pika** | 9.5.0 | Async RabbitMQ client | **Always** - Required for async message processing with FastAPI. Supports publisher confirms, consumer acks, and connection pooling. |
| **pika** | 1.3.2 | Sync RabbitMQ client | Only for synchronous scripts (rare). Aio-pika should be primary choice. |
- Connection per service (singleton pattern)
- Channel per message type
- Publisher confirms for reliability
- Consumer acknowledgments with retry logic
- Dead Letter Exchanges (DLX) for failed messages
- **aio-pika**: Actively maintained, pure async, built on top of robust pika
- **aiorabbit**: Less mature, smaller community
- **aioamqp**: Lower-level, requires more boilerplate
## Computer Vision (YOLO)
| Technology | Version | Purpose | Notes |
|------------|---------|---------|-------|
| **Ultralytics** | 8.3.55 | YOLO model inference | **MANDATORY** - Official YOLO library. Supports YOLOv8, v9, v10, v11. GPU/CPU inference, automatic model downloading, simple API. |
| **torch** | 2.5.1 | PyTorch backend | Required by Ultralytics. GPU acceleration via CUDA 12.4. |
| **opencv-python** | 4.10.0.84 | Image preprocessing | Standard CV library. Use headless version (`opencv-python-headless`) to reduce image size. |
| **Pillow** | 11.0.0 | Image format handling | PIL replacement. Better format support, security patches. |
- Official, battle-tested implementation
- Single-line model loading: `YOLO("yolo11m-seg.pt")`
- Automatic model download from Hugging Face
- Built-in CUDA/GPU detection
- Active development (weekly releases)
- MIT license
- Ultralytics provides complete pipeline (preprocessing, NMS, visualization)
- TorchVision requires manual model implementation
- YOLO-specific optimizations built-in
- **YOLO11m-seg**: Balanced speed/accuracy for segmentation (11.9M params, 259 FPS)
- **YOLO11n-seg**: Nano version for CPU inference (2.6M params, 674 FPS)
- **Fallback**: Download both, runtime selection based on GPU availability
## Object Storage (MinIO/S3)
| Technology | Version | Purpose | Notes |
|------------|---------|---------|-------|
| **boto3** | 1.35.90 | S3-compatible client | Standard AWS SDK. Works seamlessly with MinIO. Supports async via aioboto3. |
| **aioboto3** | 13.2.0 | Async S3 client | **Required** for non-blocking uploads. Drop-in replacement for boto3 with async/await. |
| **minio** | 7.2.11 | MinIO-specific client | Alternative to boto3. Simpler API, but boto3 is more flexible and standard. |
- boto3 is the industry standard, more documentation
- Works with AWS S3, GCS, Azure (future-proofing)
- Better error handling and retry logic
- Larger ecosystem (s3fs, moto for testing)
- Use aioboto3 for all service operations (upload, download, list)
- Implement multipart upload for >100MB files
- Generate pre-signed URLs for external access
- Use S3 object tags for metadata (source, processed timestamp)
## Orchestration (Airflow)
| Technology | Version | Purpose | Notes |
|------------|---------|---------|-------|
| **apache-airflow** | 2.10.4 | DAG orchestration | Modern Python sensor-based polling, not active waiting |
| **apache-airflow-providers-rabbitmq** | 1.2.0 | RabbitMQ hooks | Official provider for RabbitMQ integration |
| **apache-airflow-providers-amazon** | 8.28.0 | S3 hooks | S3 sensor for file detection |
- Mature scheduler with backfill, catchup, retries
- Web UI for monitoring DAG runs
- Sensors support event-driven workflows
- Python-native DAG definition
- Airflow has largest ecosystem
- More operators available
- Better enterprise support if needed later
- Already mentioned in project requirements
## APIs (gRPC + REST)
| Technology | Version | Purpose | When to Use |
|------------|---------|---------|-------------|
| **grpcio** | 1.68.0 | gRPC server/client | Internal service-to-service communication. 5-10x faster than REST for protobuf messages. |
| **grpcio-tools** | 1.68.0 | Protobuf compiler | Generate Python stubs from .proto files |
| **FastAPI** | 0.115.6 | REST endpoints | External/debugging endpoints, human-readable responses |
| From → To | Protocol | Why |
|-----------|----------|-----|
| API Gateway → Services | REST | Human debugging, JSON payloads |
| Airflow → Services | REST | Simple webhook triggering |
| Services ↔ Services | gRPC | Performance, strongly-typed contracts |
| External clients | REST | Standard HTTP/JSON APIs |
- Strongly-typed contracts via protobuf
- Bi-directional streaming support
- Built-in load balancing and retries
- Smaller payload sizes (binary protobuf)
- Native async support (grpcio.aio)
# Service exposes both on different ports
- 8000: REST (FastAPI)
- 50051: gRPC (grpcio.server)
# Same business logic, different protocol adapters
## Observability
### Metrics (Prometheus)
| Technology | Version | Purpose | When to Use |
|------------|---------|---------|-------------|
| **prometheus-client** | 0.21.1 | Metrics instrumentation | **Mandatory** - All services expose /metrics endpoint |
| **prometheus-fastapi-instrumentator** | 7.0.0 | Auto-instrumentation | REST API metrics (latency, throughput, errors) |
# Pipeline metrics
# System metrics
### Logging (Structured JSON)
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| **structlog** | 24.4.0 | JSON structured logging | Produces machine-parseable logs, integrates with ELK/Grafana Loki |
| **python-json-logger** | 3.2.1 | JSON formatter for stdlib | Alternative if structlog is too heavy |
- Type-safe log construction
- Built-in JSON rendering
- Context binding (correlation_id only set once)
- Better performance in async contexts
### Tracing (Optional but Recommended)
| Technology | Version | Purpose | When |
|------------|---------|---------|------|
| **opentelemetry-api** | 1.28.2 | Distributed tracing | Trace requests across service boundaries |
| **opentelemetry-instrumentation-fastapi** | 0.49b2 | Auto-instrumentation | If deep debugging needed |
## Supporting Libraries
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| **SQLAlchemy** | 2.0.36 | ORM (if needed) | If you add relational DB for metadata (PostgreSQL) |
| **alembic** | 1.14.0 | DB migrations | Schema versioning for relational stores |
| **redis** | 5.2.0 | Cache/locks | Rate limiting, deduplication |
| **httpx** | 0.28.1 | HTTP client | Async HTTP calls to external services |
| **pydantic-settings** | 2.7.1 | Configuration management | Type-safe env var parsing |
| **pytest** | 8.3.4 | Testing framework | Unit/integration testing |
| **pytest-asyncio** | 0.25.0 | Async test support | Test async functions |
| **fakeredis** | 2.26.1 | Redis mocking | Test without real Redis |
| **moto** | 5.0.21 | S3 mocking | Test S3 operations locally |
| **pytest-docker** | 3.1.1 | Integration testing | Spin up Docker services in tests |
| **black** | 24.10.0 | Code formatting | Pre-commit hook |
| **ruff** | 0.8.4 | Linting | 10-100x faster than flake8 |
| **mypy** | 1.13.0 | Type checking | Static type analysis |
## Docker / Deployment
### Base Images
| Service | Base Image | Why |
|---------|------------|-----|
| **FastAPI services** | `python:3.12.7-slim` | Slim variant reduces size by 60% vs standard. Alpine is problematic for compiled extensions (torch, grpc). |
| **Airflow** | `apache/airflow:2.10.4-python3.12` | Official image, includes all providers |
| **RabbitMQ** | `rabbitmq:3.13-management` | Includes management UI on port 15672 |
| **MinIO** | `minio/minio:RELEASE.2024-12-13T07-45-01Z` | S3-compatible storage |
| **Prometheus** | `prom/prometheus:v3.0.1` | Metrics collection |
- Alpine uses musl libc, causes segfaults with numpy/pytorch/grpc compiled wheels
- Slim uses glibc, compatible with all Python packages
- Size difference: slim ~130MB, alpine ~100MB (not worth the compatibility issues)
### Multi-stage Build Pattern (required)
# Build stage
# Runtime stage
- Reduces final image size by 40-60%
- No build dependencies in production (gcc, python-dev)
- Faster deployments
- Smaller attack surface
### Compose Configuration
## Security Considerations
| Technology | Purpose | Implementation |
|------------|---------|----------------|
| **python-multipart** | File upload security (if REST upload) | Validates content-type, size limits |
| **PyJWT** | Service-to-service auth | gRPC/REST API authentication |
| **cryptography** | Secrets management | Encrypt sensitive configs |
| **bandit** | Security linting | Pre-commit hook for vulnerabilities |
- Validate MIME type (not just extension)
- Maximum file size (10MB per image initially)
- Virus scanning (ClamAV integration if user uploads)
- Image dimension limits (8192x8192 max to prevent DoS)
- Use presigned URLs instead of static credentials
- Bucket policies restrict by IP (dev environment)
- Enable versioning for disaster recovery
## Testing Strategy
### Unit Tests (70% of coverage)
- Business logic tests with mocked dependencies
- No external services (RabbitMQ, MinIO mocked)
- Use pytest with monkeypatch
### Integration Tests (20% of coverage)
- Test service integration points
- Use TestContainers to spin up RabbitMQ/MinIO
- Test with moto (S3 mocking) or real MinIO container
### E2E Tests (10% of coverage)
- Full pipeline test: Airflow DAG → RabbitMQ → Service → MinIO
- Use pytest-docker to orchestrate
- Only critical paths (happy path + 1-2 failure modes)
- Use small subset of COCO dataset (100 images)
- Generate synthetic test images (colored squares for segmentation tests)
- Include corrupted images to test error handling
## Performance Targets
| Metric | Target | Measured At |
|--------|--------|-------------|
| API latency (p95) | <100ms | REST endpoints |
| YOLO inference (GPU) | <50ms | Segmentation service |
| YOLO inference (CPU) | <500ms | Fallback mode |
| Queue processing | <1s lag | RabbitMQ queue depth |
| MinIO upload | <100ms | Image storage |
- Use `pytest-benchmark` for microbenchmarks
- Load testing with `locust` for API endpoints
- YOLO timing per image in logs (structured logging)
## Summary Installation
### Base Requirements (requirements.txt)
# Core framework
# Message queue
# Computer vision
# Object storage
# APIs
# Observability
# Utilities
# Testing
### Development Requirements (requirements-dev.txt)
### Airflow Requirements (requirements-airflow.txt)
## Alternatives Considered
| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| **API Framework** | FastAPI | Flask + Quart | Flask requires extensions for OpenAPI and async. Quart less mature ecosystem. |
| **Message Queue** | RabbitMQ | Redis Streams | Redis lacks durability guarantees and ack/retry patterns. Redis has memory limits. |
| | | Apache Kafka | Overkill for this scale (seconds, not millions/sec). Complexity too high. |
| | | NATS | Smaller ecosystem, fewer Python libraries. |
| **CV Framework** | Ultralytics YOLO | MMDetection (OpenMMLab) | MMDetection more complex config system, steeper learning curve. YOLO faster for inference. |
| | | Detectron2 (Facebook) | PyTorch only, less model variety. YOLO has better speed/accuracy tradeoff. |
| **Storage** | MinIO | Local filesystem | Breaks containerization (volumes required), no S3 API compatibility. |
| | | PostgreSQL + BYTEA | Poor performance for large binary objects. S3 has better tooling. |
| **Orchestration** | Airflow | Prefect | Prefect Cloud dependency for advanced features. Airflow has larger operator ecosystem. |
| | | Temporal | Requires rewriting services in Temporal SDK. Not Python-native. |
| | | Cadence | Similar to Temporal. Ruby/Java focused origins. |
| **Observability** | Prometheus + Grafana | Datadog/New Relic | Paid services, not self-hosted. Violates requirement for local deployment. |
## Anti-Patterns to Avoid
## Version Pinning Rationale
- **Exact versions** (==) for production reproducibility
- **Lock file** (pip-compile or poetry.lock) should be committed
- **Monthly updates** to patch versions (security fixes)
- **Quarterly updates** to minor versions (features)
- **Evaluated updates** to major versions (breaking changes)
## Sources
- **Python 3.12**: https://www.python.org/downloads/release/python-3127/
- **FastAPI 0.115.6**: https://fastapi.tiangolo.com/release-notes/
- **Ultralytics 8.3.55**: https://github.com/ultralytics/ultralytics/releases
- **RabbitMQ 3.13**: https://www.rabbitmq.com/changelog.html
- **Airflow 2.10.4**: https://airflow.apache.org/docs/apache-airflow/stable/release_notes.html
- **Prometheus Python client**: https://github.com/prometheus/client_python
- **Structlog**: https://www.structlog.org/en/stable/
- **ASGI spec**: https://asgi.readthedocs.io/en/latest/
- **Docker Python best practices**: https://pythonspeed.com/docker/
- **Google gRPC Python**: https://grpc.io/docs/languages/python/
## Confidence Assessment
| Area | Level | Notes |
|------|-------|-------|
| Core Framework | **HIGH** | FastAPI is undisputed leader for async Python APIs |
| Message Queue | **HIGH** | RabbitMQ + aio-pika is production standard |
| Computer Vision | **HIGH** | Ultralytics YOLO is current SOTA |
| Object Storage | **HIGH** | boto3 + MinIO is proven pattern |
| Orchestration | **HIGH** | Airflow 2.x is mature and stable |
| APIs | **HIGH** | gRPC + REST pattern is well-established |
| Observability | **HIGH** | Prometheus + structured logging is CNCF standard |
| Supporting Libs | **HIGH** | Standard Python productivity stack |
| Docker | **HIGH** | Multi-stage builds are best practice |
| Security | **MEDIUM** | Recommendations follow OWASP but require implementation |
## Final Recommendations
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, or `.github/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
