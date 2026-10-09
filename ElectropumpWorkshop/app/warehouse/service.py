"""The warehouse ledger: seeding, posting from the process, stock and reports.

A form field of type «اقلام انبار» (``wh_lines``) is a small table — item,
specification (e.g. «384/10+73.5»), plaque/serial, condition, quantity — and
its settings (``wh_config``) say which warehouse it moves stock in or out of
and why. When a stage is sent, every such answer of that stage is written to
the ledger, replacing what the same stage of the same process wrote before,
so sending a stage again (after a return) never counts the items twice.
"""
from __future__ import annotations

import io
import json
import logging

from ..extensions import db
from .models import DIRECTIONS, KINDS, REASONS, WAREHOUSES, WhCondition, WhItem, WhMovement

log = logging.getLogger(__name__)

SEED_KEY = "warehouse_seed_v1"

CONDITIONS = [
    ("reusable", "قابل استفاده مجدد", "equipment,part", "#16a34a"),
    ("repair", "تعمیری", "equipment,part", "#d97706"),
    ("new", "نو (خریداری‌شده)", "equipment,part", "#2563eb"),
    ("scrap", "اسقاط", "equipment,part", "#dc2626"),
    ("assembled", "مونتاژشده — آماده نصب", "equipment", "#7c3aed"),
]

# A proposal to start with; the real catalogue replaces it («ورود از اکسل»).
ITEMS = [
    ("EQ-01", "الکتروموتور شناور", "equipment", "الکتروموتور", "دستگاه"),
    ("EQ-02", "پمپ شناور", "equipment", "پمپ", "دستگاه"),
    ("EQ-03", "الکتروپمپ کامل (مونتاژشده)", "equipment", "الکتروپمپ", "دستگاه"),
    ("PT-01", "پروانه (ایمپلر)", "part", "پمپ", "عدد"),
    ("PT-02", "دیفیوزر / بدنه طبقه", "part", "پمپ", "عدد"),
    ("PT-03", "شفت پمپ", "part", "پمپ", "عدد"),
    ("PT-04", "بوش و یاتاقان", "part", "پمپ", "عدد"),
    ("PT-05", "کوپلینگ", "part", "پمپ", "عدد"),
    ("PT-06", "سرپمپ (دهانه خروجی)", "part", "پمپ", "عدد"),
    ("PT-07", "صافی / توری مکش", "part", "پمپ", "عدد"),
    ("PT-08", "شیر یک‌طرفه", "part", "پمپ", "عدد"),
    ("PT-09", "مکانیکال سیل", "part", "الکتروموتور", "عدد"),
    ("PT-10", "بلبرینگ", "part", "الکتروموتور", "عدد"),
    ("PT-11", "اورینگ و کاسه‌نمد", "part", "الکتروموتور", "دست"),
    ("PT-12", "سیم‌پیچ الکتروموتور", "part", "الکتروموتور", "دست"),
    ("PT-13", "مایع / روغن الکتروموتور", "part", "الکتروموتور", "لیتر"),
    ("PT-14", "کابل رابط تخت", "part", "کابل", "متر"),
    ("PT-15", "مفصل کابل", "part", "کابل", "عدد"),
    ("PT-16", "گارد کابل", "part", "پمپ", "عدد"),
    ("PT-17", "پیچ و مهره", "part", "اتصالات", "عدد"),
    ("PT-18", "واشر", "part", "اتصالات", "عدد"),
]


def seed_warehouse() -> dict:
    """Condition classes always; the proposed items only into an empty book."""
    added = {"conditions": 0, "items": 0}
    have = {c.code for c in WhCondition.query.all()}
    for n, (code, label, applies, color) in enumerate(CONDITIONS):
        if code not in have:
            db.session.add(WhCondition(code=code, label=label, applies_to=applies,
                                       color=color, sort_order=n))
            added["conditions"] += 1
    if not WhItem.query.count():
        for n, (code, name, kind, cat, unit) in enumerate(ITEMS):
            db.session.add(WhItem(code=code, name=name, kind=kind, category=cat,
                                  unit=unit, sort_order=n, source="پیشنهادی"))
            added["items"] += 1
    if any(added.values()):
        db.session.commit()
    return added


