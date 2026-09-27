# -*- coding: utf-8 -*-
"""Who may see which report, and never more than the data itself allows.

Two gates, both checked on the server for every call:

1. the report: a principal row (user, role, مرکز or group) granting this
   person the level they ask for — dashboard, analysis, raw data, one export
   format, print;
2. the data: the source's own base permission — records need record.view,
   processes workflow.view, users user.manage. A report grant never opens data
   the person could not read directly.

Designing, publishing and granting reports is the system admin's alone
(report.manage). Optionally a report reads only the viewer's مراکز.
"""
from __future__ import annotations

from ..models.report import (REPORT_ACCESS, REPORT_PUBLISHED, Report,
                             ReportPermission, UserGroup)
from .catalogue import get_source

ALL_ACCESS = set(REPORT_ACCESS)


def is_manager(user) -> bool:
    return user is not None and (user.role == "admin" or user.can("report.manage"))


def principals_of(user) -> set:
    out = {("user", str(user.id)), ("role", user.role)}
    for c in getattr(user, "centers", []) or []:
        out.add(("center", str(c.id)))
    for g in UserGroup.query.all():
        if any(m.id == user.id for m in g.members):
            out.add(("group", str(g.id)))
    return out


def access_for(user, report: Report) -> set:
    """The levels this user has on this report (empty: cannot see it)."""
    if user is None or report is None:
        return set()
    if is_manager(user):
        return set(ALL_ACCESS)
    if report.status != REPORT_PUBLISHED or report.published_version is None:
        return set()
    mine = principals_of(user)
    levels = set()
    for p in report.permissions:
        if (p.principal_kind, str(p.principal)) in mine:
            levels.update(p.access)
    if not levels:
        return set()
    # the data gate: a grant is worth nothing on data the person cannot read
    source = get_source((report.published_version.definition or {}).get("source") or "")
    if source is None or not source.allowed_for(user):
        return set()
    return levels


def can(user, report, level: str) -> bool:
    return level in access_for(user, report)


def scope_for(user, report: Report):
    """The مرکز ids this viewer's rows are limited to, or None for all."""
    if report is None or not report.scope_to_centers or is_manager(user):
        return None
    return [c.id for c in getattr(user, "centers", []) or []]


def visible_reports(user) -> list:
    """Published reports this user may open, with their levels."""
    out = []
    reports = Report.query.filter(Report.status == REPORT_PUBLISHED).all()
    for r in reports:
        levels = access_for(user, r)
        if levels & {"view_dashboard", "view_analysis", "run"}:
            out.append((r, levels))
    return out


def principal_label(kind, principal, lookups=None):
    from ..models import AppUser, LookupItem
    from ..models.auth import ROLES
    if kind == "user":
        u = AppUser.query.get(int(principal)) if str(principal).isdigit() else None
        return u.full_name if u else f"کاربر #{principal}"
    if kind == "role":
        return ROLES.get(principal, {}).get("label", principal)
    if kind == "center":
        c = LookupItem.query.get(int(principal)) if str(principal).isdigit() else None
        return c.label if c else f"مرکز #{principal}"
    if kind == "group":
        g = UserGroup.query.get(int(principal)) if str(principal).isdigit() else None
        return g.name if g else f"گروه #{principal}"
    return str(principal)


def set_permissions(report: Report, rows: list):
    """Replace a report's grants with ``rows`` [{principal_kind, principal, access}]."""
    from ..models.report import PRINCIPAL_KINDS
    from ..extensions import db
    clean = []
    seen = set()
    for r in rows or []:
        kind = r.get("principal_kind")
        principal = str(r.get("principal") or "").strip()
        if kind not in PRINCIPAL_KINDS or not principal:
            continue
        access = [a for a in r.get("access") or [] if a in REPORT_ACCESS]
        if (kind, principal) in seen:
            continue
        seen.add((kind, principal))
        clean.append((kind, principal, access))
    ReportPermission.query.filter_by(report_id=report.id).delete()
    for kind, principal, access in clean:
        p = ReportPermission(report_id=report.id, principal_kind=kind, principal=principal)
        p.access = access
        db.session.add(p)
    return clean
