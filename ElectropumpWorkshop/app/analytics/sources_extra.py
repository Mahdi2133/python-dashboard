"""Report-builder sources for the separate databases.

قطعات (مونتاژ و دمونتاژ), گردش انبار, دبی‌سنجی, روند تولید, ویدئومتری and
سوابق سنجش دبی each become a source of the report builder like the records and processes:
every column a field to group, filter, sum or chart by. A row that belongs to
a register well carries that well's center, so a user limited to some centers
sees only theirs.
"""
from __future__ import annotations

import json

from ..extensions import db
from ..services.jalali import MONTHS_FA, parse_jalali_to_date


def _fdef(*a, **k):
    from .catalogue import fdef
    return fdef(*a, **k)


def _jdate(text):
    try:
        return parse_jalali_to_date(text) if text else None
    except Exception:  # noqa: BLE001
        return None


def _wells():
    """main well id → (name, center id, center label)."""
    from ..models import LookupItem, Well
    labels = {i.id: (i.label or i.value) for i in LookupItem.query.all()}
    return {w.id: (w.name, w.center_id, labels.get(w.center_id))
            for w in Well.query.with_entities(Well.id, Well.name, Well.center_id)}


def _in_scope(scope, center_id):
    return scope is None or center_id in scope


# ── قطعات: مونتاژ و دمونتاژ ──────────────────────────────────────────────────
def parts_fields():
    g, h, q = "قطعه", "تجهیز و اقدام", "مقادیر"
    return [
        _fdef("_date", "تاریخ اقدام", "date", h),
        _fdef("_year", "سال", "integer", h),
        _fdef("_month", "ماه", "single", h),
        _fdef("_source", "منبع", "single", h),
        _fdef("_equipment_code", "کد تجهیز", "text", h),
        _fdef("_equipment_kind", "نوع تجهیز", "single", h),
        _fdef("_equipment_name", "نام تجهیز", "single", h),
        _fdef("_related_action", "اقدام مرتبط", "single", h),
        _fdef("_activity", "نوع فعالیت", "single", h),
        _fdef("_failure", "خرابی مشاهده شده", "single", h),
        _fdef("_cause", "علت خرابی", "single", h),
        _fdef("_action_done", "اقدام انجام شده", "single", h),
        _fdef("_facility", "تاسیس / چاه", "single", h),
        _fdef("_center", "مرکز", "center", h),
        _fdef("_user", "ثبت‌کننده", "single", h),
        _fdef("_part_action", "اقدام در سطح قطعه", "single", g),
        _fdef("_state", "وضعیت نو/کهنه", "single", g),
        _fdef("_assessment", "ارزیابی قطعه‌ی جمع‌آوری‌شده", "single", g),
        _fdef("_part_code", "کد انباری قطعه", "text", g),
        _fdef("_part_name", "شرح قطعه", "single", g),
        _fdef("_part_type", "نوع قطعه", "single", g),
        _fdef("_qty", "تعداد", "decimal", q),
        _fdef("_installed_new", "نصب — نو", "decimal", q),
        _fdef("_installed_repair", "نصب — کهنه (قابل استفاده مجدد)", "decimal", q),
        _fdef("_collected", "جمع‌آوری (ارزیابی‌نشده)", "decimal", q),
        _fdef("_reusable", "قابل استفاده مجدد", "decimal", q),
        _fdef("_scrap", "اسقاط", "decimal", q),
    ]


