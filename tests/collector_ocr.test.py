import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "collector"))

from app import has_truncated_currency_candidate, parse_aether_candidates, parse_currency_candidates, recognize


class CollectorParsingTests(unittest.TestCase):
    def test_blue_zero_is_valid(self):
        fields, _ = parse_aether_candidates([("285(+0)/840", 0.96)])
        self.assertEqual(fields, {"whiteEnergy": 285, "blueEnergy": 0})

    def test_white_and_blue_zero_are_valid(self):
        fields, _ = parse_aether_candidates([("0(+0)/840", 0.94)])
        self.assertEqual(fields, {"whiteEnergy": 0, "blueEnergy": 0})

    def test_split_aether_lines_are_joined(self):
        fields, _ = parse_aether_candidates([("285", 0.93), ("(+1,140)", 0.91), ("/840", 0.96)])
        self.assertEqual(fields, {"whiteEnergy": 285, "blueEnergy": 1140})

    def test_plain_aether_counter_means_blue_zero(self):
        fields, _ = parse_aether_candidates([("285/840", 0.97)])
        self.assertEqual(fields, {"whiteEnergy": 285, "blueEnergy": 0})

    @patch("app.rapid_read")
    def test_capture_pipeline_preserves_blue_zero_for_web_update(self, rapid_read):
        rapid_read.side_effect = [
            [("45/840", 0.99), ("0", 0.99), ("338", 0.99),
             ("93,196,241", 0.99), ("91,925,241", 0.99)],
            [],
        ]
        fields, _ = recognize(Image.new("RGB", (1920, 1080), "black"))
        self.assertEqual(fields["whiteEnergy"], 45)
        self.assertIn("blueEnergy", fields)
        self.assertEqual(fields["blueEnergy"], 0)

    def test_kina_zero_is_valid(self):
        result = parse_currency_candidates([
            ("72,000", 0.95), ("1,538", 0.96), ("0", 0.98), ("31,146", 0.95)
        ], has_aether=True)
        self.assertEqual(result[0], 0)

    def test_normal_hud_kina_is_first_of_three_formatted_currencies(self):
        result = parse_currency_candidates([
            ("190,418,686", 0.99),
            ("167,517,846", 0.99),
            ("13,706,005", 0.99),
        ], has_aether=False)
        self.assertEqual(result[0], 190_418_686)

    def test_normal_hud_skips_small_formatted_purple_currency(self):
        result = parse_currency_candidates([
            ("3,338", 0.99),
            ("433,589,356", 0.99),
        ], has_aether=False)
        self.assertEqual(result[0], 433_589_356)

    def test_normal_hud_skips_purple_currency_when_all_three_are_visible(self):
        result = parse_currency_candidates([
            ("3,338", 0.99),
            ("433,589,356", 0.99),
            ("433,589,356", 0.99),
        ], has_aether=False)
        self.assertEqual(result[0], 433_589_356)

    def test_normal_hud_keeps_regular_two_large_currency_order(self):
        result = parse_currency_candidates([
            ("190,418,686", 0.99),
            ("167,517,846", 0.99),
        ], has_aether=False)
        self.assertEqual(result[0], 190_418_686)

    def test_truncated_currency_group_requests_scale_fallback(self):
        self.assertTrue(has_truncated_currency_candidate([
            ("3,338", 0.99),
            ("438,589,36", 0.84),
            ("433,589,356", 0.85),
        ]))
        self.assertFalse(has_truncated_currency_candidate([
            ("3,338", 0.99),
            ("438,589,356", 0.87),
            ("433,589,356", 0.84),
        ]))

    @patch("app.rapid_read")
    def test_capture_rechecks_truncated_kina_at_native_scale(self, rapid_read):
        rapid_read.side_effect = [
            [("3,338", 0.99), ("438,589,36", 0.84), ("433,589,356", 0.85)],
            [("3,338", 0.99), ("438,589,356", 0.87), ("433,589,356", 0.84)],
            [],
        ]
        fields, _ = recognize(Image.new("RGB", (3840, 2160), "black"))
        self.assertEqual(fields["kina"], 438_589_356)


if __name__ == "__main__":
    unittest.main()
