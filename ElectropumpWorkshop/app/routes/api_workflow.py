# -*- coding: utf-8 -*-
"""/api/workflow — the process builder, the کارتابل, and process tracking."""
import mimetypes
import os
import secrets

from flask import Blueprint, Response, request, send_file

from ..extensions import db
from ..models import (AppUser, FormField, FormSection, WorkflowAttachment,
                      WorkflowDefinition, WorkflowInstance, WorkflowStage,
                      WorkflowStageEntry, WorkflowStageItem)
from ..models.workflow import (APPLIES_TO, ENTRY_AWAITING, ENTRY_DONE,
                               ENTRY_PENDING, ENTRY_STATUS, INSTANCE_OPEN,
                               INSTANCE_STATUS, OPERATION_KINDS,
                               REFERRAL_MODES, REFER_CHOOSE, REFER_USER)
from ..paths import instance_dir
from ..services.audit import record_audit
from ..services.auth import (current_user, login_required,
                             permission_required,
                             permission_required_any)
from ..services.jalali import to_jalali_str
from ..services.lookups import normalize_text
from ..services.workflow import (WorkflowError, active_workflow,
                                 applicable_stages, awaiting_approval,
                                 cancel_instance, current_stage_of,
                                 decide_stage, may_act, owner_of,
                                 owners_of, startable_kinds,
                                 entry_stage,
                                 pending_stages, previous_values_for,
                                 may_start, referral_choices, stage_by_number,
                                 stage_form, stages_of_user,
                                 submitted_summary,
                                 start_instance, submit_stage, sync_entries,
                                 waiting_before)
from ._helpers import body, fail, ok, paging

bp = Blueprint("api_workflow", __name__, url_prefix="/api/workflow")

# Anything the workshop might photograph, scan or export. The list is a guard
# against executables rather than a whitelist of useful formats.
BLOCKED_SUFFIXES = {".exe", ".dll", ".bat", ".cmd", ".com", ".scr", ".msi",
                    ".ps1", ".vbs", ".js", ".jar", ".sh", ".php"}
MAX_ATTACHMENT_BYTES = 64 * 1024 * 1024        # 64 MB per file


def _pick_workflow(wanted):
    """The process the caller means: the one named, else the active one.

    The builder edits a process that need not be the active one — a process is
    usually drawn before it is switched on — so an explicit id always wins.
    """
    if wanted:
        return db.session.get(WorkflowDefinition, int(wanted))
    return (active_workflow()
            or WorkflowDefinition.query.order_by(WorkflowDefinition.id).first())


def _people(raw):
    """A list of users from a list of ids. Returns (users, error)."""
    if raw in (None, "", []):
        return [], None
    if not isinstance(raw, (list, tuple)):
        raw = [raw]
    out, seen = [], set()
    for item in raw:
        if item in (None, "", 0, "0"):
            continue
        user = db.session.get(AppUser, int(item))
        if user is None:
            return None, "یکی از کاربران انتخاب‌شده یافت نشد."
        if not user.is_active:
            return None, f"کاربر «{user.full_name}» غیرفعال است."
        if user.id not in seen:
            seen.add(user.id)
            out.append(user)
    return out, None


def _person(raw):
    """Resolve a user id from the builder. Returns (user or None, error)."""
    if raw in (None, "", 0, "0", "-1"):
        return None, None
    try:
        user = db.session.get(AppUser, int(raw))
    except (TypeError, ValueError):
        return None, "شناسه‌ی کاربر نامعتبر است."
    if user is None:
        return None, "کاربر انتخاب‌شده یافت نشد."
    if not user.is_active:
        return None, f"کاربر «{user.full_name}» غیرفعال است."
    return user, None


def _attachment_dir():
    path = instance_dir() / "attachments"
    path.mkdir(parents=True, exist_ok=True)
    return path


# ── definition (فرایندساز) ───────────────────────────────────────────────────
@bp.get("/definition")
# A stage owner already sees the stage names on their own کارتابل path strip,
# so reading the shape of the process tells them nothing new — and the
# documents filter needs it.
@permission_required_any("workflow.view", "workflow.act", "workflow.manage")
def get_definition():
    """The process as it stands, plus everything droppable onto a stage.

    Without ``workflow_id`` this is the active process — what the کارتابل
    runs. With one, it is whichever process the builder's selector is on,
    which need not be the active one: a process is usually drawn before it is
    switched on.
    """
    workflow = _pick_workflow(request.args.get("workflow_id"))
    if workflow is None:
        return fail("هیچ فرایندی تعریف نشده است. با دکمه‌ی «فرایند جدید» "
                    "یکی بسازید.", 404)
    sections = (FormSection.query.filter_by(is_active=True)
                .order_by(FormSection.sort_order).all())
    palette_sections = [{"kind": "section", "id": s.id, "code": s.code,
                         "title": s.title, "icon": s.icon,
                         "field_count": len([f for f in s.fields if f.is_active])}
                        for s in sections]
    palette_fields = [{"kind": "field", "id": f.id, "code": f.field_name,
                       "title": f.label, "section": f.section.code if f.section else None,
                       "section_title": f.section.title if f.section else None}
                      for f in FormField.query.filter_by(is_active=True)
                      .order_by(FormField.section_id, FormField.sort_order).all()]
    users = [{"id": u.id, "username": u.username, "full_name": u.full_name,
              "role": u.role, "role_label": u.role_label,
              "is_active": u.is_active}
             for u in AppUser.query.filter_by(is_active=True)
             .order_by(AppUser.first_name, AppUser.username).all()]
    return ok({"workflow": workflow.to_dict(),
               "palette": {"sections": palette_sections, "fields": palette_fields},
               "users": users,
               "applies_to": [{"value": k, "label": v} for k, v in APPLIES_TO.items()],
               "referral_modes": [{"value": k, "label": v}
                                  for k, v in REFERRAL_MODES.items()],
               "operation_kinds": [{"value": k, "label": v}
                                   for k, v in OPERATION_KINDS.items()]})


# ── defining a process ───────────────────────────────────────────────────────
@bp.get("/definitions")
@permission_required("workflow.manage")
def list_definitions():
    """Every process the workshop has defined, with how many stages each has."""
    rows = []
    for wf in WorkflowDefinition.query.order_by(WorkflowDefinition.id).all():
        rows.append({**wf.to_dict(with_stages=False),
                     "stage_count": len([s for s in wf.stages if s.is_active]),
                     "instance_count": WorkflowInstance.query.filter_by(
                         workflow_id=wf.id).count()})
    return ok(rows)


