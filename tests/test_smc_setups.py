import unittest

from app.smc.setups import SetupEvidence, score_setup


class SetupScoringTests(unittest.TestCase):
    def test_full_evidence_scores_ten(self):
        score = score_setup(SetupEvidence(
            liquidity_sweep=True,
            order_block_fvg_overlap=True,
            ote_overlap=True,
            higher_timeframe_bias_aligned=True,
            higher_timeframe_agreement=True,
            confirmation_volume=151,
            average_volume=100,
            clean_path_to_tp1=True,
        ))
        self.assertEqual((score.total, score.maximum), (10, 10))
        self.assertEqual(dict(score.components)["volume_above_1_5x_average"], 1)

    def test_volume_bonus_requires_strictly_more_than_one_point_five_times(self):
        for volume, expected in ((150, 0), (149, 0), (150.01, 1), (0, 0)):
            with self.subTest(volume=volume):
                score = score_setup(SetupEvidence(False, False, False, False, False,
                                                  volume, 100, False))
                self.assertEqual(dict(score.components)["volume_above_1_5x_average"], expected)

    def test_each_rule_uses_tz_weights(self):
        score = score_setup(SetupEvidence(True, True, True, True, True, 0, 0, True))
        self.assertEqual(score.total, 9)
        self.assertEqual(dict(score.components), {
            "liquidity_sweep": 2,
            "order_block_fvg_overlap": 2,
            "ote_overlap": 1,
            "higher_timeframe_bias_aligned": 2,
            "higher_timeframe_agreement": 1,
            "volume_above_1_5x_average": 0,
            "clean_path_to_tp1": 1,
        })

    def test_invalid_flags_and_volume_are_rejected(self):
        with self.assertRaises(ValueError):
            score_setup(SetupEvidence(1, False, False, False, False, 10, 5, False))
        for value in (float("nan"), float("inf"), True, "100", -1):
            with self.subTest(value=value), self.assertRaises(ValueError):
                score_setup(SetupEvidence(False, False, False, False, False, value, 5, False))


if __name__ == "__main__":
    unittest.main()
