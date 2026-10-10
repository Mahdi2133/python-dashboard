"""/api/form-builder — the real form designer (requirements 13 & 14)."""
import json
import re

from flask import Blueprint, request

from ..extensions import db
from ..models import (FormField, FormFieldOption, FormSection, LookupCategory,
                      LookupItem, RecordDynamicValue)
from ..models.formbuilder import FIELD_TYPES
from ..services.auth import (FORM_READERS, permission_required,
                             permission_required_any)
from ..services.audit import record_audit
from ..services.jalali import MONTHS_FA
from ..services.lookups import items_by_category, normalize_text
from ._helpers import body, fail, ok

bp = Blueprint("api_formbuilder", __name__, url_prefix="/api/form-builder")


def _sync_options(field, options):
    """Reconcile a field's own options with the list the editor submitted.

    Options in use by saved records must not vanish, so an option that is
    dropped from the list is deactivated rather than deleted; one that comes
    back is reactivated. Matching is by value, which is what records store.
    """
    incoming = []
    for idx, opt in enumerate(options):
        if isinstance(opt, dict):
            value = normalize_text(opt.get("value"))
            label = normalize_text(opt.get("label")) or value
            icon = (opt.get("icon") or "").strip() or None
            active = opt.get("is_active", True) in (True, "true", "1", 1)
        else:
            value = label = normalize_text(opt)
            icon, active = None, True
        if not value:
            continue
        incoming.append({"value": value, "label": label, "icon": icon,
                         "sort_order": idx, "is_active": active})

    existing = {o.value: o for o in field.options}
    seen = set()
    for spec in incoming:
        seen.add(spec["value"])
        current = existing.get(spec["value"])
        if current is None:
            db.session.add(FormFieldOption(field_id=field.id, **spec))
        else:
            current.label = spec["label"]
            current.icon = spec["icon"]
            current.sort_order = spec["sort_order"]
            current.is_active = spec["is_active"]
    for value, option in existing.items():
        if value not in seen:
            option.is_active = False
    db.session.flush()


def _month_options():
    return [{"value": str(i), "label": MONTHS_FA[i], "is_active": True,
             "sort_order": i} for i in range(1, 13)]


@bp.get("")
@permission_required_any(*FORM_READERS)
def get_schema():
    """Everything the data-entry page needs to render itself, in one call."""
    active_only = request.args.get("all") not in ("1", "true")
    query = FormSection.query.order_by(FormSection.sort_order)
    if active_only:
        query = query.filter(FormSection.is_active.is_(True))
    if request.args.get("for") == "entry":
        # The standalone entry page leaves out the process-only forms — except
        # one the admin linked to a question («اتصال‌ها»): a linked form opens
        # wherever its question is asked, so two forms linked to one answer
        # both open, not only the one that happens to be on the entry page.
        from ..services.conditions import parse_rules as _rules
        linked = lambda s: any(vals for _on, vals in _rules(s.visible_when))  # noqa: E731
        rows = [s for s in query.all() if s.show_on_entry is not False or linked(s)]
    else:
        rows = query.all()
    sections = [s.to_dict(include_fields=True, active_only=active_only) for s in rows]
    if active_only:
        # one widget per answer: a «فیلد مشترک» whose field is already drawn
        # in an earlier form is not drawn twice
        seen = set()
        for sec in sections:
            kept = []
            for f in sec.get("fields") or []:
                if f["field_name"] in seen:
                    continue
                seen.add(f["field_name"])
                kept.append(f)
            sec["fields"] = kept
    lookups = items_by_category(active_only=active_only)
    lookups["__months__"] = _month_options()
    # Flattened "show this field only while that one holds this value" rules,
    # so the form can evaluate them without re-walking the section tree.
    # One entry per form or field, carrying every rule on it («any»): the page
    # shows it when any one of them holds.
    from ..services.conditions import parse_rules

    def entry(raw):
        rules = parse_rules(raw)
        if not rules:
            return None
        return {"on": rules[0][0], "value": "|".join(rules[0][1]),
                "any": [{"on": on, "value": "|".join(vals)} for on, vals in rules]}

    conditional = []
    for section in sections:
        rule = entry(section.get("visible_when"))
        if rule:
            conditional.append({"section": section["code"],
                                "fields": [f["field_name"] for f in section["fields"]],
                                **rule})
        for field in section["fields"]:
            rule = entry(field.get("visible_when"))
            if rule:
                conditional.append({"field": field["field_name"], **rule})
    from ..services.workflow import PREFILL_WELL_ATTRS, PREFILL_WHEN
    extra = {}
    if not active_only:
        # the editor's pickers: who may approve an answer, and which process
        # stage a field may be filled at
        from ..models import AppUser, WorkflowDefinition
        extra["users"] = [{"id": u.id, "name": u.full_name}
                          for u in AppUser.query.filter_by(is_active=True)
                          .order_by(AppUser.first_name, AppUser.username).all()]
        extra["stages"] = [
            {"id": s.id, "stage_number": s.stage_number, "title": s.title,
             "workflow_id": w.id, "workflow": w.name}
            for w in WorkflowDefinition.query.filter_by(is_active=True)
            .order_by(WorkflowDefinition.id).all()
            for s in sorted(w.stages, key=lambda x: x.stage_number)
            if s.is_active and s.stage_number > 0]
        extra["warehouse"] = _warehouse_options()
    return ok({"sections": sections, "lookups": lookups,
               "conditional": conditional,
               "prefill_when": [{"value": k, "label": v}
                                for k, v in PREFILL_WHEN.items()],
               "prefill_well": [{"value": "@well:" + k, "label": v}
                                for k, v in PREFILL_WELL_ATTRS.items()],
               "prefill_ref": _ref_options(),
               "field_types": list(FIELD_TYPES), **extra})


