
import argparse
import json
import statistics

from collections import Counter
from datetime import datetime, timezone

from backend.settings import layer
from data_generator.generate_users import generate_users
from data_generator.generate_products import generate_products
from data_generator.simulate_sessions import simulate_sessions


# ==========================================
# 1. CONFIGURATION
# ==========================================

SEEDS = [42, 123, 2026]

CATALOG_SEED = 42
USER_COUNT = 100
PRODUCT_COUNT = 300
EVENT_COUNT = 10000
SCENARIO = "S3_cold_start"


# ==========================================
# 2. HELPER FUNCTIONS
# ==========================================

def safe_divide(numerator, denominator):
    return numerator / denominator if denominator else 0.0


def distribution_summary(values):
    if not values:
        return {
            "min": 0,
            "mean": 0,
            "median": 0,
            "max": 0
        }

    return {
        "min": min(values),
        "mean": round(statistics.mean(values), 4),
        "median": statistics.median(values),
        "max": max(values)
    }


# ==========================================
# 3. PROFILE ONE DATASET
# ==========================================

def profile_dataset(events, users, products, seed):

    event_counts = Counter(
        event["event_name"] for event in events
    )

    events_per_user = Counter(
        event["distinct_id"] for event in events
    )

    sessions = {
        (event["distinct_id"], event["session_id"])
        for event in events
    }

    sessions_per_user = Counter(
        uid for uid, _ in sessions
    )

    events_per_session = Counter(
        event["session_id"] for event in events
    )

    product_map = {
        p["id"]: p for p in products
    }

    impressions_per_product = Counter()
    clicks_per_product = Counter()
    category_impressions = Counter()
    category_clicks = Counter()

    interactions = set()

    for event in events:

        name = event["event_name"]
        uid = event["distinct_id"]
        pid = event["product_id"]

        # Unique user-product pairs with an action
        if name in {
            "product_click",
            "product_view",
            "add_to_cart",
            "purchase"
        }:
            interactions.add((uid, pid))

        if name == "product_impression":
            impressions_per_product[pid] += 1

            category = product_map[pid]["category"]
            category_impressions[category] += 1

        elif name == "product_click":
            clicks_per_product[pid] += 1

            category = product_map[pid]["category"]
            category_clicks[category] += 1

    impressions = event_counts["product_impression"]
    clicks = event_counts["product_click"]
    carts = event_counts["add_to_cart"]
    purchases = event_counts["purchase"]

    active_products = [
        p for p in products if p["stock"] > 0
    ]

    total_possible_pairs = (
        len(users) * len(active_products)
    )

    sparsity = 1 - safe_divide(
        len(interactions),
        total_possible_pairs
    )

    # Include users/sessions/products with zero activity
    user_event_values = [
        events_per_user[u["id"]]
        for u in users
    ]

    user_session_values = [
        sessions_per_user[u["id"]]
        for u in users
    ]

    impression_values = [
        impressions_per_product[p["id"]]
        for p in active_products
    ]

    click_values = [
        clicks_per_product[p["id"]]
        for p in active_products
    ]

    # Sessions are unique; every generated session
    # represented here has at least one event.
    session_event_values = list(
        events_per_session.values()
    )

    return {
        "seed": seed,
        "scenario": SCENARIO,

        "counts": {
            "events": len(events),
            "users": len(users),
            "active_users": len(events_per_user),
            "products": len(products),
            "active_products": len(active_products),
            "sessions": len(sessions),
        },

        "event_distribution": dict(event_counts),

        "rates": {
            "ctr": safe_divide(clicks, impressions),
            "cart_per_click": safe_divide(carts, clicks),
            "purchase_per_cart": safe_divide(
                purchases, carts
            ),
            "purchase_per_impression": safe_divide(
                purchases, impressions
            )
        },

        "user_activity": {
            "events_per_user": distribution_summary(
                user_event_values
            ),
            "sessions_per_user": distribution_summary(
                user_session_values
            )
        },

        "session_activity": {
            "events_per_session": distribution_summary(
                session_event_values
            )
        },

        "product_activity": {
            "impressions_per_product": distribution_summary(
                impression_values
            ),
            "clicks_per_product": distribution_summary(
                click_values
            ),
            "top_10_by_impressions": (
                impressions_per_product.most_common(10)
            )
        },

        "category_distribution": {
            "impressions": dict(category_impressions),
            "clicks": dict(category_clicks)
        },

        "interaction_matrix": {
            "observed_pairs": len(interactions),
            "possible_pairs": total_possible_pairs,
            "sparsity": sparsity
        }
    }


# ==========================================
# 4. MULTI-SEED SUMMARY
# ==========================================

def summarize_seeds(results):
    metric_names = [
        "ctr",
        "cart_per_click",
        "purchase_per_cart",
        "purchase_per_impression"
    ]

    summary = {}

    for metric in metric_names:
        values = [
            result["rates"][metric]
            for result in results
        ]

        summary[metric] = {
            "mean": statistics.mean(values),
            "min": min(values),
            "max": max(values),
            "std": (
                statistics.stdev(values)
                if len(values) > 1
                else 0.0
            )
        }

    return summary


# ==========================================
# 5. MAIN EXECUTION
# ==========================================

def main():

    users = generate_users(
        USER_COUNT, seed=CATALOG_SEED
    )

    products = generate_products(
        PRODUCT_COUNT, seed=CATALOG_SEED
    )

    results = []

    for seed in SEEDS:

        print(f"\nGenerating dataset with seed={seed}")

        events = list(simulate_sessions(
            users=users,
            products=products,
            count=EVENT_COUNT,
            seed=seed,
            scenario=SCENARIO
        ))

        result = profile_dataset(
            events=events,
            users=users,
            products=products,
            seed=seed
        )

        results.append(result)

        print(
            f"Events: {result['counts']['events']}, "
            f"Sessions: {result['counts']['sessions']}"
        )

        print(
            f"CTR: {result['rates']['ctr']:.2%}, "
            f"Sparsity: "
            f"{result['interaction_matrix']['sparsity']:.2%}"
        )

    summary = summarize_seeds(results)

    report = {
        "created_at": datetime.now(
            timezone.utc
        ).isoformat(),

        "configuration": {
            "catalog_seed": CATALOG_SEED,
            "simulation_seeds": SEEDS,
            "users": USER_COUNT,
            "products": PRODUCT_COUNT,
            "events_per_seed": EVENT_COUNT,
            "scenario": SCENARIO
        },

        "datasets": results,
        "multi_seed_summary": summary
    }

    output_dir = layer("mock") / "profiling"
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = (
        output_dir / "multi_seed_profile.json"
    )

    output_path.write_text(
        json.dumps(
            report,
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )

    print("\n========== MULTI-SEED SUMMARY ==========")

    for metric, values in summary.items():
        print(
            f"{metric:<28}"
            f"mean={values['mean']:.2%}  "
            f"std={values['std']:.2%}  "
            f"range=[{values['min']:.2%}, "
            f"{values['max']:.2%}]"
        )

    print(f"\nReport saved: {output_path}")


if __name__ == "__main__":
    main()
