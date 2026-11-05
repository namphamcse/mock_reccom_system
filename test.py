import random

from data_generator.generate_products import generate_products
from data_generator.preferences import (
    TECHNICAL_RULES,
    generate_technical_preferences,
)

products = generate_products()

for category in TECHNICAL_RULES:
    candidates = [
        p for p in products
        if p["category"] == category
    ]

    rng = random.Random(42)

    technical = generate_technical_preferences(
        category, candidates, rng
    )

    print(category, technical)

    assert technical, f"No technical preferences: {category}"