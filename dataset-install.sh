#!/bin/bash
set -euo pipefail

# Always run relative to this script's directory
ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

# ==============================
# CONFIGURATION
# ==============================
DATASET_DIR="dataset"
MINIO_URL="http://localhost:9000"
MINIO_USER="minioadmin"
MINIO_PASS="minioadmin"
MINIO_BUCKET="datasets"

HUMAN_DATASET="ashwingupta3012/human-faces"
CAT_DATASET="crawford/cat-dataset"

require_cmd() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "ERROR: required command not found: $1"
        exit 1
    fi
}

# ==============================
# 1. START MINIO (if not running)
# ==============================
start_minio() {
    if curl -fsS -o /dev/null "$MINIO_URL/minio/health/live"; then
        echo "✓ MinIO already running"
        return
    fi

    echo "Starting MinIO from existing compose file..."
    docker compose up -d minio

    until curl -fsS -o /dev/null "$MINIO_URL/minio/health/live"; do
        sleep 2
    done

    echo "✓ MinIO ready"
}

# ==============================
# 2. INSTALL MC CLIENT (if needed)
# ==============================
install_mc() {
    if command -v mc >/dev/null 2>&1; then
        echo "✓ mc already installed"
        return
    fi

    echo "Installing mc client..."
    local os arch url tmpdir
    os="$(uname -s | tr '[:upper:]' '[:lower:]')"
    arch="$(uname -m)"
    [[ "$arch" == "x86_64" ]] && arch="amd64"
    [[ "$arch" == "arm64" || "$arch" == "aarch64" ]] && arch="arm64"

    url="https://dl.min.io/client/mc/release/${os}-${arch}/mc"
    tmpdir="$(mktemp -d)"
    curl -fsSL -o "$tmpdir/mc" "$url"
    chmod +x "$tmpdir/mc"

    if sudo install -m 0755 "$tmpdir/mc" /usr/local/bin/mc 2>/dev/null; then
        echo "✓ mc installed globally"
    else
        echo "⚠ Could not install globally; using local copy"
        export PATH="$PATH:$tmpdir"
    fi
}

# ==============================
# 3. DOWNLOAD DATASETS (skip if already done)
# ==============================
download_kaggle_dataset() {
    local dataset="$1"
    local output_dir="$2"
    local marker="$output_dir/.download_complete"

    if [ -f "$marker" ]; then
        echo "✓ $dataset already downloaded, skipping"
        return 0
    fi

    echo "Downloading $dataset..."
    mkdir -p "$output_dir"
    uv run python source/utils/kaggle_download.py --dataset "$dataset" --target "$output_dir"
    touch "$marker"
    echo "✓ $dataset downloaded"
}

# ==============================
# 4. RUN SEGMENTATION (masks only, filter small masks)
# ==============================
run_segmentation() {
    local marker="$DATASET_DIR/processed/.segmentation_done"

    if [ -f "$marker" ]; then
        echo "✓ Segmentation already done, skipping"
        return 0
    fi

    echo "Running segmentation (masks only, filter <25% size)..."
    mkdir -p "$DATASET_DIR/raw/humans" "$DATASET_DIR/raw/cats" "$DATASET_DIR/processed"

    if [ ! -f "yolov8s-seg.pt" ]; then
        uv run python -c "from ultralytics import YOLO; YOLO('yolov8s-seg.pt')"
    fi

    uv run python source/preprocessing/segmentation-module.py --input "$DATASET_DIR"
    touch "$marker"
    echo "✓ Segmentation complete"
}

# ==============================
# 5. UPLOAD TO MINIO USING MC
# ==============================
upload_to_minio() {
    echo "Uploading to MinIO..."

    require_cmd mc

    mc alias set local "$MINIO_URL" "$MINIO_USER" "$MINIO_PASS" >/dev/null
    mc mb "local/$MINIO_BUCKET" >/dev/null 2>&1 || true

    if [ ! -d "$DATASET_DIR" ]; then
        echo "ERROR: Dataset directory '$DATASET_DIR' not found!"
        exit 1
    fi

    local file_count
    file_count="$(find "$DATASET_DIR" -type f | awk 'END { print NR }')"

    if [ "$file_count" -eq 0 ]; then
        echo "ERROR: No files found in '$DATASET_DIR' to upload!"
        exit 1
    fi

    echo "Uploading $file_count files from $DATASET_DIR to MinIO..."
    mc cp --recursive "$DATASET_DIR/" "local/$MINIO_BUCKET/patch-dataset/"

    echo "✓ Upload completed successfully"
}

# ==============================
# 6. VERIFY UPLOAD
# ==============================
verify_upload() {
    echo
    echo "Verifying upload..."

    local listing count
    listing="$(mc ls --recursive "local/$MINIO_BUCKET/patch-dataset/" 2>/dev/null || true)"
    count="$(awk 'END { print NR }' <<<"$listing")"

    echo "✓ $count files in MinIO"

    if [ "$count" -gt 0 ]; then
        echo "Sample files:"
        sed -n '1,5p' <<<"$listing"
    else
        echo "⚠ No files found in MinIO bucket!"
        echo "Check bucket permissions and path."
    fi
}

# ==============================
# MAIN
# ==============================
echo "=== Dataset Pipeline with MinIO ==="

require_cmd curl
require_cmd docker
require_cmd uv

start_minio
install_mc

Run download and segmentation if needed
echo "=== Download Phase ==="
download_kaggle_dataset "$HUMAN_DATASET" "$DATASET_DIR/raw/humans"
download_kaggle_dataset "$CAT_DATASET" "$DATASET_DIR/raw/cats"
echo "=== Segmentation Phase ==="
run_segmentation

echo "=== Upload Phase ==="
upload_to_minio
verify_upload

echo
echo "✓ Done. MinIO console: http://localhost:9001"
echo "  Login: $MINIO_USER / $MINIO_PASS"
echo "  Bucket: $MINIO_BUCKET/patch-dataset/"
