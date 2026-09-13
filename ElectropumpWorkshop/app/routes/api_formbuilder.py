"""/api/form-builder — the real form designer (requirements 13 & 14)."""
from flask import Blueprint, request

from ..extensions import db
from ..models import (FormField, FormFieldOption, FormSection, LookupCategory,
                      LookupItem, RecordDynamicValue)
from ..models.formbuilder import FIELD_TYPES
from ..services.auth import permission_required
from ..services.audit import record_audit
from ..services.jalali import MONTHS_FA
from ..services.lookups import items_by_category, normalize_text
from ._helpers import body, fail, ok

bp = Blueprint("api_formbuilder", __name__, url_prefix="/api/form-builder")


def _sync_options(field, options):
    """Reconcile a field's own options with the list the editor submitted.

    Options in use by saved records must not vanish, so an option that is
    dropped from the list is deactivated rather than deleted; one that comes
    back is reactivated. Matching is by value, which is what records store.
    """
    incoming = []
    for idx, opt in enumerate(options):
        if isinstance(opt, dict):
            value = normalize_text(opt.get("value"))
            label = normalize_text(opt.get("label")) or value
            icon = (opt.get("icon") or "").strip() or None
            active = opt.get("is_active", True) in (True, "true", "1", 1)
        else:
            value = label = normalize_text(opt)
            icon, active = None, True
        if not value:
            continue
        incoming.append({"value": value, "label": label, "icon": icon,
                         "sort_order": idx, "is_active": active})

    existing = {o.value: o for o in field.options}
    seen = set()
    for spec in incoming:
        seen.add(spec["value"])
        current = existing.get(spec["value"])
        if current is None:
            db.session.add(FormFieldOption(field_id=field.id, **spec))
        else:
            current.label = spec["label"]
            current.icon = spec["icon"]
            current.sort_order = spec["sort_order"]
            current.is_active = spec["is_active"]
    for value, option in existing.items():
        if value not in seen:
            option.is_active = False
    db.session.flush()


def _month_options():
    return [{"value": str(i), "label": MONTHS_FA[i], "is_active": True,
             "sort_order": i} for i in range(1, 13)]


@bp.get("")
@permission_required("record.create")
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
@permission_required("form.manage")
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
@permission_required("form.manage")
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
@permission_required("form.manage")
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
@permission_required("form.manage")
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
    _sync_options(field, payload.get("options") or [])
    record_audit("create", "form_field", field.id, summary=f"افزودن فیلد «{label}»")
    db.session.commit()
    return ok(field.to_dict(active_only=False), message="فیلد افزوده شد.")


@bp.put("/fields/<int:field_id>")
@permission_required("form.manage")
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

    # Options were previously ignored here, so editing a field's choices did
    # nothing — the field came back with its original list every time.
    if "options" in payload:
        _sync_options(field, payload.get("options") or [])

    record_audit("update", "form_field", field.id, summary=f"ویرایش فیلد «{field.label}»")
    db.session.commit()
    return ok(field.to_dict(active_only=False), message="فیلد به‌روزرسانی شد.")


@bp.delete("/fields/<int:field_id>")
@permission_required("form.manage")
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
@permission_required("form.manage")
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
@permission_required("form.manage")
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


@bp.get("/fields/<int:field_id>/options")
@permission_required("form.manage")
def field_options(field_id):
    """The options actually shown for a field, wherever they are stored."""
    field = db.session.get(FormField, field_id)
    if field is None:
        return fail("فیلد یافت نشد.", 404)
    source = field.options_source
    if source == "lookup":
        cat = LookupCategory.query.filter_by(code=field.lookup_category).one_or_none()
        items = sorted(cat.items, key=lambda i: (i.sort_order, i.id)) if cat else []
        return ok({
            "source": "lookup", "category": field.lookup_category,
            "category_name": cat.name_fa if cat else field.lookup_category,
            "shared_with": [f.field_name for f in FormField.query.filter_by(
                lookup_category=field.lookup_category).all() if f.id != field.id],
            "options": [i.to_dict() for i in items],
        })
    if source == "months":
        return ok({"source": "months", "options": _month_options(),
                   "readonly": True,
                   "note": "ماه‌های تقویم شمسی ثابت‌اند و ویرایش نمی‌شوند."})
    if source == "wells":
        return ok({"source": "wells", "options": [], "readonly": True,
                   "note": "گزینه‌های این فیلد از جدول «چاه‌ها» خوانده می‌شود؛ "
                           "از صفحه‌ی «چاه‌ها» مدیریت کنید."})
    return ok({"source": "own", "options": [o.to_dict() for o in
                                            sorted(field.options,
                                                   key=lambda o: o.sort_order)]})


