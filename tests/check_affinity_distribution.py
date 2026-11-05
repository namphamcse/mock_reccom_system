
from collections import Counter

from data_generator.generate_users import generate_users
from data_generator.generate_products import generate_products
from data_generator.preferences import generate_user_preference
from data_generator.affinity import calculate_affinity
from data_generator.simulate_sessions import simulate_sessions


SEED = 42

users = generate_users(100, seed=SEED)
products = [
    p for p in generate_products(300, seed=SEED)
    if p["stock"] > 0
]

product_map = {p["id"]: p for p in products}

profiles = {
    u["id"]: generate_user_preference(
        u["id"], products, seed=SEED
    )
    for u in users
}


def affinity_bucket(score):
    return min(3, int(score * 4))


# 1. Phân phối affinity trong toàn catalog
catalog_stats = Counter()

for user in users:
    profile = profiles[user["id"]]

    for product in products:
        score = calculate_affinity(profile, product)
        catalog_stats[affinity_bucket(score)] += 1


# 2. Phân phối affinity của sản phẩm được hiển thị
events = list(simulate_sessions(
    users, products,
    count=10000,
    seed=SEED,
    scenario="S1_long_term"
))

exposure_stats = Counter()

for event in events:
    if event["event_name"] != "product_impression":
        continue

    profile = profiles[event["distinct_id"]]
    product = product_map[event["product_id"]]

    score = calculate_affinity(profile, product)
    exposure_stats[affinity_bucket(score)] += 1


# 3. So sánh hai phân phối
names = ["Low", "Medium-Low", "Medium-High", "High"]

catalog_total = sum(catalog_stats.values())
exposure_total = sum(exposure_stats.values())

print("\nAFFINITY DISTRIBUTION COMPARISON\n")

print(
    f"{'Group':<15}"
    f"{'Catalog %':>12}"
    f"{'Exposure %':>14}"
    f"{'Lift':>12}"
)

print("-" * 53)

for bucket in range(4):
    catalog_pct = catalog_stats[bucket] / catalog_total
    exposure_pct = exposure_stats[bucket] / exposure_total

    lift = (
        exposure_pct / catalog_pct
        if catalog_pct > 0
        else 0
    )

    print(
        f"{names[bucket]:<15}"
        f"{catalog_pct:>11.2%}"
        f"{exposure_pct:>13.2%}"
        f"{lift:>11.2f}x"
    )
