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


# ── «ورود از اکسل»: a table of rows filled from a workbook ──────────────────
UNITS = re.compile(r"\([^)]*\)|\[[^\]]*\]")
# other names the same quantity goes by on a test bench sheet
ALIASES = {"هد": ("head", "h", "ارتفاع"), "دبی": ("flow", "q", "آبدهی", "دبی آب"),
           "آبدهی": ("flow", "q", "دبی")}


def _norm(text) -> str:
    t = str(text or "").replace("ي", "ی").replace("ك", "ک").replace("‌", " ").lower()
    return "".join(t.split())


def _bare(text) -> str:
    """«هد (m)» → «هد», as compared."""
    return _norm(UNITS.sub("", str(text or "")))


def grid_columns(section) -> list:
    """The table's typed columns (formula columns are worked out, not read):
    [(column key, heading, {row: field name})], in the form's order."""
    fields = sorted([f for f in section.fields if f.is_active], key=lambda f: f.sort_order or 0)
    cells = grid_cells(section, [f.field_name for f in fields])
    cols, order = {}, []
    for f in fields:
        if f.field_name not in cells:
            continue
        key, n = cells[f.field_name]
        if key not in cols:
            cols[key] = {"heading": strip_row(f.label, section, n), "rows": {}, "typed": False}
            order.append(key)
        cols[key]["rows"][n] = f.field_name
        if f.field_type not in ("formula", "mirror", "chart"):
            cols[key]["typed"] = True
    return [(k, cols[k]["heading"], cols[k]["rows"]) for k in order if cols[k]["typed"]]


def grid_template(section) -> bytes:
    """A workbook to fill: the row names down, the typed columns across."""
    from io import BytesIO
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    cols = grid_columns(section)
    rows = sorted({n for _k, _h, r in cols for n in r})
    wb = Workbook()
    ws = wb.active
    ws.title = "جدول"
    ws.sheet_view.rightToLeft = True
    head = [(getattr(section, "grid_label", None) or DEFAULT_LABEL).replace("{n}", "").strip(" —-") or "ردیف"]
    ws.append(head + [h for _k, h, _r in cols])
    for c in ws[1]:
        c.font = Font(bold=True)
        c.fill = PatternFill("solid", fgColor="DBEAFE")
    for n in rows:
        ws.append([row_title(section, n)] + [None] * len(cols))
    ws.column_dimensions["A"].width = 14
    for i in range(len(cols)):
        ws.column_dimensions[chr(66 + i) if i < 25 else "Z"].width = 16
    out = BytesIO()
    wb.save(out)
    return out.getvalue()


def grid_read(section, data: bytes) -> dict:
    """The values a workbook gives the table: {field name: number}.

    The heading row is the first one naming at least one of the table's
    columns (by its heading, with or without the unit, or a usual other name
    — «Head», «Q»); the rows under it are the table's rows in order, or by
    the number in their first cell («نقطه 3», «3»)."""
    from io import BytesIO
    from openpyxl import load_workbook
    cols = grid_columns(section)
    if not cols:
        raise ValueError("این بخش ستونی برای ورود از اکسل ندارد.")
    want = []
    for key, heading, rows in cols:
        names = {_norm(heading), _bare(heading)}
        for base, other in ALIASES.items():
            if _bare(heading) == _norm(base):
                names.update(_norm(o) for o in other)
        want.append((key, {n for n in names if n}, rows))
    wb = load_workbook(BytesIO(data), data_only=True, read_only=True)
    for ws in wb.worksheets:
        grid = [list(r) for r in ws.iter_rows(values_only=True)]
        for h, line in enumerate(grid[:30]):
            found = {}
            for c, cell in enumerate(line):
                if not isinstance(cell, str):
                    continue
                for key, names, _rows in want:
                    if key not in found and (_norm(cell) in names or _bare(cell) in names):
                        found[key] = c
                        break
            if not found:
                continue
            values, k, used = {}, 0, []
            top = max((n for _key, _names, rows in want for n in rows), default=0)
            for line2 in grid[h + 1:]:
                if not any(v not in (None, "") for v in line2):
                    continue
                nums = {key: _number(line2[c]) if c < len(line2) else None for key, c in found.items()}
                if all(v is None for v in nums.values()):
                    continue
                k += 1
                n = k
                first = line2[0] if line2 and 0 not in found.values() else None
                if isinstance(first, str):
                    m = re.search(r"(\d+)", first.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")))
                    n = int(m.group(1)) if m else k
                elif isinstance(first, (int, float)) and float(first).is_integer() and 1 <= first <= top:
                    n = int(first)
                for key, _names, rows in want:
                    if key in nums and nums[key] is not None and n in rows:
                        values[rows[n]] = nums[key]
                used.append(n)
            return {"values": values, "rows": len(used), "sheet": ws.title,
                    "columns": [h2 for key, h2, _r in cols if key in found],
                    "missing": [h2 for key, h2, _r in cols if key not in found]}
    raise ValueError("سطر عنوان جدول در فایل پیدا نشد؛ از «قالب اکسل» همین بخش استفاده کنید.")


def _number(v):
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return round(float(v), 6)
    t = str(v).strip().translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")).replace("٫", ".").replace(",", "")
    m = re.match(r"^-?\d+(\.\d+)?$", t)
    return float(t) if m else None
