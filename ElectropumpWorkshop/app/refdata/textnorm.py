"""Reading Persian spreadsheets the same way every time.

The source workbooks were typed on different machines over several years:
Arabic «ي/ك» next to Persian «ی/ک», right-to-left marks inside words
(«داده‏هاي»), Persian digits, dates as «1403/10/16», «1405.05.23» or
14050523, numbers stored as text. Everything that compares a label, a well
name or reads a value goes through here.
"""
from __future__ import annotations

import math
import re

_CHARS = str.maketrans({
    "ي": "ی", "ى": "ی", "ئ": "ی", "ك": "ک", "ة": "ه", "ۀ": "ه",
    "أ": "ا", "إ": "ا", "ٱ": "ا", "ؤ": "و",
    "‌": " ", "‏": " ", "‎": " ", "‍": "", "\xa0": " ",
    "﻿": "",
})
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩٫", "01234567890123456789.")
_MARKS = re.compile(r"[ً-ٰٟـ]")     # harakat, shadda, tatweel
_SPACES = re.compile(r"\s+")
_PARENS = re.compile(r"\([^)]*\)")


def norm_text(value) -> str:
    """Unified letters and digits, single spaces; '' for None."""
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    text = str(value).translate(_CHARS).translate(_DIGITS)
    text = _MARKS.sub("", text)
    return _SPACES.sub(" ", text).strip()


def norm_label(value) -> str:
    """A label to compare: no units in brackets, no trailing colon."""
    text = _PARENS.sub(" ", norm_text(value))
    text = text.replace("تیب", "تیپ").replace("ولتاز", "ولتاژ").replace("آمبر", "آمپر")
    text = text.strip(" :：-")
    return _SPACES.sub(" ", text).strip().lower()


def name_key(value) -> str:
    """A well name to match on: «صدف2» = «صدف 2» = «صَدَف ۲»."""
    text = norm_text(value).replace("آ", "ا").lower()
    return re.sub(r"[\s\-_.,()\[\]/\\«»\"']+", "", text)


def to_float(value):
    """A number out of a cell, or None («-», «ـ», «&», blank, text)."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        f = float(value)
        return None if math.isnan(f) or math.isinf(f) else f
    text = norm_text(value).replace(",", "").replace(" ", "")
    if re.fullmatch(r"-?\d+(\.\d+)?", text):
        return float(text)
    return None


def to_text(value):
    if value is None:
        return None
    if isinstance(value, float):
        if math.isnan(value):
            return None
        if value.is_integer():
            return str(int(value))
        return f"{value:g}"
    text = norm_text(value)
    return text or None


_DATE_SEP = re.compile(r"(1[34]\d{2})\s*[/.\-_]\s*(\d{1,2})\s*[/.\-_]\s*(\d{1,2})")
_DATE_RUN = re.compile(r"(?<!\d)(1[34]\d{2})(\d{2})(\d{2})(?!\d)")


def to_jdate(value):
    """«1403/10/16» out of any of the ways a Jalali date was written."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not value.is_integer():
            return None
        value = str(int(value))
    text = norm_text(value)
    for rx in (_DATE_SEP, _DATE_RUN):
        m = rx.search(text)
        if m:
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if 1 <= mo <= 12 and 1 <= d <= 31:
                return f"{y}/{mo:02d}/{d:02d}"
    return None


def jdate_num(jdate) -> int | None:
    """«1403/10/16» → 14031016, for sorting and «the latest»."""
    if not jdate:
        return None
    try:
        y, m, d = (int(x) for x in str(jdate).split("/"))
        return y * 10000 + m * 100 + d
    except ValueError:
        return None


def year_of(value):
    f = to_float(value)
    if f is not None and 1300 <= f <= 1500:
        return int(f)
    d = to_jdate(value)
    return int(d[:4]) if d else None
