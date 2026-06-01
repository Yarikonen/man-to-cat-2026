# Man-to-Cat Image Processing Service

An image processing service with a Telegram bot interface. Users send photos to the bot, which are processed through a 4-stage ML pipeline and returned transformed.

## Architecture

```
User → Telegram Bot → S3 (originals) + PostgreSQL + Redis Queue
                                      ↓
                            Model Service (worker)
                                      ↓
                     S3 (processed) + PostgreSQL (updated)
                                      ↓
                        Bot polls DB → sends result
```

### Services

| Service | Port | Description |
|---------|------|-------------|
| Bot | 8001 | aiogram Telegram bot + status poller |
| Model Service | 8002 | ML pipeline worker |
| PostgreSQL | 5432 | Image metadata database |
| MinIO | 9000/9001 | S3-compatible storage (originals + processed) |
| Redis | 6379 | Job queue |
| Prometheus | 9090 | Metrics collection |
| Grafana | 3000 | Dashboards |
| cAdvisor | 8080 | Container resource metrics |
| Redis Exporter | 9121 | Redis metrics for Prometheus |
| Postgres Exporter | 9187 | PostgreSQL metrics for Prometheus |

### Image Processing Pipeline

1. **Preprocessing** — Converts raw image bytes to torch tensor
2. **Quality Gate** — Checks if image meets processing standards
3. **Primary Model** — Applies the ML transformation
4. **Postprocessing** — Converts tensor back to PIL image

### Status Flow

```
received → preprocessing → quality_check → processing → postprocessing → done
                                                                          ↓
                                                                       failed
```

## Quick Start

### Prerequisites

- Docker & Docker Compose
- A Telegram bot token from [@BotFather](https://t.me/BotFather)

### Setup

1. **Clone and configure:**
   ```bash
   cp .env.example .env
   # Edit .env and set your TELEGRAM_BOT_TOKEN
   ```

2. **Start all services:**
   ```bash
   docker-compose up -d --build
   ```

3. **Verify services are healthy:**
   ```bash
   docker-compose ps
   ```

4. **Open your Telegram bot and send a photo!**

### Accessing Dashboards

- **Grafana:** http://localhost:3000 (admin/admin)
- **Prometheus:** http://localhost:9090
- **MinIO Console:** http://localhost:9001 (minioadmin/minioadmin)

## Project Structure

```
man-to-cat-2026/
├── docker-compose.yml          # All services orchestration
├── .env.example                # Environment variable template
├── shared/                     # Shared infrastructure code
│   ├── config.py               # Pydantic settings
│   ├── db.py                   # Async PostgreSQL manager
│   ├── s3_client.py            # MinIO/S3 wrapper
│   ├── queue.py                # Redis queue manager
│   └── metrics.py              # Prometheus metrics
├── bot/                        # Telegram bot service
│   ├── main.py                 # Entrypoint
│   ├── handlers.py             # Command & photo handlers
│   ├── poller.py               # Background status poller
│   ├── pyproject.toml          # Bot dependencies (uv)
│   └── Dockerfile              # Uses uv for package management
├── model_service/              # ML processing worker
│   ├── main.py                 # Worker entrypoint
│   ├── pipeline.py             # Pipeline orchestrator
│   ├── modules/                # Processing modules (stubs)
│   │   ├── preprocessing.py
│   │   ├── quality_gate.py
│   │   ├── primary_model.py
│   │   └── postprocessing.py
│   ├── pyproject.toml          # Model service dependencies (uv)
│   └── Dockerfile              # Uses uv for package management
├── monitoring/                 # Prometheus & Grafana config
│   ├── prometheus.yml
│   └── grafana/
│       ├── dashboards/
│       └── provisioning/
└── scripts/
    └── init-db.sql             # PostgreSQL schema
```

## Customizing the ML Modules

The pipeline modules in `model_service/modules/` are stubs. Replace them with your actual implementations:

- **`preprocessing.py`** — Implement `PreprocessingModule.process(bytes) -> torch.Tensor`
- **`quality_gate.py`** — Implement `QualityGateModule.check(Tensor) -> (bool, str|None)`
- **`primary_model.py`** — Implement `PrimaryModelModule.infer(Tensor) -> Tensor`
- **`postprocessing.py`** — Implement `PostprocessingModule.process(Tensor) -> PIL.Image`

## Monitoring

The Grafana dashboard includes:
- Processing duration by stage (histogram)
- Images in queue (gauge)
- Images by status (bar gauge)
- Processing rate (counter)
- Container CPU/memory usage (from cAdvisor)

## Development

### Rebuild a single service:
```bash
docker-compose up -d --build bot
```

### View logs:
```bash
docker-compose logs -f bot
docker-compose logs -f model_service
```

### Stop everything:
```bash
docker-compose down
```

### Stop and remove all data:
```bash
docker-compose down -v
```
