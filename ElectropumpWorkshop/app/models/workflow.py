# -*- coding: utf-8 -*-
"""The process layer: a workflow graph the admin draws, and the runs through it.

Nothing about any particular process lives here. A workshop that pulls and
installs pumps, and one that does something else entirely, are both just rows:
nodes, edges, conditions and principals. The engine walks the graph; it never
knows what «کشیدن» means.

Two layers:

*   the **template** — nodes (start, phase, approval, decision, action, end),
    the edges between them, the condition on each edge, and who fills or
    approves each node. Drawn in the process designer, stored as data.
*   the **instance** — one run through a *snapshot* of that template, its
    tasks, approvals and history. The snapshot is what lets the admin redraw
    the process tomorrow without breaking what is running today.
"""
import json
from datetime import datetime

from ..extensions import db
from ..services.jalali import local_now

# ── node vocabulary ──────────────────────────────────────────────────────────
NODE_START = "start"        # where a run begins
NODE_PHASE = "phase"        # somebody fills a form
NODE_APPROVAL = "approval"  # somebody approves or rejects
NODE_DECISION = "decision"  # no task; routes on a condition
NODE_ACTION = "action"      # the server does something (e.g. write the record)
NODE_END = "end"            # the run finishes

NODE_TYPES = {
    NODE_START:    {"label": "شروع",      "shape": "circle",    "icon": "🚦"},
    NODE_PHASE:    {"label": "فاز",        "shape": "rect",      "icon": "📝"},
    NODE_APPROVAL: {"label": "تأیید",      "shape": "hexagon",   "icon": "✅"},
    NODE_DECISION: {"label": "تصمیم",      "shape": "diamond",   "icon": "🔀"},
    NODE_ACTION:   {"label": "اقدام",      "shape": "rounded",   "icon": "⚙"},
    NODE_END:      {"label": "پایان",      "shape": "diamond",   "icon": "🏁"},
}

# How an approval node decides it is satisfied.
APPROVAL_ANY = "any"        # one approver is enough
APPROVAL_ALL = "all"        # every approver must approve
APPROVAL_QUORUM = "quorum"  # a set number of approvals is enough
APPROVAL_MODES = {
    APPROVAL_ANY: "تأیید یکی از تأییدکنندگان کافی است",
    APPROVAL_ALL: "تأیید همه‌ی تأییدکنندگان الزامی است",
    APPROVAL_QUORUM: "تأیید حداقل تعدادی از تأییدکنندگان کافی است",
}

# What a person is to a node.
ROLE_ASSIGNEE = "assignee"  # fills it
ROLE_APPROVER = "approver"  # approves it
ROLE_VIEWER = "viewer"      # may look
ROLE_EDITOR = "editor"      # may change what was filled
PRINCIPAL_ROLES = {
    ROLE_ASSIGNEE: "مسئول تکمیل",
    ROLE_APPROVER: "تأییدکننده",
    ROLE_VIEWER: "مجاز به مشاهده",
    ROLE_EDITOR: "مجاز به ویرایش",
}

# A principal is a user or a role; groups slot in here later without a schema
# change, which is why this is a kind/value pair rather than a user column.
PRINCIPAL_USER = "user"
PRINCIPAL_ROLE = "role"

# Edge flavours. A plain edge is taken when its condition passes; the approved
# and rejected ones are what an approval node routes down.
EDGE_DEFAULT = "default"
EDGE_APPROVED = "approved"
EDGE_REJECTED = "rejected"
EDGE_ELSE = "else"          # taken when no other edge matched
EDGE_KINDS = {
    EDGE_DEFAULT: "عادی",
    EDGE_APPROVED: "در صورت تأیید",
    EDGE_REJECTED: "در صورت رد",
    EDGE_ELSE: "در غیر این صورت",
}

# ── run vocabulary ───────────────────────────────────────────────────────────
TASK_FILL = "fill"
TASK_APPROVE = "approve"

TASK_PENDING = "pending"
TASK_SUBMITTED = "submitted"
TASK_APPROVED = "approved"
TASK_REJECTED = "rejected"
TASK_SKIPPED = "skipped"
TASK_CANCELLED = "cancelled"
TASK_STATUS = {
    TASK_PENDING: "در انتظار",
    TASK_SUBMITTED: "ثبت شده",
    TASK_APPROVED: "تأیید شده",
    TASK_REJECTED: "رد شده",
    TASK_SKIPPED: "طی نشده",
    TASK_CANCELLED: "لغو شده",
}

