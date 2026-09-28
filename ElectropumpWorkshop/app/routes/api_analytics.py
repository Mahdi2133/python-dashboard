# -*- coding: utf-8 -*-
"""/api/analytics — the report builder, report access and report output.

Two kinds of caller:

* the system admin (``report.manage``) designs, tests, publishes and grants
  reports — everything under «گزارش‌ساز»;
* everyone else opens the published reports they were granted, at the levels
  they were granted, on data they could read anyway — «خروجی گزارش».

Every level is checked here, on the server, for every call; hiding a button
in the page is only a courtesy.
"""
from __future__ import annotations

import functools
import json

from flask import Blueprint, Response, current_app, request, send_file

from ..analytics import access as acc
from ..analytics.catalogue import SOURCES, TYPES, get_source
from ..analytics.engine import (AGGREGATIONS, GRANULARITY, OPERATORS, RELATIVE,
                                ReportError, Run, crosstab, detail_rows, jalali_str,
                                raw_rows, run_report, serialize_value,
                                statistics_summary)
from ..analytics.exports import FORMAT_ACCESS, render_export
from ..analytics.formula import FormulaError, compile_formula, function_help
from ..analytics.jobs import (FREQUENCIES, job_path, next_run, run_schedule,
                              start_export_job)
from ..analytics.lifecycle import (CHART_TYPES, STATUS_FLOW, definition_summary,
                                   normalise, publish, reports_depending_on,
                                   restore_as_draft, save_definition, validate)
from ..extensions import db
from ..models import AppUser, LookupCategory, LookupItem
from ..models.auth import ROLES
from ..models.report import (PRINCIPAL_KINDS, REPORT_ACCESS, REPORT_ARCHIVED,
                             REPORT_DRAFT, REPORT_PUBLISHED, REPORT_STATUSES,
                             Report, ReportCategory, ReportExportJob,
                             ReportFavorite, ReportPermission, ReportSchedule,
                             ReportSnapshot, ReportVersion, UserGroup)
from ..services.audit import record_audit
from ..services.auth import current_user, login_required
from ..services.jalali import local_now
from ._helpers import body, fail, ok

bp = Blueprint("api_analytics", __name__, url_prefix="/api/analytics")

ASYNC_ROWS = 20000          # exports of more rows than this run in the background
VIEW_LEVELS = {"view_dashboard", "view_analysis", "run"}


def manager_required(view):
    @functools.wraps(view)
    @login_required
    def wrapper(*args, **kwargs):
        if not acc.is_manager(current_user()):
            return fail("طراحی و مدیریت گزارش‌ها فقط برای مدیر سیستم است.", 403)
        return view(*args, **kwargs)
    return wrapper


def _report_or_404(report_id):
    report = db.session.get(Report, report_id)
    if report is None:
        return None, fail("گزارش پیدا نشد.", 404)
    return report, None


def _err(exc):
    return fail(str(exc), 422)


# ═══════════════════════════ builder (admin) ═══════════════════════════════
@bp.get("/meta")
@login_required
def meta():
    user = current_user()
    manager = acc.is_manager(user)
    data = {
        "is_manager": manager,
        "statuses": REPORT_STATUSES,
        "access_levels": REPORT_ACCESS,
        "categories": [c.to_dict() for c in
                       ReportCategory.query.order_by(ReportCategory.sort_order, ReportCategory.name)],
        "aggregations": [{"key": k, "label": v[0], "numeric": v[2]} for k, v in AGGREGATIONS.items()],
        "operators": [{"key": k, "label": v} for k, v in OPERATORS.items()],
        "relative": [{"key": k, "label": v} for k, v in RELATIVE.items()],
        "granularity": [{"key": k, "label": v} for k, v in GRANULARITY.items()],
        "chart_types": [{"key": k, "label": v[0], "family": v[1]} for k, v in CHART_TYPES.items()],
    }
    if manager:
        data.update({
            "sources": [s.to_dict() for s in SOURCES.values()],
            "types": TYPES,
            "functions": function_help(),
            "principal_kinds": PRINCIPAL_KINDS,
            "frequencies": FREQUENCIES,
        })
    return ok(data)


@bp.get("/sources/<key>/fields")
@manager_required
def source_fields(key):
    source = get_source(key)
    if source is None:
        return fail("منبع داده پیدا نشد.", 404)
    return ok({"source": source.to_dict(), "fields": source.fields()})


def _distinct_values(source, field_key, scope=None, q=None, limit=300, definition=None):
    fmap = source.field_map()
    f = fmap.get(field_key)
    rows = None
    if f is None:
        # a calculated field of the report: its values come from running it
        calc = next((c for c in (definition or {}).get("calcs") or [] if c.get("key") == field_key), None)
        if calc is None:
            return []
        try:
            rows = Run({"source": source.key, "calcs": definition.get("calcs")}, scope=scope).rows
        except (ReportError, FormulaError):
            return []
        f = {}
    if f.get("options"):
        vals = list(f["options"])
    else:
        seen = []
        marks = set()
        for r in (rows if rows is not None else source.rows(scope)):
            v = r.get(field_key)
            for x in (v if isinstance(v, list) else [v]):
                if x in (None, ""):
                    continue
                x = serialize_value(x)
                if x not in marks:
                    marks.add(x)
                    seen.append(x)
            if len(seen) > 5000:
                break
        try:
            vals = sorted(seen)
        except TypeError:
            vals = sorted(seen, key=str)
    if q:
        vals = [v for v in vals if str(q) in str(v)]
    return vals[:limit]


@bp.get("/sources/<key>/values/<field>")
@manager_required
def source_values(key, field):
    source = get_source(key)
    if source is None:
        return fail("منبع داده پیدا نشد.", 404)
    return ok(_distinct_values(source, field, q=request.args.get("q")))


@bp.get("/reports")
@manager_required
def list_reports():
    q = Report.query
    status = request.args.get("status")
    if status:
        q = q.filter(Report.status == status)
    return ok([r.to_dict() for r in q.order_by(Report.updated_at.desc()).all()])