def catalogue() -> dict:
    """What a form needs to draw «اقلام انبار» rows."""
    from .models import WhEquipment
    return {
        "equipment": [{"code": e.code, "name": e.name, "kind": e.kind}
                      for e in WhEquipment.query.order_by(WhEquipment.code)],
        "items": [i.to_dict() for i in WhItem.query.filter_by(is_active=True)
                  .order_by(WhItem.kind, WhItem.sort_order, WhItem.id)],
        "conditions": [c.to_dict() for c in WhCondition.query.filter_by(is_active=True)
                       .order_by(WhCondition.sort_order)],
        "warehouses": WAREHOUSES, "kinds": KINDS, "reasons": REASONS,
        "directions": DIRECTIONS,
    }


def parse_config(text) -> dict:
    try:
        cfg = json.loads(text) if isinstance(text, str) and text.strip() else (text or {})
    except ValueError:
        cfg = {}
    cfg = dict(cfg) if isinstance(cfg, dict) else {}
    cfg.setdefault("warehouse", "equipment")
    cfg.setdefault("direction", "in")
    cfg.setdefault("reason", "manual")
    return cfg


def clean_lines(value) -> list:
    """The rows of an answer, as a list of dicts with a positive quantity."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return []
    out = []
    for row in value or []:
        if not isinstance(row, dict):
            continue
        name = str(row.get("item_name") or row.get("item") or "").strip()
        item_id = row.get("item_id")
        if not name and not item_id:
            continue
        try:
            qty = float(str(row.get("qty") or 1).replace("٫", "."))
        except ValueError:
            qty = 1.0
        if qty <= 0:
            continue
        out.append({"item_id": int(item_id) if str(item_id or "").isdigit() else None,
                    "item_name": name, "qty": qty,
                    "condition": (row.get("condition") or "").strip() or None,
                    "spec": (str(row.get("spec") or "").strip() or None),
                    "serial": (str(row.get("serial") or "").strip() or None),
                    "note": (str(row.get("note") or "").strip() or None)})
    return out


PART_COLUMNS = [("installed_new", "نصب — نو"), ("installed_repair", "نصب — کهنه (قابل استفاده مجدد)"),
                ("collected_new", "جمع‌آوری — نو"), ("collected_old", "جمع‌آوری — کهنه"),
                ("reusable", "قابل استفاده مجدد"), ("scrap", "اسقاط")]


def clean_parts(value) -> list:
    """A parts-form answer: rows with at least one count."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return []
    out = []
    for row in value or []:
        if not isinstance(row, dict) or not (row.get("item_id") or row.get("item_name")):
            continue
        counts = {}
        for key, _label in PART_COLUMNS:
            try:
                n = float(str(row.get(key) or 0).replace("٫", "."))
            except ValueError:
                n = 0
            if n > 0:
                counts[key] = n
        if not counts and not (row.get("note") or "").strip():
            continue
        out.append({"item_id": int(row["item_id"]) if str(row.get("item_id") or "").isdigit() else None,
                    "item_name": str(row.get("item_name") or "").strip(),
                    "code": str(row.get("code") or "").strip() or None,
                    "note": (str(row.get("note") or "").strip() or None), **counts})
    return out


def is_parts_answer(value) -> bool:
    rows = value
    if isinstance(rows, str):
        try:
            rows = json.loads(rows)
        except ValueError:
            return False
    return bool(rows) and isinstance(rows, list) and isinstance(rows[0], dict) and any(
        k in rows[0] for k, _l in PART_COLUMNS)