INSTANCE_DRAFT = "draft"
INSTANCE_RUNNING = "running"
INSTANCE_WAITING = "waiting_approval"
INSTANCE_REJECTED = "rejected"
INSTANCE_RETURNED = "returned"
INSTANCE_COMPLETED = "completed"
INSTANCE_CANCELLED = "cancelled"
INSTANCE_STATUS = {
    INSTANCE_DRAFT: "پیش‌نویس",
    INSTANCE_RUNNING: "در جریان",
    INSTANCE_WAITING: "منتظر تأیید",
    INSTANCE_REJECTED: "ردشده",
    INSTANCE_RETURNED: "برگشت‌خورده",
    INSTANCE_COMPLETED: "تکمیل شده",
    INSTANCE_CANCELLED: "لغو شده",
}
# Statuses that mean the run is over, one way or another.
INSTANCE_CLOSED = (INSTANCE_COMPLETED, INSTANCE_CANCELLED, INSTANCE_REJECTED)
# …and the ones a کارتابل still has work for.
INSTANCE_LIVE = (INSTANCE_DRAFT, INSTANCE_RUNNING, INSTANCE_WAITING,
                 INSTANCE_RETURNED)

TEMPLATE_DRAFT = "draft"
TEMPLATE_PUBLISHED = "published"
TEMPLATE_ARCHIVED = "archived"
TEMPLATE_STATUS = {
    TEMPLATE_DRAFT: "پیش‌نویس",
    TEMPLATE_PUBLISHED: "منتشرشده",
    TEMPLATE_ARCHIVED: "بایگانی",
}


def _loads(text, fallback):
    if not text:
        return fallback
    try:
        value = json.loads(text)
    except ValueError:
        return fallback
    return value if isinstance(value, type(fallback)) else fallback


class WorkflowDefinition(db.Model):
    """A process template: one drawing of one process, at one version."""
    __tablename__ = "workflow_definitions"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(60), nullable=False, index=True)
    version = db.Column(db.Integer, nullable=False, default=1)
    name = db.Column(db.String(160), nullable=False)
    description = db.Column(db.Text)
    status = db.Column(db.String(16), nullable=False, default=TEMPLATE_DRAFT,
                       index=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    # Canvas viewport (zoom/offset) so the map opens where it was left.
    canvas_json = db.Column(db.Text)
    # Template-wide settings: who may start it, what it is for, defaults.
    config_json = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=local_now, nullable=False)
    updated_at = db.Column(db.DateTime, default=local_now, onupdate=local_now,
                           nullable=False)

    __table_args__ = (db.UniqueConstraint("code", "version",
                                          name="uq_workflow_code_version"),)

    nodes = db.relationship("WorkflowStage", back_populates="workflow",
                            cascade="all, delete-orphan",
                            order_by="WorkflowStage.stage_number")
    edges = db.relationship("WorkflowEdge", back_populates="workflow",
                            cascade="all, delete-orphan",
                            order_by="WorkflowEdge.priority")

    # Kept as an alias so older call sites reading `.stages` keep working.
    @property
    def stages(self):
        return self.nodes

    @property
    def canvas(self) -> dict:
        return _loads(self.canvas_json, {})

    @property
    def config(self) -> dict:
        return _loads(self.config_json, {})

    def set_config(self, data: dict):
        self.config_json = json.dumps(data or {}, ensure_ascii=False)

    @property
    def instance_count(self):
        from .workflow import WorkflowInstance
        return WorkflowInstance.query.filter_by(workflow_id=self.id).count()

    def to_dict(self, with_graph=True):
        data = {
            "id": self.id, "code": self.code, "version": self.version,
            "name": self.name, "description": self.description,
            "status": self.status,
            "status_label": TEMPLATE_STATUS.get(self.status, self.status),
            "is_active": self.is_active, "canvas": self.canvas,
            "config": self.config,
        }
        if with_graph:
            data["nodes"] = [n.to_dict() for n in self.nodes]
            data["edges"] = [e.to_dict() for e in self.edges]
            data["stages"] = data["nodes"]     # alias for older callers
        return data


