# -*- coding: utf-8 -*-
"""Starting reports: the workshop's earlier fixed reports, as editable data.

The fourteen fixed reports (and three supplementary ones) used to be Python
functions. Here each is only a report *definition* — the same thing the admin
builds in گزارش‌ساز — seeded once, published and granted to the supervisor
and viewer roles. From then on they are ordinary reports: the admin edits,
versions, re-grants, archives or deletes them like any other, and no code
knows them. A template that names a field the forms no longer have is simply
not seeded.
"""
from __future__ import annotations

import json
import logging

from ..extensions import db

log = logging.getLogger(__name__)
SEED_KEY = "report_templates_v1"

BASIC = "گزارش‌های پایه کارگاه"
PROCESS = "فرایندها و مراحل"
VIEW_LEVELS = ["view_dashboard", "view_analysis", "run", "filter", "drilldown",
               "export_xlsx", "export_pdf", "export_docx", "export_csv", "print"]
GRANTS = [{"principal_kind": "role", "principal": "supervisor",
           "access": VIEW_LEVELS + ["raw_data"]},
          {"principal_kind": "role", "principal": "viewer", "access": VIEW_LEVELS}]


def m(key, field="*", agg="count", label=None, **kw):
    out = {"key": key, "field": field, "agg": agg}
    if label:
        out["label"] = label
    out.update(kw)
    return out


def chart(cid, ctype, title, x=None, measures=None, **kw):
    out = {"id": cid, "type": ctype, "title": title, "measures": measures or ["n"]}
    if x:
        out["x"] = {"field": x} if isinstance(x, str) else x
    out.update(kw)
    return out


def kpi(kid, title, **kw):
    out = {"id": kid, "title": title, "value": kw.pop("value", {"agg": "count", "field": "*"})}
    out.update(kw)
    return out


DATE_FILTER = {"id": "f_date", "field": "_date", "kind": "date_range", "label": "تاریخ عملیات"}
CENTER_FILTER = {"id": "f_center", "field": "center", "kind": "multi", "label": "مرکز"}
OP_FILTER = {"id": "f_op", "field": "c_op", "kind": "select", "label": "عملیات"}
COMMON_FILTERS = [DATE_FILTER, CENTER_FILTER, OP_FILTER]
# New records keep the operation in «نوع عملیات», history in «عملیات انجام شده».
OP_CALC = {"key": "c_op", "label": "عملیات", "result_type": "text",
           "formula": "COALESCE([operation_kind], [operation])"}
DETAIL_FIELDS = [{"key": k} for k in ("_date", "well", "center", "c_op", "failure",
                                      "contractor", "pump_curr", "motor_curr")]


def grouped(title, group, measures, charts, key, desc, kpis=None, extra=None, category=BASIC,
            filters=None, drill=None):
    d = {"source": "records", "groups": group if isinstance(group, list) else [{"field": group}],
         "measures": measures, "charts": charts, "kpis": kpis or [],
         "tables": [{"id": "t1", "title": "جدول " + title, "kind": "grouped"}],
         "fields": DETAIL_FIELDS, "interactive_filters": filters or COMMON_FILTERS,
         "sort": [{"key": measures[0]["key"], "dir": "desc"}],
         "drill": drill or {"enabled": True, "path": [(group if isinstance(group, str) else group[0]["field"]),
                                                     "_date:year"]}}
    d.update(extra or {})
    return {"key": key, "name": title, "description": desc, "category": category, "definition": d}


