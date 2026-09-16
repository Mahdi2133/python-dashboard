# -*- coding: utf-8 -*-
"""The process engine: whose turn it is, what they see, and where it goes next.

The engine knows nothing about pumps, wells, water centres or the people who
work on them. It reads a map — nodes, arrows, conditions, principals — and
walks it. Every rule that used to be written here as an ``if`` about a stage
number or a Persian answer is now a row the admin can draw, rename or delete
in the process designer:

*   which node starts the run, and who may start it → the start node and its
    principals;
*   which branch a run takes → the condition on each arrow;
*   who fills a phase, who may see it, who approves it and how many of them →
    the node's principals and its approval settings;
*   what happens at the end → an action node bound to a named handler.

A run keeps a snapshot of the map it started on, so redrawing the process
tomorrow changes what starts tomorrow and leaves today's runs untouched.

Phases do not block each other. Every phase the run can still reach is open to
its owner from the moment the process starts; if the phases before it have not
reported, the owner is *told* rather than stopped. Nodes that genuinely cannot
run early — an approval, the action that closes the run — wait, and say so.
"""
from __future__ import annotations

import logging

from ..extensions import db
from ..models import (FormField, FormSection, Record, WorkflowDefinition,
                      WorkflowInstance, WorkflowStage, WorkflowStageEntry)
from ..models.workflow import (APPROVAL_ALL, APPROVAL_ANY, APPROVAL_QUORUM,
                               EDGE_APPROVED, EDGE_DEFAULT, EDGE_ELSE,
                               EDGE_REJECTED,
                               INSTANCE_CANCELLED, INSTANCE_COMPLETED,
                               INSTANCE_REJECTED, INSTANCE_RETURNED,
                               INSTANCE_RUNNING, INSTANCE_WAITING,
                               NODE_ACTION, NODE_APPROVAL, NODE_DECISION,
                               NODE_END, NODE_PHASE, NODE_START,
                               ROLE_APPROVER, ROLE_ASSIGNEE, ROLE_EDITOR,
                               ROLE_VIEWER, TASK_APPROVE, TASK_APPROVED,
                               TASK_CANCELLED, TASK_FILL, TASK_PENDING,
                               TASK_REJECTED, TASK_SKIPPED, TASK_STATUS,
                               TASK_SUBMITTED, TEMPLATE_ARCHIVED,
                               TEMPLATE_PUBLISHED)
from .audit import record_audit
from .conditions import evaluate, fields_used
from .graph import Graph, graph_of
from .jalali import local_now, to_jalali_str
from .lookups import normalize_text
from .records import ValidationError, create_record, resolve_well

log = logging.getLogger(__name__)

DONE_TASK = (TASK_SUBMITTED, TASK_APPROVED)


class WorkflowError(Exception):
    """A process rule refused the move. Carries a Persian message."""


# ── templates ────────────────────────────────────────────────────────────────
def active_workflow(code: str | None = None) -> WorkflowDefinition | None:
    """The template new runs start on — the newest active version of a code.

    Without a code this is the *default* process: the one flagged as such, and
    otherwise the oldest, which on this installation is the workshop's own.
    Several processes may be active at once; picking between them is the
    caller's business, not a guess made here.
    """
    live = (WorkflowDefinition.query
            .filter(WorkflowDefinition.is_active.is_(True),
                    WorkflowDefinition.status != TEMPLATE_ARCHIVED))
    if code:
        return live.filter_by(code=code).order_by(
            WorkflowDefinition.version.desc()).first()
    rows = live.order_by(WorkflowDefinition.id).all()
    if not rows:
        return None
    default = next((w for w in rows if (w.config or {}).get("is_default")),
                   rows[0])
    return max((w for w in rows if w.code == default.code),
               key=lambda w: w.version)


def startable_templates(user) -> list:
    """Every active process this person is allowed to open."""
    seen, out = set(), []
    for workflow in (WorkflowDefinition.query
                     .filter(WorkflowDefinition.is_active.is_(True),
                             WorkflowDefinition.status != TEMPLATE_ARCHIVED)
                     .order_by(WorkflowDefinition.id,
                               WorkflowDefinition.version.desc()).all()):
        if workflow.code in seen or not may_start(user, workflow):
            continue
        seen.add(workflow.code)
        out.append(workflow)
    return out


def workflow_templates() -> list:
    """Every template the admin may run or edit, newest version of each first."""
    rows = (WorkflowDefinition.query
            .order_by(WorkflowDefinition.code,
                      WorkflowDefinition.version.desc()).all())
    return rows


def live_graph(definition: WorkflowDefinition | None = None) -> Graph:
    definition = definition or active_workflow()
    return Graph(graph_of(definition)) if definition else Graph({})


def graph_for(instance: WorkflowInstance) -> Graph:
    """The map this run is on: its own snapshot, or the live one if it predates
    snapshots (an instance created before the designer existed)."""
    data = instance.graph
    if data and data.get("nodes"):
        return Graph(data)
    graph = live_graph(instance.workflow)
    if graph:
        instance.set_graph(graph.data)
    return graph


# ── context ──────────────────────────────────────────────────────────────────
def context_of(instance: WorkflowInstance, draft: dict | None = None) -> dict:
    """What the conditions on the arrows are evaluated against.

    Everything anybody has answered, plus a few facts about the run itself
    under ``__`` names so a condition can route on them without clashing with
    a form field.
    """
    context = dict(instance.payload or {})
    context.update(draft or {})
    context["__status"] = instance.status
    context["__well"] = instance.well.name if instance.well else instance.well_name_raw
    context["__created_by"] = instance.created_by
    for entry in instance.entries:
        if entry.node_key and entry.task_kind == TASK_FILL:
            context[f"__status:{entry.node_key}"] = entry.status
    return context