class WorkflowStage(db.Model):
    """A node on the map.

    Still called ``workflow_stages`` in the database because that is where the
    rows already live and the process builder has been writing them; what
    changed is that a row is now any kind of node, not only a form-filling
    stage, and its place in the flow comes from its edges rather than from
    ``stage_number``.
    """
    __tablename__ = "workflow_stages"
    __table_args__ = (db.UniqueConstraint("workflow_id", "stage_number",
                                          name="uq_workflow_stage_number"),)

    id = db.Column(db.Integer, primary_key=True)
    workflow_id = db.Column(db.Integer,
                            db.ForeignKey("workflow_definitions.id",
                                          ondelete="CASCADE"),
                            nullable=False, index=True)
    # Stable identity across versions — an instance snapshot refers to this,
    # not to the row id, so a redrawn map still matches its history.
    node_key = db.Column(db.String(60), index=True)
    node_type = db.Column(db.String(16), nullable=False, default=NODE_PHASE,
                          index=True)
    stage_number = db.Column(db.Integer, nullable=False)   # display order only
    title = db.Column(db.String(160), nullable=False)
    description = db.Column(db.Text)
    icon = db.Column(db.String(16))

    # Where the box sits on the canvas.
    pos_x = db.Column(db.Float, nullable=False, default=0)
    pos_y = db.Column(db.Float, nullable=False, default=0)
    width = db.Column(db.Float, nullable=False, default=210)
    height = db.Column(db.Float, nullable=False, default=90)

    # Per-type settings: approval mode and quorum, action name, and so on.
    config_json = db.Column(db.Text)

    # The single assignee column predates principals. It is still written so an
    # older page keeps working, but the principals table is the real answer.
    assignee_id = db.Column(db.Integer, db.ForeignKey("app_users.id",
                                                      ondelete="SET NULL"),
                            index=True)
    applies_to = db.Column(db.String(10), nullable=False, default="both")
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    workflow = db.relationship("WorkflowDefinition", back_populates="nodes")
    assignee = db.relationship("AppUser", foreign_keys=[assignee_id])
    items = db.relationship("WorkflowStageItem", back_populates="stage",
                            cascade="all, delete-orphan",
                            order_by="WorkflowStageItem.sort_order")
    principals = db.relationship("WorkflowNodePrincipal", back_populates="node",
                                 cascade="all, delete-orphan")
    out_edges = db.relationship(
        "WorkflowEdge", back_populates="source",
        foreign_keys="WorkflowEdge.source_id",
        cascade="all, delete-orphan", order_by="WorkflowEdge.priority")

    @property
    def config(self) -> dict:
        return _loads(self.config_json, {})

    def set_config(self, data: dict):
        self.config_json = json.dumps(data or {}, ensure_ascii=False)

    @property
    def key(self) -> str:
        return self.node_key or f"n{self.id}"

    def principal_ids(self, role: str) -> list:
        return [p.user_id for p in self.principals
                if p.role == role and p.user_id]

    def to_dict(self):
        return {
            "id": self.id, "key": self.key, "node_type": self.node_type,
            "type_label": NODE_TYPES.get(self.node_type, {}).get("label",
                                                                 self.node_type),
            "shape": NODE_TYPES.get(self.node_type, {}).get("shape", "rect"),
            "stage_number": self.stage_number,
            "title": self.title, "description": self.description,
            "icon": self.icon or NODE_TYPES.get(self.node_type, {}).get("icon"),
            "x": self.pos_x, "y": self.pos_y,
            "width": self.width, "height": self.height,
            "config": self.config,
            "is_active": self.is_active,
            "applies_to": self.applies_to,
            "assignee_id": self.assignee_id,
            "assignee_name": self.assignee.full_name if self.assignee else None,
            "principals": [p.to_dict() for p in self.principals],
            "items": [i.to_dict() for i in self.items],
        }


class WorkflowNodePrincipal(db.Model):
    """Who a node belongs to — as assignee, approver, viewer or editor.

    A pair of (kind, value) rather than a user column, so a role today and a
    group tomorrow need no schema change, and so a node can have as many
    approvers as the process calls for.
    """
    __tablename__ = "workflow_node_principals"

    id = db.Column(db.Integer, primary_key=True)
    node_id = db.Column(db.Integer, db.ForeignKey("workflow_stages.id",
                                                  ondelete="CASCADE"),
                        nullable=False, index=True)
    role = db.Column(db.String(16), nullable=False, default=ROLE_ASSIGNEE,
                     index=True)
    principal_kind = db.Column(db.String(16), nullable=False,
                               default=PRINCIPAL_USER)
    user_id = db.Column(db.Integer, db.ForeignKey("app_users.id",
                                                  ondelete="CASCADE"),
                        index=True)
    role_code = db.Column(db.String(40))          # when principal_kind == role
    sort_order = db.Column(db.Integer, nullable=False, default=0)

    node = db.relationship("WorkflowStage", back_populates="principals")
    user = db.relationship("AppUser", foreign_keys=[user_id])

    def to_dict(self):
        return {
            "id": self.id, "role": self.role,
            "role_label": PRINCIPAL_ROLES.get(self.role, self.role),
            "principal_kind": self.principal_kind,
            "user_id": self.user_id,
            "user_name": self.user.full_name if self.user else None,
            "username": self.user.username if self.user else None,
            "role_code": self.role_code,
        }


