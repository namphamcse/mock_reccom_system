
import hashlib
import json

from backend.settings import layer


def write_json(path, data):
    """
    Ghi dữ liệu JSON theo định dạng ổn định.
    Trả về SHA-256 của nội dung file.
    """
    payload = json.dumps(
        data,
        indent=2,
        sort_keys=True,
        ensure_ascii=False
    )

    content = payload.encode("utf-8")
    path.write_bytes(content)

    return hashlib.sha256(content).hexdigest()


def export_ground_truth(
    ground_truth,
    scenario,
    seed,
    events_sha256,
    catalog_sha256,
    cfg
):
    """
    Xuất Ground Truth cho một lần chạy simulator.
    """

    dataset_id = (
        f"{scenario}-{seed}-{events_sha256[:12]}"
    )

    output_dir = (
        layer("mock")
        / "ground_truth"
        / dataset_id
    )

    output_dir.mkdir(parents=True, exist_ok=True)

    user_profiles = ground_truth["user_profiles"]
    session_profiles = ground_truth["session_profiles"]

    user_hash = write_json(
        output_dir / "user_profiles.json",
        user_profiles
    )

    session_hash = write_json(
        output_dir / "session_profiles.json",
        session_profiles
    )

    manifest = {
        "dataset_id": dataset_id,
        "scenario": scenario,
        "seed": seed,
        "generator_version": cfg["version"],
        "preference_mode": cfg["preference_mode"],
        "events_sha256": events_sha256,
        "catalog_sha256": catalog_sha256,
        "user_count": len(user_profiles),
        "session_count": len(session_profiles),
        "files": {
            "user_profiles.json": user_hash,
            "session_profiles.json": session_hash
        },
        "config": cfg,
        "usage": "Synthetic ground truth for validation",
        "warning": (
            "Do not use latent profiles as "
            "model training features."
        )
    }

    write_json(
        output_dir / "manifest.json",
        manifest
    )

    return output_dir