def _warehouse_options():
    """The «اقلام انبار» editor's lists, from the warehouse's own tables: the
    conditions defined on the warehouse page and every equipment kind that
    has a parts list in the item catalogue."""
    try:
        from ..warehouse.models import REASONS, WhCondition, WhItem
        from ..warehouse.service import PART_COLUMNS
        kinds = sorted({i.category for i in WhItem.query.filter_by(kind="part", is_active=True)
                        if i.category})
        return {"items": [{"code": i.code, "name": i.name, "kind": i.kind} for i in
                          WhItem.query.filter_by(is_active=True, kind="equipment")
                          .order_by(WhItem.sort_order, WhItem.id) if i.code],
                "conditions": [{"code": c.code, "label": c.label} for c in
                               WhCondition.query.filter_by(is_active=True)
                               .order_by(WhCondition.sort_order)],
                "equipment_types": kinds, "reasons": REASONS,
                "columns": [{"code": k, "label": v} for k, v in PART_COLUMNS]}
    except Exception:  # noqa: BLE001 — the form builder opens without them
        return {}


def _ref_options():
    """The reference databases' values a field can start from («@ref:…»)."""
    try:
        from ..refdata.profile import catalogue_options
        return catalogue_options()
    except Exception:  # noqa: BLE001 — the form builder opens without them
        return []


@bp.post("/sections")
@permission_required("form.manage")
def create_section():
    payload = body()
    code = normalize_text(payload.get("code"))
    title = normalize_text(payload.get("title"))
    if not code or not title:
        return fail("کد و عنوان بخش الزامی است.", 422)
    if FormSection.query.filter_by(code=code).first():
        return fail("بخشی با این کد وجود دارد.", 409)
    section = FormSection(
        code=code, title=title, icon=payload.get("icon"),
        columns=int(payload.get("columns") or 3),
        full_width=bool(payload.get("full_width")),
        sort_order=int(payload.get("sort_order")
                       or (db.session.query(db.func.max(FormSection.sort_order))
                           .scalar() or 0) + 1),
        description=payload.get("description"),
        visible_when=normalize_text(payload.get("visible_when")) or None,
        show_on_entry=payload.get("show_on_entry", True) in (True, "true", "1", 1),
        collapse_formulas=payload.get("collapse_formulas") in (True, "true", "1", 1),
        repeat_group=(normalize_text(payload.get("repeat_group")) or None),
        layout=("grid" if payload.get("layout") == "grid" else None),
        grid_label=(normalize_text(payload.get("grid_label")) or None),
    )
    db.session.add(section)
    db.session.flush()
    record_audit("create", "form_section", section.id, summary=f"افزودن بخش «{title}»")
    db.session.commit()
    return ok(section.to_dict(), message="بخش افزوده شد.")


@bp.put("/sections/<int:section_id>")
@permission_required("form.manage")
def update_section(section_id):
    section = db.session.get(FormSection, section_id)
    if section is None:
        return fail("بخش یافت نشد.", 404)
    payload = body()
    for attr in ("title", "icon", "description", "visible_when", "repeat_group", "grid_label"):
        if attr in payload:
            setattr(section, attr, normalize_text(payload[attr]) or None)
    if "layout" in payload:
        section.layout = "grid" if payload["layout"] == "grid" else None
    for attr in ("columns", "sort_order"):
        if attr in payload:
            setattr(section, attr, int(payload[attr] or 0))
    for attr in ("full_width", "is_active", "show_on_entry", "collapse_formulas"):
        if attr in payload:
            setattr(section, attr, payload[attr] in (True, "true", "1", 1))
    record_audit("update", "form_section", section.id, summary=f"ویرایش بخش «{section.title}»")
    db.session.commit()
    return ok(section.to_dict(), message="بخش به‌روزرسانی شد.")


@bp.delete("/sections/<int:section_id>")
@permission_required("form.manage")
def delete_section(section_id):
    section = db.session.get(FormSection, section_id)
    if section is None:
        return fail("بخش یافت نشد.", 404)
    if any(f.is_builtin for f in section.fields):
        section.is_active = False
        db.session.commit()
        return ok(message="این بخش شامل فیلدهای پایه است؛ غیرفعال شد و حذف نگردید.")
    # Deleting a section cascades to its fields and from there to every stored
    # answer, so a section holding real data is deactivated, never dropped.
    field_ids = [f.id for f in section.fields]
    used = (RecordDynamicValue.query.filter(RecordDynamicValue.field_id.in_(field_ids)).count()
            if field_ids else 0)
    if used:
        section.is_active = False
        for field in section.fields:
            field.is_active = False
        record_audit("update", "form_section", section.id,
                     summary=f"غیرفعال‌سازی بخش «{section.title}» ({used} مقدار ثبت‌شده)")
        db.session.commit()
        return ok(message=f"{used} مقدار ثبت‌شده به فیلدهای این بخش وابسته است؛ "
                          "بخش غیرفعال شد و داده‌ها حفظ شدند.")
    record_audit("delete", "form_section", section.id, summary=f"حذف بخش «{section.title}»")
    db.session.delete(section)
    db.session.commit()
    return ok(message="بخش حذف شد.")


def _special_settings(field, payload):
    """Validate and store what «مستند»، «محاسباتی» and «فیلد مشترک» need.

    Returns a Persian error, or None.
    """
    ftype = field.field_type
    if "file_accept" in payload:
        field.file_accept = normalize_text(payload.get("file_accept")) or None
    if "file_multiple" in payload:
        field.file_multiple = payload.get("file_multiple") in (True, "true", "1", 1)
    if ftype == "mirror":
        target_name = normalize_text(payload.get("mirror_of", field.mirror_of)) or None
        if not target_name:
            return "برای «فیلد مشترک»، فیلدی را که باید نمایش دهد انتخاب کنید."
        target = FormField.query.filter_by(field_name=target_name).first()
        if target is None:
            return f"فیلد «{target_name}» پیدا نشد."
        if target.id == field.id:
            return "فیلد مشترک نمی‌تواند به خودش اشاره کند."
        field.mirror_of = target_name
        if field.mirror_source() is None:
            field.mirror_of = None
            return "این انتخاب یک حلقه می‌سازد (فیلد مشترکی که به خودش برمی‌گردد)."
        # a mirror stores nothing of its own and is never «required» on its
        # own — the field it shows carries that
        field.is_required = False
    else:
        field.mirror_of = None
    if ftype == "formula":
        text = (payload.get("formula", field.formula) or "").strip()
        if not text:
            return "برای «فیلد محاسباتی» فرمول را بنویسید؛ مثلاً [design_flow] * 0.001 / [dynamic_level]"
        from ..analytics.formula import FormulaError
        from ..services.formfields import compile_field_formula
        try:
            compile_field_formula(text, exclude=field.field_name)
        except FormulaError as exc:
            return f"فرمول نامعتبر است: {exc}"
        field.formula = text
    elif "formula" in payload and ftype != "formula":
        field.formula = None
    if ftype == "formula" and "result_type" in payload:
        field.result_type = "text" if payload.get("result_type") == "text" else None
    if ftype == "chart":
        problem = _chart_settings(field, payload)
        if problem:
            return problem
    elif "chart_config" in payload:
        field.chart_config = None
    if ftype == "wh_lines":
        problem = _warehouse_settings(field, payload)
        if problem:
            return problem
    elif "wh_config" in payload:
        field.wh_config = None
    return _behaviour_settings(field, payload)