@bp.post("/definitions")
@permission_required("workflow.manage")
def create_definition():
    """A new process: a name, and a step zero to start it from.

    Everything after that is adding stages and saying who does what — the
    same screen the existing process uses, because it is the same thing.
    """
    payload = body()
    name = normalize_text(payload.get("name") or "")
    if not name:
        return fail("نام فرایند الزامی است.", 422)
    code = normalize_text(payload.get("code") or "") or f"p{secrets.token_hex(3)}"
    if WorkflowDefinition.query.filter_by(code=code).first():
        return fail(f"فرایندی با شناسه «{code}» از قبل هست.", 422)
    workflow = WorkflowDefinition(
        code=code, name=name,
        description=(payload.get("description") or "").strip() or None,
        is_active=False)
    db.session.add(workflow)
    db.session.flush()
    # Step zero exists in every process: it is what the «شروع فرایند» card in
    # the کارتابل opens, and it is where the operation and the well are set.
    intake = WorkflowStage(workflow_id=workflow.id, stage_number=0,
                           title="شروع فرایند",
                           description="این مرحله فرایند را آغاز می‌کند.",
                           is_active=True)
    db.session.add(intake)
    db.session.flush()
    section = FormSection.query.filter_by(code="intake").first()
    if section is not None:
        db.session.add(WorkflowStageItem(stage_id=intake.id,
                                         section_id=section.id, sort_order=0))
    record_audit("create", "workflow_definition", workflow.id,
                 summary=f"تعریف فرایند «{name}»")
    db.session.commit()
    return ok(workflow.to_dict(), message="فرایند ساخته شد. حالا مرحله‌ها را "
                                          "اضافه کنید.")


@bp.put("/definitions/<int:workflow_id>")
@permission_required("workflow.manage")
def update_definition(workflow_id):
    workflow = db.session.get(WorkflowDefinition, workflow_id)
    if workflow is None:
        return fail("فرایند یافت نشد.", 404)
    payload = body()
    if "name" in payload:
        name = normalize_text(payload["name"])
        if not name:
            return fail("نام فرایند الزامی است.", 422)
        workflow.name = name
    if "description" in payload:
        workflow.description = (payload["description"] or "").strip() or None
    if "is_active" in payload:
        active = payload["is_active"] in (True, "true", "1", 1)
        if active:
            if not [s for s in workflow.stages if s.stage_number > 0
                    and s.is_active]:
                return fail("فرایندی که هیچ مرحله‌ای ندارد فعال نمی‌شود؛ "
                            "اول مرحله‌ها را تعریف کنید.", 422)
            # Exactly one process runs at a time; activating this retires the
            # others rather than leaving two «فرایند فعال» to choose between.
            (WorkflowDefinition.query
             .filter(WorkflowDefinition.id != workflow.id)
             .update({"is_active": False}, synchronize_session=False))
        workflow.is_active = active
    record_audit("update", "workflow_definition", workflow.id,
                 summary=f"ویرایش فرایند «{workflow.name}»")
    db.session.commit()
    return ok(workflow.to_dict(), message="فرایند ذخیره شد.")


@bp.delete("/definitions/<int:workflow_id>")
@permission_required("workflow.manage")
def delete_definition(workflow_id):
    workflow = db.session.get(WorkflowDefinition, workflow_id)
    if workflow is None:
        return fail("فرایند یافت نشد.", 404)
    if WorkflowInstance.query.filter_by(workflow_id=workflow.id).count():
        return fail("این فرایند اجرا داشته است و حذف نمی‌شود؛ می‌توانید "
                    "غیرفعالش کنید تا فرایند تازه‌ای روی آن شروع نشود.", 409)
    name = workflow.name
    db.session.delete(workflow)
    record_audit("delete", "workflow_definition", workflow_id,
                 summary=f"حذف فرایند «{name}»")
    db.session.commit()
    return ok(message="فرایند حذف شد.")


@bp.post("/stages")
@permission_required("workflow.manage")
def create_stage():
    """Add a stage to a process: a title, and who does it."""
    payload = body()
    workflow = db.session.get(WorkflowDefinition,
                              int(payload.get("workflow_id") or 0))
    if workflow is None:
        return fail("فرایند یافت نشد.", 404)
    title = normalize_text(payload.get("title") or "")
    if not title:
        return fail("عنوان مرحله الزامی است.", 422)
    taken = {s.stage_number for s in workflow.stages}
    if payload.get("as_intake"):
        # Putting step zero back after it was deleted. A process needs some
        # door — either a step zero, or a stage marked «می‌تواند فرایند را
        # شروع کند» — or only an admin can open one.
        if 0 in taken:
            return fail("این فرایند از قبل مرحله ۰ دارد.", 422)
        number = 0
    else:
        number = max(taken or {0}) + 1
    person, error = _person(payload.get("assignee_id"))
    if error:
        return fail(error, 422)
    applies = payload.get("applies_to") or "both"
    if applies not in APPLIES_TO:
        return fail("مقدار «شامل» نامعتبر است.", 422)
    stage = WorkflowStage(
        workflow_id=workflow.id, stage_number=number, title=title,
        description=(payload.get("description") or "").strip() or None,
        assignee_id=person.id if person else None,
        applies_to=applies, is_active=True,
        can_start=payload.get("can_start") in (True, "true", "1", 1),
        route_by_center=payload.get("route_by_center") in (True, "true", "1", 1))
    db.session.add(stage)
    record_audit("create", "workflow_stage", workflow.id,
                 summary=f"افزودن مرحله «{title}» به «{workflow.name}»")
    db.session.commit()
    return ok(stage.to_dict(), message="مرحله اضافه شد.")


@bp.delete("/stages/<int:stage_id>")
@permission_required("workflow.manage")
def delete_stage(stage_id):
    """Remove a stage. Any stage — step zero included.

    Deleting step zero is allowed but it is not free: starting a process is
    step zero's job, so until another stage numbered 0 exists only an admin
    can open one. The message says so rather than the route refusing; the
    builder offers to put one back.
    """
    stage = db.session.get(WorkflowStage, stage_id)
    if stage is None:
        return fail("مرحله یافت نشد.", 404)
    used = WorkflowStageEntry.query.filter_by(stage_id=stage.id).count()
    title, number = stage.title, stage.stage_number
    workflow_id = stage.workflow_id

    if used:
        # Somebody's work hangs off it. Take it out of the chain but keep the
        # row, so the history that points at it still reads.
        stage.is_active = False
        message = (f"مرحله «{title}» در {used} فرایند سابقه دارد، بنابراین از "
                   f"مسیر برداشته شد ولی حذف نشد تا تاریخچه‌اش بماند.")
    else:
        db.session.delete(stage)
        message = f"مرحله «{title}» حذف شد."

    # A stage other stages route their rejections to is now gone.
    orphans = WorkflowStage.query.filter_by(workflow_id=workflow_id,
                                            reject_to_stage=number).all()
    for other in orphans:
        if other.id != stage_id:
            other.reject_to_stage = None
    if orphans:
        message += (f" «در صورت رد» در {len(orphans)} مرحله که به این مرحله "
                    f"اشاره داشت، به حالت پیش‌فرض برگشت.")
    if number == 0:
        message += (" توجه: شروع فرایند کار مرحله ۰ است؛ تا وقتی مرحله‌ای با "
                    "شماره ۰ تعریف نکنید، فقط مدیر سیستم می‌تواند فرایند "
                    "جدید باز کند.")
    record_audit("delete", "workflow_stage", stage_id,
                 summary=f"حذف مرحله «{title}»")
    db.session.commit()
    return ok({"deleted": not used, "was_intake": number == 0},
              message=message)


