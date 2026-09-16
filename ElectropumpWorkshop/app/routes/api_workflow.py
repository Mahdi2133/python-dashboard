# -*- coding: utf-8 -*-
"""/api/workflow — the process designer, the کارتابل, and process tracking.

Three surfaces over one graph:

*   **the designer** (`/definition`, `/nodes`, `/edges`, `/map`) — the admin
    draws a process. Every property of every node and arrow is writable here,
    which is what makes a brand-new, unrelated process possible without code.
*   **the کارتابل** (`/inbox`, `/instances/…`) — whoever holds a phase fills
    it, and whoever approves one approves or rejects it.
*   **tracking** (`/instances/<id>/map`, `/events`) — the same drawing, painted
    with where each run has got to.
"""
import mimetypes
import os
import secrets

from flask import Blueprint, request, send_file

from ..extensions import db
from ..models import (AppUser, FormField, FormSection, WorkflowAttachment,
                      WorkflowDefinition, WorkflowInstance, WorkflowStage,
                      WorkflowStageEntry, WorkflowStageItem)
from ..models.auth import ROLES
from ..models.workflow import (APPLIES_TO, APPROVAL_MODES, EDGE_KINDS,
                               INSTANCE_LIVE, INSTANCE_STATUS, NODE_APPROVAL,
                               NODE_PHASE, NODE_TYPES, OPERATION_KINDS,
                               PRINCIPAL_ROLES, PRINCIPAL_ROLE, PRINCIPAL_USER,
                               TEMPLATE_ARCHIVED, TEMPLATE_DRAFT,
                               TEMPLATE_PUBLISHED, TEMPLATE_STATUS,
                               WorkflowEdge, WorkflowEvent,
                               WorkflowNodePrincipal)
from ..paths import instance_dir
from ..services.audit import record_audit
from ..services.auth import (current_user, login_required,
                             permission_required,
                             permission_required_any)
from ..services.conditions import describe, operator_list
from ..services.graph import Graph, edge_kind_of, graph_of
from ..services.lookups import normalize_text
from ..services.workflow import (WorkflowError, action_list, active_workflow,
                                 applicable_stages, approvals_of_user,
                                 cancel_instance, current_stage_of, decide,
                                 live_graph, graph_for, map_state, may_act,
                                 may_approve, may_fill, may_start,
                                 node_by_key, node_by_stage_number, node_form,
                                 node_view, nodes_of_user, pending_nodes,
                                 previous_values_for, reachable_nodes,
                                 stage_form, start_form, startable_templates,
                                 submit_node,
                                 submitted_summary, start_instance, sync_tasks,
                                 waiting_before)
from ._helpers import body, fail, ok, paging

bp = Blueprint("api_workflow", __name__, url_prefix="/api/workflow")

# Anything the workshop might photograph, scan or export. The list is a guard
# against executables rather than a whitelist of useful formats.
BLOCKED_SUFFIXES = {".exe", ".dll", ".bat", ".cmd", ".com", ".scr", ".msi",
                    ".ps1", ".vbs", ".js", ".jar", ".sh", ".php"}
MAX_ATTACHMENT_BYTES = 64 * 1024 * 1024        # 64 MB per file

MAP_READ = ("workflow.map.view", "workflow.view", "workflow.act",
            "workflow.manage")
MAP_WRITE = ("workflow.map.edit", "workflow.manage")


def _attachment_dir():
    path = instance_dir() / "attachments"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _definition(workflow_id=None):
    if workflow_id:
        return db.session.get(WorkflowDefinition, int(workflow_id))
    return active_workflow()


def _locked(definition) -> int:
    """How many runs are on this exact version — the reason not to redraw it."""
    return WorkflowInstance.query.filter(
        WorkflowInstance.workflow_id == definition.id,
        WorkflowInstance.status.in_(INSTANCE_LIVE)).count()