def _apply_meta(report, data):
    if "name" in data:
        name = (data.get("name") or "").strip()
        if not name:
            raise ValueError("نام گزارش خالی است.")
        report.name = name[:200]
    if "description" in data:
        report.description = (data.get("description") or "").strip() or None
    if "category_id" in data:
        cid = data.get("category_id")
        report.category_id = int(cid) if cid not in (None, "", 0, "0") else None
    if "scope_to_centers" in data:
        report.scope_to_centers = bool(data.get("scope_to_centers"))


@bp.post("/reports")
@manager_required
def create_report():
    data = body()
    user = current_user()
    report = Report(name="گزارش جدید", created_by=user.id, status=REPORT_DRAFT)
    try:
        _apply_meta(report, data)
    except ValueError as exc:
        return _err(exc)
    db.session.add(report)
    db.session.flush()
    save_definition(report, data.get("definition") or {"source": data.get("source") or "records"},
                    user, note="ایجاد گزارش")
    record_audit("create", "report", report.id, summary=f"ساخت گزارش «{report.name}»")
    db.session.commit()
    return ok(_full(report))


def _full(report):
    data = report.to_dict(brief=False)
    latest = report.latest_version
    data["definition"] = normalise(latest.definition) if latest else normalise({})
    data["version_id"] = latest.id if latest else None
    data["version_frozen"] = bool(latest and latest.frozen)
    data["permissions"] = [dict(p.to_dict(), label=acc.principal_label(p.principal_kind, p.principal))
                           for p in report.permissions]
    data["schedules"] = [s.to_dict() for s in
                         ReportSchedule.query.filter_by(report_id=report.id).all()]
    return data


@bp.get("/reports/<int:report_id>")
@manager_required
def get_report(report_id):
    report, err = _report_or_404(report_id)
    if err:
        return err
    return ok(_full(report))


@bp.put("/reports/<int:report_id>")
@manager_required
def update_report(report_id):
    report, err = _report_or_404(report_id)
    if err:
        return err
    data = body()
    try:
        _apply_meta(report, data)
    except ValueError as exc:
        return _err(exc)
    if "definition" in data:
        v = save_definition(report, data["definition"] or {}, current_user(), note=data.get("note"))
        record_audit("update", "report", report.id,
                     summary=f"ذخیره‌ی گزارش «{report.name}» (نسخه {v.number})")
    else:
        record_audit("update", "report", report.id, summary=f"ویرایش مشخصات «{report.name}»")
    report.updated_at = local_now()
    db.session.commit()
    return ok(_full(report))


@bp.delete("/reports/<int:report_id>")
@manager_required
def delete_report(report_id):
    report, err = _report_or_404(report_id)
    if err:
        return err
    name = report.name
    ReportFavorite.query.filter_by(report_id=report.id).delete()
    ReportSnapshot.query.filter_by(report_id=report.id).delete()
    ReportSchedule.query.filter_by(report_id=report.id).delete()
    ReportExportJob.query.filter_by(report_id=report.id).delete()
    db.session.delete(report)
    record_audit("delete", "report", report_id, summary=f"حذف گزارش «{name}»")
    db.session.commit()
    return ok()


@bp.post("/reports/<int:report_id>/duplicate")
@manager_required
def duplicate_report(report_id):
    report, err = _report_or_404(report_id)
    if err:
        return err
    user = current_user()
    copy = Report(name=f"{report.name} (کپی)", description=report.description,
                  category_id=report.category_id, scope_to_centers=report.scope_to_centers,
                  created_by=user.id, status=REPORT_DRAFT)
    db.session.add(copy)
    db.session.flush()
    save_definition(copy, report.latest_version.definition if report.latest_version else {},
                    user, note=f"کپی از «{report.name}»")
    acc.set_permissions(copy, [p.to_dict() for p in report.permissions])
    record_audit("create", "report", copy.id, summary=f"کپی گزارش «{report.name}»")
    db.session.commit()
    return ok(_full(copy))


@bp.post("/preview")
@manager_required
def preview():
    data = body()
    definition = normalise(data.get("definition") or {})
    try:
        res = run_report(definition, extra_filter=_interactive_tree(definition, data.get("filters")),
                         drill=data.get("drill"))
    except (ReportError, FormulaError) as exc:
        return _err(exc)
    return ok(res)


@bp.post("/formula/validate")
@manager_required
def formula_validate():
    data = body()
    source = get_source(data.get("source") or "")
    if source is None:
        return fail("منبع داده انتخاب نشده است.", 422)
    fields = source.field_map()
    for c in data.get("calcs") or []:
        if c.get("key") and c.get("key") != data.get("key"):
            fields[c["key"]] = {"key": c["key"], "label": c.get("label") or c["key"]}
    try:
        comp = compile_formula(data.get("formula") or "", fields)
    except FormulaError as exc:
        return ok({"valid": False, "error": str(exc)})
    sample = None
    try:
        from ..analytics.formula import Evaluator
        rows = source.rows()[:500]
        ev = Evaluator(fields)
        if comp["kind"] == "group":
            sample = serialize_value(ev.group(comp["tree"], rows))
        else:
            for row in rows:
                try:
                    v = ev.row(comp["tree"], row)
                except Exception:  # noqa: BLE001
                    continue
                if v not in (None, ""):
                    sample = serialize_value(v)
                    break
    except Exception:  # noqa: BLE001
        sample = None
    return ok({"valid": True, "kind": comp["kind"],
               "kind_label": "تجمیعی (روی گروه)" if comp["kind"] == "group" else "سطری (روی هر ردیف)",
               "refs": sorted(comp["refs"]), "sample": sample})


@bp.post("/validate")
@manager_required
def validate_definition():
    data = body()
    report = db.session.get(Report, int(data["report_id"])) if data.get("report_id") else None
    return ok(validate(data.get("definition") or {}, report))


