"""Create / update / serialise workshop records, with validation."""
from __future__ import annotations

import datetime as dt
import logging
import re

from sqlalchemy import or_

from ..extensions import db
from ..models import (FormField, FormSection, LookupItem, Record,
                      RecordDynamicValue,
                      RecordTag, Well, WellAlias)
from .audit import diff_fields, record_audit
from .jalali import (MONTHS_FA, jalali_parts_to_date, local_now,
                     normalize_digits, parse_jalali, parse_jalali_to_date,
                     tehran_time_str, to_jalali_str)
from .lookups import (fold_persian, normalize_text, resolve_id,
                      resolve_item, well_key)

log = logging.getLogger(__name__)


class ValidationError(Exception):
    """Carries a dict of {field: Persian message} back to the caller."""

    def __init__(self, errors: dict):
        super().__init__("خطای اعتبارسنجی")
        self.errors = errors


# ── coercion helpers ─────────────────────────────────────────────────────────
def to_float(value, field=None, errors=None, minimum=None, maximum=None):
    if value in (None, "", []):
        return None
    try:
        num = float(normalize_digits(str(value)).replace(",", "").strip())
    except (TypeError, ValueError):
        if errors is not None and field:
            errors[field] = "مقدار باید عددی باشد."
        return None
    if minimum is not None and num < minimum:
        if errors is not None and field:
            errors[field] = f"مقدار نباید کمتر از {minimum} باشد."
        return None
    if maximum is not None and num > maximum:
        if errors is not None and field:
            errors[field] = f"مقدار نباید بیشتر از {maximum} باشد."
        return None
    return num


def to_int(value, field=None, errors=None, minimum=None, maximum=None):
    num = to_float(value, field, errors, minimum, maximum)
    return None if num is None else int(round(num))


def to_bool(value):
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "on", "yes", "بله", "دارد", "√"}


_PUMP_SPLIT = re.compile(r"^\s*([^/\\\s]+)\s*[/\\]\s*(\d{1,2})\s*$")


def split_pump_type(raw):
    """'384/10' → ('384', 10). Anything else comes back untouched."""
    text = normalize_digits(normalize_text(raw))
    if not text:
        return None, None
    m = _PUMP_SPLIT.match(text)
    if m:
        return m.group(1), int(m.group(2))
    return text, None


# ── wells ────────────────────────────────────────────────────────────────────
def resolve_well(name_or_id, create_missing=False):
    """Accept a well id, an exact name, or an alias. Returns (well, raw_name)."""
    if name_or_id in (None, "", []):
        return None, None
    if isinstance(name_or_id, int):
        well = db.session.get(Well, name_or_id)
        if well:
            return well, well.name
    raw = normalize_text(name_or_id)
    if not raw:
        return None, None
    well = Well.query.filter_by(name=raw).one_or_none()
    if well:
        return well, raw
    alias = WellAlias.query.filter_by(alias=raw).one_or_none()
    if alias:
        return alias.well, raw
    folded = fold_persian(raw)
    candidates = Well.query.all()
    for candidate in candidates:
        if fold_persian(candidate.name) == folded:
            return candidate, raw
    # Last resort before inventing a well: the looser key, which also reads a
    # spelled-out index as its digit. A sheet that writes «گلشهر یک» means the
    # register's «گلشهر 1», and creating a second row for it is how the picker
    # filled up with duplicates in the first place. Prefer a registered well
    # when the key matches more than one.
    loose = well_key(raw)
    if loose:
        matches = [w for w in candidates if well_key(w.name) == loose]
        if matches:
            matches.sort(key=lambda w: (bool(w.pm_code), w.is_active, w.is_verified),
                         reverse=True)
            return matches[0], raw
    if create_missing:
        well = Well(name=raw, is_active=True, is_verified=False,
                    notes="هنگام ورود داده ایجاد شد؛ نیازمند تأیید مدیر.")
        db.session.add(well)
        db.session.flush()
        log.info("Unverified well created: %s", raw)
        return well, raw
    return None, raw