class WorkflowEdge(db.Model):
    """An arrow: where the run goes next, and what has to be true for it."""
    __tablename__ = "workflow_edges"

    id = db.Column(db.Integer, primary_key=True)
    workflow_id = db.Column(db.Integer,
                            db.ForeignKey("workflow_definitions.id",
                                          ondelete="CASCADE"),
                            nullable=False, index=True)
    source_id = db.Column(db.Integer, db.ForeignKey("workflow_stages.id",
                                                    ondelete="CASCADE"),
                          nullable=False, index=True)
    target_id = db.Column(db.Integer, db.ForeignKey("workflow_stages.id",
                                                    ondelete="CASCADE"),
                          nullable=False, index=True)
    label = db.Column(db.String(160))
    kind = db.Column(db.String(16), nullable=False, default=EDGE_DEFAULT)
    # The JSON condition language in services/conditions.py. Empty = always.
    condition_json = db.Column(db.Text)
    # Lower goes first; the first edge whose condition passes wins.
    priority = db.Column(db.Integer, nullable=False, default=0)
    description = db.Column(db.Text)

    workflow = db.relationship("WorkflowDefinition", back_populates="edges")
    source = db.relationship("WorkflowStage", foreign_keys=[source_id],
                             back_populates="out_edges")
    target = db.relationship("WorkflowStage", foreign_keys=[target_id])

    @property
    def condition(self) -> dict:
        return _loads(self.condition_json, {})

    def set_condition(self, data):
        self.condition_json = (json.dumps(data, ensure_ascii=False)
                               if data else None)

    def to_dict(self):
        return {
            "id": self.id, "source_id": self.source_id,
            "target_id": self.target_id,
            "source_key": self.source.key if self.source else None,
            "target_key": self.target.key if self.target else None,
            "label": self.label, "kind": self.kind,
            "kind_label": EDGE_KINDS.get(self.kind, self.kind),
            "condition": self.condition, "priority": self.priority,
            "description": self.description,
        }


class WorkflowStageItem(db.Model):
    """A section — or a single field — the node asks for."""
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
    applies_to = db.Column(db.String(10), nullable=False, default="both")
    is_optional = db.Column(db.Boolean, nullable=False, default=False)
    # Shown but not editable here — the well, once step zero has settled it.
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
            "is_optional": self.is_optional,
            "is_read_only": self.is_read_only,
        }