@bp.post("/reports/<int:report_id>/status")
@manager_required
def change_status(report_id):
    report, err = _report_or_404(report_id)
    if err:
        return err
    target = body().get("status")
    if target not in REPORT_STATUSES:
        return fail("وضعیت نامعتبر است.", 422)
    if target == report.status:
        return ok(_full(report))
    if target not in STATUS_FLOW.get(report.status, set()):
        return fail(f"از «{REPORT_STATUSES[report.status]}» نمی‌توان به "
                    f"«{REPORT_STATUSES[target]}» رفت.", 422)
    if target == REPORT_PUBLISHED:
        return _publish_version(report, report.latest_version)
    if target == REPORT_ARCHIVED:
        report.status = REPORT_ARCHIVED
    else:
        report.status = target
        # a report pulled back from publication is no longer anyone's to open
        if report.published_version_id and target == REPORT_DRAFT:
            pass
    record_audit("update", "report", report.id,
                 summary=f"وضعیت «{report.name}» → {REPORT_STATUSES[target]}")
    db.session.commit()
    return ok(_full(report))


def _publish_version(report, version):
    if version is None:
        return fail("این گزارش هنوز نسخه‌ای ندارد.", 422)
    check = validate(version.definition, report)
    if not check["ok"]:
        return fail("گزارش پیش از انتشار باید همه‌ی بررسی‌ها را بگذراند.", 422, validation=check)
    publish(report, version)
    record_audit("publish", "report", report.id,
                 summary=f"انتشار «{report.name}» — نسخه {version.number}")
    db.session.commit()
    return ok(dict(_full(report), validation=check))


@bp.post("/reports/<int:report_id>/publish")
@manager_required
def publish_report(report_id):
    report, err = _report_or_404(report_id)
    if err:
        return err
    return _publish_version(report, report.latest_version)


@bp.get("/reports/<int:report_id>/versions")
@manager_required
def versions(report_id):
    report, err = _report_or_404(report_id)
    if err:
        return err
    return ok([v.to_dict(brief=True) for v in reversed(report.versions)])


def _version(report, version_id):
    v = db.session.get(ReportVersion, version_id)
    return v if v is not None and v.report_id == report.id else None


@bp.get("/reports/<int:report_id>/versions/<int:version_id>")
@manager_required
def version_detail(report_id, version_id):
    report, err = _report_or_404(report_id)
    if err:
        return err
    v = _version(report, version_id)
    if v is None:
        return fail("نسخه پیدا نشد.", 404)
    return ok(dict(v.to_dict(), summary=definition_summary(report, v)))


@bp.post("/reports/<int:report_id>/versions/<int:version_id>/restore")
@manager_required
def version_restore(report_id, version_id):
    report, err = _report_or_404(report_id)
    if err:
        return err
    v = _version(report, version_id)
    if v is None:
        return fail("نسخه پیدا نشد.", 404)
    new = restore_as_draft(report, v, current_user())
    record_audit("update", "report", report.id,
                 summary=f"بازگردانی نسخه {v.number} «{report.name}» به نسخه‌ی کاری {new.number}")
    db.session.commit()
    return ok(_full(report))


@bp.post("/reports/<int:report_id>/versions/<int:version_id>/activate")
@manager_required
def version_activate(report_id, version_id):
    """Publish an earlier version again (rollback)."""
    report, err = _report_or_404(report_id)
    if err:
        return err
    v = _version(report, version_id)
    if v is None:
        return fail("نسخه پیدا نشد.", 404)
    return _publish_version(report, v)


# ── access ──
@bp.get("/reports/<int:report_id>/permissions")
@manager_required
def get_permissions(report_id):
    report, err = _report_or_404(report_id)
    if err:
        return err
    return ok([dict(p.to_dict(), label=acc.principal_label(p.principal_kind, p.principal))
               for p in report.permissions])


@bp.put("/reports/<int:report_id>/permissions")
@manager_required
def put_permissions(report_id):
    report, err = _report_or_404(report_id)
    if err:
        return err
    rows = body().get("permissions") or []
    clean = acc.set_permissions(report, rows)
    record_audit("permission", "report", report.id,
                 summary=f"دسترسی‌های «{report.name}» ({len(clean)} ردیف)",
                 details=[{"kind": k, "principal": p, "access": a} for k, p, a in clean])
    db.session.commit()
    db.session.refresh(report)
    return ok([dict(p.to_dict(), label=acc.principal_label(p.principal_kind, p.principal))
               for p in report.permissions])


@bp.get("/principals")
@manager_required
def principals():
    cat = LookupCategory.query.filter_by(code="center").first()
    centers = (LookupItem.query.filter_by(category_id=cat.id).order_by(LookupItem.sort_order, LookupItem.label).all()
               if cat else [])
    return ok({
        "users": [{"id": u.id, "name": u.full_name, "username": u.username, "role": u.role,
                   "is_active": u.is_active}
                  for u in sorted(AppUser.query.all(), key=lambda u: u.full_name or "")],
        "roles": [{"key": k, "label": v["label"]} for k, v in ROLES.items()],
        "centers": [{"id": c.id, "label": c.label} for c in centers if c.is_active],
        "groups": [g.to_dict() for g in UserGroup.query.order_by(UserGroup.name).all()],
        "kinds": PRINCIPAL_KINDS, "levels": REPORT_ACCESS,
    })


@bp.get("/access/principal")
@manager_required
def access_of_principal():
    kind, principal = request.args.get("kind"), str(request.args.get("principal") or "")
    if kind not in PRINCIPAL_KINDS or not principal:
        return fail("نوع و شناسه‌ی گیرنده‌ی دسترسی لازم است.", 422)
    grants = {p.report_id: p.access for p in
              ReportPermission.query.filter_by(principal_kind=kind, principal=principal)}
    out = []
    for r in Report.query.order_by(Report.name).all():
        out.append({"id": r.id, "name": r.name, "status": r.status,
                    "status_label": REPORT_STATUSES.get(r.status),
                    "category": r.category.name if r.category else None,
                    "access": grants.get(r.id, [])})
    # for a single user: what they finally get, through every role/مرکز/group
    effective = None
    if kind == "user" and principal.isdigit():
        u = db.session.get(AppUser, int(principal))
        if u is not None:
            effective = {r.id: sorted(acc.access_for(u, r)) for r in Report.query.all()}
    return ok({"reports": out, "effective": effective})