# ── the designer ─────────────────────────────────────────────────────────────
@bp.get("/definition")
@permission_required_any(*MAP_READ)
def get_definition():
    """The map as it stands, plus everything the designer can put on it."""
    workflow = _definition(request.args.get("workflow_id"))
    if workflow is None:
        return fail("هیچ فرایندی تعریف نشده است.", 404)
    sections = (FormSection.query.filter_by(is_active=True)
                .order_by(FormSection.sort_order).all())
    palette_sections = [{"kind": "section", "id": s.id, "code": s.code,
                         "title": s.title, "icon": s.icon,
                         "field_count": len([f for f in s.fields if f.is_active])}
                        for s in sections]
    palette_fields = [{"kind": "field", "id": f.id, "code": f.field_name,
                       "title": f.label,
                       "section": f.section.code if f.section else None,
                       "section_title": f.section.title if f.section else None}
                      for f in FormField.query.filter_by(is_active=True)
                      .order_by(FormField.section_id, FormField.sort_order).all()]
    users = [{"id": u.id, "username": u.username, "full_name": u.full_name,
              "role": u.role, "role_label": u.role_label,
              "is_active": u.is_active}
             for u in AppUser.query.filter_by(is_active=True)
             .order_by(AppUser.first_name, AppUser.username).all()]
    user = current_user()
    return ok({
        "workflow": workflow.to_dict(),
        "graph": Graph(graph_of(workflow)).to_dict(),
        "templates": [_template_row(w) for w in _template_list()],
        "palette": {"sections": palette_sections, "fields": palette_fields},
        "users": users,
        "roles": [{"value": code, "label": spec["label"]}
                  for code, spec in ROLES.items()],
        "node_types": [dict(spec, value=code) for code, spec in NODE_TYPES.items()],
        "edge_kinds": [{"value": k, "label": v} for k, v in EDGE_KINDS.items()],
        "principal_roles": [{"value": k, "label": v}
                            for k, v in PRINCIPAL_ROLES.items()],
        "approval_modes": [{"value": k, "label": v}
                           for k, v in APPROVAL_MODES.items()],
        "template_status": [{"value": k, "label": v}
                            for k, v in TEMPLATE_STATUS.items()],
        "operators": operator_list(),
        "actions": action_list(),
        "field_names": [{"value": f.field_name, "label": f.label}
                        for f in FormField.query.order_by(FormField.section_id,
                                                          FormField.sort_order)],
        "applies_to": [{"value": k, "label": v} for k, v in APPLIES_TO.items()],
        "operation_kinds": [{"value": k, "label": v}
                            for k, v in OPERATION_KINDS.items()],
        "running": _locked(workflow),
        "may_edit": bool(user and any(user.can(p) for p in MAP_WRITE)),
    })


def _template_list():
    return (WorkflowDefinition.query
            .order_by(WorkflowDefinition.code,
                      WorkflowDefinition.version.desc()).all())


def _template_row(workflow):
    data = workflow.to_dict(with_graph=False)
    data["node_count"] = len([n for n in workflow.nodes if n.is_active])
    data["edge_count"] = len(workflow.edges)
    data["running"] = _locked(workflow)
    return data


@bp.get("/templates")
@permission_required_any(*MAP_READ)
def list_templates():
    return ok([_template_row(w) for w in _template_list()])


@bp.post("/templates")
@permission_required_any(*MAP_WRITE)
def create_template():
    """A brand-new process: an empty map with a start and an end on it.

    Everything after this is drawing. No part of the engine has to learn what
    the new process is about.
    """
    payload = body()
    name = normalize_text(payload.get("name") or "")
    if not name:
        return fail("نام فرایند الزامی است.", 422)
    code = normalize_text(payload.get("code") or "") or f"p{secrets.token_hex(3)}"
    if WorkflowDefinition.query.filter_by(code=code).first():
        return fail(f"فرایندی با شناسه «{code}» از قبل وجود دارد.", 422)
    workflow = WorkflowDefinition(
        code=code, version=1, name=name,
        description=payload.get("description") or None,
        status=TEMPLATE_DRAFT,
        is_active=bool(payload.get("is_active", False)))
    db.session.add(workflow)
    db.session.flush()
    for spec in ({"key": "start", "type": "start", "title": "شروع",
                  "number": 0, "x": 80, "y": 200},
                 {"key": "end", "type": "end", "title": "پایان",
                  "number": 1, "x": 520, "y": 200}):
        node = WorkflowStage(workflow_id=workflow.id, node_key=spec["key"],
                             node_type=spec["type"], title=spec["title"],
                             stage_number=spec["number"],
                             pos_x=spec["x"], pos_y=spec["y"],
                             width=170, height=88, is_active=True)
        db.session.add(node)
    record_audit("create", "workflow_definition", workflow.id,
                 summary=f"ایجاد فرایند «{name}»")
    db.session.commit()
    return ok(_template_row(workflow), message="فرایند جدید ساخته شد.")


@bp.put("/templates/<int:workflow_id>")
@permission_required_any(*MAP_WRITE)
def update_template(workflow_id):
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
        workflow.description = payload["description"] or None
    if "status" in payload:
        if payload["status"] not in TEMPLATE_STATUS:
            return fail("وضعیت فرایند نامعتبر است.", 422)
        workflow.status = payload["status"]
    if "is_active" in payload:
        active = payload["is_active"] in (True, "true", "1", 1)
        if active:
            # One live template per code: activating this retires the others.
            (WorkflowDefinition.query
             .filter(WorkflowDefinition.code == workflow.code,
                     WorkflowDefinition.id != workflow.id)
             .update({"is_active": False}, synchronize_session=False))
        workflow.is_active = active
    if "canvas" in payload:
        import json
        workflow.canvas_json = json.dumps(payload["canvas"] or {},
                                          ensure_ascii=False)
    if "config" in payload:
        workflow.set_config(payload["config"] or {})
    record_audit("update", "workflow_definition", workflow.id,
                 summary=f"ویرایش فرایند «{workflow.name}»")
    db.session.commit()
    return ok(_template_row(workflow), message="فرایند ذخیره شد.")


