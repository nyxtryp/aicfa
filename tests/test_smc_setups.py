import unittest

from app.smc.setups import SetupEvidence, evaluate_candidate, score_setup


class SetupScoringTests(unittest.TestCase):
    def evidence(self, **overrides):
        values = dict(
            liquidity_sweep=True,
            order_block_fvg_overlap=True,
            ote_overlap=True,
            higher_timeframe_bias_aligned=True,
            higher_timeframe_agreement=True,
            confirmation_volume=151,
            average_volume=100,
            clean_path_to_tp1=True,
        )
        values.update(overrides)
        return SetupEvidence(**values)

    def test_full_evidence_scores_ten(self):
        score = score_setup(self.evidence())
        self.assertEqual((score.total, score.maximum), (10, 10))
        self.assertEqual(dict(score.components)["volume_above_1_5x_average"], 1)

    def test_volume_bonus_requires_strictly_more_than_one_point_five_times(self):
        for volume, expected in ((150, 0), (149, 0), (150.01, 1), (0, 0)):
            with self.subTest(volume=volume):
                score = score_setup(self.evidence(confirmation_volume=volume, average_volume=100))
                self.assertEqual(dict(score.components)["volume_above_1_5x_average"], expected)

    def test_each_rule_uses_tz_weights(self):
        score = score_setup(self.evidence(
            liquidity_sweep=True, order_block_fvg_overlap=True, ote_overlap=True,
            higher_timeframe_bias_aligned=True, higher_timeframe_agreement=True,
            confirmation_volume=0, average_volume=0, clean_path_to_tp1=True,
        ))
        self.assertEqual(score.total, 9)
        self.assertEqual(dict(score.components)["volume_above_1_5x_average"], 0)

    def test_invalid_flags_and_volume_are_rejected(self):
        with self.assertRaises(ValueError):
            score_setup(self.evidence(liquidity_sweep=1))
        for value in (float("nan"), float("inf"), True, "100", -1):
            with self.subTest(value=value), self.assertRaises(ValueError):
                score_setup(self.evidence(confirmation_volume=value))

    def evaluate(self, **overrides):
        values = dict(
            direction="long", higher_timeframe_bias="long",
            premium_discount_zone="discount", zone_intersects_ote=True,
            confirmation_aligned=True, one_minute_confirmed=True,
            profile="intraday", entry_price=100, current_price=100.5,
            stop_price=95, tp1_price=110, tick_size=0.1,
            min_stop_distance=1, data_fresh=True,
            tradfi_market_open=True, duplicate=False, cooldown_active=False,
            active_count=0, max_active=8,
        )
        values.update(overrides)
        return evaluate_candidate(self.evidence(), **values)

    def test_candidate_is_eligible_only_when_all_gates_pass(self):
        decision = self.evaluate()
        self.assertEqual(decision.status, "ELIGIBLE")
        self.assertEqual(decision.entry_limit, 101.0)
        self.assertGreaterEqual(decision.risk_reward, 1.5)
        self.assertEqual(decision.reasons, ())

    def test_price_past_limit_is_missed_not_accepted(self):
        decision = self.evaluate(current_price=101.1)
        self.assertEqual(decision.status, "MISSED_PRICE")
        self.assertEqual(decision.reasons, ("price_beyond_acceptable_entry",))

    def test_mandatory_gates_return_explicit_reasons(self):
        decision = self.evaluate(
            higher_timeframe_bias="short", premium_discount_zone="premium",
            zone_intersects_ote=False, confirmation_aligned=False,
            data_fresh=False, duplicate=True, cooldown_active=True, active_count=8,
        )
        self.assertEqual(decision.status, "REJECTED")
        for reason in ("higher_timeframe_bias_conflict", "wrong_premium_discount_zone",
                       "zone_does_not_intersect_ote", "confirmation_not_aligned",
                       "market_data_stale_or_incomplete", "duplicate_setup",
                       "cooldown_active", "active_setup_limit_reached"):
            self.assertIn(reason, decision.reasons)

    def test_scalp_requires_one_minute_confirmation(self):
        decision = self.evaluate(profile="scalp", one_minute_confirmed=False)
        self.assertEqual(decision.status, "REJECTED")
        self.assertIn("one_minute_confirmation_missing", decision.reasons)

    def test_short_candidate_uses_lower_price_boundary(self):
        decision = self.evaluate(
            direction="short", higher_timeframe_bias="short",
            premium_discount_zone="premium", entry_price=100,
            current_price=99.5, stop_price=105, tp1_price=90,
        )
        self.assertEqual(decision.status, "ELIGIBLE")
        self.assertEqual(decision.entry_limit, 99.0)


if __name__ == "__main__":
    unittest.main()