def _warehouse_settings(field, payload):
    """«اقلام انبار»: which warehouse, in or out, why, and which items/conditions."""
    from ..warehouse.models import REASONS, WAREHOUSES
    raw = payload.get("wh_config", field.wh_config)
    if isinstance(raw, str):
        try:
            raw = json.loads(raw or "{}")
        except ValueError:
            return "تنظیمات «اقلام انبار» نامعتبر است."
    raw = raw if isinstance(raw, dict) else {}
    try:
        before = json.loads(field.wh_config or "{}")
    except ValueError:
        before = {}
    before = before if isinstance(before, dict) else {}
    if raw.get("warehouse") not in WAREHOUSES:
        return "برای «اقلام انبار» انبار (تجهیزات یا قطعات) را انتخاب کنید."
    if raw.get("direction") not in ("in", "out"):
        return "برای «اقلام انبار» مشخص کنید ورود است یا خروج."
    mode = raw.get("mode", before.get("mode")) or "rows"
    cfg = {
        "mode": "parts" if mode == "parts" else "rows",
        "warehouse": raw["warehouse"], "direction": raw["direction"],
        "reason": raw.get("reason") if raw.get("reason") in REASONS else "manual",
        "kinds": [k for k in raw.get("kinds") or [] if k in ("equipment", "part")],
        "categories": [normalize_text(c) for c in raw.get("categories") or [] if c],
        "conditions": [c for c in raw.get("conditions") or [] if c],
        "default_condition": raw.get("default_condition") or None,
        "spec": bool(raw.get("spec", True)), "serial": bool(raw.get("serial", True)),
    }
    keep = lambda k, d=None: raw.get(k, before.get(k, d))  # noqa: E731
    if cfg["mode"] == "rows":
        # «ردیف‌های ثابت»: rows the form starts with (item code, a spec that
        # may be a formula, quantity); «قفل» leaves only condition and plate open
        preset = []
        for row in raw.get("preset", before.get("preset")) or []:
            if not isinstance(row, dict) or not str(row.get("item_code") or "").strip():
                continue
            try:
                qty = float(str(row.get("qty") or 1).replace("٫", "."))
            except ValueError:
                qty = 1
            preset.append({"item_code": str(row["item_code"]).strip(),
                           "spec": str(row.get("spec") or "").strip(),
                           "serial": str(row.get("serial") or "").strip() or None,
                           "qty": qty if qty > 0 else 1,
                           "condition": str(row.get("condition") or "").strip() or None})
        if preset:
            cfg["preset"] = preset
            cfg["preset_lock"] = bool(raw.get("preset_lock", before.get("preset_lock")))
        # «ستون وضعیت» shown or not; plaques searched in the equipment
        # register; rows joined into one electropump (its item code)
        cfg["condition"] = bool(keep("condition", True))
        cfg["serial_source"] = "register" if keep("serial_source") == "register" else None
        cfg["join_into"] = str(keep("join_into") or "").strip() or None
        if normalize_text(keep("preset_hint")):
            cfg["preset_hint"] = normalize_text(keep("preset_hint"))
    if cfg["mode"] == "parts":
        # «فرم قطعات»: the equipment whose parts are listed, the counted
        # columns, and the fields of the same form that name the equipment
        # and its failure — a key the builder does not show is kept as it was
        from ..warehouse.service import PART_COLUMNS
        known = {k for k, _l in PART_COLUMNS}
        pick = lambda k: (str(raw.get(k, before.get(k)) or "").strip() or None)  # noqa: E731
        cfg.update({
            "equipment_type": pick("equipment_type"),
            "columns": [c for c in raw.get("columns", before.get("columns")) or [] if c in known],
            "equipment_field": pick("equipment_field"), "failure_field": pick("failure_field"),
            "cause_field": pick("cause_field"), "action_field": pick("action_field"),
            "related_action": pick("related_action"),
            # the whole list at once; the stock checked; the pump's stage count
            # and type for «× طبقات» and per-type parts; the equipment leaving
            # the equipment warehouse when it is taken apart
            "list_all": bool(keep("list_all", False)), "check_stock": bool(keep("check_stock", False)),
            "stages_field": pick("stages_field"), "type_field": pick("type_field"),
            "equipment_out": bool(keep("equipment_out", False)), "equipment_item": pick("equipment_item"),
        })
        labels = keep("labels") or {}
        if isinstance(labels, dict):
            labels = {k: normalize_text(v) for k, v in labels.items() if k in known and normalize_text(v)}
            if labels:
                cfg["labels"] = labels
        if not cfg["equipment_type"]:
            return "برای «فرم قطعات» تجهیز (الکتروموتور یا پمپ) را انتخاب کنید."
        if not cfg["columns"]:
            return "برای «فرم قطعات» دست‌کم یک ستون شمارش را انتخاب کنید."
    field.wh_config = json.dumps(cfg, ensure_ascii=False)
    return None


