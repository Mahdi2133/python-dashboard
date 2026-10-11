"""One-time changes for this release, once per database (see upgrade_r13).

Each step looks for the forms and stages as the previous release left them
and leaves alone anything the admin has changed since. The steps:

* the mechanical workshop's three stages run in the workshop's own order —
  «دمونتاژ و انتقال به انبار قطعات», «مونتاژ و برداشت از انبار تجهیزات و
  قطعات», «آزمایش پمپاژ» — and all three are in Kahani's کارتابل together:
  the test no longer waits for this run's assembly, because what it tests is
  an assembled electropump picked from the equipment warehouse (the one this
  run assembled, by default);
* the pumping test says which electropump it is about (a new form at its
  top), and once the test is approved that electropump carries «آزمایش پمپاژ
  انجام شده» — the catalogue comparison follows the model of the one picked;
* the install takes its electropump from the warehouse one by one, by
  plaque, and only one whose pumping test is done can be picked (the server
  refuses the rest as well);
* the test's points 1…5 become one «جدول ردیفی» with a sixth point and «ورود
  از اکسل» (a template to fill and the file read back), and the catalogue
  comparison is laid out the same way, its worked-out fields folded behind
  «ƒ نمایش محاسبات»;
* the disassembly forms list every part of the motor and the pump, like the
  assembly's, the counts typed in place;
* the sample stock's electropumps get plaques (the first one tested).
"""
from __future__ import annotations

import json
import logging
import re

from ..extensions import db

log = logging.getLogger(__name__)

KEY = "r16_workshop_v1"

ROW_LABEL = "نقطه {n}"
UNIT_ITEM = "EQ-03"
TESTED = "tested"
INSTALL_WHEN = "review_action=انتخاب پمپ"

TITLES = {  # R15's title → this release's, only while the admin has not renamed it
    "دمونتاژ و تفکیک قطعات (انبار تجهیزات ← انبار قطعات)": "کارگاه مکانیک — دمونتاژ و انتقال به انبار قطعات",
    "کارگاه مکانیک — مونتاژ (الکتروموتور / پمپ / الکتروپمپ)": "کارگاه مکانیک — مونتاژ و برداشت از انبار تجهیزات و قطعات",
}


def apply_r16() -> dict:
    from ..models import AppMeta
    if AppMeta.get(KEY):
        return {}
    done = {}
    for name, step in (("workshop_order", _workshop_order), ("test_unit", _test_unit),
                       ("test_grid", _test_grid), ("compare_grid", _compare_grid),
                       ("compare_unit", _compare_unit), ("install_units", _install_units),
                       ("disassembly_lists", _disassembly_lists), ("sample_units", _sample_units)):
        try:
            done[name] = step()
            db.session.commit()
        except Exception:  # noqa: BLE001 — one step failing leaves the others in
            db.session.rollback()
            log.exception("R16 change «%s» failed", name)
            done[name] = "failed"
    AppMeta.set(KEY, "done")
    db.session.commit()
    log.info("R16 changes: %s", done)
    return done


# ── helpers ──────────────────────────────────────────────────────────────────
def _field(name):
    from ..models import FormField
    return FormField.query.filter_by(field_name=name).first()


def _section(code):
    from ..models import FormSection
    return FormSection.query.filter_by(code=code).first()


def _stage_with(code):
    from ..models import WorkflowStageItem
    sec = _section(code)
    if sec is None:
        return None
    stages = sorted({i.stage for i in WorkflowStageItem.query.filter_by(section_id=sec.id).all()
                     if i.stage is not None and i.stage.is_active},
                    key=lambda s: (s.workflow_id, s.stage_number))
    return stages[0] if stages else None


def _cfg(field) -> dict:
    try:
        cfg = json.loads(field.wh_config or "{}")
    except ValueError:
        cfg = {}
    return cfg if isinstance(cfg, dict) else {}


# ── 1. دمونتاژ → مونتاژ → آزمایش پمپاژ, all three in the کارتابل ───────────
def _workshop_order():
    dis, asm, test = _stage_with("dm_head"), _stage_with("mt_head"), _stage_with("pumping_test")
    if not (dis and asm and test) or len({dis.workflow_id, asm.workflow_id, test.workflow_id}) != 1:
        return 0
    for stage in (dis, asm):
        if stage.title in TITLES:
            stage.title = TITLES[stage.title]
    workflow = asm.workflow
    trio = [dis.id, asm.id, test.id]
    ordered = sorted(workflow.stages, key=lambda s: s.stage_number)
    first = min(s.stage_number for s in (dis, asm, test))
    ids = []
    for s in ordered:
        if s.id in trio:
            continue
        if s.stage_number > first and trio[0] not in ids:
            ids += trio
        ids.append(s.id)
    if trio[0] not in ids:
        ids += trio
    from .workflow import renumber_stages
    moved = renumber_stages(workflow, ids)
    db.session.flush()
    # the test opens with the assembly (after the expert's review), not after it
    if test.waits_for and str(test.waits_for).strip() == str(asm.stage_number):
        test.waits_for = asm.waits_for
    if test.needs_approval:
        test.reject_to_stage = test.stage_number
    return {"moved": moved, "order": [dis.stage_number, asm.stage_number, test.stage_number]}


