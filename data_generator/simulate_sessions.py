"""Reproducible exposure -> click -> view -> cart -> purchase sessions."""
import argparse
import hashlib
import json
import random
from datetime import datetime, timedelta
from uuid import NAMESPACE_URL, uuid5

import pandas as pd
from backend.db import records, save_events
from backend.settings import ROOT, layer
from backend.observability import audit
from pipeline.storage import write_parquet

from data_generator.preferences import generate_user_preference
from data_generator.affinity import calculate_affinity

from data_generator.ground_truth import export_ground_truth


def simulate_sessions(
    users,
    products,
    count=100000,
    seed=42,
    scenario="S1_long_term",
    ground_truth=None
):
    cfg = json.loads((ROOT / 'configs/simulator.json').read_text())
    if scenario not in cfg['scenarios'] or count < 0:
        raise ValueError('Invalid scenario/count')
    rng = random.Random(seed)
    products = sorted([p for p in products if p['stock']
                      > 0], key=lambda p: p['id'])
    if not users or not products:
        raise ValueError('Seed catalog/users first')
    # Only identity affects simulation; ignore every legacy user attribute.
    users = [{'id': u['id']} for u in sorted(users, key=lambda u: u['id'])]
    item_ids = [p["id"] for p in products]
    mode = cfg.get("preference_mode", "product_id_based")
    if mode not in {"product_id_based", "attribute_based"}:
        raise ValueError(f"Invalid preference mode: {mode}")

    preferences = {}
    shifted_preferences = {}

    if mode == "product_id_based":
        preferences = {
            u["id"]: random.Random(
                f"{seed}:{u['id']}"
            ).sample(
                item_ids,
                max(1, len(item_ids) // 5)
            )
            for u in users
        }
    else:
        for user in users:
            uid = user["id"]

            # Long-term user profile
            preferences[uid] = generate_user_preference(
                user_id=uid,
                products=products,
                seed=seed
            )

            # Profile dùng sau khi intent shift.
            # Chọn một category khác để đảm bảo có sự thay đổi.
            current_category = preferences[uid][
                "preferred_category"
            ]

            other_products = [
                p for p in products
                if p["category"] != current_category
            ]

            if other_products:
                shifted_preferences[uid] = (
                    generate_user_preference(
                        user_id=uid,
                        products=other_products,
                        seed=f"{seed}:shift"
                    )
                )
            else:
                shifted_preferences[uid] = preferences[uid]

    if ground_truth is not None:
        if mode != "attribute_based":
            raise ValueError(
                "Ground Truth export requires attribute_based mode"
            )

        ground_truth["user_profiles"] = []

        for user in users:
            uid = user["id"]

            ground_truth["user_profiles"].append({
                "user_id": uid,
                "long_term_profile": preferences[uid],
                "shifted_profile": (
                    shifted_preferences[uid]
                    if scenario == "S2_intent_shift"
                    else None
                )
            })
        ground_truth["session_profiles"] = []
    dataset_key = hashlib.sha256(json.dumps({'config': cfg, 'count': count, 'seed': seed, 'scenario': scenario,
                                            'users': users, 'products': products}, sort_keys=True).encode()).hexdigest()[:20]
    # Reserve final 10% of products as metadata-only cold items.
    exposed_pool = products[:max(1, int(len(products) * .9))]
    active_users = users[:max(1, int(len(users) * .9))
                         ] if scenario == 'S3_cold_start' else users
    start = datetime.fromisoformat(cfg['start'])
    emitted, session_num = 0, 0
    while emitted < count:
        session_num += 1
        estimated_sessions = max(1, count / (cfg['exposure_size'] + 6))
        day = min(cfg['days'] - 1, int((session_num - 1)
                  * cfg['days'] / estimated_sessions))
        session_users = users if scenario == 'S3_cold_start' and day >= cfg[
            'days']*.7 else active_users
        session_pool = products if scenario == 'S3_cold_start' and day >= cfg[
            'days']*.7 else exposed_pool
        user = session_users[(session_num - 1) % len(session_users)]
        sid = str(
            uuid5(NAMESPACE_URL, f"{cfg['version']}:{dataset_key}:session:{session_num}"))
        ts = start + timedelta(days=day, hours=8 +
                               rng.randrange(12), minutes=rng.randrange(60))

        if mode == "product_id_based":
            preferred_items = preferences[user["id"]]

            alternatives = [
                pid for pid in item_ids
                if pid not in preferred_items
            ]

            shifted = random.Random(
                f"{seed}:{user['id']}:shift"
            ).sample(
                alternatives,
                min(len(preferred_items), len(alternatives))
            )

            intent_items = (
                shifted
                if scenario == "S2_intent_shift"
                and day >= cfg["days"] * 0.65
                else preferred_items
            )

            if rng.random() < 0.15:
                intent_items = rng.sample(
                    item_ids,
                    max(1, len(item_ids) // 5)
                )

        else:
            profile = preferences[user["id"]]
            intent_type = "long_term"

            if (
                scenario == "S2_intent_shift"
                and day >= cfg["days"] * 0.65
            ):
                profile = shifted_preferences[user["id"]]
                intent_type = "shifted"

            if rng.random() < cfg["session_intent_probability"]:

                other_categories = sorted({
                    p["category"]
                    for p in session_pool
                    if p["category"] != profile["preferred_category"]
                })

                if other_categories:
                    temporary_category = rng.choice(other_categories)

                    candidates = [
                        p for p in session_pool
                        if p["category"] == temporary_category
                    ]

                    profile = generate_user_preference(
                        user_id=user["id"],
                        products=candidates,
                        seed=f"{seed}:session:{session_num}"
                    )

                    intent_type = "temporary"
        budget = rng.uniform(500, 1800)
        if ground_truth is not None:
            ground_truth["session_profiles"].append({
                "session_id": sid,
                "user_id": user["id"],
                "scenario": scenario,
                "day_index": day,
                "intent_type": intent_type,
                "effective_profile": profile
            })
        # ---------------------------------
        # 1. Select product exposure
        # ---------------------------------

        if mode == "product_id_based":

            # Original exposure sampling
            pool = rng.sample(
                session_pool,
                min(cfg["exposure_size"] * 3, len(session_pool))
            )

            weights = [
                cfg["exploration"] + int(p["id"] in intent_items)
                for p in pool
            ]

            exposure = []

            while pool and len(exposure) < cfg["exposure_size"]:
                index = rng.choices(
                    range(len(pool)),
                    weights=weights
                )[0]

                exposure.append(pool.pop(index))
                weights.pop(index)

        else:

            # Attribute-based exposure sampling
            exposure = sample_exposure(
                session_pool=session_pool,
                profile=profile,
                rng=rng,
                cfg=cfg,
                budget=budget
            )

        # ---------------------------------
        # 2. Simulate user behavior
        # ---------------------------------

        planned = []

        for position, p in enumerate(exposure, 1):

            planned.append((
                "product_impression", p, position, None
            ))

            affordable = min(
                1.0,
                budget / max(p["price"], 1)
            )

            if mode == "product_id_based":

                relevance = int(p["id"] in intent_items)

                probability = (
                    cfg["noise_click"]
                    + 0.7 * relevance * affordable
                ) / (1 + 0.08 * (position - 1))

            else:

                probability = calculate_click_probability(
                    profile=profile,
                    product=p,
                    position=position,
                    budget=budget,
                    cfg=cfg
                )

            if rng.random() < probability:

                planned.extend([
                    ("product_click", p, position, None),
                    ("product_view", p, position, None)
                ])

                if rng.random() < cfg["wishlist_probability"]:
                    planned.append((
                        "add_to_wishlist", p, position, None
                    ))

                if rng.random() < cfg["cart_probability"] * affordable:

                    planned.append((
                        "add_to_cart", p, position, None
                    ))

                    if rng.random() < cfg["purchase_probability"]:
                        planned.append((
                            "purchase",
                            p,
                            position,
                            f"{sid}:order"
                        ))
        for step, (name, p, position, order) in enumerate(planned):
            if emitted >= count:
                break
            ts += timedelta(seconds=rng.randint(3, 50))
            eid = str(uuid5(NAMESPACE_URL, f'{sid}:{step}'))
            yield {'event_id': eid, 'timestamp': ts.isoformat(), 'distinct_id': user['id'], 'session_id': sid,
                   'event_name': name, 'product_id': p['id'], 'source': 'simulator', 'synthetic': True,
                   'environment': 'dev', 'position': position, 'order_id': order,
                   'order_item_id': f'{order}:{p["id"]}' if order else None}
            emitted += 1


def generate(count=100000, seed=42, scenario='S1_long_term', send=False):
    from data_generator.seed import seed as seed_catalog
    seed_catalog(seed_value=seed)
    cfg = json.loads(
        (ROOT / "configs/simulator.json").read_text()
    )

    users = records("users")
    products = records("products")

    collect_ground_truth = (
        cfg.get("preference_mode") == "attribute_based"
    )

    ground_truth = {} if collect_ground_truth else None

    events = list(simulate_sessions(
        users=users,
        products=products,
        count=count,
        seed=seed,
        scenario=scenario,
        ground_truth=ground_truth
    ))
    payload = "\n".join(
        json.dumps(e, sort_keys=True)
        for e in events
    )

    payload_bytes = payload.encode("utf-8")

    digest = hashlib.sha256(payload_bytes).hexdigest()
    out = layer('raw', 'synthetic') / f'{scenario}-{seed}-{digest[:12]}'
    out.mkdir(parents=True, exist_ok=True)
    (out / "events.jsonl").write_bytes(payload_bytes)
    write_parquet(pd.DataFrame(events), out / 'events.parquet')
    catalog_sha256 = hashlib.sha256(
        json.dumps(products, sort_keys=True).encode("utf-8")
    ).hexdigest()

    ground_truth_dir = None
    if collect_ground_truth:
        ground_truth_dir = export_ground_truth(
            ground_truth=ground_truth,
            scenario=scenario,
            seed=seed,
            events_sha256=digest,
            catalog_sha256=catalog_sha256,
            cfg=cfg,
        )

    manifest = {'scenario': scenario, 'seed': seed, 'count': count, 'sha256': digest, 'config': cfg,
                'origin': 'synthetic', 'sessions': len({e['session_id'] for e in events}),
                'catalog_sha256': catalog_sha256,
                'note': 'Synthetic sanity check only; not real-user accuracy.',
                'ground_truth_exported': collect_ground_truth,
                'ground_truth_path': str(ground_truth_dir) if ground_truth_dir else None}
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    audit('simulator.generated', origin='synthetic',
          scenario=scenario, seed=seed, count=count, path=str(out))
    if send:
        from pipeline.extract.posthog_client import send_events
        send_events(events)
    else:
        inserted = save_events(events)
        audit('simulator.local_saved', origin='synthetic', count=count,
              inserted=inserted, duplicates=count-inserted)
    return manifest


def sample_exposure(
    session_pool,
    profile,
    rng,
    cfg,
    budget
):
    pool = list(session_pool)
    exposure = []

    while pool and len(exposure) < cfg["exposure_size"]:
        weights = []

        for product in pool:
            affinity = calculate_affinity(
                profile,
                product,
                weights=cfg["affinity_weights"]
            )

            # Affinity đã có price matching.
            # Budget phiên sẽ tiếp tục ảnh hưởng đến hành vi.
            weight = (
                cfg["exploration"]
                + cfg["affinity_exposure_boost"] * affinity
            )

            weights.append(weight)

        index = rng.choices(
            range(len(pool)),
            weights=weights,
            k=1
        )[0]

        exposure.append(pool.pop(index))

    return exposure


def calculate_click_probability(
    profile,
    product,
    position,
    budget,
    cfg
):
    affinity = calculate_affinity(
        profile,
        product,
        weights=cfg["affinity_weights"]
    )

    affordable = min(
        1.0,
        budget / max(product["price"], 1)
    )

    position_bias = 1 + 0.08 * (position - 1)

    probability = (
        cfg["noise_click"]
        + cfg["affinity_click_boost"] * affinity * affordable
    ) / position_bias

    return max(0.0, min(1.0, probability))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--events', type=int, default=100000)
    p.add_argument('--seed', type=int, default=42)
    p.add_argument('--scenario', choices=['S1_long_term',
                   'S2_intent_shift', 'S3_cold_start'], default='S1_long_term')
    p.add_argument('--posthog', action='store_true')
    a = p.parse_args()
    print(json.dumps(generate(a.events, a.seed, a.scenario, a.posthog), indent=2))