def _chart_curve(raw, known):
    """«منحنی از فرمول»: y as a formula of [x] and the form's fields, an
    optional condition for drawing it and the note shown when it fails."""
    if not isinstance(raw, dict) or not str(raw.get("y") or "").strip():
        return None
    out = {}
    for key in ("y", "require"):
        text = str(raw.get(key) or "").strip()
        if not text:
            continue
        refs = {r.strip() for r in re.findall(r"\[([^\]]+)\]", text)} - {"x"}
        missing = sorted(r for r in refs if r not in known)
        if missing:
            return f"فیلد «{missing[0]}» در فرمول منحنی پیدا نشد."
        out[key] = text
    if normalize_text(raw.get("note")):
        out["note"] = normalize_text(raw.get("note"))
    if normalize_text(raw.get("eq_label")):
        out["eq_label"] = normalize_text(raw.get("eq_label"))
    return out


def _chart_settings(field, payload):
    """«نمودار»: series of x/y fields, an axis each, an optional trend line."""
    raw = payload.get("chart_config", field.chart_spec)
    if isinstance(raw, str):
        try:
            raw = json.loads(raw or "{}")
        except ValueError:
            return "تنظیمات نمودار نامعتبر است."
    raw = raw if isinstance(raw, dict) else {}
    known = {f.field_name for f in FormField.query.all()}
    series = []
    for sr in raw.get("series") or []:
        if isinstance(sr.get("catalogue"), dict):
            # a catalogue curve: the fields naming the model, kept as set
            refs = [r for r in (sr["catalogue"].get("type"), sr["catalogue"].get("stages"))
                    if isinstance(r, str) and r]
            missing = [n for n in refs if n not in known]
            if missing:
                return f"فیلد «{missing[0]}» برای نمودار پیدا نشد."
            series.append(sr)
            continue
        xs = [x for x in sr.get("x") or [] if x]
        ys = [y for y in sr.get("y") or [] if y]
        if not xs or not ys:
            continue
        missing = [n for n in xs + ys if n not in known]
        if missing:
            return f"فیلد «{missing[0]}» برای نمودار پیدا نشد."
        if len(xs) != len(ys):
            return f"در سری «{sr.get('label') or ''}» تعداد فیلدهای محور افقی و عمودی باید برابر باشد."
        curve = _chart_curve(sr.get("curve"), known)
        if isinstance(curve, str):
            return curve
        extra = {"curve": curve} if curve else {}
        if "scale" in sr and sr["scale"] in (None, ""):
            sr = {k: v for k, v in sr.items() if k != "scale"}
        series.append({"label": normalize_text(sr.get("label")) or "سری", **extra,
                       "x": xs, "y": ys,
                       "axis": "right" if sr.get("axis") == "right" else "left",
                       "trend": sr.get("trend") if sr.get("trend") in
                       ("poly2", "poly2_0", "power", "linear") else "",
                       # drawing settings the editor does not show, kept as set
                       **{k: sr[k] for k in ("start", "connect", "scale", "color",
                                              "hide_same_as") if k in sr}})
    if not series:
        return "برای نمودار دست‌کم یک سری با فیلدهای محور افقی و عمودی تعریف کنید."
    field.chart_config = json.dumps({
        "series": series,
        "x_label": normalize_text(raw.get("x_label")) or "",
        "y_label": normalize_text(raw.get("y_label")) or "",
        "y2_label": normalize_text(raw.get("y2_label")) or "",
        "y_max": raw.get("y_max") if isinstance(raw.get("y_max"), (int, float)) else None,
        "y2_max": raw.get("y2_max") if isinstance(raw.get("y2_max"), (int, float)) else None,
    }, ensure_ascii=False)
    field.is_required = False
    return None


def _approvers_ok(ids):
    from ..models import AppUser
    for pid in ids:
        person = db.session.get(AppUser, pid)
        if person is None or not person.is_active:
            return False
    return True