# ── tasks ────────────────────────────────────────────────────────────────────
def _tasks_of(instance, key, kind=None) -> list:
    return [e for e in instance.entries
            if e.node_key == key and (kind is None or e.task_kind == kind)]


def fill_task(instance, key):
    tasks = _tasks_of(instance, key, TASK_FILL)
    return tasks[0] if tasks else None


def _ensure_fill_task(instance, node):
    task = fill_task(instance, node["key"])
    if task is None:
        task = WorkflowStageEntry(
            instance_id=instance.id, stage_id=node.get("id"),
            node_key=node["key"], stage_number=node.get("stage_number") or 0,
            task_kind=TASK_FILL, status=TASK_PENDING)
        db.session.add(task)
        instance.entries.append(task)
    ids = Graph.user_ids(node, ROLE_ASSIGNEE)
    if task.assignee_id is None:
        task.assignee_id = ids[0] if ids else node.get("assignee_id")
    return task


def _approver_users(node) -> list:
    """The approvers of a node, as user ids — roles expanded to their holders."""
    from ..models.auth import AppUser
    ids = list(Graph.user_ids(node, ROLE_APPROVER))
    codes = Graph.role_codes(node, ROLE_APPROVER)
    if codes:
        rows = AppUser.query.filter(AppUser.role.in_(codes),
                                    AppUser.is_active.is_(True)).all()
        ids.extend(u.id for u in rows)
    seen, out = set(), []
    for value in ids:
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def _ensure_approval_tasks(instance, node):
    """One task per approver, created when the approval opens."""
    existing = {t.assignee_id: t for t in _tasks_of(instance, node["key"],
                                                    TASK_APPROVE)}
    wanted = _approver_users(node)
    if not wanted:
        # Nobody was named. Leave one unassigned task so the run is visibly
        # stuck on a setting the admin must fix, rather than silently open.
        wanted = [None]
    for user_id in wanted:
        if user_id in existing:
            continue
        task = WorkflowStageEntry(
            instance_id=instance.id, stage_id=node.get("id"),
            node_key=node["key"], stage_number=node.get("stage_number") or 0,
            task_kind=TASK_APPROVE, status=TASK_PENDING, assignee_id=user_id)
        db.session.add(task)
        instance.entries.append(task)
    return _tasks_of(instance, node["key"], TASK_APPROVE)


# ── node state ───────────────────────────────────────────────────────────────
def approval_state(instance, node) -> str:
    """``approved``, ``rejected`` or ``pending`` for one approval node."""
    tasks = _tasks_of(instance, node["key"], TASK_APPROVE)
    if not tasks:
        return TASK_PENDING
    config = node.get("config") or {}
    mode = config.get("approval_mode") or APPROVAL_ANY
    approved = [t for t in tasks if t.status == TASK_APPROVED]
    rejected = [t for t in tasks if t.status == TASK_REJECTED]
    # «یک رد کافی است»: the admin can say that any single refusal ends it,
    # rather than waiting to see whether the rest could still carry it.
    if rejected and config.get("reject_on_first"):
        return TASK_REJECTED
    if mode == APPROVAL_ALL:
        if rejected:
            return TASK_REJECTED
        return TASK_APPROVED if len(approved) == len(tasks) else TASK_PENDING
    if mode == APPROVAL_QUORUM:
        need = max(1, int(config.get("approval_quorum") or 2))
        if len(approved) >= need:
            return TASK_APPROVED
        # Refused only once the remaining approvers could not reach the number.
        if len(tasks) - len(rejected) < need:
            return TASK_REJECTED
        return TASK_PENDING
    # any
    if approved:
        return TASK_APPROVED
    return TASK_REJECTED if len(rejected) == len(tasks) else TASK_PENDING


def node_status(instance, node) -> str:
    """One node's state on this run, in task words."""
    kind = node.get("type")
    if kind == NODE_APPROVAL:
        return approval_state(instance, node)
    task = fill_task(instance, node["key"])
    if task is not None:
        return task.status
    if kind == NODE_START:
        return TASK_SUBMITTED
    return TASK_PENDING


def is_done(instance, node) -> bool:
    return node_status(instance, node) in DONE_TASK


# ── planning ─────────────────────────────────────────────────────────────────
def plan(instance, draft: dict | None = None) -> dict:
    """Which nodes this run can still reach, given everything answered so far.

    An approval holds shut: until it is given, nothing behind it is on the
    table, and when it is refused the only way out is the «در صورت رد» arrow.
    """
    graph = graph_for(instance)
    context = context_of(instance, draft)

    def gate(node, edge):
        kind = edge.get("kind") or EDGE_DEFAULT
        if node.get("type") == NODE_APPROVAL:
            state = approval_state(instance, node)
            if state == TASK_APPROVED:
                return kind in (EDGE_APPROVED, EDGE_DEFAULT, EDGE_ELSE)
            if state == TASK_REJECTED:
                return kind == EDGE_REJECTED
            return False
        # Elsewhere an approved/rejected arrow has nothing to say.
        return kind not in (EDGE_APPROVED, EDGE_REJECTED)

    return graph.reachable(context, gate=gate)


def reachable_nodes(instance, draft=None) -> list:
    graph = graph_for(instance)
    found = plan(instance, draft)
    return [n for n in graph.ordered() if n["key"] in found]


def human_nodes(instance) -> list:
    """Reachable nodes somebody has to do something with."""
    return [n for n in reachable_nodes(instance)
            if n.get("type") in (NODE_PHASE, NODE_APPROVAL)]