def parts_text(value) -> str:
    parts = []
    for r in clean_parts(value):
        bits = [f"{lab} {_n(r[k])}" for k, lab in PART_COLUMNS if r.get(k)]
        parts.append(f"{r['item_name']}: " + "، ".join(bits) + (f" ({r['note']})" if r.get("note") else ""))
    return "؛ ".join(parts)


def _n(q):
    return str(int(q)) if float(q).is_integer() else str(q)


def lines_text(value) -> str:
    """One answer as text, for summaries and exports."""
    if is_parts_answer(value):
        return parts_text(value)
    conds = {c.code: c.label for c in WhCondition.query.all()}
    parts = []
    for r in clean_lines(value):
        name = r["item_name"]
        if not name and r["item_id"]:
            item = db.session.get(WhItem, r["item_id"])
            name = item.name if item else "?"
        bits = [name]
        if r["spec"]:
            bits.append(r["spec"])
        if r["serial"]:
            bits.append(f"پلاک {r['serial']}")
        if r["condition"]:
            bits.append(conds.get(r["condition"], r["condition"]))
        q = r["qty"]
        bits.append(f"{int(q) if float(q).is_integer() else q} عدد")
        parts.append(" — ".join(bits))
    return "؛ ".join(parts)


def post_stage(instance, stage, data: dict, user=None) -> int:
    """Write this stage's «اقلام انبار» answers to the ledger (replacing)."""
    from ..models import FormField
    fields = FormField.query.filter_by(field_type="wh_lines", is_active=True).all()
    if not fields:
        return 0
    from ..services.jalali import today_jalali
    jy, jm, jd = today_jalali()
    jdate = f"{jy}/{jm:02d}/{jd:02d}"
    written = 0
    for field in fields:
        if field.field_name not in data:
            continue
        WhMovement.query.filter_by(instance_id=instance.id, stage_number=stage.stage_number,
                                   field_name=field.field_name).delete()
        cfg = parse_config(field.wh_config)
        if cfg.get("mode") == "parts":
            written += _post_parts(instance, stage, field, cfg, data, user, jdate, jy, jm, jd)
            continue
        for r in clean_lines(data.get(field.field_name)):
            item = db.session.get(WhItem, r["item_id"]) if r["item_id"] else None
            db.session.add(WhMovement(
                jdate=jdate, date_num=jy * 10000 + jm * 100 + jd,
                warehouse=cfg["warehouse"], direction=cfg["direction"], reason=cfg["reason"],
                item_id=item.id if item else None,
                item_name=(item.name if item else r["item_name"]) or "?",
                item_kind=item.kind if item else None, unit=item.unit if item else None,
                qty=r["qty"], condition=r["condition"] or cfg.get("default_condition"),
                spec=r["spec"], serial=r["serial"], note=r["note"],
                instance_id=instance.id,
                workflow_name=instance.workflow.name if instance.workflow else None,
                stage_number=stage.stage_number, stage_title=stage.title,
                field_name=field.field_name, well_id=instance.well_id,
                well_name=(instance.well.name if instance.well else instance.well_name_raw),
                user_id=getattr(user, "id", None),
                user_name=getattr(user, "full_name", None)))
            written += 1
    return written


