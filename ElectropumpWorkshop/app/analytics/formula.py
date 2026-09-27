# -*- coding: utf-8 -*-
"""Calculated fields: a small, safe expression language.

    [مدت اجرا (ساعت)] - [مهلت مرحله (ساعت)]
    ROUND(COUNT_IF([وضعیت فرایند] = "تکمیل‌شده") / COUNT() * 100, 1)
    IF([تأخیر (ساعت)] > 24, "بحرانی", "عادی")

Fields are referenced as ``[key]`` or ``[label]``. A formula is either
*row-level* (computed on every row, then usable like any field — in filters,
groupings and measures) or *group-level* (it contains an aggregate such as SUM,
COUNT or AVG and is computed once per group, like a measure).

Nothing is ever passed to ``eval``: the text is tokenised and parsed into a
tree here, and only the functions listed below exist. A formula is validated
before it can be saved — unknown fields and functions, wrong argument counts,
a bare field outside an aggregate in a group-level formula, circular calculated
fields — and at run time a division by zero or a missing value yields an empty
result rather than an error.
"""
from __future__ import annotations

import datetime as _dt
import math
import re
import statistics

from ..services.jalali import gregorian_to_jalali, parse_jalali_to_date


class FormulaError(ValueError):
    pass


# ── tokens ─────────────────────────────────────────────────────────────────
_FA_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٫", "0123456789.")
_TOKEN = re.compile(r"""
    (?P<ws>\s+)
  | (?P<num>\d+(?:\.\d+)?)
  | (?P<str>"[^"]*"|'[^']*'|«[^»]*»)
  | (?P<field>\[[^\]]+\]|\{[^}]+\})
  | (?P<op><=|>=|<>|!=|==|[-+*/%^&=<>(),])
  | (?P<name>[A-Za-z_][A-Za-z_0-9]*)
""", re.X)


def tokenize(text: str) -> list:
    text = (text or "").translate(_FA_DIGITS).replace("×", "*").replace("÷", "/")
    pos, out = 0, []
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if not m:
            raise FormulaError(f"نویسه‌ی نامعتبر در فرمول: «{text[pos]}» (جایگاه {pos + 1})")
        kind = m.lastgroup
        value = m.group(kind)
        pos = m.end()
        if kind == "ws":
            continue
        if kind == "str":
            value = value[1:-1]
        elif kind == "field":
            value = value[1:-1].strip()
        elif kind == "num":
            value = float(value) if "." in value else int(value)
        elif kind == "name":
            value = value.upper()
        out.append((kind, value))
    return out


# ── parser: precedence climbing ────────────────────────────────────────────
_BIN_PREC = {"=": 1, "==": 1, "<>": 1, "!=": 1, "<": 1, "<=": 1, ">": 1, ">=": 1,
             "&": 2, "+": 3, "-": 3, "*": 4, "/": 4, "%": 4, "^": 5}


class _Parser:
    def __init__(self, tokens):
        self.t, self.i = tokens, 0

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else (None, None)

    def take(self):
        tok = self.peek()
        self.i += 1
        return tok

    def expect(self, value):
        kind, v = self.take()
        if v != value:
            raise FormulaError(f"«{value}» انتظار می‌رفت ولی «{v if v is not None else 'پایان فرمول'}» آمد.")

    def parse(self):
        if not self.t:
            raise FormulaError("فرمول خالی است.")
        node = self.expr(0)
        if self.i != len(self.t):
            raise FormulaError(f"بخش اضافه در فرمول: «{self.peek()[1]}»")
        return node

    def expr(self, min_prec):
        left = self.unary()
        while True:
            kind, v = self.peek()
            if kind != "op" or v not in _BIN_PREC or _BIN_PREC[v] < min_prec:
                return left
            prec = _BIN_PREC[v]
            self.take()
            right = self.expr(prec + (0 if v == "^" else 1))
            left = ("bin", v, left, right)

    def unary(self):
        kind, v = self.peek()
        if kind == "op" and v == "-":
            self.take()
            return ("neg", self.unary())
        if kind == "op" and v == "+":
            self.take()
            return self.unary()
        return self.atom()

    def atom(self):
        kind, v = self.take()
        if kind == "num":
            return ("num", v)
        if kind == "str":
            return ("str", v)
        if kind == "field":
            return ("field", v)
        if kind == "name":
            if v in ("TRUE", "FALSE"):
                return ("num", v == "TRUE")
            if v == "NULL":
                return ("null",)
            if self.peek()[1] != "(":
                raise FormulaError(f"«{v}» تابع شناخته‌شده‌ای نیست؛ برای فیلد از [نام فیلد] استفاده کنید.")
            self.take()
            args = []
            if self.peek()[1] != ")":
                while True:
                    args.append(self.expr(0))
                    if self.peek()[1] == ",":
                        self.take()
                        continue
                    break
            self.expect(")")
            return ("call", v, args)
        if kind == "op" and v == "(":
            node = self.expr(0)
            self.expect(")")
            return node
        raise FormulaError(f"«{v if v is not None else 'پایان فرمول'}» اینجا معنا ندارد.")