def load_parts(scope):
    from ..warehouse.models import WhPartAction
    wells = _wells() if scope is not None else {}
    rows = []
    for a in WhPartAction.query.yield_per(5000):
        center_id = wells.get(a.well_id, (None, None, None))[1] if a.well_id else None
        if scope is not None and a.well_id and not _in_scope(scope, center_id):
            continue
        qty = a.qty or 0
        installed = a.part_action == "installed"
        rows.append({
            "_id": a.id, "_date": _jdate(a.jdate), "_year": a.year,
            "_month": MONTHS_FA[a.month] if a.month and 1 <= a.month <= 12 else None,
            "_source": "فرایند" if a.source == "workflow" else "سوابق ۱۳۹۸ تا ۱۴۰۵",
            "_equipment_code": a.equipment_code, "_equipment_kind": a.equipment_kind,
            "_equipment_name": a.equipment_name, "_related_action": a.related_action,
            "_activity": a.activity, "_failure": a.failure, "_cause": a.cause,
            "_action_done": a.action_done, "_facility": a.well_name or a.facility_name,
            "_center": a.center, "_user": a.user_name,
            "_part_action": "نصب شد" if installed else "جمع‌آوری شد",
            "_state": ("نو" if a.state == "نو" else "کهنه (قابل استفاده مجدد)" if a.state == "کهنه" else None),
            "_assessment": (None if installed else "قابل استفاده مجدد" if a.reusable is True
                            else "اسقاط" if a.reusable is False else "ارزیابی‌نشده"),
            "_part_code": a.part_code, "_part_name": a.part_name, "_part_type": a.part_type,
            "_qty": qty,
            "_installed_new": qty if installed and a.state == "نو" else 0,
            "_installed_repair": qty if installed and a.state == "کهنه" else 0,
            "_collected": qty if not installed and a.reusable is None else 0,
            "_reusable": qty if not installed and a.reusable is True else 0,
            "_scrap": qty if not installed and a.reusable is False else 0,
            "_center_id": center_id})
    return rows


# ── موجودی انبار به تفکیک تیپ ───────────────────────────────────────────────
def stock_fields():
    h, q = "کالا", "موجودی"
    return [
        _fdef("_warehouse", "انبار", "single", h), _fdef("_item", "کالا", "single", h),
        _fdef("_kind", "نوع کالا", "single", h), _fdef("_category", "گروه", "single", h),
        _fdef("_variant", "تیپ (kW / تیپ/طبقه / تیپ پمپ)", "single", h),
        _fdef("_condition", "وضعیت", "single", h), _fdef("_unit", "واحد", "single", h),
        _fdef("_in", "ورود", "decimal", q), _fdef("_out", "خروج", "decimal", q),
        _fdef("_balance", "موجودی", "decimal", q),
    ]


def load_stock(scope):
    from ..warehouse.models import WhItem
    from ..warehouse.service import stock
    items = {i.id: i for i in WhItem.query.all()}
    rows = []
    for n, r in enumerate(stock()):
        it = items.get(r["item_id"])
        rows.append({"_id": n + 1, "_warehouse": r["warehouse_label"], "_item": r["item_name"],
                     "_kind": "تجهیز" if (it and it.kind == "equipment") else "قطعه",
                     "_category": it.category if it else None, "_variant": r["variant"] or None,
                     "_condition": r["condition_label"], "_unit": r["unit"], "_in": r["in"],
                     "_out": r["out"], "_balance": r["balance"], "_center_id": None})
    return rows


# ── گردش انبار ──────────────────────────────────────────────────────────────
def moves_fields():
    h, q = "گردش", "مقادیر"
    return [
        _fdef("_date", "تاریخ", "date", h), _fdef("_warehouse", "انبار", "single", h),
        _fdef("_direction", "ورود/خروج", "single", h), _fdef("_reason", "علت", "single", h),
        _fdef("_item", "کالا", "single", h), _fdef("_kind", "نوع کالا", "single", h),
        _fdef("_condition", "وضعیت", "single", h), _fdef("_spec", "تیپ / مشخصات", "text", h),
        _fdef("_variant", "تیپ (شمارش موجودی)", "single", h),
        _fdef("_serial", "پلاک / کد تجهیز", "text", h), _fdef("_well", "چاه", "single", h),
        _fdef("_workflow", "فرایند", "single", h), _fdef("_stage", "مرحله", "single", h),
        _fdef("_user", "کاربر", "single", h),
        _fdef("_qty", "مقدار", "decimal", q), _fdef("_in", "ورود", "decimal", q),
        _fdef("_out", "خروج", "decimal", q), _fdef("_net", "خالص (ورود − خروج)", "decimal", q),
    ]


