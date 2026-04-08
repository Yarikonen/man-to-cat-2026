# Feature Landscape: ML Data Processing Pipelines

**Domain:** Computer Vision Data Engineering Pipeline
**Researched:** 2026-04-08
**Confidence:** LOW (based on training data - external verification recommended)

## Table Stakes Features

Features users expect from ML data pipelines. Missing these = product feels incomplete.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **Multi-source Data Ingestion** | CV pipelines must handle various image sources (public datasets, user uploads, API feeds) | MEDIUM | Support structured paths, filename parsing, metadata extraction. S3-compatible storage (MinIO) expected. |
| **Message Queue Integration** | Async processing required for heavy CV operations (segmentation, augmentation) | MEDIUM | RabbitMQ: reliable queuing, ack/nack patterns, DLQ support for failed messages. |
| **Workflow Orchestration** | Complex DAGs needed: collect → segment → preprocess → validate | MEDIUM | Airflow: schedule management, dependency resolution, task retries, backfills. |
| **Containerized Services** | Reproducible environments across dev/staging/prod | LOW | Docker Compose: standard for local dev. Enables consistent Python environments. |
| **Error Handling & DLQ** | CV tasks fail (corrupt images, OOM). Users expect graceful handling, not silent failures | MEDIUM | RabbitMQ DLQ + Airflow retry logic. Structured error logging with traceability. |
| **Data Validation** | Garbage in, garbage out. CV models require valid images, proper formats, consistent dimensions | MEDIUM | Validate: image integrity, format support (PNG/JPEG), metadata completeness. |
| **Preprocessing Pipeline** | Raw images need normalization before training | HIGH | Resizing, normalization, format conversion. Model-specific requirements. |
| **Data Augmentation** | CV requires augmentation for generalization | HIGH | Geometric (rotate, flip, crop), color space (brightness, contrast), advanced (mixup, cutout). |
| **Observability** | Opaque pipelines fail silently. Need visibility into data flow | MEDIUM | Prometheus metrics: queue depth, processing latency, success rates. Structured JSON logs. |
| **State Management** | Need to track which images are processed, failed, or in-flight | MEDIUM | Airflow XComs, database checkpoints, or S3 markers. Prevents duplicate processing. |

## Differentiators (Competitive Advantage)

Features that set the product apart from basic ML pipelines.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Smart Data Quality Gates** | Auto-detect corrupted/blurry/low-quality images before annotation | HIGH | OpenCV quality checks, blur detection, exposure analysis. Filters bad data upstream. |
| **Caching Layer** | Avoid re-processing unchanged images; speed up development | MEDIUM | Redis or memory cache: check file hash before re-processing. Critical for pipeline iteration. |
| **Advanced Augmentation Strategies** | CV-specific augmentations beyond basic transforms: domain-adaptive | HIGH | Albumentations: mixup, cutout, random erasure. Domain-specific for human-to-animal. |
| **Data Lineage Tracking** | Audit trail: which raw image → which segmented mask → which augmented version | MEDIUM | Track IDs through pipeline. Validation: regenerate results reliably. |
| **Dynamic Sampling & Balancing** | Balance dataset distribution (person vs cat) automatically | MEDIUM | Analyze class distributions at preprocessing stage. Auto-sampling strategies. |
| **Introspection APIs** | Debug pipeline state: inspect queues, worker status, retry counts | LOW | REST endpoints: queue depths, processing stats. Speeds debugging. |
| **Schema Evolution** | Handle v1 masks vs v2 masks gracefully. Backward-compatible metadata | MEDIUM | Versioned schemas in metadata JSON. Migration scripts for older data. |
| **Parallel Processing Controls** | Tune concurrency: per-stage worker counts based on bottlenecks | MEDIUM | Separate queues for segmentation vs preprocessing. Independent scaling. |

## Anti-Features (Do NOT Build)

Features that seem valuable but create problems.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| **Real-Time Synchronous Processing** | CV inference + augmentation is CPU/GPU heavy. Synchronous requests timeout, block clients. | Async via message queue. REST API returns job ID, client polls for completion. |
| **Monolithic Pipeline Service** | Single service handles ingestion, segmentation, preprocessing. Tight coupling kills scalability. | Three services: orchestration (Airflow), segmentation, preprocessing. Queue decoupling. |
| **Hardcoded Pipeline Configuration** | Hardcoded paths, queue names, model params → inflexible, no per-environment customization. | Config via environment variables or config files. Feature flags for toggling behaviors. |
| **No Idempotency** | Re-running same job creates duplicates (duplicate masks, duplicate preprocessed images). | Use deterministic job IDs, check existence before processing. Implement at-least-once semantics correctly. |
| **Weak Error Messages** | Generic "pipeline failed" with no context → impossible to debug. | Structured logging with correlation IDs, job context, failure reasons. Include image ID, processing stage. |

## Feature Dependencies