# ── write path ───────────────────────────────────────────────────────────────
def _apply_date(record, payload, errors):
    """Accept either Jalali y/m/d parts or a 'YYYY/MM/DD' Jalali string."""
    jy = payload.get("j_year")
    jm = payload.get("j_month")
    jd = payload.get("j_day")
    text = payload.get("op_jdate") or payload.get("op_date")

    if (jy in (None, "")) and text:
        parts = parse_jalali(text)
        if parts:
            jy, jm, jd = parts
        else:
            errors["op_jdate"] = "قالب تاریخ نامعتبر است (نمونه: ۱۴۰۵/۰۶/۲۲)."
            return

    jy = to_int(jy, "j_year", errors, 1300, 1500)
    jm = to_int(jm, "j_month", errors, 1, 12)
    jd = to_int(jd, "j_day", errors, 1, 31)

    if jy is None and jm is None and jd is None:
        errors.setdefault("op_jdate", "تاریخ عملیات الزامی است.")
        return
    if jm is None:
        errors.setdefault("j_month", "ماه الزامی است.")
    if jd is None:
        errors.setdefault("j_day", "روز الزامی است.")
    if errors:
        return

    record.j_year, record.j_month, record.j_day = jy, jm, jd
    record.op_date = jalali_parts_to_date(jy, jm, jd)
    if record.op_date is None:
        errors["op_jdate"] = "تاریخ شمسی نامعتبر است."
    else:
        from .jalali import today_jalali
        if jy > today_jalali()[0] + 1:
            # Kept, not rejected — the source spreadsheet really does contain a
            # few mistyped years, and dropping those rows would lose real work.
            errors.setdefault("__warn_year__",
                              f"سال {jy} از سال جاری جلوتر است؛ لطفاً بررسی شود.")


def _apply_choice_fields(record, payload, create_missing):
    """Fill each *_id column from the payload.

    The two spellings are kept strictly apart: ``center_id`` is a lookup row
    id, ``center`` is the option's *value*. They must never be conflated,
    because plenty of real option values are themselves numeric — pump type
    "384", motor rating "73" — and treating those as row ids silently points
    the record at an unrelated option.
    """
    for attr, category in Record.CHOICE_FIELDS.items():
        key = attr[:-3]                      # center_id -> center
        if attr in payload:
            raw_id = payload.get(attr)
            if raw_id in (None, "", []):
                setattr(record, attr, None)
            else:
                try:
                    item = db.session.get(LookupItem, int(raw_id))
                except (TypeError, ValueError):
                    item = None
                setattr(record, attr, item.id if item else None)
            continue
        if key not in payload:
            continue
        raw = payload.get(key)
        if raw in (None, "", []):
            setattr(record, attr, None)
            continue
        setattr(record, attr, resolve_id(category, raw, create_missing=True))


def _apply_tags(record, payload, create_missing):
    for key, category in Record.MULTI_FIELDS.items():
        if key not in payload:
            continue
        values = payload.get(key) or []
        if isinstance(values, str):
            values = [v.strip() for v in values.split(",") if v.strip()]
        record.tags = [t for t in record.tags if t.category_code != category]
        seen = set()
        for value in values:
            text = normalize_text(value)
            if not text or text in seen:
                continue
            seen.add(text)
            item = resolve_item(category, text, create_missing=True)
            record.tags.append(RecordTag(category_code=category,
                                         item_id=item.id if item else None,
                                         value=item.value if item else text))


def _apply_dynamic(record, payload, errors):
    """Store answers to fields that have no column of their own.

    The entry form nests them under ``dynamic``; the workflow hands the merged
    payload over flat, keyed by field name like everything else. Both are
    accepted, so neither caller has to know which fields happen to be backed by
    a column.
    """
    fields = {f.field_name: f for f in
              FormField.query.filter(FormField.model_attr.is_(None)).all()}
    dyn = dict(payload.get("dynamic") or {})
    for name in fields:
        if name not in dyn and name in payload and name not in Record.MULTI_FIELDS:
            dyn[name] = payload[name]
    if not dyn:
        return
    existing = {v.field_id: v for v in record.dynamic_values}
    for name, raw in dyn.items():
        field = fields.get(name)
        if field is None:
            continue
        holder = existing.get(field.id) or RecordDynamicValue(field_id=field.id)
        holder.value_text = holder.value_num = holder.value_date = None
        if raw in (None, "", []):
            pass
        elif field.field_type == "number":
            holder.value_num = to_float(raw, name, errors, field.min_value,
                                        field.max_value)
        elif field.field_type == "jalali_date":
            holder.value_date = parse_jalali_to_date(raw)
            if holder.value_date is None:
                errors[name] = "قالب تاریخ نامعتبر است."
        elif field.field_type == "date":
            try:
                holder.value_date = dt.date.fromisoformat(str(raw))
            except ValueError:
                errors[name] = "قالب تاریخ نامعتبر است."
        elif field.field_type in ("checkbox", "multiselect", "checklist"):
            holder.value_text = ", ".join(raw) if isinstance(raw, list) else str(raw)
        else:
            holder.value_text = str(raw)
        if field.is_required and holder.value in (None, ""):
            errors[name] = f"«{field.label}» الزامی است."
        if holder.id is None and holder.field_id not in existing:
            record.dynamic_values.append(holder)


