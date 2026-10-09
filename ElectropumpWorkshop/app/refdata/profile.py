"""What the reference databases know about one well, ready to fill a form.

``well_profile(well_id)`` gathers the latest flow test, the production trend
and the latest camera inspection of a register well; ``CATALOGUE`` lists every
value a form field can be told to start from («@ref:<key>» in فرم‌ساز), with
its source and unit; ``ref_value`` fits one of them to the field it fills.

The «best.*» values weigh the sources against each other by date: the well
depth and the static level are the most recent measurement, wherever it was
taken; the electropump in the well is the most recent install known to the
system, the production register or a flow test — written «384/10+73.5».
"""
from __future__ import annotations

import json
import re

from ..extensions import db
from ..services.epump import electropump_label, fmt_num
from .textnorm import jdate_num, name_key, norm_text

# key → (label, source title, unit)
CATALOGUE = {}


def _add(source, title, items):
    for key, label, unit in items:
        CATALOGUE[f"{source}.{key}"] = (label, title, unit)


_add("best", "بهترین مقدار (ترکیب بانک‌ها)", [
    ("electropump", "تیپ الکتروپمپ فعلی چاه (384/10+73.5)", ""),
    ("pump_type", "تیپ پمپ فعلی چاه", ""),
    ("pump_stages", "طبقات پمپ فعلی چاه", ""),
    ("motor_kw", "توان موتور فعلی چاه", "kW"),
    ("well_depth", "عمق چاه (آخرین اندازه‌گیری)", "m"),
    ("static_level", "سطح ایستابی (آخرین اندازه‌گیری)", "m"),
    ("install_depth", "عمق نصب (آخرین دبی‌سنجی)", "m"),
    ("dynamic_level", "سطح دینامیک در فشار شبکه (آخرین دبی‌سنجی)", "m"),
    ("operating_flow", "دبی بهره‌برداری (روند تولید، یا دبی‌سنجی)", "l/s"),
    ("last_install_date", "تاریخ آخرین نصب الکتروپمپ", ""),
])
_add("ft", "دبی‌سنجی (آخرین آزمایش)", [
    ("test_date", "تاریخ آخرین دبی‌سنجی", ""),
    ("electropump", "تیپ الکتروپمپ در دبی‌سنجی", ""),
    ("well_depth", "عمق چاه", "m"),
    ("install_depth", "عمق نصب", "m"),
    ("prev_install_depth", "عمق نصب قبلی", "m"),
    ("static_level", "سطح ایستایی اندازه‌گیری‌شده", "m"),
    ("prev_static", "سطح ایستایی قبلی", "m"),
    ("dynamic_level", "سطح دینامیک در فشار شبکه", "m"),
    ("net_flow", "آبدهی در فشار شبکه", "l/s"),
    ("net_pressure", "فشار شبکه", "atm"),
    ("net_pressure_m", "فشار شبکه (atm×10)", "m"),
    ("net_head", "هد در فشار شبکه", "m"),
    ("net_amps", "آمپر در فشار شبکه", "A"),
    ("design_flow", "دبی طراحی", "l/s"),
    ("discharge_pipe", "قطر لوله آبده", "inch"),
    ("casing", "قطر لوله جدار", "inch"),
    ("drill_year", "سال حفر", ""),
    ("well_type", "نوع چاه (سیمانته/غیرسیمانته)", ""),
    ("last_install_date", "تاریخ آخرین نصب", ""),
    ("starter", "سیستم راه‌انداز", ""),
    ("allowed_current", "جریان مجاز", "A"),
    ("efficiency", "راندمان در فشار شبکه", "%"),
    ("energy_intensity", "شدت انرژی", "kWh/m³"),
    ("cos_phi", "ضریب قدرت", ""),
    ("water_change", "تغییر ستون آب به ازای دبی", "m/(l/s)"),
    ("zone", "پهنه", ""),
    ("network_type", "نوع شبکه", ""),
    ("well_class", "کلاسه چاه", ""),
    ("pull_reason", "علت کشیدن پمپ (فرم دبی‌سنجی)", ""),
    ("last_rehab_date", "تاریخ آخرین بهسازی", ""),
    ("meter_status", "وضعیت کنتور", ""),
    ("expert_opinion", "نظر کارشناس دبی‌سنجی", ""),
])
for _n in range(1, 6):
    _add("ft", "دبی‌سنجی (آخرین آزمایش)", [
        (f"q{_n}", f"کارکرد {_n} — آبدهی", "l/s"),
        (f"dyn{_n}", f"کارکرد {_n} — سطح پویایی", "m"),
        (f"press{_n}", f"کارکرد {_n} — فشار", "atm"),
        (f"head{_n}", f"کارکرد {_n} — هد", "m"),
        (f"amps{_n}", f"کارکرد {_n} — آمپر", "A"),
    ])