def load_moves(scope):
    from ..warehouse.models import DIRECTIONS, REASONS, WAREHOUSES, WhCondition, WhMovement
    conds = {c.code: c.label for c in WhCondition.query.all()}
    wells = _wells() if scope is not None else {}
    rows = []
    for m in WhMovement.query.all():
        center_id = wells.get(m.well_id, (None, None, None))[1] if m.well_id else None
        if scope is not None and m.well_id and not _in_scope(scope, center_id):
            continue
        q = m.qty or 0
        rows.append({"_id": m.id, "_date": _jdate(m.jdate),
                     "_warehouse": WAREHOUSES.get(m.warehouse, m.warehouse),
                     "_direction": DIRECTIONS.get(m.direction), "_reason": REASONS.get(m.reason, m.reason),
                     "_item": m.item_name, "_kind": "تجهیز" if m.item_kind == "equipment" else "قطعه",
                     "_condition": conds.get(m.condition, m.condition), "_spec": m.spec,
                     "_variant": m.variant, "_serial": m.serial, "_well": m.well_name, "_workflow": m.workflow_name,
                     "_stage": m.stage_title or "ثبت دستی", "_user": m.user_name, "_qty": q,
                     "_in": q if m.direction == "in" else 0, "_out": q if m.direction == "out" else 0,
                     "_net": q if m.direction == "in" else -q, "_center_id": center_id})
    return rows


# ── دبی‌سنجی ─────────────────────────────────────────────────────────────────
def flow_fields():
    h, w, e, n = "آزمایش", "چاه", "الکتروپمپ", "اندازه‌گیری"
    return [
        _fdef("_date", "تاریخ آزمایش", "date", h), _fdef("_year", "سال", "integer", h),
        _fdef("_office", "اداره", "single", h), _fdef("_reason", "دلیل آزمایش", "single", h),
        _fdef("_well", "چاه در سامانه", "single", w), _fdef("_form_well", "نام چاه در فرم", "text", w),
        _fdef("_center", "مرکز", "center", w), _fdef("_class", "کلاسه چاه", "text", w),
        _fdef("_well_type", "نوع چاه", "single", w), _fdef("_drill_year", "سال حفر", "integer", w),
        _fdef("_electropump", "تیپ الکتروپمپ", "single", e), _fdef("_pump_type", "تیپ پمپ", "single", e),
        _fdef("_stages", "طبقات", "single", e), _fdef("_motor_kw", "توان موتور (kW)", "decimal", e),
        _fdef("_starter", "سیستم راه‌انداز", "single", e),
        _fdef("_well_depth", "عمق چاه", "decimal", n), _fdef("_install_depth", "عمق نصب", "decimal", n),
        _fdef("_static", "سطح ایستایی", "decimal", n), _fdef("_dynamic", "سطح دینامیک (فشار شبکه)", "decimal", n),
        _fdef("_design_flow", "دبی طراحی (l/s)", "decimal", n), _fdef("_net_flow", "آبدهی در فشار شبکه (l/s)", "decimal", n),
        _fdef("_net_pressure", "فشار شبکه (atm)", "decimal", n), _fdef("_efficiency", "راندمان (%)", "decimal", n),
        _fdef("_energy", "شدت انرژی", "decimal", n), _fdef("_points", "تعداد کارکرد", "integer", n),
    ]


