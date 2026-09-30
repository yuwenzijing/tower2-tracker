import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "collector"))

from combat_power import combat_power_delta, format_combat_delta, format_combat_power, parse_combat_power, power_to_k


class CombatPowerUnitTests(unittest.TestCase):
    def test_m_value_preserves_unit_and_three_decimal_places(self):
        self.assertEqual(parse_combat_power("1.023M"), (1.023, "M"))

    def test_k_value_preserves_unit_and_thousands_separator(self):
        self.assertEqual(parse_combat_power("1,023.5K"), (1023.5, "K"))

    def test_item_level_without_unit_is_not_combat_power(self):
        self.assertIsNone(parse_combat_power("4,531"))

    def test_cross_unit_comparison_uses_same_k_scale(self):
        self.assertEqual(power_to_k(1.023, "M"), power_to_k(1023, "K"))
        self.assertEqual((power_to_k(1.023, "M") - power_to_k(999, "K")) / 1000, 0.024)

    def test_format_keeps_the_selected_unit(self):
        self.assertEqual(format_combat_power(1.023, "M"), "1.023M")
        self.assertEqual(format_combat_power(1023, "K"), "1,023K")

    def test_cross_unit_delta_does_not_round_small_change_to_zero(self):
        delta = combat_power_delta(1023.4, "K", 1.023, "M")
        self.assertEqual(format_combat_delta(delta, "M"), "0.4K")
        self.assertEqual(combat_power_delta(999.9, "K", 1.0, "M"), 0.1)


if __name__ == "__main__":
    unittest.main()
