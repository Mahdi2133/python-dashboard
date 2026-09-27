# -*- coding: utf-8 -*-
"""Reports as entities: definitions, versions, access, snapshots, schedules.

A report never copies the workshop's data. It holds a *definition* — which data
source, which fields, filters, groupings, formulas, KPIs, charts, tables and
layout — and reads the live tables every time it runs. What it may keep is a
snapshot: the frozen result of one run, so «گزارش عملکرد مرداد ۱۴۰۵» still
reads the same after the data behind it moves on.

Each saved change of a published report is a new version; the definition of a
version is one JSON document so a version can be restored whole, in one step.
What has to be searched — dependencies and permissions — is kept in rows.
"""
import json

from ..extensions import db
from ..services.jalali import local_now

REPORT_DRAFT = "draft"
REPORT_TESTING = "testing"
REPORT_PUBLISHED = "published"
REPORT_ARCHIVED = "archived"
REPORT_STATUSES = {
    REPORT_DRAFT: "پیش‌نویس",
    REPORT_TESTING: "در حال آزمایش",
    REPORT_PUBLISHED: "منتشرشده",
    REPORT_ARCHIVED: "بایگانی",
}

# What a principal may do with a report it can see. Checked on the server for
# every call, not only by hiding buttons.
REPORT_ACCESS = {
    "view_dashboard": "مشاهده داشبورد",
    "view_analysis": "تحلیل تخصصی",
    "run": "اجرای گزارش",
    "filter": "اعمال فیلتر",
    "drilldown": "Drill-down",
    "raw_data": "مشاهده داده خام",
    "export_xlsx": "خروجی Excel",
    "export_pdf": "خروجی PDF",
    "export_docx": "خروجی Word",
    "export_csv": "خروجی CSV",
    "export_json": "خروجی JSON",
    "print": "چاپ",
}

PRINCIPAL_KINDS = {"user": "کاربر", "role": "نقش", "center": "مرکز (واحد)",
                   "group": "گروه کاربری"}


def _load(raw, default):
    try:
        return json.loads(raw) if raw else default
    except ValueError:
        return default


class ReportCategory(db.Model):
    __tablename__ = "report_categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)

    def to_dict(self):
        return {"id": self.id, "name": self.name, "sort_order": self.sort_order}


class Report(db.Model):
    __tablename__ = "reports"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    category_id = db.Column(db.Integer, db.ForeignKey("report_categories.id",
                                                      ondelete="SET NULL"), index=True)
    status = db.Column(db.String(12), nullable=False, default=REPORT_DRAFT, index=True)
    # The version users see. Editing never touches it: a published report is
    # changed by publishing another version.
    published_version_id = db.Column(db.Integer)
    # «فقط داده‌ی مراکز کاربر» — rows outside the viewer's مراکز are not read.
    scope_to_centers = db.Column(db.Boolean, nullable=False, default=False)
    template_key = db.Column(db.String(60))     # set when seeded from a fixed report
    created_by = db.Column(db.Integer, db.ForeignKey("app_users.id"))
    created_at = db.Column(db.DateTime, default=local_now, nullable=False)
    updated_at = db.Column(db.DateTime, default=local_now, onupdate=local_now,
                           nullable=False)
    published_at = db.Column(db.DateTime)

    category = db.relationship("ReportCategory")
    versions = db.relationship("ReportVersion", back_populates="report",
                               cascade="all, delete-orphan",
                               order_by="ReportVersion.number")
    permissions = db.relationship("ReportPermission", back_populates="report",
                                  cascade="all, delete-orphan")
    creator = db.relationship("AppUser", foreign_keys=[created_by])

    @property
    def latest_version(self):
        return self.versions[-1] if self.versions else None

    @property
    def published_version(self):
        return next((v for v in self.versions if v.id == self.published_version_id), None)

    def to_dict(self, brief=True):
        latest = self.latest_version
        pub = self.published_version
        data = {
            "id": self.id, "name": self.name, "description": self.description,
            "category_id": self.category_id,
            "category": self.category.name if self.category else None,
            "status": self.status, "status_label": REPORT_STATUSES.get(self.status, self.status),
            "scope_to_centers": self.scope_to_centers,
            "template_key": self.template_key,
            "latest_version": latest.number if latest else None,
            "published_version": pub.number if pub else None,
            "created_by": self.creator.full_name if self.creator else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "source": (latest.definition.get("source") if latest else None),
        }
        if not brief:
            data["versions"] = [v.to_dict(brief=True) for v in reversed(self.versions)]
        return data