# ── 2. which electropump the test is about ──────────────────────────────────
def _test_unit():
    from ..models import FormField, FormSection, WorkflowStageItem
    test = _stage_with("pumping_test")
    if test is None or _field("wt_unit") is not None:
        return 0
    # only where the assembly is a stage of its own that joins an electropump
    # into stock — otherwise there is nothing in the warehouse to pick
    asm, join = _stage_with("mt_head"), _field("wh_build_in_items")
    if asm is None or asm.id == test.id or join is None or not _cfg(join).get("join_into"):
        return 0
    from ..warehouse.models import WhItem
    if WhItem.query.filter_by(code=UNIT_ITEM).first() is None:
        return 0
    top = (db.session.query(db.func.min(FormSection.sort_order)).scalar() or 0)
    sec = _section("wk_test_unit")
    if sec is None:
        sec = FormSection(code="wk_test_unit", title="الکتروپمپ مورد آزمایش (از انبار تجهیزات)", icon="🔖",
                          columns=3, full_width=True, is_active=True, show_on_entry=False,
                          sort_order=top, description=(
                              "الکتروپمپ مونتاژشده‌ای که آزمایش می‌شود از موجودی انبار تجهیزات انتخاب شود "
                              "(پیش‌فرض: همانی که در مونتاژ همین فرایند ساخته شد). با تأیید آزمایش، «آزمایش پمپاژ "
                              "انجام شده» روی همان الکتروپمپ ثبت می‌شود و فقط آن‌وقت برای نصب برداشته می‌شود."))
        db.session.add(sec)
        db.session.flush()
    cfg = {"mode": "mark", "mark": TESTED, "item_code": UNIT_ITEM, "warehouse": "equipment",
           "direction": "in", "reason": "assembled", "variant_field": "wt_unit_model", "required": True,
           "pick_hint": "الکتروپمپ مونتاژشده‌ای که آزمایش می‌شود را از موجودی انبار تجهیزات انتخاب کنید",
           "empty_hint": ("هیچ الکتروپمپ مونتاژشده‌ای در انبار تجهیزات نیست؛ ابتدا مونتاژ «هر دو "
                          "(الکتروپمپ)» را ثبت کنید.")}
    db.session.add(FormField(section_id=sec.id, field_name="wt_unit", field_type="wh_lines",
                             label="الکتروپمپ آزمایش‌شده (پلاک از موجودی انبار)", sort_order=0, col_span=3,
                             wh_config=json.dumps(cfg, ensure_ascii=False), is_active=True,
                             help_text="با تأیید آزمایش توسط کارشناس، تیک «آزمایش پمپاژ انجام شده» این الکتروپمپ می‌خورد."))
    db.session.add(FormField(section_id=sec.id, field_name="wt_unit_model", field_type="text",
                             label="مدل الکتروپمپ آزمایش‌شده", sort_order=1, is_active=True,
                             help_text="با انتخاب الکتروپمپ پر می‌شود (مثلاً 384/10+73.5)."))
    db.session.add(FormField(section_id=sec.id, field_name="wt_unit_type", field_type="formula",
                             label="تیپ پمپ برای مقایسه با کاتالوگ", sort_order=2, is_active=True,
                             formula='COALESCE(EPPART([wt_unit_model], "type"), [pump_curr])', result_type="text"))
    db.session.flush()
    items = sorted(test.items, key=lambda i: (i.sort_order or 0, i.id))
    db.session.add(WorkflowStageItem(stage_id=test.id, section_id=sec.id, applies_to="both",
                                     is_optional=False, is_read_only=False, sort_order=0))
    for k, it in enumerate(items, start=1):
        it.sort_order = k
    return 1


# ── 3. the test's points as one table, with a sixth point ───────────────────
def _row_label(label: str, n: int) -> str:
    """«هد 1 (m)» / «I1 — نقطه 1 (A)» → «نقطه 1 — هد (m)» / «نقطه 1 — I1 (A)»."""
    text = str(label or "")
    if text.startswith(ROW_LABEL.format(n=n)):
        return text
    if re.search(rf"نقطه\s*{n}(?!\d)", text):
        text = re.sub(rf"\s*[—–-]?\s*نقطه\s*{n}(?!\d)\s*[—–-]?\s*", " ", text)
    else:
        text = re.sub(rf"\s{n}(?=\s|\(|$)", "", text, count=1)
    text = " ".join(text.split())
    return f"{ROW_LABEL.format(n=n)} — {text}"