def _post_parts(instance, stage, field, cfg, data, user, jdate, jy, jm, jd) -> int:
    """A parts form: counts per part → part actions and parts-warehouse moves.

    نصب (نو / تعمیری) leaves the parts warehouse; what was جمع‌آوری and judged
    قابل استفاده مجدد or اسقاط enters it under that condition. Every count is
    also kept as a part action, the same kind of row as the 98–05 history."""
    from .models import WhPartAction
    WhPartAction.query.filter_by(instance_id=instance.id, stage_number=stage.stage_number,
                                 field_name=field.field_name).delete()
    eq_code = str(data.get(cfg.get("equipment_field") or "", "") or "").strip() or None
    pick = lambda k: (str(data.get(cfg.get(k) or "", "") or "").strip() or None)  # noqa: E731
    well = instance.well.name if instance.well else instance.well_name_raw
    common = dict(jdate=jdate, date_num=jy * 10000 + jm * 100 + jd, year=jy, month=jm,
                  equipment_code=eq_code, equipment_kind=cfg.get("equipment_type"),
                  related_action=cfg.get("related_action"), failure=pick("failure_field"),
                  cause=pick("cause_field"), action_done=pick("action_field"),
                  instance_id=instance.id, stage_number=stage.stage_number,
                  field_name=field.field_name, well_id=instance.well_id, well_name=well,
                  user_name=getattr(user, "full_name", None), source="workflow",
                  facility_name=well)
    moves = 0
    for r in clean_parts(data.get(field.field_name)):
        item = db.session.get(WhItem, r["item_id"]) if r["item_id"] else None
        name = item.name if item else r["item_name"]
        if item is not None and item.note and "کد انباری" in item.note:
            code = item.note.replace("کد انباری", "").strip()
        elif item is not None and item.code:
            code = item.code[:-2] if item.code.endswith("-P") else item.code
        else:
            code = r.get("code")
        acts = [("installed", "نو", None, r.get("installed_new")),
                ("installed", "کهنه", None, r.get("installed_repair")),
                ("collected", "نو", None, r.get("collected_new")),
                ("collected", "کهنه", None, r.get("collected_old")),
                ("collected", None, True, r.get("reusable")),
                ("collected", None, False, r.get("scrap"))]
        for pact, state, reuse, q in acts:
            if q:
                db.session.add(WhPartAction(part_action=pact, state=state, reusable=reuse,
                                            part_code=code, part_name=name, qty=q,
                                            note=r.get("note"), **common))
        # the parts warehouse: a used part put back into a motor or pump
        # comes out of the «قابل استفاده مجدد» stock that disassembly fills
        for key, direction, condition, reason in (
                ("installed_new", "out", "new", "assembly"),
                ("installed_repair", "out", "reusable", "assembly"),
                ("reusable", "in", "reusable", "disassembly"),
                ("scrap", "in", "scrap", "disassembly")):
            if r.get(key):
                db.session.add(WhMovement(
                    jdate=jdate, date_num=jy * 10000 + jm * 100 + jd, warehouse="parts",
                    direction=direction, reason=reason, item_id=item.id if item else None,
                    item_name=name or "?", item_kind="part", unit=item.unit if item else "عدد",
                    qty=r[key], condition=condition, spec=cfg.get("equipment_type"),
                    serial=eq_code, note=r.get("note"), instance_id=instance.id,
                    workflow_name=instance.workflow.name if instance.workflow else None,
                    stage_number=stage.stage_number, stage_title=stage.title,
                    field_name=field.field_name, well_id=instance.well_id, well_name=well,
                    user_id=getattr(user, "id", None), user_name=getattr(user, "full_name", None)))
                moves += 1
    return moves


