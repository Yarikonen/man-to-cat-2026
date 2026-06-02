"""
YOLOv8-Seg clear dataset builder
--------------------------------
For each image:
- Detect ONLY TARGET_CLASS (cat or person)
- Keep only ONE best instance per image (largest segmentation area)
- Use segmentation mask only for filtering
- Object must occupy >= 25% of final crop
- Square crop
- Skip if crop < 256x256 before resize
- Resize valid crop to EXACTLY 256x256
- Save image only

Set:
TARGET_CLASS = "cat"
or
TARGET_CLASS = "person"

Requirements:
pip install ultralytics opencv-python numpy
"""

import os

os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"

import cv2
import numpy as np
from ultralytics import YOLO

# =========================
# CONFIG
# =========================
INPUT_DIR = "dataset/raw/humans"
OUTPUT_DIR = "dataset/clear/humans"

MODEL_PATH = "yolov8s-seg.pt"   
CONF_THRESHOLD = 0.4

MIN_CROP_SIZE = 256
FINAL_SIZE = 256
MIN_MASK_RATIO = 0.25  # target must occupy >=25% of crop

# Select target class: "cat" or "person"
TARGET_CLASS = "person"

# COCO classes
CLASS_MAP = {
    "person": 0,
    "cat": 15
}

if TARGET_CLASS not in CLASS_MAP:
    raise ValueError("TARGET_CLASS must be 'cat' or 'person'")

TARGET_CLASS_ID = CLASS_MAP[TARGET_CLASS]

os.makedirs(OUTPUT_DIR, exist_ok=True)

# =========================
# MODEL
# =========================
device = 'mps' if __import__('torch').backends.mps.is_available() else 'cuda' if __import__('torch').cuda.is_available() else 'cpu'

model = YOLO(MODEL_PATH).to(device)


# =========================
# HELPERS
# =========================
def make_square_bbox(x1, y1, x2, y2, img_w, img_h):
    """
    Convert bbox to square while preserving center.
    """
    w = x2 - x1
    h = y2 - y1
    side = max(w, h)

    cx = (x1 + x2) / 2
    cy = (y1 + y2) / 2

    nx1 = int(cx - side / 2)
    ny1 = int(cy - side / 2)
    nx2 = int(cx + side / 2)
    ny2 = int(cy + side / 2)

    # Boundary correction
    if nx1 < 0:
        nx2 += -nx1
        nx1 = 0
    if ny1 < 0:
        ny2 += -ny1
        ny1 = 0
    if nx2 > img_w:
        shift = nx2 - img_w
        nx1 -= shift
        nx2 = img_w
    if ny2 > img_h:
        shift = ny2 - img_h
        ny1 -= shift
        ny2 = img_h

    nx1 = max(0, nx1)
    ny1 = max(0, ny1)

    return nx1, ny1, nx2, ny2


def polygon_to_mask(polygon, img_h, img_w):
    """
    Convert segmentation polygon to full-size mask.
    """
    mask = np.zeros((img_h, img_w), dtype=np.uint8)
    pts = polygon.astype(np.int32)
    cv2.fillPoly(mask, [pts], 255)
    return mask


def crop_valid(crop):
    h, w = crop.shape[:2]
    return h >= MIN_CROP_SIZE and w >= MIN_CROP_SIZE


def resize_crop(crop):
    return cv2.resize(
        crop,
        (FINAL_SIZE, FINAL_SIZE),
        interpolation=cv2.INTER_AREA
    )


def resize_mask(mask):
    return cv2.resize(
        mask,
        (FINAL_SIZE, FINAL_SIZE),
        interpolation=cv2.INTER_NEAREST
    )


def mask_ratio(mask):
    return np.count_nonzero(mask) / mask.size


# =========================
# BEST INSTANCE SELECTION
# =========================
def select_best_target_instance(result, image_shape):
    """
    Select only the largest instance of TARGET_CLASS in image.
    """
    best_instance = None

    if result.boxes is None or result.masks is None:
        return None

    boxes = result.boxes.xyxy.cpu().numpy()
    classes = result.boxes.cls.cpu().numpy().astype(int)
    polygons = result.masks.xy

    img_h, img_w = image_shape[:2]

    best_area = 0

    for i, (box, cls_id) in enumerate(zip(boxes, classes)):
        if cls_id != TARGET_CLASS_ID:
            continue

        full_mask = polygon_to_mask(polygons[i], img_h, img_w)
        area = np.count_nonzero(full_mask)

        if area > best_area:
            best_area = area
            best_instance = {
                "box": box,
                "mask": full_mask,
                "area": area
            }

    return best_instance


# =========================
# MAIN PIPELINE
# =========================
def process_dataset():
    valid_ext = [".jpg", ".jpeg", ".png", ".bmp", ".webp"]

    image_paths = []
    for root, _, files in os.walk(INPUT_DIR):
        for file in files:
            if os.path.splitext(file)[1].lower() in valid_ext:
                image_paths.append(os.path.join(root, file))

    total_saved = 0

    for img_path in image_paths:
        image = cv2.imread(img_path)

        if image is None:
            print(f"Could not read: {img_path}")
            continue

        img_h, img_w = image.shape[:2]

        results = model(image, conf=CONF_THRESHOLD, verbose=False)

        for result in results:
            best_instance = select_best_target_instance(
                result,
                image.shape
            )

            if best_instance is None:
                continue

            x1, y1, x2, y2 = map(int, best_instance["box"])
            full_mask = best_instance["mask"]

            # Square crop
            x1, y1, x2, y2 = make_square_bbox(
                x1, y1, x2, y2, img_w, img_h
            )

            crop = image[y1:y2, x1:x2]
            crop_mask = full_mask[y1:y2, x1:x2]

            # Skip small crops
            if not crop_valid(crop):
                continue

            # Resize
            final_crop = resize_crop(crop)
            final_mask = resize_mask(crop_mask)

            # Object area validation
            if mask_ratio(final_mask) < MIN_MASK_RATIO:
                continue

            # Save
            base_name = os.path.splitext(
                os.path.basename(img_path)
            )[0]

            save_name = f"{base_name}_{TARGET_CLASS}.png"
            save_path = os.path.join(OUTPUT_DIR, save_name)

            cv2.imwrite(save_path, final_crop)

            total_saved += 1
            print(f"Saved: {save_path}")

    print(f"\nFinished. Total saved {TARGET_CLASS} images: {total_saved}")


# =========================
# ENTRY
# =========================
if __name__ == "__main__":
    process_dataset()
