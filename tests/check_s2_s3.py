
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from backend.settings import ROOT
from data_generator.generate_users import generate_users
from data_generator.generate_products import generate_products
from data_generator.preferences import generate_user_preference
from data_generator.simulate_sessions import simulate_sessions


# ==========================================
# 1. CONFIGURATION
# ==========================================

SEED = 42
USER_COUNT = 100
PRODUCT_COUNT = 300
EVENT_COUNT = 10000

cfg = json.loads(
    (ROOT / "configs/simulator.json").read_text()
)

assert cfg["preference_mode"] == "attribute_based"
assert cfg["session_intent_probability"] == 0.0

start = datetime.fromisoformat(cfg["start"])

s2_day = math.ceil(cfg["days"] * 0.65)
s3_day = math.ceil(cfg["days"] * 0.70)

s2_cutoff = start + timedelta(days=s2_day)
s3_cutoff = start + timedelta(days=s3_day)


# ==========================================
# 2. GENERATE USERS AND PRODUCTS
# ==========================================

users = generate_users(USER_COUNT, seed=SEED)

products = sorted(
    [
        p for p in generate_products(PRODUCT_COUNT, seed=SEED)
        if p["stock"] > 0
    ],
    key=lambda p: p["id"]
)

product_map = {p["id"]: p for p in products}

users = sorted(users, key=lambda u: u["id"])


# ==========================================
# 3. REBUILD S2 USER PROFILES
# ==========================================

original_profiles = {}
shifted_profiles = {}

for user in users:
    uid = user["id"]

    original = generate_user_preference(
        user_id=uid,
        products=products,
        seed=SEED
    )

    other_products = [
        p for p in products
        if p["category"] != original["preferred_category"]
    ]

    shifted = generate_user_preference(
        user_id=uid,
        products=other_products,
        seed=f"{SEED}:shift"
    ) if other_products else original

    original_profiles[uid] = original
    shifted_profiles[uid] = shifted


# ==========================================
# 4. GENERATE SCENARIO EVENTS
# ==========================================

def generate_events(scenario):
    events = list(simulate_sessions(
        users=users,
        products=products,
        count=EVENT_COUNT,
        seed=SEED,
        scenario=scenario
    ))

    assert len(events) == EVENT_COUNT
    assert len({e["event_id"] for e in events}) == EVENT_COUNT

    return events


print("\nGenerating S1, S2 and S3...")

s1_events = generate_events("S1_long_term")
s2_events = generate_events("S2_intent_shift")
s3_events = generate_events("S3_cold_start")


# ==========================================
# 5. S2: ANALYZE CATEGORY SHIFT
# ==========================================

def analyze_s2(events, label):
    stats = defaultdict(Counter)

    for event in events:
        if event["event_name"] != "product_click":
            continue

        uid = event["distinct_id"]
        product = product_map[event["product_id"]]
        timestamp = datetime.fromisoformat(event["timestamp"])

        period = "before" if timestamp < s2_cutoff else "after"

        old_category = original_profiles[uid]["preferred_category"]
        new_category = shifted_profiles[uid]["preferred_category"]

        stats[period]["total"] += 1

        if product["category"] == old_category:
            stats[period]["old"] += 1

        if product["category"] == new_category:
            stats[period]["new"] += 1

    print(f"\n{label}")

    print(
        f"{'Period':<12}"
        f"{'Clicks':>10}"
        f"{'Old Cat %':>13}"
        f"{'New Cat %':>13}"
    )

    result = {}

    for period in ("before", "after"):
        row = stats[period]
        total = row["total"]

        old_share = row["old"] / total if total else 0
        new_share = row["new"] / total if total else 0

        result[period] = {
            "clicks": total,
            "old_share": old_share,
            "new_share": new_share
        }

        print(
            f"{period:<12}"
            f"{total:>10}"
            f"{old_share:>12.2%}"
            f"{new_share:>12.2%}"
        )

    return result