class ReportVersion(db.Model):
    __tablename__ = "report_versions"
    __table_args__ = (db.UniqueConstraint("report_id", "number", name="uq_report_version"),)

    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.Integer, db.ForeignKey("reports.id", ondelete="CASCADE"),
                          nullable=False, index=True)
    number = db.Column(db.Integer, nullable=False)
    definition_json = db.Column(db.Text, nullable=False, default="{}")
    note = db.Column(db.String(300))
    # A version that has been published is frozen; editing it makes a new one.
    frozen = db.Column(db.Boolean, nullable=False, default=False)
    created_by = db.Column(db.Integer, db.ForeignKey("app_users.id"))
    created_at = db.Column(db.DateTime, default=local_now, nullable=False)
    updated_at = db.Column(db.DateTime, default=local_now, onupdate=local_now,
                           nullable=False)

    report = db.relationship("Report", back_populates="versions")
    creator = db.relationship("AppUser", foreign_keys=[created_by])

    @property
    def definition(self) -> dict:
        return _load(self.definition_json, {})

    @definition.setter
    def definition(self, value):
        self.definition_json = json.dumps(value or {}, ensure_ascii=False)

    def to_dict(self, brief=False):
        data = {"id": self.id, "number": self.number, "note": self.note,
                "frozen": self.frozen,
                "published": self.report is not None
                and self.report.published_version_id == self.id,
                "created_by": self.creator.full_name if self.creator else None,
                "created_at": self.created_at.isoformat() if self.created_at else None,
                "updated_at": self.updated_at.isoformat() if self.updated_at else None}
        if not brief:
            data["definition"] = self.definition
        return data


class ReportDependency(db.Model):
    """What a version reads: a field, a form, a stage, a process, a source.

    Kept as rows so the form builder and the process builder can ask «which
    reports use this?» before a field or a stage is changed or removed.
    """
    __tablename__ = "report_dependencies"

    id = db.Column(db.Integer, primary_key=True)
    version_id = db.Column(db.Integer, db.ForeignKey("report_versions.id",
                                                     ondelete="CASCADE"),
                           nullable=False, index=True)
    kind = db.Column(db.String(20), nullable=False, index=True)   # source|field|form|stage|process
    ref = db.Column(db.String(160), nullable=False, index=True)


class ReportPermission(db.Model):
    __tablename__ = "report_permissions"

    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.Integer, db.ForeignKey("reports.id", ondelete="CASCADE"),
                          nullable=False, index=True)
    principal_kind = db.Column(db.String(10), nullable=False)     # user|role|center|group
    principal = db.Column(db.String(80), nullable=False)          # id or role code
    access_json = db.Column(db.Text, nullable=False, default="[]")

    report = db.relationship("Report", back_populates="permissions")

    @property
    def access(self) -> list:
        return [a for a in _load(self.access_json, []) if a in REPORT_ACCESS]

    @access.setter
    def access(self, value):
        self.access_json = json.dumps([a for a in (value or []) if a in REPORT_ACCESS])

    def to_dict(self):
        return {"id": self.id, "principal_kind": self.principal_kind,
                "principal": self.principal, "access": self.access}


class ReportFavorite(db.Model):
    __tablename__ = "report_favorites"
    __table_args__ = (db.UniqueConstraint("report_id", "user_id", name="uq_report_fav"),)

    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.Integer, db.ForeignKey("reports.id", ondelete="CASCADE"),
                          nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("app_users.id", ondelete="CASCADE"),
                        nullable=False, index=True)