def _behaviour_settings(field, payload):
    """What a field does in a process — whose approval its answers need, which
    answers stop the stage, where it is filled. None of it touches how the
    answer is stored, so built-in fields («خرابی مشاهده شده») take it too."""
    # «طبقات از کاتالوگ برای تیپِ فیلد …»
    if "stages_of" in payload:
        target_name = normalize_text(payload.get("stages_of")) or None
        if target_name:
            if field.field_type not in ("number", "text", "radio", "select", "autocomplete"):
                return "«طبقات از کاتالوگ» برای فیلد عددی، متنی یا انتخابی است."
            target = FormField.query.filter_by(field_name=target_name).first()
            if target is None or target.id == field.id:
                return f"فیلد تیپ پمپ «{target_name}» پیدا نشد."
        field.stages_of = target_name
    # «تأیید گزینه»: several rules, each its own answers → its own approvers
    if "approval_rules" in payload:
        rules = []
        for r in payload.get("approval_rules") or []:
            opts = list(dict.fromkeys(normalize_text(x) for x in r.get("options") or []
                                      if normalize_text(x)))
            who = list(dict.fromkeys(int(x) for x in r.get("approvers") or []
                                     if str(x or "").isdigit()))
            if not opts and not who:
                continue
            if not field.is_choice:
                return "«تأیید گزینه» فقط برای فیلدهای انتخابی است."
            if not opts:
                return "در هر قاعده‌ی تأیید، دست‌کم یک گزینه را تیک بزنید."
            if not who:
                return "برای هر قاعده‌ی تأیید، تأییدکننده را انتخاب کنید."
            if not _approvers_ok(who):
                return "تأییدکننده پیدا نشد یا غیرفعال است."
            answer = normalize_text(r.get("answer_field")) or None
            if answer:
                target = FormField.query.filter_by(field_name=answer).first()
                if target is None or not target.is_choice or target.id == field.id:
                    return "«پاسخ تأییدکننده» باید یک فیلد انتخابی دیگر باشد."
            rules.append({"options": opts, "approvers": who, "answer_field": answer,
                          "required": bool(r.get("required"))})
        field.approval_rules = json.dumps(rules, ensure_ascii=False) if rules else None
        first = rules[0] if rules else None   # the single-rule columns follow the first
        field.approval_options = json.dumps(first["options"], ensure_ascii=False) if first else None
        field.approval_user_id = first["approvers"][0] if first else None
        field.approval_user_ids = ",".join(map(str, first["approvers"])) if first else None
        field.approval_answer_field = first["answer_field"] if first else None
    elif any(k in payload for k in ("approval_options", "approval_user_id", "approval_user_ids")):
        chosen = [normalize_text(x) for x in (payload.get("approval_options") or [])
                  if normalize_text(x)]
        # one approver or several — every one of them must approve
        raw = payload.get("approval_user_ids")
        if raw is None:
            raw = [payload.get("approval_user_id")] if payload.get("approval_user_id") else []
        who = list(dict.fromkeys(int(x) for x in raw if str(x or "").isdigit()))
        if chosen and not field.is_choice:
            return "«تأیید گزینه» فقط برای فیلدهای انتخابی است."
        if chosen and not who:
            return "برای گزینه‌های نیازمند تأیید، تأییدکننده را انتخاب کنید."
        if chosen and not _approvers_ok(who):
            return "تأییدکننده پیدا نشد یا غیرفعال است."
        answer = normalize_text(payload.get("approval_answer_field")) or None
        if chosen and answer:
            target = FormField.query.filter_by(field_name=answer).first()
            if target is None or not target.is_choice or target.id == field.id:
                return "«پاسخ تأییدکننده» باید یک فیلد انتخابی دیگر باشد."
        field.approval_rules = None
        field.approval_options = (json.dumps(list(dict.fromkeys(chosen)), ensure_ascii=False)
                                  if chosen else None)
        field.approval_user_id = who[0] if chosen else None
        field.approval_user_ids = ",".join(str(x) for x in who) if chosen else None
        field.approval_answer_field = answer if chosen else None
    # «مانع ارسال»: answers with which the stage is not sent on
    if "block_options" in payload:
        blocked = list(dict.fromkeys(normalize_text(x) for x in payload.get("block_options") or []
                                     if normalize_text(x)))
        if blocked and not field.is_choice:
            return "«مانع ارسال» فقط برای فیلدهای انتخابی است."
        field.block_options = json.dumps(blocked, ensure_ascii=False) if blocked else None
    # «مرحله‌ی پرکردن»: at most one stage per process
    if "fill_stage_ids" in payload:
        from ..models import WorkflowStage
        ids = [int(x) for x in (payload.get("fill_stage_ids") or []) if str(x).isdigit()]
        stages = [db.session.get(WorkflowStage, i) for i in dict.fromkeys(ids)]
        if any(s is None for s in stages):
            return "مرحله‌ی انتخاب‌شده برای پرکردن پیدا نشد."
        per_flow = {}
        for s in stages:
            if s.workflow_id in per_flow:
                return (f"در فرایند «{s.workflow.name}» فقط یک مرحله را برای پرکردن "
                        f"این فیلد انتخاب کنید.")
            per_flow[s.workflow_id] = s
        field.fill_stage_ids = ",".join(str(s.id) for s in stages) or None
    return None


@bp.post("/formula/check")
@permission_required("form.manage")
def check_formula():
    """Validate a form formula while it is being typed."""
    from ..analytics.formula import FormulaError
    from ..services.formfields import compile_field_formula
    payload = body()
    try:
        comp = compile_field_formula(payload.get("formula") or "",
                                     exclude=payload.get("field_name"))
    except FormulaError as exc:
        return ok({"valid": False, "error": str(exc)})
    return ok({"valid": True, "refs": sorted(comp["refs"])})


@bp.post("/fields")
@permission_required("form.manage")
def create_field():
    payload = body()
    name = normalize_text(payload.get("field_name"))
    label = normalize_text(payload.get("label"))
    ftype = payload.get("field_type") or "text"
    if not name or not label:
        return fail("نام فیلد و برچسب الزامی است.", 422)
    if ftype not in FIELD_TYPES:
        return fail(f"نوع فیلد نامعتبر است. مقادیر مجاز: {', '.join(FIELD_TYPES)}", 422)
    if not name.replace("_", "").isalnum():
        return fail("نام فیلد فقط می‌تواند شامل حروف انگلیسی، عدد و زیرخط باشد.", 422)
    if FormField.query.filter_by(field_name=name).first():
        return fail("فیلدی با این نام وجود دارد.", 409)
    section = db.session.get(FormSection, int(payload.get("section_id") or 0))
    if section is None:
        return fail("بخش مربوطه را انتخاب کنید.", 422)
    field = FormField(
        section_id=section.id, field_name=name, label=label, field_type=ftype,
        # Admin-created fields are always dynamic: they may not claim a Record
        # column, which would let the form overwrite a built-in value.
        model_attr=None, lookup_category=payload.get("lookup_category") or None,
        placeholder=payload.get("placeholder"), help_text=payload.get("help_text"),
        default_value=payload.get("default_value"),
        is_required=payload.get("is_required") in (True, "true", "1", 1),
        is_active=payload.get("is_active", True) in (True, "true", "1", 1),
        is_builtin=False,
        allow_other=payload.get("allow_other") in (True, "true", "1", 1),
        sort_order=int(payload.get("sort_order")
                       or max([f.sort_order for f in section.fields], default=0) + 1),
        col_span=int(payload.get("col_span") or 1),
        min_value=payload.get("min_value") or None,
        max_value=payload.get("max_value") or None,
        max_length=payload.get("max_length") or None,
        step=payload.get("step") or None,
        show_in_table=payload.get("show_in_table") in (True, "true", "1", 1),
        table_order=int(payload.get("table_order") or 0),
        export_header=payload.get("export_header") or label,
        visible_when=normalize_text(payload.get("visible_when")) or None,
        # «برداشت از سوابق» chosen while creating the field was dropped here,
        # so a new field never filled from the well's history until edited.
        prefill_from=normalize_text(payload.get("prefill_from")) or None,
    )
    problem = _special_settings(field, payload)
    if problem:
        return fail(problem, 422)
    db.session.add(field)
    db.session.flush()
    _sync_options(field, payload.get("options") or [])
    record_audit("create", "form_field", field.id, summary=f"افزودن فیلد «{label}»")
    db.session.commit()
    return ok(field.to_dict(active_only=False), message="فیلد افزوده شد.")


