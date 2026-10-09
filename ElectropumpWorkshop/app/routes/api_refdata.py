"""/api/refdata — the reference databases: browse, import, link, export.

Reading a well's profile is open to everyone who fills a form (the stage view
shows it beside the form); browsing the tables needs «refdata.view» and
importing or re-linking «refdata.manage».
"""
from __future__ import annotations

import io
import json
import os

from flask import Blueprint, current_app, request, send_file

from ..extensions import db
from ..refdata import SOURCES, bind_path
from ..refdata import flowtest as ft_mod
from ..refdata import production as pr_mod
from ..refdata import videometry as vm_mod
from ..refdata.models import (FlowPoint, FlowSource, FlowTest, ProdMonth, ProdSource,
                              ProdWell, VideoInspection, VideoSource)
from ..refdata.profile import catalogue_options, well_profile
from ..refdata.textnorm import name_key
from ..services.audit import record_audit
from ..services.auth import FORM_READERS, permission_required, permission_required_any
from ._helpers import body, fail, ok

bp = Blueprint("api_refdata", __name__, url_prefix="/api/refdata")

READERS = FORM_READERS + ("refdata.view",)


def _well_names(ids):
    from ..models import Well
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return {w.id: w.name for w in Well.query.filter(Well.id.in_(ids)).all()}


def _file_info(key):
    path = bind_path(current_app, key)
    try:
        size = os.path.getsize(path)
    except OSError:
        size = 0
    return {"file": os.path.basename(path), "path": path, "size": size}


# ── overview ─────────────────────────────────────────────────────────────────
@bp.get("/summary")
@permission_required("refdata.view")
def summary():
    last = lambda model: (model.query.order_by(model.id.desc()).first())  # noqa: E731
    lf, lp, lv = last(FlowSource), last(ProdSource), last(VideoSource)
    years = [y for (y,) in db.session.query(ProdMonth.year).distinct().order_by(ProdMonth.year)]
    return ok({"sources": [
        {"key": "flowtest", "title": SOURCES["flowtest"][0], "icon": SOURCES["flowtest"][2],
         **_file_info("flowtest"),
         "rows": FlowTest.query.count(), "points": FlowPoint.query.count(),
         "wells": db.session.query(db.func.count(db.distinct(FlowTest.main_well_id))).scalar(),
         "unmatched": FlowTest.query.filter(FlowTest.main_well_id.is_(None)).count(),
         "files": FlowSource.query.filter_by(status="ok").count(),
         "errors": [{"file": s.file_name, "message": s.message}
                    for s in FlowSource.query.filter_by(status="error").all()],
         "range": [db.session.query(db.func.min(FlowTest.test_date)).scalar(),
                   db.session.query(db.func.max(FlowTest.test_date)).scalar()],
         "imported_at": lf.imported_at.isoformat(" ", "minutes") if lf else None},
        {"key": "production", "title": SOURCES["production"][0], "icon": SOURCES["production"][2],
         **_file_info("production"),
         "rows": ProdWell.query.count(), "points": ProdMonth.query.count(),
         "wells": ProdWell.query.filter(ProdWell.main_well_id.isnot(None)).count(),
         "unmatched": ProdWell.query.filter(ProdWell.main_well_id.is_(None)).count(),
         "files": ProdSource.query.count(), "errors": [],
         "range": [years[0] if years else None, years[-1] if years else None],
         "imported_at": lp.imported_at.isoformat(" ", "minutes") if lp else None},
        {"key": "videometry", "title": SOURCES["videometry"][0], "icon": SOURCES["videometry"][2],
         **_file_info("videometry"),
         "rows": VideoInspection.query.count(), "points": None,
         "wells": db.session.query(db.func.count(db.distinct(VideoInspection.main_well_id))).scalar(),
         "unmatched": VideoInspection.query.filter(VideoInspection.main_well_id.is_(None)).count(),
         "files": VideoSource.query.count(), "errors": [],
         "range": [db.session.query(db.func.min(VideoInspection.insp_date)).scalar(),
                   db.session.query(db.func.max(VideoInspection.insp_date)).scalar()],
         "imported_at": lv.imported_at.isoformat(" ", "minutes") if lv else None},
    ]})


