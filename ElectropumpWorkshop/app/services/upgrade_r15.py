"""One-time changes for this release, once per database (see upgrade_r13).

Each step looks for the forms and stages as the previous release left them
and leaves alone anything the admin has changed since. The steps:

* «اطلاعات چاه از بانک‌های اطلاعاتی» is not shown at the centre's stages,
  at the pull and at the install (a per-stage switch in فرایندساز);
* the expert's کارکرد 1…5 sections («محاسبات دبی‌سنجی» and «آزمایش پمپاژ
  با دور موتور») become one «جدول ردیفی» each — one row per کارکرد, the
  typed columns only, the worked-out ones folded;
* the drawdowns of «محاسبات دبی‌سنجی» are taken from the static level of
  the same flow test (a new field, «سطح ایستایی در همان دبی‌سنجی»), not
  from the well's static level of another day — with videometry's level,
  every drawdown carried a constant and a or b came out negative;
* pump and motor types are picked from a dropdown with a search box;
* the pull counts its 6, 12 and 18 metre branches (the metres pulled are
  their sum), says whether they were worn or new, and hands the motor and
  pump to the equipment warehouse with their plaques from the register and
  no «وضعیت»;
* the warehouse counts stock by type, the pump parts that go by the stage
  count (بوش، پروانه، طبقه) or one per pump (شافت، سوپاپ) are marked, and a
  sample stock count and register types are filled in until the real ones
  are imported;
* the mechanical workshop's stage is split: «مونتاژ» (motor, pump or both —
  the whole parts list, total / new / repaired, checked against the stock;
  both together go to the equipment warehouse as one electropump),
  «آزمایش پمپاژ و تحویل» (the test, Amin's approval, the install process),
  and «دمونتاژ» after them — the equipment taken apart leaving the
  equipment warehouse.
"""
from __future__ import annotations

import json
import logging

from ..extensions import db

log = logging.getLogger(__name__)

KEY = "r15_workshop_v1"

KIND_FIELD = "mt_kind"
KIND_MOTOR, KIND_PUMP, KIND_BOTH = "الکتروموتور", "پمپ", "هر دو (الکتروپمپ)"
WHEN_MOTOR = f"{KIND_FIELD}={KIND_MOTOR}|{KIND_BOTH}"
WHEN_PUMP = f"{KIND_FIELD}={KIND_PUMP}|{KIND_BOTH}"
WHEN_BOTH = f"{KIND_FIELD}={KIND_BOTH}"


def apply_r15() -> dict:
    from ..models import AppMeta
    if AppMeta.get(KEY):
        return {}
    done = {}
    for name, step in (("refdata_box", _refdata_box), ("points_grid", _points_grid),
                       ("flowtest_static", _flowtest_static), ("type_dropdowns", _type_dropdowns),
                       ("pull_pipes", _pull_pipes), ("pull_rows", _pull_rows),
                       ("inventory", _inventory), ("workshop_stages", _workshop_stages)):
        try:
            done[name] = step()
            db.session.commit()
        except Exception:  # noqa: BLE001 — one step failing leaves the others in
            db.session.rollback()
            log.exception("R15 change «%s» failed", name)
            done[name] = "failed"
    AppMeta.set(KEY, "done")
    db.session.commit()
    log.info("R15 changes: %s", done)
    return done


# ── helpers ──────────────────────────────────────────────────────────────────
def _field(name):
    from ..models import FormField
    return FormField.query.filter_by(field_name=name).first()


def _section(code):
    from ..models import FormSection
    return FormSection.query.filter_by(code=code).first()


def _new_field(section, name, label, ftype, order, **kw):
    """A field the release adds — or the one already there under that name."""
    from ..models import FormField, FormFieldOption
    f = _field(name)
    if f is not None:
        return f, False
    opts = kw.pop("options", None)
    f = FormField(section_id=section.id, field_name=name, label=label, field_type=ftype,
                  sort_order=order, **kw)
    db.session.add(f)
    db.session.flush()
    for k, value in enumerate(opts or []):
        db.session.add(FormFieldOption(field_id=f.id, value=value, label=value, sort_order=k))
    return f, True


