"""Resolving a submitted or imported value onto a lookup option."""
import logging
import re

from ..extensions import db
from ..models import LookupAlias, LookupCategory, LookupItem

log = logging.getLogger(__name__)

# ZWNJ is deliberately NOT folded away here: it is meaningful in Persian
# ("می‌رود" is not "می رود") and this function also normalises text that is
# about to be *stored* and shown back to the user. Matching strips it instead,
# in fold_persian().
_ARABIC_MAP = str.maketrans({"ي": "ی", "ك": "ک", "ة": "ه", "ۀ": "ه",
                             "‏": "", "‎": ""})


def normalize_text(value) -> str:
    """Fold the spelling noise the real spreadsheet is full of."""
    if value is None:
        return ""
    text = str(value).translate(_ARABIC_MAP)
    text = re.sub(r"\s+", " ", text).strip()
    return text


_ALEF_MAP = str.maketrans({"آ": "ا", "أ": "ا", "إ": "ا", "ٱ": "ا",
                           "ؤ": "و", "ئ": "ی", "ى": "ی"})
_HARAKAT = re.compile(r"[\u064B-\u065F\u0670\u0640]")


def fold_persian(value) -> str:
    """Aggressive fold for matching two spellings of the same Persian name.

    Beyond ``normalize_text`` this also collapses the alef family (آ/أ/إ → ا),
    hamze carriers (ئ → ی), harakat and every kind of space or dash. Persian
    data entry treats these as interchangeable — «آزاد شهر» and «ازاد شهر» are
    one well — so matching must too.
    """
    text = normalize_text(value).translate(_ALEF_MAP)
    text = _HARAKAT.sub("", text)
    return re.sub(r"[\s\u200c_\-]+", "", text).lower()


def _fold(value: str) -> str:
    return fold_persian(value)


# ── well names ───────────────────────────────────────────────────────────────
# Well registers spell the index of a well either as a digit or as a word, so
# «ده غیبی 1» and «ده غیبی یک» are one well entered twice. Only a *trailing*
# word is treated as an index: «ده سرخ», «چهار فصل» and «سه راه دانش» all carry
# a number word that is part of the name itself, and folding those would merge
# genuinely different wells.
_INDEX_WORDS = {
    "صفر": 0, "یک": 1, "اول": 1, "یکم": 1, "دو": 2, "دوم": 2, "سه": 3, "سوم": 3,
    "چهار": 4, "چهارم": 4, "پنج": 5, "پنجم": 5, "شش": 6, "شیش": 6, "ششم": 6,
    "هفت": 7, "هفتم": 7, "هشت": 8, "هشتم": 8, "نه": 9, "نهم": 9,
    # «ده» is deliberately absent. In this register every tenth well is written
    # «... 10»; the word only ever turns up meaning *village* — «ده سرخ»,
    # «ده غیبی», «جمال ده» — so reading it as an index invents duplicates.
    "یازده": 11, "دوازده": 12, "سیزده": 13, "چهارده": 14,
    "پانزده": 15, "پونزده": 15, "شانزده": 16, "شونزده": 16, "هفده": 17,
    "هیفده": 17, "هجده": 18, "هیجده": 18, "نوزده": 19, "بیست": 20,
}
_INDEX_WORDS = {fold_persian(k): v for k, v in _INDEX_WORDS.items()}

# Qualifiers that sit *after* the index («ابوطالب یک قدیم»), so the index is
# the last token before them rather than the last token outright.
_NAME_SUFFIXES = {fold_persian(s) for s in ("قدیم", "قدیمی", "جدید", "نو")}

_PUNCT = re.compile(r"[()\[\]{}«»\"'`.,،؛;:/\\|]+")


def pm_digits(code) -> str:
    """A PM code reduced to its digits, for comparing across spellings.

    The register is published twice, once as «10/24/41» and once as «102441».
    Only ever use this together with the کلاسه (see deduplicate_wells): on its
    own the digits are not quite unique.
    """
    return re.sub(r"\D", "", str(code or ""))


def well_key(value) -> str:
    """The identity of a well name, for matching only — never for display.

    On top of ``fold_persian`` this drops punctuation, turns Persian digits
    into ASCII and rewrites a trailing index word as its digit, so the picker
    cannot offer «ده غیبی یک» and «ده غیبی 1» as two different wells. It is
    deliberately conservative: a name whose number word is not in the index
    position is left alone, and callers still refuse to merge two wells whose
    PM codes disagree, because the register's own key outranks any spelling
    rule.
    """
    from .jalali import normalize_digits

    text = _PUNCT.sub(" ", normalize_digits(normalize_text(value)))
    tokens = [t for t in text.split() if t]
    if not tokens:
        return ""
    last = len(tokens) - 1
    while last > 0 and fold_persian(tokens[last]) in _NAME_SUFFIXES:
        last -= 1
    # ``last > 0`` keeps a well actually called «ده» from becoming «10».
    if last > 0:
        digit = _INDEX_WORDS.get(fold_persian(tokens[last]))
        if digit is not None:
            tokens[last] = str(digit)
    return fold_persian(" ".join(tokens))




def get_category(code: str) -> LookupCategory | None:
    return LookupCategory.query.filter_by(code=code).one_or_none()


def resolve_item(category_code: str, value, create_missing: bool = False,
                 adhoc_note: str | None = None) -> LookupItem | None:
    """Find the option for ``value`` in ``category_code``.

    Matching goes: exact value → alias → case/space-insensitive fold. When
    nothing matches and ``create_missing`` is set (import path), a new option
    is added as **inactive + ad-hoc** so the imported row keeps its meaning and
    the admin can later merge or activate it. Nothing is ever discarded.
    """
    text = normalize_text(value)
    if not text:
        return None
    cat = get_category(category_code)
    if cat is None:
        log.warning("Unknown lookup category %r", category_code)
        return None

    item = LookupItem.query.filter_by(category_id=cat.id, value=text).one_or_none()
    if item is not None:
        return item

    alias = (LookupAlias.query
             .filter_by(category_id=cat.id, alias=text).one_or_none())
    if alias is not None:
        return alias.item

    folded = _fold(text)
    for candidate in cat.items:
        if _fold(candidate.value) == folded or _fold(candidate.label) == folded:
            return candidate
    for al in LookupAlias.query.filter_by(category_id=cat.id).all():
        if _fold(al.alias) == folded:
            return al.item

    if not create_missing:
        return None

    max_order = max([i.sort_order for i in cat.items], default=0)
    item = LookupItem(
        category_id=cat.id, value=text, label=text, sort_order=max_order + 1,
        is_active=False, is_adhoc=True,
        notes=adhoc_note or "به‌صورت خودکار هنگام ورود داده ایجاد شد؛ نیازمند بازبینی مدیر.",
    )
    db.session.add(item)
    db.session.flush()
    log.info("Ad-hoc lookup option created: %s/%s", category_code, text)
    return item


def resolve_id(category_code: str, value, create_missing: bool = False):
    item = resolve_item(category_code, value, create_missing=create_missing)
    return item.id if item else None


def items_by_category(active_only: bool = True) -> dict:
    """{category_code: [item dicts]} — one query for the whole form."""
    out = {}
    for cat in LookupCategory.query.order_by(LookupCategory.sort_order).all():
        items = sorted((i for i in cat.items if i.is_active or not active_only),
                       key=lambda i: (i.sort_order, i.id))
        out[cat.code] = [i.to_dict() for i in items]
    return out