def pending_nodes(instance) -> list:
    """Reachable human nodes still owed."""
    return [n for n in human_nodes(instance) if not is_done(instance, n)]


def feeders(graph, node, found) -> list:
    """The human nodes that feed this one directly.

    Directly means through the arrows into it, passing straight through
    decisions and actions, which do no work of their own. An approval waits
    for what it is meant to approve — not for every phase anywhere upstream,
    which in a chain would be all of them.
    """
    out, seen, queue = [], {node["key"]}, [node["key"]]
    while queue:
        current = queue.pop(0)
        for edge in graph.in_edges(current):
            source = edge["source"]
            if source in seen or source not in found:
                continue
            seen.add(source)
            upstream = graph.node(source)
            if upstream.get("type") in (NODE_PHASE, NODE_APPROVAL):
                out.append(upstream)
            else:
                queue.append(source)       # a decision decides nothing to wait for
    return out


def ready(instance, node) -> bool:
    """Whether a node may run now, or is still waiting on what feeds it."""
    if not Graph.waits_for_predecessors(node):
        return True
    graph = graph_for(instance)
    found = plan(instance)
    if node.get("type") in (NODE_ACTION, NODE_END):
        # The end of a run, and anything that writes on its way out, wait for
        # everything: that is what "the process is finished" means.
        gates = [graph.node(k) for k in graph.ancestors(node["key"])
                 if k in found
                 and (graph.node(k) or {}).get("type") in (NODE_PHASE,
                                                           NODE_APPROVAL)]
    else:
        gates = feeders(graph, node, found)
    return all(is_done(instance, gate) for gate in gates)


def waiting_before(instance, node) -> list:
    """Reachable nodes that feed ``node`` and have not reported yet.

    Not a blocker for a phase — the workshop can record the motor before the
    expert has ruled — but the owner is told, because filling a form whose
    input has not arrived is usually a mistake worth noticing.
    """
    if node is None:
        return []
    graph = graph_for(instance)
    found = plan(instance)
    out = []
    for key in graph.ancestors(node["key"]):
        if key not in found:
            continue
        upstream = graph.node(key)
        if upstream.get("type") not in (NODE_PHASE, NODE_APPROVAL):
            continue
        if not is_done(instance, upstream):
            out.append(upstream)
    return out


def sync_tasks(instance: WorkflowInstance):
    """Give every reachable node its task, and retire the ones the run passed by.

    Called on every read as well as every write: a branch closes or opens as
    answers arrive, and the کارتابل must reflect that without anyone pressing
    anything.
    """
    graph = graph_for(instance)
    if not graph:
        return
    found = plan(instance)
    for node in graph.ordered():
        key = node["key"]
        kind = node.get("type")
        if key in found:
            if kind == NODE_PHASE:
                task = _ensure_fill_task(instance, node)
                if task.status == TASK_SKIPPED:
                    task.status, task.note = TASK_PENDING, None
            elif kind == NODE_APPROVAL and ready(instance, node):
                _ensure_approval_tasks(instance, node)
        else:
            for task in _tasks_of(instance, key):
                if task.status == TASK_PENDING:
                    task.status = TASK_SKIPPED
                    task.note = "مسیر فرایند از این فاز عبور نکرد."
    _refresh_position(instance, graph)


def _refresh_position(instance, graph=None):
    graph = graph or graph_for(instance)
    outstanding = pending_nodes(instance)
    node = outstanding[0] if outstanding else None
    if node is None:
        ends = graph.of_type(NODE_END)
        node = ends[0] if ends else None
    instance.current_node = node["key"] if node else None
    instance.current_stage = (node.get("stage_number") or 0) if node else 0
    if instance.status == INSTANCE_RUNNING and outstanding:
        if all(n.get("type") == NODE_APPROVAL for n in outstanding):
            instance.status = INSTANCE_WAITING
    elif instance.status == INSTANCE_WAITING and outstanding and \
            any(n.get("type") != NODE_APPROVAL for n in outstanding):
        instance.status = INSTANCE_RUNNING
    return outstanding


# ── audit ────────────────────────────────────────────────────────────────────
def log_event(instance, action, user=None, from_node=None, to_node=None,
              status=None, comment=None, payload=None):
    from ..models.workflow import WorkflowEvent
    event = WorkflowEvent(instance_id=instance.id, action=action,
                          from_node=from_node, to_node=to_node,
                          status=status or instance.status, comment=comment,
                          user_id=user.id if user else None)
    if payload:
        import json
        event.payload_json = json.dumps(payload, ensure_ascii=False)
    db.session.add(event)
    instance.events.append(event)
    return event


# ── permissions ──────────────────────────────────────────────────────────────
def _is_manager(user) -> bool:
    return bool(user and (user.role == "admin" or user.can("workflow.manage")))


def may_start(user, definition: WorkflowDefinition | None = None) -> bool:
    """Whether ``user`` may open a run of this template.

    Configured, never assumed: the start node's principals say who starts, and
    a template may name a permission instead under ``start_permission``.
    """
    if user is None:
        return False
    if _is_manager(user):
        return True
    definition = definition or active_workflow()
    if definition is None:
        return False
    graph = live_graph(definition)
    start = graph.start_node()
    if start is None:
        return False
    if Graph.belongs_to(start, user, ROLE_ASSIGNEE):
        return True
    needed = (start.get("config") or {}).get("start_permission")
    if needed:
        return user.can(needed)
    # A start node with neither an owner nor a permission is open to anybody
    # who may take part at all, so a fresh install is not stuck on day one.
    if not Graph.principals(start, ROLE_ASSIGNEE) and not start.get("assignee_id"):
        return user.can("workflow.act")
    return False