def parts_summary(args) -> dict:
    """Parts installed and collected — by part, equipment kind, year and month."""
    from .models import WhPartAction
    q = WhPartAction.query
    if args.get("equipment_kind"):
        q = q.filter(WhPartAction.equipment_kind == args["equipment_kind"])
    if args.get("source"):
        q = q.filter(WhPartAction.source == args["source"])
    from ..refdata.textnorm import jdate_num
    if args.get("date_from") and jdate_num(args["date_from"]):
        q = q.filter(WhPartAction.date_num >= jdate_num(args["date_from"]))
    if args.get("date_to") and jdate_num(args["date_to"]):
        q = q.filter(WhPartAction.date_num <= jdate_num(args["date_to"]))
    if args.get("equipment_code"):
        q = q.filter(WhPartAction.equipment_code.contains(args["equipment_code"]))
    by_part, by_kind, by_year = {}, {}, {}
    total = {"installed_new": 0, "installed_repair": 0, "installed_unknown": 0,
             "collected": 0, "reusable": 0, "scrap": 0, "rows": 0}
    equipments = set()
    for a in q.all():
        qty = a.qty or 0
        total["rows"] += 1
        if a.equipment_code:
            equipments.add(a.equipment_code)
        key = (a.equipment_kind or "—", a.part_code or "", a.part_name or "?")
        row = by_part.setdefault(key, {"equipment_kind": key[0], "part_code": key[1], "part_name": key[2],
                                       "installed_new": 0, "installed_repair": 0, "installed_unknown": 0,
                                       "collected": 0, "reusable": 0, "scrap": 0})
        kind = by_kind.setdefault(a.equipment_kind or "—", {"equipment_kind": a.equipment_kind or "—",
                                                            "installed": 0, "collected": 0, "reusable": 0, "scrap": 0})
        year = by_year.setdefault(a.year or 0, {"year": a.year, "installed": 0, "collected": 0,
                                                "new": 0, "repair": 0, "reusable": 0, "scrap": 0})
        if a.part_action == "installed":
            k = ("installed_new" if a.state == "نو" else "installed_repair" if a.state == "کهنه"
                 else "installed_unknown")
            row[k] += qty
            total[k] += qty
            kind["installed"] += qty
            year["installed"] += qty
            if a.state == "نو":
                year["new"] += qty
            elif a.state == "کهنه":
                year["repair"] += qty
        else:
            if a.reusable is True:
                row["reusable"] += qty
                total["reusable"] += qty
                kind["reusable"] += qty
                year["reusable"] += qty
            elif a.reusable is False:
                row["scrap"] += qty
                total["scrap"] += qty
                kind["scrap"] += qty
                year["scrap"] += qty
            else:
                row["collected"] += qty
                total["collected"] += qty
                kind["collected"] += qty
                year["collected"] += qty
    parts = sorted(by_part.values(), key=lambda r: -(r["installed_new"] + r["installed_repair"]
                                                      + r["installed_unknown"] + r["collected"]))
    total["equipments"] = len(equipments)
    return {"total": total, "by_part": parts,
            "by_kind": sorted(by_kind.values(), key=lambda r: r["equipment_kind"]),
            "by_year": sorted((v for v in by_year.values() if v["year"]), key=lambda r: r["year"])}


# ── stock and reports ────────────────────────────────────────────────────────
def _filtered(args):
    q = WhMovement.query
    if args.get("warehouse"):
        q = q.filter(WhMovement.warehouse == args["warehouse"])
    if args.get("direction"):
        q = q.filter(WhMovement.direction == args["direction"])
    if args.get("condition"):
        q = q.filter(WhMovement.condition == args["condition"])
    if args.get("reason"):
        q = q.filter(WhMovement.reason == args["reason"])
    if args.get("item_id"):
        q = q.filter(WhMovement.item_id == int(args["item_id"]))
    if args.get("well"):
        q = q.filter(WhMovement.well_name.contains(args["well"]))
    from ..refdata.textnorm import jdate_num
    if args.get("date_from") and jdate_num(args["date_from"]):
        q = q.filter(WhMovement.date_num >= jdate_num(args["date_from"]))
    if args.get("date_to") and jdate_num(args["date_to"]):
        q = q.filter(WhMovement.date_num <= jdate_num(args["date_to"]))
    return q


def movements(args, limit=2000) -> list:
    return [m.to_dict() for m in _filtered(args)
            .order_by(WhMovement.date_num.desc(), WhMovement.id.desc()).limit(limit)]