@bp.get("/catalogue")
@permission_required_any(*READERS, "form.manage")
def catalogue():
    """The values a form field can start from (فرم‌ساز → «پر شدن خودکار»)."""
    return ok({"options": catalogue_options()})


# ── one well ─────────────────────────────────────────────────────────────────
@bp.get("/well")
@permission_required_any(*READERS)
def well():
    """A register well's profile, its flow tests, production months, inspections."""
    well_id = request.args.get("well_id", type=int)
    if not well_id and request.args.get("well"):
        from ..services.records import resolve_well
        w, _raw = resolve_well(request.args.get("well"), create_missing=False)
        well_id = w.id if w else None
    if not well_id:
        return ok({"profile": {"values": {}, "sources": []}, "tests": [], "months": [],
                   "inspections": []})
    prof = well_profile(well_id)
    tests = (FlowTest.query.filter_by(main_well_id=well_id)
             .order_by(FlowTest.test_date_num.desc().nullslast()).limit(30).all())
    pw = (ProdWell.query.filter_by(main_well_id=well_id)
          .order_by(ProdWell.snapshot_year.desc().nullslast()).first())
    months = sorted(pw.months, key=lambda m: (m.year, m.month)) if pw else []
    insp = (VideoInspection.query.filter_by(main_well_id=well_id)
            .order_by(VideoInspection.insp_date_num.desc().nullslast()).all())
    from ..refdata.profile import CATALOGUE
    labelled = [{"key": k, "label": CATALOGUE[k][0], "group": CATALOGUE[k][1],
                 "unit": CATALOGUE[k][2], "value": v}
                for k, v in prof["values"].items() if k in CATALOGUE]
    return ok({"well_id": well_id, "profile": prof, "labelled": labelled,
               "tests": [_test_row(t, points=True) for t in tests],
               "production": _prod_row(pw) if pw else None,
               "months": [{"year": m.year, "month": m.month, "production": m.production,
                           "hours": m.hours, "avg_flow": m.avg_flow, "pressure": m.pressure,
                           "pressure_type": m.pressure_type} for m in months],
               "inspections": [_video_row(v) for v in insp]})


# ── tables ───────────────────────────────────────────────────────────────────
def _page():
    return max(1, request.args.get("page", 1, type=int)), min(500, request.args.get("size", 100, type=int))


def _test_row(t, points=False, names=None):
    from ..services.epump import electropump_label
    row = {"id": t.id, "well_name": t.well_name, "office": t.office, "well_class": t.well_class,
           "main_well_id": t.main_well_id, "match_method": t.match_method,
           "main_well": (names or {}).get(t.main_well_id),
           "test_date": t.test_date, "test_reason": t.test_reason,
           "electropump": electropump_label(t.pump_type, t.pump_stages, t.motor_kw) or t.pump_label,
           "well_depth": t.well_depth, "install_depth": t.install_depth,
           "static_level": t.static_level, "design_flow": t.design_flow,
           "net_flow": t.net_flow, "net_pressure": t.net_pressure, "efficiency": t.efficiency,
           "starter": t.starter, "well_type": t.well_type, "expert_opinion": t.expert_opinion,
           "point_count": len(t.points)}
    if points:
        row["points"] = [{"point_no": p.point_no, "label": p.label, "at_network": p.at_network,
                          "amps": p.amps, "head": p.head, "pipe_loss": p.pipe_loss,
                          "flow": p.flow, "water_column": p.water_column,
                          "dynamic_level": p.dynamic_level, "pressure": p.pressure,
                          "active_power": p.active_power} for p in t.points]
        row["design_curve"] = json.loads(t.design_curve) if t.design_curve else None
        src = db.session.get(FlowSource, t.source_id) if t.source_id else None
        row["source_file"] = src.file_name if src else None
    return row