def may_fill(user, instance, node) -> bool:
    if user is None or node is None:
        return False
    if instance.status in (INSTANCE_COMPLETED, INSTANCE_CANCELLED,
                           INSTANCE_REJECTED):
        return False
    if _is_manager(user):
        return True
    return (Graph.belongs_to(node, user, ROLE_ASSIGNEE)
            or Graph.belongs_to(node, user, ROLE_EDITOR))


def may_approve(user, instance, node) -> bool:
    if user is None or node is None or node.get("type") != NODE_APPROVAL:
        return False
    if _is_manager(user):
        return True
    if Graph.belongs_to(node, user, ROLE_APPROVER):
        return True
    return any(t.assignee_id == user.id
               for t in _tasks_of(instance, node["key"], TASK_APPROVE))


def may_view(user, instance, node=None) -> bool:
    """Who may look. Viewers watch; they never act."""
    if user is None:
        return False
    if _is_manager(user) or user.can("workflow.view"):
        return True
    if node is not None and Graph.belongs_to(node, user, ROLE_VIEWER):
        return True
    return bool(nodes_of_user(instance, user))


def nodes_of_user(instance, user, role=ROLE_ASSIGNEE) -> list:
    """Reachable nodes this person holds on this run."""
    if user is None:
        return []
    return [n for n in reachable_nodes(instance)
            if Graph.belongs_to(n, user, role)]


def approvals_of_user(instance, user) -> list:
    """Approval nodes open to this person right now."""
    out = []
    for node in reachable_nodes(instance):
        if node.get("type") != NODE_APPROVAL:
            continue
        if approval_state(instance, node) != TASK_PENDING:
            continue
        if not ready(instance, node):
            continue
        tasks = _tasks_of(instance, node["key"], TASK_APPROVE)
        mine = [t for t in tasks
                if t.status == TASK_PENDING
                and (t.assignee_id == user.id
                     or (t.assignee_id is None and _is_manager(user)))]
        if mine or (_is_manager(user) and tasks):
            out.append(node)
    return out


# ── starting ─────────────────────────────────────────────────────────────────
def start_instance(payload: dict, user, code: str | None = None) -> WorkflowInstance:
    """Open a run: answer the start node, snapshot the map, and plan the rest."""
    definition = active_workflow(code)
    if definition is None:
        raise WorkflowError("هیچ فرایند فعالی تعریف نشده است.")
    if not may_start(user, definition):
        raise WorkflowError(
            "شروع این فرایند در اختیار متولی «شروع» است. اگر لازم است شما آن "
            "را آغاز کنید، از مدیر سیستم بخواهید در «نقشه فرایند» شما را "
            "متولی گره شروع کند.")
    graph = live_graph(definition)
    start = graph.start_node()
    if start is None:
        raise WorkflowError("نقشه این فرایند گره «شروع» ندارد؛ "
                            "ابتدا آن را در طراح فرایند اضافه کنید.")

    payload = dict(payload or {})
    instance = WorkflowInstance(
        workflow_id=definition.id, template_version=definition.version,
        status=INSTANCE_RUNNING, created_by=user.id if user else None)
    instance.set_graph(graph.data)
    _bind_well(instance, payload, required=_start_needs_well(graph, start))

    missing = _missing_required(graph, start, payload)
    if missing:
        raise WorkflowError("این موارد در شروع فرایند الزامی است: "
                            + "، ".join(missing))
    instance.set_payload(payload)
    instance.operation_kind = _operation_hint(payload)
    db.session.add(instance)
    db.session.flush()

    task = _ensure_fill_task(instance, start)
    task.status = TASK_SUBMITTED
    task.user_id = user.id if user else None
    task.submitted_at = local_now()
    task.set_payload(payload)

    log_event(instance, "started", user, to_node=start["key"], payload=payload)
    sync_tasks(instance)
    advance(instance, user)
    record_audit("create", "workflow", instance.id,
                 summary=f"شروع فرایند «{definition.name}»"
                         + (f" برای «{instance.well.name}»" if instance.well else ""))
    db.session.commit()
    return instance


def _start_needs_well(graph, start) -> bool:
    """Whether the map asks for a well at the start — data, not an assumption."""
    for item in start.get("items") or []:
        if item.get("kind") == "field" and item.get("code") == "well":
            return True
        if item.get("kind") == "section":
            section = FormSection.query.filter_by(code=item["code"]).first()
            if section and any(f.field_name == "well" for f in section.fields):
                return True
    return False


def _bind_well(instance, payload, required=False):
    """Attach the run to a well when the form named one.

    Optional as far as the engine is concerned: a template about something else
    entirely never mentions a well and runs perfectly well without one.
    """
    raw_value = payload.get("well")
    if not normalize_text(raw_value or ""):
        if required:
            raise WorkflowError("نام چاه را انتخاب کنید؛ چاه در همین مرحله "
                                "یک‌بار تعیین می‌شود و در فازهای بعد تکرار "
                                "نمی‌شود.")
        return
    well, raw = resolve_well(raw_value, create_missing=False)
    if well is None:
        raise WorkflowError(f"چاهی با نام «{raw}» در فهرست چاه‌ها نیست. "
                            f"از فهرست پیشنهادی یک چاه را انتخاب کنید.")
    instance.well_id = well.id
    instance.well_name_raw = raw
    payload["well"] = well.name


def _operation_hint(payload) -> str | None:
    """A short tag for the instance list filter, read from whatever the start
    form called the operation. Cosmetic only — nothing routes on it."""
    value = payload.get("operation_kind")
    if isinstance(value, list):
        value = value[0] if value else None
    return normalize_text(value)[:10] if value else None