def load_flow(scope):
    from ..refdata.models import FlowTest
    from ..services.epump import electropump_label
    wells = _wells()
    rows = []
    for t in FlowTest.query.all():
        name, center_id, center = wells.get(t.main_well_id, (None, None, None))
        if scope is not None and not _in_scope(scope, center_id):
            continue
        net = next((p for p in t.points if p.at_network), None)
        rows.append({"_id": t.id, "_date": _jdate(t.test_date),
                     "_year": int(t.test_date[:4]) if t.test_date else None,
                     "_office": t.office, "_reason": t.test_reason, "_well": name,
                     "_form_well": t.well_name, "_center": center, "_class": t.well_class,
                     "_well_type": t.well_type, "_drill_year": t.drill_year,
                     "_electropump": electropump_label(t.pump_type, t.pump_stages, t.motor_kw) or t.pump_label,
                     "_pump_type": t.pump_type, "_stages": t.pump_stages, "_motor_kw": t.motor_kw,
                     "_starter": t.starter, "_well_depth": t.well_depth, "_install_depth": t.install_depth,
                     "_static": t.static_level, "_dynamic": net.dynamic_level if net else None,
                     "_design_flow": t.design_flow, "_net_flow": t.net_flow,
                     "_net_pressure": t.net_pressure, "_efficiency": t.efficiency,
                     "_energy": t.energy_intensity, "_points": len(t.points), "_center_id": center_id})
    return rows


# ── روند تولید ───────────────────────────────────────────────────────────────
def prod_fields():
    h, q = "چاه و ماه", "مقادیر"
    return [
        _fdef("_date", "ماه (تاریخ)", "date", h), _fdef("_year", "سال", "integer", h),
        _fdef("_month", "ماه", "single", h), _fdef("_code", "کد تاسیس", "text", h),
        _fdef("_name", "نام چاه", "single", h), _fdef("_well", "چاه در سامانه", "single", h),
        _fdef("_center", "مرکز", "center", h), _fdef("_zone", "پهنه", "single", h),
        _fdef("_urban", "شهری/روستایی", "single", h), _fdef("_electropump", "تیپ الکتروپمپ", "single", h),
        _fdef("_pressure_type", "نوع فشار", "single", h),
        _fdef("_production", "تولید (m³)", "decimal", q), _fdef("_hours", "کارکرد (ساعت)", "decimal", q),
        _fdef("_avg_flow", "دبی متوسط (l/s)", "decimal", q), _fdef("_pressure", "فشار (atm)", "decimal", q),
    ]


def load_prod(scope):
    from ..refdata.models import ProdMonth, ProdWell
    from ..services.epump import electropump_label
    wells = _wells()
    meta = {}
    for w in ProdWell.query.all():
        name, center_id, center = wells.get(w.main_well_id, (None, None, None))
        meta[w.id] = (w, name, center_id, center,
                      electropump_label(w.pump_type, w.pump_stages, w.motor_kw))
    rows = []
    for m in ProdMonth.query.yield_per(5000):
        w, name, center_id, center, ep = meta.get(m.well_id, (None,) * 5)
        if w is None or (scope is not None and not _in_scope(scope, center_id)):
            continue
        rows.append({"_id": m.id, "_date": _jdate(f"{m.year}/{m.month:02d}/01"), "_year": m.year,
                     "_month": MONTHS_FA[m.month] if 1 <= m.month <= 12 else None,
                     "_code": w.facility_code, "_name": w.name, "_well": name, "_center": center,
                     "_zone": w.zone, "_urban": w.urban_rural, "_electropump": ep,
                     "_pressure_type": m.pressure_type, "_production": m.production,
                     "_hours": m.hours, "_avg_flow": m.avg_flow, "_pressure": m.pressure,
                     "_center_id": center_id})
    return rows


