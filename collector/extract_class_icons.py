"""Extract the existing web profession icons for the desktop collector build."""

from __future__ import annotations

import base64
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "public" / "index.html"
OUTPUT = Path(__file__).resolve().parent / "assets" / "classes"


def main() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    block = re.search(r"const CLASS_ICONS = \{(.*?)\n\};", source, re.S)
    if not block:
        raise RuntimeError("CLASS_ICONS was not found")
    icons = re.findall(r"'([^']+)'\s*:\s*'data:image/webp;base64,([^']+)'", block.group(1))
    if not icons:
        raise RuntimeError("No profession icons were found")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for key, payload in icons:
        (OUTPUT / f"{key}.webp").write_bytes(base64.b64decode(payload))
    print(f"Extracted {len(icons)} profession icons to {OUTPUT}")


if __name__ == "__main__":
    main()
