import unittest

from app.smc.breaks import StructureBreak
from app.smc.order_blocks import OrderBlock, find_order_blocks, is_order_block_mitigated


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

    def test_invalid_ohlc_is_rejected(self):
        with self.assertRaises(ValueError):
            find_order_blocks([5], [4], [6], [5], [])


if __name__ == "__main__":
    unittest.main()
