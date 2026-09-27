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

# ── fields the admin added ───────────────────────────────────────────────────
#
# Everything above is a column on ``records``. The form builder's own fields —
# the parameters of each علت خرابی among them — live in ``record_dynamic_values``
# instead, one row per answer, and the admin adds and removes them at will. So
# they are read from the form definition each time rather than listed here, and
# they are offered for listing and for calculation; grouping and aggregation
# still work on the fixed columns only.
_DYNAMIC_NUMERIC = ("number",)


def dynamic_fields() -> list:
    """The form-builder fields, as report fields."""
    from ..models import FormField
    out = []
    for f in (FormField.query.filter(FormField.is_active.is_(True),
                                     FormField.model_attr.is_(None),
                                     FormField.field_type != "mirror")
              .order_by(FormField.sort_order).all()):
        out.append({
            "key": f"dyn.{f.field_name}", "label": f.label, "kind": "dynamic",
            "attr": f.field_name,
            "numeric": f.field_type in _DYNAMIC_NUMERIC,
            "section": f.section.title if f.section else None,
        })
    return out


DATASETS = {
    "records": {
        "label": "رکوردهای عملیات کارگاه",
        "fields": RECORD_FIELDS + TAG_FIELDS,
    },
}

_STATIC_INDEX = {f["key"]: f for f in RECORD_FIELDS + TAG_FIELDS}


class _FieldIndex:
    """The fixed columns plus whatever the form builder currently holds.

    A mapping rather than a dict so a field the admin added five minutes ago
    resolves without restarting anything; the fixed columns are still answered
    straight from the dict.
    """

    def __contains__(self, key):
        return self.get(key) is not None

    def get(self, key, default=None):
        if key in _STATIC_INDEX:
            return _STATIC_INDEX[key]
        if isinstance(key, str) and key.startswith("dyn."):
            return next((f for f in dynamic_fields() if f["key"] == key), default)
        return default

    def __getitem__(self, key):
        found = self.get(key)
        if found is None:
            raise KeyError(key)
        return found


_FIELD_INDEX = _FieldIndex()


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
    if field["kind"] == "dynamic":
        # A form-builder answer is a row in another table, matched by name.
        from ..models import FormField, RecordDynamicValue
        clause = RecordDynamicValue.value == str(value)
        if operator == "contains":
            clause = RecordDynamicValue.value.ilike(f"%{value}%")
        elif operator == "is_null":
            return query.filter(~Record.dynamic_values.any(
                RecordDynamicValue.field.has(
                    FormField.field_name == field["attr"])))
        elif operator == "not_null":
            return query.filter(Record.dynamic_values.any(
                RecordDynamicValue.field.has(
                    FormField.field_name == field["attr"])))
        return query.filter(Record.dynamic_values.any(db.and_(
            RecordDynamicValue.field.has(FormField.field_name == field["attr"]),
            clause)))
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


# ── calculated columns ───────────────────────────────────────────────────────
#
# «یک ستون تازه که نشان بدهد این عدد با آن عدد چه نسبتی دارد» — the admin names
# the column and picks the operation and the fields; nothing here knows what
# آمپر or فشار mean, so a calculation the workshop invents tomorrow needs no
# code. Each one is computed per row, after the row is read, so it works the
# same on a fixed column and on a form-builder field.
def _num(value):
    """A number, or None when the cell holds something that is not one."""
    if value is None or value == "" or value == "—":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace("٬", "").replace(",", "")
    for fa, en in zip("۰۱۲۳۴۵۶۷۸۹", "0123456789"):
        text = text.replace(fa, en)
    try:
        return float(text)
    except ValueError:
        return None


def _pct_change(values):
    """(new − base) ÷ base × 100, with the base first — «درصد تغییرات»."""
    if len(values) < 2 or values[0] == 0:
        return None
    return (values[1] - values[0]) / values[0] * 100.0


CALCULATIONS = {
    "sum":        ("جمع", lambda v: sum(v)),
    "diff":       ("تفاضل (اولی منهای بقیه)",
                   lambda v: v[0] - sum(v[1:]) if len(v) > 1 else None),
    "product":    ("حاصل‌ضرب", lambda v: _product(v)),
    "avg":        ("میانگین", lambda v: sum(v) / len(v)),
    "min":        ("کمینه", min),
    "max":        ("بیشینه", max),
    "range":      ("دامنه (بیشینه منهای کمینه)", lambda v: max(v) - min(v)),
    "ratio":      ("نسبت (اولی تقسیم بر دومی)",
                   lambda v: v[0] / v[1] if len(v) > 1 and v[1] else None),
    "pct_of":     ("درصد اولی از دومی",
                   lambda v: v[0] / v[1] * 100.0 if len(v) > 1 and v[1] else None),
    "pct_change": ("درصد تغییر (از اولی به دومی)", _pct_change),
}