def _missing_required(graph, node, payload) -> list:
    """Required fields of a node's own form that the payload does not answer."""
    missing = []
    for block in _node_blocks(graph, node, payload):
        for field in block.get("fields") or []:
            if not field.get("is_required") or field.get("read_only"):
                continue
            value = payload.get(field["field_name"])
            if value in (None, "", [], {}):
                missing.append(field.get("label") or field["field_name"])
    return missing


# ── forms ────────────────────────────────────────────────────────────────────
def _claimed_elsewhere(instance, except_key) -> set:
    """Sections and fields another node of this run has already submitted."""
    graph = graph_for(instance)
    owned = set()
    for task in instance.entries:
        if task.node_key == except_key or task.task_kind != TASK_FILL:
            continue
        if task.status not in DONE_TASK:
            continue
        node = graph.node(task.node_key)
        for item in (node.get("items") if node else []) or []:
            if item.get("code"):
                owned.add((item["kind"], item["code"]))
    return owned


def _settled_values(instance, except_key) -> dict:
    """What other nodes answered — shown locked rather than asked again."""
    values = {}
    for task in instance.entries:
        if task.node_key == except_key or task.task_kind != TASK_FILL:
            continue
        if task.status not in DONE_TASK:
            continue
        for name, value in (task.payload or {}).items():
            if value not in (None, "", [], {}):
                values.setdefault(name, value)
    return values


def _node_blocks(graph, node, context, instance=None, except_claimed=True):
    """The sections and fields one node asks for, resolved against the form."""
    claimed = (_claimed_elsewhere(instance, node["key"])
               if instance is not None and except_claimed else set())
    settled = (_settled_values(instance, node["key"])
               if instance is not None else {})

    blocks = []
    for item in node.get("items") or []:
        code = item.get("code")
        if not code or (item["kind"], code) in claimed:
            continue
        if item["kind"] == "section":
            section = FormSection.query.filter_by(code=code,
                                                  is_active=True).one_or_none()
            if section is None:
                continue
            block = section.to_dict(include_fields=True, active_only=True)
        else:
            field = FormField.query.filter_by(field_name=code,
                                              is_active=True).one_or_none()
            if field is None:
                continue
            block = {"id": None, "code": f"field_{code}", "title": field.label,
                     "icon": "◽", "columns": 1, "full_width": True,
                     "is_active": True, "description": None,
                     "fields": [field.to_dict()]}
        block["fields"] = _usable_fields(block.get("fields") or [], context,
                                         settled, item)
        if not block["fields"]:
            continue
        block["is_optional"] = item.get("is_optional", False)
        blocks.append(block)
    return blocks


def _usable_fields(fields, context, settled, item):
    """Hide what this branch never asks; lock what is already settled.

    A field with a ``visible_when`` rule whose source is *not on this form* is
    decided here, once, from what the run already knows — that is how a
    question bound to one branch disappears on the other without the engine
    knowing what either branch is. A rule whose source *is* on this form stays
    for the browser, so it reacts as the user types.
    """
    names = {f.get("field_name") for f in fields}
    kept = []
    for field in fields:
        rule = (field.get("visible_when") or "").strip()
        if rule and "=" in rule:
            source, wanted = (part.strip() for part in rule.split("=", 1))
            if source not in names:
                if not evaluate({"field": source, "op": "eq", "value": wanted},
                                context):
                    continue
        name = field.get("field_name")
        if item.get("is_read_only") or (name in settled
                                        and name not in (None, "")):
            if name in settled:
                field = dict(field)
                field["read_only"] = True
                field["read_only_value"] = _as_text(settled[name])
                field["help_text"] = (field.get("help_text")
                                      or "در فاز پیشین ثبت شده است.")
            elif item.get("is_read_only"):
                field = dict(field)
                field["read_only"] = True
        kept.append(field)
    return kept


def _as_text(value):
    if isinstance(value, list):
        return "، ".join(str(v) for v in value if v not in (None, ""))
    return value


def node_form(instance, node, draft: dict | None = None) -> dict:
    """Everything the browser needs to draw one node of one run."""
    graph = graph_for(instance)
    context = context_of(instance, draft)
    blocks = _node_blocks(graph, node, context, instance=instance)
    routing = set()
    for edge in graph.out_edges(node["key"]):
        routing |= fields_used(edge.get("condition"))
    for block in blocks:
        for field in block.get("fields") or []:
            if field.get("field_name") in routing:
                field["affects_routing"] = True
    return {
        "stage": node_view(instance, node),
        "node": node_view(instance, node),
        "sections": blocks,
        "routing_fields": sorted(routing),
    }


def start_form(definition) -> dict:
    """The start node's own form, before any run exists.

    The dialog that opens a process is drawn from this, not written into the
    page: whatever the admin dropped on the start node is what the person
    starting a run is asked for — here a well and an operation, in another
    process something else entirely.
    """
    graph = live_graph(definition)
    start = graph.start_node()
    if start is None:
        return {"sections": [], "node": None}
    blocks = _node_blocks(graph, start, {}, instance=None)
    routing = set()
    for edge in graph.out_edges(start["key"]):
        routing |= fields_used(edge.get("condition"))
    for block in blocks:
        for field in block.get("fields") or []:
            if field.get("field_name") in routing:
                field["affects_routing"] = True
    return {
        "sections": blocks,
        "routing_fields": sorted(routing),
        "node": {"key": start["key"], "title": start.get("title"),
                 "description": start.get("description"),
                 "icon": start.get("icon")},
        "workflow": {"id": definition.id, "code": definition.code,
                     "name": definition.name,
                     "description": definition.description},
    }


