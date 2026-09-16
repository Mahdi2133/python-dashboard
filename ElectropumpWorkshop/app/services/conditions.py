# -*- coding: utf-8 -*-
"""Conditions, as data.

An arrow on the process map is taken when its condition passes. The condition
is a small JSON tree the admin builds in the designer — never a line of Python
about any particular process:

    {"field": "operation_kind", "op": "eq", "value": "کشیدن"}

    {"all": [{"field": "required_action", "op": "eq", "value": "نصب الکتروپمپ جدید"},
             {"field": "pump_type_now",  "op": "eq", "value": "بله"}]}

    {"any": [...]}      {"not": {...}}      {}   ← always true

Comparison is Persian-aware: «کشیدن» typed with an Arabic ک matches one typed
with a Persian ک, and ۱۲ matches 12, because the people filling these forms
switch keyboards mid-sentence and a workflow that hinges on a code point is a
workflow that stops for no reason.
"""
from __future__ import annotations

import re

from .lookups import fold_persian, normalize_text

# ── operators ────────────────────────────────────────────────────────────────
# code -> (Persian label, how many values it takes: 0, 1 or many)
OPERATORS = {
    "eq":        ("برابر است با", 1),
    "ne":        ("برابر نیست با", 1),
    "in":        ("یکی از", "many"),
    "not_in":    ("هیچ‌کدام از", "many"),
    "contains":  ("شامل", 1),
    "not_contains": ("شامل نیست", 1),
    "starts_with": ("شروع می‌شود با", 1),
    "gt":        ("بزرگ‌تر از", 1),
    "gte":       ("بزرگ‌تر یا مساوی", 1),
    "lt":        ("کوچک‌تر از", 1),
    "lte":       ("کوچک‌تر یا مساوی", 1),
    "empty":     ("خالی است", 0),
    "not_empty": ("خالی نیست", 0),
    "is_true":   ("بله است", 0),
    "is_false":  ("خیر است", 0),
    "matches":   ("با الگو می‌خواند", 1),
}

_TRUE = {"true", "1", "yes", "on", "بله", "آری", "دارد"}
_FALSE = {"false", "0", "no", "off", "خیر", "ندارد", "نه"}


def operator_list() -> list:
    """The operator palette, for the designer's condition editor."""
    return [{"value": code, "label": label, "arity": arity}
            for code, (label, arity) in OPERATORS.items()]


# ── comparison helpers ───────────────────────────────────────────────────────
def _key(value) -> str:
    """A comparison key: folded Persian, Latin digits, no stray spacing."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return fold_persian(normalize_text(str(value))).casefold()


def _number(value):
    try:
        return float(_key(value))
    except (TypeError, ValueError):
        return None


def _is_empty(value) -> bool:
    if value is None or value is False:
        return True
    if isinstance(value, (list, tuple, set, dict)):
        return not value
    return not str(value).strip()


def _as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return _key(value) in _TRUE


def _falsy(value) -> bool:
    if isinstance(value, bool):
        return not value
    return _key(value) in _FALSE


# ── the evaluator ────────────────────────────────────────────────────────────
def compare(actual, op: str, expected=None) -> bool:
    """One comparison. Unknown operators are false rather than an exception —
    a broken condition must not take the whole process down."""
    if op == "empty":
        return _is_empty(actual)
    if op == "not_empty":
        return not _is_empty(actual)
    if op == "is_true":
        return _truthy(actual)
    if op == "is_false":
        return _falsy(actual) or _is_empty(actual)

    # A multi-answer field (checkboxes) passes if any of its answers does.
    actual_keys = [_key(v) for v in _as_list(actual)] or [""]
    expected_keys = [_key(v) for v in _as_list(expected)]

    if op == "eq":
        return any(a in expected_keys for a in actual_keys)
    if op == "ne":
        return not any(a in expected_keys for a in actual_keys)
    if op == "in":
        return any(a in expected_keys for a in actual_keys)
    if op == "not_in":
        return not any(a in expected_keys for a in actual_keys)
    if op == "contains":
        return any(e and e in a for a in actual_keys for e in expected_keys)
    if op == "not_contains":
        return not any(e and e in a for a in actual_keys for e in expected_keys)
    if op == "starts_with":
        return any(e and a.startswith(e) for a in actual_keys for e in expected_keys)
    if op == "matches":
        for pattern in expected_keys:
            try:
                if any(re.search(pattern, a) for a in actual_keys):
                    return True
            except re.error:
                return False
        return False

    if op in ("gt", "gte", "lt", "lte"):
        left = _number(_as_list(actual)[0] if _as_list(actual) else None)
        right = _number(_as_list(expected)[0] if expected_keys else None)
        if left is None or right is None:
            return False
        return {"gt": left > right, "gte": left >= right,
                "lt": left < right, "lte": left <= right}[op]
    return False


def evaluate(condition, context: dict) -> bool:
    """Whether ``condition`` holds for ``context``.

    An empty condition is true — an unlabelled arrow is always taken. A
    condition that names a field nobody has filled yet is false, which is what
    keeps a branch closed until the answer that opens it arrives.
    """
    if not condition:
        return True
    if isinstance(condition, list):
        return all(evaluate(part, context) for part in condition)
    if not isinstance(condition, dict):
        return bool(condition)

    if "all" in condition:
        return all(evaluate(p, context) for p in condition["all"] or [])
    if "any" in condition:
        parts = condition["any"] or []
        return any(evaluate(p, context) for p in parts) if parts else True
    if "none" in condition:
        return not any(evaluate(p, context) for p in condition["none"] or [])
    if "not" in condition:
        return not evaluate(condition["not"], context)

    field = condition.get("field") or condition.get("source")
    if not field:
        return True
    op = condition.get("op") or "eq"
    expected = condition.get("value", condition.get("values"))
    return compare((context or {}).get(field), op, expected)


def describe(condition) -> str:
    """The condition in words, for the map label and the audit trail."""
    if not condition:
        return ""
    if isinstance(condition, dict):
        for joiner, word in (("all", " و "), ("any", " یا ")):
            if joiner in condition:
                parts = [describe(p) for p in condition[joiner] or []]
                parts = [p for p in parts if p]
                return word.join(parts)
        if "none" in condition:
            parts = [describe(p) for p in condition["none"] or []]
            return "هیچ‌کدام از: " + "، ".join(p for p in parts if p)
        if "not" in condition:
            return "نه (" + describe(condition["not"]) + ")"
        field = condition.get("field") or condition.get("source") or ""
        label = condition.get("label") or field
        op = condition.get("op") or "eq"
        op_label = OPERATORS.get(op, (op, 1))[0]
        value = condition.get("value", condition.get("values"))
        if OPERATORS.get(op, ("", 1))[1] == 0:
            return f"{label} {op_label}"
        values = "، ".join(str(v) for v in _as_list(value))
        return f"{label} {op_label} «{values}»"
    return str(condition)


def fields_used(condition, out=None) -> set:
    """Every field a condition reads — the designer marks these «مؤثر بر مسیر»."""
    out = set() if out is None else out
    if isinstance(condition, list):
        for part in condition:
            fields_used(part, out)
    elif isinstance(condition, dict):
        for joiner in ("all", "any", "none"):
            if joiner in condition:
                for part in condition[joiner] or []:
                    fields_used(part, out)
        if "not" in condition:
            fields_used(condition["not"], out)
        name = condition.get("field") or condition.get("source")
        if name:
            out.add(name)
    return out
