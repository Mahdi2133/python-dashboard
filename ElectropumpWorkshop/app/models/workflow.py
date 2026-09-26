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

# How much of the record the approver is shown. An approval is a judgement on
# something, so the something has to be decided: everything the process has
# recorded, only the stage being approved, or a choice the sender makes when
# they send it.
SEE_ALL = "all"
SEE_STAGE = "stage"
SEE_PICK = "pick"
APPROVAL_SEES = {
    SEE_ALL: "همه‌ی اطلاعات ثبت‌شده تا اینجا",
    SEE_STAGE: "فقط اطلاعات همین مرحله",
    SEE_PICK: "ثبت‌کننده هنگام ارسال انتخاب می‌کند",
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
# Closed on purpose by somebody in the chain who judged it need not go on —
# «نیاز به کشیدن ندارد، قابل اصلاح است». Not a failure and not a cancellation
# by the admin, so it has its own name in the tracking view and the reports.
INSTANCE_STOPPED = "stopped"
INSTANCE_STATUS = {
    INSTANCE_OPEN: "در جریان",
    INSTANCE_COMPLETED: "تکمیل شده",
    INSTANCE_CANCELLED: "لغو شده",
    INSTANCE_STOPPED: "متوقف شد (نیاز به ادامه نبود)",
}

# What somebody at a stage can decide, beyond sending the work on. Each stage
# lists the ones it offers, and each one says who at that stage may use it.
ACTION_FORWARD = "forward"   # the ordinary hand-on, always there
ACTION_STOP = "stop"         # close the process here, with a reason
ACTION_RETURN = "return"     # send it back to a stage to complete or document
ACTION_KINDS = {
    ACTION_FORWARD: "ارسال به مرحله بعد",
    ACTION_STOP: "توقف فرایند",
    ACTION_RETURN: "برگشت برای تکمیل یا مستندسازی",
}


class WorkflowDefinition(db.Model):
    """One named process.

    Several may run at once, one per operation: «فرایند کشیدن» opens at مرکز
    آبرسانی and «فرایند نصب» at کارگاه نصب, each with its own stages and
    forms. ``operation_kind`` says which operation a process is for; empty
    means both, as the single process of older installs was.
    """
    __tablename__ = "workflow_definitions"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(60), unique=True, nullable=False)
    name = db.Column(db.String(160), nullable=False)
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    operation_kind = db.Column(db.String(10))
    created_at = db.Column(db.DateTime, default=local_now, nullable=False)
    updated_at = db.Column(db.DateTime, default=local_now, onupdate=local_now,
                           nullable=False)

    stages = db.relationship("WorkflowStage", back_populates="workflow",
                             cascade="all, delete-orphan",
                             order_by="WorkflowStage.stage_number")

    def to_dict(self, with_stages=True):
        data = {"id": self.id, "code": self.code, "name": self.name,
                "description": self.description, "is_active": self.is_active,
                "operation_kind": self.operation_kind,
                "operation_label": (OPERATION_KINDS.get(self.operation_kind)
                                    if self.operation_kind else "هر دو عملیات")}
        if with_stages:
            data["stages"] = [s.to_dict() for s in self.stages]
        return data


def _ids(raw) -> list:
    """Comma-separated user ids, in order, without repeats."""
    out = []
    for part in str(raw or "").split(","):
        part = part.strip()
        if part.isdigit() and int(part) not in out:
            out.append(int(part))
    return out


# A stage's متولی is a list, not a person. The city has eight مراکز آبرسانی,
# each with its own user, and one stage — «اعلام علت خرابی» — belongs to all of
# them. ``assignee_id`` stays as the first of the list so every older row and
# every screen that shows one name keeps working.
workflow_stage_owners = db.Table(
    "workflow_stage_owners",
    db.Column("stage_id", db.Integer,
              db.ForeignKey("workflow_stages.id", ondelete="CASCADE"),
              primary_key=True),
    db.Column("user_id", db.Integer,
              db.ForeignKey("app_users.id", ondelete="CASCADE"),
              primary_key=True),
)