# ── ویدئومتری ────────────────────────────────────────────────────────────────
def video_fields():
    h, q = "بازدید", "مقادیر"
    return [
        _fdef("_date", "تاریخ ویدئومتری", "date", h), _fdef("_code", "کد تاسیس", "text", h),
        _fdef("_name", "نام", "single", h), _fdef("_well", "چاه در سامانه", "single", h),
        _fdef("_center", "مرکز", "center", h), _fdef("_notes", "توضیحات", "text", h),
        _fdef("_depth", "عمق چاه", "decimal", q), _fdef("_static", "سطح ایستابی", "decimal", q),
        _fdef("_screen", "عمق شروع مشبک", "decimal", q), _fdef("_defects", "تعداد ایرادات", "integer", q),
        _fdef("_repairs", "ترمیم", "integer", q), _fdef("_tears", "پارگی", "integer", q),
        _fdef("_changes", "تغییر جدار", "integer", q), _fdef("_clogs", "گرفتگی مشبک", "integer", q),
    ]


def load_video(scope):
    from ..refdata.models import VideoInspection
    wells = _wells()
    rows = []
    for v in VideoInspection.query.all():
        name, center_id, center = wells.get(v.main_well_id, (None, None, v.center))
        if scope is not None and not _in_scope(scope, center_id):
            continue
        count = lambda t: len(json.loads(t or "[]"))  # noqa: E731
        rows.append({"_id": v.id, "_date": _jdate(v.insp_date), "_code": v.facility_code,
                     "_name": v.name, "_well": name, "_center": center or v.center,
                     "_notes": v.notes, "_depth": v.depth, "_static": v.static_level,
                     "_screen": v.screen_start, "_defects": v.defect_count,
                     "_repairs": count(v.repair), "_tears": count(v.tear),
                     "_changes": count(v.change), "_clogs": count(v.clog), "_center_id": center_id})
    return rows


# ── سوابق سنجش دبی ───────────────────────────────────────────────────────────
def frec_fields():
    h, w, e, n, el = "سنجش", "چاه", "الکتروپمپ", "اندازه‌گیری", "برق"
    return [
        _fdef("_date", "تاریخ دبی‌سنجی", "date", h), _fdef("_year", "سال", "integer", h),
        _fdef("_reason", "دلیل سنجش دبی", "single", h), _fdef("_notes", "توضیحات", "text", h),
        _fdef("_code", "کد تاسیس", "text", w), _fdef("_name", "نام تاسیس", "single", w),
        _fdef("_well", "چاه در سامانه", "single", w), _fdef("_center", "مرکز", "center", w),
        _fdef("_electropump", "تیپ الکتروپمپ", "single", e), _fdef("_pump_type", "تیپ پمپ", "single", e),
        _fdef("_stages", "طبقات", "single", e), _fdef("_motor_kw", "توان موتور (kW)", "decimal", e),
        _fdef("_rehab", "تاریخ آخرین بهسازی", "text", e),
        _fdef("_well_depth", "عمق چاه", "decimal", n), _fdef("_install_depth", "عمق نصب", "decimal", n),
        _fdef("_static", "سطح ایستایی", "decimal", n), _fdef("_dynamic", "سطح پویایی", "decimal", n),
        _fdef("_drawdown", "افت سطح آب چاه (m)", "decimal", n),
        _fdef("_flow", "آبدهی (l/s)", "decimal", n), _fdef("_head", "هد (m)", "decimal", n),
        _fdef("_spcap", "ظرفیت ویژه", "decimal", n),
        _fdef("_net_pressure", "فشار شبکه (atm)", "decimal", n), _fdef("_line_pressure", "فشار خط (bar)", "decimal", n),
        _fdef("_active_power", "توان اکتیو (kW)", "decimal", el), _fdef("_cos_phi", "ضریب قدرت", "decimal", el),
        _fdef("_efficiency", "راندمان (%)", "decimal", el), _fdef("_energy", "شدت انرژی", "decimal", el),
    ]