def _prod_row(w, names=None):
    from ..services.epump import electropump_label
    months = sorted(w.months, key=lambda m: (m.year, m.month))
    flows = [m for m in months if m.avg_flow not in (None, 0)]
    last = flows[-1] if flows else None
    return {"id": w.id, "facility_code": w.facility_code, "name": w.name,
            "main_well_id": w.main_well_id, "match_method": w.match_method,
            "main_well": (names or {}).get(w.main_well_id),
            "center_code": w.center_code, "zone": w.zone, "urban_rural": w.urban_rural,
            "electropump": electropump_label(w.pump_type, w.pump_stages, w.motor_kw),
            "pump_install_date": w.pump_install_date, "last_rehab_date": w.last_rehab_date,
            "last_flow": last.avg_flow if last else None,
            "last_flow_month": f"{last.year}/{last.month:02d}" if last else None,
            "low_run_reason": w.low_run_reason, "meter_status": w.meter_status,
            "months": len(months)}


def _video_row(v, names=None):
    return {"id": v.id, "facility_code": v.facility_code, "name": v.name, "center": v.center,
            "main_well_id": v.main_well_id, "match_method": v.match_method,
            "main_well": (names or {}).get(v.main_well_id),
            "insp_date": v.insp_date, "depth": v.depth, "static_level": v.static_level,
            "screen_start": v.screen_start, "defect_count": v.defect_count, "notes": v.notes,
            "no_screen": json.loads(v.no_screen or "[]"), "repair": json.loads(v.repair or "[]"),
            "tear": json.loads(v.tear or "[]"), "change": json.loads(v.change or "[]"),
            "clog": json.loads(v.clog or "[]")}


def _search(query, cols, text):
    """Rows whose name, name key or code contains what was typed."""
    text = (text or "").strip()
    if not text:
        return query
    from ..refdata.textnorm import norm_text
    probes = {text, norm_text(text), name_key(text)} - {""}
    return query.filter(db.or_(*[c.contains(p) for c in cols for p in probes]))


@bp.get("/flowtests")
@permission_required("refdata.view")
def flowtests():
    q = FlowTest.query
    q = _search(q, [FlowTest.well_name, FlowTest.well_key, FlowTest.well_class], request.args.get("q"))
    if request.args.get("office"):
        q = q.filter(FlowTest.office == request.args["office"])
    if request.args.get("unmatched") == "1":
        q = q.filter(FlowTest.main_well_id.is_(None))
    if request.args.get("well_id", type=int):
        q = q.filter(FlowTest.main_well_id == request.args.get("well_id", type=int))
    total = q.count()
    page, size = _page()
    rows = (q.order_by(FlowTest.test_date_num.desc().nullslast(), FlowTest.id.desc())
            .offset((page - 1) * size).limit(size).all())
    names = _well_names(r.main_well_id for r in rows)
    offices = [o for (o,) in db.session.query(FlowTest.office).distinct() if o]
    return ok({"rows": [_test_row(r, names=names) for r in rows], "total": total,
               "page": page, "size": size, "offices": sorted(offices)})


@bp.get("/flowtests/<int:test_id>")
@permission_required("refdata.view")
def flowtest_detail(test_id):
    t = db.session.get(FlowTest, test_id)
    if t is None:
        return fail("آزمایش پیدا نشد.", 404)
    row = _test_row(t, points=True, names=_well_names([t.main_well_id]))
    raw = json.loads(t.raw_json or "{}")
    row["raw"] = raw
    # every cell the sheet carried, under the sheet's own (Persian) label
    KV = ft_mod.KV
    extra = {"pump_type": "تیپ پمپ", "pump_stages": "تعداد طبقات", "motor_kw": "تیپ موتور (kW)",
             "expert_opinion": "نظر کارشناس"}
    order = [k for k in KV if k in raw] + [k for k in raw if k not in KV]
    row["raw_labelled"] = [{"key": k, "label": KV[k][0][0] if k in KV else extra.get(k, k),
                            "value": raw[k]}
                           for k in order if k not in ("well_name", "sheet", "expert_opinion")
                           and raw[k] not in (None, "")]
    return ok(row)


@bp.get("/production")
@permission_required("refdata.view")
def production():
    q = ProdWell.query
    q = _search(q, [ProdWell.name, ProdWell.name_key, ProdWell.facility_code], request.args.get("q"))
    if request.args.get("unmatched") == "1":
        q = q.filter(ProdWell.main_well_id.is_(None))
    total = q.count()
    page, size = _page()
    rows = q.order_by(ProdWell.facility_code).offset((page - 1) * size).limit(size).all()
    names = _well_names(r.main_well_id for r in rows)
    return ok({"rows": [_prod_row(r, names) for r in rows], "total": total,
               "page": page, "size": size})