@bp.put("/access/principal")
@manager_required
def set_access_of_principal():
    data = body()
    kind, principal = data.get("kind"), str(data.get("principal") or "")
    if kind not in PRINCIPAL_KINDS or not principal:
        return fail("نوع و شناسه‌ی گیرنده‌ی دسترسی لازم است.", 422)
    grants = data.get("grants") or {}
    changed = 0
    for rid, levels in grants.items():
        report = db.session.get(Report, int(rid))
        if report is None:
            continue
        levels = [a for a in levels or [] if a in REPORT_ACCESS]
        row = ReportPermission.query.filter_by(report_id=report.id, principal_kind=kind,
                                               principal=principal).first()
        if not levels:
            if row is not None:
                db.session.delete(row)
                changed += 1
            continue
        if row is None:
            row = ReportPermission(report_id=report.id, principal_kind=kind, principal=principal)
            db.session.add(row)
        row.access = levels
        changed += 1
    record_audit("permission", "report", None,
                 summary=f"دسترسی گزارش‌ها برای {PRINCIPAL_KINDS[kind]} "
                         f"«{acc.principal_label(kind, principal)}» ({changed} گزارش)")
    db.session.commit()
    return ok({"changed": changed})


# ── categories ──
@bp.get("/categories")
@login_required
def categories():
    return ok([c.to_dict() for c in
               ReportCategory.query.order_by(ReportCategory.sort_order, ReportCategory.name)])


@bp.post("/categories")
@manager_required
def create_category():
    name = (body().get("name") or "").strip()
    if not name:
        return fail("نام دسته خالی است.", 422)
    if ReportCategory.query.filter_by(name=name).first():
        return fail("این دسته از قبل هست.", 422)
    c = ReportCategory(name=name[:120], sort_order=ReportCategory.query.count())
    db.session.add(c)
    db.session.commit()
    return ok(c.to_dict())


@bp.put("/categories/<int:cid>")
@manager_required
def update_category(cid):
    c = db.session.get(ReportCategory, cid)
    if c is None:
        return fail("دسته پیدا نشد.", 404)
    data = body()
    if data.get("name"):
        c.name = data["name"].strip()[:120]
    if "sort_order" in data:
        c.sort_order = int(data.get("sort_order") or 0)
    db.session.commit()
    return ok(c.to_dict())


@bp.delete("/categories/<int:cid>")
@manager_required
def delete_category(cid):
    c = db.session.get(ReportCategory, cid)
    if c is None:
        return fail("دسته پیدا نشد.", 404)
    Report.query.filter_by(category_id=cid).update({"category_id": None})
    db.session.delete(c)
    db.session.commit()
    return ok()


# ── user groups ──
@bp.get("/groups")
@manager_required
def groups():
    return ok([g.to_dict() for g in UserGroup.query.order_by(UserGroup.name).all()])


def _save_group(g, data):
    if "name" in data:
        name = (data.get("name") or "").strip()
        if not name:
            raise ValueError("نام گروه خالی است.")
        dup = UserGroup.query.filter(UserGroup.name == name, UserGroup.id != (g.id or 0)).first()
        if dup:
            raise ValueError("گروهی با این نام هست.")
        g.name = name[:120]
    if "description" in data:
        g.description = (data.get("description") or "").strip()[:300] or None
    if "member_ids" in data:
        ids = [int(i) for i in data.get("member_ids") or [] if str(i).isdigit()]
        g.members = AppUser.query.filter(AppUser.id.in_(ids)).all() if ids else []


@bp.post("/groups")
@manager_required
def create_group():
    g = UserGroup(name="")
    try:
        _save_group(g, body())
    except ValueError as exc:
        return _err(exc)
    if not g.name:
        return fail("نام گروه خالی است.", 422)
    db.session.add(g)
    record_audit("create", "user_group", None, summary=f"گروه کاربری «{g.name}»")
    db.session.commit()
    return ok(g.to_dict())


@bp.put("/groups/<int:gid>")
@manager_required
def update_group(gid):
    g = db.session.get(UserGroup, gid)
    if g is None:
        return fail("گروه پیدا نشد.", 404)
    try:
        _save_group(g, body())
    except ValueError as exc:
        return _err(exc)
    record_audit("update", "user_group", gid, summary=f"گروه کاربری «{g.name}»")
    db.session.commit()
    return ok(g.to_dict())


@bp.delete("/groups/<int:gid>")
@manager_required
def delete_group(gid):
    g = db.session.get(UserGroup, gid)
    if g is None:
        return fail("گروه پیدا نشد.", 404)
    ReportPermission.query.filter_by(principal_kind="group", principal=str(gid)).delete()
    db.session.delete(g)
    record_audit("delete", "user_group", gid, summary=f"حذف گروه «{g.name}»")
    db.session.commit()
    return ok()


# ── schedules ──
@bp.post("/reports/<int:report_id>/schedules")
@manager_required
def create_schedule(report_id):
    report, err = _report_or_404(report_id)
    if err:
        return err
    data = body()
    freq = data.get("frequency") or "daily"
    if freq not in FREQUENCIES:
        return fail("دوره‌ی اجرا نامعتبر است.", 422)
    s = ReportSchedule(report_id=report.id, frequency=freq, hour=int(data.get("hour") or 7),
                       is_active=bool(data.get("is_active", True)),
                       recipients_json=json.dumps(data.get("recipients") or [], ensure_ascii=False),
                       created_by=current_user().id)
    s.next_run_at = next_run(s.frequency, s.hour)
    db.session.add(s)
    record_audit("create", "report_schedule", None,
                 summary=f"زمان‌بندی {FREQUENCIES[freq]} برای «{report.name}»")
    db.session.commit()
    return ok(s.to_dict())


