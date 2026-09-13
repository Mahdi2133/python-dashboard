"""/api/dashboard — the original dashboard, now fed from the database."""
from flask import Blueprint
from sqlalchemy import func

from ..extensions import db
from ..models import LookupItem, Record, RecordTag, Well
from ..services.auth import permission_required
from ..services.jalali import MONTHS_FA, today_jalali
from ..services.records import search_query
from ._helpers import ok, query_params

bp = Blueprint("api_dashboard", __name__, url_prefix="/api/dashboard")


def _top_lookup(ids, attr, limit=12):
    rows = (db.session.query(LookupItem.value, func.count(Record.id))
            .outerjoin(Record, getattr(Record, attr) == LookupItem.id)
            .filter(Record.id.in_(ids))
            .group_by(LookupItem.value)
            .order_by(func.count(Record.id).desc()).limit(limit).all())
    return [{"label": v or "—", "value": c} for v, c in rows]


def _top_tag(ids, category, limit=12):
    rows = (db.session.query(RecordTag.value, func.count(RecordTag.record_id))
            .filter(RecordTag.category_code == category, RecordTag.record_id.in_(ids))
            .group_by(RecordTag.value)
            .order_by(func.count(RecordTag.record_id).desc()).limit(limit).all())
    return [{"label": v, "value": c} for v, c in rows]


@bp.get("")
@permission_required("dashboard.view")
def dashboard():
    params = query_params()
    base = search_query(params).order_by(None)
    ids = db.select(base.with_entities(Record.id).subquery())

    total = db.session.query(func.count(Record.id)).filter(Record.id.in_(ids)).scalar() or 0
    op_counts = dict(
        db.session.query(LookupItem.value, func.count(Record.id))
        .join(Record, Record.operation_id == LookupItem.id)
        .filter(Record.id.in_(ids)).group_by(LookupItem.value).all())

    monthly_raw = dict(
        db.session.query(Record.j_month, func.count(Record.id))
        .filter(Record.id.in_(ids), Record.j_month.isnot(None))
        .group_by(Record.j_month).all())
    monthly = [{"label": MONTHS_FA[m], "value": monthly_raw.get(m, 0)}
               for m in range(1, 13)]

    yearly = [{"label": str(y), "value": c} for y, c in
              db.session.query(Record.j_year, func.count(Record.id))
              .filter(Record.id.in_(ids), Record.j_year.isnot(None))
              .group_by(Record.j_year).order_by(Record.j_year).all()]

    cur_year = today_jalali()[0]
    stats = [
        {"key": "total", "label": "کل رکوردها", "value": total,
         "icon": "📋", "color": "#0a3d62"},
        {"key": "pull", "label": "عملیات کشیدن", "value": op_counts.get("کشیدن", 0),
         "icon": "🔼", "color": "#e74c3c"},
        {"key": "install", "label": "عملیات نصب", "value": op_counts.get("نصب", 0),
         "icon": "🔽", "color": "#27ae60"},
        {"key": "collect", "label": "جمع‌آوری", "value": op_counts.get("جمع آوری", 0),
         "icon": "📦", "color": "#f39c12"},
        {"key": "new_install", "label": "نصب جدید", "value": op_counts.get("نصب جدید", 0),
         "icon": "🆕", "color": "#8e44ad"},
        {"key": "wells", "label": "چاه‌های درگیر",
         "value": db.session.query(func.count(func.distinct(Record.well_id)))
         .filter(Record.id.in_(ids)).scalar() or 0, "icon": "🕳", "color": "#1e6fa5"},
        {"key": "this_year", "label": f"رکوردهای سال {cur_year}",
         "value": db.session.query(func.count(Record.id))
         .filter(Record.id.in_(ids), Record.j_year == cur_year).scalar() or 0,
         "icon": "📅", "color": "#16a085"},
        {"key": "registered_wells", "label": "چاه‌های ثبت‌شده",
         "value": Well.query.filter_by(is_active=True).count(),
         "icon": "🗂", "color": "#7f8c8d"},
    ]

    return ok({
        "stats": stats,
        "charts": {
            "center": _top_lookup(ids, "center_id"),
            "operation": _top_lookup(ids, "operation_id"),
            "failure": _top_tag(ids, "failure_reason"),
            "contractor": _top_lookup(ids, "contractor_id"),
            "monthly": monthly,
            "pump": _top_lookup(ids, "pump_curr_id"),
            "motor": _top_lookup(ids, "motor_curr_id"),
            "starter": _top_lookup(ids, "starter_id"),
            "opinion": _top_tag(ids, "workshop_opinion"),
            "yearly": yearly,
        },
    })