def _next_row_formula(text: str, names: set, n: int) -> str:
    """Point n's formula written for point n+1: «[wt_q5]» → «[wt_q6]» where
    the field has a point-4 sibling too (a point field, not «wt_volt»)."""
    def swap(m):
        ref = m.group(1).strip()
        base = ref[:-len(str(n))] if ref.endswith(str(n)) else None
        if base and f"{base}{n - 1}" in names:
            return f"[{base}{n + 1}]"
        return m.group(0)
    return re.sub(r"\[([^\]]+)\]", swap, text or "")


def _add_row(section, n: int) -> list:
    """Copy the table's row n as row n+1 (fields, labels, formulas)."""
    from ..models import FormField
    from .gridlayout import grid_cells
    fields = sorted([f for f in section.fields], key=lambda f: f.sort_order or 0)
    names = {f.field_name for f in FormField.query.all()}
    cells = grid_cells(section, [f.field_name for f in fields if f.is_active])
    made = []
    for f in fields:
        if f.field_name not in cells or cells[f.field_name][1] != n:
            continue
        key = cells[f.field_name][0]
        new = f"{key}{n + 1}"
        if new in names:
            continue
        clone = FormField(
            section_id=section.id, field_name=new, field_type=f.field_type,
            label=f.label.replace(ROW_LABEL.format(n=n), ROW_LABEL.format(n=n + 1)),
            sort_order=(f.sort_order or 0) + 100, col_span=f.col_span, is_active=True,
            min_value=f.min_value, max_value=f.max_value, step=f.step, help_text=f.help_text,
            placeholder=f.placeholder, result_type=f.result_type, is_required=False,
            formula=_next_row_formula(f.formula, names, n) if f.formula else None)
        db.session.add(clone)
        made.append(new)
    db.session.flush()
    return made


def _extend_lists(added: list, n: int) -> int:
    """Totals and charts over points 1…n take point n+1 in too."""
    from ..models import FormField
    bases = {name[:-len(str(n + 1))] for name in added}
    changed = 0
    for f in FormField.query.all():
        text = f.formula or ""
        new_text = text
        for base in bases:
            a, b, c = f"[{base}{n - 1}]", f"[{base}{n}]", f"[{base}{n + 1}]"
            if a in new_text and b in new_text and c not in new_text and f.field_name != f"{base}{n}":
                new_text = new_text.replace(b, f"{b}, {c}")
        if new_text != text:
            f.formula = new_text
            changed += 1
        if f.field_type == "chart" and f.chart_config:
            try:
                cfg = json.loads(f.chart_config)
            except ValueError:
                continue
            touched = False
            for sr in cfg.get("series") or []:
                for axis in ("x", "y"):
                    seq = sr.get(axis)
                    if not isinstance(seq, list) or not seq:
                        continue
                    last = str(seq[-1])
                    base = last[:-len(str(n))] if last.endswith(str(n)) else None
                    if base in bases and f"{base}{n - 1}" in seq and f"{base}{n + 1}" not in seq:
                        seq.append(f"{base}{n + 1}")
                        touched = True
            if touched:
                f.chart_config = json.dumps(cfg, ensure_ascii=False)
                changed += 1
    return changed


def _as_grid(section, title=None):
    from .gridlayout import grid_cells
    fields = sorted([f for f in section.fields if f.is_active], key=lambda f: f.sort_order or 0)
    cells = grid_cells(section, [f.field_name for f in fields])
    for f in fields:
        if f.field_name in cells:
            f.label = _row_label(f.label, cells[f.field_name][1])
    if title:
        section.title = title
    section.layout = "grid"
    section.grid_label = ROW_LABEL
    section.full_width = True
    section.collapse_formulas = True
    return len(cells)


