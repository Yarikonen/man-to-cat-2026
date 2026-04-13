import os
import shutil
import argparse
from tqdm import tqdm
import kagglehub


IMAGE_EXTS = {".jpg", ".jpeg", ".png"}


def safe_copy_flat(src_dir: str, dst_dir: str):

    os.makedirs(dst_dir, exist_ok=True)

    images = []

    for root, _, files in os.walk(src_dir):
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in IMAGE_EXTS:
                images.append(os.path.join(root, f))

    print(f"Found {len(images)} images")

    for i, img_path in enumerate(tqdm(images, desc="Copying images")):

        ext = os.path.splitext(img_path)[1].lower()

        # deterministic zero-padded naming to avoid collisions
        dst_path = os.path.join(dst_dir, f"{i:08d}{ext}")

        shutil.copy2(img_path, dst_path)


def download_dataset(dataset: str, target_dir: str):

    print(f"Downloading dataset via Kaggle Hub: {dataset}")

    cache_path = kagglehub.dataset_download(dataset)

    print(f"Cached path: {cache_path}")

    safe_copy_flat(cache_path, target_dir)

    print("Dataset flattened successfully")


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--dataset", required=True)
    parser.add_argument("--target", required=True)

    args = parser.parse_args()

    download_dataset(args.dataset, args.target)


if __name__ == "__main__":
    main()
