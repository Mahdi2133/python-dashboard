# -*- coding: utf-8 -*-
"""Report exports: Excel, PDF, Word, CSV, JSON and a printable HTML page.

Every format is built from the same two things — the report's definition and
one run's result — so what is exported is exactly what was shown. Chart
pictures come from the browser (ECharts renders them); a scheduled export has
none, so Excel falls back to native charts, PDF to vector charts and Word to
the chart's numbers as a table.
"""
from __future__ import annotations

import base64
import csv
import datetime as _dt
import html
import io
import json

from ..paths import resource_dir
from ..services.exporter import _register_pdf_font, shape_rtl

MIMES = {
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "csv": "text/csv; charset=utf-8",
    "json": "application/json; charset=utf-8",
    "html": "text/html; charset=utf-8",
    "print": "text/html; charset=utf-8",
}
FORMAT_ACCESS = {"xlsx": "export_xlsx", "pdf": "export_pdf", "docx": "export_docx",
                 "csv": "export_csv", "json": "export_json", "html": "print", "print": "print"}
STYLE_FILL = {"ok": "D4EFDF", "warn": "FFF1C7", "bad": "F9D6D5", "info": "D6E9F8"}
STATUS_TEXT = {"ok": "مطلوب", "warn": "نزدیک هدف", "bad": "نامطلوب"}


# ── values ──────────────────────────────────────────────────────────────────
def fmt_value(v, col=None) -> str:
    col = col or {}
    if v is None or v == "":
        return ""
    if isinstance(v, bool):
        return "بله" if v else "خیر"
    if isinstance(v, (list, tuple)):
        return "، ".join(fmt_value(x) for x in v)
    if isinstance(v, (_dt.date, _dt.datetime)):
        from .engine import jalali_str
        return jalali_str(v, isinstance(v, _dt.datetime))
    if isinstance(v, (int, float)):
        dec = col.get("decimals")
        if dec in (None, ""):
            dec = 0 if float(v).is_integer() else 2
        text = f"{float(v):,.{int(dec)}f}"
        if col.get("format") == "percent":
            text += "٪"
        if col.get("unit"):
            text += f" {col['unit']}"
        return text
    return str(v)


