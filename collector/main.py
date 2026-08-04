from __future__ import annotations

import ctypes
import ctypes.wintypes
import hashlib
import os
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk
import pystray
from PIL import Image, ImageDraw
from pathlib import Path

from app import (
    API_BASE,
    APP_NAME,
    APP_VERSION,
    FIELD_LABELS,
    ApiClient,
    ApiError,
    GameWindow,
    ImageGrab,
    accounts_and_characters,
    configure_ocr,
    find_active_game,
    load_config,
    match_character_hint,
    recognize,
    recognize_character_text,
    save_config,
    user32,
    window_title,
)


BG = "#07111f"
PANEL = "#0d1a2d"
PANEL_2 = "#101f35"
BORDER = "#1d3554"
TEXT = "#e8f1ff"
MUTED = "#91a4bd"
CYAN = "#31d7ed"
GREEN = "#42e6a4"
PURPLE = "#5668d8"
PURPLE_HOVER = "#687bec"
RED = "#ff6b78"
AMBER = "#f4b95f"
FONT = "Microsoft YaHei UI"

HWND_TOPMOST = -1
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
GWL_EXSTYLE = -20
GWLP_HWNDPARENT = -8
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000
OVERLAY_WIDTH = 168
OVERLAY_HEIGHT = 52

user32.GetAncestor.argtypes = [ctypes.wintypes.HWND, ctypes.c_uint]
user32.GetAncestor.restype = ctypes.wintypes.HWND
user32.SetWindowLongPtrW.argtypes = [ctypes.wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t


def relaunch_from_ascii_runtime() -> bool:
    """Tk/Tcl cannot initialize reliably from non-ASCII PyInstaller paths.

    Keep the package portable: cache only the small UI executable under the
    user's ASCII LocalAppData path, while OCR resources remain beside the
    original portable package.
    """
    if not getattr(sys, "frozen", False):
        return False
    executable = Path(sys.executable).resolve()
    if all(ord(char) < 128 for char in str(executable)):
        return False
    cache = Path(os.environ.get("TEMP", os.environ.get("TMP", Path.home()))) / "BuyaliCollector" / "bin"
    cache.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(executable.read_bytes()).hexdigest()[:12]
    target_dir = cache / f"ui-{digest}"
    target = target_dir / executable.name
    if not target.exists():
        shutil.copytree(executable.parent, target_dir, dirs_exist_ok=True)
    portable_root = executable.parent
    if not (portable_root / "runtime").exists() and (portable_root.parent / "runtime").exists():
        portable_root = portable_root.parent
    environment = os.environ.copy()
    environment["BUYALI_PORTABLE_ROOT"] = str(portable_root)
    subprocess.Popen([str(target)], cwd=str(cache), env=environment)
    return True


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_ulong), ("rcMonitor", RECT), ("rcWork", RECT), ("dwFlags", ctypes.c_ulong)]


def work_area_for_point(x: int, y: int):
    point = ctypes.wintypes.POINT(x, y)
    monitor = user32.MonitorFromPoint(point, 2)
    info = MONITORINFO()
    info.cbSize = ctypes.sizeof(info)
    if monitor and user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        return info.rcWork.left, info.rcWork.top, info.rcWork.right, info.rcWork.bottom
    return 0, 0, user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


def button(parent, text, command, primary=False, danger=False, width=12):
    bg = PURPLE if primary else ("#3b1e2a" if danger else PANEL_2)
    fg = RED if danger else TEXT
    active = PURPLE_HOVER if primary else ("#512534" if danger else BORDER)
    return tk.Button(
        parent, text=text, command=command, width=width, bg=bg, fg=fg,
        activebackground=active, activeforeground=TEXT, relief="flat", bd=0,
        font=(FONT, 10, "bold"), cursor="hand2", padx=10, pady=7,
    )


