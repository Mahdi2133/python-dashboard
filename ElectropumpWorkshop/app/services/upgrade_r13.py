"""One-time changes to the forms an existing database was configured with.

The admin builds the forms in فرم‌ساز, so the program never rewrites them on
its own — except here, once per database, for the changes the workshop asked
for in this release. Each step looks for the form exactly as the previous
release left it (by section code, field name and the formula it had) and
leaves anything the admin has changed since alone. A fresh database, which
has none of these forms, is untouched. The steps:

* stage 1 of the pull process reads «اعلام خرابی مشاهده شده از سمت بهره بردار»;
* the workshop's pump test (هد، دبی، جریان — ۵ نقطه) becomes five point
  sections of one repeatable group, point 1 shown and the rest opened with «➕»;
* the well-efficiency charts draw the efficiency curve 100·b / (b + a·Q)
  with its equation, and the efficiency points only where b > 0 and a ≥ 0;
* the equipment brought to the warehouse at the pull stage is the motor and
  pump just pulled: two fixed rows whose type comes from the well's
  «تیپ الکتروپمپ فعلی»;
* the stage counts are picked from the pump catalogue for their pump type;
* flow-test and production pressures reach metre fields in metres.
"""
from __future__ import annotations

import json
import logging

from ..extensions import db

log = logging.getLogger(__name__)

KEY = "r13_forms_v1"

OLD_STAGE_TITLE = "اعلام علت خرابی"
NEW_STAGE_TITLE = "اعلام خرابی مشاهده شده از سمت بهره بردار"


def apply_r13() -> dict:
    from ..models import AppMeta
    if AppMeta.get(KEY):
        return {}
    done = {}
    for name, step in (("stage_title", _rename_stage), ("pump_test_points", _split_pump_test),
                       ("efficiency", _efficiency), ("pull_rows", _pull_rows),
                       ("catalogue_stages", _catalogue_stages), ("pressure_units", _pressure_units)):
        try:
            done[name] = step()
            db.session.commit()
        except Exception:  # noqa: BLE001 — one step failing leaves the others in
            db.session.rollback()
            log.exception("R13 form change «%s» failed", name)
            done[name] = "failed"
    AppMeta.set(KEY, "done")
    db.session.commit()
    log.info("R13 form changes: %s", done)
    return done


# ── 1. the center's first stage ─────────────────────────────────────────────
def _rename_stage():
    from ..models import WorkflowStage
    n = 0
    for st in WorkflowStage.query.filter_by(title=OLD_STAGE_TITLE).all():
        st.title = NEW_STAGE_TITLE
        n += 1
    return n


# ── 2. the workshop pump test: five points, one shown ───────────────────────
def _split_pump_test():
    from ..models import FormField, FormSection, WorkflowStageItem
    sec = FormSection.query.filter_by(code="wk_test").first()
    if sec is None or FormSection.query.filter_by(code="wk_test_p1").first() is not None:
        return 0
    fields = {f.field_name: f for f in sec.fields}
    if "wt_h1" not in fields or "wt_q1" not in fields:
        return 0
    per_point = ["wt_h{n}", "wt_q{n}", "wt_i1_{n}", "wt_i2_{n}", "wt_i3_{n}",
                 "wt_iavg{n}", "wt_pe{n}", "wt_ph{n}", "wt_eff{n}"]
    made = []
    for n in range(1, 6):
        point = FormSection(code=f"wk_test_p{n}",
                            title=f"آزمایش الکتروپمپ — نقطه {n} (هد، دبی و جریان)",
                            icon=sec.icon, columns=5, full_width=True,
                            sort_order=sec.sort_order or 0, is_active=True,
                            show_on_entry=sec.show_on_entry, collapse_formulas=True,
                            repeat_group="wk_test_points",
                            description="نقطه‌های بعدی با «➕ افزودن» باز می‌شوند.")
        db.session.add(point)
        db.session.flush()
        for k, pattern in enumerate(per_point):
            f = fields.get(pattern.format(n=n))
            if f is not None:
                f.section_id = point.id
                f.sort_order = k + 1
        made.append(point)
    # what stays is the chart over all the points
    sec.title = "آزمایش الکتروپمپ — نمودار هد–دبی و راندمان"
    sec.columns = 3
    sec.sort_order = (sec.sort_order or 0) + 1
    # every stage showing the test shows the points, in place, before the chart
    for item in WorkflowStageItem.query.filter_by(section_id=sec.id).all():
        items = sorted(WorkflowStageItem.query.filter_by(stage_id=item.stage_id).all(),
                       key=lambda i: (i.sort_order, i.id))
        new = []
        for it in items:
            if it.id == item.id:
                for point in made:
                    new.append(WorkflowStageItem(
                        stage_id=item.stage_id, section_id=point.id, applies_to=item.applies_to,
                        is_optional=True, is_read_only=item.is_read_only))
            new.append(it)
        for k, it in enumerate(new):
            it.sort_order = k
            db.session.add(it)
    return len(made)


