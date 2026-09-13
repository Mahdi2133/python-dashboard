# -*- coding: utf-8 -*-
"""Dynamic Report Builder (requirement 20).

    Dataset → Fields → Filters → Grouping → Sorting → Aggregation

Only columns declared in ``DATASETS`` can be referenced, and every value the
user supplies is bound as a SQLAlchemy parameter, so a report definition can
never turn into SQL injection.
"""
from __future__ import annotations

from sqlalchemy import func

from ..extensions import db
from ..models import LookupItem, Record, RecordTag, Well
from ..services.jalali import MONTHS_FA, to_jalali_str
from ..services.records import search_query

AGGREGATIONS = {
    "count": ("تعداد", func.count),
    "count_distinct": ("تعداد یکتا", lambda c: func.count(func.distinct(c))),
    "sum": ("جمع", func.sum),
    "avg": ("میانگین", func.avg),
    "min": ("کمینه", func.min),
    "max": ("بیشینه", func.max),
}

OPERATORS = {
    "eq": "برابر", "ne": "نامساوی", "gt": "بزرگ‌تر از", "gte": "بزرگ‌تر مساوی",
    "lt": "کوچک‌تر از", "lte": "کوچک‌تر مساوی", "contains": "شامل",
    "is_null": "خالی", "not_null": "پرشده",
}


def _lookup_field(key, label, attr, category):
    return {"key": key, "label": label, "kind": "lookup", "attr": attr,
            "category": category}


def _plain(key, label, attr, kind="number"):
    return {"key": key, "label": label, "kind": kind, "attr": attr}


RECORD_FIELDS = [
    {"key": "well", "label": "نام چاه", "kind": "well"},
    {"key": "j_year", "label": "سال شمسی", "kind": "int", "attr": "j_year"},
    {"key": "j_month", "label": "ماه شمسی", "kind": "month", "attr": "j_month"},
    {"key": "op_date", "label": "تاریخ عملیات", "kind": "date", "attr": "op_date"},
    _lookup_field("center", "مرکز", "center_id", "center"),
    _lookup_field("shift", "شیفت کاری", "shift_id", "shift"),
    _lookup_field("operation", "نوع عملیات", "operation_id", "operation"),
    _lookup_field("pm", "فرم نصب در PM", "pm_id", "pm_form"),
    _lookup_field("contractor", "پیمانکار", "contractor_id", "contractor"),
    _lookup_field("executor", "مجری", "executor_id", "executor"),
    _lookup_field("motor_prev", "تیپ موتور قبلی", "motor_prev_id", "motor_type"),
    _lookup_field("motor_curr", "تیپ موتور فعلی", "motor_curr_id", "motor_type"),
    _lookup_field("motor_maker", "سازنده موتور", "motor_maker_id", "maker"),
    _lookup_field("motor_condition", "نو/تعمیری موتور", "motor_condition_id", "condition"),
    _lookup_field("pump_prev", "تیپ پمپ قبلی", "pump_prev_id", "pump_type"),
    _lookup_field("pump_curr", "تیپ پمپ فعلی", "pump_curr_id", "pump_type"),
    _lookup_field("pump_maker", "سازنده پمپ", "pump_maker_id", "maker"),
    _lookup_field("pump_condition", "نو/تعمیری پمپ", "pump_condition_id", "condition"),
    _lookup_field("type_change", "تغییر تیپ", "type_change_id", "change_flag"),
    _lookup_field("pipe_diameter", "قطر لوله آبده", "pipe_diameter_id", "pipe_diameter"),
    _lookup_field("starter", "راه‌انداز", "starter_id", "starter"),
    _lookup_field("cable_size", "سایز کابل", "cable_size_id", "cable_size"),
    _plain("pump_stages", "طبقه پمپ", "pump_stages"),
    _plain("well_depth", "عمق چاه", "well_depth"),
    _plain("prev_install_depth", "عمق نصب قبلی", "prev_install_depth"),
    _plain("curr_install_depth", "عمق نصب فعلی", "curr_install_depth"),
    _plain("static_level", "سطح استاتیک", "static_level"),
    _plain("dynamic_level", "سطح دینامیک", "dynamic_level"),
    _plain("path_loss", "تلفات مسیر", "path_loss"),
    _plain("network_pressure", "فشار شبکه", "network_pressure"),
    _plain("total_head", "هد کلی", "total_head"),
    _plain("design_flow", "دبی طراحی", "design_flow"),
    _plain("test_pressure", "فشار آزمایش", "test_pressure"),
    _plain("test_flow", "دبی آزمایش", "test_flow"),
    _plain("flow_after_install", "دبی پس از نصب", "flow_after_install"),
    _plain("flow_before_pull", "دبی قبل از کشیدن", "flow_before_pull"),
    _plain("working_months", "تعداد ماه کارکرد", "working_months"),
    _plain("young_wells", "چاه با عمر کمتر از یک سال", "young_wells"),
    _plain("motor_plaque", "پلاک موتور", "motor_plaque", "text"),
    _plain("pump_plaque", "پلاک پمپ", "pump_plaque", "text"),
    _plain("install_supervisor", "ناظر نصب", "install_supervisor", "text"),
    _plain("cable_well", "چاه کابل", "cable_well", "text"),
    _plain("description", "توضیحات", "description", "text"),
    _plain("workshop_note", "شرح خرابی کارگاه", "workshop_note", "text"),
]

