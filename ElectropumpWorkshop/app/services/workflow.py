# -*- coding: utf-8 -*-
"""The process engine: whose turn it is, what they see, and where it goes next.

The rules the workshop asked for, in one place:

*   Step 0 asks کشیدن or نصب and nothing else.
*   نصب starts the chain at stage 3 (the workshop); کشیدن starts at stage 1 so
    the water centre puts the fault on record first, and stage 2 rules on
    whether the well really needs pulling.
*   «اطلاعات پایه» belongs to whichever stage runs first — stage 1 on a pull,
    stage 3 on an install — and is never asked twice.
*   At stage 4 a pull first answers «اقدام مورد نیاز». Anything but «نصب
    الکتروپمپ جدید» files «اطلاعات چاه و نصب» away and moves on; that one asks
    whether the pump type is being chosen now, and only «بله» opens the form.
*   Stage 5 signs off, and only then does a row appear in ``records``.
"""
from __future__ import annotations

import logging

from ..extensions import db
from ..models import (AppUser, FormField, FormSection, Record,
                      WorkflowAttachment,
                      WorkflowDefinition, WorkflowInstance, WorkflowStage,
                      WorkflowStageEntry, WorkflowStageItem)
from ..models.workflow import (APPLIES_BOTH, ENTRY_ARCHIVED, ENTRY_AWAITING,
                               SEE_PICK, SEE_STAGE,
                               ENTRY_DEFERRED, ENTRY_DONE, ENTRY_PENDING,
                               ENTRY_REJECTED, ENTRY_SKIPPED, ENTRY_STATUS,
                               ENTRY_SUBMITTED, INSTANCE_CANCELLED,
                               INSTANCE_COMPLETED, INSTANCE_OPEN,
                               OPERATION_INSTALL, OPERATION_KINDS,
                               OPERATION_PULL, REFER_CHOOSE, REFER_NEXT,
                               REFER_USER)
from .audit import record_audit
from .jalali import local_now, to_jalali_str
from .lookups import normalize_text
from .records import ValidationError, create_record, resolve_well

log = logging.getLogger(__name__)

# The one answer that keeps «اطلاعات چاه و نصب» open at stage 4.
ACTION_NEW_PUMP = "نصب الکتروپمپ جدید"
STAGE_INTAKE = 0
# Where each branch used to begin, before the admin could say so. Kept only as
# the fallback for a process nobody has marked a start stage on yet; once any
# stage carries ``can_start`` these are never consulted again.
STAGE_FIRST_PULL = 1
STAGE_FIRST_INSTALL = 3
# «اطلاعات چاه و نصب» is only asked for when the action decision says a new
# pump is going in. That rule belongs to the section, not to whatever number
# its stage happens to carry, so it follows the section when the admin moves
# or reorders it.
SECTION_WELL_INSTALL = "well_install"


class WorkflowError(Exception):
    """A process rule refused the move. Carries a Persian message.

    ``fields`` names the individual answers at fault, so the form can mark
    each one rather than leaving the operator to hunt for them.
    """

    def __init__(self, message, fields=None):
        super().__init__(message)
        self.fields = fields or {}


# ── definition ───────────────────────────────────────────────────────────────
def active_workflow() -> WorkflowDefinition | None:
    return (WorkflowDefinition.query.filter_by(is_active=True)
            .order_by(WorkflowDefinition.id).first())


def _kind_matches(applies_to: str, kind: str | None) -> bool:
    """Whether an item or stage marked ``applies_to`` is used for ``kind``."""
    if applies_to == APPLIES_BOTH or not applies_to:
        return True
    if kind is None:
        return True          # before the branch is chosen, assume it may apply
    return applies_to == kind


def stages_for(workflow: WorkflowDefinition, kind: str | None) -> list:
    """The stages this operation actually visits, in order."""
    return [s for s in workflow.stages
            if s.is_active and _kind_matches(s.applies_to, kind)]


def entry_stage(workflow, kind: str | None):
    """The stage a ``kind`` process opens at, as the admin marked it.

    «کشیدن از مرکز آبرسانی شروع می‌شود، نصب از کارگاه نصب» is a setting, not a
    rule in this file: whichever stages carry ``can_start`` and admit this
    operation are the doors, and the earliest of them is the one it opens at.
    """
    if workflow is None:
        return None
    doors = doors_for(workflow, kind)
    return doors[0] if doors else None


def doors_for(workflow, kind: str | None) -> list:
    """Every stage a ``kind`` process may be opened at, earliest first."""
    if workflow is None:
        return []
    return [s for s in sorted(workflow.stages, key=lambda x: x.stage_number)
            if s.is_active and s.can_start
            and _kind_matches(s.start_kind or s.applies_to, kind)]


def door_of(workflow, kind: str | None, user):
    """The door this person opens a ``kind`` process at.

    Their own, when they hold one: «نصب از کارگاه نصب» means the workshop's
    owner starts an install at the workshop's stage, even though stage 1 may
    admit both operations too. An admin holds every key and starts at the
    earliest door.
    """
    doors = doors_for(workflow, kind)
    if not doors:
        return None
    if user is not None and not (user.role == "admin"
                                 or user.can("workflow.manage")):
        mine = [d for d in doors if user.id in stage_owner_ids(d)]
        if mine:
            return mine[0]
    return doors[0]


def first_stage_number(kind: str | None, workflow=None) -> int:
    """Where the real work starts once the operation is known."""
    door = entry_stage(workflow if workflow is not None else active_workflow(),
                       kind)
    if door is not None:
        return door.stage_number
    # Nothing marked yet — the process as it was seeded.
    return STAGE_FIRST_INSTALL if kind == OPERATION_INSTALL else STAGE_FIRST_PULL


def last_stage_number(workflow) -> int:
    """One past the final stage: where ``current_stage`` rests when done."""
    numbers = [s.stage_number for s in (workflow.stages if workflow else [])
               if s.is_active]
    return max(numbers) if numbers else STAGE_INTAKE