@bp.post("/templates/<int:workflow_id>/version")
@permission_required_any(*MAP_WRITE)
def new_version(workflow_id):
    """Copy a template to a new version, so runs on the old one are untouched.

    The runs already going keep their own snapshot regardless; a new version is
    for keeping the *old drawing* readable next to the new one.
    """
    source = db.session.get(WorkflowDefinition, workflow_id)
    if source is None:
        return fail("فرایند یافت نشد.", 404)
    highest = (db.session.query(db.func.max(WorkflowDefinition.version))
               .filter(WorkflowDefinition.code == source.code).scalar() or 0)
    clone = WorkflowDefinition(
        code=source.code, version=highest + 1, name=source.name,
        description=source.description, status=TEMPLATE_DRAFT,
        is_active=False, canvas_json=source.canvas_json,
        config_json=source.config_json)
    db.session.add(clone)
    db.session.flush()

    mapping = {}
    for node in source.nodes:
        copy = WorkflowStage(
            workflow_id=clone.id, node_key=node.node_key,
            node_type=node.node_type, stage_number=node.stage_number,
            title=node.title, description=node.description, icon=node.icon,
            pos_x=node.pos_x, pos_y=node.pos_y, width=node.width,
            height=node.height, config_json=node.config_json,
            assignee_id=node.assignee_id, applies_to=node.applies_to,
            is_active=node.is_active)
        db.session.add(copy)
        db.session.flush()
        mapping[node.id] = copy.id
        for principal in node.principals:
            db.session.add(WorkflowNodePrincipal(
                node_id=copy.id, role=principal.role,
                principal_kind=principal.principal_kind,
                user_id=principal.user_id, role_code=principal.role_code,
                sort_order=principal.sort_order))
        for item in node.items:
            db.session.add(WorkflowStageItem(
                stage_id=copy.id, section_id=item.section_id,
                field_id=item.field_id, sort_order=item.sort_order,
                applies_to=item.applies_to, is_optional=item.is_optional,
                is_read_only=item.is_read_only))
    for edge in source.edges:
        db.session.add(WorkflowEdge(
            workflow_id=clone.id, source_id=mapping[edge.source_id],
            target_id=mapping[edge.target_id], label=edge.label,
            kind=edge.kind, condition_json=edge.condition_json,
            priority=edge.priority, description=edge.description))
    record_audit("create", "workflow_definition", clone.id,
                 summary=f"نسخه {clone.version} از فرایند «{clone.name}»")
    db.session.commit()
    return ok(_template_row(clone),
              message=f"نسخه {clone.version} ساخته شد؛ نسخه قبلی دست‌نخورده است.")


@bp.delete("/templates/<int:workflow_id>")
@permission_required_any(*MAP_WRITE)
def delete_template(workflow_id):
    workflow = db.session.get(WorkflowDefinition, workflow_id)
    if workflow is None:
        return fail("فرایند یافت نشد.", 404)
    if WorkflowInstance.query.filter_by(workflow_id=workflow.id).count():
        workflow.status = TEMPLATE_ARCHIVED
        workflow.is_active = False
        db.session.commit()
        return ok(_template_row(workflow),
                  message="این فرایند اجرا داشته است، بنابراین حذف نشد و به "
                          "بایگانی رفت تا سابقه‌اش بماند.")
    record_audit("delete", "workflow_definition", workflow.id,
                 summary=f"حذف فرایند «{workflow.name}»")
    db.session.delete(workflow)
    db.session.commit()
    return ok(message="فرایند حذف شد.")


