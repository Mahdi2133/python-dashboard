"""«جدول ردیفی»: a form section drawn as one table of numbered rows.

A section whose ``layout`` is ``grid`` lays out the fields whose names end in
a number — ``fc_q1 … fc_q5`` — as the rows of a table, one column per
quantity (the name without its number). A quantity is a column only when it
appears in at least two rows; the other fields of the section are drawn
above the table as usual. Each row is named by the section's ``grid_label``
(«کارکرد {n}» when it is empty); a field's label may carry that name
(«کارکرد 2 — آبدهی (l/s)»), so it reads on its own in a report, and the
table drops it from the column heading.

The form engine (formengine.js) draws the table; this module gives the same
reading to everything server-side that lists a section's answers.
"""
from __future__ import annotations

import re

ROW = re.compile(r"^(.*?)(\d+)$")
DEFAULT_LABEL = "کارکرد {n}"


def row_title(section, n) -> str:
    return (getattr(section, "grid_label", None) or DEFAULT_LABEL).replace("{n}", str(n))


def grid_cells(section, names) -> dict:
    """field name → (column key, row number) for the fields that make the table."""
    seen = {}
    for name in names:
        m = ROW.match(name or "")
        if m:
            seen.setdefault(m.group(1), set()).add(int(m.group(2)))
    out = {}
    for name in names:
        m = ROW.match(name or "")
        if m and len(seen.get(m.group(1), ())) >= 2:
            out[name] = (m.group(1), int(m.group(2)))
    return out


def strip_row(label: str, section, n) -> str:
    """«کارکرد 2 — آبدهی (l/s)» → «آبدهی (l/s)»."""
    text = str(label or "")
    title = row_title(section, n)
    if title and title in text:
        text = text.replace(title, "")
    return text.strip(" —–-:|،") or str(label or "")


def is_grid(section) -> bool:
    return getattr(section, "layout", None) == "grid"
