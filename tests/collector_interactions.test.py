import unittest
from pathlib import Path


SOURCE = (Path(__file__).resolve().parents[1] / "collector" / "main.py").read_text(encoding="utf-8")
APP_SOURCE = (Path(__file__).resolve().parents[1] / "collector" / "app.py").read_text(encoding="utf-8")
WORKER_SOURCE = (Path(__file__).resolve().parents[1] / "src" / "index.js").read_text(encoding="utf-8")


class CollectorInteractionTests(unittest.TestCase):
    def test_removed_hover_callback_is_not_called(self):
        self.assertNotIn("close_info_panel_if_left", SOURCE)

    def test_left_and_right_actions_require_pairing(self):
        capture = SOURCE[SOURCE.index("    def capture(self):"):SOURCE.index("    def capture_after_hide", SOURCE.index("    def capture(self):"))]
        info = SOURCE[SOURCE.index("    def toggle_info_panel"):SOURCE.index("    def load_info_panel", SOURCE.index("    def toggle_info_panel"))]
        guard = 'if not self.pair_verified or not self.config.get("deviceToken"):'
        self.assertIn(guard, capture)
        self.assertIn("self.pair()", capture)
        self.assertIn(guard, info)
        self.assertIn("self.pair()", info)

    def test_test_patch_versions_use_test_environment(self):
        self.assertIn('IS_TEST_BUILD = "-test" in APP_VERSION', APP_SOURCE)
        self.assertIn('DEFAULT_API_BASE = "https://test.buyali.xyz" if IS_TEST_BUILD', APP_SOURCE)
        self.assertNotIn('APP_VERSION.endswith("-test")', APP_SOURCE + SOURCE)

    def test_role_summary_receives_and_uses_web_profession(self):
        self.assertIn("charClass: character.charClass || ''", WORKER_SOURCE)
        self.assertIn('character.get("charClass")', SOURCE)
        panel = SOURCE[SOURCE.index("    def show_info_panel"):SOURCE.index("    def close_info_panel")]
        self.assertNotIn('char_class or "未设置"', panel)


if __name__ == "__main__":
    unittest.main()
