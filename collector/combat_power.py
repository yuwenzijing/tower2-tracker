from __future__ import annotations

import re


_COMBAT_POWER_PATTERN = re.compile(r"((?:\d{1,3}(?:,\d{3})+|\d{1,4})(?:\.\d{1,3})?)([KkMm])")


def parse_combat_power(text: str) -> tuple[float, str] | None:
    """Parse a displayed K/M value while preserving its source unit."""
    clean = re.sub(r"\s+", "", str(text))
    match = _COMBAT_POWER_PATTERN.fullmatch(clean)
    if not match:
        return None
    unit = match.group(2).upper()
    digits = 3 if unit == "M" else 2
    value = round(float(match.group(1).replace(",", "")), digits)
    return (value, unit)


def power_to_k(value: float, unit: str = "K") -> float:
    return round(float(value) * (1000 if str(unit).upper() == "M" else 1), 6)


def combat_power_delta(before: float, before_unit: str, after: float, after_unit: str) -> float:
    """Return the difference in K, regardless of either displayed unit."""
    return round(power_to_k(after, after_unit) - power_to_k(before, before_unit), 6)


def format_combat_delta(magnitude: float, unit: str = "K") -> str:
    """Format a normalized delta in K (unit arg retained for compatibility)."""
    del unit
    return f"{abs(float(magnitude)):,.2f}".rstrip("0").rstrip(".") + "K"


def format_combat_power(value: float, unit: str = "K") -> str:
    unit = str(unit).upper()
    digits = 3 if unit == "M" else 2
    return f"{float(value):,.{digits}f}".rstrip("0").rstrip(".") + unit