@bp.get("/production/<int:well_row_id>")
@permission_required("refdata.view")
def production_detail(well_row_id):
    w = db.session.get(ProdWell, well_row_id)
    if w is None:
        return fail("چاه پیدا نشد.", 404)
    months = sorted(w.months, key=lambda m: (m.year, m.month))
    return ok({**_prod_row(w, _well_names([w.main_well_id])),
               "last_rehab_failure": w.last_rehab_failure,
               "months": [{"year": m.year, "month": m.month, "production": m.production,
                           "hours": m.hours, "avg_flow": m.avg_flow, "pressure": m.pressure,
                           "pressure_type": m.pressure_type} for m in months]})


@bp.get("/videometry")
@permission_required("refdata.view")
def videometry():
    q = VideoInspection.query
    q = _search(q, [VideoInspection.name, VideoInspection.name_key, VideoInspection.facility_code],
                request.args.get("q"))
    if request.args.get("unmatched") == "1":
        q = q.filter(VideoInspection.main_well_id.is_(None))
    total = q.count()
    page, size = _page()
    rows = (q.order_by(VideoInspection.insp_date_num.desc().nullslast())
            .offset((page - 1) * size).limit(size).all())
    names = _well_names(r.main_well_id for r in rows)
    return ok({"rows": [_video_row(r, names) for r in rows], "total": total,
               "page": page, "size": size})


# ── import, link, export ─────────────────────────────────────────────────────
IMPORTERS = {"flowtest": ft_mod, "production": pr_mod, "videometry": vm_mod}
ACCEPT = {"flowtest": (".zip", ".xls", ".xlsx", ".xlsm"),
          "production": (".xlsx", ".xlsm"),
          "videometry": (".xlsx", ".xlsm", ".json")}


@bp.post("/<source>/import")
@permission_required("refdata.manage")
def import_files(source):
    if source not in IMPORTERS:
        return fail("بانک اطلاعاتی نامعتبر است.", 404)
    files = request.files.getlist("files") or request.files.getlist("file")
    if not files:
        return fail("فایلی انتخاب نشده است.", 422)
    force = request.form.get("force") in ("1", "true")
    from ..refdata.matching import WellIndex
    index = WellIndex()
    results = []
    for f in files:
        name = os.path.basename(f.filename or "file")
        if not name.lower().endswith(ACCEPT[source]):
            results.append({"file": name, "error": "نوع فایل برای این بانک پذیرفته نیست "
                            f"(مجاز: {'، '.join(ACCEPT[source])})."})
            continue
        try:
            results.append({"file": name, **IMPORTERS[source].import_bytes(
                f.read(), name, force=force, index=index)})
        except Exception as exc:  # noqa: BLE001 — report per file, keep going
            db.session.rollback()
            results.append({"file": name, "error": str(exc)[:300]})
    record_audit("import", "refdata", None,
                 summary=f"ورود {len(files)} فایل به بانک «{SOURCES[source][0]}»", commit=True)
    from ..analytics.catalogue import bump_data_version
    bump_data_version()
    return ok({"results": results}, message="ورود اطلاعات انجام شد.")


@bp.post("/relink")
@permission_required("refdata.manage")
def relink():
    """Match every row to the register again (after wells were added/renamed)."""
    from ..refdata.matching import WellIndex
    index = WellIndex()
    out = {"flowtest": ft_mod.relink(index), "production": pr_mod.relink(index),
           "videometry": vm_mod.relink(index)}
    return ok(out, message="اتصال ردیف‌ها به چاه‌های سامانه دوباره بررسی شد.")


MODELS = {"flowtest": FlowTest, "production": ProdWell, "videometry": VideoInspection}


