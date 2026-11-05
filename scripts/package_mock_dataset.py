
import argparse
import hashlib
import json
import shutil

from pathlib import Path

from backend.db import records
from backend.settings import layer


def sha256_file(path):
    h = hashlib.sha256()

    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)

    return h.hexdigest()


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )


def copy_required(src, dst):
    if not src.is_file():
        raise FileNotFoundError(src)

    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def package_dataset(dataset_dir, output_root):
    dataset_dir = dataset_dir.resolve()
    dataset_id = dataset_dir.name

    source_manifest = json.loads(
        (dataset_dir / "manifest.json").read_text(
            encoding="utf-8"
        )
    )

    # Verify raw dataset before packaging
    event_path = dataset_dir / "events.jsonl"

    if sha256_file(event_path) != source_manifest["sha256"]:
        raise ValueError("Source events SHA-256 mismatch")

    quality_path = dataset_dir / "data_quality_report.json"

    quality = json.loads(
        quality_path.read_text(encoding="utf-8")
    )

    if quality["status"] != "PASS":
        raise ValueError("Data Quality must PASS")

    connectivity_path = (
        dataset_dir / "connectivity_report.json"
    )

    if not connectivity_path.is_file():
        raise FileNotFoundError(connectivity_path)

    # Read current catalog
    users = sorted(
        records("users"), key=lambda x: x["id"]
    )
    products = sorted(
        records("products"), key=lambda x: x["id"]
    )

    # Verify product catalog against source manifest
    catalog_hash = hashlib.sha256(
        json.dumps(
            products, sort_keys=True
        ).encode("utf-8")
    ).hexdigest()

    if catalog_hash != source_manifest["catalog_sha256"]:
        raise ValueError(
            "Product catalog no longer matches source dataset"
        )

    # Ground Truth directory from existing project layout
    gt_dir = (
        layer("mock")
        / "ground_truth"
        / dataset_id
    )

    required_gt = [
        "user_profiles.json",
        "session_profiles.json",
        "manifest.json",
    ]

    for filename in required_gt:
        if not (gt_dir / filename).is_file():
            raise FileNotFoundError(gt_dir / filename)

    # Ensure GT corresponds to the dataset
    gt_manifest = json.loads(
        (gt_dir / "manifest.json").read_text(
            encoding="utf-8"
        )
    )

    if gt_manifest["events_sha256"] != source_manifest["sha256"]:
        raise ValueError("Ground Truth dataset hash mismatch")

    # Check user IDs against Ground Truth
    gt_users = json.loads(
        (gt_dir / "user_profiles.json").read_text(
            encoding="utf-8"
        )
    )

    catalog_ids = {u["id"] for u in users}
    gt_ids = {u["user_id"] for u in gt_users}

    if catalog_ids != gt_ids:
        raise ValueError(
            "User catalog does not match Ground Truth users"
        )

    # Build package
    output_dir = output_root / dataset_id

    if output_dir.exists():
        raise FileExistsError(
            f"Package already exists: {output_dir}"
        )

    (output_dir / "data").mkdir(
        parents=True, exist_ok=True
    )

    write_json(output_dir / "data/users.json", users)
    write_json(output_dir / "data/products.json", products)

    copy_required(
        dataset_dir / "events.jsonl",
        output_dir / "data/events.jsonl"
    )

    parquet_source = dataset_dir / "events.parquet"

    if parquet_source.is_file():
        copy_required(
            parquet_source,
            output_dir / "data/events.parquet"
        )

    for filename in required_gt:
        copy_required(
            gt_dir / filename,
            output_dir / "ground_truth" / filename
        )

    copy_required(
        quality_path,
        output_dir / "reports/data_quality_report.json"
    )

    copy_required(
        connectivity_path,
        output_dir / "reports/connectivity_report.json"
    )

    copy_required(
        dataset_dir / "manifest.json",
        output_dir / "source_manifest.json"
    )

    # Dataset-specific onboarding documentation
    readme = f"""# NUTEE Synthetic Dataset — {dataset_id}

## Tổng quan

- Scenario: {source_manifest['scenario']}
- Seed: {source_manifest['seed']}
- Events: {source_manifest['count']}
- Catalog users: {len(users)}
- Catalog products: {len(products)}
- Data Quality: PASS
- Ground Truth: Available

## Thư mục

- `data/`: users, products và behavioral events
- `ground_truth/`: latent user/session preferences
- `reports/`: data quality và connectivity
- `source_manifest.json`: nguồn gốc dataset
- `handoff_manifest.json`: SHA-256 cho các file

## Đọc dữ liệu

```python
import json
import pandas as pd

users = json.load(open("data/users.json", encoding="utf-8"))
products = json.load(open("data/products.json", encoding="utf-8"))

events = pd.read_json(
    "data/events.jsonl",
    lines=True
)
```

## Ý nghĩa các hành vi

- `product_impression`: sản phẩm được hiển thị
- `product_click`: người dùng nhấp sản phẩm
- `product_view`: người dùng xem chi tiết
- `add_to_wishlist`: thêm danh sách yêu thích
- `add_to_cart`: thêm vào giỏ hàng
- `purchase`: mua hàng giả lập

## Lưu ý cho nhóm AI

1. Dữ liệu hoàn toàn synthetic.
2. Impression không đồng nghĩa phản hồi tích cực.
3. Chia train/test theo thời gian trước khi tổng hợp interactions.
4. Không dùng Ground Truth latent profiles làm features
   huấn luyện trực tiếp nếu mục tiêu là học từ hành vi.
5. Đọc các báo cáo trong `reports/` trước khi sử dụng.
6. Các phiên cuối có thể bị cắt do giới hạn số events.
"""

    (output_dir / "README.md").write_text(
        readme, encoding="utf-8"
    )

    # SHA-256 of all packaged files
    checksums = {}

    for path in sorted(output_dir.rglob("*")):
        if path.is_file():
            rel = path.relative_to(output_dir).as_posix()
            checksums[rel] = sha256_file(path)

    handoff_manifest = {
        "dataset_id": dataset_id,
        "scenario": source_manifest["scenario"],
        "seed": source_manifest["seed"],
        "event_count": source_manifest["count"],
        "user_count": len(users),
        "product_count": len(products),
        "data_quality": "PASS",
        "files": checksums
    }

    write_json(
        output_dir / "handoff_manifest.json",
        handoff_manifest
    )

    print("Package created:", output_dir)
    print("Files:", len(checksums))
    print("Users:", len(users))
    print("Products:", len(products))
    print("Events:", source_manifest["count"])

    return output_dir


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--dataset-dir",
        type=Path,
        required=True
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/handoff")
    )

    args = parser.parse_args()

    package_dataset(
        dataset_dir=args.dataset_dir,
        output_root=args.output_dir
    )


if __name__ == "__main__":
    main()
