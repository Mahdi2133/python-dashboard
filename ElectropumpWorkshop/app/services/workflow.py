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
from ..models import (FormField, FormSection, Record, WorkflowAttachment,
                      WorkflowDefinition, WorkflowInstance, WorkflowStage,
                      WorkflowStageEntry, WorkflowStageItem)
from ..models.workflow import (APPLIES_BOTH, ENTRY_ARCHIVED, ENTRY_DEFERRED,
                               ENTRY_STATUS,
                               ENTRY_PENDING, ENTRY_SKIPPED, ENTRY_SUBMITTED,
                               INSTANCE_CANCELLED, INSTANCE_COMPLETED,
                               INSTANCE_OPEN, OPERATION_INSTALL, OPERATION_KINDS,
                               OPERATION_PULL)
from .audit import record_audit
from .jalali import local_now, to_jalali_str
from .lookups import normalize_text
from .records import ValidationError, create_record, resolve_well

log = logging.getLogger(__name__)

# The one answer that keeps «اطلاعات چاه و نصب» open at stage 4.
ACTION_NEW_PUMP = "نصب الکتروپمپ جدید"
STAGE_INTAKE = 0
STAGE_FIRST_PULL = 1
STAGE_FIRST_INSTALL = 3
STAGE_WELL_INSTALL = 4
STAGE_FINAL = 5


class WorkflowError(Exception):
    """A process rule refused the move. Carries a Persian message."""


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


def first_stage_number(kind: str | None) -> int:
    """Where the real work starts once step zero is answered."""
    return STAGE_FIRST_INSTALL if kind == OPERATION_INSTALL else STAGE_FIRST_PULL


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
            if item.section:
                owned.add(("section", item.section.code))
            elif item.field:
                owned.add(("field", item.field.field_name))
    return owned


def stage_items(instance: WorkflowInstance, stage: WorkflowStage,
                payload: dict | None = None) -> list:
    """The sections and fields this stage asks for, on this instance."""
    kind = instance.operation_kind
    merged = dict(instance.payload)
    merged.update(payload or {})
    owned = _already_owned(instance, stage.stage_number)
    state = (well_install_state(kind, merged)
             if stage.stage_number == STAGE_WELL_INSTALL else "show")

    visible = []
    for item in stage.items:
        if not _kind_matches(item.applies_to, kind):
            continue
        key = (("section", item.section.code) if item.section
               else ("field", item.field.field_name) if item.field else None)
        if key is None or key in owned:
            continue
        if (stage.stage_number == STAGE_WELL_INSTALL
                and item.section is not None
                and item.section.code == "well_install"
                and state != "show"):
            continue          # archived or deferred by the action decision
        visible.append(item)
    return visible


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
            kept.append(field)
        return kept

    blocks = []
    for item in stage_items(instance, stage, draft):
        if item.section:
            block = item.section.to_dict(include_fields=True, active_only=True)
            block["fields"] = usable(block.get("fields") or [])
            if not block["fields"]:
                continue
            block["is_optional"] = item.is_optional
            blocks.append(block)
        elif item.field:
            fields = usable([item.field.to_dict()])
            if not fields:
                continue
            blocks.append({
                "id": None, "code": f"field_{item.field.field_name}",
                "title": item.field.label, "icon": "◽", "columns": 1,
                "full_width": True, "is_active": True,
                "is_optional": item.is_optional,
                "description": None,
                "fields": fields,
            })
    return {
        "stage": stage.to_dict(),
        "sections": blocks,
        "well_install_state": (well_install_state(
                                   instance.operation_kind,
                                   {**instance.payload, **(draft or {})})
                               if stage.stage_number == STAGE_WELL_INSTALL
                               else None),
    }


def submitted_summary(instance: WorkflowInstance, except_stage: int = None) -> list:
    """What the other stages have already recorded, ready to show read-only.

    Whoever is holding the process needs to see the work behind it — the
    engineer at stage 5 signs off on what four people before him wrote — but
    none of it is his to change, so it is handed over as labelled text rather
    than as fields.
    """
    labels = {f.field_name: f.label for f in FormField.query.all()}
    out = []
    for entry in sorted(instance.entries, key=lambda e: e.stage_number):
        if entry.stage_number == except_stage or entry.stage_number == STAGE_INTAKE:
            continue
        if entry.status not in (ENTRY_SUBMITTED, ENTRY_ARCHIVED, ENTRY_DEFERRED):
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