@bp.put("/stages/order")
@permission_required("workflow.manage")
def reorder_stages():
    """Renumber the stages of one process into the order they were dragged.

    A stage number is not a label — the engine routes on it, every stage entry
    carries a copy, attachments are filed under it and «در صورت رد» points at
    it. So the move has to take all of that with it, or a finished process
    would start reading somebody else's answers.

    Done in two passes through negative numbers, because both
    (workflow_id, stage_number) and (instance_id, stage_number) are unique and
    any one-pass renumbering collides with itself halfway through.
    """
    payload = body()
    workflow = db.session.get(WorkflowDefinition,
                              int(payload.get("workflow_id") or 0))
    if workflow is None:
        return fail("فرایند یافت نشد.", 404)
    wanted = [int(x) for x in (payload.get("stage_ids") or []) if x]
    stages = {s.id: s for s in workflow.stages}
    if sorted(wanted) != sorted(stages):
        return fail("فهرست مرحله‌ها با فرایند نمی‌خواند؛ صفحه را تازه کنید.",
                    422)

    moves = {sid: index for index, sid in enumerate(wanted)
             if stages[sid].stage_number != index}
    if not moves:
        return ok({"moved": 0}, message="ترتیب همین بود.")
    old_of = {sid: stages[sid].stage_number for sid in moves}

    instances = [i.id for i in
                 WorkflowInstance.query.filter_by(workflow_id=workflow.id).all()]

    # ── pass one: park everything that moves out of the way ────────────────
    for offset, sid in enumerate(moves):
        stages[sid].stage_number = -(1000 + offset)
    db.session.flush()
    for offset, sid in enumerate(moves):
        park = -(1000 + offset)
        WorkflowStageEntry.query.filter(
            WorkflowStageEntry.stage_id == sid,
            WorkflowStageEntry.instance_id.in_(instances)).update(
                {"stage_number": park}, synchronize_session=False)
        WorkflowAttachment.query.filter(
            WorkflowAttachment.instance_id.in_(instances),
            WorkflowAttachment.stage_number == old_of[sid]).update(
                {"stage_number": park}, synchronize_session=False)
    db.session.flush()

    # ── pass two: put them where they belong ───────────────────────────────
    for sid, number in moves.items():
        stages[sid].stage_number = number
        WorkflowStageEntry.query.filter(
            WorkflowStageEntry.stage_id == sid,
            WorkflowStageEntry.instance_id.in_(instances)).update(
                {"stage_number": number}, synchronize_session=False)
    for offset, sid in enumerate(moves):
        WorkflowAttachment.query.filter(
            WorkflowAttachment.instance_id.in_(instances),
            WorkflowAttachment.stage_number == -(1000 + offset)).update(
                {"stage_number": moves[sid]}, synchronize_session=False)
    db.session.flush()

    # «در صورت رد» stores a number, so it has to follow the move too.
    remap = {old_of[sid]: moves[sid] for sid in moves}
    for stage in workflow.stages:
        if stage.reject_to_stage in remap:
            stage.reject_to_stage = remap[stage.reject_to_stage]

    # Wherever a process was sitting is now called something else.
    for instance in WorkflowInstance.query.filter_by(
            workflow_id=workflow.id).all():
        if instance.current_stage in remap:
            instance.current_stage = remap[instance.current_stage]

    record_audit("update", "workflow_definition", workflow.id,
                 summary=f"تغییر ترتیب مرحله‌های «{workflow.name}»")
    db.session.commit()
    return ok({"moved": len(moves)},
              message=f"ترتیب {len(moves)} مرحله عوض شد.")


@bp.put("/stages/<int:stage_id>")
@permission_required("workflow.manage")
def update_stage(stage_id):
    """Rename a stage, hand it to somebody, or bind it to one branch."""
    stage = db.session.get(WorkflowStage, stage_id)
    if stage is None:
        return fail("مرحله یافت نشد.", 404)
    payload = body()
    if "title" in payload:
        title = normalize_text(payload["title"])
        if not title:
            return fail("عنوان مرحله الزامی است.", 422)
        stage.title = title
    if "description" in payload:
        stage.description = payload["description"] or None
    if "assignee_id" in payload:
        raw = payload["assignee_id"]
        if raw in (None, "", 0, "0"):
            stage.assignee_id = None
        else:
            user = db.session.get(AppUser, int(raw))
            if user is None:
                return fail("کاربر انتخاب‌شده یافت نشد.", 422)
            if not user.is_active:
                return fail(f"کاربر «{user.full_name}» غیرفعال است.", 422)
            stage.assignee_id = user.id
    if "applies_to" in payload:
        if payload["applies_to"] not in APPLIES_TO:
            return fail("مقدار «شامل» نامعتبر است.", 422)
        stage.applies_to = payload["applies_to"]
    if "is_active" in payload:
        stage.is_active = payload["is_active"] in (True, "true", "1", 1)
    if "can_start" in payload:
        stage.can_start = payload["can_start"] in (True, "true", "1", 1)
    if "route_by_center" in payload:
        stage.route_by_center = payload["route_by_center"] in (True, "true", "1", 1)
    # The متولی list. One stage can belong to all eight مراکز آبرسانی, so this
    # is a list; ``assignee_id`` follows its first entry, which is the name
    # every single-owner screen still shows.
    if "owner_ids" in payload:
        people, error = _people(payload["owner_ids"])
        if error:
            return fail(error, 422)
        stage.owners = people
        stage.assignee_id = people[0].id if people else None

    # ── the referral: where this stage's work goes when it is finished ──────
    if "referral_mode" in payload:
        if payload["referral_mode"] not in REFERRAL_MODES:
            return fail("نوع ارجاع نامعتبر است.", 422)
        stage.referral_mode = payload["referral_mode"]
    if "referral_user_id" in payload:
        person, error = _person(payload["referral_user_id"])
        if error:
            return fail(error, 422)
        stage.referral_user_id = person.id if person else None
    if "referral_hint" in payload:
        stage.referral_hint = (payload["referral_hint"] or "").strip() or None
    if stage.referral_mode == REFER_USER and stage.referral_user_id is None:
        return fail("برای ارجاع «همیشه به یک کاربر مشخص»، کاربر مقصد را "
                    "انتخاب کنید.", 422)

    # ── the approval: who signs it off, and where a rejection lands ─────────
    if "needs_approval" in payload:
        stage.needs_approval = payload["needs_approval"] in (True, "true", "1", 1)
    if "approver_id" in payload:
        person, error = _person(payload["approver_id"])
        if error:
            return fail(error, 422)
        stage.approver_id = person.id if person else None
    if "reject_to_stage" in payload:
        raw = payload["reject_to_stage"]
        if raw in (None, "", "-1"):
            stage.reject_to_stage = None
        else:
            target = WorkflowStage.query.filter_by(
                workflow_id=stage.workflow_id, stage_number=int(raw)).first()
            if target is None:
                return fail("مرحله‌ی مقصدِ برگشت پیدا نشد.", 422)
            stage.reject_to_stage = target.stage_number
    if stage.needs_approval and stage.approver_id is None:
        return fail("مرحله‌ای که نیاز به تأیید دارد باید تأییدکننده داشته "
                    "باشد.", 422)
    if stage.needs_approval and stage.approver_id == stage.assignee_id:
        return fail("تأییدکننده نمی‌تواند خودِ متولی مرحله باشد؛ آن‌وقت تأیید "
                    "معنایی ندارد.", 422)

    record_audit("update", "workflow_stage", stage.id,
                 summary=f"ویرایش مرحله «{stage.title}»")
    db.session.commit()
    return ok(stage.to_dict(), message="مرحله به‌روزرسانی شد.")