_add("pr", "روند تولید", [
    ("last_flow", "آخرین دبی متوسط بهره‌برداری", "l/s"),
    ("last_flow_month", "ماه آخرین دبی بهره‌برداری", ""),
    ("avg_flow_12", "میانگین دبی ۱۲ ماه اخیر", "l/s"),
    ("last_pressure", "آخرین فشار ماهانه", ""),
    ("avg_pressure_12", "میانگین فشار ۱۲ ماه اخیر", ""),
    ("last_production", "تولید آخرین ماه", "m³"),
    ("last_hours", "کارکرد آخرین ماه", "ساعت"),
    ("electropump", "تیپ الکتروپمپ در روند تولید", ""),
    ("pump_install_date", "تاریخ نصب الکتروپمپ", ""),
    ("last_rehab_date", "تاریخ آخرین بهسازی", ""),
    ("last_rehab_failure", "خرابی مشاهده‌شده در آخرین بهسازی", ""),
    ("low_run_reason", "علت کارکرد کمتر از انتظار", ""),
    ("meter_status", "آخرین وضعیت کنتور", ""),
    ("zone", "پهنه", ""),
    ("urban_rural", "شهری/روستایی", ""),
    ("facility_code", "کد تاسیس", ""),
])
_add("vm", "ویدئومتری (آخرین بازدید)", [
    ("date", "تاریخ آخرین ویدئومتری", ""),
    ("depth", "عمق چاه (ویدئومتری)", "m"),
    ("static_level", "سطح ایستابی (ویدئومتری)", "m"),
    ("screen_start", "عمق شروع مشبک", "m"),
    ("defects", "خلاصه ایرادات جدار", ""),
    ("notes", "توضیحات ویدئومتری", ""),
])


def catalogue_options():
    """For فرم‌ساز: every reference value, grouped by source."""
    return [{"value": "@ref:" + key, "label": f"{label}" + (f" ({unit})" if unit else ""),
             "group": title}
            for key, (label, title, unit) in CATALOGUE.items()]


# ── gathering ────────────────────────────────────────────────────────────────
def _latest_flowtest(well_id):
    from .models import FlowTest
    return (FlowTest.query.filter_by(main_well_id=well_id)
            .order_by(FlowTest.test_date_num.desc().nullslast(), FlowTest.id.desc()).first())


def _prod_well(well_id):
    from .models import ProdWell
    return (ProdWell.query.filter_by(main_well_id=well_id)
            .order_by(ProdWell.snapshot_year.desc().nullslast()).first())


def _latest_video(well_id):
    from .models import VideoInspection
    return (VideoInspection.query.filter_by(main_well_id=well_id)
            .order_by(VideoInspection.insp_date_num.desc().nullslast(),
                      VideoInspection.id.desc()).first())


def _system_pump(well_id):
    """The pump the system itself last recorded in this well, with its date."""
    from ..models import LookupItem, Record
    from ..services.jalali import to_jalali_str
    rec = (Record.query.filter(Record.well_id == well_id, Record.is_active.is_(True),
                               Record.pump_curr_id.isnot(None))
           .order_by(Record.op_date.desc().nullslast(), Record.id.desc()).first())
    if rec is None:
        return None
    pump = db.session.get(LookupItem, rec.pump_curr_id)
    motor = db.session.get(LookupItem, rec.motor_curr_id) if rec.motor_curr_id else None
    date = to_jalali_str(rec.op_date) if rec.op_date else None
    return {"pump_type": pump.value if pump else None, "pump_stages": rec.pump_stages,
            "motor_kw": motor.value if motor else None, "date": date}


def _months(pw):
    rows = sorted(pw.months, key=lambda m: (m.year, m.month))
    return rows


