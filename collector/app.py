from __future__ import annotations

import ctypes
import ctypes.wintypes
import difflib
import json
import os
import re
import sys
import threading
import time
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from collections import Counter
from tkinter import messagebox, simpledialog, ttk
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import numpy as np
from PIL import Image, ImageEnhance, ImageGrab
try:
    from rapidocr_onnxruntime import RapidOCR
except ImportError:  # Parsing-only tests do not need the OCR runtime.
    RapidOCR = None


APP_NAME = "Buyali 数据采集助手"
APP_VERSION = "1.3.4.1"
IS_TEST_BUILD = "-test" in APP_VERSION
DEFAULT_API_BASE = "https://test.buyali.xyz" if IS_TEST_BUILD else "https://buyali.xyz"
API_BASE = os.environ.get("BUYALI_API_BASE", DEFAULT_API_BASE).rstrip("/")
CONFIG_DIR_NAME = "BuyaliCollector-test" if IS_TEST_BUILD else "BuyaliCollector"
CONFIG_DIR = Path(os.environ.get("APPDATA", Path.home())) / CONFIG_DIR_NAME
CONFIG_FILE = CONFIG_DIR / "config.json"
FIELD_LABELS = {"whiteEnergy": "白奥德", "blueEnergy": "蓝奥德", "combatPower": "战斗力", "itemLevel": "道具等级", "kina": "基纳"}

user32 = ctypes.windll.user32
try:
    user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
    user32.SetProcessDpiAwarenessContext.restype = ctypes.c_bool
    if not user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
        user32.SetProcessDPIAware()
except (AttributeError, OSError):
    user32.SetProcessDPIAware()
WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
user32.EnumWindows.argtypes = [WNDENUMPROC, ctypes.wintypes.LPARAM]
user32.EnumWindows.restype = ctypes.c_bool
user32.GetForegroundWindow.restype = ctypes.wintypes.HWND
user32.GetWindowTextLengthW.argtypes = [ctypes.wintypes.HWND]
user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = [ctypes.wintypes.HWND, ctypes.wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int
user32.IsWindowVisible.argtypes = [ctypes.wintypes.HWND]
user32.IsWindowVisible.restype = ctypes.c_bool
user32.IsIconic.argtypes = [ctypes.wintypes.HWND]
user32.IsIconic.restype = ctypes.c_bool
user32.IsWindow.argtypes = [ctypes.wintypes.HWND]
user32.IsWindow.restype = ctypes.c_bool
user32.GetWindowRect.argtypes = [ctypes.wintypes.HWND, ctypes.POINTER(ctypes.wintypes.RECT)]
user32.GetWindowRect.restype = ctypes.c_bool
user32.SetWindowPos.argtypes = [ctypes.wintypes.HWND, ctypes.wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
user32.SetWindowPos.restype = ctypes.c_bool


def resource_path(relative: str) -> Path:
    portable_root = os.environ.get("BUYALI_PORTABLE_ROOT")
    if portable_root:
        portable = Path(portable_root) / relative
        if portable.exists():
            return portable
    beside_exe = Path(sys.executable).parent / relative
    if getattr(sys, "frozen", False) and beside_exe.exists():
        return beside_exe
    return Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / relative


def configure_ocr() -> None:
    # RapidOCR is bundled with the portable application and needs no external
    # executable or language-pack installation.
    rapid_engine()


_RAPID_ENGINE = None
_RAPID_ENGINE_LOCK = threading.Lock()
_RAPID_INFERENCE_LOCK = threading.Lock()


def rapid_engine():
    global _RAPID_ENGINE
    if RapidOCR is None:
        raise RuntimeError("RapidOCR 运行库未安装，无法执行图像识别")
    if _RAPID_ENGINE is None:
        with _RAPID_ENGINE_LOCK:
            if _RAPID_ENGINE is None:
                _RAPID_ENGINE = RapidOCR()
    return _RAPID_ENGINE


def rapid_read(image: Image.Image, target_height: int = 220) -> list[tuple[str, float]]:
    """Return local neural-OCR lines with confidence, preserving UI order."""
    scale = max(1, min(4, int(round(target_height / max(1, image.height)))))
    prepared = image.convert("RGB")
    if scale > 1:
        prepared = prepared.resize((prepared.width * scale, prepared.height * scale), Image.Resampling.LANCZOS)
    with _RAPID_INFERENCE_LOCK:
        result, _ = rapid_engine()(np.asarray(prepared))
    return [(str(item[1]).strip(), float(item[2])) for item in (result or []) if str(item[1]).strip()]


def load_config() -> dict:
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_config(config: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


class ApiError(RuntimeError):
    def __init__(self, message: str, pairing_required: bool = False):
        super().__init__(message)
        self.pairing_required = pairing_required


class ApiClient:
    def __init__(self, config: dict):
        self.config = config

    def request(self, method: str, route: str, payload=None, authenticated=True):
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) BuyaliCollector/{APP_VERSION}",
        }
        if authenticated:
            token = self.config.get("deviceToken")
            if not token:
                raise ApiError("采集助手尚未配对，请输入网页显示的 6 位连接码", pairing_required=True)
            headers["Authorization"] = "Bearer " + token
        body = json.dumps(payload).encode() if payload is not None else None
        req = Request(API_BASE + "/api/capture/" + route, data=body, headers=headers, method=method)
        try:
            with urlopen(req, timeout=12) as response:
                result = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            try:
                detail = json.loads(exc.read().decode("utf-8")).get("error", str(exc))
            except Exception:
                detail = str(exc)
            if authenticated and exc.code in (401, 403):
                self.config.pop("deviceToken", None)
                self.config["bindings"] = {}
                self.config["windowCharacters"] = {}
                self.config["apiBase"] = API_BASE
                save_config(self.config)
                raise ApiError("配对已失效，请重新输入网页显示的 6 位连接码", pairing_required=True) from exc
            raise ApiError(detail) from exc
        except (URLError, TimeoutError) as exc:
            raise ApiError("无法连接 Buyali 正式服务") from exc
        if not result.get("ok", True):
            raise ApiError(result.get("error", "请求失败"))
        return result

    def redeem(self, code: str):
        result = self.request("POST", "redeem", {"code": re.sub(r"\D", "", code)}, authenticated=False)
        self.config["deviceToken"] = result["deviceToken"]
        self.config["apiBase"] = API_BASE
        save_config(self.config)
        return result

    def state(self):
        return self.request("GET", "state")

    def apply(self, payload):
        return self.request("POST", "apply", payload)

    def undo(self, transaction_id):
        return self.request("POST", "undo", {"transactionId": transaction_id})

    def create_character(self, account_id, name):
        return self.request("POST", "create-character", {"accountId": account_id, "name": name})


@dataclass
class GameWindow:
    hwnd: int
    title: str
    character: str | None
    rect: tuple[int, int, int, int]


def parse_character(title: str) -> str | None:
    # The live client uses a lower-case Latin "l" as the separator:
    # "AION2 l Character". Older builds and regions also use |, -, or :.
    match = re.match(r"^\s*AION2\s*(?:[|｜]|[lI](?=\s)|[-:：—–])\s*(.+?)\s*$", title, re.I)
    return match.group(1).strip() if match and match.group(1).strip() else None


def window_title(hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def find_active_game() -> GameWindow | None:
    foreground = user32.GetForegroundWindow()
    candidates = [foreground]
    found = []
    def enum_cb(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            title = window_title(hwnd)
            if parse_character(title) or re.match(r"^\s*AION2\b", title, re.I):
                found.append(hwnd)
        return True

    user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
    candidates.extend(found)
    for hwnd in candidates:
        title = window_title(hwnd)
        character = parse_character(title)
        is_aion = bool(re.match(r"^\s*AION2\b", title, re.I))
        if user32.IsIconic(hwnd):
            continue
        rect = ctypes.wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        width, height = rect.right - rect.left, rect.bottom - rect.top
        if (character or is_aion) and width >= 800 and height >= 500:
            return GameWindow(hwnd, title, character, (rect.left, rect.top, rect.right, rect.bottom))
    return None


def crop_ratio(image: Image.Image, box):
    w, h = image.size
    return image.crop((int(box[0] * w), int(box[1] * h), int(box[2] * w), int(box[3] * h)))


def ocr_digits(image: Image.Image, allowed="0123456789,.+Kk/", psm=7) -> tuple[str, float]:
    processed = image.convert("L")
    scale = 6 if psm == 11 else 4
    processed = processed.resize((processed.width * scale, processed.height * scale), Image.Resampling.BICUBIC)
    if psm != 11:
        processed = ImageEnhance.Contrast(processed).enhance(1.8)
        processed = ImageEnhance.Brightness(processed).enhance(1.08)
    data = pytesseract.image_to_data(processed, config=f"--psm {psm} -c tessedit_char_whitelist={allowed}", output_type=pytesseract.Output.DICT)
    words, confidences = [], []
    for text, confidence in zip(data["text"], data["conf"]):
        if text.strip():
            words.append(text.strip())
            try:
                if float(confidence) >= 0:
                    confidences.append(float(confidence))
            except ValueError:
                pass
    return "".join(words), (sum(confidences) / len(confidences) if confidences else 0)


def ocr_cyan_stat(image: Image.Image) -> tuple[str, float]:
    """Isolate and vote on cyan combat-power readings across color masks."""
    rgb = image.convert("RGB")
    source = rgb.load()
    votes = []
    for threshold in (80, 95, 110, 125, 140):
        mask = Image.new("L", rgb.size, 255)
        target = mask.load()
        for y in range(rgb.height):
            for x in range(rgb.width):
                red, green, blue = source[x, y]
                if green >= threshold and blue >= threshold - 10 and green > red * 1.18:
                    target[x, y] = 0
        prepared = mask.resize((mask.width * 6, mask.height * 6), Image.Resampling.NEAREST)
        text = pytesseract.image_to_string(
            prepared,
            config="--psm 6 -c tessedit_char_whitelist=0123456789.Kk",
        ).replace(" ", "").replace("\n", "")
        match = re.search(r"\d{1,3}(?:\.\d{1,2})?[Kk]", text)
        if match:
            votes.append(match.group(0).upper())
    if not votes:
        return "", 0
    counts = Counter(votes)
    text = max(counts, key=lambda candidate: (counts[candidate], len(candidate)))
    score = min(98, 38 + counts[text] * 12)
    return text, score


def ocr_white_item_level(image: Image.Image) -> tuple[str, float]:
    """Read item level using an ensemble instead of trusting one threshold.

    Stone/grass/effect backgrounds change antialiasing around the white glyphs.
    Several neutral-color and luminance masks are evaluated independently; a
    lone plausible-looking OCR result is deliberately marked low-confidence.
    """
    rgb = image.convert("RGB")
    source = rgb.load()
    masks = []
    for brightness, spread in ((115, 55), (135, 65), (150, 70), (170, 80), (190, 90)):
        mask = Image.new("L", rgb.size, 255)
        target = mask.load()
        for y in range(rgb.height):
            for x in range(rgb.width):
                red, green, blue = source[x, y]
                if min(red, green, blue) >= brightness and max(red, green, blue) - min(red, green, blue) <= spread:
                    target[x, y] = 0
        masks.append(mask)
    gray = rgb.convert("L")
    masks.extend(gray.point(lambda value, threshold=threshold: 0 if value >= threshold else 255) for threshold in (145, 175, 205))

    votes = []
    formatted_votes = Counter()
    for mask in masks:
        prepared = mask.resize((mask.width * 6, mask.height * 6), Image.Resampling.NEAREST)
        text = pytesseract.image_to_string(
            prepared,
            config="--psm 6 -c tessedit_char_whitelist=0123456789,",
        )
        for candidate in re.findall(r"\d{1,2},\d{3}|\d{3,4}", text):
            value = integer(candidate)
            if value is None or not 100 <= value <= 9999:
                continue
            votes.append(value)
            if "," in candidate:
                formatted_votes[value] += 1
    if not votes:
        return "", 0
    counts = Counter(votes)
    value = max(counts, key=lambda candidate: (formatted_votes[candidate], counts[candidate], candidate))
    agreement = counts[value]
    # Require independent agreement for automatic submission. A comma is
    # strong structural evidence, but never enough by itself after one pass.
    score = min(98, 38 + agreement * 10 + formatted_votes[value] * 5)
    display = f"{value:,}" if formatted_votes[value] else str(value)
    return display, score


def ocr_high_contrast_digits(image: Image.Image) -> tuple[str, float]:
    """Read bright top-bar counters on dark or highly animated backgrounds."""
    gray = image.convert("L").resize((image.width * 5, image.height * 5), Image.Resampling.BICUBIC)
    votes = []
    for threshold in (105, 130, 150, 175, 200):
        binary = gray.point(lambda value, threshold=threshold: 0 if value > threshold else 255)
        text = pytesseract.image_to_string(
            binary,
            config="--psm 6 -c tessedit_char_whitelist=0123456789,+/()",
        ).strip().replace(" ", "").replace("\n", "")
        match = re.search(r"\d{1,3}(?:\(?\+\d{1,4}\)?)?/840", text)
        if match:
            votes.append(match.group(0))
    detailed, _ = ocr_digits(image, psm=11)
    match = re.search(r"\d{1,3}(?:\(?\+\d{1,4}\)?)?/840", detailed.replace(" ", ""))
    if match:
        votes.append(match.group(0))
    if not votes:
        return detailed, 0
    counts = Counter(votes)
    text = max(counts, key=lambda candidate: (counts[candidate], len(candidate)))
    score = min(98, 46 + counts[text] * 10)
    return text, score


def integer(text: str):
    digits = re.sub(r"[^0-9]", "", text)
    return int(digits) if digits else None


def compact_number(text: str):
    clean = text.replace(",", "").strip()
    match = re.search(r"(\d+(?:\.\d+)?)\s*([Kk]?)", clean)
    if not match:
        return None
    value = float(match.group(1))
    # The website stores combat power in K units (75.00K => 75.0), while
    # item level is a plain integer. Keep the OCR unit instead of expanding it.
    if match.group(2):
        return round(value, 2)
    return int(round(value))


def parse_aether_candidates(lines: list[tuple[str, float]]) -> tuple[dict, dict]:
    """Parse Aether without treating a visible zero as a missing value.

    OCR engines sometimes split ``285(+0)/840`` into several adjacent lines.
    Try each line first, then short ordered joins. A field is returned only
    when its syntax is present; the numeric value zero remains valid.
    """
    normalized = [(re.sub(r"\s+", "", text).replace(".", ","), confidence) for text, confidence in lines]
    candidates = list(normalized)
    for start in range(len(normalized)):
        for size in (2, 3):
            group = normalized[start:start + size]
            if len(group) == size:
                candidates.append(("".join(item[0] for item in group), min(item[1] for item in group)))

    fields, scores = {}, {}
    for compact, confidence in candidates:
        match = re.search(r"(?<!\d)(\d{1,3})\(?\+([\d,]{1,6})\)?/840", compact)
        if match:
            white, blue = integer(match.group(1)), integer(match.group(2))
            if white is not None and blue is not None and 0 <= white <= 840 and 0 <= blue <= 2000:
                score = min(99, confidence * 100)
                return {"whiteEnergy": white, "blueEnergy": blue}, {"whiteEnergy": score, "blueEnergy": score}
    for compact, confidence in candidates:
        match = re.search(r"(?<!\d)(\d{1,3})/840(?:[^0-9]|$)", compact)
        if match:
            white = integer(match.group(1))
            if white is not None and 0 <= white <= 840:
                score = min(99, confidence * 100)
                # The current game UI omits the ``+0`` segment entirely. A
                # complete ``white/840`` counter therefore explicitly means
                # blue aether is zero, rather than that the field is missing.
                fields.update(whiteEnergy=white, blueEnergy=0)
                scores.update(whiteEnergy=score, blueEnergy=score)
                break
    return fields, scores


def parse_currency_candidates(lines: list[tuple[str, float]], has_aether: bool) -> tuple[int, float] | None:
    """Select kina by UI order while retaining standalone ``0`` counters."""
    values = []
    for text, confidence in lines:
        compact = re.sub(r"\s+", "", text)
        if "/840" in compact or re.search(r"[+()]", compact):
            continue
        # A standalone zero is a real counter. Reject short non-zero values,
        # which are normally level/badge noise in the same top strip.
        if re.fullmatch(r"0", compact):
            values.append((0, confidence))
        elif re.fullmatch(r"\d{1,3}(?:,\d{3})+", compact):
            value = integer(compact)
            if value is not None and value <= 999_999_999_999:
                values.append((value, confidence))
    if len(values) < 2:
        return None
    if not has_aether:
        # The purple wallet currency sits immediately before kina in the
        # normal HUD. Once it reaches four digits it also gains a thousands
        # separator and becomes indistinguishable by syntax alone. If OCR
        # loses a later counter, the old two-value fallback incorrectly chose
        # that small first value (for example 3,338 instead of 433,589,356).
        # Treat only the characteristic small-to-large jump as this layout;
        # ordinary multi-million kina/bound-currency pairs keep their order.
        first_value, _ = values[0]
        second_value, _ = values[1]
        if 1_000 <= first_value <= 9_999 and second_value >= 1_000_000:
            return values[1]
    # With aether visible, kina is followed by one counter. In the normal HUD
    # three formatted currencies are shown and kina is the first one. Older
    # code selected the penultimate value for a three-counter HUD, assigning
    # the adjacent currency to kina.
    index = -2 if has_aether else (-3 if len(values) >= 3 else -2)
    return values[index]


def has_truncated_currency_candidate(lines: list[tuple[str, float]]) -> bool:
    """Detect comma-grouped counters where OCR dropped trailing digits."""
    for text, _confidence in lines:
        compact = re.sub(r"\s+", "", text).strip(".,")
        if re.fullmatch(r"\d{1,3}(?:,\d{3})+,\d{1,2}", compact):
            return True
    return False


def recognize_top_status_bar(image: Image.Image) -> tuple[dict, dict]:
    """Recognize menu counters by their semantic format and order.

    This scans the complete top status strip, so it is independent of dungeon
    artwork, UI color, and horizontal shifts caused by resolution/UI scaling.
    """
    # Scan the entire top strip.  The normal HUD places currencies on the
    # left, while expedition/conquest menus place the same counters on the
    # right.  Restricting this crop to either side makes recognition depend on
    # the currently open screen and can clip the first digit of kina.
    band = crop_ratio(image, (0.0, 0.0, 0.98, 0.075)).convert("L")
    variants = [band]
    variants.extend(band.point(lambda value, threshold=threshold: 0 if value > threshold else 255) for threshold in (80, 100, 130, 160))
    texts = [
        pytesseract.image_to_string(
            variant,
            config="--psm 11 -c tessedit_char_whitelist=0123456789,.+Kk/()",
        )
        for variant in variants
    ]
    line_sets = [[re.sub(r"\s+", "", line) for line in text.splitlines() if line.strip()] for text in texts]
    fields, scores = {}, {}

    # Search both individual OCR lines and their compact form. Backgrounds can
    # alter line segmentation, but not the counter's semantic format.
    candidates = []
    for text, lines in zip(texts, line_sets):
        candidates.extend(lines)
        candidates.append(re.sub(r"\s+", "", text))
    for line in candidates:
        normalized = line.replace(".", ",")
        # Do not accept the trailing three digits of a four-digit OCR error
        # (for example 1650+... becoming 650+...).
        blue = re.search(r"(?<!\d)(\d{1,3})\(?\+([\d,]+)\)?/840", normalized)
        if blue:
            white_value, blue_value = integer(blue.group(1)), integer(blue.group(2))
            if white_value is not None and blue_value is not None and 0 <= white_value <= 840 and 0 <= blue_value <= 9999:
                fields.update(whiteEnergy=white_value, blueEnergy=blue_value)
                scores.update(whiteEnergy=94, blueEnergy=94)
                break
    plain_aether_zero = False
    if "whiteEnergy" not in fields:
        for line in candidates:
            normalized = line.replace(".", ",")
            white = re.search(r"(?<![\d,])(\d{1,3})/840(?:[^0-9]|$)", normalized)
            if not white:
                continue
            white_value = integer(white.group(1))
            if white_value is not None and 0 <= white_value <= 840:
                fields["whiteEnergy"], scores["whiteEnergy"] = white_value, 92
                plain_aether_zero = True
                break
    if "whiteEnergy" in fields and "blueEnergy" not in fields:
        # One threshold may preserve the '+blue/840' suffix while damaging the
        # white prefix (for example 165 becoming 1650). Combine that suffix
        # with a separately validated white reading instead of discarding it.
        blue_votes = []
        for line in candidates:
            normalized = line.replace(".", ",")
            match = re.search(r"\+([\d,]{1,6})\)?/840", normalized)
            if match:
                value = integer(match.group(1))
                if value is not None and 0 <= value <= 2000:
                    blue_votes.append(value)
        if blue_votes:
            counts = Counter(blue_votes)
            value = max(counts, key=lambda candidate: (counts[candidate], candidate))
            fields["blueEnergy"] = value
            scores["blueEnergy"] = min(88, 55 + counts[value] * 10)
        elif plain_aether_zero:
            # ``45/840`` is the game's zero-blue form. Preserve zero as a
            # real update value so the server can clear an earlier balance.
            fields["blueEnergy"] = 0
            scores["blueEnergy"] = scores["whiteEnergy"]

    # Currency values are laid out in a stable order. The final two numeric
    # counters are kina and the following gold currency; select the penultimate
    # counter rather than relying on its screen coordinate or icon color.
    kina_votes = []
    for text in texts:
        currency_values = []
        # Keep OCR word boundaries. Joining a whole line can turn adjacent
        # counters into one number (for example 1,53817,619,502).
        for token in re.findall(r"[0-9][0-9,.]*", text):
            clean = token.strip(".,")
            if not re.fullmatch(r"\d{1,3}(?:[,.]\d{3})+", clean):
                continue
            value = integer(clean)
            if value is not None and value <= 999_999_999_999:
                currency_values.append(value)
        if len(currency_values) >= 2:
            kina_votes.append(currency_values[-2])
    if kina_votes:
        # Background animation may make one threshold lose a leading digit or
        # confuse a single glyph.  Prefer agreement between independent image
        # variants; use the longest plausible reading only as a tie-breaker.
        counts = Counter(kina_votes)
        value = max(counts, key=lambda candidate: (counts[candidate], len(str(candidate)), candidate))
        agreement = counts[value]
        fields["kina"] = value
        scores["kina"] = 96 if agreement >= 2 else 70
    return fields, scores


def recognize(image: Image.Image) -> tuple[dict, dict]:
    fields, scores = {}, {}

    # Both the normal HUD and menu screens keep resource counters in the top
    # 7.5% strip; their horizontal position changes, so read the entire strip.
    top_band = crop_ratio(image, (0.0, 0.0, 0.98, 0.075))
    top_lines = rapid_read(top_band, target_height=260)
    aether_fields, aether_scores = parse_aether_candidates(top_lines)
    fields.update(aether_fields)
    scores.update(aether_scores)

    currency = parse_currency_candidates(top_lines, "whiteEnergy" in fields)
    if has_truncated_currency_candidate(top_lines):
        # Scaling can occasionally merge a digit into the currency icon or
        # neighboring glyph (438,589,356 -> 438,589,36). Re-read at the source
        # scale only for this suspicious syntax and prefer the stronger valid
        # result. This avoids doubling OCR work during ordinary captures.
        native_lines = rapid_read(top_band, target_height=180)
        native_currency = parse_currency_candidates(native_lines, "whiteEnergy" in fields)
        if native_currency and (currency is None or native_currency[1] > currency[1]):
            currency = native_currency
    if currency is not None:
        value, confidence = currency
        fields["kina"], scores["kina"] = value, min(99, confidence * 100)

    # Center-bottom stat plaque: K suffix unambiguously means combat power;
    # comma-formatted 3-4 digits means item level. The crop deliberately also
    # includes the level emblem, which is ignored by these structural rules.
    stat_lines = rapid_read(crop_ratio(image, (0.455, 0.835, 0.545, 0.975)), target_height=420)
    combat_candidates, item_candidates = [], []
    for text, confidence in stat_lines:
        clean = re.sub(r"\s+", "", text)
        combat = re.fullmatch(r"(\d{1,3}(?:\.\d{1,2})?)[Kk]", clean)
        if combat:
            combat_candidates.append((float(combat.group(1)), confidence))
            continue
        if re.fullmatch(r"\d{1,2},\d{3}|\d{3,4}", clean):
            value = integer(clean)
            if value is not None and 100 <= value <= 9999:
                item_candidates.append((value, confidence, "," in clean))
    if combat_candidates:
        value, confidence = max(combat_candidates, key=lambda item: item[1])
        fields["combatPower"], scores["combatPower"] = round(value, 2), min(99, confidence * 100)
    elif item_candidates:
        value, confidence, _ = max(item_candidates, key=lambda item: (item[2], item[1]))
        fields["itemLevel"], scores["itemLevel"] = value, min(99, confidence * 100)

    return fields, scores


def accounts_and_characters(data):
    results = []
    for account in data.get("accounts", []):
        for character in account.get("characters", []):
            results.append((account, character))
    return results


def recognize_character_text(image: Image.Image) -> str:
    """Read the green player name above the avatar in the center HUD."""
    crop = crop_ratio(image, (0.43, 0.39, 0.57, 0.59))
    candidates = []
    for text, confidence in rapid_read(crop, target_height=600):
        clean = re.sub(r"[^0-9A-Za-z\u3400-\u9fff\uac00-\ud7af]", "", text)
        if 2 <= len(clean) <= 16:
            candidates.append((confidence, clean))
    # OCR results are returned top-to-bottom. The character name is below the
    # guild/title line, so spatial order is stronger evidence than a tiny
    # confidence difference between the two lines.
    return candidates[-1][1] if candidates else ""


def match_character_hint(data, hint):
    """Fuzzy-match OCR output to one unique existing web character."""
    if not hint:
        return None
    ranked = []
    for account, character in accounts_and_characters(data):
        name = str(character.get("name", "")).strip()
        if not name:
            continue
        score = 1.0 if name == hint else difflib.SequenceMatcher(None, hint, name).ratio()
        ranked.append((score, account, character))
    ranked.sort(key=lambda item: item[0], reverse=True)
    if not ranked:
        return None
    best = ranked[0]
    second_score = ranked[1][0] if len(ranked) > 1 else 0.0
    if best[0] >= 0.62 and (best[0] == 1.0 or best[0] - second_score >= 0.12):
        return best[1], best[2]
    return None


class CollectorApp:
    def __init__(self):
        configure_ocr()
        self.config = load_config()
        self.api = ApiClient(self.config)
        self.root = tk.Tk()
        self.root.title(APP_NAME)
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.94)
        self.root.configure(bg="#07111f")
        self.root.geometry("126x44+20+180")
        self.game = None
        self.busy = False
        self.drag_origin = None
        self.offset = self.config.get("offset", [20, 180])
        if not isinstance(self.offset, list) or len(self.offset) != 2:
            self.offset = [20, 180]

        self.button = tk.Button(self.root, text="📷 采集", command=self.capture, bg="#4352a5", fg="white", activebackground="#5668c9", activeforeground="white", bd=0, font=("Microsoft YaHei UI", 11, "bold"), cursor="hand2")
        self.button.pack(fill="both", expand=True, padx=2, pady=2)
        for widget in (self.root, self.button):
            widget.bind("<ButtonPress-1>", self.drag_start, add="+")
            widget.bind("<B1-Motion>", self.drag_move, add="+")
            widget.bind("<ButtonRelease-1>", self.drag_end, add="+")
            widget.bind("<Button-3>", self.context_menu)
        self.menu = tk.Menu(self.root, tearoff=0)
        self.menu.add_command(label="重新绑定", command=self.rebind)
        self.menu.add_separator()
        self.menu.add_command(label="退出", command=self.quit)
        self.root.after(300, self.follow_game)
        if not self.config.get("deviceToken"):
            self.root.after(600, self.pair)

    def drag_start(self, event):
        self.drag_origin = (event.x_root, event.y_root, self.root.winfo_x(), self.root.winfo_y())

    def drag_move(self, event):
        if self.drag_origin:
            x0, y0, wx, wy = self.drag_origin
            self.root.geometry(f"+{wx + event.x_root - x0}+{wy + event.y_root - y0}")

    def drag_end(self, _):
        self.drag_origin = None
        if self.game:
            self.offset = [self.root.winfo_x() - self.game.rect[0], self.root.winfo_y() - self.game.rect[1]]
            self.config["offset"] = self.offset
        save_config(self.config)

    def context_menu(self, event):
        self.menu.tk_popup(event.x_root, event.y_root)

    def follow_game(self):
        if not self.busy:
            game = find_active_game()
            if not game and self.game and user32.IsWindow(self.game.hwnd):
                game = self.game
            if game:
                self.game = game
                x = game.rect[0] + int(self.offset[0])
                y = game.rect[1] + int(self.offset[1])
                x_part = f"+{x}" if x >= 0 else str(x)
                y_part = f"+{y}" if y >= 0 else str(y)
                self.root.geometry(f"126x44{x_part}{y_part}")
                if not self.root.winfo_viewable():
                    self.root.deiconify()
            elif not self.root.winfo_viewable():
                self.root.deiconify()
            self.root.update_idletasks()
            user32.SetWindowPos(self.root.winfo_id(), -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)
        self.root.after(350, self.follow_game)

    def pair(self):
        code = simpledialog.askstring(APP_NAME, "请在 buyali.xyz 点击“数据采集”，输入显示的 6 位配对码：", parent=self.root)
        if not code:
            return
        try:
            self.api.redeem(code)
            messagebox.showinfo(APP_NAME, "配对成功", parent=self.root)
        except ApiError as exc:
            messagebox.showerror(APP_NAME, str(exc), parent=self.root)

    def rebind(self):
        self.config.pop("deviceToken", None)
        self.config["bindings"] = {}
        self.config["windowCharacters"] = {}
        save_config(self.config)
        self.pair()

    @staticmethod
    def window_slot(game):
        left, top, right, bottom = game.rect
        return f"{left},{top},{right-left},{bottom-top}"

    def capture(self):
        if self.busy:
            return
        game = self.game or find_active_game()
        if not game:
            messagebox.showwarning(APP_NAME, "请先激活包含角色名的 AION2 游戏窗口", parent=self.root)
            return
        if not game.character:
            slot = self.window_slot(game)
            remembered = self.config.setdefault("windowCharacters", {}).get(slot)
            if remembered:
                game.character = remembered
        self.busy = True
        self.root.withdraw()
        self.root.after(140, lambda: self.capture_after_hide(game))

    def capture_after_hide(self, game):
        try:
            image = ImageGrab.grab(bbox=game.rect, all_screens=True)
            fields, scores = recognize(image)
            character_hint = recognize_character_text(image)
            image.close()
            if not fields:
                raise RuntimeError("未识别到有效数据，请确认已打开目标界面")
            threading.Thread(target=self.prepare_result, args=(game, fields, scores, character_hint), daemon=True).start()
        except Exception as exc:
            self.busy = False
            self.root.deiconify()
            messagebox.showerror(APP_NAME, f"采集失败：{exc}", parent=self.root)

    def prepare_result(self, game, fields, scores, character_hint=""):
        try:
            data = self.api.state()
            matched = match_character_hint(data, character_hint)
            if matched:
                _, character = matched
                game.character = str(character.get("name", "")).strip()
                self.config.setdefault("windowCharacters", {})[self.window_slot(game)] = game.character
                save_config(self.config)
            elif not game.character:
                if not matched:
                    game.character = self.ask_character_name(character_hint)
                self.config.setdefault("windowCharacters", {})[self.window_slot(game)] = game.character
                save_config(self.config)
            target = self.resolve_character(data, game.character)
            self.root.after(0, lambda: self.confirm_dialog(game, target, fields, scores))
        except Exception as exc:
            self.root.after(0, lambda: self.capture_error(exc))

    def ask_character_name(self, character_hint=""):
        result, ready = [], threading.Event()
        def show():
            prompt = "游戏窗口未能唯一匹配角色，请输入当前角色名（首次绑定后会记住）。"
            if character_hint:
                prompt += f"\n识别到：{character_hint}"
            value = simpledialog.askstring(APP_NAME, prompt, parent=self.root)
            if value and value.strip():
                result.append(value.strip())
            ready.set()
        self.root.after(0, show)
        ready.wait()
        if not result:
            raise ApiError("已取消角色识别")
        return result[0]

    def capture_error(self, exc):
        self.busy = False
        self.root.deiconify()
        messagebox.showerror(APP_NAME, str(exc), parent=self.root)

    def resolve_character(self, data, game_name):
        all_roles = accounts_and_characters(data)
        bindings = self.config.setdefault("bindings", {})
        bound = bindings.get(game_name)
        if bound:
            for account, character in all_roles:
                if str(account.get("id")) == str(bound["accountId"]) and str(character.get("id")) == str(bound["characterId"]):
                    return account, character
        matches = [(a, c) for a, c in all_roles if c.get("name", "").strip() == game_name]
        if len(matches) == 1:
            account, character = matches[0]
            bindings[game_name] = {"accountId": account["id"], "characterId": character["id"]}
            save_config(self.config)
            return account, character
        return self.choose_binding(data, game_name)

    def choose_binding(self, data, game_name):
        # Called from worker via a synchronized UI handoff.
        result, ready = [], threading.Event()
        def show():
            dialog = tk.Toplevel(self.root)
            dialog.title("绑定角色")
            dialog.attributes("-topmost", True)
            dialog.geometry("430x260")
            tk.Label(dialog, text=f"游戏角色：{game_name}\n请选择已有角色，或选择账号后创建新角色", justify="left").pack(padx=18, pady=14, anchor="w")
            entries = accounts_and_characters(data)
            labels = [f"{a.get('name', '未命名账号')} / {c.get('name', '未命名角色')}" for a, c in entries]
            combo = ttk.Combobox(dialog, values=labels, state="readonly", width=48)
            combo.pack(padx=18, pady=8)
            if labels: combo.current(0)
            def bind():
                if combo.current() >= 0:
                    result.append(entries[combo.current()]); dialog.destroy(); ready.set()
            def create():
                accounts = data.get("accounts", [])
                names = [a.get("name", "未命名账号") for a in accounts]
                account_name = simpledialog.askstring("创建角色", "请输入目标账号名称：", parent=dialog)
                selected = next((a for a in accounts if a.get("name") == account_name), None)
                if selected:
                    try:
                        created = self.api.create_character(selected["id"], game_name)["character"]
                        result.append((selected, created)); dialog.destroy(); ready.set()
                    except ApiError as exc: messagebox.showerror(APP_NAME, str(exc), parent=dialog)
                elif names: messagebox.showwarning(APP_NAME, "账号名称不匹配：" + "、".join(names), parent=dialog)
            row = tk.Frame(dialog); row.pack(pady=16)
            tk.Button(row, text="绑定已有角色", command=bind).pack(side="left", padx=6)
            tk.Button(row, text="创建新角色", command=create).pack(side="left", padx=6)
            dialog.protocol("WM_DELETE_WINDOW", lambda: (dialog.destroy(), ready.set()))
        self.root.after(0, show)
        ready.wait()
        if not result:
            raise ApiError("已取消角色绑定")
        account, character = result[0]
        self.config.setdefault("bindings", {})[game_name] = {"accountId": account["id"], "characterId": character["id"]}
        save_config(self.config)
        return account, character

    def confirm_dialog(self, game, target, fields, scores):
        account, character = target
        dialog = tk.Toplevel(self.root)
        dialog.title("确认采集结果")
        dialog.attributes("-topmost", True)
        dialog.geometry("380x330")
        tk.Label(dialog, text=f"账号：{account.get('name')}\n角色：{character.get('name')}", font=("Microsoft YaHei UI", 11, "bold"), justify="left").pack(anchor="w", padx=20, pady=14)
        entries = {}
        form = tk.Frame(dialog); form.pack(fill="x", padx=20)
        for key, value in fields.items():
            row = tk.Frame(form); row.pack(fill="x", pady=4)
            tk.Label(row, text=FIELD_LABELS[key], width=10, anchor="w").pack(side="left")
            entry = tk.Entry(row); entry.insert(0, str(value)); entry.pack(side="left", fill="x", expand=True)
            entries[key] = entry
        reliable = all(scores.get(key, 0) >= 80 for key in fields)
        status = tk.Label(dialog, text="", fg="#3267b1"); status.pack(pady=12)
        remaining = [5]

        def cancel():
            dialog.destroy(); self.busy = False; self.root.deiconify()
        def submit():
            try:
                edited = {key: int(entry.get().replace(",", "")) for key, entry in entries.items()}
            except ValueError:
                messagebox.showerror(APP_NAME, "请输入有效整数", parent=dialog); return
            payload = {"accountId": account["id"], "characterId": character["id"], "characterName": game.character, "windowTitle": game.title, "fields": edited}
            dialog.destroy()
            threading.Thread(target=self.apply_result, args=(payload, edited, game.character), daemon=True).start()
        def tick():
            if not dialog.winfo_exists(): return
            if not reliable:
                status.config(text="部分数据需要确认，已暂停自动写入", fg="#b45309"); return
            status.config(text=f"{remaining[0]} 秒后自动确认写入")
            if remaining[0] == 0: submit(); return
            remaining[0] -= 1; dialog.after(1000, tick)
        row = tk.Frame(dialog); row.pack(side="bottom", pady=18)
        tk.Button(row, text="取消", command=cancel, width=12).pack(side="left", padx=5)
        tk.Button(row, text="立即确认", command=submit, width=12, bg="#4352a5", fg="white").pack(side="left", padx=5)
        dialog.protocol("WM_DELETE_WINDOW", cancel)
        tick()

    def apply_result(self, payload, fields, character):
        try:
            result = self.api.apply(payload)
            self.root.after(0, lambda: self.success_dialog(result["transactionId"], fields, character))
        except Exception as exc:
            self.root.after(0, lambda: self.capture_error(exc))

    def success_dialog(self, transaction_id, fields, character):
        dialog = tk.Toplevel(self.root); dialog.title("采集成功"); dialog.attributes("-topmost", True); dialog.geometry("330x260")
        tk.Label(dialog, text="✓ 已写入", fg="#16803a", font=("Microsoft YaHei UI", 15, "bold")).pack(pady=14)
        tk.Label(dialog, text="当前角色：" + character).pack()
        tk.Label(dialog, text="\n".join(f"{FIELD_LABELS[k]}：{v:,}" for k, v in fields.items()), justify="left").pack(pady=10)
        status = tk.Label(dialog); status.pack(pady=7)
        remaining = [8]
        def finish():
            if dialog.winfo_exists(): dialog.destroy()
            self.busy = False; self.root.deiconify()
        def undo():
            try:
                self.api.undo(transaction_id)
                self.root.after(0, lambda: (messagebox.showinfo(APP_NAME, "已撤回本次采集写入", parent=dialog), finish()))
            except ApiError as exc:
                self.root.after(0, lambda: messagebox.showerror(APP_NAME, str(exc), parent=dialog))
        button = tk.Button(dialog, text="撤回", command=lambda: threading.Thread(target=undo, daemon=True).start(), width=14); button.pack()
        def tick():
            if not dialog.winfo_exists(): return
            status.config(text=f"{remaining[0]} 秒内可撤回")
            if remaining[0] == 0: finish(); return
            remaining[0] -= 1; dialog.after(1000, tick)
        dialog.protocol("WM_DELETE_WINDOW", finish); tick()

    def quit(self):
        self.config["offset"] = self.offset; save_config(self.config); self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    kernel32 = ctypes.windll.kernel32
    mutex = kernel32.CreateMutexW(None, False, "Local\\BuyaliCollector-1.3.4.1")
    if kernel32.GetLastError() == 183:
        user32.MessageBoxW(None, "数据采集助手已经在运行。", APP_NAME, 0x40)
        sys.exit(0)
    CollectorApp().run()