def node_view(instance, node) -> dict:
    """One node, as the کارتابل and the map want it."""
    status = node_status(instance, node) if instance is not None else None
    data = {
        "key": node["key"], "id": node.get("id"),
        "node_type": node.get("type"), "type": node.get("type"),
        "stage_number": node.get("stage_number"),
        "title": node.get("title"), "description": node.get("description"),
        "icon": node.get("icon"),
        "x": node.get("x"), "y": node.get("y"),
        "width": node.get("width"), "height": node.get("height"),
        "config": node.get("config") or {},
        "principals": node.get("principals") or [],
        "assignee_name": ("، ".join(Graph.owner_names(node)) or None),
        "approver_names": Graph.owner_names(node, ROLE_APPROVER),
        "status": status,
        "status_label": TASK_STATUS.get(status, status),
    }
    if instance is not None and node.get("type") == NODE_APPROVAL:
        data["approvals"] = [t.to_dict() for t in
                             _tasks_of(instance, node["key"], TASK_APPROVE)]
    return data


def submitted_summary(instance, except_key=None) -> list:
    """What the other nodes have recorded, ready to show read-only.

    Whoever is holding the process needs to see the work behind it — the
    engineer signing off sees what four people before him wrote — but none of
    it is his to change, so it arrives as labelled text, not as fields.
    """
    graph = graph_for(instance)
    labels = {f.field_name: f.label for f in FormField.query.all()}
    out = []
    for task in sorted(instance.entries,
                       key=lambda e: (e.stage_number or 0, e.id or 0)):
        if task.node_key == except_key or task.task_kind != TASK_FILL:
            continue
        if task.status not in DONE_TASK:
            continue
        node = graph.node(task.node_key) or {}
        if node.get("type") == NODE_START and not (task.payload or {}):
            continue
        values = []
        for name, value in (task.payload or {}).items():
            if value in (None, "", [], False):
                continue
            text = _as_text(value)
            if not text:
                continue
            values.append({"label": labels.get(name, name), "value": str(text)})
        if not values and not task.note:
            continue
        out.append({
            "stage_number": task.stage_number, "node_key": task.node_key,
            "title": node.get("title") or "",
            "status": task.status,
            "status_label": TASK_STATUS.get(task.status, task.status),
            "user_name": task.user.full_name if task.user else None,
            "submitted_at_j": (to_jalali_str(task.submitted_at)
                               if task.submitted_at else None),
            "note": task.note,
            "values": values,
        })
    return out


# ── acting ───────────────────────────────────────────────────────────────────
def node_by_key(instance, key):
    return graph_for(instance).node(key)


def node_by_stage_number(instance, number):
    return graph_for(instance).by_stage_number(number)


def submit_node(instance, key, payload: dict, user, note: str | None = None):
    """Record one phase's answers, then let the run move as far as it can."""
    if instance.status in (INSTANCE_COMPLETED, INSTANCE_CANCELLED):
        raise WorkflowError("این فرایند بسته شده است.")
    graph = graph_for(instance)
    node = graph.node(key)
    if node is None:
        raise WorkflowError("فاز موردنظر در این فرایند پیدا نشد.")
    sync_tasks(instance)
    if node["key"] not in plan(instance):
        raise WorkflowError(f"فاز «{node.get('title')}» در مسیر این فرایند "
                            f"قرار ندارد.")
    if not may_fill(user, instance, node):
        owner = "، ".join(Graph.owner_names(node)) or "تعیین‌نشده"
        raise WorkflowError(f"فاز «{node.get('title')}» در اختیار «{owner}» است.")
    if not ready(instance, node):
        blockers = "، ".join(n.get("title") or "" for n in
                             waiting_before(instance, node))
        raise WorkflowError("این فاز تا تکمیل فازهای پیش از خود باز نمی‌شود: "
                            + blockers)

    payload = dict(payload or {})
    merged = dict(instance.payload)
    merged.update(payload)
    missing = _missing_required(graph, node, merged)
    if missing:
        raise WorkflowError("این موارد الزامی است: " + "، ".join(missing))

    if payload.get("well") and not instance.well_id:
        _bind_well(instance, payload)

    task = _ensure_fill_task(instance, node)
    task.status = TASK_SUBMITTED
    task.user_id = user.id if user else None
    task.submitted_at = local_now()
    task.set_payload(payload)
    if note:
        task.note = ((task.note + " ") if task.note else "") + note
    instance.set_payload(merged)
    if instance.status == INSTANCE_RETURNED:
        instance.status = INSTANCE_RUNNING

    log_event(instance, "submitted", user, from_node=node["key"],
              comment=note, payload=payload)
    record_audit("update", "workflow", instance.id,
                 summary=f"ثبت فاز «{node.get('title')}»")
    sync_tasks(instance)
    advance(instance, user)
    db.session.commit()
    return instance