# Which مرکز each person answers for. Only consulted by a stage that asks to
# be routed by the well's مرکز; a user with no centres is simply never narrowed
# out, so this stays empty until somebody fills it in.
app_user_centers = db.Table(
    "app_user_centers",
    db.Column("user_id", db.Integer,
              db.ForeignKey("app_users.id", ondelete="CASCADE"),
              primary_key=True),
    db.Column("center_id", db.Integer,
              db.ForeignKey("lookup_items.id", ondelete="CASCADE"),
              primary_key=True),
)


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
    # Whether a process can be opened here. This is what makes «کشیدن شروع
    # می‌شود از مرکز آبرسانی، نصب از کارگاه نصب» a setting rather than a rule
    # in the code: mark both stages, and ``applies_to`` says which operation
    # each one opens.
    can_start = db.Column(db.Boolean, nullable=False, default=False)
    # Which operation this door opens. Separate from ``applies_to`` because
    # the two answer different questions: کارگاه مکانیک is *visited* by both
    # a کشیدن and a نصب, but only a نصب *starts* there. Empty falls back to
    # ``applies_to``.
    start_kind = db.Column(db.String(10))
    # With eight centres owning one stage, all eight would otherwise see every
    # job. Turn this on and the work goes only to the owner whose مرکز is the
    # well's.
    route_by_center = db.Column(db.Boolean, nullable=False, default=False)

    # ── the referral: where this stage's work goes when it is done ──────────
    referral_mode = db.Column(db.String(10), nullable=False, default=REFER_NEXT)
    # For REFER_USER. For REFER_CHOOSE this is merely the default offered.
    referral_user_id = db.Column(db.Integer,
                                 db.ForeignKey("app_users.id",
                                               ondelete="SET NULL"),
                                 index=True)
    # A note the submitter sees next to the referral box — «به کدام کارتابل».
    referral_hint = db.Column(db.String(200))
    # Several fixed recipients, comma-separated user ids — «ارجاع به دفتر فنی و
    # بهره‌بردار» names two people at once. ``referral_user_id`` stays as the
    # first of them so a single-recipient screen still reads right.
    referral_user_ids = db.Column(db.String(200))
    # When the work goes to more than one person: must every one of them
    # record before it moves on, or is one of them enough?
    refer_all = db.Column(db.Boolean, nullable=False, default=False)
    # The decisions this stage offers beyond «ارسال به مرحله بعد», as a JSON
    # list: {id, kind, label, target_stage, needs_docs, user_ids}. «امین checks
    # مرکز آبرسانی's report and may stop it, or send it back for a video» is
    # this list, and «who may» is per action, per stage.
    actions_json = db.Column(db.Text)

    # ── the approval: whether somebody has to sign this stage off ───────────
    needs_approval = db.Column(db.Boolean, nullable=False, default=False)
    # Whether that approval *holds the process up*. Off, the approver rules at
    # their own pace while the stages after this one carry on; on, nothing
    # after this stage may be filled until they have ruled. The admin decides
    # per stage — «تا زمانی که ایکس تأیید نکند نمی‌توان ادامه داد» is a choice
    # about this stage, not a rule of the engine.
    approval_blocks = db.Column(db.Boolean, nullable=False, default=False)
    # What the approver is shown by default: SEE_ALL everything recorded so
    # far, SEE_STAGE only this stage's own answers, or SEE_PICK — the sender
    # chooses, stage by stage, at the moment they send it.
    approval_sees = db.Column(db.String(10), nullable=False, default=SEE_ALL)
    approver_id = db.Column(db.Integer, db.ForeignKey("app_users.id",
                                                      ondelete="SET NULL"),
                            index=True)
    # Where a rejection sends it. Empty means back to this stage's own owner,
    # which is what «برگشت به کارگاه جهت اصلاح» means.
    reject_to_stage = db.Column(db.Integer)

    workflow = db.relationship("WorkflowDefinition", back_populates="stages")
    assignee = db.relationship("AppUser", foreign_keys=[assignee_id])
    owners = db.relationship("AppUser", secondary=workflow_stage_owners,
                             lazy="selectin")
    referral_user = db.relationship("AppUser", foreign_keys=[referral_user_id])
    approver = db.relationship("AppUser", foreign_keys=[approver_id])
    items = db.relationship("WorkflowStageItem", back_populates="stage",
                            cascade="all, delete-orphan",
                            order_by="WorkflowStageItem.sort_order")

    @property
    def all_owners(self):
        """Everyone who owns this stage, the primary متولی first.

        ``owners`` is the list the admin edits. ``assignee_id`` is kept in step
        with its first entry, so a process seeded before this existed — and
        every screen that shows a single name — still reads correctly.
        """
        people = list(self.owners)
        if self.assignee is not None and self.assignee not in people:
            people.insert(0, self.assignee)
        elif self.assignee is not None:
            people.remove(self.assignee)
            people.insert(0, self.assignee)
        return people

    @property
    def owner_ids(self):
        return [u.id for u in self.all_owners]

    @property
    def actions(self):
        """The decision actions this stage offers, clean and in order."""
        import json
        try:
            raw = json.loads(self.actions_json or "[]")
        except ValueError:
            raw = []
        out = []
        for n, a in enumerate(raw if isinstance(raw, list) else []):
            kind = a.get("kind")
            if kind not in (ACTION_STOP, ACTION_RETURN):
                continue
            out.append({
                "id": str(a.get("id") or f"a{n + 1}"),
                "kind": kind,
                "label": (a.get("label") or "").strip() or ACTION_KINDS[kind],
                "target_stage": (int(a["target_stage"])
                                 if kind == ACTION_RETURN
                                 and str(a.get("target_stage", "")).lstrip("-").isdigit()
                                 else None),
                "needs_docs": bool(a.get("needs_docs")) if kind == ACTION_RETURN
                              else False,
                "user_ids": _ids(",".join(str(x) for x in (a.get("user_ids") or []))),
                # «field=a|b»: offer this decision only while that answer is
                # given — «نتیجه بررسی = نیاز به کشیدن ندارد». Empty: always.
                "when": (a.get("when") or "").strip() or None,
            })
        return out

    @property
    def referral_ids(self):
        """The fixed recipients, the first one first."""
        ids = _ids(self.referral_user_ids)
        if self.referral_user_id and self.referral_user_id not in ids:
            ids.insert(0, self.referral_user_id)
        return ids

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
            "can_start": self.can_start,
            "start_kind": self.start_kind or self.applies_to,
            "route_by_center": self.route_by_center,
            "owner_ids": self.owner_ids,
            "owner_names": [u.full_name for u in self.all_owners],
            "referral_mode": self.referral_mode,
            "referral_mode_label": REFERRAL_MODES.get(self.referral_mode,
                                                      self.referral_mode),
            "referral_user_id": self.referral_user_id,
            "referral_user_name": (self.referral_user.full_name
                                   if self.referral_user else None),
            "referral_hint": self.referral_hint,
            "referral_user_ids": self.referral_ids,
            "refer_all": self.refer_all,
            "actions": self.actions,
            "needs_approval": self.needs_approval,
            "approval_blocks": self.approval_blocks,
            "approval_sees": self.approval_sees,
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
    # Fields of this section that are shown here but not editable — the rest
    # of the section is filled as usual. «تیپ پمپ قبلی» read off the well's
    # history, visible to کارگاه but not theirs to change.
    locked_fields = db.Column(db.Text)

    stage = db.relationship("WorkflowStage", back_populates="items")
    section = db.relationship("FormSection")
    field = db.relationship("FormField")

    @property
    def locked_names(self) -> list:
        return [n.strip() for n in (self.locked_fields or "").split(",") if n.strip()]

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
            "locked_fields": self.locked_names,
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
    # Why the run ended where it did, when somebody stopped it on purpose —
    # «نیاز به کشیدن ندارد، قابل اصلاح است» — and who.
    outcome_note = db.Column(db.Text)
    outcome_by = db.Column(db.Integer, db.ForeignKey("app_users.id"))
    # The stage this run was opened at. Two doors can admit the same
    # operation — مرکز آبرسانی's and کارگاه نصب's — and the run starts at the
    # one its starter owns, so that choice is remembered here instead of being
    # recomputed as "the earliest door" every time the path is drawn.
    entry_stage = db.Column(db.Integer)
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
            "workflow_name": self.workflow.name if self.workflow else None,
            "operation_kind": self.operation_kind,
            "operation_label": self.operation_label,
            "well_id": self.well_id,
            "well": self.well.name if self.well else self.well_name_raw,
            "well_pm_code": self.well.pm_code if self.well else None,
            "current_stage": self.current_stage,
            "entry_stage": self.entry_stage,
            "outcome_note": self.outcome_note,
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
    # Everyone this one hand-off went to, comma-separated; ``referred_to_id``
    # is the first of them. With ``refer_all`` each of them has to record, and
    # ``done_by_ids`` is who already has.
    referred_to_ids = db.Column(db.String(200))
    refer_all = db.Column(db.Boolean, nullable=False, default=False)
    done_by_ids = db.Column(db.String(200))
    # Sent back to be completed «with a photo, a video, any document»: this
    # stage cannot be recorded again until something is attached after the
    # request was made.
    needs_docs = db.Column(db.Boolean, nullable=False, default=False)
    docs_requested_at = db.Column(db.DateTime)

    # ── the approval, on this run ───────────────────────────────────────────
    approver_id = db.Column(db.Integer, db.ForeignKey("app_users.id"),
                            index=True)
    # Which stages' answers this particular referral opened to the approver, as
    # a comma-separated list of stage numbers. Empty means "everything recorded
    # so far", which is the default; the sender narrows it when the stage is
    # set to «ثبت‌کننده انتخاب می‌کند».
    shared_stages = db.Column(db.String(120))
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
    def shared_stage_numbers(self):
        """The stages this referral opened, or None for "everything so far"."""
        raw = (self.shared_stages or "").strip()
        if not raw:
            return None
        return [int(p) for p in (x.strip() for x in raw.split(","))
                if p.lstrip("-").isdigit()]

    @property
    def recipient_ids(self):
        ids = _ids(self.referred_to_ids)
        if self.referred_to_id and self.referred_to_id not in ids:
            ids.insert(0, self.referred_to_id)
        return ids

    @property
    def done_ids(self):
        return _ids(self.done_by_ids)

    @property
    def pinned_owner_ids(self):
        """Everyone this run put the stage with, or None.

        An approval pins it to the approver. A referral pins it to its
        recipients — all of them when one is enough, or only those who have
        not recorded yet when every one of them must.
        """
        if self.status == ENTRY_AWAITING:
            return [self.approver_id] if self.approver_id else None
        people = self.recipient_ids
        if not people:
            return None
        if self.refer_all:
            left = [p for p in people if p not in self.done_ids]
            return left or people
        return people

    @property
    def pinned_owner_id(self):
        """The one person this run put this stage with, or None.

        A referral wins over the stage's standing متولی: the whole point of
        «ارجاع» is that this particular job goes to this particular person,
        without changing who owns the stage in general. An approval does the
        same until the approver has ruled.

        Nothing else pins it. A stage's متولی is a list — eight مراکز آبرسانی
        can share one — and «فقط متولی مرکزِ چاه» narrows that list per well,
        so when this run has pinned nobody the answer must be None and not the
        stage's first owner, or neither of those ever gets a chance to run.
        """
        if self.status == ENTRY_AWAITING:
            return self.approver_id
        return self.referred_to_id or None

    @property
    def owner_id(self):
        """The one name to show for this entry — see ``pinned_owner_id``."""
        pinned = self.pinned_owner_id
        if pinned is not None:
            return pinned
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