TEMPLATES = [
    {"key": "overall", "name": "داشبورد کلی کارگاه", "category": BASIC,
     "description": "نمای مدیریتی کارگاه: حجم عملیات، روند ماهانه، سهم نوع عملیات، مراکز و علت‌های پرتکرار خرابی.",
     "definition": {
         "source": "records",
         "groups": [{"field": "center"}],
         "measures": [m("n", label="تعداد عملیات"), m("wells", "well", "count_distinct", "تعداد چاه"),
                      m("head", "total_head", "avg", "میانگین هد کلی (متر)", decimals=1)],
         "kpis": [kpi("k_total", "کل عملیات", icon="🛠", period_field="_date", period="month",
                      compare=True, trend=True),
                  kpi("k_wells", "چاه‌های درگیر", icon="💧", value={"agg": "count_distinct", "field": "well"}),
                  kpi("k_year", "عملیات امسال", icon="📅", filters={"op": "and", "items": [
                      {"field": "_date", "operator": "relative", "value": "this_year"}]}),
                  kpi("k_head", "میانگین هد کلی", icon="📏", unit="متر", decimals=1,
                      value={"agg": "avg", "field": "total_head"})],
         "charts": [chart("c_trend", "trend_month", "روند ماهانه‌ی عملیات", "_date", limit=None),
                    chart("c_kind", "donut", "سهم نوع عملیات", "c_op", show_labels=True),
                    chart("c_center", "bar", "عملیات به تفکیک مرکز", "center", sort={"by": "value"}),
                    chart("c_fail", "pareto", "پارتوی علت خرابی (۱۰ مورد اول)", "failure", limit=10,
                          filters={"op": "and", "items": [{"field": "failure", "operator": "not_empty"}]})],
         "tables": [{"id": "t1", "title": "خلاصه‌ی مراکز", "kind": "grouped"}],
         "fields": DETAIL_FIELDS, "interactive_filters": COMMON_FILTERS,
         "sort": [{"key": "n", "dir": "desc"}],
         "drill": {"enabled": True, "path": ["center", "_date:year", "_date:month"]},
         "layout": [{"ref": "kpi:k_total", "w": 3}, {"ref": "kpi:k_wells", "w": 3},
                    {"ref": "kpi:k_year", "w": 3}, {"ref": "kpi:k_head", "w": 3},
                    {"ref": "chart:c_trend", "w": 8}, {"ref": "chart:c_kind", "w": 4},
                    {"ref": "chart:c_center", "w": 6}, {"ref": "chart:c_fail", "w": 6},
                    {"ref": "table:t1", "w": 12}]}},
    {"key": "date_range", "name": "فهرست عملیات در بازه‌ی زمانی", "category": BASIC,
     "description": "همه‌ی عملیات ثبت‌شده بین دو تاریخ شمسی، با جستجو، مرتب‌سازی و خروجی.",
     "definition": {"source": "records", "fields": DETAIL_FIELDS,
                    "kpis": [kpi("k_n", "تعداد عملیات در بازه")],
                    "tables": [{"id": "t1", "title": "فهرست عملیات", "kind": "detail", "limit": 5000,
                                "page_size": 50}],
                    "sort": [{"key": "_date", "dir": "desc"}],
                    "interactive_filters": COMMON_FILTERS + [
                        {"id": "f_well", "field": "well", "kind": "text", "label": "نام چاه"}]}},
    grouped("گزارش ماهانه", [{"field": "_date", "granularity": "month"}],
            [m("n", label="تعداد عملیات"), m("wells", "well", "count_distinct", "تعداد چاه")],
            [chart("c1", "trend_month", "روند ماهانه", "_date", measures=["n", "wells"])],
            "monthly", "تعداد عملیات و چاه‌ها به تفکیک ماه شمسی.",
            drill={"enabled": True, "path": ["_date:month", "center"]}),
    grouped("گزارش سالانه", [{"field": "_year"}, {"field": "c_op"}],
            [m("n", label="تعداد عملیات")],
            [chart("c1", "stacked_column", "عملیات هر سال به تفکیک نوع", "_year",
                   series_by={"field": "c_op"})],
            "yearly", "مقایسه‌ی سال‌ها به تفکیک نوع عملیات، با جمع هر سال.",
            extra={"tables": [{"id": "t1", "title": "سال × نوع عملیات", "kind": "grouped",
                               "subtotals": True}]},
            drill={"enabled": True, "path": ["_year", "center"]}),
    grouped("گزارش نوع عملیات", "c_op", [m("n", label="تعداد")],
            [chart("c1", "pie", "سهم هر نوع عملیات", "c_op", show_labels=True)],
            "operation", "تعداد عملیات به تفکیک نوع عملیات."),
    grouped("گزارش علت خرابی", "failure", [m("n", label="تعداد")],
            [chart("c1", "pareto", "پارتوی علت خرابی", "failure"),
             chart("c2", "hbar", "علت خرابی", "failure", sort={"by": "value"}, show_labels=True)],
            "failure", "هر علت خرابی چند بار ثبت شده است (هر گزینه‌ی چندانتخابی جدا شمرده می‌شود).",
            extra={"filters": {"op": "and", "items": [{"field": "failure", "operator": "not_empty"}]}}),
    grouped("گزارش پیمانکار", "contractor",
            [m("n", label="تعداد"), m("head", "total_head", "avg", "میانگین هد (متر)", decimals=1),
             m("flow", "test_flow", "avg", "میانگین دبی آزمایش", decimals=1)],
            [chart("c1", "bar", "عملیات هر پیمانکار", "contractor", sort={"by": "value"})],
            "contractor", "عملکرد هر پیمانکار با میانگین شاخص‌های فنی.",
            extra={"filters": {"op": "and", "items": [{"field": "contractor", "operator": "not_empty"}]}}),
    grouped("گزارش مرکز", "center",
            [m("n", label="تعداد عملیات"), m("wells", "well", "count_distinct", "تعداد چاه")],
            [chart("c1", "bar", "عملیات هر مرکز", "center", sort={"by": "value"}, show_labels=True)],
            "center", "عملیات و چاه‌های هر مرکز (واحد)."),
    grouped("گزارش پمپ", "pump_curr",
            [m("n", label="تعداد"), m("flow", "design_flow", "avg", "میانگین دبی طراحی", decimals=1),
             m("head", "total_head", "avg", "میانگین هد (متر)", decimals=1)],
            [chart("c1", "hbar", "۱۵ تیپ پرکاربرد پمپ", "pump_curr", sort={"by": "value"}, limit=15)],
            "pump", "تیپ‌های پمپ نصب‌شده با میانگین دبی و هد."),
    grouped("گزارش الکتروموتور", "motor_curr", [m("n", label="تعداد")],
            [chart("c1", "hbar", "۱۵ تیپ پرکاربرد الکتروموتور", "motor_curr", sort={"by": "value"}, limit=15)],
            "motor", "تیپ‌های الکتروموتور (توان) نصب‌شده."),
    grouped("گزارش چاه", "well",
            [m("n", label="تعداد مراجعه"), m("head", "total_head", "avg", "میانگین هد (متر)", decimals=1)],
            [chart("c1", "ranking", "۲۰ چاه با بیشترین مراجعه", "well", limit=20)],
            "wells", "تعداد مراجعه و شاخص‌های میانگین هر چاه.",
            drill={"enabled": True, "path": ["well", "_date:year"]}),
    grouped("گزارش تکرار خرابی", "well", [m("n", label="تعداد خرابی")],
            [chart("c1", "ranking", "۲۰ چاه با بیشترین خرابی", "well", limit=20, show_labels=True)],
            "failure_repeat", "کدام چاه‌ها بیشترین خرابی را داشته‌اند؛ سه بار و بیشتر قرمز می‌شود.",
            extra={"filters": {"op": "and", "items": [{"field": "failure", "operator": "not_empty"}]},
                   "rules": [{"target": "n", "operator": ">=", "value": 3, "style": "bad",
                              "label": "خرابی تکراری"}]},
            drill={"enabled": True, "path": ["well", "failure"]}),
    {"key": "pumping_test", "name": "گزارش تست پمپاژ", "category": BASIC,
     "description": "عملیات دارای آزمایش پمپاژ کارگاه مکانیک با دبی و فشار آزمایش.",
     "definition": {"source": "records",
                    "filters": {"op": "and", "items": [{"field": "test_flow", "operator": "not_empty"}]},
                    "fields": [{"key": k} for k in ("_date", "well", "center", "test_date", "test_pressure",
                                                    "test_flow", "design_flow", "pump_curr")],
                    "kpis": [kpi("k_n", "تعداد تست"),
                             kpi("k_flow", "میانگین دبی آزمایش", decimals=1,
                                 value={"agg": "avg", "field": "test_flow"}),
                             kpi("k_press", "میانگین فشار آزمایش", decimals=1,
                                 value={"agg": "avg", "field": "test_pressure"})],
                    "charts": [chart("c1", "histogram", "توزیع دبی آزمایش", value_field="test_flow", bins=12)],
                    "tables": [{"id": "t1", "title": "تست‌ها", "kind": "detail", "limit": 3000,
                                "totals": {"test_flow": "avg", "test_pressure": "avg"}}],
                    "interactive_filters": [DATE_FILTER, CENTER_FILTER]}},
    {"key": "design_vs_test", "name": "مقایسه‌ی دبی طراحی و دبی آزمایش", "category": BASIC,
     "description": "انحراف دبی آزمایش از دبی طراحی؛ انحراف بیش از ۱۰٪ کمتر از طراحی قرمز می‌شود.",
     "definition": {"source": "records",
                    "filters": {"op": "and", "items": [{"field": "test_flow", "operator": "not_empty"},
                                                       {"field": "design_flow", "operator": "gt", "value": 0}]},
                    "calcs": [{"key": "c_dev", "label": "انحراف از طراحی (٪)", "result_type": "percent",
                               "formula": "ROUND(([test_flow] - [design_flow]) / [design_flow] * 100, 1)"},
                              {"key": "c_below", "label": "سهم کمتر از طراحی (٪)", "result_type": "percent",
                               "formula": "ROUND(COUNT_IF([c_dev] < 0) / COUNT() * 100, 1)"}],
                    "fields": [{"key": k} for k in ("_date", "well", "center", "design_flow", "test_flow", "c_dev")],
                    "kpis": [kpi("k_n", "تعداد مقایسه"),
                             kpi("k_below", "سهم کمتر از طراحی", value={"calc": "c_below"}, unit="٪",
                                 target=20, direction="lower"),
                             kpi("k_dev", "میانگین انحراف", value={"agg": "avg", "field": "c_dev"}, unit="٪",
                                 decimals=1)],
                    "charts": [chart("c1", "scatter", "دبی طراحی در برابر دبی آزمایش", "design_flow",
                                     y_field="test_flow")],
                    "tables": [{"id": "t1", "title": "مقایسه‌ها", "kind": "detail", "limit": 3000,
                                "totals": {"c_dev": "avg"}}],
                    "rules": [{"target": "c_dev", "operator": "<", "value": -10, "style": "bad",
                               "label": "کمتر از طراحی"},
                              {"target": "c_dev", "operator": ">=", "value": 0, "style": "ok"}],
                    "interactive_filters": [DATE_FILTER, CENTER_FILTER]}},
    grouped("سازنده / تعمیرکار پمپ", "pump_maker", [m("n", label="تعداد")],
            [chart("c1", "donut", "سهم سازنده‌ها", "pump_maker", show_labels=True)],
            "maker", "سهم هر سازنده یا تعمیرکار در پمپ‌های نصب‌شده."),
    grouped("نظر کارگاه مکانیک", "workshop_opinion", [m("n", label="تعداد")],
            [chart("c1", "hbar", "تشخیص کارگاه مکانیک", "workshop_opinion", sort={"by": "value"})],
            "opinion", "تشخیص نهایی کارگاه مکانیک.",
            extra={"filters": {"op": "and", "items": [{"field": "workshop_opinion", "operator": "not_empty"}]}}),
    grouped("مجری (امانی / پیمانی)", "executor", [m("n", label="تعداد")],
            [chart("c1", "donut", "سهم مجری", "executor", show_labels=True),
             chart("c2", "stacked_column", "مجری در سال‌ها", "_year", series_by={"field": "executor"})],
            "executor", "سهم امانی و پیمانی در عملیات."),
    {"key": "process_perf", "name": "عملکرد فرایندها", "category": PROCESS,
     "description": "اجرای فرایندهای کشیدن و نصب: وضعیت، مدت، برگشت‌ها و تأخیرها.",
     "definition": {"source": "process", "groups": [{"field": "_process"}],
                    "measures": [m("n", label="تعداد اجرا"),
                                 m("days", "_duration_days", "avg", "میانگین مدت (روز)", decimals=1),
                                 m("ret", "_returns", "sum", "برگشت‌ها"), m("del", "_delays", "sum", "مراحل تأخیردار")],
                    "calcs": [{"key": "c_done", "label": "درصد تکمیل", "result_type": "percent",
                               "formula": "ROUND(COUNT_IF([_status] = \"تکمیل‌شده\") / COUNT() * 100, 1)"}],
                    "kpis": [kpi("k_n", "کل اجراها", period_field="_created_date", compare=True, trend=True),
                             kpi("k_done", "درصد تکمیل", value={"calc": "c_done"}, unit="٪", target=80),
                             kpi("k_days", "میانگین مدت اجرا", unit="روز", decimals=1,
                                 value={"agg": "avg", "field": "_duration_days"}, direction="lower"),
                             kpi("k_ret", "برگشت‌ها", value={"agg": "sum", "field": "_returns"}, direction="lower")],
                    "charts": [chart("c1", "pie", "وضعیت اجراها", "_status", show_labels=True),
                               chart("c2", "bar", "میانگین مدت هر فرایند (روز)", "_process", measures=["days"]),
                               chart("c3", "trend_month", "روند شروع فرایندها", "_created_date")],
                    "tables": [{"id": "t1", "title": "فرایندها", "kind": "grouped"}],
                    "fields": [{"key": k} for k in ("_id", "_process", "_well", "_center", "_status",
                                                    "_created_date", "_duration_days", "_returns")],
                    "interactive_filters": [{"id": "f_kind", "field": "_kind", "kind": "select", "label": "نوع عملیات"},
                                            {"id": "f_center", "field": "_center", "kind": "multi", "label": "مرکز"},
                                            {"id": "f_date", "field": "_created_date", "kind": "date_range",
                                             "label": "تاریخ شروع"}],
                    "drill": {"enabled": True, "path": ["_process", "_status"]}}},
    {"key": "stage_sla", "name": "عملکرد مراحل و مهلت (SLA)", "category": PROCESS,
     "description": "مدت انجام هر مرحله، صدک ۹۰، تأخیر نسبت به مهلت مرحله و سهم مراحل تأخیردار.",
     "definition": {"source": "steps", "groups": [{"field": "_stage"}],
                    "filters": {"op": "and", "items": [{"field": "_status", "operator": "eq", "value": "ثبت‌شده"}]},
                    "measures": [m("n", label="تعداد"),
                                 m("dur", "_duration_hours", "avg", "میانگین مدت (ساعت)", decimals=1),
                                 m("p90", "_duration_hours", "percentile", "صدک ۹۰ مدت (ساعت)", p=90, decimals=1),
                                 m("late", "_delayed", "pct_true", "سهم تأخیردار (٪)", decimals=1)],
                    "kpis": [kpi("k_dur", "میانگین مدت هر مرحله", unit="ساعت", decimals=1,
                                 value={"agg": "avg", "field": "_duration_hours"}, direction="lower"),
                             kpi("k_late", "سهم مراحل تأخیردار", unit="٪", decimals=1, target=10, direction="lower",
                                 value={"agg": "pct_true", "field": "_delayed"})],
                    "charts": [chart("c1", "hbar", "میانگین مدت هر مرحله (ساعت)", "_stage", measures=["dur"]),
                               chart("c2", "box", "پراکندگی مدت انجام مرحله", value_field="_duration_hours",
                                     x={"field": "_stage"})],
                    "tables": [{"id": "t1", "title": "مراحل", "kind": "grouped"}],
                    "rules": [{"target": "late", "operator": ">", "value": 20, "style": "bad", "label": "تأخیر زیاد"}],
                    "fields": [{"key": k} for k in ("_run_id", "_process", "_stage", "_well", "_filled_by",
                                                    "_started_at", "_submitted_at", "_duration_hours", "_delay_hours")],
                    "interactive_filters": [{"id": "f_proc", "field": "_process", "kind": "select", "label": "فرایند"},
                                            {"id": "f_date", "field": "_submitted_date", "kind": "date_range",
                                             "label": "تاریخ ثبت مرحله"}],
                    "drill": {"enabled": True, "path": ["_stage", "_filled_by"]}}},
]