class CollectorApp:
    def __init__(self):
        configure_ocr()
        self.config = load_config()
        self.api = ApiClient(self.config)
        self.game: GameWindow | None = None
        self.busy = False
        self.capture_serial = 0
        self.capture_phase = "idle"
        self.pair_verified = False
        self.pair_dialog_open = False
        self.overlay_user_hidden = False
        self.drag_origin = None
        self.offset = self.config.get("offset", [20, 180])
        if not isinstance(self.offset, list) or len(self.offset) != 2:
            self.offset = [20, 180]

        # A normal root window owns the taskbar entry. It never participates in
        # screenshots or overlay visibility, so the process remains manageable.
        self.root = tk.Tk()
        self.root.title(f"{APP_NAME} {APP_VERSION}")
        self.root.geometry("520x455")
        self.root.minsize(500, 430)
        self.root.configure(bg=BG)
        self.root.protocol("WM_DELETE_WINDOW", self.root.iconify)
        self._build_control_panel()
        self._build_tray()

        # The overlay is an independent native top-level window.
        # One Tcl event loop owns every UI window. Native ownership is removed
        # below so minimizing the taskbar window does not hide the overlay.
        self.overlay = tk.Toplevel(self.root)
        self.overlay.overrideredirect(True)
        self.overlay.attributes("-topmost", True)
        self.overlay.configure(bg=CYAN)
        self.overlay.geometry(f"{OVERLAY_WIDTH}x{OVERLAY_HEIGHT}+20+180")
        self.capture_button = tk.Button(
            self.overlay, text="◎  采集数据", command=self.capture, bg=PANEL,
            fg=TEXT, activebackground=PANEL_2, activeforeground=CYAN,
            relief="flat", bd=0, font=(FONT, 11, "bold"), cursor="hand2",
        )
        self.capture_button.pack(fill="both", expand=True, padx=2, pady=2)
        for widget in (self.overlay, self.capture_button):
            widget.bind("<ButtonPress-1>", self.drag_start, add="+")
            widget.bind("<B1-Motion>", self.drag_move, add="+")
            widget.bind("<ButtonRelease-1>", self.drag_end, add="+")
            widget.bind("<Button-3>", self.show_control_panel)

        self.root.update_idletasks()
        self.overlay.update_idletasks()
        control_hwnd = user32.GetAncestor(self.root.winfo_id(), 2)
        overlay_hwnd = user32.GetAncestor(self.overlay.winfo_id(), 2)
        # Explicit native ownership/styles: the control window owns the taskbar
        # entry; the overlay is an ownerless tool window and survives minimize.
        user32.SetWindowLongPtrW(overlay_hwnd, GWLP_HWNDPARENT, 0)
        control_style = user32.GetWindowLongW(control_hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(control_hwnd, GWL_EXSTYLE, (control_style | WS_EX_APPWINDOW) & ~WS_EX_TOOLWINDOW)
        overlay_style = user32.GetWindowLongW(overlay_hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(overlay_hwnd, GWL_EXSTYLE, (overlay_style | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW)

        self.root.after(250, self.follow_game)
        if self.config.get("deviceToken"):
            self.root.after(600, self.verify_pairing)
        else:
            self.root.after(600, self.pair)

    def _build_control_panel(self):
        header = tk.Frame(self.root, bg=BG)
        header.pack(fill="x", padx=24, pady=(22, 12))
        tk.Label(header, text="BUYALI", bg=BG, fg=CYAN, font=(FONT, 10, "bold")).pack(anchor="w")
        tk.Label(header, text="数据采集助手", bg=BG, fg=TEXT, font=(FONT, 18, "bold")).pack(anchor="w", pady=(2, 0))
        tk.Label(header, text=f"正式版 · {APP_VERSION}", bg=BG, fg=MUTED, font=(FONT, 9)).pack(anchor="w", pady=(4, 0))

        card = tk.Frame(self.root, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        card.pack(fill="x", padx=24, pady=8)
        self.connection_label = tk.Label(card, text="● 检查连接中", bg=PANEL, fg=AMBER, font=(FONT, 10, "bold"), anchor="w")
        self.connection_label.pack(fill="x", padx=16, pady=(14, 5))
        self.game_label = tk.Label(card, text="游戏窗口：等待检测", bg=PANEL, fg=MUTED, font=(FONT, 10), anchor="w")
        self.game_label.pack(fill="x", padx=16, pady=5)
        self.character_label = tk.Label(card, text="当前角色：等待检测", bg=PANEL, fg=MUTED, font=(FONT, 10), anchor="w")
        self.character_label.pack(fill="x", padx=16, pady=(5, 14))
        self.position_label = tk.Label(card, text="浮窗位置：等待游戏窗口", bg=PANEL, fg=MUTED, font=(FONT, 9), anchor="w")
        self.position_label.pack(fill="x", padx=16, pady=(0, 14))

        actions = tk.Frame(self.root, bg=BG)
        actions.pack(fill="x", padx=22, pady=(12, 4))
        actions.columnconfigure(0, weight=1, uniform="action")
        actions.columnconfigure(1, weight=1, uniform="action")
        self.overlay_toggle = button(actions, "显示 / 隐藏浮窗", self.toggle_overlay, width=16)
        self.overlay_toggle.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        button(actions, "重新绑定", self.rebind, width=16).grid(row=0, column=1, sticky="ew", padx=5, pady=5)
        self.cancel_button = button(actions, "取消当前采集", self.cancel_capture, danger=True, width=16)
        self.cancel_button.grid(row=1, column=0, columnspan=2, sticky="ew", padx=5, pady=5)
        tk.Label(self.root, text="更多操作：任务栏右下角 BUYALI 图标右键菜单", bg=BG, fg=MUTED, font=(FONT, 9)).pack(pady=(2, 8))

    def _build_tray(self):
        image = Image.new("RGBA", (64, 64), BG)
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((5, 5, 59, 59), radius=14, fill=PANEL, outline=CYAN, width=4)
        draw.ellipse((22, 18, 42, 38), fill=CYAN)
        draw.rectangle((29, 35, 35, 52), fill=CYAN)
        call = lambda fn: (lambda _icon=None, _item=None: self.root.after(0, fn))
        menu = pystray.Menu(
            pystray.MenuItem("显示控制面板", call(self.show_control_panel), default=True),
            pystray.MenuItem("显示 / 隐藏浮窗", call(self.toggle_overlay)),
            pystray.MenuItem("取消当前采集", call(self.cancel_capture)),
            pystray.MenuItem("重置浮窗", call(self.reset_overlay_position)),
            pystray.MenuItem("重新绑定", call(self.rebind)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出", call(self.quit)),
        )
        self.tray = pystray.Icon("BuyaliCollector", image, "Buyali 数据采集助手", menu)
        self.tray.run_detached()

    def show_control_panel(self, _event=None):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def show_overlay(self):
        self.overlay_user_hidden = False
        self.overlay.deiconify()
        self.force_overlay_topmost()
        self.overlay_toggle.config(text="显示 / 隐藏浮窗")

    def toggle_overlay(self):
        if self.overlay.winfo_viewable():
            self.overlay_user_hidden = True
            self.overlay.withdraw()
            self.overlay_toggle.config(text="显示浮窗")
        else:
            self.show_overlay()

    def force_overlay_topmost(self):
        self.overlay.update_idletasks()
        hwnd = user32.GetAncestor(self.overlay.winfo_id(), 2)
        self.overlay.attributes("-topmost", True)
        self.overlay.lift()
        user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE | SWP_SHOWWINDOW)

    def safe_overlay_position(self, game, reset=False):
        left, top, right, bottom = game.rect
        width, height = right - left, bottom - top
        default_x = left + 24
        default_y = top + min(180, max(24, height - 70))
        x = left + int(self.offset[0])
        y = top + int(self.offset[1])
        valid = (
            not reset
            and left <= x <= right - OVERLAY_WIDTH
            and top <= y <= bottom - OVERLAY_HEIGHT
        )
        if not valid:
            x, y = default_x, default_y
        x = min(max(x, left + 8), max(left + 8, right - OVERLAY_WIDTH - 8))
        y = min(max(y, top + 8), max(top + 8, bottom - OVERLAY_HEIGHT - 8))
        self.offset = [x - left, y - top]
        self.config["offset"] = self.offset
        return x, y

    def reset_overlay_position(self):
        game = self.current_game()
        if not game:
            self.notice("无法重置浮窗", "当前没有检测到 AION2 游戏窗口。", "error")
            return
        self.game = game
        x, y = self.safe_overlay_position(game, reset=True)
        self.overlay.geometry(f"{OVERLAY_WIDTH}x{OVERLAY_HEIGHT}{x:+d}{y:+d}")
        save_config(self.config)
        self.show_overlay()
        self.position_label.config(text=f"浮窗位置：{x}, {y}", fg=GREEN)

    def drag_start(self, event):
        self.drag_origin = (event.x_root, event.y_root, self.overlay.winfo_x(), self.overlay.winfo_y())

    def drag_move(self, event):
        if not self.drag_origin:
            return
        x0, y0, wx, wy = self.drag_origin
        new_x = wx + event.x_root - x0
        new_y = wy + event.y_root - y0
        self.overlay.geometry(f"{new_x:+d}{new_y:+d}")

    def drag_end(self, _event):
        self.drag_origin = None
        if self.game:
            self.offset = [self.overlay.winfo_x() - self.game.rect[0], self.overlay.winfo_y() - self.game.rect[1]]
            self.config["offset"] = self.offset
            save_config(self.config)

    def current_game(self):
        detected = find_active_game()
        if detected:
            return detected
        if self.game and user32.IsWindow(self.game.hwnd):
            if user32.IsIconic(self.game.hwnd):
                return self.game
            title = window_title(self.game.hwnd)
            rect = ctypes.wintypes.RECT()
            if user32.GetWindowRect(self.game.hwnd, ctypes.byref(rect)):
                from app import parse_character
                return GameWindow(self.game.hwnd, title, parse_character(title), (rect.left, rect.top, rect.right, rect.bottom))
        return None

    def follow_game(self):
        if not self.busy and not self.drag_origin:
            game = self.current_game()
            if game:
                changed_hwnd = not self.game or self.game.hwnd != game.hwnd
                self.game = game
                old_offset = list(self.offset)
                x, y = self.safe_overlay_position(game)
                self.overlay.geometry(f"{OVERLAY_WIDTH}x{OVERLAY_HEIGHT}{x:+d}{y:+d}")
                if old_offset != self.offset:
                    save_config(self.config)
                self.game_label.config(text="游戏窗口：已连接", fg=GREEN)
                role = game.character or self.config.get("windowCharacters", {}).get(str(game.hwnd))
                self.character_label.config(text=f"当前角色：{role or '截图时识别'}", fg=TEXT if role else MUTED)
                self.position_label.config(text=f"浮窗位置：{x}, {y}", fg=GREEN)
                if not self.overlay_user_hidden and not self.overlay.winfo_viewable():
                    self.overlay.deiconify()
                if changed_hwnd:
                    self.force_overlay_topmost()
            else:
                self.game_label.config(text="游戏窗口：等待 AION2", fg=AMBER)
                self.character_label.config(text="当前角色：等待检测", fg=MUTED)
                self.position_label.config(text="浮窗位置：等待游戏窗口", fg=MUTED)
            paired = self.pair_verified and bool(self.config.get("deviceToken"))
            checking = bool(self.config.get("deviceToken")) and not self.pair_verified
            status = "● 已配对" if paired else ("● 正在验证配对" if checking else "● 尚未配对")
            self.connection_label.config(text=status, fg=GREEN if paired else AMBER)
            if self.overlay.winfo_viewable() and not self.overlay_user_hidden:
                self.force_overlay_topmost()
        self.root.after(350, self.follow_game)

    def dialog_position(self, width, height):
        self.overlay.update_idletasks()
        ox, oy = self.overlay.winfo_x(), self.overlay.winfo_y()
        ow, oh = self.overlay.winfo_width(), self.overlay.winfo_height()
        left, top, right, bottom = work_area_for_point(ox + ow // 2, oy + oh // 2)
        x = min(max(ox, left + 8), right - width - 8)
        below = oy + oh + 10
        y = below if below + height <= bottom - 8 else oy - height - 10
        y = min(max(y, top + 8), bottom - height - 8)
        return x, y

    def make_dialog(self, title, width, height):
        if not self.overlay.winfo_viewable():
            self.overlay.deiconify()
            self.force_overlay_topmost()
        dialog = tk.Toplevel(self.overlay)
        dialog.overrideredirect(True)
        dialog.attributes("-topmost", True)
        dialog.configure(bg=BORDER)
        x, y = self.dialog_position(width, height)
        dialog.geometry(f"{width}x{height}{x:+d}{y:+d}")
        shell = tk.Frame(dialog, bg=BG)
        shell.pack(fill="both", expand=True, padx=1, pady=1)
        head = tk.Frame(shell, bg=PANEL)
        head.pack(fill="x")
        tk.Label(head, text=title, bg=PANEL, fg=TEXT, font=(FONT, 12, "bold"), anchor="w").pack(fill="x", padx=18, pady=13)
        body = tk.Frame(shell, bg=BG)
        body.pack(fill="both", expand=True, padx=18, pady=14)
        dialog.update_idletasks()
        hwnd = user32.GetAncestor(dialog.winfo_id(), 2)
        user32.SetWindowLongPtrW(hwnd, GWLP_HWNDPARENT, 0)
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, (style | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW)
        user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE | SWP_SHOWWINDOW)
        return dialog, body

    def notice(self, title, message, kind="info", on_close=None):
        lines = max(1, (len(str(message)) + 25) // 26)
        dialog, body = self.make_dialog(title, 440, 220 + max(0, lines - 1) * 28)
        color = GREEN if kind == "success" else (RED if kind == "error" else CYAN)
        tk.Label(body, text=message, bg=BG, fg=color, font=(FONT, 11), justify="left", wraplength=340).pack(fill="x", pady=(8, 20))
        def close():
            dialog.destroy()
            if on_close: on_close()
        button(body, "确定", close, primary=True, width=10).pack(fill="x")
        dialog.protocol("WM_DELETE_WINDOW", close)
        return dialog

    def ask_text(self, title, prompt, initial="", secret=False):
        result = []
        # Reserve a fixed footer area for both actions.  At 125%-200% Windows
        # scaling Tk fonts grow more than the previous fixed-height dialog,
        # which clipped the confirmation buttons below the input field.
        prompt_lines = max(1, (len(prompt) + 22) // 23 + prompt.count("\n"))
        dialog_height = max(300, 238 + max(0, prompt_lines - 1) * 24)
        dialog, body = self.make_dialog(title, 460, dialog_height)
        tk.Label(body, text=prompt, bg=BG, fg=MUTED, font=(FONT, 10), justify="left", wraplength=365).pack(fill="x", pady=(2, 12))
        value = tk.StringVar(value=initial)
        entry = tk.Entry(body, textvariable=value, show="•" if secret else "", bg=PANEL_2, fg=TEXT, insertbackground=TEXT, relief="flat", font=(FONT, 11))
        entry.pack(fill="x", ipady=8)
        row = tk.Frame(body, bg=BG); row.pack(side="bottom", fill="x", pady=(22, 2))
        def close(ok=False):
            if ok and value.get().strip(): result.append(value.get().strip())
            dialog.destroy()
        button(row, "取消", close, width=9).pack(side="right", padx=(8, 0))
        button(row, "确认", lambda: close(True), primary=True, width=9).pack(side="right")
        entry.bind("<Return>", lambda _e: close(True))
        dialog.protocol("WM_DELETE_WINDOW", close)
        entry.focus_force(); self.root.wait_window(dialog)
        return result[0] if result else None

    def pair(self):
        if self.pair_dialog_open:
            return
        self.pair_dialog_open = True
        code = self.ask_text("连接数据采集助手", "请在 buyali.xyz 点击“数据采集”，输入显示的 6 位配对码：")
        self.pair_dialog_open = False
        if not code:
            return
        try:
            self.api.redeem(code)
            self.pair_verified = True
            self.notice("连接成功", "采集助手已与 buyali.xyz 配对。", "success")
        except ApiError as exc:
            self.pair_verified = False
            self.notice("连接失败", str(exc), "error")

    def verify_pairing(self):
        """Validate persisted credentials before presenting the app as paired."""
        def worker():
            try:
                self.api.state()
            except ApiError as exc:
                self.root.after(0, lambda: self.pairing_invalid(exc))
            else:
                self.root.after(0, self.pairing_valid)
        threading.Thread(target=worker, daemon=True).start()

    def pairing_valid(self):
        self.pair_verified = True

    def pairing_invalid(self, exc):
        self.pair_verified = False
        if getattr(exc, "pairing_required", False):
            self.notice("需要重新连接", str(exc), "error", on_close=self.pair)
        else:
            # A temporary network failure must not erase a valid saved pairing.
            self.notice("连接检查失败", str(exc), "error")

    def rebind(self):
        self.config.pop("deviceToken", None)
        self.config["bindings"] = {}
        self.config["windowCharacters"] = {}
        save_config(self.config)
        self.pair_verified = False
        self.pair()

    def capture(self):
        if self.busy: return
        game = self.current_game()
        if not game:
            self.notice("未找到游戏", "没有检测到 AION2 游戏窗口，请确认游戏已经启动。", "error")
            return
        self.game = game
        game.character_from_cache = False
        if not game.character:
            game.character = self.config.setdefault("windowCharacters", {}).get(str(game.hwnd))
            game.character_from_cache = bool(game.character)
        self.busy = True
        self.capture_serial += 1
        serial = self.capture_serial
        self.capture_phase = "capturing"
        self.capture_button.config(text="◌  正在识别…", fg=CYAN, state="normal")
        self.overlay.withdraw()
        self.root.after(160, lambda: self.capture_after_hide(game, serial))
        self.root.after(25000, lambda: self.capture_watchdog(serial))

    def capture_after_hide(self, game, serial):
        try:
            if serial != self.capture_serial: return
            image = ImageGrab.grab(bbox=game.rect, all_screens=True)
            fields, scores = recognize(image)
            # Read the visible role every time. A game window handle is reused
            # when switching characters, so a remembered role must not suppress
            # fresh recognition.
            hint = recognize_character_text(image)
            image.close()
            if not fields:
                raise RuntimeError("未识别到有效数据，请确认已打开奥德或角色数据界面。")
            self.capture_phase = "network"
            threading.Thread(target=self.prepare_result, args=(game, fields, scores, hint, serial), daemon=True).start()
        except Exception as exc:
            self.capture_error(exc, serial)

    def prepare_result(self, game, fields, scores, hint, serial):
        try:
            data = self.api.state()
            if serial != self.capture_serial: return
            # A visible green role name is fresh evidence. If it maps to one web
            # role, continue directly to data confirmation. If it is a new role,
            # trust the recognized name and open the create/bind screen without
            # an extra role-name confirmation step.
            if hint:
                matched = match_character_hint(data, hint)
                if matched:
                    game.character = str(matched[1].get("name", "")).strip()
                elif not game.character or getattr(game, "character_from_cache", False):
                    game.character = hint
            elif not game.character:
                game.character = self.ui_ask_character("")
            self.config.setdefault("windowCharacters", {})[str(game.hwnd)] = game.character
            save_config(self.config)
            target = self.resolve_character(data, game.character)
            self.root.after(0, lambda: self.confirm_dialog(game, target, fields, scores, serial, data))
        except Exception as exc:
            self.root.after(0, lambda exc=exc: self.capture_error(exc, serial))

    def capture_watchdog(self, serial):
        if serial == self.capture_serial and self.busy and self.capture_phase in ("capturing", "network"):
            self.capture_error("识别请求超时，已自动恢复，请重新采集。", serial)

    def cancel_capture(self):
        if not self.busy:
            self.notice("当前没有采集任务", "采集助手目前处于空闲状态。")
            return
        self.capture_serial += 1
        self.reset_after_capture(show=True)

    def ui_ask_character(self, hint):
        result, ready = [], threading.Event()
        def show():
            prompt = "未能唯一匹配角色，请输入当前角色名。首次绑定后会记住。"
            if hint: prompt += f"\n绿色名字识别结果：{hint}"
            value = self.ask_text("确认当前角色", prompt, hint)
            if value: result.append(value)
            ready.set()
        self.root.after(0, show); ready.wait()
        if not result: raise ApiError("已取消角色识别")
        return result[0]

    def resolve_character(self, data, game_name):
        roles = accounts_and_characters(data)
        bindings = self.config.setdefault("bindings", {})
        # A unique same-name role is stronger evidence than a historical binding.
        # This also repairs old accidental bindings automatically.
        exact = [(a, c) for a, c in roles if str(c.get("name", "")).strip() == game_name]
        if len(exact) == 1:
            account, character = exact[0]
            bindings[game_name] = {"accountId": account["id"], "characterId": character["id"]}
            save_config(self.config)
            return account, character
        bound = bindings.get(game_name)
        if bound:
            for account, character in roles:
                if str(account.get("id")) == str(bound.get("accountId")) and str(character.get("id")) == str(bound.get("characterId")):
                    if str(character.get("name", "")).strip() == game_name:
                        return account, character
                    # Never silently reuse an old cross-name binding. With the
                    # current one-to-one role model this is stale/incorrect.
                    bindings.pop(game_name, None)
                    save_config(self.config)
                    break
        return self.choose_binding(data, game_name)

    def choose_binding(self, data, game_name):
        result, ready = [], threading.Event()
        def show():
            dialog, body = self.make_dialog("绑定网页角色", 600, 430)
            tk.Label(body, text=f"已识别游戏角色：{game_name}", bg=BG, fg=CYAN, font=(FONT, 11, "bold"), justify="left").pack(fill="x", pady=(0, 14))
            entries = [
                (account, character)
                for account, character in accounts_and_characters(data)
                if str(character.get("name", "")).strip() == game_name
            ]
            labels = [f"{a.get('name', '未命名账号')} / {c.get('name', '未命名角色')}" for a, c in entries]
            existing_text = "绑定网页中的同名角色" if labels else "网页中没有同名角色，请在下方创建"
            tk.Label(body, text=existing_text, bg=BG, fg=MUTED if labels else AMBER, font=(FONT, 9), anchor="w").pack(fill="x", pady=(0, 5))
            existing_row = tk.Frame(body, bg=BG); existing_row.pack(fill="x")
            existing_row.columnconfigure(0, weight=1)
            combo = ttk.Combobox(existing_row, values=labels, state="readonly", font=(FONT, 10))
            combo.grid(row=0, column=0, sticky="ew", ipady=6, padx=(0, 10))
            if labels: combo.current(0)

            tk.Frame(body, bg=BORDER, height=1).pack(fill="x", pady=18)
            accounts = data.get("accounts", [])
            account_labels = [str(account.get("name", "未命名账号")) for account in accounts]
            tk.Label(body, text=f"或将“{game_name}”创建到以下账号", bg=BG, fg=MUTED, font=(FONT, 9), anchor="w").pack(fill="x", pady=(0, 5))
            create_row = tk.Frame(body, bg=BG); create_row.pack(fill="x")
            create_row.columnconfigure(0, weight=1)
            account_combo = ttk.Combobox(create_row, values=account_labels, state="readonly", font=(FONT, 10))
            account_combo.grid(row=0, column=0, sticky="ew", ipady=6, padx=(0, 10))
            if account_labels: account_combo.current(0)

            def finish(value=None):
                if value: result.append(value)
                dialog.destroy(); ready.set()
            def bind_existing():
                if combo.current() >= 0:
                    finish(entries[combo.current()])
                else:
                    self.notice("没有已有角色", "请改为选择账号并创建新角色。", "error")
            def create_new():
                index = account_combo.current()
                if index < 0 or index >= len(accounts):
                    self.notice("没有可用账号", "请先在网页中创建账号。", "error"); return
                selected = accounts[index]
                try:
                    created = self.api.create_character(selected["id"], game_name)["character"]
                    finish((selected, created))
                except ApiError as exc: self.notice("创建失败", str(exc), "error")
            bind_button = button(existing_row, "绑定已有角色", bind_existing, primary=True, width=13)
            bind_button.grid(row=0, column=1, sticky="ew")
            if not labels: bind_button.config(state="disabled", cursor="arrow")
            button(create_row, "创建并绑定", create_new, primary=not labels, width=12).grid(row=0, column=1, sticky="ew")
            footer = tk.Frame(body, bg=BG); footer.pack(fill="x", pady=(22, 0))
            button(footer, "取消", finish, width=12).pack(side="right")
            dialog.protocol("WM_DELETE_WINDOW", finish)
        self.root.after(0, show); ready.wait()
        if not result: raise ApiError("已取消角色绑定")
        account, character = result[0]
        self.config.setdefault("bindings", {})[game_name] = {"accountId": account["id"], "characterId": character["id"]}
        save_config(self.config)
        return account, character

    def confirm_dialog(self, game, target, fields, scores, serial, data):
        if serial != self.capture_serial: return
        self.capture_phase = "confirm"
        account, character = target
        height = 390 + 52 * len(fields)
        dialog, body = self.make_dialog("确认采集内容", 590, height)
        tk.Label(body, text=f"识别角色：{game.character}", bg=BG, fg=CYAN, font=(FONT, 11, "bold"), anchor="w").pack(fill="x")
        tk.Label(body, text=f"写入位置：{account.get('name')} · {character.get('name')}", bg=BG, fg=TEXT, font=(FONT, 10), anchor="w").pack(fill="x", pady=(3, 12))
        headings = tk.Frame(body, bg=BG); headings.pack(fill="x", pady=(0, 3))
        tk.Label(headings, text="数据项", width=10, bg=BG, fg=MUTED, font=(FONT, 9), anchor="w").pack(side="left")
        tk.Label(headings, text="变更前", width=15, bg=BG, fg=MUTED, font=(FONT, 9), anchor="w").pack(side="left")
        tk.Label(headings, text="变更后", bg=BG, fg=MUTED, font=(FONT, 9), anchor="w").pack(side="left", padx=(24, 0))
        entries = {}
        old_values = {}
        def display_value(value):
            if value is None or value == "": return "—"
            if isinstance(value, (int, float)): return f"{value:,}"
            return str(value)
        def parsed_value(key, value):
            clean = value.replace(",", "").strip()
            return round(float(clean), 2) if key == "combatPower" else int(clean)
        def update_change_color(key, entry):
            try:
                after = parsed_value(key, entry.get())
                before = old_values[key]
                if before is not None:
                    before = round(float(before), 2) if key == "combatPower" else int(before)
                changed = before is None or after != before
            except (TypeError, ValueError):
                changed = True
            entry.config(fg=AMBER if changed else TEXT)
        for key, value in fields.items():
            row = tk.Frame(body, bg=BG); row.pack(fill="x", pady=4)
            tk.Label(row, text=FIELD_LABELS[key], width=10, bg=BG, fg=MUTED, font=(FONT, 10), anchor="w").pack(side="left")
            # White aether shown by the webpage includes automatic three-hour
            # recovery.  The API exposes that effective value separately from
            # the stored baseline so the comparison matches what users see.
            old_values[key] = character.get("whiteEnergyDisplay") if key == "whiteEnergy" else character.get(key)
            if old_values[key] is None:
                old_values[key] = character.get(key)
            tk.Label(row, text=display_value(old_values[key]), width=15, bg=BG, fg=TEXT, font=(FONT, 10), anchor="w").pack(side="left")
            tk.Label(row, text="→", width=3, bg=BG, fg=MUTED, font=(FONT, 10)).pack(side="left")
            entry = tk.Entry(row, bg=PANEL_2, fg=TEXT, insertbackground=TEXT, relief="flat", font=(FONT, 10))
            entry.insert(0, str(value)); entry.pack(side="left", fill="x", expand=True, ipady=6); entries[key] = entry
            entry.bind("<KeyRelease>", lambda _event, k=key, e=entry: update_change_color(k, e))
            update_change_color(key, entry)
        binding_matches = str(character.get("name", "")).strip() == str(game.character).strip()
        reasonable_change = True
        for key, after in fields.items():
            before = old_values.get(key)
            if before in (None, ""):
                continue
            try:
                before_number, after_number = float(before), float(after)
                ratio = abs(after_number - before_number) / max(1.0, abs(before_number))
            except (TypeError, ValueError):
                continue
            # These values normally move incrementally. Large jumps are still
            # editable, but must never pass the automatic-write countdown.
            if key == "itemLevel" and ratio > 0.05:
                reasonable_change = False
            elif key == "combatPower" and ratio > 0.30:
                reasonable_change = False
            elif key == "kina" and ratio > 0.60:
                reasonable_change = False
        reliable = all(scores.get(key, 0) >= 80 for key in fields) and binding_matches and reasonable_change
        status = tk.Label(body, bg=BG, fg=CYAN, font=(FONT, 9)); status.pack(fill="x", pady=(12, 8))
        controls = tk.Frame(body, bg=BG); controls.pack(fill="x")
        remaining = [5]
        def finish():
            if dialog.winfo_exists(): dialog.destroy()
            self.reset_after_capture()
        def submit():
            try:
                edited = {k: parsed_value(k, e.get()) for k, e in entries.items()}
            except ValueError:
                self.notice("数据格式错误", "请输入有效整数。", "error"); return
            payload = {"accountId": account["id"], "characterId": character["id"], "characterName": game.character, "windowTitle": game.title, "fields": edited}
            dialog.destroy()
            self.capture_phase = "applying"
            threading.Thread(target=self.apply_result, args=(payload, edited, game.character, serial), daemon=True).start()
        def change_binding():
            if dialog.winfo_exists(): dialog.destroy()
            self.capture_phase = "binding"
            threading.Thread(target=self.rebind_for_capture, args=(data, game, fields, scores, serial), daemon=True).start()
        for column in range(3): controls.columnconfigure(column, weight=1, uniform="confirm")
        button(controls, "更换绑定", change_binding, width=10).grid(row=0, column=0, sticky="ew", padx=(0, 5))
        button(controls, "立即写入", submit, primary=True, width=11).grid(row=0, column=1, sticky="ew", padx=5)
        button(controls, "取消", finish, width=9).grid(row=0, column=2, sticky="ew", padx=(5, 0))
        def tick():
            if not dialog.winfo_exists(): return
            if not reliable:
                if not binding_matches:
                    status.config(text="识别角色与写入位置不同，请更换绑定或人工确认", fg=AMBER)
                else:
                    message = "识别结果变化异常，请人工确认" if not reasonable_change else "部分结果可信度较低，请人工确认"
                    status.config(text=message, fg=AMBER)
                return
            status.config(text=f"{remaining[0]} 秒后自动写入")
            if remaining[0] == 0: submit(); return
            remaining[0] -= 1; dialog.after(1000, tick)
        dialog.protocol("WM_DELETE_WINDOW", finish); tick()

    def rebind_for_capture(self, data, game, fields, scores, serial):
        try:
            if serial != self.capture_serial: return
            target = self.choose_binding(data, game.character)
            if serial != self.capture_serial: return
            self.root.after(0, lambda: self.confirm_dialog(game, target, fields, scores, serial, data))
        except Exception as exc:
            self.root.after(0, lambda exc=exc: self.capture_error(exc, serial))

    def apply_result(self, payload, fields, character, serial):
        try:
            result = self.api.apply(payload)
            if serial != self.capture_serial: return
            self.root.after(0, lambda: self.success_dialog(result["transactionId"], fields, character, serial))
        except Exception as exc:
            self.root.after(0, lambda exc=exc: self.capture_error(exc, serial))

    def success_dialog(self, transaction_id, fields, character, serial):
        if serial != self.capture_serial: return
        self.capture_phase = "success"
        dialog, body = self.make_dialog("采集成功", 460, 350 + 28 * len(fields))
        tk.Label(body, text="✓  已写入云端", bg=BG, fg=GREEN, font=(FONT, 15, "bold")).pack(anchor="w")
        tk.Label(body, text=f"当前角色：{character}\n" + "\n".join(f"{FIELD_LABELS[k]}：{v:,}" for k, v in fields.items()), bg=BG, fg=TEXT, font=(FONT, 10), justify="left").pack(anchor="w", pady=14)
        status = tk.Label(body, bg=BG, fg=MUTED, font=(FONT, 9)); status.pack(fill="x", pady=5)
        remaining = [8]
        def finish():
            if dialog.winfo_exists(): dialog.destroy()
            self.reset_after_capture()
        def undo_worker():
            try:
                self.api.undo(transaction_id)
                self.root.after(0, lambda: self.notice("已撤回", "本次采集写入已撤回。", "success", finish))
            except ApiError as exc:
                self.root.after(0, lambda exc=exc: self.notice("撤回失败", str(exc), "error"))
        controls = tk.Frame(body, bg=BG); controls.pack(fill="x", pady=(12, 0))
        controls.columnconfigure(0, weight=1); controls.columnconfigure(1, weight=1)
        button(controls, "撤回本次写入", lambda: threading.Thread(target=undo_worker, daemon=True).start(), primary=True, width=15).grid(row=0, column=0, sticky="ew", padx=(0, 5))
        button(controls, "确认并关闭", finish, width=12).grid(row=0, column=1, sticky="ew", padx=(5, 0))
        def tick():
            if not dialog.winfo_exists(): return
            status.config(text=f"{remaining[0]} 秒内可撤回")
            if remaining[0] == 0: finish(); return
            remaining[0] -= 1; dialog.after(1000, tick)
        dialog.protocol("WM_DELETE_WINDOW", finish); tick()

    def capture_error(self, exc, serial=None):
        if serial is not None and serial != self.capture_serial: return
        self.reset_after_capture(show=True)
        if getattr(exc, "pairing_required", False):
            self.pair_verified = False
            self.notice("需要重新连接", str(exc), "error", on_close=self.pair)
        else:
            self.notice("采集失败", str(exc), "error")

    def reset_after_capture(self, show=True):
        self.busy = False
        self.capture_phase = "idle"
        self.capture_button.config(text="◎  采集数据", fg=TEXT, state="normal")
        if show:
            self.overlay.deiconify(); self.force_overlay_topmost()

    def quit(self):
        self.config["offset"] = self.offset
        save_config(self.config)
        if getattr(self, "tray", None):
            self.tray.stop()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    if not relaunch_from_ascii_runtime():
        kernel32 = ctypes.windll.kernel32
        kernel32.SetLastError(0)
        mutex = kernel32.CreateMutexW(None, False, "Local\\BuyaliCollector-1.3.1")
        if kernel32.GetLastError() != 183:
            CollectorApp().run()
