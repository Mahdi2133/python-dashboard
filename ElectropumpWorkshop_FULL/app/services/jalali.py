"""Jalali ⇄ Gregorian conversion.

Storage standard (requirement 16): every date column in the database holds a
**Gregorian ISO date**; the UI is always Jalali. The Jalali parts the operator
typed are additionally kept on the record (``j_year/j_month/j_day``) so an
imported partial date is never silently "corrected".

The algorithm is the standard Birashk-free arithmetic conversion via Julian
Day Number, so no external dependency is needed inside the EXE.
"""
from __future__ import annotations

import datetime as _dt
import re

MONTHS_FA = ["", "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
             "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]
WEEKDAYS_FA = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه"]
FA_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
AR_DIGITS = "٠١٢٣٤٥٦٧٨٩"

# Borkowski's 33-year-cycle breaks — the algorithm behind jalaali-js and
# jdatetime. Accurate for Jalali years 1178..1633, which covers every date
# this system can ever hold.
_BREAKS = [-61, 9, 38, 199, 426, 686, 756, 818, 1111, 1181, 1210,
           1635, 2060, 2097, 2192, 2262, 2324, 2394, 2456, 3178]


def _jal_cal(jy: int):
    """Return (leap_offset, gregorian_year, march_day_of_1_farvardin)."""
    if jy < _BREAKS[0] or jy >= _BREAKS[-1]:
        raise ValueError(f"سال شمسی خارج از محدوده پشتیبانی‌شده: {jy}")
    gy = jy + 621
    leap_j = -14
    jp = _BREAKS[0]
    jump = 0
    for jm in _BREAKS[1:]:
        jump = jm - jp
        if jy < jm:
            break
        leap_j += (jump // 33) * 8 + (jump % 33) // 4
        jp = jm
    n = jy - jp
    leap_j += (n // 33) * 8 + ((n % 33) + 3) // 4
    if jump % 33 == 4 and jump - n == 4:
        leap_j += 1
    leap_g = gy // 4 - ((gy // 100 + 1) * 3) // 4 - 150
    march = 20 + leap_j - leap_g
    if jump - n < 6:
        n = n - jump + ((jump + 4) // 33) * 33
    leap = ((n + 1) % 33 - 1) % 4
    if leap == -1:
        leap = 4
    return leap, gy, march


def is_leap_jalali(jy: int) -> bool:
    return _jal_cal(int(jy))[0] == 0


def jalali_month_days(jy: int, jm: int) -> int:
    jm = int(jm)
    if jm <= 6:
        return 31
    if jm <= 11:
        return 30
    return 30 if is_leap_jalali(jy) else 29


def _g2jdn(gy: int, gm: int, gd: int) -> int:
    a = (14 - gm) // 12
    y = gy + 4800 - a
    m = gm + 12 * a - 3
    return gd + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100 + y // 400 - 32045


def _jdn2g(jdn: int):
    a = jdn + 32044
    b = (4 * a + 3) // 146097
    c = a - (146097 * b) // 4
    d = (4 * c + 3) // 1461
    e = c - (1461 * d) // 4
    m = (5 * e + 2) // 153
    day = e - (153 * m + 2) // 5 + 1
    month = m + 3 - 12 * (m // 10)
    year = 100 * b + d - 4800 + m // 10
    return year, month, day


def _j2jdn(jy: int, jm: int, jd: int) -> int:
    _, gy, march = _jal_cal(jy)
    return _g2jdn(gy, 3, march) + (jm - 1) * 31 - (jm // 7) * (jm - 7) + jd - 1


def _jdn2j(jdn: int):
    gy = _jdn2g(jdn)[0]
    jy = gy - 621
    leap, _, march = _jal_cal(jy)
    k = jdn - _g2jdn(gy, 3, march)
    if k >= 0:
        if k <= 185:
            return jy, 1 + k // 31, 1 + k % 31
        k -= 186
    else:
        # Before Nowruz: the day belongs to the previous Jalali year, whose
        # length depends on the leap flag computed above (not the new jy).
        jy -= 1
        k += 179
        if leap == 1:
            k += 1
    return jy, 7 + k // 30, 1 + k % 30


def jalali_to_gregorian(jy: int, jm: int, jd: int) -> _dt.date:
    return _dt.date(*_jdn2g(_j2jdn(int(jy), int(jm), int(jd))))


def gregorian_to_jalali(d: _dt.date):
    return _jdn2j(_g2jdn(d.year, d.month, d.day))


def normalize_digits(text: str) -> str:
    """Turn Persian/Arabic-Indic digits into ASCII so parsing is uniform."""
    if not text:
        return text
    out = []
    for ch in str(text):
        i = FA_DIGITS.find(ch)
        if i < 0:
            i = AR_DIGITS.find(ch)
        out.append(str(i) if i >= 0 else ch)
    return "".join(out)


_DATE_RE = re.compile(r"^\s*(\d{2,4})\s*[/\-.]\s*(\d{1,2})\s*[/\-.]\s*(\d{1,2})\s*$")


def parse_jalali(text) -> tuple[int, int, int] | None:
    """Parse '1404/01/05', '۱۴۰۴-۱-۵' or the sheets' 2-digit '99/01/01'."""
    if text in (None, ""):
        return None
    if isinstance(text, (_dt.date, _dt.datetime)):
        return gregorian_to_jalali(text.date() if isinstance(text, _dt.datetime) else text)
    m = _DATE_RE.match(normalize_digits(str(text)))
    if not m:
        return None
    y, mo, d = (int(g) for g in m.groups())
    # The older sheets abbreviate the year: '99/01/01' and '400/01/06' both
    # occur and both mean a 14th-century Jalali year.
    if y < 100:
        y += 1400 if y < 50 else 1300
    elif y < 1000:
        y += 1000
    if not (1 <= mo <= 12) or not (1 <= d <= 31):
        return None
    if d > jalali_month_days(y, mo):
        return None
    return y, mo, d


def parse_jalali_to_date(text) -> _dt.date | None:
    parts = parse_jalali(text)
    if not parts:
        return None
    try:
        return jalali_to_gregorian(*parts)
    except (ValueError, OverflowError):
        return None


# Iran dropped daylight saving in 2022, so its offset is a constant +03:30.
TEHRAN_OFFSET = _dt.timedelta(hours=3, minutes=30)
TEHRAN_TZ = _dt.timezone(TEHRAN_OFFSET, "Asia/Tehran")


def local_now() -> _dt.datetime:
    """The moment to stamp on a row: the workshop PC's own wall clock.

    Timestamps used to be written with ``datetime.utcnow()`` and shifted by
    +03:30 when shown. That is only right while Windows' *timezone* is set to
    Tehran — and on a workshop PC it often is not, even though the clock on the
    taskbar reads correctly. The shift then lands the login hours away from
    what the operator saw, which is exactly the 8pm login this replaces.

    Storing the wall clock removes the dependency altogether: the number in the
    database is the number on the clock, and displaying it needs no arithmetic
    that could be wrong. This is a single-site application in one timezone
    without daylight saving, so there is nothing an absolute UTC instant would
    buy back.
    """
    return _dt.datetime.now()


def to_tehran(value):
    """Render a stored timestamp on the clock it was written against.

    Naive values are already wall-clock and pass straight through; an aware one
    (an older row, or a caller that built its own) is converted to Tehran and
    stripped, so everything downstream compares like with like.
    """
    if value is None:
        return None
    if not isinstance(value, _dt.datetime):
        return value
    if value.tzinfo is None:
        return value
    return value.astimezone(TEHRAN_TZ).replace(tzinfo=None)


def tehran_now() -> _dt.datetime:
    return local_now()


def tehran_time_str(value, with_seconds: bool = True) -> str:
    """HH:MM[:SS] on the local clock."""
    local = to_tehran(value)
    if local is None:
        return ""
    return local.strftime("%H:%M:%S" if with_seconds else "%H:%M")


def to_jalali_str(value, with_month_name: bool = False, sep: str = "/") -> str:
    """Jinja filter: render a stored Gregorian date in Jalali.

    A datetime is taken on the local clock, so the Jalali day matches the day
    the operator actually saw.
    """
    if value in (None, ""):
        return ""
    if isinstance(value, _dt.datetime):
        value = to_tehran(value).date()
    if not isinstance(value, _dt.date):
        return str(value)
    jy, jm, jd = gregorian_to_jalali(value)
    if with_month_name:
        return f"{jd} {MONTHS_FA[jm]} {jy}"
    return f"{jy}{sep}{jm:02d}{sep}{jd:02d}"


def jalali_parts_to_date(jy, jm, jd):
    """Best-effort date from possibly-missing Jalali parts (day defaults to 1)."""
    try:
        jy = int(jy)
        jm = int(jm) if jm else 1
        jd = int(jd) if jd else 1
    except (TypeError, ValueError):
        return None
    if not (1300 <= jy <= 1500 and 1 <= jm <= 12):
        return None
    jd = min(max(jd, 1), jalali_month_days(jy, jm))
    try:
        return jalali_to_gregorian(jy, jm, jd)
    except (ValueError, OverflowError):
        return None


def today_jalali() -> tuple[int, int, int]:
    return gregorian_to_jalali(_dt.date.today())


def jalali_year_bounds(jy: int) -> tuple[_dt.date, _dt.date]:
    return jalali_to_gregorian(jy, 1, 1), jalali_to_gregorian(jy, 12, jalali_month_days(jy, 12))


def jalali_month_bounds(jy: int, jm: int) -> tuple[_dt.date, _dt.date]:
    return jalali_to_gregorian(jy, jm, 1), jalali_to_gregorian(jy, jm, jalali_month_days(jy, jm))
