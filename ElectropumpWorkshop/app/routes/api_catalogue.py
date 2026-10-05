"""/api/catalogue — the pump catalogue: read by every form, kept by the admin."""
import io

from flask import Blueprint, request, send_file

from ..extensions import db
from ..models import PumpCatalogModel, PumpCatalogPoint
from ..models.catalogue import norm_stages, norm_type
from ..services import catalogue as cat
from ..services.audit import record_audit
from ..services.auth import FORM_READERS, permission_required, permission_required_any
from ._helpers import body, fail, ok

bp = Blueprint("api_catalogue", __name__, url_prefix="/api/catalogue")


@bp.get("/compact")
@permission_required_any(*FORM_READERS)
def compact():
    """Every active model's curve, keyed «type|stages», for the form engine."""
    return ok({"models": cat.compact()})


@bp.get("")
@permission_required_any(*FORM_READERS)
def list_models():
    q = PumpCatalogModel.query
    if request.args.get("all") not in ("1", "true"):
        q = q.filter_by(is_active=True)
    t = (request.args.get("type") or "").strip()
    if t:
        q = q.filter_by(pump_type=norm_type(t))
    rows = q.order_by(PumpCatalogModel.sort_order, PumpCatalogModel.id).all()
    types = sorted({m.pump_type for m in PumpCatalogModel.query.all()},
                   key=lambda x: (len(x), x))
    return ok({"models": [m.to_dict(points=request.args.get("points") == "1") for m in rows],
               "types": types})


@bp.get("/<int:model_id>")
@permission_required_any(*FORM_READERS)
def get_model(model_id):
    m = db.session.get(PumpCatalogModel, model_id)
    if m is None:
        return fail("مدل پیدا نشد.", 404)
    return ok(m.to_dict())


def _num(v):
    if v in (None, ""):
        return None
    try:
        return float(str(v).replace("٫", ".").replace(",", ""))
    except ValueError:
        raise ValueError(f"«{v}» عدد نیست.")


def _apply(m, data):
    for key in ("motor_kw", "motor_hp", "current_a", "weight_kg", "pump_length_mm",
                "total_length_mm", "motor_eff"):
        if key in data:
            setattr(m, key, _num(data[key]))
    for key in ("trim", "note", "brand", "source"):
        if key in data:
            setattr(m, key, (str(data[key]).strip() or None) if data[key] is not None else None)
    if not m.brand:
        m.brand = "گازار"
    if "is_active" in data:
        m.is_active = bool(data["is_active"])
    if "points" in data:
        pts = []
        for p in data["points"] or []:
            q, h = _num(p.get("q_m3h")), _num(p.get("head"))
            if q is None and _num(p.get("q_ls")) is not None:
                q = _num(p.get("q_ls")) * 3.6
            if q is None and h is None:
                continue
            if q is None or h is None:
                raise ValueError("هر نقطه‌ی منحنی هم دبی می‌خواهد هم هد.")
            pts.append(PumpCatalogPoint(q_m3h=q, head=h, pump_eff=_num(p.get("pump_eff"))))
        if len(pts) < 2:
            raise ValueError("منحنی دست‌کم دو نقطه لازم دارد.")
        m.points = sorted(pts, key=lambda p: p.q_m3h)


@bp.post("")
@permission_required("form.manage")
def create_model():
    data = body()
    t, s = norm_type(data.get("pump_type")), norm_stages(data.get("stages"))
    if not t or not s:
        return fail("تیپ پمپ و تعداد طبقات لازم است.")
    brand = (data.get("brand") or "گازار").strip()
    if PumpCatalogModel.query.filter_by(brand=brand, pump_type=t, stages=s).first():
        return fail(f"مدل {t}/{s} از قبل در کاتالوگ هست.", 409)
    top = (db.session.query(db.func.max(PumpCatalogModel.sort_order)).scalar() or 0) + 1
    m = PumpCatalogModel(brand=brand, pump_type=t, stages=s, sort_order=top, source="افزوده‌ی دستی")
    db.session.add(m)
    try:
        _apply(m, data)
    except ValueError as exc:
        db.session.rollback()
        return fail(str(exc), 422)
    db.session.flush()
    record_audit("create", "pump_catalog", m.id, summary=f"مدل {m.title} به کاتالوگ پمپ افزوده شد")
    db.session.commit()
    cat.invalidate()
    return ok(m.to_dict())


@bp.put("/<int:model_id>")
@permission_required("form.manage")
def update_model(model_id):
    m = db.session.get(PumpCatalogModel, model_id)
    if m is None:
        return fail("مدل پیدا نشد.", 404)
    try:
        _apply(m, body())
    except ValueError as exc:
        db.session.rollback()
        return fail(str(exc), 422)
    record_audit("update", "pump_catalog", m.id, summary=f"مدل {m.title} در کاتالوگ پمپ ویرایش شد")
    db.session.commit()
    cat.invalidate()
    return ok(m.to_dict())


@bp.get("/export.xlsx")
@permission_required_any(*FORM_READERS)
def export_xlsx():
    return send_file(io.BytesIO(cat.export_xlsx()), as_attachment=True,
                     download_name="pump_catalogue.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@bp.post("/import")
@permission_required("form.manage")
def import_xlsx():
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        return fail("فایل اکسل انتخاب نشده است.")
    if not upload.filename.lower().endswith((".xlsx", ".xlsm")):
        return fail("فقط فایل .xlsx پشتیبانی می‌شود.", 422)
    try:
        result = cat.import_xlsx(upload.read())
    except ValueError as exc:
        db.session.rollback()
        return fail(str(exc), 422)
    record_audit("import", "pump_catalog", None,
                 summary=f"کاتالوگ پمپ از اکسل: {result['added']} مدل جدید، {result['updated']} مدل به‌روز")
    db.session.commit()
    return ok(result)