def _demote_coercion_errors(errors, warnings):
    """In lenient (import) mode a bad cell empties that column and warns.

    The workshop sheets contain «نامعلوم» in a depth column and stray marks in
    numeric ones. Rejecting the whole row over one such cell would throw away
    forty good values, so the cell is left NULL and reported as a warning.
    """
    for key in list(errors):
        if errors[key].startswith("مقدار"):
            warnings[key] = errors.pop(key)


_MISSING = object()


def _stored_value_of(record, field_name):
    """What ``record`` currently holds for ``field_name``, as a plain value."""
    if record is None:
        return None
    field = FormField.query.filter_by(field_name=field_name).first()
    if field is None:
        return None
    if field.model_attr:
        value = getattr(record, field.model_attr, None)
        return _label(value) if field.model_attr.endswith("_id") else value
    if field_name in Record.MULTI_FIELDS:
        return record.tag_values(Record.MULTI_FIELDS[field_name])
    holder = next((v for v in record.dynamic_values
                   if v.field and v.field.field_name == field_name), None)
    return holder.value if holder is not None else None


def _hidden_by_condition(payload, record=None, unanswered_hides=False) -> set:
    """Field names whose "visible_when" condition is not met.

    Enforced on the server as well as in the browser: a contractor sent along
    with مجری=امانی is dropped rather than stored, and a hidden field is never
    treated as a missing required answer.

    When the payload does not mention the field the rule keys on, the record's
    own stored value decides. Without that, editing one unrelated field would
    silently clear every conditional field on the record, because a partial
    update carries no مجری and the rule would read it as "not پیمانی".
    """
    def unmet(raw) -> bool | None:
        """Several rules: shown when any one of them is met.

        True only when every rule that can be judged is unmet; None when
        none of them can be judged.
        """
        from .conditions import SEP
        verdicts = [unmet_one(part) for part in str(raw or "").split(SEP)
                    if "=" in part]
        judged = [v for v in verdicts if v is not None]
        if not judged:
            return None
        return all(judged)

    def unmet_one(rule) -> bool | None:
        """True when the rule is not satisfied, None when it cannot be judged.

        A multi-valued source — «علت خرابی» is a multi-select — satisfies the
        rule when it *contains* the value: ticking سوختن الکتروپمپ and هوادهی
        together must open both of their forms, not neither.
        """
        rule = (rule or "").strip()
        if "=" not in rule:
            return None
        on, _, expected = rule.partition("=")
        on, expected = on.strip(), expected.strip()
        sent = payload.get(on, _MISSING)
        if sent is _MISSING:
            if record is None:
                # Nothing to judge by. Editing a record, that means "leave the
                # field alone"; asking whether a stage is complete, a question
                # nobody has answered yet opened nothing — «علت خرابی» not yet
                # ticked means none of the cause forms is owed.
                return True if unanswered_hides else None
            sent = _stored_value_of(record, on)
        values = sent if isinstance(sent, list) else [sent]
        if not isinstance(sent, list) and isinstance(sent, str) and "،" in sent:
            values = sent.split("،")
        # «a|b|c» — several values open the same thing: «سوختن الکتروپمپ» and
        # «سوختن الکتروموتور» can both open the burn form. An empty list is a
        # form linked to no cause yet, which opens for nothing.
        wanted = {normalize_text(x) for x in expected.split("|") if x.strip()}
        return not any(normalize_text(v) in wanted for v in values)

    hidden = set()
    # A section can carry the rule for all of its fields at once, which is how
    # one علت خرابی brings its whole block of readings with it.
    for section in FormSection.query.filter(FormSection.visible_when.isnot(None),
                                            FormSection.is_active.is_(True)).all():
        if unmet(section.visible_when):
            hidden.update(f.field_name for f in section.fields if f.is_active)
    for field in FormField.query.filter(FormField.visible_when.isnot(None),
                                        FormField.is_active.is_(True)).all():
        if unmet(field.visible_when):
            hidden.add(field.field_name)
    return hidden


