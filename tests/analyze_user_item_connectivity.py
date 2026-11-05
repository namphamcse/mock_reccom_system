
import argparse
import json
import statistics

from collections import Counter, defaultdict
from pathlib import Path

from backend.db import records


ACTION_EVENTS = {
    "product_click",
    "product_view",
    "add_to_wishlist",
    "add_to_cart",
    "purchase",
}


def summarize(values):
    values = sorted(values)

    if not values:
        return {
            "min": 0, "mean": 0,
            "median": 0, "p10": 0,
            "p90": 0, "max": 0
        }

    def percentile(p):
        index = round((len(values) - 1) * p)
        return values[index]

    return {
        "min": min(values),
        "mean": round(statistics.mean(values), 3),
        "median": statistics.median(values),
        "p10": percentile(0.10),
        "p90": percentile(0.90),
        "max": max(values),
    }


def load_action_pairs(event_path):
    """Đọc JSONL và lấy các cặp user-item có action."""
    pairs = set()
    action_counts = Counter()
    impressions = Counter()

    with event_path.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue

            event = json.loads(line)
            name = event["event_name"]
            uid = event["distinct_id"]
            pid = event["product_id"]

            if name == "product_impression":
                impressions[pid] += 1

            if name in ACTION_EVENTS:
                pairs.add((uid, pid))
                action_counts[pid] += 1

    return pairs, action_counts, impressions


def connected_components(pairs):
    """Tìm các thành phần liên thông của đồ thị user-item."""
    parent = {}
    size = {}

    def find(x):
        if x not in parent:
            parent[x] = x
            size[x] = 1

        if parent[x] != x:
            parent[x] = find(parent[x])

        return parent[x]

    def union(a, b):
        ra, rb = find(a), find(b)

        if ra == rb:
            return

        if size[ra] < size[rb]:
            ra, rb = rb, ra

        parent[rb] = ra
        size[ra] += size[rb]

    for uid, pid in pairs:
        union(f"user:{uid}", f"item:{pid}")

    components = defaultdict(list)

    for node in parent:
        components[find(node)].append(node)

    sizes = sorted(
        (len(nodes) for nodes in components.values()),
        reverse=True
    )

    return {
        "component_count": len(sizes),
        "largest_component_nodes": sizes[0] if sizes else 0,
        "largest_component_fraction": (
            sizes[0] / len(parent) if parent else 0
        ),
        "isolated_catalog_nodes_excluded": True,
    }


def analyze(dataset_dir):
    event_path = dataset_dir / "events.jsonl"
    manifest_path = dataset_dir / "manifest.json"

    if not event_path.exists():
        raise FileNotFoundError(event_path)

    manifest = json.loads(
        manifest_path.read_text(encoding="utf-8")
    )

    users = records("users")
    products = records("products")

    user_ids = {u["id"] for u in users}
    product_ids = {p["id"] for p in products}

    pairs, action_counts, impressions = load_action_pairs(
        event_path
    )

    # Không phân tích sai catalog.
    invalid_pairs = [
        (uid, pid)
        for uid, pid in pairs
        if uid not in user_ids or pid not in product_ids
    ]

    if invalid_pairs:
        raise ValueError(
            f"Found {len(invalid_pairs)} invalid user-item pairs"
        )

    user_items = defaultdict(set)
    item_users = defaultdict(set)

    for uid, pid in pairs:
        user_items[uid].add(pid)
        item_users[pid].add(uid)

    items_per_user = [
        len(user_items[uid]) for uid in sorted(user_ids)
    ]

    users_per_item = [
        len(item_users[pid]) for pid in sorted(product_ids)
    ]

    possible_pairs = len(user_ids) * len(product_ids)
    observed_pairs = len(pairs)

    total_actions = sum(action_counts.values())

    top_10_actions = sum(
        count
        for _, count in action_counts.most_common(10)
    )

    report = {
        "dataset_id": dataset_dir.name,
        "scenario": manifest["scenario"],
        "seed": manifest["seed"],
        "catalog_users": len(user_ids),
        "catalog_products": len(product_ids),
        "observed_pairs": observed_pairs,
        "possible_pairs": possible_pairs,
        "density": (
            observed_pairs / possible_pairs
            if possible_pairs else 0
        ),
        "sparsity": (
            1 - observed_pairs / possible_pairs
            if possible_pairs else 0
        ),
        "items_per_user": summarize(items_per_user),
        "users_per_item": summarize(users_per_item),
        "users_with_zero_action_items": sum(
            x == 0 for x in items_per_user
        ),
        "users_with_fewer_than_5_items": sum(
            x < 5 for x in items_per_user
        ),
        "items_with_zero_actions": sum(
            x == 0 for x in users_per_item
        ),
        "items_with_zero_impressions": sum(
            impressions[pid] == 0
            for pid in product_ids
        ),
        "total_action_events": total_actions,
        "top_10_item_action_share": (
            top_10_actions / total_actions
            if total_actions else 0
        ),
        "connectivity": connected_components(pairs),
        "interaction_definition": sorted(ACTION_EVENTS),
    }

    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        required=True
    )

    args = parser.parse_args()
    report = analyze(args.dataset_dir)

    output = args.dataset_dir / "connectivity_report.json"

    output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    print("\n=== USER-ITEM CONNECTIVITY ===")
    print("Users:", report["catalog_users"])
    print("Products:", report["catalog_products"])
    print("Unique pairs:", report["observed_pairs"])
    print(f"Sparsity: {report['sparsity']:.2%}")

    print("Items per user:", report["items_per_user"])
    print("Users per item:", report["users_per_item"])

    print(
        "Users with fewer than 5 items:",
        report["users_with_fewer_than_5_items"]
    )
    print(
        "Items with zero actions:",
        report["items_with_zero_actions"]
    )
    print(
        "Largest component:",
        f"{report['connectivity']['largest_component_fraction']:.2%}"
    )
    print(
        "Top 10 item action share:",
        f"{report['top_10_item_action_share']:.2%}"
    )
    print("Saved:", output)


if __name__ == "__main__":
    main()