@bp.put("/fields/<int:field_id>")
@permission_required("form.manage")
def update_field(field_id):
    field = db.session.get(FormField, field_id)
    if field is None:
        return fail("فیلد یافت نشد.", 404)
    payload = body()
    if payload.get("field_type") and payload["field_type"] not in FIELD_TYPES:
        return fail("نوع فیلد نامعتبر است.", 422)
    if field.is_builtin:
        # Renaming, reordering, help text and required-ness stay editable; the
        # storage identity (field_name / model_attr / type) does not, because
        # Record columns, reports and exports are bound to it.
        editable = {"label", "placeholder", "help_text", "default_value", "is_required",
                    "is_active", "sort_order", "col_span", "min_value", "max_value",
                    "step", "show_in_table", "table_order", "export_header",
                    "allow_other", "section_id", "visible_when", "prefill_from",
                    "approval_rules", "approval_options", "approval_user_id",
                    "approval_user_ids", "approval_answer_field", "block_options",
                    "fill_stage_ids"}
        payload = {k: v for k, v in payload.items() if k in editable}
    for attr in ("label", "placeholder", "help_text", "default_value", "export_header",
                 "step", "lookup_category", "field_type", "field_name", "visible_when",
                 "prefill_from"):
        if attr in payload:
            setattr(field, attr, normalize_text(payload[attr]) or None)
    for attr in ("sort_order", "col_span", "table_order", "section_id", "max_length"):
        if attr in payload and payload[attr] not in (None, ""):
            setattr(field, attr, int(payload[attr]))
    for attr in ("min_value", "max_value"):
        if attr in payload:
            setattr(field, attr, float(payload[attr]) if payload[attr] not in (None, "")
                    else None)
    for attr in ("is_required", "is_active", "allow_other", "show_in_table"):
        if attr in payload:
            setattr(field, attr, payload[attr] in (True, "true", "1", 1))

    problem = (_special_settings(field, payload) if not field.is_builtin
               else _behaviour_settings(field, payload))
    if problem:
        db.session.rollback()
        return fail(problem, 422)

    # Options were previously ignored here, so editing a field's choices did
    # nothing — the field came back with its original list every time.
    if "options" in payload:
        _sync_options(field, payload.get("options") or [])

    record_audit("update", "form_field", field.id, summary=f"ویرایش فیلد «{field.label}»")
    db.session.commit()
    return ok(field.to_dict(active_only=False), message="فیلد به‌روزرسانی شد.")


@bp.delete("/fields/<int:field_id>")
@permission_required("form.manage")
def delete_field(field_id):
    field = db.session.get(FormField, field_id)
    if field is None:
        return fail("فیلد یافت نشد.", 404)
    if field.is_builtin:
        field.is_active = False
        db.session.commit()
        return ok(message="فیلد پایه حذف نمی‌شود؛ غیرفعال شد و از فرم پنهان گردید.")
    used = RecordDynamicValue.query.filter_by(field_id=field.id).count()
    if used:
        field.is_active = False
        db.session.commit()
        return ok(message=f"{used} رکورد مقدار این فیلد را دارند؛ فیلد غیرفعال شد.")
    record_audit("delete", "form_field", field.id, summary=f"حذف فیلد «{field.label}»")
    db.session.delete(field)
    db.session.commit()
    return ok(message="فیلد حذف شد.")


@bp.post("/fields/<int:field_id>/options")
@permission_required("form.manage")
def add_field_option(field_id):
    field = db.session.get(FormField, field_id)
    if field is None:
        return fail("فیلد یافت نشد.", 404)
    payload = body()
    value = normalize_text(payload.get("value"))
    if not value:
        return fail("مقدار گزینه الزامی است.", 422)
    if any(o.value == value for o in field.options):
        return fail("این گزینه وجود دارد.", 409)
    opt = FormFieldOption(
        field_id=field.id, value=value,
        label=normalize_text(payload.get("label")) or value,
        icon=payload.get("icon"),
        sort_order=max([o.sort_order for o in field.options], default=0) + 1)
    db.session.add(opt)
    db.session.commit()
    return ok(field.to_dict(), message="گزینه افزوده شد.")


@bp.put("/options/<int:option_id>")
@permission_required("form.manage")
def update_field_option(option_id):
    opt = db.session.get(FormFieldOption, option_id)
    if opt is None:
        return fail("گزینه یافت نشد.", 404)
    payload = body()
    for attr in ("value", "label", "icon"):
        if attr in payload:
            setattr(opt, attr, normalize_text(payload[attr]) or None)
    if "sort_order" in payload:
        opt.sort_order = int(payload["sort_order"] or 0)
    if "is_active" in payload:
        opt.is_active = payload["is_active"] in (True, "true", "1", 1)
    db.session.commit()
    return ok(opt.to_dict(), message="گزینه به‌روزرسانی شد.")


@bp.get("/fields/<int:field_id>/options")
@permission_required("form.manage")
def field_options(field_id):
    """The options actually shown for a field, wherever they are stored."""
    field = db.session.get(FormField, field_id)
    if field is None:
        return fail("فیلد یافت نشد.", 404)
    source = field.options_source
    if source == "lookup":
        cat = LookupCategory.query.filter_by(code=field.lookup_category).one_or_none()
        items = sorted(cat.items, key=lambda i: (i.sort_order, i.id)) if cat else []
        return ok({
            "source": "lookup", "category": field.lookup_category,
            "category_name": cat.name_fa if cat else field.lookup_category,
            "shared_with": [f.field_name for f in FormField.query.filter_by(
                lookup_category=field.lookup_category).all() if f.id != field.id],
            "options": [i.to_dict() for i in items],
        })
    if source == "months":
        return ok({"source": "months", "options": _month_options(),
                   "readonly": True,
                   "note": "ماه‌های تقویم شمسی ثابت‌اند و ویرایش نمی‌شوند."})
    if source == "wells":
        return ok({"source": "wells", "options": [], "readonly": True,
                   "note": "گزینه‌های این فیلد از جدول «چاه‌ها» خوانده می‌شود؛ "
                           "از صفحه‌ی «چاه‌ها» مدیریت کنید."})
    return ok({"source": "own", "options": [o.to_dict() for o in
                                            sorted(field.options,
                                                   key=lambda o: o.sort_order)]})