def _stage_with(code):
    """The stage that carries the form with this code (the first, by number)."""
    from ..models import WorkflowStageItem
    sec = _section(code)
    if sec is None:
        return None
    items = WorkflowStageItem.query.filter_by(section_id=sec.id).all()
    stages = sorted({i.stage for i in items if i.stage is not None},
                    key=lambda s: (s.workflow_id, s.stage_number))
    return stages[0] if stages else None


# ── 1. the reference box where the process builder now says so ──────────────
def _refdata_box():
    from ..models import WorkflowStage
    n = 0
    for stage in WorkflowStage.query.all():
        codes = {i.section.code for i in stage.items if i.section is not None}
        if stage.route_by_center or codes & {"pl_status", "in_install"}:
            if stage.show_refdata is not False:
                stage.show_refdata = False
                n += 1
    return n


# ── 2. کارکرد 1…5 as one table ──────────────────────────────────────────────
GRIDS = (("ps_fc_p", "محاسبات دبی‌سنجی — جدول کارکردها"),
         ("wr_p", "آزمایش پمپاژ با دور موتور — جدول کارکردها"))


def _points_grid():
    from ..models import WorkflowStageItem
    merged = 0
    for prefix, title in GRIDS:
        base = _section(f"{prefix}1")
        if base is None or base.layout == "grid":
            continue
        parts = [s for s in (_section(f"{prefix}{n}") for n in range(1, 6)) if s is not None]
        if len(parts) < 2:
            continue
        for n, sec in enumerate(parts, start=1):
            for k, f in enumerate(sorted(sec.fields, key=lambda f: f.sort_order or 0)):
                f.section_id = base.id
                f.sort_order = n * 100 + k
                if "کارکرد" not in (f.label or ""):
                    f.label = f"کارکرد {n} — {f.label}"
        base.title = title
        base.layout = "grid"
        base.grid_label = "کارکرد {n}"
        base.full_width = True
        base.collapse_formulas = True
        base.description = ("آبدهی، سطح پویایی و فشار هر کارکرد در یک ردیف؛ ستون‌های محاسبه‌ای با "
                            "«ƒ نمایش محاسبات» دیده می‌شوند.")
        # the other four leave the stages; their per-field settings join the table's
        others = [s.id for s in parts if s.id != base.id]
        for item in WorkflowStageItem.query.filter(WorkflowStageItem.section_id.in_(others)).all():
            keep = WorkflowStageItem.query.filter_by(stage_id=item.stage_id, section_id=base.id).first()
            if keep is not None:
                for attr in ("locked_fields", "hidden_fields"):
                    mine = _names(getattr(keep, attr))
                    theirs = _names(getattr(item, attr))
                    if theirs:
                        setattr(keep, attr, json.dumps(sorted(set(mine) | set(theirs)), ensure_ascii=False))
            db.session.delete(item)
        for s in parts:
            if s.id != base.id:
                s.is_active = False
        merged += 1
    return merged


def _names(text):
    try:
        v = json.loads(text) if text else []
    except ValueError:
        v = [x.strip() for x in str(text).split(",") if x.strip()]
    return list(v) if isinstance(v, list) else []


# ── 3. drawdowns from the static level of the same flow test ────────────────
STATIC_FIELD = "fc_static"
STATIC_EXPR = f"COALESCE([{STATIC_FIELD}], [static_level])"


def _flowtest_static():
    base = _section("ps_fc_p1")
    if base is None:
        return 0
    f, made = _new_field(
        base, STATIC_FIELD, "سطح ایستایی در همان دبی‌سنجی (m)", "number", 0,
        prefill_from="@ref:ft.static_level", step="0.1",
        help_text=("افت هر کارکرد (سطح پویایی − سطح ایستایی) از سطح ایستایی همان دبی‌سنجی حساب می‌شود "
                   "تا ضرایب a و b درست درآیند؛ خالی بماند، سطح استاتیک فرم به کار می‌رود."))
    changed = int(made)
    for n in range(1, 6):
        for name in (f"fc_dd{n}", f"fc_spcap{n}"):
            fld = _field(name)
            if fld is not None and fld.formula and "[static_level]" in fld.formula \
                    and STATIC_FIELD not in fld.formula:
                fld.formula = fld.formula.replace("[static_level]", STATIC_EXPR)
                changed += 1
    return changed