# ── nodes ────────────────────────────────────────────────────────────────────
def _node_payload(node, payload):
    """Apply whatever the properties panel sent. Every field is optional."""
    if "title" in payload:
        title = normalize_text(payload["title"])
        if not title:
            return "عنوان گره الزامی است."
        node.title = title
    if "node_type" in payload:
        if payload["node_type"] not in NODE_TYPES:
            return "نوع گره نامعتبر است."
        node.node_type = payload["node_type"]
    if "description" in payload:
        node.description = payload["description"] or None
    if "icon" in payload:
        node.icon = (payload["icon"] or None)
    for attr, key in (("pos_x", "x"), ("pos_y", "y"),
                      ("width", "width"), ("height", "height")):
        if key in payload and payload[key] is not None:
            try:
                setattr(node, attr, float(payload[key]))
            except (TypeError, ValueError):
                return "مختصات گره باید عدد باشد."
    if "stage_number" in payload and payload["stage_number"] not in (None, ""):
        try:
            node.stage_number = int(payload["stage_number"])
        except (TypeError, ValueError):
            return "شماره فاز باید عدد باشد."
    if "config" in payload:
        node.set_config(payload["config"] or {})
    if "applies_to" in payload and payload["applies_to"] in APPLIES_TO:
        node.applies_to = payload["applies_to"]
    if "is_active" in payload:
        node.is_active = payload["is_active"] in (True, "true", "1", 1)
    if "assignee_id" in payload:
        raw = payload["assignee_id"]
        if raw in (None, "", 0, "0"):
            node.assignee_id = None
        else:
            user = db.session.get(AppUser, int(raw))
            if user is None:
                return "کاربر انتخاب‌شده یافت نشد."
            node.assignee_id = user.id
    if "principals" in payload:
        error = _set_principals(node, payload["principals"])
        if error:
            return error
    return None


def _set_principals(node, rows):
    """Replace a node's people: assignees, approvers, viewers, editors."""
    if not isinstance(rows, list):
        return "فهرست متولیان باید آرایه باشد."
    cleaned = []
    for order, raw in enumerate(rows):
        role = raw.get("role") or "assignee"
        if role not in PRINCIPAL_ROLES:
            return "نقش متولی نامعتبر است."
        kind = raw.get("kind") or raw.get("principal_kind") or PRINCIPAL_USER
        if kind == PRINCIPAL_ROLE:
            code = raw.get("role_code")
            if code not in ROLES:
                return "نقش کاربری انتخاب‌شده نامعتبر است."
            cleaned.append(WorkflowNodePrincipal(
                node_id=node.id, role=role, principal_kind=PRINCIPAL_ROLE,
                role_code=code, sort_order=order))
        else:
            user = db.session.get(AppUser, int(raw.get("user_id") or 0))
            if user is None:
                return "کاربر انتخاب‌شده یافت نشد."
            cleaned.append(WorkflowNodePrincipal(
                node_id=node.id, role=role, principal_kind=PRINCIPAL_USER,
                user_id=user.id, sort_order=order))
    WorkflowNodePrincipal.query.filter_by(node_id=node.id).delete()
    for row in cleaned:
        db.session.add(row)
    # Keep the single-owner column in step for anything still reading it.
    first = next((r for r in cleaned
                  if r.role == "assignee" and r.user_id), None)
    node.assignee_id = first.user_id if first else None
    return None


@bp.post("/nodes")
@permission_required_any(*MAP_WRITE)
def create_node():
    payload = body()
    workflow = _definition(payload.get("workflow_id"))
    if workflow is None:
        return fail("فرایند یافت نشد.", 404)
    keys = {n.node_key for n in workflow.nodes}
    base = payload.get("key") or (payload.get("node_type") or "node")
    key, index = base, 1
    while key in keys:
        index += 1
        key = f"{base}{index}"
    highest = max([n.stage_number for n in workflow.nodes] or [-1])
    node = WorkflowStage(
        workflow_id=workflow.id, node_key=key,
        node_type=payload.get("node_type") or NODE_PHASE,
        stage_number=highest + 1,
        title=normalize_text(payload.get("title") or "") or "گره جدید",
        pos_x=float(payload.get("x") or 60), pos_y=float(payload.get("y") or 60),
        width=float(payload.get("width") or 210),
        height=float(payload.get("height") or 96), is_active=True)
    db.session.add(node)
    db.session.flush()
    error = _node_payload(node, payload)
    if error:
        db.session.rollback()
        return fail(error, 422)
    record_audit("create", "workflow_stage", node.id,
                 summary=f"افزودن گره «{node.title}»")
    db.session.commit()
    return ok(node.to_dict(), message="گره اضافه شد.")


@bp.put("/nodes/<int:node_id>")
@permission_required_any(*MAP_WRITE)
def update_node(node_id):
    node = db.session.get(WorkflowStage, node_id)
    if node is None:
        return fail("گره یافت نشد.", 404)
    error = _node_payload(node, body())
    if error:
        db.session.rollback()
        return fail(error, 422)
    record_audit("update", "workflow_stage", node.id,
                 summary=f"ویرایش گره «{node.title}»")
    db.session.commit()
    db.session.refresh(node)
    return ok(node.to_dict(), message="گره ذخیره شد.")


