# -*- coding: utf-8 -*-
"""The fourteen fixed reports of requirement 19, queried from the database.

Each report returns the same envelope::

    {"key", "title", "columns": [{"key","label","type"}], "rows": [...],
     "summary": {...}, "chart": {...}|None}

so a single template, a single Excel writer and a single PDF writer serve all
of them.
"""
from __future__ import annotations

from sqlalchemy import case, func, or_

from ..extensions import db
from ..models import LookupItem, Record, RecordTag, Well
from ..services.jalali import MONTHS_FA, parse_jalali_to_date, to_jalali_str
from ..services.records import search_query


def _col(key, label, type_="text"):
    return {"key": key, "label": label, "type": type_}


def _base(params):
    """Every report honours the shared date/center/… filter bar."""
    return search_query(params).order_by(None)


def _lookup_join(attr):
    """Group a record column by its lookup label, keeping NULLs visible."""
    return db.aliased(LookupItem)


# ── گزارش ۱ — گزارش کلی کارگاه ───────────────────────────────────────────────
def report_overall(params):
    q = _base(params)
    ids_sq = q.with_entities(Record.id).subquery()
    scoped = db.session.query(Record).filter(Record.id.in_(db.select(ids_sq)))

    def count_choice(attr, category, value):
        item = (db.session.query(LookupItem.id)
                .join(LookupItem.category)
                .filter(LookupItem.value == value)
                .filter_by()
                .first())
        return scoped.filter(getattr(Record, attr) == item[0]).count() if item else 0

    total = scoped.count()
    op_counts = dict(
        db.session.query(LookupItem.value, func.count(Record.id))
        .join(Record, Record.operation_id == LookupItem.id)
        .filter(Record.id.in_(db.select(ids_sq)))
        .group_by(LookupItem.value).all())

    failure_rows = (db.session.query(func.count(func.distinct(RecordTag.record_id)))
                    .filter(RecordTag.category_code == "failure_reason")
                    .filter(RecordTag.record_id.in_(db.select(ids_sq))).scalar() or 0)
    repair_rows = (db.session.query(func.count(func.distinct(Record.id)))
                   .join(LookupItem, Record.motor_condition_id == LookupItem.id)
                   .filter(LookupItem.value == "تعمیری")
                   .filter(Record.id.in_(db.select(ids_sq))).scalar() or 0)

    distinct_wells = (db.session.query(func.count(func.distinct(Record.well_id)))
                      .filter(Record.id.in_(db.select(ids_sq))).scalar() or 0)
    distinct_pumps = (db.session.query(func.count(func.distinct(Record.pump_curr_id)))
                      .filter(Record.id.in_(db.select(ids_sq)),
                              Record.pump_curr_id.isnot(None)).scalar() or 0)
    distinct_motors = (db.session.query(func.count(func.distinct(Record.motor_curr_id)))
                       .filter(Record.id.in_(db.select(ids_sq)),
                               Record.motor_curr_id.isnot(None)).scalar() or 0)
    distinct_contractors = (db.session.query(func.count(func.distinct(Record.contractor_id)))
                            .filter(Record.id.in_(db.select(ids_sq)),
                                    Record.contractor_id.isnot(None)).scalar() or 0)

    rows = [
        {"metric": "تعداد کل رکوردها", "value": total},
        {"metric": "عملیات نصب", "value": op_counts.get("نصب", 0)},
        {"metric": "عملیات کشیدن", "value": op_counts.get("کشیدن", 0)},
        {"metric": "عملیات جمع‌آوری", "value": op_counts.get("جمع آوری", 0)},
        {"metric": "عملیات نصب جدید", "value": op_counts.get("نصب جدید", 0)},
        {"metric": "رکوردهای دارای خرابی ثبت‌شده", "value": failure_rows},
        {"metric": "رکوردهای با تجهیز تعمیری (موتور)", "value": repair_rows},
        {"metric": "تعداد چاه‌های درگیر", "value": distinct_wells},
        {"metric": "تعداد تیپ‌های پمپ به‌کاررفته", "value": distinct_pumps},
        {"metric": "تعداد تیپ‌های الکتروموتور به‌کاررفته", "value": distinct_motors},
        {"metric": "تعداد پیمانکاران فعال", "value": distinct_contractors},
        {"metric": "کل چاه‌های ثبت‌شده در سامانه",
         "value": Well.query.filter_by(is_active=True).count()},
    ]
    return {"columns": [_col("metric", "شاخص"), _col("value", "مقدار", "number")],
            "rows": rows, "summary": {"total": total},
            "chart": {"type": "bar", "labels": [r["metric"] for r in rows[1:5]],
                      "values": [r["value"] for r in rows[1:5]]}}