# ── 4. pump and motor types from a dropdown with a search box ───────────────
def _type_dropdowns():
    from ..models import FormField
    n = 0
    for f in FormField.query.filter(FormField.lookup_category.in_(("pump_type", "motor_type")),
                                    FormField.field_type == "radio").all():
        f.field_type = "select"
        n += 1
    return n


# ── 5. the pull: branches of 6, 12 and 18 metres ────────────────────────────
SUM_COUNT = "COALESCE([pl_pipe_6], 0) + COALESCE([pl_pipe_12], 0) + COALESCE([pl_pipe_18], 0)"
SUM_METRES = "=6 * COALESCE([pl_pipe_6], 0) + 12 * COALESCE([pl_pipe_12], 0) + 18 * COALESCE([pl_pipe_18], 0)"


def _pull_pipes():
    sec = _section("pl_pipe")
    method, count, metres = _field("pl_pull_method"), _field("pl_pipe_count"), _field("pl_pulled_m")
    if sec is None or count is None or metres is None or _field("pl_pipe_6") is not None:
        return 0
    if method is None or not method.is_active or "LEADNUM" not in (metres.default_value or ""):
        return 0
    for k, length in enumerate((6, 12, 18)):
        _new_field(sec, f"pl_pipe_{length}", f"تعداد شاخه‌ی {length} متری", "number", 2 + k,
                   step="1", min_value=0)
    count.field_type = "formula"
    count.formula = SUM_COUNT
    count.label = "تعداد کل شاخه‌های کشیده‌شده"
    count.visible_when = None
    count.default_value = None
    count.help_text = "جمع شاخه‌های ۶، ۱۲ و ۱۸ متری."
    count.sort_order = 5
    metres.default_value = SUM_METRES
    metres.label = "کل متراژ کشیده‌شده (متر)"
    metres.help_text = "خودکار: ۶ × شاخه‌های ۶ متری + ۱۲ × ۱۲ متری + ۱۸ × ۱۸ متری — قابل ویرایش."
    metres.sort_order = 6
    method.is_active = False
    _new_field(sec, "pl_pipe_state", "وضعیت شاخه‌های کشیده‌شده", "radio", 7,
               options=["فرسوده", "نو"], help_text="یک گزینه برای همه‌ی شاخه‌های کشیده‌شده.")
    sec.columns = max(sec.columns or 3, 3)
    return 1


# ── 6. motor and pump to the equipment warehouse: plaques, no condition ─────
def _pull_rows():
    f = _field("wh_pull_items")
    if f is None or f.field_type != "wh_lines":
        return 0
    try:
        cfg = json.loads(f.wh_config or "{}")
    except ValueError:
        return 0
    if cfg.get("serial_source") == "register" or cfg.get("mode") == "parts":
        return 0
    cfg.update({"condition": False, "default_condition": "pulled", "conditions": [],
                "serial_source": "register",
                "preset_hint": "الکتروموتور و پمپی که از چاه کشیده شد؛ تیپ از «تیپ الکتروپمپ فعلی» خوانده "
                               "می‌شود — پلاک / سریال هر کدام را از شناسنامه‌ی تجهیزات جستجو و انتخاب کنید."})
    f.wh_config = json.dumps(cfg, ensure_ascii=False)
    f.help_text = "پلاک / سریال الکتروموتور و پمپ کشیده‌شده را از شناسنامه‌ی تجهیزات انتخاب کنید."
    sec = _section("wh_pull_in")
    if sec is not None:
        sec.description = ("الکتروموتور و پمپ کشیده‌شده با تیپ و پلاک (از شناسنامه‌ی تجهیزات) تحویل "
                           "انبار تجهیزات می‌شوند و به موجودی آن (به تفکیک تیپ) اضافه می‌شوند.")
    return 1