@bp.put("/fields/<int:field_id>/options")
@permission_required("form.manage")
def set_field_options(field_id):
    """Save the option list of a field, routing to the right store.

    For a lookup-backed field this edits the shared category, which is what
    the operator means when they open «مرکز» and change its buttons; the UI
    warns them that other fields share that list.
    """
    field = db.session.get(FormField, field_id)
    if field is None:
        return fail("فیلد یافت نشد.", 404)
    source = field.options_source
    if source in ("months", "wells"):
        return fail("گزینه‌های این فیلد از این بخش قابل ویرایش نیستند.", 422)

    options = body().get("options")
    if not isinstance(options, list):
        return fail("فهرست گزینه‌ها ارسال نشده است.", 422)

    if source == "own":
        _sync_options(field, options)
        record_audit("update", "form_field", field.id,
                     summary=f"ویرایش گزینه‌های فیلد «{field.label}»")
        db.session.commit()
        return ok(field.to_dict(active_only=False), message="گزینه‌ها ذخیره شد.")

    cat = LookupCategory.query.filter_by(code=field.lookup_category).one_or_none()
    if cat is None:
        return fail("دسته‌ی گزینه یافت نشد.", 404)

    existing = {i.value: i for i in cat.items}
    seen, created = set(), 0
    for idx, opt in enumerate(options):
        value = normalize_text(opt.get("value") if isinstance(opt, dict) else opt)
        if not value:
            continue
        label = normalize_text(opt.get("label")) if isinstance(opt, dict) else value
        icon = (opt.get("icon") or "").strip() or None if isinstance(opt, dict) else None
        active = (opt.get("is_active", True) in (True, "true", "1", 1)
                  if isinstance(opt, dict) else True)
        seen.add(value)
        item = existing.get(value)
        if item is None:
            item = LookupItem(category_id=cat.id, value=value, label=label or value,
                              icon=icon, sort_order=idx, is_active=active)
            db.session.add(item)
            created += 1
        else:
            item.label = label or value
            item.icon = icon
            item.sort_order = idx
            item.is_active = active
            # "Ad-hoc" means an imported value nobody has vetted yet. Activating
            # it IS the admin vetting it; merely saving the list while leaving
            # it switched off is not, so the flag stays and it keeps showing up
            # for review.
            if active:
                item.is_adhoc = False
    # Options left out are deactivated, never deleted: records point at them.
    for value, item in existing.items():
        if value not in seen:
            item.is_active = False
    record_audit("update", "lookup_item", None,
                 summary=f"ویرایش گزینه‌های «{cat.name_fa}» از فرم‌ساز "
                         f"({created} گزینه جدید)")
    db.session.commit()
    return ok({"source": "lookup", "category": cat.code,
               "options": [i.to_dict() for i in
                           sorted(cat.items, key=lambda i: (i.sort_order, i.id))]},
              message="گزینه‌ها ذخیره شد.")


@bp.post("/reorder")
@permission_required("form.manage")
def reorder_fields():
    payload = body()
    for position, field_id in enumerate(payload.get("fields") or []):
        FormField.query.filter_by(id=int(field_id)).update({"sort_order": position})
    for position, section_id in enumerate(payload.get("sections") or []):
        FormSection.query.filter_by(id=int(section_id)).update({"sort_order": position})
    db.session.commit()
    return ok(message="ترتیب ذخیره شد.")