def _check_required(record, payload, errors, hidden=frozenset()):
    """Required-ness comes from the form definition, so the admin controls it."""
    for field in FormField.query.filter_by(is_required=True, is_active=True).all():
        if field.field_name in hidden:
            continue
        if field.field_name in ("op_jdate",):
            continue
        if field.model_attr and hasattr(record, field.model_attr):
            if getattr(record, field.model_attr) in (None, "", []):
                errors.setdefault(field.field_name, f"«{field.label}» الزامی است.")
        elif field.lookup_category and not field.model_attr:
            if not record.tag_values(field.lookup_category):
                errors.setdefault(field.field_name, f"«{field.label}» الزامی است.")


def apply_payload(record: Record, payload: dict, create_missing=False,
                  partial=False) -> Record:
    """Map a submitted payload onto a Record.

    ``partial=True`` is the import/patch mode: a missing date or a
    non-numeric cell is tolerated (and reported as a warning on
    ``record.import_warnings``) instead of rejecting the row.
    """
    errors: dict = {}
    warnings: dict = {}

    date_keys = ("op_jdate", "op_date", "j_year", "j_month", "j_day")
    # Re-parse the date only when the caller sent one, or when the record has
    # none yet — a PATCH of a single field must not demand the whole date back.
    if any(k in payload for k in date_keys) or record.op_date is None:
        _apply_date(record, payload, errors)
        if "__warn_year__" in errors:
            warnings["j_year"] = errors.pop("__warn_year__")
        if partial:
            # Historical sheets legitimately lack a day, or a date entirely.
            for key in ("op_jdate", "j_month", "j_day", "j_year"):
                if key in errors:
                    warnings[key] = errors.pop(key)

    if "well" in payload or "well_id" in payload or "well_name" in payload:
        if payload.get("well_id") not in (None, "", []):
            try:
                candidate = int(payload["well_id"])
            except (TypeError, ValueError):
                candidate = payload["well_id"]
        else:
            candidate = payload.get("well") or payload.get("well_name")
        well, raw = resolve_well(candidate, create_missing=True)
        record.well_id = well.id if well else None
        record.well_name_raw = raw
        if well is None:
            errors["well"] = "نام چاه الزامی است."

    _apply_choice_fields(record, payload, create_missing)

    # The 1398-1403 sheets store the *current* pump the same combined way.
    if "pump_curr" in payload and record.pump_curr_id:
        type_part, stages = split_pump_type(payload.get("pump_curr"))
        if stages is not None:
            record.pump_curr_id = resolve_id("pump_type", type_part, create_missing=True)
            if not payload.get("pump_stages"):
                record.pump_stages = stages

    # pump previous type may arrive combined as "384/10"
    if "pump_prev" in payload or "pump_prev_raw" in payload:
        raw = payload.get("pump_prev_raw", payload.get("pump_prev"))
        record.pump_prev_raw = normalize_text(raw) or None
        type_part, stages = split_pump_type(raw)
        if type_part:
            record.pump_prev_id = resolve_id("pump_type", type_part, create_missing=True)
        else:
            record.pump_prev_id = None
        if stages is not None and not payload.get("pump_prev_stages"):
            record.pump_prev_stages = stages

    for name in Record.NUMERIC_FIELDS:
        if name in payload:
            setattr(record, name, to_float(payload[name], name, errors))
    for name in Record.INT_FIELDS:
        if name in payload and name not in ("j_year", "j_month", "j_day"):
            setattr(record, name, to_int(payload[name], name, errors))
    for name in Record.TEXT_FIELDS:
        if name in payload:
            value = payload[name]
            setattr(record, name, normalize_text(value) or None
                    if isinstance(value, str) else value)
    if "reported_to_finance" in payload:
        record.reported_to_finance = to_bool(payload["reported_to_finance"])

    for name, raw_key in (("prev_install_date", "prev_install_date"),
                          ("test_date", "test_date")):
        if raw_key in payload:
            raw = payload[raw_key]
            setattr(record, name, parse_jalali_to_date(raw))
            setattr(record, f"{name}_raw",
                    normalize_text(raw) or None if raw not in (None, "") else None)

    hidden = _hidden_by_condition(payload, record)
    for name in hidden:
        field = FormField.query.filter_by(field_name=name).first()
        if field and field.model_attr and hasattr(record, field.model_attr):
            setattr(record, field.model_attr, None)

    _apply_tags(record, payload, create_missing)
    _apply_dynamic(record, payload, errors)
    if partial:
        _demote_coercion_errors(errors, warnings)
    else:
        _check_required(record, payload, errors, hidden)

    record.import_warnings = warnings
    if errors:
        raise ValidationError(errors)
    return record