@bp.put("/stages/<int:stage_id>/items")
@permission_required("workflow.manage")
def set_stage_items(stage_id):
    """Replace a stage's contents with what the builder dropped on it.

    Sent whole rather than as add/remove calls: the builder is a drag surface,
    and the order the admin sees is the order that must be stored.
    """
    stage = db.session.get(WorkflowStage, stage_id)
    if stage is None:
        return fail("مرحله یافت نشد.", 404)
    payload = body()
    items = payload.get("items")
    if not isinstance(items, list):
        return fail("فهرست موارد باید آرایه باشد.", 422)

    cleaned = []
    for order, raw in enumerate(items):
        kind = raw.get("kind")
        applies = raw.get("applies_to") or "both"
        if applies not in APPLIES_TO:
            return fail("مقدار «شامل» نامعتبر است.", 422)
        if kind == "section":
            target = db.session.get(FormSection, int(raw.get("id") or 0))
            if target is None:
                return fail("بخش انتخاب‌شده یافت نشد.", 422)
            cleaned.append(WorkflowStageItem(
                stage_id=stage.id, section_id=target.id, sort_order=order,
                applies_to=applies, is_optional=bool(raw.get("is_optional")),
                is_read_only=bool(raw.get("is_read_only"))))
        elif kind == "field":
            target = db.session.get(FormField, int(raw.get("id") or 0))
            if target is None:
                return fail("فیلد انتخاب‌شده یافت نشد.", 422)
            cleaned.append(WorkflowStageItem(
                stage_id=stage.id, field_id=target.id, sort_order=order,
                applies_to=applies, is_optional=bool(raw.get("is_optional")),
                is_read_only=bool(raw.get("is_read_only"))))
        else:
            return fail("نوع مورد باید «section» یا «field» باشد.", 422)

    WorkflowStageItem.query.filter_by(stage_id=stage.id).delete()
    for item in cleaned:
        db.session.add(item)
    record_audit("update", "workflow_stage", stage.id,
                 summary=f"تنظیم فرم مرحله «{stage.title}» ({len(cleaned)} مورد)")
    db.session.commit()
    db.session.refresh(stage)
    return ok(stage.to_dict(), message="فرم این مرحله ذخیره شد.")