def _num(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return v
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


def decode_images(images) -> dict:
    """{chart id: data-URL or base64} → {chart id: PNG bytes}."""
    out = {}
    for key, val in (images or {}).items():
        if not val:
            continue
        if isinstance(val, bytes):
            out[str(key)] = val
            continue
        text = str(val)
        if "," in text and text.startswith("data:"):
            text = text.split(",", 1)[1]
        try:
            data = base64.b64decode(text)
        except Exception:  # noqa: BLE001
            continue
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            out[str(key)] = data
    return out


def _chart_defs(definition):
    return {str(c.get("id")): c for c in (definition or {}).get("charts") or []}


def _table_defs(definition):
    return {str(t.get("id")): t for t in (definition or {}).get("tables") or []}


def _chart_title(cdef, chart, i):
    return (cdef or {}).get("title") or f"نمودار {i + 1}"


def _table_title(tdef, table, i):
    return (tdef or {}).get("title") or ("جدول اصلی" if table.get("id") in (None, "_main")
                                         else f"جدول {i + 1}")


def _cell_rule(rules, key, value):
    from .engine import rule_style
    st = rule_style(rules, key, value)
    return st.get("style") if st else None


def _table_matrix(table, rules=None):
    """A result table → (header labels, [[text]], row fills, bold rows, cols)."""
    cols = table.get("columns") or []
    header = [c.get("label") or c.get("key") for c in cols]
    rows, fills, bold = [], {}, set()
    for ri, r in enumerate(table.get("rows") or []):
        line = []
        for c in cols:
            v = r.get(c["key"])
            style = _cell_rule(rules, c["key"], v) if c.get("type") == "measure" or rules else None
            text = fmt_value(v, c)
            line.append((text, STYLE_FILL.get(style)) if style else text)
        if r.get("_subtotal"):
            fills[ri] = "E6EEF5"
            bold.add(ri)
        rows.append(line)
    if table.get("total"):
        tot = table["total"]
        line = []
        for i, c in enumerate(cols):
            if c["key"] in tot:
                line.append(fmt_value(tot[c["key"]], c))
            else:
                line.append("جمع کل" if i == 0 else "")
        fills[len(rows)] = "DCE6F0"
        bold.add(len(rows))
        rows.append(line)
    return header, rows, fills, bold, cols


def _chart_rows(chart):
    """A chart's numbers as a small table (header, rows)."""
    t = chart.get("type")
    if chart.get("points") is not None:
        return ([chart.get("x_label") or "X", chart.get("y_label") or "Y"],
                [[fmt_value(p[0]), fmt_value(p[1])] for p in chart["points"][:200]])
    if chart.get("bins") is not None:
        return (["بازه", "تعداد"], [[b["label"], fmt_value(b["value"])] for b in chart["bins"]])
    if chart.get("boxes") is not None:
        return (["دسته", "کمینه", "چارک اول", "میانه", "چارک سوم", "بیشینه"],
                [[b["label"]] + [fmt_value(x) for x in (b.get("stats") or [""] * 5)]
                 for b in chart["boxes"]])
    cats = chart.get("categories") or []
    series = chart.get("series") or []
    header = ["دسته"] + [s.get("name") or "" for s in series]
    rows = []
    for i, c in enumerate(cats):
        rows.append([c] + [fmt_value((s.get("data") or [None] * (i + 1))[i]
                                     if i < len(s.get("data") or []) else None) for s in series])
    if t in ("kpi", "gauge", "progress") and chart.get("value") is not None and not rows:
        rows = [["مقدار", fmt_value(chart.get("value"))]]
        header = ["", ""]
    return header, rows


def _info_pairs(meta, result):
    pairs = [("نام گزارش", meta.get("name") or "")]
    if meta.get("category"):
        pairs.append(("دسته", meta["category"]))
    if meta.get("description"):
        pairs.append(("شرح", meta["description"]))
    pairs += [("منبع داده", result.get("source_label") or ""),
              ("نسخه‌ی گزارش", str(meta.get("version") or "—")),
              ("وضعیت", meta.get("status_label") or meta.get("status") or ""),
              ("تهیه‌کننده‌ی خروجی", meta.get("user") or ""),
              ("زمان اجرا", result.get("generated_at") or ""),
              ("تعداد ردیف‌های داده", f"{result.get('row_count', 0):,}")]
    if meta.get("scope"):
        pairs.append(("محدوده‌ی داده", meta["scope"]))
    if meta.get("snapshot"):
        pairs.append(("Snapshot", meta["snapshot"]))
    return pairs


def _kpi_rows(result):
    rows = []
    for k in result.get("kpis") or []:
        if k.get("error"):
            rows.append([k.get("title") or "", "خطا: " + k["error"], "", "", ""])
            continue
        col = {"format": k.get("format"), "decimals": k.get("decimals"), "unit": k.get("unit")}
        change = ""
        if k.get("change_pct") is not None:
            change = f"{k['change_pct']:+.1f}٪ نسبت به {k.get('period_label') or 'دوره'} قبل"
        rows.append([k.get("title") or "", fmt_value(k.get("value"), col),
                     fmt_value(k.get("target"), col) if k.get("target") not in (None, "") else "",
                     (STATUS_TEXT.get(k.get("status")) or k.get("rule_label") or "",
                      STYLE_FILL.get(k.get("status"))),
                     change])
    return rows


def _filter_lines(meta):
    return list(meta.get("filters") or [])


def _stem(meta):
    return meta.get("file_stem") or "report"


# ── Excel ───────────────────────────────────────────────────────────────────
def to_xlsx(meta, definition, result, raw=None, images=None, extras=None) -> bytes:
    from openpyxl import Workbook
    from openpyxl.chart import (AreaChart, BarChart, DoughnutChart, LineChart, PieChart,
                                RadarChart, Reference, ScatterChart, Series)
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    rules = (definition or {}).get("rules") or []
    wb = Workbook()
    head_fill = PatternFill("solid", fgColor="0A3D62")
    head_font = Font(name="Tahoma", bold=True, color="FFFFFF", size=10)
    body_font = Font(name="Tahoma", size=10)
    bold_font = Font(name="Tahoma", size=10, bold=True)
    title_font = Font(name="Tahoma", size=14, bold=True, color="0A3D62")
    thin = Side(style="thin", color="C9D3DC")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    right = Alignment(horizontal="right", vertical="center", wrap_text=True)

    def prep(ws, title):
        ws.sheet_view.rightToLeft = True
        ws.oddHeader.center.text = f"{meta.get('name') or ''} — {title}"
        ws.oddHeader.center.size = 9
        ws.oddFooter.center.text = "صفحه &P از &N"
        ws.oddFooter.right.text = result.get("generated_at") or ""
        ws.page_setup.orientation = "landscape"
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0
        ws.sheet_properties.pageSetUpPr.fitToPage = True

    def header_row(ws, r, labels):
        for i, lab in enumerate(labels, start=1):
            c = ws.cell(row=r, column=i, value=lab)
            c.fill, c.font, c.border, c.alignment = head_fill, head_font, border, center

    def widths(ws, ncols, rows_from, rows_to, minimum=10):
        for i in range(1, ncols + 1):
            letter = get_column_letter(i)
            best = minimum
            for r in range(rows_from, min(rows_to, rows_from + 400) + 1):
                v = ws.cell(row=r, column=i).value
                if v is not None:
                    best = max(best, min(len(str(v)) + 3, 50))
            ws.column_dimensions[letter].width = best

    # 1. summary
    ws = wb.active
    ws.title = "خلاصه"
    prep(ws, "خلاصه")
    ws.cell(row=1, column=1, value=meta.get("name") or "گزارش").font = title_font
    r = 3
    for k, v in _info_pairs(meta, result):
        ws.cell(row=r, column=1, value=k).font = bold_font
        ws.cell(row=r, column=2, value=v).font = body_font
        ws.cell(row=r, column=2).alignment = right
        r += 1
    filters = _filter_lines(meta)
    if filters:
        r += 1
        ws.cell(row=r, column=1, value="فیلترهای اعمال‌شده").font = bold_font
        r += 1
        for f in filters:
            ws.cell(row=r, column=1, value="•")
            ws.cell(row=r, column=2, value=f).font = body_font
            r += 1
    kpis = result.get("kpis") or []
    if kpis:
        r += 1
        ws.cell(row=r, column=1, value="شاخص‌های کلیدی (KPI)").font = bold_font
        r += 1
        header_row(ws, r, ["شاخص", "مقدار", "هدف", "وضعیت", "مقایسه"])
        r += 1
        for k, row in zip(kpis, _kpi_rows(result)):
            for i, val in enumerate(row, start=1):
                text, fill = (val if isinstance(val, tuple) else (val, None))
                if i == 2 and _num(k.get("value")) is not None and not k.get("error"):
                    text = _num(k.get("value"))
                c = ws.cell(row=r, column=i, value=text)
                c.font, c.border, c.alignment = body_font, border, center
                if fill:
                    c.fill = PatternFill("solid", fgColor=fill)
            r += 1
    ws.column_dimensions["A"].width = 30
    ws.column_dimensions["B"].width = 45
    for letter in "CDE":
        ws.column_dimensions[letter].width = 22

    # 2. tables
    tdefs = _table_defs(definition)
    used = {"خلاصه"}

    def sheet_name(base):
        base = "".join(ch for ch in base if ch not in '[]:*?/\\')[:28] or "برگه"
        name, n = base, 2
        while name in used:
            name, n = f"{base[:25]} {n}", n + 1
        used.add(name)
        return name

    for ti, table in enumerate(result.get("tables") or []):
        title = _table_title(tdefs.get(str(table.get("id"))), table, ti)
        ws = wb.create_sheet(sheet_name(title))
        prep(ws, title)
        ws.cell(row=1, column=1, value=title).font = title_font
        if table.get("error"):
            ws.cell(row=3, column=1, value="خطا: " + table["error"])
            continue
        cols = table.get("columns") or []
        header_row(ws, 3, [c.get("label") or c["key"] for c in cols])
        rr = 4
        for row in table.get("rows") or []:
            for ci, c in enumerate(cols, start=1):
                v = row.get(c["key"])
                if isinstance(v, (list, tuple)):
                    v = "، ".join(map(str, v))
                cell = ws.cell(row=rr, column=ci, value=v)
                cell.font = bold_font if row.get("_subtotal") else body_font
                cell.border, cell.alignment = border, center
                if isinstance(v, float):
                    dec = c.get("decimals")
                    cell.number_format = "#,##0" + ("." + "0" * int(dec) if dec else ".00") \
                        if dec not in (0, "0") else "#,##0"
                elif isinstance(v, int):
                    cell.number_format = "#,##0"
                style = _cell_rule(rules, c["key"], v)
                if style in STYLE_FILL:
                    cell.fill = PatternFill("solid", fgColor=STYLE_FILL[style])
                elif row.get("_subtotal"):
                    cell.fill = PatternFill("solid", fgColor="E6EEF5")
            rr += 1
        last = rr - 1
        if table.get("total"):
            for ci, c in enumerate(cols, start=1):
                v = table["total"].get(c["key"], "جمع کل" if ci == 1 else None)
                cell = ws.cell(row=rr, column=ci, value=v)
                cell.font, cell.border, cell.alignment = bold_font, border, center
                cell.fill = PatternFill("solid", fgColor="DCE6F0")
                if isinstance(v, (int, float)):
                    cell.number_format = "#,##0.##"
            rr += 1
        ws.freeze_panes = "A4"
        if cols and last >= 4:
            ws.auto_filter.ref = f"A3:{get_column_letter(len(cols))}{last}"
        widths(ws, len(cols), 3, rr)
        if table.get("truncated"):
            ws.cell(row=rr + 1, column=1,
                    value=f"نمایش {len(table.get('rows') or []):,} ردیف از {table.get('row_count', 0):,}")

    # 3. charts: numbers on a data sheet, native charts beside them
    charts = [c for c in result.get("charts") or [] if not c.get("error")]
    if charts:
        cdefs = _chart_defs(definition)
        ws = wb.create_sheet(sheet_name("نمودارها"))
        prep(ws, "نمودارها")
        rr, anchor_row = 1, 1
        for i, ch in enumerate(charts):
            cdef = cdefs.get(str(ch.get("id"))) or {}
            title = _chart_title(cdef, ch, i)
            header, rows = _chart_rows(ch)
            ws.cell(row=rr, column=1, value=title).font = bold_font
            top = rr + 1
            header_row(ws, top, header)
            for j, row in enumerate(rows, start=top + 1):
                for ci, val in enumerate(row, start=1):
                    n = _num(val) if ci > 1 else None
                    cell = ws.cell(row=j, column=ci, value=n if n is not None else val)
                    cell.font, cell.border, cell.alignment = body_font, border, center
            bottom = top + len(rows)
            ncols = len(header)
            chart = None
            t = ch.get("type") or "bar"
            if rows and ncols >= 2 and ch.get("categories") is not None:
                if t in ("pie", "donut"):
                    chart = DoughnutChart() if t == "donut" else PieChart()
                elif t in ("line", "trend_day", "trend_week", "trend_month", "trend_year"):
                    chart = LineChart()
                elif t == "area":
                    chart = AreaChart()
                elif t == "radar":
                    chart = RadarChart()
                else:
                    chart = BarChart()
                    chart.type = "bar" if t in ("hbar", "ranking", "stacked_bar") else "col"
                    if t in ("stacked_bar", "stacked_column"):
                        chart.grouping = "stacked"
                        chart.overlap = 100
                data = Reference(ws, min_col=2, max_col=ncols, min_row=top, max_row=bottom)
                cats = Reference(ws, min_col=1, min_row=top + 1, max_row=bottom)
                chart.add_data(data, titles_from_data=True)
                chart.set_categories(cats)
            elif rows and ch.get("bins") is not None:
                chart = BarChart()
                chart.add_data(Reference(ws, min_col=2, min_row=top, max_row=bottom), titles_from_data=True)
                chart.set_categories(Reference(ws, min_col=1, min_row=top + 1, max_row=bottom))
                chart.gapWidth = 5
            elif rows and ch.get("points") is not None:
                chart = ScatterChart()
                chart.style = 13
                xs = Reference(ws, min_col=1, min_row=top + 1, max_row=bottom)
                ys = Reference(ws, min_col=2, min_row=top, max_row=bottom)
                s = Series(ys, xs, title_from_data=True)
                s.marker.symbol = "circle"
                s.graphicalProperties.line.noFill = True
                chart.series.append(s)
            if chart is not None:
                chart.title = title
                chart.height, chart.width = 8, 16
                ws.add_chart(chart, f"{get_column_letter(ncols + 2)}{max(anchor_row, rr)}")
            rr = max(bottom + 3, rr + 18 if chart is not None else bottom + 3)
            anchor_row = rr
        ws.column_dimensions["A"].width = 26

    # 4. statistics / crosstab from the analysis page
    ex = extras or {}
    if ex.get("stats"):
        ws = wb.create_sheet(sheet_name("آمار توصیفی"))
        prep(ws, "آمار توصیفی")
        labels = ["فیلد", "تعداد", "خالی", "جمع", "میانگین", "میانه", "انحراف معیار",
                  "کمینه", "چارک اول", "چارک سوم", "بیشینه", "دامنه"]
        keys = ["label", "count", "empty", "sum", "mean", "median", "stddev", "min", "p25",
                "p75", "max", "range"]
        header_row(ws, 1, labels)
        for j, s in enumerate(ex["stats"], start=2):
            for ci, k in enumerate(keys, start=1):
                v = s.get(k)
                cell = ws.cell(row=j, column=ci, value=round(v, 4) if isinstance(v, float) else v)
                cell.font, cell.border, cell.alignment = body_font, border, center
        ws.freeze_panes = "B2"
        widths(ws, len(labels), 1, len(ex["stats"]) + 1)
    if ex.get("crosstab"):
        ct = ex["crosstab"]
        ws = wb.create_sheet(sheet_name("جدول متقاطع"))
        prep(ws, "جدول متقاطع")
        ws.cell(row=1, column=1, value=f"{ct.get('measure_label')} — {ct.get('row_label')} × "
                f"{ct.get('col_label')}").font = bold_font
        header_row(ws, 3, [ct.get("row_label")] + list(ct.get("cols") or []) + ["جمع"])
        for j, rl in enumerate(ct.get("rows") or [], start=4):
            vals = [rl] + list(ct["cells"][j - 4]) + [ct["row_totals"][j - 4]]
            for ci, v in enumerate(vals, start=1):
                cell = ws.cell(row=j, column=ci, value=v)
                cell.font, cell.border, cell.alignment = body_font, border, center
        j = 4 + len(ct.get("rows") or [])
        for ci, v in enumerate(["جمع"] + list(ct.get("col_totals") or []) + [ct.get("grand_total")],
                               start=1):
            cell = ws.cell(row=j, column=ci, value=v)
            cell.font, cell.border, cell.alignment = bold_font, border, center
        widths(ws, len(ct.get("cols") or []) + 2, 3, j)

    # 5. raw data
    if raw and raw.get("columns"):
        ws = wb.create_sheet(sheet_name("داده‌ی خام"))
        prep(ws, "داده‌ی خام")
        cols = raw["columns"]
        header_row(ws, 1, [c.get("label") or c["key"] for c in cols])
        for j, row in enumerate(raw.get("rows") or [], start=2):
            for ci, c in enumerate(cols, start=1):
                v = row.get(c["key"])
                if isinstance(v, (list, tuple)):
                    v = "، ".join(map(str, v))
                ws.cell(row=j, column=ci, value=v).font = body_font
        ws.freeze_panes = "A2"
        n = len(raw.get("rows") or [])
        if n:
            ws.auto_filter.ref = f"A1:{get_column_letter(len(cols))}{n + 1}"
        widths(ws, len(cols), 1, n + 1)

    # 6. definitions — where the numbers come from
    ws = wb.create_sheet(sheet_name("تعاریف"))
    prep(ws, "تعاریف")
    summary = ex.get("summary") or {}
    rr = 1
    ws.cell(row=rr, column=1, value="این اعداد از کجا آمده‌اند؟").font = title_font
    rr += 2
    for k, v in (("منبع", summary.get("source")), ("شرح منبع", summary.get("source_description")),
                 ("نسخه", summary.get("version")),
                 ("گروه‌بندی", "، ".join(summary.get("groups") or []))):
        ws.cell(row=rr, column=1, value=k).font = bold_font
        ws.cell(row=rr, column=2, value=v)
        rr += 1
    for title, items, fmt in (("فیلترهای ثابت گزارش", summary.get("filters") or [], lambda x: [x]),
                              ("سنجه‌ها", summary.get("measures") or [],
                               lambda x: [x.get("label"), x.get("definition")]),
                              ("فرمول‌ها", summary.get("calcs") or [],
                               lambda x: [x.get("label"), x.get("formula")])):
        if not items:
            continue
        rr += 1
        ws.cell(row=rr, column=1, value=title).font = bold_font
        rr += 1
        for it in items:
            for ci, v in enumerate(fmt(it), start=1):
                ws.cell(row=rr, column=ci + (1 if len(fmt(it)) == 1 else 0), value=v)
            rr += 1
    ws.column_dimensions["A"].width = 28
    ws.column_dimensions["B"].width = 70

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ── PDF ─────────────────────────────────────────────────────────────────────
def _rl_chart(ch, width, height):
    """A reportlab vector drawing for a categorical chart (no picture needed)."""
    from reportlab.graphics.charts.barcharts import HorizontalBarChart, VerticalBarChart
    from reportlab.graphics.charts.linecharts import HorizontalLineChart
    from reportlab.graphics.charts.piecharts import Pie
    from reportlab.graphics.shapes import Drawing
    from reportlab.lib import colors

    palette = [colors.HexColor(c) for c in ("#1f77b4", "#ff7f0e", "#2ca02c", "#d62728",
                                            "#9467bd", "#8c564b", "#e377c2", "#17becf")]
    cats = [shape_rtl(str(c)[:18]) for c in (ch.get("categories") or [])][:60]
    series = ch.get("series") or []
    if not cats or not series:
        return None
    data = [[_num(v) or 0 for v in (s.get("data") or [])[:len(cats)]] for s in series]
    d = Drawing(width, height)
    t = ch.get("type")
    if t in ("pie", "donut"):
        p = Pie()
        p.x, p.y, p.width, p.height = width / 2 - height / 2.6, 15, height / 1.4, height / 1.4
        p.data = data[0]
        p.labels = cats
        p.simpleLabels = 1
        for i in range(len(p.data)):
            p.slices[i].fillColor = palette[i % len(palette)]
            p.slices[i].fontName = "Vazir"
            p.slices[i].fontSize = 7
        if t == "donut":
            p.innerRadiusFraction = 0.5
        d.add(p)
        return d
    if t in ("line", "area", "trend_day", "trend_week", "trend_month", "trend_year"):
        c = HorizontalLineChart()
    elif t in ("hbar", "ranking", "stacked_bar"):
        c = HorizontalBarChart()
    else:
        c = VerticalBarChart()
    c.x, c.y, c.width, c.height = 50, 45, width - 70, height - 60
    c.data = data
    step = max(1, len(cats) // 12)
    c.categoryAxis.categoryNames = [n if i % step == 0 else "" for i, n in enumerate(cats)]
    c.categoryAxis.labels.fontName = "Vazir"
    c.categoryAxis.labels.fontSize = 7
    if isinstance(c, VerticalBarChart) and len(cats) > 6:
        c.categoryAxis.labels.angle = 30
        c.categoryAxis.labels.boxAnchor = "ne"
    c.valueAxis.labels.fontName = "Vazir"
    c.valueAxis.labels.fontSize = 7
    c.valueAxis.valueMin = min(0, min((min(s) for s in data if s), default=0))
    if t in ("stacked_bar", "stacked_column"):
        c.categoryAxis.style = "stacked"
    for i in range(len(data)):
        try:
            if hasattr(c, "bars"):
                c.bars[i].fillColor = palette[i % len(palette)]
            else:
                c.lines[i].strokeColor = palette[i % len(palette)]
                c.lines[i].strokeWidth = 1.5
        except Exception:  # noqa: BLE001
            pass
    d.add(c)
    return d


def to_pdf(meta, definition, result, raw=None, images=None, extras=None) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph,
                                    SimpleDocTemplate, Spacer, Table, TableStyle)

    if not _register_pdf_font():
        raise RuntimeError("فونت فارسی برای تولید PDF یافت نشد.")
    rules = (definition or {}).get("rules") or []
    exp = (definition or {}).get("export") or {}
    land = (exp.get("orientation") or "landscape") == "landscape"
    page = landscape(A4) if land else A4
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=page, rightMargin=12 * mm, leftMargin=12 * mm,
                            topMargin=22 * mm, bottomMargin=16 * mm,
                            title=meta.get("name") or "report")
    usable = page[0] - 24 * mm
    st_title = ParagraphStyle("t", fontName="Vazir-Bold", fontSize=16, alignment=1, leading=24,
                              textColor=colors.HexColor("#0a3d62"), spaceAfter=4)
    st_h = ParagraphStyle("h", fontName="Vazir-Bold", fontSize=12, alignment=2, leading=18,
                          textColor=colors.HexColor("#0a3d62"), spaceBefore=8, spaceAfter=4)
    st_p = ParagraphStyle("p", fontName="Vazir", fontSize=9, alignment=2, leading=14)
    st_small = ParagraphStyle("s", fontName="Vazir", fontSize=8, alignment=1, leading=12,
                              textColor=colors.HexColor("#5b6b78"))
    logo_path = resource_dir() / "app" / "static" / "img" / "electropump.png"
    app_title = meta.get("app_title") or ""

    def on_page(canvas, doc_):
        canvas.saveState()
        w, h = page
        if exp.get("logo", True) and logo_path.exists():
            try:
                canvas.drawImage(str(logo_path), w - 12 * mm - 12 * mm, h - 17 * mm,
                                 width=12 * mm, height=12 * mm, mask="auto")
            except Exception:  # noqa: BLE001
                pass
        canvas.setFont("Vazir-Bold", 9)
        canvas.drawRightString(w - 27 * mm, h - 10 * mm, shape_rtl(app_title))
        canvas.setFont("Vazir", 8)
        canvas.drawRightString(w - 27 * mm, h - 15 * mm, shape_rtl(meta.get("name") or ""))
        canvas.drawString(12 * mm, h - 12 * mm, shape_rtl(result.get("generated_at") or ""))
        canvas.setStrokeColor(colors.HexColor("#c9d3dc"))
        canvas.line(12 * mm, h - 19 * mm, w - 12 * mm, h - 19 * mm)
        canvas.line(12 * mm, 12 * mm, w - 12 * mm, 12 * mm)
        canvas.drawCentredString(w / 2, 7 * mm, shape_rtl(f"صفحه {doc_.page}"))
        if meta.get("version"):
            canvas.drawString(12 * mm, 7 * mm, shape_rtl(f"نسخه {meta['version']}"))
        canvas.restoreState()

    def rl_table(header, rows, fills=None, bold=None, col_widths=None, font=7.5):
        data = ([[shape_rtl(h) for h in header][::-1]] if header else [])
        cell_styles = []
        off = 1 if header else 0
        for ri, row in enumerate(rows):
            line = []
            for ci, v in enumerate(row):
                text, fill = v if isinstance(v, tuple) else (v, None)
                line.append(shape_rtl(str(text)[:80]))
                if fill:
                    col = len(row) - 1 - ci
                    cell_styles.append(("BACKGROUND", (col, ri + off), (col, ri + off),
                                        colors.HexColor("#" + fill)))
            data.append(line[::-1])
        n = max(len(data[0]) if data else 1, 1)
        widths = col_widths or [usable / n] * n
        t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
        style = [("FONTNAME", (0, 0), (-1, -1), "Vazir"), ("FONTSIZE", (0, 0), (-1, -1), font),
                 ("ALIGN", (0, 0), (-1, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                 ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c9d3dc")),
                 ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
                 ("ROWBACKGROUNDS", (0, off), (-1, -1), [colors.white, colors.HexColor("#f4f7fa")])]
        if header:
            style += [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0a3d62")),
                      ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                      ("FONTNAME", (0, 0), (-1, 0), "Vazir-Bold")]
        for ri, fill in (fills or {}).items():
            style.append(("BACKGROUND", (0, ri + off), (-1, ri + off), colors.HexColor("#" + fill)))
        for ri in bold or ():
            style.append(("FONTNAME", (0, ri + off), (-1, ri + off), "Vazir-Bold"))
        t.setStyle(TableStyle(style + cell_styles))
        return t

    story = [Paragraph(shape_rtl(meta.get("name") or "گزارش"), st_title)]
    if meta.get("description"):
        story.append(Paragraph(shape_rtl(meta["description"]), st_small))
    story.append(Spacer(1, 4))
    pairs = _info_pairs(meta, result)
    story.append(rl_table([], [[k, v] for k, v in pairs], col_widths=[usable * 0.65, usable * 0.35]))
    filters = _filter_lines(meta)
    if filters:
        story.append(Paragraph(shape_rtl("فیلترهای اعمال‌شده"), st_h))
        for f in filters:
            story.append(Paragraph(shape_rtl("• " + f), st_p))
    kr = _kpi_rows(result)
    if kr:
        story.append(Paragraph(shape_rtl("شاخص‌های کلیدی"), st_h))
        story.append(rl_table(["شاخص", "مقدار", "هدف", "وضعیت", "مقایسه"], kr, font=9))
    # charts
    charts = [c for c in result.get("charts") or [] if not c.get("error")]
    if charts:
        cdefs = _chart_defs(definition)
        story.append(Paragraph(shape_rtl("نمودارها"), st_h))
        try:
            import PIL  # noqa: F401  (reportlab needs it for PNG pictures)
            can_img = True
        except ImportError:
            can_img = False
        for i, ch in enumerate(charts):
            cdef = cdefs.get(str(ch.get("id"))) or {}
            title = _chart_title(cdef, ch, i)
            block = [Paragraph(shape_rtl(title), ParagraphStyle(
                "ct", parent=st_p, fontName="Vazir-Bold", alignment=1))]
            img = (images or {}).get(str(ch.get("id")))
            if img and can_img:
                from .docx_writer import _png_size
                w, h = _png_size(img) or (800, 400)
                dw = min(usable, 170 * mm if not land else 230 * mm)
                dh = dw * h / float(w)
                maxh = page[1] * 0.36
                if dh > maxh:
                    dw, dh = dw * maxh / dh, maxh
                block.append(Image(io.BytesIO(img), width=dw, height=dh))
            else:
                drawing = _rl_chart(ch, min(usable, 200 * mm), 75 * mm)
                if drawing is not None:
                    block.append(drawing)
                else:
                    header, rows = _chart_rows(ch)
                    if rows:
                        block.append(rl_table(header, rows[:40]))
            block.append(Spacer(1, 6))
            story.append(KeepTogether(block))
    # tables
    tdefs = _table_defs(definition)
    for ti, table in enumerate(result.get("tables") or []):
        title = _table_title(tdefs.get(str(table.get("id"))), table, ti)
        story.append(Paragraph(shape_rtl(title), st_h))
        if table.get("error"):
            story.append(Paragraph(shape_rtl("خطا: " + table["error"]), st_p))
            continue
        header, rows, fills, bold, cols = _table_matrix(table, rules)
        if not cols:
            continue
        rows = rows[:3000]
        story.append(rl_table(header, rows, fills, bold,
                              font=7 if len(cols) > 10 else 8))
        if table.get("truncated") or len(table.get("rows") or []) > 3000:
            story.append(Paragraph(shape_rtl(
                f"نمایش بخشی از {table.get('row_count', 0):,} ردیف؛ خروجی کامل در Excel."), st_small))
    ex = extras or {}
    if ex.get("stats"):
        story.append(Paragraph(shape_rtl("آمار توصیفی"), st_h))
        story.append(rl_table(["فیلد", "تعداد", "میانگین", "میانه", "انحراف معیار", "کمینه", "بیشینه"],
                              [[s.get("label"), fmt_value(s.get("count")), fmt_value(s.get("mean")),
                                fmt_value(s.get("median")), fmt_value(s.get("stddev")),
                                fmt_value(s.get("min")), fmt_value(s.get("max"))]
                               for s in ex["stats"] if s.get("count")]))
    summary = ex.get("summary") or {}
    if summary.get("calcs") or summary.get("measures"):
        story.append(PageBreak())
        story.append(Paragraph(shape_rtl("تعاریف و فرمول‌ها"), st_h))
        rows = [[m.get("label"), m.get("definition")] for m in summary.get("measures") or []]
        rows += [[c.get("label"), c.get("formula")] for c in summary.get("calcs") or []]
        story.append(rl_table(["نام", "تعریف"], rows, col_widths=[usable * 0.6, usable * 0.4]))
    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    return buf.getvalue()


# ── Word ────────────────────────────────────────────────────────────────────
def to_docx(meta, definition, result, raw=None, images=None, extras=None) -> bytes:
    from .docx_writer import DocxWriter

    rules = (definition or {}).get("rules") or []
    exp = (definition or {}).get("export") or {}
    w = DocxWriter(title=meta.get("name") or "گزارش",
                   landscape=(exp.get("orientation") or "portrait") == "landscape")
    w.header_text = f"{meta.get('app_title') or ''} — {meta.get('name') or ''}"
    w.footer_text = f"نسخه {meta.get('version') or '—'} | {result.get('generated_at') or ''}"
    logo_path = resource_dir() / "app" / "static" / "img" / "electropump.png"
    if exp.get("logo", True) and logo_path.exists():
        w.image(logo_path.read_bytes(), width_cm=2.2)
    w.title_block(meta.get("name") or "گزارش", meta.get("description"))

    # 1. report information
    w.heading("۱. مشخصات گزارش", 1)
    w.key_values(_info_pairs(meta, result))
    # 2. executive summary
    kr = _kpi_rows(result)
    w.heading("۲. خلاصه‌ی مدیریتی", 1)
    if kr:
        w.table(["شاخص", "مقدار", "هدف", "وضعیت", "مقایسه"], kr, widths=[2.2, 1.3, 1, 1, 2])
        for k in result.get("kpis") or []:
            if k.get("change_pct") is not None:
                trend = "افزایش" if k["change_pct"] > 0 else ("کاهش" if k["change_pct"] < 0 else "بدون تغییر")
                w.bullet(f"«{k.get('title')}» در {k.get('period_label') or 'دوره'} جاری نسبت به قبل "
                         f"{abs(k['change_pct']):.1f}٪ {trend} داشته است.")
    else:
        w.paragraph(f"این گزارش {result.get('row_count', 0):,} ردیف داده از «"
                    f"{result.get('source_label')}» را خلاصه می‌کند.")
    # 3. filters
    w.heading("۳. فیلترها و محدوده‌ی داده", 1)
    filters = _filter_lines(meta)
    if filters:
        for f in filters:
            w.bullet(f)
    else:
        w.paragraph("فیلتری اعمال نشده است؛ همه‌ی داده‌های منبع در گزارش آمده‌اند.")
    # 4. charts
    charts = [c for c in result.get("charts") or [] if not c.get("error")]
    if charts:
        w.heading("۴. نمودارها", 1)
        cdefs = _chart_defs(definition)
        for i, ch in enumerate(charts):
            title = _chart_title(cdefs.get(str(ch.get("id"))), ch, i)
            w.heading(title, 3)
            img = (images or {}).get(str(ch.get("id")))
            if not (img and w.image(img, caption=title)):
                header, rows = _chart_rows(ch)
                if rows:
                    w.table(header, rows[:60])
    # 5. tables
    w.heading("۵. جداول", 1)
    tdefs = _table_defs(definition)
    for ti, table in enumerate(result.get("tables") or []):
        title = _table_title(tdefs.get(str(table.get("id"))), table, ti)
        w.heading(title, 2)
        if table.get("error"):
            w.paragraph("خطا: " + table["error"], color="B03A2E")
            continue
        header, rows, fills, bold, cols = _table_matrix(table, rules)
        if not cols:
            continue
        limit = 1500
        w.table(header, rows[:limit], row_fills=fills, bold_rows=bold,
                font_size=8 if len(cols) > 7 else 9)
        if len(rows) > limit or table.get("truncated"):
            w.paragraph(f"نمایش {min(len(rows), limit):,} ردیف از {table.get('row_count', len(rows)):,}؛ "
                        "داده‌ی کامل در خروجی Excel است.", size=8, color="5B6B78")
    ex = extras or {}
    # 6. statistics
    if ex.get("stats"):
        w.heading("۶. تحلیل آماری", 1)
        w.table(["فیلد", "تعداد", "میانگین", "میانه", "انحراف معیار", "کمینه", "بیشینه"],
                [[s.get("label"), fmt_value(s.get("count")), fmt_value(s.get("mean")),
                  fmt_value(s.get("median")), fmt_value(s.get("stddev")), fmt_value(s.get("min")),
                  fmt_value(s.get("max"))] for s in ex["stats"] if s.get("count")],
                widths=[2.4, 1, 1, 1, 1, 1, 1])
    # 7. definitions
    summary = ex.get("summary") or {}
    w.heading("۷. تعاریف، سنجه‌ها و فرمول‌ها", 1)
    rows = [[m.get("label"), m.get("definition")] for m in summary.get("measures") or []]
    rows += [[c.get("label"), c.get("formula")] for c in summary.get("calcs") or []]
    if rows:
        w.table(["نام", "تعریف"], rows, widths=[1.2, 2.5])
    if summary.get("filters"):
        w.paragraph("فیلترهای ثابت گزارش:", bold=True)
        for f in summary["filters"]:
            w.bullet(f)
    if not rows and not summary.get("filters"):
        w.paragraph("این گزارش سنجه یا فرمول محاسباتی ندارد.")
    # 8. audit
    w.heading("۸. نسخه و ممیزی", 1)
    w.key_values([("نسخه‌ی تعریف گزارش", str(meta.get("version") or "—")),
                  ("منبع داده", result.get("source_label") or ""),
                  ("زمان اجرای کوئری", result.get("generated_at") or ""),
                  ("کاربر", meta.get("user") or ""),
                  ("شناسه‌ی گزارش", str(meta.get("report_id") or ""))])
    # 9. notes / sign-off
    w.heading("۹. توضیحات و تأیید", 1)
    w.paragraph(meta.get("notes") or "………………………………………………………………………………………………")
    w.spacer(18)
    w.table(["تهیه‌کننده", "بررسی‌کننده", "تأییدکننده"], [[" ", " ", " "]] * 2,
            zebra=False)
    return w.to_bytes()


# ── CSV / JSON / HTML ───────────────────────────────────────────────────────
def to_csv(meta, definition, result, raw=None, images=None, extras=None) -> bytes:
    buf = io.StringIO()
    wr = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)
    if raw and raw.get("columns"):
        cols = raw["columns"]
        wr.writerow([c.get("label") or c["key"] for c in cols])
        for r in raw.get("rows") or []:
            wr.writerow([fmt_value(r.get(c["key"])) if isinstance(r.get(c["key"]), (list, tuple))
                         else ("" if r.get(c["key"]) is None else r.get(c["key"])) for c in cols])
    else:
        tables = [t for t in result.get("tables") or [] if not t.get("error")]
        for i, t in enumerate(tables):
            if i:
                wr.writerow([])
            cols = t.get("columns") or []
            wr.writerow([c.get("label") or c["key"] for c in cols])
            for r in t.get("rows") or []:
                wr.writerow(["" if r.get(c["key"]) is None else
                             (fmt_value(r.get(c["key"])) if isinstance(r.get(c["key"]), (list, tuple))
                              else r.get(c["key"])) for c in cols])
            if t.get("total"):
                wr.writerow([t["total"].get(c["key"], "جمع کل" if j == 0 else "")
                             for j, c in enumerate(cols)])
    return "﻿".encode("utf-8") + buf.getvalue().encode("utf-8")


def to_json(meta, definition, result, raw=None, images=None, extras=None) -> bytes:
    payload = {"report": {k: v for k, v in meta.items() if k not in ("file_stem",)},
               "result": result, "definition_summary": (extras or {}).get("summary")}
    if raw:
        payload["raw"] = raw
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str).encode("utf-8")


