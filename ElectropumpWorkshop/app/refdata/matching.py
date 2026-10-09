"""Which well of the main register a reference row is about.

The sources share codes with the register: production and videometry carry
«کد تاسیس» (the register's PM code, e.g. 10/21/4) and the flow tests carry
«کلاسه چاه» (the register's well class). A name — compared without spaces,
diacritics or Arabic/Persian letter differences, and through the register's
aliases — is the fallback; when a name is ambiguous the office/center decides,
and if it still is, the row stays unlinked rather than guessing.
"""
from __future__ import annotations

from .textnorm import name_key, norm_text


class WellIndex:
    def __init__(self):
        from ..models import LookupItem, Well, WellAlias
        self.by_pm, self.by_class, self.by_name = {}, {}, {}
        self.center_of = {}
        centers = {i.id: name_key(i.value) for i in LookupItem.query.all()}
        for w in Well.query.all():
            if w.pm_code:
                self.by_pm.setdefault(norm_text(w.pm_code), w.id)
            if w.well_class:
                self.by_class.setdefault(_class_key(w.well_class), w.id)
            self.by_name.setdefault(name_key(w.name), set()).add(w.id)
            self.center_of[w.id] = centers.get(w.center_id)
        try:
            for a in WellAlias.query.all():
                alias = getattr(a, "alias", None) or getattr(a, "name", None)
                if alias:
                    self.by_name.setdefault(name_key(alias), set()).add(a.well_id)
        except Exception:  # noqa: BLE001 — aliases are a help, never required
            pass

    def match(self, *, pm_code=None, well_class=None, name=None, center=None):
        """(main well id, how) or (None, None)."""
        if pm_code:
            hit = self.by_pm.get(norm_text(pm_code))
            if hit:
                return hit, "code"
        if well_class:
            hit = self.by_class.get(_class_key(well_class))
            if hit:
                return hit, "class"
        if name:
            ids = self.by_name.get(name_key(name)) or set()
            if len(ids) == 1:
                return next(iter(ids)), "name"
            if len(ids) > 1 and center:
                ck = name_key(center)
                narrowed = [i for i in ids if self.center_of.get(i) and
                            (ck in self.center_of[i] or self.center_of[i] in ck)]
                if len(narrowed) == 1:
                    return narrowed[0], "name"
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
