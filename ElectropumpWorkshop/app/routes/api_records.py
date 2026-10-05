"""/api/records — the table, the form's save path, and record detail."""
from flask import Blueprint

from ..extensions import db
from ..models import Record
from ..services.auth import edit_window_closed, permission_required
from ..services.records import (ValidationError, create_record, deactivate_record,
                                search_query, serialize_record, update_record)
from ._helpers import body, fail, ok, paging, query_params

bp = Blueprint("api_records", __name__, url_prefix="/api/records")


@bp.get("")
@permission_required("record.view")
def list_records():
    """Server-side pagination (requirement 26) — the table never loads it all."""
    page, size = paging()
    query = search_query(query_params())
    total = query.order_by(None).count()
    rows = query.limit(size).offset((page - 1) * size).all()
    return ok(
        [serialize_record(r) for r in rows],
        total=total, page=page, page_size=size,
        pages=max(1, (total + size - 1) // size),
    )


@bp.get("/<int:record_id>")
@permission_required("record.view")
def get_record(record_id):
    record = db.session.get(Record, record_id)
    if record is None:
        return fail("رکورد یافت نشد.", 404)
    return ok(serialize_record(record))


def _outside_scope(data):
    """A مرکز آبرسانی user records their own مرکز's wells only."""
    from ..services.auth import current_user
    from ..services.records import resolve_well
    from ..services.workflow import well_center_scope
    scope = well_center_scope(current_user())
    if scope is None:
        return None
    candidate = data.get("well_id") or data.get("well") or data.get("well_name")
    if candidate in (None, "", []):
        return None
    well, _raw = resolve_well(candidate, create_missing=False)
    if well is not None and well.center_id not in scope:
        return f"چاه «{well.name}» از مرکز شما نیست؛ فقط چاه‌های مرکز خودتان قابل انتخاب است."
    return None


@bp.post("")
@permission_required("record.create")
def post_record():
    data = body()
    blocked = _outside_scope(data)
    if blocked:
        return fail(blocked, 403, fields={"well": blocked})
    try:
        record = create_record(data)
    except ValidationError as exc:
        return fail("اطلاعات فرم کامل یا معتبر نیست.", 422, fields=exc.errors)
    return ok(serialize_record(record), message="رکورد با موفقیت ثبت شد.")


@bp.put("/<int:record_id>")
@bp.patch("/<int:record_id>")
@permission_required("record.edit")
def put_record(record_id):
    record = db.session.get(Record, record_id)
    if record is None:
        return fail("رکورد یافت نشد.", 404)
    expired = edit_window_closed(record)
    if expired:
        return fail(expired, 403)
    data = body()
    blocked = _outside_scope(data) if ("well" in data or "well_id" in data) else None
    if blocked:
        return fail(blocked, 403, fields={"well": blocked})
    try:
        update_record(record, data)
    except ValidationError as exc:
        return fail("اطلاعات فرم کامل یا معتبر نیست.", 422, fields=exc.errors)
    return ok(serialize_record(record), message="رکورد به‌روزرسانی شد.")


@bp.delete("/<int:record_id>")
@permission_required("record.delete")
def delete_record(record_id):
    record = db.session.get(Record, record_id)
    if record is None:
        return fail("رکورد یافت نشد.", 404)
    expired = edit_window_closed(record)
    if expired:
        return fail(expired, 403)
    hard = str(query_params().get("hard", "")).lower() in ("1", "true")
    deactivate_record(record, hard=hard)
    return ok(message="رکورد حذف قطعی شد." if hard else "رکورد غیرفعال شد.")


@bp.post("/<int:record_id>/restore")
@permission_required("record.delete")
def restore_record(record_id):
    record = db.session.get(Record, record_id)
    if record is None:
        return fail("رکورد یافت نشد.", 404)
    expired = edit_window_closed(record)
    if expired:
        return fail(expired, 403)
    record.is_active = True
    db.session.commit()
    return ok(serialize_record(record), message="رکورد بازیابی شد.")