TAG_FIELDS = [
    {"key": "failure", "label": "علت خرابی", "kind": "tag", "category": "failure_reason"},
    {"key": "workshop_opinion", "label": "نظر کارگاه مکانیک", "kind": "tag",
     "category": "workshop_opinion"},
    {"key": "desc_tags", "label": "برچسب توضیحات", "kind": "tag", "category": "desc_tag"},
]

DATASETS = {
    "records": {
        "label": "رکوردهای عملیات کارگاه",
        "fields": RECORD_FIELDS + TAG_FIELDS,
    },
}

_FIELD_INDEX = {f["key"]: f for f in RECORD_FIELDS + TAG_FIELDS}


def _column_for(field, alias_cache):
    """Return (sqlalchemy expression, needs_join) for a declared field."""
    kind = field["kind"]
    if kind == "lookup":
        alias = alias_cache.get(field["key"])
        if alias is None:
            alias = db.aliased(LookupItem)
            alias_cache[field["key"]] = (alias, field["attr"])
            return alias.value, ("lookup", alias, field["attr"])
        return alias[0].value, None
    if kind == "well":
        return func.coalesce(Well.name, Record.well_name_raw), ("well", None, None)
    if kind == "tag":
        return RecordTag.value, ("tag", None, field["category"])
    return getattr(Record, field["attr"]), None


def _apply_filter(query, field, operator, value):
    if field["kind"] == "tag":
        clause = RecordTag.value == value
        if operator == "contains":
            clause = RecordTag.value.ilike(f"%{value}%")
        return query.filter(Record.tags.any(
            db.and_(RecordTag.category_code == field["category"], clause)))
    if field["kind"] == "lookup":
        alias = db.aliased(LookupItem)
        query = query.outerjoin(alias, getattr(Record, field["attr"]) == alias.id)
        col = alias.value
    elif field["kind"] == "well":
        query = query.outerjoin(Well, Record.well_id == Well.id)
        col = func.coalesce(Well.name, Record.well_name_raw)
    else:
        col = getattr(Record, field["attr"])

    if operator == "is_null":
        return query.filter(col.is_(None))
    if operator == "not_null":
        return query.filter(col.isnot(None))
    if operator == "contains":
        return query.filter(col.ilike(f"%{value}%"))
    ops = {"eq": col.__eq__, "ne": col.__ne__, "gt": col.__gt__,
           "gte": col.__ge__, "lt": col.__lt__, "lte": col.__le__}
    fn = ops.get(operator)
    if fn is None:
        raise ValueError(f"عملگر نامعتبر: {operator}")
    return query.filter(fn(value))