def startable_kinds(user) -> list:
    """Which operations this person may open a process for.

    A door is a stage marked ``can_start``; its متولی holds the key, and its
    «شامل» says which operation it opens. An admin holds every key.
    """
    if user is None:
        return []
    workflow = active_workflow()
    if workflow is None:
        return []
    if user.role == "admin" or user.can("workflow.manage"):
        return list(OPERATION_KINDS)
    out = []
    for kind in OPERATION_KINDS:
        doors = doors_for(workflow, kind)
        if any(user.id in stage_owner_ids(d) for d in doors):
            out.append(kind)
            continue
        door = doors[0] if doors else None
        # A process that still has its intake step keeps the old rule: whoever
        # owns step zero opens everything.
        intake = next((s for s in workflow.stages
                       if s.stage_number == STAGE_INTAKE and s.is_active), None)
        if door is None and intake is not None \
                and user.id in stage_owner_ids(intake):
            out.append(kind)
    return out


def stage_owner_ids(stage) -> list:
    """Everyone who owns this stage, ignoring any one run of the process."""
    return stage.owner_ids if stage is not None else []


# ── stage 4's branch ─────────────────────────────────────────────────────────
def well_install_state(kind: str | None, payload: dict) -> str:
    """What stage 4 should do with «اطلاعات چاه و نصب».

    ``show`` fill it here · ``archived`` the action does not need it ·
    ``deferred`` a new pump is going in but its type is not settled yet ·
    ``ask`` the decision has not been made.
    """
    if kind == OPERATION_INSTALL:
        return "show"                       # an install has no action question
    action = normalize_text(payload.get("required_action") or "")
    if not action:
        return "ask"
    if action != normalize_text(ACTION_NEW_PUMP):
        return "archived"
    answer = normalize_text(payload.get("pump_type_now") or "")
    if not answer:
        return "ask"
    return "show" if answer == "بله" else "deferred"


# ── what a stage shows ───────────────────────────────────────────────────────
def _already_owned(instance: WorkflowInstance, except_stage: int) -> set:
    """Sections and fields some *other* stage of this run has already filled.

    This is what keeps «اطلاعات پایه» from being asked twice: it hangs off both
    stage 1 and stage 3, and whichever gets there first claims it. Because the
    stages do not run in order, "first" means whoever submitted — not whoever
    comes earlier in the chain.
    """
    owned = set()
    for entry in instance.entries:
        if entry.stage_number == except_stage:
            continue
        if entry.status not in (ENTRY_SUBMITTED, ENTRY_ARCHIVED):
            continue
        if entry.stage is None:
            continue
        for item in entry.stage.items:
            if item.is_read_only:
                continue     # this one is meant to be shown again, locked
            if item.section:
                owned.add(("section", item.section.code))
            elif item.field:
                owned.add(("field", item.field.field_name))
    return owned


def carries_well_install(stage: WorkflowStage) -> bool:
    """Whether «اطلاعات چاه و نصب» is on this stage, wherever the admin put it."""
    return any(i.section is not None and i.section.code == SECTION_WELL_INSTALL
               for i in stage.items)


def stage_items(instance: WorkflowInstance, stage: WorkflowStage,
                payload: dict | None = None) -> list:
    """The sections and fields this stage asks for, on this instance."""
    kind = instance.operation_kind
    merged = dict(instance.payload)
    merged.update(payload or {})
    owned = _already_owned(instance, stage.stage_number)
    state = well_install_state(kind, merged)

    visible = []
    for item in stage.items:
        if not _kind_matches(item.applies_to, kind):
            continue
        key = (("section", item.section.code) if item.section
               else ("field", item.field.field_name) if item.field else None)
        if key is None or (key in owned and not item.is_read_only):
            continue
        if (item.section is not None
                and item.section.code == SECTION_WELL_INSTALL
                and state != "show"):
            continue          # archived or deferred by the action decision
        visible.append(item)
    return visible


def _settled_values(instance: WorkflowInstance, except_stage: int) -> dict:
    """Everything the other stages of this run have already answered."""
    values = {}
    for entry in instance.entries:
        if entry.stage_number == except_stage or entry.status not in ENTRY_DONE:
            continue
        for name, value in (entry.payload or {}).items():
            if value not in (None, "", [], {}):
                values.setdefault(name, value)
    return values


def stage_form(instance: WorkflowInstance, stage: WorkflowStage,
               draft: dict | None = None) -> dict:
    """Everything the browser needs to draw one stage of one instance.

    A stage that owns a single field out of somebody else's section (stage 1
    and «علت خرابی») gets that field wrapped in a one-field section, so the
    page has one thing to render rather than two.
    """
    def usable(fields):
        """Drop fields this branch never asks, and lock the ones already settled.

        «علت خرابی» and «نصب مرتبط با…» sit in the same section, each bound to
        one operation; the branch decides here, once, rather than being decided
        again in the browser from a second copy of the answer. The well is
        chosen at step zero, so later stages are shown it rather than asked to
        search for it again.
        """
        kept = []
        for field in fields:
            rule = (field.get("visible_when") or "").strip()
            if rule.startswith("operation_kind=") and instance.operation_kind:
                wanted = rule.split("=", 1)[1].strip()
                if wanted != OPERATION_KINDS.get(instance.operation_kind):
                    continue
            if field.get("field_name") == "well" and instance.well_id:
                field = dict(field)
                field["read_only"] = True
                field["read_only_value"] = instance.well.name
                field["help_text"] = "در شروع فرایند انتخاب شده است."
            # The مرکز follows the well: the register already knows which
            # centre a well belongs to, so asking is both extra work and a
            # chance to get it wrong. Shown, never editable.
            if (field.get("field_name") == "center" and instance.well_id
                    and instance.well.center is not None):
                field = dict(field)
                field["read_only"] = True
                field["read_only_value"] = instance.well.center.label
                field["help_text"] = (f"مرکز چاه «{instance.well.name}» است و "
                                      "از فهرست چاه‌ها خوانده می‌شود.")
            kept.append(field)
        return kept

    settled = _settled_values(instance, stage.stage_number)

    def locked(fields):
        """Show what an earlier stage put here, and refuse the pen.

        This is what «قفل» means on a stage item: the checklist the workshop
        ticked is carried into the stages after it, visible in full, and not
        theirs to change. The admin decides which items are like this.
        """
        out = []
        for field in fields:
            field = dict(field)
            field["read_only"] = True
            value = settled.get(field.get("field_name"))
            if value not in (None, "", [], {}):
                field["read_only_value"] = (
                    "، ".join(str(v) for v in value if v not in (None, ""))
                    if isinstance(value, list) else value)
            else:
                field["read_only_value"] = "—"
            field["help_text"] = (field.get("help_text")
                                  or "در مرحله‌ی پیشین ثبت شده است.")
            out.append(field)
        return out

    blocks = []
    for item in stage_items(instance, stage, draft):
        if item.section:
            block = item.section.to_dict(include_fields=True, active_only=True)
            block["fields"] = usable(block.get("fields") or [])
            if item.is_read_only:
                block["fields"] = locked(block["fields"])
                block["is_locked"] = True
            if not block["fields"]:
                continue
            block["is_optional"] = item.is_optional
            blocks.append(block)
        elif item.field:
            fields = usable([item.field.to_dict()])
            if item.is_read_only:
                fields = locked(fields)
            if not fields:
                continue
            blocks.append({
                "id": None, "code": f"field_{item.field.field_name}",
                "title": item.field.label, "icon": "◽", "columns": 1,
                "full_width": True, "is_active": True,
                "is_optional": item.is_optional,
                "is_locked": item.is_read_only,
                "description": None,
                "fields": fields,
            })
    blocks += _dependent_sections(blocks, usable, settled)
    return {
        "stage": stage.to_dict(),
        "sections": blocks,
        "well_install_state": (well_install_state(
                                   instance.operation_kind,
                                   {**instance.payload, **(draft or {})})
                               if carries_well_install(stage) else None),
    }