class WorkflowInstance(db.Model):
    """One run through a template.

    ``graph_json`` is a snapshot of the template taken when the run started.
    Redrawing the map afterwards changes what new runs do and leaves this one
    exactly as it was — which is the whole point of versioning here.
    """
    __tablename__ = "workflow_instances"

    id = db.Column(db.Integer, primary_key=True)
    workflow_id = db.Column(db.Integer,
                            db.ForeignKey("workflow_definitions.id"),
                            nullable=False, index=True)
    template_version = db.Column(db.Integer, nullable=False, default=1)
    graph_json = db.Column(db.Text)

    # Kept for the wells this workshop runs on; both are optional as far as the
    # engine is concerned — a template need not involve a well at all.
    operation_kind = db.Column(db.String(10), index=True)
    well_id = db.Column(db.Integer, db.ForeignKey("wells.id"), index=True)
    well_name_raw = db.Column(db.String(200))

    current_stage = db.Column(db.Integer, nullable=False, default=0, index=True)
    # Where the run is on the map. ``current_stage`` is the same thing as a
    # number, kept because the records table and the exports read it.
    current_node = db.Column(db.String(60), index=True)
    status = db.Column(db.String(24), nullable=False, default=INSTANCE_RUNNING,
                       index=True)
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
                              order_by="WorkflowStageEntry.id")
    attachments = db.relationship("WorkflowAttachment", back_populates="instance",
                                  cascade="all, delete-orphan")
    events = db.relationship("WorkflowEvent", back_populates="instance",
                             cascade="all, delete-orphan",
                             order_by="WorkflowEvent.id")

    @property
    def payload(self) -> dict:
        return _loads(self.payload_json, {})

    def set_payload(self, data: dict):
        self.payload_json = json.dumps(data or {}, ensure_ascii=False)

    def merge_payload(self, data: dict):
        merged = self.payload
        merged.update(data or {})
        self.set_payload(merged)

    @property
    def graph(self) -> dict:
        """The template as it stood when this run began."""
        return _loads(self.graph_json, {})

    def _node_title(self, key):
        """A node's name as this run knew it — from its own snapshot, so a
        phase the admin has since deleted still reads as itself here."""
        if not key:
            return None
        for node in (self.graph.get("nodes") or []):
            if node.get("key") == key:
                return node.get("title")
        return key

    def set_graph(self, data: dict):
        self.graph_json = json.dumps(data or {}, ensure_ascii=False)

    @property
    def operation_label(self):
        return self.payload.get("operation_kind") or "—"

    def to_dict(self, with_entries=True):
        from ..services.jalali import tehran_time_str, to_jalali_str
        data = {
            "id": self.id, "workflow_id": self.workflow_id,
            "template_version": self.template_version,
            "operation_kind": self.operation_kind,
            "operation_label": self.operation_label,
            "well_id": self.well_id,
            "well": self.well.name if self.well else self.well_name_raw,
            "well_pm_code": self.well.pm_code if self.well else None,
            "current_stage": self.current_stage,
            "current_node": self.current_node,
            "current_node_title": self._node_title(self.current_node),
            "status": self.status,
            "status_label": INSTANCE_STATUS.get(self.status, self.status),
            "record_id": self.record_id,
            "created_by": self.created_by,
            "created_by_name": self.author.full_name if self.author else None,
            "created_at_j": to_jalali_str(self.created_at),
            "created_at_time": tehran_time_str(self.created_at, with_seconds=False),
            "updated_at_j": to_jalali_str(self.updated_at),
            "completed_at_j": (to_jalali_str(self.completed_at)
                               if self.completed_at else None),
            "attachment_count": len(self.attachments),
            "workflow_name": self.workflow.name if self.workflow else None,
            "workflow_code": self.workflow.code if self.workflow else None,
        }
        if with_entries:
            data["entries"] = [e.to_dict() for e in self.entries]
        return data


class WorkflowStageEntry(db.Model):
    """A task: fill this node, or approve it.

    One row per person per node for approvals, one row per node for filling.
    """
    __tablename__ = "workflow_stage_entries"

    id = db.Column(db.Integer, primary_key=True)
    instance_id = db.Column(db.Integer,
                            db.ForeignKey("workflow_instances.id",
                                          ondelete="CASCADE"),
                            nullable=False, index=True)
    stage_id = db.Column(db.Integer, db.ForeignKey("workflow_stages.id",
                                                   ondelete="SET NULL"))
    node_key = db.Column(db.String(60), index=True)
    stage_number = db.Column(db.Integer, nullable=False, index=True)
    task_kind = db.Column(db.String(12), nullable=False, default=TASK_FILL,
                          index=True)
    status = db.Column(db.String(16), nullable=False, default=TASK_PENDING,
                       index=True)
    # Who it is *for* (approvals name their approver up front); user_id is who
    # actually acted.
    assignee_id = db.Column(db.Integer, db.ForeignKey("app_users.id"),
                            index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("app_users.id"))
    payload_json = db.Column(db.Text)
    comment = db.Column(db.Text)
    note = db.Column(db.Text)
    started_at = db.Column(db.DateTime, default=local_now, nullable=False)
    submitted_at = db.Column(db.DateTime)

    instance = db.relationship("WorkflowInstance", back_populates="entries")
    stage = db.relationship("WorkflowStage")
    user = db.relationship("AppUser", foreign_keys=[user_id])
    assignee = db.relationship("AppUser", foreign_keys=[assignee_id])

    @property
    def payload(self) -> dict:
        return _loads(self.payload_json, {})

    def set_payload(self, data: dict):
        self.payload_json = json.dumps(data or {}, ensure_ascii=False)

    def to_dict(self):
        from ..services.jalali import tehran_time_str, to_jalali_str
        return {
            "id": self.id, "stage_number": self.stage_number,
            "stage_id": self.stage_id, "node_key": self.node_key,
            "task_kind": self.task_kind,
            "title": self.stage.title if self.stage else None,
            "status": self.status,
            "status_label": TASK_STATUS.get(self.status, self.status),
            "user_id": self.user_id,
            "user_name": self.user.full_name if self.user else None,
            "assignee_id": self.assignee_id,
            "assignee_name": (self.assignee.full_name if self.assignee
                              else self.stage.assignee.full_name
                              if self.stage and self.stage.assignee else None),
            "comment": self.comment, "note": self.note,
            "submitted_at_j": (to_jalali_str(self.submitted_at)
                               if self.submitted_at else None),
            "submitted_at_time": (tehran_time_str(self.submitted_at,
                                                  with_seconds=False)
                                  if self.submitted_at else None),
            "payload": self.payload,
        }