```
Data Ingestion
└──→ Message Queue Integration
    └──→ YOLO Segmentation Service
        └──→ MinIO Storage
            └──→ Preprocessing Pipeline
                └──→ Data Validation
                    └──→ Data Augmentation
                        └──→ Observability

Workflow Orchestration (Airflow)
├──depends──→ Message Queue (publish/consume)
├──depends──→ State Management (XCom/metastore)
└──enhances──→ Retry Logic & DLQ

Advanced Augmentation
└──requires──→ Caching Layer (avoid re-augmentation)
    └──enhances──→ Smart Data Quality Gates (balance datasets)

Data Lineage Tracking
└──requires──→ Structured Logging (correlation IDs)
└──requires──→ State Management (track IDs)
    └──enables──→ Introspection APIs (expose state)

Parallel Processing Controls
├──conflicts──→ Hardcoded Configuration (needs dynamic config)
└──requires──→ Dynamic Sampling (coordinate workers)
```

## MVP Definition

### Launch With (v1)
Minimum viable product — core pipeline from PROJECT.md

- [ ] **Multi-source Data Ingestion** — Validate concept: collect from public datasets
- [ ] **Message Queue Integration** — Async decoupling essential for reliability
- [ ] **YOLO Segmentation Service** — Core transformation: extract masks from images
- [ ] **Preprocessing Pipeline** — Normalize images for model training
- [ ] **Data Augmentation** — Basic transforms: rotate, flip, color jitter
- [ ] **Error Handling & DLQ** — Without this, pipeline silently fails
- [ ] **Observability** — Prometheus + structured logging: visibility into failures
- [ ] **State Management** — Track processed images, prevent duplicates

### Add After Validation (v1.x)
Once core pipeline works reliably

- [ ] **Smart Data Quality Gates** — Disable low-quality images automatically (block bad data)
- [ ] **Caching Layer** — Speed up development, avoid re-processing
- [ ] **Advanced Augmentation** — Domain-specific augmentations for human/cat translation
- [ ] **Data Lineage Tracking** — Audit trail when troubleshooting model performance
- [ ] **Introspection APIs** — Debug production issues faster

### Future Consideration (v2+)
Defer until product-market fit

- [ ] **Dynamic Sampling & Balancing** — Scale-dependent feature; defer until dataset size requires it
- [ ] **Multi-tenant Support** — Separate queues per user/team; not needed initially
- [ ] **Schema Evolution** — Backward compatibility only needed when changing output schemas
- [ ] **Auto-scaling** — Over-optimization; manual scaling sufficient for initial volumes

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Message Queue Integration | CRITICAL | MEDIUM | P1 |
| YOLO Segmentation Service | CRITICAL | HIGH | P1 |
| Data Ingestion | HIGH | MEDIUM | P1 |
| Preprocessing Pipeline | HIGH | HIGH | P1 |
| Error Handling & DLQ | HIGH | MEDIUM | P1 |
| Observability | HIGH | LOW | P1 |
| Basic Augmentation | HIGH | MEDIUM | P1 |
| State Management | MEDIUM | MEDIUM | P1 |
| Caching Layer | MEDIUM | MEDIUM | P2 |
| Smart Quality Gates | MEDIUM | HIGH | P2 |
| Advanced Augmentation | MEDIUM | HIGH | P2 |
| Data Lineage | MEDIUM | MEDIUM | P2 |
| Introspection APIs | LOW | LOW | P2 |
| Dynamic Sampling | LOW | MEDIUM | P3 |
| Multi-tenant | LOW | HIGH | P3 |
| Auto-scaling | LOW | HIGH | P3 |

**Priority Key:**
- **P1**: Must have for launch. No P1 = no working pipeline.
- **P2**: Should have, accelerates development or improves reliability.
- **P3**: Nice to have, defensible to cut from initial launch.

## Implementation Notes

Based on PROJECT.md decisions:

**Technology Stack Validation:**
- **RabbitMQ**: Appropriate for task queuing (not event streaming). DLQ support needed.
- **Airflow**: Good for batch orchestration. Overkill for simple cron jobs; justified by DAG complexity.
- **gRPC**: Performance gain for internal services. REST for debugging is pragmatic.
- **MinIO**: S3-compatible simplifies path to AWS/GCS. But metadata tracking requires separate DB.
- **Prometheus**: Standard metrics, but consider OpenTelemetry for tracing correlation IDs.

**Critical Integration Points:**
1. Airflow → RabbitMQ: task publishing with retry logic
2. RabbitMQ → Segmentation service: ack/nack handling, DLQ configuration
3. Segmentation → MinIO: atomic writes (write temp, then rename)
4. Preprocessing → Augmentation: deterministic augmentation seeding for reproducibility
5. All services → Prometheus: standardized metric naming, labels (stage, image_type, status)

**Performance Considerations:**
- YOLO inference: GPU utilization critical for throughput
- Image I/O: Bottleneck for large images; consider memory mapping or parallel I/O
- Queue depth: Monitor segmentation queue size; preprocessing queue likely smaller
- Worker concurrency: Start with 2-4 workers per service, adjust based on CPU/GPU

---

*Feature research for: Man-to-Cat AI Translation Pipeline*
*Researched: 2026-04-08*

## Sources

- Project context: `.planning/PROJECT.md` (internal requirements)
- Training data: Common patterns in ML/data engineering (LOW confidence - requires verification)
- RabbitMQ DLQ patterns: Message queuing best practices (unverified)
- Airflow ML pipelines: Common orchestration patterns (unverified)
- Prometheus metrics: Observability patterns (unverified)

**Confidence Note**: This research primarily reflects ML/data pipeline standard patterns from training data. Live source verification (Airflow docs, RabbitMQ cookbooks, CV pipeline case studies) is strongly recommended before committing to roadmap.
