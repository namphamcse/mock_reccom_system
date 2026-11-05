from data_generator.generate_products import generate_products
from data_generator.preferences import generate_user_preference
from data_generator.affinity import calculate_affinity


products = generate_products(count=300, seed=42)

profile = generate_user_preference(
    user_id="U0001",
    products=products,
    seed=42
)

ranked_products = []

for product in products:
    score = calculate_affinity(profile, product)

    ranked_products.append({
        "product_id": product["id"],
        "category": product["category"],
        "brand": product["brand"],
        "price": product["price"],
        "affinity": score,
    })

ranked_products.sort(
    key=lambda p: p["affinity"],
    reverse=True
)

print("USER PROFILE:")
print(profile)

print("\nTOP 10 PRODUCTS:")

for product in ranked_products[:10]:
    print(product)