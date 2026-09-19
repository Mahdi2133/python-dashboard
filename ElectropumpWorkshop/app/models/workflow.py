# -*- coding: utf-8 -*-
"""The process (فرایند) layer: who fills which part of the form, and when.

A record used to be one person filling one long form. In the workshop it is
really a chain: the water centre reports a fault, an engineer decides whether
the well must be pulled, the workshop records motor and pump, another engineer
settles the installation, and the last one signs off the pumping test. Only
then does a row belong in ``records``.

Two layers live here:

*   the **definition** — stages, who owns each, and which form sections and
    fields they fill. It is data, not code, so the admin rearranges it in the
    process builder without a release.
*   the **instance** — one well's journey through those stages, the payload
    each stage submitted, and the documents they attached.
"""
import json
from datetime import datetime

from ..extensions import db
from ..services.jalali import local_now

# The two things a job can be. Everything else in the process branches on it.
OPERATION_PULL = "pull"        # کشیدن
OPERATION_INSTALL = "install"  # نصب
OPERATION_KINDS = {
    OPERATION_PULL: "کشیدن",
    OPERATION_INSTALL: "نصب",
}

# When a stage item is shown. "both" is the default; the other two let the
# admin bind a section to one branch of the process.
APPLIES_BOTH = "both"
APPLIES_PULL = "pull"
APPLIES_INSTALL = "install"
APPLIES_TO = {
    APPLIES_BOTH: "هر دو عملیات",
    APPLIES_PULL: "فقط کشیدن",
    APPLIES_INSTALL: "فقط نصب",
}

# What happened to a stage in one particular run.
ENTRY_PENDING = "pending"      # waiting for its owner
ENTRY_SUBMITTED = "submitted"  # owner filled and sent it on
ENTRY_SKIPPED = "skipped"      # the branch does not visit this stage
ENTRY_ARCHIVED = "archived"    # visited, but its form was set aside by a rule
ENTRY_DEFERRED = "deferred"    # visited, its form left for later on purpose
ENTRY_STATUS = {
    ENTRY_PENDING: "در انتظار",
    ENTRY_SUBMITTED: "ثبت شده",
    ENTRY_SKIPPED: "طی نشده",
    ENTRY_ARCHIVED: "بایگانی",
    ENTRY_DEFERRED: "موکول به بعد",
}

INSTANCE_OPEN = "open"
INSTANCE_COMPLETED = "completed"
INSTANCE_CANCELLED = "cancelled"
INSTANCE_STATUS = {
    INSTANCE_OPEN: "در جریان",
    INSTANCE_COMPLETED: "تکمیل شده",
    INSTANCE_CANCELLED: "لغو شده",
}


class WorkflowDefinition(db.Model):
    """One named process. The workshop runs a single one, but not by force."""
    __tablename__ = "workflow_definitions"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(60), unique=True, nullable=False)
    name = db.Column(db.String(160), nullable=False)
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_at = db.Column(db.DateTime, default=local_now, nullable=False)
    updated_at = db.Column(db.DateTime, default=local_now, onupdate=local_now,
                           nullable=False)

    stages = db.relationship("WorkflowStage", back_populates="workflow",
                             cascade="all, delete-orphan",
                             order_by="WorkflowStage.stage_number")

    def to_dict(self, with_stages=True):
        data = {"id": self.id, "code": self.code, "name": self.name,
                "description": self.description, "is_active": self.is_active}
        if with_stages:
            data["stages"] = [s.to_dict() for s in self.stages]
        return data


class WorkflowStage(db.Model):
    """A step and the person who owns it.

    ``stage_number`` 0 is the intake step that only picks کشیدن or نصب; the
    five numbered stages after it are the real forms.
    """
    __tablename__ = "workflow_stages"
    __table_args__ = (db.UniqueConstraint("workflow_id", "stage_number",
                                          name="uq_workflow_stage_number"),)

    id = db.Column(db.Integer, primary_key=True)
    workflow_id = db.Column(db.Integer,
                            db.ForeignKey("workflow_definitions.id",
                                          ondelete="CASCADE"),
                            nullable=False, index=True)
    stage_number = db.Column(db.Integer, nullable=False)
    title = db.Column(db.String(160), nullable=False)
    description = db.Column(db.Text)
    # The متولی. Nullable so a freshly seeded process can be assigned later —
    # an unassigned stage is reported rather than silently skipped.
    assignee_id = db.Column(db.Integer, db.ForeignKey("app_users.id",
                                                      ondelete="SET NULL"),
                            index=True)
    # Which branch visits this stage at all.
    applies_to = db.Column(db.String(10), nullable=False, default=APPLIES_BOTH)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    workflow = db.relationship("WorkflowDefinition", back_populates="stages")
    assignee = db.relationship("AppUser", foreign_keys=[assignee_id])
    items = db.relationship("WorkflowStageItem", back_populates="stage",
                            cascade="all, delete-orphan",
                            order_by="WorkflowStageItem.sort_order")

    def to_dict(self):
        return {
            "id": self.id, "stage_number": self.stage_number,
            "title": self.title, "description": self.description,
            "assignee_id": self.assignee_id,
            "assignee_name": self.assignee.full_name if self.assignee else None,
            "assignee_username": self.assignee.username if self.assignee else None,
            "applies_to": self.applies_to,
            "applies_to_label": APPLIES_TO.get(self.applies_to, self.applies_to),
            "is_active": self.is_active,
            "items": [i.to_dict() for i in self.items],
        }