def _actor_id():
    """Id of the signed-in user, or None when running from the CLI/importer."""
    try:
        from flask import g, has_request_context
        if has_request_context():
            user = getattr(g, "current_user", None)
            return user.id if user else None
    except Exception:
        pass
    return None


def create_record(payload: dict, create_missing=False) -> Record:
    record = Record()
    apply_payload(record, payload, create_missing=create_missing)
    record.created_by = _actor_id()
    record.updated_by = record.created_by
    db.session.add(record)
    db.session.flush()
    record_audit("create", "record", record.id,
                 summary=f"ثبت رکورد برای چاه «{record.well_name_raw or '-'}»")
    db.session.commit()
    return record


def update_record(record: Record, payload: dict) -> Record:
    before = serialize_record(record)
    apply_payload(record, payload)
    record.updated_by = _actor_id()
    db.session.flush()
    after = serialize_record(record)
    record_audit("update", "record", record.id,
                 summary=f"ویرایش رکورد #{record.id}",
                 details=diff_fields(before, after))
    db.session.commit()
    return record


def deactivate_record(record: Record, hard: bool = False) -> None:
    """Soft delete by default — history stays intact (requirement 15/26)."""
    if hard:
        record_audit("delete", "record", record.id,
                     summary=f"حذف قطعی رکورد #{record.id}",
                     details=serialize_record(record))
        db.session.delete(record)
    else:
        record.is_active = False
        record_audit("delete", "record", record.id,
                     summary=f"غیرفعال‌سازی رکورد #{record.id}")
    db.session.commit()


# ── read path ────────────────────────────────────────────────────────────────
def _label(item_id):
    if not item_id:
        return None
    item = db.session.get(LookupItem, item_id)
    return item.value if item else None


def serialize_record(record: Record, verbose: bool = True) -> dict:
    data = {"id": record.id, "is_active": record.is_active}
    for attr in Record.CHOICE_FIELDS:
        data[attr] = getattr(record, attr)
        if verbose:
            data[attr[:-3]] = _label(getattr(record, attr))
    for name in (Record.NUMERIC_FIELDS + Record.INT_FIELDS + Record.TEXT_FIELDS):
        data[name] = getattr(record, name)
    for name in Record.DATE_FIELDS:
        value = getattr(record, name)
        data[name] = value.isoformat() if value else None
        if verbose:
            data[name + "_j"] = to_jalali_str(value)
    data["reported_to_finance"] = bool(record.reported_to_finance)
    data["well_id"] = record.well_id
    data["well"] = record.well.name if record.well else record.well_name_raw
    # Carried on every record so exports and reports can show them without a
    # second lookup; they belong to the well, not to the operation.
    data["well_pm_code"] = record.well.pm_code if record.well else None
    data["well_class"] = record.well.well_class if record.well else None
    data["pump_prev"] = record.pump_prev_raw or _label(record.pump_prev_id)
    for key, category in Record.MULTI_FIELDS.items():
        data[key] = record.tag_values(category)
    if verbose:
        data["month_name"] = MONTHS_FA[record.j_month] if record.j_month else ""
        data["date_display"] = (f"{record.j_year or ''}/{record.j_month or 0:02d}/"
                                f"{record.j_day or 0:02d}" if record.j_year else "")
        data["dynamic"] = {v.field.field_name: v.value for v in record.dynamic_values
                           if v.field}
        data["created_at"] = record.created_at.isoformat() if record.created_at else None
        data["updated_at"] = record.updated_at.isoformat() if record.updated_at else None
        data.update(_edit_window(record))
    return data