# ── who is connected to what ─────────────────────────────────────────────────
@bp.get("/connections")
@permission_required("workflow.manage")
def connections():
    """Every user, and every place in the process they are wired into.

    The workshop assigned forms to مرکز آبرسانی, opened that user's کارتابل,
    found it empty and concluded nothing had connected. It had — there was
    simply no process running at the time. This is the view that says so: for
    each person, the stages they fill, approve or receive referrals on, and
    which parts of the form each of those stages actually asks for. Delete a
    stage or a section and the row it came from visibly loses it.
    """
    workflow = _pick_workflow(request.args.get("workflow_id"))
    if workflow is None:
        return fail("فرایندی تعریف نشده است.", 404)

    rows = {}
    def row(user):
        if user is None:
            return None
        if user.id not in rows:
            rows[user.id] = {
                "user_id": user.id, "username": user.username,
                "full_name": user.full_name, "role_label": user.role_label,
                "is_active": user.is_active,
                "owns": [], "approves": [], "referred": [], "open_work": 0,
            }
        return rows[user.id]

    for stage in sorted(workflow.stages, key=lambda s: s.stage_number):
        if not stage.is_active:
            continue
        # What this stage actually asks for. A stage whose form is empty is
        # worth seeing: it is usually a section somebody deleted.
        parts = []
        for item in sorted(stage.items, key=lambda i: i.sort_order):
            if item.section is not None:
                parts.append({"kind": "section", "title": item.section.title,
                              "count": len([f for f in item.section.fields
                                            if f.is_active]),
                              "locked": item.is_read_only})
            elif item.field is not None:
                parts.append({"kind": "field", "title": item.field.label,
                              "count": 1, "locked": item.is_read_only})
        people = stage.all_owners
        card = {"stage_id": stage.id, "stage_number": stage.stage_number,
                "title": stage.title, "applies_to": stage.applies_to,
                "applies_to_label": APPLIES_TO.get(stage.applies_to,
                                                   stage.applies_to),
                "can_start": stage.can_start,
                "route_by_center": stage.route_by_center,
                "shared_with": max(0, len(people) - 1),
                "parts": parts, "empty": not parts}
        for person in people:
            owner = row(person)
            if owner is not None:
                owner["owns"].append(card)
        approver = row(stage.approver)
        if approver is not None:
            approver["approves"].append(card)
        if stage.referral_mode == REFER_USER:
            target = row(stage.referral_user)
            if target is not None:
                target["referred"].append(card)

    # What is actually sitting with each of them right now, so an empty
    # کارتابل can be told apart from an empty assignment.
    live = (db.session.query(WorkflowStageEntry)
            .join(WorkflowInstance,
                  WorkflowStageEntry.instance_id == WorkflowInstance.id)
            .filter(WorkflowInstance.workflow_id == workflow.id,
                    WorkflowInstance.status == INSTANCE_OPEN,
                    WorkflowStageEntry.status.in_((ENTRY_PENDING,
                                                   ENTRY_AWAITING,
                                                   "rejected"))).all())
    for entry in live:
        holder = entry.owner_id
        if holder in rows:
            rows[holder]["open_work"] += 1

    unassigned = [{"stage_id": s.id, "stage_number": s.stage_number,
                   "title": s.title}
                  for s in sorted(workflow.stages, key=lambda x: x.stage_number)
                  if s.is_active and not s.owner_ids]
    empty_forms = [{"stage_id": s.id, "stage_number": s.stage_number,
                    "title": s.title}
                   for s in sorted(workflow.stages, key=lambda x: x.stage_number)
                   if s.is_active and s.stage_number > 0 and not s.items]

    # «فقط نمایش» means "show what an earlier stage recorded". On the *first*
    # stage that carries a part, there is no earlier stage — so the field is
    # shown as «—» to everybody and nobody can ever fill it. That is almost
    # never what was meant, and it is invisible until somebody opens the form.
    first_seen, stuck = {}, []
    for stage in sorted(workflow.stages, key=lambda x: x.stage_number):
        if not stage.is_active:
            continue
        for item in stage.items:
            part = item.section or item.field
            if part is None:
                continue
            key = (("section", item.section_id) if item.section
                   else ("field", item.field_id))
            if key in first_seen:
                continue
            first_seen[key] = stage
            if item.is_read_only:
                stuck.append({
                    "stage_number": stage.stage_number, "title": stage.title,
                    "part": getattr(part, "title", None) or part.label,
                })
    return ok({
        "workflow": workflow.to_dict(with_stages=False),
        "users": sorted(rows.values(), key=lambda r: -(len(r["owns"]))),
        "unassigned": unassigned,
        "empty_forms": empty_forms,
        "locked_first": stuck,
        "has_intake": any(s.stage_number == 0 and s.is_active
                          for s in workflow.stages),
        # Where each operation opens, so the panel can say it in words rather
        # than leaving the admin to work it out from six checkboxes.
        "doors": [{"kind": kind, "kind_label": label,
                   "stage_number": (door.stage_number if door else None),
                   "title": (door.title if door else None),
                   "owners": [u.full_name for u in door.all_owners]
                             if door else []}
                  for kind, label in OPERATION_KINDS.items()
                  for door in [entry_stage(workflow, kind)]],
        "running": WorkflowInstance.query.filter_by(
            workflow_id=workflow.id, status=INSTANCE_OPEN).count(),
    })


@bp.get("/uses")
@permission_required_any("workflow.manage", "form.manage")
def form_uses():
    """Which stages — and so which people — a section or field is wired into.

    Asked before a section is deleted in the form builder: removing it takes
    it off every stage that carried it, and the person who owns that stage is
    the one who will notice.
    """
    kind = request.args.get("kind")
    code = request.args.get("code")
    query = WorkflowStageItem.query.join(
        WorkflowStage, WorkflowStageItem.stage_id == WorkflowStage.id)
    if kind == "section":
        section = FormSection.query.filter_by(code=code).first()
        if section is None:
            return ok({"stages": [], "title": code})
        query = query.filter(WorkflowStageItem.section_id == section.id)
        title = section.title
    elif kind == "field":
        field = FormField.query.filter_by(field_name=code).first()
        if field is None:
            return ok({"stages": [], "title": code})
        query = query.filter(WorkflowStageItem.field_id == field.id)
        title = field.label
    else:
        return fail("نوع مورد باید «section» یا «field» باشد.", 422)

    stages = []
    for item in query.all():
        stage = item.stage
        if stage is None or not stage.is_active:
            continue
        stages.append({
            "stage_id": stage.id, "stage_number": stage.stage_number,
            "title": stage.title,
            "workflow": stage.workflow.name if stage.workflow else None,
            "assignee": stage.assignee.full_name if stage.assignee else None,
            "locked": item.is_read_only,
        })
    return ok({"title": title, "kind": kind, "code": code,
               "stages": sorted(stages, key=lambda s: s["stage_number"])})


# ── instances ────────────────────────────────────────────────────────────────
@bp.post("/instances")
@permission_required("workflow.act")
def create_instance():
    try:
        instance = start_instance(body(), current_user())
    except WorkflowError as exc:
        return fail(str(exc), 422)
    return ok(instance.to_dict(), message="فرایند آغاز شد.")


