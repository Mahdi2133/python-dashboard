# -*- coding: utf-8 -*-
"""The query engine: from a report definition and a data source to results.

Everything a report shows — KPI cards, charts, tables, drill-down levels, the
analysis page and every export — is computed here from the one definition, so
the dashboard, the specialised analysis and the files can never disagree.

Pipeline for one run::

    source rows (row-level scope applied)
      → row-level calculated fields
      → report filters  AND  interactive filters  AND  drill-down path
      → per element: grouping (multi-level, date granularity, multi-choice
        exploded) and aggregation (registry below, extensible)
      → group-level calculated fields
      → sort, limit, totals, rules

Rows come from the catalogue's cache (keyed by the data version) so repeated
runs of dashboards do not re-read the database; a hard row cap keeps a runaway
report from taking the server with it.
"""
from __future__ import annotations

import datetime as _dt
import statistics
from collections import OrderedDict, defaultdict

from ..services.jalali import (MONTHS_FA, gregorian_to_jalali, jalali_to_gregorian,
                               local_now, parse_jalali_to_date, today_jalali)
from .catalogue import NUMERIC, TEMPORAL, get_source
from .formula import Evaluator, FormulaError, check_cycles, compile_formula, percentile

MAX_ROWS = 200_000          # rows read from a source in one run
MAX_GROUPS = 5_000          # groups returned by one element
DETAIL_PAGE_MAX = 500


class ReportError(ValueError):
    pass


# ── aggregations (extensible: add an entry) ────────────────────────────────
def _nums(values):
    out = []
    for v in values:
        if isinstance(v, bool):
            out.append(int(v))
        elif isinstance(v, (int, float)):
            out.append(v)
        elif v not in (None, "", []):
            try:
                out.append(float(str(v).replace(",", "")))
            except ValueError:
                pass
    return out


def _distinct(values):
    seen = set()
    for v in values:
        for x in (v if isinstance(v, list) else [v]):
            if x not in (None, ""):
                seen.add(str(x))
    return seen


AGGREGATIONS = OrderedDict([
    ("count", ("تعداد", lambda vals, p=None: len(vals), False)),
    ("count_values", ("تعداد مقادیر غیرخالی",
                      lambda vals, p=None: len([v for v in vals if v not in (None, "", [])]), False)),
    ("count_distinct", ("تعداد یکتا", lambda vals, p=None: len(_distinct(vals)), False)),
    ("sum", ("جمع", lambda vals, p=None: sum(_nums(vals)), True)),
    ("avg", ("میانگین", lambda vals, p=None: (sum(n) / len(n)) if (n := _nums(vals)) else None, True)),
    ("min", ("کمینه", lambda vals, p=None: min(n) if (n := _nums(vals)) else None, True)),
    ("max", ("بیشینه", lambda vals, p=None: max(n) if (n := _nums(vals)) else None, True)),
    ("median", ("میانه", lambda vals, p=None: statistics.median(n) if (n := _nums(vals)) else None, True)),
    ("percentile", ("صدک", lambda vals, p=None: percentile(_nums(vals), p or 90), True)),
    ("stddev", ("انحراف معیار", lambda vals, p=None:
                (statistics.stdev(n) if len(n) > 1 else 0.0) if (n := _nums(vals)) else None, True)),
    ("variance", ("واریانس", lambda vals, p=None:
                  (statistics.variance(n) if len(n) > 1 else 0.0) if (n := _nums(vals)) else None, True)),
    ("range", ("دامنه", lambda vals, p=None: (max(n) - min(n)) if (n := _nums(vals)) else None, True)),
    ("count_true", ("تعداد «بله»", lambda vals, p=None: len([v for v in vals if v is True]), False)),
    ("pct_true", ("درصد «بله»", lambda vals, p=None:
                  (100.0 * len([v for v in vals if v is True]) / len(vals)) if vals else None, False)),
])


# ── operators ───────────────────────────────────────────────────────────────
OPERATORS = OrderedDict([
    ("eq", "مساوی"), ("ne", "نامساوی"), ("contains", "شامل"),
    ("not_contains", "شامل نباشد"), ("starts", "شروع با"), ("ends", "پایان با"),
    ("gt", "بزرگ‌تر از"), ("gte", "بزرگ‌تر یا مساوی"), ("lt", "کوچک‌تر از"),
    ("lte", "کوچک‌تر یا مساوی"), ("between", "بین دو مقدار"), ("in", "یکی از"),
    ("empty", "خالی"), ("not_empty", "غیرخالی"), ("date_on", "تاریخ مشخص"),
    ("date_between", "بازه‌ی تاریخی"), ("relative", "بازه‌ی نسبی"),
])

RELATIVE = OrderedDict([
    ("today", "امروز"), ("yesterday", "دیروز"), ("this_week", "این هفته"),
    ("last_week", "هفته‌ی قبل"), ("this_month", "این ماه"), ("last_month", "ماه قبل"),
    ("this_quarter", "این فصل"), ("last_quarter", "فصل قبل"), ("this_year", "امسال"),
    ("last_year", "سال قبل"), ("last_7", "۷ روز اخیر"), ("last_30", "۳۰ روز اخیر"),
    ("last_90", "۹۰ روز اخیر"), ("last_365", "یک سال اخیر"),
])