def parse(text: str):
    return _Parser(tokenize(text)).parse()


# ── functions ──────────────────────────────────────────────────────────────
AGGREGATES = {"SUM", "AVG", "COUNT", "COUNT_DISTINCT", "COUNT_IF", "SUM_IF", "MEDIAN",
              "STDDEV", "VARIANCE", "PERCENTILE", "MIN_OF", "MAX_OF"}
# MIN and MAX: with one argument inside a group-level formula they aggregate,
# with several they compare.

FUNCTIONS = {
    # name: (min args, max args or None, help)
    "IF": (2, 3, "IF(شرط، مقدار اگر درست، مقدار اگر نادرست)"),
    "AND": (1, None, "AND(شرط۱، شرط۲، …)"),
    "OR": (1, None, "OR(شرط۱، شرط۲، …)"),
    "NOT": (1, 1, "NOT(شرط)"),
    "ROUND": (1, 2, "ROUND(عدد، تعداد اعشار)"),
    "ABS": (1, 1, "ABS(عدد)"),
    "MIN": (1, None, "MIN(a، b، …) یا در گزارش گروهی MIN([فیلد])"),
    "MAX": (1, None, "MAX(a، b، …) یا در گزارش گروهی MAX([فیلد])"),
    "CONCAT": (1, None, "CONCAT(متن۱، متن۲، …)"),
    "COALESCE": (1, None, "COALESCE(مقدار۱، مقدار۲، …) — اولین مقدار غیرخالی"),
    "DATE_DIFF": (2, 3, 'DATE_DIFF(تاریخ پایان، تاریخ شروع، "day"|"hour"|"month"|"year")'),
    "DAY": (1, 1, "DAY(تاریخ) — روز شمسی"),
    "MONTH": (1, 1, "MONTH(تاریخ) — ماه شمسی"),
    "YEAR": (1, 1, "YEAR(تاریخ) — سال شمسی"),
    "LEN": (1, 1, "LEN(متن یا فهرست)"),
    "TODAY": (0, 0, "TODAY() — تاریخ امروز"),
    "NUMBER": (1, 1, "NUMBER(مقدار) — تبدیل به عدد"),
    "TEXT": (1, 1, "TEXT(مقدار) — تبدیل به متن"),
    "CONTAINS": (2, 2, "CONTAINS(فهرست یا متن، مقدار)"),
    "SUM": (1, 1, "SUM([فیلد]) — جمع در گروه"),
    "AVG": (1, 1, "AVG([فیلد]) — میانگین در گروه"),
    "COUNT": (0, 1, "COUNT() یا COUNT([فیلد]) — تعداد در گروه"),
    "COUNT_DISTINCT": (1, 1, "COUNT_DISTINCT([فیلد]) — تعداد مقادیر یکتا"),
    "COUNT_IF": (1, 1, "COUNT_IF(شرط) — تعداد ردیف‌هایی که شرط در آن‌ها درست است"),
    "SUM_IF": (2, 2, "SUM_IF([فیلد]، شرط)"),
    "MEDIAN": (1, 1, "MEDIAN([فیلد]) — میانه"),
    "STDDEV": (1, 1, "STDDEV([فیلد]) — انحراف معیار"),
    "VARIANCE": (1, 1, "VARIANCE([فیلد]) — واریانس"),
    "PERCENTILE": (2, 2, "PERCENTILE([فیلد]، 90) — صدک"),
    "MIN_OF": (1, 1, "MIN_OF([فیلد]) — کمینه در گروه"),
    "MAX_OF": (1, 1, "MAX_OF([فیلد]) — بیشینه در گروه"),
}