def _missing_required(instance: WorkflowInstance, stage: WorkflowStage,
                      payload: dict) -> dict:
    """Required answers this stage asked for and did not get.

    Checked here, at the stage that owns the question, rather than only when
    the final record is written: otherwise a cause ticked at stage 1 with its
    readings left blank surfaces as an error in front of the stage-5 engineer,
    who can neither see nor fill them. A section still closed by its rule —
    a cause nobody ticked — asks for nothing.
    """
    from .records import _hidden_by_condition
    merged = dict(instance.payload)
    merged.update(payload or {})
    hidden = _hidden_by_condition(merged, unanswered_hides=True)
    missing = {}
    for block in stage_form(instance, stage, payload)["sections"]:
        if block.get("is_locked") or block.get("is_optional"):
            continue
        for f in block.get("fields") or []:
            name = f.get("field_name")
            if (not f.get("is_required") or f.get("read_only")
                    or name in hidden):
                continue
            # An answer another stage already recorded counts: a stage adds
            # to the record, it does not re-type what is on it.
            if merged.get(name) in (None, "", [], {}):
                missing[name] = f"«{f.get('label') or name}» الزامی است."
    return missing


def _dependent_sections(blocks: list, usable, settled=None) -> list:
    """Sections that open off a field this stage is asking for.

    A section with «نمایش فقط وقتی علت خرابی = سوختن الکتروپمپ» belongs with
    whichever stage asks «علت خرابی» — it is the second half of that question.
    Attaching all ten cause forms to that stage by hand, and again every time
    one is added, is exactly the kind of wiring that gets forgotten; so they
    follow the field on their own, drawn hidden and opened in the browser the
    moment their cause is ticked. Only a field this stage may still answer
    pulls them in: a cause settled at an earlier stage brought its readings
    with it there.
    """
    asked = set()
    present = set()
    already = set((settled or {}).keys())
    for block in blocks:
        present.add(block.get("code"))
        if block.get("is_locked"):
            continue
        for f in block.get("fields") or []:
            # A question an earlier stage already answered brought its forms
            # with it there; asking them again here would only duplicate them.
            if not f.get("read_only") and f.get("field_name") not in already:
                asked.add(f.get("field_name"))
    if not asked:
        return []
    out = []
    for section in (FormSection.query.filter(
            FormSection.visible_when.isnot(None),
            FormSection.is_active.is_(True))
            .order_by(FormSection.sort_order).all()):
        on = (section.visible_when or "").partition("=")[0].strip()
        if on not in asked or section.code in present:
            continue
        block = section.to_dict(include_fields=True, active_only=True)
        block["fields"] = usable(block.get("fields") or [])
        if not block["fields"]:
            continue
        block["is_optional"] = False
        block["conditional"] = True
        out.append(block)
    return out


def submitted_summary(instance: WorkflowInstance, except_stage: int = None,
                      only_stages: list | None = None) -> list:
    """What the other stages have already recorded, ready to show read-only.

    Whoever is holding the process needs to see the work behind it — the
    engineer at stage 5 signs off on what four people before him wrote — but
    none of it is his to change, so it is handed over as labelled text rather
    than as fields.

    ``only_stages`` narrows it to what one referral opened. An approver is
    being asked to rule on something, and the person asking says what that
    something is; without it they see everything recorded so far, which is the
    default and the usual answer.
    """
    labels = {f.field_name: f.label for f in FormField.query.all()}
    out = []
    for entry in sorted(instance.entries, key=lambda e: e.stage_number):
        if entry.stage_number == except_stage or entry.stage_number == STAGE_INTAKE:
            continue
        if only_stages is not None and entry.stage_number not in only_stages:
            continue
        if entry.status not in ENTRY_DONE:
            continue
        values = []
        for name, value in (entry.payload or {}).items():
            if value in (None, "", [], False):
                continue
            if isinstance(value, list):
                value = "، ".join(str(v) for v in value if v not in (None, ""))
                if not value:
                    continue
            values.append({"label": labels.get(name, name), "value": str(value)})
        if not values and not entry.note:
            continue
        out.append({
            "stage_number": entry.stage_number,
            "title": entry.stage.title if entry.stage else "",
            "status": entry.status,
            "status_label": ENTRY_STATUS.get(entry.status, entry.status),
            "user_name": entry.user.full_name if entry.user else None,
            "submitted_at_j": (to_jalali_str(entry.submitted_at)
                               if entry.submitted_at else None),
            "note": entry.note,
            "values": values,
        })
    return out