def well_profile(well_id) -> dict:
    """{values: {key: value}, sources: [...], flowtest/production/video summaries}."""
    if not well_id:
        return {"values": {}, "sources": []}
    values, sources = {}, []
    ft = _latest_flowtest(well_id)
    pw = _prod_well(well_id)
    vm = _latest_video(well_id)

    if ft is not None:
        from .models import FlowTest
        count = FlowTest.query.filter_by(main_well_id=well_id).count()
        sources.append({"key": "flowtest", "title": "دبی‌سنجی", "date": ft.test_date,
                        "count": count})
        v = values
        v["ft.test_date"] = ft.test_date
        v["ft.electropump"] = (electropump_label(ft.pump_type, ft.pump_stages, ft.motor_kw)
                               or ft.pump_label)
        for k in ("well_depth", "install_depth", "prev_install_depth", "static_level",
                  "prev_static", "design_flow", "discharge_pipe", "casing", "drill_year",
                  "well_type", "last_install_date", "starter", "allowed_current",
                  "efficiency", "energy_intensity", "cos_phi", "water_change", "zone",
                  "network_type", "well_class", "pull_reason", "last_rehab_date",
                  "meter_status", "expert_opinion"):
            v[f"ft.{k}"] = getattr(ft, k)
        net = next((p for p in ft.points if p.at_network), None)
        v["ft.net_flow"] = ft.net_flow if ft.net_flow is not None else (net.flow if net else None)
        v["ft.net_pressure"] = ft.net_pressure if ft.net_pressure is not None else (
            net.pressure if net else None)
        v["ft.net_pressure_m"] = (round(v["ft.net_pressure"] * 10, 2)
                                  if v["ft.net_pressure"] is not None else None)
        v["ft.dynamic_level"] = net.dynamic_level if net else None
        v["ft.net_head"] = net.head if net else None
        v["ft.net_amps"] = net.amps if net else None
        for p in ft.points:
            n = p.point_no
            if 1 <= n <= 5:
                v[f"ft.q{n}"], v[f"ft.dyn{n}"] = p.flow, p.dynamic_level
                v[f"ft.press{n}"], v[f"ft.head{n}"], v[f"ft.amps{n}"] = p.pressure, p.head, p.amps

    if pw is not None:
        months = _months(pw)
        flows = [m for m in months if m.avg_flow not in (None, 0)]
        last = flows[-1] if flows else None
        recent = flows[-12:]
        press = [m for m in months if m.pressure not in (None, 0)][-12:]
        values.update({
            "pr.facility_code": pw.facility_code,
            "pr.last_flow": last.avg_flow if last else None,
            "pr.last_flow_month": f"{last.year}/{last.month:02d}" if last else None,
            "pr.avg_flow_12": (round(sum(m.avg_flow for m in recent) / len(recent), 2)
                               if recent else None),
            "pr.last_pressure": press[-1].pressure if press else None,
            "pr.avg_pressure_12": (round(sum(m.pressure for m in press) / len(press), 2)
                                   if press else None),
            "pr.last_production": last.production if last else None,
            "pr.last_hours": last.hours if last else None,
            "pr.electropump": electropump_label(pw.pump_type, pw.pump_stages, pw.motor_kw),
            "pr.pump_install_date": pw.pump_install_date,
            "pr.last_rehab_date": pw.last_rehab_date,
            "pr.last_rehab_failure": pw.last_rehab_failure,
            "pr.low_run_reason": pw.low_run_reason,
            "pr.meter_status": pw.meter_status,
            "pr.zone": pw.zone,
            "pr.urban_rural": pw.urban_rural,
        })
        sources.append({"key": "production", "title": "روند تولید",
                        "date": values["pr.last_flow_month"], "count": len(months)})

    if vm is not None:
        from .models import VideoInspection
        defects = []
        for key, title in (("repair", "ترمیم"), ("tear", "پارگی"), ("change", "تغییر جدار"),
                           ("clog", "گرفتگی مشبک")):
            items = json.loads(getattr(vm, key) or "[]")
            if items:
                defects.append(f"{title}: " + "، ".join(
                    f"{fmt_num(i.get('from'))}–{fmt_num(i.get('to'))}"
                    + (f" ({i['sev']})" if i.get("sev") else "") for i in items))
        values.update({
            "vm.date": vm.insp_date, "vm.depth": vm.depth, "vm.static_level": vm.static_level,
            "vm.screen_start": vm.screen_start, "vm.notes": vm.notes,
            "vm.defects": " | ".join(defects) or None,
        })
        sources.append({"key": "videometry", "title": "ویدئومتری", "date": vm.insp_date,
                        "count": VideoInspection.query.filter_by(main_well_id=well_id).count()})

    _best(values, well_id)
    return {"values": {k: v for k, v in values.items() if v not in (None, "")},
            "sources": sources}


