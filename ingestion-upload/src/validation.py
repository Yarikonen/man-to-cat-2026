import cv2
import numpy as np

def validate_image_quality(file_path: str):
    """
    Validates the quality of an image.
    Checks for blur, corruption, and dimensions.
    """
    try:
        image = cv2.imread(file_path)
        if image is None:
            return False, "Image is corrupted or not a valid image format.", {}

        # Dimension validation
        height, width, _ = image.shape
        if height < 128 or width < 128:
            return False, f"Image dimensions ({width}x{height}) are too small. Minimum is 128x128.", {}

        # Blur detection
        laplacian_var = cv2.Laplacian(image, cv2.CV_64F).var()
        if laplacian_var < 100: # Threshold can be tuned
            return False, f"Image is too blurry (Laplacian variance: {laplacian_var:.2f}).", {"laplacian_variance": laplacian_var}

        return True, "Image is valid.", {"laplacian_variance": laplacian_var, "width": width, "height": height}

    except Exception as e:
        return False, f"An error occurred during image validation: {e}", {}
