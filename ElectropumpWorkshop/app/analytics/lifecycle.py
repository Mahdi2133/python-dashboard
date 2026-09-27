# -*- coding: utf-8 -*-
"""Versions, validation, publishing and dependencies of reports."""
from __future__ import annotations

from collections import OrderedDict

from ..extensions import db
from ..models.report import (REPORT_ARCHIVED, REPORT_DRAFT, REPORT_PUBLISHED,
                             REPORT_TESTING, Report, ReportDependency, ReportVersion)
from ..services.jalali import local_now
from .catalogue import get_source
from .engine import (AGGREGATIONS, OPERATORS, ReportError, Run, run_report,
                     tree_fields)
from .formula import FormulaError, compile_formula

# Chart types: one module each on the page. Adding one is an entry here and a
# renderer in report_view.js.
CHART_TYPES = OrderedDict([
    ("bar", ("میله‌ای", "پایه")), ("hbar", ("میله‌ای افقی", "پایه")),
    ("column", ("ستونی", "پایه")), ("line", ("خطی", "پایه")), ("area", ("مساحت", "پایه")),
    ("pie", ("دایره‌ای", "پایه")), ("donut", ("دونات", "پایه")),
    ("stacked_bar", ("میله‌ای انباشته", "پایه")), ("stacked_column", ("ستونی انباشته", "پایه")),
    ("scatter", ("پراکندگی", "تحلیلی")), ("bubble", ("حبابی", "تحلیلی")),
    ("histogram", ("هیستوگرام", "تحلیلی")), ("box", ("جعبه‌ای (Box Plot)", "تحلیلی")),
    ("heatmap", ("نقشه‌ی حرارتی", "تحلیلی")), ("radar", ("رادار", "تحلیلی")),
    ("pareto", ("پارتو", "تحلیلی")),
    ("trend_day", ("روند روزانه", "زمانی")), ("trend_week", ("روند هفتگی", "زمانی")),
    ("trend_month", ("روند ماهانه", "زمانی")), ("trend_year", ("روند سالانه", "زمانی")),
    ("kpi", ("کارت KPI", "مدیریتی")), ("gauge", ("گیج", "مدیریتی")),
    ("progress", ("نوار پیشرفت", "مدیریتی")), ("ranking", ("رتبه‌بندی", "مدیریتی")),
    ("comparison", ("مقایسه", "مدیریتی")),
])
TREND_GRAN = {"trend_day": "day", "trend_week": "week", "trend_month": "month",
              "trend_year": "year"}


def normalise(defn: dict) -> dict:
    """Fill in what a definition may leave out, so every renderer can rely on it."""
    d = dict(defn or {})
    for key in ("fields", "calcs", "groups", "measures", "sort", "kpis", "charts",
                "tables", "rules", "layout", "interactive_filters"):
        if not isinstance(d.get(key), list):
            d[key] = []
    d.setdefault("filters", {"op": "and", "items": []})
    d.setdefault("drill", {"enabled": False, "path": []})
    d.setdefault("analysis", {"enabled": True, "crosstab": True, "stats": True})
    d.setdefault("export", {"orientation": "landscape", "logo": True})
    for c in d["charts"]:
        if c.get("type") in TREND_GRAN:
            x = dict(c.get("x") or {})
            x["granularity"] = TREND_GRAN[c["type"]]
            c["x"] = x
    return d


def referenced_fields(d: dict) -> set:
    refs = set()
    refs |= {f.get("key") for f in d.get("fields") or []}
    refs |= tree_fields(d.get("filters"))
    refs |= {g.get("field") for g in d.get("groups") or []}
    refs |= {m.get("field") for m in d.get("measures") or [] if m.get("field") not in (None, "*")}
    refs |= {f.get("field") for f in d.get("interactive_filters") or []}
    for k in d.get("kpis") or []:
        v = k.get("value") or {}
        if v.get("field") not in (None, "*"):
            refs.add(v["field"])
        if k.get("period_field"):
            refs.add(k["period_field"])
        refs |= tree_fields(k.get("filters"))
    for c in d.get("charts") or []:
        for part in ("x", "series_by"):
            if (c.get(part) or {}).get("field"):
                refs.add(c[part]["field"])
        for part in ("y_field", "size_field", "value_field"):
            if c.get(part):
                refs.add(c[part])
        for m in c.get("measures") or []:
            if isinstance(m, dict) and m.get("field") not in (None, "*"):
                refs.add(m["field"])
        refs |= tree_fields(c.get("filters"))
    for t in d.get("tables") or []:
        refs |= set(t.get("columns") or [])
        refs |= {g.get("field") for g in t.get("groups") or []}
    for level in (d.get("drill") or {}).get("path") or []:
        if level not in ("_detail", "_records"):
            refs.add(str(level).split(":")[0])
    calc_keys = {c.get("key") for c in d.get("calcs") or []}
    return {r for r in refs if r and r not in calc_keys}