# ── running an instance ──────────────────────────────────────────────────────
def _entry_for(instance: WorkflowInstance, stage_number: int):
    return next((e for e in instance.entries
                 if e.stage_number == stage_number), None)


def _ensure_entry(instance: WorkflowInstance, stage: WorkflowStage):
    entry = _entry_for(instance, stage.stage_number)
    if entry is None:
        entry = WorkflowStageEntry(instance_id=instance.id, stage_id=stage.id,
                                   stage_number=stage.stage_number,
                                   status=ENTRY_PENDING)
        db.session.add(entry)
        instance.entries.append(entry)
    return entry


def may_start(user) -> bool:
    """Whether ``user`` may open a process of any kind at all.

    Opening is the job of whoever owns a stage marked «می‌تواند فرایند را شروع
    کند», not of every stage owner — otherwise each person in the chain has a
    button that makes work for everybody else.
    """
    return bool(startable_kinds(user))


def start_instance(payload: dict, user) -> WorkflowInstance:
    """Answer step zero and open a process."""
    workflow = active_workflow()
    if workflow is None:
        raise WorkflowError("هیچ فرایند فعالی تعریف نشده است.")
    allowed = startable_kinds(user)
    if not allowed:
        raise WorkflowError("شروع فرایند با متولی مرحله‌ای است که در فرایندساز "
                            "«می‌تواند فرایند را شروع کند» علامت خورده باشد. "
                            "از مدیر سیستم بخواهید شما را متولی آن مرحله کند.")
    # Either the Persian label the form shows or the key the API speaks —
    # the کارتابل builds its radios from the server's own list of startable
    # operations, which carries both, and a caller should not have to know
    # which of the two this end expects.
    kind_value = normalize_text(payload.get("operation_kind") or "")
    kind = next((k for k, label in OPERATION_KINDS.items()
                 if kind_value in (k, normalize_text(label))), None)
    if kind is None:
        raise WorkflowError("نوع عملیات را انتخاب کنید: "
                            + " یا ".join(OPERATION_KINDS.values()) + ".")
    if kind not in allowed:
        raise WorkflowError(
            f"شروع عملیات «{OPERATION_KINDS[kind]}» با شما نیست؛ این عملیات از "
            f"مرحله‌ی دیگری آغاز می‌شود. شما می‌توانید "
            + "، ".join(OPERATION_KINDS[k] for k in allowed) + " را شروع کنید.")

    # The well is settled here and nowhere else: every later stage is shown it
    # locked, so it must be a real well from the register before we start.
    if not normalize_text(payload.get("well") or ""):
        raise WorkflowError("نام چاه را انتخاب کنید؛ چاه در همین مرحله یک‌بار "
                            "تعیین می‌شود و در مرحله‌های بعد تکرار نمی‌شود.")
    well, raw = resolve_well(payload.get("well"), create_missing=False)
    if well is None:
        raise WorkflowError(f"چاهی با نام «{raw}» در فهرست چاه‌ها نیست. "
                            f"از فهرست پیشنهادی یک چاه را انتخاب کنید.")
    door = door_of(workflow, kind, user)
    start_at = (door.stage_number if door is not None
                else first_stage_number(kind, workflow))
    instance = WorkflowInstance(
        workflow_id=workflow.id, operation_kind=kind,
        well_id=well.id if well else None, well_name_raw=raw,
        current_stage=start_at, entry_stage=start_at, status=INSTANCE_OPEN,
        created_by=user.id if user else None)
    # The مرکز is decided by the well, not by whoever fills the form, so it
    # is settled here with the well and shown locked from then on.
    opening = {"operation_kind": OPERATION_KINDS[kind]}
    if well is not None and well.center is not None:
        opening["center"] = well.center.label
    instance.set_payload(opening)
    db.session.add(instance)
    db.session.flush()

    # Step zero — when the process still has one — is answered by the act of
    # starting, so record it as submitted and hand the process straight on. A
    # process whose start stage is a real form has no step zero to answer.
    intake = next((s for s in workflow.stages
                   if s.stage_number == STAGE_INTAKE and s.is_active), None)
    if intake is not None:
        entry = _ensure_entry(instance, intake)
        entry.status = ENTRY_SUBMITTED
        entry.user_id = user.id if user else None
        entry.submitted_at = local_now()
        entry.set_payload({"operation_kind": OPERATION_KINDS[kind]})
    sync_entries(instance)
    refresh_position(instance)
    record_audit("create", "workflow", instance.id,
                 summary=f"شروع فرایند {OPERATION_KINDS[kind]}"
                         + (f" برای «{well.name}»" if well else ""))
    db.session.commit()
    return instance


def applicable_stages(instance: WorkflowInstance) -> list:
    """Stages this instance's branch actually visits, in order.

    Step zero is excluded: it is answered by the act of starting.
    """
    kind = instance.operation_kind
    start = (instance.entry_stage if instance.entry_stage is not None
             else first_stage_number(kind, instance.workflow))
    return [s for s in sorted(instance.workflow.stages, key=lambda x: x.stage_number)
            if s.is_active and s.stage_number > STAGE_INTAKE
            and s.stage_number >= start
            and _kind_matches(s.applies_to, kind)]


def sync_entries(instance: WorkflowInstance):
    """Make sure every stage has an entry, and mark the ones this branch skips.

    Stages do not wait on each other, so every applicable stage gets a pending
    entry as soon as the process starts. Each owner can open theirs whenever
    they like; the ones the branch never visits are marked as such so the
    tracking view does not show them as outstanding.
    """
    applicable = {s.stage_number for s in applicable_stages(instance)}
    for stage in instance.workflow.stages:
        if stage.stage_number == STAGE_INTAKE:
            continue
        entry = _ensure_entry(instance, stage)
        if stage.stage_number in applicable:
            if entry.status == ENTRY_SKIPPED:
                entry.status = ENTRY_PENDING
                entry.note = None
        elif entry.status == ENTRY_PENDING:
            entry.status = ENTRY_SKIPPED
            entry.note = ("این مرحله در عملیات "
                          f"«{OPERATION_KINDS.get(instance.operation_kind, '')}» "
                          "طی نمی‌شود.")


