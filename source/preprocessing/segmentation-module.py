import os
import argparse
import numpy as np
from ultralytics import YOLO
import cv2
from tqdm import tqdm

os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'

MODEL_PATH = "yolov8s-seg.pt"
TARGET_CLASSES = {"human": 0, "cat": 15}
MIN_MASK_RATIO = 0.25  # 25% of image size

def calculate_mask_ratio(mask, image_shape):
    """Calculate the ratio of mask area to total image area"""
    mask_area = np.sum(mask > 0)
    image_area = image_shape[0] * image_shape[1]
    return mask_area / image_area

def save_mask(mask, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    mask_img = (mask * 255).astype(np.uint8)
    cv2.imwrite(path, mask_img)

def segment_folder(folder, object_type, out_dir):
    if not os.path.exists(folder):
        print(f"Warning: Folder not found: {folder}")
        return 0, 0, 0
    
    # Get all images
    image_extensions = {'.jpg', '.jpeg', '.png'}
    images = []
    for root, _, files in os.walk(folder):
        for file in files:
            if any(file.lower().endswith(ext) for ext in image_extensions):
                images.append(os.path.join(root, file))
    
    if not images:
        print(f"Warning: No images found in {folder}")
        return 0, 0, 0
    
    print(f"\nProcessing {len(images)} {object_type} images")
    print(f"Filtering masks smaller than {MIN_MASK_RATIO * 100}% of image size")
    
    # Create masks output directory only
    mask_dir = os.path.join(out_dir, "masks")
    os.makedirs(mask_dir, exist_ok=True)
    
    model = YOLO(MODEL_PATH)
    target_class_id = TARGET_CLASSES[object_type]
    
    images_processed = 0
    masks_created = 0
    masks_filtered = 0
    
    # Process with tqdm progress bar
    for img_id, img_path in enumerate(tqdm(images, desc=f"Segmenting {object_type}s")):
        # Read image to get dimensions
        img = cv2.imread(img_path)
        if img is None:
            continue
            
        img_height, img_width = img.shape[:2]
        
        # Run segmentation
        results = model.predict(img_path, conf=0.25, iou=0.45, verbose=False)
        
        for r in results:
            if r.boxes is None or r.masks is None:
                continue
            
            cls = r.boxes.cls.cpu().numpy().astype(int)
            masks = r.masks.data.cpu().numpy()
            orig_img = r.orig_img if hasattr(r, 'orig_img') else img
            
            for i in range(len(cls)):
                if cls[i] != target_class_id:
                    continue
                
                # Calculate mask ratio
                mask_ratio = calculate_mask_ratio(masks[i], orig_img.shape[:2])
                
                # Filter small masks
                if mask_ratio < MIN_MASK_RATIO:
                    masks_filtered += 1
                    continue
                
                # Save mask only, reference original image by name
                original_name = os.path.splitext(os.path.basename(img_path))[0]
                mask_filename = f"{original_name}_{i}.png"
                mask_path = os.path.join(mask_dir, mask_filename)
                save_mask(masks[i], mask_path)
                masks_created += 1
        
        images_processed += 1
    
    return images_processed, masks_created, masks_filtered

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Input directory containing raw/humans and raw/cats")
    parser.add_argument("--min-ratio", type=float, default=0.25, help="Minimum mask ratio (default: 0.25 = 25%%)")
    args = parser.parse_args()
    
    global MIN_MASK_RATIO
    MIN_MASK_RATIO = args.min_ratio
    
    input_dir = args.input
    humans_dir = os.path.join(input_dir, "raw/humans")
    cats_dir = os.path.join(input_dir, "raw/cats")
    
    # Process humans
    print("=" * 50)
    print(f"HUMAN SEGMENTATION (Masks > {MIN_MASK_RATIO * 100}% of image)")
    print("=" * 50)
    human_out = os.path.join(input_dir, "processed/humans")
    os.makedirs(human_out, exist_ok=True)
    
    if os.path.exists(humans_dir):
        human_images, human_masks, human_filtered = segment_folder(humans_dir, "human", human_out)
        print(f"\n✓ Humans: {human_images} images processed")
        print(f"  - Masks created: {human_masks}")
        print(f"  - Masks filtered (<{MIN_MASK_RATIO * 100}%): {human_filtered}")
    else:
        print(f"⚠ Humans directory not found: {humans_dir}")
    
    # Process cats
    print("\n" + "=" * 50)
    print(f"CAT SEGMENTATION (Masks > {MIN_MASK_RATIO * 100}% of image)")
    print("=" * 50)
    cat_out = os.path.join(input_dir, "processed/cats")
    os.makedirs(cat_out, exist_ok=True)
    
    if os.path.exists(cats_dir):
        cat_images, cat_masks, cat_filtered = segment_folder(cats_dir, "cat", cat_out)
        print(f"\n✓ Cats: {cat_images} images processed")
        print(f"  - Masks created: {cat_masks}")
        print(f"  - Masks filtered (<{MIN_MASK_RATIO * 100}%): {cat_filtered}")
    else:
        print(f"⚠ Cats directory not found: {cats_dir}")
    
    print("\n" + "=" * 50)
    print("SEGMENTATION COMPLETE!")
    print("=" * 50)

if __name__ == "__main__":
    main()
    