# ── گزارش ۲ — بازه زمانی ─────────────────────────────────────────────────────
def report_date_range(params):
    q = _base(params)
    rows = []
    for rec in q.order_by(Record.op_date.asc()).limit(5000).all():
        rows.append({
            "date": to_jalali_str(rec.op_date),
            "well": rec.well.name if rec.well else rec.well_name_raw,
            "center": rec.center.value if getattr(rec, "center", None) else _label(rec.center_id),
            "operation": _label(rec.operation_id),
            "contractor": _label(rec.contractor_id),
            "failures": "، ".join(rec.tag_values("failure_reason")),
        })
    return {
        "columns": [_col("date", "تاریخ"), _col("well", "نام چاه"), _col("center", "مرکز"),
                    _col("operation", "عملیات"), _col("contractor", "پیمانکار"),
                    _col("failures", "شرح خرابی")],
        "rows": rows,
        "summary": {"count": len(rows),
                    "from": params.get("date_from") or "—",
                    "to": params.get("date_to") or "—"},
        "chart": None,
    }


def _label(item_id):
    if not item_id:
        return ""
    item = db.session.get(LookupItem, item_id)
    return item.value if item else ""


# ── گزارش ۳ — ماهانه ─────────────────────────────────────────────────────────
def report_monthly(params):
    q = _base(params)
    ids = db.select(q.with_entities(Record.id).subquery())
    op_case = {}
    for value in ("نصب", "کشیدن", "جمع آوری", "نصب جدید"):
        item = (LookupItem.query.join(LookupItem.category)
                .filter(LookupItem.value == value).first())
        op_case[value] = item.id if item else -1

    grouped = (db.session.query(
        Record.j_month,
        func.count(Record.id),
        func.sum(case((Record.operation_id == op_case["نصب"], 1), else_=0)),
        func.sum(case((Record.operation_id == op_case["کشیدن"], 1), else_=0)),
        func.sum(case((Record.operation_id == op_case["جمع آوری"], 1), else_=0)),
    ).filter(Record.id.in_(ids)).group_by(Record.j_month).all())
    by_month = {int(m): row for m, *_ in [(g[0], ) for g in grouped]
                for row in [next(g for g in grouped if g[0] == m)] if m}

    rows = []
    for m in range(1, 13):
        g = by_month.get(m)
        rows.append({"month": MONTHS_FA[m], "month_no": m,
                     "total": g[1] if g else 0, "install": int(g[2] or 0) if g else 0,
                     "pull": int(g[3] or 0) if g else 0,
                     "collect": int(g[4] or 0) if g else 0})
    return {
        "columns": [_col("month", "ماه"), _col("total", "کل رکوردها", "number"),
                    _col("install", "نصب", "number"), _col("pull", "کشیدن", "number"),
                    _col("collect", "جمع‌آوری", "number")],
        "rows": rows,
        "summary": {"total": sum(r["total"] for r in rows)},
        "chart": {"type": "bar", "labels": [r["month"] for r in rows],
                  "values": [r["total"] for r in rows]},
    }


