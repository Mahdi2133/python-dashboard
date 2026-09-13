"""/api/form-builder — the real form designer (requirements 13 & 14)."""
from flask import Blueprint, request

from ..extensions import db
from ..models import FormField, FormFieldOption, FormSection, RecordDynamicValue
from ..models.formbuilder import FIELD_TYPES
from ..services.audit import record_audit
from ..services.jalali import MONTHS_FA
from ..services.lookups import items_by_category, normalize_text
from ._helpers import body, fail, ok

bp = Blueprint("api_formbuilder", __name__, url_prefix="/api/form-builder")


def _month_options():
    return [{"value": str(i), "label": MONTHS_FA[i], "is_active": True,
             "sort_order": i} for i in range(1, 13)]


@bp.get("")
def get_schema():
    """Everything the data-entry page needs to render itself, in one call."""
    active_only = request.args.get("all") not in ("1", "true")
    query = FormSection.query.order_by(FormSection.sort_order)
    if active_only:
        query = query.filter(FormSection.is_active.is_(True))
    sections = [s.to_dict(include_fields=True, active_only=active_only)
                for s in query.all()]
    lookups = items_by_category(active_only=active_only)
    lookups["__months__"] = _month_options()
    return ok({"sections": sections, "lookups": lookups,
               "field_types": list(FIELD_TYPES)})


@bp.post("/sections")
def create_section():
    payload = body()
    code = normalize_text(payload.get("code"))
    title = normalize_text(payload.get("title"))
    if not code or not title:
        return fail("کد و عنوان بخش الزامی است.", 422)
    if FormSection.query.filter_by(code=code).first():
        return fail("بخشی با این کد وجود دارد.", 409)
    section = FormSection(
        code=code, title=title, icon=payload.get("icon"),
        columns=int(payload.get("columns") or 3),
        full_width=bool(payload.get("full_width")),
        sort_order=int(payload.get("sort_order")
                       or (db.session.query(db.func.max(FormSection.sort_order))
                           .scalar() or 0) + 1),
        description=payload.get("description"),
    )
    db.session.add(section)
    db.session.flush()
    record_audit("create", "form_section", section.id, summary=f"افزودن بخش «{title}»")
    db.session.commit()
    return ok(section.to_dict(), message="بخش افزوده شد.")


@bp.put("/sections/<int:section_id>")
def update_section(section_id):
    section = db.session.get(FormSection, section_id)
    if section is None:
        return fail("بخش یافت نشد.", 404)
    payload = body()
    for attr in ("title", "icon", "description"):
        if attr in payload:
            setattr(section, attr, normalize_text(payload[attr]) or None)
    for attr in ("columns", "sort_order"):
        if attr in payload:
            setattr(section, attr, int(payload[attr] or 0))
    for attr in ("full_width", "is_active"):
        if attr in payload:
            setattr(section, attr, payload[attr] in (True, "true", "1", 1))
    record_audit("update", "form_section", section.id, summary=f"ویرایش بخش «{section.title}»")
    db.session.commit()
    return ok(section.to_dict(), message="بخش به‌روزرسانی شد.")


@bp.delete("/sections/<int:section_id>")
def delete_section(section_id):
    section = db.session.get(FormSection, section_id)
    if section is None:
        return fail("بخش یافت نشد.", 404)
    if any(f.is_builtin for f in section.fields):
        section.is_active = False
        db.session.commit()
        return ok(message="این بخش شامل فیلدهای پایه است؛ غیرفعال شد و حذف نگردید.")
    # Deleting a section cascades to its fields and from there to every stored
    # answer, so a section holding real data is deactivated, never dropped.
    field_ids = [f.id for f in section.fields]
    used = (RecordDynamicValue.query.filter(RecordDynamicValue.field_id.in_(field_ids)).count()
            if field_ids else 0)
    if used:
        section.is_active = False
        for field in section.fields:
            field.is_active = False
        record_audit("update", "form_section", section.id,
                     summary=f"غیرفعال‌سازی بخش «{section.title}» ({used} مقدار ثبت‌شده)")
        db.session.commit()
        return ok(message=f"{used} مقدار ثبت‌شده به فیلدهای این بخش وابسته است؛ "
                          "بخش غیرفعال شد و داده‌ها حفظ شدند.")
    record_audit("delete", "form_section", section.id, summary=f"حذف بخش «{section.title}»")
    db.session.delete(section)
    db.session.commit()
    return ok(message="بخش حذف شد.")


