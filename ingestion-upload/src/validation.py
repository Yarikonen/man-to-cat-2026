import cv2
from pathlib import Path

def detect_corruption(image_path: str):
    image = cv2.imread(image_path)
    if image is None:
        return True, "cv2.imread returned None"
    if image.size == 0:
        return True, "Image has zero dimensions"
    if len(image.shape) not in [2, 3]:
        return True, f"Invalid image shape: {image.shape}"
    return False, None

def validate_dimensions(image_path: str, min_width=224, min_height=224):
    image = cv2.imread(image_path)
    if image is None:
        return True, None
    height, width = image.shape[:2]
    is_valid = width >= min_width and height >= min_height
    return is_valid, (width, height)

def detect_blur(image_path: str, threshold=100.0):
    gray = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if gray is None:
        return True, 0.0
    laplacian = cv2.Laplacian(gray, cv2.CV_64F)
    variance = laplacian.var()
    return variance < threshold, variance

def validate_image_quality(image_path: str):
    is_corrupt, reason = detect_corruption(image_path)
    if is_corrupt:
        return False, f"corruption: {reason}", {}

    is_valid_dims, dimensions = validate_dimensions(image_path, 224, 224)
    if not is_valid_dims:
        w, h = dimensions
        return False, f"dimensions: {w}x{h} < 224x224", {}

    is_blurry, variance = detect_blur(image_path, 100.0)
    if is_blurry:
        return False, f"blur: variance={variance:.2f} < 100.0", {}

    return True, None, {"dimensions": dimensions, "blur_variance": variance}