# ── گزارش ۴ — سالانه (الگوی شیت «99-403») ────────────────────────────────────
def report_yearly(params):
    q = _base(params)
    ids = db.select(q.with_entities(Record.id).subquery())

    def item_id(category, value):
        row = (db.session.query(LookupItem.id).join(LookupItem.category)
               .filter(LookupItem.value == value)
               .filter(LookupItem.category.has(code=category)).first())
        return row[0] if row else -1

    ops = {v: item_id("operation", v) for v in ("نصب", "کشیدن", "جمع آوری")}
    conds = {v: item_id("condition", v) for v in ("نو", "تعمیری", "برگشتی")}
    execs = {v: item_id("executor", v) for v in ("امانی", "پیمانی")}

    def s(col, target):
        return func.sum(case((col == target, 1), else_=0))

    grouped = (db.session.query(
        Record.j_year, func.count(Record.id),
        s(Record.operation_id, ops["نصب"]), s(Record.operation_id, ops["کشیدن"]),
        s(Record.operation_id, ops["جمع آوری"]),
        s(Record.motor_condition_id, conds["نو"]),
        s(Record.motor_condition_id, conds["تعمیری"]),
        s(Record.motor_condition_id, conds["برگشتی"]),
        s(Record.pump_condition_id, conds["نو"]),
        s(Record.pump_condition_id, conds["تعمیری"]),
        s(Record.pump_condition_id, conds["برگشتی"]),
        s(Record.executor_id, execs["امانی"]), s(Record.executor_id, execs["پیمانی"]),
    ).filter(Record.id.in_(ids), Record.j_year.isnot(None))
        .group_by(Record.j_year).order_by(Record.j_year).all())

    keys = ["year", "total", "install", "pull", "collect", "motor_new", "motor_repair",
            "motor_return", "pump_new", "pump_repair", "pump_return",
            "exec_internal", "exec_contract"]
    rows = [dict(zip(keys, [int(v or 0) for v in g])) for g in grouped]
    return {
        "columns": [_col("year", "سال"), _col("total", "کل", "number"),
                    _col("install", "نصب", "number"), _col("pull", "کشیدن", "number"),
                    _col("collect", "جمع‌آوری", "number"),
                    _col("motor_new", "موتور نو", "number"),
                    _col("motor_repair", "موتور تعمیری", "number"),
                    _col("motor_return", "موتور برگشتی", "number"),
                    _col("pump_new", "پمپ نو", "number"),
                    _col("pump_repair", "پمپ تعمیری", "number"),
                    _col("pump_return", "پمپ برگشتی", "number"),
                    _col("exec_internal", "مجری امانی", "number"),
                    _col("exec_contract", "مجری پیمانی", "number")],
        "rows": rows, "summary": {"years": len(rows)},
        "chart": {"type": "bar", "labels": [str(r["year"]) for r in rows],
                  "values": [r["total"] for r in rows]},
    }


# ── گزارش‌های گروهی ۵ تا ۱۰ ───────────────────────────────────────────────────
def _group_by_lookup(params, attr, label, extra_metrics=False):
    q = _base(params)
    ids = db.select(q.with_entities(Record.id).subquery())
    col = getattr(Record, attr)
    selects = [LookupItem.value, func.count(Record.id)]
    if extra_metrics:
        selects += [func.avg(Record.design_flow), func.avg(Record.test_flow),
                    func.avg(Record.total_head), func.avg(Record.working_months)]
    grouped = (db.session.query(*selects)
               .outerjoin(LookupItem, col == LookupItem.id)
               .filter(Record.id.in_(ids))
               .group_by(LookupItem.value)
               .order_by(func.count(Record.id).desc()).all())
    rows = []
    for g in grouped:
        row = {"label": g[0] or "— ثبت‌نشده —", "count": g[1]}
        if extra_metrics:
            row.update({
                "avg_design_flow": round(g[2], 2) if g[2] is not None else None,
                "avg_test_flow": round(g[3], 2) if g[3] is not None else None,
                "avg_head": round(g[4], 2) if g[4] is not None else None,
                "avg_months": round(g[5], 1) if g[5] is not None else None,
            })
        rows.append(row)
    columns = [_col("label", label), _col("count", "تعداد", "number")]
    if extra_metrics:
        columns += [_col("avg_design_flow", "میانگین دبی طراحی", "number"),
                    _col("avg_test_flow", "میانگین دبی آزمایش", "number"),
                    _col("avg_head", "میانگین هد کلی", "number"),
                    _col("avg_months", "میانگین ماه کارکرد", "number")]
    return {"columns": columns, "rows": rows,
            "summary": {"groups": len(rows), "total": sum(r["count"] for r in rows)},
            "chart": {"type": "bar", "labels": [r["label"] for r in rows[:15]],
                      "values": [r["count"] for r in rows[:15]]}}


