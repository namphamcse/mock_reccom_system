
from collections import defaultdict

from data_generator.generate_users import generate_users
from data_generator.generate_products import generate_products
from data_generator.preferences import generate_user_preference
from data_generator.affinity import calculate_affinity
from data_generator.simulate_sessions import simulate_sessions


# ==========================================
# 1. CONFIGURATION
# ==========================================

SEED = 42
USER_COUNT = 100
PRODUCT_COUNT = 300
EVENT_COUNT = 10000

SCENARIOS = [
    "S1_long_term",
    "S2_intent_shift",
    "S3_cold_start",
]


# ==========================================
# 2. GENERATE MOCK DATA
# ==========================================

users = generate_users(USER_COUNT, seed=SEED)
products = generate_products(PRODUCT_COUNT, seed=SEED)

product_map = {
    product["id"]: product
    for product in products
}

profiles = {
    user["id"]: generate_user_preference(
        user_id=user["id"],
        products=[p for p in products if p["stock"] > 0],
        seed=SEED
    )
    for user in users
}


# ==========================================
# 3. TEST SESSION GENERATION
# ==========================================

print("\n========== SESSION GENERATION ==========\n")

for scenario in SCENARIOS:

    events = list(simulate_sessions(
        users=users,
        products=products,
        count=EVENT_COUNT,
        seed=SEED,
        scenario=scenario
    ))

    assert len(events) == EVENT_COUNT

    event_ids = {
        event["event_id"]
        for event in events
    }

    assert len(event_ids) == EVENT_COUNT

    session_ids = {
        event["session_id"]
        for event in events
    }

    print(
        f"{scenario}: "
        f"events={len(events)}, "
        f"sessions={len(session_ids)}"
    )


# ==========================================
# 4. GENERATE S1 EVENTS FOR CTR ANALYSIS
# ==========================================

print("\n========== AFFINITY CTR ANALYSIS ==========\n")

events = list(simulate_sessions(
    users=users,
    products=products,
    count=EVENT_COUNT,
    seed=SEED,
    scenario="S1_long_term"
))


# ==========================================
# 5. CALCULATE AFFINITY AND CTR
# ==========================================

stats = defaultdict(
    lambda: {
        "impressions": 0,
        "clicks": 0
    }
)

for event in events:

    event_name = event["event_name"]

    if event_name not in {
        "product_impression",
        "product_click"
    }:
        continue

    user_id = event["distinct_id"]
    product_id = event["product_id"]

    profile = profiles[user_id]
    product = product_map[product_id]

    affinity = calculate_affinity(
        profile=profile,
        product=product
    )

    # Divide affinity into 4 buckets
    bucket = min(3, int(affinity * 4))

    if event_name == "product_impression":
        stats[bucket]["impressions"] += 1

    elif event_name == "product_click":
        stats[bucket]["clicks"] += 1


# ==========================================
# 6. DISPLAY CTR RESULTS
# ==========================================

BUCKET_NAMES = {
    0: "Low         (0.00 - 0.25)",
    1: "Medium-Low  (0.25 - 0.50)",
    2: "Medium-High (0.50 - 0.75)",
    3: "High        (0.75 - 1.00)",
}

print(
    f"{'Affinity Group':<30}"
    f"{'Impressions':>15}"
    f"{'Clicks':>12}"
    f"{'CTR':>12}"
)

print("-" * 69)

for bucket in range(4):

    row = stats[bucket]

    impressions = row["impressions"]
    clicks = row["clicks"]

    ctr = (
        clicks / impressions
        if impressions > 0
        else 0
    )

    print(
        f"{BUCKET_NAMES[bucket]:<30}"
        f"{impressions:>15}"
        f"{clicks:>12}"
        f"{ctr:>11.2%}"
    )


# ==========================================
# 7. REPRODUCIBILITY TEST
# ==========================================

print("\n========== REPRODUCIBILITY TEST ==========\n")

events_1 = list(simulate_sessions(
    users=users,
    products=products,
    count=1000,
    seed=SEED,
    scenario="S1_long_term"
))

events_2 = list(simulate_sessions(
    users=users,
    products=products,
    count=1000,
    seed=SEED,
    scenario="S1_long_term"
))

assert events_1 == events_2

print("Reproducibility: PASS")
