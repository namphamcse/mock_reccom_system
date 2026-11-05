from data_generator.preferences import extract_cpu_vendor

AFFINITY_WEIGHTS = {
    "category": 0.35,
    "brand": 0.15,
    "price": 0.20,
    "technical": 0.30,
}


def category_score(profile, product):
    preferred = profile['preferred_category']
    actual = product['category']
    return 1.0 if preferred == actual else 0


def brand_score(profile, product):
    preferred = profile['preferred_brand']
    actual = product['brand']
    return 1.0 if preferred == actual else 0


def price_score(profile, product):
    budget = profile['preferred_budget']
    actual = product['price']
    if budget <= 0:
        raise ValueError("Budget must be positive")
    if actual < 0:
        raise ValueError("Product price must be positive")
    if actual == 0:
        return 1.0
    return min(1.0, budget/actual)


def compare_attribute(actual, expected, mode):
    if mode == "exact":
        return 1.0 if actual == expected else 0

    actual = float(actual)
    expected = float(expected)

    if mode == 'min':
        if expected <= 0:
            raise ValueError("Minimum threshold must be positive")

        return min(1.0, max(0.0, actual / expected))
    if mode == "max":
        if expected <= 0:
            raise ValueError("Minimum threshold must be positive")
        if actual <= 0:
            raise ValueError("Actual value must be positive")
        return min(1.0, expected/actual)

    raise ValueError(f"Unknown comparison mode: {mode}")


def technical_score(profile, product):
    if profile["preferred_category"] != product["category"]:
        return 0.0

    preferences = profile.get("technical_preferences", {})
    attributes = product.get("attributes", {})

    if not preferences:
        return 0.0

    scores = []

    for key, expected in preferences.items():
        if key.startswith("min_"):
            mode = "min"
            attribute = key[4:]
        elif key.startswith("max_"):
            mode = "max"
            attribute = key[4:]
        else:
            mode = "exact"
            attribute = key

        if attribute == "cpu_vendor":
            cpu = attributes.get("cpu")
            actual = extract_cpu_vendor(cpu) if cpu is not None else None
        else:
            actual = attributes.get(attribute)
        if actual is None:
            scores.append(0.0)
            continue

        score = compare_attribute(
            actual, expected, mode
        )
        scores.append(score)
    return sum(scores)/len(scores)


def calculate_affinity(profile, product, weights=None):
    if weights is None:
        weights = AFFINITY_WEIGHTS

    if set(weights) != set(AFFINITY_WEIGHTS):
        raise ValueError("Invalid affinity weight keys")

    if any(w < 0 for w in weights.values()):
        raise ValueError("Weights cannot be negative")

    if abs(sum(weights.values()) - 1.0) > 1e-9:
        raise ValueError("Affinity weights must sum to 1")

    scores = {
        "category": category_score(profile, product),
        "brand": brand_score(profile, product),
        "price": price_score(profile, product),
        "technical": technical_score(profile, product),
    }

    affinity = sum(
        weights[key] * scores[key] for key in weights
    )

    return round(affinity, 6)