def seed_templates(force=False) -> dict:
    """Create the starting reports once. Returns what was done."""
    from ..models import AppMeta
    from ..models.report import Report, ReportCategory
    from . import access as acc
    from .catalogue import get_source
    from .lifecycle import publish, referenced_fields, save_definition, validate
    if not force and AppMeta.get(SEED_KEY):
        return {"skipped": True}
    done, skipped = [], []
    cats = {}
    for t in TEMPLATES:
        if Report.query.filter_by(template_key=t["key"]).first():
            continue
        d = dict(t["definition"])
        if "c_op" in json.dumps(d, ensure_ascii=False) and not any(
                c.get("key") == "c_op" for c in d.get("calcs") or []):
            d["calcs"] = [OP_CALC] + list(d.get("calcs") or [])
        source = get_source(d["source"])
        fmap = source.field_map() if source else {}
        calc_keys = {c["key"] for c in d.get("calcs") or []}
        missing = [k for k in referenced_fields(d) if k not in fmap and k not in calc_keys]
        if source is None or missing:
            skipped.append((t["key"], missing))
            continue
        name = t["category"]
        if name not in cats:
            cats[name] = ReportCategory.query.filter_by(name=name).first() or ReportCategory(
                name=name, sort_order=len(cats))
            db.session.add(cats[name])
            db.session.flush()
        report = Report(name=t["name"], description=t["description"], category_id=cats[name].id,
                        template_key=t["key"])
        db.session.add(report)
        db.session.flush()
        version = save_definition(report, d, None, note="الگوی اولیه (از گزارش‌های ثابت قبلی)")
        acc.set_permissions(report, GRANTS)
        db.session.flush()
        db.session.refresh(report)
        check = validate(version.definition, report, run_query=False)
        if check["ok"]:
            publish(report, version)
        done.append(t["key"])
    AppMeta.set(SEED_KEY, "1")
    db.session.commit()
    if skipped:
        log.info("Report templates not seeded (fields missing): %s", skipped)
    return {"seeded": done, "skipped": skipped}
