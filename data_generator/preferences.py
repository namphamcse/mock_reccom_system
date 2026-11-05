import random

TECHNICAL_RULES = {
    "Laptops": {
        "cpu_vendor": ("derived", "cpu"),
        "ram_gb": "min",
        "storage_gb": "min",
        "battery_wh": "min",
    },
    "Phones": {
        "chipset": "exact",
        "ram_gb": "min",
        "camera_mp": "min",
        "battery_mah": "min",
    },
    "Tablets": {
        "ram_gb": "min",
        "storage_gb": "min",
        "display_inches": "min",
    },
    "Headphones": {
        "anc": "exact",
        "battery_hours": "min",
        "driver_mm": "min",
    },
    "Keyboards": {
        "switch_type": "exact",
        "connection": "exact",
        "key_count": "min",
    },
    "Mice": {
        "sensor_dpi": "min",
        "weight_g": "max",
        "connection": "exact",
    },
    "Monitors": {
        "refresh_hz": "min",
        "resolution": "exact",
        "panel": "exact",
    },
    "Cameras": {
        "sensor": "exact",
        "resolution_mp": "min",
        "video": "exact",
    },
    "Speakers": {
        "power_w": "min",
        "battery_hours": "min",
        "water_resistance": "exact",
    },
    "Wearables": {
        "gps": "exact",
        "battery_days": "min",
        "water_resistance": "exact",
    },
}


def generate_user_preference(user_id, products, seed=42):
    rng = random.Random(f"{seed}:{user_id}:attributes")

    categories = sorted({p['category'] for p in products})
    preferred_category = rng.choice(categories)

    candidates = [
        p for p in products
        if p['category'] == preferred_category
    ]

    brands = sorted({p['brand'] for p in candidates})
    preferred_brand = rng.choice(brands)

    prices = sorted({p['price'] for p in candidates})
    preferred_budget = rng.choice(prices)

    technical_preferences = generate_technical_preferences(
        preferred_category, candidates, rng)

    profile = {
        "user_id": user_id,
        "preferred_category": preferred_category,
        "preferred_brand": preferred_brand,
        "preferred_budget": preferred_budget,
        "technical_preferences": technical_preferences,
    }

    # Backward-compatibility aliases for older code paths.
    profile["prefered_category"] = preferred_category
    profile["prefered_brand"] = preferred_brand
    profile["preferred_price"] = preferred_budget
    profile["prefered_price"] = preferred_budget

    return profile


def extract_cpu_vendor(cpu):
    cpu = str(cpu).lower()
    if "amd" in cpu:
        return "AMD"
    elif "intel" in cpu:
        return "Intel"

    return "None"


def generate_technical_preferences(category, candidates, rng):
    rules = TECHNICAL_RULES.get(category, {})
    if not candidates:
        raise ValueError("No products found for category")

    preferences = {}
    for attribute, rule in rules.items():
        if isinstance(rule, tuple):
            mode, source_attribute = rule
        else:
            mode = rule
            source_attribute = attribute

        values = []

        for product in candidates:
            value = product.get("attributes", {}).get(source_attribute)

            if value is None:
                continue

            if mode == "derived" and attribute == "cpu_vendor":
                value = extract_cpu_vendor(value)

            values.append(value)

        if not values:
            continue

        unique_values = sorted(set(values), key=str)
        selected_value = rng.choice(unique_values)

        if mode in ("min", "max"):
            prefix = "min_" if mode == "min" else "max_"
            preferences[f"{prefix}{attribute}"] = selected_value

        else:
            preferences[attribute] = selected_value

    return preferences