@bp.put("/schedules/<int:sid>")
@manager_required
def update_schedule(sid):
    s = db.session.get(ReportSchedule, sid)
    if s is None:
        return fail("زمان‌بندی پیدا نشد.", 404)
    data = body()
    if data.get("frequency") in FREQUENCIES:
        s.frequency = data["frequency"]
    if "hour" in data:
        s.hour = int(data.get("hour") or 0)
    if "is_active" in data:
        s.is_active = bool(data["is_active"])
    if "recipients" in data:
        s.recipients_json = json.dumps(data.get("recipients") or [], ensure_ascii=False)
    s.next_run_at = next_run(s.frequency, s.hour)
    db.session.commit()
    return ok(s.to_dict())


@bp.delete("/schedules/<int:sid>")
@manager_required
def delete_schedule(sid):
    s = db.session.get(ReportSchedule, sid)
    if s is None:
        return fail("زمان‌بندی پیدا نشد.", 404)
    db.session.delete(s)
    db.session.commit()
    return ok()


@bp.post("/schedules/<int:sid>/run")
@manager_required
def run_schedule_now(sid):
    s = db.session.get(ReportSchedule, sid)
    if s is None:
        return fail("زمان‌بندی پیدا نشد.", 404)
    status = run_schedule(s)
    db.session.commit()
    return ok(dict(s.to_dict(), message=status))


# ── dependencies ──
@bp.get("/dependencies")
@login_required
def dependencies():
    """Which reports read a field, form, stage or process — asked by the form
    builder and the process builder before a change that would break them."""
    user = current_user()
    if not (acc.is_manager(user) or user.can("form.manage") or user.can("workflow.manage")):
        return fail("شما مجوز دسترسی به این بخش را ندارید.", 403)
    kind, ref = request.args.get("kind"), request.args.get("ref")
    if not kind or ref in (None, ""):
        return fail("نوع و شناسه لازم است.", 422)
    refs = [r for r in str(ref).split(",") if r]
    out, seen = [], set()
    for r in refs:
        for rep in reports_depending_on(kind, r):
            if rep["id"] not in seen:
                seen.add(rep["id"])
                out.append(rep)
    return ok(out)


# ═══════════════════════════ output (viewers) ══════════════════════════════
def _levels(report):
    return acc.access_for(current_user(), report)


def _viewer_report(report_id, need=None):
    """The report and this user's levels, or an error response."""
    report = db.session.get(Report, report_id)
    user = current_user()
    if report is None:
        return None, None, fail("گزارش پیدا نشد.", 404)
    levels = acc.access_for(user, report)
    if not (levels & VIEW_LEVELS):
        return None, None, fail("این گزارش برای شما در دسترس نیست.", 403)
    if need:
        needs = need if isinstance(need, (set, tuple, list)) else {need}
        if not (levels & set(needs)):
            return None, None, fail("این سطح از گزارش برای شما باز نیست.", 403)
    return report, levels, None


def _version_for(report, data):
    """The published version — or, for the admin testing, the working one."""
    user = current_user()
    if acc.is_manager(user):
        if data.get("version_id"):
            v = db.session.get(ReportVersion, int(data["version_id"]))
            if v is not None and v.report_id == report.id:
                return v
        if data.get("draft") or report.published_version is None:
            return report.latest_version
    return report.published_version


def _interactive_tree(definition, values):
    """The viewer's picks in the report's own filter controls → a filter tree.

    Only the controls the report defines are honoured: a viewer cannot filter
    on a field the designer did not offer.
    """
    values = values or {}
    items = []
    for f in definition.get("interactive_filters") or []:
        key = f.get("field")
        if not key:
            continue
        v = values.get(f.get("id") or key, values.get(key))
        if v in (None, "", [], {}):
            continue
        kind = f.get("kind") or "select"
        if kind == "multi":
            vals = v if isinstance(v, list) else [v]
            items.append({"field": key, "operator": "in", "value": vals})
        elif kind == "date_range" and isinstance(v, dict):
            if v.get("relative"):
                items.append({"field": key, "operator": "relative", "value": v["relative"]})
            elif v.get("from") or v.get("to"):
                items.append({"field": key, "operator": "date_between",
                              "value": v.get("from") or None, "value2": v.get("to") or None})
        elif kind == "number_range" and isinstance(v, dict):
            if v.get("min") not in (None, "") or v.get("max") not in (None, ""):
                items.append({"field": key, "operator": "between",
                              "value": v.get("min"), "value2": v.get("max")})
        elif kind == "text":
            items.append({"field": key, "operator": "contains", "value": str(v)})
        else:
            items.append({"field": key, "operator": "in" if isinstance(v, list) else "eq",
                          "value": v})
    return {"op": "and", "items": items} if items else None


def _filter_texts(definition, values, summary=None):
    labels = {}
    source = get_source(definition.get("source") or "")
    fmap = source.field_map() if source else {}
    out = list((summary or {}).get("filters") or [])
    for f in definition.get("interactive_filters") or []:
        key = f.get("field")
        v = (values or {}).get(f.get("id") or key, (values or {}).get(key))
        if v in (None, "", [], {}):
            continue
        label = f.get("label") or fmap.get(key, {}).get("label", key)
        if isinstance(v, dict):
            if v.get("relative"):
                text = RELATIVE.get(v["relative"], v["relative"])
            else:
                parts = [f"از {v.get('from') or v.get('min')}" if (v.get("from") or v.get("min") not in (None, "")) else "",
                         f"تا {v.get('to') or v.get('max')}" if (v.get("to") or v.get("max") not in (None, "")) else ""]
                text = " ".join(p for p in parts if p)
        elif isinstance(v, list):
            text = "، ".join(map(str, v))
        else:
            text = str(v)
        labels[key] = text
        out.append(f"«{label}»: {text}")
    return out