def dependencies(d: dict) -> set:
    """(kind, ref) pairs this definition reads, for change warnings."""
    out = set()
    source = get_source(d.get("source") or "")
    if source is None:
        return out
    out.add(("source", source.key))
    fmap = source.field_map()
    keys = referenced_fields(d)
    calcs = d.get("calcs") or []
    for c in calcs:
        try:
            comp = compile_formula(c.get("formula") or "", dict(fmap, **{
                x.get("key"): {"label": x.get("label")} for x in calcs}))
            keys |= {k for k in comp["refs"] if k in fmap}
        except FormulaError:
            pass
    for k in keys:
        f = fmap.get(k)
        if f is None:
            out.add(("field", k))
            continue
        if f.get("form_field"):
            out.add(("field", f["form_field"]))
        if f.get("form"):
            out.add(("form", f["form"]))
        if f.get("stage"):
            out.add(("stage", str(f["stage"])))
        if f.get("process"):
            out.add(("process", str(f["process"])))
    return out


def record_dependencies(version: ReportVersion):
    ReportDependency.query.filter_by(version_id=version.id).delete()
    for kind, ref in sorted(dependencies(version.definition)):
        db.session.add(ReportDependency(version_id=version.id, kind=kind, ref=str(ref)))


def reports_depending_on(kind: str, ref: str) -> list:
    """Reports whose current or published version reads ``(kind, ref)``."""
    rows = (db.session.query(ReportDependency.version_id)
            .filter(ReportDependency.kind == kind, ReportDependency.ref == str(ref)).all())
    vids = {v for (v,) in rows}
    if not vids:
        return []
    out = []
    for r in Report.query.all():
        live = {r.published_version_id, r.latest_version.id if r.latest_version else None}
        if live & vids:
            out.append({"id": r.id, "name": r.name, "status": r.status})
    return out


def validate(d: dict, report: Report | None = None, run_query=True) -> dict:
    """Everything that must hold before a report may be published."""
    d = normalise(d)
    errors, warnings, checks = [], [], []

    def check(ok, text, level="error"):
        checks.append({"ok": bool(ok), "text": text, "level": level})
        if not ok:
            (errors if level == "error" else warnings).append(text)

    source = get_source(d.get("source") or "")
    check(source is not None, "منبع داده انتخاب شده و معتبر است")
    if source is None:
        return {"ok": False, "errors": errors, "warnings": warnings, "checks": checks}
    fmap = source.field_map()
    calc_keys = {c.get("key") for c in d.get("calcs") or []}
    missing = sorted(k for k in referenced_fields(d) if k not in fmap and k not in calc_keys)
    check(not missing, "همه‌ی فیلدهای گزارش در منبع داده وجود دارند"
          + (f" (نیستند: {'، '.join(missing)})" if missing else ""))
    fields_all = dict(fmap, **{c.get("key"): {"label": c.get("label") or c.get("key")}
                              for c in d.get("calcs") or [] if c.get("key")})
    bad_formula = []
    for c in d.get("calcs") or []:
        try:
            compile_formula(c.get("formula") or "", fields_all)
        except FormulaError as exc:
            bad_formula.append(f"«{c.get('label') or c.get('key')}»: {exc}")
    check(not bad_formula, "فرمول‌ها معتبرند" + (f" — {' | '.join(bad_formula)}" if bad_formula else ""))
    bad_measure = [m for m in d.get("measures") or []
                   if not m.get("calc") and (m.get("agg") or "count") not in AGGREGATIONS]
    check(not bad_measure, "تجمیع‌ها معتبرند")
    bad_filter = []

    def walk(node):
        if not node:
            return
        if "items" in node:
            for i in node.get("items") or []:
                walk(i)
        elif node.get("field") and (node.get("operator") or "eq") not in OPERATORS:
            bad_filter.append(node.get("operator"))
    walk(d.get("filters"))
    check(not bad_filter, "عملگرهای فیلتر معتبرند")
    bad_chart = []
    for c in d.get("charts") or []:
        t = c.get("type")
        if t not in CHART_TYPES:
            bad_chart.append(f"نوع «{t}» ناشناخته است")
        elif t in ("scatter", "bubble") and not ((c.get("x") or {}).get("field") and c.get("y_field")):
            bad_chart.append(f"«{c.get('title') or t}» محور X و Y عددی می‌خواهد")
        elif t in ("histogram", "box") and not c.get("value_field"):
            bad_chart.append(f"«{c.get('title') or t}» فیلد مقدار می‌خواهد")
        elif t not in ("scatter", "bubble", "histogram", "box", "kpi", "gauge", "progress") \
                and not (c.get("x") or {}).get("field"):
            bad_chart.append(f"«{c.get('title') or t}» محور X (دسته‌بندی) ندارد")
    check(not bad_chart, "تنظیمات نمودارها معتبر است" + (f" — {'؛ '.join(bad_chart)}" if bad_chart else ""))
    has_content = bool(d.get("kpis") or d.get("charts") or d.get("tables") or d.get("fields")
                       or d.get("measures"))
    check(has_content, "گزارش دست‌کم یک KPI، نمودار، جدول یا فیلد دارد")
    if report is not None:
        check(bool(report.permissions), "دسترسی گزارش برای دست‌کم یک کاربر، نقش، مرکز یا گروه تعریف شده است")
        check(any(p.access for p in report.permissions),
              "دست‌کم یک سطح دسترسی (مثلاً مشاهده‌ی داشبورد) داده شده است")
    if run_query and not errors:
        try:
            res = run_report(d)
            failing = [x.get("error") for x in res["kpis"] + res["charts"] + res["tables"]
                       if x.get("error")]
            check(not failing, "کوئری گزارش بدون خطا اجرا می‌شود"
                  + (f" — {'؛ '.join(failing)}" if failing else ""))
            check(res["row_count"] > 0, f"گزارش با داده‌ی فعلی {res['row_count']:,} ردیف دارد", "warning")
            try:
                from .exports import render_export
                render_export("xlsx", {"name": "test"}, d, res)
                check(True, "خروجی آزمایشی Excel ساخته می‌شود")
            except Exception as exc:  # noqa: BLE001
                check(False, f"خروجی آزمایشی ساخته نشد: {exc}")
        except (ReportError, FormulaError) as exc:
            check(False, f"کوئری گزارش اجرا نشد: {exc}")
    return {"ok": not errors, "errors": errors, "warnings": warnings, "checks": checks}