@bp.post("/<source>/<int:row_id>/link")
@permission_required("refdata.manage")
def link(source, row_id):
    """Tie a row (and its name's other rows) to a register well by hand."""
    model = MODELS.get(source)
    if model is None:
        return fail("بانک اطلاعاتی نامعتبر است.", 404)
    row = db.session.get(model, row_id)
    if row is None:
        return fail("ردیف پیدا نشد.", 404)
    payload = body()
    from ..models import Well
    well = db.session.get(Well, int(payload.get("well_id") or 0)) if payload.get("well_id") else None
    if well is None and payload.get("well"):
        from ..services.records import resolve_well
        well, _raw = resolve_well(payload.get("well"), create_missing=False)
    if well is None and not payload.get("unlink"):
        return fail("چاه را از فهرست چاه‌های سامانه انتخاب کنید.", 422)
    if source == "flowtest":
        targets = FlowTest.query.filter_by(well_key=row.well_key).all()
    elif source == "videometry":
        targets = VideoInspection.query.filter_by(facility_code=row.facility_code).all()
    else:
        targets = [row]
    for t in targets:
        t.main_well_id = well.id if well else None
        t.match_method = "manual" if well else None
    db.session.commit()
    return ok({"linked": len(targets), "well": well.name if well else None},
              message=(f"{len(targets)} ردیف به چاه «{well.name}» وصل شد." if well
                       else "اتصال برداشته شد."))


@bp.get("/<source>/export.xlsx")
@permission_required("refdata.view")
def export(source):
    from openpyxl import Workbook
    from openpyxl.styles import Font
    wb = Workbook()
    ws = wb.active
    ws.sheet_view.rightToLeft = True
    if source == "flowtest":
        ws.title = "دبی‌سنجی"
        head = ["چاه", "اداره", "کلاسه", "چاه در سامانه", "تاریخ", "تیپ الکتروپمپ", "عمق چاه",
                "عمق نصب", "سطح ایستایی", "دبی طراحی", "آبدهی در فشار شبکه", "فشار شبکه (atm)",
                "راندمان (%)", "کارکرد", "آبدهی (l/s)", "سطح پویایی", "فشار (atm)", "هد", "آمپر"]
        ws.append(head)
        rows = FlowTest.query.order_by(FlowTest.well_key, FlowTest.test_date_num).all()
        names = _well_names(r.main_well_id for r in rows)
        for t in rows:
            base = _test_row(t, names=names)
            lead = [t.well_name, t.office, t.well_class, base["main_well"], t.test_date,
                    base["electropump"], t.well_depth, t.install_depth, t.static_level,
                    t.design_flow, t.net_flow, t.net_pressure, t.efficiency]
            if not t.points:
                ws.append(lead)
            for p in t.points:
                ws.append(lead + [p.label, p.flow, p.dynamic_level, p.pressure, p.head, p.amps])
    elif source == "production":
        ws.title = "روند تولید"
        ws.append(["کد تاسیس", "نام چاه", "چاه در سامانه", "تیپ الکتروپمپ", "سال", "ماه",
                   "تولید (m³)", "کارکرد (ساعت)", "دبی متوسط (l/s)", "فشار", "نوع فشار"])
        wells = ProdWell.query.order_by(ProdWell.facility_code).all()
        names = _well_names(w.main_well_id for w in wells)
        for w in wells:
            ep = _prod_row(w)["electropump"]
            for m in sorted(w.months, key=lambda m: (m.year, m.month)):
                ws.append([w.facility_code, w.name, names.get(w.main_well_id), ep, m.year, m.month,
                           m.production, m.hours, m.avg_flow, m.pressure, m.pressure_type])
    elif source == "videometry":
        ws.title = "ویدئومتری"
        ws.append(["کد تاسیس", "نام", "مرکز", "چاه در سامانه", "تاریخ", "عمق چاه", "سطح ایستابی",
                   "شروع مشبک", "تعداد ایراد", "توضیحات"])
        rows = VideoInspection.query.order_by(VideoInspection.facility_code,
                                              VideoInspection.insp_date_num).all()
        names = _well_names(r.main_well_id for r in rows)
        for v in rows:
            ws.append([v.facility_code, v.name, v.center, names.get(v.main_well_id), v.insp_date,
                       v.depth, v.static_level, v.screen_start, v.defect_count, v.notes])
    else:
        return fail("بانک اطلاعاتی نامعتبر است.", 404)
    for c in ws[1]:
        c.font = Font(bold=True)
    ws.freeze_panes = "A2"
    out = io.BytesIO()
    wb.save(out)
    out.seek(0)
    return send_file(out, as_attachment=True, download_name=f"refdata_{source}.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