# ── 7. stock by type: part rules, a sample count, register types ────────────
PUMP_PARTS = [  # name, code if new, rule, per pump type
    ("پروانه", "PS-01", "stages", True),
    ("بوش", "PS-02", "stages", True),
    ("طبقه", "PS-03", "stages", True),
    ("شافت", "PS-04", "1", False),
    ("سوپاپ", "PS-05", "1", False),
]
PUMP_CATEGORY = "پمپ شناور"


def _inventory():
    from ..warehouse.models import WhItem
    from ..warehouse.service import enrich_register, seed_sample_opening, seed_warehouse
    seed_warehouse()
    touched = 0
    for k, (name, code, rule, per_type) in enumerate(PUMP_PARTS):
        item = WhItem.query.filter_by(kind="part", category=PUMP_CATEGORY, name=name).first()
        if item is None:
            if WhItem.query.filter_by(code=code).first() is not None:
                continue
            item = WhItem(code=code, name=name, kind="part", category=PUMP_CATEGORY, unit="عدد",
                          source="پیشنهادی", note="قطعه‌ی پایه‌ی پمپ")
            db.session.add(item)
        if not item.qty_rule:
            item.qty_rule = rule
        if per_type and not item.per_type:
            item.per_type = True
        item.sort_order = -20 + k                 # first in the pump's parts list
        touched += 1
    db.session.flush()
    out = {"parts": touched, "register_typed": enrich_register()}
    out["opening_rows"] = seed_sample_opening()
    db.session.commit()
    return out


# ── 8. the mechanical workshop: assembly, test, disassembly ─────────────────
TEST_SECTIONS = ["pumping_test", "wk_test_cond", "wk_test_p1", "wk_test_p2", "wk_test_p3",
                 "wk_test_p4", "wk_test_p5", "wk_test", "ps_prepare", "wk_compare",
                 "cable_starter", "ps_cable_existing", "ps_delivery", "ps_prep_consumables",
                 "ps_request"]
ASSEMBLY_ORDER = ["mt_head", "mt_motor_parts", "mt_pump_parts", "wh_build_in"]
JOIN_PRESET = [
    {"item_code": "EQ-01", "spec": 'IF(LEN([motor_curr]) > 0, CONCAT([motor_curr], " kW"))',
     "serial": "[mt_motor_code]", "qty": 1},
    {"item_code": "EQ-02", "spec": "EPUMP([pump_curr], [pump_stages])",
     "serial": "[mt_pump_code]", "qty": 1},
]