def save_definition(report: Report, definition: dict, user, note=None) -> ReportVersion:
    """Save the working definition: into the open version, or a new one."""
    d = normalise(definition)
    latest = report.latest_version
    if latest is None or latest.frozen:
        number = (latest.number + 1) if latest else 1
        latest = ReportVersion(report_id=report.id, number=number,
                               created_by=user.id if user else None)
        db.session.add(latest)
        report.versions.append(latest)
    latest.definition = d
    if note:
        latest.note = note
    db.session.flush()
    record_dependencies(latest)
    if report.status == REPORT_ARCHIVED:
        report.status = REPORT_DRAFT
    report.updated_at = local_now()
    return latest


def publish(report: Report, version: ReportVersion):
    version.frozen = True
    report.published_version_id = version.id
    report.status = REPORT_PUBLISHED
    report.published_at = local_now()


def restore_as_draft(report: Report, version: ReportVersion, user) -> ReportVersion:
    latest = report.latest_version
    number = (latest.number + 1) if latest else 1
    new = ReportVersion(report_id=report.id, number=number,
                        created_by=user.id if user else None,
                        note=f"بازگردانی از نسخه {version.number}")
    new.definition = version.definition
    db.session.add(new)
    report.versions.append(new)
    db.session.flush()
    record_dependencies(new)
    if report.status == REPORT_ARCHIVED:
        report.status = REPORT_DRAFT
    return new


STATUS_FLOW = {REPORT_DRAFT: {REPORT_TESTING, REPORT_PUBLISHED, REPORT_ARCHIVED},
               REPORT_TESTING: {REPORT_DRAFT, REPORT_PUBLISHED, REPORT_ARCHIVED},
               REPORT_PUBLISHED: {REPORT_TESTING, REPORT_DRAFT, REPORT_ARCHIVED},
               REPORT_ARCHIVED: {REPORT_DRAFT}}


def definition_summary(report: Report, version: ReportVersion) -> dict:
    """«این عدد از کجا آمده؟» — source, filters, formulas and version, in words."""
    d = version.definition if version else {}
    source = get_source(d.get("source") or "")
    fmap = source.field_map() if source else {}
    label = lambda k: fmap.get(k, {}).get("label", k)  # noqa: E731

    def describe(node, depth=0):
        if not node:
            return []
        if "items" in node:
            items = [x for x in node.get("items") or [] if x]
            if not items:
                return []
            joiner = " و " if (node.get("op") or "and") == "and" else " یا "
            parts = [" ".join(describe(i, depth + 1)) for i in items]
            text = joiner.join(p for p in parts if p)
            return [f"({text})" if depth else text]
        op = OPERATORS.get(node.get("operator") or "eq", node.get("operator"))
        val = node.get("value")
        if isinstance(val, list):
            val = "، ".join(map(str, val))
        extra = f" تا {node.get('value2')}" if node.get("value2") not in (None, "") else ""
        from .engine import RELATIVE
        if node.get("operator") == "relative":
            val = RELATIVE.get(val, val)
        return [f"«{label(node.get('field'))}» {op} {val if val is not None else ''}{extra}".strip()]

    return {
        "report": report.name, "version": version.number if version else None,
        "source": source.label if source else None,
        "source_description": source.description if source else None,
        "filters": describe(d.get("filters")),
        "calcs": [{"label": c.get("label"), "formula": c.get("formula")} for c in d.get("calcs") or []],
        "measures": [{"label": m.get("label") or next(
                          (c.get("label") for c in d.get("calcs") or [] if c.get("key") == m.get("calc")),
                          None) or m.get("key"),
                      "definition": (f"{AGGREGATIONS.get(m.get('agg') or 'count', ('',))[0]} "
                                     f"{label(m.get('field')) if m.get('field') not in (None, '*') else 'ردیف‌ها'}"
                                     if not m.get("calc") else f"فرمول «{m.get('calc')}»")}
                     for m in d.get("measures") or []],
        "groups": [label(g.get("field")) for g in d.get("groups") or []],
    }
