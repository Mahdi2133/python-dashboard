"""Which well of the main register a reference row is about.

The sources share codes with the register: production, videometry and the
flow-measurement records carry «کد تاسیس» (the register's PM code, e.g.
10/21/4); the flow-test sheets carry «کلاسه چاه» (the register's well class)
and the well's name. The rules, in order:

* an active well always wins over its merged or «قدیم» copy, which keep the
  same codes but are hidden from the forms;
* a PM code decides on its own;
* a class and a name that point to the same well decide;
* a name that is a proper well of the register (with a class or a centre)
  beats a class that belongs to a different well — a sheet copied from
  another well's form keeps that well's class, but the operator writes the
  name of the well tested («سوران 8» with the class of «سپاد 1»);
* a class alone decides, unless its well sits in another office and shares
  not a word with the name written on the sheet — then it is not trusted;
* a name alone decides when it is unique (the office breaks a tie); the
  whole name before the name without its note, so «سوران 3 قدیم» is the
  register's old well of that name when it has one.

Names are compared without spaces, diacritics, Arabic/Persian letter
differences or a trailing «(…)» note, and through the register's aliases.
A row that stays ambiguous is left unlinked — it can be linked by hand on
the reference-data page — rather than linked to a guess.
"""
from __future__ import annotations

import re

from .textnorm import name_key as _name_key, norm_text

_PAREN = re.compile(r"\s*\([^)]*\)\s*")


def name_key(value) -> str:
    """textnorm's key, without the marks typed into some sheets («#ده غیبی 1»)."""
    return re.sub(r"[#*+]", "", _name_key(value))


def _strip_note(name) -> str:
    """«سوران 2 (10/27/100148)» → «سوران 2»; «… - قدیم» loses the «قدیم».
    «(شهرداری)» stays: a municipal well is not the company's well of that name."""
    raw = str(name or "")
    if "شهرداری" in raw:
        return raw.strip()
    text = _PAREN.sub(" ", raw)
    text = re.sub(r"[-–]\s*قدیم\s*$", "", text.strip())
    return text.strip()


def _tokens(name) -> set:
    """The words and numbers of a name: «صدف1» → {صدف, 1}."""
    text = norm_text(name or "").replace("ئ", "ی")
    return {t for t in re.findall(r"[^\W\d_]+|\d+", text) if len(t) > 1 or t.isdigit()}


def _similar(a, b) -> bool:
    """Two names that share a word, or the first letters («نیروهوایی» and
    «نیرو هوائی 2») — enough to say a code and a name may be the same well."""
    if _tokens(a) & _tokens(b):
        return True
    ka, kb = name_key(a).replace("ئ", "ی"), name_key(b).replace("ئ", "ی")
    n = 0
    while n < min(len(ka), len(kb)) and ka[n] == kb[n]:
        n += 1
    return n >= 4 or (len(ka) >= 4 and (ka in kb or kb in ka))


def _real_class(value) -> bool:
    """«518445» is a class; «ندارد», «-», «...» and a stray «1» are blanks."""
    return sum(ch.isdigit() for ch in str(value or "")) >= 4


class WellIndex:
    def __init__(self):
        from ..models import LookupItem, Well, WellAlias
        self.by_pm, self.by_class, self.by_name = {}, {}, {}
        self.info = {}
        centers = {i.id: name_key(i.value) for i in LookupItem.query.all()}
        for w in Well.query.all():
            active = bool(w.is_active)
            self.info[w.id] = {"active": active, "center": centers.get(w.center_id),
                               "name": w.name,
                               "proper": active and bool(w.well_class or w.center_id)}
            if w.pm_code:
                self.by_pm.setdefault(norm_text(w.pm_code), []).append(w.id)
            if _real_class(w.well_class):
                self.by_class.setdefault(_class_key(w.well_class), []).append(w.id)
            keys = {name_key(w.name), name_key(_strip_note(w.name))}
            self.info[w.id]["keys"] = keys
            for key in keys:
                if key:
                    self.by_name.setdefault(key, set()).add(w.id)
        try:
            for a in WellAlias.query.all():
                alias = getattr(a, "alias", None) or getattr(a, "name", None)
                if alias and a.well_id in self.info:
                    self.by_name.setdefault(name_key(alias), set()).add(a.well_id)
        except Exception:  # noqa: BLE001 — aliases are a help, never required
            pass

    # ── helpers ──────────────────────────────────────────────────────────
    def _in_center(self, wid, center) -> bool:
        ck, cen = name_key(center or ""), self.info[wid]["center"]
        return bool(ck and cen and (ck in cen or cen in ck))

    def _narrow(self, ids, center):
        """Active wells first, then those of the office, if that leaves any."""
        ids = sorted(set(ids))
        live = [i for i in ids if self.info[i]["active"]] or ids
        if center:
            here = [i for i in live if self._in_center(i, center)]
            if here:
                live = here
        return live

    def _pick(self, ids, center):
        """One well out of wells that share a code (the first, if still several)."""
        live = self._narrow(ids, center)
        return live[0] if live else None

    def _unique(self, ids, center):
        """One well out of wells that share a name — or none if it stays ambiguous."""
        live = self._narrow(ids, center)
        return live[0] if len(live) == 1 else None

    def _names(self, name) -> set:
        if not name:
            return set()
        return (self.by_name.get(name_key(name)) or set()) | \
            (self.by_name.get(name_key(_strip_note(name))) or set())

    # ── the match ────────────────────────────────────────────────────────
    def match(self, *, pm_code=None, well_class=None, name=None, center=None):
        """(main well id, how) or (None, None)."""
        if pm_code:
            hit = self._pick(self.by_pm.get(norm_text(pm_code)) or [], center)
            if hit:
                return hit, "code"
        by_class = (self.by_class.get(_class_key(well_class)) or []) if _real_class(well_class) else []
        by_name = self._names(name)
        if by_class and by_name:
            both = set(by_class) & by_name
            if both:
                return self._pick(both, center), "class"
            proper = [i for i in by_name if self.info[i]["proper"]]
            hit = self._unique(proper, center)
            if hit:
                return hit, "name"            # the sheet's class is another well's
        if by_class:
            hit = self._pick(by_class, center)
            far = (hit and name and center and self.info[hit]["center"]
                   and not self._in_center(hit, center))
            if hit and far and not _similar(name, self.info[hit]["name"]):
                hit = None                    # another office, and nothing in common
            if hit:
                return hit, "class"
        if by_name:
            # the name as written first: «سوران 3 قدیم» is the register's old
            # well of that name, not «سوران 3» — the note decides only when no
            # well carries the whole name
            exact = self.by_name.get(name_key(name)) or set()
            hit = (self._unique(exact, center) if exact else None) or self._unique(by_name, center)
            if hit:
                return hit, "name"
        # last: a short name written inside one proper well's name of the same
        # office («کال زرکش 3» → «روستایی کال زرکش3 (جدید)»)
        key = name_key(_strip_note(name)) if name else ""
        if center and len(key) >= 4:
            inside = [i for i, inf in self.info.items()
                      if inf["proper"] and self._in_center(i, center)
                      and any(key in k for k in inf["keys"] if k)]
            if len(inside) == 1:
                return inside[0], "name"
        return None, None


def _class_key(value) -> str:
    text = norm_text(value)
    try:
        f = float(text)
        if f.is_integer():
            return str(int(f))
    except ValueError:
        pass
    return text