@bp.delete("/nodes/<int:node_id>")
@permission_required_any(*MAP_WRITE)
def delete_node(node_id):
    """Remove a node from the map without erasing it from history.

    A run that already passed through it keeps its own snapshot, so the phase
    stays visible — with everything recorded on it — in that run's map and
    audit trail. What goes is only its place on the drawing.
    """
    node = db.session.get(WorkflowStage, node_id)
    if node is None:
        return fail("گره یافت نشد.", 404)
    used = WorkflowStageEntry.query.filter_by(stage_id=node.id).count()
    title = node.title
    if used:
        node.is_active = False
        WorkflowEdge.query.filter(
            db.or_(WorkflowEdge.source_id == node.id,
                   WorkflowEdge.target_id == node.id)).delete()
        message = ("این گره در فرایندهای در جریان سابقه دارد، بنابراین از "
                   "نقشه برداشته شد ولی تاریخچه‌اش حفظ شد.")
    else:
        db.session.delete(node)
        message = "گره حذف شد."
    record_audit("delete", "workflow_stage", node_id,
                 summary=f"حذف گره «{title}»")
    db.session.commit()
    return ok(message=message)


@bp.put("/nodes/<int:node_id>/items")
@permission_required_any(*MAP_WRITE)
def set_node_items(node_id):
    """Replace a node's form with what the builder dropped on it."""
    node = db.session.get(WorkflowStage, node_id)
    if node is None:
        return fail("گره یافت نشد.", 404)
    items = body().get("items")
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
                stage_id=node.id, section_id=target.id, sort_order=order,
                applies_to=applies, is_optional=bool(raw.get("is_optional")),
                is_read_only=bool(raw.get("is_read_only"))))
        elif kind == "field":
            target = db.session.get(FormField, int(raw.get("id") or 0))
            if target is None:
                return fail("فیلد انتخاب‌شده یافت نشد.", 422)
            cleaned.append(WorkflowStageItem(
                stage_id=node.id, field_id=target.id, sort_order=order,
                applies_to=applies, is_optional=bool(raw.get("is_optional")),
                is_read_only=bool(raw.get("is_read_only"))))
        else:
            return fail("نوع مورد باید «section» یا «field» باشد.", 422)

    WorkflowStageItem.query.filter_by(stage_id=node.id).delete()
    for item in cleaned:
        db.session.add(item)
    record_audit("update", "workflow_stage", node.id,
                 summary=f"تنظیم فرم گره «{node.title}» ({len(cleaned)} مورد)")
    db.session.commit()
    db.session.refresh(node)
    return ok(node.to_dict(), message="فرم این گره ذخیره شد.")


# ── edges ────────────────────────────────────────────────────────────────────
def _edge_payload(edge, payload):
    if "label" in payload:
        edge.label = normalize_text(payload["label"] or "") or None
    if "kind" in payload:
        edge.kind = edge_kind_of(payload["kind"])
    if "condition" in payload:
        edge.set_condition(payload["condition"] or None)
    if "priority" in payload and payload["priority"] not in (None, ""):
        try:
            edge.priority = int(payload["priority"])
        except (TypeError, ValueError):
            return "اولویت باید عدد باشد."
    if "description" in payload:
        edge.description = payload["description"] or None
    if "target_id" in payload:
        target = db.session.get(WorkflowStage, int(payload["target_id"] or 0))
        if target is None:
            return "گره مقصد یافت نشد."
        edge.target_id = target.id
    return None


@bp.post("/edges")
@permission_required_any(*MAP_WRITE)
def create_edge():
    payload = body()
    source = db.session.get(WorkflowStage, int(payload.get("source_id") or 0))
    target = db.session.get(WorkflowStage, int(payload.get("target_id") or 0))
    if source is None or target is None:
        return fail("گره مبدأ یا مقصد یافت نشد.", 422)
    if source.workflow_id != target.workflow_id:
        return fail("دو گره از دو فرایند مختلف را نمی‌توان وصل کرد.", 422)
    if source.id == target.id:
        return fail("یک گره را نمی‌توان به خودش وصل کرد.", 422)
    if WorkflowEdge.query.filter_by(source_id=source.id,
                                    target_id=target.id).first():
        return fail("این دو گره از قبل به هم وصل‌اند.", 422)
    edge = WorkflowEdge(workflow_id=source.workflow_id, source_id=source.id,
                        target_id=target.id,
                        priority=WorkflowEdge.query.filter_by(
                            source_id=source.id).count())
    error = _edge_payload(edge, payload)
    if error:
        return fail(error, 422)
    db.session.add(edge)
    record_audit("create", "workflow_edge", source.id,
                 summary=f"اتصال «{source.title}» به «{target.title}»")
    db.session.commit()
    return ok(edge.to_dict(), message="اتصال اضافه شد.")


