import unittest

from app.smc.indicators import calculate_atr, calculate_average_volume


class IndicatorTests(unittest.TestCase):
    def test_wilder_atr_uses_seed_average_then_recursive_smoothing(self):
        self.assertEqual(
            calculate_atr([10, 12, 13], [8, 9, 11], [9, 11, 12], period=2),
            (None, 2.5, 2.25),
        )

    def test_atr_does_not_emit_before_full_seed_window(self):
        self.assertEqual(
            calculate_atr([10], [8], [9], period=2),
            (None,),
        )

    def test_average_volume_is_trailing_and_causal(self):
        self.assertEqual(
            calculate_average_volume([10, 20, 30, 50], period=2),
            (None, 15.0, 25.0, 40.0),
        )

    def test_invalid_inputs_are_rejected(self):
        with self.assertRaises(ValueError):
            calculate_atr([1, 2], [0], [0], period=1)
        with self.assertRaises(ValueError):
            calculate_average_volume([1, -1], period=1)
        with self.assertRaises(ValueError):
            calculate_atr([1], [0], [2], period=1)

    def test_non_finite_indicator_inputs_are_rejected(self):
        for bad in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    calculate_atr([bad], [0], [0], period=1)
                with self.assertRaises(ValueError):
                    calculate_average_volume([bad], period=1)

    def test_period_must_be_a_positive_integer(self):
        for bad in (0, -1, 1.5, True):
            with self.subTest(period=bad):
                with self.assertRaises(ValueError):
                    calculate_atr([1], [0], [0], period=bad)
                with self.assertRaises(ValueError):
                    calculate_average_volume([1], period=bad)

if __name__ == "__main__":
    unittest.main()