print("\n========== S2 INTENT SHIFT ==========")

changed = sum(
    original_profiles[u["id"]]["preferred_category"]
    != shifted_profiles[u["id"]]["preferred_category"]
    for u in users
)

print(f"Users with changed category: {changed}/{len(users)}")
print(f"Shift starts: {s2_cutoff.isoformat()}")

s1_result = analyze_s2(s1_events, "S1 CONTROL")
s2_result = analyze_s2(s2_events, "S2 INTENT SHIFT")

assert changed == len(users)

assert s2_result["before"]["clicks"] > 0
assert s2_result["after"]["clicks"] > 0

new_share_change_s1 = (
    s1_result["after"]["new_share"]
    - s1_result["before"]["new_share"]
)

new_share_change_s2 = (
    s2_result["after"]["new_share"]
    - s2_result["before"]["new_share"]
)

effect = new_share_change_s2 - new_share_change_s1

print("\nChange in new-category click share:")
print(f"S1: {new_share_change_s1:+.2%}")
print(f"S2: {new_share_change_s2:+.2%}")
print(f"Difference-in-differences: {effect:+.2%}")

if effect > 0:
    print("S2 behavioral shift: POSITIVE SIGNAL")
else:
    print("S2 behavioral shift: NEEDS INVESTIGATION")


# ==========================================
# 6. S3: IDENTIFY COLD USERS / PRODUCTS
# ==========================================

active_user_count = max(1, int(len(users) * 0.9))
exposed_product_count = max(1, int(len(products) * 0.9))

cold_users = {
    u["id"]
    for u in users[active_user_count:]
}

cold_products = {
    p["id"]
    for p in products[exposed_product_count:]
}

print("\n========== S3 COLD START ==========")
print(f"Cold-start begins: {s3_cutoff.isoformat()}")
print(f"Cold users: {len(cold_users)}")
print(f"Cold products: {len(cold_products)}")


# ==========================================
# 7. S3: CHECK COLD-START EVENTS
# ==========================================

stats = defaultdict(Counter)
observed_cold_users = set()
observed_cold_products = set()

for event in s3_events:
    timestamp = datetime.fromisoformat(event["timestamp"])

    period = "before" if timestamp < s3_cutoff else "after"

    uid = event["distinct_id"]
    pid = event["product_id"]
    name = event["event_name"]

    if uid in cold_users:
        stats[period]["cold_user_events"] += 1

        if period == "after":
            observed_cold_users.add(uid)

    if pid in cold_products:
        stats[period]["cold_product_events"] += 1

        if period == "after" and name == "product_impression":
            observed_cold_products.add(pid)

    if name == "product_impression":
        stats[period]["impressions"] += 1

    if name == "product_click":
        stats[period]["clicks"] += 1


for period in ("before", "after"):
    print(f"\n{period.upper()}")
    for key in (
        "impressions",
        "clicks",
        "cold_user_events",
        "cold_product_events"
    ):
        print(f"{key}: {stats[period][key]}")

print(
    f"\nObserved cold users: "
    f"{len(observed_cold_users)}/{len(cold_users)}"
)

print(
    f"Cold products with impressions: "
    f"{len(observed_cold_products)}/{len(cold_products)}"
)


# ==========================================
# 8. VALIDATION
# ==========================================

assert stats["before"]["cold_user_events"] == 0
assert stats["before"]["cold_product_events"] == 0

assert stats["after"]["cold_user_events"] > 0
assert stats["after"]["cold_product_events"] > 0

print("\nS3 cold-start activation: PASS")

if len(observed_cold_users) == len(cold_users):
    print("Cold-user coverage: FULL")
else:
    print("Cold-user coverage: PARTIAL")

if len(observed_cold_products) == len(cold_products):
    print("Cold-product exposure coverage: FULL")
else:
    print("Cold-product exposure coverage: PARTIAL")