def blocking_approvals(instance: WorkflowInstance) -> list:
    """Stages whose approval is still owed and which hold the process up.

    «تا زمانی که ایکس تأیید نکند نمی‌توان ادامه داد» is a per-stage setting,
    so this is a list rather than a rule: a stage marked ``approval_blocks``
    and still waiting on its approver stops every later stage. Stages *before*
    it carry on — their work is already behind the thing being approved.
    """
    out = []
    for stage in applicable_stages(instance):
        if not (stage.needs_approval and stage.approval_blocks):
            continue
        entry = _entry_for(instance, stage.stage_number)
        if entry is not None and entry.status == ENTRY_AWAITING:
            out.append(stage)
    return out


def blocked_by(instance: WorkflowInstance, stage_number: int):
    """The blocking approval standing in front of ``stage_number``, if any."""
    for stage in blocking_approvals(instance):
        if stage.stage_number < stage_number:
            return stage
    return None


def pending_stages(instance: WorkflowInstance) -> list:
    """Applicable stages nobody has submitted yet."""
    done = {e.stage_number for e in instance.entries
            if e.status in ENTRY_DONE}
    return [s for s in applicable_stages(instance) if s.stage_number not in done]


def waiting_before(instance: WorkflowInstance, stage_number: int) -> list:
    """Earlier stages that have not reported in yet.

    Not a blocker — stage 3 can record the motor without waiting for stage 2 —
    but the owner is told, because filling a form whose input has not arrived
    is usually a mistake worth noticing.
    """
    return [s for s in pending_stages(instance) if s.stage_number < stage_number]


def refresh_position(instance: WorkflowInstance):
    """Point ``current_stage`` at the earliest stage still owed."""
    pending = pending_stages(instance)
    instance.current_stage = (pending[0].stage_number if pending
                              else last_stage_number(instance.workflow))
    return pending


def current_stage_of(instance: WorkflowInstance) -> WorkflowStage | None:
    return next((s for s in instance.workflow.stages
                 if s.stage_number == instance.current_stage), None)


def stage_by_number(instance: WorkflowInstance, number: int):
    return next((s for s in instance.workflow.stages
                 if s.stage_number == number), None)


def owners_of(instance: WorkflowInstance, stage: WorkflowStage) -> list:
    """Whose کارتابل this stage sits in, on this run.

    Normally the stage's standing متولی‌ها — a list, because one stage can
    belong to all eight مراکز آبرسانی at once. Two things narrow it:

    * a referral — «ارجاع به کارگاه مکانیک» — puts this one job with one
      particular person, and an approval puts it with the approver until they
      have ruled; the entry knows, the stage only knows the default;
    * «فقط متولی مرکز چاه», which keeps the owner whose مرکز is this well's, so
      the other seven centres are not shown somebody else's job.
    """
    entry = _entry_for(instance, stage.stage_number)
    if entry is not None and entry.pinned_owner_ids:
        return list(entry.pinned_owner_ids)
    people = stage.all_owners
    # A disabled account cannot open its کارتابل, so work must not rest there
    # while somebody else on the stage could do it. If every owner is disabled
    # the list stays as it is — the stage is then visibly stuck, which is the
    # truth, rather than silently ownerless.
    live = [u for u in people if u.is_active]
    people = live or people
    if stage.route_by_center:
        people = _for_this_center(people, instance)
    return [u.id for u in people]


def _for_this_center(people: list, instance: WorkflowInstance) -> list:
    """Narrow a stage's owners to the one who answers for this well's مرکز.

    Nobody is narrowed out by a centre they were never given: if no owner
    claims this well's مرکز, the stage stays with all of them rather than
    falling into a کارتابل nobody reads.
    """
    well = instance.well
    center_id = well.center_id if well is not None else None
    if center_id is None:
        return people
    matching = [u for u in people
                if any(c.id == center_id for c in u.centers)]
    return matching or people


def owner_of(instance: WorkflowInstance, stage: WorkflowStage):
    """The one name to show for this stage — the first of its owners."""
    people = owners_of(instance, stage)
    return people[0] if people else None


def stages_of_user(instance: WorkflowInstance, user) -> list:
    """Which applicable stages this person holds on this instance."""
    if user is None:
        return []
    return [s for s in applicable_stages(instance)
            if user.id in owners_of(instance, s)]


def may_act(user, instance: WorkflowInstance, stage: WorkflowStage = None) -> bool:
    """Whether ``user`` may fill ``stage`` (or any stage) of this instance."""
    if user is None or instance.status != INSTANCE_OPEN:
        return False
    if user.role == "admin" or user.can("workflow.manage"):
        return True
    if stage is not None:
        return user.id in owners_of(instance, stage)
    return bool(stages_of_user(instance, user))


def awaiting_approval(instance: WorkflowInstance, user) -> list:
    """Stages of this run that are sitting with ``user`` for a decision."""
    if user is None:
        return []
    manager = user.role == "admin" or user.can("workflow.manage")
    out = []
    for stage in applicable_stages(instance):
        entry = _entry_for(instance, stage.stage_number)
        if entry is None or entry.status != ENTRY_AWAITING:
            continue
        if manager or entry.approver_id == user.id:
            out.append(stage)
    return out