class ReportSnapshot(db.Model):
    """The frozen result of one run, with what produced it."""
    __tablename__ = "report_snapshots"

    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.Integer, db.ForeignKey("reports.id", ondelete="CASCADE"),
                          nullable=False, index=True)
    version_id = db.Column(db.Integer, db.ForeignKey("report_versions.id",
                                                     ondelete="SET NULL"))
    title = db.Column(db.String(200), nullable=False)
    filters_json = db.Column(db.Text)
    result_json = db.Column(db.Text, nullable=False)
    row_count = db.Column(db.Integer, nullable=False, default=0)
    created_by = db.Column(db.Integer, db.ForeignKey("app_users.id"))
    created_at = db.Column(db.DateTime, default=local_now, nullable=False, index=True)
    source = db.Column(db.String(20), nullable=False, default="manual")  # manual|schedule

    version = db.relationship("ReportVersion")
    creator = db.relationship("AppUser", foreign_keys=[created_by])

    def to_dict(self, with_result=False):
        data = {"id": self.id, "report_id": self.report_id, "title": self.title,
                "version": self.version.number if self.version else None,
                "filters": _load(self.filters_json, {}), "row_count": self.row_count,
                "created_by": self.creator.full_name if self.creator else None,
                "created_at": self.created_at.isoformat() if self.created_at else None,
                "source": self.source}
        if with_result:
            data["result"] = _load(self.result_json, {})
        return data


class ReportSchedule(db.Model):
    """Run a report on a calendar and keep the result as a snapshot.

    Sending it to people is the next step; the schedule already records who
    would receive it, so that step adds a transport, not a redesign.
    """
    __tablename__ = "report_schedules"

    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.Integer, db.ForeignKey("reports.id", ondelete="CASCADE"),
                          nullable=False, index=True)
    frequency = db.Column(db.String(12), nullable=False)          # daily|weekly|monthly|quarterly
    hour = db.Column(db.Integer, nullable=False, default=7)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    recipients_json = db.Column(db.Text)
    next_run_at = db.Column(db.DateTime, index=True)
    last_run_at = db.Column(db.DateTime)
    last_status = db.Column(db.String(200))
    created_by = db.Column(db.Integer, db.ForeignKey("app_users.id"))
    created_at = db.Column(db.DateTime, default=local_now, nullable=False)

    report = db.relationship("Report")

    def to_dict(self):
        return {"id": self.id, "report_id": self.report_id, "frequency": self.frequency,
                "hour": self.hour, "is_active": self.is_active,
                "recipients": _load(self.recipients_json, []),
                "next_run_at": self.next_run_at.isoformat() if self.next_run_at else None,
                "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
                "last_status": self.last_status}


class ReportExportJob(db.Model):
    """A heavy export made in the background; the file waits for download."""
    __tablename__ = "report_export_jobs"

    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.Integer, db.ForeignKey("reports.id", ondelete="CASCADE"),
                          nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("app_users.id"), index=True)
    fmt = db.Column(db.String(8), nullable=False)
    status = db.Column(db.String(12), nullable=False, default="queued")  # queued|running|done|failed
    message = db.Column(db.Text)
    file_name = db.Column(db.String(200))
    stored_name = db.Column(db.String(120))
    created_at = db.Column(db.DateTime, default=local_now, nullable=False)
    finished_at = db.Column(db.DateTime)

    def to_dict(self):
        return {"id": self.id, "report_id": self.report_id, "fmt": self.fmt,
                "status": self.status, "message": self.message,
                "file_name": self.file_name,
                "created_at": self.created_at.isoformat() if self.created_at else None,
                "finished_at": self.finished_at.isoformat() if self.finished_at else None}


user_group_members = db.Table(
    "user_group_members",
    db.Column("group_id", db.Integer, db.ForeignKey("user_groups.id", ondelete="CASCADE"),
              primary_key=True),
    db.Column("user_id", db.Integer, db.ForeignKey("app_users.id", ondelete="CASCADE"),
              primary_key=True),
)


class UserGroup(db.Model):
    """A named set of users, for granting reports to several people at once."""
    __tablename__ = "user_groups"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    description = db.Column(db.String(300))
    created_at = db.Column(db.DateTime, default=local_now, nullable=False)

    members = db.relationship("AppUser", secondary=user_group_members, lazy="selectin")

    def to_dict(self):
        return {"id": self.id, "name": self.name, "description": self.description,
                "member_ids": [u.id for u in self.members],
                "member_names": [u.full_name for u in self.members]}