@bp.post("/fields")
def create_field():
    payload = body()
    name = normalize_text(payload.get("field_name"))
    label = normalize_text(payload.get("label"))
    ftype = payload.get("field_type") or "text"
    if not name or not label:
        return fail("نام فیلد و برچسب الزامی است.", 422)
    if ftype not in FIELD_TYPES:
        return fail(f"نوع فیلد نامعتبر است. مقادیر مجاز: {', '.join(FIELD_TYPES)}", 422)
    if not name.replace("_", "").isalnum():
        return fail("نام فیلد فقط می‌تواند شامل حروف انگلیسی، عدد و زیرخط باشد.", 422)
    if FormField.query.filter_by(field_name=name).first():
        return fail("فیلدی با این نام وجود دارد.", 409)
    section = db.session.get(FormSection, int(payload.get("section_id") or 0))
    if section is None:
        return fail("بخش مربوطه را انتخاب کنید.", 422)
    field = FormField(
        section_id=section.id, field_name=name, label=label, field_type=ftype,
        # Admin-created fields are always dynamic: they may not claim a Record
        # column, which would let the form overwrite a built-in value.
        model_attr=None, lookup_category=payload.get("lookup_category") or None,
        placeholder=payload.get("placeholder"), help_text=payload.get("help_text"),
        default_value=payload.get("default_value"),
        is_required=payload.get("is_required") in (True, "true", "1", 1),
        is_active=payload.get("is_active", True) in (True, "true", "1", 1),
        is_builtin=False,
        allow_other=payload.get("allow_other") in (True, "true", "1", 1),
        sort_order=int(payload.get("sort_order")
                       or max([f.sort_order for f in section.fields], default=0) + 1),
        col_span=int(payload.get("col_span") or 1),
        min_value=payload.get("min_value") or None,
        max_value=payload.get("max_value") or None,
        max_length=payload.get("max_length") or None,
        step=payload.get("step") or None,
        show_in_table=payload.get("show_in_table") in (True, "true", "1", 1),
        table_order=int(payload.get("table_order") or 0),
        export_header=payload.get("export_header") or label,
    )
    db.session.add(field)
    db.session.flush()
    for idx, opt in enumerate(payload.get("options") or []):
        value = normalize_text(opt.get("value") if isinstance(opt, dict) else opt)
        if not value:
            continue
        db.session.add(FormFieldOption(
            field_id=field.id, value=value,
            label=normalize_text(opt.get("label")) if isinstance(opt, dict) else value,
            icon=opt.get("icon") if isinstance(opt, dict) else None,
            sort_order=idx))
    record_audit("create", "form_field", field.id, summary=f"افزودن فیلد «{label}»")
    db.session.commit()
    return ok(field.to_dict(), message="فیلد افزوده شد.")


