"""One way to write an electropump: «384/10+73.5».

The number before the slash is the pump type, the one after it the number of
stages, and the one after the plus the motor's power in kW. Every place that
shows a whole electropump — the forms, the catalogue, the reference databases,
the reports — goes through these two functions, so the format is the same
everywhere and a label typed by hand («384 / 10 + 73.5», «63+345/8»,
«293 (9)» with «9A (30)») is read back into its three parts.
"""
from __future__ import annotations

import re

_FA_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩٫", "01234567890123456789.")


def fmt_num(value) -> str:
    """73.5 → «73.5», 30.0 → «30», «9A» stays «9A»."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(int(value))
    if isinstance(value, (int, float)):
        return f"{float(value):g}"
    text = str(value).strip().translate(_FA_DIGITS)
    try:
        return f"{float(text):g}"
    except ValueError:
        return text


def electropump_label(pump_type, stages=None, motor_kw=None) -> str | None:
    """«384/10+73.5»; whatever parts are known, in that order."""
    t, s, m = fmt_num(pump_type), fmt_num(stages), fmt_num(motor_kw)
    if not re.search(r"[0-9A-Za-z]", t):
        return None
    out = t + (f"/{s}" if s else "")
    return out + (f"+{m}" if m else "")


_FULL = re.compile(r"^(\d{2,4}[a-z]*)/(\d+[a-z]?(?:\([^)]*\))?)\+(\d+(?:\.\d+)?)", re.I)
_REVERSED = re.compile(r"^(\d+(?:\.\d+)?)\+(\d{2,4}[a-z]*)/(\d+[a-z]?)$", re.I)
_PARTIAL = re.compile(r"^(\d{2,4}[a-z]*)/(\d+[a-z]?)$", re.I)
_PAREN = re.compile(r"^([0-9a-z]+)\s*\(\s*(\d+(?:\.\d+)?[a-z]?)\s*\)$", re.I)


def parse_electropump_label(text):
    """(pump type, stages, motor kW) out of a label, each None when absent."""
    if text in (None, ""):
        return None, None, None
    s = str(text).translate(_FA_DIGITS).replace(" ", "").replace("‌", "")
    m = _FULL.match(s)
    if m:
        return m.group(1).upper(), m.group(2).lower(), float(m.group(3))
    m = _REVERSED.match(s)
    if m:
        return m.group(2).upper(), m.group(3).lower(), float(m.group(1))
    m = _PARTIAL.match(s)
    if m:
        return m.group(1).upper(), m.group(2).lower(), None
    return None, None, None


def parse_paren(text):
    """«293 (9)» → («293», «9»); «9A (30)» → («9A», «30»)."""
    if text in (None, ""):
        return None, None
    s = str(text).translate(_FA_DIGITS).strip()
    if not re.search(r"[0-9A-Za-z]", s):      # «()», «-», «/» — an empty cell
        return None, None
    m = _PAREN.match(s)
    if m:
        return m.group(1).upper(), m.group(2)
    return s, None
