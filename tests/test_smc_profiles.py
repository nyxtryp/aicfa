import unittest

from app.smc.profiles import PROFILES, get_profile


class ProfileConfigTests(unittest.TestCase):
    def test_scalp_profile_matches_tz(self):
        profile = get_profile("scalp")
        self.assertEqual(
            (profile.bias_timeframe, profile.zone_timeframe,
             profile.confirmation_timeframe, profile.extra_confirmation_timeframe),
            ("1h", "15m", "5m", "1m"),
        )
        self.assertEqual((profile.swing_left, profile.swing_right), (2, 2))
        self.assertEqual((profile.lifetime_hours, profile.cooldown_minutes), (3, 30))
        self.assertEqual((profile.min_rr, profile.score_threshold, profile.stop_buffer_atr),
                         (1.5, 6, 0.3))

    def test_intraday_profile_matches_tz(self):
        profile = get_profile("intraday")
        self.assertEqual(
            (profile.bias_timeframe, profile.zone_timeframe,
             profile.confirmation_timeframe, profile.extra_confirmation_timeframe),
            ("4h", "1h", "15m", None),
        )
        self.assertEqual((profile.swing_left, profile.swing_right), (3, 3))
        self.assertEqual((profile.lifetime_hours, profile.cooldown_minutes), (12, 120))
        self.assertEqual(profile.tradfi_cutoff_minutes, 15)

    def test_only_two_profiles_are_available(self):
        self.assertEqual(set(PROFILES), {"scalp", "intraday"})
        for name in ("", "swing", "SCALP", None):
            with self.subTest(name=name), self.assertRaises(ValueError):
                get_profile(name)


if __name__ == "__main__":
    unittest.main()
