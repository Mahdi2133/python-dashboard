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

# Who a stage hands its work to when it is done. The workshop's process is a
# chain of referrals — «ارجاع به کارگاه مکانیک», «برگشت به کارتابل بهره‌بردار»
# — so the admin says, per stage, how the next owner is chosen.
REFER_NEXT = "next"      # whoever owns the next stage (the default)
REFER_USER = "user"      # always this one person
REFER_CHOOSE = "choose"  # the person finishing this stage picks, from a list
REFERRAL_MODES = {
    REFER_NEXT: "متولی مرحله بعد",
    REFER_USER: "همیشه به یک کاربر مشخص",
    REFER_CHOOSE: "ثبت‌کننده هنگام ارسال انتخاب می‌کند",
}

# What happened to a stage in one particular run.
ENTRY_PENDING = "pending"      # waiting for its owner
ENTRY_SUBMITTED = "submitted"  # owner filled and sent it on
ENTRY_SKIPPED = "skipped"      # the branch does not visit this stage
ENTRY_ARCHIVED = "archived"    # visited, but its form was set aside by a rule
ENTRY_DEFERRED = "deferred"    # visited, its form left for later on purpose
ENTRY_AWAITING = "awaiting"    # filled, now sitting with its approver
ENTRY_REJECTED = "rejected"    # the approver sent it back to be redone
ENTRY_STATUS = {
    ENTRY_PENDING: "در انتظار",
    ENTRY_SUBMITTED: "ثبت شده",
    ENTRY_SKIPPED: "طی نشده",
    ENTRY_ARCHIVED: "بایگانی",
    ENTRY_DEFERRED: "موکول به بعد",
    ENTRY_AWAITING: "در انتظار تأیید",
    ENTRY_REJECTED: "برگشت خورده",
}
# Statuses that mean the stage has had its say and the process may move on.
ENTRY_DONE = (ENTRY_SUBMITTED, ENTRY_ARCHIVED, ENTRY_DEFERRED)

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

    # ── the referral: where this stage's work goes when it is done ──────────
    referral_mode = db.Column(db.String(10), nullable=False, default=REFER_NEXT)
    # For REFER_USER. For REFER_CHOOSE this is merely the default offered.
    referral_user_id = db.Column(db.Integer,
                                 db.ForeignKey("app_users.id",
                                               ondelete="SET NULL"),
                                 index=True)
    # A note the submitter sees next to the referral box — «به کدام کارتابل».
    referral_hint = db.Column(db.String(200))

    # ── the approval: whether somebody has to sign this stage off ───────────
    needs_approval = db.Column(db.Boolean, nullable=False, default=False)
    approver_id = db.Column(db.Integer, db.ForeignKey("app_users.id",
                                                      ondelete="SET NULL"),
                            index=True)
    # Where a rejection sends it. Empty means back to this stage's own owner,
    # which is what «برگشت به کارگاه جهت اصلاح» means.
    reject_to_stage = db.Column(db.Integer)

    workflow = db.relationship("WorkflowDefinition", back_populates="stages")
    assignee = db.relationship("AppUser", foreign_keys=[assignee_id])
    referral_user = db.relationship("AppUser", foreign_keys=[referral_user_id])
    approver = db.relationship("AppUser", foreign_keys=[approver_id])
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
            "referral_mode": self.referral_mode,
            "referral_mode_label": REFERRAL_MODES.get(self.referral_mode,
                                                      self.referral_mode),
            "referral_user_id": self.referral_user_id,
            "referral_user_name": (self.referral_user.full_name
                                   if self.referral_user else None),
            "referral_hint": self.referral_hint,
            "needs_approval": self.needs_approval,
            "approver_id": self.approver_id,
            "approver_name": (self.approver.full_name
                              if self.approver else None),
            "reject_to_stage": self.reject_to_stage,
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
    # Shown with what an earlier stage put in it, but not editable here. This
    # is how a checklist filled in one stage is carried, read-only, into the
    # stages after it — and the admin decides, item by item, which it is.
    is_read_only = db.Column(db.Boolean, nullable=False, default=False)

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
            "is_read_only": self.is_read_only,
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

    # ── the referral, on this run ───────────────────────────────────────────
    # Who this piece of work is actually sitting with. Empty means the stage's
    # own متولی; set, it overrides them for this run and this run only, which
    # is what «ارجاع به کارگاه مکانیک» does.
    referred_to_id = db.Column(db.Integer, db.ForeignKey("app_users.id"),
                               index=True)
    referred_by_id = db.Column(db.Integer, db.ForeignKey("app_users.id"))
    referred_at = db.Column(db.DateTime)
    referral_note = db.Column(db.Text)

    # ── the approval, on this run ───────────────────────────────────────────
    approver_id = db.Column(db.Integer, db.ForeignKey("app_users.id"),
                            index=True)
    decided_by_id = db.Column(db.Integer, db.ForeignKey("app_users.id"))
    decided_at = db.Column(db.DateTime)
    decision_note = db.Column(db.Text)

    instance = db.relationship("WorkflowInstance", back_populates="entries")
    stage = db.relationship("WorkflowStage")
    user = db.relationship("AppUser", foreign_keys=[user_id])
    referred_to = db.relationship("AppUser", foreign_keys=[referred_to_id])
    referred_by = db.relationship("AppUser", foreign_keys=[referred_by_id])
    approver = db.relationship("AppUser", foreign_keys=[approver_id])
    decided_by = db.relationship("AppUser", foreign_keys=[decided_by_id])

    @property
    def owner_id(self):
        """Whose کارتابل this entry belongs in right now.

        A referral wins over the stage's standing متولی: the whole point of
        «ارجاع» is that this particular job goes to this particular person,
        without changing who owns the stage in general.
        """
        if self.status == ENTRY_AWAITING:
            return self.approver_id
        if self.referred_to_id:
            return self.referred_to_id
        return self.stage.assignee_id if self.stage else None

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
            "owner_id": self.owner_id,
            "referred_to_id": self.referred_to_id,
            "referred_to_name": (self.referred_to.full_name
                                 if self.referred_to else None),
            "referred_by_name": (self.referred_by.full_name
                                 if self.referred_by else None),
            "referred_at_j": (to_jalali_str(self.referred_at)
                              if self.referred_at else None),
            "referral_note": self.referral_note,
            "approver_id": self.approver_id,
            "approver_name": self.approver.full_name if self.approver else None,
            "decided_by_name": (self.decided_by.full_name
                                if self.decided_by else None),
            "decided_at_j": (to_jalali_str(self.decided_at)
                             if self.decided_at else None),
            "decision_note": self.decision_note,
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