@bp.put("/fields/<int:field_id>/options")
@permission_required("form.manage")
def set_field_options(field_id):
    """Save the option list of a field, routing to the right store.

    For a lookup-backed field this edits the shared category, which is what
    the operator means when they open «مرکز» and change its buttons; the UI
    warns them that other fields share that list.
    """
    field = db.session.get(FormField, field_id)
    if field is None:
        return fail("فیلد یافت نشد.", 404)
    source = field.options_source
    if source in ("months", "wells"):
        return fail("گزینه‌های این فیلد از این بخش قابل ویرایش نیستند.", 422)

    options = body().get("options")
    if not isinstance(options, list):
        return fail("فهرست گزینه‌ها ارسال نشده است.", 422)

    if source == "own":
        _sync_options(field, options)
        record_audit("update", "form_field", field.id,
                     summary=f"ویرایش گزینه‌های فیلد «{field.label}»")
        db.session.commit()
        return ok(field.to_dict(active_only=False), message="گزینه‌ها ذخیره شد.")

    cat = LookupCategory.query.filter_by(code=field.lookup_category).one_or_none()
    if cat is None:
        return fail("دسته‌ی گزینه یافت نشد.", 404)

    existing = {i.value: i for i in cat.items}
    seen, created = set(), 0
    for idx, opt in enumerate(options):
        value = normalize_text(opt.get("value") if isinstance(opt, dict) else opt)
        if not value:
            continue
        label = normalize_text(opt.get("label")) if isinstance(opt, dict) else value
        icon = (opt.get("icon") or "").strip() or None if isinstance(opt, dict) else None
        active = (opt.get("is_active", True) in (True, "true", "1", 1)
                  if isinstance(opt, dict) else True)
        seen.add(value)
        item = existing.get(value)
        if item is None:
            item = LookupItem(category_id=cat.id, value=value, label=label or value,
                              icon=icon, sort_order=idx, is_active=active)
            db.session.add(item)
            created += 1
        else:
            item.label = label or value
            item.icon = icon
            item.sort_order = idx
            item.is_active = active
            # "Ad-hoc" means an imported value nobody has vetted yet. Activating
            # it IS the admin vetting it; merely saving the list while leaving
            # it switched off is not, so the flag stays and it keeps showing up
            # for review.
            if active:
                item.is_adhoc = False
    # Options left out are deactivated, never deleted: records point at them.
    for value, item in existing.items():
        if value not in seen:
            item.is_active = False
    record_audit("update", "lookup_item", None,
                 summary=f"ویرایش گزینه‌های «{cat.name_fa}» از فرم‌ساز "
                         f"({created} گزینه جدید)")
    db.session.commit()
    return ok({"source": "lookup", "category": cat.code,
               "options": [i.to_dict() for i in
                           sorted(cat.items, key=lambda i: (i.sort_order, i.id))]},
              message="گزینه‌ها ذخیره شد.")


@bp.post("/reorder")
@permission_required("form.manage")
def reorder_fields():
    payload = body()
    # A field dragged into another section moves there: the page sends where
    # each field now sits, not only in what order. Before, only the order was
    # saved and a moved field sprang back to its old section on reload.
    sections = {s.id for s in FormSection.query.all()}
    moved = []
    for position, row in enumerate(payload.get("placement") or []):
        field = db.session.get(FormField, int(row.get("id") or 0))
        target = int(row.get("section_id") or 0)
        if field is None or target not in sections:
            continue
        if field.section_id != target:
            moved.append(field.label)
            field.section_id = target
        field.sort_order = position
    if moved:
        record_audit("update", "form_field", None,
                     summary="انتقال فیلد به بخش دیگر: " + "، ".join(moved))
    for position, field_id in enumerate(payload.get("fields") or []):
        FormField.query.filter_by(id=int(field_id)).update({"sort_order": position})
    for position, section_id in enumerate(payload.get("sections") or []):
        FormSection.query.filter_by(id=int(section_id)).update({"sort_order": position})
    db.session.commit()
    return ok(message="ترتیب ذخیره شد.")


def _free_name(base: str) -> str:
    """``base_2``, ``base_3``… — the first field name nobody has."""
    base = base[:70]
    n = 2
    while FormField.query.filter_by(field_name=f"{base}_{n}").first():
        n += 1
    return f"{base}_{n}"


@bp.post("/fields/<int:field_id>/copy")
@permission_required("form.manage")
def copy_field(field_id):
    """A second field built like this one, in the section asked for.

    A copy is its own field with its own answers — «قطر لوله» in «مشخصات
    پمپ» and again in «جدار چاه». Its settings, options and «برداشت از
    سوابق» come along; a built-in field's copy stores its answers as a form-
    builder value, since the record column belongs to the original.
    """
    source = db.session.get(FormField, field_id)
    if source is None:
        return fail("فیلد یافت نشد.", 404)
    payload = body()
    section = db.session.get(FormSection, int(payload.get("section_id") or 0))
    if section is None:
        return fail("بخش مقصد را انتخاب کنید.", 422)
    copy = FormField(
        section_id=section.id, field_name=_free_name(source.field_name),
        label=normalize_text(payload.get("label")) or source.label,
        field_type=source.field_type, model_attr=None,
        lookup_category=source.lookup_category,
        placeholder=source.placeholder, help_text=source.help_text,
        default_value=source.default_value, is_required=source.is_required,
        is_active=True, is_builtin=False, allow_other=source.allow_other,
        sort_order=max([f.sort_order for f in section.fields], default=0) + 1,
        col_span=source.col_span, min_value=source.min_value,
        max_value=source.max_value, max_length=source.max_length, step=source.step,
        visible_when=source.visible_when, prefill_from=source.prefill_from,
        show_in_table=False, table_order=0,
        export_header=(source.export_header or source.label) + f" ({section.title})",
    )
    db.session.add(copy)
    db.session.flush()
    for opt in source.options:
        db.session.add(FormFieldOption(field_id=copy.id, value=opt.value,
                                       label=opt.label, icon=opt.icon,
                                       sort_order=opt.sort_order,
                                       is_active=opt.is_active))
    record_audit("create", "form_field", copy.id,
                 summary=f"کپی فیلد «{source.label}» در بخش «{section.title}»")
    db.session.commit()
    return ok(copy.to_dict(active_only=False),
              message=f"کپی «{source.label}» در بخش «{section.title}» ساخته شد.")