def _prepare_run(report, levels, data):
    version = _version_for(report, data)
    if version is None:
        raise ReportError("این گزارش نسخه‌ی منتشرشده ندارد.")
    definition = normalise(version.definition)
    values = data.get("filters") or {}
    if values and "filter" not in levels:
        values = {}
    drill = data.get("drill")
    if drill and "drilldown" not in levels:
        drill = None
    scope = acc.scope_for(current_user(), report)
    return version, definition, values, drill, scope


def _view_config(report, version, levels):
    d = normalise(version.definition) if version else normalise({})
    source = get_source(d.get("source") or "")
    fmap = source.field_map() if source else {}
    filters = []
    for f in d.get("interactive_filters") or []:
        fd = fmap.get(f.get("field")) or {}
        item = dict(f, label=f.get("label") or fd.get("label") or f.get("field"),
                    type=fd.get("type"))
        if (f.get("kind") or "select") in ("select", "multi") and source is not None:
            item["options"] = _distinct_values(source, f.get("field"),
                                               acc.scope_for(current_user(), report), limit=400,
                                               definition=d)
        filters.append(item)
    field_labels = {k: v.get("label") for k, v in fmap.items()}
    for c in d.get("calcs") or []:
        field_labels[c.get("key")] = c.get("label") or c.get("key")
    return {
        "report": report.to_dict(),
        "version": version.number if version else None,
        "version_id": version.id if version else None,
        "levels": sorted(levels),
        "layout": d.get("layout"), "kpis": d.get("kpis"), "charts": d.get("charts"),
        "tables": d.get("tables"), "rules": d.get("rules"),
        "interactive_filters": filters,
        "drill": d.get("drill"), "analysis": d.get("analysis"),
        "export": d.get("export"), "theme": d.get("theme"),
        "fields": [{"key": k, "label": v.get("label"), "type": v.get("type"), "group": v.get("group")}
                   for k, v in fmap.items() if not k.startswith("_center")],
        "field_labels": field_labels,
        "measures": d.get("measures"), "groups": d.get("groups"),
        "source_label": source.label if source else None,
    }


@bp.get("/catalog")
@login_required
def catalog():
    user = current_user()
    manager = acc.is_manager(user)
    favs = {f.report_id for f in ReportFavorite.query.filter_by(user_id=user.id)}
    items = []
    if manager:
        reports = [(r, acc.ALL_ACCESS) for r in Report.query.filter(
            Report.status == REPORT_PUBLISHED).all()]
    else:
        if not user.can("report.view"):
            return ok({"reports": [], "categories": [], "is_manager": False})
        reports = acc.visible_reports(user)
    for r, levels in reports:
        d = r.to_dict()
        d["levels"] = sorted(levels)
        d["favorite"] = r.id in favs
        items.append(d)
    order = {c.id: (c.sort_order, c.name) for c in ReportCategory.query.all()}
    items.sort(key=lambda x: (not x["favorite"], order.get(x.get("category_id"), (999, "")), x["name"]))
    return ok({"reports": items, "is_manager": manager,
               "categories": [c.to_dict() for c in ReportCategory.query.order_by(
                   ReportCategory.sort_order, ReportCategory.name)]})


@bp.post("/reports/<int:report_id>/favorite")
@login_required
def toggle_favorite(report_id):
    report, _levels_, err = _viewer_report(report_id)
    if err:
        return err
    user = current_user()
    row = ReportFavorite.query.filter_by(report_id=report.id, user_id=user.id).first()
    if row:
        db.session.delete(row)
        fav = False
    else:
        db.session.add(ReportFavorite(report_id=report.id, user_id=user.id))
        fav = True
    db.session.commit()
    return ok({"favorite": fav})


@bp.get("/reports/<int:report_id>/view")
@login_required
def view_report(report_id):
    report, levels, err = _viewer_report(report_id)
    if err:
        return err
    version = _version_for(report, request.args)
    if version is None:
        return fail("این گزارش نسخه‌ی منتشرشده ندارد.", 404)
    record_audit("view", "report", report.id, summary=f"مشاهده‌ی گزارش «{report.name}»", commit=True)
    return ok(_view_config(report, version, levels))


@bp.post("/reports/<int:report_id>/run")
@login_required
def run(report_id):
    report, levels, err = _viewer_report(report_id, {"view_dashboard", "run"})
    if err:
        return err
    data = body()
    try:
        version, definition, values, drill, scope = _prepare_run(report, levels, data)
        res = run_report(definition, scope=scope,
                         extra_filter=_interactive_tree(definition, values), drill=drill)
    except (ReportError, FormulaError) as exc:
        return _err(exc)
    res["version"] = version.number
    return ok(res)


def _analysis_run(report_id, data, need="view_analysis"):
    report, levels, err = _viewer_report(report_id, need)
    if err:
        return None, None, None, err
    try:
        version, definition, values, drill, scope = _prepare_run(report, levels, data)
        r = Run(definition, scope=scope, extra_filter=_interactive_tree(definition, values),
                drill=drill)
    except (ReportError, FormulaError) as exc:
        return None, None, None, _err(exc)
    return report, levels, r, None


@bp.post("/reports/<int:report_id>/analysis/detail")
@login_required
def analysis_detail(report_id):
    data = body()
    _report, _lv, r, err = _analysis_run(report_id, data)
    if err:
        return err
    return ok(detail_rows(r, keys=data.get("keys"), search=data.get("search"),
                          sort=data.get("sort"), page=data.get("page") or 1,
                          page_size=data.get("page_size") or 50))