@bp.put("/fields/<int:field_id>")
def update_field(field_id):
    field = db.session.get(FormField, field_id)
    if field is None:
        return fail("فیلد یافت نشد.", 404)
    payload = body()
    if payload.get("field_type") and payload["field_type"] not in FIELD_TYPES:
        return fail("نوع فیلد نامعتبر است.", 422)
    if field.is_builtin:
        # Renaming, reordering, help text and required-ness stay editable; the
        # storage identity (field_name / model_attr / type) does not, because
        # Record columns, reports and exports are bound to it.
        editable = {"label", "placeholder", "help_text", "default_value", "is_required",
                    "is_active", "sort_order", "col_span", "min_value", "max_value",
                    "step", "show_in_table", "table_order", "export_header",
                    "allow_other", "section_id"}
        payload = {k: v for k, v in payload.items() if k in editable}
    for attr in ("label", "placeholder", "help_text", "default_value", "export_header",
                 "step", "lookup_category", "field_type", "field_name"):
        if attr in payload:
            setattr(field, attr, normalize_text(payload[attr]) or None)
    for attr in ("sort_order", "col_span", "table_order", "section_id", "max_length"):
        if attr in payload and payload[attr] not in (None, ""):
            setattr(field, attr, int(payload[attr]))
    for attr in ("min_value", "max_value"):
        if attr in payload:
            setattr(field, attr, float(payload[attr]) if payload[attr] not in (None, "")
                    else None)
    for attr in ("is_required", "is_active", "allow_other", "show_in_table"):
        if attr in payload:
            setattr(field, attr, payload[attr] in (True, "true", "1", 1))
    record_audit("update", "form_field", field.id, summary=f"ویرایش فیلد «{field.label}»")
    db.session.commit()
    return ok(field.to_dict(), message="فیلد به‌روزرسانی شد.")


@bp.delete("/fields/<int:field_id>")
def delete_field(field_id):
    field = db.session.get(FormField, field_id)
    if field is None:
        return fail("فیلد یافت نشد.", 404)
    if field.is_builtin:
        field.is_active = False
        db.session.commit()
        return ok(message="فیلد پایه حذف نمی‌شود؛ غیرفعال شد و از فرم پنهان گردید.")
    used = RecordDynamicValue.query.filter_by(field_id=field.id).count()
    if used:
        field.is_active = False
        db.session.commit()
        return ok(message=f"{used} رکورد مقدار این فیلد را دارند؛ فیلد غیرفعال شد.")
    record_audit("delete", "form_field", field.id, summary=f"حذف فیلد «{field.label}»")
    db.session.delete(field)
    db.session.commit()
    return ok(message="فیلد حذف شد.")


@bp.post("/fields/<int:field_id>/options")
def add_field_option(field_id):
    field = db.session.get(FormField, field_id)
    if field is None:
        return fail("فیلد یافت نشد.", 404)
    payload = body()
    value = normalize_text(payload.get("value"))
    if not value:
        return fail("مقدار گزینه الزامی است.", 422)
    if any(o.value == value for o in field.options):
        return fail("این گزینه وجود دارد.", 409)
    opt = FormFieldOption(
        field_id=field.id, value=value,
        label=normalize_text(payload.get("label")) or value,
        icon=payload.get("icon"),
        sort_order=max([o.sort_order for o in field.options], default=0) + 1)
    db.session.add(opt)
    db.session.commit()
    return ok(field.to_dict(), message="گزینه افزوده شد.")


@bp.put("/options/<int:option_id>")
def update_field_option(option_id):
    opt = db.session.get(FormFieldOption, option_id)
    if opt is None:
        return fail("گزینه یافت نشد.", 404)
    payload = body()
    for attr in ("value", "label", "icon"):
        if attr in payload:
            setattr(opt, attr, normalize_text(payload[attr]) or None)
    if "sort_order" in payload:
        opt.sort_order = int(payload["sort_order"] or 0)
    if "is_active" in payload:
        opt.is_active = payload["is_active"] in (True, "true", "1", 1)
    db.session.commit()
    return ok(opt.to_dict(), message="گزینه به‌روزرسانی شد.")


@bp.post("/reorder")
def reorder_fields():
    payload = body()
    for position, field_id in enumerate(payload.get("fields") or []):
        FormField.query.filter_by(id=int(field_id)).update({"sort_order": position})
    for position, section_id in enumerate(payload.get("sections") or []):
        FormSection.query.filter_by(id=int(section_id)).update({"sort_order": position})
    db.session.commit()
    return ok(message="ترتیب ذخیره شد.")