def start_instance(payload: dict, user) -> WorkflowInstance:
    """Answer step zero and open a process."""
    workflow = active_workflow()
    if workflow is None:
        raise WorkflowError("هیچ فرایند فعالی تعریف نشده است.")
    kind_value = normalize_text(payload.get("operation_kind") or "")
    kind = next((k for k, label in OPERATION_KINDS.items()
                 if normalize_text(label) == kind_value), None)
    if kind is None:
        raise WorkflowError("نوع عملیات را انتخاب کنید: کشیدن یا نصب.")

    well, raw = resolve_well(payload.get("well"), create_missing=False)
    instance = WorkflowInstance(
        workflow_id=workflow.id, operation_kind=kind,
        well_id=well.id if well else None, well_name_raw=raw,
        current_stage=STAGE_INTAKE, status=INSTANCE_OPEN,
        created_by=user.id if user else None)
    instance.set_payload({"operation_kind": OPERATION_KINDS[kind]})
    db.session.add(instance)
    db.session.flush()

    # Step zero is answered by the act of starting, so record it as submitted
    # and hand the process straight to the first real stage.
    intake = next((s for s in workflow.stages
                   if s.stage_number == STAGE_INTAKE), None)
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
    start = first_stage_number(kind)
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


def pending_stages(instance: WorkflowInstance) -> list:
    """Applicable stages nobody has submitted yet."""
    done = {e.stage_number for e in instance.entries
            if e.status in (ENTRY_SUBMITTED, ENTRY_ARCHIVED, ENTRY_DEFERRED)}
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
                              else STAGE_FINAL)
    return pending


def current_stage_of(instance: WorkflowInstance) -> WorkflowStage | None:
    return next((s for s in instance.workflow.stages
                 if s.stage_number == instance.current_stage), None)


def stage_by_number(instance: WorkflowInstance, number: int):
    return next((s for s in instance.workflow.stages
                 if s.stage_number == number), None)


def stages_of_user(instance: WorkflowInstance, user) -> list:
    """Which applicable stages this person owns on this instance."""
    if user is None:
        return []
    return [s for s in applicable_stages(instance) if s.assignee_id == user.id]


def may_act(user, instance: WorkflowInstance, stage: WorkflowStage = None) -> bool:
    """Whether ``user`` may fill ``stage`` (or any stage) of this instance."""
    if user is None or instance.status != INSTANCE_OPEN:
        return False
    if user.role == "admin" or user.can("workflow.manage"):
        return True
    if stage is not None:
        return stage.assignee_id == user.id
    return bool(stages_of_user(instance, user))


def submit_stage(instance: WorkflowInstance, payload: dict, user,
                 note: str | None = None,
                 stage_number: int | None = None) -> WorkflowInstance:
    """Record one stage's answers.

    Stages are independent: the owner of stage 3 does not wait for stage 2.
    The process completes on its own once no applicable stage is outstanding,
    whichever order they came in.
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
        owner = stage.assignee.full_name if stage.assignee else "تعیین‌نشده"
        raise WorkflowError(f"مرحله «{stage.title}» در اختیار «{owner}» است.")

    merged = dict(instance.payload)
    merged.update(payload or {})
    entry = _ensure_entry(instance, stage)

    if stage.stage_number == STAGE_WELL_INSTALL:
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


def finalize(instance: WorkflowInstance, user) -> Record:
    """Turn a finished process into a row in ``records``.

    Reached when no applicable stage is outstanding — usually the moment the
    last stage signs off, but equally when a straggler finally reports in after
    everyone else has finished.
    """
    payload = dict(instance.payload)
    if instance.well_id and not payload.get("well"):
        payload["well"] = instance.well.name
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
    instance.current_stage = STAGE_FINAL
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
