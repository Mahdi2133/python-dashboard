# -*- coding: utf-8 -*-
"""The process map as a graph, and the rules for walking it.

Everything here is about shape, never about content. The graph does not know
that one node is a water centre and another a mechanic's workshop; it knows
that a node has a type, an owner, some form items, and arrows leaving it, each
with a condition.

Two ways in:

*   :func:`graph_of` reads the live template — what the designer is drawing.
*   :func:`Graph` over ``instance.graph_json`` reads the snapshot taken when a
    run started, so redrawing the map tomorrow leaves today's runs alone.

Reachability is the heart of it. From the start node we follow every arrow
whose condition holds. An arrow with no condition always holds, so a phase is
reachable the moment the process opens — that is what lets phase 3 be filled
without waiting for phase 2. An arrow whose condition reads an answer nobody
has given yet does *not* hold, so the branch behind it stays closed until the
answer arrives, and opens by itself when it does.
"""
from __future__ import annotations

from .conditions import describe, evaluate
from ..models.workflow import (EDGE_APPROVED, EDGE_DEFAULT, EDGE_ELSE,
                               EDGE_REJECTED, NODE_ACTION, NODE_APPROVAL,
                               NODE_DECISION, NODE_END, NODE_PHASE, NODE_START,
                               NODE_TYPES, ROLE_APPROVER, ROLE_ASSIGNEE,
                               ROLE_EDITOR, ROLE_VIEWER)

# Node types that stop and ask somebody for something.
HUMAN_NODES = (NODE_START, NODE_PHASE, NODE_APPROVAL)
# Node types the engine passes straight through.
AUTO_NODES = (NODE_DECISION, NODE_ACTION, NODE_END)
# Which types wait for everything upstream before they may run. A phase does
# not (the workshop asked for independent phases, warned rather than blocked);
# an approval does, because approving a form nobody has filled is nonsense.
WAITS_BY_DEFAULT = (NODE_APPROVAL, NODE_ACTION, NODE_END)


# ── building ─────────────────────────────────────────────────────────────────
def node_snapshot(node) -> dict:
    """One node of the live template, as plain data."""
    return {
        "key": node.key,
        "id": node.id,
        # Both spellings: the map code reads `type`, everything that grew out
        # of the stage builder reads `node_type`, and neither should have to
        # care which one this dictionary came from.
        "type": node.node_type,
        "node_type": node.node_type,
        "stage_number": node.stage_number,
        "title": node.title,
        "description": node.description,
        "icon": node.icon or NODE_TYPES.get(node.node_type, {}).get("icon"),
        "x": node.pos_x, "y": node.pos_y,
        "width": node.width, "height": node.height,
        "config": node.config,
        "is_active": node.is_active,
        "applies_to": node.applies_to,
        "assignee_id": node.assignee_id,
        "principals": [
            {"role": p.role, "kind": p.principal_kind, "user_id": p.user_id,
             "role_code": p.role_code,
             "name": p.user.full_name if p.user else p.role_code}
            for p in node.principals],
        "items": [
            {"kind": i.kind,
             "code": (i.section.code if i.section
                      else i.field.field_name if i.field else None),
             "title": (i.section.title if i.section
                       else i.field.label if i.field else None),
             "section_id": i.section_id, "field_id": i.field_id,
             "applies_to": i.applies_to,
             "is_optional": i.is_optional, "is_read_only": i.is_read_only,
             "sort_order": i.sort_order}
            for i in sorted(node.items, key=lambda x: x.sort_order)],
    }


def edge_snapshot(edge) -> dict:
    return {
        "id": edge.id,
        "source": edge.source.key if edge.source else None,
        "target": edge.target.key if edge.target else None,
        "kind": edge.kind, "label": edge.label,
        "condition": edge.condition, "priority": edge.priority,
        "description": edge.description,
    }


