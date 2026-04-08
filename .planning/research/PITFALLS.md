# Domain Pitfalls

**Domain:** ML Data Processing Pipeline - Computer Vision with Message Queues
**Project:** Man-to-Cat Translation - Data Engineering
**Researched:** 2026-04-08

## Critical Pitfalls

Mistakes that cause rewrites, data loss, or pipeline collapse.

### Pitfall 1: Embedding Large Image Data in Message Queue Payloads

**What goes wrong:** RabbitMQ messages exceed 256MB and get rejected, or queue memory explodes. Airflow XComs store full image data and crash workers.

**Why it happens:** Developers pass image bytes directly in messages ("message should contain everything"). Airflow operators load images into memory for task state.

**Consequences:**
- Queue crashes with "Memory limit exceeded" errors
- Airflow workers OOM and get killed by k8s/Docker
- Task retries cascade into complete pipeline failure
- Messages silently dropped (no DLQ configured)

**Prevention:**
- Pass MinIO/S3 object keys only in messages (e.g., `{"image_id": "uuid", "s3_path": "bucket/key.jpg"}`)
- Never pass >1KB in RabbitMQ messages for this pipeline
- Use Airflow XCom for metadata only (timestamps, status flags, object keys)
- Implement early validation: reject messages with embedded data

**Detection:**
- Monitor `rabbitmq_queue_depth_bytes` metric from Prometheus
- Alert when message size >1KB or queue memory >50MB
- Stack traces showing `MemoryError` or `OutOfMemoryError` in consumer logs

**Phase to Address:** Phase 1 (Infrastructure setup - RabbitMQ + MinIO integration)

### Pitfall 2: No Idempotency = Duplicate Processing & Data Corruption

**What goes wrong:** RabbitMQ message redelivery (after consumer crash) causes images to be processed multiple times. Same image gets different segmentation masks on retry.

**Why it happens:** Services aren't idempotent: they create new records instead of upserting. No deduplication key tracked.

**Consequences:**
- Training data contains duplicates with conflicting labels
- MinIO storage fills with duplicate processed images
- Metrics double-count throughput (inflates to 2x actual)
- Airflow DAGs can't safely retry tasks (creates bad data)

**Prevention:**
- Use deterministic IDs: `segmentation-{image_id}` not random UUIDs
- Build idempotency into consumers: UPSERT pattern, not INSERT
- Store processing state in database (PostgreSQL) with unique constraints
- Implement exactly-once semantics: atomic publish + state update
- Use RabbitMQ message deduplication plugin with `x-message-deduplication-id`

**Detection:**
- Count distinct `image_id` vs total processed records (should match)
- Monitor RabbitMQ `redelivered` flag frequency in logs
- Check MinIO for files with same prefix + different timestamps

**Phase to Address:** Phase 1 (Consumer service architecture), Phase 2 (Processing logic)

### Pitfall 3: Model Loading per Message = Latency Death

**What goes wrong:** Segmentation service loads YOLO model from disk for each image (5-10 seconds per message). Pipeline throughput drops to 0.1 images/second.

**Why it happens:** Naive implementation: `process_message()` calls `model = load_yolo()` each time. No model caching or GPU memory management.

**Consequences:**
- Near real-time target (seconds) becomes minutes per image
- GPU underutilized (loading time >> inference time)
- Queue depth explodes (consumers slower than producers)
- Docker containers hit I/O limits reading model repeatedly

**Prevention:**
- Load model once at service startup, reuse for all messages
- Singleton pattern: `YOLOModel.get_instance()` returns cached model
- Warm start: preload model in Docker `HEALTHCHECK` before accepting messages
- GPU memory pre-allocation: configure PyTorch/TensorFlow memory fraction
- Batch inference: accumulate N messages, run single batch forward pass

**Detection:**
- Prometheus metric for `model_load_duration_seconds` (histogram)
- Log timestamps: gap between message received and inference start
- Top command showing repeated model file reads (`iotop`)
- Compare: p50 inference time (should be <1s) vs p99 (closer to 10s = red flag)

**Phase to Address:** Phase 1 (Segmentation service implementation)

### Pitfall 4: No Dead Letter Queue = Poison Pills Block Everything

**What goes wrong:** Single malformed image (corrupted JPEG, wrong format) crashes consumer. Message retries infinitely. All valid images queue up behind it.

**Why it happens:** No error handling or DLQ configuration. Default retry logic (3x) kicks it back to main queue. Consumer keeps crashing on same message.

