FROM python:3.12-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# Copy dependency definitions
COPY model_service/pyproject.toml /tmp/pyproject.toml

# Install dependencies with uv (no cache for smaller images)
RUN uv pip install --system --no-cache --requirement /tmp/pyproject.toml
RUN uv pip install --system --no-cache accelerate

RUN apt-get update && apt-get install -y \
    libxcb1 \
    libx11-6 \
    libxext6 \
    libxrender1 \
    libgl1 \
    libglib2.0-0 \
    libsm6

# Copy application code
COPY shared/ /app/shared/
COPY model_service/ /app/model_service/

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "model_service.main"]
