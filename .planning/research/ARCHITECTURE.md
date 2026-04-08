# Architecture Patterns

**Domain:** ML Data Pipeline for Computer Vision
**Researched:** 2026-04-08
**Confidence:** MEDIUM (Unable to verify latest practices due to search tool issues)

## Recommended Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        API Gateway Layer                            │
│  (REST for external/debug, gRPC for internal performance)           │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Orchestration Layer                          │
│  Airflow DAGs coordinate workflow execution                         │
│  - Trigger ingestion on schedule/events                            │
│  - Publish tasks to message queue                                  │
│  - Poll for completion, trigger next stages                        │
│  - Handle failures and retries                                     │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                    ┌─────────────┼─────────────┐
                    │             │             │
                    ▼             ▼             ▼
        ┌─────────────────┐ ┌───────────┐ ┌──────────────┐
        │  Ingestion      │ │  Queue    │ │   Storage    │
        │  Service        │ │  Layer    │ │   Registry   │
        │                 │ │           │ │              │
        │ - Validate      │ │ RabbitMQ  │ │ - MinIO/S3   │
        │ - Transform     │ │ Celery    │ │ - Metadata   │
        │ - Deduplicate   │ │           │ │ - Versioning │
        │ - Publish tasks │ │           │ │              │
        └─────────────────┘ └───────────┘ └──────────────┘
                    │             │             │
                    └──────┬──────┴──────┬────┘
                           │             │
                           ▼             ▼
                 ┌─────────────────────────────┐
                 │   Worker Processing Layer   │
                 │                             │
                 │  ┌───────────────────────┐  │
                 │  │  Segmentation Workers │  │
                 │  │  - YOLO inference    │  │
                 │  │  - Extract masks/bbox  │  │
                 │  │  - Save results        │  │
                 │  └───────────────────────┘  │
                 │                             │
                 │  ┌───────────────────────┐  │
                 │  │  Preprocess Workers   │  │
                 │  │  - Augmentation       │  │
                 │  │  - Normalization      │  │
                 │  │  - Format conversion  │  │
                 │  └───────────────────────┘  │
                 └─────────────────────────────┘
                           │             │
                           └──────┬──────┘
                                  ▼
                 ┌─────────────────────────────┐
                 │      Data Storage Layer     │
                 │                             │
                 │  ┌───────────────────────┐  │
                 │  │  Object Storage       │  │
                 │  │  (Images, Masks)      │  │
                 │  └───────────────────────┘  │
                 │                             │
                 │  ┌───────────────────────┐  │
                 │  │  Metadata Store       │  │
                 │  │  (PostgreSQL/Mongo)   │  │
                 │  └───────────────────────┘  │
                 └─────────────────────────────┘
                                  │
                                  ▼
                 ┌─────────────────────────────┐
                 │    Observability Layer      │
                 │  - Prometheus metrics       │
                 │  - Structured logging       │
                 │  - Grafana dashboards       │
                 └─────────────────────────────┘
```

### Component Boundaries

| Component | Responsibility | Communicates With |
|-----------|---------------|-------------------|
| **API Gateway** | Route requests, auth, rate limiting | External clients, Orchestration |
| **Orchestration (Airflow)** | Workflow scheduling, task coordination | All services via message queue |
| **Ingestion Service** | Data validation, format conversion, dedup | API Gateway, Queue, Storage |
| **Queue Layer (RabbitMQ)** | Async task distribution, reliable delivery | All workers, Orchestration |
| **Worker Services** | CPU/GPU-intensive processing | Queue, Storage, Metadata |
| **Object Storage (MinIO)** | Binary data persistence (images, masks) | Workers, Ingestion |
| **Metadata Store** | Track processing state, lineage, versions | Orchestration, Workers |
| **Observability** | Metrics, logs, monitoring | All components |

## Data Flow

### 1. Ingestion Flow
```
Raw Image → API Gateway → Ingestion Service → Validation → Storage (MinIO)
                                      ↓
                              Publish Task to Queue
                                      ↓
                          Update Metadata (pending)
```

### 2. Segmentation Flow
```
Queue Task → Worker → Fetch Image from Storage → YOLO Inference
                                      ↓
                              Extract Masks/BBoxes → Save to Storage
                                      ↓
                          Update Metadata (completed)
                                      ↓
                              Publish Completion Event
