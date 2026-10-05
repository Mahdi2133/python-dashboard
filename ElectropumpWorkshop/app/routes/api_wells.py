"""/api/wells — replaces the hardcoded ALL_WELLS array (requirement 25)."""
from flask import Blueprint, request
from sqlalchemy import func

from ..extensions import db
from ..models import Record, Well, WellAlias
from ..services.auth import (permission_required,
                             permission_required_any)
from ..services.audit import record_audit
from ..services.lookups import normalize_text, resolve_id, well_key
from ._helpers import body, fail, ok, paging

bp = Blueprint("api_wells", __name__, url_prefix="/api/wells")


@bp.get("")
@permission_required_any("well.view", "workflow.act")
def list_wells():
    q = normalize_text(request.args.get("q", ""))
    limit = min(int(request.args.get("limit", 20) or 20), 500)
    query = Well.query
    if request.args.get("all") not in ("1", "true"):
        query = query.filter(Well.is_active.is_(True))
    # a مرکز آبرسانی user picks from their own مرکز's wells only
    from ..services.auth import current_user
    from ..services.workflow import well_center_scope
    scope = well_center_scope(current_user())
    if scope is not None:
        query = query.filter(Well.center_id.in_(scope))
    if q:
        like = f"%{q}%"
        # Operators look wells up by PM code as often as by name.
        query = query.filter(db.or_(Well.name.ilike(like),
                                    Well.pm_code.ilike(like),
                                    Well.well_class.ilike(like),
                                    Well.aliases.any(WellAlias.alias.ilike(like))))
    if q:
        # Relevance before alphabet: an exact name, then names that start with
        # what was typed, then the rest — otherwise typing "کورده 1" offers
        # "چاه کورده 14" first purely because it sorts earlier. Within each
        # band, wells from the official register (they carry a PM code) come
        # before ones that only ever appeared in an operations spreadsheet.
        rank = db.case(
            (Well.name == q, 0),
            (Well.pm_code == q, 0),
            (Well.name.ilike(f"{q}%"), 1),
            (Well.well_class == q, 1),
            else_=2,
        )
        wells = (query.order_by(rank, Well.pm_code.is_(None),
                                db.func.length(Well.name), Well.name)
                 # Fetched deep, then collapsed: the picker must still be able
                 # to offer `limit` distinct wells after duplicates are dropped.
                 .limit(limit * 4).all())
    else:
        wells = (query.order_by(Well.pm_code.is_(None), Well.name)
                 .limit(limit * 4).all())
    return ok([w.to_dict() for w in _collapse(wells, limit)])


def _collapse(wells, limit):
    """Drop rows that are the same well spelled differently.

    deduplicate_wells() merges these away at startup, but a well added by hand
    or by an import since then can reintroduce a pair, and the operator must
    never be asked to choose between «ده غیبی یک» and «ده غیبی 1». The list is
    already in relevance order and puts registered wells first, so the first
    row of each group is the one to keep. Wells whose PM codes differ are kept
    apart: those are two real wells whose names happen to read alike.
    """
    seen, out = {}, []
    for well in wells:
        key = well_key(well.name)
        if key not in seen:
            seen[key] = {well.pm_code}
        elif well.pm_code and well.pm_code not in seen[key]:
            seen[key].add(well.pm_code)   # a second register entry, not a copy
        else:
            continue
        out.append(well)
        if len(out) >= limit:
            break
    return out


def _same_well_as(name, exclude_id=None):
    """The active well ``name`` would duplicate, if any.

    Compared on ``well_key`` rather than the raw string, so adding «ده غیبی یک»
    beside the register's «ده غیبی 1» is refused at the door instead of having
    to be merged away later.
    """
    key = well_key(name)
    if not key:
        return None
    query = Well.query.filter(Well.is_active.is_(True))
    if exclude_id is not None:
        query = query.filter(Well.id != exclude_id)
    return next((w for w in query.all() if well_key(w.name) == key), None)