GRANULARITY = OrderedDict([("day", "روز"), ("week", "هفته"), ("month", "ماه"),
                           ("quarter", "فصل"), ("year", "سال")])


def _gdate(jy, jm, jd):
    return jalali_to_gregorian(jy, jm, jd)


def _month_start(jy, jm):
    return _gdate(jy, jm, 1)


def _next_month(jy, jm):
    return (jy + 1, 1) if jm == 12 else (jy, jm + 1)


def relative_range(key: str, today: _dt.date | None = None):
    """[start, end) in Gregorian dates for a Jalali relative period."""
    today = today or local_now().date()
    jy, jm, jd = gregorian_to_jalali(today)
    one = _dt.timedelta(days=1)
    if key == "today":
        return today, today + one
    if key == "yesterday":
        return today - one, today
    if key in ("this_week", "last_week"):
        start = today - _dt.timedelta(days=(today.weekday() + 2) % 7)  # Saturday
        if key == "last_week":
            start -= _dt.timedelta(days=7)
        return start, start + _dt.timedelta(days=7)
    if key == "this_month":
        return _month_start(jy, jm), _month_start(*_next_month(jy, jm))
    if key == "last_month":
        py, pm = (jy - 1, 12) if jm == 1 else (jy, jm - 1)
        return _month_start(py, pm), _month_start(jy, jm)
    if key in ("this_quarter", "last_quarter"):
        q = (jm - 1) // 3
        qy = jy
        if key == "last_quarter":
            q -= 1
            if q < 0:
                q, qy = 3, jy - 1
        start = _month_start(qy, q * 3 + 1)
        ey, em = (qy + 1, 1) if q == 3 else (qy, q * 3 + 4)
        return start, _month_start(ey, em)
    if key == "this_year":
        return _month_start(jy, 1), _month_start(jy + 1, 1)
    if key == "last_year":
        return _month_start(jy - 1, 1), _month_start(jy, 1)
    if key.startswith("last_") and key[5:].isdigit():
        return today - _dt.timedelta(days=int(key[5:]) - 1), today + one
    raise ReportError(f"بازه‌ی نسبی «{key}» شناخته نشد.")


def _to_date(v):
    if v is None or v == "":
        return None
    if isinstance(v, _dt.datetime):
        return v.date()
    if isinstance(v, _dt.date):
        return v
    text = str(v).strip()
    if len(text) >= 10 and text[:2] in ("19", "20") and text[4] == "-":
        try:
            return _dt.date.fromisoformat(text[:10])
        except ValueError:
            return None
    return parse_jalali_to_date(text)