@bp.post("/reports/<int:report_id>/analysis/crosstab")
@login_required
def analysis_crosstab(report_id):
    data = body()
    _report, _lv, r, err = _analysis_run(report_id, data)
    if err:
        return err
    if not data.get("row_field") or not data.get("col_field"):
        return fail("فیلد سطر و ستون را انتخاب کنید.", 422)
    for k in (data["row_field"], data["col_field"]):
        if k not in r.fields:
            return fail("فیلد انتخاب‌شده در این گزارش نیست.", 422)
    measure = data.get("measure") or {"field": "*", "agg": "count"}
    if measure.get("field") not in (None, "*") and measure["field"] not in r.fields:
        return fail("فیلد سنجه در این گزارش نیست.", 422)
    try:
        return ok(crosstab(r, data["row_field"], data["col_field"], measure,
                           data.get("row_granularity"), data.get("col_granularity")))
    except ReportError as exc:
        return _err(exc)


@bp.post("/reports/<int:report_id>/analysis/stats")
@login_required
def analysis_stats(report_id):
    data = body()
    _report, _lv, r, err = _analysis_run(report_id, data)
    if err:
        return err
    keys = [k for k in data.get("keys") or [] if k in r.fields] or None
    return ok(statistics_summary(r, keys))


@bp.post("/reports/<int:report_id>/raw")
@login_required
def raw_data(report_id):
    data = body()
    report, _lv, r, err = _analysis_run(report_id, data, need="raw_data")
    if err:
        return err
    record_audit("view", "report", report.id, summary=f"داده‌ی خام «{report.name}»", commit=True)
    return ok(raw_rows(r, page=data.get("page") or 1, page_size=data.get("page_size") or 100))


@bp.get("/reports/<int:report_id>/info")
@login_required
def report_info(report_id):
    report, _levels_, err = _viewer_report(report_id)
    if err:
        return err
    version = _version_for(report, request.args)
    info = definition_summary(report, version)
    info["published_at"] = jalali_str(report.published_at, True) if report.published_at else None
    info["scope_to_centers"] = report.scope_to_centers
    return ok(info)


@bp.get("/reports/<int:report_id>/values/<field>")
@login_required
def report_values(report_id, field):
    report, levels, err = _viewer_report(report_id, "filter")
    if err:
        return err
    version = _version_for(report, request.args)
    d = normalise(version.definition) if version else {}
    if field not in {f.get("field") for f in d.get("interactive_filters") or []}:
        return fail("این فیلتر در گزارش تعریف نشده است.", 422)
    source = get_source(d.get("source") or "")
    return ok(_distinct_values(source, field, acc.scope_for(current_user(), report),
                               q=request.args.get("q"), definition=d))


# ── exports ──
def _export_meta(report, version, user, definition, values, summary, levels, snapshot=None):
    scope = acc.scope_for(user, report)
    return {
        "name": report.name, "description": report.description,
        "category": report.category.name if report.category else None,
        "version": version.number if version else None,
        "status": report.status, "status_label": REPORT_STATUSES.get(report.status),
        "user": user.full_name, "report_id": report.id,
        "filters": _filter_texts(definition, values, summary),
        "app_title": current_app.config.get("APP_TITLE"),
        "scope": "فقط مراکز کاربر" if scope is not None else None,
        "snapshot": snapshot,
        "file_stem": f"report_{report.id}",
    }


def _attachment(payload, mimetype, filename):
    from urllib.parse import quote
    return Response(payload, mimetype=mimetype, headers={
        "Content-Disposition": f"attachment; filename=\"{filename.encode('ascii', 'ignore').decode() or 'report'}\"; "
                               f"filename*=UTF-8''{quote(filename)}"})


def _file_name(report, ext):
    from ..services.jalali import today_jalali
    jy, jm, jd = today_jalali()
    return f"report_{report.id}_{jy}-{jm:02d}-{jd:02d}.{ext}"


@bp.post("/reports/<int:report_id>/export/<fmt>")
@login_required
def export(report_id, fmt):
    fmt = (fmt or "").lower()
    level = FORMAT_ACCESS.get(fmt)
    if level is None:
        return fail("قالب خروجی پشتیبانی نمی‌شود.", 422)
    report, levels, err = _viewer_report(report_id, level)
    if err:
        return err
    user = current_user()
    data = body()
    try:
        version, definition, values, drill, scope = _prepare_run(report, levels, data)
    except ReportError as exc:
        return _err(exc)
    include_raw = bool(data.get("include_raw")) and "raw_data" in levels
    include_analysis = bool(data.get("include_analysis")) and "view_analysis" in levels
    images = data.get("chart_images") or {}
    summary = definition_summary(report, version)
    meta = _export_meta(report, version, user, definition, values, summary, levels)
    tree = _interactive_tree(definition, values)

    def build():
        r = Run(definition, scope=scope, extra_filter=tree, drill=drill)
        res = run_report(definition, scope=scope, extra_filter=tree, drill=drill)
        raw = raw_rows(r, 1, 200000) if include_raw else None
        extras = {"summary": summary}
        if include_analysis:
            extras["stats"] = statistics_summary(r)
        payload, mimetype, ext = render_export(fmt, meta, definition, res, raw=raw,
                                               chart_images=images, extras=extras)
        return payload, mimetype, ext, res

    audit_text = f"خروجی {fmt.upper()} از «{report.name}» (نسخه {version.number})"
    # heavy exports run in the background and wait for download
    try:
        probe = Run(definition, scope=scope, extra_filter=tree, drill=drill)
        big = len(probe.rows) > ASYNC_ROWS and fmt in ("xlsx", "pdf", "docx", "csv")
    except (ReportError, FormulaError) as exc:
        return _err(exc)
    if data.get("async") or big:
        job = ReportExportJob(report_id=report.id, user_id=user.id, fmt="html" if fmt == "print" else fmt,
                              status="queued")
        db.session.add(job)
        record_audit("export", "report", report.id, summary=audit_text + " — در صف", commit=False)
        db.session.commit()
        app = current_app._get_current_object()

        rid = report.id

        def job_build():
            payload, _m, ext, _r = build()
            from ..services.jalali import today_jalali
            jy, jm, jd = today_jalali()
            return payload, f"report_{rid}_{jy}-{jm:02d}-{jd:02d}.{ext}"
        start_export_job(app, job.id, job_build)
        return ok({"job": job.to_dict(), "async": True})
    try:
        payload, mimetype, ext, _res = build()
    except (ReportError, FormulaError, ValueError, RuntimeError) as exc:
        return _err(exc)
    except Exception as exc:  # noqa: BLE001 — an export must answer, not crash
        current_app.logger.exception("export %s of report %s failed", fmt, report.id)
        return fail(f"ساخت خروجی {fmt.upper()} ناموفق بود: {type(exc).__name__}: {exc}", 500)
    record_audit("export", "report", report.id, summary=audit_text, commit=True)
    if fmt == "print":
        return Response(payload, mimetype=mimetype)
    return _attachment(payload, mimetype, _file_name(report, ext))