def submit_stage(instance: WorkflowInstance, payload: dict, user,
                 note: str | None = None,
                 stage_number: int | None = None,
                 refer_to: int | None = None,
                 referral_note: str | None = None,
                 share_stages: list | None = None) -> WorkflowInstance:
    """Record one stage's answers, then hand the work on.

    Stages are independent: the owner of stage 3 does not wait for stage 2.
    The process completes on its own once no applicable stage is outstanding,
    whichever order they came in.

    What happens after the answers are stored depends on how the admin set the
    stage up. If it needs an approval, the entry goes to the approver and the
    process waits. Otherwise the next stage is referred onward — to its own
    متولی, to a fixed person, or to whoever ``refer_to`` names.
    """
    if instance.status != INSTANCE_OPEN:
        raise WorkflowError("این فرایند بسته شده است.")
    sync_entries(instance)

    if stage_number is None:
        owned = stages_of_user(instance, user)
        pending_owned = [s for s in owned if s in pending_stages(instance)]
        stage = (pending_owned or owned or [current_stage_of(instance)])[0]
    else:
        stage = stage_by_number(instance, stage_number)
    if stage is None:
        raise WorkflowError("مرحله‌ی موردنظر در این فرایند پیدا نشد.")
    if stage.stage_number not in {s.stage_number for s in applicable_stages(instance)}:
        raise WorkflowError(
            f"مرحله «{stage.title}» در عملیات "
            f"«{OPERATION_KINDS.get(instance.operation_kind, '')}» طی نمی‌شود.")
    if not may_act(user, instance, stage):
        holders = [db.session.get(AppUser, i).full_name
                   for i in owners_of(instance, stage)
                   if db.session.get(AppUser, i) is not None]
        owner = "، ".join(holders) if holders else "تعیین‌نشده"
        raise WorkflowError(f"مرحله «{stage.title}» در اختیار «{owner}» است.")
    # An approval the admin marked as blocking is exactly that: nothing after
    # that stage may be recorded until its approver has ruled.
    hold = blocked_by(instance, stage.stage_number)
    if hold is not None:
        who = hold.approver.full_name if hold.approver else "تأییدکننده"
        raise WorkflowError(
            f"مرحله «{hold.title}» در انتظار تأیید «{who}» است و تا زمانی که "
            f"تأیید نشود، مرحله‌های بعدی ثبت نمی‌شوند.")

    # When several people share one stage, what an earlier one of them wrote
    # counts — the second is confirming the form, not typing it again.
    shared = _entry_for(instance, stage.stage_number)
    so_far = (shared.payload or {}) if shared is not None and shared.refer_all \
        else {}
    missing = _missing_required(instance, stage, {**so_far, **(payload or {})})
    if missing:
        raise WorkflowError(
            "این مرحله کامل نیست؛ " + str(len(missing))
            + " مورد الزامی پر نشده است.", fields=missing)

    merged = dict(instance.payload)
    merged.update(payload or {})
    entry = _ensure_entry(instance, stage)

    # Referred to several people who must *all* record: this submission is one
    # of theirs. Keep what they wrote, note that they are done, and hold the
    # stage until the last of them has recorded too. An admin stepping in
    # closes it outright.
    if entry.refer_all and user is not None and user.id in entry.recipient_ids:
        done = entry.done_ids
        if user.id not in done:
            done.append(user.id)
        left = [p for p in entry.recipient_ids if p not in done]
        if left:
            entry.done_by_ids = ",".join(str(x) for x in done)
            entry.set_payload({**(entry.payload or {}), **(payload or {})})
            instance.set_payload(merged)
            record_audit("update", "workflow", instance.id,
                         summary=f"ثبت سهم «{user.full_name}» در مرحله "
                                 f"{stage.stage_number} «{stage.title}»؛ "
                                 f"{len(left)} نفر دیگر مانده")
            db.session.commit()
            return instance
        entry.done_by_ids = ",".join(str(x) for x in done)
        payload = {**(entry.payload or {}), **(payload or {})}

    if carries_well_install(stage):
        state = well_install_state(instance.operation_kind, merged)
        if state == "ask":
            raise WorkflowError("ابتدا «اقدام مورد نیاز» را مشخص کنید.")
        if state == "archived":
            entry.status = ENTRY_ARCHIVED
            entry.note = (f"اقدام مورد نیاز «{merged.get('required_action')}» "
                          f"است، بنابراین «اطلاعات چاه و نصب» بایگانی شد.")
        elif state == "deferred":
            entry.status = ENTRY_DEFERRED
            entry.note = ("تیپ الکتروپمپ در این مرحله انتخاب نشد؛ "
                          "«اطلاعات چاه و نصب» به بعد موکول شد.")
        else:
            entry.status = ENTRY_SUBMITTED
    else:
        entry.status = ENTRY_SUBMITTED

    if note:
        entry.note = ((entry.note + " ") if entry.note else "") + note
    entry.user_id = user.id if user else None
    entry.submitted_at = local_now()
    entry.set_payload(payload or {})
    instance.set_payload(merged)

    # An approval holds the work here until somebody rules on it; only then is
    # it referred onward. Anything else goes on its way immediately.
    if entry.status == ENTRY_SUBMITTED and stage.needs_approval:
        approver = _approver_for(stage)
        if approver is None:
            raise WorkflowError(
                f"مرحله «{stage.title}» نیاز به تأیید دارد ولی تأییدکننده‌ای "
                f"برایش تعیین نشده است. از مدیر سیستم بخواهید در فرایندساز "
                f"تأییدکننده را مشخص کند.")
        entry.status = ENTRY_AWAITING
        entry.approver_id = approver
        entry.shared_stages = _shared_for(stage, share_stages)
        entry.decided_by_id = entry.decided_at = entry.decision_note = None
        record_audit("update", "workflow", instance.id,
                     summary=f"ارسال مرحله {stage.stage_number} "
                             f"«{stage.title}» برای تأیید")
    else:
        _refer_onward(instance, stage, user, refer_to, referral_note)

    # A well named at any stage belongs to the instance, not just the payload.
    if payload and payload.get("well") and not instance.well_id:
        well, raw = resolve_well(payload["well"], create_missing=False)
        instance.well_id = well.id if well else None
        instance.well_name_raw = raw

    record_audit("update", "workflow", instance.id,
                 summary=f"ثبت مرحله {stage.stage_number} «{stage.title}»")

    if not refresh_position(instance):
        finalize(instance, user)
    db.session.commit()
    return instance