def run_builder(spec: dict) -> dict:
    """Execute a report definition and return the standard report envelope."""
    dataset = spec.get("dataset") or "records"
    if dataset not in DATASETS:
        raise ValueError("مجموعه‌داده انتخاب‌شده معتبر نیست.")

    group_keys = [k for k in (spec.get("group_by") or []) if k in _FIELD_INDEX]
    aggs = []
    for agg in (spec.get("aggregations") or []):
        fn = agg.get("fn") or "count"
        if fn not in AGGREGATIONS:
            raise ValueError(f"تابع تجمیع نامعتبر: {fn}")
        key = agg.get("field")
        if fn not in ("count",) and key not in _FIELD_INDEX:
            raise ValueError("فیلد تجمیع را انتخاب کنید.")
        aggs.append({"fn": fn, "field": key})
    if not aggs:
        aggs = [{"fn": "count", "field": None}]

    # Filters from the shared bar (dates, center, …) plus explicit ones.
    base = search_query(spec.get("base_filters") or {}).order_by(None)
    query = base
    for flt in (spec.get("filters") or []):
        field = _FIELD_INDEX.get(flt.get("field"))
        if field is None:
            continue
        query = _apply_filter(query, field, flt.get("op") or "eq", flt.get("value"))

    if not group_keys:
        return _run_flat(query, spec, aggs)
    return _run_grouped(query, spec, group_keys, aggs)


def _needs_tag_join(keys):
    return [k for k in keys if _FIELD_INDEX[k]["kind"] == "tag"]


def _run_grouped(query, spec, group_keys, aggs):
    ids = db.select(query.with_entities(Record.id).subquery())
    q = db.session.query().select_from(Record).filter(Record.id.in_(ids))

    selects, columns = [], []
    joined_wells = False
    for key in group_keys:
        field = _FIELD_INDEX[key]
        if field["kind"] == "lookup":
            alias = db.aliased(LookupItem)
            q = q.outerjoin(alias, getattr(Record, field["attr"]) == alias.id)
            col = alias.value
        elif field["kind"] == "well":
            if not joined_wells:
                q = q.outerjoin(Well, Record.well_id == Well.id)
                joined_wells = True
            col = func.coalesce(Well.name, Record.well_name_raw)
        elif field["kind"] == "tag":
            tag_alias = db.aliased(RecordTag)
            q = q.join(tag_alias, db.and_(tag_alias.record_id == Record.id,
                                          tag_alias.category_code == field["category"]))
            col = tag_alias.value
        else:
            col = getattr(Record, field["attr"])
        selects.append(col.label(key))
        columns.append({"key": key, "label": field["label"], "type": "text"})

    for agg in aggs:
        label_fa, fn = AGGREGATIONS[agg["fn"]]
        if agg["field"] is None:
            expr = func.count(Record.id)
            col_label, col_key = "تعداد", "count"
        else:
            field = _FIELD_INDEX[agg["field"]]
            if field["kind"] in ("lookup", "well", "tag"):
                target = Record.id
            else:
                target = getattr(Record, field["attr"])
            expr = fn(target)
            col_key = f"{agg['fn']}_{agg['field']}"
            col_label = f"{label_fa} {field['label']}"
        selects.append(expr.label(col_key))
        columns.append({"key": col_key, "label": col_label, "type": "number"})

    q = q.with_entities(*selects).group_by(*[s for s in selects[:len(group_keys)]])

    sort_key = spec.get("sort_by")
    direction = (spec.get("sort_dir") or "desc").lower()
    sort_col = next((s for s, c in zip(selects, columns) if c["key"] == sort_key), None)
    if sort_col is None:
        sort_col = selects[len(group_keys)] if len(selects) > len(group_keys) else selects[0]
    q = q.order_by(sort_col.desc() if direction == "desc" else sort_col.asc())

    limit = min(int(spec.get("limit") or 1000), 20000)
    rows = []
    for r in q.limit(limit).all():
        row = {}
        for col, value in zip(columns, r):
            if col["key"] == "j_month" and value:
                value = MONTHS_FA[int(value)]
            if isinstance(value, float):
                value = round(value, 3)
            row[col["key"]] = value if value is not None else "—"
        rows.append(row)

    return {"columns": columns, "rows": rows,
            "summary": {"groups": len(rows)},
            "chart": {"type": "bar",
                      "labels": [str(r[columns[0]["key"]]) for r in rows[:20]],
                      "values": [r[columns[len(group_keys)]["key"]] for r in rows[:20]]}
            if len(columns) > len(group_keys) else None}