def _group_by_tag(params, category, label):
    q = _base(params)
    ids = db.select(q.with_entities(Record.id).subquery())
    grouped = (db.session.query(RecordTag.value, func.count(RecordTag.record_id))
               .filter(RecordTag.category_code == category,
                       RecordTag.record_id.in_(ids))
               .group_by(RecordTag.value)
               .order_by(func.count(RecordTag.record_id).desc()).all())
    rows = [{"label": v, "count": c} for v, c in grouped]
    return {"columns": [_col("label", label), _col("count", "تعداد", "number")],
            "rows": rows,
            "summary": {"groups": len(rows), "total": sum(r["count"] for r in rows)},
            "chart": {"type": "bar", "labels": [r["label"] for r in rows[:15]],
                      "values": [r["count"] for r in rows[:15]]}}


# ── گزارش ۱۱ — چاه ───────────────────────────────────────────────────────────
def report_wells(params):
    q = _base(params)
    ids = db.select(q.with_entities(Record.id).subquery())
    grouped = (db.session.query(
        func.coalesce(Well.name, Record.well_name_raw).label("well"),
        func.count(Record.id), func.max(Record.op_date),
        func.avg(Record.curr_install_depth), func.avg(Record.test_flow),
        func.avg(Record.working_months))
        .outerjoin(Well, Record.well_id == Well.id)
        .filter(Record.id.in_(ids))
        .group_by("well").order_by(func.count(Record.id).desc()).all())
    failure_counts = dict(
        db.session.query(func.coalesce(Well.name, Record.well_name_raw),
                         func.count(RecordTag.id))
        .select_from(RecordTag).join(Record, RecordTag.record_id == Record.id)
        .outerjoin(Well, Record.well_id == Well.id)
        .filter(RecordTag.category_code == "failure_reason", Record.id.in_(ids))
        .group_by(func.coalesce(Well.name, Record.well_name_raw)).all())
    rows = [{
        "well": g[0] or "—", "visits": g[1],
        "last_date": to_jalali_str(g[2]),
        "avg_depth": round(g[3], 1) if g[3] is not None else None,
        "avg_test_flow": round(g[4], 2) if g[4] is not None else None,
        "avg_months": round(g[5], 1) if g[5] is not None else None,
        "failures": failure_counts.get(g[0], 0),
    } for g in grouped]
    return {"columns": [_col("well", "نام چاه"), _col("visits", "تعداد مراجعه", "number"),
                        _col("failures", "تعداد خرابی", "number"),
                        _col("last_date", "آخرین عملیات"),
                        _col("avg_depth", "میانگین عمق نصب", "number"),
                        _col("avg_test_flow", "میانگین دبی آزمایش", "number"),
                        _col("avg_months", "میانگین ماه کارکرد", "number")],
            "rows": rows, "summary": {"wells": len(rows)},
            "chart": {"type": "bar", "labels": [r["well"] for r in rows[:15]],
                      "values": [r["visits"] for r in rows[:15]]}}


# ── گزارش ۱۲ — تکرار خرابی ───────────────────────────────────────────────────
def report_failure_repeat(params):
    """«کدام چاه/پمپ/موتور بیشترین خرابی را داشته است؟» — requirement 19."""
    q = _base(params)
    ids = db.select(q.with_entities(Record.id).subquery())
    pump = db.aliased(LookupItem)
    motor = db.aliased(LookupItem)
    grouped = (db.session.query(
        func.coalesce(Well.name, Record.well_name_raw).label("well"),
        pump.value, motor.value,
        func.count(func.distinct(RecordTag.record_id)),
        func.max(Record.op_date), func.avg(Record.working_months))
        .select_from(Record)
        .join(RecordTag, db.and_(RecordTag.record_id == Record.id,
                                 RecordTag.category_code == "failure_reason"))
        .outerjoin(Well, Record.well_id == Well.id)
        .outerjoin(pump, Record.pump_curr_id == pump.id)
        .outerjoin(motor, Record.motor_curr_id == motor.id)
        .filter(Record.id.in_(ids))
        .group_by("well", pump.value, motor.value)
        .order_by(func.count(func.distinct(RecordTag.record_id)).desc())
        .limit(300).all())
    rows = [{"well": g[0] or "—", "pump": g[1] or "—", "motor": g[2] or "—",
             "failure_count": g[3], "last_failure": to_jalali_str(g[4]),
             "avg_months": round(g[5], 1) if g[5] is not None else None}
            for g in grouped]
    return {"columns": [_col("well", "چاه"), _col("pump", "تیپ پمپ"),
                        _col("motor", "تیپ موتور"),
                        _col("failure_count", "تعداد خرابی", "number"),
                        _col("last_failure", "آخرین خرابی"),
                        _col("avg_months", "میانگین ماه کارکرد", "number")],
            "rows": rows, "summary": {"combinations": len(rows)},
            "chart": {"type": "bar", "labels": [r["well"] for r in rows[:15]],
                      "values": [r["failure_count"] for r in rows[:15]]}}


