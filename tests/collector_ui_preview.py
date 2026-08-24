"""Offline native UI preview for the V1.3.3 test collector.

Never connects to an API and never writes configuration. Usage:
  python tests/collector_ui_preview.py control
  python tests/collector_ui_preview.py confirm
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

from PIL import ImageGrab


COLLECTOR_DIR = Path(__file__).resolve().parents[1] / "collector"
sys.path.insert(0, str(COLLECTOR_DIR))
sys.modules.setdefault("pystray", SimpleNamespace())

from main import CollectorApp  # noqa: E402


def build_app():
    CollectorApp._build_tray = lambda self: setattr(self, "tray", None)
    CollectorApp.follow_game = lambda self: None
    CollectorApp.verify_pairing = lambda self: None
    CollectorApp.pair = lambda self: None
    CollectorApp.check_for_updates = lambda self: None
    app = CollectorApp()
    app.pair_verified = True
    app.config["deviceToken"] = "preview-only"
    app.game = SimpleNamespace(hwnd=1, title="AION2", character="蒋劲夫", rect=(0, 0, 1920, 1080))
    app.overlay.withdraw()
    return app


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "control"
    app = build_app()
    if mode == "confirm":
        app.root.withdraw()
        account = {"id": "account-1", "name": "账号1"}
        character = {
            "id": "character-1", "name": "蒋劲夫", "kina": 167_517_846,
            "itemLevel": 4531, "combatPower": 385.5,
        }
        fields = {"kina": 190_418_686, "itemLevel": 4546, "combatPower": 416.4}
        scores = {key: 99 for key in fields}
        app.confirm_dialog(app.game, (account, character), fields, scores, app.capture_serial, {"accounts": []})
        window = next(child for child in app.overlay.winfo_children() if isinstance(child, __import__("tkinter").Toplevel) and child.winfo_exists())
    else:
        app.root.deiconify()
        app.connection_label.config(text="已配对", fg="#42e6a4")
        app.game_label.config(text="已连接", fg="#42e6a4")
        app.character_label.config(text="蒋劲夫", fg="#e8f1ff")
        app.position_label.config(text="位置 969, 1921 · 缓存角色信息可立即打开", fg="#42e6a4")
        app.update_status_label.config(text="已是最新版本", fg="#42e6a4")
        window = app.root

    def capture():
        app.root.update_idletasks()
        left, top = window.winfo_rootx(), window.winfo_rooty()
        right, bottom = left + window.winfo_width(), top + window.winfo_height()
        output = Path(__file__).resolve().parent / "artifacts" / f"collector-{mode}-preview.png"
        output.parent.mkdir(parents=True, exist_ok=True)
        try:
            ImageGrab.grab(bbox=(left, top, right, bottom), all_screens=True).save(output)
            print({"mode": mode, "geometry": window.geometry(), "output": str(output)})
        finally:
            app.root.destroy()

    app.root.after(700, capture)
    app.root.mainloop()


if __name__ == "__main__":
    main()