def _workshop_stages():
    from ..models import WorkflowStage, WorkflowStageItem
    stage = _stage_with("mt_head")
    if stage is None or _field(KIND_FIELD) is not None:
        return 0
    head = _section("mt_head")
    out = {"head": _assembly_head(head), "parts": _assembly_parts(), "join": _join_rows(),
           "disassembly": _disassembly()}
    # the stage that keeps the assembly, and the new one for the test
    workflow = stage.workflow
    test = WorkflowStage(workflow_id=workflow.id, stage_number=900 + stage.stage_number,
                         title="کارگاه مکانیک — آزمایش پمپاژ و تحویل الکتروپمپ",
                         description="آزمایش الکتروپمپ مونتاژشده، آماده‌سازی و کابل، و تحویل برای نصب.",
                         assignee_id=stage.assignee_id, applies_to=stage.applies_to, is_active=True,
                         referral_mode=stage.referral_mode or "next",
                         start_kind=stage.start_kind, waits_for=str(stage.stage_number),
                         visit_when=stage.visit_when,
                         needs_approval=stage.needs_approval, approver_id=stage.approver_id,
                         approval_blocks=stage.approval_blocks, approval_sees=stage.approval_sees,
                         spawn_workflow_id=stage.spawn_workflow_id, spawn_when=stage.spawn_when,
                         sla_hours=stage.sla_hours, show_refdata=True)
    test.owners = list(stage.owners)
    db.session.add(test)
    db.session.flush()
    test.reject_to_stage = None
    # the approval and the install process go with the test
    stage.needs_approval = False
    stage.approver_id = None
    stage.approval_blocks = False
    stage.reject_to_stage = None
    stage.spawn_workflow_id = None
    stage.spawn_when = None
    stage.title = "کارگاه مکانیک — مونتاژ (الکتروموتور / پمپ / الکتروپمپ)"
    stage.description = ("مونتاژ الکتروموتور، پمپ یا هر دو: کد، تعمیرکار و تیپ؛ قطعه‌های مصرفی از انبار قطعات "
                         "کسر می‌شود و الکتروپمپ متصل‌شده به انبار تجهیزات می‌رود.")
    moved = 0
    by_code = {}
    for it in sorted(stage.items, key=lambda i: (i.sort_order or 0, i.id)):
        code = it.section.code if it.section is not None else None
        by_code.setdefault(code, []).append(it)
    for k, code in enumerate(TEST_SECTIONS):
        for it in by_code.get(code, []):
            it.stage_id = test.id
            it.sort_order = k
            moved += 1
    for it in by_code.get("wh_build_out", []):
        db.session.delete(it)                     # one electropump goes in; nothing is taken out
    for k, code in enumerate(ASSEMBLY_ORDER):
        for it in by_code.get(code, []):
            it.sort_order = k
    # anything else the assembly carried stays with it, after its own forms
    rest = [it for c, items in by_code.items() if c not in TEST_SECTIONS + ASSEMBLY_ORDER + ["wh_build_out"]
            for it in items]
    for k, it in enumerate(rest):
        it.sort_order = len(ASSEMBLY_ORDER) + k
    db.session.flush()
    # order: … assembly, test, everything after the assembly
    from .workflow import renumber_stages
    ordered = sorted([s for s in workflow.stages if s.id != test.id], key=lambda s: s.stage_number)
    ids = []
    for s in ordered:
        ids.append(s.id)
        if s.id == stage.id:
            ids.append(test.id)
    renumber_stages(workflow, ids)
    if test.needs_approval:
        test.reject_to_stage = test.stage_number
    out.update({"test_stage": test.stage_number, "forms_moved": moved})
    return out


def _assembly_head(head):
    """«مونتاژ کدام تجهیز؟», then per equipment: code, repairman and type."""
    from ..models import FormField
    if head is None:
        return 0
    kind, _ = _new_field(head, KIND_FIELD, "مونتاژ کدام تجهیز؟", "radio", 0,
                         options=[KIND_MOTOR, KIND_PUMP, KIND_BOTH], is_required=True,
                         help_text="«هر دو»: الکتروموتور و پمپ به هم متصل و به‌صورت یک الکتروپمپ به انبار تجهیزات "
                                   "می‌رود؛ «الکتروموتور» یا «پمپ» تنها: فقط مونتاژ همان تجهیز.")
    plan = [  # name, label, type, visible, extra
        ("mt_motor_code", "کد اختصاص‌یافته‌ی الکتروموتور", "text", WHEN_MOTOR, {"lookup_category": "equipment:motor"}),
        ("mt_repairman", "تعمیرکار الکتروموتور", "text", WHEN_MOTOR, {}),
        ("mt_motor_type", "تیپ الکتروموتور (kW)", "mirror", WHEN_MOTOR, {"mirror_of": "motor_curr"}),
        ("mt_pump_code", "کد اختصاص‌یافته‌ی پمپ", "text", WHEN_PUMP, {"lookup_category": "equipment:pump"}),
        ("mt_pump_repairman", "تعمیرکار پمپ", "text", WHEN_PUMP, {}),
        ("mt_pump_type", "تیپ پمپ", "mirror", WHEN_PUMP, {"mirror_of": "pump_curr"}),
        ("mt_pump_model", "تیپ/طبقه پمپ (از کاتالوگ)", "mirror", WHEN_PUMP, {"mirror_of": "pump_stages"}),
    ]
    n = 1
    for k, (name, label, ftype, when, extra) in enumerate(plan, start=1):
        f = _field(name)
        if f is None:
            f, made = _new_field(head, name, label, ftype, k, **extra)
            n += int(made)
        else:
            f.label = label
            for key, value in extra.items():
                setattr(f, key, value)
        f.section_id = head.id
        f.sort_order = k
        f.visible_when = when
    # the mirrors are drawn as the record's own fields; make sure those exist
    for src in ("motor_curr", "pump_curr", "pump_stages"):
        if FormField.query.filter_by(field_name=src).first() is None:
            log.warning("R15: «%s» is missing — its mirror in the assembly shows nothing", src)
    head.title = "مونتاژ — تجهیز، کد، تعمیرکار و تیپ"
    head.columns = 4
    return n