def _newest(*pairs):
    """The value of the most recently dated (value, date) pair."""
    best, best_n = None, -1
    for value, date in pairs:
        if value in (None, ""):
            continue
        n = jdate_num(date) or 0
        if n > best_n:
            best, best_n = value, n
    return best


def _measured(well_id, attr):
    """(value, date) of the newest flow test that actually recorded ``attr``."""
    from .models import FlowTest
    col = getattr(FlowTest, attr)
    row = (FlowTest.query.filter(FlowTest.main_well_id == well_id, col.isnot(None))
           .order_by(FlowTest.test_date_num.desc().nullslast(), FlowTest.id.desc()).first())
    return (getattr(row, attr), row.test_date) if row is not None else (None, None)


def _best(v, well_id):
    v["best.well_depth"] = _newest((v.get("vm.depth"), v.get("vm.date")),
                                   _measured(well_id, "well_depth"))
    v["best.static_level"] = _newest((v.get("vm.static_level"), v.get("vm.date")),
                                     _measured(well_id, "static_level"))
    v["best.install_depth"] = v.get("ft.install_depth") or _measured(well_id, "install_depth")[0]
    v["best.dynamic_level"] = v.get("ft.dynamic_level")
    v["best.operating_flow"] = v.get("pr.last_flow") or v.get("ft.net_flow")
    # the electropump: the newest install the system, production or a test knows of
    from .models import FlowTest  # noqa: F401
    cands = []
    sysp = _system_pump(well_id)
    if sysp and sysp.get("pump_type"):
        cands.append((jdate_num(sysp["date"]) or 0, 3,
                      (sysp["pump_type"], sysp["pump_stages"], sysp["motor_kw"]), sysp["date"]))
    from .models import ProdWell
    pw = _prod_well(well_id)
    if pw is not None and pw.pump_type:
        cands.append((jdate_num(pw.pump_install_date) or (pw.snapshot_year or 0) * 10000, 2,
                      (pw.pump_type, pw.pump_stages, pw.motor_kw), pw.pump_install_date))
    ft = _latest_flowtest(well_id)
    if ft is not None and ft.pump_type:
        cands.append((jdate_num(ft.last_install_date) or jdate_num(ft.test_date) or 0, 1,
                      (ft.pump_type, ft.pump_stages, ft.motor_kw), ft.last_install_date))
    if cands:
        cands.sort(key=lambda c: (c[0], c[1]), reverse=True)
        (t, s, m), since = cands[0][2], cands[0][3]
        v["best.electropump"] = electropump_label(t, s, m)
        v["best.pump_type"], v["best.pump_stages"], v["best.motor_kw"] = t, s, m
        v["best.last_install_date"] = since


# ── fitting a value to a field ───────────────────────────────────────────────
_SYNONYMS = {"soft": "سافت", "drive": "درایو", "star": "ستاره", "dol": "تک ضرب"}


def fit_choice(value, choices):
    """The stored option a reference value means, or None if none fits."""
    if value in (None, ""):
        return None
    text = norm_text(str(value)).lower()
    for en, fa in _SYNONYMS.items():
        text = text.replace(en, fa)
    key = name_key(fmt_num(value) if isinstance(value, (int, float)) else text)
    keys = {c: name_key(fmt_num(c)) for c in choices}
    for c, k in keys.items():
        if k == key:
            return c
    if re.fullmatch(r"[\d.]+", key):           # numbers match exactly, never 7 → 7.5
        return None
    for c in choices:                           # «سافت» → «سافت/درایو»
        parts = [name_key(p) for p in str(c).split("/") if p.strip()]
        if any(p and (key.startswith(p) or p.startswith(key)) for p in parts):
            return c
    return None