class WorkflowEvent(db.Model):
    """Audit trail: everything that happened to one run, in order."""
    __tablename__ = "workflow_events"

    id = db.Column(db.Integer, primary_key=True)
    instance_id = db.Column(db.Integer,
                            db.ForeignKey("workflow_instances.id",
                                          ondelete="CASCADE"),
                            nullable=False, index=True)
    action = db.Column(db.String(40), nullable=False)   # started, submitted, …
    from_node = db.Column(db.String(60))
    to_node = db.Column(db.String(60))
    status = db.Column(db.String(24))
    comment = db.Column(db.Text)
    user_id = db.Column(db.Integer, db.ForeignKey("app_users.id"))
    payload_json = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=local_now, nullable=False,
                           index=True)

    instance = db.relationship("WorkflowInstance", back_populates="events")
    user = db.relationship("AppUser", foreign_keys=[user_id])

    ACTION_LABELS = {
        "started": "شروع فرایند",
        "submitted": "ثبت فاز",
        "approved": "تأیید",
        "rejected": "رد",
        "routed": "انتقال به فاز بعد",
        "skipped": "عبور از فاز",
        "action": "اجرای اقدام",
        "completed": "تکمیل فرایند",
        "cancelled": "لغو فرایند",
        "reopened": "بازگشت به فاز قبل",
    }

    @property
    def payload(self) -> dict:
        return _loads(self.payload_json, {})

    def to_dict(self):
        from ..services.jalali import tehran_time_str, to_jalali_str
        return {
            "id": self.id, "action": self.action,
            "action_label": self.ACTION_LABELS.get(self.action, self.action),
            "from_node": self.from_node, "to_node": self.to_node,
            "from_title": (self.instance._node_title(self.from_node)
                           if self.instance else self.from_node),
            "to_title": (self.instance._node_title(self.to_node)
                         if self.instance else self.to_node),
            "status": self.status, "comment": self.comment,
            "user_id": self.user_id,
            "user_name": self.user.full_name if self.user else None,
            "at_j": to_jalali_str(self.created_at),
            "at_time": tehran_time_str(self.created_at, with_seconds=False),
            "payload": self.payload,
        }


class WorkflowAttachment(db.Model):
    """A document attached while the run passed through a node."""
    __tablename__ = "workflow_attachments"

    id = db.Column(db.Integer, primary_key=True)
    instance_id = db.Column(db.Integer,
                            db.ForeignKey("workflow_instances.id",
                                          ondelete="CASCADE"),
                            nullable=False, index=True)
    stage_number = db.Column(db.Integer, index=True)
    node_key = db.Column(db.String(60))
    filename = db.Column(db.String(260), nullable=False)
    stored_name = db.Column(db.String(160), nullable=False)
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
            "stage_number": self.stage_number, "node_key": self.node_key,
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


# Older code imported these names; keep them resolvable.
OPERATION_KINDS = {"pull": "کشیدن", "install": "نصب"}
APPLIES_BOTH, APPLIES_PULL, APPLIES_INSTALL = "both", "pull", "install"
APPLIES_TO = {APPLIES_BOTH: "هر دو عملیات", APPLIES_PULL: "فقط کشیدن",
              APPLIES_INSTALL: "فقط نصب"}
ENTRY_PENDING, ENTRY_SUBMITTED = TASK_PENDING, TASK_SUBMITTED
ENTRY_SKIPPED, ENTRY_ARCHIVED, ENTRY_DEFERRED = TASK_SKIPPED, "archived", "deferred"
ENTRY_STATUS = dict(TASK_STATUS, archived="بایگانی", deferred="موکول به بعد")
INSTANCE_OPEN = INSTANCE_RUNNING