def is_aggregate_call(node) -> bool:
    return node[0] == "call" and (node[1] in AGGREGATES or
                                  (node[1] in ("MIN", "MAX") and len(node[2]) == 1))


def walk(node):
    yield node
    if node[0] == "bin":
        yield from walk(node[2])
        yield from walk(node[3])
    elif node[0] == "neg":
        yield from walk(node[1])
    elif node[0] == "call":
        for a in node[2]:
            yield from walk(a)


def field_refs(node) -> set:
    return {n[1] for n in walk(node) if n[0] == "field"}


def has_aggregate(node) -> bool:
    return any(is_aggregate_call(n) for n in walk(node))


# ── validation ─────────────────────────────────────────────────────────────
def resolve_ref(ref: str, fields: dict, labels: dict):
    if ref in fields:
        return ref
    return labels.get(ref)


def compile_formula(text: str, fields: dict) -> dict:
    """Parse and check a formula against the fields it may use.

    ``fields`` maps key → field dict (with ``label`` and ``type``). Returns
    {"tree", "kind": "row"|"group", "refs": [keys]}; raises FormulaError.
    """
    tree = parse(text)
    labels = {f.get("label"): k for k, f in fields.items()}
    refs = set()
    for node in walk(tree):
        if node[0] == "field":
            key = resolve_ref(node[1], fields, labels)
            if key is None:
                raise FormulaError(f"فیلد «{node[1]}» در این منبع داده وجود ندارد.")
            refs.add(key)
        elif node[0] == "call":
            spec = FUNCTIONS.get(node[1])
            if spec is None:
                raise FormulaError(f"تابع «{node[1]}» وجود ندارد.")
            lo, hi, _help = spec
            n = len(node[2])
            if n < lo or (hi is not None and n > hi):
                raise FormulaError(f"تعداد ورودی‌های {node[1]} نادرست است: {spec[2]}")
            if node[1] in ("DATE_DIFF",) and n == 3 and node[2][2][0] == "str" \
                    and node[2][2][1] not in ("day", "hour", "month", "year", "minute"):
                raise FormulaError('واحد DATE_DIFF باید یکی از "day"، "hour"، "month"، "year" باشد.')
    kind = "group" if has_aggregate(tree) else "row"
    if kind == "group":
        # every field reference must sit inside an aggregate
        def outside(node, inside):
            if node[0] == "field" and not inside:
                return node[1]
            if node[0] == "bin":
                return outside(node[2], inside) or outside(node[3], inside)
            if node[0] == "neg":
                return outside(node[1], inside)
            if node[0] == "call":
                agg = is_aggregate_call(node)
                for a in node[2]:
                    bad = outside(a, inside or agg)
                    if bad:
                        return bad
            return None
        bad = outside(tree, False)
        if bad:
            raise FormulaError(f"در فرمول گروهی، فیلد «{bad}» باید داخل یک تابع تجمیعی "
                               "(مثل SUM، AVG، COUNT_IF) باشد.")
    return {"tree": tree, "kind": kind, "refs": sorted(refs)}


def check_cycles(calcs: list, fields: dict):
    """Refuse calculated fields that refer to each other in a circle."""
    graph = {}
    keys = {c["key"] for c in calcs}
    for c in calcs:
        comp = compile_formula(c["formula"], fields)
        graph[c["key"]] = [r for r in comp["refs"] if r in keys]
    seen, stack = set(), set()

    def visit(k):
        if k in stack:
            raise FormulaError(f"فیلدهای محاسباتی به هم ارجاع دوری دارند («{k}»).")
        if k in seen:
            return
        stack.add(k)
        for n in graph.get(k, []):
            visit(n)
        stack.discard(k)
        seen.add(k)
    for k in graph:
        visit(k)
    # an order in which row-level calcs can be computed
    order, done = [], set()

    def place(k):
        if k in done:
            return
        for n in graph.get(k, []):
            place(n)
        done.add(k)
        order.append(k)
    for k in graph:
        place(k)
    return order


# ── evaluation ─────────────────────────────────────────────────────────────
def _num(v):
    if v is None or v == "":
        return None
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (int, float)):
        return v
    try:
        return float(str(v).translate(_FA_DIGITS).replace(",", ""))
    except ValueError:
        return None


