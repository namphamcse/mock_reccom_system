import unittest

from data_generator.simulate_sessions import (
    calculate_click_probability
)


class TestSimulatorAffinity(unittest.TestCase):

    def setUp(self):
        self.profile = {
            "preferred_category": "Laptops",
            "preferred_brand": "Nova",
            "preferred_budget": 1200,
            "technical_preferences": {
                "cpu_vendor": "AMD",
                "min_ram_gb": 32
            }
        }

        self.product = {
            "id": "P0001",
            "category": "Laptops",
            "brand": "Nova",
            "price": 1000,
            "attributes": {
                "cpu": "AMD Ryzen 7 7840U",
                "ram_gb": 32
            }
        }

        self.cfg = {
            "affinity_weights": {
                "category": 0.35,
                "brand": 0.15,
                "price": 0.20,
                "technical": 0.30
            },
            "noise_click": 0.05,
            "affinity_click_boost": 0.7
        }

    def test_click_probability_range(self):
        probability = calculate_click_probability(
            self.profile,
            self.product,
            position=1,
            budget=1200,
            cfg=self.cfg
        )

        self.assertGreaterEqual(probability, 0)
        self.assertLessEqual(probability, 1)

    def test_position_bias(self):
        p1 = calculate_click_probability(
            self.profile, self.product, 1, 1200, self.cfg
        )

        p8 = calculate_click_probability(
            self.profile, self.product, 8, 1200, self.cfg
        )

        self.assertGreater(p1, p8)

    def test_affordability(self):
        high_budget = calculate_click_probability(
            self.profile, self.product, 1, 1500, self.cfg
        )

        low_budget = calculate_click_probability(
            self.profile, self.product, 1, 500, self.cfg
        )

        self.assertGreater(high_budget, low_budget)


if __name__ == "__main__":
    unittest.main()