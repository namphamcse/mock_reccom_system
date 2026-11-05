import unittest

from data_generator.affinity import (
    calculate_affinity,
    technical_score,
    price_score,
)


class TestAffinity(unittest.TestCase):

    def setUp(self):
        self.profile = {
            "user_id": "U0001",
            "preferred_category": "Laptops",
            "preferred_brand": "Nova",
            "preferred_budget": 1000,
            "technical_preferences": {
                "cpu_vendor": "AMD",
                "min_ram_gb": 32,
                "min_storage_gb": 512,
            },
        }

        self.product = {
            "id": "P0001",
            "category": "Laptops",
            "brand": "Nova",
            "price": 950,
            "attributes": {
                "cpu": "AMD Ryzen 7 7840U",
                "ram_gb": 32,
                "storage_gb": 1024,
            },
        }

    def test_perfect_match(self):
        score = calculate_affinity(
            self.profile, self.product
        )
        self.assertAlmostEqual(score, 1.0)

    def test_lower_ram(self):
        product = {
            **self.product,
            "attributes": {
                **self.product["attributes"],
                "ram_gb": 16,
            },
        }

        score = technical_score(self.profile, product)
        self.assertAlmostEqual(score, 2.5 / 3)

    def test_over_budget(self):
        product = {**self.product, "price": 1500}

        score = price_score(self.profile, product)
        self.assertAlmostEqual(score, 1000 / 1500)

    def test_different_category(self):
        product = {
            **self.product,
            "category": "Phones",
        }

        self.assertEqual(
            technical_score(self.profile, product), 0.0
        )

        score = calculate_affinity(
            self.profile, product
        )
        self.assertLess(score, 1.0)

    def test_affinity_range(self):
        score = calculate_affinity(
            self.profile, self.product
        )
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)


if __name__ == "__main__":
    unittest.main()