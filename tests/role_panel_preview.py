"""Local visual-QA harness for the V1.3.3 role panel.

It uses the real test-page values supplied during design review and never
connects to an API or writes collector configuration.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from types import SimpleNamespace

from PIL import ImageGrab


COLLECTOR_DIR = Path(__file__).resolve().parents[1] / "collector"
sys.path.insert(0, str(COLLECTOR_DIR))

from main import CollectorApp  # noqa: E402


PREVIEW_STATE = {
    "accounts": [{
        "id": "preview-account-1",
        "name": "账号1",
        "characters": [
            {"name": "飒雷雅", "charClass": "ranger", "itemLevel": 5885, "whiteEnergy": 840, "blueEnergy": 790},
            {"name": "唐三", "charClass": "cleric", "itemLevel": 4531, "whiteEnergy": 840, "blueEnergy": 205},
            {"name": "璎蝶", "charClass": "chanter", "itemLevel": 3291, "whiteEnergy": 840, "blueEnergy": 165},
            {"name": "迪希雅", "charClass": "chanter", "itemLevel": 4591, "whiteEnergy": 840, "blueEnergy": 15},
            {"name": "方心观", "charClass": "spirit", "itemLevel": 4092, "whiteEnergy": 840, "blueEnergy": 5},
            {"name": "蒋劲夫", "charClass": "fighter", "itemLevel": 4546, "whiteEnergy": 840, "blueEnergy": 0},
            {"name": "希格雯", "charClass": "cleric", "itemLevel": 1016, "whiteEnergy": 840, "blueEnergy": 0},
        ],
    }],
}


def main():
    CollectorApp._build_tray = lambda self: setattr(self, "tray", None)
    CollectorApp.follow_game = lambda self: None
    CollectorApp.verify_pairing = lambda self: None
    CollectorApp.pair = lambda self: None
    CollectorApp.check_for_updates = lambda self: None
    app = CollectorApp()
    app.pair_verified = True
    app.config["deviceToken"] = "preview-only"
    app.same_account_var.set(True)
    app.info_auto_refresh_var.set(True)
    app.cached_state = PREVIEW_STATE
    app.cached_state_at = time.time()
    app.game = SimpleNamespace(character="飒雷雅")
    app.root.withdraw()
    app.overlay.withdraw()
    app.show_info_panel(PREVIEW_STATE)
    app.toggle_info_settings()
    if "--interactive" in sys.argv:
        app.root.update_idletasks()
        print({"info": app.info_panel.geometry(), "settings": app.info_settings_panel.geometry()})
        app.root.mainloop()
        return
    def capture_preview():
        app.root.update_idletasks()
        windows = (app.info_panel, app.info_settings_panel)
        left = min(window.winfo_rootx() for window in windows)
        top = min(window.winfo_rooty() for window in windows)
        right = max(window.winfo_rootx() + window.winfo_width() for window in windows)
        bottom = max(window.winfo_rooty() + window.winfo_height() for window in windows)
        print({"info": app.info_panel.geometry(), "settings": app.info_settings_panel.geometry(), "bbox": (left, top, right, bottom)})
        output = Path(__file__).resolve().parent / "artifacts" / "role-panel-preview.png"
        output.parent.mkdir(parents=True, exist_ok=True)
        try:
            ImageGrab.grab(bbox=(left, top, right, bottom), all_screens=True).save(output)
        finally:
            app.root.destroy()
    app.root.after(700, capture_preview)
    app.root.mainloop()


if __name__ == "__main__":
    main()
