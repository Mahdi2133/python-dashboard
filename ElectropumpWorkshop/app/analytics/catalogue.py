# -*- coding: utf-8 -*-
"""Data sources a report can read, and the fields each one offers.

A source knows *how* to read rows; the fields it offers are built from what the
form builder and the process builder hold right now. A field added to a form
tomorrow is in the report builder tomorrow, with its type, its options and the
roles it can play — and no source or report knows any particular form.

Rows are plain dicts keyed by field key. Values keep their real type — a date is
a ``date``, a multi-choice answer is a list — so filters, groupings and
formulas can treat them properly; the renderers format them.

Adding a source is registering one more ``Source``: a key, a label, the base
permission its data needs, a field builder and a row loader.
"""
from __future__ import annotations

import datetime as _dt
import json
import re
import threading
from collections import defaultdict

from sqlalchemy import event

from ..extensions import db
from ..services.jalali import MONTHS_FA, gregorian_to_jalali, local_now, parse_jalali_to_date

# ── field types ────────────────────────────────────────────────────────────
TYPES = {
    "text": "متن", "integer": "عدد صحیح", "decimal": "عدد اعشاری",
    "percent": "درصد", "boolean": "بله/خیر", "date": "تاریخ",
    "datetime": "تاریخ و زمان", "time": "زمان", "single": "تک‌انتخابی",
    "multi": "چندانتخابی", "user": "کاربر", "center": "مرکز (واحد)",
    "file": "فایل/مستند", "relation": "ارتباط", "calc": "محاسباتی",
}
NUMERIC = {"integer", "decimal", "percent"}
TEMPORAL = {"date", "datetime"}
CATEGORICAL = {"text", "single", "multi", "user", "center", "boolean", "relation"}

# The roles a field can play in a report, by type. The builder offers only
# these, so a text field is never summed and a date is never averaged.
ROLES_BY_TYPE = {
    "numeric": ["measure", "dimension", "filter", "sort", "display", "kpi"],
    "temporal": ["dimension", "date", "filter", "sort", "display", "group"],
    "categorical": ["dimension", "category", "group", "filter", "sort", "display"],
}


def roles_for(ftype: str) -> list:
    if ftype in NUMERIC:
        return ROLES_BY_TYPE["numeric"]
    if ftype in TEMPORAL:
        return ROLES_BY_TYPE["temporal"]
    return ROLES_BY_TYPE["categorical"]


def fdef(key, label, ftype, group, **extra):
    data = {"key": key, "label": label, "type": ftype, "type_label": TYPES.get(ftype, ftype),
            "group": group, "roles": roles_for(ftype)}
    data.update({k: v for k, v in extra.items() if v is not None})
    return data


def jalali_parts(value):
    """(year, month, day) of a date or datetime, in the Jalali calendar."""
    if value is None:
        return None
    if isinstance(value, _dt.datetime):
        value = value.date()
    return gregorian_to_jalali(value)