def graph_of(definition) -> dict:
    """The live template as a snapshot-shaped dict."""
    nodes = [node_snapshot(n) for n in definition.nodes if n.is_active]
    keys = {n["key"] for n in nodes}
    edges = [edge_snapshot(e) for e in definition.edges]
    edges = [e for e in edges if e["source"] in keys and e["target"] in keys]
    return {
        "workflow": {"id": definition.id, "code": definition.code,
                     "version": definition.version, "name": definition.name,
                     "description": definition.description},
        "nodes": nodes,
        "edges": sorted(edges, key=lambda e: (e["priority"], e["id"] or 0)),
    }


class Graph:
    """A read-only view over one process map."""

    def __init__(self, data: dict):
        data = data or {}
        self.data = data
        self.meta = data.get("workflow") or {}
        self.nodes = {}
        for raw in data.get("nodes") or []:
            key = raw.get("key")
            if key:
                self.nodes[key] = raw
        self.edges = [e for e in (data.get("edges") or [])
                      if e.get("source") in self.nodes
                      and e.get("target") in self.nodes]
        self.edges.sort(key=lambda e: (e.get("priority") or 0, e.get("id") or 0))
        self._out, self._in = {}, {}
        for edge in self.edges:
            self._out.setdefault(edge["source"], []).append(edge)
            self._in.setdefault(edge["target"], []).append(edge)

    # -- lookups ------------------------------------------------------------
    def __bool__(self):
        return bool(self.nodes)

    def node(self, key):
        return self.nodes.get(key)

    def by_stage_number(self, number):
        for raw in self.nodes.values():
            if raw.get("stage_number") == number:
                return raw
        return None

    def out_edges(self, key):
        return self._out.get(key, [])

    def in_edges(self, key):
        return self._in.get(key, [])

    def of_type(self, *types):
        return [n for n in self.ordered() if n.get("type") in types]

    def start_node(self):
        starts = [n for n in self.nodes.values() if n.get("type") == NODE_START]
        if starts:
            return sorted(starts, key=lambda n: n.get("stage_number") or 0)[0]
        # A map drawn without a start node: take whatever has no way in.
        orphans = [n for n in self.nodes.values() if not self.in_edges(n["key"])]
        pool = orphans or list(self.nodes.values())
        return sorted(pool, key=lambda n: n.get("stage_number") or 0)[0] if pool else None

    # -- ordering -----------------------------------------------------------
    def ordered(self) -> list:
        """Nodes in the order a reader follows them: breadth-first from start,
        then anything unreachable, each fallback ordered by stage number."""
        seen, out = set(), []
        queue = []
        start = self.start_node()
        if start:
            queue.append(start["key"])
        while queue:
            key = queue.pop(0)
            if key in seen:
                continue
            seen.add(key)
            out.append(self.nodes[key])
            for edge in self.out_edges(key):
                if edge["target"] not in seen:
                    queue.append(edge["target"])
        for raw in sorted(self.nodes.values(),
                          key=lambda n: (n.get("stage_number") or 0, n["key"])):
            if raw["key"] not in seen:
                out.append(raw)
        return out

    def ancestors(self, key) -> list:
        """Every node that can lead to ``key``, nearest first."""
        seen, order, queue = {key}, [], [key]
        while queue:
            current = queue.pop(0)
            for edge in self.in_edges(current):
                source = edge["source"]
                if source in seen:
                    continue
                seen.add(source)
                order.append(source)
                queue.append(source)
        return order

    # -- walking ------------------------------------------------------------
    def passable(self, edge, context: dict) -> bool:
        return evaluate(edge.get("condition"), context or {})

    def next_edges(self, key, context: dict, kind=None, gate=None) -> list:
        """Arrows leaving ``key`` that this context takes.

        ``kind`` narrows to the approved or rejected arrows of an approval
        node; ``gate`` lets the caller veto an arrow for a reason the map
        cannot express — chiefly that an approval has not been given yet.
        Priority decides between competing arrows; an «در غیر این صورت» arrow
        is taken only when nothing else was.
        """
        edges = self.out_edges(key)
        if kind is not None:
            edges = [e for e in edges if (e.get("kind") or EDGE_DEFAULT) == kind] \
                    or [e for e in edges
                        if (e.get("kind") or EDGE_DEFAULT) == EDGE_DEFAULT]
        if gate is not None:
            node = self.node(key)
            edges = [e for e in edges if gate(node, e)]
        primary = [e for e in edges if (e.get("kind") or EDGE_DEFAULT) != EDGE_ELSE]
        taken = [e for e in primary if self.passable(e, context)]
        if taken:
            return taken
        return [e for e in edges if (e.get("kind") or EDGE_DEFAULT) == EDGE_ELSE]

    def reachable(self, context: dict, stop_at=(), gate=None) -> dict:
        """Every node this context can still get to, and how it got there.

        Returns ``{key: {"via": [edge, …], "depth": n}}``. Nodes in ``stop_at``
        are reached but not walked through, and ``gate`` decides arrow by arrow
        — which is how an approval holds everything behind it closed until it
        is given.
        """
        start = self.start_node()
        if start is None:
            return {}
        found = {start["key"]: {"via": [], "depth": 0}}
        queue = [start["key"]]
        while queue:
            key = queue.pop(0)
            if key in stop_at:
                continue
            depth = found[key]["depth"]
            for edge in self.next_edges(key, context, gate=gate):
                target = edge["target"]
                entry = found.get(target)
                if entry is None:
                    found[target] = {"via": [edge], "depth": depth + 1}
                    queue.append(target)
                elif edge not in entry["via"]:
                    entry["via"].append(edge)
                    entry["depth"] = min(entry["depth"], depth + 1)
        return found

    # -- node questions -----------------------------------------------------
    @staticmethod
    def waits_for_predecessors(node) -> bool:
        config = node.get("config") or {}
        if "wait_for_predecessors" in config:
            return bool(config["wait_for_predecessors"])
        return node.get("type") in WAITS_BY_DEFAULT

    @staticmethod
    def principals(node, role) -> list:
        return [p for p in (node.get("principals") or [])
                if (p.get("role") or ROLE_ASSIGNEE) == role]

    @staticmethod
    def user_ids(node, role) -> list:
        return [p["user_id"] for p in Graph.principals(node, role)
                if p.get("user_id")]

    @staticmethod
    def role_codes(node, role) -> list:
        return [p["role_code"] for p in Graph.principals(node, role)
                if p.get("role_code")]

    @staticmethod
    def belongs_to(node, user, role=ROLE_ASSIGNEE) -> bool:
        """Whether ``user`` holds ``node`` in that capacity.

        A principal is a user or a role, so the admin can hand a phase to one
        person, to several, or to everyone with a job title — without the
        engine ever naming anybody.
        """
        if user is None or node is None:
            return False
        if user.id in Graph.user_ids(node, role):
            return True
        if user.role and user.role in Graph.role_codes(node, role):
            return True
        # The single-owner column the first process builder wrote.
        if (role == ROLE_ASSIGNEE and not Graph.principals(node, ROLE_ASSIGNEE)
                and node.get("assignee_id")):
            return node["assignee_id"] == user.id
        return False

    @staticmethod
    def owner_names(node, role=ROLE_ASSIGNEE) -> list:
        names = [p.get("name") for p in Graph.principals(node, role)
                 if p.get("name")]
        return names

    def approvers_of(self, node) -> list:
        return self.principals(node, ROLE_APPROVER)

    def viewers_of(self, node) -> list:
        return self.principals(node, ROLE_VIEWER)

    def editors_of(self, node) -> list:
        return self.principals(node, ROLE_EDITOR)

    # -- description --------------------------------------------------------
    def to_dict(self) -> dict:
        return {"workflow": self.meta,
                "nodes": self.ordered(),
                "edges": [dict(e, condition_label=describe(e.get("condition")))
                          for e in self.edges]}


def edge_kind_of(value) -> str:
    return value if value in (EDGE_DEFAULT, EDGE_APPROVED, EDGE_REJECTED,
                              EDGE_ELSE) else EDGE_DEFAULT