@bp.put("/edges/<int:edge_id>")
@permission_required_any(*MAP_WRITE)
def update_edge(edge_id):
    edge = db.session.get(WorkflowEdge, edge_id)
    if edge is None:
        return fail("اتصال یافت نشد.", 404)
    error = _edge_payload(edge, body())
    if error:
        return fail(error, 422)
    record_audit("update", "workflow_edge", edge.id, summary="ویرایش اتصال")
    db.session.commit()
    return ok(edge.to_dict(), message="اتصال ذخیره شد.")


@bp.delete("/edges/<int:edge_id>")
@permission_required_any(*MAP_WRITE)
def delete_edge(edge_id):
    edge = db.session.get(WorkflowEdge, edge_id)
    if edge is None:
        return fail("اتصال یافت نشد.", 404)
    db.session.delete(edge)
    record_audit("delete", "workflow_edge", edge_id, summary="حذف اتصال")
    db.session.commit()
    return ok(message="اتصال حذف شد.")


@bp.put("/map")
@permission_required_any(*MAP_WRITE)
def save_map():
    """Save a whole drag: positions, sizes and the viewport, in one request."""
    payload = body()
    workflow = _definition(payload.get("workflow_id"))
    if workflow is None:
        return fail("فرایند یافت نشد.", 404)
    nodes = {n.id: n for n in workflow.nodes}
    moved = 0
    for raw in payload.get("nodes") or []:
        node = nodes.get(int(raw.get("id") or 0))
        if node is None:
            continue
        for attr, key in (("pos_x", "x"), ("pos_y", "y"),
                          ("width", "width"), ("height", "height")):
            if raw.get(key) is not None:
                setattr(node, attr, float(raw[key]))
        moved += 1
    if "canvas" in payload:
        import json
        workflow.canvas_json = json.dumps(payload["canvas"] or {},
                                          ensure_ascii=False)
    db.session.commit()
    return ok({"moved": moved}, message="چیدمان نقشه ذخیره شد.")


# ── instances ────────────────────────────────────────────────────────────────
@bp.post("/instances")
@permission_required_any("workflow.act", "workflow.start", "workflow.manage")
def create_instance():
    payload = body()
    try:
        instance = start_instance(payload.get("data") or payload,
                                  current_user(),
                                  code=payload.get("workflow_code"))
    except WorkflowError as exc:
        return fail(str(exc), 422)
    return ok(instance.to_dict(), message="فرایند آغاز شد.")


@bp.get("/start-form")
@permission_required_any("workflow.act", "workflow.start", "workflow.manage")
def get_start_form():
    """What to ask when opening a run — read off the start node, never fixed.

    A process about wells asks for a well; a process about anything else asks
    for whatever its own start node carries. The dialog is the same either way.
    """
    user = current_user()
    allowed = startable_templates(user)
    if not allowed:
        return fail("شما اجازه‌ی شروع هیچ فرایندی را ندارید.", 403)
    code = request.args.get("code")
    workflow = next((w for w in allowed if w.code == code), None) or allowed[0]
    data = start_form(workflow)
    data["options"] = [{"id": w.id, "code": w.code, "name": w.name,
                        "description": w.description} for w in allowed]
    return ok(data)


@bp.get("/instances")
@permission_required_any("workflow.view", "workflow.act", "workflow.manage")
def list_instances():
    page, size = paging(default_size=50)
    query = WorkflowInstance.query
    status = request.args.get("status")
    if status:
        query = query.filter(WorkflowInstance.status == status)
    if request.args.get("workflow_id"):
        query = query.filter(WorkflowInstance.workflow_id
                             == int(request.args["workflow_id"]))
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
              page_size=size, pages=max(1, (total + size - 1) // size),
              statuses=[{"value": k, "label": v}
                        for k, v in INSTANCE_STATUS.items()])