@bp.get("/page")
@permission_required_any("well.view", "workflow.act")
def paged_wells():
    page, size = paging()
    q = normalize_text(request.args.get("q", ""))
    query = Well.query
    if q:
        query = query.filter(Well.name.ilike(f"%{q}%"))
    if request.args.get("unverified") in ("1", "true"):
        query = query.filter(Well.is_verified.is_(False))
    total = query.count()
    counts = dict(db.session.query(Record.well_id, func.count(Record.id))
                  .filter(Record.is_active.is_(True))
                  .group_by(Record.well_id).all())
    rows = query.order_by(Well.name).limit(size).offset((page - 1) * size).all()
    data = []
    for w in rows:
        d = w.to_dict()
        d["record_count"] = counts.get(w.id, 0)
        data.append(d)
    return ok(data, total=total, page=page, page_size=size,
              pages=max(1, (total + size - 1) // size))


@bp.post("")
@permission_required("well.manage")
def create_well():
    payload = body()
    name = normalize_text(payload.get("name"))
    if not name:
        return fail("نام چاه الزامی است.", 422)
    clash = _same_well_as(name)
    if clash is not None:
        return fail(f"چاهی با این نام از قبل ثبت شده است: «{clash.name}».", 409)
    well = Well(
        name=name, code=normalize_text(payload.get("code")) or None,
        pm_code=normalize_text(payload.get("pm_code")) or None,
        well_class=normalize_text(payload.get("well_class")) or None,
        address=normalize_text(payload.get("address")) or None,
        center_id=resolve_id("center", payload.get("center")),
        depth=payload.get("depth") or None,
        notes=payload.get("notes"), is_verified=True,
    )
    db.session.add(well)
    db.session.flush()
    record_audit("create", "well", well.id, summary=f"افزودن چاه «{name}»")
    db.session.commit()
    return ok(well.to_dict(), message="چاه افزوده شد.")


@bp.put("/<int:well_id>")
@permission_required("well.manage")
def update_well(well_id):
    well = db.session.get(Well, well_id)
    if well is None:
        return fail("چاه یافت نشد.", 404)
    payload = body()
    if payload.get("name"):
        new_name = normalize_text(payload["name"])
        clash = _same_well_as(new_name, exclude_id=well.id)
        if clash is not None:
            return fail(f"نام تکراری است: «{clash.name}».", 409)
        well.name = new_name
    for attr in ("code", "notes", "status", "pm_code", "well_class", "address"):
        if attr in payload:
            setattr(well, attr, normalize_text(payload[attr]) or None)
    if "center" in payload or "center_id" in payload:
        well.center_id = (payload.get("center_id")
                          or resolve_id("center", payload.get("center")))
    if "depth" in payload:
        well.depth = payload["depth"] or None
    if "is_active" in payload:
        well.is_active = bool(payload["is_active"])
    if "is_verified" in payload:
        well.is_verified = bool(payload["is_verified"])
    record_audit("update", "well", well.id, summary=f"ویرایش چاه «{well.name}»")
    db.session.commit()
    return ok(well.to_dict(), message="چاه به‌روزرسانی شد.")


@bp.delete("/<int:well_id>")
@permission_required("well.manage")
def deactivate_well(well_id):
    """Deactivate, never delete — old records must keep their well."""
    well = db.session.get(Well, well_id)
    if well is None:
        return fail("چاه یافت نشد.", 404)
    well.is_active = False
    record_audit("delete", "well", well.id, summary=f"غیرفعال‌سازی چاه «{well.name}»")
    db.session.commit()
    return ok(message="چاه غیرفعال شد (رکوردهای قبلی حفظ شدند).")


@bp.post("/<int:well_id>/merge")
@permission_required("well.manage")
def merge_well(well_id):
    """Fold a duplicate/misspelled well into a canonical one."""
    target = db.session.get(Well, well_id)
    payload = body()
    source = db.session.get(Well, int(payload.get("source_id") or 0))
    if target is None or source is None:
        return fail("چاه مبدأ یا مقصد یافت نشد.", 404)
    if target.id == source.id:
        return fail("چاه مبدأ و مقصد یکسان است.", 422)
    moved = Record.query.filter_by(well_id=source.id).update(
        {"well_id": target.id}, synchronize_session=False)
    if not WellAlias.query.filter_by(alias=source.name).first():
        db.session.add(WellAlias(well_id=target.id, alias=source.name))
    # Keep whichever identifiers the pair has between them.
    for attr in ("pm_code", "well_class", "address", "code", "center_id", "depth"):
        if not getattr(target, attr) and getattr(source, attr):
            setattr(target, attr, getattr(source, attr))
    source.is_active = False
    record_audit("update", "well", target.id,
                 summary=f"ادغام «{source.name}» در «{target.name}» ({moved} رکورد)")
    db.session.commit()
    return ok(message=f"{moved} رکورد منتقل شد و «{source.name}» غیرفعال گردید.")