```

### 3. Preprocessing Flow
```
Completion Event → Orchestration → Preprocess Worker
                                      ↓
                          Fetch Image + Masks → Augmentation
                                      ↓
                          Normalize → Format → Save to Storage
                                      ↓
                      Update Metadata (training-ready)
```

## Patterns to Follow

### Pattern 1: Queue-Based Task Distribution
**What:** Use message queue for async work distribution with acknowledgment
**When:** Decoupling producers from consumers, handling variable load
**Why:** Provides reliability, scalability, and fault isolation

**Implementation:**
```python
# Producer: Orchestration publishes tasks
channel.basic_publish(
    exchange='',
    routing_key='segmentation_tasks',
    body=json.dumps(task),
    properties=pika.BasicProperties(
        delivery_mode=2,  # Persistent
        correlation_id=task_id
    )
)

# Consumer: Worker processes with acknowledgment
def callback(ch, method, properties, body):
    try:
        process_task(body)
        ch.basic_ack(delivery_tag=method.delivery_tag)
    except Exception as e:
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
```

### Pattern 2: Immutable Data Storage
**What:** Store all processing artifacts as immutable objects with versioning
**When:** Need reproducibility, debugging, audit trails
**Why:** Prevents accidental data loss, enables rollback

**Implementation:**
```python
# Versioned storage paths
def storage_path(pipeline_id, step, filename):
    return f"{pipeline_id}/{step}/{uuid.uuid4()}/{filename}"

