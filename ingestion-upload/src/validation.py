import cv2
from pathlib import Path
from typing import Tuple, Dict, Any


def detect_corruption(image_path: str) -> Tuple[bool, str]:
    """Check if image is corrupted or unreadable."""
    try:
        image = cv2.imread(image_path)
        if image is None:
            return True, "cv2.imread returned None - corrupted or format not supported"
        if image.size == 0:
            return True, "Image has zero dimensions/empty"
        if len(image.shape) not in [2, 3]:
            return True, f"Invalid image shape: {image.shape}"
        return False, None
    except Exception as e:
        return True, f"Exception during read: {str(e)}"


def validate_dimensions(image_path: str, min_width: int = 224, min_height: int = 224) -> Tuple[bool, Tuple[int, int]]:
    """Validate image meets minimum dimension requirements."""
    try:
        image = cv2.imread(image_path)
        if image is None:
            return False, (0, 0)

        height, width = image.shape[:2]
        is_valid = width >= min_width and height >= min_height
        return is_valid, (width, height)
    except Exception as e:
        return False, (0, 0)


def detect_blur(image_path: str, threshold: float = 100.0) -> Tuple[bool, float]:
    """Detect blur using Laplacian variance."""
    try:
        gray = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
        if gray is None:
            return True, 0.0

        laplacian = cv2.Laplacian(gray, cv2.CV_64F)
        variance = laplacian.var()

        is_blurry = variance < threshold
        return is_blurry, variance
    except Exception as e:
        return True, 0.0


def validate_image_quality(image_path: str) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Complete image quality validation pipeline.

    Returns:
        is_valid: bool - True if image passes all validation checks
        reject_reason: str - Reason for rejection if invalid
        metrics: dict - Validation metrics for debugging
    """
    metrics = {}

    # Check 1: Corruption
    is_corrupt, corrupt_reason = detect_corruption(image_path)
    if is_corrupt:
        return (False, f"corruption: {corrupt_reason}", metrics)

    # Check 2: Dimensions
    is_valid_dims, dimensions = validate_dimensions(image_path, 224, 224)
    metrics["dimensions"] = dimensions
    if not is_valid_dims:
        w, h = dimensions if dimensions else (0, 0)
        return (False, f"dimensions: {w}x{h} < 224x224", metrics)

    # Check 3: Blur detection
    is_blurry, variance = detect_blur(image_path, threshold=100.0)
    metrics["blur_variance"] = variance
    if is_blurry:
        return (False, f"blur: variance={variance:.2f} < 100.0", metrics)

    # All checks passed
    return (True, None, metrics)