**Consequences:**
- Pipeline effectively halts (head-of-line blocking)
- No visibility into which messages are causing failures
- Wasted compute reprocessing bad data
- Queue depth grows unbounded
- Good data goes stale waiting behind poison pill

**Prevention:**
- Configure RabbitMQ DLQ: `x-dead-letter-exchange` on main queue
- Implement dead letter routing: after 3 failures, publish to `segmentation.dlq`
- Dead letter queue TTL: expire after 7 days, not forever
- Alert on DLQ depth > 0 (critical alert, not warning)
- Build admin tooling to inspect DLQ messages and purge manually
- Validate message schema at consumption: reject malformed messages immediately

**Detection:**
- Monitor `queue_depth_messages` for main queue growing
- Alert when DLQ depth > 0
- Logs showing same message ID reprocessed 3+ times

**Phase to Address:** Phase 1 (RabbitMQ topology setup)

### Pitfall 5: Airflow Polling Instead of Callbacks = Latency & Resource Waste

**What goes wrong:** Airflow DAG runs sensor every 30 seconds checking RabbitMQ for completion. Wastes 1,000s of unnecessary API calls. Adds average 15 seconds latency (half of interval).

**Why it happens:** Default Airflow pattern: use `RabbitMQSensor` or `ExternalTaskSensor` polling. No async callbacks configured.

**Consequences:**
- Airflow scheduler overloaded with sensor tasks (thousands per hour)
- RabbitMQ management API rate limited (blocks real traffic)
- Actual processing time 5 seconds, but total pipeline latency 30-60 seconds
- Waste 90% of compute on polling, not actual work
- Hides real bottlenecks (latency attributed to "waiting" not actual processing)

**Prevention:**
- Use RabbitMQ push-based pattern: segmentation service publishes to `segmentation.completed` exchange
- Airflow DAG starts with trigger from message, not polling sensor
- Use `HttpSensor` with poke_interval=5s only if absolutely necessary
- Callback pattern: segmentation service calls Airflow REST API to trigger downstream DAG
- Consider Airflow deferrable operators (new in 2.6+) for async waiting

**Detection:**
- Airflow UI shows thousands of sensor task runs vs few actual tasks
- RabbitMQ mgmt API logs show high request rate from Airflow host
- Task duration breakdown: 80% time spent in "sensing" state

**Phase to Address:** Phase 2 (Airflow DAG design)

### Pitfall 6: No Backpressure = Queue Memory Exhaustion & OOM

**What goes wrong:** Airflow collects images at 100 images/second but segmentation service only processes 10/second. RabbitMQ queue grows to 10M messages, consumes all RAM, crashes container.

**Why it happens:** No rate limiting or flow control. Producer runs at full speed regardless of consumer capacity.

**Consequences:**
- RabbitMQ pod OOMKilled, loses all in-flight messages
- Data loss (messages not persisted to disk)
- Pipeline down until manual restart
- Docker volume fills with queue data, host disk full

