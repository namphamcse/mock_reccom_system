
from collections import Counter

from data_generator.generate_users import generate_users
from data_generator.generate_products import generate_products
from data_generator.simulate_sessions import simulate_sessions


SEED = 42
EVENT_COUNT = 1000

users = generate_users(100, seed=SEED)
products = generate_products(300, seed=SEED)

SCENARIOS = [
    "S1_long_term",
    "S2_intent_shift",
    "S3_cold_start"
]

for scenario in SCENARIOS:

    ground_truth = {}

    events = list(simulate_sessions(
        users=users,
        products=products,
        count=EVENT_COUNT,
        seed=SEED,
        scenario=scenario,
        ground_truth=ground_truth
    ))

    user_profiles = ground_truth["user_profiles"]
    session_profiles = ground_truth["session_profiles"]

    event_session_ids = {
        e["session_id"] for e in events
    }

    gt_session_ids = {
        s["session_id"] for s in session_profiles
    }

    # Kiểm tra số event
    assert len(events) == EVENT_COUNT

    # Kiểm tra số user profiles
    assert len(user_profiles) == len(users)

    # Mỗi session có đúng một effective profile
    assert len(session_profiles) == len(gt_session_ids)

    # Mỗi session trong events đều có Ground Truth
    assert event_session_ids == gt_session_ids

    # Kiểm tra intent types
    intent_counts = Counter(
        s["intent_type"]
        for s in session_profiles
    )

    # Không được thiếu effective profile
    assert all(
        isinstance(s["effective_profile"], dict)
        for s in session_profiles
    )

    print(f"\nScenario: {scenario}")
    print(f"Events: {len(events)}")
    print(f"Users: {len(user_profiles)}")
    print(f"Sessions: {len(session_profiles)}")
    print(f"Intent types: {dict(intent_counts)}")
    print("Ground Truth collection: PASS")