def stock(args=None) -> list:
    """Balance per warehouse, item and condition (in − out)."""
    args = args or {}
    conds = {c.code: c.label for c in WhCondition.query.all()}
    rows = {}
    q = WhMovement.query
    if args.get("warehouse"):
        q = q.filter(WhMovement.warehouse == args["warehouse"])
    for m in q.all():
        key = (m.warehouse, m.item_id or m.item_name, m.condition or "")
        r = rows.setdefault(key, {"warehouse": m.warehouse,
                                  "warehouse_label": WAREHOUSES.get(m.warehouse, m.warehouse),
                                  "item_id": m.item_id, "item_name": m.item_name,
                                  "unit": m.unit, "condition": m.condition,
                                  "condition_label": conds.get(m.condition, m.condition or "—"),
                                  "in": 0.0, "out": 0.0})
        r["in" if m.direction == "in" else "out"] += m.qty or 0
    out = []
    for r in rows.values():
        r["balance"] = round(r["in"] - r["out"], 3)
        out.append(r)
    out.sort(key=lambda r: (r["warehouse"], str(r["item_name"]), str(r["condition"])))
    return out


def summary(args) -> dict:
    """The manager's report: what moved, by warehouse, reason and condition."""
    conds = {c.code: c.label for c in WhCondition.query.all()}
    q = _filtered(args).all()
    by_reason, by_cond, by_item = {}, {}, {}
    instances = {"pull": set(), "assembled": set(), "install": set()}
    for m in q:
        key = (m.warehouse, m.direction, m.reason)
        by_reason[key] = by_reason.get(key, 0) + (m.qty or 0)
        ck = (m.warehouse, m.direction, m.condition or "")
        by_cond[ck] = by_cond.get(ck, 0) + (m.qty or 0)
        ik = (m.warehouse, m.item_name, m.condition or "", m.direction)
        by_item[ik] = by_item.get(ik, 0) + (m.qty or 0)
        if m.reason in instances and m.instance_id:
            instances[m.reason].add(m.instance_id)
    return {
        "headline": {
            "electropumps_pulled": len(instances["pull"]),
            "electropumps_assembled": len(instances["assembled"]),
            "electropumps_installed": len(instances["install"]),
            "parts_scrapped": sum(m.qty or 0 for m in q if m.condition == "scrap"),
            "parts_new": sum(m.qty or 0 for m in q if m.condition == "new" and m.direction == "out"),
            "parts_reused": sum(m.qty or 0 for m in q
                                if m.condition == "reusable" and m.direction == "out"),
            "movements": len(q),
        },
        "by_reason": [{"warehouse": WAREHOUSES.get(w, w), "direction": DIRECTIONS.get(d, d),
                       "reason": REASONS.get(r, r), "qty": round(v, 3)}
                      for (w, d, r), v in sorted(by_reason.items())],
        "by_condition": [{"warehouse": WAREHOUSES.get(w, w), "direction": DIRECTIONS.get(d, d),
                          "condition": conds.get(c, c or "—"), "qty": round(v, 3)}
                         for (w, d, c), v in sorted(by_cond.items())],
        "parts": parts_summary(args),
        "by_item": [{"warehouse": WAREHOUSES.get(w, w), "item": i,
                     "condition": conds.get(c, c or "—"), "direction": DIRECTIONS.get(d, d),
                     "qty": round(v, 3)}
                    for (w, i, c, d), v in sorted(by_item.items(), key=lambda kv: (kv[0][0], str(kv[0][1])))],
    }


def add_manual(payload: dict, user=None) -> WhMovement:
    from ..refdata.textnorm import jdate_num, to_jdate
    from ..services.jalali import today_jalali
    wh = payload.get("warehouse")
    if wh not in WAREHOUSES:
        raise ValueError("انبار را انتخاب کنید.")
    direction = payload.get("direction")
    if direction not in DIRECTIONS:
        raise ValueError("ورود یا خروج را مشخص کنید.")
    item = db.session.get(WhItem, int(payload["item_id"])) if str(payload.get("item_id") or "").isdigit() else None
    if item is None:
        raise ValueError("کالا را از فهرست اقلام انتخاب کنید.")
    try:
        qty = float(str(payload.get("qty") or "").replace("٫", "."))
    except ValueError:
        qty = 0
    if qty <= 0:
        raise ValueError("تعداد / مقدار باید بیشتر از صفر باشد.")
    jy, jm, jd = today_jalali()
    jdate = to_jdate(payload.get("jdate")) or f"{jy}/{jm:02d}/{jd:02d}"
    reason = payload.get("reason") if payload.get("reason") in REASONS else "manual"
    m = WhMovement(jdate=jdate, date_num=jdate_num(jdate), warehouse=wh, direction=direction,
                   reason=reason, item_id=item.id, item_name=item.name, item_kind=item.kind,
                   unit=item.unit, qty=qty, condition=payload.get("condition") or None,
                   spec=(payload.get("spec") or None), serial=(payload.get("serial") or None),
                   note=(payload.get("note") or None), well_name=(payload.get("well") or None),
                   user_id=getattr(user, "id", None), user_name=getattr(user, "full_name", None))
    db.session.add(m)
    db.session.commit()
    return m