def _shared_for(stage: WorkflowStage, chosen: list | None) -> str | None:
    """What this referral opens to the approver, as the entry stores it.

    The admin sets the rule on the stage; «ثبت‌کننده انتخاب می‌کند» hands the
    choice to the person sending it. An empty choice there is an answer, not a
    missing one: it means «only the stage I am sending», which is exactly what
    unticking everything says. ``None`` means no choice was offered at all, and
    then the default — everything recorded so far — stands.
    """
    if stage.approval_sees == SEE_STAGE:
        return str(stage.stage_number)
    if stage.approval_sees == SEE_PICK and chosen is not None:
        numbers = {int(n) for n in chosen if str(n).lstrip("-").isdigit()}
        # The stage being approved is always in it — that is the thing being
        # judged, and leaving it out makes the decision meaningless.
        numbers.add(stage.stage_number)
        return ",".join(str(n) for n in sorted(numbers))
    return None                     # everything recorded so far


def shareable_stages(instance: WorkflowInstance, stage: WorkflowStage) -> list:
    """The stages a sender may open to the approver, with what each holds."""
    out = []
    for other in applicable_stages(instance):
        if other.stage_number == stage.stage_number:
            continue
        entry = _entry_for(instance, other.stage_number)
        if entry is None or entry.status not in ENTRY_DONE:
            continue
        filled = len([v for v in (entry.payload or {}).values()
                      if v not in (None, "", [], {}, False)])
        out.append({"stage_number": other.stage_number, "title": other.title,
                    "field_count": filled,
                    "owner": (entry.user.full_name if entry.user else None)})
    return out


# ── referrals ────────────────────────────────────────────────────────────────
def _approver_for(stage: WorkflowStage):
    """Who signs this stage off. Falls back to nobody rather than guessing."""
    return stage.approver_id


def next_stage_after(instance: WorkflowInstance, stage_number: int):
    """The next stage of this run that is still owed."""
    return next((s for s in pending_stages(instance)
                 if s.stage_number > stage_number), None)


def _users(ids) -> list:
    """Users by id, in the given order, skipping any that are gone."""
    out = []
    for i in ids or []:
        person = db.session.get(AppUser, int(i))
        if person is not None:
            out.append(person)
    return out


def referral_progress(entry) -> dict | None:
    """Who a shared hand-off went to, and who of them has recorded."""
    if entry is None or not entry.recipient_ids:
        return None
    done = entry.done_ids
    return {
        "all_must": entry.refer_all,
        "people": [{"id": p.id, "full_name": p.full_name,
                    "done": p.id in done}
                   for p in _users(entry.recipient_ids)],
    }


def referral_choices(instance: WorkflowInstance, stage: WorkflowStage) -> dict:
    """What the submit form should offer for «ارجاع به».

    Only meaningful for a stage the admin set to ``choose``; the other modes
    decide by themselves and the page shows who it will go to.
    """
    target = next_stage_after(instance, stage.stage_number)
    data = {
        "mode": stage.referral_mode,
        "hint": stage.referral_hint,
        "needs_approval": stage.needs_approval,
        "approver_name": stage.approver.full_name if stage.approver else None,
        "next_stage": (
            {"stage_number": target.stage_number, "title": target.title,
             "assignee_name": (target.assignee.full_name
                               if target.assignee else None)}
            if target else None),
        "default_user_id": stage.referral_user_id,
        "default_user_name": (stage.referral_user.full_name
                              if stage.referral_user else None),
        "default_user_ids": stage.referral_ids,
        "default_user_names": [p.full_name for p in _users(stage.referral_ids)],
        "refer_all": stage.refer_all,
        "users": [],
    }
    if stage.referral_mode == REFER_CHOOSE:
        from ..models.auth import AppUser
        data["users"] = [
            {"id": u.id, "full_name": u.full_name, "username": u.username,
             "role_label": u.role_label}
            for u in AppUser.query.filter_by(is_active=True)
            .order_by(AppUser.first_name, AppUser.username).all()]
    return data


def _refer_onward(instance, stage, user, refer_to=None, referral_note=None):
    """Put the next stage in somebody's کارتابل, by name.

    «ارجاع به کارگاه مکانیک جهت دمونتاژ» is not a figure of speech in this
    workshop: the next person is chosen when the work is handed over, and the
    handover is recorded — who sent it, to whom, and what they said.
    """
    target = next_stage_after(instance, stage.stage_number)
    if target is None:
        return None
    entry = _ensure_entry(instance, target)
    if entry.status not in (ENTRY_PENDING, ENTRY_REJECTED):
        return None                       # already dealt with; leave it alone

    if stage.referral_mode == REFER_USER:
        chosen = stage.referral_ids
    elif stage.referral_mode == REFER_CHOOSE:
        # One id or several — «ارجاع به دفتر فنی و بهره‌بردار» picks two.
        picked = refer_to if isinstance(refer_to, (list, tuple)) else [refer_to]
        chosen = [int(x) for x in picked if str(x or "").strip().isdigit()]
        chosen = chosen or stage.referral_ids
    else:
        chosen = []                       # the next stage's own متولی
    if not chosen:
        return None

    from ..models.auth import AppUser
    people = []
    for pid in dict.fromkeys(chosen):
        person = db.session.get(AppUser, int(pid))
        if person is None or not person.is_active:
            raise WorkflowError("کاربری که کار به او ارجاع شده پیدا نشد یا "
                                "غیرفعال است.")
        people.append(person)
    entry.status = ENTRY_PENDING
    entry.referred_to_id = people[0].id
    entry.referred_to_ids = ",".join(str(p.id) for p in people)
    # «همه باید ثبت کنند» only means something with more than one recipient.
    entry.refer_all = bool(stage.refer_all and len(people) > 1)
    entry.done_by_ids = None
    entry.referred_by_id = user.id if user else None
    entry.referred_at = local_now()
    entry.referral_note = referral_note or None
    names = "، ".join(p.full_name for p in people)
    record_audit("update", "workflow", instance.id,
                 summary=f"ارجاع مرحله {target.stage_number} «{target.title}» "
                         f"به «{names}»"
                         + (" (همه باید ثبت کنند)" if entry.refer_all else ""))
    return entry


