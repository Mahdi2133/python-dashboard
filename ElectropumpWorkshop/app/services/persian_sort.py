"""Persian alphabetical order for SQLite sorting.

SQLite compares text by code point, which puts «پ چ ژ گ» after «ی» and
Arabic «ي ك» away from their Persian twins. The ``fa`` collation fixes that:
it follows the Persian alphabet, treats the Arabic letter forms as the Persian
ones, and compares runs of digits (Persian, Arabic or Latin) as numbers, so
«چاه ۲» comes before «چاه ۱۰».

Registered on every SQLite connection in ``app._sqlite_pragmas``; a sort column
opts in with ``.collate("fa")``.
"""
from __future__ import annotations

import re
from functools import lru_cache

COLLATION = "fa"

_ALPHABET = ("ا آ ب پ ت ث ج چ ح خ د ذ ر ز ژ س ش ص ض ط ظ ع غ ف ق ک گ ل م ن و ه ی").split()
_RANK = {ch: i for i, ch in enumerate(_ALPHABET)}
# letter forms that sort as one Persian letter
_SAME = {"أ": "ا", "إ": "ا", "ٱ": "ا", "ء": "ا", "ؤ": "و", "ئ": "ی", "ي": "ی",
         "ى": "ی", "ك": "ک", "ة": "ه", "ۀ": "ه"}
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_SKIP = {"‌", "‍", "ً", "ٌ", "ٍ", "َ", "ُ",
         "ِ", "ّ", "ْ", "ـ"}  # ZWNJ, harakat, tatweel
_TOKEN = re.compile(r"\d+|\s+|.", re.S)


@lru_cache(maxsize=20000)
def fa_key(text: str) -> tuple:
    """A sort key: spaces < numbers < Persian letters < everything else."""
    text = (text or "").translate(_DIGITS)
    key = []
    for tok in _TOKEN.findall(text):
        if tok.isspace():
            key.append((0, 0))
        elif tok.isdigit():
            key.append((1, int(tok)))
        elif tok in _SKIP:
            continue
        else:
            ch = _SAME.get(tok, tok)
            if ch in _RANK:
                key.append((2, _RANK[ch]))
            else:
                key.append((3, ord(ch.lower())))
    return tuple(key)


def fa_collate(a: str, b: str) -> int:
    ka, kb = fa_key(a), fa_key(b)
    if ka == kb:
        return (a > b) - (a < b)
    return -1 if ka < kb else 1