@bp.get("/inbox")
@permission_required_any("workflow.act", "workflow.approve", "workflow.manage")
def inbox():
    """Everything open that wants something from this person.

    Both kinds of work in one list: phases to fill and approvals to give. Not
    only the node the run is "on" — phases do not wait on each other, so their
    owners see them as soon as the run can reach them, and are merely told what
    has not reported yet.
    """
    user = current_user()
    manager = user.role == "admin" or user.can("workflow.manage")
    rows = []
    for instance in (WorkflowInstance.query
                     .filter(WorkflowInstance.status.in_(INSTANCE_LIVE))
                     .order_by(WorkflowInstance.updated_at.desc()).all()):
        sync_tasks(instance)
        outstanding = {n["key"] for n in pending_nodes(instance)}
        mine = [n for n in nodes_of_user(instance, user)
                if n["key"] in outstanding]
        approvals = approvals_of_user(instance, user)
        todo = mine + [n for n in approvals if n not in mine]
        if manager:
            # The admin watches the whole path, so everything still owed is in
            # their کارتابل — not only whatever happens to be assigned to them.
            todo += [n for n in reachable_nodes(instance)
                     if n["key"] in outstanding and n not in todo]
        # A phase may be filled early — that is the point of them being
        # independent — but an approval cannot be given before there is
        # anything to approve, so one that is not open yet is not work.
        todo = [n for n in todo
                if n.get("type") != NODE_APPROVAL
                or n in approvals
                or not waiting_before(instance, n)]
        for node in todo:
            waiting = waiting_before(instance, node)
            data = instance.to_dict(with_entries=False)
            data.update({
                "stage_number": node.get("stage_number"),
                "stage_title": node.get("title"),
                "stage_id": node.get("id"),
                "node_key": node["key"],
                "node_type": node.get("type"),
                "task_kind": ("approve" if node.get("type") == NODE_APPROVAL
                              else "fill"),
                "is_mine": any(n["key"] == node["key"] for n in mine + approvals),
                "unassigned": not (node.get("principals")
                                   or node.get("assignee_id")),
                "ready": node["key"] not in {w["key"] for w in waiting},
                "waiting_on": [{"stage_number": w.get("stage_number"),
                                "node_key": w["key"], "title": w.get("title"),
                                "assignee": (", ".join(
                                    Graph.owner_names(w)) or None)}
                               for w in waiting],
            })
            rows.append(data)
    db.session.commit()
    # Which processes this person may open. More than one is normal once the
    # admin has drawn a second process; the کارتابل offers whichever apply.
    startable = [{"id": w.id, "code": w.code, "name": w.name,
                  "description": w.description} for w in startable_templates(user)]
    return ok(rows, total=len(rows), may_start=bool(startable),
              start_options=startable)


@bp.get("/instances/<int:instance_id>")
@permission_required_any("workflow.act", "workflow.view", "workflow.approve",
                         "workflow.manage")
def get_instance(instance_id):
    instance = db.session.get(WorkflowInstance, instance_id)
    if instance is None:
        return fail("فرایند یافت نشد.", 404)
    user = current_user()
    sync_tasks(instance)
    db.session.commit()

    data = instance.to_dict()
    data["payload"] = instance.payload
    data["attachments"] = [a.to_dict() for a in instance.attachments]

    # Which node to draw: the one asked for, else the first this user owes,
    # else wherever the run currently sits.
    node = None
    wanted_key = request.args.get("node")
    wanted_number = request.args.get("stage")
    if wanted_key:
        node = node_by_key(instance, wanted_key)
    elif wanted_number not in (None, ""):
        node = node_by_stage_number(instance, int(wanted_number))
    if node is None:
        outstanding = {n["key"] for n in pending_nodes(instance)}
        mine = [n for n in nodes_of_user(instance, user)
                if n["key"] in outstanding]
        approvals = approvals_of_user(instance, user)
        node = (mine + approvals + [current_stage_of(instance)])[0] \
            if (mine or approvals or current_stage_of(instance)) else None

    data["may_act"] = may_act(user, instance, node)
    data["may_approve"] = may_approve(user, instance, node) if node else False
    data["form"] = node_form(instance, node) if node else None
    data["node"] = node_view(instance, node) if node else None
    data["my_stages"] = [n.get("stage_number")
                         for n in nodes_of_user(instance, user)]
    data["my_nodes"] = [n["key"] for n in nodes_of_user(instance, user)]
    data["waiting_on"] = [
        {"stage_number": w.get("stage_number"), "node_key": w["key"],
         "title": w.get("title"),
         "assignee": ", ".join(Graph.owner_names(w)) or None}
        for w in waiting_before(instance, node)]
    data["path"] = [node_view(instance, n) for n in applicable_stages(instance)]
    data["map"] = map_state(instance)
    data["events"] = [e.to_dict() for e in instance.events]
    # What everyone before has recorded, read-only: whoever holds the run has
    # to see the work behind it before adding to it.
    data["summary"] = submitted_summary(
        instance, except_key=node["key"] if node else None)
    return ok(data)


@bp.get("/instances/<int:instance_id>/map")
@permission_required_any("workflow.act", "workflow.view", "workflow.map.view",
                         "workflow.manage")
def instance_map(instance_id):
    """The run painted on its own map — the same drawing the designer made."""
    instance = db.session.get(WorkflowInstance, instance_id)
    if instance is None:
        return fail("فرایند یافت نشد.", 404)
    sync_tasks(instance)
    db.session.commit()
    return ok({"instance": instance.to_dict(with_entries=False),
               "map": map_state(instance),
               "graph": graph_for(instance).to_dict(),
               "events": [e.to_dict() for e in instance.events]})