# ── گزارش ۱۳ — تست پمپاژ ─────────────────────────────────────────────────────
def report_pumping_test(params):
    q = _base(params).filter(or_(Record.test_flow.isnot(None),
                                 Record.test_pressure.isnot(None),
                                 Record.test_date.isnot(None)))
    rows = []
    for rec in q.order_by(Record.test_date.desc().nullslast()).limit(5000).all():
        rows.append({
            "test_date": to_jalali_str(rec.test_date) or (rec.test_date_raw or ""),
            "well": rec.well.name if rec.well else rec.well_name_raw,
            "center": _label(rec.center_id),
            "pump": _label(rec.pump_curr_id), "stages": rec.pump_stages,
            "motor": _label(rec.motor_curr_id),
            "test_pressure": rec.test_pressure, "test_flow": rec.test_flow,
            "design_flow": rec.design_flow, "total_head": rec.total_head,
            "static_level": rec.static_level, "dynamic_level": rec.dynamic_level,
        })
    flows = [r["test_flow"] for r in rows if r["test_flow"] is not None]
    return {"columns": [_col("test_date", "تاریخ آزمایش"), _col("well", "چاه"),
                        _col("center", "مرکز"), _col("pump", "تیپ پمپ"),
                        _col("stages", "طبقه", "number"), _col("motor", "تیپ موتور"),
                        _col("test_pressure", "فشار آزمایش", "number"),
                        _col("test_flow", "دبی آزمایش", "number"),
                        _col("design_flow", "دبی طراحی", "number"),
                        _col("total_head", "هد کلی", "number"),
                        _col("static_level", "سطح استاتیک", "number"),
                        _col("dynamic_level", "سطح دینامیک", "number")],
            "rows": rows,
            "summary": {"tests": len(rows),
                        "avg_test_flow": round(sum(flows) / len(flows), 2) if flows else None},
            "chart": None}


# ── گزارش ۱۴ — مقایسه طراحی و تست ────────────────────────────────────────────
def report_design_vs_test(params):
    """دبی طراحی در برابر دبی آزمایش — الگوی شیت «رجائی 2»."""
    q = _base(params).filter(Record.design_flow.isnot(None),
                             Record.test_flow.isnot(None))
    rows = []
    for rec in q.order_by(Record.op_date.desc().nullslast()).limit(5000).all():
        diff = round(rec.test_flow - rec.design_flow, 2)
        pct = round(diff / rec.design_flow * 100, 1) if rec.design_flow else None
        rows.append({
            "date": to_jalali_str(rec.op_date),
            "well": rec.well.name if rec.well else rec.well_name_raw,
            "pump": _label(rec.pump_curr_id), "stages": rec.pump_stages,
            "total_head": rec.total_head,
            "design_flow": rec.design_flow, "test_flow": rec.test_flow,
            "difference": diff, "deviation_pct": pct,
            "status": "بالاتر از طراحی" if diff > 0 else
                      ("مطابق طراحی" if diff == 0 else "پایین‌تر از طراحی"),
        })
    under = [r for r in rows if r["difference"] < 0]
    diffs = [r["difference"] for r in rows]
    return {"columns": [_col("date", "تاریخ"), _col("well", "چاه"),
                        _col("pump", "تیپ پمپ"), _col("stages", "طبقه", "number"),
                        _col("total_head", "هد کلی", "number"),
                        _col("design_flow", "دبی طراحی", "number"),
                        _col("test_flow", "دبی آزمایش", "number"),
                        _col("difference", "اختلاف", "number"),
                        _col("deviation_pct", "انحراف (٪)", "number"),
                        _col("status", "وضعیت")],
            "rows": rows,
            "summary": {"compared": len(rows), "below_design": len(under),
                        "avg_difference": round(sum(diffs) / len(diffs), 2) if diffs else None},
            "chart": None}