@bp.get("/jobs")
@login_required
def jobs():
    user = current_user()
    rows = (ReportExportJob.query.filter_by(user_id=user.id)
            .order_by(ReportExportJob.id.desc()).limit(30).all())
    return ok([j.to_dict() for j in rows])


@bp.get("/jobs/<int:job_id>/download")
@login_required
def job_download(job_id):
    user = current_user()
    job = db.session.get(ReportExportJob, job_id)
    if job is None or (job.user_id != user.id and not acc.is_manager(user)):
        return fail("فایل پیدا نشد.", 404)
    if job.status != "done" or not job.stored_name:
        return fail("خروجی هنوز آماده نیست.", 409)
    path = job_path(job.stored_name)
    if not path.exists():
        return fail("فایل خروجی دیگر روی سرور نیست.", 410)
    from ..analytics.exports import MIMES
    return send_file(str(path), mimetype=MIMES.get(job.fmt), as_attachment=True,
                     download_name=job.file_name or path.name)


# ── snapshots ──
@bp.get("/reports/<int:report_id>/snapshots")
@login_required
def snapshots(report_id):
    report, _lv, err = _viewer_report(report_id)
    if err:
        return err
    rows = (ReportSnapshot.query.filter_by(report_id=report.id)
            .order_by(ReportSnapshot.created_at.desc()).limit(100).all())
    return ok([s.to_dict() for s in rows])


@bp.post("/reports/<int:report_id>/snapshots")
@login_required
def create_snapshot(report_id):
    report, levels, err = _viewer_report(report_id, {"view_dashboard", "run"})
    if err:
        return err
    data = body()
    try:
        version, definition, values, drill, scope = _prepare_run(report, levels, data)
        res = run_report(definition, scope=scope, extra_filter=_interactive_tree(definition, values))
    except (ReportError, FormulaError) as exc:
        return _err(exc)
    from ..services.jalali import to_jalali_str
    title = (data.get("title") or "").strip() or f"{report.name} — {to_jalali_str(local_now())}"
    snap = ReportSnapshot(report_id=report.id, version_id=version.id, title=title[:200],
                          filters_json=json.dumps({"values": values,
                                                   "texts": _filter_texts(definition, values)},
                                                  ensure_ascii=False),
                          result_json=json.dumps(res, ensure_ascii=False, default=str),
                          row_count=res.get("row_count") or 0, source="manual",
                          created_by=current_user().id)
    db.session.add(snap)
    record_audit("create", "report_snapshot", None, summary=f"Snapshot «{title}»")
    db.session.commit()
    return ok(snap.to_dict())


def _snapshot(sid):
    snap = db.session.get(ReportSnapshot, sid)
    if snap is None:
        return None, None, fail("Snapshot پیدا نشد.", 404)
    report, levels, err = _viewer_report(snap.report_id)
    if err:
        return None, None, err
    return snap, levels, None


@bp.get("/snapshots/<int:sid>")
@login_required
def get_snapshot(sid):
    snap, _lv, err = _snapshot(sid)
    if err:
        return err
    data = snap.to_dict(with_result=True)
    if snap.version is not None:
        report = db.session.get(Report, snap.report_id)
        data["config"] = _view_config(report, snap.version, _levels(report))
    return ok(data)


@bp.delete("/snapshots/<int:sid>")
@login_required
def delete_snapshot(sid):
    snap, _lv, err = _snapshot(sid)
    if err:
        return err
    user = current_user()
    if snap.created_by != user.id and not acc.is_manager(user):
        return fail("فقط سازنده‌ی Snapshot یا مدیر سیستم می‌تواند آن را حذف کند.", 403)
    db.session.delete(snap)
    db.session.commit()
    return ok()


@bp.post("/snapshots/<int:sid>/export/<fmt>")
@login_required
def export_snapshot(sid, fmt):
    fmt = (fmt or "").lower()
    snap, levels, err = _snapshot(sid)
    if err:
        return err
    level = FORMAT_ACCESS.get(fmt)
    if level is None or level not in levels:
        return fail("این قالب خروجی برای شما باز نیست.", 403)
    report = db.session.get(Report, snap.report_id)
    version = snap.version
    definition = normalise(version.definition) if version else {}
    filters = json.loads(snap.filters_json or "{}")
    summary = definition_summary(report, version) if version else {}
    meta = _export_meta(report, version, current_user(), definition, filters.get("values") or {},
                        summary, levels, snapshot=f"{snap.title} — {jalali_str(snap.created_at, True)}")
    result = json.loads(snap.result_json or "{}")
    try:
        payload, mimetype, ext = render_export(fmt, meta, definition, result,
                                               chart_images=body().get("chart_images"),
                                               extras={"summary": summary})
    except (ValueError, RuntimeError) as exc:
        return _err(exc)
    record_audit("export", "report_snapshot", snap.id,
                 summary=f"خروجی {fmt.upper()} از Snapshot «{snap.title}»", commit=True)
    if fmt == "print":
        return Response(payload, mimetype=mimetype)
    return _attachment(payload, mimetype, _file_name(report, ext))