@bp.get("/instances/<int:instance_id>/events")
@permission_required_any("workflow.view", "workflow.act", "workflow.manage")
def instance_events(instance_id):
    instance = db.session.get(WorkflowInstance, instance_id)
    if instance is None:
        return fail("فرایند یافت نشد.", 404)
    return ok([e.to_dict() for e in instance.events])


@bp.post("/instances/<int:instance_id>/form")
@permission_required_any("workflow.act", "workflow.manage")
def preview_form(instance_id):
    """The node's form as it would look given answers not yet submitted.

    A node that asks a routing question before it knows whether to ask anything
    else re-reads its own form the moment that answer changes. Nothing is
    written — the draft is merged only for the length of this call.
    """
    instance = db.session.get(WorkflowInstance, instance_id)
    if instance is None:
        return fail("فرایند یافت نشد.", 404)
    payload = body()
    node = None
    if payload.get("node_key"):
        node = node_by_key(instance, payload["node_key"])
    elif payload.get("stage_number") not in (None, ""):
        node = node_by_stage_number(instance, int(payload["stage_number"]))
    node = node or current_stage_of(instance)
    if node is None:
        return fail("فاز یافت نشد.", 404)
    draft = dict(instance.payload)
    draft.update(payload.get("data") or {})
    return ok({"form": node_form(instance, node, draft=draft),
               "operation_label": instance.operation_label})


@bp.post("/instances/<int:instance_id>/submit")
@permission_required_any("workflow.act", "workflow.manage")
def submit(instance_id):
    instance = db.session.get(WorkflowInstance, instance_id)
    if instance is None:
        return fail("فرایند یافت نشد.", 404)
    payload = body()
    key = payload.get("node_key")
    if not key:
        number = payload.get("stage_number")
        node = (node_by_stage_number(instance, int(number))
                if number not in (None, "") else current_stage_of(instance))
        if node is None:
            return fail("فاز یافت نشد.", 404)
        key = node["key"]
    try:
        submit_node(instance, key, payload.get("data") or {}, current_user(),
                    note=payload.get("note"))
    except WorkflowError as exc:
        return fail(str(exc), 422)
    message = ("فرایند تکمیل شد و رکورد ثبت گردید."
               if instance.record_id else "فاز ثبت شد.")
    return ok(instance.to_dict(), message=message)


@bp.post("/instances/<int:instance_id>/decide")
@permission_required_any("workflow.approve", "workflow.act", "workflow.manage")
def decide_instance(instance_id):
    """Approve or reject, with the comment the کارتابل asks for."""
    instance = db.session.get(WorkflowInstance, instance_id)
    if instance is None:
        return fail("فرایند یافت نشد.", 404)
    payload = body()
    key = payload.get("node_key")
    if not key:
        node = current_stage_of(instance)
        key = node["key"] if node else None
    approved = payload.get("approved") in (True, "true", "1", 1, "approve")
    try:
        decide(instance, key, current_user(), approved,
               comment=payload.get("comment"))
    except WorkflowError as exc:
        return fail(str(exc), 422)
    return ok(instance.to_dict(),
              message="تأیید ثبت شد." if approved else "رد ثبت شد.")


@bp.post("/instances/<int:instance_id>/cancel")
@permission_required_any("workflow.manage")
def cancel(instance_id):
    instance = db.session.get(WorkflowInstance, instance_id)
    if instance is None:
        return fail("فرایند یافت نشد.", 404)
    cancel_instance(instance, (body().get("reason") or "").strip(),
                    current_user())
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
@permission_required_any("workflow.act", "workflow.manage")
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

    node_key = request.form.get("node_key") or instance.current_node
    attachment = WorkflowAttachment(
        instance_id=instance.id, stage_number=instance.current_stage,
        node_key=node_key, filename=original, stored_name=stored,
        size_bytes=size,
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
@permission_required_any("workflow.act", "workflow.view", "workflow.manage")
def list_attachments():
    """Every document attached to any run, in one place.

    The admin and the phase owners both need this: a photo of a plaque taken in
    the workshop is what the final sign-off is judged against, and nobody
    should have to open five processes to find it.
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
        node = (graph_for(instance).node(row.node_key)
                if instance and row.node_key else None)
        item["stage_title"] = (node.get("title") if node else next(
            (s.title for s in (instance.workflow.stages if instance else [])
             if s.stage_number == row.stage_number), None))
        data.append(item)
    return ok(data, total=total, page=page, page_size=size,
              pages=max(1, (total + size - 1) // size))


@bp.get("/attachments/<int:attachment_id>")
@permission_required_any("workflow.act", "workflow.view", "workflow.manage")
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
@permission_required_any("workflow.act", "workflow.manage")
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