def _as_date(v):
    if v is None:
        return None
    if isinstance(v, _dt.datetime):
        return v
    if isinstance(v, _dt.date):
        return v
    text = str(v)
    if re.match(r"^(19|20)\d\d-\d\d-\d\d", text):
        try:
            return _dt.date.fromisoformat(text[:10])
        except ValueError:
            return None
    return parse_jalali_to_date(text)


def _truthy(v):
    if isinstance(v, list):
        return bool(v)
    return bool(v) and v != "0"


def _compare(op, a, b):
    if isinstance(a, list):
        a = "، ".join(str(x) for x in a)
    if a is None or b is None:
        if op in ("=", "=="):
            return a is None and b is None
        if op in ("<>", "!="):
            return not (a is None and b is None)
        return False
    na, nb = _num(a), _num(b)
    if na is not None and nb is not None and not (isinstance(a, str) and isinstance(b, str)):
        a, b = na, nb
    elif isinstance(a, (_dt.date, _dt.datetime)) or isinstance(b, (_dt.date, _dt.datetime)):
        a, b = _as_date(a), _as_date(b)
        if isinstance(a, _dt.datetime) != isinstance(b, _dt.datetime):
            a = a.date() if isinstance(a, _dt.datetime) else a
            b = b.date() if isinstance(b, _dt.datetime) else b
        if a is None or b is None:
            return False
    else:
        a, b = str(a), str(b)
    try:
        return {"=": a == b, "==": a == b, "<>": a != b, "!=": a != b, "<": a < b,
                "<=": a <= b, ">": a > b, ">=": a >= b}[op]
    except TypeError:
        return False


def _date_diff(a, b, unit="day"):
    a, b = _as_date(a), _as_date(b)
    if a is None or b is None:
        return None
    if isinstance(a, _dt.datetime) or isinstance(b, _dt.datetime):
        a = a if isinstance(a, _dt.datetime) else _dt.datetime.combine(a, _dt.time())
        b = b if isinstance(b, _dt.datetime) else _dt.datetime.combine(b, _dt.time())
        seconds = (a - b).total_seconds()
    else:
        seconds = (a - b).days * 86400
    if unit == "minute":
        return round(seconds / 60, 2)
    if unit == "hour":
        return round(seconds / 3600, 2)
    if unit == "month":
        return round(seconds / 86400 / 30.44, 2)
    if unit == "year":
        return round(seconds / 86400 / 365.25, 2)
    return round(seconds / 86400, 2)


def _jparts(v):
    d = _as_date(v)
    if d is None:
        return None
    if isinstance(d, _dt.datetime):
        d = d.date()
    return gregorian_to_jalali(d)