@bp.get("/instances")
@permission_required("workflow.view")
def list_instances():
    page, size = paging(default_size=50)
    query = WorkflowInstance.query
    status = request.args.get("status")
    if status:
        query = query.filter(WorkflowInstance.status == status)
    if request.args.get("kind"):
        query = query.filter(WorkflowInstance.operation_kind
                             == request.args["kind"])
    if request.args.get("stage"):
        query = query.filter(WorkflowInstance.current_stage
                             == int(request.args["stage"]))
    total = query.count()
    rows = (query.order_by(WorkflowInstance.updated_at.desc())
            .limit(size).offset((page - 1) * size).all())
    return ok([r.to_dict() for r in rows], total=total, page=page,
              page_size=size, pages=max(1, (total + size - 1) // size))


@bp.get("/inbox")
@permission_required("workflow.act")
def inbox():
    """Every open process with a stage this user still owes.

    Not only the stage the process is "on": stages do not wait on each other,
    so the owner of stage 3 sees their work as soon as the process starts, and
    is merely told that stage 2 has not reported yet.
    """
    user = current_user()
    rows = []
    for instance in (WorkflowInstance.query.filter_by(status=INSTANCE_OPEN)
                     .order_by(WorkflowInstance.updated_at.desc()).all()):
        sync_entries(instance)
        outstanding = {s.stage_number for s in pending_stages(instance)}
        mine = [s for s in stages_of_user(instance, user)
                if s.stage_number in outstanding]
        # Two kinds of work land here: a stage to fill, and a stage somebody
        # has sent me to approve. They read differently and are answered with
        # different buttons, so the کارتابل says which is which.
        to_decide = awaiting_approval(instance, user)
        # A stage sitting with its approver belongs to them as a *decision*,
        # not as a form to fill again — and `owner_of` hands it to them either
        # way, so the decision has to win.
        deciding = {s.stage_number for s in to_decide}
        todo = [(s, "approve") for s in to_decide] + \
               [(s, "fill") for s in mine
                if s.stage_number not in deciding]
        if not todo and user.role == "admin":
            todo = [(s, "fill") for s in applicable_stages(instance)
                    if s.stage_number in outstanding]
        for stage, task in todo:
            waiting = waiting_before(instance, stage.stage_number)
            entry = next((e for e in instance.entries
                          if e.stage_number == stage.stage_number), None)
            data = instance.to_dict(with_entries=False)
            data.update({
                "stage_number": stage.stage_number,
                "stage_title": stage.title,
                "stage_id": stage.id,
                "task_kind": task,
                "entry_status": entry.status if entry else ENTRY_PENDING,
                "is_mine": user.id in owners_of(instance, stage),
                "unassigned": not owners_of(instance, stage),
                "referred_to_name": (entry.referred_to.full_name
                                     if entry and entry.referred_to else None),
                "referred_by_name": (entry.referred_by.full_name
                                     if entry and entry.referred_by else None),
                "referral_note": entry.referral_note if entry else None,
                "waiting_on": [{"stage_number": w.stage_number, "title": w.title,
                                "assignee": (w.assignee.full_name
                                             if w.assignee else None)}
                               for w in waiting],
            })
            rows.append(data)
    db.session.commit()
    # An empty کارتابل reads as "my forms are not connected to me". It is
    # almost never that: the stages are wired, there is simply no process
    # running that has reached them. Say so, and name them, so the wiring
    # done in the process builder is visible from here too.
    mine_stages = []
    for stage in (WorkflowStage.query.join(
            WorkflowDefinition,
            WorkflowStage.workflow_id == WorkflowDefinition.id)
            .filter(WorkflowDefinition.is_active.is_(True),
                    WorkflowStage.is_active.is_(True))
            .order_by(WorkflowStage.stage_number).all()):
        if user.id in stage.owner_ids:
            role = "fill"
        elif stage.approver_id == user.id:
            role = "approve"
        else:
            continue
        mine_stages.append({
            "stage_number": stage.stage_number, "title": stage.title,
            "role": role, "field_count": len(stage.items),
            "can_start": stage.can_start,
            "shared_with": max(0, len(stage.owner_ids) - 1),
            "workflow": stage.workflow.name if stage.workflow else None,
        })
    # Only the owner of a stage marked «می‌تواند فرایند را شروع کند» opens
    # processes, and only for the operations that stage admits — so the card
    # offers those operations and no others.
    kinds = startable_kinds(user)
    return ok(rows, total=len(rows), may_start=bool(kinds),
              startable=[{"value": k, "label": OPERATION_KINDS[k]}
                         for k in kinds],
              my_stages=mine_stages,
              running=WorkflowInstance.query.filter_by(
                  status=INSTANCE_OPEN).count())


@bp.get("/instances/<int:instance_id>")
@permission_required("workflow.act")
def get_instance(instance_id):
    instance = db.session.get(WorkflowInstance, instance_id)
    if instance is None:
        return fail("فرایند یافت نشد.", 404)
    data = instance.to_dict()
    data["payload"] = instance.payload
    data["attachments"] = [a.to_dict() for a in instance.attachments]
    user = current_user()
    sync_entries(instance)
    db.session.commit()

    # Which stage to draw: the one asked for, else the first one this user
    # still owes, else wherever the process currently sits.
    wanted = request.args.get("stage")
    stage = None
    if wanted not in (None, ""):
        stage = stage_by_number(instance, int(wanted))
    if stage is None:
        outstanding = {s.stage_number for s in pending_stages(instance)}
        mine = [s for s in stages_of_user(instance, user)
                if s.stage_number in outstanding]
        stage = mine[0] if mine else current_stage_of(instance)

    data["may_act"] = may_act(user, instance, stage)
    data["form"] = stage_form(instance, stage) if stage else None
    # Who this stage's work goes to when it is sent on, and whether this user
    # is the one being asked to approve it rather than to fill it.
    entry = next((e for e in instance.entries
                  if stage and e.stage_number == stage.stage_number), None)
    data["referral"] = referral_choices(instance, stage) if stage else None
    data["entry_status"] = entry.status if entry else None
    data["awaiting_my_decision"] = bool(
        stage and stage.stage_number in
        {s.stage_number for s in awaiting_approval(instance, user)})
    data["referred_to_name"] = (entry.referred_to.full_name
                                if entry and entry.referred_to else None)
    data["referred_by_name"] = (entry.referred_by.full_name
                                if entry and entry.referred_by else None)
    data["referral_note"] = entry.referral_note if entry else None
    data["my_stages"] = [s.stage_number for s in stages_of_user(instance, user)]
    data["waiting_on"] = [
        {"stage_number": w.stage_number, "title": w.title,
         "assignee": w.assignee.full_name if w.assignee else None}
        for w in (waiting_before(instance, stage.stage_number) if stage else [])]
    data["path"] = [s.to_dict() for s in applicable_stages(instance)]
    # What everyone before has recorded, read-only: the stage holding the
    # process has to see the work behind it before adding to it.
    data["summary"] = submitted_summary(instance,
                                        except_stage=stage.stage_number if stage
                                        else None)
    return ok(data)


@bp.post("/instances/<int:instance_id>/form")
@permission_required("workflow.act")
def preview_form(instance_id):
    """The stage form as it would look given answers not yet submitted.

    Stage 4 asks «اقدام مورد نیاز» before it knows whether to ask anything
    else, so the page re-reads the form the moment that answer changes. Nothing
    is written — the draft is merged only for the length of this call.
    """
    instance = db.session.get(WorkflowInstance, instance_id)
    if instance is None:
        return fail("فرایند یافت نشد.", 404)
    payload = body()
    number = payload.get("stage_number")
    stage = (stage_by_number(instance, int(number)) if number not in (None, "")
             else current_stage_of(instance))
    if stage is None:
        return fail("مرحله یافت نشد.", 404)
    draft = dict(instance.payload)
    draft.update(payload.get("data") or {})
    return ok({"form": stage_form(instance, stage, draft=draft),
               "operation_label": instance.operation_label})


@bp.post("/instances/<int:instance_id>/submit")
@permission_required("workflow.act")
def submit(instance_id):
    instance = db.session.get(WorkflowInstance, instance_id)
    if instance is None:
        return fail("فرایند یافت نشد.", 404)
    payload = body()
    stage_number = payload.get("stage_number")
    try:
        submit_stage(instance, payload.get("data") or {}, current_user(),
                     note=payload.get("note"),
                     stage_number=(int(stage_number)
                                   if stage_number not in (None, "") else None),
                     refer_to=payload.get("refer_to") or None,
                     referral_note=payload.get("referral_note"))
    except WorkflowError as exc:
        return fail(str(exc), 422)
    data = instance.to_dict()
    if instance.record_id:
        message = "فرایند تکمیل شد و رکورد ثبت گردید."
    elif any(e.status == ENTRY_AWAITING for e in instance.entries):
        message = "مرحله ثبت شد و برای تأیید ارسال گردید."
    else:
        message = "مرحله ثبت و ارجاع شد."
    return ok(data, message=message)


@bp.post("/instances/<int:instance_id>/decide")
@permission_required("workflow.act")
def decide(instance_id):
    """Approve a stage, or send it back with a reason."""
    instance = db.session.get(WorkflowInstance, instance_id)
    if instance is None:
        return fail("فرایند یافت نشد.", 404)
    payload = body()
    number = payload.get("stage_number")
    if number in (None, ""):
        return fail("مرحله‌ی موردنظر مشخص نیست.", 422)
    approved = payload.get("approved") in (True, "true", "1", 1, "approve")
    try:
        decide_stage(instance, int(number), current_user(), approved,
                     comment=payload.get("comment"))
    except WorkflowError as exc:
        return fail(str(exc), 422)
    return ok(instance.to_dict(),
              message="تأیید شد و به مرحله بعد ارجاع گردید." if approved
                      else "برگشت داده شد.")


@bp.post("/instances/<int:instance_id>/cancel")
@permission_required("workflow.manage")
def cancel(instance_id):
    instance = db.session.get(WorkflowInstance, instance_id)
    if instance is None:
        return fail("فرایند یافت نشد.", 404)
    cancel_instance(instance, (body().get("reason") or "").strip(), current_user())
    return ok(instance.to_dict(), message="فرایند لغو شد.")


# ── «قبلی» values ────────────────────────────────────────────────────────────
@bp.get("/previous")
@login_required
def previous_values():
    """Last operation's readings for a well, to prefill the «…قبلی» fields."""
    well_id = request.args.get("well_id")
    if not well_id:
        from ..services.records import resolve_well
        well, _raw = resolve_well(request.args.get("well"), create_missing=False)
        well_id = well.id if well else None
    if not well_id:
        return ok({"values": {}, "source": None})
    return ok(previous_values_for(int(well_id)) or {"values": {}, "source": None})


# ── attachments ──────────────────────────────────────────────────────────────
@bp.post("/instances/<int:instance_id>/attachments")
@permission_required("workflow.act")
def upload_attachment(instance_id):
    instance = db.session.get(WorkflowInstance, instance_id)
    if instance is None:
        return fail("فرایند یافت نشد.", 404)
    uploaded = request.files.get("file")
    if uploaded is None or not uploaded.filename:
        return fail("فایلی انتخاب نشده است.", 422)

    original = os.path.basename(uploaded.filename)[:250]
    suffix = os.path.splitext(original)[1].lower()
    if suffix in BLOCKED_SUFFIXES:
        return fail(f"بارگذاری فایل با پسوند «{suffix}» مجاز نیست.", 415)

    stored = f"{instance.id}_{secrets.token_hex(8)}{suffix}"
    target = _attachment_dir() / stored
    uploaded.save(target)
    size = target.stat().st_size
    if size > MAX_ATTACHMENT_BYTES:
        target.unlink(missing_ok=True)
        return fail("حجم فایل بیش از ۶۴ مگابایت است.", 413)

    attachment = WorkflowAttachment(
        instance_id=instance.id, stage_number=instance.current_stage,
        filename=original, stored_name=stored, size_bytes=size,
        content_type=(uploaded.mimetype
                      or mimetypes.guess_type(original)[0]
                      or "application/octet-stream"),
        uploaded_by=current_user().id if current_user() else None)
    db.session.add(attachment)
    record_audit("create", "workflow", instance.id,
                 summary=f"بارگذاری مستند «{original}»")
    db.session.commit()
    return ok(attachment.to_dict(), message="مستند بارگذاری شد.")


@bp.get("/attachments")
@permission_required_any("workflow.act", "workflow.view")
def list_attachments():
    """Every document attached to any process, in one place.

    The admin and the stage owners both need this: a photo of a plaque taken
    at stage 3 is what stage 5 signs off against, and nobody should have to
    open five processes to find it.
    """
    page, size = paging(default_size=50)
    query = (db.session.query(WorkflowAttachment)
             .join(WorkflowInstance,
                   WorkflowAttachment.instance_id == WorkflowInstance.id))
    if request.args.get("instance_id"):
        query = query.filter(WorkflowAttachment.instance_id
                             == int(request.args["instance_id"]))
    if request.args.get("stage"):
        query = query.filter(WorkflowAttachment.stage_number
                             == int(request.args["stage"]))
    if request.args.get("user_id"):
        query = query.filter(WorkflowAttachment.uploaded_by
                             == int(request.args["user_id"]))
    term = normalize_text(request.args.get("q", ""))
    if term:
        query = query.filter(db.or_(
            WorkflowAttachment.filename.ilike(f"%{term}%"),
            WorkflowInstance.well_name_raw.ilike(f"%{term}%")))
    total = query.count()
    rows = (query.order_by(WorkflowAttachment.uploaded_at.desc())
            .limit(size).offset((page - 1) * size).all())
    data = []
    for row in rows:
        item = row.to_dict()
        instance = row.instance
        item["well"] = (instance.well.name if instance and instance.well
                        else instance.well_name_raw if instance else None)
        item["operation_label"] = instance.operation_label if instance else None
        item["instance_status"] = (INSTANCE_STATUS.get(instance.status,
                                                       instance.status)
                                   if instance else None)
        item["stage_title"] = next(
            (s.title for s in (instance.workflow.stages if instance else [])
             if s.stage_number == row.stage_number), None)
        data.append(item)
    return ok(data, total=total, page=page, page_size=size,
              pages=max(1, (total + size - 1) // size))


@bp.get("/attachments/<int:attachment_id>")
@permission_required_any("workflow.act", "workflow.view")
def download_attachment(attachment_id):
    attachment = db.session.get(WorkflowAttachment, attachment_id)
    if attachment is None:
        return fail("مستند یافت نشد.", 404)
    path = _attachment_dir() / attachment.stored_name
    if not path.exists():
        return fail("فایل این مستند روی دیسک پیدا نشد.", 410)
    return send_file(path, as_attachment=True,
                     download_name=attachment.filename,
                     mimetype=attachment.content_type)


@bp.delete("/attachments/<int:attachment_id>")
@permission_required("workflow.act")
def delete_attachment(attachment_id):
    attachment = db.session.get(WorkflowAttachment, attachment_id)
    if attachment is None:
        return fail("مستند یافت نشد.", 404)
    user = current_user()
    if user.role != "admin" and attachment.uploaded_by != user.id:
        return fail("فقط بارگذارنده یا مدیر سیستم می‌تواند مستند را حذف کند.", 403)
    (_attachment_dir() / attachment.stored_name).unlink(missing_ok=True)
    db.session.delete(attachment)
    record_audit("delete", "workflow", attachment.instance_id,
                 summary=f"حذف مستند «{attachment.filename}»")
    db.session.commit()
    return ok(message="مستند حذف شد.")


# ── per-stage reports ────────────────────────────────────────────────────────
# «خروجی اکسل از آیتم‌های ثبت‌شده در هر مرحله»: pick a stage, tick the columns
# you want, get a sheet. The columns on offer are exactly what that stage
# records — read off its own form items — plus a few facts about the process
# that every such report wants anyway.
_STAGE_REPORT_BASE = [
    ("__instance", "شماره فرایند"),
    ("__well", "نام چاه"),
    ("__pm_code", "کد PM"),
    ("__operation", "نوع عملیات"),
    ("__status", "وضعیت مرحله"),
    ("__user", "ثبت‌کننده"),
    ("__referred_to", "ارجاع به"),
    ("__submitted", "تاریخ ثبت"),
    ("__instance_status", "وضعیت فرایند"),
]


def _stage_field_names(stage):
    """Every field this stage asks for, section by section, in form order."""
    names = []
    for item in sorted(stage.items, key=lambda i: i.sort_order):
        if item.section is not None:
            for field in sorted(item.section.fields, key=lambda f: f.sort_order):
                if field.is_active and field.field_name not in names:
                    names.append(field.field_name)
        elif item.field is not None and item.field.field_name not in names:
            names.append(item.field.field_name)
    return names


@bp.get("/stage-report/columns")
@permission_required_any("report.build", "report.view", "workflow.manage")
def stage_report_columns():
    """What can be put in a report of one stage."""
    stage = db.session.get(WorkflowStage, int(request.args.get("stage_id") or 0))
    if stage is None:
        return fail("مرحله یافت نشد.", 404)
    labels = {f.field_name: f.label for f in FormField.query.all()}
    return ok({
        "stage": {"id": stage.id, "stage_number": stage.stage_number,
                  "title": stage.title,
                  "workflow": stage.workflow.name if stage.workflow else None},
        "base": [{"key": k, "label": v} for k, v in _STAGE_REPORT_BASE],
        "fields": [{"key": n, "label": labels.get(n, n)}
                   for n in _stage_field_names(stage)],
    })


def _stage_report(payload):
    """The rows of one stage's report, and the columns the caller asked for."""
    stage = db.session.get(WorkflowStage, int(payload.get("stage_id") or 0))
    if stage is None:
        raise WorkflowError("مرحله یافت نشد.")
    wanted = [c for c in (payload.get("columns") or []) if c]
    if not wanted:
        raise WorkflowError("حداقل یک ستون را انتخاب کنید.")

    labels = {f.field_name: f.label for f in FormField.query.all()}
    labels.update(dict(_STAGE_REPORT_BASE))
    only_done = payload.get("only_submitted") is not False

    query = (WorkflowStageEntry.query
             .filter(WorkflowStageEntry.stage_number == stage.stage_number)
             .join(WorkflowInstance,
                   WorkflowStageEntry.instance_id == WorkflowInstance.id)
             .filter(WorkflowInstance.workflow_id == stage.workflow_id))
    if only_done:
        query = query.filter(WorkflowStageEntry.status.in_(ENTRY_DONE))
    if payload.get("instance_status"):
        query = query.filter(WorkflowInstance.status == payload["instance_status"])

    rows = []
    for entry in query.order_by(WorkflowStageEntry.instance_id).all():
        instance = entry.instance
        if instance is None:
            continue
        # What this stage recorded, over what the process knew before it.
        values = dict(instance.payload or {})
        values.update(entry.payload or {})
        facts = {
            "__instance": instance.id,
            "__well": (instance.well.name if instance.well
                       else instance.well_name_raw),
            "__pm_code": instance.well.pm_code if instance.well else None,
            "__operation": instance.operation_label,
            "__status": ENTRY_STATUS.get(entry.status, entry.status),
            "__user": entry.user.full_name if entry.user else None,
            "__referred_to": (entry.referred_to.full_name
                              if entry.referred_to else None),
            "__submitted": (to_jalali_str(entry.submitted_at)
                            if entry.submitted_at else None),
            "__instance_status": INSTANCE_STATUS.get(instance.status,
                                                     instance.status),
        }
        row = {}
        for key in wanted:
            value = facts[key] if key in facts else values.get(key)
            if isinstance(value, list):
                value = "، ".join(str(v) for v in value if v not in (None, ""))
            row[key] = "" if value in (None, False) else value
        rows.append(row)

    return {
        "title": f"گزارش مرحله {stage.stage_number} — {stage.title}",
        "columns": [{"key": k, "label": labels.get(k, k)} for k in wanted],
        "rows": rows,
        "filters": {"فرایند": stage.workflow.name if stage.workflow else "",
                    "مرحله": stage.title},
    }


@bp.post("/stage-report")
@permission_required_any("report.build", "report.view", "workflow.manage")
def stage_report():
    try:
        return ok(_stage_report(body()))
    except WorkflowError as exc:
        return fail(str(exc), 422)


@bp.post("/stage-report/export.<fmt>")
@permission_required("record.export")
def stage_report_export(fmt):
    from ..services.exporter import render
    from ..services.jalali import today_jalali
    try:
        result = _stage_report(body())
    except WorkflowError as exc:
        return fail(str(exc), 422)
    jy, jm, jd = today_jalali()
    meta = {"تاریخ تهیه": f"{jy}/{jm:02d}/{jd:02d}",
            "تعداد سطر": len(result["rows"])}
    meta.update(result["filters"])
    try:
        payload, mimetype, ext = render(fmt, result["columns"], result["rows"],
                                        result["title"], meta)
    except (ValueError, RuntimeError) as exc:
        return fail(str(exc), 422)
    record_audit("export", "workflow", None,
                 summary=f"خروجی {fmt} از «{result['title']}»", commit=True)
    stem = f"stage_{result['title'][:20]}"
    return Response(payload, mimetype=mimetype, headers={
        "Content-Disposition":
            f'attachment; filename="stage_report_{jy}-{jm:02d}-{jd:02d}.{ext}"; '
            f"filename*=UTF-8''stage_report_{jy}-{jm:02d}-{jd:02d}.{ext}"})
