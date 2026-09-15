# -*- coding: utf-8 -*-
"""/api/workflow — the process builder, the کارتابل, and process tracking."""
import mimetypes
import os
import secrets

from flask import Blueprint, request, send_file

from ..extensions import db
from ..models import (AppUser, FormField, FormSection, WorkflowAttachment,
                      WorkflowDefinition, WorkflowInstance, WorkflowStage,
                      WorkflowStageEntry, WorkflowStageItem)
from ..models.workflow import (APPLIES_TO, ENTRY_PENDING, INSTANCE_OPEN,
                               INSTANCE_STATUS, OPERATION_KINDS)
from ..paths import instance_dir
from ..services.audit import record_audit
from ..services.auth import (current_user, login_required,
                             permission_required,
                             permission_required_any)
from ..services.lookups import normalize_text
from ..services.workflow import (WorkflowError, active_workflow,
                                 applicable_stages, cancel_instance,
                                 current_stage_of, may_act,
                                 pending_stages, previous_values_for,
                                 may_start, stage_by_number, stage_form,
                                 stages_of_user,
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
    """The process as it stands, plus everything droppable onto a stage."""
    workflow = active_workflow()
    if workflow is None:
        return fail("هیچ فرایند فعالی تعریف نشده است.", 404)
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
               "operation_kinds": [{"value": k, "label": v}
                                   for k, v in OPERATION_KINDS.items()]})


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
                applies_to=applies, is_optional=bool(raw.get("is_optional"))))
        elif kind == "field":
            target = db.session.get(FormField, int(raw.get("id") or 0))
            if target is None:
                return fail("فیلد انتخاب‌شده یافت نشد.", 422)
            cleaned.append(WorkflowStageItem(
                stage_id=stage.id, field_id=target.id, sort_order=order,
                applies_to=applies, is_optional=bool(raw.get("is_optional"))))
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
        if not mine and user.role != "admin":
            continue
        for stage in (mine or ([] if user.role != "admin" else
                               [s for s in applicable_stages(instance)
                                if s.stage_number in outstanding])):
            waiting = waiting_before(instance, stage.stage_number)
            data = instance.to_dict(with_entries=False)
            data.update({
                "stage_number": stage.stage_number,
                "stage_title": stage.title,
                "stage_id": stage.id,
                "is_mine": stage.assignee_id == user.id,
                "unassigned": stage.assignee_id is None,
                "waiting_on": [{"stage_number": w.stage_number, "title": w.title,
                                "assignee": (w.assignee.full_name
                                             if w.assignee else None)}
                               for w in waiting],
            })
            rows.append(data)
    db.session.commit()
    # Only step zero's owner opens processes, so only they get the button.
    return ok(rows, total=len(rows), may_start=may_start(user))


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
                                   if stage_number not in (None, "") else None))
    except WorkflowError as exc:
        return fail(str(exc), 422)
    data = instance.to_dict()
    message = ("فرایند تکمیل شد و رکورد ثبت گردید."
               if instance.record_id else "مرحله ثبت شد و به مرحله بعد رفت.")
    return ok(data, message=message)


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