def _run_flat(query, spec, aggs):
    """No grouping: either a plain field listing, or overall totals."""
    field_keys = [k for k in (spec.get("fields") or []) if k in _FIELD_INDEX]
    if not field_keys:
        # Aggregations over the whole filtered set.
        ids = db.select(query.with_entities(Record.id).subquery())
        selects, columns = [], []
        for agg in aggs:
            label_fa, fn = AGGREGATIONS[agg["fn"]]
            if agg["field"] is None:
                selects.append(func.count(Record.id))
                columns.append({"key": "count", "label": "تعداد", "type": "number"})
            else:
                field = _FIELD_INDEX[agg["field"]]
                target = (getattr(Record, field["attr"])
                          if field["kind"] not in ("lookup", "well", "tag") else Record.id)
                selects.append(fn(target))
                columns.append({"key": f"{agg['fn']}_{agg['field']}",
                                "label": f"{label_fa} {field['label']}", "type": "number"})
        values = db.session.query(*selects).filter(Record.id.in_(ids)).one()
        row = {c["key"]: (round(v, 3) if isinstance(v, float) else v)
               for c, v in zip(columns, values)}
        return {"columns": columns, "rows": [row], "summary": {}, "chart": None}

    limit = min(int(spec.get("limit") or 1000), 20000)
    sort_key = spec.get("sort_by")
    direction = (spec.get("sort_dir") or "desc").lower()
    if sort_key in _FIELD_INDEX and _FIELD_INDEX[sort_key]["kind"] not in (
            "lookup", "well", "tag"):
        col = getattr(Record, _FIELD_INDEX[sort_key]["attr"])
        query = query.order_by(col.desc().nullslast() if direction == "desc"
                               else col.asc().nullsfirst())
    else:
        query = query.order_by(Record.op_date.desc().nullslast())

    columns = [{"key": k, "label": _FIELD_INDEX[k]["label"], "type": "text"}
               for k in field_keys]
    rows = []
    for rec in query.limit(limit).all():
        row = {}
        for key in field_keys:
            field = _FIELD_INDEX[key]
            if field["kind"] == "lookup":
                item = db.session.get(LookupItem, getattr(rec, field["attr"]))
                row[key] = item.value if item else "—"
            elif field["kind"] == "well":
                row[key] = rec.well.name if rec.well else (rec.well_name_raw or "—")
            elif field["kind"] == "tag":
                row[key] = "، ".join(rec.tag_values(field["category"])) or "—"
            elif field["kind"] == "month":
                row[key] = MONTHS_FA[rec.j_month] if rec.j_month else "—"
            elif field["kind"] == "date":
                row[key] = to_jalali_str(getattr(rec, field["attr"])) or "—"
            else:
                value = getattr(rec, field["attr"])
                row[key] = value if value is not None else "—"
        rows.append(row)
    return {"columns": columns, "rows": rows, "summary": {"count": len(rows)},
            "chart": None}