def _to_num(v):
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (int, float)):
        return v
    try:
        return float(str(v).translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٫", "0123456789.")).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _text(v):
    if v is None:
        return ""
    if isinstance(v, list):
        return "، ".join(str(x) for x in v)
    if isinstance(v, bool):
        return "بله" if v else "خیر"
    if isinstance(v, (_dt.date, _dt.datetime)):
        return jalali_str(v)
    return str(v)


def jalali_str(v, with_time=False):
    if v is None:
        return ""
    if isinstance(v, _dt.datetime):
        y, m, d = gregorian_to_jalali(v.date())
        s = f"{y}/{m:02d}/{d:02d}"
        return f"{s} {v.hour:02d}:{v.minute:02d}" if with_time else s
    if isinstance(v, _dt.date):
        y, m, d = gregorian_to_jalali(v)
        return f"{y}/{m:02d}/{d:02d}"
    return str(v)


def condition_holds(row, cond, fields):
    fkey = cond.get("field")
    op = cond.get("operator") or "eq"
    field = fields.get(fkey) or {}
    ftype = field.get("type")
    value = row.get(fkey)
    target, target2 = cond.get("value"), cond.get("value2")
    if op == "empty":
        return value in (None, "", [])
    if op == "not_empty":
        return value not in (None, "", [])
    if ftype in TEMPORAL or op in ("date_on", "date_between", "relative"):
        d = _to_date(value)
        if op == "relative":
            if d is None:
                return False
            start, end = relative_range(str(target))
            return start <= d < end
        if op in ("date_on", "eq"):
            t = _to_date(target)
            return d is not None and t is not None and d == t
        if op in ("date_between", "between"):
            a, b = _to_date(target), _to_date(target2)
            if d is None:
                return False
            return (a is None or d >= a) and (b is None or d <= b)
        if op in ("gt", "gte", "lt", "lte"):
            t = _to_date(target)
            if d is None or t is None:
                return False
            return {"gt": d > t, "gte": d >= t, "lt": d < t, "lte": d <= t}[op]
        if op == "ne":
            t = _to_date(target)
            return d != t
    if isinstance(value, list):
        items = [str(x) for x in value]
        wanted = target if isinstance(target, list) else [target]
        wanted = [str(w) for w in wanted if w not in (None, "")]
        if op in ("eq", "in", "contains"):
            return any(w in items for w in wanted) if op != "contains" else \
                any(any(str(w) in i for i in items) for w in wanted)
        if op in ("ne", "not_contains"):
            return not any(w in items for w in wanted)
        text = "، ".join(items)
    else:
        text = _text(value)
    if ftype in NUMERIC or op in ("gt", "gte", "lt", "lte", "between"):
        n = _to_num(value)
        if op == "between":
            a, b = _to_num(target), _to_num(target2)
            return n is not None and (a is None or n >= a) and (b is None or n <= b)
        if op in ("gt", "gte", "lt", "lte"):
            t = _to_num(target)
            if n is None or t is None:
                return False
            return {"gt": n > t, "gte": n >= t, "lt": n < t, "lte": n <= t}[op]
        if op in ("eq", "ne") and _to_num(target) is not None and n is not None:
            return (n == _to_num(target)) == (op == "eq")
    if ftype == "boolean" and op in ("eq", "ne"):
        truth = str(target).lower() in ("1", "true", "yes", "بله")
        return (bool(value) == truth) == (op == "eq")
    if op == "in":
        wanted = target if isinstance(target, list) else [target]
        return text in [str(w) for w in wanted]
    t = _text(target)
    if op == "eq":
        return text == t
    if op == "ne":
        return text != t
    if op == "contains":
        return t in text
    if op == "not_contains":
        return t not in text
    if op == "starts":
        return text.startswith(t)
    if op == "ends":
        return text.endswith(t)
    return True


def tree_holds(row, node, fields):
    """A filter tree: {"op": "and"|"or", "items": [condition | tree]}."""
    if not node:
        return True
    if "items" not in node:
        if not node.get("field"):
            return True
        return condition_holds(row, node, fields)
    items = [i for i in node.get("items") or [] if i and (i.get("field") or i.get("items"))]
    if not items:
        return True
    results = (tree_holds(row, i, fields) for i in items)
    return any(results) if (node.get("op") or "and") == "or" else all(results)


def tree_fields(node) -> set:
    if not node:
        return set()
    if "items" not in node:
        return {node.get("field")} if node.get("field") else set()
    out = set()
    for i in node.get("items") or []:
        out |= tree_fields(i)
    return out


# ── grouping keys ───────────────────────────────────────────────────────────
def group_value(value, field, granularity=None):
    """(sort key, label) of a value for grouping; multi-choice → several."""
    ftype = (field or {}).get("type")
    if isinstance(value, list):
        return [(str(v), str(v)) for v in value] or [("", "(خالی)")]
    if ftype in TEMPORAL or isinstance(value, (_dt.date, _dt.datetime)):
        d = _to_date(value)
        if d is None:
            return [("~", "(بدون تاریخ)")]
        jy, jm, jd = gregorian_to_jalali(d)
        g = granularity or "month"
        if g == "year":
            return [(f"{jy:04d}", str(jy))]
        if g == "quarter":
            q = (jm - 1) // 3 + 1
            return [(f"{jy:04d}-{q}", f"{jy} — فصل {q}")]
        if g == "month":
            return [(f"{jy:04d}-{jm:02d}", f"{MONTHS_FA[jm]} {jy}")]
        if g == "week":
            start = d - _dt.timedelta(days=(d.weekday() + 2) % 7)
            sy, sm, sd = gregorian_to_jalali(start)
            return [(start.isoformat(), f"هفته‌ی {sy}/{sm:02d}/{sd:02d}")]
        return [(f"{jy:04d}-{jm:02d}-{jd:02d}", f"{jy}/{jm:02d}/{jd:02d}")]
    if value is None or value == "":
        return [("~", "(خالی)")]
    if isinstance(value, bool):
        return [("1" if value else "0", "بله" if value else "خیر")]
    if isinstance(value, (int, float)):
        return [(f"{value:020.4f}" if value >= 0 else f"-{-value:019.4f}", _fmt_num(value))]
    if field and field.get("key") in ("_month",) and value in MONTHS_FA:
        return [(f"{MONTHS_FA.index(value):02d}", value)]
    if field and field.get("options") and value in field["options"]:
        return [(f"{field['options'].index(value):04d}", str(value))]
    return [(str(value), str(value))]


def _fmt_num(v):
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


# ── the run context ─────────────────────────────────────────────────────────
class Run:
    """One execution of a definition: the rows it reads and how to compute."""

    def __init__(self, definition: dict, scope=None, extra_filter=None,
                 drill=None, source_rows=None):
        self.d = definition or {}
        self.source = get_source(self.d.get("source") or "")
        if self.source is None:
            raise ReportError("منبع داده‌ی گزارش انتخاب نشده یا وجود ندارد.")
        self.base_fields = self.source.field_map()
        self.fields = dict(self.base_fields)
        self.calcs = {}
        self.compiled = {}
        for c in self.d.get("calcs") or []:
            if not c.get("key") or not c.get("formula"):
                continue
            self.fields[c["key"]] = {"key": c["key"], "label": c.get("label") or c["key"],
                                     "type": "calc", "group": "محاسباتی"}
        for c in self.d.get("calcs") or []:
            if not c.get("key") or not c.get("formula"):
                continue
            try:
                comp = compile_formula(c["formula"], self.fields)
            except FormulaError as exc:
                raise ReportError(f"فرمول «{c.get('label') or c['key']}»: {exc}") from exc
            self.calcs[c["key"]] = c
            self.compiled[c["key"]] = comp
            if comp["kind"] == "row":
                self.fields[c["key"]]["type"] = c.get("result_type") or "decimal"
        self.row_order = [k for k in check_cycles(
            [c for c in self.calcs.values()], self.fields)
            if self.compiled[k]["kind"] == "row"]
        self.ev = Evaluator(self.fields)
        raw = source_rows if source_rows is not None else self.source.rows(scope)
        if len(raw) > MAX_ROWS:
            raise ReportError(f"این گزارش بیش از {MAX_ROWS:,} ردیف دارد؛ فیلتر محدودتری بگذارید.")
        rows = raw
        if self.row_order:
            rows = []
            for r in raw:
                r = dict(r)
                for k in self.row_order:
                    try:
                        r[k] = self.ev.row(self.compiled[k]["tree"], r)
                    except Exception:
                        r[k] = None
                rows.append(r)
        self.filters_applied = [self.d.get("filters"), extra_filter]
        rows = [r for r in rows if tree_holds(r, self.d.get("filters"), self.fields)
                and tree_holds(r, extra_filter, self.fields)]
        self.drill_filter = None
        if drill:
            rows = self._apply_drill(rows, drill)
        self.rows = rows

    # drill-down: equality on the levels above the one being shown
    def _apply_drill(self, rows, drill):
        path = (self.d.get("drill") or {}).get("path") or []
        values = drill.get("values") or []
        for level, val in zip(path, values):
            fkey, gran = _split_level(level)
            field = self.fields.get(fkey)
            rows = [r for r in rows if any(k == val for k, _l in
                                           group_value(r.get(fkey), field, gran))]
        return rows

    # ── measures ──
    def measure_value(self, measure: dict, rows: list):
        if measure.get("calc"):
            comp = self.compiled.get(measure["calc"])
            if comp is None:
                return None
            if comp["kind"] == "group":
                try:
                    return self.ev.group(comp["tree"], rows)
                except Exception:
                    return None
            agg = measure.get("agg") or "sum"
            vals = [r.get(measure["calc"]) for r in rows]
            return AGGREGATIONS[agg][1](vals, measure.get("p"))
        agg = measure.get("agg") or "count"
        if agg not in AGGREGATIONS:
            raise ReportError(f"تجمیع «{agg}» شناخته نشد.")
        fkey = measure.get("field") or "*"
        vals = rows if fkey == "*" else [r.get(fkey) for r in rows]
        if fkey == "*" and agg not in ("count",):
            vals = [1 for _ in rows]
        try:
            return AGGREGATIONS[agg][1](vals, measure.get("p"))
        except Exception:
            return None

    def measure_label(self, m):
        if m.get("label"):
            return m["label"]
        if m.get("calc"):
            return (self.calcs.get(m["calc"]) or {}).get("label") or m["calc"]
        agg = AGGREGATIONS.get(m.get("agg") or "count", ("",))[0]
        if (m.get("field") or "*") == "*":
            return agg
        return f"{agg} {self.fields.get(m['field'], {}).get('label', m['field'])}"

    def resolve_measures(self, refs):
        """Measure refs → measure dicts: a key of the report's measures, or inline."""
        by_key = {m.get("key"): m for m in self.d.get("measures") or [] if m.get("key")}
        out = []
        for ref in refs or []:
            if isinstance(ref, str):
                if ref in by_key:
                    out.append(by_key[ref])
                elif ref in self.calcs:
                    out.append({"key": ref, "calc": ref})
            elif isinstance(ref, dict):
                out.append(ref)
        return out

    # ── grouping ──
    def aggregate(self, groups: list, measures: list, rows=None, sort=None, limit=None,
                  totals=True):
        rows = self.rows if rows is None else rows
        groups = [g for g in groups or [] if g.get("field")]
        buckets = OrderedDict()
        if not groups:
            buckets[()] = (tuple(), rows)
        else:
            tmp = defaultdict(list)
            labels = {}
            for r in rows:
                combos = [[]]
                for g in groups:
                    field = self.fields.get(g["field"])
                    vals = group_value(r.get(g["field"]), field, g.get("granularity"))
                    if g.get("explode") is False and len(vals) > 1:
                        vals = [("، ".join(v[0] for v in vals), "، ".join(v[1] for v in vals))]
                    combos = [c + [v] for c in combos for v in vals]
                for combo in combos:
                    key = tuple(v[0] for v in combo)
                    labels[key] = tuple(v[1] for v in combo)
                    tmp[key].append(r)
            for key in sorted(tmp):
                buckets[key] = (labels[key], tmp[key])
        if len(buckets) > MAX_GROUPS:
            raise ReportError(f"گروه‌بندی بیش از {MAX_GROUPS:,} گروه می‌سازد؛ "
                              "سطح گروه‌بندی یا فیلترها را تغییر دهید.")
        columns = [{"key": f"g{i}", "label": self.fields.get(g["field"], {}).get("label", g["field"])
                    + (f" ({GRANULARITY.get(g.get('granularity'))})" if g.get("granularity") else ""),
                    "type": "dimension", "field": g["field"]} for i, g in enumerate(groups)]
        mcols = []
        for i, m in enumerate(measures):
            key = m.get("key") or f"m{i}"
            mcols.append({"key": key, "label": self.measure_label(m), "type": "measure",
                          "format": m.get("format"), "decimals": m.get("decimals"),
                          "unit": m.get("unit")})
        out = []
        for key, (labels, grp) in buckets.items():
            row = {"_key": list(key), "_count": len(grp)}
            for i, lab in enumerate(labels):
                row[f"g{i}"] = lab
            for i, m in enumerate(measures):
                row[mcols[i]["key"]] = self.measure_value(m, grp)
            out.append(row)
        if sort:
            for s in reversed(sort):
                k = s.get("key")
                rev = (s.get("dir") or "asc") == "desc"
                out.sort(key=lambda r: (r.get(k) is None,
                                        r.get(k) if not isinstance(r.get(k), str) else r.get(k)),
                         reverse=rev)
                if rev:   # keep empties last
                    out.sort(key=lambda r: r.get(k) is None)
        if limit:
            out = out[:int(limit)]
        total = None
        if totals and groups:
            total = {c["key"]: self.measure_value(m, rows) for c, m in zip(mcols, measures)}
        return {"columns": columns + mcols, "rows": out, "total": total,
                "row_count": len(rows)}


def _split_level(level):
    if isinstance(level, dict):
        return level.get("field"), level.get("granularity")
    if ":" in str(level):
        f, g = str(level).split(":", 1)
        return f, g
    return level, None


# ── elements ────────────────────────────────────────────────────────────────
def rule_style(rules, target, value):
    """The first matching rule's style for ``value`` of ``target``."""
    for r in rules or []:
        if r.get("target") not in (target, "*"):
            continue
        t = r.get("value")
        v = _to_num(value)
        tn = _to_num(t)
        op = r.get("operator") or ">"
        ok = False
        if v is not None and tn is not None:
            ok = {">": v > tn, ">=": v >= tn, "<": v < tn, "<=": v <= tn,
                  "=": v == tn, "!=": v != tn}.get(op, False)
        elif op in ("=", "!="):
            ok = (_text(value) == _text(t)) == (op == "=")
        elif op == "contains":
            ok = _text(t) in _text(value)
        if ok:
            return {"style": r.get("style") or "warn", "color": r.get("color"),
                    "label": r.get("label")}
    return None


def compute_kpi(run: Run, kpi: dict, rules=None):
    val = kpi.get("value") or {}
    rows = run.rows
    if kpi.get("filters"):
        rows = [r for r in rows if tree_holds(r, kpi["filters"], run.fields)]
    measure = ({"calc": val["calc"]} if val.get("calc") else
               {"field": val.get("field") or "*", "agg": val.get("agg") or "count",
                "p": val.get("p")})
    if val.get("formula"):
        try:
            comp = compile_formula(val["formula"], run.fields)
            value = run.ev.group(comp["tree"], rows) if comp["kind"] == "group" else None
        except FormulaError as exc:
            raise ReportError(f"فرمول KPI «{kpi.get('title')}»: {exc}") from exc
    else:
        value = run.measure_value(measure, rows)
    out = {"id": kpi.get("id"), "title": kpi.get("title") or "شاخص", "value": value,
           "unit": kpi.get("unit"), "format": kpi.get("format"),
           "decimals": kpi.get("decimals"), "min": kpi.get("min"), "max": kpi.get("max"),
           "target": kpi.get("target"), "direction": kpi.get("direction") or "higher"}
    # status against the target
    target = _to_num(kpi.get("target"))
    v = _to_num(value)
    status = None
    if target is not None and v is not None:
        good = v >= target if out["direction"] == "higher" else v <= target
        near = (abs(v - target) <= abs(target) * (float(kpi.get("tolerance") or 10) / 100.0))
        status = "ok" if good else ("warn" if near else "bad")
        out["progress"] = round(100.0 * v / target, 1) if target else None
    styled = rule_style(rules, kpi.get("id"), value)
    if styled:
        status = styled["style"]
        out["rule_label"] = styled.get("label")
        out["color"] = styled.get("color")
    out["status"] = status
    # comparison with the previous period, and the trend
    pfield = kpi.get("period_field")
    period = kpi.get("period") or "month"
    if pfield and (kpi.get("compare") or kpi.get("trend")):
        cur_key = {"month": "this_month", "quarter": "this_quarter", "year": "this_year"}[period]
        prev_key = {"month": "last_month", "quarter": "last_quarter", "year": "last_year"}[period]
        in_range = lambda r, key: (lambda d, rg: d is not None and rg[0] <= d < rg[1])(  # noqa: E731
            _to_date(r.get(pfield)), relative_range(key))
        if kpi.get("compare"):
            cur = run.measure_value(measure, [r for r in rows if in_range(r, cur_key)])
            prev = run.measure_value(measure, [r for r in rows if in_range(r, prev_key)])
            out["current"] = cur
            out["previous"] = prev
            cn, pn = _to_num(cur), _to_num(prev)
            out["change_pct"] = (round((cn - pn) / pn * 100.0, 1)
                                 if cn is not None and pn not in (None, 0) else None)
            out["period_label"] = {"month": "ماه", "quarter": "فصل", "year": "سال"}[period]
        if kpi.get("trend"):
            agg = run.aggregate([{"field": pfield, "granularity": period}], [measure],
                                rows=rows, totals=False)
            out["trend"] = [{"label": r["g0"], "value": r.get(agg["columns"][-1]["key"])}
                            for r in agg["rows"][-12:]]
    return out


def compute_chart(run: Run, chart: dict):
    rows = run.rows
    if chart.get("filters"):
        rows = [r for r in rows if tree_holds(r, chart["filters"], run.fields)]
    measures = run.resolve_measures(chart.get("measures") or [])
    if not measures:
        measures = [{"field": "*", "agg": "count", "key": "count"}]
    x = chart.get("x") or {}
    groups = []
    if x.get("field"):
        groups.append({"field": x["field"], "granularity": x.get("granularity")})
    series_by = chart.get("series_by") or {}
    if series_by.get("field"):
        groups.append({"field": series_by["field"], "granularity": series_by.get("granularity")})
    ctype = chart.get("type") or "bar"
    # charts over raw values rather than groups
    if ctype in ("scatter", "bubble") and chart.get("y_field"):
        pts = []
        for r in rows[:5000]:
            xv, yv = _to_num(r.get(x.get("field"))), _to_num(r.get(chart["y_field"]))
            if xv is None or yv is None:
                continue
            size = _to_num(r.get(chart.get("size_field"))) if chart.get("size_field") else None
            pts.append([xv, yv, size])
        return {"id": chart.get("id"), "type": ctype, "points": pts,
                "x_label": run.fields.get(x.get("field"), {}).get("label"),
                "y_label": run.fields.get(chart["y_field"], {}).get("label")}
    if ctype in ("histogram", "box") and chart.get("value_field"):
        vals = _nums(r.get(chart["value_field"]) for r in rows)
        out = {"id": chart.get("id"), "type": ctype,
               "value_label": run.fields.get(chart["value_field"], {}).get("label")}
        if ctype == "histogram":
            bins = int(chart.get("bins") or 10)
            if vals:
                lo, hi = min(vals), max(vals)
                width = (hi - lo) / bins if hi > lo else 1
                counts = [0] * bins
                for v in vals:
                    counts[min(bins - 1, int((v - lo) / width))] += 1
                out["bins"] = [{"label": f"{round(lo + i * width, 2)}–{round(lo + (i + 1) * width, 2)}",
                                "value": c} for i, c in enumerate(counts)]
            else:
                out["bins"] = []
        else:
            by = groups[0]["field"] if groups else None
            boxes = []
            if by:
                agg = run.aggregate([groups[0]], [{"field": "*", "agg": "count"}], rows=rows,
                                    totals=False)
                for g in agg["rows"]:
                    key = g["_key"][0]
                    grp = [r for r in rows if any(k == key for k, _l in group_value(
                        r.get(by), run.fields.get(by), groups[0].get("granularity")))]
                    boxes.append({"label": g["g0"], "stats": _box(_nums(r.get(chart["value_field"]) for r in grp))})
            else:
                boxes.append({"label": out["value_label"], "stats": _box(vals)})
            out["boxes"] = boxes
        return out
    agg = run.aggregate(groups, measures, rows=rows,
                        sort=[{"key": (chart.get("sort") or {}).get("key") or
                               (measures[0].get("key") or "m0"),
                               "dir": (chart.get("sort") or {}).get("dir") or "desc"}]
                        if (chart.get("sort") or {}).get("by") == "value" else None,
                        totals=False)
    mkeys = [c["key"] for c in agg["columns"] if c["type"] == "measure"]
    labels = [c["label"] for c in agg["columns"] if c["type"] == "measure"]
    data = {"id": chart.get("id"), "type": ctype, "measure_labels": labels}
    if len(groups) == 2:
        cats, series = [], OrderedDict()
        for r in agg["rows"]:
            if r["g0"] not in cats:
                cats.append(r["g0"])
            series.setdefault(r["g1"], {})[r["g0"]] = r.get(mkeys[0])
        data["categories"] = cats
        data["series"] = [{"name": s, "data": [vals.get(c) for c in cats]}
                          for s, vals in series.items()]
    else:
        rows_out = agg["rows"]
        if chart.get("limit"):
            rows_out = sorted(rows_out, key=lambda r: -(_to_num(r.get(mkeys[0])) or 0)) \
                if ctype in ("pareto", "ranking") else rows_out
            rows_out = rows_out[:int(chart["limit"])]
        elif ctype in ("pareto", "ranking"):
            rows_out = sorted(rows_out, key=lambda r: -(_to_num(r.get(mkeys[0])) or 0))
        data["categories"] = [r.get("g0", "همه") for r in rows_out]
        data["series"] = [{"name": labels[i], "data": [r.get(k) for r in rows_out]}
                          for i, k in enumerate(mkeys)]
        if ctype in ("kpi", "gauge", "progress"):
            data["value"] = rows_out[0].get(mkeys[0]) if rows_out else None
            data["target"] = chart.get("target")
            data["max"] = chart.get("max")
    return data


def _box(vals):
    if not vals:
        return None
    s = sorted(vals)
    return [s[0], percentile(s, 25), percentile(s, 50), percentile(s, 75), s[-1]]


def compute_table(run: Run, table: dict):
    rows = run.rows
    if table.get("filters"):
        rows = [r for r in rows if tree_holds(r, table["filters"], run.fields)]
    kind = table.get("kind") or ("grouped" if (run.d.get("groups") or table.get("groups")) else "detail")
    if kind == "grouped":
        groups = table.get("groups") or run.d.get("groups") or []
        measures = run.resolve_measures(table.get("measures")) or run.d.get("measures") or \
            [{"key": "count", "field": "*", "agg": "count"}]
        res = run.aggregate(groups, measures, rows=rows, sort=table.get("sort") or run.d.get("sort"),
                            limit=table.get("limit") or run.d.get("limit"))
        # subtotals per first group level
        if table.get("subtotals") and len(groups) > 1:
            subs = OrderedDict()
            for r in res["rows"]:
                subs.setdefault(r.get("g0"), []).append(r)
            merged = []
            mkeys = [c for c in res["columns"] if c["type"] == "measure"]
            for label, grp in subs.items():
                merged.extend(grp)
                sub_rows = [x for x in rows if any(
                    lab == label for _k, lab in group_value(
                        x.get(groups[0]["field"]), run.fields.get(groups[0]["field"]),
                        groups[0].get("granularity")))]
                sub = {"_subtotal": True, "g0": f"جمع «{label}»"}
                for c, m in zip(mkeys, measures):
                    sub[c["key"]] = run.measure_value(m, sub_rows)
                merged.append(sub)
            res["rows"] = merged
        res["kind"] = "grouped"
    else:
        keys = table.get("columns") or [f["key"] for f in run.d.get("fields") or []] or \
            list(run.fields)[:8]
        cols = []
        labels = {f.get("key"): f for f in run.d.get("fields") or []}
        for k in keys:
            f = run.fields.get(k)
            if f is None:
                continue
            cfg = labels.get(k) or {}
            cols.append({"key": k, "label": cfg.get("label") or f.get("label"), "type": f.get("type"),
                         "format": cfg.get("format"), "decimals": cfg.get("decimals")})
        srt = table.get("sort") or run.d.get("sort") or []
        data = list(rows)
        for s in reversed(srt):
            k = s.get("key")
            data.sort(key=lambda r: (r.get(k) is None, _sortable(r.get(k))),
                      reverse=(s.get("dir") == "desc"))
        limit = int(table.get("limit") or run.d.get("limit") or 1000)
        res = {"kind": "detail", "columns": cols,
               "rows": [serialize_row(r, [c["key"] for c in cols] + ["_id"]) for r in data[:limit]],
               "row_count": len(data), "truncated": len(data) > limit}
        # footer: sum/avg/min/max/count per numeric column
        totals = table.get("totals") or {}
        if totals:
            foot = {}
            for c in cols:
                agg = totals.get(c["key"])
                if agg in AGGREGATIONS:
                    foot[c["key"]] = AGGREGATIONS[agg][1]([r.get(c["key"]) for r in data])
            res["total"] = foot
    res["id"] = table.get("id")
    return res


def _sortable(v):
    if isinstance(v, (int, float)):
        return (0, v, "")
    if isinstance(v, (_dt.date, _dt.datetime)):
        return (1, 0, v.isoformat())
    return (2, 0, _text(v))


def serialize_value(v):
    if isinstance(v, _dt.datetime):
        return jalali_str(v, with_time=True)
    if isinstance(v, _dt.date):
        return jalali_str(v)
    return v


def serialize_row(r, keys=None):
    keys = keys or list(r)
    return {k: serialize_value(r.get(k)) for k in keys if not k.startswith("_center")}


# ── the whole report ────────────────────────────────────────────────────────
def run_report(definition: dict, scope=None, extra_filter=None, drill=None) -> dict:
    run = Run(definition, scope=scope, extra_filter=extra_filter, drill=drill)
    d = run.d
    rules = d.get("rules") or []
    out = {"row_count": len(run.rows), "source": run.source.key,
           "source_label": run.source.label,
           "kpis": [], "charts": [], "tables": [], "generated_at": jalali_str(local_now(), True)}
    for k in d.get("kpis") or []:
        try:
            out["kpis"].append(compute_kpi(run, k, rules))
        except ReportError as exc:
            out["kpis"].append({"id": k.get("id"), "title": k.get("title"), "error": str(exc)})
    for c in d.get("charts") or []:
        try:
            out["charts"].append(compute_chart(run, c))
        except ReportError as exc:
            out["charts"].append({"id": c.get("id"), "error": str(exc)})
    tables = d.get("tables") or []
    if not tables:
        tables = [{"id": "_main"}]
    for t in tables:
        try:
            out["tables"].append(compute_table(run, t))
        except ReportError as exc:
            out["tables"].append({"id": t.get("id"), "error": str(exc)})
    if drill is not None:
        out["drill"] = drill_level(run, drill)
    return out


def drill_level(run: Run, drill: dict) -> dict:
    """The next level of a drill-down path, or the rows at its end."""
    path = (run.d.get("drill") or {}).get("path") or []
    level = len(drill.get("values") or [])
    if level >= len(path) or path[level] in ("_detail", "_records"):
        keys = [f["key"] for f in run.d.get("fields") or []] or list(run.fields)[:10]
        cols = [{"key": k, "label": run.fields.get(k, {}).get("label", k)} for k in keys
                if k in run.fields]
        return {"level": level, "detail": True, "columns": cols,
                "rows": [serialize_row(r, keys + ["_id"]) for r in run.rows[:DETAIL_PAGE_MAX]],
                "row_count": len(run.rows)}
    fkey, gran = _split_level(path[level])
    measures = run.d.get("measures") or [{"key": "count", "field": "*", "agg": "count"}]
    res = run.aggregate([{"field": fkey, "granularity": gran}], measures, totals=True)
    res["level"] = level
    res["field"] = fkey
    res["field_label"] = run.fields.get(fkey, {}).get("label", fkey)
    res["detail"] = False
    return res


# ── analysis helpers ────────────────────────────────────────────────────────
def detail_rows(run: Run, keys=None, search=None, sort=None, page=1, page_size=50):
    keys = [k for k in (keys or [f["key"] for f in run.d.get("fields") or []]) if k in run.fields] \
        or [k for k in list(run.fields) if not k.startswith("_center")][:12]
    data = run.rows
    if search:
        s = str(search).strip()
        data = [r for r in data if any(s in _text(r.get(k)) for k in keys)]
    for srt in reversed(sort or []):
        k = srt.get("key")
        data = sorted(data, key=lambda r: (r.get(k) is None, _sortable(r.get(k))),
                      reverse=(srt.get("dir") == "desc"))
    page_size = max(1, min(DETAIL_PAGE_MAX, int(page_size or 50)))
    page = max(1, int(page or 1))
    start = (page - 1) * page_size
    return {"columns": [{"key": k, "label": run.fields[k].get("label", k),
                         "type": run.fields[k].get("type")} for k in keys],
            "rows": [serialize_row(r, keys + ["_id"]) for r in data[start:start + page_size]],
            "row_count": len(data), "page": page, "page_size": page_size}


def crosstab(run: Run, row_field, col_field, measure, row_gran=None, col_gran=None):
    res = run.aggregate([{"field": row_field, "granularity": row_gran},
                         {"field": col_field, "granularity": col_gran}], [measure], totals=True)
    mkey = res["columns"][-1]["key"]
    rows_l, cols_l, cells = [], [], {}
    for r in res["rows"]:
        if r["g0"] not in rows_l:
            rows_l.append(r["g0"])
        if r["g1"] not in cols_l:
            cols_l.append(r["g1"])
        cells[(r["g0"], r["g1"])] = r.get(mkey)
    # row and column totals
    rt = run.aggregate([{"field": row_field, "granularity": row_gran}], [measure], totals=False)
    ct = run.aggregate([{"field": col_field, "granularity": col_gran}], [measure], totals=False)
    row_tot = {r["g0"]: r.get(rt["columns"][-1]["key"]) for r in rt["rows"]}
    col_tot = {r["g0"]: r.get(ct["columns"][-1]["key"]) for r in ct["rows"]}
    return {"row_label": run.fields.get(row_field, {}).get("label", row_field),
            "col_label": run.fields.get(col_field, {}).get("label", col_field),
            "measure_label": run.measure_label(measure),
            "rows": rows_l, "cols": cols_l,
            "cells": [[cells.get((r, c)) for c in cols_l] for r in rows_l],
            "row_totals": [row_tot.get(r) for r in rows_l],
            "col_totals": [col_tot.get(c) for c in cols_l],
            "grand_total": res.get("total", {}).get(mkey) if res.get("total") else None}


def statistics_summary(run: Run, keys=None):
    keys = keys or [k for k, f in run.fields.items()
                    if f.get("type") in NUMERIC or (f.get("type") == "decimal")]
    out = []
    for k in keys:
        f = run.fields.get(k)
        if f is None:
            continue
        vals = _nums(r.get(k) for r in run.rows)
        if not vals:
            out.append({"key": k, "label": f.get("label"), "count": 0})
            continue
        out.append({"key": k, "label": f.get("label"), "count": len(vals),
                    "empty": len(run.rows) - len(vals),
                    "sum": sum(vals), "mean": sum(vals) / len(vals),
                    "median": statistics.median(vals),
                    "stddev": statistics.stdev(vals) if len(vals) > 1 else 0.0,
                    "min": min(vals), "p25": percentile(vals, 25), "p75": percentile(vals, 75),
                    "max": max(vals), "range": max(vals) - min(vals)})
    return out


def raw_rows(run: Run, page=1, page_size=100):
    keys = [k for k in run.fields if not k.startswith("_center")]
    page_size = max(1, min(DETAIL_PAGE_MAX, int(page_size or 100)))
    start = (max(1, int(page or 1)) - 1) * page_size
    return {"columns": [{"key": k, "label": run.fields[k].get("label", k)} for k in keys],
            "rows": [serialize_row(r, keys) for r in run.rows[start:start + page_size]],
            "row_count": len(run.rows), "page": page, "page_size": page_size}