# ── 3. efficiency: the curve, its equation, and points only where it holds ──
_EFF_NOTE = ("منحنی راندمان رسم نشد: ضریب افت سفره (b) مثبت نیست — با این نقاط، افت سفره منفی "
             "به دست می‌آید. سطح ایستایی و سطوح پویایی نقاط را بررسی کنید (حداقل دو نقطه لازم است).")


def _efficiency():
    from ..models import FormField
    changed = 0
    for p in ("fc", "wr"):
        for n in range(1, 6):
            f = FormField.query.filter_by(field_name=f"{p}_eff{n}").first()
            old = (f"IF([{p}_q{n}] > 0, IF([{p}_calcloss{n}] <> 0, "
                   f"[{p}_aqloss{n}] / [{p}_calcloss{n}], 1))")
            if f is not None and (f.formula or "").strip() == old:
                f.formula = (f"IF(AND([{p}_q{n}] > 0, [{p}_b] > 0, [{p}_a] >= 0, [{p}_calcloss{n}] > 0), "
                             f"[{p}_aqloss{n}] / [{p}_calcloss{n}])")
                changed += 1
        chart = FormField.query.filter_by(field_name=f"{p}_chart").first()
        if chart is None:
            continue
        try:
            cfg = json.loads(chart.chart_config or "{}")
        except ValueError:
            continue
        for sr in cfg.get("series") or []:
            ys = sr.get("y") or []
            if not ys or not str(ys[0]).startswith(f"{p}_eff") or sr.get("curve"):
                continue
            sr.pop("start", None)
            sr.pop("connect", None)
            sr["scale"] = 100
            sr["curve"] = {"y": f"100 * [{p}_b] / ([{p}_b] + [{p}_a] * [x])",
                           "require": f"AND([{p}_b] > 0, [{p}_a] >= 0)",
                           "note": _EFF_NOTE, "eq_label": "معادله‌ی راندمان"}
            changed += 1
        chart.chart_config = json.dumps(cfg, ensure_ascii=False)
    return changed


# ── 4. the pull stage: the motor and the pump that came out of the well ─────
PULL_PRESET = [
    {"item_code": "EQ-01",
     "spec": 'IF(LEN(COALESCE(EPPART([Electro_tip], "motor"), [motor_prev])) > 0, '
             'CONCAT(COALESCE(EPPART([Electro_tip], "motor"), [motor_prev]), " kW"))',
     "qty": 1},
    {"item_code": "EQ-02",
     "spec": 'COALESCE(EPPART([Electro_tip], "pump"), EPUMP([pump_prev], [pump_prev_stages]))',
     "qty": 1},
]


def _pull_rows():
    from ..models import FormField
    f = FormField.query.filter_by(field_name="wh_pull_items", field_type="wh_lines").first()
    if f is None:
        return 0
    try:
        cfg = json.loads(f.wh_config or "{}")
    except ValueError:
        return 0
    if cfg.get("preset") or cfg.get("mode") == "parts":
        return 0
    from ..warehouse.models import WhItem
    codes = {i.code for i in WhItem.query.filter(WhItem.code.in_(["EQ-01", "EQ-02"])).all()}
    preset = [p for p in PULL_PRESET if p["item_code"] in codes]
    if not preset:
        return 0
    cfg["preset"], cfg["preset_lock"] = preset, True
    f.wh_config = json.dumps(cfg, ensure_ascii=False)
    # the old line asked for the type to be typed in; it now comes by itself
    if not f.help_text or "بنویسید" in f.help_text:
        f.help_text = ("الکتروموتور و پمپی که از چاه کشیده شد؛ تیپ از «تیپ الکتروپمپ فعلی» "
                       "خوانده می‌شود — وضعیت و پلاک را مشخص کنید.")
    return len(preset)


# ── 5. stage counts from the catalogue, with their pump type ────────────────
CATALOGUE_STAGES = {"pump_stages": "pump_curr", "pump_prev_stages": "pump_prev",
                    "no_ste_2": "am_pump"}


def _catalogue_stages():
    from ..models import FormField
    n = 0
    for stages, type_field in CATALOGUE_STAGES.items():
        f = FormField.query.filter_by(field_name=stages).first()
        t = FormField.query.filter_by(field_name=type_field).first()
        if f is None or t is None or f.stages_of:
            continue
        f.stages_of = type_field
        n += 1
    return n


# ── 6. pressures in metres where the field is in metres ─────────────────────
PRESSURE_PREFILL = {
    "fail_flowdrop_p04": ("@ref:pr.avg_pressure_12", "@ref:pr.avg_pressure_12_m", " (m)"),
}


def _pressure_units():
    from ..models import FormField
    n = 0
    for name, (old, new, unit) in PRESSURE_PREFILL.items():
        f = FormField.query.filter_by(field_name=name).first()
        if f is not None and f.prefill_from == old:
            f.prefill_from = new
            if unit and "(" not in (f.label or ""):
                f.label = f"{f.label}{unit}"
            n += 1
    for k in range(1, 6):
        f = FormField.query.filter_by(field_name=f"fc_press{k}").first()
        if f is not None and f.prefill_from == f"@ref:ft.press{k}":
            f.prefill_from = f"@ref:ft.press{k}_m"
            if "(" not in (f.label or ""):
                f.label = f"{f.label} (m)"
            n += 1
    return n