class Evaluator:
    """Evaluate a compiled tree on a row, or on a group of rows."""

    def __init__(self, fields: dict):
        self.labels = {f.get("label"): k for k, f in fields.items()}
        self.fields = fields

    def key(self, ref):
        return ref if ref in self.fields else self.labels.get(ref, ref)

    def row(self, tree, row: dict):
        return self._ev(tree, row, None)

    def group(self, tree, rows: list):
        return self._ev(tree, None, rows)

    def _ev(self, n, row, rows):
        t = n[0]
        if t == "num" or t == "str":
            return n[1]
        if t == "null":
            return None
        if t == "field":
            return (row or {}).get(self.key(n[1]))
        if t == "neg":
            v = _num(self._ev(n[1], row, rows))
            return -v if v is not None else None
        if t == "bin":
            op = n[1]
            a = self._ev(n[2], row, rows)
            b = self._ev(n[3], row, rows)
            if op in ("=", "==", "<>", "!=", "<", "<=", ">", ">="):
                return _compare(op, a, b)
            if op == "&":
                return f"{'' if a is None else a}{'' if b is None else b}"
            a, b = _num(a), _num(b)
            if a is None or b is None:
                return None
            if op == "+":
                return a + b
            if op == "-":
                return a - b
            if op == "*":
                return a * b
            if op == "/":
                return None if b == 0 else a / b
            if op == "%":
                return None if b == 0 else a % b
            if op == "^":
                try:
                    return a ** b
                except (OverflowError, ValueError):
                    return None
        if t == "call":
            return self._call(n[1], n[2], row, rows)
        return None

    def _values(self, expr, rows):
        return [self._ev(expr, r, None) for r in rows or []]

    def _call(self, name, args, row, rows):
        if rows is not None and (name in AGGREGATES or (name in ("MIN", "MAX") and len(args) == 1)):
            return self._aggregate(name, args, rows)
        ev = lambda a: self._ev(a, row, rows)  # noqa: E731
        if name == "IF":
            return ev(args[1]) if _truthy(ev(args[0])) else (ev(args[2]) if len(args) > 2 else None)
        if name == "AND":
            return all(_truthy(ev(a)) for a in args)
        if name == "OR":
            return any(_truthy(ev(a)) for a in args)
        if name == "NOT":
            return not _truthy(ev(args[0]))
        if name == "ROUND":
            v = _num(ev(args[0]))
            d = int(_num(ev(args[1])) or 0) if len(args) > 1 else 0
            return round(v, d) if v is not None else None
        if name == "ABS":
            v = _num(ev(args[0]))
            return abs(v) if v is not None else None
        if name in ("MIN", "MAX"):
            vals = [_num(ev(a)) for a in args]
            vals = [v for v in vals if v is not None]
            return (min(vals) if name == "MIN" else max(vals)) if vals else None
        if name == "CONCAT":
            return "".join("" if v is None else ("، ".join(map(str, v)) if isinstance(v, list) else str(v))
                           for v in (ev(a) for a in args))
        if name == "COALESCE":
            for a in args:
                v = ev(a)
                if v not in (None, "", []):
                    return v
            return None
        if name == "DATE_DIFF":
            unit = ev(args[2]) if len(args) > 2 else "day"
            return _date_diff(ev(args[0]), ev(args[1]), unit or "day")
        if name in ("DAY", "MONTH", "YEAR"):
            p = _jparts(ev(args[0]))
            return None if p is None else p[{"YEAR": 0, "MONTH": 1, "DAY": 2}[name]]
        if name == "LEN":
            v = ev(args[0])
            return len(v) if isinstance(v, (list, str)) else (None if v is None else len(str(v)))
        if name == "TODAY":
            return _dt.date.today()
        if name == "NUMBER":
            return _num(ev(args[0]))
        if name == "TEXT":
            v = ev(args[0])
            return None if v is None else str(v)
        if name == "CONTAINS":
            hay, needle = ev(args[0]), ev(args[1])
            if isinstance(hay, list):
                return str(needle) in [str(x) for x in hay]
            return hay is not None and str(needle) in str(hay)
        # an aggregate used without a group: treat the single row as the group
        return self._aggregate(name, args, [row] if row is not None else [])

    def _aggregate(self, name, args, rows):
        if name == "COUNT":
            if not args:
                return len(rows)
            return len([v for v in self._values(args[0], rows) if v not in (None, "", [])])
        if name == "COUNT_IF":
            return len([1 for v in self._values(args[0], rows) if _truthy(v)])
        if name == "COUNT_DISTINCT":
            seen = set()
            for v in self._values(args[0], rows):
                for x in (v if isinstance(v, list) else [v]):
                    if x not in (None, ""):
                        seen.add(str(x))
            return len(seen)
        if name == "SUM_IF":
            total = 0
            for r in rows:
                if _truthy(self._ev(args[1], r, None)):
                    total += _num(self._ev(args[0], r, None)) or 0
            return total
        nums = [x for x in (_num(v) for v in self._values(args[0], rows)) if x is not None]
        if name == "SUM":
            return sum(nums)
        if not nums:
            return None
        if name == "AVG":
            return sum(nums) / len(nums)
        if name in ("MIN", "MIN_OF"):
            return min(nums)
        if name in ("MAX", "MAX_OF"):
            return max(nums)
        if name == "MEDIAN":
            return statistics.median(nums)
        if name == "STDDEV":
            return statistics.stdev(nums) if len(nums) > 1 else 0.0
        if name == "VARIANCE":
            return statistics.variance(nums) if len(nums) > 1 else 0.0
        if name == "PERCENTILE":
            p = _num(self._ev(args[1], rows[0] if rows else {}, None)) or 50
            return percentile(nums, p)
        return None


def percentile(nums, p):
    if not nums:
        return None
    s = sorted(nums)
    k = (len(s) - 1) * (max(0.0, min(100.0, float(p))) / 100.0)
    lo, hi = math.floor(k), math.ceil(k)
    if lo == hi:
        return s[int(k)]
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def function_help() -> list:
    return [{"name": k, "help": v[2], "aggregate": k in AGGREGATES or k in ("MIN", "MAX")}
            for k, v in FUNCTIONS.items()]
