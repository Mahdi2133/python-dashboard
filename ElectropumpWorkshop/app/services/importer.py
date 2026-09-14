# -*- coding: utf-8 -*-
"""Excel import (requirement 23) and localStorage migration (requirement 42).

The workshop workbook has a two-row header (a merged group title above a
sub-title) and a different column layout per year sheet, so the importer
detects headers rather than assuming positions, then maps each detected
header onto a target field. The mapping is returned to the browser for
review and can be corrected before anything is written.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import logging
import re

from ..extensions import db
from ..models import ImportBatch, LookupItem, Record
from .audit import record_audit
from .jalali import local_now, normalize_digits, parse_jalali
from .lookups import normalize_text
from .records import ValidationError, apply_payload, split_pump_type

log = logging.getLogger(__name__)

# Header text seen in the sheets → payload key understood by apply_payload().
# Left side is normalised (spaces collapsed, ي/ك folded) before lookup.
HEADER_MAP = {
    "ردیف": None, "رديف": None, "ی": None,
    "روز": "j_day", "ماه": "j_month", "سال": "j_year", "تاریخ": "__date__",
    "تاريخ": "__date__",
    "نام چاه": "well", "مرکز": "center", "شیفت کاری": "shift",
    "شرح خرابی از نظر بهره بردار": "failure", "نوع عیب": "failure", "نوع عيب": "failure",
    "شرح خرابی از نظر کارگاه مکانیک": "workshop_note",
    "كشيدن/نصب/جمع آوری /نصب جدید": "operation",
    "كشيدن/نصب/جمع آوری": "operation", "کشیدن/نصب/جمع آوری": "operation",
    "فرم نصب در pm": "pm", "فرم": "pm",
    "نام پيمانكار": "contractor", "نام پیمانکار": "contractor",
    "مجری": "executor",
    "تیپ الکترو موتور قبلی": "motor_prev", "تیپ الکترو موتور فعلی": "motor_curr",
    "الکترو موتور": "motor_curr", "موتور": "motor_curr",
    "تیپ پمپ قبلی": "pump_prev", "تیپ پمپ فعلی": "pump_curr", "پمپ": "pump_curr",
    "طبقه": "pump_stages",
    "سیم پیچی / سرویس": "motor_rewind",
    "تغییر تیپ": "type_change",
    "تاريخ نصب قبلي": "prev_install_date", "تاریخ نصب قبلی": "prev_install_date",
    "عمق چاه": "well_depth",
    "عمق نصب(قبلی)": "prev_install_depth", "عمق نصب(فعلی)": "curr_install_depth",
    "عمق نصب": "curr_install_depth",
    "سطح استاتیک": "static_level", "سطح دینامیک": "dynamic_level",
    "تلفات مسیر": "path_loss", "فشار شبکه(متر)": "network_pressure",
    "هد کلی (متر)": "total_head", "دبی طراحی": "design_flow", "دبی مجاز": "design_flow",
    "قطر لوله آبده ( اینچ )": "pipe_diameter",
    "تغییر تیپ کابل": "cable_type_change", "تغییر سایز کابل": "cable_size_change",
    "تاریخ آزمایش پمپاژ کارگاه مکانیک": "test_date", "تاریخ آزمایش پمپاژ": "test_date",
    "فشار آزمایش پمپاژ": "test_pressure", "دبی آزمایش پمپاژ": "test_flow",
    "نام چاه استفاذه شده": "cable_well", "نام چاه استفاده شده": "cable_well",
    "راه انداز": "starter", "سایز کابل": "cable_size",
    "سال کشیدن فعلی": "pull_year", "ماه کشیدن فعلی": "pull_month",
    "سال نصب قدیم": "old_install_year", "ماه نصب قدیم": "old_install_month",
    "سال نصب جدید": "pull_year", "ماه نصب جدید": "pull_month",
    "تعداد ماه های کارکرد": "working_months",
    "چاههای با عمر کمتر از یک سال": "young_wells",
    "نظر کارگاه مکانیک": "workshop_opinion",
    "توضیحات": "description", "توضيحات": "description",
    "ناظر نصب": "install_supervisor",
    "دبی پس از نصب پمپ جدید": "flow_after_install",
    "دبي قبل از كشيدن": "flow_before_pull",
    "دبي بعد از نصب": "flow_after_install",
    "تاريخ دبي قبل از كشيدن": "flow_before_pull_date",
    "تاريخ دبي بعد از نصب": "flow_after_install_date",
    "متراژ لوله کشیده شده(کشیدن لوله جدار)": "casing_length",
    "قطر جدار کشیده شده": "casing_pulled_diameter",
    "تعداد ترمیم": "casing_repair_count",
    "جنس جدار": "casing_material", "قطر جدار": "casing_diameter",
    "مستندات": "documents_ref",
    "اعلام شده به مالی": "reported_to_finance",
    # Sub-headers under the merged «موتور» / «پمپ» group titles are ambiguous on
    # their own; the reader disambiguates them by which group they sit under.
    "پلاک": "__plaque__", "سازنده/تعمیر کار": "__maker__", "نو / تعميري": "__condition__",
    "نو / تعمیری": "__condition__",
}

TARGET_LABELS = {
    "j_day": "روز", "j_month": "ماه", "j_year": "سال", "__date__": "تاریخ کامل",
    "well": "نام چاه", "center": "مرکز", "shift": "شیفت کاری",
    "failure": "شرح خرابی (بهره‌بردار)", "operation": "نوع عملیات",
    "pm": "فرم نصب در PM", "contractor": "پیمانکار", "executor": "مجری",
    "motor_prev": "تیپ موتور قبلی", "motor_curr": "تیپ موتور فعلی",
    "motor_plaque": "پلاک موتور", "motor_maker": "سازنده موتور",
    "motor_condition": "نو/تعمیری موتور", "motor_rewind": "سیم‌پیچی/سرویس",
    "pump_prev": "تیپ پمپ قبلی", "pump_curr": "تیپ پمپ فعلی",
    "pump_stages": "طبقه پمپ", "pump_plaque": "پلاک پمپ",
    "pump_maker": "سازنده پمپ", "pump_condition": "نو/تعمیری پمپ",
    "type_change": "تغییر تیپ", "prev_install_date": "تاریخ نصب قبلی",
    "well_depth": "عمق چاه", "prev_install_depth": "عمق نصب قبلی",
    "curr_install_depth": "عمق نصب فعلی", "static_level": "سطح استاتیک",
    "dynamic_level": "سطح دینامیک", "path_loss": "تلفات مسیر",
    "network_pressure": "فشار شبکه", "total_head": "هد کلی",
    "design_flow": "دبی طراحی", "pipe_diameter": "قطر لوله آبده",
    "cable_type_change": "تغییر تیپ کابل", "cable_size_change": "تغییر سایز کابل",
    "test_date": "تاریخ آزمایش پمپاژ", "test_pressure": "فشار آزمایش",
    "test_flow": "دبی آزمایش", "cable_well": "چاه کابل", "starter": "راه‌انداز",
    "cable_size": "سایز کابل", "pull_year": "سال کشیدن", "pull_month": "ماه کشیدن",
    "old_install_year": "سال نصب قدیم", "old_install_month": "ماه نصب قدیم",
    "working_months": "تعداد ماه کارکرد", "young_wells": "چاه کم‌عمر",
    "workshop_opinion": "نظر کارگاه", "workshop_note": "شرح خرابی کارگاه",
    "description": "توضیحات", "install_supervisor": "ناظر نصب",
    "flow_after_install": "دبی پس از نصب", "flow_before_pull": "دبی قبل از کشیدن",
    "flow_before_pull_date": "تاریخ دبی قبل", "flow_after_install_date": "تاریخ دبی بعد",
    "casing_length": "متراژ جدار", "casing_pulled_diameter": "قطر جدار کشیده",
    "casing_repair_count": "تعداد ترمیم", "casing_material": "جنس جدار",
    "casing_diameter": "قطر جدار", "documents_ref": "مستندات",
    "reported_to_finance": "اعلام شده به مالی",
}


def _norm_header(text) -> str:
    return normalize_text(text).replace("ي", "ی").replace("ك", "ک").lower()


# The map above is written with the spellings that appear in the sheets, some
# of which use Arabic kaf/yeh. Normalising the keys once means a lookup by
# normalised header always hits.
HEADER_MAP = {_norm_header(k): v for k, v in HEADER_MAP.items()}


# ── workbook reading ─────────────────────────────────────────────────────────
def read_sheet(path, sheet_name=None):
    """Return (sheet_names, chosen_name, grid) with every cell as a string."""
    path = str(path)
    if path.lower().endswith(".xls"):
        import xlrd
        book = xlrd.open_workbook(path)
        names = book.sheet_names()
        chosen = sheet_name if sheet_name in names else names[0]
        sheet = book.sheet_by_name(chosen)
        grid = []
        for r in range(sheet.nrows):
            row = []
            for c in range(sheet.ncols):
                value = sheet.cell_value(r, c)
                if isinstance(value, float) and value == int(value):
                    value = int(value)
                row.append("" if value is None else str(value).strip())
            grid.append(row)
        return names, chosen, grid

    from openpyxl import load_workbook
    book = load_workbook(path, data_only=True, read_only=True)
    names = book.sheetnames
    chosen = sheet_name if sheet_name in names else names[0]
    sheet = book[chosen]
    grid = []
    for row in sheet.iter_rows(values_only=True):
        line = []
        for value in row:
            if isinstance(value, dt.datetime):
                value = value.date().isoformat()
            elif isinstance(value, float) and value == int(value):
                value = int(value)
            line.append("" if value is None else str(value).strip())
        grid.append(line)
    book.close()
    return names, chosen, grid


def detect_header(grid):
    """Find the header block and build a (group, title) pair per column.

    Sheet layouts differ by year: some have one header row, the recent ones
    have two (a merged «موتور»/«پمپ» group title above the sub-titles), and
    «کشیدن شش ماه اول» has three. The block is detected rather than assumed,
    and each sub-title is qualified by the group above it — otherwise the two
    «پلاک» columns (motor and pump) would collide.
    """
    scores = [sum(1 for cell in grid[r] if _norm_header(cell) in HEADER_MAP)
              for r in range(min(10, len(grid)))]
    if not scores or max(scores) <= 0:
        return None, None, []
    top = scores.index(max(scores))

    # Grow the block over adjacent rows that still look like headers.
    first, last = top, top
    while first > 0 and scores[first - 1] >= 2:
        first -= 1
    while last + 1 < len(scores) and scores[last + 1] >= 2:
        last += 1

    block = [grid[r] for r in range(first, last + 1)]
    ncols = max(len(row) for row in block)

    def filled(row):
        """Forward-fill a row so a merged group title spans its columns."""
        out, current = [], ""
        for c in range(ncols):
            cell = row[c] if c < len(row) else ""
            if cell:
                current = cell
            out.append(current)
        return out

    filled_rows = [filled(row) for row in block]

    columns = []
    for c in range(ncols):
        title, title_row = "", 0
        for idx in range(len(block) - 1, -1, -1):     # bottom-most wins
            cell = block[idx][c] if c < len(block[idx]) else ""
            if cell:
                title, title_row = cell, idx
                break
        group = ""
        for idx in range(title_row - 1, -1, -1):
            if filled_rows[idx][c]:
                group = filled_rows[idx][c]
                break
        columns.append({"index": c, "title": title, "group": group,
                        "raw_main": block[0][c] if c < len(block[0]) else "",
                        "raw_sub": title})
    return first, len(block), columns


def suggest_mapping(columns):
    """Column → target field, disambiguating the موتور/پمپ sub-headers."""
    mapping = {}
    for col in columns:
        target = HEADER_MAP.get(_norm_header(col["title"]))
        if target in ("__plaque__", "__maker__", "__condition__"):
            group = _norm_header(col["group"])
            prefix = "motor" if "موتور" in group else ("pump" if "پمپ" in group else None)
            suffix = {"__plaque__": "plaque", "__maker__": "maker",
                      "__condition__": "condition"}[target]
            target = f"{prefix}_{suffix}" if prefix else None
        if target == "motor_curr" and _norm_header(col["group"]) == "پمپ":
            target = "pump_curr"
        mapping[str(col["index"])] = target
    return mapping


def preview(path, sheet_name=None, limit=15):
    names, chosen, grid = read_sheet(path, sheet_name)
    header_row, header_rows, columns = detect_header(grid)
    if header_row is None:
        return {"sheets": names, "sheet": chosen, "columns": [], "mapping": {},
                "rows": [], "data_start": 0, "total_rows": 0,
                "warning": "سرستون قابل تشخیصی در این شیت پیدا نشد. "
                           "لطفاً شیت دیگری انتخاب یا نگاشت ستون‌ها را دستی تعیین کنید."}
    start = header_row + header_rows
    data = [row for row in grid[start:] if any(str(c).strip() for c in row)]
    return {
        "sheets": names, "sheet": chosen,
        "columns": columns, "mapping": suggest_mapping(columns),
        "targets": [{"key": k, "label": v} for k, v in TARGET_LABELS.items()],
        "rows": data[:limit], "data_start": start, "total_rows": len(data),
    }


# ── writing ──────────────────────────────────────────────────────────────────
_MULTI_SPLIT = re.compile(r"[،,;؛]|\s-\s")


def _row_fingerprint(payload) -> str:
    """Identity used for duplicate detection: date + well + operation + plaques."""
    parts = [str(payload.get(k) or "") for k in
             ("j_year", "j_month", "j_day", "well", "operation",
              "motor_plaque", "pump_plaque", "motor_curr", "pump_curr")]
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()


def build_payload(row, mapping, sheet_name):
    payload, multi = {}, {}
    for index_str, target in mapping.items():
        if not target:
            continue
        idx = int(index_str)
        if idx >= len(row):
            continue
        raw = str(row[idx]).strip()
        if not raw or raw in {".", "!", "-", "؟", "?"}:
            continue
        if target == "__date__":
            parts = parse_jalali(raw)
            if parts:
                payload["j_year"], payload["j_month"], payload["j_day"] = parts
            continue
        if target in ("failure", "workshop_opinion", "desc_tags"):
            values = [v.strip() for v in _MULTI_SPLIT.split(raw) if v.strip()]
            multi.setdefault(target, []).extend(values)
            continue
        if target in ("j_day", "j_month", "j_year", "pull_year", "pull_month",
                      "old_install_year", "old_install_month"):
            digits = normalize_digits(raw)
            m = re.search(r"\d+", digits)
            if m:
                payload[target] = int(m.group())
            continue
        if target == "pump_prev":
            payload["pump_prev"] = raw
            _, stages = split_pump_type(raw)
            if stages is not None:
                payload["pump_prev_stages"] = stages
            continue
        payload[target] = raw
    payload.update(multi)
    payload["source_sheet"] = sheet_name
    # A sheet named after a Jalali year fills in a missing year column.
    if not payload.get("j_year") and re.fullmatch(r"1[34]\d\d", str(sheet_name).strip()):
        payload["j_year"] = int(str(sheet_name).strip())
    return payload


def commit_import(path, sheet_name, mapping, data_start, skip_duplicates=True,
                  dry_run=False, filename=None):
    names, chosen, grid = read_sheet(path, sheet_name)
    rows = [r for r in grid[data_start:] if any(str(c).strip() for c in r)]

    batch = ImportBatch(filename=filename or str(path), sheet_name=chosen,
                        total_rows=len(rows), status="running")
    db.session.add(batch)
    db.session.flush()

    existing = set()
    if skip_duplicates:
        for rec in Record.query.with_entities(
                Record.j_year, Record.j_month, Record.j_day, Record.well_name_raw,
                Record.operation_id, Record.motor_plaque, Record.pump_plaque).all():
            op = db.session.get(LookupItem, rec[4]) if rec[4] else None
            existing.add("|".join([str(rec[0] or ""), str(rec[1] or ""),
                                   str(rec[2] or ""), str(rec[3] or ""),
                                   op.value if op else "",
                                   str(rec[5] or ""), str(rec[6] or "")]))

    inserted = skipped = failed = warnings = 0
    errors = []
    for offset, row in enumerate(rows):
        row_no = data_start + offset + 1
        try:
            payload = build_payload(row, mapping, chosen)
            if not payload.get("well"):
                skipped += 1
                # A row carrying almost nothing is trailing spreadsheet padding,
                # not a data problem worth reporting to the operator.
                meaningful = sum(1 for k, v in payload.items()
                                 if k not in ("source_sheet", "j_year") and v not in
                                 (None, "", []))
                if meaningful >= 2:
                    errors.append({"row": row_no, "level": "skip",
                                   "message": "نام چاه خالی است؛ سطر رد شد."})
                continue
            if skip_duplicates:
                # The operation belongs in the key: a pull and an install can
                # legitimately happen on the same well on the same day.
                key = "|".join(str(payload.get(k) or "") for k in
                               ("j_year", "j_month", "j_day", "well", "operation",
                                "motor_plaque", "pump_plaque"))
                if key in existing:
                    skipped += 1
                    errors.append({"row": row_no, "level": "duplicate",
                                   "message": "رکورد تکراری (تاریخ/چاه/پلاک یکسان)."})
                    continue
                existing.add(key)

            record = Record(source_sheet=chosen, source_row=row_no,
                            import_batch_id=batch.id)
            # partial=True: historical sheets legitimately lack a day or a
            # contractor; the row is still worth keeping.
            apply_payload(record, payload, create_missing=True, partial=True)
            if record.op_date is None and record.j_year:
                from .jalali import jalali_parts_to_date
                record.op_date = jalali_parts_to_date(record.j_year, record.j_month,
                                                      record.j_day)
            for key, message in getattr(record, "import_warnings", {}).items():
                warnings += 1
                if len(errors) < 500:
                    errors.append({"row": row_no, "level": "warning",
                                   "message": f"{key}: {message} (این ستون خالی ثبت شد)"})
            db.session.add(record)
            inserted += 1
            if inserted % 200 == 0:
                db.session.flush()
        except ValidationError as exc:
            failed += 1
            detail = "، ".join(f"{k}: {v}" for k, v in exc.errors.items())
            errors.append({"row": row_no, "level": "error", "message": detail[:250]})
            log.warning("Import row %s rejected: %s", row_no, detail)
        except Exception as exc:  # one bad row must not lose the whole file
            failed += 1
            errors.append({"row": row_no, "level": "error", "message": str(exc)[:200]})
            log.warning("Import row %s failed: %s", row_no, exc)

    batch.inserted, batch.skipped, batch.failed = inserted, skipped, failed
    batch.finished_at = local_now()
    batch.status = "dry-run" if dry_run else "completed"
    batch.message = (f"{inserted} درج، {skipped} رد، {failed} خطا، "
                     f"{warnings} هشدار")

    if dry_run:
        db.session.rollback()
        return {"batch": None, "inserted": inserted, "skipped": skipped,
                "failed": failed, "warnings": warnings, "errors": errors[:300],
                "dry_run": True, "total_rows": len(rows)}

    record_audit("import", "record", None,
                 summary=f"ورود داده از «{chosen}»: {batch.message}")
    db.session.commit()
    return {"batch": batch.to_dict(), "inserted": inserted, "skipped": skipped,
            "failed": failed, "warnings": warnings, "errors": errors[:300],
            "dry_run": False, "total_rows": len(rows)}


def import_workbook(path, sheet_names=None, skip_duplicates=True):
    """CLI helper: import every (or the named) sheet of a workbook."""
    names, _, _ = read_sheet(path)
    targets = sheet_names or names
    results = {}
    for name in targets:
        if name not in names:
            continue
        info = preview(path, name, limit=1)
        if not info["columns"]:
            results[name] = {"skipped": "بدون سرستون قابل تشخیص"}
            continue
        results[name] = commit_import(path, name, info["mapping"],
                                      info["data_start"], skip_duplicates,
                                      filename=str(path))
    return results


# ── localStorage migration ───────────────────────────────────────────────────
LOCALSTORAGE_MAP = {
    "day": "j_day", "month": "j_month", "year": "j_year", "wellName": "well",
    "center": "center", "shift": "shift", "failure": "failure",
    "operation": "operation", "pm": "pm", "contractor": "contractor",
    "motorPrev": "motor_prev", "motorCurr": "motor_curr",
    "motorPlaque": "motor_plaque", "motorMaker": "motor_maker",
    "motorCondition": "motor_condition", "pumpPrev": "pump_prev",
    "pumpCurr": "pump_curr", "pumpStage": "pump_stages",
    "pumpPlaque": "pump_plaque", "pumpMaker": "pump_maker",
    "pumpCondition": "pump_condition", "typeChange": "type_change",
    "prevInstallDate": "prev_install_date", "wellDepth": "well_depth",
    "prevInstallDepth": "prev_install_depth", "currInstallDepth": "curr_install_depth",
    "staticLevel": "static_level", "dynamicLevel": "dynamic_level",
    "pathLoss": "path_loss", "networkPressure": "network_pressure",
    "totalHead": "total_head", "designFlow": "design_flow",
    "pipeDiameter": "pipe_diameter", "cableTypeChange": "cable_type_change",
    "testDate": "test_date", "testPressure": "test_pressure",
    "testFlow": "test_flow", "cableSizeChange": "cable_size_change",
    "cableWell": "cable_well", "starter": "starter", "cableSize": "cable_size",
    "pullYear": "pull_year", "pullMonth": "pull_month",
    "oldInstallYear": "old_install_year", "oldInstallMonth": "old_install_month",
    "workingMonths": "working_months", "workshopOpinion": "workshop_opinion",
    "description": "description", "youngWells": "young_wells",
}


def import_localstorage(records: list, skip_duplicates=True) -> dict:
    """Move records saved by the old HTML page (``electropump_records_v1``)."""
    batch = ImportBatch(filename="localStorage (electropump_records_v1)",
                        sheet_name="localStorage", total_rows=len(records),
                        status="running")
    db.session.add(batch)
    db.session.flush()

    existing = set()
    if skip_duplicates:
        for rec in Record.query.with_entities(
                Record.j_year, Record.j_month, Record.j_day, Record.well_name_raw).all():
            existing.add("|".join(str(v or "") for v in rec))

    inserted = skipped = failed = 0
    errors = []
    for idx, raw in enumerate(records or []):
        try:
            if not isinstance(raw, dict):
                skipped += 1
                continue
            payload = {}
            for src, target in LOCALSTORAGE_MAP.items():
                value = raw.get(src)
                if value in (None, ""):
                    continue
                if target in ("failure", "workshop_opinion"):
                    payload[target] = [v.strip() for v in str(value).split(",") if v.strip()]
                else:
                    payload[target] = value
            # The old page glued the description tags and free text with ' | '.
            if raw.get("description"):
                text = str(raw["description"])
                if "|" in text:
                    tags, _, free = text.partition("|")
                    payload["desc_tags"] = [t.strip() for t in tags.split(",") if t.strip()]
                    payload["description"] = free.strip()
            if not payload.get("well"):
                skipped += 1
                errors.append({"row": idx + 1, "level": "skip", "message": "نام چاه خالی است."})
                continue
            if skip_duplicates:
                key = "|".join(str(payload.get(k) or "") for k in
                               ("j_year", "j_month", "j_day", "well"))
                if key in existing:
                    skipped += 1
                    errors.append({"row": idx + 1, "level": "duplicate",
                                   "message": "رکورد تکراری."})
                    continue
                existing.add(key)
            record = Record(source_sheet="localStorage", source_row=idx + 1,
                            import_batch_id=batch.id)
            apply_payload(record, payload, create_missing=True, partial=True)
            db.session.add(record)
            inserted += 1
        except Exception as exc:
            failed += 1
            errors.append({"row": idx + 1, "level": "error", "message": str(exc)[:200]})

    batch.inserted, batch.skipped, batch.failed = inserted, skipped, failed
    batch.finished_at = local_now()
    batch.status = "completed"
    batch.message = f"{inserted} درج، {skipped} رد، {failed} خطا"
    record_audit("import", "record", None,
                 summary=f"انتقال داده از localStorage: {batch.message}")
    db.session.commit()
    return {"batch": batch.to_dict(), "inserted": inserted, "skipped": skipped,
            "failed": failed, "errors": errors[:200]}