def decide_stage(instance: WorkflowInstance, stage_number: int, user,
                 approved: bool, comment: str | None = None):
    """Approve a stage, or send it back to be redone.

    A rejection is not a dead end — it returns the work to whoever filled it
    (or to whichever stage the admin nominated) with the reason attached, so
    «برگشت به کارگاه جهت اصلاح» is a round trip rather than a full stop.
    """
    if instance.status != INSTANCE_OPEN:
        raise WorkflowError("این فرایند بسته شده است.")
    stage = stage_by_number(instance, stage_number)
    entry = _entry_for(instance, stage_number)
    if stage is None or entry is None:
        raise WorkflowError("مرحله‌ی موردنظر پیدا نشد.")
    if entry.status != ENTRY_AWAITING:
        raise WorkflowError(f"مرحله «{stage.title}» در انتظار تأیید نیست.")
    manager = user is not None and (user.role == "admin"
                                    or user.can("workflow.manage"))
    if not manager and entry.approver_id != (user.id if user else None):
        raise WorkflowError("تأیید این مرحله در اختیار شما نیست.")
    if not approved and not (comment or "").strip():
        raise WorkflowError("برای برگشت دادن، ذکر دلیل الزامی است.")

    entry.decided_by_id = user.id if user else None
    entry.decided_at = local_now()
    entry.decision_note = comment or None

    if approved:
        entry.status = ENTRY_SUBMITTED
        record_audit("update", "workflow", instance.id,
                     summary=f"تأیید مرحله {stage.stage_number} «{stage.title}»")
        _refer_onward(instance, stage, user)
        if not refresh_position(instance):
            finalize(instance, user)
    else:
        back = (stage_by_number(instance, stage.reject_to_stage)
                if stage.reject_to_stage is not None else None) or stage
        target = _ensure_entry(instance, back)
        target.status = ENTRY_REJECTED
        target.referred_to_id = entry.user_id or target.referred_to_id
        target.referred_by_id = user.id if user else None
        target.referred_at = local_now()
        target.referral_note = comment
        target.note = (f"برگشت از «{stage.title}»: {comment}")
        if back.stage_number != stage.stage_number:
            entry.status = ENTRY_PENDING        # this stage waits to re-judge
        record_audit("update", "workflow", instance.id,
                     summary=f"برگشت مرحله {stage.stage_number} "
                             f"«{stage.title}» به «{back.title}»")
        refresh_position(instance)
    db.session.commit()
    return instance


def finalize(instance: WorkflowInstance, user) -> Record:
    """Turn a finished process into a row in ``records``.

    Reached when no applicable stage is outstanding — usually the moment the
    last stage signs off, but equally when a straggler finally reports in after
    everyone else has finished.
    """
    payload = dict(instance.payload)
    if instance.well_id and not payload.get("well"):
        payload["well"] = instance.well.name
    # The centre is shown locked rather than asked, so it never comes back in
    # a stage's answers — read it from the well instead of losing it.
    if (instance.well_id and not payload.get("center")
            and instance.well.center is not None):
        payload["center"] = instance.well.center.label
    try:
        record = create_record(payload)
    except ValidationError as exc:
        # Do not lose the process over a missing field — say which one.
        names = "، ".join(sorted(k for k in exc.errors
                                 if not k.startswith("__"))) or "نامشخص"
        raise WorkflowError(
            "ثبت نهایی ممکن نشد؛ این فیلدها کامل نیستند: " + names) from exc
    instance.record_id = record.id
    instance.status = INSTANCE_COMPLETED
    instance.completed_at = local_now()
    instance.current_stage = last_stage_number(instance.workflow)
    record_audit("create", "workflow", instance.id,
                 summary=f"فرایند تکمیل و رکورد #{record.id} ثبت شد")
    log.info("Workflow %s finalised into record %s", instance.id, record.id)
    return record


def cancel_instance(instance: WorkflowInstance, reason: str, user):
    instance.status = INSTANCE_CANCELLED
    for entry in instance.entries:
        if entry.status == ENTRY_PENDING:
            entry.status = ENTRY_SKIPPED
    record_audit("delete", "workflow", instance.id,
                 summary=f"لغو فرایند: {reason or 'بدون توضیح'}")
    db.session.commit()
    return instance


# ── «قبلی» fields ────────────────────────────────────────────────────────────
# What this operation installs becomes what the next one finds. Each pair is
# (field to fill now, where to read it from on the previous record).
PREVIOUS_SOURCES = {
    "motor_prev": "motor_curr_id",
    "pump_prev": "pump_curr_id",
    "pump_prev_stages": "pump_stages",
    "prev_install_depth": "curr_install_depth",
}


def previous_values_for(well_id, before_record_id=None) -> dict:
    """The «…قبلی» answers, read off this well's last operation.

    Returned as suggestions, never as settled facts: the form fills them in and
    leaves them editable, because the register is not always right and the
    person standing at the well is.
    """
    if not well_id:
        return {}
    from .records import _label

    query = (Record.query.filter(Record.well_id == well_id,
                                 Record.is_active.is_(True))
             .order_by(Record.op_date.desc().nullslast(), Record.id.desc()))
    if before_record_id:
        query = query.filter(Record.id != before_record_id)
    previous = query.first()
    if previous is None:
        return {}

    values = {}
    for target, source in PREVIOUS_SOURCES.items():
        raw = getattr(previous, source, None)
        value = _label(raw) if source.endswith("_id") else raw
        if value not in (None, ""):
            values[target] = value
    if previous.op_date:
        from .jalali import to_jalali_str
        values["prev_install_date"] = to_jalali_str(previous.op_date)
    if previous.j_year:
        values["old_install_year"] = previous.j_year
    if previous.j_month:
        from .jalali import MONTHS_FA
        values["old_install_month"] = MONTHS_FA[previous.j_month]
    return {
        "values": values,
        "source": {
            "record_id": previous.id,
            "date": (f"{previous.j_year}/{previous.j_month:02d}/"
                     f"{previous.j_day:02d}" if previous.j_year else None),
            "operation": _label(previous.operation_id),
        },
    }
