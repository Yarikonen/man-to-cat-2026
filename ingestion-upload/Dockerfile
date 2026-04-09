# Build stage
FROM python:3.12.7-slim as builder

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Runtime stage
FROM python:3.12.7-slim

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY . .

# Add the app directory to the Python path
ENV PYTHONPATH=/app

CMD ["python", "main.py"]
