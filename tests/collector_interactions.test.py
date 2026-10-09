import unittest
from pathlib import Path
import sys


SOURCE = (Path(__file__).resolve().parents[1] / "collector" / "main.py").read_text(encoding="utf-8")
APP_SOURCE = (Path(__file__).resolve().parents[1] / "collector" / "app.py").read_text(encoding="utf-8")
WORKER_SOURCE = (Path(__file__).resolve().parents[1] / "src" / "index.js").read_text(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "collector"))
from combat_power import format_combat_power


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
        self.assertIn('CONFIG_DIR_NAME = "BuyaliCollector-test" if IS_TEST_BUILD else "BuyaliCollector"', APP_SOURCE)
        self.assertNotIn('APP_VERSION.endswith("-test")', APP_SOURCE + SOURCE)

    def test_role_summary_receives_and_uses_web_profession(self):
        self.assertIn("charClass: character.charClass || ''", WORKER_SOURCE)
        self.assertIn('character.get("charClass")', SOURCE)
        panel = SOURCE[SOURCE.index("    def show_info_panel"):SOURCE.index("    def close_info_panel")]
        self.assertNotIn('char_class or "未设置"', panel)

    def test_role_panel_shows_cache_immediately_then_refreshes(self):
        loader = SOURCE[SOURCE.index("    def load_info_panel"):SOURCE.index("    def show_info_loading")]
        self.assertIn("if self.cached_state:", loader)
        self.assertIn("self.show_info_panel(self.cached_state, checking=True)", loader)
        self.assertIn("self.show_info_loading()", loader)
        self.assertIn("data = self.api.state()", loader)

    def test_role_data_auto_refresh_is_independent_and_change_driven(self):
        self.assertIn("INFO_REFRESH_MS = 2000", SOURCE)
        self.assertIn('self.config.setdefault("infoAutoRefresh", True)', SOURCE)
        self.assertIn('self.config["infoAutoRefresh"] = bool(self.info_auto_refresh_var.get())', SOURCE)
        scheduler = SOURCE[SOURCE.index("    def schedule_info_refresh"):SOURCE.index("    def show_info_panel")]
        self.assertIn("self.info_auto_refresh_var.get()", scheduler)
        self.assertIn("INFO_REFRESH_MS", scheduler)
        finish = SOURCE[SOURCE.index("    def finish_info_load"):SOURCE.index("    def finish_info_error")]
        self.assertIn("changed = data != self.cached_state", finish)
        self.assertIn("if not self.valid_role_state(data):", finish)
        self.assertLess(finish.index("valid_role_state"), finish.index("self.cache_state(data)"))

    def test_role_panel_uses_confirmed_web_fields_without_transient_header_status(self):
        panel = SOURCE[SOURCE.index("    def show_info_panel"):SOURCE.index("    def close_info_panel")]
        self.assertIn('text="道具等级"', panel)
        self.assertIn('character.get("itemLevel")', panel)
        self.assertIn('character.get("whiteEnergyDisplay", character.get("whiteEnergy", 0))', panel)
        self.assertIn('character.get("blueEnergy", 0)', panel)
        self.assertNotIn('刚刚同步', panel)
        self.assertNotIn('自动更新 · 检查中', panel)
        self.assertIn('"每 2 秒检查 · 仅变化时重绘"', panel)

    def test_role_panel_keeps_profession_visual_and_removes_duplicate_name(self):
        panel = SOURCE[SOURCE.index("    def show_info_panel"):SOURCE.index("    def close_info_panel")]
        self.assertIn('assets/classes/{char_class}.webp', panel)
        self.assertNotIn("CLASS_LABELS.get", panel)
        self.assertIn('text="奥德"', panel)
        self.assertNotIn('奥德（白奥德 + 蓝奥德）', panel)

    def test_role_panel_uses_same_cached_character_as_control_panel(self):
        self.assertIn('def current_character_name(self):', SOURCE)
        self.assertIn('self.config.get("windowCharacters", {}).get(str(self.game.hwnd))', SOURCE)
        panel = SOURCE[SOURCE.index("    def show_info_panel"):SOURCE.index("    def close_info_panel")]
        self.assertIn('current = self.current_character_name()', panel)
        self.assertIn('normalized_character_name(character_name)', panel)

    def test_role_panel_titles_and_energy_alignment_are_explicit(self):
        panel = SOURCE[SOURCE.index("    def show_info_panel"):SOURCE.index("    def close_info_panel")]
        self.assertIn('heading_font = (FONT, 9, "bold")', panel)
        self.assertIn('text="奥德", bg=PANEL_2, fg=TEXT', panel)
        self.assertIn('text="+", width=2', panel)
        self.assertIn('anchor="w").grid(row=0, column=0, sticky="ew")', panel)
        self.assertIn('anchor="w").grid(row=0, column=2, sticky="ew")', panel)

    def test_info_settings_use_source_switch_assets(self):
        self.assertIn('assets/controls/switch-{state}-source.png', SOURCE)
        settings = SOURCE[SOURCE.index("    def toggle_info_settings"):SOURCE.index("    def show_control_panel")]
        self.assertIn('image=switch_photos[state]', settings)
        self.assertNotIn('text="开启"', settings)

    def test_capture_starts_quickly_and_fetches_state_in_parallel(self):
        capture = SOURCE[SOURCE.index("    def capture(self):"):SOURCE.index("    def prepare_result")]
        self.assertIn("self.root.after(20", capture)
        self.assertIn("threading.Thread(target=fetch_latest_state", capture)
        self.assertIn("state_ready.wait", capture)
        self.assertIn("self.root.after(40000", capture)
        self.assertIn("state_ready.wait(26)", capture)

    def test_capture_uses_recent_state_cache_during_slow_refresh(self):
        worker = SOURCE[SOURCE.index("    def capture_worker"):SOURCE.index("    def prepare_result")]
        self.assertIn('if cached_state:', worker)
        self.assertIn('state_ready.wait(0.25)', worker)
        self.assertIn('state_result.get("data", cached_state)', worker)

    def test_state_cache_survives_restart_and_diagnostics_are_accessible(self):
        self.assertIn('self.config.get("cachedState")', SOURCE)
        self.assertIn('self.config["cachedState"] = data', SOURCE)
        self.assertIn('"打开诊断日志"', SOURCE)
        self.assertIn('RotatingFileHandler', APP_SOURCE)

    def test_apply_timeout_is_reconciled_by_request_id(self):
        self.assertIn('payload.setdefault("requestId", str(uuid.uuid4()))', APP_SOURCE)
        self.assertIn('"request-status?requestId="', APP_SOURCE)
        self.assertIn("route === 'request-status'", WORKER_SOURCE)

    def test_only_read_only_capture_state_get_is_retried(self):
        request = APP_SOURCE[APP_SOURCE.index("    def request(self, method: str, route: str, payload"):APP_SOURCE.index("    def redeem(self, code: str)")]
        self.assertIn('retries = 1 if method == "GET" and route == "state" else 0', request)
        self.assertIn("exc.code in (502, 503, 504) and attempt < retries", request)
        self.assertIn("except (URLError, TimeoutError, socket.timeout)", request)
        self.assertIn("已自动重试一次", request)

    def test_live_title_skips_character_ocr(self):
        worker = SOURCE[SOURCE.index("    def capture_worker"):SOURCE.index("    def prepare_result")]
        self.assertIn('if not hint or getattr(game, "character_from_cache", False):', worker)
        self.assertIn("hint = recognize_character_text(image)", worker)

    def test_precision_lens_assets_drive_all_capture_states(self):
        self.assertIn('self.set_capture_icon("recognizing")', SOURCE)
        self.assertIn('self.set_capture_icon("ready")', SOURCE)
        self.assertIn('self.set_capture_icon("idle")', SOURCE)
        self.assertNotIn('text="📷"', SOURCE)
        self.assertNotIn('text="◌"', SOURCE)

    def test_confirmation_ui_shows_signed_delta_without_changing_payload(self):
        confirm = SOURCE[SOURCE.index("    def confirm_dialog"):SOURCE.index("    def rebind_for_capture")]
        self.assertIn('make_dialog("确认采集内容", 620', confirm)
        self.assertIn('("数据项", "变更前", "变更后", "变化")', confirm)
        self.assertIn("format_change(key, before, after, before_unit, after_unit)", confirm)
        self.assertNotIn('values=("K", "M")', confirm)
        self.assertIn('entry_text = format_combat_power(value, combat_unit["value"])', confirm)
        self.assertIn('value.replace(",", "").strip().rstrip("KkMm")', confirm)
        self.assertIn('text = format_combat_delta(magnitude)', SOURCE)
        self.assertIn('edited["combatPowerUnit"] = combat_unit["value"]', confirm)
        self.assertNotIn("可信度", confirm)
        self.assertIn('"fields": edited', confirm)
        self.assertIn("args=(payload, edited, game.character, serial)", confirm)

    def test_signed_delta_supports_increase_decrease_and_no_change(self):
        helper = SOURCE[SOURCE.index("def format_change"):SOURCE.index("class CollectorApp")]
        self.assertIn('sign = "+" if delta > 0 else "-"', helper)
        self.assertIn('color = GREEN if delta > 0 else RED', helper)
        self.assertIn('return "0", MUTED', helper)

    def test_m_value_rendered_for_confirmation_parses_as_float(self):
        confirm = SOURCE[SOURCE.index("    def confirm_dialog"):SOURCE.index("    def rebind_for_capture")]
        self.assertIn('clean = value.replace(",", "").strip().rstrip("KkMm")', confirm)
        rendered = format_combat_power(1.036, "M")
        self.assertEqual(rendered, "1.036M")
        self.assertEqual(round(float(rendered.rstrip("KkMm")), 3), 1.036)

    def test_update_version_comparison_keeps_hotfix_component(self):
        helper = SOURCE[SOURCE.index("    def version_tuple"):SOURCE.index("    def check_for_updates")]
        self.assertIn("for item in numbers", helper)
        self.assertNotIn("numbers[:3]", helper)


if __name__ == "__main__":
    unittest.main()
