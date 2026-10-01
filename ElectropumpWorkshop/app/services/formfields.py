# -*- coding: utf-8 -*-
"""Behaviour of the form builder's special field types.

* «محاسباتی» (formula) — computed on the server from the other answers, so a
  number the browser showed is also the number that is stored, whatever the
  browser sends. The formula language is the report builder's: fields as
  [field_name] or [label], + − × ÷, ROUND, MIN, MAX, IF…
* «مستند» (file) — its answer is the list of documents uploaded into it on
  this process; the server reads that list from the attachments table rather
  than trusting the page.
* «فیلد مشترک» (mirror) — resolved where forms are drawn (FormField.render_dict);
  nothing here needs to know about it except that it stores nothing.
"""
from __future__ import annotations

from ..models import FormField


def _field_map():
    fields = {}
    for f in FormField.query.filter(FormField.is_active.is_(True)).all():
        if f.field_type == "mirror":
            continue
        fields[f.field_name] = {"key": f.field_name, "label": f.label,
                                "type": "decimal" if f.field_type in ("number", "formula")
                                else "text"}
    return fields


def compile_field_formula(text: str, exclude: str | None = None):
    """Validate a form formula; returns the compiled tree or raises FormulaError."""
    from ..analytics.formula import compile_formula
    fields = _field_map()
    if exclude:
        fields.pop(exclude, None)
    comp = compile_formula(text or "", fields)
    if comp["kind"] != "row":
        from ..analytics.formula import FormulaError
        raise FormulaError("در فرم فقط فرمول سطری (بدون SUM، COUNT و…) مجاز است.")
    return comp


def _numeric(v):
    if isinstance(v, str):
        t = v.strip().translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٫", "0123456789.")).replace(",", "")
        try:
            return float(t)
        except ValueError:
            return v
    return v


def formula_fields():
    return [f for f in FormField.query.filter(FormField.is_active.is_(True),
                                              FormField.field_type == "formula").all()
            if (f.formula or "").strip()]


def compute_formulas(values: dict, only: set | None = None) -> dict:
    """{field_name: value} for every formula field whose inputs are present."""
    from ..analytics.formula import Evaluator, FormulaError
    targets = [f for f in formula_fields() if only is None or f.field_name in only]
    if not targets:
        return {}
    fields = _field_map()
    ev = Evaluator(fields)
    row = {k: _numeric(v) for k, v in (values or {}).items()}
    out = {}
    # formulas may use each other (a pump calculation chains a dozen deep):
    # passes until nothing changes
    for _ in range(max(3, len(targets) + 1)):
        changed = False
        for f in targets:
            try:
                comp = compile_field_formula(f.formula, exclude=f.field_name)
                v = ev.row(comp["tree"], row)
            except (FormulaError, ZeroDivisionError, TypeError, ValueError):
                v = None
            if isinstance(v, float):
                try:
                    dec = int(f.step) if (f.step or "").strip().isdigit() else 4
                except ValueError:
                    dec = 4
                v = round(v, dec)
            if row.get(f.field_name) != v:
                row[f.field_name] = v
                out[f.field_name] = v
                changed = True
        if not changed:
            break
    return {k: v for k, v in out.items()}


def autofill_fields():
    """Ordinary fields whose «مقدار پیش‌فرض» is a formula («=…»): filled with the
    result while left empty, and editable like any answer."""
    return [f for f in FormField.query.filter(FormField.is_active.is_(True),
                                              FormField.default_value.like("=%")).all()
            if f.field_type not in ("formula", "chart", "file", "mirror")]


def compute_autofill(values: dict) -> dict:
    """{field_name: value} for the formula defaults of fields sent empty."""
    from ..analytics.formula import Evaluator, FormulaError
    out = {}
    targets = [f for f in autofill_fields()
               if f.field_name in values and values.get(f.field_name) in (None, "", [])]
    if not targets:
        return out
    ev = Evaluator(_field_map())
    row = {k: _numeric(v) for k, v in values.items()}
    for f in targets:
        try:
            comp = compile_field_formula(f.default_value[1:], exclude=f.field_name)
            v = ev.row(comp["tree"], row)
        except (FormulaError, ZeroDivisionError, TypeError, ValueError):
            v = None
        if v in (None, ""):
            continue
        if isinstance(v, float):
            v = round(v, 4)
        out[f.field_name] = v
    return out


def apply_formulas_to_payload(payload: dict) -> dict:
    """The entry page's nested shape or the workflow's flat one, with formulas filled."""
    payload = dict(payload or {})
    nested = isinstance(payload.get("dynamic"), dict)
    flat = dict(payload)
    if nested:
        flat.update(payload["dynamic"])
    computed = compute_formulas(flat)
    filled = compute_autofill({**flat, **computed})
    if filled:                                   # a filled value may feed other formulas
        computed = compute_formulas({**flat, **filled})
    if not computed and not filled:
        return payload
    if nested:
        dyn = dict(payload["dynamic"])
        dyn.update(computed)
        for k, v in filled.items():
            if k in payload and k != "dynamic":
                payload[k] = v               # a column of the record itself
            else:
                dyn[k] = v
        payload["dynamic"] = dyn
    else:
        payload.update(computed)
        payload.update(filled)
    return payload


def file_field_names() -> set:
    return {f.field_name for f in FormField.query.filter(
        FormField.is_active.is_(True), FormField.field_type == "file").all()}


def files_by_field(instance) -> dict:
    """{field_name: [attachment dict]} for a process's «مستند» fields."""
    out = {}
    for a in getattr(instance, "attachments", None) or []:
        if a.field_name:
            out.setdefault(a.field_name, []).append(a.to_dict())
    return out
