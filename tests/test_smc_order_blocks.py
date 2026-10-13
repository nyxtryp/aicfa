import unittest

from app.smc.breaks import StructureBreak
from app.smc.order_blocks import (
    OrderBlock,
    OrderBlockMitigation,
    find_order_blocks,
    is_order_block_mitigated,
    measure_order_block_mitigation,
)


class OrderBlockTests(unittest.TestCase):
    def test_bullish_break_uses_last_bearish_body_before_break(self):
        blocks = find_order_blocks(
            opens=[8, 9, 10, 11, 10],
            highs=[9, 10, 11, 12, 13],
            lows=[7, 8, 9, 10, 9],
            closes=[8.5, 8.5, 10.5, 11.5, 12.5],
            events=[StructureBreak("BOS", "bullish", 4, 0, 11.0)],
        )
        self.assertEqual(
            blocks,
            (OrderBlock("bullish", 1, 4, 8.5, 9.0, "BOS", 0),),
        )

    def test_bearish_break_uses_last_bullish_body(self):
        blocks = find_order_blocks(
            opens=[12, 10, 9, 8],
            highs=[13, 11, 10, 9],
            lows=[11, 9, 8, 6],
            closes=[12.5, 10.5, 8.5, 6.5],
            events=[StructureBreak("CHoCH", "bearish", 3, 0, 7.0)],
        )
        self.assertEqual(blocks[0].candle_index, 1)
        self.assertEqual((blocks[0].lower, blocks[0].upper), (10.0, 10.5))

    def test_mitigation_requires_close_beyond_far_edge(self):
        bullish = OrderBlock("bullish", 1, 4, 8.5, 9.0, "BOS", 0)
        bearish = OrderBlock("bearish", 1, 4, 10.0, 10.5, "BOS", 0)
        self.assertFalse(is_order_block_mitigated(bullish, 8.5))
        self.assertTrue(is_order_block_mitigated(bullish, 8.49))
        self.assertFalse(is_order_block_mitigated(bearish, 10.5))
        self.assertTrue(is_order_block_mitigated(bearish, 10.51))

    def test_mitigation_is_first_close_after_creation_and_persists(self):
        bullish = OrderBlock("bullish", 1, 2, 8.5, 9.0, "BOS", 0)
        closes = [10.0, 9.5, 12.0, 8.7, 8.4, 9.2]
        self.assertEqual(
            measure_order_block_mitigation(bullish, closes, as_of_index=3),
            OrderBlockMitigation(3, False, None),
        )
        self.assertEqual(
            measure_order_block_mitigation(bullish, closes, as_of_index=4),
            OrderBlockMitigation(4, True, 4),
        )
        self.assertEqual(
            measure_order_block_mitigation(bullish, closes, as_of_index=5),
            OrderBlockMitigation(5, True, 4),
        )

    def test_creation_candle_does_not_mitigate_new_block(self):
        bullish = OrderBlock("bullish", 1, 2, 8.5, 9.0, "BOS", 0)
        self.assertEqual(
            measure_order_block_mitigation(bullish, [10.0, 9.5, 8.0]),
            OrderBlockMitigation(2, False, None),
        )

    def test_mitigation_rejects_invalid_as_of_index(self):
        bullish = OrderBlock("bullish", 1, 2, 8.5, 9.0, "BOS", 0)
        with self.assertRaises(ValueError):
            measure_order_block_mitigation(bullish, [10.0, 9.5, 9.2], as_of_index=3)

    def test_invalid_ohlc_is_rejected(self):
        with self.assertRaises(ValueError):
            find_order_blocks([5], [4], [6], [5], [])

    def test_non_finite_ohlc_is_rejected(self):
        for value in (float("nan"), float("inf"), True, "10"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                find_order_blocks([value], [11], [9], [10], [])

    def test_invalid_event_indices_and_kind_are_rejected(self):
        for event in (
            StructureBreak("BOS", "bullish", True, 0, 10.0),
            StructureBreak("UNKNOWN", "bullish", 1, 0, 10.0),
            StructureBreak("BOS", "bullish", 1, -1, 10.0),
        ):
            with self.subTest(event=event), self.assertRaises(ValueError):
                find_order_blocks([9, 10], [10, 11], [8, 9], [9.5, 10.5], [event])

    def test_mitigation_rejects_non_finite_close_and_fractional_snapshot(self):
        block = OrderBlock("bullish", 1, 1, 8.5, 9.0, "BOS", 0)
        with self.assertRaises(ValueError):
            measure_order_block_mitigation(block, [10.0, 9.5, float("nan")])
        with self.assertRaises(ValueError):
            measure_order_block_mitigation(block, [10.0, 9.5], as_of_index=1.5)


if __name__ == "__main__":
    unittest.main()