**Prevention:**
- Implement consumer prefetch: `basic_qos(prefetch_count=10)` per consumer
- Monitor queue depth: alert at 10,000 messages (not 10 million)
- Rate limit Airflow DAG: use pools, max_active_runs=1, task concurrency limits
- Backpressure mechanism: pause producer when queue > threshold
- Horizontal scaling: run multiple segmentation service consumers (same queue)
- Queue TTL: expire old messages after 24h (don't process stale data)

**Detection:**
- Prometheus alert: `rabbitmq_queue_depth_messages > 10000`
- Grafana dashboard showing queue growth rate > consumption rate
- Docker stats showing RabbitMQ memory climbing continuously

**Phase to Address:** Phase 2 (Queue configuration + Airflow DAG tuning)

### Pitfall 7: GPU Memory Leaks & OpenCV File Descriptor Leaks

**What goes wrong:** Segmentation service slowly leaks GPU memory (PyTorch gradients not freed) and file descriptors (OpenCV images not closed). After 1,000 images: CUDA out of memory or "Too many open files" error.

**Why it happens:**
- No `with torch.no_grad()` context manager
- OpenCV images loaded but never released (`cv2.imread()` without `del img` or explicit release)
- Inference loops accumulate gradients in memory
- PIL images not closed (file handles leak)

**Consequences:**
- Service crashes after running for hours (not immediately)
- Hard to reproduce: works fine for first N images, fails in production after days
- Kubernetes pod restart loop (liveness probe fails)
- Mysterious "Too many open files (24)" errors in segmentation logs
- GPU underutilized (memory not freed, blocks new tasks)

**Prevention:**
- Wrap inference in `with torch.no_grad():` (disables gradient tracking)
- Explicit cleanup: `del image_tensor; torch.cuda.empty_cache()` after each inference
- Use `with open()` patterns for all file operations
- OpenCV: `image = cv2.imread(...); process; del image; gc.collect()`
- Context managers for resource-heavy objects
- Add `ulimits` to Docker Compose: `nofile: 65536` (prevents "Too many open files")
- Monitor GPU memory: `nvidia-smi` in health checks

**Detection:**
- Prometheus metric `process_open_fds` growing over time
- Grafana: GPU memory utilization never drops
- `lsof -p <pid>` shows hundreds of file handles to image files
- Container logs: "RuntimeError: CUDA out of memory" after N hours

**Phase to Address:** Phase 1 (Segmentation service implementation), Phase 1 (Docker Compose limits)

### Pitfall 8: No Structured Logging Correlation = Debugging Hell

**What goes wrong:** Image `cat_123.jpg` fails segmentation. Logs from 3 services show 50 messages with no correlation ID. Can't trace which log lines belong to which image.

**Why it happens:** Each service logs independently. No request ID passed in RabbitMQ headers or correlation ID context.

**Consequences:**
- Investigating failures requires manually timestamp matching across 3 containers
- Can't aggregate traces across distributed pipeline
- Debugging takes 10x longer
- Metrics by image ID impossible (no way to join logs to Prometheus)

**Prevention:**
- Generate `trace_id` at Airflow entry: `trace_id = uuid.uuid4()`
- Propagate via RabbitMQ headers: `headers={"trace_id": trace_id, "image_id": image_id}`
- Python logging: use `logging.LoggerAdapter` with extra context
- JSON logs with fields: `{"timestamp": ..., "trace_id": "...", "service": "segmentation", "event": "inference_completed"}`
- Log consistently: every service logs receive/process/complete for each image

**Detection:**
- Manual log search shows multiple services but no common identifier
- Try to find all logs for a specific image ID: impossible

**Phase to Address:** Phase 1 (All services from day 1)

### Pitfall 9: MinIO Without Lifecycle Policies = Infinite Storage Growth

**What goes wrong:** Pipeline runs for 3 months, creates 10M processed images. MinIO disk fills to 100%. Docker volume full, crashes all services.

**Why it happens:** No retention policy. All images stored forever: raw, segmented, preprocessed, augmented.

**Consequences:**
- Service downtime (disk full)
- Potential data loss (can't write new images until cleanup)
- Expensive storage costs (S3 bills in production)
- Manual cleanup crisis (delete what? which are still needed?)

**Prevention:**
- Define retention: raw images 30 days, processed images 90 days
- MinIO lifecycle policies: expire objects after N days
- Archive cold data to cheaper storage (if/when migrating to AWS S3)
- Log what to delete: "raw images can be recreated from source, keep segmentations"

**Detection:**
- Prometheus alert: `minio_bucket_size_bytes` > threshold
- `df -h` shows /data at 95%+

**Phase to Address:** Phase 2 (Storage policy planning)

### Pitfall 10: No Integration Testing = Silent Failures in Production

**What goes wrong:** Unit tests pass (mocking everything). Production deployment fails: RabbitMQ connection string wrong, MinIO bucket doesn't exist, model path invalid.

**Why it happens:** Only unit tests, no end-to-end integration tests. No testing of Docker Compose setup.

**Consequences:**
- Discover failures after deployment (not in CI)
- Long debugging cycle in production environment
- Configuration drift between dev and prod
- Queue topology changes break pipeline silently

**Prevention:**
- Integration test suite: starts full Docker Compose stack
- Tests: publish message → verify processed → check MinIO output
- Test actual YOLO inference on small test images (not mocked)
- CI pipeline: run integration tests before merge
- Health endpoint for each service (Docker depends_on condition)
- Smoke tests: `curl` each service's `/health` after deploy

**Detection:**
- Monitoring shows pipeline not processing (0 messages/min)
- First deploy fails: services can't connect to each other

**Phase to Address:** Phase 1 (CI/CD setup), Phase 2 (Integration test suite)

## Moderate Pitfalls

### Pitfall 1: Airflow TriggerDagRunOperator Without wait_for_completion

**What goes wrong:** Parent DAG triggers child DAG and marks itself success immediately. Child DAG fails silently 2 minutes later. No monitoring.

**Prevention:**
- Use `wait_for_completion=True` in TriggerDagRunOperator
- Or use `ExternalTaskSensor` to wait for child completion

**Phase:** Phase 2

### Pitfall 2: No Model Versioning

**What goes wrong:** Update YOLO model, pipeline behavior changes subtly. Can't rollback. No audit trail.

**Prevention:**
- Version models: `yolo_v8_20260408.pt` not `yolo.pt`
- Log model version in metadata for each processed image
- Store models in MinIO with versioning

**Phase:** Phase 1

### Pitfall 3: Fixed Batch Sizes Don't Adapt to Image Sizes

**What goes wrong:** Batch size 32 works for small images (256x256), but OOM on large images (2048x2048).

**Prevention:**
- Dynamic batch sizing based on image resolution
- Or separate queues by image size category

**Phase:** Phase 1

### Pitfall 4: No Circuit Breaker for YOLO Service

**What goes wrong:** YOLO service crashes (OOM). Airflow keeps publishing messages. Queue fills. When service restarts, it crashes again from backlog.

**Prevention:**
- Airflow sensor checks service health before publishing
- Circuit breaker pattern: pause DAG if error rate > threshold
- Exponential backoff on retries

**Phase:** Phase 2

## Minor Pitfalls

### Pitfall 1: No Image Format Validation

**What goes wrong:** User uploads `.zip` instead of `.jpg`. Service crashes trying to decode.

**Prevention:**
- Validate MIME type at upload: `image/jpeg`, `image/png`
- Try `cv2.imread()` and handle `None` return gracefully

**Phase:** Phase 1

### Pitfall 2: Logging Image Content (Base64) Instead of Metadata

**What goes wrong:** Logs contain base64 image data. Log files grow to GBs in hours. Hard to read.

**Prevention:**
- Log image ID, path, dimensions, meta only
- Never log pixel data or base64 strings

**Phase:** Phase 1

### Pitfall 3: Using Airflow for Real-Time Tasks

**What goes wrong:** Airflow has 5-10 seconds scheduler delay. "Near real-time" target (seconds) missed.

**Prevention:**
- Use Airflow for batch orchestration (every 5 minutes)
- Use API + direct RabbitMQ publish for true real-time path

**Phase:** Phase 2 (Architecture decision)

### Pitfall 4: No Rate Limiting on User Upload Endpoint

**What goes wrong:** User script uploads 10,000 images in 10 seconds. Queue flooded. DOS.

**Prevention:**
- Nginx rate limiting: `limit_req_zone` 10 req/sec per IP
- API gateway throttling

**Phase:** Phase 2

### Pitfall 5: Not Using Connection Pooling for MinIO

**What goes wrong:** Each image upload opens new TCP connection. Exhausts file descriptors.

**Prevention:**
- Use single MinIO client instance per service (connection pool)
- Configure `max_pool_connections` (default 10 is fine)

**Phase:** Phase 1

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| **Phase 1: RabbitMQ Setup** | No DLQ, messages lost forever | Configure DLQ exchange + TTL from day 1 |
| **Phase 1: Segmentation Service** | Model loading per message | Implement singleton pattern + warm start |
| **Phase 1: MinIO Integration** | Direct image data in messages | Enforce message schema validation (key only) |
| **Phase 1: Docker Compose** | No resource limits | Set memory/cpu limits to prevent OOM cascade |
| **Phase 2: Airflow DAGs** | Polling sensors | Use push-based callback pattern |
| **Phase 2: Preprocessing** | GPU memory leaks | Test with 1,000+ images, monitor nvidia-smi |
| **Phase 2: Observability** | Missing trace_id correlation | Implement structured JSON logging early |
| **Phase 3: User Uploads** | No rate limiting | Add Nginx throttling before opening API |
| **Phase 3: Scale Testing** | No backpressure | Load test with 10x expected rate, verify queue depth |

## Sources

- ML Pipeline Best Practices (training data + domain knowledge)
- RabbitMQ Production Checklists (message queue patterns)
- Airflow Architecture Patterns (sensor anti-patterns)
- Computer Vision Production Systems (GPU memory management)
- RabbitMQ DLQ Documentation (error handling patterns)
- OpenCV + PyTorch Memory Leak Patterns (common in CV services)

**Confidence Level:** MEDIUM - Based on established patterns in ML pipelines and message queue systems. Specific YOLO + Airflow + RabbitMQ + MinIO combination validated against best practices.