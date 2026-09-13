"""/api/lookups — admin management of every option list (requirement 15).

Options are deactivated rather than deleted, so a record recorded five years
ago still resolves to a meaningful label.
"""
from flask import Blueprint

from ..extensions import db
from ..models import LookupAlias, LookupCategory, LookupItem, Record, RecordTag
from ..services.auth import permission_required
from ..services.audit import record_audit
from ..services.lookups import items_by_category, normalize_text
from ._helpers import body, fail, ok

bp = Blueprint("api_lookups", __name__, url_prefix="/api/lookups")


@bp.get("")
@permission_required("record.create")
def all_lookups():
    active_only = "all" not in (body() or {}) and True
    from flask import request
    if request.args.get("all") in ("1", "true"):
        active_only = False
    return ok(items_by_category(active_only=active_only))


@bp.get("/categories")
@permission_required("form.manage")
def categories():
    cats = LookupCategory.query.order_by(LookupCategory.sort_order).all()
    return ok([c.to_dict() for c in cats])


@bp.get("/<code>")
@permission_required("record.create")
def category_items(code):
    cat = LookupCategory.query.filter_by(code=code).one_or_none()
    if cat is None:
        return fail("دسته‌ی گزینه یافت نشد.", 404)
    from flask import request
    active_only = request.args.get("all") not in ("1", "true")
    return ok(cat.to_dict(include_items=True, active_only=active_only))


@bp.post("/<code>")
@permission_required("form.manage")
def add_item(code):
    cat = LookupCategory.query.filter_by(code=code).one_or_none()
    if cat is None:
        return fail("دسته‌ی گزینه یافت نشد.", 404)
    payload = body()
    value = normalize_text(payload.get("value") or payload.get("label"))
    if not value:
        return fail("مقدار گزینه الزامی است.", 422)
    if LookupItem.query.filter_by(category_id=cat.id, value=value).first():
        return fail("این گزینه از قبل وجود دارد.", 409)
    item = LookupItem(
        category_id=cat.id, value=value,
        label=normalize_text(payload.get("label")) or value,
        icon=payload.get("icon") or None,
        sort_order=int(payload.get("sort_order")
                       or max([i.sort_order for i in cat.items], default=0) + 1),
        is_active=payload.get("is_active", True) in (True, "true", "1", 1),
        notes=payload.get("notes"),
    )
    db.session.add(item)
    db.session.flush()
    record_audit("create", "lookup_item", item.id, summary=f"افزودن گزینه «{value}» به {code}")
    db.session.commit()
    return ok(item.to_dict(), message="گزینه افزوده شد.")


@bp.put("/item/<int:item_id>")
@permission_required("form.manage")
def update_item(item_id):
    item = db.session.get(LookupItem, item_id)
    if item is None:
        return fail("گزینه یافت نشد.", 404)
    payload = body()
    if "value" in payload:
        new_value = normalize_text(payload["value"])
        if not new_value:
            return fail("مقدار گزینه نمی‌تواند خالی باشد.", 422)
        if LookupItem.query.filter(LookupItem.category_id == item.category_id,
                                   LookupItem.value == new_value,
                                   LookupItem.id != item.id).first():
            return fail("گزینه‌ای با این مقدار وجود دارد.", 409)
        # Records store the option by id, so renaming is safe; tag rows keep a
        # denormalised copy of the text and are updated alongside.
        RecordTag.query.filter_by(item_id=item.id).update({"value": new_value},
                                                          synchronize_session=False)
        item.value = new_value
    for attr in ("label", "icon", "notes"):
        if attr in payload:
            setattr(item, attr, normalize_text(payload[attr]) or None)
    if "sort_order" in payload:
        item.sort_order = int(payload["sort_order"] or 0)
    if "is_active" in payload:
        item.is_active = payload["is_active"] in (True, "true", "1", 1)
    if "is_adhoc" in payload:
        item.is_adhoc = payload["is_adhoc"] in (True, "true", "1", 1)
    record_audit("update", "lookup_item", item.id, summary=f"ویرایش گزینه «{item.value}»")
    db.session.commit()
    return ok(item.to_dict(), message="گزینه به‌روزرسانی شد.")


@bp.post("/item/<int:item_id>/aliases")
@permission_required("form.manage")
def add_alias(item_id):
    item = db.session.get(LookupItem, item_id)
    if item is None:
        return fail("گزینه یافت نشد.", 404)
    alias = normalize_text(body().get("alias"))
    if not alias:
        return fail("نام مستعار الزامی است.", 422)
    if LookupAlias.query.filter_by(category_id=item.category_id, alias=alias).first():
        return fail("این نام مستعار در همین دسته ثبت شده است.", 409)
    db.session.add(LookupAlias(category_id=item.category_id, item_id=item.id, alias=alias))
    db.session.commit()
    return ok(item.to_dict(), message="نام مستعار افزوده شد.")


@bp.delete("/item/<int:item_id>")
@permission_required("form.manage")
def deactivate_item(item_id):
    """Physical delete only when nothing references the option."""
    item = db.session.get(LookupItem, item_id)
    if item is None:
        return fail("گزینه یافت نشد.", 404)
    used = RecordTag.query.filter_by(item_id=item.id).count()
    if not used:
        for attr in Record.CHOICE_FIELDS:
            used += Record.query.filter(getattr(Record, attr) == item.id).count()
            if used:
                break
    if used:
        item.is_active = False
        record_audit("update", "lookup_item", item.id,
                     summary=f"غیرفعال‌سازی گزینه «{item.value}» ({used} رکورد وابسته)")
        db.session.commit()
        return ok(message=f"گزینه غیرفعال شد؛ {used} رکورد از آن استفاده می‌کنند و حفظ شدند.")
    record_audit("delete", "lookup_item", item.id, summary=f"حذف گزینه «{item.value}»")
    db.session.delete(item)
    db.session.commit()
    return ok(message="گزینه حذف شد (هیچ رکوردی از آن استفاده نمی‌کرد).")


@bp.post("/<code>/reorder")
@permission_required("form.manage")
def reorder(code):
    cat = LookupCategory.query.filter_by(code=code).one_or_none()
    if cat is None:
        return fail("دسته‌ی گزینه یافت نشد.", 404)
    order = body().get("order") or []
    for position, item_id in enumerate(order):
        LookupItem.query.filter_by(id=int(item_id), category_id=cat.id).update(
            {"sort_order": position})
    db.session.commit()
    return ok(message="ترتیب گزینه‌ها ذخیره شد.")