def decide(instance, key, user, approved: bool, comment: str | None = None):
    """Record one approver's verdict on an approval node."""
    graph = graph_for(instance)
    node = graph.node(key)
    if node is None or node.get("type") != NODE_APPROVAL:
        raise WorkflowError("گره تأیید موردنظر پیدا نشد.")
    if instance.status in (INSTANCE_COMPLETED, INSTANCE_CANCELLED):
        raise WorkflowError("این فرایند بسته شده است.")
    if not may_approve(user, instance, node):
        raise WorkflowError("تأیید این مرحله در اختیار شما نیست.")
    if not ready(instance, node):
        raise WorkflowError("تا تکمیل فازهای پیش از این مرحله، "
                            "تأیید ممکن نیست.")
    if not approved and not (comment or "").strip():
        raise WorkflowError("برای رد کردن، ذکر دلیل الزامی است.")

    tasks = _ensure_approval_tasks(instance, node)
    mine = next((t for t in tasks
                 if t.assignee_id == (user.id if user else None)
                 and t.status == TASK_PENDING), None)
    if mine is None:
        mine = next((t for t in tasks if t.status == TASK_PENDING), None)
    if mine is None:
        raise WorkflowError("تصمیم شما برای این مرحله قبلاً ثبت شده است.")
    mine.status = TASK_APPROVED if approved else TASK_REJECTED
    mine.user_id = user.id if user else None
    mine.assignee_id = mine.assignee_id or (user.id if user else None)
    mine.submitted_at = local_now()
    mine.comment = comment

    log_event(instance, "approved" if approved else "rejected", user,
              from_node=node["key"], comment=comment)
    state = approval_state(instance, node)
    if state == TASK_REJECTED:
        _handle_rejection(instance, node, user, comment)
    record_audit("update", "workflow", instance.id,
                 summary=("تأیید" if approved else "رد")
                         + f" مرحله «{node.get('title')}»")
    sync_tasks(instance)
    advance(instance, user)
    db.session.commit()
    return instance


def _handle_rejection(instance, node, user, comment):
    """Where a rejection sends the run — drawn on the map, not decided here.

    A «در صورت رد» arrow wins; failing that the node may name a node to return
    to; failing that the run stops as rejected and the admin decides.
    """
    graph = graph_for(instance)
    config = node.get("config") or {}
    targets = [e["target"] for e in graph.out_edges(node["key"])
               if (e.get("kind") or "") == EDGE_REJECTED]
    if not targets and config.get("on_reject_node"):
        targets = [config["on_reject_node"]]
    if not targets and (config.get("on_reject") or "return") == "return":
        back = [k for k in graph.ancestors(node["key"])
                if (graph.node(k) or {}).get("type") == NODE_PHASE]
        targets = back[:1]
    if not targets:
        instance.status = INSTANCE_REJECTED
        log_event(instance, "rejected", user, from_node=node["key"],
                  status=INSTANCE_REJECTED, comment=comment)
        return

    for key in targets:
        target = graph.node(key)
        if target is None:
            continue
        task = _ensure_fill_task(instance, target)
        task.status = TASK_PENDING
        task.note = (f"بازگشت از «{node.get('title')}»: "
                     + (comment or "بدون توضیح"))
        log_event(instance, "reopened", user, from_node=node["key"],
                  to_node=key, comment=comment)
    # The approval itself starts over, so the corrected work is re-judged.
    for task in _tasks_of(instance, node["key"], TASK_APPROVE):
        task.status = TASK_PENDING
        task.user_id = None
        task.submitted_at = None
    instance.status = INSTANCE_RETURNED


# ── automatic nodes ──────────────────────────────────────────────────────────
def _action_create_record(instance, node, user):
    """Write the run's answers into the records table."""
    if instance.record_id:
        return instance.record
    payload = dict(instance.payload)
    if instance.well_id and not payload.get("well"):
        payload["well"] = instance.well.name
    try:
        record = create_record(payload)
    except ValidationError as exc:
        names = "، ".join(sorted(k for k in exc.errors
                                 if not k.startswith("__"))) or "نامشخص"
        raise WorkflowError("ثبت نهایی ممکن نشد؛ این فیلدها کامل نیستند: "
                            + names) from exc
    instance.record_id = record.id
    log.info("Workflow %s wrote record %s", instance.id, record.id)
    return record


def _action_none(instance, node, user):
    return None


ACTION_HANDLERS = {
    "none": {"label": "بدون اقدام", "run": _action_none,
             "help": "فقط یک ایستگاه روی نقشه."},
    "create_record": {"label": "ثبت رکورد در جدول رکوردها",
                      "run": _action_create_record,
                      "help": "داده‌های فرایند را به‌صورت یک رکورد ذخیره می‌کند."},
}


def action_list() -> list:
    return [{"value": code, "label": spec["label"], "help": spec.get("help")}
            for code, spec in ACTION_HANDLERS.items()]


def advance(instance, user=None, guard=40):
    """Run every automatic node the process has arrived at.

    Decisions route, actions fire, and an end node closes the run. Loops in a
    badly drawn map are stopped by the guard rather than by hanging.
    """
    for _ in range(guard):
        graph = graph_for(instance)
        found = plan(instance)
        moved = False
        for node in graph.ordered():
            key = node["key"]
            kind = node.get("type")
            if key not in found or kind not in (NODE_DECISION, NODE_ACTION,
                                                NODE_END):
                continue
            task = fill_task(instance, key)
            if task is not None and task.status in DONE_TASK:
                continue
            if kind == NODE_DECISION:
                # A decision has nothing to do; it is simply travelled once
                # anything feeding it has reported.
                if not _arrived_at(instance, graph, node, found):
                    continue
                task = _ensure_fill_task(instance, node)
                task.status = TASK_SUBMITTED
                task.submitted_at = local_now()
                moved = True
                continue
            if not ready(instance, node):
                continue
            task = _ensure_fill_task(instance, node)
            if kind == NODE_ACTION:
                name = (node.get("config") or {}).get("action") or "none"
                handler = ACTION_HANDLERS.get(name)
                if handler is None:
                    task.status = TASK_SKIPPED
                    task.note = f"اقدام «{name}» شناخته نشد."
                else:
                    handler["run"](instance, node, user)
                    task.status = TASK_SUBMITTED
                    task.submitted_at = local_now()
                    log_event(instance, "action", user, from_node=key,
                              comment=(handler["label"]))
            else:
                task.status = TASK_SUBMITTED
                task.submitted_at = local_now()
                _complete(instance, node, user)
            moved = True
        if not moved:
            break
    _refresh_position(instance)
    return instance