def _test_grid():
    from ..models import WorkflowStageItem
    base = _section("wk_test_p1")
    if base is None or base.layout == "grid":
        return 0
    parts = [s for s in (_section(f"wk_test_p{n}") for n in range(1, 6)) if s is not None]
    for n, sec in enumerate(parts, start=1):
        for k, f in enumerate(sorted(sec.fields, key=lambda f: f.sort_order or 0)):
            f.section_id = base.id
            f.sort_order = n * 100 + k
    db.session.flush()
    db.session.expire(base, ["fields"])
    others = [s.id for s in parts if s.id != base.id]
    for item in WorkflowStageItem.query.filter(WorkflowStageItem.section_id.in_(others)).all():
        db.session.delete(item)
    for s in parts:
        if s.id != base.id:
            s.is_active = False
    base.repeat_group = None
    base.grid_import = True
    cells = _as_grid(base, "آزمایش الکتروپمپ — جدول نقاط (هد، دبی و جریان)")
    base.description = ("هد، دبی و جریان هر نقطه در یک ردیف (۵ یا ۶ نقطه). «⬆ بارگذاری از اکسل» جدول دستگاه "
                        "آزمایش را خودکار در ردیف‌ها می‌نشاند؛ «⬇ قالب اکسل» قالب خالی همین جدول است. "
                        "ستون‌های محاسبه‌ای با «ƒ نمایش محاسبات» دیده می‌شوند.")
    db.session.flush()
    db.session.expire(base, ["fields"])
    added = _add_row(base, 5)
    lists = _extend_lists(added, 5)
    return {"merged": len(parts), "cells": cells, "point6": len(added), "lists": lists}


def _compare_grid():
    sec = _section("wk_compare")
    if sec is None or sec.layout == "grid":
        return 0
    cells = _as_grid(sec)
    db.session.flush()
    db.session.expire(sec, ["fields"])
    added = _add_row(sec, 5) if _field("wt_h6") is not None else []
    lists = _extend_lists(added, 5)
    return {"cells": cells, "point6": len(added), "lists": lists}


# ── 4. the comparison follows the electropump actually tested ───────────────
def _compare_unit():
    if _field("wt_unit_type") is None:
        return 0
    sec = _section("wk_compare")
    changed = 0
    if sec is not None:
        for f in sec.fields:
            if f.formula and "[pump_curr]" in f.formula:
                f.formula = f.formula.replace("[pump_curr]", "[wt_unit_type]")
                changed += 1
            if f.field_type == "chart" and f.chart_config:
                try:
                    cfg = json.loads(f.chart_config)
                except ValueError:
                    continue
                for sr in cfg.get("series") or []:
                    cat = sr.get("catalogue")
                    if isinstance(cat, dict) and cat.get("type") == "pump_curr":
                        cat["type"] = "wt_unit_type"
                        changed += 1
                f.chart_config = json.dumps(cfg, ensure_ascii=False)
    stages = _field("wk_cat_stages")
    if stages is not None and stages.formula and "[pump_stages]" in stages.formula \
            and "wt_unit_model" not in stages.formula:
        stages.formula = stages.formula.replace(
            "[pump_stages]", 'COALESCE(EPPART([wt_unit_model], "stages"), [pump_stages])')
        changed += 1
    return changed


# ── 5. the install takes a tested electropump, one by one ───────────────────
def _install_units():
    f = _field("wh_install_out_items")
    if f is None:
        return 0
    cfg = _cfg(f)
    if cfg.get("units"):
        return 0
    cfg.update({"mode": "rows", "warehouse": "equipment", "direction": "out", "reason": "install",
                "kinds": ["equipment"], "spec": True, "serial": True, "condition": False,
                "default_condition": "assembled", "units": True, "require_mark": TESTED,
                "preset": [{"item_code": UNIT_ITEM, "qty": 1}], "preset_lock": True,
                "preset_hint": ("الکتروپمپ نصبی را از فهرست موجودی انبار تجهیزات (الکتروپمپ‌های مونتاژشده‌ی کارگاه "
                                "مکانیک) انتخاب کنید؛ فقط الکتروپمپی که تیک «آزمایش پمپاژ انجام شده» دارد "
                                "قابل انتخاب است."),
                "empty_hint": ("هیچ الکتروپمپی با آزمایش پمپاژ انجام‌شده در انبار تجهیزات نیست؛ تا آزمایش پمپاژ "
                               "کارگاه مکانیک انجام و تأیید نشود، نصب ممکن نیست.")})
    cfg.pop("conditions", None)
    f.wh_config = json.dumps(cfg, ensure_ascii=False)
    f.label = "الکتروپمپ برداشتی از انبار تجهیزات برای نصب (فقط آزمایش‌شده)"
    sec = f.section
    if sec is not None and not (sec.visible_when or "").strip():
        # a relocation brings its electropump from another well, not the warehouse
        sec.visible_when = INSTALL_WHEN
    return 1


# ── 6. the disassembly lists every part too, counts typed in place ─────────
def _disassembly_lists():
    n = 0
    for name in ("dm_motor_parts_f", "dm_pump_parts_f"):
        f = _field(name)
        if f is None:
            continue
        cfg = _cfg(f)
        if cfg.get("mode") != "parts" or cfg.get("list_all"):
            continue
        cfg["list_all"] = True
        f.wh_config = json.dumps(cfg, ensure_ascii=False)
        n += 1
    return n


def _sample_units():
    from ..warehouse.service import sample_units_upgrade
    return sample_units_upgrade()