def _assembly_parts():
    n = 0
    for name, sec_code, when, extra in (
            ("mt_motor_parts_f", "mt_motor_parts", WHEN_MOTOR, {}),
            ("mt_pump_parts_f", "mt_pump_parts", WHEN_PUMP,
             {"stages_field": "pump_stages", "type_field": "pump_curr"})):
        f = _field(name)
        sec = _section(sec_code)
        if f is None or f.field_type != "wh_lines":
            continue
        try:
            cfg = json.loads(f.wh_config or "{}")
        except ValueError:
            continue
        if cfg.get("mode") != "parts":
            continue
        cfg.update({"columns": ["total", "installed_new", "installed_repair"],
                    "labels": {"installed_new": "نو", "installed_repair": "تعمیری"},
                    "list_all": True, "check_stock": True, **extra})
        f.wh_config = json.dumps(cfg, ensure_ascii=False)
        f.help_text = ("همه‌ی قطعه‌های این تجهیز: «تعداد کل» هر قطعه (پروانه، بوش و طبقه به تعداد طبقات، شافت و "
                       "سوپاپ یک عدد) و اینکه چند تا نو و چند تا تعمیری است؛ با ثبت، از موجودی انبار قطعات کسر می‌شود.")
        if sec is not None:
            sec.visible_when = when
        n += 1
    return n


def _join_rows():
    f = _field("wh_build_in_items")
    if f is None or f.field_type != "wh_lines":
        return 0
    try:
        cfg = json.loads(f.wh_config or "{}")
    except ValueError:
        cfg = {}
    cfg.update({"mode": "rows", "warehouse": "equipment", "direction": "in", "reason": "assembled",
                "kinds": ["equipment"], "spec": True, "serial": True, "condition": False,
                "default_condition": "assembled", "conditions": [], "join_into": "EQ-03",
                "preset": JOIN_PRESET, "preset_lock": True,
                "preset_hint": "همین یک الکتروموتور و یک پمپ، به هم متصل، به‌صورت یک الکتروپمپ وارد انبار "
                               "تجهیزات می‌شوند (تیپ و کد از بخش مونتاژ خوانده می‌شود)."})
    f.wh_config = json.dumps(cfg, ensure_ascii=False)
    f.label = "الکتروپمپ متصل‌شده (الکتروموتور + پمپ) ← انبار تجهیزات"
    sec = _section("wh_build_in")
    if sec is not None:
        sec.title = "الکتروپمپ مونتاژشده ← انبار تجهیزات"
        sec.visible_when = WHEN_BOTH
        sec.description = "فقط وقتی «هر دو (الکتروپمپ)» مونتاژ شود؛ به موجودی انبار تجهیزات برای نصب اضافه می‌شود."
    return 1


def _disassembly():
    n = 0
    for name, item, code_field, lookup in (("dm_motor_parts_f", "EQ-01", "dm_motor_code", "equipment:motor"),
                                           ("dm_pump_parts_f", "EQ-02", "dm_pump_code", "equipment:pump")):
        f = _field(name)
        if f is not None and f.field_type == "wh_lines":
            try:
                cfg = json.loads(f.wh_config or "{}")
            except ValueError:
                cfg = {}
            if cfg.get("mode") == "parts":
                cfg.update({"equipment_out": True, "equipment_item": item})
                f.wh_config = json.dumps(cfg, ensure_ascii=False)
                n += 1
        cf = _field(code_field)
        if cf is not None and cf.field_type == "text" and not cf.lookup_category:
            cf.lookup_category = lookup
    return n