REPORTS = {
    "overall": {"title": "گزارش ۱ — گزارش کلی کارگاه", "fn": report_overall,
                "desc": "شمارش کلی رکوردها، عملیات، خرابی، چاه، پمپ، موتور و پیمانکار."},
    "date_range": {"title": "گزارش ۲ — گزارش بر اساس بازه زمانی", "fn": report_date_range,
                   "desc": "فهرست رکوردها بین دو تاریخ شمسی."},
    "monthly": {"title": "گزارش ۳ — گزارش ماهانه", "fn": report_monthly,
                "desc": "تعداد عملیات و رکوردها به تفکیک ماه شمسی."},
    "yearly": {"title": "گزارش ۴ — گزارش سالانه", "fn": report_yearly,
               "desc": "مقایسه‌ی سال‌ها بر اساس الگوی شیت «99-403» اکسل کارگاه."},
    "operation": {"title": "گزارش ۵ — گزارش نوع عملیات",
                  "fn": lambda p: _group_by_lookup(p, "operation_id", "نوع عملیات"),
                  "desc": "Group By نوع عملیات."},
    "failure": {"title": "گزارش ۶ — گزارش خرابی",
                "fn": lambda p: _group_by_tag(p, "failure_reason", "علت خرابی"),
                "desc": "Group By علت خرابی (چندانتخابی)."},
    "contractor": {"title": "گزارش ۷ — گزارش پیمانکار",
                   "fn": lambda p: _group_by_lookup(p, "contractor_id", "پیمانکار", True),
                   "desc": "Group By پیمانکار به همراه میانگین شاخص‌های فنی."},
    "center": {"title": "گزارش ۸ — گزارش مرکز",
               "fn": lambda p: _group_by_lookup(p, "center_id", "مرکز", True),
               "desc": "Group By مرکز/کارگاه."},
    "pump": {"title": "گزارش ۹ — گزارش پمپ",
             "fn": lambda p: _group_by_lookup(p, "pump_curr_id", "تیپ پمپ", True),
             "desc": "بر اساس تیپ پمپ، همراه با میانگین دبی و هد."},
    "motor": {"title": "گزارش ۱۰ — گزارش الکتروموتور",
              "fn": lambda p: _group_by_lookup(p, "motor_curr_id", "تیپ الکتروموتور (KW)", True),
              "desc": "بر اساس توان الکتروموتور."},
    "wells": {"title": "گزارش ۱۱ — گزارش چاه", "fn": report_wells,
              "desc": "تعداد مراجعه، خرابی و شاخص‌های میانگین هر چاه."},
    "failure_repeat": {"title": "گزارش ۱۲ — گزارش تکرار خرابی", "fn": report_failure_repeat,
                       "desc": "کدام چاه/پمپ/موتور بیشترین خرابی را داشته است."},
    "pumping_test": {"title": "گزارش ۱۳ — گزارش تست پمپاژ", "fn": report_pumping_test,
                     "desc": "رکوردهای دارای آزمایش پمپاژ کارگاه مکانیک."},
    "design_vs_test": {"title": "گزارش ۱۴ — مقایسه مشخصات طراحی و نتیجه تست",
                       "fn": report_design_vs_test,
                       "desc": "دبی طراحی در برابر دبی آزمایش و درصد انحراف."},
    "maker": {"title": "گزارش تکمیلی — سازنده/تعمیرکار",
              "fn": lambda p: _group_by_lookup(p, "pump_maker_id", "سازنده/تعمیرکار پمپ", True),
              "desc": "سهم هر سازنده در تعمیر پمپ‌ها."},
    "opinion": {"title": "گزارش تکمیلی — نظر کارگاه مکانیک",
                "fn": lambda p: _group_by_tag(p, "workshop_opinion", "نظر کارگاه"),
                "desc": "تشخیص نهایی کارگاه مکانیک."},
    "executor": {"title": "گزارش تکمیلی — مجری (امانی/پیمانی)",
                 "fn": lambda p: _group_by_lookup(p, "executor_id", "مجری"),
                 "desc": "بُعد «مجری» برگرفته از شیت «99-403» اکسل کارگاه."},
}


def run_report(key: str, params: dict) -> dict:
    spec = REPORTS.get(key)
    if spec is None:
        raise KeyError(key)
    result = spec["fn"](params or {})
    result["key"] = key
    result["title"] = spec["title"]
    result["description"] = spec["desc"]
    result["filters"] = {k: v for k, v in (params or {}).items() if v}
    return result
