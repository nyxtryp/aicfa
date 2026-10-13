import unittest

from app.smc.risk import acceptable_entry_limit, calculate_risk_reward


class RiskCalculationTests(unittest.TestCase):
    def test_long_limit_is_rounded_down_and_preserves_minimum_rr(self):
        limit = acceptable_entry_limit("long", 120, 90, min_rr=1.5, tick_size=0.1)
        self.assertEqual(limit, 102.0)
        self.assertGreaterEqual(calculate_risk_reward("long", limit, 90, 120), 1.5)
        self.assertLess(calculate_risk_reward("long", limit + 0.1, 90, 120), 1.5)

    def test_short_limit_is_rounded_up_and_preserves_minimum_rr(self):
        limit = acceptable_entry_limit("short", 80, 110, min_rr=1.5, tick_size=0.1)
        self.assertEqual(limit, 98.0)
        self.assertGreaterEqual(calculate_risk_reward("short", limit, 110, 80), 1.5)
        self.assertLess(calculate_risk_reward("short", limit - 0.1, 110, 80), 1.5)

    def test_rr_uses_price_levels_not_distance_inputs(self):
        self.assertEqual(calculate_risk_reward("long", 100, 95, 110), 2.0)
        self.assertEqual(calculate_risk_reward("short", 100, 105, 90), 2.0)

    def test_invalid_direction_prices_and_numeric_inputs_are_rejected(self):
        for direction in ("buy", "", None):
            with self.subTest(direction=direction), self.assertRaises(ValueError):
                calculate_risk_reward(direction, 100, 95, 110)
        for values in (("long", 95, 100, 110), ("long", 100, 100, 110),
                       ("short", 100, 90, 95)):
            with self.subTest(values=values), self.assertRaises(ValueError):
                calculate_risk_reward(*values)
        for value in (float("nan"), float("inf"), True, "100"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                calculate_risk_reward("long", value, 95, 110)
        for min_rr, tick_size in ((0, 0.1), (1.5, 0), (1.5, float("nan"))):
            with self.subTest(min_rr=min_rr, tick_size=tick_size), self.assertRaises(ValueError):
                acceptable_entry_limit("long", 120, 90, min_rr=min_rr, tick_size=tick_size)


if __name__ == "__main__":
    unittest.main()