def to_html(meta, definition, result, raw=None, images=None, extras=None, auto_print=False) -> bytes:
    rules = (definition or {}).get("rules") or []
    e = html.escape
    parts = [f"""<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8">
<title>{e(meta.get('name') or 'گزارش')}</title><style>
body{{font-family:Vazirmatn,Tahoma,sans-serif;margin:18px;color:#1d2b36;font-size:13px}}
h1{{color:#0a3d62;text-align:center;border-bottom:2px solid #0a3d62;padding-bottom:6px}}
h2{{color:#0a3d62;margin-top:22px;font-size:16px}}
table{{border-collapse:collapse;width:100%;margin:8px 0}}th,td{{border:1px solid #c9d3dc;padding:4px 6px;text-align:center}}
th{{background:#0a3d62;color:#fff}}tr:nth-child(even) td{{background:#f4f7fa}}
.kpis{{display:flex;flex-wrap:wrap;gap:10px}}.kpi{{border:1px solid #c9d3dc;border-radius:8px;padding:10px 14px;min-width:150px}}
.kpi b{{display:block;font-size:20px;color:#0a3d62}}.ok{{background:#d4efdf!important}}.warn{{background:#fff1c7!important}}.bad{{background:#f9d6d5!important}}
.sub td{{background:#e6eef5!important;font-weight:bold}}.tot td{{background:#dce6f0!important;font-weight:bold}}
.meta td:first-child{{font-weight:bold;width:30%}}img{{max-width:100%}}.chart{{page-break-inside:avoid;text-align:center}}
@media print{{body{{margin:0}}h2{{page-break-after:avoid}}}}
</style></head><body>"""]
    parts.append(f"<h1>{e(meta.get('name') or 'گزارش')}</h1>")
    if meta.get("description"):
        parts.append(f"<p style='text-align:center;color:#5b6b78'>{e(meta['description'])}</p>")
    parts.append("<table class='meta'>" + "".join(
        f"<tr><td>{e(str(k))}</td><td>{e(str(v))}</td></tr>" for k, v in _info_pairs(meta, result))
        + "</table>")
    filters = _filter_lines(meta)
    if filters:
        parts.append("<h2>فیلترهای اعمال‌شده</h2><ul>" + "".join(f"<li>{e(f)}</li>" for f in filters) + "</ul>")
    if result.get("kpis"):
        parts.append("<h2>شاخص‌های کلیدی</h2><div class='kpis'>")
        for k in result["kpis"]:
            col = {"format": k.get("format"), "decimals": k.get("decimals"), "unit": k.get("unit")}
            parts.append(f"<div class='kpi {e(k.get('status') or '')}'>{e(k.get('title') or '')}"
                         f"<b>{e(fmt_value(k.get('value'), col) if not k.get('error') else 'خطا')}</b>"
                         + (f"<small>هدف: {e(fmt_value(k.get('target'), col))}</small>"
                            if k.get("target") not in (None, "") else "") + "</div>")
        parts.append("</div>")
    charts = [c for c in result.get("charts") or [] if not c.get("error")]
    if charts:
        cdefs = _chart_defs(definition)
        parts.append("<h2>نمودارها</h2>")
        for i, ch in enumerate(charts):
            title = _chart_title(cdefs.get(str(ch.get("id"))), ch, i)
            img = (images or {}).get(str(ch.get("id")))
            parts.append(f"<div class='chart'><h3>{e(title)}</h3>")
            if img:
                parts.append(f"<img src='data:image/png;base64,{base64.b64encode(img).decode()}'>")
            else:
                header, rows = _chart_rows(ch)
                parts.append("<table><tr>" + "".join(f"<th>{e(str(h))}</th>" for h in header) + "</tr>"
                             + "".join("<tr>" + "".join(f"<td>{e(str(v))}</td>" for v in r) + "</tr>"
                                       for r in rows[:60]) + "</table>")
            parts.append("</div>")
    tdefs = _table_defs(definition)
    for ti, table in enumerate(result.get("tables") or []):
        title = _table_title(tdefs.get(str(table.get("id"))), table, ti)
        parts.append(f"<h2>{e(title)}</h2>")
        if table.get("error"):
            parts.append(f"<p>خطا: {e(table['error'])}</p>")
            continue
        header, rows, fills, bold, cols = _table_matrix(table, rules)
        inv = {v: k for k, v in STYLE_FILL.items()}
        parts.append("<table><tr>" + "".join(f"<th>{e(str(h))}</th>" for h in header) + "</tr>")
        total_idx = len(rows) - 1 if table.get("total") else -1
        for ri, r in enumerate(rows):
            cls = "tot" if ri == total_idx else ("sub" if ri in bold else "")
            cells = []
            for v in r:
                text, fill = v if isinstance(v, tuple) else (v, None)
                cells.append(f"<td class='{inv.get(fill, '')}'>{e(str(text))}</td>")
            parts.append(f"<tr class='{cls}'>" + "".join(cells) + "</tr>")
        parts.append("</table>")
    ex = extras or {}
    summary = ex.get("summary") or {}
    if summary.get("measures") or summary.get("calcs"):
        parts.append("<h2>تعاریف</h2><table><tr><th>نام</th><th>تعریف</th></tr>")
        for m in summary.get("measures") or []:
            parts.append(f"<tr><td>{e(str(m.get('label')))}</td><td>{e(str(m.get('definition')))}</td></tr>")
        for c in summary.get("calcs") or []:
            parts.append(f"<tr><td>{e(str(c.get('label')))}</td><td dir='ltr'>{e(str(c.get('formula')))}</td></tr>")
        parts.append("</table>")
    parts.append(f"<p style='color:#5b6b78;font-size:11px;text-align:center'>{e(meta.get('app_title') or '')}"
                 f" — نسخه {e(str(meta.get('version') or '—'))} — {e(result.get('generated_at') or '')}</p>")
    if auto_print:
        parts.append("<script>window.addEventListener('load',()=>setTimeout(()=>window.print(),300))</script>")
    parts.append("</body></html>")
    return "".join(parts).encode("utf-8")


RENDERERS = {"xlsx": to_xlsx, "pdf": to_pdf, "docx": to_docx, "csv": to_csv, "json": to_json,
             "html": to_html}


def render_export(fmt, meta, definition, result, raw=None, chart_images=None, extras=None):
    """→ (bytes, mimetype, extension)"""
    fmt = (fmt or "xlsx").lower()
    images = decode_images(chart_images)
    if fmt == "print":
        return to_html(meta, definition, result, raw, images, extras, auto_print=True), MIMES["print"], "html"
    if fmt not in RENDERERS:
        raise ValueError(f"قالب خروجی پشتیبانی نمی‌شود: {fmt}")
    return RENDERERS[fmt](meta, definition, result, raw, images, extras), MIMES[fmt], fmt