# How many fields each one needs at least, so the builder can say so rather
# than quietly returning an empty column.
CALC_MIN_FIELDS = {"sum": 1, "avg": 1, "min": 1, "max": 1, "range": 2,
                   "diff": 2, "product": 2, "ratio": 2, "pct_of": 2,
                   "pct_change": 2}


def _product(values):
    out = 1.0
    for v in values:
        out *= v
    return out


def _read_calcs(spec: dict) -> list:
    """Validate the calculated columns a report asked for."""
    out = []
    for n, calc in enumerate(spec.get("computed") or [], start=1):
        fn = calc.get("fn")
        if fn not in CALCULATIONS:
            raise ValueError(f"تابع محاسباتی نامعتبر: {fn}")
        keys = [k for k in (calc.get("fields") or []) if k in _FIELD_INDEX]
        if len(keys) < CALC_MIN_FIELDS[fn]:
            raise ValueError(
                f"«{CALCULATIONS[fn][0]}» دست‌کم به "
                f"{CALC_MIN_FIELDS[fn]} فیلد عددی نیاز دارد.")
        out.append({
            "key": calc.get("key") or f"calc{n}",
            "label": (calc.get("label") or "").strip() or CALCULATIONS[fn][0],
            "fn": fn, "fields": keys,
            "decimals": max(0, min(int(calc.get("decimals") or 2), 6)),
            "suffix": (calc.get("suffix") or "").strip(),
        })
    return out


def _apply_calcs(row: dict, calcs: list):
    """Fill this row's calculated cells from the ones already read.

    A row missing one of the inputs gets «—» rather than a wrong number: a
    percentage of a blank reading is not zero, it is unknown.
    """
    for calc in calcs:
        values = [_num(row.get(k)) for k in calc["fields"]]
        if any(v is None for v in values):
            row[calc["key"]] = "—"
            continue
        try:
            answer = CALCULATIONS[calc["fn"]][1](values)
        except (ZeroDivisionError, ValueError, TypeError):
            answer = None
        if answer is None:
            row[calc["key"]] = "—"
        else:
            answer = round(answer, calc["decimals"])
            if calc["decimals"] == 0:
                answer = int(answer)
            row[calc["key"]] = (f"{answer}{calc['suffix']}" if calc["suffix"]
                                else answer)


def run_builder(spec: dict) -> dict:
    """Execute a report definition and return the standard report envelope."""
    dataset = spec.get("dataset") or "records"
    if dataset not in DATASETS:
        raise ValueError("مجموعه‌داده انتخاب‌شده معتبر نیست.")

    group_keys = [k for k in (spec.get("group_by") or []) if k in _FIELD_INDEX]
    # Grouping and aggregation run in SQL over the fixed columns. A
    # form-builder field lives one table away, so it is offered for listing and
    # for calculation but not for grouping — said plainly rather than returning
    # an empty report.
    bad = [k for k in group_keys if _FIELD_INDEX[k]["kind"] == "dynamic"]
    if bad:
        raise ValueError(
            "فیلدهای فرم‌ساز («" + "»، «".join(_FIELD_INDEX[k]["label"]
                                              for k in bad)
            + "») برای گروه‌بندی در دسترس نیستند؛ آن‌ها را در فهرست ستون‌ها "
              "یا در ستون‌های محاسباتی به کار ببرید.")
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
            "lookup", "well", "tag", "dynamic"):
        col = getattr(Record, _FIELD_INDEX[sort_key]["attr"])
        query = query.order_by(col.desc().nullslast() if direction == "desc"
                               else col.asc().nullsfirst())
    else:
        query = query.order_by(Record.op_date.desc().nullslast())

    calcs = _read_calcs(spec)
    columns = [{"key": k, "label": _FIELD_INDEX[k]["label"], "type": "text"}
               for k in field_keys]
    # The calculated columns come last, where a reader expects a total.
    columns += [{"key": c["key"], "label": c["label"], "type": "number",
                 "computed": True} for c in calcs]
    rows = []
    for rec in query.limit(limit).all():
        row = {}
        dyn = None
        for key in field_keys:
            field = _FIELD_INDEX[key]
            if field["kind"] == "dynamic":
                if dyn is None:
                    dyn = {v.field.field_name: v.value
                           for v in rec.dynamic_values if v.field}
                value = dyn.get(field["attr"])
                row[key] = value if value not in (None, "") else "—"
            elif field["kind"] == "lookup":
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
        _apply_calcs(row, calcs)
        rows.append(row)
    return {"columns": columns, "rows": rows, "summary": {"count": len(rows)},
            "chart": None}
