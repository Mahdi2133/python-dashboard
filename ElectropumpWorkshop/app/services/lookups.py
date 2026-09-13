"""Resolving a submitted or imported value onto a lookup option."""
import logging
import re

from ..extensions import db
from ..models import LookupAlias, LookupCategory, LookupItem

log = logging.getLogger(__name__)

_ARABIC_MAP = str.maketrans({"ي": "ی", "ك": "ک", "ة": "ه", "ۀ": "ه",
                             "‌": " ", "‏": "", "‎": ""})


def normalize_text(value) -> str:
    """Fold the spelling noise the real spreadsheet is full of."""
    if value is None:
        return ""
    text = str(value).translate(_ARABIC_MAP)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _fold(value: str) -> str:
    return normalize_text(value).replace(" ", "").lower()


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