def _edit_window(record) -> dict:
    """How long the signed-in user still has to change this record.

    The table hides its edit and delete buttons on this, and the form shows the
    deadline; the API refuses the write regardless, so this is a courtesy, not
    the guard.
    """
    from .auth import current_user
    from flask import has_request_context

    if not has_request_context():
        return {"can_edit": True, "edit_deadline_j": None, "edit_deadline_time": None}
    user = current_user()
    if user is None or not user.has_edit_window:
        return {"can_edit": user is not None and user.can("record.edit"),
                "edit_deadline_j": None, "edit_deadline_time": None}
    deadline = user.edit_deadline(record.created_at)
    open_now = deadline is None or local_now() <= deadline
    return {
        "can_edit": bool(user.can("record.edit") and open_now),
        "edit_deadline_j": to_jalali_str(deadline) if deadline else None,
        "edit_deadline_time": (tehran_time_str(deadline, with_seconds=False)
                               if deadline else None),
    }


def search_query(params: dict):
    """Build the filtered/sorted Record query used by the table and exports."""
    query = Record.query
    if not str(params.get("include_inactive", "")).lower() in ("1", "true"):
        query = query.filter(Record.is_active.is_(True))

    def _lookup_filter(param, attr, category):
        value = params.get(param)
        if not value:
            return None
        item_id = value if str(value).isdigit() else resolve_id(category, value)
        return getattr(Record, attr) == int(item_id) if item_id else None

    for param, attr, cat in (
        ("center", "center_id", "center"), ("operation", "operation_id", "operation"),
        ("contractor", "contractor_id", "contractor"),
        ("shift", "shift_id", "shift"), ("starter", "starter_id", "starter"),
        ("pump_type", "pump_curr_id", "pump_type"),
        ("motor_type", "motor_curr_id", "motor_type"),
        ("pump_condition", "pump_condition_id", "condition"),
        ("motor_condition", "motor_condition_id", "condition"),
        ("executor", "executor_id", "executor"),
    ):
        clause = _lookup_filter(param, attr, cat)
        if clause is not None:
            query = query.filter(clause)

    if params.get("month"):
        query = query.filter(Record.j_month == int(params["month"]))
    if params.get("year"):
        query = query.filter(Record.j_year == int(params["year"]))
    if params.get("well"):
        value = params["well"]
        if str(value).isdigit():
            query = query.filter(Record.well_id == int(value))
        else:
            query = query.join(Well, isouter=True).filter(
                or_(Well.name.ilike(f"%{value}%"),
                    Record.well_name_raw.ilike(f"%{value}%")))
    if params.get("failure"):
        query = query.filter(Record.tags.any(
            db.and_(RecordTag.category_code == "failure_reason",
                    RecordTag.value == params["failure"])))
    if params.get("opinion"):
        query = query.filter(Record.tags.any(
            db.and_(RecordTag.category_code == "workshop_opinion",
                    RecordTag.value == params["opinion"])))

    date_from = parse_jalali_to_date(params.get("date_from"))
    date_to = parse_jalali_to_date(params.get("date_to"))
    if date_from:
        query = query.filter(Record.op_date >= date_from)
    if date_to:
        query = query.filter(Record.op_date <= date_to)

    search = (params.get("q") or params.get("search") or "").strip()
    if search:
        like = f"%{search}%"
        matching_items = [i.id for i in LookupItem.query.filter(
            or_(LookupItem.value.ilike(like), LookupItem.label.ilike(like))).all()]
        clauses = [
            Record.well_name_raw.ilike(like), Record.description.ilike(like),
            Record.workshop_note.ilike(like), Record.motor_plaque.ilike(like),
            Record.pump_plaque.ilike(like), Record.pump_prev_raw.ilike(like),
            Record.cable_well.ilike(like), Record.failure_other.ilike(like),
            Record.install_supervisor.ilike(like),
            Record.well.has(Well.name.ilike(like)),
            Record.tags.any(RecordTag.value.ilike(like)),
        ]
        if matching_items:
            clauses += [getattr(Record, attr).in_(matching_items)
                        for attr in Record.CHOICE_FIELDS]
        query = query.filter(or_(*clauses))

    sort = params.get("sort") or "op_date"
    direction = (params.get("dir") or "desc").lower()
    column = getattr(Record, sort, None) if sort in {
        c.name for c in Record.__table__.columns} else None
    if column is None:
        column = Record.op_date
    query = query.order_by(column.desc().nullslast() if direction == "desc"
                           else column.asc().nullsfirst(), Record.id.desc())
    return query