# Store parent references in metadata
metadata = {
    "image_id": image_id,
    "parent_id": previous_step_id,  # For lineage tracking
    "storage_path": storage_path,
    "created_at": timestamp
}
```

### Pattern 3: Metadata-Driven Orchestration
**What:** Separate data storage from processing state tracking
**When:** Complex multi-step pipelines with retries
**Why:** Enables visibility, restart capability, and lineage tracking

**Implementation:**
```python
# PostgreSQL schema for metadata tracking
CREATE TABLE pipeline_runs (
    id UUID PRIMARY KEY,
    status TEXT,  -- pending, running, completed, failed
    current_step TEXT,
    retry_count INTEGER,
    inputs JSONB,
    outputs JSONB,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

### Pattern 4: Service-Level Batch Processing
**What:** Workers process tasks in micro-batches for efficiency
**When:** High-throughput scenarios, GPU optimization
**Why:** Reduces overhead, better GPU utilization

**Implementation:**
```python
# Batch processing in workers
batch_size = 32  # Tune based on GPU memory
while True:
    batch = []
    for _ in range(batch_size):
        method, properties, body = channel.basic_get(queue='tasks')
        if body:
            batch.append((method, body))
    
    if batch:
        process_batch([body for _, body in batch])
        for method, _ in batch:
            channel.basic_ack(delivery_tag=method.delivery_tag)
```

## Anti-Patterns to Avoid

### Anti-Pattern 1: Synchronous Processing
**What:** Web server waits for ML inference to complete before responding
**Why bad:** Blocks threads, poor resource utilization, timeout failures
**Instead:** Return immediately with task ID, use async callbacks/polling

### Anti-Pattern 2: Shared Filesystem State
**What:** Multiple workers write to same files/directories
**Why bad:** Race conditions, data corruption, debugging nightmares
**Instead:** Immutable storage with unique paths, state in database

### Anti-Pattern 3: Monolithic Services
**What:** One service handles ingestion, processing, and orchestration
**Why bad:** Cannot scale independently, single point of failure
**Instead:** Separate services by function, communicate via queues

### Anti-Pattern 4: No Idempotency
**What:** Retrying tasks causes duplicate data/operations
**Why bad:** Data inconsistencies, wasted compute
**Instead:** Design all operations to be idempotent at task level

## Scalability Considerations

| Concern | At 100 users | At 10K users | At 1M users |
|---------|--------------|--------------|-------------|
| **Task Queue** | Single RabbitMQ node | RabbitMQ cluster | Kafka + multiple partitions |
| **Workers** | 2-4 workers | Auto-scaling pool | Multi-zone deployment |
| **Storage** | Single MinIO instance | MinIO distributed | S3 + CDN |
| **Metadata** | PostgreSQL single instance | Read replicas | Sharded by tenant/pipeline |
| **API Gateway** | Single instance | Load balanced | API gateway + rate limiting |
| **Orchestration** | Single Airflow | CeleryExecutor | KubernetesExecutor |

## Build Order Implications

**Phase 1: Foundation (Required First)**
1. **Storage Layer** (MinIO + PostgreSQL) - all services depend on storage
2. **Queue Layer** (RabbitMQ) - enables async communication
3. **Observability** (Prometheus + logging) - needed from day one
4. **Base services** (Docker Compose networking)

**Phase 2: Core Processing**
5. **Ingestion Service** - can be tested independently
6. **Segmentation Worker** - depends on storage and queue
7. **Preprocessing Worker** - depends on storage and queue

**Phase 3: Orchestration**
8. **Airflow DAGs** - depends on all services being ready
9. **API Gateway** - integrates all components
10. **End-to-end integration testing**

**Phase 4: Enhancement**
11. **Advanced monitoring** (Grafana dashboards)
12. **Batch optimization** (micro-batches)
13. **Model versioning** integration
14. **Data lineage tracking**

## Integration Patterns by Component

### Image Ingestion → Storage → Queue
```python
# Ingestion service pseudo-code
async def ingest_image(image_data, metadata):
    # 1. Validate and transform
    validated = validate_image(image_data)
    optimized = optimize_for_storage(validated)
    
    # 2. Store immutably
    storage_path = await storage_client.upload(optimized)
    
    # 3. Publish task atomically
    async with transaction():
        await metadata_db.insert({
            'path': storage_path,
            'status': 'pending_segmentation',
            'metadata': metadata
        })
        await queue.publish({
            'task': 'segment',
            'image_path': storage_path
        })
    
    return {'task_id': task_id, 'status': 'queued'}
```

### Queue → Worker → Storage → Metadata
```python
# Worker service pseudo-code
async def process_segmentation_task(task):
    # 1. Fetch data from storage
    image_data = await storage_client.download(task['image_path'])
    
    # 2. Process
    masks, bboxes = await yolo_model.segment(image_data)
    
    # 3. Store results
    mask_path = await storage_client.upload(masks)
    bbox_path = await storage_client.upload(bboxes)
    
    # 4. Update metadata
    await metadata_db.update(
        task['image_id'],
        {
            'segmentation_masks': mask_path,
            'bounding_boxes': bbox_path,
            'status': 'completed_segmentation'
        }
    )
    
    # 5. Publish completion event
    await queue.publish({
        'event': 'segmentation_complete',
        'image_id': task['image_id'],
        'output_paths': [mask_path, bbox_path]
    })
```

### Orchestration → Preprocessing → Final Storage
```python
# Orchestration DAG pseudo-code
def preprocessing_dag():
    # Wait for segmentation completion
    completion_event = wait_for_event('segmentation_complete')
    
    # Trigger preprocessing
    preprocess_task = PythonOperator(
        task_id='preprocess',
        python_callable=preprocess_and_augment,
        op_args=[
            completion_event['image_id'],
            completion_event['output_paths']
        ]
    )
    
    # Update final status
    mark_ready_task = PythonOperator(
        task_id='mark_training_ready',
        python_callable=update_metadata_status,
        op_args=[completion_event['image_id'], 'training_ready']
    )
    
    preprocess_task >> mark_ready_task
```

## Message Queue Topology

### Exchanges and Queues

```
┌─────────────────────────────────────────────────────────────┐
│                        RabbitMQ                             │
│                                                             │
│  Exchanges:                                                 │
│   - tasks.exchange (direct)                                  │
│   - events.exchange (topic)                                │
│                                                             │
│  Queues:                                                    │
│   - segmentation.tasks (durable, 4 workers)                │
│   - preprocessing.tasks (durable, 2 workers)               │
│   - orchestration.events (auto-delete)                     │
│                                                             │
│  Routing:                                                   │
│   - routing key: "segment" → segmentation.tasks              │
│   - routing key: "preprocess" → preprocessing.tasks        │
│   - routing key: "*.complete" → orchestration.events     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Queue Configuration Recommendations

```python
# High-throughput segmentation queue
segmentation_queue_args = {
    'x-max-length': 100000,        # Max queued messages
    'x-overflow': 'reject-publish',  # Backpressure
    'x-queue-mode': 'lazy'         # Store to disk, memory efficient
}

# Preprocessing queue (less critical, can drop)
preprocess_queue_args = {
    'x-message-ttl': 3600000,      # 1 hour TTL
    'x-dead-letter-exchange': 'dlx'  # Failed messages to DLQ
}

# Orchestration events (auto-delete when no consumers)
events_queue_args = {
    'auto_delete': True,
    'exclusive': False
}
```

## Data Storage Scheme

### Object Storage Path Structure
```
s3://bucket/
├── raw/
│   └── {pipeline_id}/
│       └── {uuid}/
│           └── original.jpg
├── segmented/
│   └── {pipeline_id}/
│       └── {uuid}/
│           ├── masks.npy
│           └── bboxes.json
└── preprocessed/
    └── {pipeline_id}/
│       └── {uuid}/
│           ├── augmented_1.jpg
│           ├── augmented_2.jpg
│           └── metadata.json
```

### Metadata Schema (PostgreSQL)
```sql
CREATE TABLE pipeline_runs (
    id UUID PRIMARY KEY,
    pipeline_id TEXT NOT NULL,
    status TEXT NOT NULL,  -- pending, running, completed, failed
    current_step TEXT,
    retry_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP
);

CREATE TABLE image_metadata (
    id UUID REFERENCES pipeline_runs(id),
    original_path TEXT,
    segmented_mask_path TEXT,
    preprocessed_paths TEXT[],
    bounding_boxes JSONB,
    labels JSONB,
    processing_time_ms INTEGER
);
```

## Failure Handling Strategies

### Retry Logic by Component
- **Ingestion**: Retry on storage failure (3 attempts, exponential backoff)
- **Segmentation**: Retry with different worker if GPU OOM (2 attempts)
- **Preprocessing**: Retry on augmentation error (1 attempt, skip if fails)
- **Queue connection**: Infinite retry with exponential backoff

### Dead Letter Queue Configuration
```python
# Failed messages go to DLQ for manual inspection
dead_letter_exchange = {
    'name': 'dlx',
    'type': 'direct'
}

dead_letter_queue = {
    'name': 'failed.tasks',
    'args': {
        'x-message-ttl': 86400000,  # 24 hours
        'x-dead-letter-exchange': 'retry'  # Can be manually requeued
    }
}
```

## Security Considerations

### Authentication Flow
```
Client → API Gateway → Validate JWT → Route to Service
                                      ↓
                            Service validates token
                                      ↓
                            Service to Service: mTLS
```

### Data Isolation
- Unique storage paths per pipeline prevent data leakage
- Queue consumer restrictions limit cross-pipeline access
- Metadata filtering at query level

## Performance Optimization

### gRPC vs REST for Internal Communication
- **Ingestion to Storage**: gRPC (binary, efficient for bulk data)
- **Worker to Metadata**: gRPC (low latency)
- **Debug endpoints**: REST (human-readable, browser-friendly)

### Batch Size Guidelines
- **Segmentation**: 1-8 images per batch (GPU memory dependent)
- **Preprocessing**: 16-32 images per batch (CPU parallelization)
- **Database writes**: 100-1000 rows per batch (connection efficiency)

## Uncertainties & Research Gaps

**LOW CONFIDENCE - Need Verification:**
- Optimal queue topology for computer vision pipelines (requires benchmarking)
- Latest MLflow/DVC integration patterns for versioning (2024+ practices)
- Batch size recommendations for modern GPU architectures
- Specific observability patterns for CV pipelines (metrics beyond standard)

**TODO for Phase-Specific Research:**
- Phase 2 (Core Processing): Benchmark batch sizes for YOLO segmentation
- Phase 3 (Orchestration): Research Airflow 2.x vs Prefect for CV workflows
- Phase 4 (Enhancement): Investigate data lineage tools (Great Expectations, etc.)

## Sources

- **MEDIUM CONFIDENCE** - Based on established patterns from MLflow, Kubeflow, and Airflow documentation
- RabbitMQ best practices: Official docs (unverified due to tool issues)
- ML pipeline patterns: TensorFlow Extended (TFX) architecture
- Computer vision pipelines: Industry-standard practices (unverified 2024+ updates)
- Observability patterns: Prometheus documentation, structured logging best practices

**Note on confidence**: Many assertions in this document are based on well-established patterns from major ML platforms (Airflow, MLflow, Kubeflow) but could not be verified against current documentation due to search tool unavailability. These represent proven architectures that should be validated against project-specific requirements and constraints.