class WorkflowStageItem(db.Model):
    """A section — or a single field — dropped onto a stage.

    Both grains exist because the process needs both: stage 3 owns whole
    sections, while stage 1 owns exactly one field (علت خرابی) out of a section
    whose other fields belong to stage 3.
    """
    __tablename__ = "workflow_stage_items"

    id = db.Column(db.Integer, primary_key=True)
    stage_id = db.Column(db.Integer, db.ForeignKey("workflow_stages.id",
                                                   ondelete="CASCADE"),
                         nullable=False, index=True)
    section_id = db.Column(db.Integer, db.ForeignKey("form_sections.id",
                                                     ondelete="CASCADE"),
                           index=True)
    field_id = db.Column(db.Integer, db.ForeignKey("form_fields.id",
                                                   ondelete="CASCADE"),
                         index=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    applies_to = db.Column(db.String(10), nullable=False, default=APPLIES_BOTH)
    # An optional item never blocks the stage from being submitted.
    is_optional = db.Column(db.Boolean, nullable=False, default=False)

    stage = db.relationship("WorkflowStage", back_populates="items")
    section = db.relationship("FormSection")
    field = db.relationship("FormField")

    @property
    def kind(self):
        return "section" if self.section_id else "field"

    def to_dict(self):
        return {
            "id": self.id, "kind": self.kind,
            "section_id": self.section_id, "field_id": self.field_id,
            "code": (self.section.code if self.section
                     else self.field.field_name if self.field else None),
            "title": (self.section.title if self.section
                      else self.field.label if self.field else None),
            "sort_order": self.sort_order,
            "applies_to": self.applies_to,
            "applies_to_label": APPLIES_TO.get(self.applies_to, self.applies_to),
            "is_optional": self.is_optional,
        }


class WorkflowInstance(db.Model):
    """One well's trip through the process."""
    __tablename__ = "workflow_instances"

    id = db.Column(db.Integer, primary_key=True)
    workflow_id = db.Column(db.Integer,
                            db.ForeignKey("workflow_definitions.id"),
                            nullable=False, index=True)
    operation_kind = db.Column(db.String(10), index=True)   # pull | install
    well_id = db.Column(db.Integer, db.ForeignKey("wells.id"), index=True)
    well_name_raw = db.Column(db.String(200))

    current_stage = db.Column(db.Integer, nullable=False, default=0, index=True)
    status = db.Column(db.String(16), nullable=False, default=INSTANCE_OPEN,
                       index=True)
    # Everything every stage has submitted so far, merged. The record is built
    # from this once the last stage signs off.
    payload_json = db.Column(db.Text)

    record_id = db.Column(db.Integer, db.ForeignKey("records.id"), index=True)
    created_by = db.Column(db.Integer, db.ForeignKey("app_users.id"))
    created_at = db.Column(db.DateTime, default=local_now, nullable=False,
                           index=True)
    updated_at = db.Column(db.DateTime, default=local_now, onupdate=local_now,
                           nullable=False)
    completed_at = db.Column(db.DateTime)

    workflow = db.relationship("WorkflowDefinition")
    well = db.relationship("Well")
    record = db.relationship("Record")
    author = db.relationship("AppUser", foreign_keys=[created_by])
    entries = db.relationship("WorkflowStageEntry", back_populates="instance",
                              cascade="all, delete-orphan",
                              order_by="WorkflowStageEntry.stage_number")
    attachments = db.relationship("WorkflowAttachment", back_populates="instance",
                                  cascade="all, delete-orphan")

    @property
    def payload(self) -> dict:
        if not self.payload_json:
            return {}
        try:
            value = json.loads(self.payload_json)
            return value if isinstance(value, dict) else {}
        except ValueError:
            return {}

    def set_payload(self, data: dict):
        self.payload_json = json.dumps(data or {}, ensure_ascii=False)

    def merge_payload(self, data: dict):
        merged = self.payload
        merged.update(data or {})
        self.set_payload(merged)

    @property
    def operation_label(self):
        return OPERATION_KINDS.get(self.operation_kind, "—")

    def to_dict(self, with_entries=True):
        from ..services.jalali import tehran_time_str, to_jalali_str
        data = {
            "id": self.id, "workflow_id": self.workflow_id,
            "operation_kind": self.operation_kind,
            "operation_label": self.operation_label,
            "well_id": self.well_id,
            "well": self.well.name if self.well else self.well_name_raw,
            "well_pm_code": self.well.pm_code if self.well else None,
            "current_stage": self.current_stage,
            "status": self.status,
            "status_label": INSTANCE_STATUS.get(self.status, self.status),
            "record_id": self.record_id,
            "created_by": self.created_by,
            "created_by_name": self.author.full_name if self.author else None,
            "created_at_j": to_jalali_str(self.created_at),
            "created_at_time": tehran_time_str(self.created_at, with_seconds=False),
            "updated_at_j": to_jalali_str(self.updated_at),
            "completed_at_j": to_jalali_str(self.completed_at) if self.completed_at else None,
            "attachment_count": len(self.attachments),
        }
        if with_entries:
            data["entries"] = [e.to_dict() for e in self.entries]
        return data


class WorkflowStageEntry(db.Model):
    """What one stage did on one instance — including doing nothing, and why."""
    __tablename__ = "workflow_stage_entries"
    __table_args__ = (db.UniqueConstraint("instance_id", "stage_number",
                                          name="uq_instance_stage"),)

    id = db.Column(db.Integer, primary_key=True)
    instance_id = db.Column(db.Integer,
                            db.ForeignKey("workflow_instances.id",
                                          ondelete="CASCADE"),
                            nullable=False, index=True)
    stage_id = db.Column(db.Integer, db.ForeignKey("workflow_stages.id",
                                                   ondelete="SET NULL"))
    stage_number = db.Column(db.Integer, nullable=False, index=True)
    status = db.Column(db.String(16), nullable=False, default=ENTRY_PENDING,
                       index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("app_users.id"))
    payload_json = db.Column(db.Text)
    note = db.Column(db.Text)              # why it was archived/deferred, etc.
    started_at = db.Column(db.DateTime, default=local_now, nullable=False)
    submitted_at = db.Column(db.DateTime)

    instance = db.relationship("WorkflowInstance", back_populates="entries")
    stage = db.relationship("WorkflowStage")
    user = db.relationship("AppUser", foreign_keys=[user_id])

    @property
    def payload(self) -> dict:
        if not self.payload_json:
            return {}
        try:
            value = json.loads(self.payload_json)
            return value if isinstance(value, dict) else {}
        except ValueError:
            return {}

    def set_payload(self, data: dict):
        self.payload_json = json.dumps(data or {}, ensure_ascii=False)

    def to_dict(self):
        from ..services.jalali import tehran_time_str, to_jalali_str
        return {
            "id": self.id, "stage_number": self.stage_number,
            "stage_id": self.stage_id,
            "title": self.stage.title if self.stage else None,
            "status": self.status,
            "status_label": ENTRY_STATUS.get(self.status, self.status),
            "user_id": self.user_id,
            "user_name": self.user.full_name if self.user else None,
            "assignee_name": (self.stage.assignee.full_name
                              if self.stage and self.stage.assignee else None),
            "note": self.note,
            "submitted_at_j": (to_jalali_str(self.submitted_at)
                               if self.submitted_at else None),
            "submitted_at_time": (tehran_time_str(self.submitted_at,
                                                  with_seconds=False)
                                  if self.submitted_at else None),
            "payload": self.payload,
        }


class WorkflowAttachment(db.Model):
    """A document someone attached while the process was passing through them.

    Anything goes — a photo of the plaque, a pump curve PDF, the contractor's
    spreadsheet — so the file is stored under a generated name and the original
    is kept only as a label.
    """
    __tablename__ = "workflow_attachments"

    id = db.Column(db.Integer, primary_key=True)
    instance_id = db.Column(db.Integer,
                            db.ForeignKey("workflow_instances.id",
                                          ondelete="CASCADE"),
                            nullable=False, index=True)
    stage_number = db.Column(db.Integer, index=True)
    filename = db.Column(db.String(260), nullable=False)      # as uploaded
    stored_name = db.Column(db.String(160), nullable=False)   # on disk
    content_type = db.Column(db.String(120))
    size_bytes = db.Column(db.Integer)
    uploaded_by = db.Column(db.Integer, db.ForeignKey("app_users.id"))
    uploaded_at = db.Column(db.DateTime, default=local_now, nullable=False)

    instance = db.relationship("WorkflowInstance", back_populates="attachments")
    uploader = db.relationship("AppUser", foreign_keys=[uploaded_by])

    def to_dict(self):
        from ..services.jalali import tehran_time_str, to_jalali_str
        return {
            "id": self.id, "instance_id": self.instance_id,
            "stage_number": self.stage_number,
            "filename": self.filename, "content_type": self.content_type,
            "size_bytes": self.size_bytes,
            "size_label": _human_size(self.size_bytes),
            "uploaded_by_name": self.uploader.full_name if self.uploader else None,
            "uploaded_at_j": to_jalali_str(self.uploaded_at),
            "uploaded_at_time": tehran_time_str(self.uploaded_at, with_seconds=False),
            "url": f"/api/workflow/attachments/{self.id}",
        }


def _human_size(size):
    if not size:
        return "—"
    for unit in ("بایت", "کیلوبایت", "مگابایت", "گیگابایت"):
        if size < 1024 or unit == "گیگابایت":
            return f"{size:.0f} {unit}" if unit == "بایت" else f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} گیگابایت"