def load_frec(scope):
    from ..refdata.models import FrRecord
    from ..services.epump import electropump_label
    wells = _wells()
    rows = []
    for r in FrRecord.query.all():
        name, center_id, center = wells.get(r.main_well_id, (None, None, None))
        if scope is not None and not _in_scope(scope, center_id):
            continue
        rows.append({"_id": r.id, "_date": _jdate(r.test_date),
                     "_year": int(r.test_date[:4]) if r.test_date else None,
                     "_reason": r.test_reason, "_notes": r.notes, "_code": r.facility_code,
                     "_name": r.name, "_well": name, "_center": center or r.center,
                     "_electropump": electropump_label(r.pump_type, r.pump_stages, r.motor_kw) or r.pump_label,
                     "_pump_type": r.pump_type, "_stages": r.pump_stages, "_motor_kw": r.motor_kw,
                     "_rehab": r.last_rehab_date, "_well_depth": r.well_depth,
                     "_install_depth": r.install_depth, "_static": r.static_level,
                     "_dynamic": r.dynamic_level, "_drawdown": r.level_drop, "_flow": r.flow,
                     "_head": r.head, "_spcap": r.specific_capacity, "_net_pressure": r.net_pressure,
                     "_line_pressure": r.line_pressure, "_active_power": r.active_power,
                     "_cos_phi": r.cos_phi, "_efficiency": r.efficiency,
                     "_energy": r.energy_intensity, "_center_id": center_id})
    return rows


def register(SOURCES, Source):
    SOURCES["wh_parts"] = Source(
        "wh_parts", "قطعات: مونتاژ و دمونتاژ (کارگاه مکانیک)",
        "هر ردیف یک قطعه‌ی نصب‌شده یا جمع‌آوری‌شده در یک تجهیز؛ سوابق ۹۸ تا ۰۵ و فرم‌های قطعات فرایند — "
        "نو/کهنه، قابل استفاده مجدد/اسقاط، به تفکیک قطعه، تجهیز، سال و ماه.",
        ("warehouse.view", "workflow.view", "report.manage"), "قطعه", parts_fields, load_parts)
    SOURCES["wh_moves"] = Source(
        "wh_moves", "گردش انبار تجهیزات و قطعات",
        "هر ردیف یک ورود یا خروج انبار؛ علت، وضعیت، چاه، مرحله‌ی فرایند و کاربر.",
        ("warehouse.view", "workflow.view", "report.manage"), "گردش", moves_fields, load_moves)
    SOURCES["wh_stock"] = Source(
        "wh_stock", "موجودی انبار (به تفکیک تیپ)",
        "هر ردیف موجودی یک کالا در یک تیپ و وضعیت: الکتروموتور به kW، پمپ به تیپ/طبقه، الکتروپمپ با برچسب کامل، "
        "قطعه‌های وابسته به تیپ پمپ به تفکیک تیپ — از انبارگردانی و همه‌ی ورود و خروج‌ها.",
        ("warehouse.view", "workflow.view", "report.manage"), "موجودی", stock_fields, load_stock)
    SOURCES["ft_tests"] = Source(
        "ft_tests", "دبی‌سنجی چاه‌ها", "هر ردیف یک آزمایش دبی‌سنجی (بانک دبی‌سنجی).",
        ("refdata.view", "report.manage"), "آزمایش", flow_fields, load_flow)
    SOURCES["pr_months"] = Source(
        "pr_months", "روند تولید (ماهانه)", "هر ردیف یک چاه در یک ماه: تولید، کارکرد، دبی متوسط و فشار.",
        ("refdata.view", "report.manage"), "ماه", prod_fields, load_prod)
    SOURCES["vm_insp"] = Source(
        "vm_insp", "ویدئومتری چاه‌ها", "هر ردیف یک بازدید ویدئومتری: عمق، سطح ایستابی و ایرادات جدار.",
        ("refdata.view", "report.manage"), "بازدید", video_fields, load_video)
    SOURCES["fr_records"] = Source(
        "fr_records", "سوابق سنجش دبی", "هر ردیف یک سنجش دبی چاه (بانک سوابق سنجش دبی): سطوح، آبدهی و فشار شبکه، "
        "توان و راندمان.", ("refdata.view", "report.manage"), "سنجش", frec_fields, load_frec)
