import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "collector"))

from app import parse_aether_candidates, parse_currency_candidates


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

    def test_missing_blue_is_not_fabricated_as_zero(self):
        fields, _ = parse_aether_candidates([("285/840", 0.97)])
        self.assertEqual(fields, {"whiteEnergy": 285})

    def test_kina_zero_is_valid(self):
        result = parse_currency_candidates([
            ("72,000", 0.95), ("1,538", 0.96), ("0", 0.98), ("31,146", 0.95)
        ], has_aether=True)
        self.assertEqual(result[0], 0)


if __name__ == "__main__":
    unittest.main()