def _arrived_at(instance, graph, node, found) -> bool:
    """Whether the run has actually reached a node — something upstream of it
    has reported, or it has nothing upstream at all."""
    incoming = [e for e in graph.in_edges(node["key"]) if e["source"] in found]
    if not incoming:
        return True
    return any(is_done(instance, graph.node(e["source"])) for e in incoming)


def _complete(instance, node, user):
    instance.status = INSTANCE_COMPLETED
    instance.completed_at = local_now()
    log_event(instance, "completed", user, to_node=node["key"],
              status=INSTANCE_COMPLETED)
    record_audit("update", "workflow", instance.id, summary="فرایند تکمیل شد")
    for task in instance.entries:
        if task.status == TASK_PENDING:
            task.status = TASK_SKIPPED
            task.note = task.note or "فرایند پیش از رسیدن به این فاز تکمیل شد."


def cancel_instance(instance, reason: str, user):
    instance.status = INSTANCE_CANCELLED
    for task in instance.entries:
        if task.status == TASK_PENDING:
            task.status = TASK_CANCELLED
    log_event(instance, "cancelled", user, comment=reason,
              status=INSTANCE_CANCELLED)
    record_audit("delete", "workflow", instance.id,
                 summary=f"لغو فرایند: {reason or 'بدون توضیح'}")
    db.session.commit()
    return instance


# ── the live map ─────────────────────────────────────────────────────────────
def map_state(instance) -> dict:
    """The run painted onto its own map: every node's state and the path taken.

    One drawing serves both purposes — the admin watches a run on exactly the
    picture the designer drew, which is the point of drawing it.
    """
    graph = graph_for(instance)
    found = plan(instance)
    nodes, travelled = [], set()
    for node in graph.ordered():
        key = node["key"]
        view = node_view(instance, node)
        reachable = key in found
        status = view["status"]
        if not reachable and status == TASK_PENDING:
            status = TASK_SKIPPED
        view.update({
            "reachable": reachable,
            "state": _map_state_of(instance, node, status, reachable),
            "status": status,
            "status_label": TASK_STATUS.get(status, status),
            "waiting_on": [n["key"] for n in waiting_before(instance, node)],
        })
        if status in DONE_TASK:
            travelled.add(key)
        nodes.append(view)

    edges = []
    for edge in graph.edges:
        taken = edge["source"] in travelled and (
            edge["target"] in travelled
            or (instance.current_node == edge["target"]))
        edges.append(dict(edge, taken=taken,
                          active=(edge["target"] == instance.current_node
                                  and edge["source"] in travelled)))
    return {"nodes": nodes, "edges": edges,
            "current_node": instance.current_node,
            "status": instance.status}


def _map_state_of(instance, node, status, reachable) -> str:
    """The colour the map paints a node in — named, not coloured, here."""
    if not reachable:
        return "skipped"
    if node.get("type") == NODE_APPROVAL:
        if status == TASK_APPROVED:
            return "approved"
        if status == TASK_REJECTED:
            return "rejected"
        return "awaiting_approval" if ready(instance, node) else "pending"
    if status in DONE_TASK:
        return "done"
    if status in (TASK_SKIPPED, TASK_CANCELLED):
        return "skipped"
    if node["key"] == instance.current_node:
        return "active"
    return "pending" if not ready(instance, node) else "open"


# ── «قبلی» fields ────────────────────────────────────────────────────────────
# What this operation installs becomes what the next one finds. Each pair is
# (field to fill now, where to read it from on the previous record). A mapping,
# not a rule: the admin can add a pair without touching the engine.
PREVIOUS_SOURCES = {
    "motor_prev": "motor_curr_id",
    "pump_prev": "pump_curr_id",
    "pump_prev_stages": "pump_stages",
    "prev_install_depth": "curr_install_depth",
}


def previous_values_for(well_id, before_record_id=None) -> dict:
    """The «…قبلی» answers, read off this well's last operation.

    Suggestions, never settled facts: the form fills them in and leaves them
    editable, because the register is not always right and the person standing
    at the well is.
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


# ── names the rest of the app already calls ──────────────────────────────────
# The کارتابل, the documents hub and the exports were written against stages.
# A node is a stage with more to it, so these keep working rather than being
# rewritten twice.
def sync_entries(instance):
    return sync_tasks(instance)


def applicable_stages(instance) -> list:
    return [n for n in reachable_nodes(instance)
            if n.get("type") in (NODE_PHASE, NODE_APPROVAL)]


def pending_stages(instance) -> list:
    return pending_nodes(instance)


def stages_of_user(instance, user) -> list:
    return nodes_of_user(instance, user)


def stage_by_number(instance, number):
    return node_by_stage_number(instance, number)


def current_stage_of(instance):
    graph = graph_for(instance)
    if instance.current_node:
        node = graph.node(instance.current_node)
        if node:
            return node
    outstanding = pending_nodes(instance)
    return outstanding[0] if outstanding else None


def may_act(user, instance, stage=None) -> bool:
    if stage is not None:
        if stage.get("type") == NODE_APPROVAL:
            return may_approve(user, instance, stage)
        return may_fill(user, instance, stage)
    return bool(nodes_of_user(instance, user)) or _is_manager(user)


def stage_form(instance, stage, draft=None):
    return node_form(instance, stage, draft)


def submit_stage(instance, payload, user, note=None, stage_number=None,
                 node_key=None):
    if node_key is None:
        node = (node_by_stage_number(instance, stage_number)
                if stage_number is not None else current_stage_of(instance))
        if node is None:
            raise WorkflowError("فاز موردنظر در این فرایند پیدا نشد.")
        node_key = node["key"]
    return submit_node(instance, node_key, payload, user, note=note)