# ── which choice opens which form ────────────────────────────────────────────
#
# «علت خرابی ← فرم» as a table the admin edits, rather than a rule typed into
# each section. The links live where they always did — a section's
# ``visible_when`` — so the stage forms, the entry page and the server's
# required-field check all read the same thing; this is only a better way to
# see and change them. A section keyed on the field but linked to nothing is
# stored as «field=» and opens for nothing, rather than for everything.
def _choice_sources():
    """Choice fields a form can be hung off — the ones that have options."""
    out = []
    for f in (FormField.query.filter(FormField.is_active.is_(True))
              .order_by(FormField.sort_order).all()):
        if f.field_type in ("checkbox", "multiselect", "radio", "select",
                            "checklist", "autocomplete") \
                and (f.lookup_category or f.options) and f.field_name != "well":
            out.append(f)
    return out


def _options_of(field):
    if field.options:
        return [{"value": o.value, "label": o.label or o.value}
                for o in field.options if o.is_active]
    cat = LookupCategory.query.filter_by(code=field.lookup_category).first()
    if cat is None:
        return []
    return [{"value": i.value, "label": i.label or i.value}
            for i in sorted(cat.items, key=lambda x: x.sort_order) if i.is_active]


def _links_on(section, field_name):
    from ..services.conditions import rule_for
    return rule_for(section.visible_when, field_name)


@bp.get("/cause-links")
@permission_required("form.manage")
def cause_links():
    name = request.args.get("field") or "failure"
    field = FormField.query.filter_by(field_name=name).first()
    if field is None:
        return fail("فیلد مبنا یافت نشد.", 404)
    options = _options_of(field)
    forms, others = [], []
    for sec in (FormSection.query.filter(FormSection.is_active.is_(True))
                .order_by(FormSection.sort_order).all()):
        links = _links_on(sec, name)
        row = {"id": sec.id, "code": sec.code, "title": sec.title,
               "icon": sec.icon, "process_only": sec.show_on_entry is False,
               "field_count": len([f for f in sec.fields if f.is_active])}
        if links is None:
            # Offered for linking, with a warning when it currently shows for
            # everybody: linking it makes it conditional.
            # Already opened by another question: linking it here adds a
            # second way in, it does not take the first one away.
            row["has_rule"] = bool((sec.visible_when or "").strip())
            row["linked_elsewhere"] = bool((sec.visible_when or "").strip())
            if sec.id != field.section_id:
                others.append(row)
        else:
            row["causes"] = links
            forms.append(row)
    # Single fields can be opened by a choice too — «قطر لوله» only when
    # «جنس جدار = فولادی». Keyed «field:<name>» so they sit beside the forms.
    field_links, field_others = [], []
    for f in (FormField.query.filter(FormField.is_active.is_(True))
              .order_by(FormField.section_id, FormField.sort_order).all()):
        if f.id == field.id:
            continue
        row = {"code": "field:" + f.field_name, "title": f.label,
               "section_title": f.section.title if f.section else None}
        from ..services.conditions import rule_for
        mine = rule_for(f.visible_when, name)
        if mine is not None:
            row["causes"] = mine
            field_links.append(row)
        else:
            row["has_rule"] = bool((f.visible_when or "").strip())
            field_others.append(row)
    for opt in options:
        opt["forms"] = ([f["code"] for f in forms if opt["value"] in f["causes"]]
                        + [f["code"] for f in field_links
                           if opt["value"] in f["causes"]])
    return ok({
        "field": {"name": field.field_name, "label": field.label},
        "sources": [{"name": f.field_name, "label": f.label,
                     "section_title": f.section.title if f.section else None}
                    for f in _choice_sources()],
        "causes": options, "forms": forms, "others": others,
        "field_links": field_links, "field_others": field_others,
    })


@bp.put("/cause-links")
@permission_required("form.manage")
def save_cause_links():
    payload = body()
    name = payload.get("field") or "failure"
    field = FormField.query.filter_by(field_name=name).first()
    if field is None:
        return fail("فیلد مبنا یافت نشد.", 404)
    allowed = {o["value"] for o in _options_of(field)}
    links = payload.get("links") or {}
    if not isinstance(links, dict):
        return fail("ساختار اتصال‌ها نامعتبر است.", 422)
    changed = 0
    for code, values in links.items():
        if code.startswith("field:"):
            target = FormField.query.filter_by(field_name=code[6:]).first()
            if target is None:
                return fail(f"فیلد «{code[6:]}» یافت نشد.", 404)
            if target.id == field.id:
                return fail("یک فیلد نمی‌تواند به خودش وصل شود.", 422)
            picked = [v for v in dict.fromkeys(values or []) if v in allowed]
            # Only this question's rule changes; links to other questions stay.
            # A field left with no rule at all is an ordinary field again.
            from ..services.conditions import with_rule
            rule = with_rule(target.visible_when, name, picked or None)
            if target.visible_when != rule:
                target.visible_when = rule
                changed += 1
            continue
        section = FormSection.query.filter_by(code=code).first()
        if section is None:
            return fail(f"فرم «{code}» یافت نشد.", 404)
        if section.id == field.section_id:
            return fail("فرمی که خود «" + field.label + "» در آن است نمی‌تواند "
                        "به آن وصل شود.", 422)
        picked = [v for v in dict.fromkeys(values or []) if v in allowed]
        from ..services.conditions import with_rule
        rule = with_rule(section.visible_when, name, picked)
        if section.visible_when != rule:
            section.visible_when = rule
            changed += 1
    record_audit("update", "form_section", None,
                 summary=f"ویرایش اتصال «{field.label}» به فرم‌ها ({changed} فرم)")
    db.session.commit()
    return ok({"changed": changed}, message="اتصال‌ها ذخیره شد.")