def season_of(month: int | None) -> str | None:
    if not month:
        return None
    return ["بهار", "تابستان", "پاییز", "زمستان"][(int(month) - 1) // 3]


# ── the data version: any change to the data behind reports ────────────────
_DATA_VERSION = {"n": 0}
_WATCHED = None


def data_version() -> int:
    return _DATA_VERSION["n"]


def bump_data_version():
    _DATA_VERSION["n"] += 1


def _watched_classes():
    global _WATCHED
    if _WATCHED is None:
        from ..models import (AppUser, LookupItem, Record, RecordDynamicValue,
                              RecordTag, Well, WorkflowInstance, WorkflowStageEntry,
                              FormField, WorkflowStage)
        _WATCHED = (Record, RecordTag, RecordDynamicValue, WorkflowInstance,
                    WorkflowStageEntry, Well, AppUser, LookupItem, FormField,
                    WorkflowStage)
    return _WATCHED


def install_change_listener():
    """Bump the data version whenever reported-on data is written."""
    from sqlalchemy.orm import Session
    if _DATA_VERSION.get("listening"):
        return
    _DATA_VERSION["listening"] = True

    @event.listens_for(Session, "after_flush")
    def _after_flush(session, _ctx):
        watched = _watched_classes()
        for obj in list(session.new) + list(session.dirty) + list(session.deleted):
            if isinstance(obj, watched):
                bump_data_version()
                return


# ── row cache ──────────────────────────────────────────────────────────────
_CACHE: dict = {}
_CACHE_LOCK = threading.Lock()
_CACHE_MAX = 24


def cached_rows(source_key: str, scope, loader):
    key = (source_key, tuple(sorted(scope)) if scope is not None else None, data_version())
    with _CACHE_LOCK:
        hit = _CACHE.get(key)
    if hit is not None:
        return hit
    rows = loader(scope)
    with _CACHE_LOCK:
        if len(_CACHE) >= _CACHE_MAX:
            for stale in [k for k in _CACHE if k[2] != data_version()] or list(_CACHE)[:4]:
                _CACHE.pop(stale, None)
        _CACHE[key] = rows
    return rows


# ── shared lookups ─────────────────────────────────────────────────────────
def _lookups():
    from ..models import LookupItem
    return {i.id: i.label or i.value for i in LookupItem.query.all()}


def _user_names():
    from ..models import AppUser
    return {u.id: u.full_name for u in AppUser.query.all()}


# ── form fields as report fields ───────────────────────────────────────────
MULTI_TYPES = ("checkbox", "multiselect", "checklist")


def form_field_type(field) -> str:
    if field.field_type == "number":
        return "decimal"
    if field.field_type in ("date", "jalali_date"):
        return "date"
    if field.field_type in MULTI_TYPES:
        return "boolean" if field.model_attr == "reported_to_finance" else "multi"
    if field.field_type in ("select", "radio", "autocomplete"):
        if field.field_name == "center":
            return "center"
        return "single"
    return "text"


def form_field_options(field, labels_by_cat=None) -> list | None:
    if field.lookup_category == "__months__":
        return MONTHS_FA[1:]
    if field.options:
        return [o.label or o.value for o in field.options if o.is_active]
    if field.lookup_category and labels_by_cat is not None:
        return labels_by_cat.get(field.lookup_category)
    return None


def _labels_by_category():
    from ..models import LookupCategory
    out = {}
    for cat in LookupCategory.query.all():
        out[cat.code] = [i.label or i.value for i in
                         sorted(cat.items, key=lambda x: x.sort_order) if i.is_active]
    return out


def report_form_fields() -> list:
    """The form-builder fields reports can read.

    Every active field — and every hidden one that still has a column full of
    history: «نوع عملیات» is hidden in today's form but three thousand records
    carry it, and a report that forgot them would rewrite the workshop's past.
    """
    from ..models import FormField, FormSection
    from sqlalchemy import or_
    return (FormField.query.join(FormSection)
            .filter(or_(FormField.is_active.is_(True), FormField.model_attr.isnot(None)))
            .order_by(FormSection.sort_order, FormField.sort_order).all())


def form_fields(prefix: str = "", group_prefix: str = "") -> list:
    """Every reportable form-builder field, as a report field."""
    cats = _labels_by_category()
    out = []
    for field in report_form_fields():
        ftype = form_field_type(field)
        label = field.label + ("" if field.is_active else " (پنهان در فرم)")
        out.append(fdef(prefix + field.field_name, label, ftype,
                        group_prefix + (field.section.title if field.section else "فرم"),
                        options=form_field_options(field, cats) if ftype in ("single", "multi", "center") else None,
                        form_field=field.field_name,
                        form=field.section.code if field.section else None))
    return out


def _number(value):
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return value
    text = str(value).strip().translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٫،", "0123456789.,"))
    text = text.replace(",", "")
    try:
        num = float(text)
    except ValueError:
        return None
    return int(num) if num.is_integer() else num


def _date(value):
    if value in (None, ""):
        return None
    if isinstance(value, _dt.datetime):
        return value.date()
    if isinstance(value, _dt.date):
        return value
    text = str(value).strip()
    if re.match(r"^(19|20)\d\d-\d\d-\d\d", text):
        try:
            return _dt.date.fromisoformat(text[:10])
        except ValueError:
            return None
    return parse_jalali_to_date(text)


def coerce(ftype: str, value):
    """A raw answer (payload JSON, form text) as the field's own type."""
    if value in (None, "", [], {}):
        return None
    if ftype in NUMERIC:
        return _number(value)
    if ftype == "date":
        return _date(value)
    if ftype == "multi":
        if isinstance(value, list):
            return [str(v) for v in value if v not in (None, "")]
        return [v.strip() for v in re.split(r"[,،]", str(value)) if v.strip()]
    if ftype == "boolean":
        return str(value).lower() in ("1", "true", "yes", "بله", "on")
    if isinstance(value, list):
        return "، ".join(str(v) for v in value)
    return str(value)


# ── sources ────────────────────────────────────────────────────────────────
class Source:
    def __init__(self, key, label, description, permission, row_label,
                 fields, loader, id_label="شناسه", scope_note=None):
        self.key, self.label, self.description = key, label, description
        self.permission = permission          # a code, or a tuple of any-of codes
        self.row_label = row_label
        self._fields, self._loader = fields, loader
        self.id_label = id_label
        self.scope_note = scope_note

    def fields(self) -> list:
        return self._fields()

    def field_map(self) -> dict:
        return {f["key"]: f for f in self.fields()}

    def rows(self, scope=None) -> list:
        return cached_rows(self.key, scope, self._loader)

    def allowed_for(self, user) -> bool:
        if user is None:
            return False
        codes = self.permission if isinstance(self.permission, tuple) else (self.permission,)
        return any(user.can(c) for c in codes)

    def to_dict(self, with_fields=False):
        data = {"key": self.key, "label": self.label, "description": self.description,
                "row_label": self.row_label,
                "permission": list(self.permission) if isinstance(self.permission, tuple)
                else [self.permission]}
        if with_fields:
            data["fields"] = self.fields()
        return data


# records ────────────────────────────────────────────────────────────────────
def _record_fields():
    base = [
        fdef("_id", "شناسه رکورد", "integer", "مشخصات رکورد"),
        fdef("_date", "تاریخ عملیات", "date", "زمان"),
        fdef("_year", "سال (شمسی)", "integer", "زمان"),
        fdef("_month", "ماه", "single", "زمان", options=MONTHS_FA[1:]),
        fdef("_season", "فصل", "single", "زمان", options=["بهار", "تابستان", "پاییز", "زمستان"]),
        fdef("_well_class", "کلاس چاه", "single", "چاه"),
        fdef("_well_pm", "کد PM چاه", "text", "چاه"),
        fdef("_well_depth", "عمق چاه (از مشخصات چاه)", "decimal", "چاه"),
        fdef("_created_by", "ثبت‌کننده", "user", "مشخصات رکورد"),
        fdef("_created_at", "زمان ثبت", "datetime", "مشخصات رکورد"),
        fdef("_from_process", "ثبت از طریق فرایند", "boolean", "مشخصات رکورد"),
    ]
    return base + form_fields()


def _load_records(scope):
    from ..models import (FormField, Record, RecordDynamicValue, RecordTag, Well,
                          WorkflowInstance)
    labels = _lookups()
    users = _user_names()
    wells = {w.id: w for w in Well.query.all()}
    query = Record.query.filter(Record.is_active.is_(True))
    if scope is not None:
        query = query.filter(Record.center_id.in_(scope or [-1]))
    records = query.all()
    ids = [r.id for r in records]
    tags = defaultdict(lambda: defaultdict(list))
    dyn = defaultdict(dict)
    if ids:
        for chunk in range(0, len(ids), 900):
            part = ids[chunk:chunk + 900]
            for t in RecordTag.query.filter(RecordTag.record_id.in_(part)).all():
                tags[t.record_id][t.category_code].append(t.value)
            for v in RecordDynamicValue.query.filter(RecordDynamicValue.record_id.in_(part)).all():
                dyn[v.record_id][v.field_id] = v
    from_process = {rid for (rid,) in db.session.query(WorkflowInstance.record_id)
                    .filter(WorkflowInstance.record_id.isnot(None)).all()}
    fields = report_form_fields()
    multi_map = Record.MULTI_FIELDS
    rows = []
    for rec in records:
        well = wells.get(rec.well_id)
        row = {
            "_id": rec.id, "_date": rec.op_date, "_year": rec.j_year,
            "_month": MONTHS_FA[rec.j_month] if rec.j_month else None,
            "_season": season_of(rec.j_month),
            "_well_class": well.well_class if well else None,
            "_well_pm": well.pm_code if well else None,
            "_well_depth": well.depth if well else None,
            "_created_by": users.get(rec.created_by),
            "_created_at": rec.created_at,
            "_from_process": rec.id in from_process,
            "_center_id": rec.center_id,
            "_month_no": rec.j_month,
        }
        for f in fields:
            name = f.field_name
            ftype = form_field_type(f)
            value = None
            if name in multi_map:
                value = list(tags[rec.id].get(multi_map[name], []))
            elif f.model_attr:
                attr = f.model_attr
                raw = getattr(rec, attr, None)
                if attr == "well_id":
                    value = well.name if well else rec.well_name_raw
                elif attr == "pump_prev_id":
                    value = rec.pump_prev_raw or labels.get(raw)
                elif attr.endswith("_id"):
                    value = labels.get(raw)
                elif f.lookup_category == "__months__":
                    value = MONTHS_FA[raw] if isinstance(raw, int) and 1 <= raw <= 12 else None
                else:
                    value = raw
            else:
                holder = dyn[rec.id].get(f.id)
                if holder is not None:
                    if holder.value_num is not None:
                        value = holder.value_num
                    elif holder.value_date is not None:
                        value = holder.value_date
                    else:
                        value = coerce(ftype, holder.value_text)
            if ftype == "multi" and not isinstance(value, list):
                value = coerce("multi", value) or []
            row[name] = value
        rows.append(row)
    return rows


# processes ──────────────────────────────────────────────────────────────────
INSTANCE_STATUS_FA = {"open": "در جریان", "completed": "تکمیل‌شده", "cancelled": "لغوشده",
                      "stopped": "متوقف‌شده"}
ENTRY_STATUS_FA = {"pending": "در انتظار", "submitted": "ثبت‌شده", "skipped": "طی نشده",
                   "archived": "بایگانی", "deferred": "موکول به بعد",
                   "awaiting": "در انتظار تأیید", "rejected": "برگشت‌خورده"}

_RETURN_FROM = re.compile(r"برگشت (?:از )?مرحله (\d+)")


def _hours(start, end):
    if not start or not end:
        return None
    return round((end - start).total_seconds() / 3600.0, 2)


def _returns_by_instance():
    """How many times each run was sent back, and from which stages."""
    from ..models import AuditLog
    per_run, per_stage = defaultdict(int), defaultdict(int)
    for entity_id, summary in (db.session.query(AuditLog.entity_id, AuditLog.summary)
                               .filter(AuditLog.entity == "workflow",
                                       AuditLog.summary.like("برگشت%")).all()):
        if entity_id is None:
            continue
        per_run[entity_id] += 1
        m = _RETURN_FROM.search(summary or "")
        if m:
            per_stage[(entity_id, int(m.group(1)))] += 1
    return per_run, per_stage


def _stage_timing_fields():
    from ..models import WorkflowDefinition
    out = []
    for wf in WorkflowDefinition.query.order_by(WorkflowDefinition.id).all():
        for st in sorted(wf.stages, key=lambda s: s.stage_number):
            if not st.is_active or st.stage_number == 0:
                continue
            out.append(fdef(f"_stage_{st.id}_hours",
                            f"مدت مرحله «{st.title}» — {wf.name} (ساعت)", "decimal",
                            "زمان مراحل", stage=st.id, process=wf.id))
    return out


def _process_fields():
    base = [
        fdef("_id", "شناسه فرایند", "integer", "اجرای فرایند"),
        fdef("_process", "فرایند", "single", "اجرای فرایند"),
        fdef("_kind", "نوع عملیات", "single", "اجرای فرایند", options=["کشیدن", "نصب"]),
        fdef("_status", "وضعیت فرایند", "single", "اجرای فرایند",
             options=list(INSTANCE_STATUS_FA.values())),
        fdef("_well", "چاه", "single", "اجرای فرایند"),
        fdef("_center", "مرکز", "center", "اجرای فرایند"),
        fdef("_created_by", "ایجادکننده", "user", "اجرای فرایند"),
        fdef("_created_at", "زمان شروع", "datetime", "زمان"),
        fdef("_created_date", "تاریخ شروع", "date", "زمان"),
        fdef("_completed_at", "زمان پایان", "datetime", "زمان"),
        fdef("_completed_date", "تاریخ پایان", "date", "زمان"),
        fdef("_duration_hours", "مدت اجرا (ساعت)", "decimal", "زمان"),
        fdef("_duration_days", "مدت اجرا (روز)", "decimal", "زمان"),
        fdef("_current_stage", "مرحله‌ی جاری", "single", "اجرای فرایند"),
        fdef("_entry_stage", "مرحله‌ی شروع", "single", "اجرای فرایند"),
        fdef("_stages_total", "تعداد مراحل", "integer", "اجرای فرایند"),
        fdef("_stages_done", "مراحل ثبت‌شده", "integer", "اجرای فرایند"),
        fdef("_returns", "تعداد برگشت", "integer", "اجرای فرایند"),
        fdef("_delays", "تعداد مراحل تأخیردار", "integer", "اجرای فرایند"),
        fdef("_referrals", "تعداد ارجاع", "integer", "اجرای فرایند"),
        fdef("_outcome_note", "دلیل توقف", "text", "اجرای فرایند"),
        fdef("_has_record", "رکورد نهایی ثبت شده", "boolean", "اجرای فرایند"),
        fdef("_record_id", "شناسه رکورد نهایی", "integer", "اجرای فرایند"),
        fdef("_documents", "تعداد مستندات", "integer", "اجرای فرایند"),
    ]
    return base + _stage_timing_fields() + form_fields(group_prefix="فرم: ")


def _load_processes(scope):
    from ..models import (FormField, Well, WorkflowAttachment, WorkflowInstance)
    users = _user_names()
    wells = {w.id: w for w in Well.query.all()}
    labels = _lookups()
    per_run, _per_stage = _returns_by_instance()
    docs = defaultdict(int)
    for (iid,) in db.session.query(WorkflowAttachment.instance_id).all():
        docs[iid] += 1
    fields = report_form_fields()
    now = local_now()
    rows = []
    for inst in WorkflowInstance.query.order_by(WorkflowInstance.id).all():
        well = wells.get(inst.well_id)
        center_id = well.center_id if well else None
        if scope is not None and center_id not in scope:
            continue
        stages = {s.stage_number: s for s in inst.workflow.stages} if inst.workflow else {}
        entries = [e for e in inst.entries if e.stage_number != 0]
        applicable = [e for e in entries if e.status != "skipped"]
        done = [e for e in applicable if e.status in ("submitted", "archived", "deferred")]
        end = inst.completed_at or (None if inst.status == "open" else inst.updated_at)
        dur = _hours(inst.created_at, end or now)
        payload = inst.payload or {}
        cur = stages.get(inst.current_stage)
        entry = stages.get(inst.entry_stage)
        row = {
            "_id": inst.id, "_process": inst.workflow.name if inst.workflow else None,
            "_kind": inst.operation_label if hasattr(inst, "operation_label") else inst.operation_kind,
            "_status": INSTANCE_STATUS_FA.get(inst.status, inst.status),
            "_well": well.name if well else inst.well_name_raw,
            "_center": labels.get(center_id),
            "_created_by": users.get(inst.created_by),
            "_created_at": inst.created_at,
            "_created_date": inst.created_at.date() if inst.created_at else None,
            "_completed_at": inst.completed_at,
            "_completed_date": inst.completed_at.date() if inst.completed_at else None,
            "_duration_hours": dur,
            "_duration_days": round(dur / 24.0, 2) if dur is not None else None,
            "_current_stage": (cur.title if cur and inst.status == "open" else
                               ("—" if inst.status != "open" else None)),
            "_entry_stage": entry.title if entry else None,
            "_stages_total": len(applicable), "_stages_done": len(done),
            "_returns": per_run.get(inst.id, 0),
            "_referrals": len([e for e in entries if e.referred_by_id]),
            "_outcome_note": getattr(inst, "outcome_note", None),
            "_has_record": bool(inst.record_id), "_record_id": inst.record_id,
            "_documents": docs.get(inst.id, 0),
            "_center_id": center_id,
        }
        delays = 0
        for e in entries:
            st = stages.get(e.stage_number)
            if st is None:
                continue
            start = e.referred_at or e.started_at or inst.created_at
            finish = e.submitted_at if e.status in ("submitted", "archived", "deferred") else None
            hrs = _hours(start, finish) if finish else None
            row[f"_stage_{st.id}_hours"] = hrs
            sla = getattr(st, "sla_hours", None)
            if sla and ((hrs is not None and hrs > sla) or
                        (finish is None and e.status == "pending"
                         and _hours(start, now) and _hours(start, now) > sla)):
                delays += 1
        row["_delays"] = delays
        for f in fields:
            row[f.field_name] = coerce(form_field_type(f), payload.get(f.field_name))
        rows.append(row)
    return rows


def _step_fields():
    base = [
        fdef("_id", "شناسه مرحله‌ی اجرا", "integer", "مرحله"),
        fdef("_run_id", "شناسه فرایند", "integer", "اجرای فرایند"),
        fdef("_process", "فرایند", "single", "اجرای فرایند"),
        fdef("_kind", "نوع عملیات", "single", "اجرای فرایند", options=["کشیدن", "نصب"]),
        fdef("_run_status", "وضعیت فرایند", "single", "اجرای فرایند",
             options=list(INSTANCE_STATUS_FA.values())),
        fdef("_well", "چاه", "single", "اجرای فرایند"),
        fdef("_center", "مرکز", "center", "اجرای فرایند"),
        fdef("_stage_number", "شماره مرحله", "integer", "مرحله"),
        fdef("_stage", "مرحله", "single", "مرحله"),
        fdef("_status", "وضعیت مرحله", "single", "مرحله", options=list(ENTRY_STATUS_FA.values())),
        fdef("_owners", "متولی مرحله", "multi", "مرحله"),
        fdef("_filled_by", "ثبت‌کننده‌ی مرحله", "user", "مرحله"),
        fdef("_started_at", "زمان رسیدن کار", "datetime", "زمان"),
        fdef("_submitted_at", "زمان ثبت مرحله", "datetime", "زمان"),
        fdef("_started_date", "تاریخ رسیدن کار", "date", "زمان"),
        fdef("_submitted_date", "تاریخ ثبت مرحله", "date", "زمان"),
        fdef("_duration_hours", "مدت انجام (ساعت)", "decimal", "زمان"),
        fdef("_sla_hours", "مهلت مرحله (ساعت)", "decimal", "زمان"),
        fdef("_delay_hours", "تأخیر (ساعت)", "decimal", "زمان"),
        fdef("_delayed", "تأخیردار", "boolean", "زمان"),
        fdef("_returns_from", "برگشت از این مرحله", "integer", "مرحله"),
        fdef("_referred_by", "ارجاع‌دهنده", "user", "مرحله"),
        fdef("_referred_to", "ارجاع به", "multi", "مرحله"),
        fdef("_needs_approval", "نیاز به تأیید", "boolean", "مرحله"),
    ]
    return base + form_fields(group_prefix="فرم مرحله: ")


def _load_steps(scope):
    from ..models import FormField, Well, WorkflowInstance
    users = _user_names()
    wells = {w.id: w for w in Well.query.all()}
    labels = _lookups()
    _per_run, per_stage = _returns_by_instance()
    fields = report_form_fields()
    now = local_now()
    rows = []
    for inst in WorkflowInstance.query.order_by(WorkflowInstance.id).all():
        well = wells.get(inst.well_id)
        center_id = well.center_id if well else None
        if scope is not None and center_id not in scope:
            continue
        stages = {s.stage_number: s for s in inst.workflow.stages} if inst.workflow else {}
        for e in inst.entries:
            if e.stage_number == 0 or e.status == "skipped":
                continue
            st = stages.get(e.stage_number)
            start = e.referred_at or e.started_at or inst.created_at
            finished = e.status in ("submitted", "archived", "deferred")
            finish = e.submitted_at if finished else None
            hrs = _hours(start, finish if finished else (now if inst.status == "open" else None))
            sla = getattr(st, "sla_hours", None) if st else None
            delay = round(max(0.0, hrs - sla), 2) if (sla and hrs is not None) else None
            row = {
                "_id": e.id, "_run_id": inst.id,
                "_process": inst.workflow.name if inst.workflow else None,
                "_kind": inst.operation_label if hasattr(inst, "operation_label") else inst.operation_kind,
                "_run_status": INSTANCE_STATUS_FA.get(inst.status, inst.status),
                "_well": well.name if well else inst.well_name_raw,
                "_center": labels.get(center_id),
                "_stage_number": e.stage_number,
                "_stage": st.title if st else f"مرحله {e.stage_number}",
                "_status": ENTRY_STATUS_FA.get(e.status, e.status),
                "_owners": [u.full_name for u in (st.all_owners if st else [])],
                "_filled_by": users.get(e.user_id),
                "_started_at": start, "_submitted_at": finish,
                "_started_date": start.date() if start else None,
                "_submitted_date": finish.date() if finish else None,
                "_duration_hours": hrs, "_sla_hours": sla, "_delay_hours": delay,
                "_delayed": bool(delay and delay > 0),
                "_returns_from": per_stage.get((inst.id, e.stage_number), 0),
                "_referred_by": users.get(e.referred_by_id),
                "_referred_to": [users.get(i) for i in e.recipient_ids if users.get(i)]
                if hasattr(e, "recipient_ids") else [],
                "_needs_approval": bool(st.needs_approval) if st else False,
                "_center_id": center_id,
            }
            payload = e.payload or {}
            for f in fields:
                row[f.field_name] = coerce(form_field_type(f), payload.get(f.field_name))
            rows.append(row)
    return rows


# users, centres, wells ──────────────────────────────────────────────────────

def _user_fields():
    return [
        fdef("_id", "شناسه کاربر", "integer", "کاربر"),
        fdef("_name", "نام", "user", "کاربر"),
        fdef("_username", "نام کاربری", "text", "کاربر"),
        fdef("_role", "نقش", "single", "کاربر"),
        fdef("_unit", "واحد", "text", "کاربر"),
        fdef("_centers", "مراکز", "multi", "کاربر"),
        fdef("_groups", "گروه‌ها", "multi", "کاربر"),
        fdef("_active", "فعال", "boolean", "کاربر"),
        fdef("_last_login", "آخرین ورود", "datetime", "فعالیت"),
        fdef("_login_count", "تعداد ورود", "integer", "فعالیت"),
        fdef("_records_created", "رکوردهای ثبت‌شده", "integer", "فعالیت"),
        fdef("_stages_submitted", "مراحل ثبت‌شده", "integer", "فعالیت"),
        fdef("_avg_stage_hours", "میانگین مدت انجام مرحله (ساعت)", "decimal", "فعالیت"),
    ]


def _load_users(scope):
    from ..models import AppUser, Record, UserGroup, WorkflowStageEntry
    from sqlalchemy import func
    recs = dict(db.session.query(Record.created_by, func.count(Record.id))
                .filter(Record.is_active.is_(True)).group_by(Record.created_by).all())
    stage_counts, stage_hours = defaultdict(int), defaultdict(list)
    for e in WorkflowStageEntry.query.filter(WorkflowStageEntry.user_id.isnot(None),
                                             WorkflowStageEntry.stage_number != 0).all():
        if e.status not in ("submitted", "archived", "deferred"):
            continue
        stage_counts[e.user_id] += 1
        start = e.referred_at or e.started_at or (e.instance.created_at if e.instance else None)
        hrs = _hours(start, e.submitted_at)
        if hrs is not None:
            stage_hours[e.user_id].append(hrs)
    groups = defaultdict(list)
    for g in UserGroup.query.all():
        for m in g.members:
            groups[m.id].append(g.name)
    rows = []
    for u in AppUser.query.order_by(AppUser.id).all():
        centers = [c.id for c in u.centers]
        if scope is not None and centers and not (set(centers) & set(scope)):
            continue
        hours = stage_hours.get(u.id) or []
        rows.append({
            "_id": u.id, "_name": u.full_name, "_username": u.username,
            "_role": u.role_label, "_unit": u.unit, "_centers": [c.label for c in u.centers],
            "_groups": groups.get(u.id, []), "_active": bool(u.is_active),
            "_last_login": u.last_login_at, "_login_count": u.login_count or 0,
            "_records_created": recs.get(u.id, 0), "_stages_submitted": stage_counts.get(u.id, 0),
            "_avg_stage_hours": round(sum(hours) / len(hours), 2) if hours else None,
            "_center_id": centers[0] if centers else None,
        })
    return rows


def _center_fields():
    return [
        fdef("_id", "شناسه مرکز", "integer", "مرکز"),
        fdef("_name", "مرکز", "center", "مرکز"),
        fdef("_wells", "تعداد چاه", "integer", "مرکز"),
        fdef("_records", "تعداد عملیات ثبت‌شده", "integer", "مرکز"),
        fdef("_records_this_year", "عملیات امسال", "integer", "مرکز"),
        fdef("_open_processes", "فرایندهای در جریان", "integer", "مرکز"),
        fdef("_completed_processes", "فرایندهای تکمیل‌شده", "integer", "مرکز"),
        fdef("_users", "کاربران مرکز", "integer", "مرکز"),
    ]


def _load_centers(scope):
    from ..models import (AppUser, LookupCategory, Record, Well, WorkflowInstance)
    from sqlalchemy import func
    from ..services.jalali import today_jalali
    cat = LookupCategory.query.filter_by(code="center").first()
    if cat is None:
        return []
    jy = today_jalali()[0]
    wells = dict(db.session.query(Well.center_id, func.count(Well.id))
                 .filter(Well.is_active.is_(True)).group_by(Well.center_id).all())
    recs = dict(db.session.query(Record.center_id, func.count(Record.id))
                .filter(Record.is_active.is_(True)).group_by(Record.center_id).all())
    recs_y = dict(db.session.query(Record.center_id, func.count(Record.id))
                  .filter(Record.is_active.is_(True), Record.j_year == jy)
                  .group_by(Record.center_id).all())
    well_center = {w.id: w.center_id for w in Well.query.all()}
    open_p, done_p = defaultdict(int), defaultdict(int)
    for inst in WorkflowInstance.query.all():
        c = well_center.get(inst.well_id)
        if inst.status == "open":
            open_p[c] += 1
        elif inst.status == "completed":
            done_p[c] += 1
    users = defaultdict(int)
    for u in AppUser.query.all():
        for c in u.centers:
            users[c.id] += 1
    rows = []
    for item in sorted(cat.items, key=lambda i: i.sort_order):
        if scope is not None and item.id not in scope:
            continue
        rows.append({"_id": item.id, "_name": item.label or item.value,
                     "_wells": wells.get(item.id, 0), "_records": recs.get(item.id, 0),
                     "_records_this_year": recs_y.get(item.id, 0),
                     "_open_processes": open_p.get(item.id, 0),
                     "_completed_processes": done_p.get(item.id, 0),
                     "_users": users.get(item.id, 0), "_center_id": item.id})
    return rows


def _well_fields():
    return [
        fdef("_id", "شناسه چاه", "integer", "چاه"),
        fdef("_name", "چاه", "single", "چاه"),
        fdef("_code", "کد چاه", "text", "چاه"),
        fdef("_center", "مرکز", "center", "چاه"),
        fdef("_depth", "عمق", "decimal", "چاه"),
        fdef("_class", "کلاس", "single", "چاه"),
        fdef("_pm_code", "کد PM", "text", "چاه"),
        fdef("_active", "فعال", "boolean", "چاه"),
        fdef("_records", "تعداد عملیات", "integer", "سوابق"),
        fdef("_failures", "تعداد خرابی ثبت‌شده", "integer", "سوابق"),
        fdef("_last_operation", "تاریخ آخرین عملیات", "date", "سوابق"),
        fdef("_open_processes", "فرایندهای در جریان", "integer", "سوابق"),
    ]


def _load_wells(scope):
    from ..models import Record, RecordTag, Well, WorkflowInstance
    from sqlalchemy import func
    labels = _lookups()
    recs = {}
    for wid, cnt, last in (db.session.query(Record.well_id, func.count(Record.id),
                                            func.max(Record.op_date))
                           .filter(Record.is_active.is_(True)).group_by(Record.well_id).all()):
        recs[wid] = (cnt, last)
    failures = dict(db.session.query(Record.well_id, func.count(func.distinct(Record.id)))
                    .join(RecordTag, RecordTag.record_id == Record.id)
                    .filter(RecordTag.category_code == "failure_reason",
                            Record.is_active.is_(True))
                    .group_by(Record.well_id).all())
    open_p = dict(db.session.query(WorkflowInstance.well_id, func.count(WorkflowInstance.id))
                  .filter(WorkflowInstance.status == "open")
                  .group_by(WorkflowInstance.well_id).all())
    rows = []
    for w in Well.query.order_by(Well.name).all():
        if scope is not None and w.center_id not in scope:
            continue
        cnt, last = recs.get(w.id, (0, None))
        last_date = last if isinstance(last, _dt.date) else _date(last)
        rows.append({"_id": w.id, "_name": w.name, "_code": w.code,
                     "_center": labels.get(w.center_id), "_depth": w.depth,
                     "_class": w.well_class, "_pm_code": w.pm_code,
                     "_active": bool(w.is_active), "_records": cnt,
                     "_failures": failures.get(w.id, 0), "_last_operation": last_date,
                     "_open_processes": open_p.get(w.id, 0), "_center_id": w.center_id})
    return rows


# combined: a process run with its final record and its well ─────────────────
def _combined_fields():
    proc = [f for f in _process_fields() if f["group"] and not f["group"].startswith("فرم: ")]
    rec = [dict(f, key="rec." + f["key"], label="رکورد: " + f["label"],
                group="رکورد نهایی — " + f["group"]) for f in _record_fields()]
    return proc + rec


def _load_combined(scope):
    runs = SOURCES["process"].rows(scope)
    recs = {r["_id"]: r for r in SOURCES["records"].rows(scope)}
    out = []
    for run in runs:
        row = {k: v for k, v in run.items()}
        rec = recs.get(run.get("_record_id"))
        if rec:
            for k, v in rec.items():
                if not k.startswith("_center_id"):
                    row["rec." + k] = v
        out.append(row)
    return out


SOURCES = {
    "records": Source("records", "پاسخ فرم‌ها (رکوردهای عملیات)",
                      "هر ردیف یک عملیات ثبت‌شده؛ همه‌ی فیلدهای فرم‌ساز، چاه، زمان و ثبت‌کننده.",
                      "record.view", "رکورد", _record_fields, _load_records),
    "process": Source("process", "اجرای فرایندها",
                      "هر ردیف یک اجرای فرایند؛ وضعیت، زمان‌ها، مدت، برگشت‌ها، تأخیرها و داده‌ی فرم‌های آن اجرا.",
                      ("workflow.view", "workflow.manage"), "فرایند", _process_fields, _load_processes),
    "steps": Source("steps", "مراحل فرایندها",
                    "هر ردیف یک مرحله در یک اجرا؛ متولی، ثبت‌کننده، زمان رسیدن و ثبت، مدت، مهلت و تأخیر، ارجاع و برگشت.",
                    ("workflow.view", "workflow.manage"), "مرحله", _step_fields, _load_steps),
    "process_record": Source("process_record", "ترکیبی: فرایند + رکورد نهایی",
                             "هر اجرای فرایند همراه با فیلدهای رکورد نهایی آن و چاه.",
                             ("workflow.view", "workflow.manage"), "فرایند",
                             _combined_fields, _load_combined),
    "users": Source("users", "کاربران", "هر ردیف یک کاربر؛ نقش، مراکز، گروه‌ها و فعالیت.",
                    "user.manage", "کاربر", _user_fields, _load_users),
    "centers": Source("centers", "مراکز (واحدها)", "هر ردیف یک مرکز؛ چاه‌ها، عملیات و فرایندها.",
                      "well.view", "مرکز", _center_fields, _load_centers),
    "wells": Source("wells", "چاه‌ها", "هر ردیف یک چاه؛ مشخصات و سوابق.",
                    "well.view", "چاه", _well_fields, _load_wells),
}


def get_source(key: str) -> Source | None:
    return SOURCES.get(key)