# ── items to and from Excel ──────────────────────────────────────────────────
ITEM_COLUMNS = [("code", "کد کالا"), ("name", "نام کالا"), ("kind", "نوع (تجهیز/قطعه)"),
                ("category", "گروه"), ("unit", "واحد"), ("is_active", "فعال"),
                ("note", "توضیحات")]


def items_xlsx() -> bytes:
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "اقلام انبار"
    ws.sheet_view.rightToLeft = True
    ws.append([lab for _k, lab in ITEM_COLUMNS])
    for i in WhItem.query.order_by(WhItem.kind, WhItem.sort_order, WhItem.id):
        ws.append([i.code, i.name, "تجهیز" if i.kind == "equipment" else "قطعه",
                   i.category, i.unit, "بله" if i.is_active else "خیر", i.note])
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def import_items(data: bytes) -> dict:
    """Upsert items from a sheet: «کد کالا»/«نام کالا» columns at least."""
    from openpyxl import load_workbook
    from ..refdata.textnorm import norm_label, norm_text, to_text
    wb = load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    ws = wb.worksheets[0]
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    hdr = next((i for i, r in enumerate(rows[:10]) if any(
        isinstance(v, str) and norm_label(v).startswith(("نام کالا", "نام قطعه", "شرح کالا"))
        for v in r)), None)
    if hdr is None:
        raise ValueError("ستون «نام کالا» در سطرهای اول فایل پیدا نشد.")
    head = [norm_label(v) if isinstance(v, str) else "" for v in rows[hdr]]

    def col(*names):
        return next((c for c, h in enumerate(head) for n in names if h.startswith(n)), None)
    c_code, c_name = col("کد کالا", "کد"), col("نام کالا", "نام قطعه", "شرح کالا")
    c_kind, c_cat, c_unit = col("نوع"), col("گروه", "دسته"), col("واحد")
    c_active, c_note = col("فعال"), col("توضیحات")
    added = updated = 0
    top = (db.session.query(db.func.max(WhItem.sort_order)).scalar() or 0) + 1
    for n, r in enumerate(rows[hdr + 1:]):
        def cell(c):
            return r[c] if c is not None and c < len(r) else None
        name = to_text(cell(c_name))
        if not name:
            continue
        code = to_text(cell(c_code))
        item = (WhItem.query.filter_by(code=code).first() if code else None) or \
            WhItem.query.filter_by(name=name).first()
        if item is None:
            item = WhItem(name=name, code=code, sort_order=top + n)
            db.session.add(item)
            added += 1
        else:
            updated += 1
        kind = norm_text(cell(c_kind) or "")
        item.name = name
        item.code = code or item.code
        item.kind = "equipment" if ("تجهیز" in kind or "equip" in kind.lower()) else (
            "part" if kind else item.kind or "part")
        item.category = to_text(cell(c_cat)) or item.category
        item.unit = to_text(cell(c_unit)) or item.unit or "عدد"
        active = norm_text(cell(c_active) or "")
        item.is_active = not active.startswith(("خیر", "0", "no", "غیر"))
        item.note = to_text(cell(c_note)) or item.note
        item.source = "ورود از اکسل"
    db.session.commit()
    return {"added": added, "updated": updated}
