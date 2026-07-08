################################################################################
# MERGED PYTHON PROJECT
# This file was generated automatically.
################################################################################


################################################################################
# FILE: __init__.py
################################################################################




################################################################################
# FILE: aid_elevation_import.py
################################################################################

"""Fill well ground elevation from Aid's 'رقوم ارتفاعی' sheet (826 wells).

Matches by clean PM code (کد_تا == well.pm_code) first, then by unambiguous
name-key. Only fills wells whose elevation is currently missing (Aid is the
authoritative source; existing Aid-sourced values are left as-is). Re-runnable.
"""
import openpyxl

from app.extensions import db
from app.models.well import Well
from app.imports.wells_import import match_key, _clean

S_NAME, S_ELEV, S_CODE = 3, 4, 7


def run(path="current data/Aid data.xlsx", dry_run=False):
    stats = {"sheet_rows": 0, "filled_by_code": 0, "filled_by_name": 0,
             "already_set": 0, "unmatched": 0}

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb["رقوم ارتفاعی"]
    rows = list(ws.iter_rows(values_only=True))[2:]

    wells = db.session.scalars(db.select(Well)).all()
    by_pm = {w.pm_code: w for w in wells if w.pm_code}
    by_key = {}
    for w in wells:
        by_key.setdefault(w.match_key, []).append(w)

    for r in rows:
        nm = _clean(r[S_NAME]) if len(r) > S_NAME else None
        el = r[S_ELEV] if len(r) > S_ELEV else None
        if not nm or not isinstance(el, (int, float)):
            continue
        stats["sheet_rows"] += 1
        code = _clean(r[S_CODE]) if len(r) > S_CODE else None

        well = by_pm.get(code) if code else None
        matched_by = "code"
        if well is None:
            cands = by_key.get(match_key(nm), [])
            well = cands[0] if len(cands) == 1 else None
            matched_by = "name"
        if well is None:
            stats["unmatched"] += 1
            continue
        if well.ground_elevation is not None:
            stats["already_set"] += 1
            continue
        well.ground_elevation = float(el)
        stats["filled_by_code" if matched_by == "code" else "filled_by_name"] += 1

    if dry_run:
        db.session.rollback()
    else:
        db.session.commit()
    return stats



################################################################################
# FILE: aid_production_import.py
################################################################################

"""Reconcile monthly production with 'Aid data.xlsx' as the authoritative base.

Aid (sheet 'تولید ماهیانه') carries clean monthly blocks for 1403 & 1404
(production / run-hours / avg-discharge / pressure, فروردین→اسفند). Its values
match the earlier 'روند تولید' file where both exist, but Aid is the curated
base and also covers wells whose روند rows failed to import.

Policy: Aid WINS for 1403 & 1404 (rows re-stamped source='import:aid'); the
earlier 'import:trend' rows for 1399–1402 & 1405 are left untouched. Re-runnable.
"""
from collections import defaultdict

import openpyxl

from app.extensions import db
from app.models.well import Well
from app.models.production import MonthlyProduction
from app.imports.wells_import import match_key, _clean, _num
from app.imports.production_import import _office_resolver

SOURCE = "import:aid"
A_NAME, A_OFFICE = 4, 6

# 12-month blocks (فروردین→اسفند); first column index per metric per Jalali year
BLOCKS = {
    1403: {"production_m3": 74, "run_hours": 104, "avg_discharge_lps": 135, "well_pressure": 43},
    1404: {"production_m3": 86, "run_hours": 116, "avg_discharge_lps": 147, "well_pressure": 55},
}


def run(path="current data/Aid data.xlsx", dry_run=False):
    stats = {"rows": 0, "wells_matched": 0, "unmatched_rows": 0,
             "periods_set": 0, "new_periods": 0, "value_conflicts": 0, "cells": 0}
    samples = []

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb["تولید ماهیانه"]
    rows = ws.iter_rows(values_only=True)
    next(rows)  # header

    office_of = _office_resolver()
    by_key_office, by_key = {}, {}
    for w in db.session.scalars(db.select(Well)).all():
        by_key.setdefault(w.match_key, []).append(w)
        by_key_office[(w.match_key, w.office_id)] = w

    # existing rows for the two reconciled years, for idempotent upsert
    existing = {}
    for mp in db.session.scalars(
            db.select(MonthlyProduction).where(MonthlyProduction.jyear.in_(list(BLOCKS)))).all():
        existing[(mp.well_id, mp.jyear, mp.jmonth)] = mp

    matched = set()
    for row in rows:
        name = _clean(row[A_NAME]) if len(row) > A_NAME else None
        if not name:
            continue
        stats["rows"] += 1
        nk = match_key(name)
        oid = office_of(row[A_OFFICE] if len(row) > A_OFFICE else None)
        well = by_key_office.get((nk, oid))
        if well is None:
            cands = by_key.get(nk, [])
            well = cands[0] if len(cands) == 1 else None
        if well is None:
            stats["unmatched_rows"] += 1
            continue
        matched.add(well.id)

        for yr, cols in BLOCKS.items():
            for m in range(12):
                vals = {}
                for metric, c0 in cols.items():
                    v = _num(row[c0 + m], zero_is_null=False) if (c0 + m) < len(row) else None
                    if v is not None:
                        vals[metric] = v
                if not vals:
                    continue
                stats["cells"] += len(vals)
                rec = existing.get((well.id, yr, m + 1))
                if rec is None:
                    rec = MonthlyProduction(well_id=well.id, jyear=yr, jmonth=m + 1)
                    db.session.add(rec)
                    existing[(well.id, yr, m + 1)] = rec
                    stats["new_periods"] += 1
                else:
                    old = rec.production_m3
                    new = vals.get("production_m3")
                    if old is not None and new is not None and abs(old - new) > 1:
                        stats["value_conflicts"] += 1
                        if len(samples) < 8:
                            samples.append((well.name, yr, m + 1, round(old), round(new)))
                rec.production_m3 = vals.get("production_m3")
                rec.run_hours = vals.get("run_hours")
                rec.avg_discharge_lps = vals.get("avg_discharge_lps")
                rec.well_pressure = vals.get("well_pressure")
                rec.source = SOURCE
                stats["periods_set"] += 1

    stats["wells_matched"] = len(matched)
    stats["_conflict_samples"] = samples
    if dry_run:
        db.session.rollback()
    else:
        db.session.commit()
    return stats



################################################################################
# FILE: aid_reconcile.py
################################################################################

"""Reconcile all prior data against the clean 'Aid data.xlsx' master.

'Aid data.xlsx' (sheet 'تولید ماهیانه') is a curated master: clean unique PM
codes, normalized names, center codes, office, zone, elevation. We cross-check it
against (a) our well registry and (b) the production-trend wells, and emit a
multi-sheet discrepancy workbook so the user can finalize the registry.

Sheets:
  خلاصه              counts
  نگاشت_تمیز         our wells that DO match Aid -> adopt clean PM/center/elevation
  مغایرت_PM          matched wells whose stored (non-synthetic) PM differs from Aid
  گمشده_در_Aid       Aid wells absent from our registry (ADD candidates; flag data)
  رجیستری_بدون_Aid   our wells with no Aid match (synthetic? has-data? fuzzy hint)
  تولید_یتیم         production wells present in neither registry nor Aid
"""
import re
from collections import Counter, defaultdict
from difflib import get_close_matches

import openpyxl
import pandas as pd

from app.extensions import db
from app.models.well import Well
from app.imports.wells_import import match_key, _clean

# Aid sheet column indices
A_PM, A_CENTER, A_NAME, A_OFFICE, A_URBAN, A_STATUS, A_ELEV = 2, 3, 4, 6, 8, 17, 22

# production-trend file (to flag recoverable data & find true orphans)
PROD_FILE = "current data/روند تولید چاه ها.xlsx"


def _load_aid(path):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb["تولید ماهیانه"]
    recs, by_key, dup = [], {}, []
    for r in list(ws.iter_rows(values_only=True))[1:]:
        nm = _clean(r[A_NAME]) if len(r) > A_NAME else None
        if not nm:
            continue
        k = match_key(nm)
        rec = {
            "name": nm, "key": k,
            "pm": _clean(r[A_PM]), "center": _clean(r[A_CENTER]),
            "office": _clean(r[A_OFFICE]), "urban": _clean(r[A_URBAN]),
            "status": _clean(r[A_STATUS]) if len(r) > A_STATUS else None,
            "elev": _clean(r[A_ELEV]) if len(r) > A_ELEV else None,
        }
        recs.append(rec)
        if k in by_key:
            dup.append(k)
        else:
            by_key[k] = rec
    return recs, by_key, set(dup)


def _load_prod_keys(path):
    """name-key -> office string, for production-trend wells."""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    out = {}
    for r in list(ws.iter_rows(values_only=True))[1:]:
        nm = _clean(r[0]) if r else None
        if nm:
            out[match_key(nm)] = _clean(r[1]) if len(r) > 1 else None
    return out


def export(aid_path="current data/Aid data.xlsx", out_path="aid_reconciliation.xlsx"):
    aid_recs, aid_by_key, aid_dups = _load_aid(aid_path)
    aid_keys = set(aid_by_key)
    prod_keys = _load_prod_keys(PROD_FILE)

    wells = db.session.scalars(db.select(Well)).all()
    from app.models.production import MonthlyProduction as MP
    from app.models.flow import FlowTest
    has_prod = set(db.session.scalars(db.select(MP.well_id.distinct())).all())
    has_flow = set(db.session.scalars(db.select(FlowTest.well_id.distinct())).all())

    def well_has_data(w):
        return w.id in has_prod or w.id in has_flow

    clean_map, pm_conflict, reg_no_aid = [], [], []
    matched_keys = set()
    for w in wells:
        aid = aid_by_key.get(w.match_key)
        if aid:
            matched_keys.add(w.match_key)
            clean_map.append({
                "نام چاه": w.name, "PM رجیستری": w.pm_code,
                "PM تمیز (Aid)": aid["pm"], "کد مرکز (Aid)": aid["center"],
                "اداره (Aid)": aid["office"], "رقوم ارتفاعی": aid["elev"],
            })
            synthetic = (w.pm_code or "").startswith("W-")
            if not synthetic and aid["pm"] and _clean(w.pm_code) != aid["pm"]:
                pm_conflict.append({
                    "نام چاه": w.name, "PM رجیستری": w.pm_code,
                    "PM در Aid": aid["pm"], "اداره": w.office.name if w.office else "",
                })
        else:
            hint = get_close_matches(w.match_key, list(aid_keys), n=1, cutoff=0.82)
            reg_no_aid.append({
                "نام چاه (رجیستری)": w.name, "PM فعلی": w.pm_code,
                "PM مصنوعی؟": "بله" if (w.pm_code or "").startswith("W-") else "خیر",
                "داده دارد؟": "بله" if well_has_data(w) else "خیر",
                "احتمال تطبیق در Aid": aid_by_key[hint[0]]["name"] if hint else "",
            })

    # Aid wells missing from registry
    aid_missing = []
    for aid in aid_recs:
        if aid["key"] in matched_keys or aid["key"] in {w.match_key for w in wells}:
            continue
        aid_missing.append({
            "نام چاه (Aid)": aid["name"], "کد PM": aid["pm"],
            "کد مرکز": aid["center"], "اداره": aid["office"],
            "شهری/روستایی": aid["urban"], "وضعیت": aid["status"],
            "رقوم ارتفاعی": aid["elev"],
            "داده تولید موجود؟": "بله" if aid["key"] in prod_keys else "خیر",
        })
    # de-dup aid_missing by name-key (keep first)
    seen = set(); aid_missing_u = []
    for r in aid_missing:
        k = match_key(r["نام چاه (Aid)"])
        if k in seen:
            continue
        seen.add(k); aid_missing_u.append(r)

    # production wells in NEITHER registry nor Aid
    reg_keys = {w.match_key for w in wells}
    prod_orphans = [{"نام چاه (تولید)": k, "اداره": off}
                    for k, off in prod_keys.items()
                    if k not in reg_keys and k not in aid_keys]
    # show the real name not the key
    prodwb = openpyxl.load_workbook(PROD_FILE, read_only=True, data_only=True)
    pw = prodwb[prodwb.sheetnames[0]]
    keyname = {}
    for r in list(pw.iter_rows(values_only=True))[1:]:
        nm = _clean(r[0]) if r else None
        if nm:
            keyname.setdefault(match_key(nm), nm)
    for r in prod_orphans:
        r["نام چاه (تولید)"] = keyname.get(r["نام چاه (تولید)"], r["نام چاه (تولید)"])

    summary = pd.DataFrame({"شاخص": [
        "چاه‌های Aid (مرجع تمیز)", "کد PM یکتا در Aid (بدون اشتراک)",
        "چاه‌های رجیستری ما", "تطبیق رجیستری↔Aid (نگاشت تمیز)",
        "مغایرت PM (PM واقعی متفاوت)", "گمشده: در Aid هست، در رجیستری نیست",
        "رجیستری بدون معادل در Aid", "  از آن: PM مصنوعی",
        "  از آن: بدون هیچ داده", "تولیدِ یتیم (در هیچ‌کدام نیست)",
    ], "مقدار": [
        len({r["key"] for r in aid_recs}), len({r["pm"] for r in aid_recs if r["pm"]}),
        len(wells), len(clean_map), len(pm_conflict), len(aid_missing_u),
        len(reg_no_aid), sum(1 for r in reg_no_aid if r["PM مصنوعی؟"] == "بله"),
        sum(1 for r in reg_no_aid if r["داده دارد؟"] == "خیر"), len(prod_orphans),
    ]})

    with pd.ExcelWriter(out_path, engine="openpyxl") as xl:
        summary.to_excel(xl, sheet_name="خلاصه", index=False)
        pd.DataFrame(clean_map).to_excel(xl, sheet_name="نگاشت_تمیز", index=False)
        pd.DataFrame(pm_conflict).to_excel(xl, sheet_name="مغایرت_PM", index=False)
        pd.DataFrame(aid_missing_u).to_excel(xl, sheet_name="گمشده_در_Aid", index=False)
        pd.DataFrame(reg_no_aid).to_excel(xl, sheet_name="رجیستری_بدون_Aid", index=False)
        pd.DataFrame(prod_orphans).to_excel(xl, sheet_name="تولید_یتیم", index=False)
        for name, wsx in xl.sheets.items():
            for col in wsx.columns:
                w = max((len(str(c.value)) for c in col if c.value is not None), default=10)
                wsx.column_dimensions[col[0].column_letter].width = min(max(w + 2, 12), 42)

    return {
        "aid_wells": len(aid_recs), "aid_unique_pm": len({r["pm"] for r in aid_recs if r["pm"]}),
        "registry_wells": len(wells), "clean_mapped": len(clean_map),
        "pm_conflicts": len(pm_conflict), "aid_missing_from_registry": len(aid_missing_u),
        "registry_not_in_aid": len(reg_no_aid), "production_orphans": len(prod_orphans),
        "aid_dup_names": len(aid_dups), "out_path": out_path,
    }



################################################################################
# FILE: aid_sync.py
################################################################################

"""Apply the clean 'Aid data.xlsx' master to the registry (reconcile steps 1+2).

Step 1 — for wells that already exist (matched by name-key), adopt Aid's clean
         PM code and ground elevation. The previous *real* pm (if any) is kept in
         well_identifiers as 'pm_legacy'. PM reassignment is collision-safe via a
         temp phase, so swaps (e.g. کورده 12↔13) apply cleanly.
Step 2 — create the wells that exist in Aid but not in the registry, with clean
         identity (pm, office, kind, status, elevation).

Center is NOT mapped: our OrgUnit centers carry no codes that match Aid's center
codes, so it is left untouched (reported, not guessed). Re-runnable.
"""
import hashlib
from collections import defaultdict

import openpyxl

from app.extensions import db
from app.models.well import Well, WellIdentifier
from app.imports.wells_import import match_key, _clean
from app.imports.production_import import _office_resolver
from app.utils.dates import to_english_digits

# Aid sheet column indices
A_PM, A_CENTER, A_NAME, A_OFFICE, A_URBAN, A_INCIRCUIT, A_ELEV = 2, 3, 4, 6, 8, 29, 22


def _elev(v):
    s = _clean(v)
    if s is None:
        return None
    try:
        return float(to_english_digits(s))
    except ValueError:
        return None


def _kind(urban):
    u = _clean(urban) or ""
    if "روستای" in u:
        return "rural"
    if "شهر" in u:
        return "urban"
    return "urban"


def _status(incircuit, has_prod):
    s = _clean(incircuit) or ""
    if "خارج" in s:
        return "out"
    if "مدار" in s:
        return "in_circuit"
    return "in_circuit" if has_prod else "unknown"


def _load(path):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb["تولید ماهیانه"]
    recs = []
    for r in list(ws.iter_rows(values_only=True))[1:]:
        nm = _clean(r[A_NAME]) if len(r) > A_NAME else None
        if not nm:
            continue
        recs.append({
            "name": nm, "key": match_key(nm),
            "pm": _clean(r[A_PM]), "center": _clean(r[A_CENTER]),
            "office": _clean(r[A_OFFICE]), "urban": _clean(r[A_URBAN]),
            "incircuit": _clean(r[A_INCIRCUIT]) if len(r) > A_INCIRCUIT else None,
            "elev": _elev(r[A_ELEV]) if len(r) > A_ELEV else None,
        })
    return recs


def run(aid_path="current data/Aid data.xlsx", dry_run=False):
    stats = {"pm_updated": 0, "pm_legacy_saved": 0, "elevation_set": 0,
             "pm_conflicts_skipped": 0, "wells_added": 0, "add_pm_synth": 0,
             "add_skipped_existing": 0, "centers_unmapped": 0}

    recs = _load(aid_path)
    # one Aid record per name-key (first wins; Aid keys are ~unique)
    aid_by_key = {}
    for a in recs:
        aid_by_key.setdefault(a["key"], a)

    office_of = _office_resolver()
    wells = db.session.scalars(db.select(Well)).all()
    reg_by_key = defaultdict(list)
    for w in wells:
        reg_by_key[w.match_key].append(w)

    stats["wells_pm_matched"] = 0

    # pm codes held by wells we will NOT touch in step 1 (for collision checks)
    def is_real(pm):
        return bool(pm) and not pm.startswith(("W-", "K", "BW-", "TMP-"))

    # ---------- STEP 1: update name-matched wells ----------
    def pick_primary(cohort, aid):
        for w in cohort:
            if _clean(w.pm_code) == aid["pm"]:
                return w
        for w in cohort:
            if w.has_pm:
                return w
        return min(cohort, key=lambda w: w.id)

    updates = []          # (well, aid)
    primary_ids = set()
    for key, aid in aid_by_key.items():
        cohort = reg_by_key.get(key)
        if not cohort or not aid["pm"]:
            continue
        primary = pick_primary(cohort, aid)
        updates.append((primary, aid))
        primary_ids.add(primary.id)

    # real pm -> well, for wells that are NOT name-match primaries (variant names)
    other_by_pm = {}
    for w in wells:
        if w.id not in primary_ids and is_real(w.pm_code):
            other_by_pm.setdefault(w.pm_code, w)

    safe_updates, legacy_pm = [], {}
    for w, aid in updates:
        if aid["pm"] in other_by_pm:   # target pm sits on a variant well -> skip pm change
            stats["pm_conflicts_skipped"] += 1
            continue
        if is_real(w.pm_code) and _clean(w.pm_code) != aid["pm"]:
            legacy_pm[w.id] = w.pm_code
        safe_updates.append((w, aid))

    # phase A: temp pm to avoid transient unique clashes (swaps)
    for i, (w, aid) in enumerate(safe_updates):
        if _clean(w.pm_code) != aid["pm"]:
            w.pm_code = f"TMP-{w.id}-{i}"
    db.session.flush()
    # phase B: final pm + elevation + legacy preservation
    for w, aid in safe_updates:
        if str(w.pm_code).startswith("TMP-"):
            w.pm_code = aid["pm"]
            stats["pm_updated"] += 1
            if w.id in legacy_pm:
                db.session.add(WellIdentifier(
                    well_id=w.id, id_type="pm_legacy", value=legacy_pm[w.id]))
                stats["pm_legacy_saved"] += 1
        if aid["elev"] is not None and w.ground_elevation != aid["elev"]:
            w.ground_elevation = aid["elev"]
            stats["elevation_set"] += 1

    # ---------- STEP 1b: PM-match variant-named wells (avoid duplicates) ----------
    # An Aid well not matched by name may already exist under a shorter/variant name
    # but with the SAME clean pm. Adopt the Aid canonical name + key so it aligns and
    # its production data attaches to the EXISTING well instead of a duplicate.
    for aid in recs:
        key = aid["key"]
        if key in reg_by_key or not aid["pm"]:
            continue
        w = other_by_pm.get(aid["pm"])
        if w is None:
            continue
        if w.name != aid["name"]:
            db.session.add(WellIdentifier(well_id=w.id, id_type="name", value=w.name))
            w.name = aid["name"]
        w.match_key = key
        if aid["elev"] is not None:
            w.ground_elevation = aid["elev"]
        reg_by_key[key].append(w)        # now treated as existing
        stats["wells_pm_matched"] += 1

    # ---------- STEP 2: add truly-missing wells ----------
    existing_keys = set(reg_by_key)
    used_pms = {w.pm_code for w in wells} | {aid["pm"] for _, aid in safe_updates}
    added_keys = set()
    for aid in recs:
        key = aid["key"]
        if key in existing_keys or key in added_keys:
            stats["add_skipped_existing"] += 1
            continue
        pm = aid["pm"]
        if not pm or pm in used_pms:
            # synthesize a deterministic key when missing/colliding
            pm = "W-" + hashlib.md5(f"{key}|{aid['office']}".encode()).hexdigest()[:12]
            stats["add_pm_synth"] += 1
        used_pms.add(pm)
        if aid["center"]:
            stats["centers_unmapped"] += 1
        has_prod = False  # production attaches on the subsequent import-production
        w = Well(
            pm_code=pm, name=aid["name"], match_key=key,
            office_id=office_of(aid["office"]),
            well_kind=_kind(aid["urban"]),
            status=_status(aid["incircuit"], has_prod),
            ground_elevation=aid["elev"],
            notes="افزوده‌شده از Aid data",
        )
        db.session.add(w)
        added_keys.add(key)
        stats["wells_added"] += 1

    if dry_run:
        db.session.rollback()
    else:
        db.session.commit()
    return stats



################################################################################
# FILE: catalog_import.py
################################################################################

"""Importer for the pump catalog from pump_data.js (full reload, idempotent).

pump_data.js holds `var pumpData = { "Pumps": [ {point}, ... ] }`. Rows are
grouped by model (عنوان تیپ پمپ); optional BEP/BEB marker columns ('*') flag the
best-efficiency point and band. Re-running replaces the whole catalog.
"""
import json
import re

from app.extensions import db
from app.models.pump_catalog import PumpModel, PumpCurvePoint
from app.imports.wells_import import _num, _intstr, _clean


def _int(v):
    s = _intstr(v)
    if not s:
        return None
    m = re.match(r"\d+", s)
    return int(m.group(0)) if m else None


def _marker(row, *key_parts):
    """True if a column whose name contains all key_parts has value '*'."""
    for k, v in row.items():
        name = str(k)
        if all(p in name for p in key_parts):
            return str(v).strip() == "*"
    return False


def run(js_path, dry_run=False):
    txt = open(js_path, encoding="utf-8").read()
    data = json.loads(txt[txt.index("{"):txt.rindex("}") + 1])
    rows = data["Pumps"]

    grouped = {}
    for r in rows:
        flow_m3h = _num(r.get("میزان آبدهی مترمکعب/ساعت"))
        if flow_m3h is None:
            continue
        model = _clean(r.get("عنوان تیپ پمپ"))
        if not model:
            continue
        grouped.setdefault(model, []).append(r)

    # full reload
    db.session.query(PumpCurvePoint).delete()
    db.session.query(PumpModel).delete()
    db.session.flush()

    stats = {"models": 0, "points": 0}
    for model, rs in grouped.items():
        head0 = rs[0]
        pm = PumpModel(
            model=model,
            ptype=_clean(head0.get("تیپ پمپ")),
            title_electro=_clean(head0.get("عنوان تیپ الکتروپمپ")),
            stages=_int(head0.get("تعداد طبقات")),
            motor_power_kw=_num(head0.get("توان الکتروموتور")),
            npsh=_num(head0.get("NPSH")),
            nominal_current=_num(head0.get("جریان نامی (آمپر)")),
            length_mm=_int(head0.get("طول کلی mm")),
            weight_kg=_int(head0.get("وزن کلی Kg")),
        )
        db.session.add(pm)
        db.session.flush()
        stats["models"] += 1
        for r in rs:
            q = _num(r.get("میزان آبدهی مترمکعب/ساعت"))
            db.session.add(PumpCurvePoint(
                model_id=pm.id,
                flow_m3h=q,
                flow_lps=_num(r.get("دبی L/s")) or (q / 3.6 if q else None),
                head_m=_num(r.get("هد - متر")),
                efficiency_pct=_num(r.get("راندمان پمپ %")) or _num(r.get("راندمان پمپ")),
                is_bep=_marker(r, "بهینه"),
                is_beb_start=_marker(r, "شروع BEB"),
                is_beb_end=_marker(r, "پایان BEB"),
            ))
            stats["points"] += 1

    if dry_run:
        db.session.rollback()
    else:
        db.session.commit()
    return stats



################################################################################
# FILE: construction_import.py
################################################################################

"""Fill well construction_type (سیمانته/غیرسیمانته) from 'تجمیعی (400-405).xlsx'.

The aggregate flow-metering sheet records «نوع چاه» (سیمانته / غیرسیمانته) on each
row — far richer than the Borwells drilling-permit source. We take the majority
value per well, matched by match_key(name)+office (name-only fallback when
unambiguous), and map سیمانته→cementation, غیرسیمانته→normal. The geological
'limestone' (آهکی) classification from Borwells is preserved (not overwritten).
Re-runnable (deterministic majority).
"""
from collections import defaultdict, Counter

import openpyxl

from app.extensions import db
from app.models.well import Well
from app.imports.wells_import import match_key, _clean
from app.imports.production_import import _office_resolver

C_NAME, C_OFFICE, C_TYPE = 0, 3, 53


def _norm_type(v):
    s = _clean(v)
    if not s:
        return None
    s = s.replace("ي", "ی").replace("ك", "ک")
    if "غیرسیمانت" in s:
        return "normal"        # غیرسیمانته
    if "سیمانت" in s:
        return "cementation"   # سیمانته
    return None


def run(path="current data/تجمیعی (400-405).xlsx", dry_run=False):
    stats = {"rows": 0, "wells_with_type": 0, "matched": 0, "unmatched": 0,
             "set_cementation": 0, "set_normal": 0, "preserved_limestone": 0, "unchanged": 0}

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb["تجمیع دبی‌سنجی"]
    rows = ws.iter_rows(values_only=True)
    next(rows)

    # majority نوع چاه per (name-key, office-token)
    votes = defaultdict(Counter)
    for r in rows:
        nm = _clean(r[C_NAME]) if len(r) > C_NAME else None
        ty = _norm_type(r[C_TYPE]) if len(r) > C_TYPE else None
        if not nm or not ty:
            continue
        stats["rows"] += 1
        off = _clean(r[C_OFFICE]) if len(r) > C_OFFICE else None
        votes[(match_key(nm), off)].update([ty])

    office_of = _office_resolver()
    by_key_office, by_key = {}, {}
    for w in db.session.scalars(db.select(Well)).all():
        by_key.setdefault(w.match_key, []).append(w)
        by_key_office[(w.match_key, w.office_id)] = w

    # collapse votes to one value per well (resolve well, then majority)
    well_value = {}
    for (nk, off), counter in votes.items():
        stats["wells_with_type"] += 1
        oid = office_of(off)
        well = by_key_office.get((nk, oid))
        if well is None:
            cands = by_key.get(nk, [])
            well = cands[0] if len(cands) == 1 else None
        if well is None:
            stats["unmatched"] += 1
            continue
        well_value.setdefault(well.id, Counter()).update(counter)

    for wid, counter in well_value.items():
        stats["matched"] += 1
        value = counter.most_common(1)[0][0]
        w = db.session.get(Well, wid)
        if w.construction_type == "limestone":
            stats["preserved_limestone"] += 1
            continue
        if w.construction_type == value:
            stats["unchanged"] += 1
            continue
        w.construction_type = value
        stats["set_cementation" if value == "cementation" else "set_normal"] += 1

    if dry_run:
        db.session.rollback()
    else:
        db.session.commit()
    return stats



################################################################################
# FILE: coords_import.py
################################################################################

"""Complete missing well coordinates from the electricity 'کل چاهها' sheet (UTM).

Only fills wells that currently lack lat/lon, matched by an unambiguous name-key.
UTM 40N (Mashhad) is validated to a sane bounding box before transforming to
WGS84 with pyproj. Re-runnable (only touches coord-less wells).
"""
import openpyxl
from pyproj import Transformer

from app.extensions import db
from app.models.well import Well
from app.imports.wells_import import match_key, _clean

_T = Transformer.from_crs("EPSG:32640", "EPSG:4326", always_xy=True)  # UTM40N -> WGS84
# Mashhad-area sanity bounds for UTM zone 40N
X_MIN, X_MAX = 600000, 800000
Y_MIN, Y_MAX = 3900000, 4150000


def _num(v):
    try:
        return float(_clean(v))
    except (TypeError, ValueError):
        return None


def run(path="current data/electricity.xlsx", dry_run=False):
    stats = {"sheet_rows": 0, "valid_utm": 0, "filled": 0,
             "ambiguous": 0, "no_match": 0, "out_of_range": 0}

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb["کل چاهها"]
    hdr = list(next(ws.iter_rows(values_only=True)))
    idx = {h: i for i, h in enumerate(hdr) if h}
    ci_nm, ci_x, ci_y = idx["نام چاه"], idx["UTM X"], idx["UTM Y"]

    # index our coord-less wells by name-key
    coordless = {}
    for w in db.session.scalars(db.select(Well).where(Well.latitude.is_(None))).all():
        coordless.setdefault(w.match_key, []).append(w)

    for r in ws.iter_rows(min_row=2, values_only=True):
        nm = _clean(r[ci_nm]) if ci_nm < len(r) else None
        if not nm:
            continue
        stats["sheet_rows"] += 1
        x, y = _num(r[ci_x]), _num(r[ci_y])
        if x is None or y is None:
            continue
        stats["valid_utm"] += 1
        if not (X_MIN <= x <= X_MAX and Y_MIN <= y <= Y_MAX):
            stats["out_of_range"] += 1
            continue
        cands = coordless.get(match_key(nm))
        if not cands:
            stats["no_match"] += 1
            continue
        if len(cands) > 1:
            stats["ambiguous"] += 1
            continue
        w = cands[0]
        lon, lat = _T.transform(x, y)
        w.utm_x, w.utm_y, w.utm_zone = x, y, "40N"
        w.latitude, w.longitude = round(lat, 6), round(lon, 6)
        stats["filled"] += 1

    if dry_run:
        db.session.rollback()
    else:
        db.session.commit()
    return stats



################################################################################
# FILE: dedup_stubs.py
################################################################################

"""Merge & remove duplicate stub wells.

Within each duplicate name group (normalized base name, qualifier suffixes
stripped — same key as the data-export tool), the member with the MOST data is
kept as the primary; low-data stubs (<= threshold records) are MERGED into the
primary (their data is reassigned, conflicting rows dropped) and then deleted.
No data is lost. Dry-run supported.
"""
from collections import defaultdict

from sqlalchemy import text

from app.extensions import db
from app.services.data_export import dup_group

# event/timeseries tables that count as "data" for ranking primary vs stub
DATA_TABLES = [
    "monthly_production", "flow_tests", "pump_tests", "drilling",
    "pump_installations", "rehabilitations", "videometry_logs",
    "pump_selections", "water_level_logs", "water_quality", "maintenance_records",
]
# all tables to reassign well_id from stub -> primary
WELL_ID_TABLES = DATA_TABLES + ["relocations", "well_identifiers", "well_baselines"]
# unique-constrained tables: (table, key columns besides well_id)
UNIQUE_TABLES = {
    "monthly_production": ["jyear", "jmonth"],
    "water_level_logs": ["measure_date", "source"],
    "well_technical": [],          # well_id itself is unique (1:1)
}


def _data_counts():
    counts = defaultdict(int)
    for t in DATA_TABLES:
        for wid, n in db.session.execute(
                text(f"SELECT well_id, COUNT(*) FROM {t} GROUP BY well_id")):
            if wid is not None:
                counts[wid] += n
    return counts


def _merge_unique(table, key_cols, stub_id, primary_id):
    """Move stub rows to primary where (key) free; delete conflicting stub rows."""
    if not key_cols:   # 1:1 (well_technical)
        has = db.session.execute(
            text(f"SELECT 1 FROM {table} WHERE well_id=:p"), {"p": primary_id}).first()
        if has:
            db.session.execute(text(f"DELETE FROM {table} WHERE well_id=:s"), {"s": stub_id})
        else:
            db.session.execute(text(f"UPDATE {table} SET well_id=:p WHERE well_id=:s"),
                               {"p": primary_id, "s": stub_id})
        return
    keys = ", ".join(key_cols)
    cond = " AND ".join(f"t.{k}=p.{k}" for k in key_cols)
    # delete stub rows whose key already exists on primary
    db.session.execute(text(
        f"DELETE FROM {table} WHERE well_id=:s AND EXISTS "
        f"(SELECT 1 FROM {table} p WHERE p.well_id=:p AND "
        + " AND ".join(f"p.{k}={table}.{k}" for k in key_cols) + ")"),
        {"s": stub_id, "p": primary_id})
    # move the rest
    db.session.execute(text(f"UPDATE {table} SET well_id=:p WHERE well_id=:s"),
                       {"p": primary_id, "s": stub_id})


def _merge_well(stub_id, primary_id):
    # unique-constrained first
    for table, keys in UNIQUE_TABLES.items():
        _merge_unique(table, keys, stub_id, primary_id)
    # plain reassign for the rest
    for t in WELL_ID_TABLES:
        if t in UNIQUE_TABLES:
            continue
        db.session.execute(text(f"UPDATE {t} SET well_id=:p WHERE well_id=:s"),
                           {"p": primary_id, "s": stub_id})
    # inbound references
    db.session.execute(text("UPDATE relocations SET new_well_id=:p WHERE new_well_id=:s"),
                       {"p": primary_id, "s": stub_id})
    db.session.execute(text("UPDATE wells SET parent_well_id=:p WHERE parent_well_id=:s"),
                       {"p": primary_id, "s": stub_id})
    db.session.execute(text(
        "UPDATE attachments SET entity_id=:p WHERE entity_type='well' AND entity_id=:s"),
        {"p": primary_id, "s": stub_id})
    db.session.execute(text("DELETE FROM wells WHERE id=:s"), {"s": stub_id})


def run(threshold=2, dry_run=False):
    from app.models.well import Well
    stats = {"groups": 0, "deleted": 0, "kept": 0, "skipped_groups": 0}
    deleted = []

    wells = db.session.scalars(db.select(Well)).all()
    counts = _data_counts()
    groups = defaultdict(list)
    for w in wells:
        groups[dup_group(w.name)].append(w)

    for key, members in groups.items():
        if len(members) < 2:
            continue
        stats["groups"] += 1
        members.sort(key=lambda w: (counts.get(w.id, 0), w.has_pm, -w.id), reverse=True)
        primary = members[0]
        p_count = counts.get(primary.id, 0)
        if p_count <= threshold:
            stats["skipped_groups"] += 1     # whole group is sparse -> leave for manual
            continue
        for w in members[1:]:
            if counts.get(w.id, 0) <= threshold:
                deleted.append({"id": w.id, "name": w.name, "data": counts.get(w.id, 0),
                                "into": primary.name, "into_id": primary.id,
                                "into_data": p_count})
                _merge_well(w.id, primary.id)
                stats["deleted"] += 1
        stats["kept"] += 1

    stats["_sample"] = deleted[:25]
    stats["_total_deleted_list"] = len(deleted)
    if dry_run:
        db.session.rollback()
    else:
        db.session.commit()
    return stats



################################################################################
# FILE: discrepancy_export.py
################################################################################

"""Export well-identity discrepancies to Excel for manual correction.

Sheets:
  - راهنما         : how to use
  - pم‌های_خراب    : pm codes shared by several distinct wells (fill correct pm)
  - بدون_pm        : wells that have no pm code at all (fill pm)
  - نام_چند_pm     : one well-name mapped to several pm codes
The user fills the 'کد PM صحیح' column and returns the file.
"""
from collections import defaultdict

import pandas as pd

from app.imports.wells_import import _norm_name, _intstr, _clean, match_key


def export(tajmi_path, out_path):
    tj = pd.read_excel(tajmi_path, sheet_name="تجمیع دبی‌سنجی")
    tj.columns = [str(c).strip() for c in tj.columns]

    rep_name, offices, klasses, pms = {}, defaultdict(set), defaultdict(set), defaultdict(set)
    pm_keys = defaultdict(set)       # pm -> {name-key}
    key_pms = defaultdict(set)       # name-key -> {pm}
    year = {}
    for _, r in tj.iterrows():
        nm = _norm_name(r.get("نام چاه"))
        if not nm:
            continue
        nk = match_key(nm)
        yr = _intstr(r.get("سال")) or "0"
        if nk not in rep_name or yr >= year.get(nk, "0"):
            rep_name[nk] = nm
            year[nk] = yr
        off = _clean(r.get("نام اداره"))
        if off:
            offices[nk].add(off)
        kl = _intstr(r.get("کلاسه چاه"))
        if kl:
            klasses[nk].add(kl)
        pm = _intstr(r.get("کد PM"))
        if pm:
            pms[nk].add(pm)
            pm_keys[pm].add(nk)
            key_pms[nk].add(pm)

    join = lambda s: "، ".join(sorted(s)) if s else ""

    # 1) corrupt pm
    corrupt_rows = []
    for pm, keys in sorted(pm_keys.items(), key=lambda x: -len(x[1])):
        if len(keys) < 2:
            continue
        for nk in sorted(keys, key=lambda k: rep_name[k]):
            corrupt_rows.append({
                "کد PM مشکوک": pm,
                "تعداد چاه با این PM": len(keys),
                "نام چاه": rep_name[nk],
                "اداره": join(offices[nk]),
                "کلاسه": join(klasses[nk]),
                "کد PM صحیح": "",
                "توضیحات": "",
            })

    # 2) no pm
    nopm_rows = []
    for nk, p in sorted(key_pms.items(), key=lambda x: rep_name[x[0]]):
        pass
    for nk in sorted(rep_name, key=lambda k: rep_name[k]):
        if not pms[nk]:
            nopm_rows.append({
                "نام چاه": rep_name[nk], "اداره": join(offices[nk]),
                "کلاسه": join(klasses[nk]), "کد PM صحیح": "", "توضیحات": "",
            })

    # 3) one name -> many pm
    multi_rows = []
    for nk, ps in sorted(key_pms.items(), key=lambda x: rep_name[x[0]]):
        if len(ps) > 1:
            multi_rows.append({
                "نام چاه": rep_name[nk], "اداره": join(offices[nk]),
                "کدهای PM": join(ps), "کد PM صحیح": "", "توضیحات": "",
            })

    guide = pd.DataFrame({"راهنما": [
        "این فایل موارد مغایرتِ کد PM در «تجمیعی (400-405)» را فهرست می‌کند.",
        "ستون «کد PM صحیح» را پر کنید و فایل را بازگردانید.",
        "",
        "pم‌های_خراب: هر کد PM که به چند چاهِ متفاوت چسبیده — برای هر چاه PM درست را بنویسید.",
        "بدون_pm: چاه‌هایی که اصلاً PM ندارند — PM را اضافه کنید.",
        "نام_چند_pm: یک نام چاه که به چند PM نگاشت شده — PM درست را مشخص کنید.",
    ]})

    sheets = {
        "راهنما": guide,
        "pم‌های_خراب": pd.DataFrame(corrupt_rows),
        "بدون_pm": pd.DataFrame(nopm_rows),
        "نام_چند_pm": pd.DataFrame(multi_rows),
    }
    with pd.ExcelWriter(out_path, engine="openpyxl") as xw:
        for name, df in sheets.items():
            df.to_excel(xw, sheet_name=name, index=False)
            ws = xw.sheets[name]
            ws.sheet_view.rightToLeft = True
            for col in ws.columns:
                width = max((len(str(c.value)) for c in col if c.value), default=10)
                ws.column_dimensions[col[0].column_letter].width = min(width + 4, 40)

    return {"corrupt_rows": len(corrupt_rows), "no_pm": len(nopm_rows),
            "name_multi_pm": len(multi_rows)}



################################################################################
# FILE: drilling_import.py
################################################################################

"""Idempotent importer for drilling/construction events.

Base source: Borwells.xlsx (one construction record per well), enriched from
حفاری.xlsx (executor, supervisor, credit source, actual depth, a/b coefficients,
address). Each imported record carries source='import:borwells' so re-running
updates in place instead of duplicating. Imported records are stored as
'approved' (historical, authoritative) and logged to the audit trail.
"""
from datetime import datetime

import pandas as pd

from app.extensions import db
from app.models.well import Well, WellIdentifier
from app.models.drilling import Drilling
from app.models.audit import RecordHistory
from app.utils.dates import parse_jalali
from app.imports.wells_import import (
    _norm_name, _clean, _intstr, _num, _build_pm_map, _col,
)

SOURCE = "import:borwells"

REQUEST_MAP = {"جدید": "new", "جابجایی": "relocation", "کف شکنی": "deepening", "کف‌شکنی": "deepening"}
METHOD_MAP = {"دورانی": "rotary", "ضربه‌ای": "percussion", "ضربه ای": "percussion"}


def _date(v):
    s = _clean(v)
    if not s:
        return None
    try:
        return parse_jalali(s)
    except Exception:
        return None


def _videometry(v):
    s = _clean(v)
    if not s or s in ("0", "-", "خیر", "نه"):
        return False
    return ("انجام" in s) or ("شد" in s) or (s == "بله")


def _find_exact(df, name):
    for c in df.columns:
        if str(c).strip() == name:
            return c
    return None


def _build_hafari_index(hafari_path):
    """klasse/name -> dict of enrichment fields from حفاری.xlsx."""
    hf = pd.read_excel(hafari_path, sheet_name="ALL", header=1)
    hf.columns = [str(c).strip() for c in hf.columns]
    cols = {
        "name": _col(hf, "نام چاه"),
        "klasse": _col(hf, "کلاسه"),
        "executor": _col(hf, "نام مجری"),
        "supervisor": _col(hf, "نام ناظر"),
        "credit": _col(hf, "محل تامین اعتبار"),
        "depth_actual": _col(hf, "عمق حفاری اصلاحی"),
        "address": _col(hf, "آدرس"),
        "a": _find_exact(hf, "a"),
        "b": _find_exact(hf, "b"),
    }
    by_klasse, by_name = {}, {}
    for _, r in hf.iterrows():
        extra = {
            "executor": _clean(r.get(cols["executor"])),
            "supervisor": _clean(r.get(cols["supervisor"])),
            "credit_source": _clean(r.get(cols["credit"])),
            "well_depth_actual": _num(r.get(cols["depth_actual"])),
            "address": _clean(r.get(cols["address"])),
            "coeff_a": _num(r.get(cols["a"])),
            "coeff_b": _num(r.get(cols["b"])),
        }
        k = _intstr(r.get(cols["klasse"]))
        if k:
            by_klasse.setdefault(k, extra)
        nm = _norm_name(r.get(cols["name"]))
        if nm:
            by_name.setdefault(nm, extra)
    return by_klasse, by_name


def _resolve_well(pm, klasse, name):
    if pm:
        w = db.session.scalar(db.select(Well).filter_by(pm_code=pm))
        if w:
            return w
    if klasse:
        wi = db.session.scalar(
            db.select(WellIdentifier).filter_by(id_type="klasse", value=klasse)
        )
        if wi:
            return db.session.get(Well, wi.well_id)
    if name:
        return db.session.scalar(db.select(Well).filter_by(name=name))
    return None


def run(borwells_path, tajmi_path, hafari_path, dry_run=False):
    stats = {"rows": 0, "created": 0, "updated": 0, "enriched": 0,
             "well_not_found": 0, "with_dates": 0}

    by_klasse, by_name = _build_pm_map(tajmi_path)
    hf_klasse, hf_name = _build_hafari_index(hafari_path)

    bw = pd.read_excel(borwells_path, sheet_name="ALL", header=1)
    bw.columns = [str(c).strip() for c in bw.columns]

    C = {
        "name": _col(bw, "نام چاه"), "permit": _col(bw, "پروانه"),
        "method": _col(bw, "روش حفاری"), "klasse": _col(bw, "کلاسه"),
        "contractor": _col(bw, "پیمانکار"), "contract_no": _col(bw, "شماره قرارداد"),
        "contract_date": _col(bw, "تاریخ قرارداد"),
        "start": _col(bw, "استقرار دستگاه"), "end": _col(bw, "ترخیص دستگاه"),
        "depth_permit": _col(bw, "عمق چاه در پروانه"),
        "casing_dia": _col(bw, "قطر لوله"), "casing_total": _col(bw, "طول کلی"),
        "steel_blank": _col(bw, "فولادی ساده"), "steel_screen": _col(bw, "فولادی مشبک"),
        "upvc_blank": _col(bw, "ساده UPVC"), "upvc_screen": _col(bw, "مشبک UPVC"),
        "transition": _col(bw, "قطعه تبدیلی"),
        "static": _col(bw, "سطح استاتیک"), "max_yield": _col(bw, "حداکثر آبدهی"),
        "proposed": _col(bw, "دبی پیشنهادی"), "dynamic": _col(bw, "سطح دینامیک"),
        "drawdown": _col(bw, "مقدار افت"), "video": _col(bw, "ویدیومتری"),
        "notes": _col(bw, "توضیحات"),
    }

    for _, row in bw.iterrows():
        name = _norm_name(row.get(C["name"]))
        if not name:
            continue
        stats["rows"] += 1
        klasse = _intstr(row.get(C["klasse"]))
        pm = None
        if klasse and klasse in by_klasse:
            pm = by_klasse[klasse][0]
        elif name in by_name:
            pm = by_name[name][0]

        well = _resolve_well(pm, klasse, name)
        if well is None:
            stats["well_not_found"] += 1
            continue

        # Natural key for a construction record: a well may have several
        # (original + redrill/relocation), distinguished by contract & start date.
        cn = _intstr(row.get(C["contract_no"]))
        sd = _date(row.get(C["start"]))
        rec = db.session.scalar(
            db.select(Drilling).filter_by(
                well_id=well.id, source=SOURCE, contract_no=cn, start_date=sd
            )
        )
        creating = rec is None
        if creating:
            rec = Drilling(well_id=well.id, source=SOURCE, status="approved",
                           approved_at=datetime.utcnow(), contract_no=cn, start_date=sd)
            db.session.add(rec)

        rec.request_type = REQUEST_MAP.get(_clean(row.get(C["permit"])))
        rec.drill_method = METHOD_MAP.get(_clean(row.get(C["method"])), "other")
        rec.contractor = _clean(row.get(C["contractor"]))
        rec.contract_no = cn
        rec.contract_date = _date(row.get(C["contract_date"]))
        rec.start_date = sd
        rec.end_date = _date(row.get(C["end"]))
        if rec.start_date or rec.end_date:
            stats["with_dates"] += 1
        rec.well_depth_permit = _num(row.get(C["depth_permit"]))
        rec.casing_diameter_in = _num(row.get(C["casing_dia"]))
        rec.casing_total_len = _num(row.get(C["casing_total"]))
        rec.steel_blank_len = _num(row.get(C["steel_blank"]))
        rec.steel_screen_len = _num(row.get(C["steel_screen"]))
        rec.upvc_blank_len = _num(row.get(C["upvc_blank"]))
        rec.upvc_screen_len = _num(row.get(C["upvc_screen"]))
        rec.transition_len = _num(row.get(C["transition"]))
        rec.static_level = _num(row.get(C["static"]))
        rec.max_yield_lps = _num(row.get(C["max_yield"]))
        rec.proposed_discharge_lps = _num(row.get(C["proposed"]))
        rec.dynamic_at_proposed = _num(row.get(C["dynamic"]))
        rec.drawdown = _num(row.get(C["drawdown"]))
        rec.videometry_done = _videometry(row.get(C["video"]))
        note = _clean(row.get(C["notes"]))
        rec.notes = None if note in (None, "-") else note

        # enrich from حفاری
        extra = (hf_klasse.get(klasse) if klasse else None) or hf_name.get(name)
        if extra:
            rec.executor = extra["executor"]
            rec.supervisor = extra["supervisor"]
            rec.credit_source = extra["credit_source"]
            rec.well_depth_actual = extra["well_depth_actual"]
            rec.address = extra["address"]
            if extra["coeff_a"] is not None:
                rec.coeff_a = extra["coeff_a"]
            if extra["coeff_b"] is not None:
                rec.coeff_b = extra["coeff_b"]
            stats["enriched"] += 1

        db.session.flush()
        if creating:
            db.session.add(RecordHistory(
                entity_type="drilling", entity_id=rec.id, action="create",
                user_id=None, detail="وارد شده از Borwells/حفاری",
            ))
        stats["created" if creating else "updated"] += 1

    if dry_run:
        db.session.rollback()
    else:
        db.session.commit()
    return stats



################################################################################
# FILE: duplicates_export.py
################################################################################

"""Export the remaining duplicate groups (after auto stub-merge) for manual review.

Lists every well still sharing a normalized base-name with another, with a
per-table data breakdown so the user can decide which to keep / merge. Only
groups with >1 member are included; members sorted by total data desc.
"""
from collections import defaultdict

import pandas as pd
from sqlalchemy import text

from app.extensions import db
from app.services.data_export import dup_group

TABLES = [
    ("monthly_production", "تولید ماهانه"), ("flow_tests", "دبی‌سنجی"),
    ("pump_tests", "آزمایش پمپاژ"), ("drilling", "حفاری"),
    ("pump_installations", "نصب/کشیدن"), ("rehabilitations", "بهسازی"),
    ("videometry_logs", "چاه‌نگاری"), ("pump_selections", "انتخاب پمپ"),
    ("water_level_logs", "تراز آب"), ("water_quality", "کیفیت"),
    ("maintenance_records", "نگهداری"), ("relocations", "جابه‌جایی"),
]


def export(out_path="remaining_duplicates.xlsx"):
    from app.models.well import Well
    from app.models.constants import WELL_STATUSES
    status_l = dict(WELL_STATUSES)

    per_table = {}
    for t, _label in TABLES:
        d = defaultdict(int)
        for wid, n in db.session.execute(
                text(f"SELECT well_id, COUNT(*) FROM {t} GROUP BY well_id")):
            if wid is not None:
                d[wid] = n
        per_table[t] = d

    wells = db.session.scalars(db.select(Well)).all()
    groups = defaultdict(list)
    for w in wells:
        groups[dup_group(w.name)].append(w)

    rows = []
    for key, members in groups.items():
        if len(members) < 2:
            continue
        enriched = []
        for w in members:
            total = sum(per_table[t].get(w.id, 0) for t, _ in TABLES)
            enriched.append((w, total))
        enriched.sort(key=lambda x: -x[1])
        for rank, (w, total) in enumerate(enriched):
            row = {
                "گروه": key, "نقش پیشنهادی": "اصلی (پرداده)" if rank == 0 else "بررسی",
                "نام چاه": w.name, "کد PM": w.pm_code,
                "PM مصنوعی؟": "بله" if not w.has_pm else "خیر",
                "اداره": w.office.name if w.office else "",
                "وضعیت": status_l.get(w.status, w.status),
                "مختصات": "دارد" if w.latitude is not None else "—",
                "مجموع داده": total,
            }
            for t, label in TABLES:
                row[label] = per_table[t].get(w.id, 0) or ""
            row["تصمیم (نگه‌داشتن/ادغام/حذف)"] = ""
            rows.append(row)

    df = pd.DataFrame(rows).sort_values(["گروه", "مجموع داده"],
                                        ascending=[True, False], kind="stable")
    n_groups = df["گروه"].nunique() if len(df) else 0
    with pd.ExcelWriter(out_path, engine="openpyxl") as xl:
        df.to_excel(xl, sheet_name="گروه‌های_تکراری", index=False)
        ws = xl.sheets["گروه‌های_تکراری"]
        for col in ws.columns:
            wdt = max((len(str(c.value)) for c in col if c.value is not None), default=10)
            ws.column_dimensions[col[0].column_letter].width = min(max(wdt + 2, 10), 36)
    return {"groups": n_groups, "wells": len(df), "out_path": out_path}



################################################################################
# FILE: electricity_import.py
################################################################################

"""Import monthly electricity (kWh + cost) from electricity.xlsx into
monthly_production, enabling specific energy (kWh/m³).

STRICT matching ("انطباق کامل"): an energy row is imported ONLY when two
independent identifiers agree on the same registry well —
  (1) the official electricity dossier (شماره پرونده / رمز رايانه) resolved via
      the bridge sheet 'کل چاهها' to an ABFA well name, AND
  (2) the energy row's own well name (نام, minus the 'چاه ' prefix).
Rows where the two disagree, or only one resolves, or neither resolves, are
skipped and counted. Period 140409 -> Jalali 1404/09. Re-runnable.
"""
import openpyxl

from app.extensions import db
from app.models.well import Well
from app.models.production import MonthlyProduction
from app.imports.wells_import import match_key, _clean, _num

SOURCE = "import:electricity"
ENERGY_SHEET = "Energy_Cost_2026_02_02-11_15"
BRIDGE_SHEET = "کل چاهها"

# energy-sheet column indices
E_PERIOD, E_PARVANDE, E_RAMZ, E_NAME = 0, 1, 2, 5
E_CONTRACT_KW, E_CONSUMED_KW, E_TOTAL_KWH, E_COST = 11, 13, 19, 32


def _period_to_jalali(v):
    """'140409' -> (1404, 9)."""
    s = _clean(v)
    if not s or len(s) < 5:
        return None, None
    s = s.zfill(6)
    return int(s[:4]), int(s[4:6])


def _build_bridge(wb):
    ws = wb[BRIDGE_SHEET]
    hdr = next(ws.iter_rows(values_only=True))
    idx = {h: i for i, h in enumerate(hdr) if h}
    ci_par, ci_id, ci_nm = idx["شماره پرونده"], idx["شناسايي برق"], idx["نام چاه"]
    par2name, id2name = {}, {}
    for r in ws.iter_rows(min_row=2, values_only=True):
        nm = _clean(r[ci_nm]) if ci_nm < len(r) else None
        if not nm:
            continue
        if ci_par < len(r) and r[ci_par] not in (None, ""):
            par2name[_clean(r[ci_par])] = nm
        if ci_id < len(r) and r[ci_id] not in (None, ""):
            id2name[_clean(r[ci_id])] = nm
    return par2name, id2name


def run(path="current data/electricity.xlsx", dry_run=False):
    stats = {"rows": 0, "matched": 0, "created": 0, "updated": 0,
             "skip_conflict": 0, "skip_single_key": 0, "skip_unmatched": 0}

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    par2name, id2name = _build_bridge(wb)

    reg = {}
    for w in db.session.scalars(db.select(Well)).all():
        reg.setdefault(w.match_key, []).append(w)

    def resolve(name):
        if not name:
            return None
        cands = reg.get(match_key(name), [])
        return cands[0] if len(cands) == 1 else None

    existing = {(m.well_id, m.jyear, m.jmonth): m
                for m in db.session.scalars(db.select(MonthlyProduction)).all()}

    ws = wb[ENERGY_SHEET]
    for r in ws.iter_rows(min_row=2, values_only=True):
        if not r or r[E_PERIOD] in (None, ""):
            continue
        stats["rows"] += 1
        jy, jm = _period_to_jalali(r[E_PERIOD])
        if jy is None:
            continue

        bridge_name = par2name.get(_clean(r[E_PARVANDE])) or id2name.get(_clean(r[E_RAMZ]))
        w_bridge = resolve(bridge_name)
        w_name = resolve(str(r[E_NAME]).replace("چاه", "", 1) if r[E_NAME] else None)

        # STRICT: both independent keys must resolve to the SAME well
        if w_bridge and w_name:
            if w_bridge.id != w_name.id:
                stats["skip_conflict"] += 1
                continue
            well = w_bridge
        elif w_bridge or w_name:
            stats["skip_single_key"] += 1
            continue
        else:
            stats["skip_unmatched"] += 1
            continue

        stats["matched"] += 1
        key = (well.id, jy, jm)
        rec = existing.get(key)
        if rec is None:
            rec = MonthlyProduction(well_id=well.id, jyear=jy, jmonth=jm, source=SOURCE)
            db.session.add(rec)
            existing[key] = rec
            stats["created"] += 1
        else:
            stats["updated"] += 1
        rec.energy_kwh = _num(r[E_TOTAL_KWH], zero_is_null=False)
        rec.energy_cost_rial = _num(r[E_COST], zero_is_null=False)
        rec.contract_power_kw = _num(r[E_CONTRACT_KW], zero_is_null=False)
        rec.consumed_power_kw = _num(r[E_CONSUMED_KW], zero_is_null=False)

    if dry_run:
        db.session.rollback()
    else:
        db.session.commit()
    return stats



################################################################################
# FILE: flow_import.py
################################################################################

"""Idempotent importer for flow-metering (دبی‌سنجی) from تجمیعی (400-405).xlsx.

Each تجمیعی row is one operating point (کارکرد); rows are grouped by
(well, test_date) into a FlowTest header + its FlowTestPoint children. Wells are
matched by name + office (the source pm is corrupt). Imported tests are stored
as 'approved' (historical) with an audit entry; re-running updates in place.
"""
from datetime import datetime

import pandas as pd

from app.extensions import db
from app.models.well import Well
from app.models.flow import FlowTest, FlowTestPoint
from app.models.audit import RecordHistory
from app.utils.dates import parse_jalali
from app.imports.wells_import import (
    _norm_name, _clean, _num, _intstr, match_key, _office_getter,
)

SOURCE = "import:tajmi"

# exact column names in تجمیعی "تجمیع دبی‌سنجی"
C = {
    "name": "نام چاه", "office": "نام اداره", "test_date": "تاریخ آزمایش",
    "op_no": "شماره کارکرد", "op_type": "نوع کارکرد", "efficiency": "راندمان",
    "mech": "توان مکانیکی (Kw)", "cos": "کسینوس فی", "react": "توان راکتیو (Kvar)",
    "active": "توان اکتیو (Kw)", "amperes": "آمپرها (A)", "head": "هد (m)",
    "drawdown": "میزان افت (m)", "disch_m3h": "آبدهی (m3/hr)", "dynamic": "سطح پویایی (m)",
    "pressure": "فشار (atm)", "disch_lps": "آبدهی (lit/s)", "apparent": "توان ظاهری (KVA)",
    "energy": "مصرف ویژه انرژی (Kwh/m3)", "wcol": "ستون آب (m)", "wcol_ch": "تغییر ستون آب (m)",
    # header
    "ep": "تیپ الکتروپمپ", "ep_prev": "تیپ الکتروپمپ قبلی", "install_date": "تاریخ نصب",
    "install_depth": "عمق نصب", "well_depth": "عمق چاه", "constr": "نوع چاه",
    "allowed_q": "دبی مجاز", "power_sub": "اشتراک برق", "static": "سطح ایستایی",
    "static_prev": "سطح ایستایی قبلی", "last_rehab": "تاریخ آخرین بهسازی",
    "pull": "علت کشیدن پمپ", "meter": "کالیبراسیون/وضعیت کنتور", "starter": "نوع تابلو راه‌انداز",
    "reason": "دلیل آزمایش", "network": "نوع شبکه", "line_p": "فشار خط",
    "v_on": "ولتاژ روشن", "v_off": "ولتاژ خاموش", "ohm_ff": "مقاومت اهمی ف-ف",
    "ohm_fg": "مقاومت اهمی ف-ب", "cap": "ظرفیت خازن",
}


def _date(v):
    s = _clean(v)
    if not s:
        return None
    try:
        return parse_jalali(s)
    except Exception:
        return None


def _opno(v):
    s = _intstr(v)
    if s and s.lstrip("-").isdigit():
        return int(float(s))
    return None


def run(tajmi_path, dry_run=False):
    stats = {"rows": 0, "tests_created": 0, "tests_updated": 0, "points": 0,
             "wells_matched": 0, "unmatched_rows": 0, "no_date_rows": 0}

    tj = pd.read_excel(tajmi_path, sheet_name="تجمیع دبی‌سنجی")
    tj.columns = [str(c).strip() for c in tj.columns]
    get_office = _office_getter()

    # well resolver cache: (name_key, office_id) -> well
    wcache = {}

    def resolve_well(name, office_token):
        nk = match_key(name)
        oid = get_office(office_token)
        ck = (nk, oid)
        if ck in wcache:
            return wcache[ck]
        w = db.session.scalar(db.select(Well).filter_by(match_key=nk, office_id=oid))
        if w is None:  # fall back to name-only if unambiguous
            cands = db.session.scalars(db.select(Well).filter_by(match_key=nk)).all()
            w = cands[0] if len(cands) == 1 else None
        wcache[ck] = w
        return w

    # group rows by (well_id, test_date)
    groups = {}   # (well_id, date) -> {"header": row, "points": [rows]}
    for _, r in tj.iterrows():
        name = _norm_name(r.get(C["name"]))
        if not name:
            continue
        stats["rows"] += 1
        td = _date(r.get(C["test_date"]))
        if td is None:
            stats["no_date_rows"] += 1
            continue
        well = resolve_well(name, _clean(r.get(C["office"])))
        if well is None:
            stats["unmatched_rows"] += 1
            continue
        key = (well.id, td)
        g = groups.setdefault(key, {"header": r, "points": []})
        g["points"].append(r)

    stats["wells_matched"] = len({k[0] for k in groups})

    for (well_id, td), g in groups.items():
        h = g["header"]
        rec = db.session.scalar(db.select(FlowTest).filter_by(
            well_id=well_id, test_date=td, source=SOURCE))
        creating = rec is None
        if creating:
            rec = FlowTest(well_id=well_id, test_date=td, source=SOURCE,
                           status="approved", approved_at=datetime.utcnow())
            db.session.add(rec)

        rec.test_reason = _clean(h.get(C["reason"]))
        rec.network_type = _clean(h.get(C["network"]))
        rec.electropump_type = _clean(h.get(C["ep"]))
        rec.electropump_type_prev = _clean(h.get(C["ep_prev"]))
        rec.install_date = _date(h.get(C["install_date"]))
        rec.install_depth = _num(h.get(C["install_depth"]))
        rec.well_depth = _num(h.get(C["well_depth"]))
        rec.construction_type = _clean(h.get(C["constr"]))
        rec.allowed_q = _num(h.get(C["allowed_q"]))
        rec.power_subscription = _clean(h.get(C["power_sub"]))
        rec.static_level = _num(h.get(C["static"]))
        rec.static_level_prev = _num(h.get(C["static_prev"]))
        rec.last_rehab_date = _date(h.get(C["last_rehab"]))
        rec.pull_reason = _clean(h.get(C["pull"]))
        rec.meter_status = _clean(h.get(C["meter"]))
        rec.starter_type = _clean(h.get(C["starter"]))
        rec.line_pressure = _num(h.get(C["line_p"]))
        rec.voltage_on = _clean(h.get(C["v_on"]))
        rec.voltage_off = _clean(h.get(C["v_off"]))
        rec.ohm_ff = _clean(h.get(C["ohm_ff"]))
        rec.ohm_fg = _clean(h.get(C["ohm_fg"]))
        rec.capacitor_capacity = _num(h.get(C["cap"]))
        db.session.flush()

        rec.points.clear()
        for i, p in enumerate(g["points"], start=1):
            rec.points.append(FlowTestPoint(
                operating_no=_opno(p.get(C["op_no"])) or i,
                operating_type=_clean(p.get(C["op_type"])),
                efficiency=_num(p.get(C["efficiency"])),
                mechanical_power_kw=_num(p.get(C["mech"])),
                cos_phi=_num(p.get(C["cos"])),
                reactive_power_kvar=_num(p.get(C["react"])),
                active_power_kw=_num(p.get(C["active"])),
                apparent_power_kva=_num(p.get(C["apparent"])),
                amperes=_clean(p.get(C["amperes"])),
                head_m=_num(p.get(C["head"])),
                drawdown_m=_num(p.get(C["drawdown"])),
                discharge_m3h=_num(p.get(C["disch_m3h"])),
                discharge_lps=_num(p.get(C["disch_lps"])),
                dynamic_level_m=_num(p.get(C["dynamic"])),
                pressure_atm=_num(p.get(C["pressure"])),
                water_column_m=_num(p.get(C["wcol"])),
                water_column_change=_num(p.get(C["wcol_ch"])),
                energy_intensity_kwh_m3=_num(p.get(C["energy"])),
            ))
            stats["points"] += 1

        db.session.flush()
        if creating:
            db.session.add(RecordHistory(entity_type="flow_tests", entity_id=rec.id,
                                         action="create", user_id=None,
                                         detail="وارد شده از تجمیعی"))
            stats["tests_created"] += 1
        else:
            stats["tests_updated"] += 1

    if dry_run:
        db.session.rollback()
    else:
        db.session.commit()
    return stats



################################################################################
# FILE: flow_reconcile.py
################################################################################

"""Reconcile the two flow-metering sources without data loss.

rawflow (detailed per-form) is canonical; tajmi (aggregated) is merged into it
for exact (well_id, test_date) duplicates: any field/point value that rawflow is
missing but tajmi has is copied over, THEN the duplicate tajmi test is deleted.
tajmi tests with no rawflow counterpart (e.g. 1405) are kept as-is. Idempotent.
"""
from collections import defaultdict

from app.extensions import db
from app.models.flow import FlowTest, FlowTestPoint
from app.models.audit import RecordHistory

HEADER_COLS = [
    "test_reason", "network_type", "electropump_type", "electropump_type_prev",
    "install_date", "install_depth", "well_depth", "construction_type", "allowed_q",
    "design_q", "license_q", "power_subscription", "static_level", "static_level_prev",
    "last_rehab_date", "pull_reason", "meter_status", "meter_brand", "starter_type",
    "capacitor_capacity", "voltage_on", "voltage_off", "ohm_ff", "ohm_fg",
    "line_pressure", "regulated_pressure", "discharge_volume_m3", "expert_note",
]
POINT_COLS = [
    "operating_type", "discharge_m3h", "discharge_lps", "head_m", "drawdown_m",
    "dynamic_level_m", "pressure_atm", "water_column_m", "water_column_change",
    "amperes", "efficiency", "cos_phi", "active_power_kw", "reactive_power_kvar",
    "apparent_power_kva", "mechanical_power_kw", "energy_intensity_kwh_m3",
]


def _empty(v):
    return v is None or (isinstance(v, str) and not v.strip())


def _fill(dst, src, cols):
    """Copy non-empty src.col into dst.col where dst.col is empty. Returns #filled."""
    n = 0
    for c in cols:
        if _empty(getattr(dst, c)) and not _empty(getattr(src, c)):
            setattr(dst, c, getattr(src, c))
            n += 1
    return n


def run(dry_run=False):
    stats = {"duplicates": 0, "header_fields_filled": 0, "points_filled": 0,
             "points_added": 0, "tajmi_deleted": 0,
             "kept_tajmi_only": 0, "kept_rawflow_only": 0}

    raw_by_key = {}
    taj_by_key = {}
    for t in db.session.scalars(db.select(FlowTest)).all():
        if t.source == "import:rawflow":
            raw_by_key[(t.well_id, t.test_date)] = t
        elif t.source == "import:tajmi":
            taj_by_key[(t.well_id, t.test_date)] = t

    stats["kept_rawflow_only"] = len(set(raw_by_key) - set(taj_by_key))
    stats["kept_tajmi_only"] = len(set(taj_by_key) - set(raw_by_key))

    for key, taj in list(taj_by_key.items()):
        raw = raw_by_key.get(key)
        if raw is None:
            continue  # tajmi-only -> keep
        stats["duplicates"] += 1

        # header enrichment
        stats["header_fields_filled"] += _fill(raw, taj, HEADER_COLS)

        # point enrichment (match by operating_no)
        raw_pts = {p.operating_no: p for p in raw.points if p.operating_no is not None}
        for tp in taj.points:
            rp = raw_pts.get(tp.operating_no)
            if rp is not None:
                stats["points_filled"] += _fill(rp, tp, POINT_COLS)
            else:
                np = FlowTestPoint(operating_no=tp.operating_no)
                for c in POINT_COLS:
                    setattr(np, c, getattr(tp, c))
                raw.points.append(np)
                stats["points_added"] += 1

        # delete the duplicate tajmi test + its audit rows
        db.session.query(RecordHistory).filter_by(
            entity_type="flow_tests", entity_id=taj.id).delete(synchronize_session=False)
        db.session.delete(taj)
        stats["tajmi_deleted"] += 1

    if dry_run:
        db.session.rollback()
    else:
        db.session.commit()
    return stats



################################################################################
# FILE: install_import.py
################################################################################

"""Idempotent importer for pump installation/pull records.

Source: 'نصب و کشیدن پمپ- تجمیعی.xlsx' sheet 'نصب‌ها_با_مشخصات' (one row per
installation, with its pull date + useful life). Wells matched by name; suppliers
(سازنده / پیمانکار) get-or-created. Imported as approved/locked with audit.
"""
import re
from datetime import datetime

import pandas as pd

from app.extensions import db
from app.models.well import Well
from app.models.pump_asset import PumpInstallation, Supplier
from app.models.audit import RecordHistory
from app.utils.dates import parse_jalali
from app.imports.wells_import import _norm_name, _clean, _num, _intstr, match_key

SOURCE = "import:nasb"
COND = {"نو": "new", "تعمیری": "repaired"}


def _date(v):
    s = _clean(v)
    if not s:
        return None
    try:
        return parse_jalali(s)
    except Exception:
        return None


def _supplier_getter():
    cache = {}

    def get(name, kind):
        from app.models.constants import canonical_supplier
        name = canonical_supplier(_clean(name))
        if not name:
            return None
        if name in cache:
            return cache[name]
        s = db.session.scalar(db.select(Supplier).filter_by(name=name))
        if s is None:
            s = Supplier(name=name, kind=kind)
            db.session.add(s)
            db.session.flush()
        cache[name] = s.id
        return s.id

    return get


def _col(df, *keys):
    for c in df.columns:
        name = str(c).strip()
        if all(k in name for k in keys):
            return c
    return None


def run(nasb_path, dry_run=False):
    stats = {"rows": 0, "created": 0, "updated": 0, "well_not_found": 0, "suppliers": 0}

    df = pd.read_excel(nasb_path, sheet_name="نصب‌ها_با_مشخصات")
    df.columns = [str(c).strip() for c in df.columns]
    C = {
        "name": _col(df, "نام چاه"), "install_no": _col(df, "شماره نصب"),
        "install_date": _col(df, "تاریخ نصب"), "pull_date": _col(df, "تاریخ کشیدن"),
        "motor": _col(df, "موتور"), "motor_cond": _col(df, "موتور نو"),
        "pump": _col(df, "پمپ"), "maker": _col(df, "سازنده"),
        "pump_cond": _col(df, "پمپ نو"), "stages": _col(df, "طبقه"),
        "depth": _col(df, "عمق"), "contractor": _col(df, "پیمانکار"),
    }
    get_supplier = _supplier_getter()

    # well lookup by name-key
    well_by_key = {}
    for w in db.session.scalars(db.select(Well)).all():
        well_by_key.setdefault(w.match_key, w)

    for _, r in df.iterrows():
        name = _norm_name(r.get(C["name"]))
        if not name:
            continue
        stats["rows"] += 1
        well = well_by_key.get(match_key(name))
        if well is None:
            stats["well_not_found"] += 1
            continue

        idate = _date(r.get(C["install_date"]))
        pump_type = _clean(r.get(C["pump"]))
        rec = db.session.scalar(db.select(PumpInstallation).filter_by(
            well_id=well.id, source=SOURCE, install_date=idate, pump_type=pump_type))
        creating = rec is None
        if creating:
            rec = PumpInstallation(well_id=well.id, source=SOURCE, install_date=idate,
                                   pump_type=pump_type, status="approved",
                                   approved_at=datetime.utcnow())
            db.session.add(rec)

        no = _intstr(r.get(C["install_no"]))
        m = re.search(r"\d+", no) if no else None
        rec.install_no = int(m.group(0)) if m else None
        rec.pull_date = _date(r.get(C["pull_date"]))
        rec.motor_power_kw = _num(r.get(C["motor"]))
        rec.motor_condition = COND.get(_clean(r.get(C["motor_cond"])))
        rec.pump_condition = COND.get(_clean(r.get(C["pump_cond"])))
        st = _intstr(r.get(C["stages"]))
        rec.pump_stages = int(st) if st and st.isdigit() else None
        rec.install_depth_m = _num(r.get(C["depth"]))
        rec.manufacturer_id = get_supplier(r.get(C["maker"]), "manufacturer")
        rec.contractor_id = get_supplier(r.get(C["contractor"]), "contractor")

        db.session.flush()
        if creating:
            db.session.add(RecordHistory(entity_type="pump_installations", entity_id=rec.id,
                                         action="create", user_id=None,
                                         detail="وارد شده از فایل نصب و کشیدن"))
            stats["created"] += 1
        else:
            stats["updated"] += 1

    stats["suppliers"] = db.session.scalar(db.select(db.func.count(Supplier.id)))
    if dry_run:
        db.session.rollback()
    else:
        db.session.commit()
    return stats



################################################################################
# FILE: permit_import.py
################################################################################

"""ورود وضعیت پروانه‌ی چاه‌ها از فایل پایگاه داده‌ی چاه‌ها.

منبع اصلی: شیت «کل چاهها» (پوشش کامل ستون‌های پروانه: کد/نوع/شماره/تاریخ آخرین
پروانه، تاریخ اعتبار، وضعیت پرونده). جریمه‌ی انقضا و پیگیری درخواست از شیت
«Data Base» تکمیل می‌شود (در صورت وجود).

تطبیق چاه = match_key(نام) [+ اداره در صورت ابهام]. یک رکورد WellPermit به‌ازای
هر چاه. ایدمپوتنت (source='import:permit'): اجرای مجدد رکورد موجود را به‌روزرسانی
می‌کند، نه تکراری.
"""
import openpyxl

from app.extensions import db
from app.models.well import Well
from app.models.permit import WellPermit
from app.imports.wells_import import match_key, _clean, _num
from app.imports.production_import import _office_resolver
from app.utils.dates import to_english_digits

SOURCE = "import:permit"

# --- شیت «کل چاهها» (هدر در ردیف 1، داده از ردیف 2) ---
SHEET_MAIN = "کل چاهها"
M = {
    "name": 1, "office": None,        # این شیت ستون اداره‌ی جدا ندارد؛ از مرکز/نام تطبیق می‌شود
    "case_status": 13,                # وضعیت پرونده
    "permit_code": 15,                # کد آخرین پروانه
    "permit_type": 16,                # نوع آخرین پروانه
    "permit_no": 17,                  # شماره آخرین پروانه
    "permit_date": 18,                # تاریخ آخرین پروانه
    "expiry_date": 19,                # تاریخ اعتبار تا
}

# --- شیت «Data Base» (هدر ترکیبی ردیف 1و2، داده از ردیف 3) ---
SHEET_FOLLOW = "Data Base"
D = {
    "name": 1, "center": 2, "tariff": 3, "power_kw": 4,
    "expiry_penalty_rial": 7,
    "klasse": 10, "request_type": 11, "followup_stage": 12, "cost_paid": 13,
    "notes": 14,
}


def _norm_jdate(v):
    """هر فرمت تاریخ شمسی (فشرده/با اسلش/فارسی) را به 'yyyy/mm/dd' برمی‌گرداند."""
    s = to_english_digits(str(v or "")).strip()
    if not s:
        return None
    digits = "".join(ch for ch in s if ch.isdigit())
    if len(digits) == 8:
        return f"{digits[:4]}/{digits[4:6]}/{digits[6:8]}"
    # اگر با جداکننده بود
    for sep in ("/", "-", "."):
        s = s.replace(sep, "/")
    parts = [p for p in s.split("/") if p]
    if len(parts) == 3:
        y, m, d = parts
        return f"{int(y):04d}/{int(m):02d}/{int(d):02d}"
    return None


def _truthy(v):
    s = _clean(v)
    if s is None:
        return None
    return s in ("✔", "✓", "بله", "دارد", "1", "true", "True", "yes")


def run(path="current data/Data_Base_of_Wells.xlsx", dry_run=False):
    stats = {"main_rows": 0, "created": 0, "updated": 0, "unmatched": 0,
             "follow_rows": 0, "follow_matched": 0}

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)

    # well lookup
    by_key, by_key_office = {}, {}
    for w in db.session.scalars(db.select(Well)).all():
        by_key.setdefault(w.match_key, []).append(w)
        by_key_office[(w.match_key, w.office_id)] = w
    existing = {p.well_id: p for p in db.session.scalars(db.select(WellPermit)).all()}

    def find_well(name, office_token=None):
        nk = match_key(name)
        if not nk:
            return None
        cands = by_key.get(nk, [])
        if len(cands) == 1:
            return cands[0]
        if office_token is not None:
            oid = _office_resolver()(office_token)
            w = by_key_office.get((nk, oid))
            if w:
                return w
        return cands[0] if cands else None

    # ---------- پاس ۱: شیت اصلی «کل چاهها» ----------
    ws = wb[SHEET_MAIN]
    rows = list(ws.iter_rows(values_only=True))
    for row in rows[2:]:
        name = _clean(row[M["name"]]) if len(row) > M["name"] else None
        if not name:
            continue
        stats["main_rows"] += 1

        def cell(c):
            return row[c] if (c is not None and c < len(row)) else None

        well = find_well(name)
        if well is None:
            stats["unmatched"] += 1
            continue

        rec = existing.get(well.id)
        if rec is None:
            rec = WellPermit(well_id=well.id, source=SOURCE, status="approved")
            db.session.add(rec)
            existing[well.id] = rec
            stats["created"] += 1
        else:
            stats["updated"] += 1

        rec.case_status = _clean(cell(M["case_status"]))
        rec.permit_code = _clean(cell(M["permit_code"]))
        rec.permit_type = _clean(cell(M["permit_type"]))
        rec.permit_no = _clean(cell(M["permit_no"]))
        rec.permit_date = _norm_jdate(cell(M["permit_date"]))
        rec.expiry_date = _norm_jdate(cell(M["expiry_date"]))

    # ---------- پاس ۲: شیت «Data Base» (پیگیری + جریمه) ----------
    if SHEET_FOLLOW in wb.sheetnames:
        ws2 = wb[SHEET_FOLLOW]
        rows2 = list(ws2.iter_rows(values_only=True))
        for row in rows2[3:]:
            name = _clean(row[D["name"]]) if len(row) > D["name"] else None
            if not name:
                continue
            stats["follow_rows"] += 1

            def cell2(c):
                return row[c] if c < len(row) else None

            well = find_well(name, cell2(D["center"]))
            if well is None:
                continue
            stats["follow_matched"] += 1

            rec = existing.get(well.id)
            if rec is None:
                rec = WellPermit(well_id=well.id, source=SOURCE, status="approved")
                db.session.add(rec)
                existing[well.id] = rec
                stats["created"] += 1

            rec.tariff = _clean(cell2(D["tariff"])) or rec.tariff
            rec.contract_power_kw = _num(cell2(D["power_kw"])) or rec.contract_power_kw
            rec.expiry_penalty_rial = _num(cell2(D["expiry_penalty_rial"]))
            rec.klasse = _clean(cell2(D["klasse"])) or rec.klasse
            rec.request_type = _clean(cell2(D["request_type"]))
            rec.followup_stage = _clean(cell2(D["followup_stage"]))
            rec.cost_paid = _truthy(cell2(D["cost_paid"]))
            note = _clean(cell2(D["notes"]))
            if note:
                rec.notes = note

    if dry_run:
        db.session.rollback()
    else:
        db.session.commit()
    return stats



################################################################################
# FILE: production_import.py
################################################################################

"""Idempotent importer for the monthly operational time-series.

Source: 'روند تولید چاه ها.xlsx' — a WIDE pivot (596 wells × 444 cols) where each
metric is spread across one column per Jalali month for 1399..1405. We MELT it
into the long `monthly_production` table (one row per well/year/month).

Metrics & their header shapes (normalized):
  production_m3      "تولید YYYY(MONTH)"
  avg_discharge_lps  "دبی متوسط YYYY(MONTH)"
  well_pressure      "فشار چاه YYYY(MONTH)"
  run_hours          "کارکرد MONTH YYYY"     (month-then-year, no parens)

Wells are matched by (match_key(name), office) — NOT pm_code. Re-runnable: rows
carry source="import:trend" and are updated in place on (well_id, jyear, jmonth).
"""
import re

import openpyxl

from app.extensions import db
from app.models.well import Well
from app.models.org import OrgUnit
from app.models.production import MonthlyProduction
from app.imports.wells_import import match_key, _num, _clean
from app.utils.dates import to_english_digits

SOURCE = "import:trend"

_MONTHS = {
    "فروردین": 1, "اردیبهشت": 2, "خرداد": 3, "تیر": 4, "مرداد": 5, "شهریور": 6,
    "مهر": 7, "آبان": 8, "آذر": 9, "دی": 10, "بهمن": 11, "اسفند": 12,
}


def _norm_hdr(s):
    s = to_english_digits("" if s is None else str(s))
    s = s.replace("ي", "ی").replace("ك", "ک")
    return " ".join(s.split()).strip()


def _build_colmap(headers):
    """header-index -> (metric, jyear, jmonth) for the four monthly series."""
    months = "|".join(_MONTHS)
    pat_paren = re.compile(r"^(.+?)\s*(\d{4})\s*\(\s*(" + months + r")\s*\)$")
    pat_run = re.compile(r"^کارکرد\s+(" + months + r")\s+(\d{4})$")
    metric_by_prefix = {
        "تولید": "production_m3",
        "دبی متوسط": "avg_discharge_lps",
        "فشار چاه": "well_pressure",
    }
    colmap = {}
    for idx, h in enumerate(headers):
        hh = _norm_hdr(h)
        if not hh:
            continue
        m = pat_paren.match(hh)
        if m:
            prefix, yr, mon = m.group(1).strip(), int(m.group(2)), _MONTHS[m.group(3)]
            metric = metric_by_prefix.get(prefix)
            if metric:
                colmap[idx] = (metric, yr, mon)
            continue
        m = pat_run.match(hh)
        if m:
            colmap[idx] = ("run_hours", int(m.group(2)), _MONTHS[m.group(1)])
    return colmap


def _office_resolver():
    """token (اداره) -> office_id, fuzzy-contains against existing offices."""
    offices = db.session.scalars(
        db.select(OrgUnit).filter_by(unit_type="office")).all()
    cache = {}

    def resolve(token):
        token = _clean(token)
        if not token:
            return None
        token = token.replace("ي", "ی").replace("ك", "ک")
        if token in cache:
            return cache[token]
        oid = None
        for o in offices:
            on = (o.name or "").replace("ي", "ی").replace("ك", "ک")
            if token in on or on in token:
                oid = o.id
                break
        cache[token] = oid
        return oid

    return resolve


def run(path="current data/روند تولید چاه ها.xlsx", dry_run=False):
    stats = {"rows": 0, "wells_matched": 0, "unmatched_rows": 0,
             "periods_created": 0, "periods_updated": 0, "cells": 0, "empty_periods": 0}

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    rows = ws.iter_rows(values_only=True)
    headers = list(next(rows))
    colmap = _build_colmap(headers)
    if not colmap:
        raise RuntimeError("No monthly metric columns recognized in header.")

    office_of = _office_resolver()

    # well lookup indexes
    by_key_office, by_key = {}, {}
    for w in db.session.scalars(db.select(Well)).all():
        by_key.setdefault(w.match_key, []).append(w)
        by_key_office[(w.match_key, w.office_id)] = w

    matched_well_ids = set()
    # existing rows for idempotency: (well_id, jyear, jmonth) -> record
    existing = {}
    for mp in db.session.scalars(
            db.select(MonthlyProduction).filter_by(source=SOURCE)).all():
        existing[(mp.well_id, mp.jyear, mp.jmonth)] = mp

    for row in rows:
        name = _clean(row[0]) if row else None
        if not name:
            continue
        stats["rows"] += 1
        nk = match_key(name)
        oid = office_of(row[1] if len(row) > 1 else None)
        well = by_key_office.get((nk, oid))
        if well is None:  # fall back to name-only if unambiguous
            cands = by_key.get(nk, [])
            well = cands[0] if len(cands) == 1 else None
        if well is None:
            stats["unmatched_rows"] += 1
            continue
        matched_well_ids.add(well.id)

        # gather metrics per (year, month)
        periods = {}   # (jyear, jmonth) -> {metric: value}
        for idx, (metric, yr, mon) in colmap.items():
            if idx >= len(row):
                continue
            val = _num(row[idx], zero_is_null=False)
            if val is None:
                continue
            periods.setdefault((yr, mon), {})[metric] = val
            stats["cells"] += 1

        for (yr, mon), vals in periods.items():
            if not vals:
                stats["empty_periods"] += 1
                continue
            rec = existing.get((well.id, yr, mon))
            if rec is None:
                rec = MonthlyProduction(well_id=well.id, jyear=yr, jmonth=mon, source=SOURCE)
                db.session.add(rec)
                existing[(well.id, yr, mon)] = rec
                stats["periods_created"] += 1
            else:
                stats["periods_updated"] += 1
            rec.production_m3 = vals.get("production_m3")
            rec.run_hours = vals.get("run_hours")
            rec.avg_discharge_lps = vals.get("avg_discharge_lps")
            rec.well_pressure = vals.get("well_pressure")

    stats["wells_matched"] = len(matched_well_ids)
    if dry_run:
        db.session.rollback()
    else:
        db.session.commit()
    return stats



################################################################################
# FILE: production_unmatched_export.py
################################################################################

"""Export wells present in 'روند تولید چاه ها.xlsx' but ABSENT from the master
registry, so the user can review and (if valid) add them.

For each unmatched well we include the file's own metadata (office, zone, drill
year, status, max yield) plus a summary of how much production history would be
recovered if it were added (year span, months of data, latest annual mean Q).
The user fills the 'تصمیم' column (افزودن / نادیده) and optional notes.
"""
from collections import defaultdict

import openpyxl
import pandas as pd

from app.extensions import db
from app.models.well import Well
from app.imports.wells_import import match_key, _clean
from app.imports.production_import import _build_colmap, _office_resolver, SOURCE
from app.utils.dates import to_english_digits


# helpful metadata columns (by header index in the wide sheet)
_META = {
    7: "وضعیت تعیین محل",
    8: "دبی مجاز پیشنهادی",
    11: "سال حفر",
    12: "حداکثر آبدهی",
    16: "پهنه اصلی",
    17: "زیرپهنه",
    18: "وضعیت چاه",
    4: "تاریخ نصب الکتروپمپ",
}


def _num(v):
    s = _clean(v)
    if s is None:
        return None
    try:
        return float(to_english_digits(s))
    except ValueError:
        return None


def export(path="current data/روند تولید چاه ها.xlsx",
           out_path="production_unmatched_wells.xlsx"):
    stats = {"file_rows": 0, "unmatched": 0}

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    rows = ws.iter_rows(values_only=True)
    headers = list(next(rows))
    colmap = _build_colmap(headers)
    # per-(year) discharge columns to summarize recoverable history
    disc_cols = {(yr, mon): idx for idx, (metric, yr, mon) in colmap.items()
                 if metric == "avg_discharge_lps"}
    prod_cols = {idx for idx, (metric, _y, _m) in colmap.items()
                 if metric == "production_m3"}

    office_of = _office_resolver()
    by_key_office, by_key = {}, {}
    for w in db.session.scalars(db.select(Well)).all():
        by_key.setdefault(w.match_key, []).append(w)
        by_key_office[(w.match_key, w.office_id)] = w

    out_rows = []
    for row in rows:
        name = _clean(row[0]) if row else None
        if not name:
            continue
        stats["file_rows"] += 1
        nk = match_key(name)
        oid = office_of(row[1] if len(row) > 1 else None)
        well = by_key_office.get((nk, oid))
        if well is None:
            cands = by_key.get(nk, [])
            well = cands[0] if len(cands) == 1 else None
        if well is not None:
            continue
        stats["unmatched"] += 1

        # recoverable-history summary
        yearly = defaultdict(list)
        for (yr, mon), idx in disc_cols.items():
            if idx < len(row):
                v = _num(row[idx])
                if v and v > 0:
                    yearly[yr].append(v)
        months_prod = sum(1 for idx in prod_cols if idx < len(row) and _num(row[idx]) is not None)
        years = sorted(yearly)
        latest_mean = (sum(yearly[years[-1]]) / len(yearly[years[-1]])) if years else None

        rec = {
            "نام چاه (در فایل تولید)": name,
            "اداره": _clean(row[1]) if len(row) > 1 else "",
        }
        for idx, label in _META.items():
            rec[label] = _clean(row[idx]) if idx < len(row) else ""
        rec["سال‌های دارای داده"] = "، ".join(str(y) for y in years) if years else ""
        rec["ماه‌های داده تولید"] = months_prod
        rec["میانگین دبی آخرین سال (l/s)"] = round(latest_mean, 1) if latest_mean is not None else ""
        rec["تصمیم (افزودن/نادیده)"] = ""
        rec["کد PM (در صورت افزودن)"] = ""
        rec["توضیح"] = ""
        out_rows.append(rec)

    out_rows.sort(key=lambda r: (str(r["اداره"]), str(r["نام چاه (در فایل تولید)"])))

    guide = pd.DataFrame({
        "راهنمای استفاده": [
            "این فایل، چاه‌هایی را فهرست می‌کند که در «روند تولید چاه ها.xlsx» داده دارند اما در رجیستری اصلی سامانه نیستند.",
            "این چاه‌ها در منابع مرجع (تجمیعی ۴۰۰-۴۰۵ و Borwells) وجود نداشته‌اند؛ بنابراین داده‌ی تولیدشان فعلاً وارد نشده است.",
            "ستون «ماه‌های داده تولید» و «سال‌های دارای داده» نشان می‌دهد چه مقدار تاریخچه با افزودن هر چاه بازیابی می‌شود.",
            "در ستون «تصمیم» بنویسید: «افزودن» (اگر چاه معتبر است) یا «نادیده» (اگر تکراری/نامعتبر است).",
            "اگر «افزودن» را انتخاب کردید و کد PM معتبری دارید، آن را در ستون مربوطه وارد کنید (اختیاری).",
            "پس از تکمیل، فایل را برگردانید تا چاه‌های تأییدشده به رجیستری اضافه و داده‌ی تولیدشان وارد شود.",
        ]
    })

    with pd.ExcelWriter(out_path, engine="openpyxl") as xl:
        guide.to_excel(xl, sheet_name="راهنما", index=False)
        df = pd.DataFrame(out_rows)
        df.to_excel(xl, sheet_name="چاه‌های_بدون_تطبیق", index=False)
        # widen columns for readability
        ws_out = xl.sheets["چاه‌های_بدون_تطبیق"]
        for col_cells in ws_out.columns:
            width = max((len(str(c.value)) for c in col_cells if c.value is not None), default=10)
            ws_out.column_dimensions[col_cells[0].column_letter].width = min(max(width + 2, 12), 40)

    stats["out_path"] = out_path
    return stats



################################################################################
# FILE: pump_select_import.py
################################################################################

"""Idempotent importer for pump selection / re-engineering records.

Source: '14050308 مهندسی مجدد و انتخاب پمپ ....xlsx' sheet 'افزایش آبدهی'.
Wells matched by name. Imported as approved/locked with audit.
"""
from datetime import datetime

import pandas as pd

from app.extensions import db
from app.models.well import Well
from app.models.pump_select import PumpSelection
from app.models.audit import RecordHistory
from app.utils.dates import parse_jalali
from app.imports.wells_import import _norm_name, _clean, _num, match_key

SOURCE = "import:pump_select"


def _date(v):
    s = _clean(v)
    if not s:
        return None
    try:
        return parse_jalali(s)
    except Exception:
        return None


def _col(df, *keys):
    for c in df.columns:
        name = str(c).strip()
        if all(k in name for k in keys):
            return c
    return None


def run(path, dry_run=False):
    stats = {"rows": 0, "created": 0, "updated": 0, "well_not_found": 0}

    df = pd.read_excel(path, sheet_name="افزایش آبدهی", header=1)
    df.columns = [str(c).strip() for c in df.columns]
    C = {
        "name": _col(df, "نام چاه"), "action": _col(df, "اقدام"),
        "prev_pump": _col(df, "تیپ پمپ قبلی"), "prev_motor": _col(df, "تیپ موتور قبلی"),
        "prev_q": _col(df, "دبی قبلی"),
        "sel_pump": _col(df, "تیپ پمپ پس از"), "sel_motor": _col(df, "تیپ موتور پس از"),
        "target_q": _col(df, "دبی پس از"), "increase": _col(df, "میزان افزایش"),
        "head": _col(df, "هد پمپ"), "status": _col(df, "وضعیت انجام"),
        "jyear": _col(df, "سال"), "jmonth": _col(df, "ماه"),
        "form_date": _col(df, "تحویل فرم"), "pull": _col(df, "تاریخ کشیدن"),
        "video": _col(df, "ویدیومتری") or _col(df, "ویدئومتری"),
        "install": _col(df, "تاریخ نصب"), "vflow": _col(df, "تاریخ دبی"),
        "vq": _col(df, "آبدهی دبی"), "vhead": _col(df, "هد دبی"),
    }

    well_by_key = {}
    for w in db.session.scalars(db.select(Well)).all():
        well_by_key.setdefault(w.match_key, w)

    for _, r in df.iterrows():
        name = _norm_name(r.get(C["name"]))
        if not name:
            continue
        stats["rows"] += 1
        well = well_by_key.get(match_key(name))
        if well is None:
            stats["well_not_found"] += 1
            continue

        fdate = _date(r.get(C["form_date"]))
        action = _clean(r.get(C["action"]))
        rec = db.session.scalar(db.select(PumpSelection).filter_by(
            well_id=well.id, source=SOURCE, form_delivery_date=fdate, action_needed=action))
        creating = rec is None
        if creating:
            rec = PumpSelection(well_id=well.id, source=SOURCE, form_delivery_date=fdate,
                                action_needed=action, status="approved", approved_at=datetime.utcnow())
            db.session.add(rec)

        rec.jyear = _clean(r.get(C["jyear"]))
        rec.jmonth = _clean(r.get(C["jmonth"]))
        rec.status_done = _clean(r.get(C["status"]))
        rec.prev_pump_type = _clean(r.get(C["prev_pump"]))
        rec.prev_motor_type = _clean(r.get(C["prev_motor"]))
        rec.prev_discharge_lps = _num(r.get(C["prev_q"]))
        rec.selected_pump_type = _clean(r.get(C["sel_pump"]))
        rec.selected_motor_type = _clean(r.get(C["sel_motor"]))
        rec.target_discharge_lps = _num(r.get(C["target_q"]))
        rec.discharge_increase_lps = _num(r.get(C["increase"]))
        rec.selected_head_m = _num(r.get(C["head"]))
        rec.pull_date = _date(r.get(C["pull"]))
        rec.videometry_date = _date(r.get(C["video"]))
        rec.install_date = _date(r.get(C["install"]))
        rec.verify_flowtest_date = _date(r.get(C["vflow"]))
        rec.verify_discharge_lps = _num(r.get(C["vq"]))
        rec.verify_head_m = _num(r.get(C["vhead"]))

        db.session.flush()
        if creating:
            db.session.add(RecordHistory(entity_type="pump_selections", entity_id=rec.id,
                                         action="create", user_id=None, detail="وارد شده از فایل مهندسی مجدد"))
            stats["created"] += 1
        else:
            stats["updated"] += 1

    if dry_run:
        db.session.rollback()
    else:
        db.session.commit()
    return stats



################################################################################
# FILE: pump_test_import.py
################################################################################

"""Idempotent importer for pump-test events from حفاری.xlsx.

The bulk file carries the pump-test HEADER hydraulics (test date, proposed
discharge, static/dynamic level, drawdown) for ~220 wells; detailed step rows
exist for only a couple of wells (imported where present). a/b coefficients and
duration are empty in bulk. Wells matched by klasse then name. Approved/locked.
"""
from datetime import datetime

import pandas as pd

from app.extensions import db
from app.models.well import Well, WellIdentifier
from app.models.pump_test import PumpTest, PumpTestStep
from app.models.audit import RecordHistory
from app.utils.dates import parse_jalali
from app.imports.wells_import import _norm_name, _clean, _num, _intstr, match_key

SOURCE = "import:pumptest"


def _date(v):
    s = _clean(v)
    if not s:
        return None
    try:
        return parse_jalali(s)
    except Exception:
        return None


def _exact(df, name):
    for c in df.columns:
        if str(c).strip() == name:
            return c
    return None


def run(hafari_path, dry_run=False):
    stats = {"rows": 0, "created": 0, "updated": 0, "with_steps": 0, "well_not_found": 0}

    df = pd.read_excel(hafari_path, sheet_name="ALL", header=1)
    df.columns = [str(c).strip() for c in df.columns]
    C = {
        "name": _exact(df, "نام چاه"), "klasse": _exact(df, "کلاسه پرونده"),
        "test_date": _exact(df, "تاریخ اتمام آزمایش پمپاژ"),
        "proposed": _exact(df, "دبی پیشنهادی"),
        "max_yield": _exact(df, "حداکثر آبدهی چاه"),
        "static": _exact(df, "سطح استاتیک"),
        "dynamic": _exact(df, "سطح دینامیک در دبی پیشنهادی"),
        "drawdown": _exact(df, "مقدار افت آب"),
        "contractor": _exact(df, "پیمانکار"),
    }
    step_cols = [(
        _exact(df, f"دور موتور {i}"),
        _exact(df, f"حداکثر آبدهی چاه {i}"),
        _exact(df, f"مقدار افت آب {i}"),
    ) for i in range(1, 6)]

    # well lookups
    well_by_klasse, well_by_name = {}, {}
    for w in db.session.scalars(db.select(Well)).all():
        well_by_name.setdefault(w.match_key, w)
    for wi in db.session.scalars(db.select(WellIdentifier).filter_by(id_type="klasse")).all():
        well_by_klasse.setdefault(wi.value, wi.well_id)

    for _, r in df.iterrows():
        name = _norm_name(r.get(C["name"]))
        if not name:
            continue
        stats["rows"] += 1
        klasse = _intstr(r.get(C["klasse"]))
        well = None
        if klasse and klasse in well_by_klasse:
            well = db.session.get(Well, well_by_klasse[klasse])
        if well is None:
            well = well_by_name.get(match_key(name))
        if well is None:
            stats["well_not_found"] += 1
            continue

        tdate = _date(r.get(C["test_date"]))
        rec = db.session.scalar(db.select(PumpTest).filter_by(
            well_id=well.id, source=SOURCE, test_date=tdate))
        creating = rec is None
        if creating:
            rec = PumpTest(well_id=well.id, source=SOURCE, test_date=tdate,
                           status="approved", approved_at=datetime.utcnow())
            db.session.add(rec)

        rec.test_type = "step"
        rec.proposed_discharge_lps = _num(r.get(C["proposed"]))
        rec.max_yield_lps = _num(r.get(C["max_yield"]))
        rec.static_level = _num(r.get(C["static"]))
        rec.max_dynamic_level = _num(r.get(C["dynamic"]))
        rec.resulting_drawdown_m = _num(r.get(C["drawdown"]))
        rec.contractor = _clean(r.get(C["contractor"]))
        db.session.flush()

        rec.steps.clear()
        for i, (c_rpm, c_q, c_dd) in enumerate(step_cols, start=1):
            rpm = _num(r.get(c_rpm)) if c_rpm else None
            q = _num(r.get(c_q)) if c_q else None
            dd = _num(r.get(c_dd)) if c_dd else None
            if rpm is None and q is None and dd is None:
                continue
            rec.steps.append(PumpTestStep(step_no=i, rpm=rpm, discharge_lps=q, observed_drawdown=dd))
        if rec.steps:
            stats["with_steps"] += 1

        db.session.flush()
        if creating:
            db.session.add(RecordHistory(entity_type="pump_tests", entity_id=rec.id,
                                         action="create", user_id=None, detail="وارد شده از حفاری.xlsx"))
            stats["created"] += 1
        else:
            stats["updated"] += 1

    if dry_run:
        db.session.rollback()
    else:
        db.session.commit()
    return stats



################################################################################
# FILE: rawflow_import.py
################################################################################

"""Bulk importer for the raw دبی‌سنجی form workbooks (current data/Flow metering).

Parses every .xls/.xlsx (1400–1404), matches the well by name (+ office from the
folder path), and stores each test sheet as a FlowTest + its operating points.
Idempotent: (well_id, test_date, source='import:rawflow'). Imported approved.
"""
import glob
import os
from datetime import datetime

from app.extensions import db
from app.models.well import Well
from app.models.org import OrgUnit
from app.models.flow import FlowTest, FlowTestPoint
from app.models.audit import RecordHistory
from app.utils.dates import parse_jalali, to_english_digits
from app.imports.wells_import import _clean, match_key
from app.imports.rawflow_parse import parse_workbook

SOURCE = "import:rawflow"
OFFICE_TOKENS = ["امام علی", "امامیه", "خیرآباد", "خیر آباد", "دانشجو", "گلشهر",
                 "منزل آباد", "منزل اباد", "سوران", "روستایی", "منطقه 5", "دوستی"]


def _num(v, zero_ok=True):
    s = to_english_digits(str(v).strip()) if v is not None else ""
    if not s or s in ("--", "-", "&"):
        return None
    try:
        f = float(s)
    except ValueError:
        return None
    if not zero_ok and f == 0:
        return None
    return f


def _date(v):
    s = _clean(v)
    if not s:
        return None
    try:
        return parse_jalali(s)
    except Exception:
        return None


def _office_from_path(path):
    norm = path.replace("اباد", "آباد")
    for tok in OFFICE_TOKENS:
        if tok.replace("اباد", "آباد") in norm:
            return tok
    return None


def run(root="current data/Flow metering", dry_run=False, limit=None):
    stats = {"files": 0, "sheets": 0, "tests_created": 0, "tests_updated": 0,
             "points": 0, "well_not_found": 0, "parse_empty": 0}
    unmatched = {}

    # office token -> office_id
    offices = db.session.scalars(db.select(OrgUnit).filter_by(unit_type="office")).all()

    def office_id(tok):
        if not tok:
            return None
        t = tok.replace("اباد", "آباد")
        for o in offices:
            if t in o.name or o.name in t:
                return o.id
        return None

    # well lookup
    wells = db.session.scalars(db.select(Well)).all()
    by_key_office = {}
    by_key = {}
    for w in wells:
        by_key.setdefault(w.match_key, []).append(w)
        by_key_office[(w.match_key, w.office_id)] = w

    files = [f for f in glob.glob(os.path.join(root, "**", "*.xls*"), recursive=True)
             if not os.path.basename(f).startswith("~") and "Thumbs" not in f]
    if limit:
        files = files[:limit]

    for path in files:
        stats["files"] += 1
        oid = office_id(_office_from_path(path))
        records = parse_workbook(path)
        if not records:
            stats["parse_empty"] += 1
            continue
        for rec in records:
            stats["sheets"] += 1
            nk = match_key(rec.get("name"))
            well = by_key_office.get((nk, oid))
            if well is None:
                cand = by_key.get(nk, [])
                well = cand[0] if len(cand) == 1 else None
            if well is None:
                stats["well_not_found"] += 1
                unmatched[(rec.get("name"), oid)] = unmatched.get((rec.get("name"), oid), 0) + 1
                continue

            tdate = _date(rec.get("test_date"))
            ft = db.session.scalar(db.select(FlowTest).filter_by(
                well_id=well.id, test_date=tdate, source=SOURCE))
            creating = ft is None
            if creating:
                ft = FlowTest(well_id=well.id, test_date=tdate, source=SOURCE,
                              status="approved", approved_at=datetime.utcnow())
                db.session.add(ft)

            ft.test_reason = _clean(rec.get("reason"))
            ft.network_type = _clean(rec.get("network"))
            ft.electropump_type = _clean(rec.get("ep"))
            ft.electropump_type_prev = _clean(rec.get("ep_prev"))
            ft.install_date = _date(rec.get("install_date"))
            ft.install_depth = _num(rec.get("install_depth"))
            ft.well_depth = _num(rec.get("well_depth"))
            ft.construction_type = _clean(rec.get("constr"))
            ft.allowed_q = _num(rec.get("allowed_q"))
            ft.design_q = _num(rec.get("design_q"))
            ft.license_q = _num(rec.get("license_q"))
            ft.power_subscription = _clean(rec.get("power_sub"))
            ft.static_level = _num(rec.get("static"))
            ft.static_level_prev = _num(rec.get("static_prev"))
            ft.last_rehab_date = _date(rec.get("last_rehab"))
            ft.pull_reason = _clean(rec.get("pull_reason"))
            ft.meter_status = _clean(rec.get("meter_status"))
            ft.meter_brand = _clean(rec.get("meter_brand"))
            ft.starter_type = _clean(rec.get("starter"))
            ft.line_pressure = _num(rec.get("line_pressure"))
            ft.regulated_pressure = _clean(rec.get("reg_pressure"))
            ft.discharge_volume_m3 = _num(rec.get("disch_vol"))
            ft.expert_note = _clean(rec.get("expert_note"))
            db.session.flush()

            ft.points.clear()
            for p in rec["points"]:
                q = _num(p.get("discharge"))
                q3 = _num(p.get("discharge_m3h"))
                if q is None and q3 is not None:
                    q = round(q3 / 3.6, 2)
                if q3 is None and q is not None:
                    q3 = round(q * 3.6, 1)
                ft.points.append(FlowTestPoint(
                    operating_no=p.get("operating_no"),
                    operating_type=p.get("operating_type"),
                    discharge_lps=q, discharge_m3h=q3,
                    head_m=_num(p.get("head")), drawdown_m=_num(p.get("drawdown")),
                    dynamic_level_m=_num(p.get("dynamic")), pressure_atm=_num(p.get("pressure")),
                    water_column_m=_num(p.get("water_col")),
                    water_column_change=_num(p.get("water_col_change")),
                    amperes=_clean(p.get("amperes")), efficiency=_num(p.get("efficiency")),
                ))
                stats["points"] += 1

            db.session.flush()
            if creating:
                db.session.add(RecordHistory(entity_type="flow_tests", entity_id=ft.id,
                                             action="create", user_id=None,
                                             detail="وارد شده از فرم خام دبی‌سنجی"))
                stats["tests_created"] += 1
            else:
                stats["tests_updated"] += 1
        # commit per file to keep memory/transactions bounded
        if not dry_run:
            db.session.commit()

    if dry_run:
        db.session.rollback()
    stats["unmatched_distinct"] = len(unmatched)
    stats["_unmatched_sample"] = sorted(unmatched.items(), key=lambda x: -x[1])[:15]
    return stats



################################################################################
# FILE: rawflow_parse.py
################################################################################

"""Parser for the raw دبی‌سنجی (flow-metering) form workbooks.

Robust across the form's layout variants by using the invariant: a field's VALUE
sits in the cell immediately to the LEFT of its label (RTL forms). Operating
points (کارکرد) are read by locating the current-metering header row and mapping
each metric label to its column. Returns one record per sheet (test date).
"""
import re

import pandas as pd


def _norm(s):
    s = str(s)
    s = s.replace("ي", "ی").replace("ك", "ک").replace("ـ", "")
    s = s.replace("‌", "").replace("‏", "").replace("‎", "")
    return re.sub(r"\s+", "", s).strip()


# normalized-label -> field name (value is the left neighbour)
LABELS = {
    "نامچاه": "name", "تاریخآزمایش": "test_date", "تاریخآزمایشقبلی": "test_date_prev",
    "تیبالکتروپمپ": "ep", "تیپالکتروپمپ": "ep",
    "تیبقبلیالکتروپمپ": "ep_prev", "تیپالکتروپمپقبلی": "ep_prev", "تیبالکتروپمپقبلی": "ep_prev",
    "سالحفر": "drill_year", "نوعچاه": "constr",
    "تاریخنصب": "install_date", "تاریخآخریننصب": "install_date",
    "عمقچاه": "well_depth", "عمقنصب": "install_depth",
    "لولهآبده": "water_pipe", "لولهجدار": "casing_pipe",
    "دبیمجاز": "allowed_q", "دبیطراحی": "design_q", "دبیپروانه": "license_q",
    "سطحایستایی": "static", "سطحایستاییقبلی": "static_prev",
    "کلاسهچاه": "klasse", "اشتراکبرق": "power_sub",
    "دلیلآزمایش": "reason", "نوعشبکه": "network", "پهنه": "zone",
    "آخرینسابقهشولات": "last_sholat",
    "ظرفیتخازن": "cap", "ولتاژروشن/خاموش": "volt", "ولتازروشن/خاموش": "volt",
    "مقاومتاهمیف-ف": "ohm_ff", "مقاومتاهمیف-ب": "ohm_fg",
    "فشارخط(bar)": "line_pressure", "فشارتنظیمی": "reg_pressure",
    "حجمتخلیه(m3)": "disch_vol",
    "کالیبراسیون/وضعیتکنتور:": "meter_status", "کالیبراسیون/وضعیتکنتور": "meter_status",
    "علتکشیدنپمپ:": "pull_reason", "تاریخآخرینبهسازی:": "last_rehab",
    "برند/سایزکنتور": "meter_brand", "سیستمراهانداز": "starter",
}

# metric header labels -> point field
POINT_METRICS = {
    "هد": "head", "هد(m)": "head",
    "میزانافت": "drawdown", "میزانافت(m)": "drawdown", "افت": "drawdown",
    "میزانافتلوله(m)": "drawdown", "افت(m)": "drawdown",
    "آبدهی": "discharge", "آبدهی(l/s)": "discharge", "آبدهی(m3/hr)": "discharge_m3h",
    "سطحپویایی": "dynamic", "پویایی": "dynamic", "سطحپویایی(m)": "dynamic", "پویایی(m)": "dynamic",
    "فشار": "pressure", "فشار(atm)": "pressure",
    "آمپرها": "amperes", "آمبرها": "amperes",
    "ستونآب": "water_col", "ستونآب(m)": "water_col",
    "تغییرستونآب": "water_col_change",
    "راندمان": "efficiency",
}


def _cell(df, r, c):
    if 0 <= r < df.shape[0] and 0 <= c < df.shape[1]:
        v = df.iat[r, c]
        return None if (v is None or (isinstance(v, float) and pd.isna(v))) else v
    return None


def _karkard(text):
    """Parse a 'کارکرد N (...)' cell -> (no, type) or (None, None)."""
    s = _norm(text)
    if "کارکرد" not in s:
        return None, None
    m = re.search(r"کارکرد(\d+)", s)
    no = int(m.group(1)) if m else None
    op_type = None
    if "فشارشبکه" in s:
        op_type = "فشار شبکه"
    elif "زیرشبکه" in s:
        op_type = "زیر شبکه"
    elif "عادی" in s:
        op_type = "عادی"
    return no, op_type


def parse_sheet(df):
    H, W = df.shape
    fields = {}
    # 1) header fields: value left of label (but ignore when the "value" is
    #    itself a label/metric-header — avoids e.g. static = "فشار (atm)").
    for r in range(H):
        for c in range(1, W):
            v = _cell(df, r, c)
            if isinstance(v, str):
                key = _norm(v)
                if key in LABELS and LABELS[key] not in fields:
                    lv = _cell(df, r, c - 1)
                    if isinstance(lv, str) and (_norm(lv) in LABELS or _norm(lv) in POINT_METRICS):
                        continue
                    fields[LABELS[key]] = lv
    if not fields.get("name") or not fields.get("test_date"):
        return None

    # 2) operating points — find the CURRENT metering header row (the later one
    #    that has both آبدهی and فشار among its cells).
    header_rows = []
    for r in range(H):
        labels = {}
        for c in range(W):
            v = _cell(df, r, c)
            if isinstance(v, str):
                k = _norm(v)
                if k in POINT_METRICS:
                    labels.setdefault(POINT_METRICS[k], c)
        if ("discharge" in labels or "discharge_m3h" in labels) and \
                "pressure" in labels and "head" in labels:
            header_rows.append((r, labels))
    points = []
    if header_rows:
        hr, colmap = header_rows[-1]  # current table is the last one
        # find کارکرد marker column (search a window of rows below header)
        marker_col = None
        for r in range(hr, min(hr + 10, H)):
            for c in range(W):
                v = _cell(df, r, c)
                if isinstance(v, str) and "کارکرد" in _norm(v):
                    marker_col = c
                    break
            if marker_col is not None:
                break
        if marker_col is not None:
            for r in range(hr + 1, min(hr + 12, H)):
                mk = _cell(df, r, marker_col)
                no, op_type = _karkard(mk) if isinstance(mk, str) else (None, None)
                if no is None:
                    continue
                pt = {"operating_no": no, "operating_type": op_type}
                for field, col in colmap.items():
                    pt[field] = _cell(df, r, col)
                if any(pt.get(k) is not None for k in ("discharge", "discharge_m3h", "head")):
                    points.append(pt)

    # 3) expert note: the longest free-text cell (not the form title / a label)
    note, best = None, 0
    for r in range(H):
        for c in range(W):
            v = _cell(df, r, c)
            if isinstance(v, str):
                t = v.strip()
                if len(t) > 40 and "فرم دبی" not in t and _norm(t) not in LABELS and len(t) > best:
                    best, note = len(t), t
    fields["expert_note"] = note

    fields["points"] = points
    return fields


def parse_workbook(path):
    out = []
    try:
        xls = pd.ExcelFile(path)
    except Exception:
        return out
    for sh in xls.sheet_names:
        if str(sh).strip().lower() in ("sheet1", "sheet2", "sheet3"):
            continue
        try:
            df = pd.read_excel(path, sheet_name=sh, header=None)
        except Exception:
            continue
        rec = parse_sheet(df)
        if rec:
            rec["_sheet"] = str(sh)
            out.append(rec)
    return out



################################################################################
# FILE: reconcile.py
################################################################################

"""Re-runnable cross-file well-identity reconciliation report.

Checks that the same well is consistently identifiable across the source files
and the DB. Run now (to confirm the base) and again at the end (safety net):
    flask reconcile-wells
"""
import glob
import os
import re

import pandas as pd

from app.extensions import db
from app.models.well import Well
from app.imports.wells_import import _norm_name, _intstr, _clean, match_key  # noqa: F401


def _find_value(df, label):
    for r in range(df.shape[0]):
        for c in range(1, df.shape[1]):
            v = df.iat[r, c]
            if isinstance(v, str) and v.strip() == label:
                left = df.iat[r, c - 1]
                if pd.notna(left):
                    return left
    return None


def run(tajmi_path, nasb_path, flow_glob):
    lines = []
    add = lines.append

    # DB index
    wells = db.session.scalars(db.select(Well)).all()
    db_key = {match_key(w.name): w for w in wells}
    db_pm = {w.pm_code for w in wells}
    real = sum(1 for w in wells if w.has_pm)
    add("=" * 60)
    add("WELL IDENTITY RECONCILIATION")
    add("=" * 60)
    add(f"DB wells: {len(wells)} | real pm: {real} | synthetic: {len(wells)-real} "
        f"| with coords: {sum(1 for w in wells if w.latitude is not None)}")

    # تجمیعی (base) coverage
    tj = pd.read_excel(tajmi_path, sheet_name="تجمیع دبی‌سنجی")
    tj.columns = [str(c).strip() for c in tj.columns]
    tj_pm = {_intstr(v) for v in tj["کد PM"] if _intstr(v)}
    add(f"\n[تجمیعی] unique pm: {len(tj_pm)} | present in DB: {len(tj_pm & db_pm)} "
        f"| MISSING from DB: {len(tj_pm - db_pm)}")
    # same pm, multiple name spellings
    nm = {}
    for _, r in tj.iterrows():
        pm = _intstr(r.get("کد PM"))
        if pm:
            nm.setdefault(pm, set()).add(_norm_name(r.get("نام چاه")))
    multi = {k: v for k, v in nm.items() if len(v) > 1}
    add(f"[تجمیعی] pm codes with >1 name spelling: {len(multi)} (info only)")

    # نصب coverage
    try:
        ns = pd.read_excel(nasb_path, sheet_name="نصب‌ها_با_مشخصات")
        ns.columns = [str(c).strip() for c in ns.columns]
        ns_pm = {_intstr(v) for v in ns["کد PM"] if _intstr(v)}
        add(f"\n[نصب] unique pm: {len(ns_pm)} | in DB: {len(ns_pm & db_pm)} "
            f"| not in DB: {len(ns_pm - db_pm)}")
        if ns_pm - db_pm:
            add("   sample pm not in DB: " + str(sorted(ns_pm - db_pm)[:10]))
    except Exception as e:
        add(f"[نصب] skipped: {e}")

    # raw flow 1405 files: match by name(+office)
    files = glob.glob(flow_glob, recursive=True)
    matched, unmatched = 0, []
    for f in files:
        office = os.path.basename(os.path.dirname(f))
        try:
            xls = pd.ExcelFile(f)
            d = pd.read_excel(f, sheet_name=xls.sheet_names[0], header=None)
            name = _find_value(d, "نام چاه")
        except Exception:
            name = None
        k = match_key(name)
        if k and k in db_key:
            matched += 1
        else:
            unmatched.append((_norm_name(name), office, os.path.basename(f)))
    add(f"\n[فرم‌های خام دبی‌سنجی] files: {len(files)} | matched to DB by name: {matched} "
        f"| UNMATCHED: {len(unmatched)}")
    for nm_, office, fn in unmatched:
        add(f"   ✗ {nm_!r:30} | اداره: {office} | {fn}")

    add("\n" + "=" * 60)
    return "\n".join(lines)



################################################################################
# FILE: rehab_import.py
################################################################################

"""Idempotent importer for rehabilitation events (گزارش بهسازی و پمپاژ.xlsx).

Wells matched by name; rehab + pumping contractors get-or-created (with alias
correction). Imported as approved/locked with audit.
"""
from datetime import datetime

import pandas as pd

from app.extensions import db
from app.models.well import Well
from app.models.rehab import Rehabilitation
from app.models.pump_asset import Supplier
from app.models.audit import RecordHistory
from app.models.constants import canonical_supplier
from app.utils.dates import parse_compact_jalali
from app.imports.wells_import import _norm_name, _clean, _num, match_key

SOURCE = "import:rehab"


def _date(v):
    s = _clean(v)
    if not s:
        return None
    try:
        return parse_compact_jalali(s)
    except Exception:
        return None


def _col(df, *keys):
    for c in df.columns:
        name = str(c).strip()
        if all(k in name for k in keys):
            return c
    return None


def run(rehab_path, dry_run=False):
    stats = {"rows": 0, "created": 0, "updated": 0, "well_not_found": 0}

    df = pd.read_excel(rehab_path, sheet_name="Sheet1", header=1)
    df.columns = [str(c).strip() for c in df.columns]
    C = {
        "name": _col(df, "نام چاه"), "stage": _col(df, "مرحله"), "jyear": _col(df, "سال"),
        "rdate": _col(df, "تاریخ بهسازی"), "rcontractor": _col(df, "پیمانکار بهسازی"),
        "pdate": _col(df, "اتمام پمپاژ"), "pcontractor": _col(df, "پیمانکار پمپاژ"),
        "ptype_b": _col(df, "پیش از بهسازی"), "q_b": _col(df, "دبی قبل"),
        "ptype_a": _col(df, "پس از بهسازی"), "q_a": _col(df, "دبی بعد"),
        "q_change": _col(df, "میزان تغییرات"), "reason": _col(df, "علت بهسازی"),
    }

    sup_cache = {}

    def get_supplier(name):
        name = canonical_supplier(_clean(name))
        if not name:
            return None
        if name in sup_cache:
            return sup_cache[name]
        s = db.session.scalar(db.select(Supplier).filter_by(name=name))
        if s is None:
            s = Supplier(name=name, kind="contractor")
            db.session.add(s)
            db.session.flush()
        sup_cache[name] = s.id
        return s.id

    well_by_key = {}
    for w in db.session.scalars(db.select(Well)).all():
        well_by_key.setdefault(w.match_key, w)

    for _, r in df.iterrows():
        name = _norm_name(r.get(C["name"]))
        if not name:
            continue
        stats["rows"] += 1
        well = well_by_key.get(match_key(name))
        if well is None:
            stats["well_not_found"] += 1
            continue

        rdate = _date(r.get(C["rdate"]))
        stage = _clean(r.get(C["stage"]))
        rec = db.session.scalar(db.select(Rehabilitation).filter_by(
            well_id=well.id, source=SOURCE, rehab_date=rdate, stage=stage))
        creating = rec is None
        if creating:
            rec = Rehabilitation(well_id=well.id, source=SOURCE, rehab_date=rdate,
                                 stage=stage, status="approved", approved_at=datetime.utcnow())
            db.session.add(rec)

        rec.jyear = _clean(r.get(C["jyear"]))
        rec.pumping_end_date = _date(r.get(C["pdate"]))
        rec.rehab_contractor_id = get_supplier(r.get(C["rcontractor"]))
        rec.pumping_contractor_id = get_supplier(r.get(C["pcontractor"]))
        rec.pump_type_before = _clean(r.get(C["ptype_b"]))
        rec.discharge_before_lps = _num(r.get(C["q_b"]))
        rec.pump_type_after = _clean(r.get(C["ptype_a"]))
        rec.discharge_after_lps = _num(r.get(C["q_a"]))
        rec.discharge_change_lps = _num(r.get(C["q_change"]))
        rec.reason = _clean(r.get(C["reason"]))

        db.session.flush()
        if creating:
            db.session.add(RecordHistory(entity_type="rehabilitations", entity_id=rec.id,
                                         action="create", user_id=None, detail="وارد شده از گزارش بهسازی"))
            stats["created"] += 1
        else:
            stats["updated"] += 1

    if dry_run:
        db.session.rollback()
    else:
        db.session.commit()
    return stats



################################################################################
# FILE: relocation_import.py
################################################################################

"""Import relocation candidacy from 'Aid data.xlsx' (sheet تولید ماهیانه).

The relocation columns are marker cells (√ / ×): candidacy (final/not/impossible/
proposed) and the chosen relocation type. We derive a RelocationRecord per well
that has any relocation marker. Approved=False (imported as draft assessments).
Wells are matched by match_key+office. Re-runnable (source='import:aid').
"""
import openpyxl

from app.extensions import db
from app.models.well import Well
from app.models.relocation import RelocationRecord
from app.imports.wells_import import match_key, _clean
from app.imports.production_import import _office_resolver

SOURCE = "import:aid"
A_NAME, A_OFFICE = 4, 6
# marker columns
C_PROPOSED, C_LETTER, C_LOCATION = 191, 195, 196
C_FINAL, C_NOT, C_IMPOSSIBLE = 208, 209, 210
TYPE_COLS = [(211, "in_place"), (212, "other_surplus"),
             (213, "green_space"), (214, "edu_admin")]


def _marked(v):
    s = _clean(v)
    return bool(s) and "√" in s or (s == "×")


def _yes(v):
    s = _clean(v)
    return bool(s) and "√" in s


def run(path="current data/Aid data.xlsx", dry_run=False):
    stats = {"rows": 0, "with_marker": 0, "created": 0, "updated": 0,
             "unmatched": 0}

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb["تولید ماهیانه"]
    rows = ws.iter_rows(values_only=True)
    next(rows)

    office_of = _office_resolver()
    by_key_office, by_key = {}, {}
    for w in db.session.scalars(db.select(Well)).all():
        by_key.setdefault(w.match_key, []).append(w)
        by_key_office[(w.match_key, w.office_id)] = w

    existing = {r.well_id: r for r in db.session.scalars(
        db.select(RelocationRecord).filter_by(source=SOURCE)).all()}

    for row in rows:
        name = _clean(row[A_NAME]) if len(row) > A_NAME else None
        if not name:
            continue
        stats["rows"] += 1

        def cell(c):
            return row[c] if c < len(row) else None

        # derive candidacy
        if _yes(cell(C_FINAL)):
            candidacy = "final"
        elif _yes(cell(C_IMPOSSIBLE)):
            candidacy = "impossible"
        elif _clean(cell(C_NOT)) == "×":
            candidacy = "not_candidate"
        elif _yes(cell(C_PROPOSED)):
            candidacy = "proposed"
        else:
            candidacy = None
        reloc_type = next((t for c, t in TYPE_COLS if _yes(cell(c))), None)
        letter = _clean(cell(C_LETTER))
        if letter and "√" in letter:
            letter = None
        location = _clean(cell(C_LOCATION))
        if location and location == "√":
            location = None

        if not (candidacy or reloc_type or letter or location):
            continue
        stats["with_marker"] += 1

        nk = match_key(name)
        oid = office_of(row[A_OFFICE] if len(row) > A_OFFICE else None)
        well = by_key_office.get((nk, oid))
        if well is None:
            cands = by_key.get(nk, [])
            well = cands[0] if len(cands) == 1 else None
        if well is None:
            stats["unmatched"] += 1
            continue

        rec = existing.get(well.id)
        if rec is None:
            rec = RelocationRecord(well_id=well.id, source=SOURCE,
                                   status="approved")
            db.session.add(rec)
            existing[well.id] = rec
            stats["created"] += 1
        else:
            stats["updated"] += 1
        rec.candidacy = candidacy
        rec.reloc_type = reloc_type
        rec.letter_no = letter
        rec.location_note = location

    if dry_run:
        db.session.rollback()
    else:
        db.session.commit()
    return stats



################################################################################
# FILE: water_level_seed.py
################################################################################

"""Seed the water-level monitoring series from existing static-level data.

Pulls static (non-pumping) water levels already recorded on flow-tests,
pump-tests and drilling events into WaterLevelLog, giving an immediate
piezometric history. Idempotent (keyed by well+date+source).
"""
from app.extensions import db
from app.models.water_level import WaterLevelLog


def run(dry_run=False):
    from app.models.flow import FlowTest
    from app.models.pump_test import PumpTest
    from app.models.drilling import Drilling

    stats = {"flowtest": 0, "pumptest": 0, "drilling": 0, "skipped": 0}

    existing = {(w.well_id, w.measure_date, w.source)
                for w in db.session.scalars(db.select(WaterLevelLog)).all()}

    def add(well_id, date, level, method, source):
        if well_id is None or date is None or level is None:
            return False
        key = (well_id, date, source)
        if key in existing:
            stats["skipped"] += 1
            return False
        db.session.add(WaterLevelLog(
            well_id=well_id, measure_date=date, static_level=level,
            is_pumping=False, method=method, source=source))
        existing.add(key)
        return True

    for t in db.session.scalars(db.select(FlowTest)).all():
        if add(t.well_id, t.test_date, t.static_level, "flowtest", "import:flowtest"):
            stats["flowtest"] += 1
    for t in db.session.scalars(db.select(PumpTest)).all():
        if add(t.well_id, t.test_date, t.static_level, "pumptest", "import:pumptest"):
            stats["pumptest"] += 1
    for d in db.session.scalars(db.select(Drilling)).all():
        date = d.end_date or d.start_date
        if add(d.well_id, date, d.static_level, "drilling", "import:drilling"):
            stats["drilling"] += 1

    if dry_run:
        db.session.rollback()
    else:
        db.session.commit()
    return stats



################################################################################
# FILE: well_technical_import.py
################################################################################

"""Enrich wells with technical metadata from the Aid master (sheet تولید ماهیانه).

Latest flow-test snapshot, meter status/brand, klasse, geo position and well
construction (columns 161-205). One WellTechnical row per well, matched by
match_key+office. Re-runnable (source='import:aid').
"""
import openpyxl

from app.extensions import db
from app.models.well import Well
from app.models.well_technical import WellTechnical
from app.imports.wells_import import match_key, _clean, _num
from app.imports.production_import import _office_resolver
from app.utils.dates import parse_compact_jalali

SOURCE = "import:aid"
A_NAME, A_OFFICE = 4, 6
C = {
    "last_flowtest_discharge": 161, "last_flowtest_pressure": 162, "last_qdate": 163,
    "meter_status": 164, "meter_brand": 166, "klasse": 192, "geo_position": 193,
    "casing_material": 200, "discharge_pipe_size": 201, "drill_depth_m": 202,
    "install_depth_m": 203, "prev_discharge_lps": 204, "last_drill_year": 205,
}
NUMERIC = {"last_flowtest_discharge", "last_flowtest_pressure",
           "drill_depth_m", "install_depth_m", "prev_discharge_lps"}


def _date(v):
    s = _clean(v)
    if not s:
        return None
    try:
        return parse_compact_jalali(s)
    except (ValueError, TypeError):
        return None


def run(path="current data/Aid data.xlsx", dry_run=False):
    stats = {"rows": 0, "created": 0, "updated": 0, "unmatched": 0, "empty": 0}

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb["تولید ماهیانه"]
    rows = ws.iter_rows(values_only=True)
    next(rows)

    office_of = _office_resolver()
    by_key_office, by_key = {}, {}
    for w in db.session.scalars(db.select(Well)).all():
        by_key.setdefault(w.match_key, []).append(w)
        by_key_office[(w.match_key, w.office_id)] = w

    existing = {t.well_id: t for t in db.session.scalars(db.select(WellTechnical)).all()}

    for row in rows:
        name = _clean(row[A_NAME]) if len(row) > A_NAME else None
        if not name:
            continue
        stats["rows"] += 1

        def cell(c):
            return row[c] if c < len(row) else None

        vals = {}
        for field, col in C.items():
            if field == "last_qdate":
                continue
            v = _num(cell(col), zero_is_null=False) if field in NUMERIC else _clean(cell(col))
            if v is not None and v != "":
                vals[field] = v
        qdate = _date(cell(C["last_qdate"]))
        if not vals and qdate is None:
            stats["empty"] += 1
            continue

        nk = match_key(name)
        oid = office_of(row[A_OFFICE] if len(row) > A_OFFICE else None)
        well = by_key_office.get((nk, oid))
        if well is None:
            cands = by_key.get(nk, [])
            well = cands[0] if len(cands) == 1 else None
        if well is None:
            stats["unmatched"] += 1
            continue

        rec = existing.get(well.id)
        if rec is None:
            rec = WellTechnical(well_id=well.id, source=SOURCE)
            db.session.add(rec)
            existing[well.id] = rec
            stats["created"] += 1
        else:
            stats["updated"] += 1
        for field in C:
            if field == "last_qdate":
                continue
            setattr(rec, field, vals.get(field))
        rec.last_flowtest_date = qdate

    if dry_run:
        db.session.rollback()
    else:
        db.session.commit()
    return stats



################################################################################
# FILE: wells_import.py
################################################################################

"""Idempotent importer for the well master registry.

Authoritative base = 'تجمیعی (400-405).xlsx'. Its `کد PM` column is CORRUPTED
(one pm shared by many distinct wells), so wells are identified by
(match_key(name), office) — NOT by pm. A pm is stored on a well only when it is
"clean" (maps to a single well); otherwise the well gets a deterministic
synthetic key. Every pm/klasse value seen is preserved in well_identifiers.
Geometry/construction come from Borwells.xlsx. Safe to re-run.
"""
import hashlib
import math
import re
from collections import defaultdict

import pandas as pd
from pyproj import Transformer

from app.extensions import db
from app.models.well import Well, WellIdentifier
from app.models.org import OrgUnit
from app.utils.dates import to_english_digits

_UTM40N = Transformer.from_crs("EPSG:32640", "EPSG:4326", always_xy=True)

KIND_MAP = {"شهری": "urban", "روستایی": "rural"}
CONSTRUCTION_MAP = {"آهکی": "limestone", "سیمانتاسیون": "cementation", "معمولی": "normal"}
PERMIT_LOCATION = {"جدید": "new", "جابجایی": "relocated_stage1"}


# ---------- cleaning helpers ----------
def _norm_name(v):
    s = to_english_digits("" if v is None else str(v))
    s = s.replace("ي", "ی").replace("ك", "ک")
    return " ".join(s.split()).strip()


def match_key(v):
    """Identity key: normalize name, unify alef/heh forms, drop spaces/ZWNJ."""
    s = _norm_name(v)
    if not s:
        return ""
    s = (s.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
           .replace("ة", "ه").replace("ؤ", "و"))
    s = re.sub(r"[\s‌‏‎]+", "", s)
    return s.lower()


def _clean(v):
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    s = str(v).strip()
    return s or None


def _intstr(v):
    s = _clean(v)
    if s is None:
        return None
    s = to_english_digits(s)
    try:
        f = float(s)
        if f.is_integer():
            return str(int(f))
    except ValueError:
        pass
    return s


def _num(v, zero_is_null=True):
    s = _clean(v)
    if s is None:
        return None
    s = to_english_digits(s)
    try:
        f = float(s)
    except ValueError:
        return None
    if zero_is_null and f == 0:
        return None
    return f


def _year(v):
    s = to_english_digits(_clean(v) or "")
    m = re.search(r"\d{4}", s)
    return m.group(0) if m else None


def _latlon(x, y):
    ex, ny = _num(x), _num(y)
    if ex is None or ny is None:
        return None, None
    try:
        lon, lat = _UTM40N.transform(ex, ny)
        return round(lat, 6), round(lon, 6)
    except Exception:
        return None, None


def _col(df, *keys):
    for c in df.columns:
        name = str(c).strip()
        if all(k in name for k in keys):
            return c
    return None


def _synthetic_pm(name_key, office_token):
    h = hashlib.md5(f"{office_token or ''}|{name_key}".encode("utf-8")).hexdigest()
    return "W-" + h[:12]


# ---------- aggregate (registry base, keyed by name+office) ----------
def _build_pm_map(tajmi_path):
    """Legacy name/klasse -> (pm, office) map (still used by drilling importer)."""
    tj = pd.read_excel(tajmi_path, sheet_name="تجمیع دبی‌سنجی")
    tj.columns = [str(c).strip() for c in tj.columns]
    by_klasse, by_name = {}, {}
    for _, r in tj.iterrows():
        pm = _intstr(r.get("کد PM"))
        if not pm:
            continue
        office = _clean(r.get("نام اداره"))
        k = _intstr(r.get("کلاسه چاه"))
        if k:
            by_klasse.setdefault(k, (pm, office))
        nm = _norm_name(r.get("نام چاه"))
        if nm:
            by_name.setdefault(nm, (pm, office))
    return by_klasse, by_name


def _build_registry(tajmi_path):
    tj = pd.read_excel(tajmi_path, sheet_name="تجمیع دبی‌سنجی")
    tj.columns = [str(c).strip() for c in tj.columns]
    agg = {}
    pm_wellkeys = defaultdict(set)   # pm -> set of distinct well name-keys
    for _, r in tj.iterrows():
        nm = _norm_name(r.get("نام چاه"))
        if not nm:
            continue
        nk = match_key(nm)
        office = _clean(r.get("نام اداره"))
        key = (nk, office)
        e = agg.setdefault(key, {"name": nm, "office": office, "year": -1,
                                 "drill_year": None, "pms": set(), "klasses": set()})
        yr = int(_year(r.get("سال")) or -1)
        if yr >= e["year"]:
            e["year"] = yr
            e["name"] = nm  # most-recent spelling for display
        dy = _year(r.get("سال حفر"))
        if dy:
            e["drill_year"] = dy
        pm = _intstr(r.get("کد PM"))
        if pm:
            e["pms"].add(pm)
            pm_wellkeys[pm].add(nk)
        k = _intstr(r.get("کلاسه چاه"))
        if k:
            e["klasses"].add(k)
    clean_pm = {pm for pm, ks in pm_wellkeys.items() if len(ks) == 1}
    return agg, clean_pm


def _build_borwells_index(borwells_path):
    bw = pd.read_excel(borwells_path, sheet_name="ALL", header=1)
    bw.columns = [str(c).strip() for c in bw.columns]
    C = {k: _col(bw, *v) for k, v in {
        "name": ("نام چاه",), "klasse": ("کلاسه",), "kind": ("شهری",),
        "permit": ("پروانه",), "constr": ("نوع چاه",), "year": ("سال حفر",),
        "x": ("X",), "y": ("Y",), "zone": ("ZONE",),
    }.items()}
    by_klasse, by_name, rows = {}, {}, []
    for _, r in bw.iterrows():
        name = _norm_name(r.get(C["name"]))
        if not name:
            continue
        lat, lon = _latlon(r.get(C["x"]), r.get(C["y"]))
        info = {
            "utm_x": _num(r.get(C["x"])), "utm_y": _num(r.get(C["y"])),
            "utm_zone": _clean(r.get(C["zone"])) or "40N", "lat": lat, "lon": lon,
            "construction_type": CONSTRUCTION_MAP.get(_clean(r.get(C["constr"]))),
            "location_status": PERMIT_LOCATION.get(_clean(r.get(C["permit"]))),
            "kind": KIND_MAP.get(_clean(r.get(C["kind"]))),
            "klasse": _intstr(r.get(C["klasse"])), "name": name, "nk": match_key(name),
        }
        if info["klasse"]:
            by_klasse.setdefault(info["klasse"], info)
        by_name.setdefault(info["nk"], info)
        rows.append(info)
    return by_klasse, by_name, rows


def _office_getter():
    cache = {}
    existing = db.session.scalars(db.select(OrgUnit).filter_by(unit_type="office")).all()

    def get(token):
        token = _clean(token)
        if not token:
            return None
        if token in cache:
            return cache[token]
        for o in existing:
            if token in o.name or o.name in token:
                cache[token] = o.id
                return o.id
        o = OrgUnit(name=token, unit_type="office")
        db.session.add(o)
        db.session.flush()
        existing.append(o)
        cache[token] = o.id
        return o.id

    return get


def _add_identifier(well, id_type, value):
    if not value:
        return
    exists = db.session.scalar(db.select(WellIdentifier).filter_by(
        well_id=well.id, id_type=id_type, value=value))
    if not exists:
        db.session.add(WellIdentifier(well_id=well.id, id_type=id_type, value=value))


# ---------- main ----------
def run(borwells_path, tajmi_path, dry_run=False):
    stats = {"registry_wells": 0, "created": 0, "updated": 0, "with_clean_pm": 0,
             "synthetic_key": 0, "borwells_only_created": 0, "coords_set": 0,
             "with_coords": 0}

    agg, clean_pm = _build_registry(tajmi_path)
    bw_klasse, bw_name, bw_rows = _build_borwells_index(borwells_path)
    get_office = _office_getter()
    stats["registry_wells"] = len(agg)
    used_pm = set()

    def enrich(well, info):
        if not info:
            return
        if info["lat"] is not None and well.latitude is None:
            well.latitude, well.longitude = info["lat"], info["lon"]
            well.utm_x, well.utm_y, well.utm_zone = info["utm_x"], info["utm_y"], info["utm_zone"]
            stats["coords_set"] += 1
        if info["construction_type"] and not well.construction_type:
            well.construction_type = info["construction_type"]
        if info["location_status"] and not well.location_status:
            well.location_status = info["location_status"]

    # ----- Phase A: registry from تجمیعی, keyed by (name_key, office) -----
    for (nk, office_token), e in agg.items():
        office_id = get_office(office_token)
        well = db.session.scalar(db.select(Well).filter_by(match_key=nk, office_id=office_id))
        if well is None:
            well = Well()
            db.session.add(well)
            stats["created"] += 1
        else:
            stats["updated"] += 1
        well.name = e["name"]
        well.match_key = nk
        well.office_id = office_id
        if e["drill_year"]:
            well.drill_year = e["drill_year"]
        if office_token and "روستایی" in office_token:
            well.well_kind = "rural"
        elif not well.well_kind:
            well.well_kind = "urban"
        # pm_code: a clean, unused pm if any; else deterministic synthetic key
        cpm = next((pm for pm in e["pms"] if pm in clean_pm and pm not in used_pm), None)
        well.pm_code = cpm or _synthetic_pm(nk, office_token)
        used_pm.add(well.pm_code)
        if cpm:
            stats["with_clean_pm"] += 1
        else:
            stats["synthetic_key"] += 1
        db.session.flush()
        for pm in e["pms"]:
            _add_identifier(well, "pm", pm)
        for k in e["klasses"]:
            _add_identifier(well, "klasse", k)
        info = next((bw_klasse[k] for k in e["klasses"] if k in bw_klasse), None) or bw_name.get(nk)
        if info and not well.well_kind:
            well.well_kind = info.get("kind") or "urban"
        enrich(well, info)

    # ----- Phase B: Borwells-only wells (no office in Borwells) -----
    for info in bw_rows:
        nk = info["nk"]
        well = db.session.scalar(db.select(Well).filter_by(match_key=nk))
        if well is None:
            well = Well(name=info["name"], match_key=nk,
                        well_kind=info.get("kind") or "urban",
                        pm_code=_synthetic_pm(nk, None))
            db.session.add(well)
            db.session.flush()
            stats["borwells_only_created"] += 1
            _add_identifier(well, "klasse", info["klasse"])
        enrich(well, info)

    stats["with_coords"] = db.session.scalar(
        db.select(db.func.count(Well.id)).where(Well.latitude.isnot(None)))

    if dry_run:
        db.session.rollback()
    else:
        db.session.commit()
    return stats



################################################################################
# FILE: zone_import.py
################################################################################

"""Import hydrogeological zone / sub-zone / destination reservoir from Aid.

Sheet 'تولید ماهیانه': col 18 پهنه, col 19 زیرپهنه, col 23 مخزن مقصد. Fills the
well registry's spatial-attribute fields (matched by match_key+office) so the
map and zone dashboards can theme by پهنه and supply zone. Re-runnable.
"""
import openpyxl

from app.extensions import db
from app.models.well import Well
from app.imports.wells_import import match_key, _clean
from app.imports.production_import import _office_resolver

C_ZONE, C_SUBZONE, C_RESERVOIR, A_NAME, A_OFFICE = 18, 19, 23, 4, 6


def run(path="current data/Aid data.xlsx", dry_run=False):
    stats = {"rows": 0, "zone": 0, "sub_zone": 0, "reservoir": 0, "unmatched": 0}

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb["تولید ماهیانه"]
    rows = ws.iter_rows(values_only=True)
    next(rows)

    office_of = _office_resolver()
    by_key_office, by_key = {}, {}
    for w in db.session.scalars(db.select(Well)).all():
        by_key.setdefault(w.match_key, []).append(w)
        by_key_office[(w.match_key, w.office_id)] = w

    for r in rows:
        name = _clean(r[A_NAME]) if len(r) > A_NAME else None
        if not name:
            continue
        stats["rows"] += 1
        zone = _clean(r[C_ZONE]) if C_ZONE < len(r) else None
        sub = _clean(r[C_SUBZONE]) if C_SUBZONE < len(r) else None
        res = _clean(r[C_RESERVOIR]) if C_RESERVOIR < len(r) else None
        if not (zone or sub or res):
            continue

        nk = match_key(name)
        oid = office_of(r[A_OFFICE] if len(r) > A_OFFICE else None)
        well = by_key_office.get((nk, oid))
        if well is None:
            cands = by_key.get(nk, [])
            well = cands[0] if len(cands) == 1 else None
        if well is None:
            stats["unmatched"] += 1
            continue
        if zone:
            well.zone = zone
            stats["zone"] += 1
        if sub:
            well.sub_zone = sub
            stats["sub_zone"] += 1
        if res:
            well.destination_reservoir = res
            stats["reservoir"] += 1

    if dry_run:
        db.session.rollback()
    else:
        db.session.commit()
    return stats



################################################################################
# FILE: __init__.py
################################################################################

"""Import all models so SQLAlchemy metadata and Alembic autogenerate see them."""
from app.models.rbac import User, Role, Permission  # noqa: F401
from app.models.org import OrgUnit  # noqa: F401
from app.models.well import Well, WellIdentifier  # noqa: F401
from app.models.audit import RecordHistory  # noqa: F401
from app.models.drilling import Drilling  # noqa: F401
from app.models.flow import FlowTest, FlowTestPoint  # noqa: F401
from app.models.pump_test import PumpTest, PumpTestStep  # noqa: F401
from app.models.pump_asset import Supplier, PumpInstallation  # noqa: F401
from app.models.rehab import Rehabilitation  # noqa: F401
from app.models.videometry import Videometry, VideometryFinding  # noqa: F401
from app.models.prioritization import PrioritizationCriterion  # noqa: F401
from app.models.pump_select import PumpSelection  # noqa: F401
from app.models.pump_catalog import PumpModel, PumpCurvePoint  # noqa: F401
from app.models.quality import WaterQuality  # noqa: F401
from app.models.baseline import WellBaseline  # noqa: F401
from app.models.production import MonthlyProduction  # noqa: F401
from app.models.relocation import RelocationRecord  # noqa: F401
from app.models.maintenance import MaintenanceRecord  # noqa: F401
from app.models.well_technical import WellTechnical  # noqa: F401
from app.models.water_level import WaterLevelLog  # noqa: F401
from app.models.attachment import Attachment  # noqa: F401
from app.models.economic import EconomicParam  # noqa: F401
from app.models.permit_event import WellPermitEvent  # noqa: F401
from app.models.mechanic import MechanicEvent, MechanicStageLog  # noqa: F401
from app.models.mechanic_part import MechanicPart  # noqa: F401
from app.models.finance import FinanceStatement, FinanceItem  # noqa: F401


################################################################################
# FILE: attachment.py
################################################################################

"""Polymorphic file attachment (مدیریت اسناد).

One row per uploaded file, linked to any entity via (entity_type, entity_id) —
e.g. ('well', 42), ('drilling', 7). The physical file lives under instance/
uploads/<stored_name>; the DB keeps metadata only.
"""
from app.extensions import db
from app.models.mixins import AuditMixin


class Attachment(db.Model, AuditMixin):
    __tablename__ = "attachments"
    __table_args__ = (
        db.Index("ix_attachment_entity", "entity_type", "entity_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    entity_type = db.Column(db.String(30), nullable=False)   # well|drilling|pump_test|...
    entity_id = db.Column(db.Integer, nullable=False)

    title = db.Column(db.String(200))                        # عنوان سند (optional)
    kind = db.Column(db.String(20))                          # permit|report|photo|video|other
    original_name = db.Column(db.String(255), nullable=False)
    stored_name = db.Column(db.String(80), nullable=False, unique=True)
    content_type = db.Column(db.String(100))
    size_bytes = db.Column(db.Integer)

    @property
    def size_human(self):
        n = self.size_bytes or 0
        for unit in ("B", "KB", "MB", "GB"):
            if n < 1024:
                return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
            n /= 1024
        return f"{n:.1f} TB"

    def __repr__(self):
        return f"<Attachment {self.entity_type}#{self.entity_id} {self.original_name}>"



################################################################################
# FILE: audit.py
################################################################################

"""Generic change history (audit log) for any entity."""
from datetime import datetime

from app.extensions import db


class RecordHistory(db.Model):
    __tablename__ = "record_history"

    id = db.Column(db.Integer, primary_key=True)
    entity_type = db.Column(db.String(40), nullable=False, index=True)  # e.g. "drilling"
    entity_id = db.Column(db.Integer, nullable=False, index=True)
    action = db.Column(db.String(20), nullable=False)  # create|update|submit|approve|reject|revert|delete
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    detail = db.Column(db.Text)

    user = db.relationship("User")

    def __repr__(self):
        return f"<RecordHistory {self.entity_type}#{self.entity_id} {self.action}>"



################################################################################
# FILE: baseline.py
################################################################################

"""Dynamic per-well performance baseline (خط‌پایه‌ی پویا).

The reference performance a well's decline is measured against. It is anchored to
the most recent STRUCTURAL event (drilling / rehab / relocation) — events that
change the WELL itself — so a rehab correctly resets the baseline. Recomputed by
services/baseline.py. Prioritization measures decline against the current baseline.
"""
from app.extensions import db
from app.models.mixins import TimestampMixin


class WellBaseline(db.Model, TimestampMixin):
    __tablename__ = "well_baselines"

    id = db.Column(db.Integer, primary_key=True)
    well_id = db.Column(db.Integer, db.ForeignKey("wells.id"), nullable=False, index=True)
    well = db.relationship("Well", backref=db.backref("baselines", cascade="all, delete-orphan"))

    anchor_event_type = db.Column(db.String(20))   # drilling | rehab | relocation | initial
    anchor_event_id = db.Column(db.Integer)
    anchor_date = db.Column(db.Date)

    baseline_kind = db.Column(db.String(20), default="best_observed")  # best_observed | design
    baseline_discharge_lps = db.Column(db.Float)
    baseline_dynamic_level = db.Column(db.Float)
    baseline_specific_capacity = db.Column(db.Float)   # Q / drawdown  (l/s per m)
    baseline_date = db.Column(db.Date)                 # date the baseline value was observed

    is_current = db.Column(db.Boolean, default=True, index=True)
    source = db.Column(db.String(40))

    def __repr__(self):
        return f"<WellBaseline well={self.well_id} Q={self.baseline_discharge_lps}>"



################################################################################
# FILE: constants.py
################################################################################

"""Enumerations and module/action catalogs used across the app.

Keeping these in one place lets the RBAC seed, forms, and templates stay in sync.
"""

# RBAC modules (sections of the system) and the actions each supports.
MODULES = [
    ("drilling", "حفاری و توسعه"),
    ("pump_test", "آزمایش پمپاژ"),
    ("pump_select", "انتخاب پمپ"),
    ("install", "نصب/کشیدن پمپ"),
    ("operation", "بهره‌برداری/دبی‌سنجی"),
    ("maintenance", "نگهداری و تعمیرات"),
    ("rehab", "بهسازی"),
    ("relocation", "جابه‌جایی"),
    ("water_level", "پایش تراز آب"),
    ("documents", "اسناد و مدارک"),
    ("videometry", "چاه‌نگاری"),
    ("wells", "چاه‌ها"),
    ("orgs", "واحدهای سازمانی"),
    ("reports", "گزارش‌ها"),
    ("admin", "مدیریت سیستم"),
    ("permit", "پروانه"),
    ("mechanic", "کارگاه مکانیک"),
    ("finance", "صورت‌وضعیت مالی"),
]

ACTIONS = [
    ("view", "مشاهده"),
    ("create", "ایجاد"),
    ("edit", "ویرایش"),
    ("delete", "حذف"),
    ("approve", "تأیید"),
]

MODULE_LABELS = dict(MODULES)
ACTION_LABELS = dict(ACTIONS)

# Sidebar navigation, grouped to stay uncluttered as modules grow.
# Each item: (module_or_None, endpoint, label, icon). module=None -> always shown.
# New lifecycle/module sections slot into the relevant group as they come online.
NAV_GROUPS = [
    ("عمومی", [
        (None, "main.dashboard", "داشبورد", "bi-grid-1x2-fill"),
        ("reports", "reports.alerts", "هشدارها", "bi-bell"),
    ]),
    ("اطلاعات پایه", [
        ("wells", "wells.list_wells", "چاه‌ها", "bi-droplet-half"),
        ("orgs", "orgs.list_orgs", "واحدهای سازمانی", "bi-diagram-3"),
    ]),
    ("تحلیل مکانی", [
        ("reports", "gis.map", "نقشه", "bi-geo-alt"),
        ("reports", "gis.analysis", "تحلیل هیدروژئولوژیک", "bi-layers"),
        ("reports", "reports.zones", "داشبورد پهنه‌ها", "bi-grid-3x3-gap"),
    ]),
    ("چرخه‌ی عمر", [
        ("relocation", "relocation.list_relocations", "جابه‌جایی چاه‌ها", "bi-signpost-2"),
    ]),
    ("گزارش‌ها", [
        ("reports", "reports.prioritization", "اولویت‌بندی چاه‌ها", "bi-sort-numeric-down"),
        ("reports", "reports.analytics", "تحلیل پیش‌بینانه", "bi-graph-up-arrow"),
        ("reports", "reports.portfolio", "سبد بهینه‌ی بهسازی", "bi-clipboard-check"),
        ("reports", "reports.dispatch", "بهره‌برداری بهینه میدان", "bi-diagram-3-fill"),
        ("reports", "reports.energy", "داشبورد انرژی", "bi-lightning-charge"),
        ("reports", "reports.suppliers", "مقایسه تأمین‌کننده‌ها", "bi-bar-chart"),
        ("reports", "exports.index", "خروجی داده‌ها", "bi-download"),
    ]),
    ("ابزارها", [
        ("pump_select", "pump_select.calculator", "محاسبه‌گر انتخاب پمپ", "bi-calculator"),
    ]),
    ("مدیریت", [
        ("admin", "main.admin_users", "کاربران", "bi-people"),
        ("admin", "main.admin_economics", "پارامترهای اقتصادی", "bi-cash-coin"),
    ]),
    ("تحلیل‌های ویژه", [
        (None, "production_trend.index", "تحلیل روند تولید چاه‌ها", "bi-graph-up"),
        (None, "permit.index", "وضعیت پروانه چاه‌ها", "bi-file-earmark-text"),
        (None, "mechanic.index", "کارگاه مکانیک", "bi-tools"),
        (None, "finance.index", "صورت‌وضعیت مالی", "bi-cash-stack"),
    ]),
]

# --- domain enums ---
RELOCATION_CANDIDACY = [
    ("final", "کاندید نهایی"),
    ("proposed", "پیشنهاد شده"),
    ("not_candidate", "کاندید نیست"),
    ("impossible", "امکان جابه‌جایی نیست"),
]
RELOCATION_TYPES = [
    ("in_place", "در محل خود"),
    ("other_surplus", "محل دیگر (مازاد تخصیص)"),
    ("green_space", "فضای سبز شهرداری"),
    ("edu_admin", "فضای آموزشی/اداری"),
]

MAINTENANCE_TYPES = [
    ("preventive", "پیشگیرانه"),
    ("corrective", "اصلاحی"),
    ("emergency", "اضطراری"),
]
MAINTENANCE_CATEGORIES = [
    ("mechanical", "مکانیکی"),
    ("electrical", "برقی"),
    ("hydraulic", "هیدرولیکی"),
    ("instrumentation", "ابزار دقیق/کنتور"),
    ("other", "سایر"),
]

ORG_UNIT_TYPES = [
    ("office", "اداره"),
    ("center", "مرکز آبرسانی"),
    ("rural_region", "منطقه روستایی (۵)"),
]

WELL_KINDS = [
    ("urban", "شهری"),
    ("rural", "روستایی"),
]

# نوع چاه از نظر سازه (پروانه‌ی Borwells)
WELL_CONSTRUCTION_TYPES = [
    ("limestone", "آهکی"),
    ("cementation", "سیمانتاسیون"),
    ("normal", "معمولی"),
]

WELL_STATUSES = [
    ("in_circuit", "در مدار"),
    ("out", "خارج از مدار"),
    ("under_rehab", "در حال بهسازی"),
    ("abandoned", "متروکه"),
    ("relocated", "جابه‌جا شده"),
]

LOCATION_STATUSES = [
    ("pre_drilled", "حفرشده از قبل"),
    ("relocated_stage1", "جابه‌جایی مرحله ۱"),
    ("new", "جدید"),
]

IDENTIFIER_TYPES = [
    ("klasse", "کلاسه چاه"),
    ("power_subscription", "اشتراک برق"),
    ("name", "نام پیشین"),
]

# Drilling permit / request type (پروانه چاه). Also a structural baseline-reset event.
REQUEST_TYPES = [
    ("new", "جدید"),
    ("relocation", "جابجایی"),
    ("deepening", "کف‌شکنی"),
]

DRILL_METHODS = [
    ("rotary", "دورانی"),
    ("percussion", "ضربه‌ای"),
    ("other", "سایر"),
]

# نوع کارکرد در فرم دبی‌سنجی (مقدار فارسی مستقیماً ذخیره می‌شود تا با منبع یکی باشد)
OPERATING_TYPES = ["عادی", "فشار شبکه", "زیر شبکه"]

FLOW_TEST_REASONS = ["سالیانه", "افت آبدهی", "نصب جدید", "نصب پمپ", "جمع آوری", "سایر"]

PUMP_TEST_TYPES = [("step", "پلکانی"), ("constant", "دبی ثابت")]

# تجهیز نو یا تعمیری
EQUIP_CONDITIONS = [("new", "نو"), ("repaired", "تعمیری")]
SUPPLIER_KINDS = [
    ("manufacturer", "سازنده"),
    ("repair_shop", "تعمیرگاه/کارگاه"),
    ("contractor", "پیمانکار"),
    ("mixed", "ترکیبی"),
]

# Supplier name corrections (typos / artifacts) applied on import and manual entry.
SUPPLIER_ALIASES = {
    "نصراله زاده": "نصرازاده",
    "نو پمپیران": "پمپیران",
}


def canonical_supplier(name):
    name = (name or "").strip()
    return SUPPLIER_ALIASES.get(name, name)


# Videometry (چاه‌نگاری) finding types & severities
VIDEO_FINDING_TYPES = [
    ("casing_rupture", "پارگی جدار"),
    ("screen_blockage", "گرفتگی مشبک"),
    ("sediment", "رسوب‌گذاری"),
    ("erosion", "فرسایش"),
    ("corrosion", "خوردگی"),
    ("fallen_object", "اشیاء سقوطی"),
    ("encrustation", "سیمانته‌شدن پشت جداره"),
    ("other", "سایر"),
]
SEVERITY_LEVELS = [("low", "کم"), ("medium", "متوسط"), ("high", "زیاد")]

# Workflow states for event records (used from Phase 1 onward).
WORKFLOW_STATES = [
    ("draft", "پیش‌نویس"),
    ("submitted", "ثبت‌شده"),
    ("approved", "تأییدشده"),
    ("rejected", "برگشتی"),
]



################################################################################
# FILE: drilling.py
################################################################################

"""Drilling & well-development event (بخش حفاری و توسعه).

Fields mirror the real source files (Borwells.xlsx / حفاری.xlsx / صورتجلسه).
Carries the approval workflow (draft -> submitted -> approved).
"""
from app.extensions import db
from app.models.mixins import AuditMixin, WorkflowMixin


class Drilling(db.Model, AuditMixin, WorkflowMixin):
    __tablename__ = "drilling"

    id = db.Column(db.Integer, primary_key=True)
    well_id = db.Column(db.Integer, db.ForeignKey("wells.id"), nullable=False, index=True)
    well = db.relationship("Well", backref=db.backref("drillings", cascade="all, delete-orphan"))

    # Permit / request
    request_type = db.Column(db.String(20))   # new | relocation | deepening (جدید/جابجایی/کف‌شکنی)
    drill_method = db.Column(db.String(40))    # روش حفاری (دورانی…)

    # Parties
    executor = db.Column(db.String(120))       # نام مجری
    contractor = db.Column(db.String(120))     # پیمانکار
    supervisor = db.Column(db.String(120))     # ناظر
    credit_source = db.Column(db.String(120))  # محل تأمین اعتبار
    contract_no = db.Column(db.String(40))
    contract_date = db.Column(db.Date)

    # Schedule
    start_date = db.Column(db.Date)            # تاریخ استقرار دستگاه حفاری
    end_date = db.Column(db.Date)              # تاریخ ترخیص / پایان

    # Geometry
    well_depth_permit = db.Column(db.Float)    # عمق چاه در پروانه
    well_depth_actual = db.Column(db.Float)    # عمق حفاری اصلاحی/واقعی
    casing_diameter_in = db.Column(db.Float)
    casing_total_len = db.Column(db.Float)
    steel_blank_len = db.Column(db.Float)
    steel_screen_len = db.Column(db.Float)
    upvc_blank_len = db.Column(db.Float)
    upvc_screen_len = db.Column(db.Float)
    transition_len = db.Column(db.Float)

    # Hydraulics (summary; detailed steps live with the pump test)
    static_level = db.Column(db.Float)
    max_yield_lps = db.Column(db.Float)
    proposed_discharge_lps = db.Column(db.Float)
    dynamic_at_proposed = db.Column(db.Float)
    drawdown = db.Column(db.Float)
    coeff_a = db.Column(db.Float)
    coeff_b = db.Column(db.Float)

    videometry_done = db.Column(db.Boolean, default=False)
    address = db.Column(db.String(255))
    notes = db.Column(db.Text)

    # Provenance: NULL = user-entered; "import:borwells" = migrated (idempotency key).
    source = db.Column(db.String(40), index=True)

    def __repr__(self):
        return f"<Drilling well={self.well_id} {self.status}>"



################################################################################
# FILE: economic.py
################################################################################

"""Editable economic parameters for the decision-support tools (Phase 6).

Cost data is not present in the source files, so the optimizers use these
admin-editable assumptions (electricity tariff defaults from real energy data).
"""
from app.extensions import db
from app.models.mixins import TimestampMixin


class EconomicParam(db.Model, TimestampMixin):
    __tablename__ = "economic_params"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False, index=True)
    value = db.Column(db.Float, nullable=False)
    label = db.Column(db.String(120), nullable=False)
    unit = db.Column(db.String(40))

    def __repr__(self):
        return f"<EconomicParam {self.key}={self.value}>"


# (key, label, default, unit)
DEFAULT_PARAMS = [
    ("electricity_tariff", "تعرفه‌ی برق", 2000.0, "ریال/kWh"),
    ("rehab_cost", "هزینه‌ی متوسط بهسازی هر چاه", 2000000000.0, "ریال"),
    ("pump_price_per_kw", "قیمت پمپ به‌ازای هر kW موتور", 60000000.0, "ریال/kW"),
    ("pump_install_cost", "هزینه‌ی نصب/کشیدن", 500000000.0, "ریال"),
    ("discount_rate", "نرخ تنزیل سالانه", 25.0, "٪"),
    ("analysis_years", "افق تحلیل اقتصادی", 7.0, "سال"),
]



################################################################################
# FILE: finance.py
################################################################################

"""ماژول صورت‌وضعیت مالی: اسناد هزینه‌ی عملیات چاه (بهسازی، آزمایش پمپاژ و...).

هر سند = یک عملیات روی یک چاه، با پیمانکار، ضرایب پیمان و مبلغ کل.
هر سند چند «آیتم هزینه» دارد (ردیف‌های ریز صورت‌وضعیت).
"""
from app.extensions import db
from app.models.mixins import AuditMixin, WorkflowMixin


class FinanceStatement(db.Model, AuditMixin, WorkflowMixin):
    __tablename__ = "finance_statements"

    id = db.Column(db.Integer, primary_key=True)
    well_id = db.Column(db.Integer, db.ForeignKey("wells.id"), nullable=True, index=True)
    well = db.relationship(
        "Well", backref=db.backref("finance_statements", cascade="all, delete-orphan"))

    op_type = db.Column(db.String(60), index=True)     # بهسازی / آزمایش پمپاژ / ...
    op_description = db.Column(db.Text)                 # شرح/موضوع عملیات
    contractor = db.Column(db.String(120))             # پیمانکار
    contract_no = db.Column(db.String(60))             # شماره قرارداد
    statement_no = db.Column(db.String(60))            # شماره صورت‌وضعیت
    statement_kind = db.Column(db.String(40))          # موقت / قطعی / وضعیت ۱/۲/۳
    statement_date = db.Column(db.Date, index=True)    # تاریخ صورت‌وضعیت

    # ضرایب کلی
    coef_region = db.Column(db.Float)                  # ضریب منطقه
    coef_overhead = db.Column(db.Float)                # ضریب بالاسری
    coef_contract = db.Column(db.Float)                # ضریب پیمان

    # مبالغ (ریال)
    workshop_setup = db.Column(db.Float)               # تجهیز کارگاه
    total_before = db.Column(db.Float)                 # مبلغ کل قبل از ضرایب
    total_after = db.Column(db.Float)                  # مبلغ کل پس از ضرایب

    notes = db.Column(db.Text)
    source = db.Column(db.String(40), index=True)

    def __repr__(self):
        return f"<FinanceStatement {self.op_type} well={self.well_id} {self.total_after}>"


class FinanceItem(db.Model, AuditMixin):
    """یک ردیف هزینه در یک صورت‌وضعیت."""
    __tablename__ = "finance_items"

    id = db.Column(db.Integer, primary_key=True)
    statement_id = db.Column(db.Integer, db.ForeignKey("finance_statements.id"),
                             nullable=False, index=True)
    statement = db.relationship(
        "FinanceStatement", backref=db.backref("items", cascade="all, delete-orphan"))

    category = db.Column(db.String(120))       # شرح عملیات کلی (دسته)
    row_no = db.Column(db.String(20))          # شماره ردیف در فهرست بها
    description = db.Column(db.Text)           # شرح تفصیلی
    unit = db.Column(db.String(40))            # واحد (مورد/چاه/متر/کیلوگرم/ساعت)
    contract_qty = db.Column(db.Float)         # تعداد قرارداد
    quantity = db.Column(db.Float)             # مقدار انجام‌شده
    unit_price = db.Column(db.Float)           # مبلغ واحد قبل از ضرایب
    coefficient = db.Column(db.Float)          # ضریب
    total_amount = db.Column(db.Float)         # مبلغ کل پس از ضریب

    def __repr__(self):
        return f"<FinanceItem {self.description} {self.total_amount}>"
class FinanceItemAllocation(db.Model, AuditMixin):
    """تخصیص یک آیتم هزینه به یک چاه (برای صورت‌وضعیت‌های چند-چاهی).

    هر ردیف = سهم یک چاه از مقدارِ یک آیتم (مثلاً «احیا: کورده ۳ = ۱ چاه»).
    اگر چاه با سامانه تطبیق نخورد، well_id تهی می‌ماند و نام خام در well_name
    نگه داشته می‌شود تا بعداً وصل شود.
    """
    __tablename__ = "finance_item_allocations"

    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey("finance_items.id"),
                        nullable=False, index=True)
    item = db.relationship(
        "FinanceItem", backref=db.backref("allocations", cascade="all, delete-orphan"))

    well_id = db.Column(db.Integer, db.ForeignKey("wells.id"), nullable=True, index=True)
    well = db.relationship("Well", backref=db.backref("finance_allocations"))

    well_name = db.Column(db.String(120))   # نام خام چاه در فایل اکسل
    quantity = db.Column(db.Float)          # مقدار تخصیص‌یافته به این چاه

    def __repr__(self):
        return f"<FinanceItemAllocation item={self.item_id} well={self.well_name}>"    


################################################################################
# FILE: flow.py
################################################################################

"""Flow-metering / دبی‌سنجی event (بخش بهره‌برداری).

Header (one test on a date) + child operating points (کارکرد ۱..۵). Fields mirror
the real official form. Carries the approval workflow and audit.
"""
from app.extensions import db
from app.models.mixins import AuditMixin, WorkflowMixin


class FlowTest(db.Model, AuditMixin, WorkflowMixin):
    __tablename__ = "flow_tests"

    id = db.Column(db.Integer, primary_key=True)
    well_id = db.Column(db.Integer, db.ForeignKey("wells.id"), nullable=False, index=True)
    well = db.relationship("Well", backref=db.backref("flow_tests", cascade="all, delete-orphan"))

    test_date = db.Column(db.Date, index=True)
    test_reason = db.Column(db.String(60))        # دلیل آزمایش (سالیانه/افت آبدهی…)
    network_type = db.Column(db.String(30))       # نوع شبکه

    # well/pump context snapshot
    electropump_type = db.Column(db.String(40))   # تیپ الکتروپمپ
    electropump_type_prev = db.Column(db.String(40))
    install_date = db.Column(db.Date)             # تاریخ آخرین نصب
    install_depth = db.Column(db.Float)
    well_depth = db.Column(db.Float)
    construction_type = db.Column(db.String(20))  # سیمانته/غیرسیمانته (free)
    allowed_q = db.Column(db.Float)               # دبی مجاز
    design_q = db.Column(db.Float)                # دبی طراحی
    license_q = db.Column(db.Float)               # دبی پروانه
    power_subscription = db.Column(db.String(40))
    static_level = db.Column(db.Float)
    static_level_prev = db.Column(db.Float)
    last_rehab_date = db.Column(db.Date)
    pull_reason = db.Column(db.String(80))        # علت کشیدن پمپ
    meter_status = db.Column(db.String(60))       # کالیبراسیون/وضعیت کنتور
    meter_brand = db.Column(db.String(60))

    # electrical panel
    starter_type = db.Column(db.String(40))       # سیستم راه‌انداز (سافت/ستاره مثلث…)
    capacitor_capacity = db.Column(db.Float)
    voltage_on = db.Column(db.String(20))
    voltage_off = db.Column(db.String(20))
    ohm_ff = db.Column(db.String(20))
    ohm_fg = db.Column(db.String(20))

    line_pressure = db.Column(db.Float)           # فشار خط (bar)
    regulated_pressure = db.Column(db.String(20)) # فشار تنظیمی
    discharge_volume_m3 = db.Column(db.Float)     # حجم تخلیه

    expert_note = db.Column(db.Text)              # نظر کارشناس (منبع کدورت/شولات)

    # NULL = user-entered; "import:tajmi" = migrated (idempotency key).
    source = db.Column(db.String(40), index=True)

    points = db.relationship(
        "FlowTestPoint", back_populates="test",
        cascade="all, delete-orphan", order_by="FlowTestPoint.operating_no",
    )

    def __repr__(self):
        return f"<FlowTest well={self.well_id} {self.test_date} {self.status}>"


class FlowTestPoint(db.Model):
    __tablename__ = "flow_test_points"

    id = db.Column(db.Integer, primary_key=True)
    flow_test_id = db.Column(db.Integer, db.ForeignKey("flow_tests.id"), nullable=False, index=True)
    test = db.relationship("FlowTest", back_populates="points")

    operating_no = db.Column(db.Integer)          # شماره کارکرد
    operating_type = db.Column(db.String(30))     # نوع کارکرد (زیر شبکه/فشار شبکه/عادی)
    discharge_m3h = db.Column(db.Float)
    discharge_lps = db.Column(db.Float)           # آبدهی l/s
    head_m = db.Column(db.Float)
    drawdown_m = db.Column(db.Float)              # میزان افت لوله
    dynamic_level_m = db.Column(db.Float)         # سطح پویایی
    pressure_atm = db.Column(db.Float)
    water_column_m = db.Column(db.Float)
    water_column_change = db.Column(db.Float)     # تغییر ستون آب m/lps
    amperes = db.Column(db.String(40))            # آمپرها (سه فاز، متن)
    efficiency = db.Column(db.Float)              # راندمان
    cos_phi = db.Column(db.Float)
    active_power_kw = db.Column(db.Float)
    reactive_power_kvar = db.Column(db.Float)
    apparent_power_kva = db.Column(db.Float)
    mechanical_power_kw = db.Column(db.Float)
    energy_intensity_kwh_m3 = db.Column(db.Float) # مصرف ویژه انرژی

    def __repr__(self):
        return f"<FlowTestPoint test={self.flow_test_id} k{self.operating_no}>"



################################################################################
# FILE: maintenance.py
################################################################################

"""Well maintenance & repair event (بخش نگهداری و تعمیرات).

Fills the lifecycle gap between pump install and pull: preventive/corrective/
emergency interventions on the pump, motor, electrical panel or fittings that do
not require pulling the pump. Optionally linked to the active pump installation.
"""
from app.extensions import db
from app.models.mixins import AuditMixin, WorkflowMixin


class MaintenanceRecord(db.Model, AuditMixin, WorkflowMixin):
    __tablename__ = "maintenance_records"

    id = db.Column(db.Integer, primary_key=True)
    well_id = db.Column(db.Integer, db.ForeignKey("wells.id"), nullable=False, index=True)
    well = db.relationship(
        "Well", backref=db.backref("maintenance_records", cascade="all, delete-orphan"))

    # optional link to the pump installation this maintenance applies to
    pump_installation_id = db.Column(db.Integer, db.ForeignKey("pump_installations.id"), nullable=True)
    pump_installation = db.relationship("PumpInstallation")

    report_date = db.Column(db.Date, index=True)
    maint_type = db.Column(db.String(20))         # preventive|corrective|emergency
    category = db.Column(db.String(20))           # mechanical|electrical|hydraulic|...

    down_from = db.Column(db.Date)                # شروع خاموشی
    down_to = db.Column(db.Date)                  # پایان خاموشی
    downtime_hours = db.Column(db.Float)          # مدت خاموشی (ساعت)

    fault_desc = db.Column(db.Text)               # شرح خرابی
    action_taken = db.Column(db.Text)             # اقدام انجام‌شده
    parts_replaced = db.Column(db.String(200))    # قطعات تعویض‌شده

    contractor_id = db.Column(db.Integer, db.ForeignKey("suppliers.id"))
    contractor = db.relationship("Supplier")
    cost = db.Column(db.Float)                    # هزینه (ریال/تومان)

    notes = db.Column(db.Text)
    source = db.Column(db.String(40), index=True)

    @property
    def downtime_days(self):
        if self.down_from and self.down_to:
            return (self.down_to - self.down_from).days
        return None

    def __repr__(self):
        return f"<MaintenanceRecord well={self.well_id} {self.maint_type} {self.status}>"



################################################################################
# FILE: mechanic.py
################################################################################

"""رویداد کارگاه مکانیک (کشیدن/نصب الکتروپمپ).

ثبت کامل فرایند کشیدن و نصب الکتروپمپ چاه: نوع عملیات، پیمانکار، مشخصات موتور و
پمپ، عمق‌ها و سطوح، هد و دبی، آزمایش پمپاژ کارگاه. بر پایه‌ی فایل «گزارش عملکرد
کشیدن و نصب». مثل بقیه‌ی رویدادها با گردش‌کار و ممیزی.
"""
from app.extensions import db
from app.models.mixins import AuditMixin, WorkflowMixin


class MechanicEvent(db.Model, AuditMixin, WorkflowMixin):
    __tablename__ = "mechanic_events"

    id = db.Column(db.Integer, primary_key=True)
    well_id = db.Column(db.Integer, db.ForeignKey("wells.id"), nullable=False, index=True)
    well = db.relationship(
        "Well", backref=db.backref("mechanic_events", cascade="all, delete-orphan")
    )

    # اطلاعات پایه
    op_date = db.Column(db.Date, index=True)          # تاریخ عملیات
    op_type = db.Column(db.String(40))                # کشیدن/نصب/جمع‌آوری/نصب جدید
    fault_description = db.Column(db.Text)            # شرح خرابی از نظر بهره‌بردار
    contractor = db.Column(db.String(120))           # نام پیمانکار
    pm_form_no = db.Column(db.String(60))            # فرم نصب در PM

    # موتور
    motor_desc = db.Column(db.String(200))           # مشخصات موتور
    motor_condition = db.Column(db.String(40))       # نو/تعمیری
    # پمپ
    pump_desc = db.Column(db.String(200))            # مشخصات پمپ
    pump_condition = db.Column(db.String(40))        # نو/تعمیری

    # عمق و سطوح (متر)
    tip_change = db.Column(db.String(60))            # تغییر تیپ
    prev_install_date = db.Column(db.Date)           # تاریخ نصب قبلی
    well_depth = db.Column(db.Float)                 # عمق چاه
    prev_install_depth = db.Column(db.Float)         # عمق نصب قبلی
    curr_install_depth = db.Column(db.Float)         # عمق نصب فعلی
    static_level = db.Column(db.Float)               # سطح استاتیک
    dynamic_level = db.Column(db.Float)              # سطح دینامیک
    path_loss = db.Column(db.Float)                  # تلفات مسیر
    network_pressure = db.Column(db.Float)           # فشار شبکه (متر)
    total_head = db.Column(db.Float)                 # هد کلی (متر)
    design_flow = db.Column(db.Float)                # دبی طراحی
    pipe_diameter = db.Column(db.Float)             # قطر لوله آبده (اینچ)

    # آزمایش پمپاژ کارگاه
    pt_date = db.Column(db.Date)                     # تاریخ آزمایش پمپاژ کارگاه
    pt_pressure = db.Column(db.Float)               # فشار آزمایش پمپاژ
    pt_flow = db.Column(db.Float)                    # دبی آزمایش پمپاژ

    # کابل و راه‌انداز
    cable_size = db.Column(db.String(40))           # سایز کابل
    cable_change = db.Column(db.String(60))         # تغییر سایز/تیپ کابل
    starter = db.Column(db.String(60))              # راه‌انداز

    # عمر و تحلیل
    months_worked = db.Column(db.Integer)           # تعداد ماه‌های کارکرد
    mechanic_opinion = db.Column(db.Text)           # نظر کارگاه مکانیک
    notes = db.Column(db.Text)                       # توضیحات
    stage = db.Column(db.String(60), default="اعلام حادثه", index=True)  # مرحله‌ی فعلی
    fault_type = db.Column(db.String(60))   # نوع خرابی: سوختگی/مکانیکی/کاهش آبدهی
    source = db.Column(db.String(40), index=True)

    def __repr__(self):
        return f"<MechanicEvent well={self.well_id} {self.op_type} {self.op_date}>"
class MechanicStageLog(db.Model):
    """تاریخچه‌ی تغییر مرحله‌ی هر پرونده‌ی کارگاه مکانیک."""
    __tablename__ = "mechanic_stage_logs"

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("mechanic_events.id"), nullable=False, index=True)
    event = db.relationship("MechanicEvent", backref=db.backref("stage_logs", cascade="all, delete-orphan"))
    from_stage = db.Column(db.String(60))
    to_stage = db.Column(db.String(60))
    note = db.Column(db.Text)
    changed_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    changed_by = db.relationship("User")
    changed_at = db.Column(db.DateTime, server_default=db.func.now())    


################################################################################
# FILE: mechanic_part.py
################################################################################

"""انبار قطعات کارگاه مکانیک (قطعات موتور و پمپ).

هر ردیف یک قطعه: نوع تجهیز (موتور/پمپ)، نام قطعه، و شمارش موجودی به تفکیک
قابل‌استفاده/اسقاط و نو/تعمیری. بر پایه‌ی فایل «لیست تعمیرات موتور و پمپ».
"""
from app.extensions import db
from app.models.mixins import AuditMixin


class MechanicPart(db.Model, AuditMixin):
    __tablename__ = "mechanic_parts"

    id = db.Column(db.Integer, primary_key=True)
    equipment = db.Column(db.String(20), index=True)   # موتور / پمپ
    part_name = db.Column(db.String(200), nullable=False)
    total_count = db.Column(db.Integer, default=0)      # تعداد کل
    usable = db.Column(db.Integer, default=0)           # قابل استفاده
    scrap = db.Column(db.Integer, default=0)            # اسقاط
    new_count = db.Column(db.Integer, default=0)        # نو
    repaired = db.Column(db.Integer, default=0)         # تعمیری
    inventory_code = db.Column(db.String(60), index=True)  # کد انباری قطعه
    part_type = db.Column(db.String(120))                  # نوع قطعه
    manufacturer = db.Column(db.String(120))               # سازنده قطعه
    installed_count = db.Column(db.Integer, default=0)     # تعداد «نصب شد»
    collected_count = db.Column(db.Integer, default=0)     # تعداد «جمع‌آوری شد»
    source = db.Column(db.String(40), index=True)          # import / manual
    entry_date = db.Column(db.Date)   # تاریخ ورود به انبار
    notes = db.Column(db.String(300))

    def __repr__(self):
        return f"<MechanicPart {self.equipment}:{self.part_name}>"


################################################################################
# FILE: mixins.py
################################################################################

"""Reusable model mixins: timestamps, audit (who), and workflow (status)."""
from datetime import datetime

from sqlalchemy.orm import declared_attr

from app.extensions import db


class TimestampMixin:
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class AuditMixin(TimestampMixin):
    """Adds created_by / updated_by FK columns pointing at users.id."""

    @declared_attr
    def created_by_id(cls):
        return db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    @declared_attr
    def updated_by_id(cls):
        return db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    @declared_attr
    def creator(cls):
        return db.relationship(
            "User", foreign_keys=[cls.created_by_id], viewonly=True
        )


class WorkflowMixin:
    """Draft -> submitted -> approved/rejected lifecycle for event records.

    Not used by master-data tables (wells, org_units); applied to lifecycle
    event tables starting in Phase 1.
    """

    status = db.Column(db.String(20), default="draft", nullable=False, index=True)

    @declared_attr
    def submitted_by_id(cls):
        return db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    submitted_at = db.Column(db.DateTime, nullable=True)

    @declared_attr
    def approved_by_id(cls):
        return db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    approved_at = db.Column(db.DateTime, nullable=True)
    reject_reason = db.Column(db.Text, nullable=True)

    @declared_attr
    def submitter(cls):
        return db.relationship(
            "User", foreign_keys=[cls.submitted_by_id], viewonly=True
        )

    @declared_attr
    def approver(cls):
        return db.relationship(
            "User", foreign_keys=[cls.approved_by_id], viewonly=True
        )



################################################################################
# FILE: org.py
################################################################################

"""Organizational hierarchy: offices, supply centers, rural regions."""
from app.extensions import db
from app.models.mixins import TimestampMixin
from app.models.constants import MODULE_LABELS  # noqa: F401  (kept for parity)


class OrgUnit(db.Model, TimestampMixin):
    __tablename__ = "org_units"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    code = db.Column(db.String(40), index=True)
    unit_type = db.Column(db.String(20), nullable=False)  # office|center|rural_region

    parent_id = db.Column(db.Integer, db.ForeignKey("org_units.id"), nullable=True)
    parent = db.relationship(
        "OrgUnit", remote_side=[id], backref="children", foreign_keys=[parent_id]
    )

    def __repr__(self):
        return f"<OrgUnit {self.name} ({self.unit_type})>"



################################################################################
# FILE: permit.py
################################################################################

"""وضعیت پروانه‌ی چاه (permit status).

ثبت آخرین پروانه‌ی هر چاه: کد/نوع/شماره/تاریخ، تاریخ اعتبار (انقضا)، وضعیت
پرونده، نوع درخواست در حال پیگیری (تمدید/صدور/جابجایی)، مرحله‌ی پیگیری، جریمه‌ی
ناشی از انقضای اعتبار پروانه، و کلاسه‌ی آب منطقه‌ای.

منبع داده: شیت «کل چاهها» و «Data Base» از فایل پایگاه داده‌ی چاه‌ها.
تاریخ‌ها به‌صورت رشته‌ی شمسی نگه‌داری می‌شوند (مثل بقیه‌ی سامانه) و نمایش/محاسبه‌ی
انقضا با مقایسه‌ی رشته‌ی ۸رقمی یییی‌مم‌رر انجام می‌شود.
"""
from datetime import date

import jdatetime

from app.extensions import db
from app.models.mixins import AuditMixin, WorkflowMixin


class WellPermit(db.Model, AuditMixin, WorkflowMixin):
    __tablename__ = "well_permits"

    id = db.Column(db.Integer, primary_key=True)
    well_id = db.Column(db.Integer, db.ForeignKey("wells.id"), nullable=False, index=True)
    well = db.relationship(
        "Well", backref=db.backref("permits", cascade="all, delete-orphan")
    )

    # آخرین پروانه
    permit_code = db.Column(db.String(40))        # کد آخرین پروانه
    permit_type = db.Column(db.String(60))        # نوع آخرین پروانه (بهره‌برداری/حفر/تغییر محل)
    permit_no = db.Column(db.String(60))          # شماره آخرین پروانه
    permit_date = db.Column(db.String(10))        # تاریخ آخرین پروانه (شمسی yyyy/mm/dd)
    expiry_date = db.Column(db.String(10), index=True)  # تاریخ اعتبار/انقضا (شمسی)

    case_status = db.Column(db.String(60))        # وضعیت پرونده (دارای پروانه بهره‌برداری/حفر/غیرمجاز)
    klasse = db.Column(db.String(40))             # کلاسه آب منطقه‌ای

    # پیگیری درخواست جاری
    request_type = db.Column(db.String(120))      # درخواست (تمدید/صدور/جابجایی/…)
    followup_stage = db.Column(db.String(60))     # مرحله پیگیری (کارشناس/مالی/…)
    cost_paid = db.Column(db.Boolean)             # پرداخت هزینه

    # اقتصادی
    expiry_penalty_rial = db.Column(db.Float)     # تفاوت/جریمه انقضای اعتبار پروانه (ریال)
    contract_power_kw = db.Column(db.Float)       # قدرت قرارداد
    tariff = db.Column(db.String(40))             # تعرفه

    notes = db.Column(db.Text)
    source = db.Column(db.String(40), index=True)

    # ---------- helpers ----------
    @staticmethod
    def _digits8(s):
        """تاریخ شمسی را به رشته‌ی ۸رقمی ییییممرر برمی‌گرداند (برای مقایسه)."""
        if not s:
            return None
        d = "".join(ch for ch in str(s) if ch.isdigit())
        return d if len(d) == 8 else None

    @staticmethod
    def _today8():
        t = jdatetime.date.fromgregorian(date=date.today())
        return f"{t.year:04d}{t.month:02d}{t.day:02d}"

    @property
    def expiry_state(self):
        """وضعیت اعتبار: expired | near | valid | unknown."""
        e = self._digits8(self.expiry_date)
        if not e:
            return "unknown"
        today = self._today8()
        if e < today:
            return "expired"
        # نزدیک انقضا: تا ۹۰ روز آینده (تقریبی بر مبنای رشته‌ی تاریخ)
        ey, em, ed = int(e[:4]), int(e[4:6]), int(e[6:])
        ty, tm, td = int(today[:4]), int(today[4:6]), int(today[6:])
        months_left = (ey - ty) * 12 + (em - tm)
        if months_left < 3 or (months_left == 3 and ed <= td):
            return "near"
        return "valid"

    @property
    def expiry_state_label(self):
        return {
            "expired": "منقضی شده",
            "near": "نزدیک انقضا",
            "valid": "معتبر",
            "unknown": "نامشخص",
        }[self.expiry_state]

    def __repr__(self):
        return f"<WellPermit well={self.well_id} {self.permit_type} exp={self.expiry_date}>"



################################################################################
# FILE: permit_event.py
################################################################################

"""رویداد پروانه‌ی چاه (permit event).

ثبت پروانه‌ی هر چاه به‌عنوان یک رویداد در چرخه‌ی عمر: کد/نوع/شماره/تاریخ پروانه،
تاریخ اعتبار (انقضا)، وضعیت پرونده، درخواست جاری، مرحله پیگیری و جریمه.
"""
from datetime import date

import jdatetime

from app.extensions import db
from app.models.mixins import AuditMixin, WorkflowMixin


class WellPermitEvent(db.Model, AuditMixin, WorkflowMixin):
    __tablename__ = "well_permit_events"

    id = db.Column(db.Integer, primary_key=True)
    well_id = db.Column(db.Integer, db.ForeignKey("wells.id"), nullable=False, index=True)
    well = db.relationship(
        "Well", backref=db.backref("permit_events", cascade="all, delete-orphan")
    )

    permit_type = db.Column(db.String(60))        # نوع پروانه
    permit_code = db.Column(db.String(40))        # کد آخرین پروانه
    permit_no = db.Column(db.String(60))          # شماره پروانه
    permit_date = db.Column(db.Date)              # تاریخ صدور
    expiry_date = db.Column(db.Date, index=True)  # تاریخ اعتبار/انقضا
    case_status = db.Column(db.String(60))        # وضعیت پرونده
    klasse = db.Column(db.String(40))             # کلاسه آب منطقه‌ای
    request_type = db.Column(db.String(120))      # درخواست جاری
    followup_stage = db.Column(db.String(60))     # مرحله پیگیری
    cost_paid = db.Column(db.Boolean)
    expiry_penalty_rial = db.Column(db.Float)
    notes = db.Column(db.Text)
    source = db.Column(db.String(40), index=True)

    @property
    def expiry_state(self):
        if not self.expiry_date:
            return "unknown"
        today = date.today()
        if self.expiry_date < today:
            return "expired"
        months_left = (self.expiry_date.year - today.year) * 12 + (self.expiry_date.month - today.month)
        return "near" if months_left < 3 else "valid"

    @property
    def expiry_state_label(self):
        return {"expired": "منقضی شده", "near": "نزدیک انقضا",
                "valid": "معتبر", "unknown": "نامشخص"}[self.expiry_state]

    def __repr__(self):
        return f"<WellPermitEvent well={self.well_id} {self.expiry_date} {self.status}>"


################################################################################
# FILE: prioritization.py
################################################################################

"""Configurable weighted criteria for the well prioritization engine.

Each criterion maps to a metric computed per well (see services/prioritization.py).
Admins adjust weights / activeness; the score recomputes — no code change needed.
"""
from app.extensions import db
from app.models.mixins import TimestampMixin


class PrioritizationCriterion(db.Model, TimestampMixin):
    __tablename__ = "prioritization_criteria"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(40), unique=True, nullable=False)  # metric key
    label = db.Column(db.String(120), nullable=False)
    weight = db.Column(db.Float, default=1.0, nullable=False)
    direction = db.Column(db.String(12), default="higher_worse")  # higher_worse | lower_worse
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    def __repr__(self):
        return f"<PrioritizationCriterion {self.key} w={self.weight}>"


# Default criteria seeded into the DB (editable afterwards).
DEFAULT_CRITERIA = [
    ("discharge_decline", "افت دبی نسبت به بهترین مقدار چاه", 3.0, "higher_worse"),
    ("quality_flag", "مشکل کیفی/کدورت (پرچم قرمز)", 3.0, "higher_worse"),
    ("efficiency_low", "پایین بودن راندمان", 2.0, "lower_worse"),
    ("burn_count", "دفعات سوختن پمپ", 2.0, "higher_worse"),
    ("rehab_count", "دفعات بهسازی", 1.0, "higher_worse"),
    ("age_years", "سن چاه", 1.0, "higher_worse"),
    ("specific_energy", "انرژی ویژه‌ی بالا (kWh/m³)", 2.0, "higher_worse"),
]



################################################################################
# FILE: production.py
################################################################################

"""Monthly operational time-series (روند تولید چاه‌ها).

One row per (well, Jalali year, Jalali month). Long/normalized form of the wide
"روند تولید چاه ها.xlsx" pivot: monthly production volume (m³), pump run-hours,
average discharge (l/s) and well head pressure. This is the operational backbone
that feeds the prioritization decline metric, the per-well baseline, and the
analytics/AI phase. No approval workflow — it is bulk meter/operations data.
"""
from app.extensions import db
from app.models.mixins import TimestampMixin


class MonthlyProduction(db.Model, TimestampMixin):
    __tablename__ = "monthly_production"
    __table_args__ = (
        db.UniqueConstraint("well_id", "jyear", "jmonth", name="uq_monthly_prod_well_period"),
    )

    id = db.Column(db.Integer, primary_key=True)
    well_id = db.Column(db.Integer, db.ForeignKey("wells.id"), nullable=False, index=True)
    well = db.relationship(
        "Well", backref=db.backref("monthly_production", cascade="all, delete-orphan"))

    jyear = db.Column(db.Integer, nullable=False, index=True)   # سال شمسی (e.g. 1404)
    jmonth = db.Column(db.Integer, nullable=False)              # ماه شمسی 1..12

    production_m3 = db.Column(db.Float)        # تولید (حجم ماهانه، متر مکعب)
    run_hours = db.Column(db.Float)            # کارکرد (ساعت در ماه)
    avg_discharge_lps = db.Column(db.Float)    # دبی متوسط (l/s)
    well_pressure = db.Column(db.Float)        # فشار چاه

    # electricity (آذر 1404 onward, from the برق billing file)
    energy_kwh = db.Column(db.Float)           # کل مصرف (kWh)
    energy_cost_rial = db.Column(db.Float)     # جمع هزینه برق (ریال)
    contract_power_kw = db.Column(db.Float)    # قدرت قرارداد (kW)
    consumed_power_kw = db.Column(db.Float)    # قدرت مصرفی (kW)

    # NULL = user-entered; "import:trend" = migrated (idempotency marker).
    source = db.Column(db.String(40), index=True)

    @property
    def period_key(self):
        return self.jyear * 12 + (self.jmonth - 1)

    @property
    def specific_energy(self):
        """kWh per m³ pumped — the key energy-efficiency indicator."""
        if self.energy_kwh and self.production_m3 and self.production_m3 > 0:
            return round(self.energy_kwh / self.production_m3, 3)
        return None

    def __repr__(self):
        return f"<MonthlyProduction well={self.well_id} {self.jyear}/{self.jmonth}>"



################################################################################
# FILE: pump_asset.py
################################################################################

"""Pump installation/removal events (بخش نصب و کشیدن) + suppliers.

Each PumpInstallation is one duty cycle: install (with optional pull) of a pump
on a well, capturing manufacturer/contractor (for supplier comparison) and dates
(for lifespan analysis). A physical pump-asset registry with serials is deferred
until source data provides pump identity — see docs/DATA_MODEL.md §3.4 / §6.
"""
from app.extensions import db
from app.models.mixins import AuditMixin, WorkflowMixin
from app.utils.dates import format_jalali  # noqa: F401


class Supplier(db.Model):
    __tablename__ = "suppliers"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False, index=True)
    kind = db.Column(db.String(20))  # manufacturer | repair_shop | contractor | mixed
    contact = db.Column(db.String(120))
    notes = db.Column(db.Text)

    def __repr__(self):
        return f"<Supplier {self.name}>"


class PumpInstallation(db.Model, AuditMixin, WorkflowMixin):
    __tablename__ = "pump_installations"

    id = db.Column(db.Integer, primary_key=True)
    well_id = db.Column(db.Integer, db.ForeignKey("wells.id"), nullable=False, index=True)
    well = db.relationship("Well", backref=db.backref("installations", cascade="all, delete-orphan"))

    install_no = db.Column(db.Integer)            # شماره نصب
    install_date = db.Column(db.Date, index=True)
    pull_date = db.Column(db.Date)                # تاریخ کشیدن (NULL = در حال کار)

    # motor
    motor_power_kw = db.Column(db.Float)
    motor_condition = db.Column(db.String(10))    # new | repaired

    # pump
    pump_type = db.Column(db.String(60))          # تیپ پمپ (e.g. 384/8)
    pump_stages = db.Column(db.Integer)           # طبقه
    pump_condition = db.Column(db.String(10))     # new | repaired
    manufacturer_id = db.Column(db.Integer, db.ForeignKey("suppliers.id"))
    contractor_id = db.Column(db.Integer, db.ForeignKey("suppliers.id"))
    manufacturer = db.relationship("Supplier", foreign_keys=[manufacturer_id])
    contractor = db.relationship("Supplier", foreign_keys=[contractor_id])

    install_depth_m = db.Column(db.Float)
    well_depth_m = db.Column(db.Float)
    static_level = db.Column(db.Float)
    dynamic_level = db.Column(db.Float)
    route_loss = db.Column(db.Float)              # تلفات مسیر
    grid_pressure_m = db.Column(db.Float)         # فشار شبکه

    work_shift = db.Column(db.String(20))
    removal_reason = db.Column(db.String(120))    # علت کشیدن (سوختن/شولات/...)
    fault_by_operator = db.Column(db.Text)        # شرح خرابی از نظر بهره‌بردار
    fault_by_workshop = db.Column(db.Text)        # شرح خرابی از نظر کارگاه مکانیک
    pm_form_registered = db.Column(db.Boolean, default=False)

    notes = db.Column(db.Text)
    source = db.Column(db.String(40), index=True)

    @property
    def is_running(self):
        return self.pull_date is None

    @property
    def useful_life_months(self):
        if self.install_date and self.pull_date:
            days = (self.pull_date - self.install_date).days
            return round(days / 30.4, 1) if days >= 0 else None
        return None

    def __repr__(self):
        return f"<PumpInstallation well={self.well_id} #{self.install_no} {self.status}>"



################################################################################
# FILE: pump_catalog.py
################################################################################

"""Pump catalog: models + Q-H performance-curve points.

Imported from the manufacturer catalog (pump_data.js). Drives the pump-selection
calculator (matches a design point Q/TDH to the best pump). BEP = best-efficiency
point; BEB = best-efficiency band (optimal operating range start/end).
"""
from app.extensions import db


class PumpModel(db.Model):
    __tablename__ = "pump_models"

    id = db.Column(db.Integer, primary_key=True)
    model = db.Column(db.String(40), unique=True, nullable=False, index=True)  # عنوان تیپ پمپ
    ptype = db.Column(db.String(20), index=True)   # تیپ پمپ (first digits)
    title_electro = db.Column(db.String(60))       # عنوان تیپ الکتروپمپ
    stages = db.Column(db.Integer)
    motor_power_kw = db.Column(db.Float)
    npsh = db.Column(db.Float)
    nominal_current = db.Column(db.Float)
    length_mm = db.Column(db.Integer)
    weight_kg = db.Column(db.Integer)

    points = db.relationship(
        "PumpCurvePoint", back_populates="model",
        cascade="all, delete-orphan", order_by="PumpCurvePoint.flow_m3h",
    )

    def __repr__(self):
        return f"<PumpModel {self.model}>"


class PumpCurvePoint(db.Model):
    __tablename__ = "pump_curve_points"

    id = db.Column(db.Integer, primary_key=True)
    model_id = db.Column(db.Integer, db.ForeignKey("pump_models.id"), nullable=False, index=True)
    model = db.relationship("PumpModel", back_populates="points")

    flow_m3h = db.Column(db.Float)
    flow_lps = db.Column(db.Float)
    head_m = db.Column(db.Float)
    efficiency_pct = db.Column(db.Float)
    is_bep = db.Column(db.Boolean, default=False)        # نقطه اوج راندمان
    is_beb_start = db.Column(db.Boolean, default=False)  # شروع محدوده بهینه
    is_beb_end = db.Column(db.Boolean, default=False)    # پایان محدوده بهینه

    def __repr__(self):
        return f"<PumpCurvePoint m{self.model_id} {self.flow_m3h}@{self.head_m}>"



################################################################################
# FILE: pump_select.py
################################################################################

"""Pump selection / re-engineering record (بخش انتخاب پمپ — ثبت تصمیم).

Captures the re-engineering decision (previous vs selected pump/motor/discharge)
and the execution chain (form -> pull -> videometry -> install -> verification
flow-test). The verification discharge/head vs the target shows whether the
action succeeded. The catalog-driven selection CALCULATOR is a separate part
(needs pump-catalog data).
"""
from app.extensions import db
from app.models.mixins import AuditMixin, WorkflowMixin


class PumpSelection(db.Model, AuditMixin, WorkflowMixin):
    __tablename__ = "pump_selections"

    id = db.Column(db.Integer, primary_key=True)
    well_id = db.Column(db.Integer, db.ForeignKey("wells.id"), nullable=False, index=True)
    well = db.relationship("Well", backref=db.backref("pump_selections", cascade="all, delete-orphan"))

    action_needed = db.Column(db.String(60))      # اقدام مورد نیاز (افزایش دبی…)
    jyear = db.Column(db.String(8))
    jmonth = db.Column(db.String(16))
    status_done = db.Column(db.String(40))        # وضعیت انجام

    # previous configuration
    prev_pump_type = db.Column(db.String(60))
    prev_motor_type = db.Column(db.String(60))
    prev_discharge_lps = db.Column(db.Float)

    # selected (after review)
    selected_pump_type = db.Column(db.String(60))
    selected_motor_type = db.Column(db.String(60))
    target_discharge_lps = db.Column(db.Float)
    discharge_increase_lps = db.Column(db.Float)
    selected_head_m = db.Column(db.Float)

    # execution chain
    form_delivery_date = db.Column(db.Date, index=True)
    pull_date = db.Column(db.Date)
    videometry_date = db.Column(db.Date)
    install_date = db.Column(db.Date)
    verify_flowtest_date = db.Column(db.Date)
    verify_discharge_lps = db.Column(db.Float)
    verify_head_m = db.Column(db.Float)

    notes = db.Column(db.Text)
    source = db.Column(db.String(40), index=True)

    @property
    def achieved_pct(self):
        """How much of the targeted discharge the verification flow-test reached."""
        if self.target_discharge_lps and self.verify_discharge_lps is not None and self.target_discharge_lps > 0:
            return round(self.verify_discharge_lps / self.target_discharge_lps * 100)
        return None

    def __repr__(self):
        return f"<PumpSelection well={self.well_id} {self.action_needed} {self.status}>"



################################################################################
# FILE: pump_test.py
################################################################################

"""Pump test event (بخش آزمایش پمپاژ).

Header (one test) + step-drawdown child rows. Includes the proposed equipment /
recommended pump (the صورتجلسه also proposes a pump), plus hydrodynamic
coefficients a,b (drawdown = a·Q + b·Q²). Carries the approval workflow.
"""
from app.extensions import db
from app.models.mixins import AuditMixin, WorkflowMixin


class PumpTest(db.Model, AuditMixin, WorkflowMixin):
    __tablename__ = "pump_tests"

    id = db.Column(db.Integer, primary_key=True)
    well_id = db.Column(db.Integer, db.ForeignKey("wells.id"), nullable=False, index=True)
    well = db.relationship("Well", backref=db.backref("pump_tests", cascade="all, delete-orphan"))

    test_date = db.Column(db.Date, index=True)
    test_type = db.Column(db.String(20))   # step | constant
    duration_h = db.Column(db.Float)       # مدت شستشو و آزمایش (ساعت)

    # parties / contract (from صورتجلسه)
    contractor = db.Column(db.String(120))
    consultant = db.Column(db.String(120))
    employer = db.Column(db.String(120))
    contract_no = db.Column(db.String(40))
    project_title = db.Column(db.String(255))

    # results summary
    static_level = db.Column(db.Float)
    max_dynamic_level = db.Column(db.Float)
    max_drawdown = db.Column(db.Float)
    max_yield_lps = db.Column(db.Float)
    coeff_a = db.Column(db.Float)
    coeff_b = db.Column(db.Float)

    # proposed / recommended equipment
    proposed_discharge_lps = db.Column(db.Float)   # دبی مجاز پیشنهادی
    proposed_install_depth_m = db.Column(db.Float) # عمق نصب پیشنهادی
    resulting_drawdown_m = db.Column(db.Float)     # میزان افت حاصله
    motor_type = db.Column(db.String(60))
    motor_power_hp = db.Column(db.Float)
    gearbox_power_hp = db.Column(db.Float)
    gearbox_ratio = db.Column(db.String(20))
    pump_type = db.Column(db.String(80))           # نوع پمپ توربینی
    pump_stages = db.Column(db.Integer)
    pump_diameter_in = db.Column(db.Float)
    max_rpm = db.Column(db.Float)
    discharge_pipe_diameter_in = db.Column(db.Float)

    notes = db.Column(db.Text)
    source = db.Column(db.String(40), index=True)  # NULL=manual; import marker

    steps = db.relationship(
        "PumpTestStep", back_populates="test",
        cascade="all, delete-orphan", order_by="PumpTestStep.step_no",
    )

    def __repr__(self):
        return f"<PumpTest well={self.well_id} {self.test_date} {self.status}>"


class PumpTestStep(db.Model):
    __tablename__ = "pump_test_steps"

    id = db.Column(db.Integer, primary_key=True)
    pump_test_id = db.Column(db.Integer, db.ForeignKey("pump_tests.id"), nullable=False, index=True)
    test = db.relationship("PumpTest", back_populates="steps")

    step_no = db.Column(db.Integer)
    rpm = db.Column(db.Float)                 # دور موتور
    discharge_lps = db.Column(db.Float)       # دبی
    observed_drawdown = db.Column(db.Float)   # افت مشاهده‌ای
    calc_drawdown = db.Column(db.Float)       # افت محاسبه‌شده
    grid_loss = db.Column(db.Float)           # افت شبکه
    aquifer_loss = db.Column(db.Float)        # افت سفره
    efficiency = db.Column(db.Float)          # راندمان

    def __repr__(self):
        return f"<PumpTestStep test={self.pump_test_id} s{self.step_no}>"



################################################################################
# FILE: quality.py
################################################################################

"""Water-quality observations (بخش کیفیت آب).

Qualitative flags (turbidity/کدورت, sand/شولات, potability) extracted from
flow-test expert notes, plus numeric fields (EC, turbidity NTU, chlorine, pH,
TDS) for future lab/manual entry. Feeds the prioritization red-flag criterion.
"""
from app.extensions import db
from app.models.mixins import AuditMixin


class WaterQuality(db.Model, AuditMixin):
    __tablename__ = "water_quality"

    id = db.Column(db.Integer, primary_key=True)
    well_id = db.Column(db.Integer, db.ForeignKey("wells.id"), nullable=False, index=True)
    well = db.relationship("Well", backref=db.backref("water_quality", cascade="all, delete-orphan"))

    sample_date = db.Column(db.Date, index=True)
    flow_test_id = db.Column(db.Integer, db.ForeignKey("flow_tests.id"), nullable=True)

    # qualitative flags
    turbidity = db.Column(db.Boolean, default=False)   # کدورت
    sholat = db.Column(db.Boolean, default=False)      # شولات (sand)
    is_potable = db.Column(db.Boolean)                 # None = unknown

    # numeric (lab / manual)
    ec = db.Column(db.Float)
    turbidity_ntu = db.Column(db.Float)
    chlorine = db.Column(db.Float)
    ph = db.Column(db.Float)
    tds = db.Column(db.Float)

    note = db.Column(db.Text)
    source = db.Column(db.String(40), index=True)

    @property
    def severity(self):
        if self.is_potable is False:
            return "high"
        if self.turbidity or self.sholat:
            return "medium"
        return "low"

    def __repr__(self):
        return f"<WaterQuality well={self.well_id} {self.sample_date}>"



################################################################################
# FILE: rbac.py
################################################################################

"""Users, roles, and permissions (module x action RBAC)."""
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from app.extensions import db
from app.models.mixins import TimestampMixin

user_roles = db.Table(
    "user_roles",
    db.Column("user_id", db.Integer, db.ForeignKey("users.id"), primary_key=True),
    db.Column("role_id", db.Integer, db.ForeignKey("roles.id"), primary_key=True),
)

role_permissions = db.Table(
    "role_permissions",
    db.Column("role_id", db.Integer, db.ForeignKey("roles.id"), primary_key=True),
    db.Column("permission_id", db.Integer, db.ForeignKey("permissions.id"), primary_key=True),
)


class Permission(db.Model, TimestampMixin):
    __tablename__ = "permissions"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(60), unique=True, nullable=False, index=True)  # "wells:view"
    module = db.Column(db.String(40), nullable=False, index=True)
    action = db.Column(db.String(20), nullable=False)
    description = db.Column(db.String(120))

    def __repr__(self):
        return f"<Permission {self.code}>"


class Role(db.Model, TimestampMixin):
    __tablename__ = "roles"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(60), unique=True, nullable=False)
    description = db.Column(db.String(160))
    permissions = db.relationship(
        "Permission", secondary=role_permissions, backref="roles", lazy="joined"
    )

    def __repr__(self):
        return f"<Role {self.name}>"


class User(db.Model, UserMixin, TimestampMixin):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(60), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(120))
    email = db.Column(db.String(120))
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    is_superuser = db.Column(db.Boolean, default=False, nullable=False)
    # مشخصات پرسنلی (دسته ۵ - مدیریت کاربران)
    first_name = db.Column(db.String(60))
    last_name = db.Column(db.String(60))
    national_id = db.Column(db.String(10), index=True)
    personnel_code = db.Column(db.String(30), index=True)
    position = db.Column(db.String(120))       # سمت سازمانی
    phone = db.Column(db.String(20))
    notes = db.Column(db.Text)
    last_login_at = db.Column(db.DateTime)
    last_login_ip = db.Column(db.String(50))
    last_login_agent = db.Column(db.String(255))

    # Optional geographic scope (Phase: regional access control).
    org_unit_id = db.Column(db.Integer, db.ForeignKey("org_units.id"), nullable=True)
    org_unit = db.relationship("OrgUnit", foreign_keys=[org_unit_id])

    roles = db.relationship(
        "Role", secondary=user_roles, backref="users", lazy="joined"
    )

    # --- password helpers ---
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    # --- authorization ---
    @property
    def permission_codes(self):
        codes = set()
        for role in self.roles:
            for perm in role.permissions:
                codes.add(perm.code)
        return codes

    def has_permission(self, module, action):
        if self.is_superuser:
            return True
        return f"{module}:{action}" in self.permission_codes

    def has_module(self, module):
        """True if the user can at least view the given module."""
        if self.is_superuser:
            return True
        return any(c.startswith(f"{module}:") for c in self.permission_codes)

    def __repr__(self):
        return f"<User {self.username}>"
class LoginLog(db.Model, TimestampMixin):
    """لاگ ورود/خروج کاربران برای گزارش فعالیت (دسته ۵)."""
    __tablename__ = "login_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    user = db.relationship("User", backref=db.backref("login_logs", lazy="dynamic"))

    login_at = db.Column(db.DateTime, nullable=False, index=True)
    logout_at = db.Column(db.DateTime)
    ip_address = db.Column(db.String(50))
    user_agent = db.Column(db.String(255))

    @property
    def duration_seconds(self):
        end = self.logout_at
        if not end or not self.login_at:
            return None
        return int((end - self.login_at).total_seconds())

    def __repr__(self):
        return f"<LoginLog u={self.user_id} at={self.login_at}>"


################################################################################
# FILE: rehab.py
################################################################################

"""Well rehabilitation event (بخش بهسازی).

Captures the rehab + the post-rehab pumping (separate contractors), and the
discharge before/after (the improvement metric — feeds prioritization).
"""
from app.extensions import db
from app.models.mixins import AuditMixin, WorkflowMixin


class Rehabilitation(db.Model, AuditMixin, WorkflowMixin):
    __tablename__ = "rehabilitations"

    id = db.Column(db.Integer, primary_key=True)
    well_id = db.Column(db.Integer, db.ForeignKey("wells.id"), nullable=False, index=True)
    well = db.relationship("Well", backref=db.backref("rehabilitations", cascade="all, delete-orphan"))

    stage = db.Column(db.String(20))              # مرحله (اول/دوم…)
    jyear = db.Column(db.String(8))               # سال
    rehab_date = db.Column(db.Date, index=True)   # تاریخ بهسازی
    pumping_end_date = db.Column(db.Date)         # تاریخ اتمام پمپاژ

    rehab_contractor_id = db.Column(db.Integer, db.ForeignKey("suppliers.id"))
    pumping_contractor_id = db.Column(db.Integer, db.ForeignKey("suppliers.id"))
    rehab_contractor = db.relationship("Supplier", foreign_keys=[rehab_contractor_id])
    pumping_contractor = db.relationship("Supplier", foreign_keys=[pumping_contractor_id])

    pump_type_before = db.Column(db.String(60))
    discharge_before_lps = db.Column(db.Float)
    pump_type_after = db.Column(db.String(60))
    discharge_after_lps = db.Column(db.Float)
    discharge_change_lps = db.Column(db.Float)    # میزان تغییرات دبی (as recorded)

    reason = db.Column(db.String(120))            # علت بهسازی (شولات/…)
    method = db.Column(db.String(120))
    observed_fault = db.Column(db.Text)
    notes = db.Column(db.Text)
    source = db.Column(db.String(40), index=True)

    @property
    def discharge_gain(self):
        if self.discharge_before_lps is not None and self.discharge_after_lps is not None:
            return round(self.discharge_after_lps - self.discharge_before_lps, 2)
        return self.discharge_change_lps

    def __repr__(self):
        return f"<Rehabilitation well={self.well_id} {self.rehab_date} {self.status}>"



################################################################################
# FILE: relocation.py
################################################################################

"""Well relocation event (بخش جابه‌جایی).

A relocation links a well being retired to its successor and records the
candidacy assessment (final candidate / not / impossible) and the chosen
relocation type. On approval the successor's parent_well is set and the old
well's status becomes 'relocated', forming the well lineage (شجره‌نامه).
"""
from app.extensions import db
from app.models.mixins import AuditMixin, WorkflowMixin


class RelocationRecord(db.Model, AuditMixin, WorkflowMixin):
    __tablename__ = "relocations"

    id = db.Column(db.Integer, primary_key=True)
    well_id = db.Column(db.Integer, db.ForeignKey("wells.id"), nullable=False, index=True)
    well = db.relationship(
        "Well", foreign_keys=[well_id],
        backref=db.backref("relocations", cascade="all, delete-orphan"))

    # the successor well (may not exist yet)
    new_well_id = db.Column(db.Integer, db.ForeignKey("wells.id"), nullable=True)
    new_well = db.relationship("Well", foreign_keys=[new_well_id])

    decision_date = db.Column(db.Date, index=True)
    reason = db.Column(db.String(120))            # علت جابه‌جایی
    candidacy = db.Column(db.String(20))          # final|proposed|not_candidate|impossible
    reloc_type = db.Column(db.String(20))         # in_place|other_surplus|green_space|edu_admin
    location_note = db.Column(db.String(200))     # موقعیت چاه برای جابه‌جایی
    letter_no = db.Column(db.String(60))          # شماره نامه جابه‌جایی
    distance_m = db.Column(db.Float)

    notes = db.Column(db.Text)
    source = db.Column(db.String(40), index=True)

    def __repr__(self):
        return f"<RelocationRecord well={self.well_id} {self.candidacy} {self.status}>"



################################################################################
# FILE: videometry.py
################################################################################

"""Well videometry / چاه‌نگاری (downhole camera inspection).

Header report + per-depth findings. Video/PDF files live on disk; only a
reference is stored. Findings feed rehab/relocation decisions and prioritization.
"""
from app.extensions import db
from app.models.mixins import AuditMixin, WorkflowMixin


class Videometry(db.Model, AuditMixin, WorkflowMixin):
    __tablename__ = "videometry_logs"

    id = db.Column(db.Integer, primary_key=True)
    well_id = db.Column(db.Integer, db.ForeignKey("wells.id"), nullable=False, index=True)
    well = db.relationship("Well", backref=db.backref("videometry_logs", cascade="all, delete-orphan"))

    log_date = db.Column(db.Date, index=True)
    contractor_id = db.Column(db.Integer, db.ForeignKey("suppliers.id"))
    contractor = db.relationship("Supplier", foreign_keys=[contractor_id])
    equipment = db.Column(db.String(80))
    depth_from_m = db.Column(db.Float)
    depth_to_m = db.Column(db.Float)
    final_depth_m = db.Column(db.Float)
    water_level_m = db.Column(db.Float)
    video_file_ref = db.Column(db.String(255))    # path/name on disk (not the file)
    summary = db.Column(db.Text)
    source = db.Column(db.String(40), index=True)

    findings = db.relationship(
        "VideometryFinding", back_populates="log",
        cascade="all, delete-orphan", order_by="VideometryFinding.depth_m",
    )

    def __repr__(self):
        return f"<Videometry well={self.well_id} {self.log_date} {self.status}>"


class VideometryFinding(db.Model):
    __tablename__ = "videometry_findings"

    id = db.Column(db.Integer, primary_key=True)
    videometry_id = db.Column(db.Integer, db.ForeignKey("videometry_logs.id"), nullable=False, index=True)
    log = db.relationship("Videometry", back_populates="findings")

    depth_m = db.Column(db.Float)
    finding_type = db.Column(db.String(30))   # casing_rupture | screen_blockage | ...
    severity = db.Column(db.String(10))       # low | medium | high
    note = db.Column(db.String(255))

    def __repr__(self):
        return f"<VideometryFinding {self.finding_type}@{self.depth_m}>"



################################################################################
# FILE: water_level.py
################################################################################

"""Groundwater level monitoring (پایش تراز آب زیرزمینی / پیزومتری).

A time series of static (non-pumping) water-level measurements per well — the
core long-term aquifer-decline signal the hydrogeologist tracks. Static level is
recorded as depth-to-water (m): a larger value = a deeper water table = decline.
Seeded from existing flow-test / pump-test / drilling static levels and extended
by manual entries.
"""
from app.extensions import db
from app.models.mixins import AuditMixin


class WaterLevelLog(db.Model, AuditMixin):
    __tablename__ = "water_level_logs"
    __table_args__ = (
        db.UniqueConstraint("well_id", "measure_date", "source",
                            name="uq_waterlevel_well_date_source"),
    )

    id = db.Column(db.Integer, primary_key=True)
    well_id = db.Column(db.Integer, db.ForeignKey("wells.id"), nullable=False, index=True)
    well = db.relationship(
        "Well", backref=db.backref("water_levels", cascade="all, delete-orphan"))

    measure_date = db.Column(db.Date, index=True)
    static_level = db.Column(db.Float)          # عمق تا آب (m)
    is_pumping = db.Column(db.Boolean, default=False)
    method = db.Column(db.String(20))           # manual|flowtest|pumptest|drilling
    notes = db.Column(db.String(200))
    source = db.Column(db.String(40), index=True)  # NULL=manual; import:* = seeded

    def __repr__(self):
        return f"<WaterLevelLog well={self.well_id} {self.measure_date} {self.static_level}>"



################################################################################
# FILE: well.py
################################################################################

"""Well aggregate root + its changeable identifiers.

Coordinates are stored as plain numeric columns so the schema is portable to
SQLite for development. On PostgreSQL a PostGIS `geom` column + spatial index
are added by a Postgres-only migration (see docs/ARCHITECTURE.md sec.7).
"""
from app.extensions import db
from app.models.mixins import AuditMixin, TimestampMixin


class Well(db.Model, AuditMixin):
    __tablename__ = "wells"

    id = db.Column(db.Integer, primary_key=True)

    # The source's pm column is corrupted (one pm shared by many wells), so the
    # real identity is name + office. pm_code holds a CLEAN pm when available,
    # otherwise a deterministic synthetic key ("W-<hash>"). Real-vs-synthetic is
    # distinguishable via has_pm/display_pm.
    pm_code = db.Column(db.String(40), unique=True, nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    # Normalized name used as the identity match-key (with office).
    match_key = db.Column(db.String(120), index=True)

    # Organization / geography
    office_id = db.Column(db.Integer, db.ForeignKey("org_units.id"), nullable=True)
    center_id = db.Column(db.Integer, db.ForeignKey("org_units.id"), nullable=True)
    office = db.relationship("OrgUnit", foreign_keys=[office_id])
    center = db.relationship("OrgUnit", foreign_keys=[center_id])
    zone = db.Column(db.String(40))          # پهنه
    sub_zone = db.Column(db.String(40))      # زیرپهنه
    destination_reservoir = db.Column(db.String(40))  # مخزن مقصد (supply-zone link)
    well_kind = db.Column(db.String(10), default="urban")  # urban|rural
    construction_type = db.Column(db.String(20))  # limestone|cementation|normal (نوع چاه)

    # Location (UTM as recorded; lat/lon for mapping)
    utm_x = db.Column(db.Float)
    utm_y = db.Column(db.Float)
    utm_zone = db.Column(db.String(8), default="40N")
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    ground_elevation = db.Column(db.Float)

    # Lifecycle
    drill_year = db.Column(db.String(8))     # Jalali year as text (e.g. "1404")
    location_status = db.Column(db.String(20))  # pre_drilled|relocated_stage1|new
    status = db.Column(db.String(20), default="in_circuit", index=True)

    # Relocation chain: the well this one replaced.
    parent_well_id = db.Column(db.Integer, db.ForeignKey("wells.id"), nullable=True)
    parent_well = db.relationship("Well", remote_side=[id], backref="successors")

    notes = db.Column(db.Text)

    identifiers = db.relationship(
        "WellIdentifier", back_populates="well", cascade="all, delete-orphan"
    )

    @property
    def has_coords(self):
        return self.latitude is not None and self.longitude is not None

    @property
    def has_pm(self):
        """True only when pm_code is a real (clean) pm, not a synthetic key."""
        return bool(self.pm_code) and not self.pm_code.startswith(("W-", "K", "BW-"))

    @property
    def display_pm(self):
        return self.pm_code if self.has_pm else "—"

    def __repr__(self):
        return f"<Well {self.pm_code} {self.name}>"


class WellIdentifier(db.Model, TimestampMixin):
    """History of identifiers that change over a well's life (klasse, power sub.)."""

    __tablename__ = "well_identifiers"

    id = db.Column(db.Integer, primary_key=True)
    well_id = db.Column(db.Integer, db.ForeignKey("wells.id"), nullable=False)
    id_type = db.Column(db.String(30), nullable=False)  # klasse|power_subscription|name
    value = db.Column(db.String(80), nullable=False)
    valid_from = db.Column(db.String(12))
    valid_to = db.Column(db.String(12))

    well = db.relationship("Well", back_populates="identifiers")

    def __repr__(self):
        return f"<WellIdentifier {self.id_type}={self.value}>"



################################################################################
# FILE: well_technical.py
################################################################################

"""Per-well technical snapshot enriched from the Aid master (مشخصات فنی).

One row per well (1:1). Holds the latest flow-test snapshot, meter status, well
construction and identifiers that the Aid 'تولید ماهیانه' sheet carries but the
core well registry does not. Read-mostly reference data; refreshed by the
aid-technical importer.
"""
from app.extensions import db
from app.models.mixins import TimestampMixin


class WellTechnical(db.Model, TimestampMixin):
    __tablename__ = "well_technical"

    id = db.Column(db.Integer, primary_key=True)
    well_id = db.Column(db.Integer, db.ForeignKey("wells.id"), unique=True, nullable=False, index=True)
    well = db.relationship(
        "Well", backref=db.backref("technical", uselist=False, cascade="all, delete-orphan"))

    # latest flow-test snapshot
    last_flowtest_discharge = db.Column(db.Float)     # دبی آخرین دبی‌سنجی (فشار شبکه)
    last_flowtest_pressure = db.Column(db.Float)      # فشار شبکه در آخرین دبی‌سنجی
    last_flowtest_date = db.Column(db.Date)           # تاریخ آخرین دبی‌سنجی

    # meter
    meter_status = db.Column(db.String(40))           # وضعیت کنتور
    meter_brand = db.Column(db.String(60))            # برند کنتور

    # identifiers / location
    klasse = db.Column(db.String(40))                 # کلاسه چاه
    geo_position = db.Column(db.String(120))          # موقعیت جغرافیایی

    # construction
    casing_material = db.Column(db.String(40))        # جنس لوله جدار
    discharge_pipe_size = db.Column(db.String(20))    # سایز لوله آبده
    drill_depth_m = db.Column(db.Float)               # عمق حفاری چاه
    install_depth_m = db.Column(db.Float)             # عمق نصب
    prev_discharge_lps = db.Column(db.Float)          # دبی قبلی
    last_drill_year = db.Column(db.String(8))         # سال حفاری آخرین چاه

    source = db.Column(db.String(40), index=True)

    def __repr__(self):
        return f"<WellTechnical well={self.well_id}>"



################################################################################
# FILE: __init__.py
################################################################################

"""Local, recomputable predictive analytics (Phase 4).

All methods are transparent/explainable and use only numpy on the data already in
the DB, so they recompute on demand as new monthly data arrives (no external or
cloud model). This package is the integration point for a future local AI model.
"""



################################################################################
# FILE: anomaly.py
################################################################################

"""4.4 Anomaly detection on the monthly time series.

Robust (median + MAD) modified z-scores flag months whose production / discharge
deviate strongly from the well's own norm — sudden drops (failure) or spikes
(meter error). Recomputed on demand.
"""
import numpy as np

from app.extensions import db
from app.services.analytics.base import robust_z

Z_THRESHOLD = 3.5     # |modified z| above this = anomaly
MIN_POINTS = 8


def for_well(well_id):
    from app.models.production import MonthlyProduction as MP
    rows = db.session.scalars(
        db.select(MP).filter_by(well_id=well_id)
        .order_by(MP.jyear, MP.jmonth)).all()
    out = []
    for metric, attr in (("تولید", "production_m3"), ("دبی متوسط", "avg_discharge_lps")):
        series = [(f"{r.jyear}/{r.jmonth:02d}", getattr(r, attr)) for r in rows
                  if getattr(r, attr) is not None and getattr(r, attr) > 0]
        if len(series) < MIN_POINTS:
            continue
        vals = [s[1] for s in series]
        z = robust_z(vals)
        med = float(np.median(vals))
        for i, zi in enumerate(z):
            if abs(zi) >= Z_THRESHOLD:
                out.append({
                    "metric": metric, "period": series[i][0],
                    "value": round(vals[i], 1), "expected": round(med, 1),
                    "direction": "drop" if zi < 0 else "spike",
                    "z": round(float(zi), 1),
                })
    out.sort(key=lambda a: a["period"], reverse=True)
    return out


def recent_count(well_id):
    """Count anomalies in the two most recent periods present (quick signal)."""
    a = for_well(well_id)
    if not a:
        return 0
    periods = sorted({x["period"] for x in a}, reverse=True)[:2]
    return sum(1 for x in a if x["period"] in periods)



################################################################################
# FILE: base.py
################################################################################

"""Shared numeric helpers for the analytics package (local, numpy-only)."""
import numpy as np


def linfit(t, y):
    """Ordinary least-squares line y = slope*t + intercept, with R².

    Returns None if fewer than 2 points or zero time span.
    """
    t = np.asarray(t, dtype=float)
    y = np.asarray(y, dtype=float)
    if len(t) < 2 or np.ptp(t) == 0:
        return None
    slope, intercept = np.polyfit(t, y, 1)
    yhat = slope * t + intercept
    ss_res = float(np.sum((y - yhat) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r2 = (1 - ss_res / ss_tot) if ss_tot > 0 else 0.0
    return {"slope": float(slope), "intercept": float(intercept),
            "r2": round(max(r2, 0.0), 3), "n": len(t)}


def robust_z(values):
    """Modified z-scores using median + MAD (robust to outliers).

    Returns array aligned to `values`; 0 where MAD == 0.
    """
    v = np.asarray(values, dtype=float)
    med = np.median(v)
    mad = np.median(np.abs(v - med))
    if mad == 0:
        return np.zeros_like(v)
    return 0.6745 * (v - med) / mad



################################################################################
# FILE: energy_opt.py
################################################################################

"""4.5 Pump energy-efficiency optimization.

Compares the well's actual operating point to the selected pump's best-efficiency
point (BEP) from the catalog curve, quantifies how far off-BEP it runs, and
estimates the annual energy & cost that could be saved by moving it back toward
BEP (pump resize/trim). Uses the latest monthly energy as the basis.
"""
from app.extensions import db


def _latest_operating(well_id):
    """Most recent flow-test representative operating point (Q l/s, efficiency %)."""
    from app.models.flow import FlowTest
    tests = db.session.scalars(
        db.select(FlowTest).filter_by(well_id=well_id)
        .order_by(FlowTest.test_date.desc())).all()
    for t in tests:
        pts = [(p.discharge_lps, p.efficiency) for p in t.points if p.discharge_lps]
        if pts:
            q = max(p[0] for p in pts)
            effs = [(e * 100 if e <= 1 else e) for _q, e in pts if e]
            return q, (max(effs) if effs else None)
    return None, None


def for_well(well_id):
    from app.models.pump_select import PumpSelection
    from app.models.pump_catalog import PumpModel
    from app.models.pump_asset import PumpInstallation
    from app.models.production import MonthlyProduction as MP

    # selected/installed pump model -> BEP
    sel = db.session.scalar(
        db.select(PumpSelection).filter_by(well_id=well_id)
        .order_by(PumpSelection.form_delivery_date.desc()))
    model_name = sel.selected_pump_type if sel else None
    if not model_name:
        inst = db.session.scalar(
            db.select(PumpInstallation).filter_by(well_id=well_id)
            .order_by(PumpInstallation.install_date.desc()))
        model_name = inst.pump_type if inst else None
    if not model_name:
        return None
    pm = db.session.scalar(db.select(PumpModel).filter_by(model=model_name))
    if not pm:
        return None
    bep = next((p for p in pm.points if p.is_bep and p.flow_lps), None)
    if not bep:
        return None

    q_op, eff_op = _latest_operating(well_id)
    if q_op is None:
        return None
    bep_eff = (bep.efficiency_pct if bep.efficiency_pct
               and bep.efficiency_pct > 1 else (bep.efficiency_pct or 0) * 100)

    off_bep = round((q_op - bep.flow_lps) / bep.flow_lps * 100, 1) if bep.flow_lps else None

    # potential savings: operating efficiency vs BEP efficiency
    energy_row = db.session.scalar(
        db.select(MP).filter_by(well_id=well_id).where(MP.energy_kwh.isnot(None))
        .order_by(MP.jyear.desc(), MP.jmonth.desc()))
    saving_pct = annual_kwh = annual_rial = None
    if eff_op and bep_eff and eff_op < bep_eff:
        saving_pct = round((1 - eff_op / bep_eff) * 100, 1)
        if energy_row and energy_row.energy_kwh:
            annual_kwh = round(energy_row.energy_kwh * 12 * saving_pct / 100)
            if energy_row.energy_cost_rial:
                rate = energy_row.energy_cost_rial / energy_row.energy_kwh
                annual_rial = round(annual_kwh * rate)

    return {
        "model": pm.model, "motor_kw": pm.motor_power_kw,
        "bep_flow": round(bep.flow_lps, 1), "bep_eff": round(bep_eff, 1) if bep_eff else None,
        "op_flow": round(q_op, 1), "op_eff": round(eff_op, 1) if eff_op else None,
        "off_bep_pct": off_bep,
        "saving_pct": saving_pct,
        "annual_kwh_saving": annual_kwh, "annual_rial_saving": annual_rial,
    }



################################################################################
# FILE: forecast.py
################################################################################

"""4.1 Discharge-decline forecast + optimal rehab timing, and
   4.2 Aquifer water-level forecast.

Both fit a transparent linear trend (OLS) over the monthly time series and
project it forward. Recomputed on demand — improves as more data arrives.
"""
from datetime import date, timedelta

from app.extensions import db
from app.services.analytics.base import linfit

REHAB_FRACTION = 0.5      # rehab trigger = 50% of baseline discharge
MIN_POINTS = 6


def _monthly_discharge(well_id):
    """[(months_index, Q)] for running months (Q>0), chronological."""
    from app.models.production import MonthlyProduction as MP
    rows = db.session.scalars(
        db.select(MP).filter_by(well_id=well_id)
        .order_by(MP.jyear, MP.jmonth)).all()
    pts = [(r.jyear * 12 + (r.jmonth - 1), r.avg_discharge_lps)
           for r in rows if r.avg_discharge_lps and r.avg_discharge_lps > 0]
    return pts


def decline_forecast(well_id):
    """Trend of monthly average discharge + projected rehab date.

    Returns dict or None when insufficient data.
    """
    pts = _monthly_discharge(well_id)
    if len(pts) < MIN_POINTS:
        return None
    t = [p[0] for p in pts]
    y = [p[1] for p in pts]
    fit = linfit(t, y)
    if not fit:
        return None

    slope_yr = fit["slope"] * 12.0            # l/s per year
    t_now = t[-1]
    current_trend = fit["slope"] * t_now + fit["intercept"]
    proj_12 = fit["slope"] * (t_now + 12) + fit["intercept"]

    # rehab threshold from the dynamic baseline (fallback: peak observed)
    from app.models.baseline import WellBaseline
    b = db.session.scalar(
        db.select(WellBaseline).filter_by(well_id=well_id, is_current=True))
    ref = (b.baseline_discharge_lps if b and b.baseline_discharge_lps else max(y))
    threshold = ref * REHAB_FRACTION

    rehab_date, months_ahead, overdue = None, None, False
    declining = fit["slope"] < -1e-6
    if declining and current_trend <= threshold:
        overdue = True                         # already at/below 50% of baseline
    elif declining and current_trend > threshold:
        t_cross = (threshold - fit["intercept"]) / fit["slope"]
        months_ahead = int(round(t_cross - t_now))
        if 0 <= months_ahead <= 600:
            rehab_date = date.today() + timedelta(days=int(months_ahead * 30.44))

    return {
        "slope_per_year": round(slope_yr, 2),
        "current_trend": round(current_trend, 1),
        "projected_12m": round(max(proj_12, 0), 1),
        "threshold": round(threshold, 1),
        "ref_baseline": round(ref, 1),
        "months_to_rehab": months_ahead,
        "rehab_date": rehab_date,
        "overdue": overdue,
        "r2": fit["r2"], "n": fit["n"],
        "declining": declining,
    }


def aquifer_forecast(well_id):
    """Trend of static water level (depth-to-water) + projected depth."""
    from app.models.water_level import WaterLevelLog
    rows = db.session.scalars(
        db.select(WaterLevelLog).filter_by(well_id=well_id)
        .order_by(WaterLevelLog.measure_date)).all()
    pts = [(r.measure_date, r.static_level) for r in rows
           if r.measure_date and r.static_level is not None and not r.is_pumping]
    if len(pts) < 4:
        return None
    d0 = pts[0][0]
    t = [(p[0] - d0).days / 365.25 for p in pts]   # years since first
    y = [p[1] for p in pts]
    fit = linfit(t, y)
    if not fit or fit["n"] < 4:
        return None
    t_now = t[-1]
    return {
        "decline_rate": round(fit["slope"], 2),     # m/year (positive = deepening)
        "current_depth": round(fit["slope"] * t_now + fit["intercept"], 1),
        "projected_1y": round(fit["slope"] * (t_now + 1) + fit["intercept"], 1),
        "projected_3y": round(fit["slope"] * (t_now + 3) + fit["intercept"], 1),
        "r2": fit["r2"], "n": fit["n"],
        "declining": fit["slope"] > 1e-6,
        "span_years": round(t_now, 1),
    }



################################################################################
# FILE: risk.py
################################################################################

"""4.3 Pump failure-risk score (predictive maintenance).

A transparent, explainable weighted model (no black box) combining the signals
that precede a pump pull/burn: history of burnouts, low/declining efficiency,
steep discharge decline (hydraulic stress) and age. Returns a 0-100 score with
the per-factor breakdown so an engineer can see *why*.
"""
from app.extensions import db
from app.services.analytics.forecast import decline_forecast

WEIGHTS = {"burn": 0.35, "decline": 0.30, "efficiency": 0.20, "age": 0.15}
CURRENT_JYEAR = 1405


def _latest_efficiency(well_id):
    from app.models.flow import FlowTest
    tests = db.session.scalars(
        db.select(FlowTest).filter_by(well_id=well_id)
        .order_by(FlowTest.test_date.desc())).all()
    for t in tests:
        effs = [p.efficiency for p in t.points if p.efficiency]
        if effs:
            e = max(effs)
            return e * 100 if e <= 1 else e        # normalize to %
    return None


def for_well(well_id):
    from app.models.well import Well
    from app.models.pump_asset import PumpInstallation
    w = db.session.get(Well, well_id)
    if not w:
        return None

    installs = db.session.scalars(
        db.select(PumpInstallation).filter_by(well_id=well_id)).all()
    burns = sum(1 for i in installs if i.removal_reason and "سوخت" in i.removal_reason)

    eff = _latest_efficiency(well_id)
    fc = decline_forecast(well_id)
    decline_yr = abs(fc["slope_per_year"]) if (fc and fc["declining"]) else 0.0
    try:
        age = CURRENT_JYEAR - int(w.drill_year) if w.drill_year else 0
    except (TypeError, ValueError):
        age = 0

    # factor sub-scores in [0,1]
    f_burn = min(burns / 3.0, 1.0)                       # 3+ burns = max
    f_decl = min(decline_yr / 4.0, 1.0)                  # 4 l/s/yr = max
    f_eff = max(0.0, (55 - eff) / 55.0) if eff is not None else 0.0   # <55% degrades
    f_age = min(max(age, 0) / 30.0, 1.0)                 # 30 yr = max

    score = 100 * (WEIGHTS["burn"] * f_burn + WEIGHTS["decline"] * f_decl
                   + WEIGHTS["efficiency"] * f_eff + WEIGHTS["age"] * f_age)
    score = round(score, 1)
    level = "high" if score >= 50 else ("medium" if score >= 25 else "low")
    return {
        "score": score, "level": level,
        "factors": {
            "burn": {"value": burns, "contrib": round(100 * WEIGHTS["burn"] * f_burn, 1)},
            "decline": {"value": round(decline_yr, 2), "contrib": round(100 * WEIGHTS["decline"] * f_decl, 1)},
            "efficiency": {"value": round(eff, 1) if eff is not None else None,
                           "contrib": round(100 * WEIGHTS["efficiency"] * f_eff, 1)},
            "age": {"value": age, "contrib": round(100 * WEIGHTS["age"] * f_age, 1)},
        },
    }



################################################################################
# FILE: summary.py
################################################################################

"""Per-well aggregator + fleet roll-up for the analytics dashboard.

`well(well_id)` gathers all Phase-4 results for the well-detail page. `fleet()`
rolls them up for the analytics dashboard. Both recompute on demand from current
data — ready to plug a future local model behind the same interface.
"""
import time

from app.extensions import db
from app.services.analytics import forecast, risk, anomaly, energy_opt

# simple in-process TTL cache for the (heavy) fleet roll-up
_CACHE = {"at": 0.0, "data": None}
_TTL = 600   # 10 minutes; cleared automatically as new data ages it out


def well(well_id):
    return {
        "decline": forecast.decline_forecast(well_id),
        "aquifer": forecast.aquifer_forecast(well_id),
        "risk": risk.for_well(well_id),
        "anomalies": anomaly.for_well(well_id),
        "energy": energy_opt.for_well(well_id),
    }


def fleet(force=False):
    """Fleet roll-up (counts + top lists), cached for _TTL seconds."""
    now = time.time()
    if not force and _CACHE["data"] is not None and now - _CACHE["at"] < _TTL:
        return _CACHE["data"]
    data = _fleet_compute()
    _CACHE.update(at=now, data=data)
    return data


def _fleet_compute():
    from app.models.production import MonthlyProduction as MP
    from app.models.water_level import WaterLevelLog
    from app.models.well import Well

    prod_wells = list(db.session.scalars(db.select(MP.well_id.distinct())).all())
    wl_wells = list(db.session.scalars(db.select(WaterLevelLog.well_id.distinct())).all())
    names = {w.id: w.name for w in db.session.scalars(db.select(Well)).all()}

    rehab_now, decline_soon, rehab_due_list = 0, 0, []
    declining = 0
    for wid in prod_wells:
        fc = forecast.decline_forecast(wid)
        if not fc:
            continue
        if fc["declining"]:
            declining += 1
        if fc.get("overdue"):
            rehab_now += 1
            rehab_due_list.append({"id": wid, "name": names.get(wid, "—"),
                                   "slope": fc["slope_per_year"], "when": "اکنون"})
        elif fc.get("months_to_rehab") is not None and fc["months_to_rehab"] <= 24:
            decline_soon += 1
            rehab_due_list.append({"id": wid, "name": names.get(wid, "—"),
                                   "slope": fc["slope_per_year"],
                                   "when": f"{fc['months_to_rehab']} ماه"})

    aquifer_declining = sum(1 for wid in wl_wells
                            if (lambda a: a and a["declining"])(forecast.aquifer_forecast(wid)))

    # pump risk: high-risk wells (sample over production wells)
    high_risk = []
    for wid in prod_wells:
        rk = risk.for_well(wid)
        if rk and rk["level"] == "high":
            high_risk.append({"id": wid, "name": names.get(wid, "—"), "score": rk["score"]})
    high_risk.sort(key=lambda x: -x["score"])

    # energy savings opportunities
    savings = []
    for wid in prod_wells:
        eo = energy_opt.for_well(wid)
        if eo and eo.get("annual_kwh_saving"):
            savings.append({"id": wid, "name": names.get(wid, "—"),
                            "kwh": eo["annual_kwh_saving"], "rial": eo.get("annual_rial_saving"),
                            "off_bep": eo.get("off_bep_pct")})
    savings.sort(key=lambda x: -(x["kwh"] or 0))
    total_kwh_saving = sum(s["kwh"] or 0 for s in savings)
    total_rial_saving = sum(s["rial"] or 0 for s in savings)

    rehab_due_list.sort(key=lambda x: x["slope"])
    return {
        "declining": declining, "rehab_now": rehab_now, "decline_soon": decline_soon,
        "rehab_due": rehab_due_list[:15],
        "aquifer_declining": aquifer_declining, "aquifer_total": len(wl_wells),
        "high_risk": high_risk[:15], "high_risk_count": len(high_risk),
        "savings": savings[:15], "savings_count": len(savings),
        "total_kwh_saving": total_kwh_saving, "total_rial_saving": total_rial_saving,
    }



################################################################################
# FILE: __init__.py
################################################################################




################################################################################
# FILE: alerts.py
################################################################################

"""Fleet alert engine.

Derives actionable alerts from existing data (no new inputs): performance
decline, low energy efficiency, water-quality flags, faulty meters, and final
relocation candidates. Each alert carries a severity, category, the well and a
link. Used by the /alerts page and the dashboard attention panel.
"""
from app.extensions import db

# category -> (label, icon, css color class fragment)
CATEGORIES = {
    "decline":   ("افت شدید دبی", "bi-graph-down-arrow", "danger"),
    "quality":   ("مشکل کیفی آب", "bi-droplet", "danger"),
    "energy":    ("انرژی ویژه‌ی بالا", "bi-lightning-charge", "warning"),
    "meter":     ("کنتور خراب/معیوب", "bi-bezier2", "warning"),
    "relocation": ("نامزد نهایی جابه‌جایی", "bi-signpost-2", "info"),
    "rehab_due": ("بهسازی فوری (پیش‌بینی)", "bi-tools", "danger"),
    "pump_risk": ("ریسک بالای خرابی پمپ", "bi-exclamation-octagon", "warning"),
    "saving":    ("فرصت صرفه‌جویی انرژی", "bi-piggy-bank", "info"),
}
SEV_ORDER = {"high": 0, "medium": 1, "low": 2}

# thresholds
DECLINE_PCT = 50.0
SPEC_ENERGY = 1.5


def compute(include_predictive=True):
    from app.services import prioritization
    from app.models.well_technical import WellTechnical
    from app.models.relocation import RelocationRecord
    from app.models.well import Well

    alerts = []

    def add(sev, cat, well, msg):
        alerts.append({
            "severity": sev, "category": cat, "cat_label": CATEGORIES[cat][0],
            "icon": CATEGORIES[cat][1], "color": CATEGORIES[cat][2],
            "well_id": well.id, "well": well.name,
            "office": well.office.name if well.office else "",
            "message": msg,
        })

    for r in prioritization._metrics():
        w, m = r["well"], r["metrics"]
        if m["discharge_decline"] >= DECLINE_PCT:
            add("high", "decline", w, f"افت دبی {m['discharge_decline']:.0f}٪ نسبت به اوج عملکرد")
        se = m.get("specific_energy")
        if se and se >= SPEC_ENERGY:
            add("medium", "energy", w, f"انرژی ویژه {se} kWh/m³ (بالاتر از حد کارایی)")
        q = m["quality_flag"]
        if q >= 1.6:
            add("high", "quality", w, "گزارش غیرقابل‌شرب بودن (اخیر)")
        elif q >= 0.8:
            add("medium", "quality", w, "گزارش کدورت/شولات")

    # faulty meters
    for t in db.session.scalars(
            db.select(WellTechnical).where(WellTechnical.meter_status.isnot(None))).all():
        if t.meter_status and t.meter_status.strip() not in ("سالم", "سالم "):
            add("low", "meter", t.well, f"وضعیت کنتور: {t.meter_status}")

    # final relocation candidates
    for rec in db.session.scalars(
            db.select(RelocationRecord).filter_by(candidacy="final")).all():
        add("medium", "relocation", rec.well, "کاندید نهایی جابه‌جایی")

    # predictive signals (Phase 4): rehab-overdue, high pump risk, large energy saving.
    # Heavy (fleet model) — skipped for the dashboard quick count.
    if not include_predictive:
        alerts.sort(key=lambda a: (SEV_ORDER[a["severity"]], a["category"]))
        return alerts
    from app.services.analytics import summary as analytics
    wells = {w.id: w for w in db.session.scalars(db.select(Well)).all()}
    fl = analytics.fleet()
    for r in fl["rehab_due"]:
        if r["when"] == "اکنون" and r["id"] in wells:
            add("high", "rehab_due", wells[r["id"]],
                f"روند افت {r['slope']} l/s در سال — بهسازی فوری")
    for r in fl["high_risk"]:
        if r["id"] in wells:
            add("medium", "pump_risk", wells[r["id"]], f"امتیاز ریسک خرابی پمپ: {r['score']}")
    for s in fl["savings"]:
        if s["id"] in wells and (s["kwh"] or 0) >= 30000:
            add("low", "saving", wells[s["id"]],
                f"صرفه‌جویی بالقوه {s['kwh']:,} kWh/سال (انحراف {s['off_bep']}٪ از BEP)")

    alerts.sort(key=lambda a: (SEV_ORDER[a["severity"]], a["category"]))
    return alerts


def summary(alerts=None, include_predictive=True):
    alerts = compute(include_predictive=include_predictive) if alerts is None else alerts
    by_sev = {"high": 0, "medium": 0, "low": 0}
    by_cat = {}
    for a in alerts:
        by_sev[a["severity"]] += 1
        by_cat[a["category"]] = by_cat.get(a["category"], 0) + 1
    return {"total": len(alerts), "by_severity": by_sev, "by_category": by_cat}



################################################################################
# FILE: baseline.py
################################################################################

"""Compute the dynamic per-well performance baseline.

Anchor = the most recent STRUCTURAL event (drilling end / rehabilitation) — events
that change the WELL (a new pump does NOT reset well capacity). The baseline is the
best performance observed AFTER that anchor (current configuration), so decline is
measured fairly (a rehab resets the reference). Falls back to the pump-test proposed
discharge ('design') when no post-anchor flow data exists. Full recompute.
"""
from collections import defaultdict

from app.extensions import db


def _rep(ft):
    """Representative (discharge_lps, dynamic_level) for a flow test = the point
    with the highest discharge."""
    best = None
    for p in ft.points:
        if p.discharge_lps is None:
            continue
        if best is None or p.discharge_lps > best.discharge_lps:
            best = p
    if best is None:
        return None, None
    return best.discharge_lps, best.dynamic_level_m


def run(dry_run=False):
    from app.models.well import Well
    from app.models.drilling import Drilling
    from app.models.rehab import Rehabilitation
    from app.models.flow import FlowTest
    from app.models.pump_test import PumpTest
    from app.models.baseline import WellBaseline

    stats = {"wells": 0, "from_flow": 0, "from_design": 0, "no_data": 0}

    db.session.query(WellBaseline).delete()
    db.session.flush()

    # structural anchors
    drill_anchor = {}
    for d in db.session.scalars(db.select(Drilling)).all():
        dt = d.end_date or d.start_date
        if dt and (d.well_id not in drill_anchor or dt > drill_anchor[d.well_id]):
            drill_anchor[d.well_id] = dt
    rehab_anchor = {}
    for r in db.session.scalars(db.select(Rehabilitation)).all():
        if r.rehab_date and (r.well_id not in rehab_anchor or r.rehab_date > rehab_anchor[r.well_id]):
            rehab_anchor[r.well_id] = r.rehab_date

    flows = defaultdict(list)
    for ft in db.session.scalars(db.select(FlowTest)).all():
        if ft.test_date:
            flows[ft.well_id].append(ft)

    design_q = {}
    for pt in db.session.scalars(db.select(PumpTest)).all():
        q = pt.proposed_discharge_lps or pt.max_yield_lps
        if q and pt.well_id not in design_q:
            design_q[pt.well_id] = q

    for well in db.session.scalars(db.select(Well)).all():
        da, ra = drill_anchor.get(well.id), rehab_anchor.get(well.id)
        anchor_date, anchor_type = None, "initial"
        if ra and (not da or ra >= da):
            anchor_date, anchor_type = ra, "rehab"
        elif da:
            anchor_date, anchor_type = da, "drilling"

        wf = sorted(flows.get(well.id, []), key=lambda x: x.test_date)
        post = [ft for ft in wf if anchor_date is None or ft.test_date >= anchor_date]
        # if anchor wipes out all flow data, fall back to all flow
        candidates = post or wf

        best = None  # (discharge, dynamic, static, date)
        for ft in candidates:
            q, dyn = _rep(ft)
            if q is None:
                continue
            if best is None or q > best[0]:
                best = (q, dyn, ft.static_level, ft.test_date)

        bl = WellBaseline(well_id=well.id, anchor_event_type=anchor_type,
                          anchor_date=anchor_date, is_current=True, source="computed")
        if best:
            q, dyn, static, bdate = best
            sc = None
            if dyn is not None and static is not None and (dyn - static) > 0:
                sc = round(q / (dyn - static), 3)
            bl.baseline_kind = "best_observed"
            bl.baseline_discharge_lps = q
            bl.baseline_dynamic_level = dyn
            bl.baseline_specific_capacity = sc
            bl.baseline_date = bdate
            stats["from_flow"] += 1
        elif design_q.get(well.id):
            bl.baseline_kind = "design"
            bl.baseline_discharge_lps = design_q[well.id]
            stats["from_design"] += 1
        else:
            stats["no_data"] += 1
            continue  # nothing to baseline
        db.session.add(bl)
        stats["wells"] += 1

    if dry_run:
        db.session.rollback()
    else:
        db.session.commit()
    return stats



################################################################################
# FILE: catalog.py
################################################################################

"""Build the pump-catalog 'library' (same shape the selector algorithm expects)
and design-parameter prefill from a well's operational data.
"""
from app.extensions import db


def build_library():
    from app.models.pump_catalog import PumpModel

    lib = []
    for m in db.session.scalars(db.select(PumpModel)).all():
        pts = []
        for p in m.points:
            if p.flow_m3h is None or p.head_m is None:
                continue
            pts.append({
                "flow": p.flow_m3h,
                "flow_Ls": p.flow_lps if p.flow_lps is not None else (p.flow_m3h / 3.6),
                "head": p.head_m,
                "eff": (p.efficiency_pct or 0) / 100.0,
                "bep": bool(p.is_bep), "sb": bool(p.is_beb_start), "eb": bool(p.is_beb_end),
            })
        if not pts:
            continue
        pts.sort(key=lambda x: x["flow"])
        bep = next((p for p in pts if p["bep"]), None) or max(pts, key=lambda p: p["eff"])
        start = next((p for p in pts if p["sb"]), None) or bep
        end = next((p for p in pts if p["eb"]), None) or bep
        flows = [p["flow"] for p in pts]
        flows_ls = [p["flow_Ls"] for p in pts]
        lib.append({
            "model": m.model, "type": m.ptype or "", "titleElectro": m.title_electro or "",
            "stages": m.stages or 0, "motorPower": m.motor_power_kw or 0,
            "npsh": m.npsh or 0, "current": m.nominal_current or 0,
            "length": m.length_mm or 0, "weight": m.weight_kg or 0,
            "points": [{"flow": p["flow"], "flow_Ls": p["flow_Ls"], "head": p["head"], "eff": p["eff"]} for p in pts],
            "bep": {"flow": bep["flow"], "flow_Ls": bep["flow_Ls"], "head": bep["head"], "eff": bep["eff"]},
            "startBEBPoint": {"flow": start["flow"], "flow_Ls": start["flow_Ls"], "head": start["head"], "eff": start["eff"]},
            "endBEBPoint": {"flow": end["flow"], "flow_Ls": end["flow_Ls"], "head": end["head"], "eff": end["eff"]},
            "recFlowMin": min(flows), "recFlowMax": max(flows),
            "recFlowMin_Ls": min(flows_ls), "recFlowMax_Ls": max(flows_ls),
        })
    return lib


def design_params(well):
    """Suggested design Q (L/s) and TDH (m), sourced primarily from the pump
    test (دبی مجاز پیشنهادی + سطح دینامیک), then drilling (which carries the
    pump-test results from Borwells), then the latest flow test. Returns
    (q, head, source) where source documents provenance for the UI.
    """
    from app.models.pump_test import PumpTest
    from app.models.drilling import Drilling
    from app.models.flow import FlowTest

    q = dynamic = static = None
    src = {"basis": None, "date": None, "q": None, "static": None,
           "dynamic": None, "network_head": None}

    pt = db.session.scalar(
        db.select(PumpTest).filter_by(well_id=well.id)
        .order_by(PumpTest.test_date.desc().nullslast())
    )
    if pt and (pt.proposed_discharge_lps or pt.max_yield_lps):
        q = pt.proposed_discharge_lps or pt.max_yield_lps
        dynamic = pt.max_dynamic_level
        static = pt.static_level
        src.update(basis="آزمایش پمپاژ", date=pt.test_date)

    if q is None:
        dr = db.session.scalar(
            db.select(Drilling).filter_by(well_id=well.id)
            .where(Drilling.proposed_discharge_lps.isnot(None))
            .order_by(Drilling.end_date.desc().nullslast())
        )
        if dr:
            q = dr.proposed_discharge_lps
            dynamic = dr.dynamic_at_proposed
            static = dr.static_level
            src.update(basis="حفاری / آزمایش پمپاژ", date=dr.end_date)

    # surface/network head from the latest flow test line pressure (bar -> m)
    net = None
    lf = db.session.scalar(
        db.select(FlowTest).filter_by(well_id=well.id)
        .where(FlowTest.line_pressure.isnot(None)).order_by(FlowTest.test_date.desc())
    )
    if lf and lf.line_pressure:
        net = round(lf.line_pressure * 10.2)

    head = None
    if dynamic:
        head = dynamic + (net or 0)

    # last-resort fallback: operating head from the latest flow test
    if q is None or head is None:
        latest = db.session.scalar(
            db.select(FlowTest).filter_by(well_id=well.id)
            .where(FlowTest.test_date.isnot(None)).order_by(FlowTest.test_date.desc())
        )
        if latest:
            qs = [p.discharge_lps for p in latest.points if p.discharge_lps]
            hs = [p.head_m for p in latest.points if p.head_m]
            if q is None:
                q = max(qs) if qs else latest.allowed_q
            if head is None:
                head = max(hs) if hs else None
            if src["basis"] is None:
                src.update(basis="دبی‌سنجی", date=latest.test_date)

    src.update(q=round(q, 1) if q else None, static=static, dynamic=dynamic, network_head=net)
    return round(q, 1) if q else 10.0, round(head) if head else 180, src



################################################################################
# FILE: data_export.py
################################################################################

"""Build DataFrames for the data-export / review section.

Centralizes the heavy queries and the duplicate-grouping heuristic so the export
routes stay thin. The `dup_group` key normalizes a name and strips trailing
qualifier tokens (ق / قدیم / جدید / BOT / parentheticals) while KEEPING digits,
so variants of the same physical well (e.g. «ابوطالب 1 ق» and «ابوطالب 1») share
a key and sort together for review.
"""
import re
from collections import defaultdict

import pandas as pd

from app.extensions import db
from app.utils.dates import to_english_digits

_QUALIFIERS = {"ق", "قدیم", "جدید", "جد", "بوت", "bot", "ج", "جديد", "قديم"}


def dup_group(name):
    s = to_english_digits("" if name is None else str(name))
    s = s.replace("ي", "ی").replace("ك", "ک")
    s = re.sub(r"\(.*?\)", " ", s)                 # drop parentheticals
    s = re.sub(r"[‌‎‏]", " ", s)    # zwnj/marks -> space
    toks = [t for t in s.split() if t]
    while toks and toks[-1].strip().lower() in _QUALIFIERS:
        toks.pop()
    s = "".join(toks)
    s = (s.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
           .replace("ة", "ه").replace("ؤ", "و"))
    return s.lower()


def _counts():
    from app.models.production import MonthlyProduction as MP
    from app.models.flow import FlowTest
    from app.models.pump_asset import PumpInstallation
    prod = dict(db.session.execute(
        db.select(MP.well_id, db.func.count(MP.id)).group_by(MP.well_id)).all())
    flow = dict(db.session.execute(
        db.select(FlowTest.well_id, db.func.count(FlowTest.id)).group_by(FlowTest.well_id)).all())
    inst = dict(db.session.execute(
        db.select(PumpInstallation.well_id, db.func.count(PumpInstallation.id))
        .group_by(PumpInstallation.well_id)).all())
    return prod, flow, inst


def _legacy_map():
    from app.models.well import WellIdentifier
    names, pms = defaultdict(list), defaultdict(list)
    for wi in db.session.scalars(
            db.select(WellIdentifier).where(WellIdentifier.id_type.in_(["name", "pm_legacy"]))).all():
        (names if wi.id_type == "name" else pms)[wi.well_id].append(wi.value)
    return names, pms


def wells_df():
    """All wells, enriched with data-presence + duplicate-group columns."""
    from app.models.well import Well
    from app.models.constants import WELL_KINDS, WELL_STATUSES
    kind_l, status_l = dict(WELL_KINDS), dict(WELL_STATUSES)
    prod, flow, inst = _counts()
    leg_names, leg_pms = _legacy_map()

    wells = db.session.scalars(db.select(Well)).all()
    group_size = defaultdict(int)
    for w in wells:
        group_size[dup_group(w.name)] += 1

    rows = []
    for w in wells:
        g = dup_group(w.name)
        rows.append({
            "id": w.id,
            "نام چاه": w.name,
            "گروه تکراری": g,
            "تعداد در گروه": group_size[g],
            "کد PM": w.pm_code,
            "PM مصنوعی؟": "بله" if not w.has_pm else "خیر",
            "اداره": w.office.name if w.office else "",
            "مرکز": w.center.name if w.center else "",
            "نوع": kind_l.get(w.well_kind, w.well_kind),
            "وضعیت": status_l.get(w.status, w.status),
            "پهنه": w.zone or "",
            "سال حفر": w.drill_year or "",
            "رقوم ارتفاعی": w.ground_elevation,
            "مختصات دارد؟": "بله" if w.has_coords else "خیر",
            "ماه‌های تولید": prod.get(w.id, 0),
            "آزمایش پمپاژ/دبی": flow.get(w.id, 0),
            "نصب/کشیدن": inst.get(w.id, 0),
            "مجموع داده": prod.get(w.id, 0) + flow.get(w.id, 0) + inst.get(w.id, 0),
            "نام‌های قبلی": "، ".join(leg_names.get(w.id, [])),
            "PM قبلی": "، ".join(leg_pms.get(w.id, [])),
        })
    df = pd.DataFrame(rows)
    return df.sort_values(["گروه تکراری", "نام چاه"], kind="stable").reset_index(drop=True)


def duplicates_df():
    """Only wells whose duplicate-group has more than one member."""
    df = wells_df()
    dup = df[df["تعداد در گروه"] > 1].copy()
    return dup.sort_values(["تعداد در گروه", "گروه تکراری", "مجموع داده"],
                           ascending=[False, True, False], kind="stable").reset_index(drop=True)


def production_df():
    from app.models.production import MonthlyProduction as MP
    from app.models.well import Well
    name = {w.id: w.name for w in db.session.scalars(db.select(Well)).all()}
    rows = []
    for mp in db.session.scalars(
            db.select(MP).order_by(MP.well_id, MP.jyear, MP.jmonth)).all():
        rows.append({
            "well_id": mp.well_id, "نام چاه": name.get(mp.well_id, ""),
            "سال": mp.jyear, "ماه": mp.jmonth,
            "تولید (m³)": mp.production_m3, "کارکرد (ساعت)": mp.run_hours,
            "دبی متوسط (l/s)": mp.avg_discharge_lps, "فشار": mp.well_pressure,
            "منبع": mp.source,
        })
    return pd.DataFrame(rows)



################################################################################
# FILE: economics.py
################################################################################

"""Economic-parameter access + NPV helpers for the decision-support tools."""
from app.extensions import db
from app.models.economic import EconomicParam, DEFAULT_PARAMS


def ensure_params():
    """Seed any missing parameters; derive the electricity tariff from real data."""
    existing = {p.key for p in db.session.scalars(db.select(EconomicParam)).all()}
    added = False
    for key, label, default, unit in DEFAULT_PARAMS:
        if key in existing:
            continue
        if key == "electricity_tariff":
            default = _derived_tariff() or default
        db.session.add(EconomicParam(key=key, label=label, value=default, unit=unit))
        added = True
    if added:
        db.session.commit()


def _derived_tariff():
    from app.models.production import MonthlyProduction as MP
    rows = db.session.scalars(
        db.select(MP).where(MP.energy_kwh.isnot(None), MP.energy_cost_rial.isnot(None))).all()
    kwh = sum(r.energy_kwh for r in rows if r.energy_kwh)
    cost = sum(r.energy_cost_rial for r in rows if r.energy_cost_rial)
    return round(cost / kwh, 1) if kwh else None


def params():
    ensure_params()
    return {p.key: p.value for p in db.session.scalars(db.select(EconomicParam)).all()}


def get(key, default=0.0):
    p = db.session.scalar(db.select(EconomicParam).filter_by(key=key))
    return p.value if p else default


def npv(annual_cashflow, years, rate_pct):
    """Net present value of a constant annual cashflow (rate in %)."""
    r = rate_pct / 100.0
    return sum(annual_cashflow / ((1 + r) ** y) for y in range(1, int(years) + 1))


def payback_years(investment, annual_saving):
    if not annual_saving or annual_saving <= 0:
        return None
    return round(investment / annual_saving, 1)



################################################################################
# FILE: energy_stats.py
################################################################################

"""Fleet energy analytics for the energy dashboard.

Aggregates the electricity data held in monthly_production (period with
energy_kwh set) into fleet KPIs, per-office efficiency, a specific-energy
distribution, top consumers, least-efficient wells, and power-utilization
(demand-factor) signals. Read-only.
"""
from collections import defaultdict

from app.extensions import db

# specific-energy histogram edges (kWh/m³)
SE_BINS = [(0, 0.5), (0.5, 1.0), (1.0, 1.5), (1.5, 2.0), (2.0, 3.0), (3.0, 999)]
SE_LABELS = ["<0.5", "0.5–1", "1–1.5", "1.5–2", "2–3", ">3"]
MIN_M3 = 500   # ignore tiny-production months when ranking efficiency


def compute():
    from app.models.production import MonthlyProduction as MP
    from app.models.well import Well
    from app.models.org import OrgUnit

    rows = db.session.scalars(db.select(MP).where(MP.energy_kwh.isnot(None))).all()
    wells = {w.id: w for w in db.session.scalars(db.select(Well)).all()}
    offices = {o.id: o.name for o in db.session.scalars(db.select(OrgUnit)).all()}

    if not rows:
        return None

    period = max(rows, key=lambda r: (r.jyear, r.jmonth))
    period_label = f"{period.jyear}/{period.jmonth:02d}"

    tot_kwh = sum(r.energy_kwh or 0 for r in rows)
    tot_cost = sum(r.energy_cost_rial or 0 for r in rows)
    tot_m3 = sum(r.production_m3 or 0 for r in rows if r.production_m3)
    fleet_se = round(tot_kwh / tot_m3, 3) if tot_m3 else None

    # per-office
    off = defaultdict(lambda: {"n": 0, "kwh": 0.0, "m3": 0.0})
    for r in rows:
        w = wells.get(r.well_id)
        oid = w.office_id if w else None
        a = off[oid]
        a["n"] += 1
        a["kwh"] += r.energy_kwh or 0
        if r.production_m3:
            a["m3"] += r.production_m3
    by_office = sorted([
        {"name": offices.get(oid, "نامشخص"), "n": a["n"], "kwh": round(a["kwh"]),
         "se": round(a["kwh"] / a["m3"], 2) if a["m3"] else None}
        for oid, a in off.items()], key=lambda x: -x["kwh"])

    # specific-energy distribution
    se_vals = [(r, r.specific_energy) for r in rows if r.specific_energy is not None]
    hist = [0] * len(SE_BINS)
    for _r, se in se_vals:
        for i, (lo, hi) in enumerate(SE_BINS):
            if lo <= se < hi:
                hist[i] += 1
                break

    def row_dto(r):
        w = wells.get(r.well_id)
        return {"id": r.well_id, "name": w.name if w else "—",
                "office": offices.get(w.office_id) if w else "",
                "kwh": round(r.energy_kwh) if r.energy_kwh else 0,
                "m3": round(r.production_m3) if r.production_m3 else None,
                "se": r.specific_energy, "cost": round(r.energy_cost_rial) if r.energy_cost_rial else None,
                "demand": (round(r.consumed_power_kw / r.contract_power_kw, 2)
                           if r.consumed_power_kw and r.contract_power_kw else None)}

    top_consumers = [row_dto(r) for r in sorted(rows, key=lambda r: -(r.energy_kwh or 0))[:12]]
    inefficient = [row_dto(r) for r in sorted(
        [r for r in rows if r.specific_energy is not None and (r.production_m3 or 0) >= MIN_M3],
        key=lambda r: -(r.specific_energy or 0))[:12]]

    # power utilization (demand factor)
    demand = [r.consumed_power_kw / r.contract_power_kw for r in rows
              if r.consumed_power_kw and r.contract_power_kw and r.contract_power_kw > 0]
    avg_demand = round(sum(demand) / len(demand), 2) if demand else None
    over_contracted = sum(1 for d in demand if d < 0.5)   # paying for unused capacity
    exceeding = sum(1 for d in demand if d > 1.0)          # exceeding contract power

    return {
        "period": period_label, "n_wells": len(rows),
        "tot_kwh": round(tot_kwh), "tot_cost": round(tot_cost), "tot_m3": round(tot_m3),
        "fleet_se": fleet_se,
        "by_office": by_office,
        "hist_labels": SE_LABELS, "hist": hist,
        "top_consumers": top_consumers, "inefficient": inefficient,
        "avg_demand": avg_demand, "over_contracted": over_contracted, "exceeding": exceeding,
    }



################################################################################
# FILE: optimize.py
################################################################################

"""6.1 Rehab portfolio optimizer.

Picks the set of wells to rehabilitate that maximizes total recovered discharge
under a budget. Recovered discharge per well = baseline × decline-fraction (the
flow lost to clogging/decline that rehab is expected to restore). With a uniform
per-well rehab cost this is a greedy take-highest-benefit-until-budget (optimal
for equal weights); the benefit/cost ratio keeps it valid if costs vary later.
"""
from app.extensions import db

MIN_DECLINE = 20.0      # only wells declined >= 20% are rehab candidates


def rehab_candidates():
    from app.models.baseline import WellBaseline
    from app.models.well import Well
    from app.services import prioritization

    data = prioritization._metric_data()      # cached
    baselines = {b.well_id: b.baseline_discharge_lps
                 for b in db.session.scalars(
                     db.select(WellBaseline).filter_by(is_current=True)).all()
                 if b.baseline_discharge_lps}
    wells = {w.id: w for w in db.session.scalars(db.select(Well)).all()}

    cands = []
    for wid, m in data.items():
        dec = m.get("discharge_decline", 0.0)
        bl = baselines.get(wid)
        if not bl or dec < MIN_DECLINE:
            continue
        w = wells.get(wid)
        if not w:
            continue
        recovered = round(bl * dec / 100.0, 1)
        cands.append({
            "id": wid, "name": w.name,
            "office": w.office.name if w.office else "",
            "decline": round(dec, 1), "baseline": round(bl, 1),
            "recovered": recovered,
            "lat": w.latitude, "lon": w.longitude,
        })
    cands.sort(key=lambda c: -c["recovered"])
    return cands


def portfolio(budget_rial):
    from app.services import economics
    cost = economics.get("rehab_cost", 2e9)
    cands = rehab_candidates()

    selected, spent, cum, curve = [], 0.0, 0.0, []
    for c in cands:
        if cost <= 0 or spent + cost > budget_rial:
            continue
        spent += cost
        cum += c["recovered"]
        sel = dict(c); sel["cumulative"] = round(cum, 1)
        selected.append(sel)
        curve.append({"spent_b": round(spent / 1e9, 1), "recovered": round(cum, 1)})

    total_possible = round(sum(c["recovered"] for c in cands), 1)
    return {
        "selected": selected, "count": len(selected),
        "total_recovered": round(cum, 1), "spent": spent,
        "unit_cost": cost, "curve": curve,
        "candidates": len(cands), "total_possible": total_possible,
    }


def _field_wells(group_attr, key):
    """Wells in a zone/reservoir with capacity (latest discharge) + specific energy."""
    from app.models.well import Well
    from app.models.production import MonthlyProduction as MP

    disc, spec = {}, {}
    for mp in db.session.scalars(
            db.select(MP).where(MP.avg_discharge_lps.isnot(None))
            .order_by(MP.jyear, MP.jmonth)).all():
        if mp.avg_discharge_lps and mp.avg_discharge_lps > 0:
            disc[mp.well_id] = mp.avg_discharge_lps          # last wins
        if mp.specific_energy is not None:
            spec[mp.well_id] = mp.specific_energy

    out = []
    for w in db.session.scalars(
            db.select(Well).filter_by(**{group_attr: key})).all():
        cap = disc.get(w.id)
        se = spec.get(w.id)
        if cap is None or se is None:
            continue
        out.append({"id": w.id, "name": w.name, "capacity": round(cap, 1),
                    "se": se, "status": w.status,
                    "kwh_per_s": round(se * cap * 3.6, 1)})   # kWh per second of run = se×(m³/h)
    return out


def field_dispatch(group_attr, key, demand_lps):
    """Merit-order dispatch: meet demand with the lowest-specific-energy wells first."""
    wells = sorted(_field_wells(group_attr, key), key=lambda w: w["se"])
    selected, cum = [], 0.0
    for w in wells:
        if cum >= demand_lps:
            break
        selected.append(w)
        cum += w["capacity"]
    # energy cost rate comparison (kWh per m³ pumped, capacity-weighted)
    def se_weighted(ws):
        cap = sum(w["capacity"] for w in ws)
        return round(sum(w["se"] * w["capacity"] for w in ws) / cap, 3) if cap else None
    return {
        "wells": wells, "selected_ids": {w["id"] for w in selected},
        "selected": selected, "selected_capacity": round(cum, 1),
        "demand": demand_lps, "met": cum >= demand_lps,
        "se_selected": se_weighted(selected), "se_all": se_weighted(wells),
        "total_capacity": round(sum(w["capacity"] for w in wells), 1),
        "n_total": len(wells),
    }



################################################################################
# FILE: prioritization.py
################################################################################

"""Well prioritization scoring engine.

Computes per-well metrics from operational data, normalizes them across the
fleet (min-max), applies the configurable weighted criteria, and ranks wells
(highest score = highest priority for rehab/relocation). Preliminary baseline =
the well's own best observed discharge (per-well, self-correcting) until the
dynamic well_baselines reset-on-structural-event is wired in.
"""
from collections import defaultdict
from datetime import date, timedelta

from app.extensions import db

CURRENT_JYEAR = 1405
QUALITY_RECENT_DAYS = 1100   # ~3 years

# TTL cache for the heavy per-well metric aggregation (shared by report/dashboard/alerts)
_MCACHE = {"at": 0.0, "data": None}
_MTTL = 300   # 5 minutes


def _yearly_means(series, min_months=3):
    """series: {jyear: [q>0,...]} -> {jyear: mean}.

    Years with fewer than `min_months` running months are dropped so a thin
    partial year (e.g. the current year mid-way) can't skew the comparison.
    """
    return {y: sum(v) / len(v) for y, v in series.items() if len(v) >= min_months}


def _monthly_decline(yearly):
    """Decline% of latest annual mean discharge vs peak annual mean.

    Uses annual averages (only running months, Q>0) to stay robust against the
    monthly noise and pump-off months in the production time-series.
    """
    if len(yearly) < 1:
        return None, None, None
    ref = max(yearly.values())                       # peak performance year
    latest = yearly[max(yearly)]                     # most recent year
    if not ref or ref <= 0:
        return None, ref, latest
    return max((ref - latest) / ref * 100, 0.0), ref, latest


def _metric_data(force=False):
    """Per-well metric dict {well_id: metrics} — cached (no ORM objects, so it's
    safe to reuse across requests/sessions). The heavy aggregation lives here."""
    import time
    now = time.time()
    if not force and _MCACHE["data"] is not None and now - _MCACHE["at"] < _MTTL:
        return _MCACHE["data"]
    data = _compute_metric_data()
    _MCACHE.update(at=now, data=data)
    return data


def clear_cache():
    _MCACHE.update(at=0.0, data=None)


def _metrics():
    """Rows [{well, metrics}] joining cached metric data with fresh Well objects."""
    from app.models.well import Well
    data = _metric_data()
    wells = {w.id: w for w in db.session.scalars(db.select(Well)).all()}
    return [{"well": wells[wid], "metrics": m} for wid, m in data.items() if wid in wells]


def _compute_metric_data():
    from app.models.well import Well
    from app.models.flow import FlowTest
    from app.models.pump_asset import PumpInstallation
    from app.models.rehab import Rehabilitation
    from app.models.baseline import WellBaseline
    from app.models.quality import WaterQuality
    from app.models.production import MonthlyProduction

    # flow history per well: (date, representative discharge, efficiency)
    flow = defaultdict(list)
    for t in db.session.scalars(db.select(FlowTest)).all():
        if not t.test_date:
            continue
        qs = [p.discharge_lps for p in t.points if p.discharge_lps]
        effs = [p.efficiency for p in t.points if p.efficiency]
        flow[t.well_id].append((t.test_date, max(qs) if qs else None,
                                max(effs) if effs else None))

    # monthly production time-series -> per-well yearly mean discharge (running months)
    prod_series = defaultdict(lambda: defaultdict(list))
    for mp in db.session.scalars(db.select(MonthlyProduction)).all():
        if mp.avg_discharge_lps and mp.avg_discharge_lps > 0:
            prod_series[mp.well_id][mp.jyear].append(mp.avg_discharge_lps)
    prod_decline = {}
    for wid, series in prod_series.items():
        d, _ref, _latest = _monthly_decline(_yearly_means(series))
        if d is not None:
            prod_decline[wid] = d

    # specific energy (kWh/m³) per well — higher is worse (less efficient)
    spec_energy = {}
    for mp in db.session.scalars(
            db.select(MonthlyProduction).where(MonthlyProduction.energy_kwh.isnot(None))).all():
        se = mp.specific_energy
        if se is not None:
            spec_energy[mp.well_id] = se

    # dynamic baselines (preferred reference for decline)
    baseline = {b.well_id: b.baseline_discharge_lps
                for b in db.session.scalars(db.select(WellBaseline).filter_by(is_current=True)).all()
                if b.baseline_discharge_lps}

    # water-quality severity (recency-weighted): 2=non-potable, 1=turbidity/sand
    cutoff = date.today() - timedelta(days=QUALITY_RECENT_DAYS)
    qsev = defaultdict(float)
    for wq in db.session.scalars(db.select(WaterQuality)).all():
        base = 2.0 if wq.is_potable is False else (1.0 if (wq.turbidity or wq.sholat) else 0.0)
        recent = wq.sample_date is not None and wq.sample_date >= cutoff
        qsev[wq.well_id] = max(qsev[wq.well_id], base * (1.0 if recent else 0.4))

    burn = defaultdict(int)
    for i in db.session.scalars(db.select(PumpInstallation)).all():
        if i.removal_reason and "سوخت" in i.removal_reason:
            burn[i.well_id] += 1

    rehab = defaultdict(int)
    for r in db.session.scalars(db.select(Rehabilitation)).all():
        rehab[r.well_id] += 1

    drill_year = dict(db.session.execute(db.select(Well.id, Well.drill_year)).all())

    data = {}
    for wid in set(flow) | set(prod_decline) | set(spec_energy):
        recs = sorted(flow.get(wid, []), key=lambda x: x[0])
        qs = [r[1] for r in recs if r[1] is not None]
        latest_q = next((r[1] for r in reversed(recs) if r[1] is not None), None)
        # Decline: prefer the dense monthly time-series; fall back to flow-test benchmark.
        if wid in prod_decline:
            decline = prod_decline[wid]
        else:
            ref_q = baseline.get(wid) or (max(qs) if qs else None)   # baseline preferred
            decline = ((ref_q - latest_q) / ref_q * 100) if (ref_q and latest_q and ref_q > 0) else 0.0
        latest_eff = next((r[2] for r in reversed(recs) if r[2] is not None), None)
        try:
            age = CURRENT_JYEAR - int(drill_year.get(wid)) if drill_year.get(wid) else None
        except (TypeError, ValueError):
            age = None
        data[wid] = {
            "discharge_decline": max(decline, 0.0),
            "efficiency_low": latest_eff,
            "burn_count": burn[wid],
            "rehab_count": rehab[wid],
            "age_years": age if (age and age > 0) else 0,
            "quality_flag": qsev.get(wid, 0.0),
            "specific_energy": spec_energy.get(wid),
        }
    return data


def compute(top=None):
    """Return wells ranked by priority score, with metric breakdown."""
    from app.models.prioritization import PrioritizationCriterion

    criteria = db.session.scalars(
        db.select(PrioritizationCriterion).filter_by(is_active=True)
    ).all()
    rows = _metrics()
    if not rows or not criteria:
        return [], criteria

    # min/max per metric across wells (ignore None)
    ranges = {}
    for c in criteria:
        vals = [r["metrics"].get(c.key) for r in rows if r["metrics"].get(c.key) is not None]
        ranges[c.key] = (min(vals), max(vals)) if vals else (0, 0)

    total_w = sum(c.weight for c in criteria) or 1.0
    for r in rows:
        s = 0.0
        for c in criteria:
            val = r["metrics"].get(c.key)
            lo, hi = ranges[c.key]
            if val is None:
                nb = 0.0
            elif hi == lo:
                nb = 0.0
            else:
                norm = (val - lo) / (hi - lo)
                nb = norm if c.direction == "higher_worse" else (1 - norm)
            s += c.weight * nb
        r["score"] = round(s / total_w * 100, 1)

    rows.sort(key=lambda r: r["score"], reverse=True)
    for idx, r in enumerate(rows, start=1):
        r["rank"] = idx
    return (rows[:top] if top else rows), criteria



################################################################################
# FILE: quality_extract.py
################################################################################

"""Extract water-quality flags from flow-test expert notes.

Turbidity (کدورت/کدر) and sand (شولات) are the recorded quality issues; a few
phrases mark non-potability. Creates one WaterQuality record per flow test that
mentions a quality issue. Idempotent (full reload of source='extract:notes').
"""
import re

from app.extensions import db
from app.models.flow import FlowTest
from app.models.quality import WaterQuality

TURBIDITY = ("کدورت", "کدر", "کدورتی")
SAND = ("شولات", "شولاتی")
NONPOTABLE = ("غیرقابل شرب", "غیر قابل شرب", "شرب نیست", "قابل شرب نیست",
              "غیرقابل استفاده", "غیر قابل استفاده", "از مدار خارج", "خارج از مدار")


def _norm(s):
    return re.sub(r"\s+", " ", str(s)).replace("ي", "ی").replace("ك", "ک")


def run(dry_run=False):
    stats = {"notes_scanned": 0, "created": 0, "turbidity": 0, "sand": 0, "non_potable": 0}

    db.session.query(WaterQuality).filter_by(source="extract:notes").delete()
    db.session.flush()

    tests = db.session.scalars(
        db.select(FlowTest).where(FlowTest.expert_note.isnot(None))
    ).all()
    for ft in tests:
        note = _norm(ft.expert_note)
        if not note.strip():
            continue
        stats["notes_scanned"] += 1
        turb = any(k in note for k in TURBIDITY)
        sand = any(k in note for k in SAND)
        if not (turb or sand):
            continue
        is_potable = None
        if turb and any(p in note for p in NONPOTABLE):
            is_potable = False
            stats["non_potable"] += 1
        if turb:
            stats["turbidity"] += 1
        if sand:
            stats["sand"] += 1
        db.session.add(WaterQuality(
            well_id=ft.well_id, sample_date=ft.test_date, flow_test_id=ft.id,
            turbidity=turb, sholat=sand, is_potable=is_potable,
            note=ft.expert_note[:500], source="extract:notes",
        ))
        stats["created"] += 1

    if dry_run:
        db.session.rollback()
    else:
        db.session.commit()
    return stats



################################################################################
# FILE: spatial.py
################################################################################

"""Hydrogeological spatial analysis (5.2) — local, numpy-only.

Builds the per-well metric points (static water level, specific energy, discharge
decline) used for heatmaps, and an IDW-interpolated piezometric surface (depth to
water) over the well field. No GIS engine needed — pure numpy, recompute on demand.
"""
from collections import defaultdict

import numpy as np

from app.extensions import db

GRID_N = 45          # IDW grid resolution
IDW_POWER = 2.0


def _latest_static_levels():
    from app.models.water_level import WaterLevelLog
    latest = {}
    for w in db.session.scalars(
            db.select(WaterLevelLog).where(WaterLevelLog.is_pumping.is_(False))
            .order_by(WaterLevelLog.measure_date)).all():
        if w.static_level is not None and w.measure_date:
            latest[w.well_id] = w.static_level   # last wins (ordered asc)
    return latest


def _specific_energy():
    from app.models.production import MonthlyProduction as MP
    out = {}
    for mp in db.session.scalars(db.select(MP).where(MP.energy_kwh.isnot(None))).all():
        se = mp.specific_energy
        if se is not None:
            out[mp.well_id] = se
    return out


def _decline_pct():
    """Lightweight per-well decline: peak annual mean vs latest annual mean (%)."""
    from app.models.production import MonthlyProduction as MP
    series = defaultdict(lambda: defaultdict(list))
    for mp in db.session.scalars(
            db.select(MP).where(MP.avg_discharge_lps.isnot(None))).all():
        if mp.avg_discharge_lps and mp.avg_discharge_lps > 0:
            series[mp.well_id][mp.jyear].append(mp.avg_discharge_lps)
    out = {}
    for wid, years in series.items():
        means = {y: sum(v) / len(v) for y, v in years.items() if len(v) >= 3}
        if len(means) < 1:
            continue
        ref = max(means.values())
        latest = means[max(means)]
        if ref > 0:
            out[wid] = round(max((ref - latest) / ref * 100, 0.0), 1)
    return out


def metric_points():
    """Per-well points (with coords) carrying the spatial metrics."""
    from app.models.well import Well
    sl = _latest_static_levels()
    se = _specific_energy()
    dec = _decline_pct()
    pts = []
    for w in db.session.scalars(
            db.select(Well).where(Well.latitude.isnot(None), Well.longitude.isnot(None))).all():
        pts.append({
            "id": w.id, "name": w.name, "lat": w.latitude, "lon": w.longitude,
            "static_level": sl.get(w.id),
            "specific_energy": se.get(w.id),
            "decline": dec.get(w.id),
        })
    return pts


def _idw(xs, ys, vals, gx, gy, power=IDW_POWER):
    """Vectorized inverse-distance-weighted interpolation onto grid (gx, gy)."""
    xs = np.asarray(xs); ys = np.asarray(ys); vals = np.asarray(vals)
    GX, GY = np.meshgrid(gx, gy)
    flatX, flatY = GX.ravel(), GY.ravel()
    # distance matrix (cells x samples)
    dx = flatX[:, None] - xs[None, :]
    dy = flatY[:, None] - ys[None, :]
    dist = np.sqrt(dx * dx + dy * dy)
    dist[dist < 1e-9] = 1e-9
    wts = 1.0 / dist ** power
    z = (wts @ vals) / wts.sum(axis=1)
    return z.reshape(GX.shape), GX, GY


def _haversine(lat1, lon1, lat2, lon2):
    """Great-circle distance in metres (vectorizable with numpy arrays)."""
    R = 6371000.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlmb = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlmb / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(a))


def interference(threshold_m=400):
    """Well pairs closer than threshold (mutual-drawdown / interference risk).

    Returns the pairs (with distance and latest discharges) + per-well neighbour
    counts for density. Pure numpy on the coordinate set.
    """
    pts = metric_points()
    from app.models.production import MonthlyProduction as MP
    # latest discharge per well (context)
    disc = {}
    for mp in db.session.scalars(
            db.select(MP).where(MP.avg_discharge_lps.isnot(None))
            .order_by(MP.jyear, MP.jmonth)).all():
        if mp.avg_discharge_lps:
            disc[mp.well_id] = mp.avg_discharge_lps

    n = len(pts)
    if n < 2:
        return {"pairs": [], "count": 0, "threshold_m": threshold_m, "dense": []}
    lat = np.array([p["lat"] for p in pts])
    lon = np.array([p["lon"] for p in pts])
    pairs, neigh = [], [0] * n
    for i in range(n):
        d = _haversine(lat[i], lon[i], lat[i + 1:], lon[i + 1:])
        for k, dist in enumerate(d):
            if dist <= threshold_m:
                j = i + 1 + k
                neigh[i] += 1
                neigh[j] += 1
                pairs.append({
                    "a_id": pts[i]["id"], "a": pts[i]["name"],
                    "b_id": pts[j]["id"], "b": pts[j]["name"],
                    "a_lat": pts[i]["lat"], "a_lon": pts[i]["lon"],
                    "b_lat": pts[j]["lat"], "b_lon": pts[j]["lon"],
                    "dist": round(float(dist)),
                    "qa": disc.get(pts[i]["id"]), "qb": disc.get(pts[j]["id"]),
                })
    pairs.sort(key=lambda p: p["dist"])
    dense = sorted(
        [{"id": pts[i]["id"], "name": pts[i]["name"], "neighbours": neigh[i]}
         for i in range(n) if neigh[i] >= 3],
        key=lambda x: -x["neighbours"])[:15]
    return {"pairs": pairs, "count": len(pairs), "threshold_m": threshold_m, "dense": dense}


def suitability_grid():
    """Relocation site-suitability surface (multi-criteria, 0-100).

    Higher = better new-well location: far from existing wells (less interference),
    shallower water table, and lower discharge decline locally. Criteria are
    IDW-interpolated onto the same grid. Pure numpy.
    """
    pts = metric_points()
    sl_pts = [p for p in pts if p["static_level"] is not None]
    dec_pts = [p for p in pts if p["decline"] is not None]
    if len(pts) < 8 or len(sl_pts) < 5:
        return None
    lons = [p["lon"] for p in pts]
    lats = [p["lat"] for p in pts]
    gx = np.linspace(min(lons), max(lons), GRID_N)
    gy = np.linspace(min(lats), max(lats), GRID_N)
    GX, GY = np.meshgrid(gx, gy)

    # 1) distance to nearest existing well (m) -> normalized (far is better, cap 2km)
    wlat = np.array(lats)[:, None, None]
    wlon = np.array(lons)[:, None, None]
    dmin = _haversine(GY[None, :, :], GX[None, :, :], wlat, wlon).min(axis=0)
    dist_n = np.clip(dmin / 2000.0, 0, 1)

    # 2) depth to water (IDW) -> shallower is better
    Zw, _, _ = _idw([p["lon"] for p in sl_pts], [p["lat"] for p in sl_pts],
                    [p["static_level"] for p in sl_pts], gx, gy)
    wn = (Zw - Zw.min()) / ((Zw.max() - Zw.min()) or 1)
    depth_n = 1 - wn

    # 3) local decline (IDW) -> lower is better
    if len(dec_pts) >= 5:
        Zd, _, _ = _idw([p["lon"] for p in dec_pts], [p["lat"] for p in dec_pts],
                        [p["decline"] for p in dec_pts], gx, gy)
        dn = (Zd - Zd.min()) / ((Zd.max() - Zd.min()) or 1)
        decl_n = 1 - dn
    else:
        decl_n = np.full(GX.shape, 0.5)

    score = (0.45 * dist_n + 0.30 * depth_n + 0.25 * decl_n) * 100
    dlon = (gx[1] - gx[0]) / 2.0
    dlat = (gy[1] - gy[0]) / 2.0
    cells = [{"lat": round(float(la), 6), "lon": round(float(lo), 6), "val": round(float(s), 1)}
             for lo, la, s in zip(GX.ravel(), GY.ravel(), score.ravel())]
    return {"cells": cells, "dlat": round(dlat, 6), "dlon": round(dlon, 6),
            "vmin": round(float(score.min()), 1), "vmax": round(float(score.max()), 1)}


def piezometric_grid():
    """IDW-interpolated static-water-level surface over the well field.

    Returns colored grid cells [{lat, lon, val}] + value range, or None.
    """
    pts = [p for p in metric_points() if p["static_level"] is not None]
    if len(pts) < 5:
        return None
    lons = [p["lon"] for p in pts]
    lats = [p["lat"] for p in pts]
    vals = [p["static_level"] for p in pts]
    gx = np.linspace(min(lons), max(lons), GRID_N)
    gy = np.linspace(min(lats), max(lats), GRID_N)
    Z, GX, GY = _idw(lons, lats, vals, gx, gy)
    dlon = (gx[1] - gx[0]) / 2.0
    dlat = (gy[1] - gy[0]) / 2.0
    cells = []
    zf = Z.ravel()
    for lon, lat, v in zip(GX.ravel(), GY.ravel(), zf):
        cells.append({"lat": round(float(lat), 6), "lon": round(float(lon), 6),
                      "val": round(float(v), 1)})
    return {"cells": cells, "dlat": round(dlat, 6), "dlon": round(dlon, 6),
            "vmin": round(float(zf.min()), 1), "vmax": round(float(zf.max()), 1),
            "n_wells": len(pts)}



################################################################################
# FILE: timeline.py
################################################################################

"""Build a unified, date-sorted event timeline for a well ("پرونده‌ی چاه").

Each lifecycle event module registers a provider here. Adding a new event type
in later phases is a one-function change — append to PROVIDERS.
"""
from flask import url_for

from app.extensions import db


def _drilling_events(well_id):
    from app.models.drilling import Drilling

    rows = db.session.scalars(
        db.select(Drilling).filter_by(well_id=well_id)
    ).all()
    items = []
    for r in rows:
        items.append({
            "date": r.end_date or r.start_date,
            "module": "drilling",
            "type_label": "حفاری و توسعه",
            "icon": "bi-cone-striped",
            "title": r.contractor or "حفاری",
            "summary": _drilling_summary(r),
            "status": r.status,
            "url": url_for("drilling.detail", record_id=r.id),
        })
    return items


def _drilling_summary(r):
    parts = []
    if r.well_depth_actual or r.well_depth_permit:
        parts.append(f"عمق {r.well_depth_actual or r.well_depth_permit} متر")
    if r.proposed_discharge_lps:
        parts.append(f"دبی پیشنهادی {r.proposed_discharge_lps} l/s")
    return "، ".join(parts)


def _flow_events(well_id):
    from app.models.flow import FlowTest

    rows = db.session.scalars(db.select(FlowTest).filter_by(well_id=well_id)).all()
    items = []
    for r in rows:
        # representative discharge: the network-pressure point if present
        disch = next((p.discharge_lps for p in r.points if p.discharge_lps), None)
        summary = []
        if disch:
            summary.append(f"دبی {disch} l/s")
        if r.test_reason:
            summary.append(r.test_reason)
        items.append({
            "date": r.test_date,
            "module": "operation",
            "type_label": "دبی‌سنجی",
            "icon": "bi-speedometer2",
            "title": r.electropump_type or "بهره‌برداری",
            "summary": "، ".join(summary),
            "status": r.status,
            "url": url_for("operation.detail", record_id=r.id),
        })
    return items


def _pump_test_events(well_id):
    from app.models.pump_test import PumpTest

    rows = db.session.scalars(db.select(PumpTest).filter_by(well_id=well_id)).all()
    items = []
    for r in rows:
        summary = []
        if r.proposed_discharge_lps:
            summary.append(f"دبی مجاز {r.proposed_discharge_lps} l/s")
        if r.pump_type:
            summary.append(r.pump_type)
        items.append({
            "date": r.test_date,
            "module": "pump_test",
            "type_label": "آزمایش پمپاژ",
            "icon": "bi-clipboard-data",
            "title": r.contractor or "آزمایش پمپاژ",
            "summary": "، ".join(summary),
            "status": r.status,
            "url": url_for("pump_test.detail", record_id=r.id),
        })
    return items


def _install_events(well_id):
    """A pump installation row yields TWO timeline events: an install (at
    install_date) and, if present, a pull/removal (at pull_date)."""
    from app.models.pump_asset import PumpInstallation

    rows = db.session.scalars(db.select(PumpInstallation).filter_by(well_id=well_id)).all()
    items = []
    for r in rows:
        url = url_for("install.detail", record_id=r.id)
        pump = " ".join(filter(None, [
            f"پمپ {r.pump_type}" if r.pump_type else None,
            r.manufacturer.name if r.manufacturer else None,
        ]))
        if r.install_date:
            items.append({
                "date": r.install_date, "module": "install",
                "type_label": "نصب پمپ", "icon": "bi-box-arrow-in-down",
                "title": (r.contractor.name if r.contractor else "نصب"),
                "summary": pump, "status": r.status, "url": url,
            })
        if r.pull_date:
            pull_parts = [p for p in [r.removal_reason] if p]
            if r.useful_life_months is not None:
                pull_parts.append(f"عمر مفید {r.useful_life_months} ماه")
            items.append({
                "date": r.pull_date, "module": "install",
                "type_label": "کشیدن پمپ", "icon": "bi-box-arrow-up",
                "title": (r.contractor.name if r.contractor else "کشیدن"),
                "summary": "، ".join(pull_parts), "status": r.status, "url": url,
            })
    return items


def _rehab_events(well_id):
    from app.models.rehab import Rehabilitation

    rows = db.session.scalars(db.select(Rehabilitation).filter_by(well_id=well_id)).all()
    items = []
    for r in rows:
        parts = [p for p in [r.reason] if p]
        g = r.discharge_gain
        if g is not None:
            parts.append(f"تغییر دبی {g} l/s")
        items.append({
            "date": r.rehab_date,
            "module": "rehab",
            "type_label": "بهسازی",
            "icon": "bi-arrow-repeat",
            "title": (r.rehab_contractor.name if r.rehab_contractor else "بهسازی"),
            "summary": "، ".join(parts),
            "status": r.status,
            "url": url_for("rehab.detail", record_id=r.id),
        })
    return items


def _pump_select_events(well_id):
    from app.models.pump_select import PumpSelection

    rows = db.session.scalars(db.select(PumpSelection).filter_by(well_id=well_id)).all()
    items = []
    for r in rows:
        parts = []
        if r.selected_pump_type:
            parts.append(f"پمپ {r.selected_pump_type}")
        if r.target_discharge_lps:
            parts.append(f"دبی هدف {r.target_discharge_lps} l/s")
        items.append({
            "date": r.form_delivery_date,
            "module": "pump_select",
            "type_label": "انتخاب پمپ",
            "icon": "bi-funnel",
            "title": r.action_needed or "انتخاب پمپ",
            "summary": "، ".join(parts),
            "status": r.status,
            "url": url_for("pump_select.detail", record_id=r.id),
        })
    return items


def _videometry_events(well_id):
    from app.models.videometry import Videometry

    rows = db.session.scalars(db.select(Videometry).filter_by(well_id=well_id)).all()
    items = []
    for r in rows:
        n = len(r.findings)
        high = sum(1 for f in r.findings if f.severity == "high")
        summary = []
        if n:
            summary.append(f"{n} یافته" + (f" ({high} شدید)" if high else ""))
        items.append({
            "date": r.log_date,
            "module": "videometry",
            "type_label": "چاه‌نگاری",
            "icon": "bi-camera-video",
            "title": (r.contractor.name if r.contractor else "چاه‌نگاری"),
            "summary": "، ".join(summary),
            "status": r.status,
            "url": url_for("videometry.detail", record_id=r.id),
        })
    return items


def _maintenance_events(well_id):
    from app.models.maintenance import MaintenanceRecord
    from app.models.constants import MAINTENANCE_TYPES, MAINTENANCE_CATEGORIES

    tl, cl = dict(MAINTENANCE_TYPES), dict(MAINTENANCE_CATEGORIES)
    rows = db.session.scalars(db.select(MaintenanceRecord).filter_by(well_id=well_id)).all()
    items = []
    for r in rows:
        parts = [p for p in [tl.get(r.maint_type), cl.get(r.category)] if p]
        items.append({
            "date": r.report_date,
            "module": "maintenance",
            "type_label": "نگهداری/تعمیر",
            "icon": "bi-wrench-adjustable",
            "title": (r.contractor.name if r.contractor else "نگهداری"),
            "summary": "، ".join(parts),
            "status": r.status,
            "url": url_for("maintenance.detail", record_id=r.id),
        })
    return items


def _relocation_events(well_id):
    from app.models.relocation import RelocationRecord
    from app.models.constants import RELOCATION_CANDIDACY

    cand = dict(RELOCATION_CANDIDACY)
    rows = db.session.scalars(db.select(RelocationRecord).filter_by(well_id=well_id)).all()
    items = []
    for r in rows:
        parts = [p for p in [cand.get(r.candidacy)] if p]
        if r.new_well:
            parts.append(f"جانشین: {r.new_well.name}")
        items.append({
            "date": r.decision_date,
            "module": "relocation",
            "type_label": "جابه‌جایی",
            "icon": "bi-signpost-2",
            "title": r.reason or "جابه‌جایی",
            "summary": "، ".join(parts),
            "status": r.status,
            "url": url_for("relocation.detail", record_id=r.id),
        })
    return items


# (module, provider) — extend as new event types come online.
PROVIDERS = [
    ("drilling", _drilling_events),
    ("pump_test", _pump_test_events),
    ("pump_select", _pump_select_events),
    ("install", _install_events),
    ("operation", _flow_events),
    ("rehab", _rehab_events),
    ("videometry", _videometry_events),
    ("maintenance", _maintenance_events),
    ("relocation", _relocation_events),
]


def build(well):
    """Return all events for a well, newest first. Items with no date sort last."""
    items = []
    for _module, provider in PROVIDERS:
        items.extend(provider(well.id))
    items.sort(key=lambda x: (x["date"] is not None, x["date"]), reverse=True)
    return items



################################################################################
# FILE: zone_stats.py
################################################################################

"""5.5 Zone / supply-zone analytics.

Aggregates wells by hydrogeological zone (پهنه) and destination reservoir
(مخزن مقصد): well counts, energy, fleet specific energy and average decline —
so a manager can compare zones and spot over-stressed / inefficient areas.
"""
from collections import defaultdict

from app.extensions import db


def _by(attr):
    from app.models.well import Well
    from app.models.production import MonthlyProduction as MP
    from app.services.spatial import _decline_pct

    wells = db.session.scalars(db.select(Well)).all()
    decline = _decline_pct()
    energy = defaultdict(lambda: {"kwh": 0.0, "m3": 0.0})
    for mp in db.session.scalars(db.select(MP).where(MP.energy_kwh.isnot(None))).all():
        e = energy[mp.well_id]
        e["kwh"] += mp.energy_kwh or 0
        if mp.production_m3:
            e["m3"] += mp.production_m3

    agg = defaultdict(lambda: {"n": 0, "active": 0, "kwh": 0.0, "m3": 0.0,
                               "declines": [], "mapped": 0})
    for w in wells:
        key = getattr(w, attr)
        if not key:
            continue
        a = agg[key]
        a["n"] += 1
        if w.status == "in_circuit":
            a["active"] += 1
        if w.latitude is not None:
            a["mapped"] += 1
        e = energy.get(w.id)
        if e:
            a["kwh"] += e["kwh"]
            a["m3"] += e["m3"]
        if w.id in decline:
            a["declines"].append(decline[w.id])

    rows = []
    for key, a in agg.items():
        se = round(a["kwh"] / a["m3"], 2) if a["m3"] else None
        avg_dec = round(sum(a["declines"]) / len(a["declines"]), 1) if a["declines"] else None
        rows.append({
            "key": key, "n": a["n"], "active": a["active"], "mapped": a["mapped"],
            "kwh": round(a["kwh"]), "specific_energy": se, "avg_decline": avg_dec,
        })
    rows.sort(key=lambda r: -r["n"])
    return rows


def compute():
    return {"zones": _by("zone"), "reservoirs": _by("destination_reservoir")}



################################################################################
# FILE: __init__.py
################################################################################




################################################################################
# FILE: dates.py
################################################################################

"""Jalali (Shamsi) <-> Gregorian date handling.

Policy (decided 2026-06): users enter Jalali, we store Gregorian `date`,
and display Jalali. Persian/Arabic-Indic digits are normalized to ASCII
*before* parsing — see the persian-digit-date-filter pitfall from the
Financial system.
"""
from datetime import date

import jdatetime

# Persian (U+06Fx) and Arabic-Indic (U+066x) digits -> ASCII.
_DIGIT_MAP = {ord(c): str(i % 10) for i, c in enumerate(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩"
)}
# Arabic decimal/thousands separators -> ASCII so numeric parsing works.
_DIGIT_MAP[ord("٫")] = "."   # U+066B Arabic decimal separator
_DIGIT_MAP[ord("٬")] = ""    # U+066C Arabic thousands separator


def to_english_digits(s: str) -> str:
    return (s or "").translate(_DIGIT_MAP)


def parse_jalali(value: str):
    """Parse a Jalali date string ('1404/02/08', '۱۴۰۴-۲-۸', '1404.2.8') to a
    Gregorian `date`. Returns None for empty input; raises ValueError if invalid.
    """
    if value is None:
        return None
    s = to_english_digits(str(value)).strip()
    if not s:
        return None
    for sep in ("/", "-", "."):
        s = s.replace(sep, "/")
    parts = [p for p in s.split("/") if p != ""]
    if len(parts) != 3:
        raise ValueError("فرمت تاریخ نامعتبر است (نمونه: 1404/02/08)")
    y, m, d = (int(p) for p in parts)
    # 8-digit compact form like 14040208
    if y > 9999:
        raise ValueError("سال نامعتبر است")
    return jdatetime.date(y, m, d).togregorian()


def format_jalali(value, default="—") -> str:
    """Format a Gregorian `date`/`datetime` as a Jalali 'YYYY/MM/DD' string."""
    if value is None:
        return default
    if not isinstance(value, date):
        return str(value)
    return jdatetime.date.fromgregorian(date=value).strftime("%Y/%m/%d")


def parse_compact_jalali(value: str):
    """Parse compact forms like '14040208' (seen in some source files)."""
    s = to_english_digits(str(value or "")).strip()
    if len(s) == 8 and s.isdigit():
        return jdatetime.date(int(s[:4]), int(s[4:6]), int(s[6:8])).togregorian()
    return parse_jalali(value)



################################################################################
# FILE: forms.py
################################################################################

"""Custom WTForms fields: Jalali date + Persian-digit-tolerant numbers."""
from wtforms import StringField, FloatField, IntegerField
from wtforms.validators import ValidationError

from app.utils.dates import parse_jalali, format_jalali, to_english_digits


class _PersianDigitsMixin:
    """Normalize Persian/Arabic digits (and ٫ ٬ separators) before parsing."""

    def process_formdata(self, valuelist):
        if valuelist:
            valuelist = [to_english_digits(v) if isinstance(v, str) else v
                         for v in valuelist]
        super().process_formdata(valuelist)


class PersianFloatField(_PersianDigitsMixin, FloatField):
    pass


class PersianIntegerField(_PersianDigitsMixin, IntegerField):
    pass


class JalaliDateField(StringField):
    """Text field that accepts a Jalali date and stores a Gregorian `date`.

    - `data` holds a `datetime.date` (or None).
    - The rendered value is the Jalali string.
    """

    def _value(self):
        if self.raw_data:
            return self.raw_data[0]
        return format_jalali(self.data, default="")

    def process_formdata(self, valuelist):
        if not valuelist or not valuelist[0].strip():
            self.data = None
            return
        try:
            self.data = parse_jalali(valuelist[0])
        except ValueError as e:
            self.data = None
            raise ValidationError(str(e))



################################################################################
# FILE: suggestions.py
################################################################################

"""Distinct-value suggestions for combobox (datalist) form fields.

Populated from existing DB values so data entry is select-or-type: fast and
consistent (prevents spelling variants). Exposed to templates as `suggest`
(lazy, cached per request).
"""
from functools import cached_property

from app.extensions import db


class Suggestions:
    def _distinct(self, *cols):
        vals = set()
        for col in cols:
            for (v,) in db.session.execute(db.select(col).distinct()).all():
                if v is not None and str(v).strip():
                    vals.add(str(v).strip())
        return sorted(vals)

    @cached_property
    def suppliers(self):
        from app.models.pump_asset import Supplier
        return sorted({s.name for s in db.session.scalars(db.select(Supplier)).all()})

    @cached_property
    def pump_types(self):
        from app.models.pump_asset import PumpInstallation
        from app.models.rehab import Rehabilitation
        from app.models.flow import FlowTest
        return self._distinct(
            PumpInstallation.pump_type, Rehabilitation.pump_type_before,
            Rehabilitation.pump_type_after, FlowTest.electropump_type,
        )

    @cached_property
    def removal_reasons(self):
        from app.models.pump_asset import PumpInstallation
        from app.models.flow import FlowTest
        return self._distinct(PumpInstallation.removal_reason, FlowTest.pull_reason)

    @cached_property
    def rehab_reasons(self):
        from app.models.rehab import Rehabilitation
        return self._distinct(Rehabilitation.reason)

    @cached_property
    def network_types(self):
        from app.models.flow import FlowTest
        return self._distinct(FlowTest.network_type)

    @cached_property
    def electropump_types(self):
        from app.models.flow import FlowTest
        from app.models.pump_asset import PumpInstallation
        return self._distinct(FlowTest.electropump_type, PumpInstallation.pump_type)

    @cached_property
    def starter_types(self):
        from app.models.flow import FlowTest
        return self._distinct(FlowTest.starter_type)

    @cached_property
    def equipment(self):
        from app.models.videometry import Videometry
        return self._distinct(Videometry.equipment)

    @cached_property
    def drill_methods(self):
        from app.models.drilling import Drilling
        return self._distinct(Drilling.contractor)  # contractors for drilling



################################################################################
# FILE: __init__.py
################################################################################

"""Application factory for the Water Supply well-management system."""
from flask import Flask, render_template
from sqlalchemy import event
from sqlalchemy.engine import Engine

from config import Config
from app.extensions import db, migrate, login_manager, csrf


def create_app(config_class=Config):
    app = Flask(__name__, instance_relative_config=False)
    app.config.from_object(config_class)

    # --- extensions ---
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)

    # --- models (import so SQLAlchemy/Alembic see them) ---
    with app.app_context():
        from app import models  # noqa: F401

    # --- login user loader ---
    from app.models.rbac import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    # --- blueprints ---
    from app.blueprints.auth import bp as auth_bp
    from app.blueprints.main import bp as main_bp
    from app.blueprints.orgs import bp as orgs_bp
    from app.blueprints.wells import bp as wells_bp
    from app.blueprints.gis import bp as gis_bp
    from app.blueprints.drilling import bp as drilling_bp
    from app.blueprints.operation import bp as operation_bp
    from app.blueprints.pump_test import bp as pump_test_bp
    from app.blueprints.install import bp as install_bp
    from app.blueprints.rehab import bp as rehab_bp
    from app.blueprints.videometry import bp as videometry_bp
    from app.blueprints.pump_select import bp as pump_select_bp
    from app.blueprints.reports import bp as reports_bp
    from app.blueprints.exports import bp as exports_bp
    from app.blueprints.relocation import bp as relocation_bp
    from app.blueprints.maintenance import bp as maintenance_bp
    from app.blueprints.water_level import bp as water_level_bp
    from app.blueprints.documents import bp as documents_bp
    from app.blueprints.printing import bp as printing_bp
    from app.blueprints.production_trend import bp as production_trend_bp
    from app.blueprints.permit import bp as permit_bp
    from app.blueprints.permit_event import bp as permit_event_bp
    from app.blueprints.mechanic import bp as mechanic_bp
    from app.blueprints.finance import bp as finance_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(orgs_bp)
    app.register_blueprint(wells_bp)
    app.register_blueprint(gis_bp)
    app.register_blueprint(drilling_bp)
    app.register_blueprint(operation_bp)
    app.register_blueprint(pump_test_bp)
    app.register_blueprint(install_bp)
    app.register_blueprint(rehab_bp)
    app.register_blueprint(videometry_bp)
    app.register_blueprint(pump_select_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(exports_bp)
    app.register_blueprint(relocation_bp)
    app.register_blueprint(maintenance_bp)
    app.register_blueprint(water_level_bp)
    app.register_blueprint(documents_bp)
    app.register_blueprint(printing_bp)
    app.register_blueprint(production_trend_bp)
    app.register_blueprint(permit_bp)
    app.register_blueprint(permit_event_bp)
    app.register_blueprint(mechanic_bp)
    app.register_blueprint(finance_bp)

    # --- CLI commands ---
    from app.cli import register_cli
    register_cli(app)

    # --- template context & filters ---
    @app.context_processor
    def inject_globals():
        from app.models.constants import NAV_GROUPS
        from app.utils.suggestions import Suggestions
        return {"nav_groups": NAV_GROUPS, "suggest": Suggestions()}

    # Jinja globals are visible inside imported macros (context vars are not).
    from app.workflow import badge as workflow_badge
    app.jinja_env.globals["workflow_badge"] = workflow_badge

    from app.utils.dates import format_jalali

    @app.template_filter("jdate")
    def _jdate(value, default="—"):
        return format_jalali(value, default=default)
    @app.template_filter("jdatetime")
    def _jdatetime(value, default="—"):
        if not value:
            return default
        try:
            import jdatetime as _jd
            return _jd.datetime.fromgregorian(datetime=value).strftime("%Y/%m/%d %H:%M")
        except Exception:
            return default
    

    # --- error handlers ---
    @app.errorhandler(403)
    def forbidden(e):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template("errors/404.html"), 404

    return app


# Enforce SQLite foreign keys (no-op on PostgreSQL).
@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    module = type(dbapi_connection).__module__
    if "sqlite3" in module:
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.close()



################################################################################
# FILE: cli.py
################################################################################

"""Custom Flask CLI commands (database seeding, admin creation)."""
import click
from flask import current_app

from app.extensions import db
from app.models.constants import MODULES, ACTIONS, MODULE_LABELS, ACTION_LABELS
from app.models.rbac import User, Role, Permission
from app.models.org import OrgUnit


def _sync_permissions():
    """Ensure a Permission row exists for every module x action pair."""
    created = 0
    existing = {p.code for p in db.session.scalars(db.select(Permission)).all()}
    for module, _ in MODULES:
        for action, _ in ACTIONS:
            code = f"{module}:{action}"
            if code not in existing:
                db.session.add(
                    Permission(
                        code=code,
                        module=module,
                        action=action,
                        description=f"{MODULE_LABELS.get(module, module)} - {ACTION_LABELS.get(action, action)}",
                    )
                )
                created += 1
    db.session.commit()
    return created


def register_cli(app):
    @app.cli.command("seed-db")
    @click.option("--admin-user", default="admin", help="Superuser username.")
    @click.option("--admin-pass", default="admin", help="Superuser password.")
    def seed_db(admin_user, admin_pass):
        """Create permissions, an Admin role, a superuser, and sample org units."""
        n = _sync_permissions()
        click.echo(f"Permissions synced (+{n} new).")

        # Admin role with all permissions.
        admin_role = db.session.scalar(db.select(Role).filter_by(name="مدیر سیستم"))
        if admin_role is None:
            admin_role = Role(name="مدیر سیستم", description="دسترسی کامل")
            db.session.add(admin_role)
        admin_role.permissions = db.session.scalars(db.select(Permission)).all()

        # Superuser.
        user = db.session.scalar(db.select(User).filter_by(username=admin_user))
        if user is None:
            user = User(username=admin_user, full_name="مدیر سیستم", is_superuser=True)
            user.set_password(admin_pass)
            user.roles = [admin_role]
            db.session.add(user)
            click.echo(f"Superuser '{admin_user}' created (password: '{admin_pass}').")
        else:
            click.echo(f"Superuser '{admin_user}' already exists — left unchanged.")

        # Sample organizational units (from the real data centers).
        if db.session.scalar(db.select(db.func.count(OrgUnit.id))) == 0:
            office = OrgUnit(name="اداره دانشجو", unit_type="office")
            db.session.add(office)
            db.session.flush()
            for c in ["گلشهر", "خیرآباد", "امامیه", "امام علی", "دانشجو"]:
                db.session.add(OrgUnit(name=f"مرکز {c}", unit_type="center", parent_id=office.id))
            db.session.add(OrgUnit(name="منطقه ۵ روستایی", unit_type="rural_region"))
            click.echo("Sample org units created.")

        db.session.commit()
        click.echo("Seeding complete.")

    @app.cli.command("sync-permissions")
    def sync_permissions_cmd():
        """Add any missing module x action permissions (run after adding modules)."""
        n = _sync_permissions()
        click.echo(f"Permissions synced (+{n} new).")

    @app.cli.command("import-wells")
    @click.option("--borwells", "borwells_path", default="current data/Borwells.xlsx",
                  help="Path to Borwells.xlsx")
    @click.option("--aggregate", "tajmi_path", default="current data/تجمیعی (400-405).xlsx",
                  help="Path to the aggregate file (for pm_code mapping)")
    @click.option("--dry-run", is_flag=True, help="Parse and report without writing.")
    def import_wells_cmd(borwells_path, tajmi_path, dry_run):
        """Import/refresh the well master registry from the source spreadsheets."""
        from app.imports.wells_import import run
        stats = run(borwells_path, tajmi_path, dry_run=dry_run)
        mode = "DRY-RUN (no changes)" if dry_run else "committed"
        click.echo(f"Well import {mode}:")
        for k, v in stats.items():
            click.echo(f"  {k:14}: {v}")

    @app.cli.command("export-discrepancies")
    @click.option("--out", "out_path", default="well_discrepancies.xlsx")
    def export_discrepancies_cmd(out_path):
        """Export pm-code discrepancies to Excel for manual correction."""
        from app.imports.discrepancy_export import export
        stats = export("current data/تجمیعی (400-405).xlsx", out_path)
        click.echo(f"Discrepancy report written to {out_path}:")
        for k, v in stats.items():
            click.echo(f"  {k}: {v}")

    @app.cli.command("import-install")
    @click.option("--nasb", "nasb_path", default="current data/نصب و کشیدن پمپ- تجمیعی.xlsx")
    @click.option("--dry-run", is_flag=True)
    def import_install_cmd(nasb_path, dry_run):
        """Import pump installation/pull records (matched by well name)."""
        from app.imports.install_import import run
        stats = run(nasb_path, dry_run=dry_run)
        click.echo(f"Install import {'DRY-RUN' if dry_run else 'committed'}:")
        for k, v in stats.items():
            click.echo(f"  {k:16}: {v}")

    @app.cli.command("import-catalog")
    @click.option("--file", "path", default="current data/pump selection/pump_data.js")
    def import_catalog_cmd(path):
        """(Re)load the pump catalog from pump_data.js into PumpModel/PumpCurvePoint."""
        from app.imports.catalog_import import run
        stats = run(path)
        click.echo(f"Catalog loaded: {stats['models']} models, {stats['points']} points.")

    @app.cli.command("extract-quality")
    @click.option("--dry-run", is_flag=True)
    def extract_quality_cmd(dry_run):
        """Extract water-quality flags (کدورت/شولات) from flow-test expert notes."""
        from app.services.quality_extract import run
        stats = run(dry_run=dry_run)
        click.echo(f"Water-quality extract {'DRY-RUN' if dry_run else 'committed'}:")
        for k, v in stats.items():
            click.echo(f"  {k:16}: {v}")

    @app.cli.command("recompute-baselines")
    @click.option("--dry-run", is_flag=True)
    def recompute_baselines_cmd(dry_run):
        """Recompute per-well dynamic baselines (anchored to drilling/rehab)."""
        from app.services.baseline import run
        stats = run(dry_run=dry_run)
        click.echo(f"Baselines {'DRY-RUN' if dry_run else 'committed'}:")
        for k, v in stats.items():
            click.echo(f"  {k:14}: {v}")

    @app.cli.command("reconcile-flow")
    @click.option("--dry-run", is_flag=True)
    def reconcile_flow_cmd(dry_run):
        """Merge duplicate دبی‌سنجی (rawflow canonical, enriched from tajmi)."""
        from app.imports.flow_reconcile import run
        stats = run(dry_run=dry_run)
        click.echo(f"Flow reconcile {'DRY-RUN' if dry_run else 'committed'}:")
        for k, v in stats.items():
            click.echo(f"  {k:22}: {v}")

    @app.cli.command("import-rawflow")
    @click.option("--root", default="current data/Flow metering")
    @click.option("--limit", type=int, default=None)
    @click.option("--dry-run", is_flag=True)
    def import_rawflow_cmd(root, limit, dry_run):
        """Bulk-import raw دبی‌سنجی form workbooks (Flow metering folder)."""
        from app.imports.rawflow_import import run
        stats = run(root, dry_run=dry_run, limit=limit)
        click.echo(f"Raw-flow import {'DRY-RUN' if dry_run else 'committed'}:")
        for k, v in stats.items():
            if k != "_unmatched_sample":
                click.echo(f"  {k:18}: {v}")
        click.echo("  unmatched sample:")
        for (name, oid), n in stats.get("_unmatched_sample", []):
            click.echo(f"     {n:3}  {name}  (office_id={oid})")

    @app.cli.command("import-production")
    @click.option("--file", "path", default="current data/روند تولید چاه ها.xlsx")
    @click.option("--dry-run", is_flag=True)
    def import_production_cmd(path, dry_run):
        """Melt the wide production-trend workbook into monthly_production rows."""
        from app.imports.production_import import run
        stats = run(path, dry_run=dry_run)
        click.echo(f"Production import {'DRY-RUN' if dry_run else 'committed'}:")
        for k, v in stats.items():
            click.echo(f"  {k:18}: {v}")

    @app.cli.command("reconcile-aid")
    @click.option("--aid", "aid_path", default="current data/Aid data.xlsx")
    @click.option("--out", "out_path", default="aid_reconciliation.xlsx")
    def reconcile_aid_cmd(aid_path, out_path):
        """Reconcile registry + production data against the clean Aid master."""
        from app.imports.aid_reconcile import export
        stats = export(aid_path, out_path)
        click.echo("Aid reconciliation report written:")
        for k, v in stats.items():
            click.echo(f"  {k:26}: {v}")

    @app.cli.command("import-aid-production")
    @click.option("--file", "path", default="current data/Aid data.xlsx")
    @click.option("--dry-run", is_flag=True)
    def import_aid_production_cmd(path, dry_run):
        """Reconcile monthly production with Aid as the authoritative base (1403/1404)."""
        from app.imports.aid_production_import import run
        stats = run(path, dry_run=dry_run)
        samples = stats.pop("_conflict_samples", [])
        click.echo(f"Aid production reconcile {'DRY-RUN' if dry_run else 'committed'}:")
        for k, v in stats.items():
            click.echo(f"  {k:18}: {v}")
        for nm, yr, mo, old, new in samples:
            click.echo(f"     conflict {nm} {yr}/{mo}: روند={old} -> Aid={new}")

    @app.cli.command("recompute-analytics")
    def recompute_analytics_cmd():
        """Clear analytics/metric caches so they recompute on next access."""
        from app.services import prioritization
        from app.services.analytics import summary as asum
        prioritization.clear_cache()
        asum._CACHE.update(at=0.0, data=None)
        click.echo("Analytics caches cleared.")

    @app.cli.command("export-duplicates")
    @click.option("--out", "out_path", default="remaining_duplicates.xlsx")
    def export_duplicates_cmd(out_path):
        """Export remaining duplicate groups (with per-table data breakdown) for review."""
        from app.imports.duplicates_export import export
        stats = export(out_path)
        click.echo("Remaining-duplicates report written:")
        for k, v in stats.items():
            click.echo(f"  {k}: {v}")

    @app.cli.command("dedup-stubs")
    @click.option("--threshold", default=2, help="Max data records to treat a duplicate as a stub.")
    @click.option("--dry-run", is_flag=True)
    def dedup_stubs_cmd(threshold, dry_run):
        """Merge low-data duplicate wells into the data-rich primary, then delete them."""
        from app.imports.dedup_stubs import run
        stats = run(threshold=threshold, dry_run=dry_run)
        sample = stats.pop("_sample", [])
        stats.pop("_total_deleted_list", None)
        click.echo(f"Dedup stubs {'DRY-RUN' if dry_run else 'committed'} (threshold={threshold}):")
        for k, v in stats.items():
            click.echo(f"  {k:16}: {v}")
        for d in sample:
            click.echo(f"     delete '{d['name']}' (data={d['data']}) -> '{d['into']}' (data={d['into_data']})")

    @app.cli.command("import-coords")
    @click.option("--file", "path", default="current data/electricity.xlsx")
    @click.option("--dry-run", is_flag=True)
    def import_coords_cmd(path, dry_run):
        """Complete missing well coordinates from the electricity sheet UTM."""
        from app.imports.coords_import import run
        stats = run(path, dry_run=dry_run)
        click.echo(f"Coordinate completion {'DRY-RUN' if dry_run else 'committed'}:")
        for k, v in stats.items():
            click.echo(f"  {k:14}: {v}")

    @app.cli.command("import-construction")
    @click.option("--file", "path", default="current data/تجمیعی (400-405).xlsx")
    @click.option("--dry-run", is_flag=True)
    def import_construction_cmd(path, dry_run):
        """Fill well construction_type (سیمانته/غیرسیمانته) from the aggregate sheet."""
        from app.imports.construction_import import run
        stats = run(path, dry_run=dry_run)
        click.echo(f"Construction import {'DRY-RUN' if dry_run else 'committed'}:")
        for k, v in stats.items():
            click.echo(f"  {k:20}: {v}")

    @app.cli.command("import-zones")
    @click.option("--file", "path", default="current data/Aid data.xlsx")
    @click.option("--dry-run", is_flag=True)
    def import_zones_cmd(path, dry_run):
        """Import پهنه/زیرپهنه/مخزن مقصد from Aid into the well registry."""
        from app.imports.zone_import import run
        stats = run(path, dry_run=dry_run)
        click.echo(f"Zone import {'DRY-RUN' if dry_run else 'committed'}:")
        for k, v in stats.items():
            click.echo(f"  {k:10}: {v}")

    @app.cli.command("seed-water-levels")
    @click.option("--dry-run", is_flag=True)
    def seed_water_levels_cmd(dry_run):
        """Seed water-level monitoring from existing static levels (flow/pump/drill)."""
        from app.imports.water_level_seed import run
        stats = run(dry_run=dry_run)
        click.echo(f"Water-level seed {'DRY-RUN' if dry_run else 'committed'}:")
        for k, v in stats.items():
            click.echo(f"  {k:10}: {v}")

    @app.cli.command("import-electricity")
    @click.option("--file", "path", default="current data/electricity.xlsx")
    @click.option("--dry-run", is_flag=True)
    def import_electricity_cmd(path, dry_run):
        """Import monthly electricity (kWh/cost) into monthly_production (strict match)."""
        from app.imports.electricity_import import run
        stats = run(path, dry_run=dry_run)
        click.echo(f"Electricity import {'DRY-RUN' if dry_run else 'committed'}:")
        for k, v in stats.items():
            click.echo(f"  {k:18}: {v}")

    @app.cli.command("import-well-technical")
    @click.option("--file", "path", default="current data/Aid data.xlsx")
    @click.option("--dry-run", is_flag=True)
    def import_well_technical_cmd(path, dry_run):
        """Enrich wells with technical metadata (meter/last-flowtest/construction) from Aid."""
        from app.imports.well_technical_import import run
        stats = run(path, dry_run=dry_run)
        click.echo(f"Well-technical import {'DRY-RUN' if dry_run else 'committed'}:")
        for k, v in stats.items():
            click.echo(f"  {k:12}: {v}")

    @app.cli.command("import-relocation")
    @click.option("--file", "path", default="current data/Aid data.xlsx")
    @click.option("--dry-run", is_flag=True)
    def import_relocation_cmd(path, dry_run):
        """Import relocation candidacy markers from the Aid master."""
        from app.imports.relocation_import import run
        stats = run(path, dry_run=dry_run)
        click.echo(f"Relocation import {'DRY-RUN' if dry_run else 'committed'}:")
        for k, v in stats.items():
            click.echo(f"  {k:14}: {v}")

    @app.cli.command("import-aid-elevation")
    @click.option("--file", "path", default="current data/Aid data.xlsx")
    @click.option("--dry-run", is_flag=True)
    def import_aid_elevation_cmd(path, dry_run):
        """Fill missing well elevations from Aid's رقوم ارتفاعی sheet."""
        from app.imports.aid_elevation_import import run
        stats = run(path, dry_run=dry_run)
        click.echo(f"Aid elevation {'DRY-RUN' if dry_run else 'committed'}:")
        for k, v in stats.items():
            click.echo(f"  {k:16}: {v}")

    @app.cli.command("sync-aid")
    @click.option("--aid", "aid_path", default="current data/Aid data.xlsx")
    @click.option("--dry-run", is_flag=True)
    def sync_aid_cmd(aid_path, dry_run):
        """Apply clean Aid master: adopt clean PMs/elevation + add missing wells."""
        from app.imports.aid_sync import run
        stats = run(aid_path, dry_run=dry_run)
        click.echo(f"Aid sync {'DRY-RUN (no changes)' if dry_run else 'committed'}:")
        for k, v in stats.items():
            click.echo(f"  {k:22}: {v}")

    @app.cli.command("export-production-unmatched")
    @click.option("--file", "path", default="current data/روند تولید چاه ها.xlsx")
    @click.option("--out", "out_path", default="production_unmatched_wells.xlsx")
    def export_production_unmatched_cmd(path, out_path):
        """Export wells in the production file that are absent from the registry."""
        from app.imports.production_unmatched_export import export
        stats = export(path, out_path)
        click.echo("Unmatched-wells report written:")
        for k, v in stats.items():
            click.echo(f"  {k}: {v}")

    @app.cli.command("import-pump-test")
    @click.option("--hafari", "hafari_path", default="current data/حفاری.xlsx")
    @click.option("--dry-run", is_flag=True)
    def import_pump_test_cmd(hafari_path, dry_run):
        """Import pump-test events (header hydraulics + steps) from حفاری.xlsx."""
        from app.imports.pump_test_import import run
        stats = run(hafari_path, dry_run=dry_run)
        click.echo(f"Pump-test import {'DRY-RUN' if dry_run else 'committed'}:")
        for k, v in stats.items():
            click.echo(f"  {k:16}: {v}")

    @app.cli.command("import-pump-select")
    @click.option("--file", "path", default="current data/14050308 مهندسی مجدد و انتخاب پمپ بزرگمهر.xlsx")
    @click.option("--dry-run", is_flag=True)
    def import_pump_select_cmd(path, dry_run):
        """Import pump selection / re-engineering records (matched by well name)."""
        from app.imports.pump_select_import import run
        stats = run(path, dry_run=dry_run)
        click.echo(f"Pump-select import {'DRY-RUN' if dry_run else 'committed'}:")
        for k, v in stats.items():
            click.echo(f"  {k:16}: {v}")

    @app.cli.command("import-rehab")
    @click.option("--file", "rehab_path", default="current data/گزارش بهسازی و پمپاژ.xlsx")
    @click.option("--dry-run", is_flag=True)
    def import_rehab_cmd(rehab_path, dry_run):
        """Import rehabilitation events (matched by well name)."""
        from app.imports.rehab_import import run
        stats = run(rehab_path, dry_run=dry_run)
        click.echo(f"Rehab import {'DRY-RUN' if dry_run else 'committed'}:")
        for k, v in stats.items():
            click.echo(f"  {k:16}: {v}")

    @app.cli.command("import-flow")
    @click.option("--aggregate", "tajmi_path", default="current data/تجمیعی (400-405).xlsx")
    @click.option("--dry-run", is_flag=True)
    def import_flow_cmd(tajmi_path, dry_run):
        """Import flow-metering (دبی‌سنجی) from تجمیعی; groups rows into tests+points."""
        from app.imports.flow_import import run
        stats = run(tajmi_path, dry_run=dry_run)
        click.echo(f"Flow import {'DRY-RUN' if dry_run else 'committed'}:")
        for k, v in stats.items():
            click.echo(f"  {k:16}: {v}")

    @app.cli.command("reconcile-wells")
    def reconcile_wells_cmd():
        """Cross-file well-identity reconciliation report (run now and at the end)."""
        from app.imports.reconcile import run
        report = run(
            "current data/تجمیعی (400-405).xlsx",
            "current data/نصب و کشیدن پمپ- تجمیعی.xlsx",
            "current data/دبی سنجی1405/**/*.xls",
        )
        click.echo(report)

    @app.cli.command("import-drilling")
    @click.option("--borwells", "borwells_path", default="current data/Borwells.xlsx")
    @click.option("--aggregate", "tajmi_path", default="current data/تجمیعی (400-405).xlsx")
    @click.option("--hafari", "hafari_path", default="current data/حفاری.xlsx")
    @click.option("--dry-run", is_flag=True)
    def import_drilling_cmd(borwells_path, tajmi_path, hafari_path, dry_run):
        """Import/refresh drilling events from Borwells + حفاری (links to wells)."""
        from app.imports.drilling_import import run
        stats = run(borwells_path, tajmi_path, hafari_path, dry_run=dry_run)
        click.echo(f"Drilling import {'DRY-RUN' if dry_run else 'committed'}:")
        for k, v in stats.items():
            click.echo(f"  {k:16}: {v}")

    @app.cli.command("seed-demo")
    def seed_demo():
        """Insert a few sample wells (around Mashhad) for demoing the dashboard/map."""
        from app.models.well import Well

        if db.session.scalar(db.select(db.func.count(Well.id))):
            click.echo("Wells already exist — skipping demo data.")
            return

        centers = {
            c.name: c.id
            for c in db.session.scalars(
                db.select(OrgUnit).filter_by(unit_type="center")
            ).all()
        }
        samples = [
            ("102433", "گلشهر ۱", "مرکز گلشهر", "in_circuit", 36.345, 59.470, "urban"),
            ("102320", "چمران ۳", "مرکز خیرآباد", "in_circuit", 36.290, 59.610, "urban"),
            ("102618", "امامیه ۱۳", "مرکز امامیه", "under_rehab", 36.360, 59.520, "urban"),
            ("102126", "آزاد شهر ۱", "مرکز دانشجو", "out", 36.310, 59.560, "urban"),
            ("10261", "آماده سازی ۱", "مرکز امامیه", "in_circuit", 36.370, 59.500, "urban"),
            ("102250", "۶۰۰ دستگاه", "مرکز امام علی", "relocated", 36.300, 59.580, "rural"),
        ]
        for pm, name, center, status, lat, lon, kind in samples:
            db.session.add(
                Well(
                    pm_code=pm, name=name, center_id=centers.get(center),
                    status=status, latitude=lat, longitude=lon,
                    utm_zone="40N", well_kind=kind, drill_year="1402",
                )
            )
        db.session.commit()
        click.echo(f"Inserted {len(samples)} demo wells.")



################################################################################
# FILE: extensions.py
################################################################################

"""Shared Flask extension instances (initialized in the app factory)."""
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_wtf import CSRFProtect

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()

login_manager.login_view = "auth.login"
login_manager.login_message = "برای دسترسی به این صفحه باید وارد شوید."
login_manager.login_message_category = "warning"



################################################################################
# FILE: security.py
################################################################################

"""Authorization helper: a decorator enforcing module x action permissions."""
from functools import wraps

from flask import abort
from flask_login import current_user, login_required


def permission_required(module, action):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if not current_user.has_permission(module, action):
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator



################################################################################
# FILE: workflow.py
################################################################################

"""Approval workflow engine for lifecycle event records.

States: draft -> submitted -> approved
                       \-> rejected -> (resubmit) -> submitted

Rules:
- A record is editable only while in `draft` or `rejected`.
- `approved` records are LOCKED; only a user with the module's `approve`
  permission may `revert` them back to `draft` for correction.
- Every transition is written to the audit log (RecordHistory).
"""
from datetime import datetime

from flask_login import current_user

from app.extensions import db
from app.models.audit import RecordHistory

DRAFT, SUBMITTED, APPROVED, REJECTED = "draft", "submitted", "approved", "rejected"
EDITABLE_STATES = {DRAFT, REJECTED}

BADGES = {
    DRAFT: ("پیش‌نویس", "secondary"),
    SUBMITTED: ("ثبت‌شده / در انتظار تأیید", "warning"),
    APPROVED: ("تأییدشده", "success"),
    REJECTED: ("برگشتی", "danger"),
}


class WorkflowError(Exception):
    """Raised on an invalid state transition."""


def badge(status):
    label, css = BADGES.get(status, (status or "—", "secondary"))
    return {"label": label, "css": css}


def is_editable(record):
    return getattr(record, "status", DRAFT) in EDITABLE_STATES


def _log(record, action, detail=None, user=None):
    uid = (user or current_user).id if (user or current_user) and \
        getattr(user or current_user, "is_authenticated", False) else None
    db.session.add(
        RecordHistory(
            entity_type=record.__tablename__,
            entity_id=record.id,
            action=action,
            user_id=uid,
            detail=detail,
        )
    )


def log_change(record, action, detail=None, user=None):
    """Public helper for create/update logging from routes."""
    _log(record, action, detail=detail, user=user)


def submit(record, user=None):
    if record.status not in (DRAFT, REJECTED):
        raise WorkflowError("فقط رکورد پیش‌نویس یا برگشتی قابل ثبت برای تأیید است.")
    actor = user or current_user
    record.status = SUBMITTED
    record.submitted_by_id = actor.id
    record.submitted_at = datetime.utcnow()
    record.reject_reason = None
    _log(record, "submit", user=user)


def approve(record, user=None):
    if record.status != SUBMITTED:
        raise WorkflowError("فقط رکورد ثبت‌شده قابل تأیید است.")
    actor = user or current_user
    record.status = APPROVED
    record.approved_by_id = actor.id
    record.approved_at = datetime.utcnow()
    _log(record, "approve", user=user)


def reject(record, reason, user=None):
    if record.status != SUBMITTED:
        raise WorkflowError("فقط رکورد ثبت‌شده قابل برگشت است.")
    record.status = REJECTED
    record.reject_reason = (reason or "").strip() or None
    _log(record, "reject", detail=record.reject_reason, user=user)


def revert_to_draft(record, user=None):
    """Unlock an approved record (or withdraw a submitted one) back to draft."""
    if record.status not in (APPROVED, SUBMITTED):
        raise WorkflowError("فقط رکورد تأییدشده یا ثبت‌شده قابل بازگردانی است.")
    record.status = DRAFT
    record.approved_by_id = None
    record.approved_at = None
    _log(record, "revert", user=user)



################################################################################
# FILE: blueprints\__init__.py
################################################################################




################################################################################
# FILE: blueprints\auth\__init__.py
################################################################################

from flask import Blueprint

bp = Blueprint("auth", __name__)

from app.blueprints.auth import routes  # noqa: E402,F401



################################################################################
# FILE: blueprints\auth\routes.py
################################################################################

from datetime import datetime

from flask import render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired

from app.extensions import db
from app.blueprints.auth import bp
from app.models.rbac import User, LoginLog

class LoginForm(FlaskForm):
    username = StringField("نام کاربری", validators=[DataRequired()])
    password = PasswordField("گذرواژه", validators=[DataRequired()])
    remember = BooleanField("مرا به خاطر بسپار")
    submit = SubmitField("ورود")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    form = LoginForm()
    if form.validate_on_submit():
        user = db.session.scalar(
            db.select(User).filter_by(username=form.username.data.strip())
        )
        if user is None or not user.check_password(form.password.data):
            flash("نام کاربری یا گذرواژه نادرست است.", "danger")
        elif not user.is_active:
            flash("این حساب غیرفعال است.", "warning")
        else:
            login_user(user, remember=form.remember.data)
            now = datetime.utcnow()
            ip = (request.headers.get("X-Forwarded-For", request.remote_addr) or "").split(",")[0].strip()
            agent = (request.user_agent.string or "")[:255]
            user.last_login_at = now
            user.last_login_ip = ip
            user.last_login_agent = agent
            log = LoginLog(user_id=user.id, login_at=now, ip_address=ip, user_agent=agent)
            db.session.add(log)
            db.session.commit()
            session["login_log_id"] = log.id
            next_page = request.args.get("next")
            return redirect(next_page or url_for("main.dashboard"))

    return render_template("auth/login.html", form=form)


@bp.route("/logout")
@login_required
def logout():
    log_id = session.pop("login_log_id", None)
    if log_id:
        log = db.session.get(LoginLog, log_id)
        if log and log.logout_at is None:
            log.logout_at = datetime.utcnow()
            db.session.commit()
    logout_user()
    flash("از سیستم خارج شدید.", "info")
    return redirect(url_for("auth.login"))



################################################################################
# FILE: blueprints\documents\__init__.py
################################################################################

from flask import Blueprint

bp = Blueprint("documents", __name__, url_prefix="/documents")

from app.blueprints.documents import routes  # noqa: E402,F401



################################################################################
# FILE: blueprints\documents\routes.py
################################################################################

"""Document/attachment upload, download and delete.

Files are validated against the allowed-extension allowlist, stored under
instance/uploads/ with a random UUID name, and served back with their original
filename. Entity links are polymorphic (entity_type, entity_id).
"""
import os
import uuid

from flask import (current_app, request, redirect, url_for, flash, abort,
                   send_from_directory)
from flask_login import current_user
from werkzeug.utils import secure_filename

from app.extensions import db
from app.blueprints.documents import bp
from app.security import permission_required
from app.models.attachment import Attachment

# where each entity type's page lives, to redirect back after up/delete
_BACK = {"well": ("wells.detail", "well_id")}


def _redirect_back(att_or_type, entity_id=None):
    etype = att_or_type.entity_type if isinstance(att_or_type, Attachment) else att_or_type
    eid = att_or_type.entity_id if isinstance(att_or_type, Attachment) else entity_id
    ep, arg = _BACK.get(etype, ("wells.detail", "well_id"))
    return redirect(url_for(ep, **{arg: eid}) + "#sec-docs")


def _allowed(filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext in current_app.config["ALLOWED_UPLOAD_EXT"], ext


@bp.route("/upload", methods=["POST"])
@permission_required("documents", "create")
def upload():
    etype = request.form.get("entity_type", "")
    eid = request.form.get("entity_id", type=int)
    if not etype or not eid:
        abort(400)
    f = request.files.get("file")
    if not f or not f.filename:
        flash("فایلی انتخاب نشده است.", "warning")
        return _redirect_back(etype, eid)
    ok, ext = _allowed(f.filename)
    if not ok:
        flash("نوع فایل مجاز نیست.", "danger")
        return _redirect_back(etype, eid)

    upload_dir = current_app.config["UPLOAD_DIR"]
    os.makedirs(upload_dir, exist_ok=True)
    stored = f"{uuid.uuid4().hex}.{ext}"
    f.save(os.path.join(upload_dir, stored))
    size = os.path.getsize(os.path.join(upload_dir, stored))

    att = Attachment(
        entity_type=etype, entity_id=eid,
        title=(request.form.get("title") or "").strip() or None,
        kind=request.form.get("kind") or "other",
        original_name=secure_filename(f.filename) or f"file.{ext}",
        stored_name=stored, content_type=f.mimetype, size_bytes=size,
        created_by_id=current_user.id)
    db.session.add(att)
    db.session.commit()
    flash("سند بارگذاری شد.", "success")
    return _redirect_back(att)


@bp.route("/<int:att_id>/download")
@permission_required("documents", "view")
def download(att_id):
    att = db.get_or_404(Attachment, att_id)
    return send_from_directory(
        current_app.config["UPLOAD_DIR"], att.stored_name,
        as_attachment=True, download_name=att.original_name)


@bp.route("/<int:att_id>/delete", methods=["POST"])
@permission_required("documents", "delete")
def delete(att_id):
    att = db.get_or_404(Attachment, att_id)
    path = os.path.join(current_app.config["UPLOAD_DIR"], att.stored_name)
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass
    back = _redirect_back(att)
    db.session.delete(att)
    db.session.commit()
    flash("سند حذف شد.", "info")
    return back


def attachments_for(entity_type, entity_id):
    return db.session.scalars(
        db.select(Attachment).filter_by(entity_type=entity_type, entity_id=entity_id)
        .order_by(Attachment.created_at.desc())).all()



################################################################################
# FILE: blueprints\drilling\__init__.py
################################################################################

from flask import Blueprint

bp = Blueprint("drilling", __name__)

from app.blueprints.drilling import routes  # noqa: E402,F401



################################################################################
# FILE: blueprints\drilling\routes.py
################################################################################

from flask import render_template, redirect, url_for, flash, request, abort
from flask_login import current_user
from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, TextAreaField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Optional

from app.extensions import db
from app.blueprints.drilling import bp
from app.security import permission_required
from app.utils.forms import JalaliDateField, PersianFloatField as FloatField
from app.models.well import Well
from app.models.drilling import Drilling
from app.models.audit import RecordHistory
from app.models.constants import REQUEST_TYPES, DRILL_METHODS
from app import workflow


class DrillingForm(FlaskForm):
    request_type = SelectField("نوع پروانه", choices=[("", "—")] + REQUEST_TYPES, validators=[Optional()])
    drill_method = SelectField("روش حفاری", choices=[("", "—")] + DRILL_METHODS, validators=[Optional()])
    executor = StringField("نام مجری", validators=[Optional()])
    contractor = StringField("پیمانکار", validators=[Optional()])
    supervisor = StringField("ناظر", validators=[Optional()])
    credit_source = StringField("محل تأمین اعتبار", validators=[Optional()])
    contract_no = StringField("شماره قرارداد", validators=[Optional()])
    contract_date = JalaliDateField("تاریخ قرارداد", validators=[Optional()])
    start_date = JalaliDateField("تاریخ استقرار دستگاه", validators=[Optional()])
    end_date = JalaliDateField("تاریخ پایان/ترخیص", validators=[Optional()])
    well_depth_permit = FloatField("عمق چاه در پروانه", validators=[Optional()])
    well_depth_actual = FloatField("عمق حفاری واقعی", validators=[Optional()])
    casing_diameter_in = FloatField("قطر لوله جدار (اینچ)", validators=[Optional()])
    casing_total_len = FloatField("طول کلی لوله‌گذاری", validators=[Optional()])
    steel_blank_len = FloatField("لوله فولادی ساده", validators=[Optional()])
    steel_screen_len = FloatField("لوله فولادی مشبک", validators=[Optional()])
    upvc_blank_len = FloatField("لوله UPVC ساده", validators=[Optional()])
    upvc_screen_len = FloatField("لوله UPVC مشبک", validators=[Optional()])
    transition_len = FloatField("قطعه تبدیلی", validators=[Optional()])
    static_level = FloatField("سطح استاتیک", validators=[Optional()])
    max_yield_lps = FloatField("حداکثر آبدهی (l/s)", validators=[Optional()])
    proposed_discharge_lps = FloatField("دبی پیشنهادی (l/s)", validators=[Optional()])
    dynamic_at_proposed = FloatField("سطح دینامیک در دبی پیشنهادی", validators=[Optional()])
    drawdown = FloatField("مقدار افت", validators=[Optional()])
    coeff_a = FloatField("ضریب a", validators=[Optional()])
    coeff_b = FloatField("ضریب b", validators=[Optional()])
    videometry_done = BooleanField("ویدئومتری انجام شده")
    address = StringField("آدرس", validators=[Optional()])
    notes = TextAreaField("توضیحات", validators=[Optional()])
    submit = SubmitField("ذخیره")


FIELDS = [
    "request_type", "drill_method", "executor", "contractor", "supervisor",
    "credit_source", "contract_no", "contract_date", "start_date", "end_date",
    "well_depth_permit", "well_depth_actual", "casing_diameter_in", "casing_total_len",
    "steel_blank_len", "steel_screen_len", "upvc_blank_len", "upvc_screen_len",
    "transition_len", "static_level", "max_yield_lps", "proposed_discharge_lps",
    "dynamic_at_proposed", "drawdown", "coeff_a", "coeff_b", "videometry_done",
    "address", "notes",
]


def _apply(form, rec):
    for f in FIELDS:
        setattr(rec, f, getattr(form, f).data)


@bp.route("/wells/<int:well_id>/drilling/new", methods=["GET", "POST"])
@permission_required("drilling", "create")
def create(well_id):
    well = db.get_or_404(Well, well_id)
    form = DrillingForm()
    if form.validate_on_submit():
        rec = Drilling(well_id=well.id, created_by_id=current_user.id)
        _apply(form, rec)
        db.session.add(rec)
        db.session.flush()
        workflow.log_change(rec, "create")
        db.session.commit()
        flash("رویداد حفاری ثبت شد (پیش‌نویس).", "success")
        return redirect(url_for("drilling.detail", record_id=rec.id))
    return render_template("drilling/form.html", form=form, well=well, title="ثبت حفاری")


@bp.route("/drilling/<int:record_id>")
@permission_required("drilling", "view")
def detail(record_id):
    rec = db.get_or_404(Drilling, record_id)
    history = db.session.scalars(
        db.select(RecordHistory)
        .filter_by(entity_type="drilling", entity_id=rec.id)
        .order_by(RecordHistory.timestamp.desc())
    ).all()
    return render_template(
        "drilling/detail.html",
        rec=rec, well=rec.well, history=history,
        req_labels=dict(REQUEST_TYPES), method_labels=dict(DRILL_METHODS),
        editable=workflow.is_editable(rec),
    )


@bp.route("/drilling/<int:record_id>/edit", methods=["GET", "POST"])
@permission_required("drilling", "edit")
def edit(record_id):
    rec = db.get_or_404(Drilling, record_id)
    if not workflow.is_editable(rec):
        flash("این رکورد تأیید/ثبت شده و قفل است؛ ابتدا باید به پیش‌نویس بازگردانده شود.", "warning")
        return redirect(url_for("drilling.detail", record_id=rec.id))
    form = DrillingForm(obj=rec)
    if form.validate_on_submit():
        _apply(form, rec)
        rec.updated_by_id = current_user.id
        workflow.log_change(rec, "update")
        db.session.commit()
        flash("رویداد حفاری به‌روزرسانی شد.", "success")
        return redirect(url_for("drilling.detail", record_id=rec.id))
    return render_template("drilling/form.html", form=form, well=rec.well, title="ویرایش حفاری")


@bp.route("/drilling/<int:record_id>/delete", methods=["POST"])
@permission_required("drilling", "delete")
def delete(record_id):
    rec = db.get_or_404(Drilling, record_id)
    well_id = rec.well_id
    db.session.delete(rec)
    db.session.commit()
    flash("رویداد حفاری حذف شد.", "info")
    return redirect(url_for("wells.detail", well_id=well_id))


# --- workflow transitions ---
def _transition(record_id, fn, perm_action, success_msg, **kwargs):
    rec = db.get_or_404(Drilling, record_id)
    if not current_user.has_permission("drilling", perm_action):
        abort(403)
    try:
        fn(rec, **kwargs)
        db.session.commit()
        flash(success_msg, "success")
    except workflow.WorkflowError as e:
        db.session.rollback()
        flash(str(e), "danger")
    return redirect(url_for("drilling.detail", record_id=record_id))


@bp.route("/drilling/<int:record_id>/submit", methods=["POST"])
def submit(record_id):
    return _transition(record_id, workflow.submit, "edit", "برای تأیید ثبت شد.")


@bp.route("/drilling/<int:record_id>/approve", methods=["POST"])
def approve(record_id):
    return _transition(record_id, workflow.approve, "approve", "رکورد تأیید شد.")


@bp.route("/drilling/<int:record_id>/reject", methods=["POST"])
def reject(record_id):
    reason = request.form.get("reason", "")
    return _transition(record_id, workflow.reject, "approve", "رکورد برگشت داده شد.", reason=reason)


@bp.route("/drilling/<int:record_id>/revert", methods=["POST"])
def revert(record_id):
    return _transition(record_id, workflow.revert_to_draft, "approve", "به پیش‌نویس بازگردانده شد.")



################################################################################
# FILE: blueprints\exports\__init__.py
################################################################################

from flask import Blueprint

bp = Blueprint("exports", __name__, url_prefix="/exports")

from app.blueprints.exports import routes  # noqa: E402,F401



################################################################################
# FILE: blueprints\exports\routes.py
################################################################################

"""Data export / review section.

Lets an authorized user download the full dataset as Excel for offline review —
in particular to spot duplicate wells (variants of the same physical well such as
«ابوطالب 1 ق» / «ابوطالب 1»), which share a `گروه تکراری` key here.
"""
from datetime import datetime
from io import BytesIO

import pandas as pd
from flask import render_template, send_file

from app.extensions import db
from app.blueprints.exports import bp
from app.security import permission_required
from app.services import data_export

_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _xlsx(sheets):
    """sheets: list of (sheet_name, DataFrame) -> BytesIO of an .xlsx workbook."""
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xl:
        for name, df in sheets:
            df.to_excel(xl, sheet_name=name, index=False)
            ws = xl.sheets[name]
            for col in ws.columns:
                width = max((len(str(c.value)) for c in col if c.value is not None), default=10)
                ws.column_dimensions[col[0].column_letter].width = min(max(width + 2, 12), 40)
    buf.seek(0)
    return buf


def _send(buf, prefix):
    stamp = datetime.now().strftime("%Y%m%d")
    return send_file(buf, as_attachment=True, mimetype=_MIME,
                     download_name=f"{prefix}_{stamp}.xlsx")


@bp.route("/")
@permission_required("reports", "view")
def index():
    from app.models.well import Well
    from app.models.production import MonthlyProduction as MP
    df = data_export.wells_df()
    dup_groups = int((df["تعداد در گروه"] > 1).sum())
    dup_group_count = df[df["تعداد در گروه"] > 1]["گروه تکراری"].nunique()
    stats = {
        "wells": int(db.session.scalar(db.select(db.func.count(Well.id))) or 0),
        "dup_rows": dup_groups,
        "dup_groups": int(dup_group_count),
        "production_rows": int(db.session.scalar(db.select(db.func.count(MP.id))) or 0),
    }
    return render_template("exports/index.html", stats=stats)


@bp.route("/wells.xlsx")
@permission_required("reports", "view")
def wells_xlsx():
    return _send(_xlsx([("چاه‌ها", data_export.wells_df())]), "wells")


@bp.route("/duplicates.xlsx")
@permission_required("reports", "view")
def duplicates_xlsx():
    return _send(_xlsx([("تکراری‌های مشکوک", data_export.duplicates_df())]), "duplicates")


@bp.route("/production.xlsx")
@permission_required("reports", "view")
def production_xlsx():
    return _send(_xlsx([("تولید ماهانه", data_export.production_df())]), "production")


@bp.route("/all.xlsx")
@permission_required("reports", "view")
def all_xlsx():
    sheets = [
        ("چاه‌ها", data_export.wells_df()),
        ("تکراری‌های مشکوک", data_export.duplicates_df()),
        ("تولید ماهانه", data_export.production_df()),
    ]
    return _send(_xlsx(sheets), "all_data")



################################################################################
# FILE: blueprints\finance\__init__.py
################################################################################

from flask import Blueprint

bp = Blueprint("finance", __name__, url_prefix="/finance")

from app.blueprints.finance import routes  # noqa: E402,F401


################################################################################
# FILE: blueprints\finance\routes.py
################################################################################

"""ماژول صورت‌وضعیت مالی — فاز ۲: فهرست + فرم + جزئیات."""
from flask import render_template, redirect, url_for, flash
from flask_login import current_user
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, SubmitField
from wtforms.validators import Optional

from app.extensions import db
from app.blueprints.finance import bp
from app.security import permission_required
from app.utils.forms import JalaliDateField, PersianFloatField
from app.models.well import Well
from app.models.finance import FinanceStatement

OP_TYPES = [("", "—"), ("بهسازی", "بهسازی"), ("آزمایش پمپاژ", "آزمایش پمپاژ"),
            ("حفاری", "حفاری"), ("سایر", "سایر")]
KINDS = [("", "—"), ("موقت", "موقت"), ("قطعی", "قطعی"),
         ("وضعیت ۱", "وضعیت ۱"), ("وضعیت ۲", "وضعیت ۲"), ("وضعیت ۳", "وضعیت ۳")]


class StatementForm(FlaskForm):
    op_type = SelectField("نوع عملیات", choices=OP_TYPES, validators=[Optional()])
    op_description = TextAreaField("شرح عملیات (موضوع)", validators=[Optional()])
    contractor = StringField("پیمانکار", validators=[Optional()])
    contract_no = StringField("شماره قرارداد", validators=[Optional()])
    statement_no = StringField("شماره صورت‌وضعیت", validators=[Optional()])
    statement_kind = SelectField("نوع وضعیت", choices=KINDS, validators=[Optional()])
    statement_date = JalaliDateField("تاریخ صورت‌وضعیت", validators=[Optional()])
    coef_region = PersianFloatField("ضریب منطقه", validators=[Optional()])
    coef_overhead = PersianFloatField("ضریب بالاسری", validators=[Optional()])
    coef_contract = PersianFloatField("ضریب پیمان", validators=[Optional()])
    workshop_setup = PersianFloatField("تجهیز کارگاه (ریال)", validators=[Optional()])
    total_before = PersianFloatField("مبلغ کل قبل از ضرایب (ریال)", validators=[Optional()])
    total_after = PersianFloatField("مبلغ کل پس از ضرایب (ریال)", validators=[Optional()])
    notes = TextAreaField("توضیحات", validators=[Optional()])
    submit = SubmitField("ذخیره")


FIELDS = ["op_type", "op_description", "contractor", "contract_no", "statement_no", "statement_kind",
          "statement_date", "coef_region", "coef_overhead", "coef_contract",
          "workshop_setup", "total_before", "total_after", "notes"]


def _apply(form, rec):
    for f in FIELDS:
        setattr(rec, f, getattr(form, f).data if getattr(form, f).data != "" else None)


@bp.route("/")
@permission_required("finance", "view")
def index():
    statements = db.session.scalars(
        db.select(FinanceStatement).order_by(FinanceStatement.statement_date.desc())
    ).all()
    return render_template("finance/index.html", statements=statements)


@bp.route("/well/<int:well_id>/new", methods=["GET", "POST"])
@permission_required("finance", "create")
def create(well_id):
    well = db.get_or_404(Well, well_id)
    form = StatementForm()
    if form.validate_on_submit():
        rec = FinanceStatement(well_id=well.id, created_by_id=current_user.id, source="manual")
        _apply(form, rec)
        db.session.add(rec)
        db.session.commit()
        flash("صورت‌وضعیت ثبت شد.", "success")
        return redirect(url_for("finance.detail", record_id=rec.id))
    return render_template("finance/form.html", form=form, well=well, title="ثبت صورت‌وضعیت")


@bp.route("/<int:record_id>")
@permission_required("finance", "view")
def detail(record_id):
    rec = db.get_or_404(FinanceStatement, record_id)
    # تجمیع سهم هر چاه از آیتم‌های این سند (بر اساس تخصیص‌ها + ضریب بالاسری)
    ovh = rec.coef_overhead or 1.0
    agg = {}
    for it in rec.items:
        amt = (it.total_amount or 0) * ovh
        allocs = list(it.allocations)
        tq = sum((a.quantity or 0) for a in allocs)
        if not tq:
            continue
        for a in allocs:
            key = a.well_id if a.well_id else ("name:" + (a.well_name or "?"))
            row = agg.setdefault(key, {
                "well_id": a.well_id,
                "name": (a.well.name if a.well else a.well_name) or "—",
                "qty": 0.0, "cost": 0.0})
            row["qty"] += a.quantity or 0
            row["cost"] += amt * (a.quantity or 0) / tq
    wells_breakdown = sorted(agg.values(), key=lambda r: r["cost"], reverse=True)
    return render_template("finance/detail.html", rec=rec, well=rec.well,
                           wells_breakdown=wells_breakdown)


@bp.route("/<int:record_id>/edit", methods=["GET", "POST"])
@permission_required("finance", "edit")
def edit(record_id):
    rec = db.get_or_404(FinanceStatement, record_id)
    form = StatementForm(obj=rec)
    if form.validate_on_submit():
        _apply(form, rec)
        rec.updated_by_id = current_user.id
        db.session.commit()
        flash("صورت‌وضعیت به‌روزرسانی شد.", "success")
        return redirect(url_for("finance.detail", record_id=rec.id))
    return render_template("finance/form.html", form=form, well=rec.well, title="ویرایش صورت‌وضعیت")


@bp.route("/<int:record_id>/delete", methods=["POST"])
@permission_required("finance", "delete")
def delete(record_id):
    rec = db.get_or_404(FinanceStatement, record_id)
    db.session.delete(rec)
    db.session.commit()
    flash("صورت‌وضعیت حذف شد.", "info")
    return redirect(url_for("finance.index"))
# ---------- آیتم‌های هزینه (فاز ۳) ----------
from app.models.finance import FinanceItem


class ItemForm(FlaskForm):
    category = StringField("دسته (شرح عملیات کلی)", validators=[Optional()])
    row_no = StringField("شماره ردیف", validators=[Optional()])
    description = TextAreaField("شرح تفصیلی", validators=[Optional()])
    unit = StringField("واحد", validators=[Optional()])
    contract_qty = PersianFloatField("تعداد قرارداد", validators=[Optional()])
    quantity = PersianFloatField("مقدار", validators=[Optional()])
    unit_price = PersianFloatField("مبلغ واحد (ریال)", validators=[Optional()])
    coefficient = PersianFloatField("ضریب", validators=[Optional()])
    total_amount = PersianFloatField("مبلغ کل (ریال)", validators=[Optional()])
    submit = SubmitField("ذخیره")


ITEM_FIELDS = ["category", "row_no", "description", "unit", "contract_qty",
               "quantity", "unit_price", "coefficient", "total_amount"]


@bp.route("/<int:statement_id>/item/new", methods=["GET", "POST"])
@permission_required("finance", "edit")
def item_create(statement_id):
    st = db.get_or_404(FinanceStatement, statement_id)
    form = ItemForm()
    if form.validate_on_submit():
        it = FinanceItem(statement_id=st.id, created_by_id=current_user.id)
        for f in ITEM_FIELDS:
            setattr(it, f, getattr(form, f).data)
        db.session.add(it)
        db.session.commit()
        flash("آیتم هزینه افزوده شد.", "success")
        return redirect(url_for("finance.detail", record_id=st.id))
    return render_template("finance/item_form.html", form=form, st=st, title="افزودن آیتم هزینه")


@bp.route("/item/<int:item_id>/edit", methods=["GET", "POST"])
@permission_required("finance", "edit")
def item_edit(item_id):
    it = db.get_or_404(FinanceItem, item_id)
    form = ItemForm(obj=it)
    if form.validate_on_submit():
        for f in ITEM_FIELDS:
            setattr(it, f, getattr(form, f).data)
        db.session.commit()
        flash("آیتم به‌روزرسانی شد.", "success")
        return redirect(url_for("finance.detail", record_id=it.statement_id))
    return render_template("finance/item_form.html", form=form, st=it.statement,
                           title="ویرایش آیتم هزینه", item_id=it.id)


@bp.route("/item/<int:item_id>/delete", methods=["POST"])
@permission_required("finance", "edit")
def item_delete(item_id):
    it = db.get_or_404(FinanceItem, item_id)
    sid = it.statement_id
    db.session.delete(it)
    db.session.commit()
    flash("آیتم حذف شد.", "info")
    return redirect(url_for("finance.detail", record_id=sid))

# ---------- گزارش‌ها و داشبورد مالی (فاز ۵) ----------
from io import BytesIO
from datetime import datetime
from collections import defaultdict

import pandas as pd
from flask import request, send_file

from app.models.finance import FinanceItemAllocation

_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _finance_report(op_type=None, contractor=None, statement_id=None, well_id=None):
    """داده‌ی گزارش مالی را با اعمال فیلترها می‌سازد.

    خروجی: dict شامل سه گروه‌بندی (چاه/سند/نوع عملیات)، KPIها و ردیف‌های جدول.
    هزینه‌ی هر آیتم بین چاه‌های تخصیص‌یافته به نسبت مقدار تقسیم می‌شود.
    """
    q = db.select(FinanceStatement)
    if op_type:
        q = q.where(FinanceStatement.op_type == op_type)
    if contractor:
        q = q.where(FinanceStatement.contractor == contractor)
    if statement_id:
        q = q.where(FinanceStatement.id == statement_id)
    statements = db.session.scalars(q).all()

    by_optype = defaultdict(float)
    by_statement = []                 # (label, total)
    well_cost = defaultdict(float)    # well_name -> cost
    well_meta = {}                    # well_name -> well_id
    well_docs = defaultdict(set)      # well_name -> {statement_id}
    unallocated = 0.0
    grand = 0.0

    for st in statements:
        stmt_total = 0.0
        # ضریب بالاسری در سطح سند اعمال می‌شود تا مبالغ به «مبلغ صورت‌وضعیت» برسند
        ovh = st.coef_overhead or 1.0
        for it in st.items:
            amt = (it.total_amount or 0.0) * ovh
            allocs = list(it.allocations)
            tq = sum((a.quantity or 0) for a in allocs)
            if tq > 0:
                for a in allocs:
                    if well_id and a.well_id != well_id:
                        continue
                    share = amt * (a.quantity or 0) / tq
                    name = a.well.name if a.well else (a.well_name or "—")
                    well_cost[name] += share
                    well_meta[name] = a.well_id
                    well_docs[name].add(st.id)
                    stmt_total += share
            elif st.well_id:            # سند تک‌چاهی (ثبت دستی)
                if well_id and st.well_id != well_id:
                    continue
                name = st.well.name if st.well else "—"
                well_cost[name] += amt
                well_meta[name] = st.well_id
                well_docs[name].add(st.id)
                stmt_total += amt
            else:                        # آیتم بدون تخصیص (مثل ویدئومتری)
                if not well_id:
                    unallocated += amt
                    stmt_total += amt
        # تجهیز کارگاه: هزینه‌ی ثابت سند، به هیچ چاهی تخصیص نمی‌یابد
        if not well_id and st.workshop_setup:
            unallocated += st.workshop_setup
            stmt_total += st.workshop_setup
        if stmt_total:
            by_optype[st.op_type or "نامشخص"] += stmt_total
            label = " ".join(x for x in [st.op_type, st.statement_kind,
                             ("— " + (st.contractor or st.contract_no or f"#{st.id}"))] if x)
            by_statement.append((label, stmt_total))
            grand += stmt_total

    rows = [{
        "well": n, "well_id": well_meta.get(n),
        "cost": round(c), "docs": len(well_docs[n]),
        "matched": well_meta.get(n) is not None,
    } for n, c in well_cost.items()]
    rows.sort(key=lambda r: r["cost"], reverse=True)
    by_statement.sort(key=lambda x: x[1], reverse=True)

    return {
        "rows": rows,
        "by_optype": dict(sorted(by_optype.items(), key=lambda x: x[1], reverse=True)),
        "by_statement": by_statement,
        "top_wells": {r["well"]: r["cost"] for r in rows[:15]},
        "grand": round(grand),
        "unallocated": round(unallocated),
        "well_count": len(rows),
        "doc_count": len(statements),
    }


def _filter_options():
    op_types = [x for x in db.session.scalars(
        db.select(FinanceStatement.op_type).distinct()).all() if x]
    contractors = [x for x in db.session.scalars(
        db.select(FinanceStatement.contractor).distinct()).all() if x]
    statements = db.session.scalars(
        db.select(FinanceStatement).order_by(FinanceStatement.op_type,
                                             FinanceStatement.statement_kind)).all()
    # چاه‌هایی که در مالی هزینه دارند
    wids = set(db.session.scalars(
        db.select(FinanceItemAllocation.well_id).distinct()).all())
    wids |= set(db.session.scalars(
        db.select(FinanceStatement.well_id).distinct()).all())
    wids.discard(None)
    wells = db.session.scalars(
        db.select(Well).where(Well.id.in_(wids)).order_by(Well.name)).all() if wids else []
    return op_types, contractors, statements, wells


def _current_filters():
    def _int(v):
        try:
            return int(v)
        except (TypeError, ValueError):
            return None
    return {
        "op_type": request.args.get("op_type") or None,
        "contractor": request.args.get("contractor") or None,
        "statement_id": _int(request.args.get("statement_id")),
        "well_id": _int(request.args.get("well_id")),
    }


@bp.route("/reports")
@permission_required("finance", "view")
def reports():
    f = _current_filters()
    data = _finance_report(**f)
    op_types, contractors, statements, wells = _filter_options()
    cur_qs = {k: v for k, v in f.items() if v}   # برای لینک خروجی اکسل
    return render_template("finance/reports.html", data=data, cur=f, cur_qs=cur_qs,
                           op_types=op_types, contractors=contractors,
                           statements=statements, wells=wells)


@bp.route("/reports/export")
@permission_required("finance", "view")
def reports_export():
    f = _current_filters()
    data = _finance_report(**f)
    df = pd.DataFrame([{
        "چاه": r["well"],
        "هزینه (ریال)": r["cost"],
        "تعداد سند": r["docs"],
        "تطبیق با سامانه": "بله" if r["matched"] else "خیر",
    } for r in data["rows"]])
    by_stmt = pd.DataFrame([{"سند": l, "مبلغ (ریال)": round(v)}
                            for l, v in data["by_statement"]])
    by_op = pd.DataFrame([{"نوع عملیات": k, "مبلغ (ریال)": round(v)}
                          for k, v in data["by_optype"].items()])

    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xl:
        (df if not df.empty else pd.DataFrame({"—": []})).to_excel(
            xl, sheet_name="هزینه هر چاه", index=False)
        (by_stmt if not by_stmt.empty else pd.DataFrame({"—": []})).to_excel(
            xl, sheet_name="به تفکیک سند", index=False)
        (by_op if not by_op.empty else pd.DataFrame({"—": []})).to_excel(
            xl, sheet_name="به تفکیک عملیات", index=False)
        for name in xl.sheets:
            ws = xl.sheets[name]
            for col in ws.columns:
                w = max((len(str(c.value)) for c in col if c.value is not None), default=10)
                ws.column_dimensions[col[0].column_letter].width = min(max(w + 2, 12), 45)
    buf.seek(0)
    stamp = datetime.now().strftime("%Y%m%d")
    return send_file(buf, as_attachment=True, mimetype=_XLSX_MIME,
                     download_name=f"finance_report_{stamp}.xlsx")


################################################################################
# FILE: blueprints\gis\__init__.py
################################################################################

from flask import Blueprint

bp = Blueprint("gis", __name__, url_prefix="/gis")

from app.blueprints.gis import routes  # noqa: E402,F401



################################################################################
# FILE: blueprints\gis\routes.py
################################################################################

from flask import render_template, jsonify
from flask_login import login_required

from app.extensions import db
from app.blueprints.gis import bp
from app.security import permission_required
from app.models.well import Well
from app.models.constants import WELL_STATUSES


@bp.route("/map")
@login_required
def map():
    return render_template("gis/map.html")


@bp.route("/analysis")
@permission_required("reports", "view")
def analysis():
    return render_template("gis/analysis.html")


@bp.route("/analysis.json")
@permission_required("reports", "view")
def analysis_json():
    from app.services import spatial
    return jsonify({"points": spatial.metric_points()})


@bp.route("/piezometric.json")
@permission_required("reports", "view")
def piezometric_json():
    from app.services import spatial
    return jsonify(spatial.piezometric_grid() or {})


@bp.route("/interference.json")
@permission_required("reports", "view")
def interference_json():
    from flask import request
    from app.services import spatial
    thr = request.args.get("threshold", 400, type=int)
    return jsonify(spatial.interference(threshold_m=thr))


@bp.route("/suitability.json")
@permission_required("reports", "view")
def suitability_json():
    from app.services import spatial
    return jsonify(spatial.suitability_grid() or {})


@bp.route("/wells.geojson")
@permission_required("wells", "view")
def wells_geojson():
    """Wells that have coordinates, as GeoJSON for Leaflet (themed)."""
    status_labels = dict(WELL_STATUSES)
    from app.models.production import MonthlyProduction as MP
    spec_energy = {}
    for mp in db.session.scalars(db.select(MP).where(MP.energy_kwh.isnot(None))).all():
        se = mp.specific_energy
        if se is not None:
            spec_energy[mp.well_id] = se

    wells = db.session.scalars(
        db.select(Well).where(Well.latitude.isnot(None), Well.longitude.isnot(None))
    ).all()
    features = []
    for w in wells:
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [w.longitude, w.latitude]},
            "properties": {
                "id": w.id, "pm_code": w.display_pm, "name": w.name,
                "status": status_labels.get(w.status, w.status),
                "status_key": w.status or "unknown",
                "zone": w.zone or "", "reservoir": w.destination_reservoir or "",
                "office": w.office.name if w.office else "",
                "elevation": w.ground_elevation,
                "specific_energy": spec_energy.get(w.id),
            },
        })
    return jsonify({"type": "FeatureCollection", "features": features})



################################################################################
# FILE: blueprints\install\__init__.py
################################################################################

from flask import Blueprint

bp = Blueprint("install", __name__)

from app.blueprints.install import routes  # noqa: E402,F401



################################################################################
# FILE: blueprints\install\routes.py
################################################################################

from flask import render_template, redirect, url_for, flash, request, abort
from flask_login import current_user
from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, TextAreaField, BooleanField, SubmitField
from wtforms.validators import Optional

from app.extensions import db
from app.blueprints.install import bp
from app.security import permission_required
from app.utils.forms import (
    JalaliDateField, PersianFloatField as FloatField, PersianIntegerField as IntegerField,
)
from app.models.well import Well
from app.models.pump_asset import PumpInstallation, Supplier
from app.models.audit import RecordHistory
from app.models.constants import EQUIP_CONDITIONS
from app import workflow


def get_or_create_supplier(name, kind=None):
    from app.models.constants import canonical_supplier
    name = canonical_supplier(name)
    if not name:
        return None
    s = db.session.scalar(db.select(Supplier).filter_by(name=name))
    if s is None:
        s = Supplier(name=name, kind=kind)
        db.session.add(s)
        db.session.flush()
    elif kind and not s.kind:
        s.kind = kind
    return s


class InstallForm(FlaskForm):
    install_no = IntegerField("شماره نصب", validators=[Optional()])
    install_date = JalaliDateField("تاریخ نصب", validators=[Optional()])
    pull_date = JalaliDateField("تاریخ کشیدن", validators=[Optional()])
    motor_power_kw = FloatField("توان موتور (kW)", validators=[Optional()])
    motor_condition = SelectField("موتور", choices=[("", "—")] + EQUIP_CONDITIONS, validators=[Optional()])
    pump_type = StringField("تیپ پمپ", validators=[Optional()])
    pump_stages = IntegerField("طبقه", validators=[Optional()])
    pump_condition = SelectField("پمپ", choices=[("", "—")] + EQUIP_CONDITIONS, validators=[Optional()])
    manufacturer_name = StringField("سازنده", validators=[Optional()])
    contractor_name = StringField("پیمانکار", validators=[Optional()])
    install_depth_m = FloatField("عمق نصب", validators=[Optional()])
    well_depth_m = FloatField("عمق چاه", validators=[Optional()])
    static_level = FloatField("سطح استاتیک", validators=[Optional()])
    dynamic_level = FloatField("سطح دینامیک", validators=[Optional()])
    route_loss = FloatField("تلفات مسیر", validators=[Optional()])
    grid_pressure_m = FloatField("فشار شبکه", validators=[Optional()])
    work_shift = StringField("شیفت کاری", validators=[Optional()])
    removal_reason = StringField("علت کشیدن", validators=[Optional()])
    fault_by_operator = TextAreaField("شرح خرابی (بهره‌بردار)", validators=[Optional()])
    fault_by_workshop = TextAreaField("شرح خرابی (کارگاه مکانیک)", validators=[Optional()])
    pm_form_registered = BooleanField("فرم نصب در PM ثبت شده")
    notes = TextAreaField("توضیحات", validators=[Optional()])
    submit = SubmitField("ذخیره")


SIMPLE_FIELDS = [
    "install_no", "install_date", "pull_date", "motor_power_kw", "motor_condition",
    "pump_type", "pump_stages", "pump_condition", "install_depth_m", "well_depth_m",
    "static_level", "dynamic_level", "route_loss", "grid_pressure_m", "work_shift",
    "removal_reason", "fault_by_operator", "fault_by_workshop", "pm_form_registered", "notes",
]


def _apply(form, rec):
    for f in SIMPLE_FIELDS:
        setattr(rec, f, getattr(form, f).data)
    man = get_or_create_supplier(form.manufacturer_name.data, "manufacturer")
    con = get_or_create_supplier(form.contractor_name.data, "contractor")
    rec.manufacturer_id = man.id if man else None
    rec.contractor_id = con.id if con else None


@bp.route("/wells/<int:well_id>/install/new", methods=["GET", "POST"])
@permission_required("install", "create")
def create(well_id):
    well = db.get_or_404(Well, well_id)
    form = InstallForm()
    if form.validate_on_submit():
        rec = PumpInstallation(well_id=well.id, created_by_id=current_user.id)
        _apply(form, rec)
        db.session.add(rec)
        db.session.flush()
        workflow.log_change(rec, "create")
        db.session.commit()
        flash("نصب/کشیدن پمپ ثبت شد (پیش‌نویس).", "success")
        return redirect(url_for("install.detail", record_id=rec.id))
    return render_template("install/form.html", form=form, well=well, title="ثبت نصب/کشیدن پمپ")


@bp.route("/install/<int:record_id>")
@permission_required("install", "view")
def detail(record_id):
    rec = db.get_or_404(PumpInstallation, record_id)
    history = db.session.scalars(
        db.select(RecordHistory).filter_by(entity_type="pump_installations", entity_id=rec.id)
        .order_by(RecordHistory.timestamp.desc())
    ).all()
    return render_template("install/detail.html", rec=rec, well=rec.well,
                           history=history, editable=workflow.is_editable(rec))


@bp.route("/install/<int:record_id>/edit", methods=["GET", "POST"])
@permission_required("install", "edit")
def edit(record_id):
    rec = db.get_or_404(PumpInstallation, record_id)
    if not workflow.is_editable(rec):
        flash("این رکورد قفل است؛ ابتدا باید به پیش‌نویس بازگردانده شود.", "warning")
        return redirect(url_for("install.detail", record_id=rec.id))
    form = InstallForm(obj=rec)
    if request.method == "GET":
        form.manufacturer_name.data = rec.manufacturer.name if rec.manufacturer else ""
        form.contractor_name.data = rec.contractor.name if rec.contractor else ""
    if form.validate_on_submit():
        _apply(form, rec)
        rec.updated_by_id = current_user.id
        workflow.log_change(rec, "update")
        db.session.commit()
        flash("نصب/کشیدن به‌روزرسانی شد.", "success")
        return redirect(url_for("install.detail", record_id=rec.id))
    return render_template("install/form.html", form=form, well=rec.well, title="ویرایش نصب/کشیدن")


@bp.route("/install/<int:record_id>/delete", methods=["POST"])
@permission_required("install", "delete")
def delete(record_id):
    rec = db.get_or_404(PumpInstallation, record_id)
    well_id = rec.well_id
    db.session.delete(rec)
    db.session.commit()
    flash("رکورد نصب/کشیدن حذف شد.", "info")
    return redirect(url_for("wells.detail", well_id=well_id))


def _transition(record_id, fn, perm_action, msg, **kw):
    rec = db.get_or_404(PumpInstallation, record_id)
    if not current_user.has_permission("install", perm_action):
        abort(403)
    try:
        fn(rec, **kw)
        db.session.commit()
        flash(msg, "success")
    except workflow.WorkflowError as e:
        db.session.rollback()
        flash(str(e), "danger")
    return redirect(url_for("install.detail", record_id=record_id))


@bp.route("/install/<int:record_id>/submit", methods=["POST"])
def submit(record_id):
    return _transition(record_id, workflow.submit, "edit", "برای تأیید ثبت شد.")


@bp.route("/install/<int:record_id>/approve", methods=["POST"])
def approve(record_id):
    return _transition(record_id, workflow.approve, "approve", "تأیید شد.")


@bp.route("/install/<int:record_id>/reject", methods=["POST"])
def reject(record_id):
    return _transition(record_id, workflow.reject, "approve", "برگشت داده شد.",
                       reason=request.form.get("reason", ""))


@bp.route("/install/<int:record_id>/revert", methods=["POST"])
def revert(record_id):
    return _transition(record_id, workflow.revert_to_draft, "approve", "به پیش‌نویس بازگردانده شد.")



################################################################################
# FILE: blueprints\main\__init__.py
################################################################################

from flask import Blueprint

bp = Blueprint("main", __name__)

from app.blueprints.main import routes  # noqa: E402,F401



################################################################################
# FILE: blueprints\main\routes.py
################################################################################

import re
from datetime import datetime
from io import BytesIO

from flask import render_template, request, flash, redirect, url_for, send_file
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import (StringField, PasswordField, BooleanField, TextAreaField,
                     SelectMultipleField, SubmitField)
from wtforms.validators import DataRequired, Optional, Length
from app.extensions import db
from app.blueprints.main import bp
from app.security import permission_required
from app.models.well import Well
from app.models.org import OrgUnit
from app.models.rbac import User, Role, LoginLog
from app.models.constants import WELL_STATUSES


@bp.route("/")
@login_required
def dashboard():
    well_count = db.session.scalar(db.select(db.func.count(Well.id))) or 0
    org_count = db.session.scalar(db.select(db.func.count(OrgUnit.id))) or 0
    mapped = db.session.scalar(
        db.select(db.func.count(Well.id)).where(Well.latitude.isnot(None))
    ) or 0
    in_circuit = db.session.scalar(
        db.select(db.func.count(Well.id)).where(Well.status == "in_circuit")
    ) or 0

    # Wells grouped by status (for the doughnut + legend).
    status_labels = dict(WELL_STATUSES)
    rows = db.session.execute(
        db.select(Well.status, db.func.count(Well.id)).group_by(Well.status)
    ).all()
    by_status = [
        {"key": s or "unknown", "label": status_labels.get(s, s or "نامشخص"), "count": n}
        for s, n in rows
    ]

    # Urban vs rural split.
    kind_rows = db.session.execute(
        db.select(Well.well_kind, db.func.count(Well.id)).group_by(Well.well_kind)
    ).all()
    kind_counts = {k or "unknown": n for k, n in kind_rows}

    # Coverage of mapped wells (for the progress ring).
    mapped_pct = round((mapped / well_count) * 100) if well_count else 0

    recent_wells = db.session.scalars(
        db.select(Well).order_by(Well.created_at.desc()).limit(6)
    ).all()

    # --- Attention panel (read-only surfacing of existing signals) ---
    from app.models.quality import WaterQuality
    quality_issue_wells = db.session.scalar(
        db.select(db.func.count(db.distinct(WaterQuality.well_id))).where(
            db.or_(
                WaterQuality.is_potable.is_(False),
                WaterQuality.turbidity.isnot(None),
                WaterQuality.sholat.isnot(None),
            )
        )
    ) or 0
    under_rehab = db.session.scalar(
        db.select(db.func.count(Well.id)).where(Well.status == "under_rehab")
    ) or 0

    top_priority = []
    try:
        from app.services import prioritization
        ranked, _ = prioritization.compute(top=5)
        top_priority = ranked
    except Exception:
        top_priority = []

    try:
        from app.services import alerts as alert_svc
        alert_summary = alert_svc.summary(include_predictive=False)  # fast count
    except Exception:
        alert_summary = {"total": 0, "by_severity": {"high": 0, "medium": 0, "low": 0}}

    # --- Operational signals (zone-based dashboard) ---
    from flask import url_for
    from datetime import date, timedelta
    from app.models.pump_asset import PumpInstallation
    from app.models.production import MonthlyProduction as MP
    from app.models.rehab import Rehabilitation
    from app.models.maintenance import MaintenanceRecord

    running_pumps = db.session.scalar(
        db.select(db.func.count(PumpInstallation.id)).where(PumpInstallation.pull_date.is_(None))) or 0
    fail_cutoff = date.today() - timedelta(days=365)
    recent_failures = db.session.scalar(
        db.select(db.func.count(PumpInstallation.id)).where(
            PumpInstallation.pull_date.isnot(None), PumpInstallation.pull_date >= fail_cutoff)) or 0

    e_sum = db.session.execute(
        db.select(db.func.sum(MP.energy_kwh), db.func.sum(MP.production_m3))
        .where(MP.energy_kwh.isnot(None))).first()
    fleet_se = round(e_sum[0] / e_sum[1], 2) if (e_sum and e_sum[0] and e_sum[1]) else None

    tr = db.session.execute(
        db.select(MP.jyear, MP.jmonth, db.func.sum(MP.production_m3))
        .where(MP.production_m3.isnot(None)).group_by(MP.jyear, MP.jmonth)
        .order_by(MP.jyear, MP.jmonth)).all()[-18:]
    trend = {"labels": [f"{y}/{m:02d}" for y, m, _ in tr],
             "series": [round((v or 0) / 1e6, 2) for _, _, v in tr]}

    activity = []
    for i in db.session.scalars(db.select(PumpInstallation).where(
            PumpInstallation.pull_date.isnot(None)).order_by(PumpInstallation.pull_date.desc()).limit(5)).all():
        activity.append({"date": i.pull_date, "well_id": i.well_id, "well": i.well.name,
                         "type": "کشیدن پمپ", "detail": i.removal_reason or "", "icon": "bi-tools",
                         "color": "#2f6bff", "url": url_for("install.detail", record_id=i.id)})
    for r in db.session.scalars(db.select(Rehabilitation).where(
            Rehabilitation.rehab_date.isnot(None)).order_by(Rehabilitation.rehab_date.desc()).limit(5)).all():
        activity.append({"date": r.rehab_date, "well_id": r.well_id, "well": r.well.name,
                         "type": "بهسازی", "detail": r.reason or "", "icon": "bi-arrow-repeat",
                         "color": "#e0463e", "url": url_for("rehab.detail", record_id=r.id)})
    for m in db.session.scalars(db.select(MaintenanceRecord).where(
            MaintenanceRecord.report_date.isnot(None)).order_by(MaintenanceRecord.report_date.desc()).limit(5)).all():
        activity.append({"date": m.report_date, "well_id": m.well_id, "well": m.well.name,
                         "type": "نگهداری", "detail": m.fault_desc or "", "icon": "bi-wrench-adjustable",
                         "color": "#6a7180", "url": url_for("maintenance.detail", record_id=m.id)})
    activity = sorted([a for a in activity if a["date"]], key=lambda a: a["date"], reverse=True)[:7]

    import jdatetime
    today = jdatetime.date.today().strftime("%Y/%m/%d")
    return render_template(
        "main/dashboard.html",
        today=today, well_count=well_count, org_count=org_count,
        mapped=mapped, mapped_pct=mapped_pct, in_circuit=in_circuit,
        by_status=by_status, urban=kind_counts.get("urban", 0),
        rural=kind_counts.get("rural", 0), recent_wells=recent_wells,
        status_labels=status_labels, quality_issue_wells=quality_issue_wells,
        under_rehab=under_rehab, top_priority=top_priority, alert_summary=alert_summary,
        running_pumps=running_pumps, recent_failures=recent_failures,
        fleet_se=fleet_se, trend=trend, activity=activity,
    )


@bp.route("/admin/users")
@permission_required("admin", "view")
def admin_users():
    q = (request.args.get("q") or "").strip()
    query = db.select(User).order_by(User.username)
    users = db.session.scalars(query).unique().all()
    if q:
        ql = q.lower()
        users = [u for u in users if ql in (u.username or "").lower()
                 or ql in (u.full_name or "").lower()
                 or ql in (u.personnel_code or "").lower()]
    return render_template("main/users.html", users=users, q=q)


@bp.route("/admin/economics", methods=["GET", "POST"])
@permission_required("admin", "view")
def admin_economics():
    from flask import request, flash, redirect, url_for
    from flask_login import current_user
    from app.models.economic import EconomicParam
    from app.services import economics
    from app.utils.dates import to_english_digits
    economics.ensure_params()
    rows = db.session.scalars(db.select(EconomicParam).order_by(EconomicParam.id)).all()
    if request.method == "POST":
        if not current_user.has_permission("admin", "edit"):
            flash("مجوز ویرایش ندارید.", "warning")
            return redirect(url_for("main.admin_economics"))
        for p in rows:
            v = to_english_digits(request.form.get(f"v_{p.id}", "")).strip()
            try:
                p.value = float(v)
            except ValueError:
                pass
        db.session.commit()
        flash("پارامترهای اقتصادی به‌روزرسانی شد.", "success")
        return redirect(url_for("main.admin_economics"))
    return render_template("main/economics.html", params=rows,
                           can_edit=current_user.has_permission("admin", "edit"))
# ==================== دسته ۵ — مدیریت کاربران ====================

def _password_errors(pw):
    errs = []
    if len(pw) < 8:
        errs.append("حداقل ۸ کاراکتر")
    if not re.search(r"[A-Z]", pw):
        errs.append("یک حرف بزرگ (A-Z)")
    if not re.search(r"[a-z]", pw):
        errs.append("یک حرف کوچک (a-z)")
    if not re.search(r"\d", pw):
        errs.append("یک عدد")
    if not re.search(r"[^A-Za-z0-9]", pw):
        errs.append("یک کاراکتر ویژه (!@#...)")
    return errs


class UserForm(FlaskForm):
    first_name = StringField("نام", validators=[Optional(), Length(max=60)])
    last_name = StringField("نام خانوادگی", validators=[Optional(), Length(max=60)])
    national_id = StringField("کد ملی", validators=[Optional(), Length(max=10)])
    personnel_code = StringField("کد پرسنلی", validators=[Optional(), Length(max=30)])
    position = StringField("سمت سازمانی", validators=[Optional(), Length(max=120)])
    phone = StringField("شماره تماس", validators=[Optional(), Length(max=20)])
    email = StringField("ایمیل", validators=[Optional(), Length(max=120)])
    username = StringField("نام کاربری", validators=[DataRequired(), Length(max=60)])
    password = PasswordField("رمز عبور", validators=[Optional()])
    is_active = BooleanField("فعال", default=True)
    role_ids = SelectMultipleField("نقش‌ها", coerce=int)
    notes = TextAreaField("توضیحات", validators=[Optional()])
    submit = SubmitField("ذخیره")


def _set_roles(form):
    form.role_ids.choices = [
        (r.id, r.name) for r in db.session.scalars(db.select(Role).order_by(Role.name)).unique()]


@bp.route("/admin/users/new", methods=["GET", "POST"])
@permission_required("admin", "edit")
def user_create():
    form = UserForm()
    _set_roles(form)
    if form.validate_on_submit():
        uname = form.username.data.strip()
        if db.session.scalar(db.select(User).filter_by(username=uname)):
            flash("این نام کاربری قبلاً استفاده شده است.", "danger")
        else:
            pw = form.password.data or ""
            errs = _password_errors(pw)
            if errs:
                flash("رمز عبور ضعیف است؛ باید شامل: " + "، ".join(errs), "danger")
            else:
                u = User(username=uname, is_active=bool(form.is_active.data))
                _apply_user(form, u)
                u.set_password(pw)
                db.session.add(u)
                db.session.commit()
                flash("کاربر ایجاد شد.", "success")
                return redirect(url_for("main.admin_users"))
    return render_template("main/user_form.html", form=form, title="ایجاد کاربر", is_new=True)


@bp.route("/admin/users/<int:user_id>/edit", methods=["GET", "POST"])
@permission_required("admin", "edit")
def user_edit(user_id):
    u = db.get_or_404(User, user_id)
    form = UserForm(obj=u)
    _set_roles(form)
    if request.method == "GET":
        form.role_ids.data = [r.id for r in u.roles]
    if form.validate_on_submit():
        uname = form.username.data.strip()
        clash = db.session.scalar(db.select(User).filter(User.username == uname, User.id != u.id))
        if clash:
            flash("این نام کاربری قبلاً استفاده شده است.", "danger")
        else:
            u.username = uname
            u.is_active = bool(form.is_active.data)
            _apply_user(form, u)
            if form.password.data:
                errs = _password_errors(form.password.data)
                if errs:
                    flash("رمز عبور ضعیف است؛ باید شامل: " + "، ".join(errs), "danger")
                    return render_template("main/user_form.html", form=form, title="ویرایش کاربر", is_new=False, obj=u)
                u.set_password(form.password.data)
            db.session.commit()
            flash("کاربر به‌روزرسانی شد.", "success")
            return redirect(url_for("main.admin_users"))
    return render_template("main/user_form.html", form=form, title="ویرایش کاربر", is_new=False, obj=u)


def _apply_user(form, u):
    u.first_name = form.first_name.data or None
    u.last_name = form.last_name.data or None
    u.full_name = (" ".join(x for x in [u.first_name, u.last_name] if x)).strip() or None
    u.national_id = form.national_id.data or None
    u.personnel_code = form.personnel_code.data or None
    u.position = form.position.data or None
    u.phone = form.phone.data or None
    u.email = form.email.data or None
    u.notes = form.notes.data or None
    u.roles = db.session.scalars(
        db.select(Role).filter(Role.id.in_(form.role_ids.data or []))).unique().all()


@bp.route("/admin/users/<int:user_id>/toggle", methods=["POST"])
@permission_required("admin", "edit")
def user_toggle_active(user_id):
    u = db.get_or_404(User, user_id)
    if u.id == current_user.id:
        flash("نمی‌توانید حساب خودتان را غیرفعال کنید.", "warning")
    else:
        u.is_active = not u.is_active
        db.session.commit()
        flash("وضعیت کاربر تغییر کرد.", "info")
    return redirect(url_for("main.admin_users"))


@bp.route("/admin/users/<int:user_id>/reset-password", methods=["POST"])
@permission_required("admin", "edit")
def user_reset_password(user_id):
    u = db.get_or_404(User, user_id)
    new_pw = (request.form.get("new_password") or "").strip()
    errs = _password_errors(new_pw)
    if errs:
        flash("رمز عبور ضعیف است؛ باید شامل: " + "، ".join(errs), "danger")
    else:
        u.set_password(new_pw)
        db.session.commit()
        flash(f"رمز عبور «{u.username}» بازنشانی شد.", "success")
    return redirect(url_for("main.admin_users"))


@bp.route("/admin/users/<int:user_id>/delete", methods=["POST"])
@permission_required("admin", "delete")
def user_delete(user_id):
    u = db.get_or_404(User, user_id)
    if u.id == current_user.id:
        flash("نمی‌توانید حساب خودتان را حذف کنید.", "warning")
    elif u.is_superuser:
        flash("حذف مدیر کل مجاز نیست.", "warning")
    else:
        db.session.delete(u)
        db.session.commit()
        flash("کاربر حذف شد.", "info")
    return redirect(url_for("main.admin_users"))


@bp.route("/admin/users/activity")
@permission_required("admin", "view")
def user_activity():
    logs = db.session.scalars(
        db.select(LoginLog).order_by(LoginLog.login_at.desc()).limit(1000)).all()
    rows = _activity_rows(logs)
    return render_template("main/user_activity.html", rows=rows)


def _fmt_duration(sec):
    if sec is None:
        return "—"
    h, rem = divmod(int(sec), 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}س {m}د"
    if m:
        return f"{m}د {s}ث"
    return f"{s}ث"


def _activity_rows(logs):
    counts = {}
    for lg in logs:
        counts[lg.user_id] = counts.get(lg.user_id, 0) + 1
    out = []
    for lg in logs:
        u = lg.user
        out.append({
            "full_name": (u.full_name if u else None) or (u.username if u else "—"),
            "username": u.username if u else "—",
            "login_at": lg.login_at,
            "logout_at": lg.logout_at,
            "duration": _fmt_duration(lg.duration_seconds),
            "ip": lg.ip_address or "—",
            "agent": lg.user_agent or "—",
            "count": counts.get(lg.user_id, 0),
            "online": lg.logout_at is None,
        })
    return out


@bp.route("/admin/users/activity/export")
@permission_required("admin", "view")
def user_activity_export():
    import pandas as pd
    logs = db.session.scalars(db.select(LoginLog).order_by(LoginLog.login_at.desc())).all()
    rows = _activity_rows(logs)
    df = pd.DataFrame([{
        "نام و نام خانوادگی": r["full_name"],
        "نام کاربری": r["username"],
        "تاریخ/ساعت ورود": r["login_at"].strftime("%Y-%m-%d %H:%M") if r["login_at"] else "",
        "ساعت خروج": r["logout_at"].strftime("%Y-%m-%d %H:%M") if r["logout_at"] else "",
        "مدت حضور": r["duration"],
        "IP": r["ip"],
        "مرورگر/دستگاه": r["agent"],
        "تعداد ورود": r["count"],
        "وضعیت": "آنلاین" if r["online"] else "آفلاین",
    } for r in rows])
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xl:
        (df if not df.empty else pd.DataFrame({"—": []})).to_excel(
            xl, sheet_name="فعالیت کاربران", index=False)
    buf.seek(0)
    return send_file(buf, as_attachment=True,
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                     download_name=f"user_activity_{datetime.now():%Y%m%d}.xlsx")


class ProfileForm(FlaskForm):
    first_name = StringField("نام", validators=[Optional(), Length(max=60)])
    last_name = StringField("نام خانوادگی", validators=[Optional(), Length(max=60)])
    phone = StringField("شماره تماس", validators=[Optional(), Length(max=20)])
    email = StringField("ایمیل", validators=[Optional(), Length(max=120)])
    username = StringField("نام کاربری", validators=[DataRequired(), Length(max=60)])
    current_password = PasswordField("رمز فعلی", validators=[Optional()])
    new_password = PasswordField("رمز جدید", validators=[Optional()])
    submit = SubmitField("ذخیره تغییرات")


@bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    form = ProfileForm(obj=current_user)
    if form.validate_on_submit():
        uname = form.username.data.strip()
        clash = db.session.scalar(db.select(User).filter(User.username == uname, User.id != current_user.id))
        if clash:
            flash("این نام کاربری قبلاً استفاده شده است.", "danger")
        else:
            current_user.username = uname
            current_user.first_name = form.first_name.data or None
            current_user.last_name = form.last_name.data or None
            current_user.full_name = (" ".join(x for x in [current_user.first_name, current_user.last_name] if x)).strip() or None
            current_user.phone = form.phone.data or None
            current_user.email = form.email.data or None
            if form.new_password.data:
                if not current_user.check_password(form.current_password.data or ""):
                    flash("رمز فعلی نادرست است.", "danger")
                    return render_template("main/profile.html", form=form)
                errs = _password_errors(form.new_password.data)
                if errs:
                    flash("رمز جدید ضعیف است؛ باید شامل: " + "، ".join(errs), "danger")
                    return render_template("main/profile.html", form=form)
                current_user.set_password(form.new_password.data)
            db.session.commit()
            flash("پروفایل به‌روزرسانی شد.", "success")
            return redirect(url_for("main.profile"))
    return render_template("main/profile.html", form=form)


################################################################################
# FILE: blueprints\maintenance\__init__.py
################################################################################

from flask import Blueprint

bp = Blueprint("maintenance", __name__)

from app.blueprints.maintenance import routes  # noqa: E402,F401



################################################################################
# FILE: blueprints\maintenance\routes.py
################################################################################

from flask import render_template, redirect, url_for, flash, request, abort
from flask_login import current_user
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, SubmitField
from wtforms.validators import Optional

from app.extensions import db
from app.blueprints.maintenance import bp
from app.security import permission_required
from app.utils.forms import JalaliDateField, PersianFloatField as FloatField
from app.models.well import Well
from app.models.maintenance import MaintenanceRecord
from app.models.pump_asset import PumpInstallation
from app.models.audit import RecordHistory
from app.models.constants import MAINTENANCE_TYPES, MAINTENANCE_CATEGORIES
from app.blueprints.install.routes import get_or_create_supplier
from app.utils.dates import format_jalali as _jd
from app import workflow


class MaintenanceForm(FlaskForm):
    report_date = JalaliDateField("تاریخ گزارش", validators=[Optional()])
    maint_type = SelectField("نوع نگهداری", choices=[("", "—")] + MAINTENANCE_TYPES, validators=[Optional()])
    category = SelectField("دسته", choices=[("", "—")] + MAINTENANCE_CATEGORIES, validators=[Optional()])
    down_from = JalaliDateField("شروع خاموشی", validators=[Optional()])
    down_to = JalaliDateField("پایان خاموشی", validators=[Optional()])
    downtime_hours = FloatField("مدت خاموشی (ساعت)", validators=[Optional()])
    fault_desc = TextAreaField("شرح خرابی", validators=[Optional()])
    action_taken = TextAreaField("اقدام انجام‌شده", validators=[Optional()])
    parts_replaced = StringField("قطعات تعویض‌شده", validators=[Optional()])
    contractor_name = StringField("پیمانکار/مجری", validators=[Optional()])
    cost = FloatField("هزینه", validators=[Optional()])
    pump_installation_id = SelectField("نصب مرتبط", coerce=int, validators=[Optional()])
    notes = TextAreaField("توضیحات", validators=[Optional()])
    submit = SubmitField("ذخیره")

    def populate_installs(self, well_id):
        installs = db.session.scalars(
            db.select(PumpInstallation).filter_by(well_id=well_id)
            .order_by(PumpInstallation.install_date.desc())).all()
        self.pump_installation_id.choices = [(0, "—")] + [
            (i.id, f"نصب {_jd(i.install_date, '') } — {i.pump_type or ''}".strip())
            for i in installs]


SIMPLE = ["report_date", "maint_type", "category", "down_from", "down_to",
          "downtime_hours", "fault_desc", "action_taken", "parts_replaced", "cost", "notes"]


def _apply(form, rec):
    for f in SIMPLE:
        setattr(rec, f, getattr(form, f).data or None)
    rec.pump_installation_id = form.pump_installation_id.data or None
    c = get_or_create_supplier(form.contractor_name.data, "contractor")
    rec.contractor_id = c.id if c else None


@bp.route("/wells/<int:well_id>/maintenance/new", methods=["GET", "POST"])
@permission_required("maintenance", "create")
def create(well_id):
    well = db.get_or_404(Well, well_id)
    form = MaintenanceForm()
    form.populate_installs(well.id)
    if form.validate_on_submit():
        rec = MaintenanceRecord(well_id=well.id, created_by_id=current_user.id)
        _apply(form, rec)
        db.session.add(rec)
        db.session.flush()
        workflow.log_change(rec, "create")
        db.session.commit()
        flash("نگهداری ثبت شد (پیش‌نویس).", "success")
        return redirect(url_for("maintenance.detail", record_id=rec.id))
    return render_template("maintenance/form.html", form=form, well=well, title="ثبت نگهداری/تعمیر")


@bp.route("/maintenance/<int:record_id>")
@permission_required("maintenance", "view")
def detail(record_id):
    rec = db.get_or_404(MaintenanceRecord, record_id)
    history = db.session.scalars(
        db.select(RecordHistory).filter_by(entity_type="maintenance_records", entity_id=rec.id)
        .order_by(RecordHistory.timestamp.desc())).all()
    return render_template("maintenance/detail.html", rec=rec, well=rec.well,
                           history=history, editable=workflow.is_editable(rec),
                           type_labels=dict(MAINTENANCE_TYPES),
                           cat_labels=dict(MAINTENANCE_CATEGORIES))


@bp.route("/maintenance/<int:record_id>/edit", methods=["GET", "POST"])
@permission_required("maintenance", "edit")
def edit(record_id):
    rec = db.get_or_404(MaintenanceRecord, record_id)
    if not workflow.is_editable(rec):
        flash("این رکورد قفل است؛ ابتدا باید به پیش‌نویس بازگردانده شود.", "warning")
        return redirect(url_for("maintenance.detail", record_id=rec.id))
    form = MaintenanceForm(obj=rec)
    form.populate_installs(rec.well_id)
    if request.method == "GET":
        form.contractor_name.data = rec.contractor.name if rec.contractor else ""
    if form.validate_on_submit():
        _apply(form, rec)
        rec.updated_by_id = current_user.id
        workflow.log_change(rec, "update")
        db.session.commit()
        flash("نگهداری به‌روزرسانی شد.", "success")
        return redirect(url_for("maintenance.detail", record_id=rec.id))
    return render_template("maintenance/form.html", form=form, well=rec.well, title="ویرایش نگهداری")


@bp.route("/maintenance/<int:record_id>/delete", methods=["POST"])
@permission_required("maintenance", "delete")
def delete(record_id):
    rec = db.get_or_404(MaintenanceRecord, record_id)
    well_id = rec.well_id
    db.session.delete(rec)
    db.session.commit()
    flash("رکورد نگهداری حذف شد.", "info")
    return redirect(url_for("wells.detail", well_id=well_id))


def _transition(record_id, fn, perm_action, msg, **kw):
    rec = db.get_or_404(MaintenanceRecord, record_id)
    if not current_user.has_permission("maintenance", perm_action):
        abort(403)
    try:
        fn(rec, **kw)
        db.session.commit()
        flash(msg, "success")
    except workflow.WorkflowError as e:
        db.session.rollback()
        flash(str(e), "danger")
    return redirect(url_for("maintenance.detail", record_id=record_id))


@bp.route("/maintenance/<int:record_id>/submit", methods=["POST"])
def submit(record_id):
    return _transition(record_id, workflow.submit, "edit", "برای تأیید ثبت شد.")


@bp.route("/maintenance/<int:record_id>/approve", methods=["POST"])
def approve(record_id):
    return _transition(record_id, workflow.approve, "approve", "تأیید شد.")


@bp.route("/maintenance/<int:record_id>/reject", methods=["POST"])
def reject(record_id):
    return _transition(record_id, workflow.reject, "approve", "برگشت داده شد.",
                       reason=request.form.get("reason", ""))


@bp.route("/maintenance/<int:record_id>/revert", methods=["POST"])
def revert(record_id):
    return _transition(record_id, workflow.revert_to_draft, "approve", "به پیش‌نویس بازگردانده شد.")



################################################################################
# FILE: blueprints\mechanic\__init__.py
################################################################################

from flask import Blueprint

bp = Blueprint("mechanic", __name__, url_prefix="/mechanic")

from app.blueprints.mechanic import routes  # noqa: E402,F401


################################################################################
# FILE: blueprints\mechanic\routes.py
################################################################################

"""ماژول کارگاه مکانیک — فاز ۲: فهرست + فرم ورود/ویرایش/جزئیات."""
from flask import render_template, redirect, url_for, flash
from flask_login import current_user
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, SubmitField
from wtforms.validators import Optional, ValidationError

from app.extensions import db
from app.blueprints.mechanic import bp
from app.security import permission_required
from app.utils.forms import JalaliDateField, PersianFloatField, PersianIntegerField
from app.models.well import Well
from app.models.mechanic import MechanicEvent

OP_TYPES = [
    ("", "—"),
    ("کشیدن", "کشیدن"),
    ("نصب", "نصب"),
    ("جمع‌آوری", "جمع‌آوری"),
    ("نصب جدید", "نصب جدید"),
]
COND = [("", "—"), ("نو", "نو"), ("تعمیری", "تعمیری")]


class MechanicForm(FlaskForm):
    op_date = JalaliDateField("تاریخ عملیات", validators=[Optional()])
    op_type = SelectField("نوع عملیات", choices=OP_TYPES, validators=[Optional()])
    fault_type = SelectField("نوع خرابی", choices=[("", "—"), ("سوختگی", "سوختگی"),
                             ("ایراد مکانیکی", "ایراد مکانیکی"), ("کاهش آبدهی", "کاهش آبدهی"),
                             ("سایر", "سایر")], validators=[Optional()])
    fault_description = TextAreaField("شرح خرابی از نظر بهره‌بردار", validators=[Optional()])
    contractor = StringField("نام پیمانکار", validators=[Optional()])
    pm_form_no = StringField("فرم نصب در PM", validators=[Optional()])

    motor_desc = StringField("مشخصات موتور", validators=[Optional()])
    motor_condition = SelectField("وضعیت موتور", choices=COND, validators=[Optional()])
    pump_desc = StringField("مشخصات پمپ", validators=[Optional()])
    pump_condition = SelectField("وضعیت پمپ", choices=COND, validators=[Optional()])

    tip_change = StringField("تغییر تیپ", validators=[Optional()])
    prev_install_date = JalaliDateField("تاریخ نصب قبلی", validators=[Optional()])
    well_depth = PersianFloatField("عمق چاه (متر)", validators=[Optional()])
    prev_install_depth = PersianFloatField("عمق نصب قبلی (متر)", validators=[Optional()])
    curr_install_depth = PersianFloatField("عمق نصب فعلی (متر)", validators=[Optional()])
    static_level = PersianFloatField("سطح استاتیک (متر)", validators=[Optional()])
    dynamic_level = PersianFloatField("سطح دینامیک (متر)", validators=[Optional()])
    path_loss = PersianFloatField("تلفات مسیر (متر)", validators=[Optional()])
    network_pressure = PersianFloatField("فشار شبکه (متر)", validators=[Optional()])
    total_head = PersianFloatField("هد کلی (متر)", validators=[Optional()])
    design_flow = PersianFloatField("دبی طراحی (l/s)", validators=[Optional()])
    pipe_diameter = PersianFloatField("قطر لوله آبده (اینچ)", validators=[Optional()])

    pt_date = JalaliDateField("تاریخ آزمایش پمپاژ کارگاه", validators=[Optional()])
    pt_pressure = PersianFloatField("فشار آزمایش پمپاژ", validators=[Optional()])
    pt_flow = PersianFloatField("دبی آزمایش پمپاژ (l/s)", validators=[Optional()])

    cable_size = StringField("سایز کابل", validators=[Optional()])
    cable_change = StringField("تغییر سایز/تیپ کابل", validators=[Optional()])
    starter = StringField("راه‌انداز", validators=[Optional()])

    months_worked = PersianIntegerField("تعداد ماه‌های کارکرد", validators=[Optional()])
    mechanic_opinion = TextAreaField("نظر کارگاه مکانیک", validators=[Optional()])
    notes = TextAreaField("توضیحات", validators=[Optional()])
    submit = SubmitField("ذخیره")

    def validate_design_flow(self, field):
        if field.data is not None and field.data < 0:
            raise ValidationError("دبی نمی‌تواند منفی باشد.")


FIELDS = ["op_date", "op_type", "fault_type", "fault_description", "contractor", "pm_form_no",
          "motor_desc", "motor_condition", "pump_desc", "pump_condition",
          "tip_change", "prev_install_date", "well_depth", "prev_install_depth",
          "curr_install_depth", "static_level", "dynamic_level", "path_loss",
          "network_pressure", "total_head", "design_flow", "pipe_diameter",
          "pt_date", "pt_pressure", "pt_flow", "cable_size", "cable_change",
          "starter", "months_worked", "mechanic_opinion", "notes"]


def _apply(form, rec):
    for f in FIELDS:
        setattr(rec, f, getattr(form, f).data if getattr(form, f).data not in ("",) else None)


@bp.route("/")
@permission_required("mechanic", "view")
def index():
    events = db.session.scalars(
        db.select(MechanicEvent).join(Well, MechanicEvent.well_id == Well.id)
        .order_by(MechanicEvent.op_date.desc())
    ).all()
    op_types = sorted({e.op_type for e in events if e.op_type})
    return render_template("mechanic/index.html", events=events, op_types=op_types)

@bp.route("/well/<int:well_id>/new", methods=["GET", "POST"])
@permission_required("mechanic", "create")
def create(well_id):
    well = db.get_or_404(Well, well_id)
    form = MechanicForm()
    if form.validate_on_submit():
        rec = MechanicEvent(well_id=well.id, created_by_id=current_user.id, source="manual")
        _apply(form, rec)
        db.session.add(rec)
        db.session.commit()
        flash("رویداد کارگاه مکانیک ثبت شد.", "success")
        return redirect(url_for("mechanic.detail", record_id=rec.id))
    return render_template("mechanic/form.html", form=form, well=well, title="ثبت رویداد کارگاه مکانیک")


@bp.route("/<int:record_id>")
@permission_required("mechanic", "view")
def detail(record_id):
    rec = db.get_or_404(MechanicEvent, record_id)
    return render_template("mechanic/detail.html", rec=rec, well=rec.well, stages=STAGES)


@bp.route("/<int:record_id>/edit", methods=["GET", "POST"])
@permission_required("mechanic", "edit")
def edit(record_id):
    rec = db.get_or_404(MechanicEvent, record_id)
    form = MechanicForm(obj=rec)
    if form.validate_on_submit():
        _apply(form, rec)
        rec.updated_by_id = current_user.id
        db.session.commit()
        flash("رویداد به‌روزرسانی شد.", "success")
        return redirect(url_for("mechanic.detail", record_id=rec.id))
    return render_template("mechanic/form.html", form=form, well=rec.well, title="ویرایش رویداد کارگاه مکانیک")


@bp.route("/<int:record_id>/delete", methods=["POST"])
@permission_required("mechanic", "delete")
def delete(record_id):
    rec = db.get_or_404(MechanicEvent, record_id)
    well_id = rec.well_id
    db.session.delete(rec)
    db.session.commit()
    flash("رویداد حذف شد.", "info")
    return redirect(url_for("mechanic.index"))
# ---------- انبار قطعات (فاز ۳) ----------
from app.models.mechanic_part import MechanicPart
from wtforms import IntegerField


class PartForm(FlaskForm):
    equipment = SelectField("نوع تجهیز", choices=[("موتور", "موتور"), ("پمپ", "پمپ")],
                            validators=[Optional()])
    part_name = StringField("نام قطعه", validators=[Optional()])
    total_count = PersianIntegerField("تعداد کل", validators=[Optional()])
    usable = PersianIntegerField("قابل استفاده", validators=[Optional()])
    scrap = PersianIntegerField("اسقاط", validators=[Optional()])
    new_count = PersianIntegerField("نو", validators=[Optional()])
    repaired = PersianIntegerField("تعمیری", validators=[Optional()])
    inventory_code = StringField("کد انباری قطعه", validators=[Optional()])
    part_type = StringField("نوع قطعه", validators=[Optional()])
    manufacturer = StringField("سازنده قطعه", validators=[Optional()])
    entry_date = JalaliDateField("تاریخ ورود", validators=[Optional()])
    notes = StringField("توضیحات", validators=[Optional()])
    submit = SubmitField("ذخیره")


@bp.route("/parts")
@permission_required("mechanic", "view")
def parts():
    motor = db.session.scalars(db.select(MechanicPart).filter_by(equipment="موتور")
                               .order_by(MechanicPart.id)).all()
    pump = db.session.scalars(db.select(MechanicPart).filter_by(equipment="پمپ")
                              .order_by(MechanicPart.id)).all()
    return render_template("mechanic/parts.html", motor=motor, pump=pump)


@bp.route("/parts/new", methods=["GET", "POST"])
@permission_required("mechanic", "create")
def part_create():
    form = PartForm()
    if form.validate_on_submit():
        p = MechanicPart(created_by_id=current_user.id)
        for f in ["equipment", "part_name", "total_count", "usable", "scrap",
                  "new_count", "repaired", "inventory_code", "part_type",
                  "manufacturer", "entry_date", "notes"]:
            setattr(p, f, getattr(form, f).data)
        db.session.add(p)
        db.session.commit()
        flash("قطعه ثبت شد.", "success")
        return redirect(url_for("mechanic.parts"))
    return render_template("mechanic/part_form.html", form=form, title="افزودن قطعه", part_id=None)


@bp.route("/parts/<int:part_id>/edit", methods=["GET", "POST"])
@permission_required("mechanic", "edit")
def part_edit(part_id):
    p = db.get_or_404(MechanicPart, part_id)
    form = PartForm(obj=p)
    if form.validate_on_submit():
        for f in ["equipment", "part_name", "total_count", "usable", "scrap",
                  "new_count", "repaired", "inventory_code", "part_type",
                  "manufacturer", "notes"]:
            setattr(p, f, getattr(form, f).data)
        p.updated_by_id = current_user.id
        db.session.commit()
        flash("قطعه به‌روزرسانی شد.", "success")
        return redirect(url_for("mechanic.parts"))
    return render_template("mechanic/part_form.html", form=form, title="ویرایش قطعه", part_id=p.id)


@bp.route("/parts/<int:part_id>/delete", methods=["POST"])
@permission_required("mechanic", "delete")
def part_delete(part_id):
    p = db.get_or_404(MechanicPart, part_id)
    db.session.delete(p)
    db.session.commit()
    flash("قطعه حذف شد.", "info")
    return redirect(url_for("mechanic.parts"))
# ---------- گردش کار مرحله‌ای (فاز ۴) ----------
from app.models.mechanic import MechanicStageLog

# مراحل به ترتیب فلوچارت
STAGES = [
    "اعلام حادثه",
    "تشخیص نوع خرابی",
    "دفتر فنی و مهندسی",
    "ویدئومتری",
    "بهسازی چاه",
    "انتخاب پمپ",
    "پمپاژ آزمایشی",
    "مونتاژ",
    "تست چاله پمپاژ",
    "دمونتاژ",
    "ارجاع به کارگاه نصب",
    "نصب نهایی",
    "پایان‌یافته",
]

FAULT_TYPES = ["سوختگی", "ایراد مکانیکی", "کاهش آبدهی", "سایر"]


@bp.route("/<int:record_id>/stage", methods=["POST"])
@permission_required("mechanic", "edit")
def change_stage(record_id):
    from flask import request
    rec = db.get_or_404(MechanicEvent, record_id)
    new_stage = request.form.get("to_stage", "").strip()
    note = request.form.get("note", "").strip()
    if new_stage and new_stage in STAGES and new_stage != rec.stage:
        log = MechanicStageLog(
            event_id=rec.id, from_stage=rec.stage, to_stage=new_stage,
            note=note or None, changed_by_id=current_user.id)
        rec.stage = new_stage
        db.session.add(log)
        db.session.commit()
        flash(f"مرحله به «{new_stage}» تغییر کرد.", "success")
    else:
        flash("مرحله‌ی معتبری انتخاب نشد.", "warning")
    return redirect(url_for("mechanic.detail", record_id=rec.id))
# ---------- گزارش‌های مدیریتی (فاز ۵) ----------
from sqlalchemy import func
from collections import Counter
import jdatetime

def classify_fault(event):
    """دسته‌بندی خرابی از روی fault_type یا متن fault_description."""
    # اگر نوع خرابی صریح ثبت شده، همان
    if event.fault_type:
        return event.fault_type
    text = (event.fault_description or "").strip()
    if not text:
        return "نامشخص"
    # دسته‌بندی بر اساس کلمات کلیدی
    rules = [
        ("سوختگی", ["سوخت", "سوختن"]),
        ("کاهش آبدهی", ["کاهش دبی", "کاهش آبدهی", "کمبود", "عدم آبده", "عدم ابده", "افت"]),
        ("ایراد مکانیکی", ["صدا", "لرزش", "گیرپاژ", "گیر و پاژ", "گیرو پاژ", "مکانیک"]),
        ("ایراد برقی", ["اهم", "شولات", "شولاتی", "آمپر", "امپر", "برق"]),
        ("هوادهی", ["هوادهی", "هوا"]),
        ("عملیات نصب/کشیدن", ["نصب", "کشیدن", "جمع آوری", "جمع‌آوری", "تجهیز", "جابجایی"]),
        ("تغییر فشار", ["فشار"]),
    ]
    for label, keywords in rules:
        if any(k in text for k in keywords):
            return label
    return "سایر"

@bp.route("/reports")
@permission_required("mechanic", "view")
def reports():
    from flask import request
    # فیلترها
    f_year = request.args.get("year", "").strip()
    f_optype = request.args.get("optype", "").strip()
    f_fault = request.args.get("fault", "").strip()

    q = db.select(MechanicEvent)
    events = db.session.scalars(q).all()

    # تبدیل تاریخ به سال شمسی برای فیلتر و نمودار
    def jyear(d):
        if not d:
            return None
        try:
            return jdatetime.date.fromgregorian(date=d).year
        except Exception:
            return None

    # اعمال فیلترها
    rows = []
    for e in events:
        jy = jyear(e.op_date)
        if f_year and str(jy) != f_year:
            continue
        if f_optype and (e.op_type or "") != f_optype:
            continue
        if f_fault and (e.fault_type or "") != f_fault:
            continue
        rows.append((e, jy))

    # آمار کلی
    total = len(rows)
    by_optype = Counter((e.op_type or "نامشخص") for e, _ in rows)
    by_fault = Counter(classify_fault(e) for e, _ in rows)
    by_year = Counter(jy for _, jy in rows if jy)
    by_contractor = Counter((e.contractor or "نامشخص") for e, _ in rows if e.contractor)
    by_stage = Counter((e.stage or "نامشخص") for e, _ in rows)

    # شاخص‌های بیشتر
    with_pt = sum(1 for e, _ in rows if e.pt_flow is not None)
    by_center = Counter()
    by_month = Counter()
    burnt = 0
    depths = []
    heads = []
    flows = []
    months_worked_list = []
    import jdatetime as _jd
    for e, jy in rows:
        # مرکز از توضیحات یا شرح در دسترس نیست؛ از fault_description رد می‌شویم
        # ماه شمسی برای روند ماهانه
        if e.op_date:
            try:
                jm = _jd.date.fromgregorian(date=e.op_date).month
                by_month[jm] += 1
            except Exception:
                pass
        f = classify_fault(e)
        if f == "سوختگی":
            burnt += 1
        if e.well_depth:
            depths.append(e.well_depth)
        if e.total_head:
            heads.append(e.total_head)
        if e.pt_flow:
            flows.append(e.pt_flow)
        if e.months_worked:
            months_worked_list.append(e.months_worked)

    def avg(lst):
        return round(sum(lst) / len(lst), 1) if lst else 0

    MONTHS_FA = ["", "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
                 "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]
    by_month_named = {MONTHS_FA[m]: c for m, c in sorted(by_month.items())}

    stats = {
        "total": total,
        "install": by_optype.get("نصب", 0),
        "pull": by_optype.get("کشیدن", 0),
        "collect": by_optype.get("جمع‌آوری", 0) + by_optype.get("جمع آوری", 0),
        "with_pt": with_pt,
        "burnt": burnt,
        "burnt_pct": round(100 * burnt / total) if total else 0,
        "avg_depth": avg(depths),
        "avg_head": avg(heads),
        "avg_flow": avg(flows),
        "avg_months_worked": avg(months_worked_list),
        "by_optype": dict(by_optype),
        "by_fault": dict(by_fault),
        "by_year": dict(sorted(by_year.items())),
        "by_month": by_month_named,
        "by_contractor": by_contractor.most_common(10),
        "by_stage": dict(by_stage),
    }

    # گزینه‌های فیلتر
    all_years = sorted({jyear(e.op_date) for e in events if jyear(e.op_date)}, reverse=True)
    all_optypes = sorted({e.op_type for e in events if e.op_type})

    return render_template("mechanic/reports.html", stats=stats,
                           all_years=all_years, all_optypes=all_optypes,
                           fault_types=FAULT_TYPES,
                           cur={"year": f_year, "optype": f_optype, "fault": f_fault})
# ---------- گزارش انبار قطعات ----------
@bp.route("/parts/report")
@permission_required("mechanic", "view")
def parts_report():
    parts = db.session.scalars(db.select(MechanicPart).order_by(
        MechanicPart.equipment, MechanicPart.id)).all()

    total_usable = sum(p.usable or 0 for p in parts)
    total_scrap = sum(p.scrap or 0 for p in parts)
    total_new = sum(p.new_count or 0 for p in parts)
    total_repaired = sum(p.repaired or 0 for p in parts)

    # قطعات کم‌موجود: قابل‌استفاده صفر یا کمتر از ۳
    low_stock = [p for p in parts if (p.usable or 0) < 3]
    # قطعات بدون هیچ موجودی
    empty = [p for p in parts if (p.total_count or 0) == 0]

    by_eq = {"موتور": {"usable": 0, "scrap": 0}, "پمپ": {"usable": 0, "scrap": 0}}
    for p in parts:
        if p.equipment in by_eq:
            by_eq[p.equipment]["usable"] += p.usable or 0
            by_eq[p.equipment]["scrap"] += p.scrap or 0

    stats = {
        "total_parts": len(parts),
        "total_usable": total_usable,
        "total_scrap": total_scrap,
        "total_new": total_new,
        "total_repaired": total_repaired,
        "low_stock": low_stock,
        "empty_count": len(empty),
        "by_eq": by_eq,
    }
    parts_data = [{
        "equipment": p.equipment or "نامشخص",
        "name": p.part_name or "—",
        "total": p.total_count or 0,
        "new": p.new_count or 0,
        "repaired": p.repaired or 0,
        "scrap": p.scrap or 0,
        "usable": p.usable or 0,
        "installed": getattr(p, "installed_count", 0) or 0,
    } for p in parts]
    return render_template("mechanic/parts_report.html", stats=stats, parts_data=parts_data)


################################################################################
# FILE: blueprints\operation\__init__.py
################################################################################

from flask import Blueprint

bp = Blueprint("operation", __name__)

from app.blueprints.operation import routes  # noqa: E402,F401



################################################################################
# FILE: blueprints\operation\routes.py
################################################################################

from flask import render_template, redirect, url_for, flash, request, abort
from flask_login import current_user
from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, TextAreaField, SubmitField
from wtforms.validators import Optional

from app.extensions import db
from app.blueprints.operation import bp
from app.security import permission_required
from app.utils.forms import JalaliDateField, PersianFloatField as FloatField
from app.utils.dates import to_english_digits
from app.models.well import Well
from app.models.flow import FlowTest, FlowTestPoint
from app.models.audit import RecordHistory
from app.models.constants import OPERATING_TYPES, FLOW_TEST_REASONS
from app import workflow

POINT_ROWS = 5
POINT_FIELDS = ["operating_type", "discharge_lps", "head_m", "drawdown_m",
                "dynamic_level_m", "pressure_atm", "amperes", "efficiency"]


class FlowTestForm(FlaskForm):
    test_date = JalaliDateField("تاریخ آزمایش", validators=[Optional()])
    test_reason = SelectField("دلیل آزمایش", choices=[("", "—")] + [(r, r) for r in FLOW_TEST_REASONS], validators=[Optional()])
    network_type = StringField("نوع شبکه", validators=[Optional()])
    electropump_type = StringField("تیپ الکتروپمپ", validators=[Optional()])
    electropump_type_prev = StringField("تیپ الکتروپمپ قبلی", validators=[Optional()])
    install_date = JalaliDateField("تاریخ آخرین نصب", validators=[Optional()])
    install_depth = FloatField("عمق نصب", validators=[Optional()])
    well_depth = FloatField("عمق چاه", validators=[Optional()])
    construction_type = StringField("نوع چاه (سیمانته/غیرسیمانته)", validators=[Optional()])
    allowed_q = FloatField("دبی مجاز", validators=[Optional()])
    design_q = FloatField("دبی طراحی", validators=[Optional()])
    license_q = FloatField("دبی پروانه", validators=[Optional()])
    power_subscription = StringField("اشتراک برق", validators=[Optional()])
    static_level = FloatField("سطح ایستایی", validators=[Optional()])
    last_rehab_date = JalaliDateField("تاریخ آخرین بهسازی", validators=[Optional()])
    pull_reason = StringField("علت کشیدن پمپ", validators=[Optional()])
    meter_status = StringField("کالیبراسیون/وضعیت کنتور", validators=[Optional()])
    meter_brand = StringField("برند/سایز کنتور", validators=[Optional()])
    starter_type = StringField("سیستم راه‌انداز", validators=[Optional()])
    capacitor_capacity = FloatField("ظرفیت خازن", validators=[Optional()])
    voltage_on = StringField("ولتاژ روشن", validators=[Optional()])
    voltage_off = StringField("ولتاژ خاموش", validators=[Optional()])
    ohm_ff = StringField("مقاومت اهمی ف-ف", validators=[Optional()])
    ohm_fg = StringField("مقاومت اهمی ف-ب", validators=[Optional()])
    line_pressure = FloatField("فشار خط (bar)", validators=[Optional()])
    regulated_pressure = StringField("فشار تنظیمی", validators=[Optional()])
    discharge_volume_m3 = FloatField("حجم تخلیه (m³)", validators=[Optional()])
    expert_note = TextAreaField("نظر کارشناس", validators=[Optional()])
    submit = SubmitField("ذخیره")


HEADER_FIELDS = [
    "test_date", "test_reason", "network_type", "electropump_type", "electropump_type_prev",
    "install_date", "install_depth", "well_depth", "construction_type", "allowed_q",
    "design_q", "license_q", "power_subscription", "static_level", "last_rehab_date",
    "pull_reason", "meter_status", "meter_brand", "starter_type", "capacitor_capacity",
    "voltage_on", "voltage_off", "ohm_ff", "ohm_fg", "line_pressure",
    "regulated_pressure", "discharge_volume_m3", "expert_note",
]


def _num(s):
    s = to_english_digits((s or "").strip())
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _apply_header(form, rec):
    for f in HEADER_FIELDS:
        setattr(rec, f, getattr(form, f).data)


def _apply_points(rec):
    """Rebuild child points from the manual table in request.form."""
    rec.points.clear()
    for i in range(1, POINT_ROWS + 1):
        vals = {f: request.form.get(f"pt-{i}-{f}", "").strip() for f in POINT_FIELDS}
        if not any(vals.values()):
            continue
        rec.points.append(FlowTestPoint(
            operating_no=i,
            operating_type=vals["operating_type"] or None,
            discharge_lps=_num(vals["discharge_lps"]),
            head_m=_num(vals["head_m"]),
            drawdown_m=_num(vals["drawdown_m"]),
            dynamic_level_m=_num(vals["dynamic_level_m"]),
            pressure_atm=_num(vals["pressure_atm"]),
            amperes=vals["amperes"] or None,
            efficiency=_num(vals["efficiency"]),
        ))


@bp.route("/wells/<int:well_id>/flow/new", methods=["GET", "POST"])
@permission_required("operation", "create")
def create(well_id):
    well = db.get_or_404(Well, well_id)
    form = FlowTestForm()
    if form.validate_on_submit():
        rec = FlowTest(well_id=well.id, created_by_id=current_user.id)
        _apply_header(form, rec)
        db.session.add(rec)
        _apply_points(rec)
        db.session.flush()
        workflow.log_change(rec, "create")
        db.session.commit()
        flash("دبی‌سنجی ثبت شد (پیش‌نویس).", "success")
        return redirect(url_for("operation.detail", record_id=rec.id))
    return render_template("operation/form.html", form=form, well=well,
                           title="ثبت دبی‌سنجی", points=[], operating_types=OPERATING_TYPES,
                           point_rows=POINT_ROWS, point_fields=POINT_FIELDS)


@bp.route("/flow/<int:record_id>")
@permission_required("operation", "view")
def detail(record_id):
    rec = db.get_or_404(FlowTest, record_id)
    history = db.session.scalars(
        db.select(RecordHistory).filter_by(entity_type="flow_tests", entity_id=rec.id)
        .order_by(RecordHistory.timestamp.desc())
    ).all()
    return render_template("operation/detail.html", rec=rec, well=rec.well,
                           history=history, editable=workflow.is_editable(rec))


@bp.route("/flow/<int:record_id>/edit", methods=["GET", "POST"])
@permission_required("operation", "edit")
def edit(record_id):
    rec = db.get_or_404(FlowTest, record_id)
    if not workflow.is_editable(rec):
        flash("این رکورد قفل است؛ ابتدا باید به پیش‌نویس بازگردانده شود.", "warning")
        return redirect(url_for("operation.detail", record_id=rec.id))
    form = FlowTestForm(obj=rec)
    if form.validate_on_submit():
        _apply_header(form, rec)
        _apply_points(rec)
        rec.updated_by_id = current_user.id
        workflow.log_change(rec, "update")
        db.session.commit()
        flash("دبی‌سنجی به‌روزرسانی شد.", "success")
        return redirect(url_for("operation.detail", record_id=rec.id))
    return render_template("operation/form.html", form=form, well=rec.well,
                           title="ویرایش دبی‌سنجی", points=rec.points,
                           operating_types=OPERATING_TYPES, point_rows=POINT_ROWS,
                           point_fields=POINT_FIELDS)


@bp.route("/flow/<int:record_id>/delete", methods=["POST"])
@permission_required("operation", "delete")
def delete(record_id):
    rec = db.get_or_404(FlowTest, record_id)
    well_id = rec.well_id
    db.session.delete(rec)
    db.session.commit()
    flash("دبی‌سنجی حذف شد.", "info")
    return redirect(url_for("wells.detail", well_id=well_id))


def _transition(record_id, fn, perm_action, msg, **kw):
    rec = db.get_or_404(FlowTest, record_id)
    if not current_user.has_permission("operation", perm_action):
        abort(403)
    try:
        fn(rec, **kw)
        db.session.commit()
        flash(msg, "success")
    except workflow.WorkflowError as e:
        db.session.rollback()
        flash(str(e), "danger")
    return redirect(url_for("operation.detail", record_id=record_id))


@bp.route("/flow/<int:record_id>/submit", methods=["POST"])
def submit(record_id):
    return _transition(record_id, workflow.submit, "edit", "برای تأیید ثبت شد.")


@bp.route("/flow/<int:record_id>/approve", methods=["POST"])
def approve(record_id):
    return _transition(record_id, workflow.approve, "approve", "تأیید شد.")


@bp.route("/flow/<int:record_id>/reject", methods=["POST"])
def reject(record_id):
    return _transition(record_id, workflow.reject, "approve", "برگشت داده شد.",
                       reason=request.form.get("reason", ""))


@bp.route("/flow/<int:record_id>/revert", methods=["POST"])
def revert(record_id):
    return _transition(record_id, workflow.revert_to_draft, "approve", "به پیش‌نویس بازگردانده شد.")



################################################################################
# FILE: blueprints\orgs\__init__.py
################################################################################

from flask import Blueprint

bp = Blueprint("orgs", __name__, url_prefix="/orgs")

from app.blueprints.orgs import routes  # noqa: E402,F401



################################################################################
# FILE: blueprints\orgs\routes.py
################################################################################

from flask import render_template, redirect, url_for, flash, request
from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, SubmitField
from wtforms.validators import DataRequired, Optional

from app.extensions import db
from app.blueprints.orgs import bp
from app.security import permission_required
from app.models.org import OrgUnit
from app.models.constants import ORG_UNIT_TYPES


class OrgUnitForm(FlaskForm):
    name = StringField("نام", validators=[DataRequired()])
    code = StringField("کد", validators=[Optional()])
    unit_type = SelectField("نوع", choices=ORG_UNIT_TYPES, validators=[DataRequired()])
    parent_id = SelectField("واحد بالادست", coerce=int, validators=[Optional()])
    submit = SubmitField("ذخیره")

    def populate_parents(self, exclude_id=None):
        units = db.session.scalars(db.select(OrgUnit).order_by(OrgUnit.name)).all()
        choices = [(0, "— بدون والد —")]
        for u in units:
            if exclude_id and u.id == exclude_id:
                continue
            choices.append((u.id, f"{u.name} ({dict(ORG_UNIT_TYPES).get(u.unit_type, '')})"))
        self.parent_id.choices = choices


@bp.route("/")
@permission_required("orgs", "view")
def list_orgs():
    units = db.session.scalars(
        db.select(OrgUnit).order_by(OrgUnit.unit_type, OrgUnit.name)
    ).all()
    type_labels = dict(ORG_UNIT_TYPES)
    return render_template("orgs/list.html", units=units, type_labels=type_labels)


@bp.route("/new", methods=["GET", "POST"])
@permission_required("orgs", "create")
def create_org():
    form = OrgUnitForm()
    form.populate_parents()
    if form.validate_on_submit():
        unit = OrgUnit(
            name=form.name.data.strip(),
            code=(form.code.data or "").strip() or None,
            unit_type=form.unit_type.data,
            parent_id=form.parent_id.data or None,
        )
        db.session.add(unit)
        db.session.commit()
        flash("واحد سازمانی ایجاد شد.", "success")
        return redirect(url_for("orgs.list_orgs"))
    return render_template("orgs/form.html", form=form, title="واحد سازمانی جدید")


@bp.route("/<int:unit_id>/edit", methods=["GET", "POST"])
@permission_required("orgs", "edit")
def edit_org(unit_id):
    unit = db.get_or_404(OrgUnit, unit_id)
    form = OrgUnitForm(obj=unit)
    form.populate_parents(exclude_id=unit.id)
    if form.validate_on_submit():
        unit.name = form.name.data.strip()
        unit.code = (form.code.data or "").strip() or None
        unit.unit_type = form.unit_type.data
        unit.parent_id = form.parent_id.data or None
        db.session.commit()
        flash("واحد سازمانی به‌روزرسانی شد.", "success")
        return redirect(url_for("orgs.list_orgs"))
    return render_template("orgs/form.html", form=form, title="ویرایش واحد سازمانی")


@bp.route("/<int:unit_id>/delete", methods=["POST"])
@permission_required("orgs", "delete")
def delete_org(unit_id):
    unit = db.get_or_404(OrgUnit, unit_id)
    if unit.children:
        flash("این واحد دارای زیرمجموعه است و قابل حذف نیست.", "danger")
        return redirect(url_for("orgs.list_orgs"))
    db.session.delete(unit)
    db.session.commit()
    flash("واحد سازمانی حذف شد.", "info")
    return redirect(url_for("orgs.list_orgs"))



################################################################################
# FILE: blueprints\permit\__init__.py
################################################################################

from flask import Blueprint

bp = Blueprint("permit", __name__, url_prefix="/permits")

from app.blueprints.permit import routes  # noqa: E402,F401



################################################################################
# FILE: blueprints\permit\routes.py
################################################################################

"""وضعیت پروانه چاه‌ها.

صفحه‌ی تحلیل وضعیت پروانه بر پایه‌ی جدول production_trend (ستون‌های well_permit و
permit_expiry) و فرم ورود/ویرایش اطلاعات پروانه‌ی هر چاه (به‌روزرسانی مستقیم همان
جدول). تاریخ اعتبار به‌صورت شمسیِ فشرده (مثل 14050427) است و وضعیت انقضا با مقایسه
با تاریخ امروز محاسبه می‌شود.
"""
from datetime import date
from collections import Counter

import jdatetime
from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required
from sqlalchemy import text

from app.extensions import db
from app.blueprints.permit import bp
from app.models.well import Well
from app.imports.wells_import import match_key


def _digits8(s):
    if not s:
        return None
    d = "".join(ch for ch in str(s) if ch.isdigit())
    return d if len(d) == 8 else None


def _today8():
    t = jdatetime.date.fromgregorian(date=date.today())
    return f"{t.year:04d}{t.month:02d}{t.day:02d}"


def _expiry_state(expiry, today8):
    e = _digits8(expiry)
    if not e:
        return "unknown"
    if e < today8:
        return "expired"
    ey, em = int(e[:4]), int(e[4:6])
    ty, tm = int(today8[:4]), int(today8[4:6])
    months_left = (ey - ty) * 12 + (em - tm)
    return "near" if months_left < 3 else "valid"


STATE_LABEL = {"expired": "منقضی شده", "near": "نزدیک انقضا",
               "valid": "معتبر", "unknown": "نامشخص"}


@bp.route("/")
@login_required
def index():
    today8 = _today8()
    # نگاشت نام چاه به شناسه‌ی چاه سامانه (برای لینک به جزئیات چاه)
    well_by_key = {}
    for w in db.session.scalars(db.select(Well)).all():
        well_by_key.setdefault(match_key(w.name), w.id)
    result = db.session.execute(text(
        "SELECT rowid, well_name, department, well_permit, permit_expiry, "
        "well_type, main_zone FROM production_trend"
    ))
    rows = []
    state_counter = Counter()
    type_counter = Counter()
    for r in result.fetchall():
        rowid, name, dept, permit, expiry, wtype, zone = r
        if not name or not str(name).strip():
            continue
        st = _expiry_state(expiry, today8)
        state_counter[st] += 1
        if permit and str(permit).strip() and str(permit).strip() != "0":
            type_counter[str(permit).strip()] += 1
            wid = well_by_key.get(match_key(name))
        rows.append({
            "well_id": wid, "rowid": rowid, "well_name": name, "office": dept or "—",
            "permit_type": (permit if permit and str(permit) != "0" else "—"),
            "expiry": expiry or "—", "state": st, "state_label": STATE_LABEL[st],
            "well_type": wtype or "—", "zone": zone or "—",
        })
    order = {"expired": 0, "near": 1, "valid": 2, "unknown": 3}
    rows.sort(key=lambda r: (order.get(r["state"], 9), str(r["expiry"])))

    stats = {
        "total": len(rows),
        "expired": state_counter.get("expired", 0),
        "near": state_counter.get("near", 0),
        "valid": state_counter.get("valid", 0),
        "unknown": state_counter.get("unknown", 0),
        "types": type_counter.most_common(),
    }
    return render_template("permit/index.html", rows=rows, stats=stats)


@bp.route("/<int:rowid>/edit", methods=["GET", "POST"])
@login_required
def edit(rowid):
    row = db.session.execute(
        text("SELECT rowid, well_name, department, well_permit, permit_expiry "
             "FROM production_trend WHERE rowid=:i"), {"i": rowid}
    ).fetchone()
    if not row:
        flash("چاه پیدا نشد.", "warning")
        return redirect(url_for("permit.index"))

    if request.method == "POST":
        permit = request.form.get("well_permit", "").strip()
        expiry = request.form.get("permit_expiry", "").strip()
        db.session.execute(
            text("UPDATE production_trend SET well_permit=:p, permit_expiry=:e "
                 "WHERE rowid=:i"),
            {"p": permit or None, "e": expiry or None, "i": rowid},
        )
        db.session.commit()
        flash("وضعیت پروانه به‌روزرسانی شد.", "success")
        return redirect(url_for("permit.index"))

    rec = {"rowid": row[0], "well_name": row[1], "office": row[2],
           "well_permit": row[3] or "", "permit_expiry": row[4] or ""}
    return render_template("permit/form.html", rec=rec)



################################################################################
# FILE: blueprints\permit_event\__init__.py
################################################################################

from flask import Blueprint

bp = Blueprint("permit_event", __name__, url_prefix="/permit-event")

from app.blueprints.permit_event import routes  # noqa: E402,F401


################################################################################
# FILE: blueprints\permit_event\routes.py
################################################################################

from flask import render_template, redirect, url_for, flash, request, abort
from flask_login import current_user
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, BooleanField, SubmitField
from wtforms.validators import Optional, ValidationError

from app.extensions import db
from app.blueprints.permit_event import bp
from app.security import permission_required
from app.utils.forms import JalaliDateField, PersianFloatField as FloatField
from app.models.well import Well
from app.models.permit_event import WellPermitEvent
from app.models.audit import RecordHistory
from app import workflow


PERMIT_TYPES = [
    ("", "—"),
    ("بهره‌برداری عادی", "بهره‌برداری عادی"),
    ("حفر", "حفر"),
    ("تغییر محل", "تغییر محل"),
    ("کف‌شکنی", "کف‌شکنی"),
]


class PermitEventForm(FlaskForm):
    permit_type = SelectField("نوع پروانه", choices=PERMIT_TYPES, validators=[Optional()])
    permit_code = StringField("کد آخرین پروانه", validators=[Optional()])
    permit_no = StringField("شماره پروانه", validators=[Optional()])
    permit_date = JalaliDateField("تاریخ صدور", validators=[Optional()])
    expiry_date = JalaliDateField("تاریخ اعتبار/انقضا", validators=[Optional()])
    case_status = StringField("وضعیت پرونده", validators=[Optional()])
    klasse = StringField("کلاسه آب منطقه‌ای", validators=[Optional()])
    request_type = StringField("درخواست جاری (تمدید/صدور/جابجایی)", validators=[Optional()])
    followup_stage = StringField("مرحله پیگیری", validators=[Optional()])
    cost_paid = BooleanField("هزینه پرداخت شده", validators=[Optional()])
    expiry_penalty_rial = FloatField("جریمه انقضا (ریال)", validators=[Optional()])
    notes = TextAreaField("توضیحات", validators=[Optional()])
    submit = SubmitField("ذخیره")

    def validate_expiry_date(self, field):
        if field.data and self.permit_date.data and field.data < self.permit_date.data:
            raise ValidationError("تاریخ اعتبار نمی‌تواند پیش از تاریخ صدور باشد.")

    def validate_expiry_penalty_rial(self, field):
        if field.data is not None and field.data < 0:
            raise ValidationError("جریمه نمی‌تواند منفی باشد.")


SIMPLE = ["permit_type", "permit_code", "permit_no", "permit_date", "expiry_date",
          "case_status", "klasse", "request_type", "followup_stage", "notes"]


def _apply(form, rec):
    for f in SIMPLE:
        setattr(rec, f, getattr(form, f).data or None)
    rec.cost_paid = form.cost_paid.data
    rec.expiry_penalty_rial = form.expiry_penalty_rial.data


@bp.route("/wells/<int:well_id>/permit/new", methods=["GET", "POST"])
@permission_required("permit", "create")
def create(well_id):
    well = db.get_or_404(Well, well_id)
    form = PermitEventForm()
    if form.validate_on_submit():
        rec = WellPermitEvent(well_id=well.id, created_by_id=current_user.id, source="manual")
        _apply(form, rec)
        db.session.add(rec)
        db.session.flush()
        workflow.log_change(rec, "create")
        db.session.commit()
        flash("پروانه ثبت شد (پیش‌نویس).", "success")
        return redirect(url_for("permit_event.detail", record_id=rec.id))
    return render_template("permit_event/form.html", form=form, well=well, title="ثبت پروانه")


@bp.route("/permit/<int:record_id>")
@permission_required("permit", "view")
def detail(record_id):
    rec = db.get_or_404(WellPermitEvent, record_id)
    history = db.session.scalars(
        db.select(RecordHistory).filter_by(entity_type="well_permit_events", entity_id=rec.id)
        .order_by(RecordHistory.timestamp.desc())
    ).all()
    return render_template("permit_event/detail.html", rec=rec, well=rec.well,
                           history=history, editable=workflow.is_editable(rec))


@bp.route("/permit/<int:record_id>/edit", methods=["GET", "POST"])
@permission_required("permit", "edit")
def edit(record_id):
    rec = db.get_or_404(WellPermitEvent, record_id)
    if not workflow.is_editable(rec):
        flash("این رکورد قفل است؛ ابتدا باید به پیش‌نویس بازگردانده شود.", "warning")
        return redirect(url_for("permit_event.detail", record_id=rec.id))
    form = PermitEventForm(obj=rec)
    if form.validate_on_submit():
        _apply(form, rec)
        rec.updated_by_id = current_user.id
        workflow.log_change(rec, "update")
        db.session.commit()
        flash("پروانه به‌روزرسانی شد.", "success")
        return redirect(url_for("permit_event.detail", record_id=rec.id))
    return render_template("permit_event/form.html", form=form, well=rec.well, title="ویرایش پروانه")


@bp.route("/permit/<int:record_id>/delete", methods=["POST"])
@permission_required("permit", "delete")
def delete(record_id):
    rec = db.get_or_404(WellPermitEvent, record_id)
    well_id = rec.well_id
    db.session.delete(rec)
    db.session.commit()
    flash("رکورد پروانه حذف شد.", "info")
    return redirect(url_for("wells.detail", well_id=well_id))


def _transition(record_id, fn, perm_action, msg, **kw):
    rec = db.get_or_404(WellPermitEvent, record_id)
    if not current_user.has_permission("permit", perm_action):
        abort(403)
    try:
        fn(rec, **kw)
        db.session.commit()
        flash(msg, "success")
    except workflow.WorkflowError as e:
        db.session.rollback()
        flash(str(e), "danger")
    return redirect(url_for("permit_event.detail", record_id=record_id))


@bp.route("/permit/<int:record_id>/submit", methods=["POST"])
def submit(record_id):
    return _transition(record_id, workflow.submit, "edit", "برای تأیید ثبت شد.")


@bp.route("/permit/<int:record_id>/approve", methods=["POST"])
def approve(record_id):
    return _transition(record_id, workflow.approve, "approve", "تأیید شد.")


@bp.route("/permit/<int:record_id>/reject", methods=["POST"])
def reject(record_id):
    return _transition(record_id, workflow.reject, "approve", "برگشت داده شد.",
                       reason=request.form.get("reason", ""))


@bp.route("/permit/<int:record_id>/revert", methods=["POST"])
def revert(record_id):
    return _transition(record_id, workflow.revert_to_draft, "approve", "به پیش‌نویس بازگردانده شد.")


################################################################################
# FILE: blueprints\printing\__init__.py
################################################################################

from flask import Blueprint

bp = Blueprint("printing", __name__, url_prefix="/print")

from app.blueprints.printing import routes  # noqa: E402,F401



################################################################################
# FILE: blueprints\printing\routes.py
################################################################################

"""Official print-ready reports (browser Print-to-PDF, RTL/Persian, zero deps)."""
from flask import render_template, url_for

from app.extensions import db
from app.blueprints.printing import bp
from app.security import permission_required
from app.models.well import Well
from app.models.constants import WELL_KINDS, WELL_STATUSES
from app.utils.dates import format_jalali as fj


def _today():
    import jdatetime
    return jdatetime.date.today().strftime("%Y/%m/%d")


@bp.route("/well/<int:well_id>")
@permission_required("wells", "view")
def well_sheet(well_id):
    w = db.get_or_404(Well, well_id)
    from app.models.drilling import Drilling
    from app.models.pump_asset import PumpInstallation
    from app.models.baseline import WellBaseline
    dr = db.session.scalar(db.select(Drilling).filter_by(well_id=w.id)
                           .order_by(Drilling.end_date.desc()))
    inst = db.session.scalar(db.select(PumpInstallation).filter_by(well_id=w.id)
                             .order_by(PumpInstallation.install_date.desc()))
    base = db.session.scalar(db.select(WellBaseline).filter_by(well_id=w.id, is_current=True))
    return render_template(
        "print/well_sheet.html", w=w, tech=w.technical, dr=dr, inst=inst, base=base,
        kind_labels=dict(WELL_KINDS), status_labels=dict(WELL_STATUSES),
        today=_today(), doc_id=w.display_pm, fj=fj,
        back_url=url_for("wells.detail", well_id=w.id))


@bp.route("/pump-test/<int:record_id>")
@permission_required("pump_test", "view")
def pump_test(record_id):
    from app.models.pump_test import PumpTest
    rec = db.get_or_404(PumpTest, record_id)
    return render_template("print/pump_test.html", rec=rec, w=rec.well,
                           today=_today(), doc_id=rec.well.display_pm, fj=fj,
                           back_url=url_for("pump_test.detail", record_id=rec.id))


@bp.route("/flow/<int:record_id>")
@permission_required("operation", "view")
def flow(record_id):
    from app.models.flow import FlowTest
    rec = db.get_or_404(FlowTest, record_id)
    return render_template("print/flow.html", rec=rec, w=rec.well,
                           today=_today(), doc_id=rec.well.display_pm, fj=fj,
                           back_url=url_for("operation.detail", record_id=rec.id))



################################################################################
# FILE: blueprints\production_trend\__init__.py
################################################################################

from flask import Blueprint

bp = Blueprint("production_trend", __name__, url_prefix="/production-trend")

from app.blueprints.production_trend import routes  # noqa: E402,F401



################################################################################
# FILE: blueprints\production_trend\column_import.py
################################################################################

"""افزودن سرستون جدید به جدول production_trend (روش A: ستون واقعی).

کاربر دسته/سال/ماه و فایل اکسل می‌دهد؛ سیستم نام ستون انگلیسی را طبق قرارداد
data_map می‌سازد، ستون را (در صورت نبود) به جدول اضافه می‌کند، و مقادیر را با
تطبیق نام چاه پر می‌کند. نام ستون‌ها اعتبارسنجی می‌شوند تا امن باشند.
"""
import re
import openpyxl
from sqlalchemy import text

from app.extensions import db
from app.imports.wells_import import match_key
from app.blueprints.production_trend.data_map import MONTHS_EN, MONTHS_FA
def _recalc_yearly(category, year):
    """ستون مجموع/میانگین سالانه را از روی ماه‌های موجود همان سال بازمحاسبه می‌کند."""
    cols_now = _existing_columns()
    # ماه‌های موجود این دسته/سال را جمع کن
    month_cols = []
    for mi in range(12):
        mc = make_column_name(category, year, mi)
        if mc in cols_now:
            month_cols.append(mc)
    if not month_cols:
        return

    # نام ستون سالانه
    year_col = make_column_name(category, year, None)
    if not year_col:
        return
    # اگر ستون سالانه نبود بساز
    if year_col not in cols_now:
        sqltype = CATEGORY_SQLTYPE.get(category, "REAL")
        db.session.execute(text(
            f'ALTER TABLE production_trend ADD COLUMN "{year_col}" {sqltype}'))
        db.session.commit()

    # تولید و کارکرد → جمع؛ فشار و دبی → میانگین
    is_sum = category in ("production", "runtime")
    sum_expr = " + ".join(f'COALESCE("{c}",0)' for c in month_cols)
    cnt_expr = " + ".join(f'(CASE WHEN "{c}" IS NOT NULL THEN 1 ELSE 0 END)' for c in month_cols)

    rows = db.session.execute(text(f'SELECT rowid, {sum_expr}, {cnt_expr} FROM production_trend')).fetchall()
    for rid, total, cnt in rows:
        if cnt and cnt > 0:
            val = total if is_sum else round(total / cnt, 2)
        else:
            val = None
        db.session.execute(
            text(f'UPDATE production_trend SET "{year_col}"=:v WHERE rowid=:i'),
            {"v": val, "i": rid})
    db.session.commit()

# دسته‌های پشتیبانی‌شده و الگوی نام ستون
CATEGORIES = {
    "production": "تولید",
    "average_flow": "دبی متوسط",
    "runtime": "کارکرد",
    "well_pressure": "فشار",
}

# نوع داده‌ی هر دسته در SQLite
CATEGORY_SQLTYPE = {
    "production": "INTEGER",
    "average_flow": "REAL",
    "runtime": "INTEGER",
    "well_pressure": "REAL",
}

SAFE_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


def make_column_name(category, year, month_idx):
    """نام ستون انگلیسی طبق قرارداد data_map. month_idx: 0..11 یا None برای سالانه."""
    if month_idx is None:
        # ستون سالانه
        if category == "production":
            return f"production_year_{year}"
        if category == "average_flow":
            return f"average_flow_year_{year}"
        if category == "runtime":
            return f"runtime_year_{year}"
        if category == "well_pressure":
            return f"pressure_year_{year}"
        return None
    m = MONTHS_EN[month_idx]
    if category == "production":
        return f"production_{year}_{m}"
    if category == "average_flow":
        return f"average_flow_{year}_{m}"
    if category == "runtime":
        return f"runtime_{m}_{year}"
    if category == "well_pressure":
        return f"well_pressure_{year}_{m}"
    return None


def _existing_columns():
    rows = db.session.execute(text("PRAGMA table_info(production_trend)")).fetchall()
    return {r[1] for r in rows}


def _find_key_and_value_columns(header):
    """ستون نام چاه و ستون داده را در هدر اکسل تشخیص می‌دهد."""
    name_col = None
    for i, h in enumerate(header):
        if h and any(k in str(h) for k in ("نام چاه", "نام", "چاه")):
            name_col = i
            break
    # ستون داده: اولین ستون عددیِ غیر از ستون نام (ساده: دومین ستون پرشده)
    value_col = None
    for i, h in enumerate(header):
        if i != name_col and h not in (None, ""):
            value_col = i
            break
    return name_col, value_col


def run(path, category, year, month_idx):
    """اکسل را می‌خواند و ستون جدید را می‌سازد/پر می‌کند. آمار برمی‌گرداند."""
    if category not in CATEGORIES:
        raise ValueError("دسته‌ی نامعتبر.")
    col = make_column_name(category, year, month_idx)
    if not col or not SAFE_NAME.match(col):
        raise ValueError(f"نام ستون نامعتبر ساخته شد: {col}")

    sqltype = CATEGORY_SQLTYPE[category]
    stats = {"column": col, "added_column": False, "rows": 0,
             "matched": 0, "unmatched": 0}

    # ۱) افزودن ستون اگر نبود
    if col not in _existing_columns():
        db.session.execute(text(f'ALTER TABLE production_trend ADD COLUMN "{col}" {sqltype}'))
        db.session.commit()
        stats["added_column"] = True

    # ۲) خواندن اکسل
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    if not rows:
        raise ValueError("فایل اکسل خالی است.")
    header = rows[0]
    name_col, value_col = _find_key_and_value_columns(header)
    if name_col is None or value_col is None:
        raise ValueError("ستون نام چاه یا ستون داده در اکسل پیدا نشد.")

    # ۳) نگاشت نام چاه production_trend → rowid
    pt = db.session.execute(text("SELECT rowid, well_name FROM production_trend")).fetchall()
    by_key = {}
    for rowid, wname in pt:
        by_key.setdefault(match_key(wname), rowid)

    # ۴) پر کردن مقادیر
    for row in rows[1:]:
        if name_col >= len(row):
            continue
        name = row[name_col]
        if not name or not str(name).strip():
            continue
        stats["rows"] += 1
        val = row[value_col] if value_col < len(row) else None
        rid = by_key.get(match_key(name))
        if rid is None:
            stats["unmatched"] += 1
            continue
        db.session.execute(
            text(f'UPDATE production_trend SET "{col}"=:v WHERE rowid=:i'),
            {"v": val, "i": rid},
        )
        stats["matched"] += 1
# محاسبه‌ی خودکار دبی متوسط اگر تولید و کارکرد همان ماه موجود باشند
    if category in ("production", "runtime") and month_idx is not None:
        prod_col = make_column_name("production", year, month_idx)
        run_col = make_column_name("runtime", year, month_idx)
        flow_col = make_column_name("average_flow", year, month_idx)
        cols_now = _existing_columns()
        # فقط اگر هر دو ستون تولید و کارکرد وجود دارند
        if prod_col in cols_now and run_col in cols_now:
            if flow_col not in cols_now:
                db.session.execute(text(
                    f'ALTER TABLE production_trend ADD COLUMN "{flow_col}" REAL'))
                db.session.commit()
            # برای هر چاه دبی را حساب کن: تولید×۱۰۰۰ ÷ (کارکرد×۳۶۰۰)
            rows_calc = db.session.execute(text(
                f'SELECT rowid, "{prod_col}", "{run_col}" FROM production_trend')).fetchall()
            flow_filled = 0
            for rid, prod_v, run_v in rows_calc:
                try:
                    p = float(prod_v) if prod_v not in (None, "") else None
                    h = float(run_v) if run_v not in (None, "") else None
                except (ValueError, TypeError):
                    p, h = None, None
                if p is None or h is None or h <= 0:
                    continue
                flow = round(p * 1000.0 / (h * 3600.0), 2)
                if flow < 0 or flow > 1000:  # اعتبارسنجی: مقدار غیرمنطقی رد شود
                    continue
                db.session.execute(
                    text(f'UPDATE production_trend SET "{flow_col}"=:v WHERE rowid=:i'),
                    {"v": flow, "i": rid})
                flow_filled += 1
            db.session.commit()
            stats["flow_calculated"] = flow_filled
            # به‌روزرسانی ستون مجموع/میانگین سالانه بعد از افزودن ماه جدید
    if month_idx is not None:
        _recalc_yearly(category, year)

    db.session.commit()
    return stats

    db.session.commit()
    return stats


################################################################################
# FILE: blueprints\production_trend\data_map.py
################################################################################

"""نگاشت ستون‌های انگلیسیِ جدول production_trend به کلیدهای فارسیِ اکسلِ داشبورد.

هدف: داشبورد قدیمی (script.js) داده را با کلیدهای فارسی مثل «تولید سال ۱۴۰۴» یا
«دبی متوسط ۱۴۰۴(فروردین)» می‌خواند. این ماژول هر ردیف جدول را به یک dict با همان
کلیدهای فارسی برمی‌گرداند تا کل منطق داشبورد بدون تغییر کار کند.

ستون‌های سری‌زمانی با الگو ساخته می‌شوند؛ ستون‌های ثابت نگاشت دستی دارند.
"""

# ماه‌های شمسی به ترتیب (۱..۱۲) و معادل انگلیسیِ به‌کاررفته در نام ستون‌ها
MONTHS_FA = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
             "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]
MONTHS_EN = ["farvardin", "ordibehesht", "khordad", "tir", "mordad", "shahrivar",
             "mehr", "aban", "azar", "dey", "bahman", "esfand"]
YEARS = [1399, 1400, 1401, 1402, 1403, 1404, 1405]

# ---------- نگاشت ستون‌های ثابت: انگلیسی → فارسیِ اکسل ----------
STATIC_MAP = {
    "well_name": "نام چاه",
    "department": "اداره",
    "production_zone_name": "نام پهنه تولید",
    "low_runtime_reason": "علت کارکرد کم",
    "electropump_installation_date": "تاریخ نصب الکتروپمپ",
    "observed_fault_last_rehabilitation": "خرابی مشاهده شده آخرین بهسازی",
    "last_rehabilitation_date": "تاریخ آخرین بهسازی",
    "permit_expiry": "اعتبار پروانه",
    "well_permit": "پروانه چاه",
    "well_type": "نوع چاه",
    "well_location_status": "وضعیت تعیین محل چاه",
    "proposed_permitted_flow_lps": "دبی مجاز پیشنهادی",
    "test_end_date": "تاریخ پایان آزمایش",
    "contractor": "پیمانکار",
    "drilling_year": "سال حفر",
    "max_flow_rate": "حداکثر آبدهی",
    "drawdown_amount": "مقدار افت",
    "static_level": "سطح استاتیک",
    "dynamic_level": "سطح دینامیک",
    "main_zone": "پهنه اصلی",
    "sub_zone": "زیر پهنه",
    "well_status": "وضعیت چاه",
    "full_cycle_count": "تعداد دوره کامل",
    "full_average_months": "میانگین کامل (ماه)",
    "total_average_with_open_installation_months": "میانگین کل با نصب باز (ماه)",
    "contractors": "پیمانکار ها",
}

# نگاشت پسوندهای دوره‌ی نصب/کشیدن (۱..۵ و «باز»)
CYCLE_BASE = {
    "installation": "نصب",
    "motor": "موتور",
    "motor_new_repaired": "موتور نو/تعمیری",
    "pump": "پمپ",
    "manufacturer": "سازنده",
    "pump_new_repaired": "پمپ نو/تعمیری",
    "stage": "طبقه",
    "depth": "عمق",
    "pulling": "کشیدن",
    "interval": None,  # ویژه (interval_1_months → فاصله۱ (ماه))
}


def _build_static_full():
    """نگاشت کامل ستون‌های ثابت شامل ستون‌های دوره‌ای (۱..۵ و open)."""
    m = dict(STATIC_MAP)
    suffixes = [("1", "1"), ("2", "2"), ("3", "3"), ("4", "4"), ("5", "5"),
                ("open", " (باز)")]
    for en_sfx, fa_sfx in suffixes:
        m[f"installation_{en_sfx}"] = f"نصب{fa_sfx}"
        m[f"motor_{en_sfx}"] = f"موتور{fa_sfx}"
        m[f"motor_new_repaired_{en_sfx}"] = f"موتور نو/تعمیری{fa_sfx}"
        m[f"pump_{en_sfx}"] = f"پمپ{fa_sfx}"
        m[f"manufacturer_{en_sfx}"] = f"سازنده{fa_sfx}"
        m[f"pump_new_repaired_{en_sfx}"] = f"پمپ نو/تعمیری{fa_sfx}"
        m[f"stage_{en_sfx}"] = f"طبقه{fa_sfx}"
        m[f"depth_{en_sfx}"] = f"عمق{fa_sfx}"
        if en_sfx != "open":
            m[f"pulling_{en_sfx}"] = f"کشیدن{fa_sfx}"
            m[f"interval_{en_sfx}_months"] = f"فاصله{fa_sfx} (ماه)"
    return m


STATIC_FULL = _build_static_full()


def _ts_map_for_column(col):
    """اگر ستون سری‌زمانی بود، کلید فارسی معادل را برمی‌گرداند، وگرنه None."""
    for y in YEARS:
        ys = str(y)
        # --- تولید ---
        if col == f"production_year_{ys}":
            return f"تولید سال {y}"
        for i, (men, mfa) in enumerate(zip(MONTHS_EN, MONTHS_FA)):
            if col == f"production_{ys}_{men}":
                return f"تولید {y}({mfa})"
        # --- کارکرد (runtime) ---
        if col == f"runtime_year_{ys}":
            return f"کارکرد سال {y}"
        for men, mfa in zip(MONTHS_EN, MONTHS_FA):
            if col == f"runtime_{men}_{ys}":
                return f"کارکرد {mfa} {y}"
        # --- دبی متوسط (average_flow) ---
        if col == f"average_flow_year_{ys}":
            return f"دبی متوسط سال {y}"
        for men, mfa in zip(MONTHS_EN, MONTHS_FA):
            if col == f"average_flow_{ys}_{men}":
                return f"دبی متوسط {y}({mfa})"
        # --- فشار (well_pressure) ---
        if col == f"pressure_year_{ys}":
            return f"فشار سال {y}"
        for men, mfa in zip(MONTHS_EN, MONTHS_FA):
            if col == f"well_pressure_{ys}_{men}":
                return f"فشار چاه {y}({mfa})"
        # --- تاریخ‌های آزمایش ---
        if col == f"test_date_{ys}":
            return f"تاریخ آزمایش {y}"
        if col == f"flow_test_date_{ys}":
            return f"تاریخ آزمایش دبی {y}"
        if col == f"flow_rate_lps_{ys}":
            return f"آبدهی (lit/s) {y}"
        if col == f"pressure_test_date_{ys}":
            return f"تاریخ آزمایش فشار {y}"
        if col == f"pressure_atm_{ys}":
            return f"فشار (atm) {y}"
        # --- پیمانکار سال / دبی سالانه نسبت ---
        if col == f"contractor_{ys}":
            return f"پیمانکار {y}"
        if col == f"average_flow_year_{ys}_vs_1399":
            return f"نسبت دبی متوسط {y} به 1399"
        # --- ترخیص (removal) ماهانه ---
        for men, mfa in zip(MONTHS_EN, MONTHS_FA):
            if col == f"removal_{men}_{ys}":
                return f"ترخیص {mfa} {y}"
    # ستون ویژه‌ی سن
    if col.startswith("age_until_") and col.endswith("_months"):
        return "عمر تا 1405/03/01 (ماه)"
    return None


def build_column_map(columns):
    """dict: نام ستون انگلیسی → کلید فارسیِ اکسل، برای همه‌ی ستون‌های موجود."""
    result = {}
    for col in columns:
        if col in STATIC_FULL:
            result[col] = STATIC_FULL[col]
            continue
        fa = _ts_map_for_column(col)
        result[col] = fa if fa else col  # اگر نگاشتی نبود، همان نام انگلیسی
    return result


def rows_to_fa_dicts(columns, rows):
    """ردیف‌های جدول را به لیست dict با کلیدهای فارسی تبدیل می‌کند."""
    cmap = build_column_map(columns)
    fa_keys = [cmap[c] for c in columns]
    out = []
    for row in rows:
        d = {}
        for k, v in zip(fa_keys, row):
            d[k] = v
        out.append(d)
    return out



################################################################################
# FILE: blueprints\production_trend\routes.py
################################################################################

"""تحلیل روند تولید چاه‌ها.

داشبورد کاملِ کلاینت (همان script.js اصلی با همه‌ی تب‌ها و نمودارها) در iframe
نمایش داده می‌شود، اما داده به‌جای فایل اکسل از جدول production_trend خوانده و
با کلیدهای فارسیِ اکسل به‌صورت JSON در اختیار داشبورد گذاشته می‌شود.
"""
from flask import render_template, jsonify, request, redirect, url_for, flash
from flask_login import login_required
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired, FileAllowed
from wtforms import SelectField, SubmitField
from wtforms.validators import DataRequired
import os
import tempfile
from sqlalchemy import text

from app.extensions import db
from app.blueprints.production_trend import bp
from app.blueprints.production_trend.data_map import rows_to_fa_dicts


@bp.route("/")
@login_required
def index():
    return render_template("production_trend/index.html")


@bp.route("/api/data")
@login_required
def api_data():
    """کل جدول production_trend را با کلیدهای فارسیِ اکسل برمی‌گرداند."""
    result = db.session.execute(text("SELECT * FROM production_trend"))
    columns = list(result.keys())
    rows = result.fetchall()
    data = rows_to_fa_dicts(columns, [tuple(r) for r in rows])
    # فقط ردیف‌های دارای نام چاه (مطابق فیلتر اصلی داشبورد)
    data = [d for d in data if d.get("نام چاه") and str(d.get("نام چاه")).strip()]
    resp = jsonify(data)
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp
CATEGORY_CHOICES = [
    ("production", "تولید"),
    ("runtime", "کارکرد"),
    ("well_pressure", "فشار"),
]

MONTH_CHOICES = [("-1", "سالانه (کل سال)")] + [
    (str(i), m) for i, m in enumerate(
        ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
         "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"])
]

YEAR_CHOICES = [(str(y), str(y)) for y in range(1399, 1411)]


class ColumnImportForm(FlaskForm):
    category = SelectField("دسته‌ی داده", choices=CATEGORY_CHOICES, validators=[DataRequired()])
    year = SelectField("سال", choices=YEAR_CHOICES, validators=[DataRequired()])
    month = SelectField("ماه", choices=MONTH_CHOICES, validators=[DataRequired()])
    excel = FileField("فایل اکسل (ستون اول: نام چاه، ستون دوم: مقدار)",
                      validators=[FileRequired(), FileAllowed(["xlsx", "xls"], "فقط فایل اکسل")])
    submit = SubmitField("افزودن سرستون و ورود داده")


@bp.route("/import-column", methods=["GET", "POST"])
@login_required
def import_column():
    from app.blueprints.production_trend.column_import import run
    form = ColumnImportForm()
    result = None
    if form.validate_on_submit():
        month_idx = int(form.month.data)
        month_arg = None if month_idx == -1 else month_idx
        # ذخیره‌ی موقت فایل آپلودی
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
        form.excel.data.save(tmp.name)
        tmp.close()
        try:
            result = run(tmp.name, form.category.data, int(form.year.data), month_arg)
            flash(f"ستون «{result['column']}» ساخته/به‌روزرسانی شد. "
                  f"تطبیق‌خورده: {result['matched']} | بدون تطبیق: {result['unmatched']}", "success")
        except Exception as e:
            flash(f"خطا در ورود داده: {e}", "danger")
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass  # اگر ویندوز اجازه‌ی حذف نداد، فایل موقت بعداً خودکار پاک می‌شود
        return redirect(url_for("production_trend.import_column"))
    return render_template("production_trend/import_column.html", form=form)


################################################################################
# FILE: blueprints\pump_select\__init__.py
################################################################################

from flask import Blueprint

bp = Blueprint("pump_select", __name__)

from app.blueprints.pump_select import routes  # noqa: E402,F401



################################################################################
# FILE: blueprints\pump_select\routes.py
################################################################################

from flask import render_template, redirect, url_for, flash, request, abort, jsonify
from flask_login import current_user, login_required
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SubmitField
from wtforms.validators import Optional

from app.extensions import db
from app.blueprints.pump_select import bp
from app.security import permission_required
from app.utils.forms import JalaliDateField, PersianFloatField as FloatField
from app.models.well import Well
from app.models.pump_select import PumpSelection
from app.models.audit import RecordHistory
from app.utils.dates import to_english_digits
from app import workflow


def _num(s):
    s = to_english_digits((s or "").strip())
    try:
        return float(s) if s else None
    except ValueError:
        return None


class PumpSelectionForm(FlaskForm):
    action_needed = StringField("اقدام مورد نیاز", validators=[Optional()])
    jyear = StringField("سال", validators=[Optional()])
    jmonth = StringField("ماه", validators=[Optional()])
    status_done = StringField("وضعیت انجام", validators=[Optional()])
    prev_pump_type = StringField("تیپ پمپ قبلی", validators=[Optional()])
    prev_motor_type = StringField("تیپ موتور قبلی", validators=[Optional()])
    prev_discharge_lps = FloatField("دبی قبلی (l/s)", validators=[Optional()])
    selected_pump_type = StringField("تیپ پمپ پس از بررسی", validators=[Optional()])
    selected_motor_type = StringField("تیپ موتور پس از بررسی", validators=[Optional()])
    target_discharge_lps = FloatField("دبی پس از بررسی (l/s)", validators=[Optional()])
    discharge_increase_lps = FloatField("میزان افزایش دبی", validators=[Optional()])
    selected_head_m = FloatField("هد پمپ انتخابی (m)", validators=[Optional()])
    form_delivery_date = JalaliDateField("تاریخ تحویل فرم", validators=[Optional()])
    pull_date = JalaliDateField("تاریخ کشیدن", validators=[Optional()])
    videometry_date = JalaliDateField("تاریخ ویدئومتری", validators=[Optional()])
    install_date = JalaliDateField("تاریخ نصب", validators=[Optional()])
    verify_flowtest_date = JalaliDateField("تاریخ دبی‌سنجی (صحت‌سنجی)", validators=[Optional()])
    verify_discharge_lps = FloatField("آبدهی دبی‌سنجی", validators=[Optional()])
    verify_head_m = FloatField("هد دبی‌سنجی", validators=[Optional()])
    notes = TextAreaField("توضیحات", validators=[Optional()])
    submit = SubmitField("ذخیره")


FIELDS = [
    "action_needed", "jyear", "jmonth", "status_done", "prev_pump_type", "prev_motor_type",
    "prev_discharge_lps", "selected_pump_type", "selected_motor_type", "target_discharge_lps",
    "discharge_increase_lps", "selected_head_m", "form_delivery_date", "pull_date",
    "videometry_date", "install_date", "verify_flowtest_date", "verify_discharge_lps",
    "verify_head_m", "notes",
]


def _apply(form, rec):
    for f in FIELDS:
        setattr(rec, f, getattr(form, f).data)


# ---------- catalog-driven selection calculator ----------
@bp.route("/pump-select/catalog.json")
@permission_required("pump_select", "view")
def catalog_json():
    from app.services.catalog import build_library
    return jsonify(build_library())


@bp.route("/pump-select/calculator")
@login_required
def calculator():
    from app.services.catalog import design_params
    well = None
    q, head, src = 10.0, 180, None
    well_id = request.args.get("well", type=int)
    if well_id:
        well = db.session.get(Well, well_id)
        if well:
            q, head, src = design_params(well)
    return render_template("pump_select/calculator.html", well=well, design_q=q,
                           design_head=head, src=src)


@bp.route("/wells/<int:well_id>/pump-select/from-calc", methods=["POST"])
@permission_required("pump_select", "create")
def from_calc(well_id):
    well = db.get_or_404(Well, well_id)
    rec = PumpSelection(
        well_id=well.id, created_by_id=current_user.id,
        action_needed="انتخاب از کاتالوگ",
        selected_pump_type=(request.form.get("model") or "").strip() or None,
        target_discharge_lps=_num(request.form.get("q")),
        selected_head_m=_num(request.form.get("head")),
        notes=(request.form.get("note") or "").strip() or None,
    )
    db.session.add(rec)
    db.session.flush()
    workflow.log_change(rec, "create", detail="از محاسبه‌گر کاتالوگ")
    db.session.commit()
    flash("انتخاب پمپ از محاسبه‌گر ثبت شد (پیش‌نویس).", "success")
    return redirect(url_for("pump_select.detail", record_id=rec.id))


@bp.route("/wells/<int:well_id>/pump-select/new", methods=["GET", "POST"])
@permission_required("pump_select", "create")
def create(well_id):
    well = db.get_or_404(Well, well_id)
    form = PumpSelectionForm()
    if form.validate_on_submit():
        rec = PumpSelection(well_id=well.id, created_by_id=current_user.id)
        _apply(form, rec)
        db.session.add(rec)
        db.session.flush()
        workflow.log_change(rec, "create")
        db.session.commit()
        flash("انتخاب پمپ ثبت شد (پیش‌نویس).", "success")
        return redirect(url_for("pump_select.detail", record_id=rec.id))
    return render_template("pump_select/form.html", form=form, well=well, title="ثبت انتخاب پمپ")


@bp.route("/pump-select/<int:record_id>")
@permission_required("pump_select", "view")
def detail(record_id):
    rec = db.get_or_404(PumpSelection, record_id)
    history = db.session.scalars(
        db.select(RecordHistory).filter_by(entity_type="pump_selections", entity_id=rec.id)
        .order_by(RecordHistory.timestamp.desc())
    ).all()
    return render_template("pump_select/detail.html", rec=rec, well=rec.well,
                           history=history, editable=workflow.is_editable(rec))


@bp.route("/pump-select/<int:record_id>/edit", methods=["GET", "POST"])
@permission_required("pump_select", "edit")
def edit(record_id):
    rec = db.get_or_404(PumpSelection, record_id)
    if not workflow.is_editable(rec):
        flash("این رکورد قفل است؛ ابتدا باید به پیش‌نویس بازگردانده شود.", "warning")
        return redirect(url_for("pump_select.detail", record_id=rec.id))
    form = PumpSelectionForm(obj=rec)
    if form.validate_on_submit():
        _apply(form, rec)
        rec.updated_by_id = current_user.id
        workflow.log_change(rec, "update")
        db.session.commit()
        flash("انتخاب پمپ به‌روزرسانی شد.", "success")
        return redirect(url_for("pump_select.detail", record_id=rec.id))
    return render_template("pump_select/form.html", form=form, well=rec.well, title="ویرایش انتخاب پمپ")


@bp.route("/pump-select/<int:record_id>/delete", methods=["POST"])
@permission_required("pump_select", "delete")
def delete(record_id):
    rec = db.get_or_404(PumpSelection, record_id)
    well_id = rec.well_id
    db.session.delete(rec)
    db.session.commit()
    flash("رکورد انتخاب پمپ حذف شد.", "info")
    return redirect(url_for("wells.detail", well_id=well_id))


def _transition(record_id, fn, perm_action, msg, **kw):
    rec = db.get_or_404(PumpSelection, record_id)
    if not current_user.has_permission("pump_select", perm_action):
        abort(403)
    try:
        fn(rec, **kw)
        db.session.commit()
        flash(msg, "success")
    except workflow.WorkflowError as e:
        db.session.rollback()
        flash(str(e), "danger")
    return redirect(url_for("pump_select.detail", record_id=record_id))


@bp.route("/pump-select/<int:record_id>/submit", methods=["POST"])
def submit(record_id):
    return _transition(record_id, workflow.submit, "edit", "برای تأیید ثبت شد.")


@bp.route("/pump-select/<int:record_id>/approve", methods=["POST"])
def approve(record_id):
    return _transition(record_id, workflow.approve, "approve", "تأیید شد.")


@bp.route("/pump-select/<int:record_id>/reject", methods=["POST"])
def reject(record_id):
    return _transition(record_id, workflow.reject, "approve", "برگشت داده شد.",
                       reason=request.form.get("reason", ""))


@bp.route("/pump-select/<int:record_id>/revert", methods=["POST"])
def revert(record_id):
    return _transition(record_id, workflow.revert_to_draft, "approve", "به پیش‌نویس بازگردانده شد.")



################################################################################
# FILE: blueprints\pump_test\__init__.py
################################################################################

from flask import Blueprint

bp = Blueprint("pump_test", __name__)

from app.blueprints.pump_test import routes  # noqa: E402,F401



################################################################################
# FILE: blueprints\pump_test\routes.py
################################################################################

from flask import render_template, redirect, url_for, flash, request, abort
from flask_login import current_user
from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, TextAreaField, SubmitField
from wtforms.validators import Optional

from app.extensions import db
from app.blueprints.pump_test import bp
from app.security import permission_required
from app.utils.forms import (
    JalaliDateField, PersianFloatField as FloatField, PersianIntegerField as IntegerField,
)
from app.utils.dates import to_english_digits
from app.models.well import Well
from app.models.pump_test import PumpTest, PumpTestStep
from app.models.audit import RecordHistory
from app.models.constants import PUMP_TEST_TYPES
from app import workflow

STEP_ROWS = 8
STEP_FIELDS = ["rpm", "discharge_lps", "observed_drawdown", "calc_drawdown",
               "grid_loss", "aquifer_loss", "efficiency"]


class PumpTestForm(FlaskForm):
    test_date = JalaliDateField("تاریخ آزمایش", validators=[Optional()])
    test_type = SelectField("نوع آزمایش", choices=[("", "—")] + PUMP_TEST_TYPES, validators=[Optional()])
    duration_h = FloatField("مدت شستشو/آزمایش (ساعت)", validators=[Optional()])
    contractor = StringField("پیمانکار", validators=[Optional()])
    consultant = StringField("مشاور", validators=[Optional()])
    employer = StringField("کارفرما", validators=[Optional()])
    contract_no = StringField("شماره قرارداد", validators=[Optional()])
    project_title = StringField("عنوان پروژه", validators=[Optional()])
    static_level = FloatField("سطح استاتیک", validators=[Optional()])
    max_dynamic_level = FloatField("حداکثر سطح دینامیک", validators=[Optional()])
    max_drawdown = FloatField("حداکثر افت چاه", validators=[Optional()])
    max_yield_lps = FloatField("حداکثر آبدهی (l/s)", validators=[Optional()])
    coeff_a = FloatField("ضریب a", validators=[Optional()])
    coeff_b = FloatField("ضریب b", validators=[Optional()])
    proposed_discharge_lps = FloatField("دبی مجاز پیشنهادی", validators=[Optional()])
    proposed_install_depth_m = FloatField("عمق نصب پیشنهادی", validators=[Optional()])
    resulting_drawdown_m = FloatField("میزان افت حاصله", validators=[Optional()])
    motor_type = StringField("نوع موتور", validators=[Optional()])
    motor_power_hp = FloatField("قدرت موتور (HP)", validators=[Optional()])
    gearbox_power_hp = FloatField("قدرت جعبه‌دنده (HP)", validators=[Optional()])
    gearbox_ratio = StringField("تبدیل جعبه‌دنده", validators=[Optional()])
    pump_type = StringField("نوع پمپ", validators=[Optional()])
    pump_stages = IntegerField("تعداد طبقه", validators=[Optional()])
    pump_diameter_in = FloatField("قطر پمپ (اینچ)", validators=[Optional()])
    max_rpm = FloatField("حداکثر دور موتور", validators=[Optional()])
    discharge_pipe_diameter_in = FloatField("قطر لوله آبده (اینچ)", validators=[Optional()])
    notes = TextAreaField("توضیحات", validators=[Optional()])
    submit = SubmitField("ذخیره")


HEADER_FIELDS = [
    "test_date", "test_type", "duration_h", "contractor", "consultant", "employer",
    "contract_no", "project_title", "static_level", "max_dynamic_level", "max_drawdown",
    "max_yield_lps", "coeff_a", "coeff_b", "proposed_discharge_lps",
    "proposed_install_depth_m", "resulting_drawdown_m", "motor_type", "motor_power_hp",
    "gearbox_power_hp", "gearbox_ratio", "pump_type", "pump_stages", "pump_diameter_in",
    "max_rpm", "discharge_pipe_diameter_in", "notes",
]


def _num(s):
    s = to_english_digits((s or "").strip())
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _apply_header(form, rec):
    for f in HEADER_FIELDS:
        setattr(rec, f, getattr(form, f).data)


def _apply_steps(rec):
    rec.steps.clear()
    for i in range(1, STEP_ROWS + 1):
        vals = {f: request.form.get(f"st-{i}-{f}", "").strip() for f in STEP_FIELDS}
        if not any(vals.values()):
            continue
        rec.steps.append(PumpTestStep(
            step_no=i,
            rpm=_num(vals["rpm"]),
            discharge_lps=_num(vals["discharge_lps"]),
            observed_drawdown=_num(vals["observed_drawdown"]),
            calc_drawdown=_num(vals["calc_drawdown"]),
            grid_loss=_num(vals["grid_loss"]),
            aquifer_loss=_num(vals["aquifer_loss"]),
            efficiency=_num(vals["efficiency"]),
        ))


@bp.route("/wells/<int:well_id>/pump-test/new", methods=["GET", "POST"])
@permission_required("pump_test", "create")
def create(well_id):
    well = db.get_or_404(Well, well_id)
    form = PumpTestForm()
    if form.validate_on_submit():
        rec = PumpTest(well_id=well.id, created_by_id=current_user.id)
        _apply_header(form, rec)
        db.session.add(rec)
        _apply_steps(rec)
        db.session.flush()
        workflow.log_change(rec, "create")
        db.session.commit()
        flash("آزمایش پمپاژ ثبت شد (پیش‌نویس).", "success")
        return redirect(url_for("pump_test.detail", record_id=rec.id))
    return render_template("pump_test/form.html", form=form, well=well,
                           title="ثبت آزمایش پمپاژ", steps=[], step_rows=STEP_ROWS)


@bp.route("/pump-test/<int:record_id>")
@permission_required("pump_test", "view")
def detail(record_id):
    rec = db.get_or_404(PumpTest, record_id)
    history = db.session.scalars(
        db.select(RecordHistory).filter_by(entity_type="pump_tests", entity_id=rec.id)
        .order_by(RecordHistory.timestamp.desc())
    ).all()
    return render_template("pump_test/detail.html", rec=rec, well=rec.well,
                           history=history, editable=workflow.is_editable(rec),
                           type_labels=dict(PUMP_TEST_TYPES))


@bp.route("/pump-test/<int:record_id>/edit", methods=["GET", "POST"])
@permission_required("pump_test", "edit")
def edit(record_id):
    rec = db.get_or_404(PumpTest, record_id)
    if not workflow.is_editable(rec):
        flash("این رکورد قفل است؛ ابتدا باید به پیش‌نویس بازگردانده شود.", "warning")
        return redirect(url_for("pump_test.detail", record_id=rec.id))
    form = PumpTestForm(obj=rec)
    if form.validate_on_submit():
        _apply_header(form, rec)
        _apply_steps(rec)
        rec.updated_by_id = current_user.id
        workflow.log_change(rec, "update")
        db.session.commit()
        flash("آزمایش پمپاژ به‌روزرسانی شد.", "success")
        return redirect(url_for("pump_test.detail", record_id=rec.id))
    return render_template("pump_test/form.html", form=form, well=rec.well,
                           title="ویرایش آزمایش پمپاژ", steps=rec.steps, step_rows=STEP_ROWS)


@bp.route("/pump-test/<int:record_id>/delete", methods=["POST"])
@permission_required("pump_test", "delete")
def delete(record_id):
    rec = db.get_or_404(PumpTest, record_id)
    well_id = rec.well_id
    db.session.delete(rec)
    db.session.commit()
    flash("آزمایش پمپاژ حذف شد.", "info")
    return redirect(url_for("wells.detail", well_id=well_id))


def _transition(record_id, fn, perm_action, msg, **kw):
    rec = db.get_or_404(PumpTest, record_id)
    if not current_user.has_permission("pump_test", perm_action):
        abort(403)
    try:
        fn(rec, **kw)
        db.session.commit()
        flash(msg, "success")
    except workflow.WorkflowError as e:
        db.session.rollback()
        flash(str(e), "danger")
    return redirect(url_for("pump_test.detail", record_id=record_id))


@bp.route("/pump-test/<int:record_id>/submit", methods=["POST"])
def submit(record_id):
    return _transition(record_id, workflow.submit, "edit", "برای تأیید ثبت شد.")


@bp.route("/pump-test/<int:record_id>/approve", methods=["POST"])
def approve(record_id):
    return _transition(record_id, workflow.approve, "approve", "تأیید شد.")


@bp.route("/pump-test/<int:record_id>/reject", methods=["POST"])
def reject(record_id):
    return _transition(record_id, workflow.reject, "approve", "برگشت داده شد.",
                       reason=request.form.get("reason", ""))


@bp.route("/pump-test/<int:record_id>/revert", methods=["POST"])
def revert(record_id):
    return _transition(record_id, workflow.revert_to_draft, "approve", "به پیش‌نویس بازگردانده شد.")



################################################################################
# FILE: blueprints\rehab\__init__.py
################################################################################

from flask import Blueprint

bp = Blueprint("rehab", __name__)

from app.blueprints.rehab import routes  # noqa: E402,F401



################################################################################
# FILE: blueprints\rehab\routes.py
################################################################################

from flask import render_template, redirect, url_for, flash, request, abort
from flask_login import current_user
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SubmitField
from wtforms.validators import Optional

from app.extensions import db
from app.blueprints.rehab import bp
from app.security import permission_required
from app.utils.forms import JalaliDateField, PersianFloatField as FloatField
from app.models.well import Well
from app.models.rehab import Rehabilitation
from app.models.audit import RecordHistory
from app.blueprints.install.routes import get_or_create_supplier
from app import workflow


class RehabForm(FlaskForm):
    stage = StringField("مرحله", validators=[Optional()])
    jyear = StringField("سال", validators=[Optional()])
    rehab_date = JalaliDateField("تاریخ بهسازی", validators=[Optional()])
    pumping_end_date = JalaliDateField("تاریخ اتمام پمپاژ", validators=[Optional()])
    rehab_contractor_name = StringField("پیمانکار بهسازی", validators=[Optional()])
    pumping_contractor_name = StringField("پیمانکار پمپاژ", validators=[Optional()])
    pump_type_before = StringField("تیپ پمپ پیش از بهسازی", validators=[Optional()])
    discharge_before_lps = FloatField("دبی قبل (l/s)", validators=[Optional()])
    pump_type_after = StringField("تیپ پمپ پس از بهسازی", validators=[Optional()])
    discharge_after_lps = FloatField("دبی بعد (l/s)", validators=[Optional()])
    reason = StringField("علت بهسازی", validators=[Optional()])
    method = StringField("روش", validators=[Optional()])
    observed_fault = TextAreaField("خرابی مشاهده‌شده", validators=[Optional()])
    notes = TextAreaField("توضیحات", validators=[Optional()])
    submit = SubmitField("ذخیره")


SIMPLE = ["stage", "jyear", "rehab_date", "pumping_end_date", "pump_type_before",
          "discharge_before_lps", "pump_type_after", "discharge_after_lps",
          "reason", "method", "observed_fault", "notes"]


def _apply(form, rec):
    for f in SIMPLE:
        setattr(rec, f, getattr(form, f).data)
    rc = get_or_create_supplier(form.rehab_contractor_name.data, "contractor")
    pc = get_or_create_supplier(form.pumping_contractor_name.data, "contractor")
    rec.rehab_contractor_id = rc.id if rc else None
    rec.pumping_contractor_id = pc.id if pc else None
    if rec.discharge_before_lps is not None and rec.discharge_after_lps is not None:
        rec.discharge_change_lps = round(rec.discharge_after_lps - rec.discharge_before_lps, 2)


@bp.route("/wells/<int:well_id>/rehab/new", methods=["GET", "POST"])
@permission_required("rehab", "create")
def create(well_id):
    well = db.get_or_404(Well, well_id)
    form = RehabForm()
    if form.validate_on_submit():
        rec = Rehabilitation(well_id=well.id, created_by_id=current_user.id)
        _apply(form, rec)
        db.session.add(rec)
        db.session.flush()
        workflow.log_change(rec, "create")
        db.session.commit()
        flash("بهسازی ثبت شد (پیش‌نویس).", "success")
        return redirect(url_for("rehab.detail", record_id=rec.id))
    return render_template("rehab/form.html", form=form, well=well, title="ثبت بهسازی")


@bp.route("/rehab/<int:record_id>")
@permission_required("rehab", "view")
def detail(record_id):
    rec = db.get_or_404(Rehabilitation, record_id)
    history = db.session.scalars(
        db.select(RecordHistory).filter_by(entity_type="rehabilitations", entity_id=rec.id)
        .order_by(RecordHistory.timestamp.desc())
    ).all()
    return render_template("rehab/detail.html", rec=rec, well=rec.well,
                           history=history, editable=workflow.is_editable(rec))


@bp.route("/rehab/<int:record_id>/edit", methods=["GET", "POST"])
@permission_required("rehab", "edit")
def edit(record_id):
    rec = db.get_or_404(Rehabilitation, record_id)
    if not workflow.is_editable(rec):
        flash("این رکورد قفل است؛ ابتدا باید به پیش‌نویس بازگردانده شود.", "warning")
        return redirect(url_for("rehab.detail", record_id=rec.id))
    form = RehabForm(obj=rec)
    if request.method == "GET":
        form.rehab_contractor_name.data = rec.rehab_contractor.name if rec.rehab_contractor else ""
        form.pumping_contractor_name.data = rec.pumping_contractor.name if rec.pumping_contractor else ""
    if form.validate_on_submit():
        _apply(form, rec)
        rec.updated_by_id = current_user.id
        workflow.log_change(rec, "update")
        db.session.commit()
        flash("بهسازی به‌روزرسانی شد.", "success")
        return redirect(url_for("rehab.detail", record_id=rec.id))
    return render_template("rehab/form.html", form=form, well=rec.well, title="ویرایش بهسازی")


@bp.route("/rehab/<int:record_id>/delete", methods=["POST"])
@permission_required("rehab", "delete")
def delete(record_id):
    rec = db.get_or_404(Rehabilitation, record_id)
    well_id = rec.well_id
    db.session.delete(rec)
    db.session.commit()
    flash("رکورد بهسازی حذف شد.", "info")
    return redirect(url_for("wells.detail", well_id=well_id))


def _transition(record_id, fn, perm_action, msg, **kw):
    rec = db.get_or_404(Rehabilitation, record_id)
    if not current_user.has_permission("rehab", perm_action):
        abort(403)
    try:
        fn(rec, **kw)
        db.session.commit()
        flash(msg, "success")
    except workflow.WorkflowError as e:
        db.session.rollback()
        flash(str(e), "danger")
    return redirect(url_for("rehab.detail", record_id=record_id))


@bp.route("/rehab/<int:record_id>/submit", methods=["POST"])
def submit(record_id):
    return _transition(record_id, workflow.submit, "edit", "برای تأیید ثبت شد.")


@bp.route("/rehab/<int:record_id>/approve", methods=["POST"])
def approve(record_id):
    return _transition(record_id, workflow.approve, "approve", "تأیید شد.")


@bp.route("/rehab/<int:record_id>/reject", methods=["POST"])
def reject(record_id):
    return _transition(record_id, workflow.reject, "approve", "برگشت داده شد.",
                       reason=request.form.get("reason", ""))


@bp.route("/rehab/<int:record_id>/revert", methods=["POST"])
def revert(record_id):
    return _transition(record_id, workflow.revert_to_draft, "approve", "به پیش‌نویس بازگردانده شد.")



################################################################################
# FILE: blueprints\relocation\__init__.py
################################################################################

from flask import Blueprint

bp = Blueprint("relocation", __name__)

from app.blueprints.relocation import routes  # noqa: E402,F401



################################################################################
# FILE: blueprints\relocation\routes.py
################################################################################

from flask import render_template, redirect, url_for, flash, request, abort
from flask_login import current_user
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, SubmitField
from wtforms.validators import Optional

from app.extensions import db
from app.blueprints.relocation import bp
from app.security import permission_required
from app.utils.forms import JalaliDateField, PersianFloatField as FloatField
from app.models.well import Well
from app.models.relocation import RelocationRecord
from app.models.audit import RecordHistory
from app.models.constants import RELOCATION_CANDIDACY, RELOCATION_TYPES
from app import workflow


class RelocationForm(FlaskForm):
    decision_date = JalaliDateField("تاریخ تصمیم", validators=[Optional()])
    candidacy = SelectField("وضعیت نامزدی", choices=[("", "—")] + RELOCATION_CANDIDACY,
                            validators=[Optional()])
    reloc_type = SelectField("نوع جابه‌جایی", choices=[("", "—")] + RELOCATION_TYPES,
                             validators=[Optional()])
    reason = StringField("علت جابه‌جایی", validators=[Optional()])
    location_note = StringField("موقعیت پیشنهادی", validators=[Optional()])
    letter_no = StringField("شماره نامه", validators=[Optional()])
    distance_m = FloatField("فاصله از چاه قبلی (m)", validators=[Optional()])
    new_well_id = SelectField("چاه جانشین", coerce=int, validators=[Optional()])
    notes = TextAreaField("توضیحات", validators=[Optional()])
    submit = SubmitField("ذخیره")

    def populate_wells(self, exclude_id):
        wells = db.session.scalars(db.select(Well).order_by(Well.name)).all()
        self.new_well_id.choices = [(0, "—")] + [
            (w.id, f"{w.name} ({w.display_pm})") for w in wells if w.id != exclude_id]


SIMPLE = ["decision_date", "candidacy", "reloc_type", "reason",
          "location_note", "letter_no", "distance_m", "notes"]


def _apply(form, rec):
    for f in SIMPLE:
        setattr(rec, f, getattr(form, f).data or None)
    rec.new_well_id = form.new_well_id.data or None


@bp.route("/relocation")
@permission_required("relocation", "view")
def list_relocations():
    cand_labels = dict(RELOCATION_CANDIDACY)
    type_labels = dict(RELOCATION_TYPES)
    rows = db.session.scalars(
        db.select(RelocationRecord).order_by(RelocationRecord.candidacy)).all()
    return render_template("relocation/list.html", rows=rows,
                           cand_labels=cand_labels, type_labels=type_labels)


@bp.route("/wells/<int:well_id>/relocation/new", methods=["GET", "POST"])
@permission_required("relocation", "create")
def create(well_id):
    well = db.get_or_404(Well, well_id)
    form = RelocationForm()
    form.populate_wells(well.id)
    if form.validate_on_submit():
        rec = RelocationRecord(well_id=well.id, created_by_id=current_user.id)
        _apply(form, rec)
        db.session.add(rec)
        db.session.flush()
        workflow.log_change(rec, "create")
        db.session.commit()
        flash("جابه‌جایی ثبت شد (پیش‌نویس).", "success")
        return redirect(url_for("relocation.detail", record_id=rec.id))
    return render_template("relocation/form.html", form=form, well=well, title="ثبت جابه‌جایی")


@bp.route("/relocation/<int:record_id>")
@permission_required("relocation", "view")
def detail(record_id):
    rec = db.get_or_404(RelocationRecord, record_id)
    history = db.session.scalars(
        db.select(RecordHistory).filter_by(entity_type="relocations", entity_id=rec.id)
        .order_by(RecordHistory.timestamp.desc())).all()
    return render_template("relocation/detail.html", rec=rec, well=rec.well,
                           history=history, editable=workflow.is_editable(rec),
                           cand_labels=dict(RELOCATION_CANDIDACY),
                           type_labels=dict(RELOCATION_TYPES))


@bp.route("/relocation/<int:record_id>/edit", methods=["GET", "POST"])
@permission_required("relocation", "edit")
def edit(record_id):
    rec = db.get_or_404(RelocationRecord, record_id)
    if not workflow.is_editable(rec):
        flash("این رکورد قفل است؛ ابتدا باید به پیش‌نویس بازگردانده شود.", "warning")
        return redirect(url_for("relocation.detail", record_id=rec.id))
    form = RelocationForm(obj=rec)
    form.populate_wells(rec.well_id)
    if form.validate_on_submit():
        _apply(form, rec)
        rec.updated_by_id = current_user.id
        workflow.log_change(rec, "update")
        db.session.commit()
        flash("جابه‌جایی به‌روزرسانی شد.", "success")
        return redirect(url_for("relocation.detail", record_id=rec.id))
    return render_template("relocation/form.html", form=form, well=rec.well, title="ویرایش جابه‌جایی")


@bp.route("/relocation/<int:record_id>/delete", methods=["POST"])
@permission_required("relocation", "delete")
def delete(record_id):
    rec = db.get_or_404(RelocationRecord, record_id)
    well_id = rec.well_id
    db.session.delete(rec)
    db.session.commit()
    flash("رکورد جابه‌جایی حذف شد.", "info")
    return redirect(url_for("wells.detail", well_id=well_id))


def _link_lineage(rec):
    """On approval: wire successor.parent_well = subject well, mark old relocated."""
    if rec.new_well_id and rec.new_well:
        rec.new_well.parent_well_id = rec.well_id
        rec.well.status = "relocated"


def _transition(record_id, fn, perm_action, msg, link=False, **kw):
    rec = db.get_or_404(RelocationRecord, record_id)
    if not current_user.has_permission("relocation", perm_action):
        abort(403)
    try:
        fn(rec, **kw)
        if link:
            _link_lineage(rec)
        db.session.commit()
        flash(msg, "success")
    except workflow.WorkflowError as e:
        db.session.rollback()
        flash(str(e), "danger")
    return redirect(url_for("relocation.detail", record_id=record_id))


@bp.route("/relocation/<int:record_id>/submit", methods=["POST"])
def submit(record_id):
    return _transition(record_id, workflow.submit, "edit", "برای تأیید ثبت شد.")


@bp.route("/relocation/<int:record_id>/approve", methods=["POST"])
def approve(record_id):
    return _transition(record_id, workflow.approve, "approve",
                       "تأیید شد و شجره‌نامه‌ی چاه به‌روزرسانی شد.", link=True)


@bp.route("/relocation/<int:record_id>/reject", methods=["POST"])
def reject(record_id):
    return _transition(record_id, workflow.reject, "approve", "برگشت داده شد.",
                       reason=request.form.get("reason", ""))


@bp.route("/relocation/<int:record_id>/revert", methods=["POST"])
def revert(record_id):
    return _transition(record_id, workflow.revert_to_draft, "approve", "به پیش‌نویس بازگردانده شد.")



################################################################################
# FILE: blueprints\reports\__init__.py
################################################################################

from flask import Blueprint

bp = Blueprint("reports", __name__, url_prefix="/reports")

from app.blueprints.reports import routes  # noqa: E402,F401



################################################################################
# FILE: blueprints\reports\routes.py
################################################################################

from collections import defaultdict

from flask import render_template, request, redirect, url_for, flash
from flask_login import current_user

from app.extensions import db
from app.blueprints.reports import bp
from app.security import permission_required
from app.models.pump_asset import PumpInstallation, Supplier
from app.models.prioritization import PrioritizationCriterion, DEFAULT_CRITERIA
from app.utils.dates import to_english_digits


def _aggregate(installs, key_attr):
    agg = defaultdict(lambda: {"completed": 0, "life_sum": 0.0, "running": 0, "burnt": 0})
    for i in installs:
        sid = getattr(i, key_attr)
        if not sid:
            continue
        a = agg[sid]
        if i.is_running:
            a["running"] += 1
        life = i.useful_life_months
        if life is not None:
            a["completed"] += 1
            a["life_sum"] += life
        if i.removal_reason and "سوخت" in i.removal_reason:
            a["burnt"] += 1
    return agg


def _rows(agg, names, min_completed):
    rows = []
    for sid, a in agg.items():
        if a["completed"] < min_completed:
            continue
        avg = round(a["life_sum"] / a["completed"], 1) if a["completed"] else None
        rows.append({
            "name": names.get(sid, "—"),
            "completed": a["completed"], "running": a["running"],
            "burnt": a["burnt"], "avg_life": avg,
        })
    rows.sort(key=lambda r: (r["avg_life"] is not None, r["avg_life"]), reverse=True)
    return rows


@bp.route("/suppliers")
@permission_required("reports", "view")
def suppliers():
    min_completed = int(request.args.get("min", 5))
    installs = db.session.scalars(db.select(PumpInstallation)).all()
    names = {s.id: s.name for s in db.session.scalars(db.select(Supplier)).all()}
    makers = _rows(_aggregate(installs, "manufacturer_id"), names, min_completed)
    contractors = _rows(_aggregate(installs, "contractor_id"), names, min_completed)
    return render_template("reports/suppliers.html",
                           makers=makers, contractors=contractors,
                           total=len(installs), min_completed=min_completed)


def _ensure_criteria():
    """Seed defaults and add any criteria missing by key (handles upgrades)."""
    existing = {c.key for c in db.session.scalars(db.select(PrioritizationCriterion)).all()}
    added = False
    for key, label, weight, direction in DEFAULT_CRITERIA:
        if key not in existing:
            db.session.add(PrioritizationCriterion(
                key=key, label=label, weight=weight, direction=direction))
            added = True
    if added:
        db.session.commit()


@bp.route("/prioritization", methods=["GET", "POST"])
@permission_required("reports", "view")
def prioritization():
    from app.services import prioritization as svc
    _ensure_criteria()

    if request.method == "POST":
        if not current_user.has_permission("admin", "edit"):
            flash("برای تغییر وزن‌ها مجوز مدیریت لازم است.", "warning")
            return redirect(url_for("reports.prioritization"))
        for c in db.session.scalars(db.select(PrioritizationCriterion)).all():
            w = to_english_digits(request.form.get(f"w_{c.id}", "")).strip()
            try:
                c.weight = float(w)
            except ValueError:
                pass
            c.is_active = request.form.get(f"a_{c.id}") == "on"
        db.session.commit()
        flash("وزن‌ها به‌روزرسانی شد.", "success")
        return redirect(url_for("reports.prioritization"))

    rows, criteria = svc.compute()
    all_criteria = db.session.scalars(
        db.select(PrioritizationCriterion).order_by(PrioritizationCriterion.weight.desc())
    ).all()
    return render_template("reports/prioritization.html",
                           rows=rows[:100], total=len(rows), criteria=all_criteria,
                           can_edit=current_user.has_permission("admin", "edit"))


@bp.route("/energy")
@permission_required("reports", "view")
def energy():
    from app.services import energy_stats
    return render_template("reports/energy.html", e=energy_stats.compute())


@bp.route("/alerts")
@permission_required("reports", "view")
def alerts():
    from app.services import alerts as alert_svc
    items = alert_svc.compute()
    return render_template("reports/alerts.html",
                           alerts=items, summary=alert_svc.summary(items),
                           categories=alert_svc.CATEGORIES)


@bp.route("/analytics")
@permission_required("reports", "view")
def analytics():
    from app.services.analytics import summary
    return render_template("reports/analytics.html", f=summary.fleet())


@bp.route("/zones")
@permission_required("reports", "view")
def zones():
    from app.services import zone_stats
    return render_template("reports/zones.html", z=zone_stats.compute())


@bp.route("/portfolio")
@permission_required("reports", "view")
def portfolio():
    from app.services import optimize, economics
    economics.ensure_params()
    default_budget = economics.get("rehab_cost", 2e9) * 20
    budget = request.args.get("budget", type=float)
    budget_rial = (budget * 1e9) if budget else default_budget
    return render_template("reports/portfolio.html",
                           p=optimize.portfolio(budget_rial),
                           budget_b=round(budget_rial / 1e9, 1),
                           unit_cost_b=round(economics.get("rehab_cost", 2e9) / 1e9, 2))


@bp.route("/dispatch")
@permission_required("reports", "view")
def dispatch():
    from app.services import optimize, zone_stats
    z = zone_stats.compute()
    group = request.args.get("group", "zone")
    key = request.args.get("key")
    demand = request.args.get("demand", type=float)
    result = None
    if key:
        attr = "zone" if group == "zone" else "destination_reservoir"
        result = optimize.field_dispatch(attr, key, demand or 0)
    return render_template("reports/dispatch.html", z=z, group=group,
                           key=key, demand=demand, result=result)



################################################################################
# FILE: blueprints\videometry\__init__.py
################################################################################

from flask import Blueprint

bp = Blueprint("videometry", __name__)

from app.blueprints.videometry import routes  # noqa: E402,F401



################################################################################
# FILE: blueprints\videometry\routes.py
################################################################################

from flask import render_template, redirect, url_for, flash, request, abort
from flask_login import current_user
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SubmitField
from wtforms.validators import Optional

from app.extensions import db
from app.blueprints.videometry import bp
from app.security import permission_required
from app.utils.forms import JalaliDateField, PersianFloatField as FloatField
from app.utils.dates import to_english_digits
from app.models.well import Well
from app.models.videometry import Videometry, VideometryFinding
from app.models.audit import RecordHistory
from app.models.constants import VIDEO_FINDING_TYPES, SEVERITY_LEVELS
from app.blueprints.install.routes import get_or_create_supplier
from app import workflow

FIND_ROWS = 8


class VideometryForm(FlaskForm):
    log_date = JalaliDateField("تاریخ چاه‌نگاری", validators=[Optional()])
    contractor_name = StringField("پیمانکار", validators=[Optional()])
    equipment = StringField("تجهیز/دوربین", validators=[Optional()])
    depth_from_m = FloatField("از عمق (m)", validators=[Optional()])
    depth_to_m = FloatField("تا عمق (m)", validators=[Optional()])
    final_depth_m = FloatField("عمق نهایی چاه (m)", validators=[Optional()])
    water_level_m = FloatField("سطح آب (m)", validators=[Optional()])
    video_file_ref = StringField("مسیر/نام فایل ویدئو", validators=[Optional()])
    summary = TextAreaField("خلاصه‌ی یافته‌ها", validators=[Optional()])
    submit = SubmitField("ذخیره")


HEADER = ["log_date", "equipment", "depth_from_m", "depth_to_m", "final_depth_m",
          "water_level_m", "video_file_ref", "summary"]


def _num(s):
    s = to_english_digits((s or "").strip())
    try:
        return float(s) if s else None
    except ValueError:
        return None


def _apply(form, rec):
    for f in HEADER:
        setattr(rec, f, getattr(form, f).data)
    con = get_or_create_supplier(form.contractor_name.data, "contractor")
    rec.contractor_id = con.id if con else None
    rec.findings.clear()
    for i in range(1, FIND_ROWS + 1):
        depth = request.form.get(f"f-{i}-depth_m", "").strip()
        ftype = request.form.get(f"f-{i}-finding_type", "").strip()
        sev = request.form.get(f"f-{i}-severity", "").strip()
        note = request.form.get(f"f-{i}-note", "").strip()
        if not (depth or ftype or note):
            continue
        rec.findings.append(VideometryFinding(
            depth_m=_num(depth), finding_type=ftype or None,
            severity=sev or None, note=note or None))


@bp.route("/wells/<int:well_id>/videometry/new", methods=["GET", "POST"])
@permission_required("videometry", "create")
def create(well_id):
    well = db.get_or_404(Well, well_id)
    form = VideometryForm()
    if form.validate_on_submit():
        rec = Videometry(well_id=well.id, created_by_id=current_user.id)
        _apply(form, rec)
        db.session.add(rec)
        db.session.flush()
        workflow.log_change(rec, "create")
        db.session.commit()
        flash("چاه‌نگاری ثبت شد (پیش‌نویس).", "success")
        return redirect(url_for("videometry.detail", record_id=rec.id))
    return render_template("videometry/form.html", form=form, well=well,
                           title="ثبت چاه‌نگاری", findings=[], find_rows=FIND_ROWS,
                           finding_types=VIDEO_FINDING_TYPES, severities=SEVERITY_LEVELS)


@bp.route("/videometry/<int:record_id>")
@permission_required("videometry", "view")
def detail(record_id):
    rec = db.get_or_404(Videometry, record_id)
    history = db.session.scalars(
        db.select(RecordHistory).filter_by(entity_type="videometry_logs", entity_id=rec.id)
        .order_by(RecordHistory.timestamp.desc())
    ).all()
    return render_template("videometry/detail.html", rec=rec, well=rec.well,
                           history=history, editable=workflow.is_editable(rec),
                           type_labels=dict(VIDEO_FINDING_TYPES),
                           sev_labels=dict(SEVERITY_LEVELS))


@bp.route("/videometry/<int:record_id>/edit", methods=["GET", "POST"])
@permission_required("videometry", "edit")
def edit(record_id):
    rec = db.get_or_404(Videometry, record_id)
    if not workflow.is_editable(rec):
        flash("این رکورد قفل است؛ ابتدا باید به پیش‌نویس بازگردانده شود.", "warning")
        return redirect(url_for("videometry.detail", record_id=rec.id))
    form = VideometryForm(obj=rec)
    if request.method == "GET":
        form.contractor_name.data = rec.contractor.name if rec.contractor else ""
    if form.validate_on_submit():
        _apply(form, rec)
        rec.updated_by_id = current_user.id
        workflow.log_change(rec, "update")
        db.session.commit()
        flash("چاه‌نگاری به‌روزرسانی شد.", "success")
        return redirect(url_for("videometry.detail", record_id=rec.id))
    return render_template("videometry/form.html", form=form, well=rec.well,
                           title="ویرایش چاه‌نگاری", findings=rec.findings, find_rows=FIND_ROWS,
                           finding_types=VIDEO_FINDING_TYPES, severities=SEVERITY_LEVELS)


@bp.route("/videometry/<int:record_id>/delete", methods=["POST"])
@permission_required("videometry", "delete")
def delete(record_id):
    rec = db.get_or_404(Videometry, record_id)
    well_id = rec.well_id
    db.session.delete(rec)
    db.session.commit()
    flash("رکورد چاه‌نگاری حذف شد.", "info")
    return redirect(url_for("wells.detail", well_id=well_id))


def _transition(record_id, fn, perm_action, msg, **kw):
    rec = db.get_or_404(Videometry, record_id)
    if not current_user.has_permission("videometry", perm_action):
        abort(403)
    try:
        fn(rec, **kw)
        db.session.commit()
        flash(msg, "success")
    except workflow.WorkflowError as e:
        db.session.rollback()
        flash(str(e), "danger")
    return redirect(url_for("videometry.detail", record_id=record_id))


@bp.route("/videometry/<int:record_id>/submit", methods=["POST"])
def submit(record_id):
    return _transition(record_id, workflow.submit, "edit", "برای تأیید ثبت شد.")


@bp.route("/videometry/<int:record_id>/approve", methods=["POST"])
def approve(record_id):
    return _transition(record_id, workflow.approve, "approve", "تأیید شد.")


@bp.route("/videometry/<int:record_id>/reject", methods=["POST"])
def reject(record_id):
    return _transition(record_id, workflow.reject, "approve", "برگشت داده شد.",
                       reason=request.form.get("reason", ""))


@bp.route("/videometry/<int:record_id>/revert", methods=["POST"])
def revert(record_id):
    return _transition(record_id, workflow.revert_to_draft, "approve", "به پیش‌نویس بازگردانده شد.")



################################################################################
# FILE: blueprints\water_level\__init__.py
################################################################################

from flask import Blueprint

bp = Blueprint("water_level", __name__)

from app.blueprints.water_level import routes  # noqa: E402,F401



################################################################################
# FILE: blueprints\water_level\routes.py
################################################################################

from flask import render_template, redirect, url_for, flash, request
from flask_login import current_user
from flask_wtf import FlaskForm
from wtforms import BooleanField, StringField, SubmitField
from wtforms.validators import Optional, DataRequired

from app.extensions import db
from app.blueprints.water_level import bp
from app.security import permission_required
from app.utils.forms import JalaliDateField, PersianFloatField as FloatField
from app.models.well import Well
from app.models.water_level import WaterLevelLog


class WaterLevelForm(FlaskForm):
    measure_date = JalaliDateField("تاریخ اندازه‌گیری", validators=[DataRequired()])
    static_level = FloatField("تراز آب (عمق تا آب، m)", validators=[DataRequired()])
    is_pumping = BooleanField("در حال پمپاژ")
    notes = StringField("توضیحات", validators=[Optional()])
    submit = SubmitField("ذخیره")


@bp.route("/wells/<int:well_id>/water-level/new", methods=["GET", "POST"])
@permission_required("water_level", "create")
def create(well_id):
    well = db.get_or_404(Well, well_id)
    form = WaterLevelForm()
    if form.validate_on_submit():
        rec = WaterLevelLog(well_id=well.id, method="manual",
                            created_by_id=current_user.id)
        form.populate_obj(rec)
        db.session.add(rec)
        db.session.commit()
        flash("تراز آب ثبت شد.", "success")
        return redirect(url_for("wells.detail", well_id=well.id) + "#sec-waterlevel")
    return render_template("water_level/form.html", form=form, well=well, title="ثبت تراز آب")


@bp.route("/water-level/<int:record_id>/edit", methods=["GET", "POST"])
@permission_required("water_level", "edit")
def edit(record_id):
    rec = db.get_or_404(WaterLevelLog, record_id)
    form = WaterLevelForm(obj=rec)
    if form.validate_on_submit():
        form.populate_obj(rec)
        rec.updated_by_id = current_user.id
        db.session.commit()
        flash("تراز آب به‌روزرسانی شد.", "success")
        return redirect(url_for("wells.detail", well_id=rec.well_id) + "#sec-waterlevel")
    return render_template("water_level/form.html", form=form, well=rec.well, title="ویرایش تراز آب")


@bp.route("/water-level/<int:record_id>/delete", methods=["POST"])
@permission_required("water_level", "delete")
def delete(record_id):
    rec = db.get_or_404(WaterLevelLog, record_id)
    well_id = rec.well_id
    db.session.delete(rec)
    db.session.commit()
    flash("رکورد تراز آب حذف شد.", "info")
    return redirect(url_for("wells.detail", well_id=well_id) + "#sec-waterlevel")



################################################################################
# FILE: blueprints\wells\__init__.py
################################################################################

from flask import Blueprint

bp = Blueprint("wells", __name__, url_prefix="/wells")

from app.blueprints.wells import routes  # noqa: E402,F401



################################################################################
# FILE: blueprints\wells\routes.py
################################################################################

from flask import render_template, redirect, url_for, flash, request
from flask_login import current_user
from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, TextAreaField, SubmitField
from wtforms.validators import DataRequired, Optional

from app.extensions import db
from app.blueprints.wells import bp
from app.utils.forms import PersianFloatField as FloatField
from app.security import permission_required
from app.models.well import Well
from app.models.org import OrgUnit
from app.models.constants import (
    WELL_KINDS,
    WELL_STATUSES,
    LOCATION_STATUSES,
    ORG_UNIT_TYPES,
    WELL_CONSTRUCTION_TYPES,
)


class WellForm(FlaskForm):
    pm_code = StringField("کد PM", validators=[DataRequired()])
    name = StringField("نام چاه", validators=[DataRequired()])
    well_kind = SelectField("نوع چاه", choices=WELL_KINDS)
    office_id = SelectField("اداره", coerce=int, validators=[Optional()])
    center_id = SelectField("مرکز آبرسانی", coerce=int, validators=[Optional()])
    zone = StringField("پهنه", validators=[Optional()])
    sub_zone = StringField("زیرپهنه", validators=[Optional()])
    utm_x = FloatField("UTM X", validators=[Optional()])
    utm_y = FloatField("UTM Y", validators=[Optional()])
    utm_zone = StringField("Zone", validators=[Optional()])
    latitude = FloatField("عرض جغرافیایی", validators=[Optional()])
    longitude = FloatField("طول جغرافیایی", validators=[Optional()])
    ground_elevation = FloatField("ارتفاع زمین", validators=[Optional()])
    drill_year = StringField("سال حفر", validators=[Optional()])
    location_status = SelectField(
        "وضعیت تعیین محل", choices=[("", "—")] + LOCATION_STATUSES, validators=[Optional()]
    )
    status = SelectField("وضعیت چاه", choices=WELL_STATUSES)
    parent_well_id = SelectField("چاه قبلی (در جابه‌جایی)", coerce=int, validators=[Optional()])
    notes = TextAreaField("توضیحات", validators=[Optional()])
    submit = SubmitField("ذخیره")

    def populate_choices(self, exclude_well_id=None):
        offices = db.session.scalars(
            db.select(OrgUnit).filter_by(unit_type="office").order_by(OrgUnit.name)
        ).all()
        centers = db.session.scalars(
            db.select(OrgUnit)
            .where(OrgUnit.unit_type.in_(["center", "rural_region"]))
            .order_by(OrgUnit.name)
        ).all()
        self.office_id.choices = [(0, "—")] + [(o.id, o.name) for o in offices]
        self.center_id.choices = [(0, "—")] + [(c.id, c.name) for c in centers]
        wells = db.session.scalars(db.select(Well).order_by(Well.pm_code)).all()
        self.parent_well_id.choices = [(0, "—")] + [
            (w.id, f"{w.pm_code} — {w.name}")
            for w in wells
            if w.id != exclude_well_id
        ]


@bp.route("/")
@permission_required("wells", "view")
def list_wells():
    q = (request.args.get("q") or "").strip()
    query = db.select(Well).order_by(Well.pm_code)
    if q:
        like = f"%{q}%"
        query = db.select(Well).where(
            db.or_(Well.pm_code.ilike(like), Well.name.ilike(like))
        ).order_by(Well.pm_code)
    wells = db.session.scalars(query).all()
    return render_template(
        "wells/list.html",
        wells=wells,
        q=q,
        kind_labels=dict(WELL_KINDS),
        status_labels=dict(WELL_STATUSES),
    )


@bp.route("/<int:well_id>")
@permission_required("wells", "view")
def detail(well_id):
    well = db.get_or_404(Well, well_id)
    from app.services import timeline
    from app.models.baseline import WellBaseline
    from app.models.quality import WaterQuality
    from app.models.production import MonthlyProduction
    baseline = db.session.scalar(
        db.select(WellBaseline).filter_by(well_id=well.id, is_current=True))
    quality = db.session.scalars(
        db.select(WaterQuality).filter_by(well_id=well.id)
        .order_by(WaterQuality.sample_date.desc())).all()

    # Monthly operational time-series (روند تولید) for the trend chart.
    prod_rows = db.session.scalars(
        db.select(MonthlyProduction).filter_by(well_id=well.id)
        .order_by(MonthlyProduction.jyear, MonthlyProduction.jmonth)).all()
    production = {
        "labels": [f"{r.jyear}/{r.jmonth:02d}" for r in prod_rows],
        "discharge": [r.avg_discharge_lps for r in prod_rows],
        "volume": [r.production_m3 for r in prod_rows],
        "hours": [r.run_hours for r in prod_rows],
    }
    energy = next((r for r in prod_rows if r.energy_kwh is not None), None)

    events = timeline.build(well)
    # Position lifecycle events on the production/discharge chart (nearest month).
    chart_events = []
    if prod_rows:
        import jdatetime
        from app.utils.dates import format_jalali
        periods = [r.jyear * 12 + (r.jmonth - 1) for r in prod_rows]
        colors = {
            "drilling": "#c9780b", "pump_test": "#7c4dff", "pump_select": "#11a394",
            "install": "#2f6bff", "operation": "#18a558", "rehab": "#e0463e",
            "videometry": "#0e8fa8", "relocation": "#d6457f", "maintenance": "#6a7180",
        }
        for ev in events:
            d = ev.get("date")
            if not d:
                continue
            jd = jdatetime.date.fromgregorian(date=d)
            p = jd.year * 12 + (jd.month - 1)
            idx = min(range(len(periods)), key=lambda i: abs(periods[i] - p))
            chart_events.append({
                "index": idx,
                "type_label": ev["type_label"],
                "module": ev["module"],
                "color": colors.get(ev["module"], "#6a7180"),
                "icon": ev["icon"],
                "date": format_jalali(d),
                "title": ev.get("title") or "",
                "status": ev.get("status") or "",
                "url": ev["url"],
            })

    # Pump-test step curves (Q vs drawdown / efficiency) — well-performance diagnostic.
    from app.models.pump_test import PumpTest
    from app.models.flow import FlowTest
    from app.utils.dates import format_jalali as _fj
    pump_tests = []
    for t in db.session.scalars(
            db.select(PumpTest).filter_by(well_id=well.id).order_by(PumpTest.test_date)).all():
        pts = sorted(
            [{"q": s.discharge_lps, "dd": s.observed_drawdown,
              "eff": (s.efficiency * 100 if s.efficiency and s.efficiency <= 1 else s.efficiency)}
             for s in t.steps if s.discharge_lps is not None],
            key=lambda x: x["q"])
        if pts:
            pump_tests.append({"date": _fj(t.test_date), "points": pts})

    # Flow-metering operating points (Q vs dynamic level), across tests over time.
    flow_tests = []
    for ft in db.session.scalars(
            db.select(FlowTest).filter_by(well_id=well.id).order_by(FlowTest.test_date)).all():
        pts = [{"q": p.discharge_lps, "dyn": p.dynamic_level_m, "head": p.head_m,
                "eff": (p.efficiency * 100 if p.efficiency and p.efficiency <= 1 else p.efficiency)}
               for p in ft.points if p.discharge_lps is not None]
        if pts:
            flow_tests.append({"date": _fj(ft.test_date), "points": pts})

    # Pump characteristic curve (catalog) + design point overlay for the Q-H chart.
    from app.models.pump_select import PumpSelection
    from app.models.pump_catalog import PumpModel
    from app.models.pump_asset import PumpInstallation
    sels = db.session.scalars(
        db.select(PumpSelection).filter_by(well_id=well.id)
        .order_by(PumpSelection.form_delivery_date)).all()
    dp = next((s for s in reversed(sels)
               if s.target_discharge_lps and s.selected_head_m), None)
    design_point = ({"q": dp.target_discharge_lps, "h": dp.selected_head_m,
                     "pump": dp.selected_pump_type} if dp else None)
    model_name = (dp.selected_pump_type if dp else None) or next(
        (s.selected_pump_type for s in reversed(sels) if s.selected_pump_type), None)
    if not model_name:
        inst = db.session.scalar(
            db.select(PumpInstallation).filter_by(well_id=well.id)
            .order_by(PumpInstallation.install_date.desc()))
        model_name = inst.pump_type if inst else None
    pump_curve = None
    if model_name:
        pm = db.session.scalar(db.select(PumpModel).filter_by(model=model_name))
        if pm and pm.points:
            pts = [{"q": p.flow_lps, "h": p.head_m, "eff": p.efficiency_pct}
                   for p in pm.points if p.flow_lps is not None and p.head_m is not None]
            if pts:
                bep = next((p for p in pm.points if p.is_bep), None)
                bs = next((p for p in pm.points if p.is_beb_start), None)
                be = next((p for p in pm.points if p.is_beb_end), None)
                pump_curve = {
                    "model": pm.model,
                    "points": pts,
                    "bep": ({"q": bep.flow_lps, "h": bep.head_m, "eff": bep.efficiency_pct}
                            if bep and bep.flow_lps is not None else None),
                    "beb": ({"start": bs.flow_lps, "end": be.flow_lps}
                            if bs and be and bs.flow_lps is not None and be.flow_lps is not None else None),
                }

    has_qh = (any(p["head"] is not None for ft in flow_tests for p in ft["points"])
              or design_point is not None or pump_curve is not None)

    from app.blueprints.documents.routes import attachments_for
    attachments = attachments_for("well", well.id)

    from app.services.analytics import summary as analytics_summary
    analytics = analytics_summary.well(well.id)

    # 6.2 pump-replacement ROI (uses energy saving + economic params)
    pump_roi = None
    eo = analytics.get("energy")
    if eo and eo.get("annual_rial_saving") and eo.get("motor_kw"):
        from app.services import economics
        economics.ensure_params()
        invest = (economics.get("pump_price_per_kw") * eo["motor_kw"]
                  + economics.get("pump_install_cost"))
        saving = eo["annual_rial_saving"]
        npv = economics.npv(saving, economics.get("analysis_years"),
                            economics.get("discount_rate")) - invest
        pump_roi = {
            "investment": invest, "annual_saving": saving,
            "payback": economics.payback_years(invest, saving),
            "npv": round(npv), "worth_it": npv > 0,
            "years": int(economics.get("analysis_years")),
        }

    # Groundwater level monitoring (piezometry) — static-level time series.
    from app.models.water_level import WaterLevelLog
    wl_rows = db.session.scalars(
        db.select(WaterLevelLog).filter_by(well_id=well.id)
        .order_by(WaterLevelLog.measure_date)).all()
    water_levels = [
        {"id": w.id, "date": _fj(w.measure_date), "level": w.static_level,
         "method": w.method, "pumping": w.is_pumping}
        for w in wl_rows if w.measure_date and w.static_level is not None]

    # Vertical cross-section (5.6): depths + water levels for the schematic.
    from app.models.drilling import Drilling
    from app.models.pump_asset import PumpInstallation
    from app.models.flow import FlowTestPoint
    tech = well.technical
    dr = db.session.scalar(db.select(Drilling).filter_by(well_id=well.id)
                           .order_by(Drilling.end_date.desc()))
    inst = db.session.scalar(db.select(PumpInstallation).filter_by(well_id=well.id)
                             .order_by(PumpInstallation.install_date.desc()))
    drill_depth = ((dr.well_depth_actual or dr.well_depth_permit) if dr else None) \
        or (tech.drill_depth_m if tech else None) or (inst.well_depth_m if inst else None)
    install_depth = (inst.install_depth_m if inst else None) \
        or (tech.install_depth_m if tech else None)
    static = next((w.static_level for w in reversed(wl_rows)
                   if not w.is_pumping and w.static_level is not None), None)
    dyn = db.session.scalar(
        db.select(FlowTestPoint.dynamic_level_m).join(FlowTest)
        .where(FlowTest.well_id == well.id, FlowTestPoint.dynamic_level_m.isnot(None))
        .order_by(FlowTest.test_date.desc()))
    xsection = None
    if drill_depth or install_depth:
        xsection = {
            "ground_elev": well.ground_elevation,
            "drill_depth": drill_depth, "install_depth": install_depth,
            "static": static, "dynamic": dyn,
            "casing": tech.casing_material if tech else None,
            "construction": well.construction_type,
            "max_depth": max(d for d in [drill_depth, install_depth, static, dyn, 1] if d),
        }

    return render_template(
        "wells/detail.html",
        well=well,
        timeline=events,
        chart_events=chart_events,
        baseline=baseline,
        quality=quality,
        production=production,
        energy=energy,
        pump_tests=pump_tests,
        flow_tests=flow_tests,
        has_qh=has_qh,
        pump_curve=pump_curve,
        design_point=design_point,
        water_levels=water_levels,
        attachments=attachments,
        analytics=analytics,
        pump_roi=pump_roi,
        xsection=xsection,
        kind_labels=dict(WELL_KINDS),
        status_labels=dict(WELL_STATUSES),
        loc_labels=dict(LOCATION_STATUSES),
        constr_labels=dict(WELL_CONSTRUCTION_TYPES),
    )


def _apply_form(form, well):
    well.pm_code = form.pm_code.data.strip()
    well.name = form.name.data.strip()
    well.well_kind = form.well_kind.data
    well.office_id = form.office_id.data or None
    well.center_id = well.office_id   # اداره و مرکز یکی هستند
    well.zone = (form.zone.data or "").strip() or None
    well.sub_zone = (form.sub_zone.data or "").strip() or None
    well.utm_x = form.utm_x.data
    well.utm_y = form.utm_y.data
    well.utm_zone = (form.utm_zone.data or "").strip() or None
    well.latitude = form.latitude.data
    well.longitude = form.longitude.data
    well.ground_elevation = form.ground_elevation.data
    well.drill_year = (form.drill_year.data or "").strip() or None
    well.location_status = form.location_status.data or None
    well.status = form.status.data
    well.parent_well_id = form.parent_well_id.data or None
    well.notes = (form.notes.data or "").strip() or None


@bp.route("/new", methods=["GET", "POST"])
@permission_required("wells", "create")
def create_well():
    form = WellForm()
    form.populate_choices()
    if form.validate_on_submit():
        existing = db.session.scalar(
            db.select(Well).filter_by(pm_code=form.pm_code.data.strip())
        )
        if existing:
            flash("چاهی با این کد PM از قبل وجود دارد.", "danger")
        else:
            well = Well()
            _apply_form(form, well)
            well.created_by_id = current_user.id
            db.session.add(well)
            db.session.commit()
            flash("چاه ثبت شد.", "success")
            return redirect(url_for("wells.detail", well_id=well.id))
    return render_template("wells/form.html", form=form, title="ثبت چاه جدید")


@bp.route("/<int:well_id>/edit", methods=["GET", "POST"])
@permission_required("wells", "edit")
def edit_well(well_id):
    well = db.get_or_404(Well, well_id)
    form = WellForm(obj=well)
    form.populate_choices(exclude_well_id=well.id)
    if form.validate_on_submit():
        clash = db.session.scalar(
            db.select(Well).where(
                Well.pm_code == form.pm_code.data.strip(), Well.id != well.id
            )
        )
        if clash:
            flash("چاه دیگری با این کد PM وجود دارد.", "danger")
        else:
            _apply_form(form, well)
            well.updated_by_id = current_user.id
            db.session.commit()
            flash("چاه به‌روزرسانی شد.", "success")
            return redirect(url_for("wells.detail", well_id=well.id))
    return render_template("wells/form.html", form=form, title="ویرایش چاه")


@bp.route("/<int:well_id>/delete", methods=["POST"])
@permission_required("wells", "delete")
def delete_well(well_id):
    well = db.get_or_404(Well, well_id)
    db.session.delete(well)
    db.session.commit()
    flash("چاه حذف شد.", "info")
    return redirect(url_for("wells.list_wells"))



################################################################################
# FILE: 017b9513547c_add_wells_construction_type.py
################################################################################

"""add wells.construction_type

Revision ID: 017b9513547c
Revises: 196bc38e459e
Create Date: 2026-06-20 16:20:43.871297

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '017b9513547c'
down_revision = '196bc38e459e'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('wells', schema=None) as batch_op:
        batch_op.add_column(sa.Column('construction_type', sa.String(length=20), nullable=True))

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('wells', schema=None) as batch_op:
        batch_op.drop_column('construction_type')

    # ### end Alembic commands ###



################################################################################
# FILE: 024d2a63ff2c_phase_pump_selections.py
################################################################################

"""phase: pump_selections

Revision ID: 024d2a63ff2c
Revises: 0f9bf2ce16d9
Create Date: 2026-06-21 06:45:26.783518

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '024d2a63ff2c'
down_revision = '0f9bf2ce16d9'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('pump_selections',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('well_id', sa.Integer(), nullable=False),
    sa.Column('action_needed', sa.String(length=60), nullable=True),
    sa.Column('jyear', sa.String(length=8), nullable=True),
    sa.Column('jmonth', sa.String(length=16), nullable=True),
    sa.Column('status_done', sa.String(length=40), nullable=True),
    sa.Column('prev_pump_type', sa.String(length=60), nullable=True),
    sa.Column('prev_motor_type', sa.String(length=60), nullable=True),
    sa.Column('prev_discharge_lps', sa.Float(), nullable=True),
    sa.Column('selected_pump_type', sa.String(length=60), nullable=True),
    sa.Column('selected_motor_type', sa.String(length=60), nullable=True),
    sa.Column('target_discharge_lps', sa.Float(), nullable=True),
    sa.Column('discharge_increase_lps', sa.Float(), nullable=True),
    sa.Column('selected_head_m', sa.Float(), nullable=True),
    sa.Column('form_delivery_date', sa.Date(), nullable=True),
    sa.Column('pull_date', sa.Date(), nullable=True),
    sa.Column('videometry_date', sa.Date(), nullable=True),
    sa.Column('install_date', sa.Date(), nullable=True),
    sa.Column('verify_flowtest_date', sa.Date(), nullable=True),
    sa.Column('verify_discharge_lps', sa.Float(), nullable=True),
    sa.Column('verify_head_m', sa.Float(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('source', sa.String(length=40), nullable=True),
    sa.Column('created_by_id', sa.Integer(), nullable=True),
    sa.Column('updated_by_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('submitted_at', sa.DateTime(), nullable=True),
    sa.Column('approved_at', sa.DateTime(), nullable=True),
    sa.Column('reject_reason', sa.Text(), nullable=True),
    sa.Column('submitted_by_id', sa.Integer(), nullable=True),
    sa.Column('approved_by_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['approved_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['submitted_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['well_id'], ['wells.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('pump_selections', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_pump_selections_form_delivery_date'), ['form_delivery_date'], unique=False)
        batch_op.create_index(batch_op.f('ix_pump_selections_source'), ['source'], unique=False)
        batch_op.create_index(batch_op.f('ix_pump_selections_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_pump_selections_well_id'), ['well_id'], unique=False)

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('pump_selections', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_pump_selections_well_id'))
        batch_op.drop_index(batch_op.f('ix_pump_selections_status'))
        batch_op.drop_index(batch_op.f('ix_pump_selections_source'))
        batch_op.drop_index(batch_op.f('ix_pump_selections_form_delivery_date'))

    op.drop_table('pump_selections')
    # ### end Alembic commands ###



################################################################################
# FILE: 0f9bf2ce16d9_prioritization_criteria.py
################################################################################

"""prioritization criteria

Revision ID: 0f9bf2ce16d9
Revises: 2f94be0cc5fd
Create Date: 2026-06-20 22:51:12.418402

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0f9bf2ce16d9'
down_revision = '2f94be0cc5fd'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('prioritization_criteria',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('key', sa.String(length=40), nullable=False),
    sa.Column('label', sa.String(length=120), nullable=False),
    sa.Column('weight', sa.Float(), nullable=False),
    sa.Column('direction', sa.String(length=12), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('key')
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('prioritization_criteria')
    # ### end Alembic commands ###



################################################################################
# FILE: 0f9d5cc6e8de_pump_catalog_models_curve_points.py
################################################################################

"""pump catalog: models + curve points

Revision ID: 0f9d5cc6e8de
Revises: 024d2a63ff2c
Create Date: 2026-06-21 14:57:38.842590

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0f9d5cc6e8de'
down_revision = '024d2a63ff2c'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('pump_models',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('model', sa.String(length=40), nullable=False),
    sa.Column('ptype', sa.String(length=20), nullable=True),
    sa.Column('title_electro', sa.String(length=60), nullable=True),
    sa.Column('stages', sa.Integer(), nullable=True),
    sa.Column('motor_power_kw', sa.Float(), nullable=True),
    sa.Column('npsh', sa.Float(), nullable=True),
    sa.Column('nominal_current', sa.Float(), nullable=True),
    sa.Column('length_mm', sa.Integer(), nullable=True),
    sa.Column('weight_kg', sa.Integer(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('pump_models', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_pump_models_model'), ['model'], unique=True)
        batch_op.create_index(batch_op.f('ix_pump_models_ptype'), ['ptype'], unique=False)

    op.create_table('pump_curve_points',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('model_id', sa.Integer(), nullable=False),
    sa.Column('flow_m3h', sa.Float(), nullable=True),
    sa.Column('flow_lps', sa.Float(), nullable=True),
    sa.Column('head_m', sa.Float(), nullable=True),
    sa.Column('efficiency_pct', sa.Float(), nullable=True),
    sa.Column('is_bep', sa.Boolean(), nullable=True),
    sa.Column('is_beb_start', sa.Boolean(), nullable=True),
    sa.Column('is_beb_end', sa.Boolean(), nullable=True),
    sa.ForeignKeyConstraint(['model_id'], ['pump_models.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('pump_curve_points', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_pump_curve_points_model_id'), ['model_id'], unique=False)

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('pump_curve_points', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_pump_curve_points_model_id'))

    op.drop_table('pump_curve_points')
    with op.batch_alter_table('pump_models', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_pump_models_ptype'))
        batch_op.drop_index(batch_op.f('ix_pump_models_model'))

    op.drop_table('pump_models')
    # ### end Alembic commands ###



################################################################################
# FILE: 16d3cb3c242c_water_level_logs_table.py
################################################################################

"""water_level_logs table

Revision ID: 16d3cb3c242c
Revises: f3469902de33
Create Date: 2026-06-22 17:13:42.456550

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '16d3cb3c242c'
down_revision = 'f3469902de33'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('water_level_logs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('well_id', sa.Integer(), nullable=False),
    sa.Column('measure_date', sa.Date(), nullable=True),
    sa.Column('static_level', sa.Float(), nullable=True),
    sa.Column('is_pumping', sa.Boolean(), nullable=True),
    sa.Column('method', sa.String(length=20), nullable=True),
    sa.Column('notes', sa.String(length=200), nullable=True),
    sa.Column('source', sa.String(length=40), nullable=True),
    sa.Column('created_by_id', sa.Integer(), nullable=True),
    sa.Column('updated_by_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['well_id'], ['wells.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('well_id', 'measure_date', 'source', name='uq_waterlevel_well_date_source')
    )
    with op.batch_alter_table('water_level_logs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_water_level_logs_measure_date'), ['measure_date'], unique=False)
        batch_op.create_index(batch_op.f('ix_water_level_logs_source'), ['source'], unique=False)
        batch_op.create_index(batch_op.f('ix_water_level_logs_well_id'), ['well_id'], unique=False)

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('water_level_logs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_water_level_logs_well_id'))
        batch_op.drop_index(batch_op.f('ix_water_level_logs_source'))
        batch_op.drop_index(batch_op.f('ix_water_level_logs_measure_date'))

    op.drop_table('water_level_logs')
    # ### end Alembic commands ###



################################################################################
# FILE: 196bc38e459e_phase1_drilling_event_record_history_.py
################################################################################

"""phase1: drilling event, record_history, workflow fields

Revision ID: 196bc38e459e
Revises: a333b59b1a36
Create Date: 2026-06-20 16:04:19.452633

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '196bc38e459e'
down_revision = 'a333b59b1a36'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('record_history',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('entity_type', sa.String(length=40), nullable=False),
    sa.Column('entity_id', sa.Integer(), nullable=False),
    sa.Column('action', sa.String(length=20), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('timestamp', sa.DateTime(), nullable=False),
    sa.Column('detail', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('record_history', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_record_history_entity_id'), ['entity_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_record_history_entity_type'), ['entity_type'], unique=False)

    op.create_table('drilling',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('well_id', sa.Integer(), nullable=False),
    sa.Column('request_type', sa.String(length=20), nullable=True),
    sa.Column('drill_method', sa.String(length=40), nullable=True),
    sa.Column('executor', sa.String(length=120), nullable=True),
    sa.Column('contractor', sa.String(length=120), nullable=True),
    sa.Column('supervisor', sa.String(length=120), nullable=True),
    sa.Column('credit_source', sa.String(length=120), nullable=True),
    sa.Column('contract_no', sa.String(length=40), nullable=True),
    sa.Column('contract_date', sa.Date(), nullable=True),
    sa.Column('start_date', sa.Date(), nullable=True),
    sa.Column('end_date', sa.Date(), nullable=True),
    sa.Column('well_depth_permit', sa.Float(), nullable=True),
    sa.Column('well_depth_actual', sa.Float(), nullable=True),
    sa.Column('casing_diameter_in', sa.Float(), nullable=True),
    sa.Column('casing_total_len', sa.Float(), nullable=True),
    sa.Column('steel_blank_len', sa.Float(), nullable=True),
    sa.Column('steel_screen_len', sa.Float(), nullable=True),
    sa.Column('upvc_blank_len', sa.Float(), nullable=True),
    sa.Column('upvc_screen_len', sa.Float(), nullable=True),
    sa.Column('transition_len', sa.Float(), nullable=True),
    sa.Column('static_level', sa.Float(), nullable=True),
    sa.Column('max_yield_lps', sa.Float(), nullable=True),
    sa.Column('proposed_discharge_lps', sa.Float(), nullable=True),
    sa.Column('dynamic_at_proposed', sa.Float(), nullable=True),
    sa.Column('drawdown', sa.Float(), nullable=True),
    sa.Column('coeff_a', sa.Float(), nullable=True),
    sa.Column('coeff_b', sa.Float(), nullable=True),
    sa.Column('videometry_done', sa.Boolean(), nullable=True),
    sa.Column('address', sa.String(length=255), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_by_id', sa.Integer(), nullable=True),
    sa.Column('updated_by_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('submitted_at', sa.DateTime(), nullable=True),
    sa.Column('approved_at', sa.DateTime(), nullable=True),
    sa.Column('reject_reason', sa.Text(), nullable=True),
    sa.Column('submitted_by_id', sa.Integer(), nullable=True),
    sa.Column('approved_by_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['approved_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['submitted_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['well_id'], ['wells.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('drilling', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_drilling_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_drilling_well_id'), ['well_id'], unique=False)

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('drilling', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_drilling_well_id'))
        batch_op.drop_index(batch_op.f('ix_drilling_status'))

    op.drop_table('drilling')
    with op.batch_alter_table('record_history', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_record_history_entity_type'))
        batch_op.drop_index(batch_op.f('ix_record_history_entity_id'))

    op.drop_table('record_history')
    # ### end Alembic commands ###



################################################################################
# FILE: 1e92ce74455a_part_entry_date.py
################################################################################

"""part entry date

Revision ID: 1e92ce74455a
Revises: c60a88fed047
Create Date: 2026-07-05 18:39:12.973388

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1e92ce74455a'
down_revision = 'c60a88fed047'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('mechanic_parts', schema=None) as batch_op:
        batch_op.add_column(sa.Column('entry_date', sa.Date(), nullable=True))

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('mechanic_parts', schema=None) as batch_op:
        batch_op.drop_column('entry_date')

    # ### end Alembic commands ###



################################################################################
# FILE: 2a686cd6fc98_phase1_rehabilitations.py
################################################################################

"""phase1: rehabilitations

Revision ID: 2a686cd6fc98
Revises: 65e783b3a01b
Create Date: 2026-06-20 22:10:32.925213

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '2a686cd6fc98'
down_revision = '65e783b3a01b'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('rehabilitations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('well_id', sa.Integer(), nullable=False),
    sa.Column('stage', sa.String(length=20), nullable=True),
    sa.Column('jyear', sa.String(length=8), nullable=True),
    sa.Column('rehab_date', sa.Date(), nullable=True),
    sa.Column('pumping_end_date', sa.Date(), nullable=True),
    sa.Column('rehab_contractor_id', sa.Integer(), nullable=True),
    sa.Column('pumping_contractor_id', sa.Integer(), nullable=True),
    sa.Column('pump_type_before', sa.String(length=60), nullable=True),
    sa.Column('discharge_before_lps', sa.Float(), nullable=True),
    sa.Column('pump_type_after', sa.String(length=60), nullable=True),
    sa.Column('discharge_after_lps', sa.Float(), nullable=True),
    sa.Column('discharge_change_lps', sa.Float(), nullable=True),
    sa.Column('reason', sa.String(length=120), nullable=True),
    sa.Column('method', sa.String(length=120), nullable=True),
    sa.Column('observed_fault', sa.Text(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('source', sa.String(length=40), nullable=True),
    sa.Column('created_by_id', sa.Integer(), nullable=True),
    sa.Column('updated_by_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('submitted_at', sa.DateTime(), nullable=True),
    sa.Column('approved_at', sa.DateTime(), nullable=True),
    sa.Column('reject_reason', sa.Text(), nullable=True),
    sa.Column('submitted_by_id', sa.Integer(), nullable=True),
    sa.Column('approved_by_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['approved_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['pumping_contractor_id'], ['suppliers.id'], ),
    sa.ForeignKeyConstraint(['rehab_contractor_id'], ['suppliers.id'], ),
    sa.ForeignKeyConstraint(['submitted_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['well_id'], ['wells.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('rehabilitations', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_rehabilitations_rehab_date'), ['rehab_date'], unique=False)
        batch_op.create_index(batch_op.f('ix_rehabilitations_source'), ['source'], unique=False)
        batch_op.create_index(batch_op.f('ix_rehabilitations_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_rehabilitations_well_id'), ['well_id'], unique=False)

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('rehabilitations', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_rehabilitations_well_id'))
        batch_op.drop_index(batch_op.f('ix_rehabilitations_status'))
        batch_op.drop_index(batch_op.f('ix_rehabilitations_source'))
        batch_op.drop_index(batch_op.f('ix_rehabilitations_rehab_date'))

    op.drop_table('rehabilitations')
    # ### end Alembic commands ###



################################################################################
# FILE: 2f94be0cc5fd_phase1_videometry_logs_findings.py
################################################################################

"""phase1: videometry logs + findings

Revision ID: 2f94be0cc5fd
Revises: 2a686cd6fc98
Create Date: 2026-06-20 22:19:50.138161

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '2f94be0cc5fd'
down_revision = '2a686cd6fc98'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('videometry_logs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('well_id', sa.Integer(), nullable=False),
    sa.Column('log_date', sa.Date(), nullable=True),
    sa.Column('contractor_id', sa.Integer(), nullable=True),
    sa.Column('equipment', sa.String(length=80), nullable=True),
    sa.Column('depth_from_m', sa.Float(), nullable=True),
    sa.Column('depth_to_m', sa.Float(), nullable=True),
    sa.Column('final_depth_m', sa.Float(), nullable=True),
    sa.Column('water_level_m', sa.Float(), nullable=True),
    sa.Column('video_file_ref', sa.String(length=255), nullable=True),
    sa.Column('summary', sa.Text(), nullable=True),
    sa.Column('source', sa.String(length=40), nullable=True),
    sa.Column('created_by_id', sa.Integer(), nullable=True),
    sa.Column('updated_by_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('submitted_at', sa.DateTime(), nullable=True),
    sa.Column('approved_at', sa.DateTime(), nullable=True),
    sa.Column('reject_reason', sa.Text(), nullable=True),
    sa.Column('submitted_by_id', sa.Integer(), nullable=True),
    sa.Column('approved_by_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['approved_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['contractor_id'], ['suppliers.id'], ),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['submitted_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['well_id'], ['wells.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('videometry_logs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_videometry_logs_log_date'), ['log_date'], unique=False)
        batch_op.create_index(batch_op.f('ix_videometry_logs_source'), ['source'], unique=False)
        batch_op.create_index(batch_op.f('ix_videometry_logs_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_videometry_logs_well_id'), ['well_id'], unique=False)

    op.create_table('videometry_findings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('videometry_id', sa.Integer(), nullable=False),
    sa.Column('depth_m', sa.Float(), nullable=True),
    sa.Column('finding_type', sa.String(length=30), nullable=True),
    sa.Column('severity', sa.String(length=10), nullable=True),
    sa.Column('note', sa.String(length=255), nullable=True),
    sa.ForeignKeyConstraint(['videometry_id'], ['videometry_logs.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('videometry_findings', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_videometry_findings_videometry_id'), ['videometry_id'], unique=False)

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('videometry_findings', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_videometry_findings_videometry_id'))

    op.drop_table('videometry_findings')
    with op.batch_alter_table('videometry_logs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_videometry_logs_well_id'))
        batch_op.drop_index(batch_op.f('ix_videometry_logs_status'))
        batch_op.drop_index(batch_op.f('ix_videometry_logs_source'))
        batch_op.drop_index(batch_op.f('ix_videometry_logs_log_date'))

    op.drop_table('videometry_logs')
    # ### end Alembic commands ###



################################################################################
# FILE: 3df9c24aed3f_flow_tests_add_source.py
################################################################################

"""flow_tests: add source

Revision ID: 3df9c24aed3f
Revises: a2e993f9396d
Create Date: 2026-06-20 20:23:18.530122

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '3df9c24aed3f'
down_revision = 'a2e993f9396d'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('flow_tests', schema=None) as batch_op:
        batch_op.add_column(sa.Column('source', sa.String(length=40), nullable=True))
        batch_op.create_index(batch_op.f('ix_flow_tests_source'), ['source'], unique=False)

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('flow_tests', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_flow_tests_source'))
        batch_op.drop_column('source')

    # ### end Alembic commands ###



################################################################################
# FILE: 3fcc112dd4e8_mechanic_workflow_stages.py
################################################################################

"""mechanic workflow stages

Revision ID: 3fcc112dd4e8
Revises: 1e92ce74455a
Create Date: 2026-07-05 19:00:28.096865

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '3fcc112dd4e8'
down_revision = '1e92ce74455a'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('mechanic_stage_logs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('event_id', sa.Integer(), nullable=False),
    sa.Column('from_stage', sa.String(length=60), nullable=True),
    sa.Column('to_stage', sa.String(length=60), nullable=True),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('changed_by_id', sa.Integer(), nullable=True),
    sa.Column('changed_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.ForeignKeyConstraint(['changed_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['event_id'], ['mechanic_events.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('mechanic_stage_logs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_mechanic_stage_logs_event_id'), ['event_id'], unique=False)

    with op.batch_alter_table('mechanic_events', schema=None) as batch_op:
        batch_op.add_column(sa.Column('stage', sa.String(length=60), nullable=True))
        batch_op.add_column(sa.Column('fault_type', sa.String(length=60), nullable=True))
        batch_op.create_index(batch_op.f('ix_mechanic_events_stage'), ['stage'], unique=False)

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('mechanic_events', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_mechanic_events_stage'))
        batch_op.drop_column('fault_type')
        batch_op.drop_column('stage')

    with op.batch_alter_table('mechanic_stage_logs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_mechanic_stage_logs_event_id'))

    op.drop_table('mechanic_stage_logs')
    # ### end Alembic commands ###



################################################################################
# FILE: 461af8a50d49_monthly_production_time_series.py
################################################################################

"""monthly_production time-series

Revision ID: 461af8a50d49
Revises: 46678007822c
Create Date: 2026-06-21 20:34:47.515251

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '461af8a50d49'
down_revision = '46678007822c'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('monthly_production',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('well_id', sa.Integer(), nullable=False),
    sa.Column('jyear', sa.Integer(), nullable=False),
    sa.Column('jmonth', sa.Integer(), nullable=False),
    sa.Column('production_m3', sa.Float(), nullable=True),
    sa.Column('run_hours', sa.Float(), nullable=True),
    sa.Column('avg_discharge_lps', sa.Float(), nullable=True),
    sa.Column('well_pressure', sa.Float(), nullable=True),
    sa.Column('source', sa.String(length=40), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['well_id'], ['wells.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('well_id', 'jyear', 'jmonth', name='uq_monthly_prod_well_period')
    )
    with op.batch_alter_table('monthly_production', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_monthly_production_jyear'), ['jyear'], unique=False)
        batch_op.create_index(batch_op.f('ix_monthly_production_source'), ['source'], unique=False)
        batch_op.create_index(batch_op.f('ix_monthly_production_well_id'), ['well_id'], unique=False)

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('monthly_production', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_monthly_production_well_id'))
        batch_op.drop_index(batch_op.f('ix_monthly_production_source'))
        batch_op.drop_index(batch_op.f('ix_monthly_production_jyear'))

    op.drop_table('monthly_production')
    # ### end Alembic commands ###



################################################################################
# FILE: 46678007822c_water_quality_well_baselines.py
################################################################################

"""water_quality + well_baselines

Revision ID: 46678007822c
Revises: 0f9d5cc6e8de
Create Date: 2026-06-21 17:24:28.438122

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '46678007822c'
down_revision = '0f9d5cc6e8de'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('well_baselines',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('well_id', sa.Integer(), nullable=False),
    sa.Column('anchor_event_type', sa.String(length=20), nullable=True),
    sa.Column('anchor_event_id', sa.Integer(), nullable=True),
    sa.Column('anchor_date', sa.Date(), nullable=True),
    sa.Column('baseline_kind', sa.String(length=20), nullable=True),
    sa.Column('baseline_discharge_lps', sa.Float(), nullable=True),
    sa.Column('baseline_dynamic_level', sa.Float(), nullable=True),
    sa.Column('baseline_specific_capacity', sa.Float(), nullable=True),
    sa.Column('baseline_date', sa.Date(), nullable=True),
    sa.Column('is_current', sa.Boolean(), nullable=True),
    sa.Column('source', sa.String(length=40), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['well_id'], ['wells.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('well_baselines', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_well_baselines_is_current'), ['is_current'], unique=False)
        batch_op.create_index(batch_op.f('ix_well_baselines_well_id'), ['well_id'], unique=False)

    op.create_table('water_quality',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('well_id', sa.Integer(), nullable=False),
    sa.Column('sample_date', sa.Date(), nullable=True),
    sa.Column('flow_test_id', sa.Integer(), nullable=True),
    sa.Column('turbidity', sa.Boolean(), nullable=True),
    sa.Column('sholat', sa.Boolean(), nullable=True),
    sa.Column('is_potable', sa.Boolean(), nullable=True),
    sa.Column('ec', sa.Float(), nullable=True),
    sa.Column('turbidity_ntu', sa.Float(), nullable=True),
    sa.Column('chlorine', sa.Float(), nullable=True),
    sa.Column('ph', sa.Float(), nullable=True),
    sa.Column('tds', sa.Float(), nullable=True),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('source', sa.String(length=40), nullable=True),
    sa.Column('created_by_id', sa.Integer(), nullable=True),
    sa.Column('updated_by_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['flow_test_id'], ['flow_tests.id'], ),
    sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['well_id'], ['wells.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('water_quality', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_water_quality_sample_date'), ['sample_date'], unique=False)
        batch_op.create_index(batch_op.f('ix_water_quality_source'), ['source'], unique=False)
        batch_op.create_index(batch_op.f('ix_water_quality_well_id'), ['well_id'], unique=False)

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('water_quality', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_water_quality_well_id'))
        batch_op.drop_index(batch_op.f('ix_water_quality_source'))
        batch_op.drop_index(batch_op.f('ix_water_quality_sample_date'))

    op.drop_table('water_quality')
    with op.batch_alter_table('well_baselines', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_well_baselines_well_id'))
        batch_op.drop_index(batch_op.f('ix_well_baselines_is_current'))

    op.drop_table('well_baselines')
    # ### end Alembic commands ###



################################################################################
# FILE: 541081dbd0db_finance_op_description.py
################################################################################

"""finance op_description

Revision ID: 541081dbd0db
Revises: eafc68d55b74
Create Date: 2026-07-07 11:02:00.417444

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '541081dbd0db'
down_revision = 'eafc68d55b74'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('finance_statements', schema=None) as batch_op:
        batch_op.add_column(sa.Column('op_description', sa.Text(), nullable=True))

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('finance_statements', schema=None) as batch_op:
        batch_op.drop_column('op_description')

    # ### end Alembic commands ###



################################################################################
# FILE: 65e783b3a01b_phase1_suppliers_pump_installations.py
################################################################################

"""phase1: suppliers + pump_installations

Revision ID: 65e783b3a01b
Revises: 937d9d8c1fdf
Create Date: 2026-06-20 21:31:39.886042

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '65e783b3a01b'
down_revision = '937d9d8c1fdf'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('suppliers',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=True),
    sa.Column('contact', sa.String(length=120), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('suppliers', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_suppliers_name'), ['name'], unique=True)

    op.create_table('pump_installations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('well_id', sa.Integer(), nullable=False),
    sa.Column('install_no', sa.Integer(), nullable=True),
    sa.Column('install_date', sa.Date(), nullable=True),
    sa.Column('pull_date', sa.Date(), nullable=True),
    sa.Column('motor_power_kw', sa.Float(), nullable=True),
    sa.Column('motor_condition', sa.String(length=10), nullable=True),
    sa.Column('pump_type', sa.String(length=60), nullable=True),
    sa.Column('pump_stages', sa.Integer(), nullable=True),
    sa.Column('pump_condition', sa.String(length=10), nullable=True),
    sa.Column('manufacturer_id', sa.Integer(), nullable=True),
    sa.Column('contractor_id', sa.Integer(), nullable=True),
    sa.Column('install_depth_m', sa.Float(), nullable=True),
    sa.Column('well_depth_m', sa.Float(), nullable=True),
    sa.Column('static_level', sa.Float(), nullable=True),
    sa.Column('dynamic_level', sa.Float(), nullable=True),
    sa.Column('route_loss', sa.Float(), nullable=True),
    sa.Column('grid_pressure_m', sa.Float(), nullable=True),
    sa.Column('work_shift', sa.String(length=20), nullable=True),
    sa.Column('removal_reason', sa.String(length=120), nullable=True),
    sa.Column('fault_by_operator', sa.Text(), nullable=True),
    sa.Column('fault_by_workshop', sa.Text(), nullable=True),
    sa.Column('pm_form_registered', sa.Boolean(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('source', sa.String(length=40), nullable=True),
    sa.Column('created_by_id', sa.Integer(), nullable=True),
    sa.Column('updated_by_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('submitted_at', sa.DateTime(), nullable=True),
    sa.Column('approved_at', sa.DateTime(), nullable=True),
    sa.Column('reject_reason', sa.Text(), nullable=True),
    sa.Column('submitted_by_id', sa.Integer(), nullable=True),
    sa.Column('approved_by_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['approved_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['contractor_id'], ['suppliers.id'], ),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['manufacturer_id'], ['suppliers.id'], ),
    sa.ForeignKeyConstraint(['submitted_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['well_id'], ['wells.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('pump_installations', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_pump_installations_install_date'), ['install_date'], unique=False)
        batch_op.create_index(batch_op.f('ix_pump_installations_source'), ['source'], unique=False)
        batch_op.create_index(batch_op.f('ix_pump_installations_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_pump_installations_well_id'), ['well_id'], unique=False)

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('pump_installations', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_pump_installations_well_id'))
        batch_op.drop_index(batch_op.f('ix_pump_installations_status'))
        batch_op.drop_index(batch_op.f('ix_pump_installations_source'))
        batch_op.drop_index(batch_op.f('ix_pump_installations_install_date'))

    op.drop_table('pump_installations')
    with op.batch_alter_table('suppliers', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_suppliers_name'))

    op.drop_table('suppliers')
    # ### end Alembic commands ###



################################################################################
# FILE: 7228c6b17e6b_relocations_table.py
################################################################################

"""relocations table

Revision ID: 7228c6b17e6b
Revises: 461af8a50d49
Create Date: 2026-06-22 15:35:29.006873

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7228c6b17e6b'
down_revision = '461af8a50d49'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('relocations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('well_id', sa.Integer(), nullable=False),
    sa.Column('new_well_id', sa.Integer(), nullable=True),
    sa.Column('decision_date', sa.Date(), nullable=True),
    sa.Column('reason', sa.String(length=120), nullable=True),
    sa.Column('candidacy', sa.String(length=20), nullable=True),
    sa.Column('reloc_type', sa.String(length=20), nullable=True),
    sa.Column('location_note', sa.String(length=200), nullable=True),
    sa.Column('letter_no', sa.String(length=60), nullable=True),
    sa.Column('distance_m', sa.Float(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('source', sa.String(length=40), nullable=True),
    sa.Column('created_by_id', sa.Integer(), nullable=True),
    sa.Column('updated_by_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('submitted_at', sa.DateTime(), nullable=True),
    sa.Column('approved_at', sa.DateTime(), nullable=True),
    sa.Column('reject_reason', sa.Text(), nullable=True),
    sa.Column('submitted_by_id', sa.Integer(), nullable=True),
    sa.Column('approved_by_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['approved_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['new_well_id'], ['wells.id'], ),
    sa.ForeignKeyConstraint(['submitted_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['well_id'], ['wells.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('relocations', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_relocations_decision_date'), ['decision_date'], unique=False)
        batch_op.create_index(batch_op.f('ix_relocations_source'), ['source'], unique=False)
        batch_op.create_index(batch_op.f('ix_relocations_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_relocations_well_id'), ['well_id'], unique=False)

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('relocations', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_relocations_well_id'))
        batch_op.drop_index(batch_op.f('ix_relocations_status'))
        batch_op.drop_index(batch_op.f('ix_relocations_source'))
        batch_op.drop_index(batch_op.f('ix_relocations_decision_date'))

    op.drop_table('relocations')
    # ### end Alembic commands ###



################################################################################
# FILE: 7aa4c86e912d_well_permit_events.py
################################################################################

"""well permit events

Revision ID: 7aa4c86e912d
Revises: a722e7d8c342
Create Date: 2026-07-01 20:18:48.228197

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7aa4c86e912d'
down_revision = 'a722e7d8c342'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('well_permit_events',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('well_id', sa.Integer(), nullable=False),
    sa.Column('permit_type', sa.String(length=60), nullable=True),
    sa.Column('permit_code', sa.String(length=40), nullable=True),
    sa.Column('permit_no', sa.String(length=60), nullable=True),
    sa.Column('permit_date', sa.Date(), nullable=True),
    sa.Column('expiry_date', sa.Date(), nullable=True),
    sa.Column('case_status', sa.String(length=60), nullable=True),
    sa.Column('klasse', sa.String(length=40), nullable=True),
    sa.Column('request_type', sa.String(length=120), nullable=True),
    sa.Column('followup_stage', sa.String(length=60), nullable=True),
    sa.Column('cost_paid', sa.Boolean(), nullable=True),
    sa.Column('expiry_penalty_rial', sa.Float(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('source', sa.String(length=40), nullable=True),
    sa.Column('created_by_id', sa.Integer(), nullable=True),
    sa.Column('updated_by_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('submitted_at', sa.DateTime(), nullable=True),
    sa.Column('approved_at', sa.DateTime(), nullable=True),
    sa.Column('reject_reason', sa.Text(), nullable=True),
    sa.Column('submitted_by_id', sa.Integer(), nullable=True),
    sa.Column('approved_by_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['approved_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['submitted_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['well_id'], ['wells.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('well_permit_events', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_well_permit_events_expiry_date'), ['expiry_date'], unique=False)
        batch_op.create_index(batch_op.f('ix_well_permit_events_source'), ['source'], unique=False)
        batch_op.create_index(batch_op.f('ix_well_permit_events_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_well_permit_events_well_id'), ['well_id'], unique=False)

    
    with op.batch_alter_table('well_permits', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_well_permits_expiry_date'))
        batch_op.drop_index(batch_op.f('ix_well_permits_source'))
        batch_op.drop_index(batch_op.f('ix_well_permits_status'))
        batch_op.drop_index(batch_op.f('ix_well_permits_well_id'))

    op.drop_table('well_permits')
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('well_permits',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('well_id', sa.INTEGER(), nullable=False),
    sa.Column('permit_code', sa.VARCHAR(length=40), nullable=True),
    sa.Column('permit_type', sa.VARCHAR(length=60), nullable=True),
    sa.Column('permit_no', sa.VARCHAR(length=60), nullable=True),
    sa.Column('permit_date', sa.VARCHAR(length=10), nullable=True),
    sa.Column('expiry_date', sa.VARCHAR(length=10), nullable=True),
    sa.Column('case_status', sa.VARCHAR(length=60), nullable=True),
    sa.Column('klasse', sa.VARCHAR(length=40), nullable=True),
    sa.Column('request_type', sa.VARCHAR(length=120), nullable=True),
    sa.Column('followup_stage', sa.VARCHAR(length=60), nullable=True),
    sa.Column('cost_paid', sa.BOOLEAN(), nullable=True),
    sa.Column('expiry_penalty_rial', sa.FLOAT(), nullable=True),
    sa.Column('contract_power_kw', sa.FLOAT(), nullable=True),
    sa.Column('tariff', sa.VARCHAR(length=40), nullable=True),
    sa.Column('notes', sa.TEXT(), nullable=True),
    sa.Column('source', sa.VARCHAR(length=40), nullable=True),
    sa.Column('created_by_id', sa.INTEGER(), nullable=True),
    sa.Column('updated_by_id', sa.INTEGER(), nullable=True),
    sa.Column('created_at', sa.DATETIME(), nullable=False),
    sa.Column('updated_at', sa.DATETIME(), nullable=False),
    sa.Column('status', sa.VARCHAR(length=20), nullable=False),
    sa.Column('submitted_at', sa.DATETIME(), nullable=True),
    sa.Column('approved_at', sa.DATETIME(), nullable=True),
    sa.Column('reject_reason', sa.TEXT(), nullable=True),
    sa.Column('submitted_by_id', sa.INTEGER(), nullable=True),
    sa.Column('approved_by_id', sa.INTEGER(), nullable=True),
    sa.ForeignKeyConstraint(['approved_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['submitted_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['well_id'], ['wells.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('well_permits', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_well_permits_well_id'), ['well_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_well_permits_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_well_permits_source'), ['source'], unique=False)
        batch_op.create_index(batch_op.f('ix_well_permits_expiry_date'), ['expiry_date'], unique=False)

    op.create_table('production_trend',
    *[sa.Column('well_name', sa.TEXT(), nullable=True),
    sa.Column('department', sa.TEXT(), nullable=True),
    sa.Column('test_date_1400', sa.TEXT(), nullable=True),
    sa.Column('test_date_1401', sa.TEXT(), nullable=True),
    sa.Column('test_date_1402', sa.TEXT(), nullable=True),
    sa.Column('test_date_1403', sa.TEXT(), nullable=True),
    sa.Column('test_date_1404', sa.TEXT(), nullable=True),
    sa.Column('test_date_1405', sa.TEXT(), nullable=True),
    sa.Column('pressure_test_date_1400', sa.TEXT(), nullable=True),
    sa.Column('pressure_atm_1400', sa.TEXT(), nullable=True),
    sa.Column('pressure_test_date_1401', sa.TEXT(), nullable=True),
    sa.Column('pressure_atm_1401', sa.TEXT(), nullable=True),
    sa.Column('pressure_test_date_1402', sa.TEXT(), nullable=True),
    sa.Column('pressure_atm_1402', sa.TEXT(), nullable=True),
    sa.Column('pressure_test_date_1403', sa.TEXT(), nullable=True),
    sa.Column('pressure_atm_1403', sa.TEXT(), nullable=True),
    sa.Column('pressure_test_date_1404', sa.TEXT(), nullable=True),
    sa.Column('pressure_atm_1404', sa.TEXT(), nullable=True),
    sa.Column('pressure_test_date_1405', sa.TEXT(), nullable=True),
    sa.Column('pressure_atm_1405', sa.TEXT(), nullable=True),
    sa.Column('flow_test_date_1400', sa.TEXT(), nullable=True),
    sa.Column('flow_rate_lps_1400', sa.TEXT(), nullable=True),
    sa.Column('flow_test_date_1401', sa.TEXT(), nullable=True),
    sa.Column('flow_rate_lps_1401', sa.TEXT(), nullable=True),
    sa.Column('flow_test_date_1402', sa.TEXT(), nullable=True),
    sa.Column('flow_rate_lps_1402', sa.TEXT(), nullable=True),
    sa.Column('flow_test_date_1403', sa.TEXT(), nullable=True),
    sa.Column('flow_rate_lps_1403', sa.TEXT(), nullable=True),
    sa.Column('flow_test_date_1404', sa.TEXT(), nullable=True),
    sa.Column('flow_rate_lps_1404', sa.TEXT(), nullable=True),
    sa.Column('flow_test_date_1405', sa.TEXT(), nullable=True),
    sa.Column('flow_rate_lps_1405', sa.TEXT(), nullable=True),
    sa.Column('production_zone_name', sa.TEXT(), nullable=True),
    sa.Column('low_runtime_reason', sa.TEXT(), nullable=True),
    sa.Column('electropump_installation_date', sa.INTEGER(), nullable=True),
    sa.Column('observed_fault_last_rehabilitation', sa.TEXT(), nullable=True),
    sa.Column('last_rehabilitation_date', sa.INTEGER(), nullable=True),
    sa.Column('permit_expiry', sa.TEXT(), nullable=True),
    sa.Column('well_permit', sa.TEXT(), nullable=True),
    sa.Column('well_type', sa.TEXT(), nullable=True),
    sa.Column('well_location_status', sa.TEXT(), nullable=True),
    sa.Column('proposed_permitted_flow_lps', sa.TEXT(), nullable=True),
    sa.Column('test_end_date', sa.TEXT(), nullable=True),
    sa.Column('contractor', sa.TEXT(), nullable=True),
    sa.Column('drilling_year', sa.TEXT(), nullable=True),
    sa.Column('max_flow_rate', sa.TEXT(), nullable=True),
    sa.Column('drawdown_amount', sa.TEXT(), nullable=True),
    sa.Column('static_level', sa.TEXT(), nullable=True),
    sa.Column('dynamic_level', sa.TEXT(), nullable=True),
    sa.Column('main_zone', sa.TEXT(), nullable=True),
    sa.Column('sub_zone', sa.TEXT(), nullable=True),
    sa.Column('well_status', sa.TEXT(), nullable=True),
    sa.Column('installation_1', sa.TEXT(), nullable=True),
    sa.Column('motor_1', sa.TEXT(), nullable=True),
    sa.Column('motor_new_repaired_1', sa.TEXT(), nullable=True),
    sa.Column('pump_1', sa.TEXT(), nullable=True),
    sa.Column('manufacturer_1', sa.TEXT(), nullable=True),
    sa.Column('pump_new_repaired_1', sa.TEXT(), nullable=True),
    sa.Column('stage_1', sa.TEXT(), nullable=True),
    sa.Column('depth_1', sa.TEXT(), nullable=True),
    sa.Column('pulling_1', sa.TEXT(), nullable=True),
    sa.Column('interval_1_months', sa.TEXT(), nullable=True),
    sa.Column('installation_2', sa.TEXT(), nullable=True),
    sa.Column('motor_2', sa.TEXT(), nullable=True),
    sa.Column('motor_new_repaired_2', sa.TEXT(), nullable=True),
    sa.Column('pump_2', sa.TEXT(), nullable=True),
    sa.Column('manufacturer_2', sa.TEXT(), nullable=True),
    sa.Column('pump_new_repaired_2', sa.TEXT(), nullable=True),
    sa.Column('stage_2', sa.TEXT(), nullable=True),
    sa.Column('depth_2', sa.TEXT(), nullable=True),
    sa.Column('pulling_2', sa.TEXT(), nullable=True),
    sa.Column('interval_2_months', sa.TEXT(), nullable=True),
    sa.Column('installation_3', sa.TEXT(), nullable=True),
    sa.Column('motor_3', sa.TEXT(), nullable=True),
    sa.Column('motor_new_repaired_3', sa.TEXT(), nullable=True),
    sa.Column('pump_3', sa.TEXT(), nullable=True),
    sa.Column('manufacturer_3', sa.TEXT(), nullable=True),
    sa.Column('pump_new_repaired_3', sa.TEXT(), nullable=True),
    sa.Column('stage_3', sa.TEXT(), nullable=True),
    sa.Column('depth_3', sa.TEXT(), nullable=True),
    sa.Column('pulling_3', sa.TEXT(), nullable=True),
    sa.Column('interval_3_months', sa.TEXT(), nullable=True),
    sa.Column('installation_4', sa.TEXT(), nullable=True),
    sa.Column('motor_4', sa.TEXT(), nullable=True),
    sa.Column('motor_new_repaired_4', sa.TEXT(), nullable=True),
    sa.Column('pump_4', sa.TEXT(), nullable=True),
    sa.Column('manufacturer_4', sa.TEXT(), nullable=True),
    sa.Column('pump_new_repaired_4', sa.TEXT(), nullable=True),
    sa.Column('stage_4', sa.TEXT(), nullable=True),
    sa.Column('depth_4', sa.TEXT(), nullable=True),
    sa.Column('pulling_4', sa.TEXT(), nullable=True),
    sa.Column('interval_4_months', sa.TEXT(), nullable=True),
    sa.Column('installation_5', sa.TEXT(), nullable=True),
    sa.Column('motor_5', sa.TEXT(), nullable=True),
    sa.Column('motor_new_repaired_5', sa.TEXT(), nullable=True),
    sa.Column('pump_5', sa.TEXT(), nullable=True),
    sa.Column('manufacturer_5', sa.TEXT(), nullable=True),
    sa.Column('pump_new_repaired_5', sa.TEXT(), nullable=True),
    sa.Column('stage_5', sa.TEXT(), nullable=True),
    sa.Column('depth_5', sa.TEXT(), nullable=True),
    sa.Column('pulling_5', sa.TEXT(), nullable=True),
    sa.Column('interval_5_months', sa.TEXT(), nullable=True),
    sa.Column('installation_open', sa.TEXT(), nullable=True),
    sa.Column('motor_open', sa.TEXT(), nullable=True),
    sa.Column('motor_new_repaired_open', sa.TEXT(), nullable=True),
    sa.Column('pump_open', sa.TEXT(), nullable=True),
    sa.Column('manufacturer_open', sa.TEXT(), nullable=True),
    sa.Column('pump_new_repaired_open', sa.TEXT(), nullable=True),
    sa.Column('stage_open', sa.TEXT(), nullable=True),
    sa.Column('depth_open', sa.TEXT(), nullable=True),
    sa.Column('age_until_1405_03_01_months', sa.TEXT(), nullable=True),
    sa.Column('full_cycle_count', sa.TEXT(), nullable=True),
    sa.Column('full_average_months', sa.TEXT(), nullable=True),
    sa.Column('total_average_with_open_installation_months', sa.TEXT(), nullable=True),
    sa.Column('contractors', sa.TEXT(), nullable=True),
    sa.Column('well_pressure_1400_farvardin', sa.INTEGER(), nullable=True),
    sa.Column('well_pressure_1400_ordibehesht', sa.INTEGER(), nullable=True),
    sa.Column('well_pressure_1400_khordad', sa.INTEGER(), nullable=True),
    sa.Column('well_pressure_1400_tir', sa.INTEGER(), nullable=True),
    sa.Column('well_pressure_1400_mordad', sa.INTEGER(), nullable=True),
    sa.Column('well_pressure_1400_shahrivar', sa.INTEGER(), nullable=True),
    sa.Column('well_pressure_1400_mehr', sa.INTEGER(), nullable=True),
    sa.Column('well_pressure_1400_aban', sa.INTEGER(), nullable=True),
    sa.Column('well_pressure_1400_azar', sa.INTEGER(), nullable=True),
    sa.Column('well_pressure_1400_dey', sa.INTEGER(), nullable=True),
    sa.Column('well_pressure_1400_bahman', sa.INTEGER(), nullable=True),
    sa.Column('well_pressure_1400_esfand', sa.INTEGER(), nullable=True),
    sa.Column('well_pressure_1401_farvardin', sa.INTEGER(), nullable=True),
    sa.Column('well_pressure_1401_ordibehesht', sa.INTEGER(), nullable=True),
    sa.Column('well_pressure_1401_khordad', sa.INTEGER(), nullable=True),
    sa.Column('well_pressure_1401_tir', sa.INTEGER(), nullable=True),
    sa.Column('well_pressure_1401_mordad', sa.INTEGER(), nullable=True),
    sa.Column('well_pressure_1401_shahrivar', sa.INTEGER(), nullable=True),
    sa.Column('well_pressure_1401_mehr', sa.REAL(), nullable=True),
    sa.Column('well_pressure_1401_aban', sa.INTEGER(), nullable=True),
    sa.Column('well_pressure_1401_azar', sa.INTEGER(), nullable=True),
    sa.Column('well_pressure_1401_dey', sa.INTEGER(), nullable=True),
    sa.Column('well_pressure_1401_bahman', sa.INTEGER(), nullable=True),
    sa.Column('well_pressure_1401_esfand', sa.INTEGER(), nullable=True),
    sa.Column('well_pressure_1402_farvardin', sa.INTEGER(), nullable=True),
    sa.Column('well_pressure_1402_ordibehesht', sa.INTEGER(), nullable=True),
    sa.Column('well_pressure_1402_khordad', sa.INTEGER(), nullable=True),
    sa.Column('well_pressure_1402_tir', sa.INTEGER(), nullable=True),
    sa.Column('well_pressure_1402_mordad', sa.INTEGER(), nullable=True),
    sa.Column('well_pressure_1402_shahrivar', sa.INTEGER(), nullable=True),
    sa.Column('well_pressure_1402_mehr', sa.INTEGER(), nullable=True),
    sa.Column('well_pressure_1402_aban', sa.INTEGER(), nullable=True),
    sa.Column('well_pressure_1402_azar', sa.INTEGER(), nullable=True),
    sa.Column('well_pressure_1402_dey', sa.INTEGER(), nullable=True),
    sa.Column('well_pressure_1402_bahman', sa.INTEGER(), nullable=True),
    sa.Column('well_pressure_1402_esfand', sa.INTEGER(), nullable=True),
    sa.Column('well_pressure_1403_farvardin', sa.INTEGER(), nullable=True),
    sa.Column('well_pressure_1403_ordibehesht', sa.INTEGER(), nullable=True),
    sa.Column('well_pressure_1403_khordad', sa.INTEGER(), nullable=True),
    sa.Column('well_pressure_1403_tir', sa.INTEGER(), nullable=True),
    sa.Column('well_pressure_1403_mordad', sa.INTEGER(), nullable=True),
    sa.Column('well_pressure_1403_shahrivar', sa.INTEGER(), nullable=True),
    sa.Column('well_pressure_1403_mehr', sa.INTEGER(), nullable=True),
    sa.Column('well_pressure_1403_aban', sa.INTEGER(), nullable=True),
    sa.Column('well_pressure_1403_azar', sa.INTEGER(), nullable=True),
    sa.Column('well_pressure_1403_dey', sa.INTEGER(), nullable=True),
    sa.Column('well_pressure_1403_bahman', sa.INTEGER(), nullable=True),
    sa.Column('well_pressure_1403_esfand', sa.INTEGER(), nullable=True),
    sa.Column('well_pressure_1404_farvardin', sa.INTEGER(), nullable=True),
    sa.Column('well_pressure_1404_ordibehesht', sa.INTEGER(), nullable=True),
    sa.Column('well_pressure_1404_khordad', sa.INTEGER(), nullable=True),
    sa.Column('well_pressure_1404_tir', sa.INTEGER(), nullable=True),
    sa.Column('well_pressure_1404_mordad', sa.INTEGER(), nullable=True),
    sa.Column('well_pressure_1404_shahrivar', sa.INTEGER(), nullable=True),
    sa.Column('well_pressure_1404_mehr', sa.INTEGER(), nullable=True),
    sa.Column('well_pressure_1404_aban', sa.INTEGER(), nullable=True),
    sa.Column('well_pressure_1404_azar', sa.INTEGER(), nullable=True),
    sa.Column('well_pressure_1404_dey', sa.INTEGER(), nullable=True),
    sa.Column('well_pressure_1404_bahman', sa.INTEGER(), nullable=True),
    sa.Column('well_pressure_1404_esfand', sa.INTEGER(), nullable=True),
    sa.Column('well_pressure_1405_farvardin', sa.INTEGER(), nullable=True),
    sa.Column('well_pressure_1405_ordibehesht', sa.INTEGER(), nullable=True),
    sa.Column('well_pressure_1405_khordad', sa.INTEGER(), nullable=True),
    sa.Column('pressure_year_1400', sa.INTEGER(), nullable=True),
    sa.Column('pressure_year_1401', sa.REAL(), nullable=True),
    sa.Column('pressure_year_1402', sa.INTEGER(), nullable=True),
    sa.Column('pressure_year_1403', sa.REAL(), nullable=True),
    sa.Column('pressure_year_1404', sa.INTEGER(), nullable=True),
    sa.Column('production_year_1399', sa.INTEGER(), nullable=True),
    sa.Column('production_year_1400', sa.INTEGER(), nullable=True),
    sa.Column('production_year_1401', sa.INTEGER(), nullable=True),
    sa.Column('production_year_1402', sa.INTEGER(), nullable=True),
    sa.Column('production_year_1403', sa.INTEGER(), nullable=True),
    sa.Column('production_year_1404', sa.INTEGER(), nullable=True),
    sa.Column('production_year_1405', sa.INTEGER(), nullable=True),
    sa.Column('production_1399_farvardin', sa.INTEGER(), nullable=True),
    sa.Column('production_1399_ordibehesht', sa.INTEGER(), nullable=True),
    sa.Column('production_1399_khordad', sa.INTEGER(), nullable=True),
    sa.Column('production_1399_tir', sa.INTEGER(), nullable=True),
    sa.Column('production_1399_mordad', sa.INTEGER(), nullable=True),
    sa.Column('production_1399_shahrivar', sa.INTEGER(), nullable=True),
    sa.Column('production_1399_mehr', sa.INTEGER(), nullable=True),
    sa.Column('production_1399_aban', sa.INTEGER(), nullable=True),
    sa.Column('production_1399_azar', sa.INTEGER(), nullable=True),
    sa.Column('production_1399_dey', sa.INTEGER(), nullable=True),
    sa.Column('production_1399_bahman', sa.INTEGER(), nullable=True),
    sa.Column('production_1399_esfand', sa.INTEGER(), nullable=True),
    sa.Column('production_1400_farvardin', sa.INTEGER(), nullable=True),
    sa.Column('production_1400_ordibehesht', sa.INTEGER(), nullable=True),
    sa.Column('production_1400_khordad', sa.INTEGER(), nullable=True),
    sa.Column('production_1400_tir', sa.INTEGER(), nullable=True),
    sa.Column('production_1400_mordad', sa.INTEGER(), nullable=True),
    sa.Column('production_1400_shahrivar', sa.INTEGER(), nullable=True),
    sa.Column('production_1400_mehr', sa.INTEGER(), nullable=True),
    sa.Column('production_1400_aban', sa.INTEGER(), nullable=True),
    sa.Column('production_1400_azar', sa.INTEGER(), nullable=True),
    sa.Column('production_1400_dey', sa.INTEGER(), nullable=True),
    sa.Column('production_1400_bahman', sa.INTEGER(), nullable=True),
    sa.Column('production_1400_esfand', sa.INTEGER(), nullable=True),
    sa.Column('production_1401_farvardin', sa.INTEGER(), nullable=True),
    sa.Column('production_1401_ordibehesht', sa.INTEGER(), nullable=True),
    sa.Column('production_1401_khordad', sa.INTEGER(), nullable=True),
    sa.Column('production_1401_tir', sa.INTEGER(), nullable=True),
    sa.Column('production_1401_mordad', sa.INTEGER(), nullable=True),
    sa.Column('production_1401_shahrivar', sa.INTEGER(), nullable=True),
    sa.Column('production_1401_mehr', sa.INTEGER(), nullable=True),
    sa.Column('production_1401_aban', sa.INTEGER(), nullable=True),
    sa.Column('production_1401_azar', sa.INTEGER(), nullable=True),
    sa.Column('production_1401_dey', sa.INTEGER(), nullable=True),
    sa.Column('production_1401_bahman', sa.INTEGER(), nullable=True),
    sa.Column('production_1401_esfand', sa.INTEGER(), nullable=True),
    sa.Column('production_1402_farvardin', sa.INTEGER(), nullable=True),
    sa.Column('production_1402_ordibehesht', sa.INTEGER(), nullable=True),
    sa.Column('production_1402_khordad', sa.INTEGER(), nullable=True),
    sa.Column('production_1402_tir', sa.INTEGER(), nullable=True),
    sa.Column('production_1402_mordad', sa.INTEGER(), nullable=True),
    sa.Column('production_1402_shahrivar', sa.INTEGER(), nullable=True),
    sa.Column('production_1402_mehr', sa.INTEGER(), nullable=True),
    sa.Column('production_1402_aban', sa.INTEGER(), nullable=True),
    sa.Column('production_1402_azar', sa.INTEGER(), nullable=True),
    sa.Column('production_1402_dey', sa.INTEGER(), nullable=True),
    sa.Column('production_1402_bahman', sa.INTEGER(), nullable=True),
    sa.Column('production_1402_esfand', sa.INTEGER(), nullable=True),
    sa.Column('production_1403_farvardin', sa.INTEGER(), nullable=True),
    sa.Column('production_1403_ordibehesht', sa.INTEGER(), nullable=True),
    sa.Column('production_1403_khordad', sa.INTEGER(), nullable=True),
    sa.Column('production_1403_tir', sa.INTEGER(), nullable=True),
    sa.Column('production_1403_mordad', sa.INTEGER(), nullable=True),
    sa.Column('production_1403_shahrivar', sa.INTEGER(), nullable=True),
    sa.Column('production_1403_mehr', sa.INTEGER(), nullable=True),
    sa.Column('production_1403_aban', sa.INTEGER(), nullable=True),
    sa.Column('production_1403_azar', sa.INTEGER(), nullable=True),
    sa.Column('production_1403_dey', sa.INTEGER(), nullable=True),
    sa.Column('production_1403_bahman', sa.INTEGER(), nullable=True),
    sa.Column('production_1403_esfand', sa.INTEGER(), nullable=True),
    sa.Column('production_1404_farvardin', sa.INTEGER(), nullable=True),
    sa.Column('production_1404_ordibehesht', sa.INTEGER(), nullable=True),
    sa.Column('production_1404_khordad', sa.INTEGER(), nullable=True),
    sa.Column('production_1404_tir', sa.INTEGER(), nullable=True),
    sa.Column('production_1404_mordad', sa.INTEGER(), nullable=True),
    sa.Column('production_1404_shahrivar', sa.INTEGER(), nullable=True),
    sa.Column('production_1404_mehr', sa.INTEGER(), nullable=True),
    sa.Column('production_1404_aban', sa.INTEGER(), nullable=True),
    sa.Column('production_1404_azar', sa.INTEGER(), nullable=True),
    sa.Column('production_1404_dey', sa.INTEGER(), nullable=True),
    sa.Column('production_1404_bahman', sa.INTEGER(), nullable=True),
    sa.Column('production_1404_esfand', sa.INTEGER(), nullable=True),
    sa.Column('production_1405_farvardin', sa.INTEGER(), nullable=True),
    sa.Column('production_1405_ordibehesht', sa.INTEGER(), nullable=True),
    sa.Column('runtime_year_1399', sa.INTEGER(), nullable=True),
    sa.Column('runtime_year_1400', sa.INTEGER(), nullable=True),
    sa.Column('runtime_year_1401', sa.INTEGER(), nullable=True),
    sa.Column('runtime_year_1402', sa.INTEGER(), nullable=True),
    sa.Column('runtime_year_1403', sa.INTEGER(), nullable=True),
    sa.Column('runtime_year_1404', sa.INTEGER(), nullable=True),
    sa.Column('runtime_year_1405', sa.INTEGER(), nullable=True),
    sa.Column('runtime_farvardin_1399', sa.INTEGER(), nullable=True),
    sa.Column('runtime_ordibehesht_1399', sa.INTEGER(), nullable=True),
    sa.Column('runtime_khordad_1399', sa.INTEGER(), nullable=True),
    sa.Column('runtime_tir_1399', sa.INTEGER(), nullable=True),
    sa.Column('runtime_mordad_1399', sa.INTEGER(), nullable=True),
    sa.Column('runtime_shahrivar_1399', sa.INTEGER(), nullable=True),
    sa.Column('runtime_mehr_1399', sa.INTEGER(), nullable=True),
    sa.Column('runtime_aban_1399', sa.INTEGER(), nullable=True),
    sa.Column('runtime_azar_1399', sa.INTEGER(), nullable=True),
    sa.Column('runtime_dey_1399', sa.INTEGER(), nullable=True),
    sa.Column('runtime_bahman_1399', sa.INTEGER(), nullable=True),
    sa.Column('runtime_esfand_1399', sa.INTEGER(), nullable=True),
    sa.Column('runtime_farvardin_1400', sa.INTEGER(), nullable=True),
    sa.Column('runtime_ordibehesht_1400', sa.INTEGER(), nullable=True),
    sa.Column('runtime_khordad_1400', sa.INTEGER(), nullable=True),
    sa.Column('runtime_tir_1400', sa.INTEGER(), nullable=True),
    sa.Column('runtime_mordad_1400', sa.INTEGER(), nullable=True),
    sa.Column('runtime_shahrivar_1400', sa.INTEGER(), nullable=True),
    sa.Column('runtime_mehr_1400', sa.INTEGER(), nullable=True),
    sa.Column('runtime_aban_1400', sa.INTEGER(), nullable=True),
    sa.Column('runtime_azar_1400', sa.INTEGER(), nullable=True),
    sa.Column('runtime_dey_1400', sa.INTEGER(), nullable=True),
    sa.Column('runtime_bahman_1400', sa.INTEGER(), nullable=True),
    sa.Column('runtime_esfand_1400', sa.INTEGER(), nullable=True),
    sa.Column('runtime_farvardin_1401', sa.INTEGER(), nullable=True),
    sa.Column('runtime_ordibehesht_1401', sa.INTEGER(), nullable=True),
    sa.Column('runtime_khordad_1401', sa.INTEGER(), nullable=True),
    sa.Column('runtime_tir_1401', sa.INTEGER(), nullable=True),
    sa.Column('runtime_mordad_1401', sa.INTEGER(), nullable=True),
    sa.Column('runtime_shahrivar_1401', sa.INTEGER(), nullable=True),
    sa.Column('runtime_mehr_1401', sa.INTEGER(), nullable=True),
    sa.Column('runtime_aban_1401', sa.INTEGER(), nullable=True),
    sa.Column('runtime_azar_1401', sa.INTEGER(), nullable=True),
    sa.Column('runtime_dey_1401', sa.INTEGER(), nullable=True),
    sa.Column('runtime_bahman_1401', sa.INTEGER(), nullable=True),
    sa.Column('runtime_esfand_1401', sa.INTEGER(), nullable=True),
    sa.Column('runtime_farvardin_1402', sa.INTEGER(), nullable=True),
    sa.Column('runtime_ordibehesht_1402', sa.INTEGER(), nullable=True),
    sa.Column('runtime_khordad_1402', sa.INTEGER(), nullable=True),
    sa.Column('runtime_tir_1402', sa.INTEGER(), nullable=True),
    sa.Column('runtime_mordad_1402', sa.INTEGER(), nullable=True),
    sa.Column('runtime_shahrivar_1402', sa.INTEGER(), nullable=True),
    sa.Column('runtime_mehr_1402', sa.INTEGER(), nullable=True),
    sa.Column('runtime_aban_1402', sa.INTEGER(), nullable=True),
    sa.Column('runtime_azar_1402', sa.INTEGER(), nullable=True),
    sa.Column('runtime_dey_1402', sa.INTEGER(), nullable=True),
    sa.Column('runtime_bahman_1402', sa.INTEGER(), nullable=True),
    sa.Column('runtime_esfand_1402', sa.INTEGER(), nullable=True),
    sa.Column('runtime_farvardin_1403', sa.INTEGER(), nullable=True),
    sa.Column('runtime_ordibehesht_1403', sa.INTEGER(), nullable=True),
    sa.Column('runtime_khordad_1403', sa.INTEGER(), nullable=True),
    sa.Column('runtime_tir_1403', sa.INTEGER(), nullable=True),
    sa.Column('runtime_mordad_1403', sa.INTEGER(), nullable=True),
    sa.Column('runtime_shahrivar_1403', sa.INTEGER(), nullable=True),
    sa.Column('runtime_mehr_1403', sa.INTEGER(), nullable=True),
    sa.Column('runtime_aban_1403', sa.INTEGER(), nullable=True),
    sa.Column('runtime_azar_1403', sa.INTEGER(), nullable=True),
    sa.Column('runtime_dey_1403', sa.INTEGER(), nullable=True),
    sa.Column('runtime_bahman_1403', sa.INTEGER(), nullable=True),
    sa.Column('runtime_esfand_1403', sa.INTEGER(), nullable=True),
    sa.Column('runtime_farvardin_1404', sa.INTEGER(), nullable=True),
    sa.Column('runtime_ordibehesht_1404', sa.INTEGER(), nullable=True),
    sa.Column('runtime_khordad_1404', sa.INTEGER(), nullable=True),
    sa.Column('runtime_tir_1404', sa.INTEGER(), nullable=True),
    sa.Column('runtime_mordad_1404', sa.INTEGER(), nullable=True),
    sa.Column('runtime_shahrivar_1404', sa.INTEGER(), nullable=True),
    sa.Column('runtime_mehr_1404', sa.INTEGER(), nullable=True),
    sa.Column('runtime_aban_1404', sa.INTEGER(), nullable=True),
    sa.Column('runtime_azar_1404', sa.INTEGER(), nullable=True),
    sa.Column('runtime_dey_1404', sa.INTEGER(), nullable=True),
    sa.Column('runtime_bahman_1404', sa.INTEGER(), nullable=True),
    sa.Column('runtime_esfand_1404', sa.INTEGER(), nullable=True),
    sa.Column('runtime_farvardin_1405', sa.INTEGER(), nullable=True),
    sa.Column('runtime_ordibehesht_1405', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_year_1399', sa.INTEGER(), nullable=True),
    sa.Column('contractor_1399', sa.TEXT(), nullable=True),
    sa.Column('removal_mordad_1399', sa.TEXT(), nullable=True),
    sa.Column('removal_bahman_1399', sa.TEXT(), nullable=True),
    sa.Column('average_flow_year_1400', sa.INTEGER(), nullable=True),
    sa.Column('contractor_1400', sa.TEXT(), nullable=True),
    sa.Column('removal_shahrivar_1400', sa.TEXT(), nullable=True),
    sa.Column('removal_aban_1400', sa.TEXT(), nullable=True),
    sa.Column('removal_dey_1400', sa.TEXT(), nullable=True),
    sa.Column('removal_bahman_1400', sa.TEXT(), nullable=True),
    sa.Column('average_flow_year_1401', sa.INTEGER(), nullable=True),
    sa.Column('contractor_1401', sa.TEXT(), nullable=True),
    sa.Column('removal_khordad_1401', sa.TEXT(), nullable=True),
    sa.Column('removal_tir_1401', sa.TEXT(), nullable=True),
    sa.Column('removal_shahrivar_1401', sa.TEXT(), nullable=True),
    sa.Column('removal_azar_1401', sa.TEXT(), nullable=True),
    sa.Column('removal_dey_1401', sa.TEXT(), nullable=True),
    sa.Column('removal_bahman_1401', sa.TEXT(), nullable=True),
    sa.Column('removal_esfand_1401', sa.TEXT(), nullable=True),
    sa.Column('average_flow_year_1402', sa.INTEGER(), nullable=True),
    sa.Column('contractor_1402', sa.TEXT(), nullable=True),
    sa.Column('removal_farvardin_1402', sa.TEXT(), nullable=True),
    sa.Column('removal_ordibehesht_1402', sa.TEXT(), nullable=True),
    sa.Column('removal_khordad_1402', sa.TEXT(), nullable=True),
    sa.Column('removal_tir_1402', sa.TEXT(), nullable=True),
    sa.Column('removal_mordad_1402', sa.TEXT(), nullable=True),
    sa.Column('removal_shahrivar_1402', sa.TEXT(), nullable=True),
    sa.Column('removal_aban_1402', sa.TEXT(), nullable=True),
    sa.Column('removal_azar_1402', sa.TEXT(), nullable=True),
    sa.Column('removal_dey_1402', sa.TEXT(), nullable=True),
    sa.Column('removal_bahman_1402', sa.TEXT(), nullable=True),
    sa.Column('removal_esfand_1402', sa.TEXT(), nullable=True),
    sa.Column('average_flow_year_1403', sa.INTEGER(), nullable=True),
    sa.Column('contractor_1403', sa.TEXT(), nullable=True),
    sa.Column('removal_farvardin_1403', sa.TEXT(), nullable=True),
    sa.Column('removal_ordibehesht_1403', sa.TEXT(), nullable=True),
    sa.Column('removal_khordad_1403', sa.TEXT(), nullable=True),
    sa.Column('removal_mordad_1403', sa.TEXT(), nullable=True),
    sa.Column('removal_shahrivar_1403', sa.TEXT(), nullable=True),
    sa.Column('removal_aban_1403', sa.TEXT(), nullable=True),
    sa.Column('removal_azar_1403', sa.TEXT(), nullable=True),
    sa.Column('removal_bahman_1403', sa.TEXT(), nullable=True),
    sa.Column('average_flow_year_1404', sa.INTEGER(), nullable=True),
    sa.Column('contractor_1404', sa.TEXT(), nullable=True),
    sa.Column('removal_farvardin_1404', sa.TEXT(), nullable=True),
    sa.Column('removal_khordad_1404', sa.TEXT(), nullable=True),
    sa.Column('removal_shahrivar_1404', sa.TEXT(), nullable=True),
    sa.Column('removal_aban_1404', sa.TEXT(), nullable=True),
    sa.Column('removal_azar_1404', sa.TEXT(), nullable=True),
    sa.Column('removal_dey_1404', sa.TEXT(), nullable=True),
    sa.Column('removal_bahman_1404', sa.TEXT(), nullable=True),
    sa.Column('removal_esfand_1404', sa.TEXT(), nullable=True),
    sa.Column('average_flow_year_1405', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_1399_farvardin', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_1399_ordibehesht', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_1399_khordad', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_1399_tir', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_1399_mordad', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_1399_shahrivar', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_1399_mehr', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_1399_aban', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_1399_azar', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_1399_dey', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_1399_bahman', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_1399_esfand', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_1400_farvardin', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_1400_ordibehesht', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_1400_khordad', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_1400_tir', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_1400_mordad', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_1400_shahrivar', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_1400_mehr', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_1400_aban', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_1400_azar', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_1400_dey', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_1400_bahman', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_1400_esfand', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_1401_farvardin', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_1401_ordibehesht', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_1401_khordad', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_1401_tir', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_1401_mordad', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_1401_shahrivar', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_1401_mehr', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_1401_aban', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_1401_azar', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_1401_dey', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_1401_bahman', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_1401_esfand', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_1402_farvardin', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_1402_ordibehesht', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_1402_khordad', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_1402_tir', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_1402_mordad', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_1402_shahrivar', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_1402_mehr', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_1402_aban', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_1402_azar', sa.REAL(), nullable=True),
    sa.Column('average_flow_1402_dey', sa.REAL(), nullable=True),
    sa.Column('average_flow_1402_bahman', sa.REAL(), nullable=True),
    sa.Column('average_flow_1402_esfand', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_1403_farvardin', sa.REAL(), nullable=True),
    sa.Column('average_flow_1403_ordibehesht', sa.REAL(), nullable=True),
    sa.Column('average_flow_1403_khordad', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_1403_tir', sa.REAL(), nullable=True),
    sa.Column('average_flow_1403_mordad', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_1403_shahrivar', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_1403_mehr', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_1403_aban', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_1403_azar', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_1403_dey', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_1403_bahman', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_1403_esfand', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_1404_farvardin', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_1404_ordibehesht', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_1404_khordad', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_1404_tir', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_1404_mordad', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_1404_shahrivar', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_1404_mehr', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_1404_aban', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_1404_azar', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_1404_dey', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_1404_bahman', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_1404_esfand', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_1405_farvardin', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_1405_ordibehesht', sa.INTEGER(), nullable=True),
    sa.Column('average_flow_year_1400_vs_1399', sa.REAL(), nullable=True),
    sa.Column('average_flow_year_1401_vs_1399', sa.REAL(), nullable=True),
    sa.Column('average_flow_year_1402_vs_1399', sa.REAL(), nullable=True),
    sa.Column('average_flow_year_1403_vs_1399', sa.REAL(), nullable=True),
    sa.Column('average_flow_year_1404_vs_1399', sa.REAL(), nullable=True)]
    )
    with op.batch_alter_table('well_permit_events', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_well_permit_events_well_id'))
        batch_op.drop_index(batch_op.f('ix_well_permit_events_status'))
        batch_op.drop_index(batch_op.f('ix_well_permit_events_source'))
        batch_op.drop_index(batch_op.f('ix_well_permit_events_expiry_date'))

    op.drop_table('well_permit_events')
    # ### end Alembic commands ###



################################################################################
# FILE: 85915671e942_mechanic_events_table.py
################################################################################

"""mechanic events table

Revision ID: 85915671e942
Revises: 7aa4c86e912d
Create Date: 2026-07-05 13:34:34.591283

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '85915671e942'
down_revision = '7aa4c86e912d'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('mechanic_events',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('well_id', sa.Integer(), nullable=False),
    sa.Column('op_date', sa.Date(), nullable=True),
    sa.Column('op_type', sa.String(length=40), nullable=True),
    sa.Column('fault_description', sa.Text(), nullable=True),
    sa.Column('contractor', sa.String(length=120), nullable=True),
    sa.Column('pm_form_no', sa.String(length=60), nullable=True),
    sa.Column('motor_desc', sa.String(length=200), nullable=True),
    sa.Column('motor_condition', sa.String(length=40), nullable=True),
    sa.Column('pump_desc', sa.String(length=200), nullable=True),
    sa.Column('pump_condition', sa.String(length=40), nullable=True),
    sa.Column('tip_change', sa.String(length=60), nullable=True),
    sa.Column('prev_install_date', sa.Date(), nullable=True),
    sa.Column('well_depth', sa.Float(), nullable=True),
    sa.Column('prev_install_depth', sa.Float(), nullable=True),
    sa.Column('curr_install_depth', sa.Float(), nullable=True),
    sa.Column('static_level', sa.Float(), nullable=True),
    sa.Column('dynamic_level', sa.Float(), nullable=True),
    sa.Column('path_loss', sa.Float(), nullable=True),
    sa.Column('network_pressure', sa.Float(), nullable=True),
    sa.Column('total_head', sa.Float(), nullable=True),
    sa.Column('design_flow', sa.Float(), nullable=True),
    sa.Column('pipe_diameter', sa.Float(), nullable=True),
    sa.Column('pt_date', sa.Date(), nullable=True),
    sa.Column('pt_pressure', sa.Float(), nullable=True),
    sa.Column('pt_flow', sa.Float(), nullable=True),
    sa.Column('cable_size', sa.String(length=40), nullable=True),
    sa.Column('cable_change', sa.String(length=60), nullable=True),
    sa.Column('starter', sa.String(length=60), nullable=True),
    sa.Column('months_worked', sa.Integer(), nullable=True),
    sa.Column('mechanic_opinion', sa.Text(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('source', sa.String(length=40), nullable=True),
    sa.Column('created_by_id', sa.Integer(), nullable=True),
    sa.Column('updated_by_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('submitted_at', sa.DateTime(), nullable=True),
    sa.Column('approved_at', sa.DateTime(), nullable=True),
    sa.Column('reject_reason', sa.Text(), nullable=True),
    sa.Column('submitted_by_id', sa.Integer(), nullable=True),
    sa.Column('approved_by_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['approved_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['submitted_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['well_id'], ['wells.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('mechanic_events', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_mechanic_events_op_date'), ['op_date'], unique=False)
        batch_op.create_index(batch_op.f('ix_mechanic_events_source'), ['source'], unique=False)
        batch_op.create_index(batch_op.f('ix_mechanic_events_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_mechanic_events_well_id'), ['well_id'], unique=False)

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('mechanic_events', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_mechanic_events_well_id'))
        batch_op.drop_index(batch_op.f('ix_mechanic_events_status'))
        batch_op.drop_index(batch_op.f('ix_mechanic_events_source'))
        batch_op.drop_index(batch_op.f('ix_mechanic_events_op_date'))

    op.drop_table('mechanic_events')
    # ### end Alembic commands ###



################################################################################
# FILE: 8dab06b9fbe4_attachments_table.py
################################################################################

"""attachments table

Revision ID: 8dab06b9fbe4
Revises: 16d3cb3c242c
Create Date: 2026-06-22 17:43:13.086268

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8dab06b9fbe4'
down_revision = '16d3cb3c242c'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('attachments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('entity_type', sa.String(length=30), nullable=False),
    sa.Column('entity_id', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=True),
    sa.Column('kind', sa.String(length=20), nullable=True),
    sa.Column('original_name', sa.String(length=255), nullable=False),
    sa.Column('stored_name', sa.String(length=80), nullable=False),
    sa.Column('content_type', sa.String(length=100), nullable=True),
    sa.Column('size_bytes', sa.Integer(), nullable=True),
    sa.Column('created_by_id', sa.Integer(), nullable=True),
    sa.Column('updated_by_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('stored_name')
    )
    with op.batch_alter_table('attachments', schema=None) as batch_op:
        batch_op.create_index('ix_attachment_entity', ['entity_type', 'entity_id'], unique=False)

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('attachments', schema=None) as batch_op:
        batch_op.drop_index('ix_attachment_entity')

    op.drop_table('attachments')
    # ### end Alembic commands ###



################################################################################
# FILE: 937d9d8c1fdf_phase1_pump_tests_steps.py
################################################################################

"""phase1: pump_tests + steps

Revision ID: 937d9d8c1fdf
Revises: 3df9c24aed3f
Create Date: 2026-06-20 21:19:25.565674

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '937d9d8c1fdf'
down_revision = '3df9c24aed3f'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('pump_tests',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('well_id', sa.Integer(), nullable=False),
    sa.Column('test_date', sa.Date(), nullable=True),
    sa.Column('test_type', sa.String(length=20), nullable=True),
    sa.Column('duration_h', sa.Float(), nullable=True),
    sa.Column('contractor', sa.String(length=120), nullable=True),
    sa.Column('consultant', sa.String(length=120), nullable=True),
    sa.Column('employer', sa.String(length=120), nullable=True),
    sa.Column('contract_no', sa.String(length=40), nullable=True),
    sa.Column('project_title', sa.String(length=255), nullable=True),
    sa.Column('static_level', sa.Float(), nullable=True),
    sa.Column('max_dynamic_level', sa.Float(), nullable=True),
    sa.Column('max_drawdown', sa.Float(), nullable=True),
    sa.Column('max_yield_lps', sa.Float(), nullable=True),
    sa.Column('coeff_a', sa.Float(), nullable=True),
    sa.Column('coeff_b', sa.Float(), nullable=True),
    sa.Column('proposed_discharge_lps', sa.Float(), nullable=True),
    sa.Column('proposed_install_depth_m', sa.Float(), nullable=True),
    sa.Column('resulting_drawdown_m', sa.Float(), nullable=True),
    sa.Column('motor_type', sa.String(length=60), nullable=True),
    sa.Column('motor_power_hp', sa.Float(), nullable=True),
    sa.Column('gearbox_power_hp', sa.Float(), nullable=True),
    sa.Column('gearbox_ratio', sa.String(length=20), nullable=True),
    sa.Column('pump_type', sa.String(length=80), nullable=True),
    sa.Column('pump_stages', sa.Integer(), nullable=True),
    sa.Column('pump_diameter_in', sa.Float(), nullable=True),
    sa.Column('max_rpm', sa.Float(), nullable=True),
    sa.Column('discharge_pipe_diameter_in', sa.Float(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('source', sa.String(length=40), nullable=True),
    sa.Column('created_by_id', sa.Integer(), nullable=True),
    sa.Column('updated_by_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('submitted_at', sa.DateTime(), nullable=True),
    sa.Column('approved_at', sa.DateTime(), nullable=True),
    sa.Column('reject_reason', sa.Text(), nullable=True),
    sa.Column('submitted_by_id', sa.Integer(), nullable=True),
    sa.Column('approved_by_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['approved_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['submitted_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['well_id'], ['wells.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('pump_tests', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_pump_tests_source'), ['source'], unique=False)
        batch_op.create_index(batch_op.f('ix_pump_tests_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_pump_tests_test_date'), ['test_date'], unique=False)
        batch_op.create_index(batch_op.f('ix_pump_tests_well_id'), ['well_id'], unique=False)

    op.create_table('pump_test_steps',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('pump_test_id', sa.Integer(), nullable=False),
    sa.Column('step_no', sa.Integer(), nullable=True),
    sa.Column('rpm', sa.Float(), nullable=True),
    sa.Column('discharge_lps', sa.Float(), nullable=True),
    sa.Column('observed_drawdown', sa.Float(), nullable=True),
    sa.Column('calc_drawdown', sa.Float(), nullable=True),
    sa.Column('grid_loss', sa.Float(), nullable=True),
    sa.Column('aquifer_loss', sa.Float(), nullable=True),
    sa.Column('efficiency', sa.Float(), nullable=True),
    sa.ForeignKeyConstraint(['pump_test_id'], ['pump_tests.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('pump_test_steps', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_pump_test_steps_pump_test_id'), ['pump_test_id'], unique=False)

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('pump_test_steps', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_pump_test_steps_pump_test_id'))

    op.drop_table('pump_test_steps')
    with op.batch_alter_table('pump_tests', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_pump_tests_well_id'))
        batch_op.drop_index(batch_op.f('ix_pump_tests_test_date'))
        batch_op.drop_index(batch_op.f('ix_pump_tests_status'))
        batch_op.drop_index(batch_op.f('ix_pump_tests_source'))

    op.drop_table('pump_tests')
    # ### end Alembic commands ###



################################################################################
# FILE: 96acb5369f2c_well_destination_reservoir.py
################################################################################

"""well destination_reservoir

Revision ID: 96acb5369f2c
Revises: 8dab06b9fbe4
Create Date: 2026-06-22 18:29:25.045633

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '96acb5369f2c'
down_revision = '8dab06b9fbe4'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('wells', schema=None) as batch_op:
        batch_op.add_column(sa.Column('destination_reservoir', sa.String(length=40), nullable=True))

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('wells', schema=None) as batch_op:
        batch_op.drop_column('destination_reservoir')

    # ### end Alembic commands ###



################################################################################
# FILE: a2e993f9396d_wells_add_match_key.py
################################################################################

"""wells: add match_key

Revision ID: a2e993f9396d
Revises: fe1e02f7dbb9
Create Date: 2026-06-20 18:23:50.148685

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a2e993f9396d'
down_revision = 'fe1e02f7dbb9'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('_alembic_tmp_wells')
    with op.batch_alter_table('wells', schema=None) as batch_op:
        batch_op.add_column(sa.Column('match_key', sa.String(length=120), nullable=True))
        batch_op.create_index(batch_op.f('ix_wells_match_key'), ['match_key'], unique=False)

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('wells', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_wells_match_key'))
        batch_op.drop_column('match_key')

    op.create_table('_alembic_tmp_wells',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('pm_code', sa.VARCHAR(length=40), nullable=True),
    sa.Column('name', sa.VARCHAR(length=120), nullable=False),
    sa.Column('office_id', sa.INTEGER(), nullable=True),
    sa.Column('center_id', sa.INTEGER(), nullable=True),
    sa.Column('zone', sa.VARCHAR(length=40), nullable=True),
    sa.Column('sub_zone', sa.VARCHAR(length=40), nullable=True),
    sa.Column('well_kind', sa.VARCHAR(length=10), nullable=True),
    sa.Column('utm_x', sa.FLOAT(), nullable=True),
    sa.Column('utm_y', sa.FLOAT(), nullable=True),
    sa.Column('utm_zone', sa.VARCHAR(length=8), nullable=True),
    sa.Column('latitude', sa.FLOAT(), nullable=True),
    sa.Column('longitude', sa.FLOAT(), nullable=True),
    sa.Column('ground_elevation', sa.FLOAT(), nullable=True),
    sa.Column('drill_year', sa.VARCHAR(length=8), nullable=True),
    sa.Column('location_status', sa.VARCHAR(length=20), nullable=True),
    sa.Column('status', sa.VARCHAR(length=20), nullable=True),
    sa.Column('parent_well_id', sa.INTEGER(), nullable=True),
    sa.Column('notes', sa.TEXT(), nullable=True),
    sa.Column('created_by_id', sa.INTEGER(), nullable=True),
    sa.Column('updated_by_id', sa.INTEGER(), nullable=True),
    sa.Column('created_at', sa.DATETIME(), nullable=False),
    sa.Column('updated_at', sa.DATETIME(), nullable=False),
    sa.Column('construction_type', sa.VARCHAR(length=20), nullable=True),
    sa.Column('match_key', sa.VARCHAR(length=120), nullable=True),
    sa.ForeignKeyConstraint(['center_id'], ['org_units.id'], ),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['office_id'], ['org_units.id'], ),
    sa.ForeignKeyConstraint(['parent_well_id'], ['wells.id'], ),
    sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    # ### end Alembic commands ###



################################################################################
# FILE: a333b59b1a36_initial_schema_rbac_org_wells.py
################################################################################

"""initial schema: rbac, org, wells

Revision ID: a333b59b1a36
Revises: 
Create Date: 2026-06-20 00:14:26.893104

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a333b59b1a36'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('org_units',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('code', sa.String(length=40), nullable=True),
    sa.Column('unit_type', sa.String(length=20), nullable=False),
    sa.Column('parent_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['parent_id'], ['org_units.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('org_units', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_org_units_code'), ['code'], unique=False)

    op.create_table('permissions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('code', sa.String(length=60), nullable=False),
    sa.Column('module', sa.String(length=40), nullable=False),
    sa.Column('action', sa.String(length=20), nullable=False),
    sa.Column('description', sa.String(length=120), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('permissions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_permissions_code'), ['code'], unique=True)
        batch_op.create_index(batch_op.f('ix_permissions_module'), ['module'], unique=False)

    op.create_table('roles',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=60), nullable=False),
    sa.Column('description', sa.String(length=160), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_table('role_permissions',
    sa.Column('role_id', sa.Integer(), nullable=False),
    sa.Column('permission_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['permission_id'], ['permissions.id'], ),
    sa.ForeignKeyConstraint(['role_id'], ['roles.id'], ),
    sa.PrimaryKeyConstraint('role_id', 'permission_id')
    )
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('username', sa.String(length=60), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('full_name', sa.String(length=120), nullable=True),
    sa.Column('email', sa.String(length=120), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('is_superuser', sa.Boolean(), nullable=False),
    sa.Column('org_unit_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['org_unit_id'], ['org_units.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_users_username'), ['username'], unique=True)

    op.create_table('user_roles',
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('role_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['role_id'], ['roles.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('user_id', 'role_id')
    )
    op.create_table('wells',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('pm_code', sa.String(length=40), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('office_id', sa.Integer(), nullable=True),
    sa.Column('center_id', sa.Integer(), nullable=True),
    sa.Column('zone', sa.String(length=40), nullable=True),
    sa.Column('sub_zone', sa.String(length=40), nullable=True),
    sa.Column('well_kind', sa.String(length=10), nullable=True),
    sa.Column('utm_x', sa.Float(), nullable=True),
    sa.Column('utm_y', sa.Float(), nullable=True),
    sa.Column('utm_zone', sa.String(length=8), nullable=True),
    sa.Column('latitude', sa.Float(), nullable=True),
    sa.Column('longitude', sa.Float(), nullable=True),
    sa.Column('ground_elevation', sa.Float(), nullable=True),
    sa.Column('drill_year', sa.String(length=8), nullable=True),
    sa.Column('location_status', sa.String(length=20), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=True),
    sa.Column('parent_well_id', sa.Integer(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_by_id', sa.Integer(), nullable=True),
    sa.Column('updated_by_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['center_id'], ['org_units.id'], ),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['office_id'], ['org_units.id'], ),
    sa.ForeignKeyConstraint(['parent_well_id'], ['wells.id'], ),
    sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('wells', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_wells_pm_code'), ['pm_code'], unique=True)
        batch_op.create_index(batch_op.f('ix_wells_status'), ['status'], unique=False)

    op.create_table('well_identifiers',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('well_id', sa.Integer(), nullable=False),
    sa.Column('id_type', sa.String(length=30), nullable=False),
    sa.Column('value', sa.String(length=80), nullable=False),
    sa.Column('valid_from', sa.String(length=12), nullable=True),
    sa.Column('valid_to', sa.String(length=12), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['well_id'], ['wells.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('well_identifiers')
    with op.batch_alter_table('wells', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_wells_status'))
        batch_op.drop_index(batch_op.f('ix_wells_pm_code'))

    op.drop_table('wells')
    op.drop_table('user_roles')
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_users_username'))

    op.drop_table('users')
    op.drop_table('role_permissions')
    op.drop_table('roles')
    with op.batch_alter_table('permissions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_permissions_module'))
        batch_op.drop_index(batch_op.f('ix_permissions_code'))

    op.drop_table('permissions')
    with op.batch_alter_table('org_units', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_org_units_code'))

    op.drop_table('org_units')
    # ### end Alembic commands ###



################################################################################
# FILE: a722e7d8c342_economic_params.py
################################################################################

"""economic_params

Revision ID: a722e7d8c342
Revises: 96acb5369f2c
Create Date: 2026-06-22 22:21:35.511380

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a722e7d8c342'
down_revision = '96acb5369f2c'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('economic_params',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('key', sa.String(length=50), nullable=False),
    sa.Column('value', sa.Float(), nullable=False),
    sa.Column('label', sa.String(length=120), nullable=False),
    sa.Column('unit', sa.String(length=40), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('economic_params', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_economic_params_key'), ['key'], unique=True)

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('economic_params', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_economic_params_key'))

    op.drop_table('economic_params')
    # ### end Alembic commands ###



################################################################################
# FILE: bffe7095945b_well_technical_table.py
################################################################################

"""well_technical table

Revision ID: bffe7095945b
Revises: fd402254f590
Create Date: 2026-06-22 15:59:55.690499

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'bffe7095945b'
down_revision = 'fd402254f590'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('well_technical',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('well_id', sa.Integer(), nullable=False),
    sa.Column('last_flowtest_discharge', sa.Float(), nullable=True),
    sa.Column('last_flowtest_pressure', sa.Float(), nullable=True),
    sa.Column('last_flowtest_date', sa.Date(), nullable=True),
    sa.Column('meter_status', sa.String(length=40), nullable=True),
    sa.Column('meter_brand', sa.String(length=60), nullable=True),
    sa.Column('klasse', sa.String(length=40), nullable=True),
    sa.Column('geo_position', sa.String(length=120), nullable=True),
    sa.Column('casing_material', sa.String(length=40), nullable=True),
    sa.Column('discharge_pipe_size', sa.String(length=20), nullable=True),
    sa.Column('drill_depth_m', sa.Float(), nullable=True),
    sa.Column('install_depth_m', sa.Float(), nullable=True),
    sa.Column('prev_discharge_lps', sa.Float(), nullable=True),
    sa.Column('last_drill_year', sa.String(length=8), nullable=True),
    sa.Column('source', sa.String(length=40), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['well_id'], ['wells.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('well_technical', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_well_technical_source'), ['source'], unique=False)
        batch_op.create_index(batch_op.f('ix_well_technical_well_id'), ['well_id'], unique=True)

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('well_technical', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_well_technical_well_id'))
        batch_op.drop_index(batch_op.f('ix_well_technical_source'))

    op.drop_table('well_technical')
    # ### end Alembic commands ###



################################################################################
# FILE: c60a88fed047_mechanic_parts_table.py
################################################################################

"""mechanic parts table

Revision ID: c60a88fed047
Revises: 85915671e942
Create Date: 2026-07-05 18:23:53.271157

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c60a88fed047'
down_revision = '85915671e942'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('mechanic_parts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('equipment', sa.String(length=20), nullable=True),
    sa.Column('part_name', sa.String(length=200), nullable=False),
    sa.Column('total_count', sa.Integer(), nullable=True),
    sa.Column('usable', sa.Integer(), nullable=True),
    sa.Column('scrap', sa.Integer(), nullable=True),
    sa.Column('new_count', sa.Integer(), nullable=True),
    sa.Column('repaired', sa.Integer(), nullable=True),
    sa.Column('notes', sa.String(length=300), nullable=True),
    sa.Column('created_by_id', sa.Integer(), nullable=True),
    sa.Column('updated_by_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('mechanic_parts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_mechanic_parts_equipment'), ['equipment'], unique=False)

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('mechanic_parts', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_mechanic_parts_equipment'))

    op.drop_table('mechanic_parts')
    # ### end Alembic commands ###



################################################################################
# FILE: e9e1169d4b8b_add_drilling_source.py
################################################################################

"""add drilling.source

Revision ID: e9e1169d4b8b
Revises: 017b9513547c
Create Date: 2026-06-20 16:34:29.059721

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e9e1169d4b8b'
down_revision = '017b9513547c'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('drilling', schema=None) as batch_op:
        batch_op.add_column(sa.Column('source', sa.String(length=40), nullable=True))
        batch_op.create_index(batch_op.f('ix_drilling_source'), ['source'], unique=False)

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('drilling', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_drilling_source'))
        batch_op.drop_column('source')

    # ### end Alembic commands ###



################################################################################
# FILE: eafc68d55b74_finance_statements_and_items.py
################################################################################

"""finance statements and items

Revision ID: eafc68d55b74
Revises: 3fcc112dd4e8
Create Date: 2026-07-06 23:50:06.278995

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'eafc68d55b74'
down_revision = '3fcc112dd4e8'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('finance_statements',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('well_id', sa.Integer(), nullable=True),
    sa.Column('op_type', sa.String(length=60), nullable=True),
    sa.Column('contractor', sa.String(length=120), nullable=True),
    sa.Column('contract_no', sa.String(length=60), nullable=True),
    sa.Column('statement_no', sa.String(length=60), nullable=True),
    sa.Column('statement_kind', sa.String(length=40), nullable=True),
    sa.Column('statement_date', sa.Date(), nullable=True),
    sa.Column('coef_region', sa.Float(), nullable=True),
    sa.Column('coef_overhead', sa.Float(), nullable=True),
    sa.Column('coef_contract', sa.Float(), nullable=True),
    sa.Column('workshop_setup', sa.Float(), nullable=True),
    sa.Column('total_before', sa.Float(), nullable=True),
    sa.Column('total_after', sa.Float(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('source', sa.String(length=40), nullable=True),
    sa.Column('created_by_id', sa.Integer(), nullable=True),
    sa.Column('updated_by_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('submitted_at', sa.DateTime(), nullable=True),
    sa.Column('approved_at', sa.DateTime(), nullable=True),
    sa.Column('reject_reason', sa.Text(), nullable=True),
    sa.Column('submitted_by_id', sa.Integer(), nullable=True),
    sa.Column('approved_by_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['approved_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['submitted_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['well_id'], ['wells.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('finance_statements', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_finance_statements_op_type'), ['op_type'], unique=False)
        batch_op.create_index(batch_op.f('ix_finance_statements_source'), ['source'], unique=False)
        batch_op.create_index(batch_op.f('ix_finance_statements_statement_date'), ['statement_date'], unique=False)
        batch_op.create_index(batch_op.f('ix_finance_statements_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_finance_statements_well_id'), ['well_id'], unique=False)

    op.create_table('finance_items',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('statement_id', sa.Integer(), nullable=False),
    sa.Column('category', sa.String(length=120), nullable=True),
    sa.Column('row_no', sa.String(length=20), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('unit', sa.String(length=40), nullable=True),
    sa.Column('contract_qty', sa.Float(), nullable=True),
    sa.Column('quantity', sa.Float(), nullable=True),
    sa.Column('unit_price', sa.Float(), nullable=True),
    sa.Column('coefficient', sa.Float(), nullable=True),
    sa.Column('total_amount', sa.Float(), nullable=True),
    sa.Column('created_by_id', sa.Integer(), nullable=True),
    sa.Column('updated_by_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['statement_id'], ['finance_statements.id'], ),
    sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('finance_items', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_finance_items_statement_id'), ['statement_id'], unique=False)

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('finance_items', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_finance_items_statement_id'))

    op.drop_table('finance_items')
    with op.batch_alter_table('finance_statements', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_finance_statements_well_id'))
        batch_op.drop_index(batch_op.f('ix_finance_statements_status'))
        batch_op.drop_index(batch_op.f('ix_finance_statements_statement_date'))
        batch_op.drop_index(batch_op.f('ix_finance_statements_source'))
        batch_op.drop_index(batch_op.f('ix_finance_statements_op_type'))

    op.drop_table('finance_statements')
    # ### end Alembic commands ###



################################################################################
# FILE: f3469902de33_monthly_production_energy_columns.py
################################################################################

"""monthly_production energy columns

Revision ID: f3469902de33
Revises: bffe7095945b
Create Date: 2026-06-22 16:34:06.014322

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f3469902de33'
down_revision = 'bffe7095945b'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('monthly_production', schema=None) as batch_op:
        batch_op.add_column(sa.Column('energy_kwh', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('energy_cost_rial', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('contract_power_kw', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('consumed_power_kw', sa.Float(), nullable=True))

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('monthly_production', schema=None) as batch_op:
        batch_op.drop_column('consumed_power_kw')
        batch_op.drop_column('contract_power_kw')
        batch_op.drop_column('energy_cost_rial')
        batch_op.drop_column('energy_kwh')

    # ### end Alembic commands ###



################################################################################
# FILE: fd402254f590_maintenance_records_table.py
################################################################################

"""maintenance_records table

Revision ID: fd402254f590
Revises: 7228c6b17e6b
Create Date: 2026-06-22 15:51:57.531479

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'fd402254f590'
down_revision = '7228c6b17e6b'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('maintenance_records',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('well_id', sa.Integer(), nullable=False),
    sa.Column('pump_installation_id', sa.Integer(), nullable=True),
    sa.Column('report_date', sa.Date(), nullable=True),
    sa.Column('maint_type', sa.String(length=20), nullable=True),
    sa.Column('category', sa.String(length=20), nullable=True),
    sa.Column('down_from', sa.Date(), nullable=True),
    sa.Column('down_to', sa.Date(), nullable=True),
    sa.Column('downtime_hours', sa.Float(), nullable=True),
    sa.Column('fault_desc', sa.Text(), nullable=True),
    sa.Column('action_taken', sa.Text(), nullable=True),
    sa.Column('parts_replaced', sa.String(length=200), nullable=True),
    sa.Column('contractor_id', sa.Integer(), nullable=True),
    sa.Column('cost', sa.Float(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('source', sa.String(length=40), nullable=True),
    sa.Column('created_by_id', sa.Integer(), nullable=True),
    sa.Column('updated_by_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('submitted_at', sa.DateTime(), nullable=True),
    sa.Column('approved_at', sa.DateTime(), nullable=True),
    sa.Column('reject_reason', sa.Text(), nullable=True),
    sa.Column('submitted_by_id', sa.Integer(), nullable=True),
    sa.Column('approved_by_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['approved_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['contractor_id'], ['suppliers.id'], ),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['pump_installation_id'], ['pump_installations.id'], ),
    sa.ForeignKeyConstraint(['submitted_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['well_id'], ['wells.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('maintenance_records', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_maintenance_records_report_date'), ['report_date'], unique=False)
        batch_op.create_index(batch_op.f('ix_maintenance_records_source'), ['source'], unique=False)
        batch_op.create_index(batch_op.f('ix_maintenance_records_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_maintenance_records_well_id'), ['well_id'], unique=False)

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('maintenance_records', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_maintenance_records_well_id'))
        batch_op.drop_index(batch_op.f('ix_maintenance_records_status'))
        batch_op.drop_index(batch_op.f('ix_maintenance_records_source'))
        batch_op.drop_index(batch_op.f('ix_maintenance_records_report_date'))

    op.drop_table('maintenance_records')
    # ### end Alembic commands ###



################################################################################
# FILE: fe1e02f7dbb9_phase1_flow_tests_flow_test_points.py
################################################################################

"""phase1: flow_tests + flow_test_points

Revision ID: fe1e02f7dbb9
Revises: e9e1169d4b8b
Create Date: 2026-06-20 16:58:31.872470

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'fe1e02f7dbb9'
down_revision = 'e9e1169d4b8b'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('flow_tests',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('well_id', sa.Integer(), nullable=False),
    sa.Column('test_date', sa.Date(), nullable=True),
    sa.Column('test_reason', sa.String(length=60), nullable=True),
    sa.Column('network_type', sa.String(length=30), nullable=True),
    sa.Column('electropump_type', sa.String(length=40), nullable=True),
    sa.Column('electropump_type_prev', sa.String(length=40), nullable=True),
    sa.Column('install_date', sa.Date(), nullable=True),
    sa.Column('install_depth', sa.Float(), nullable=True),
    sa.Column('well_depth', sa.Float(), nullable=True),
    sa.Column('construction_type', sa.String(length=20), nullable=True),
    sa.Column('allowed_q', sa.Float(), nullable=True),
    sa.Column('design_q', sa.Float(), nullable=True),
    sa.Column('license_q', sa.Float(), nullable=True),
    sa.Column('power_subscription', sa.String(length=40), nullable=True),
    sa.Column('static_level', sa.Float(), nullable=True),
    sa.Column('static_level_prev', sa.Float(), nullable=True),
    sa.Column('last_rehab_date', sa.Date(), nullable=True),
    sa.Column('pull_reason', sa.String(length=80), nullable=True),
    sa.Column('meter_status', sa.String(length=60), nullable=True),
    sa.Column('meter_brand', sa.String(length=60), nullable=True),
    sa.Column('starter_type', sa.String(length=40), nullable=True),
    sa.Column('capacitor_capacity', sa.Float(), nullable=True),
    sa.Column('voltage_on', sa.String(length=20), nullable=True),
    sa.Column('voltage_off', sa.String(length=20), nullable=True),
    sa.Column('ohm_ff', sa.String(length=20), nullable=True),
    sa.Column('ohm_fg', sa.String(length=20), nullable=True),
    sa.Column('line_pressure', sa.Float(), nullable=True),
    sa.Column('regulated_pressure', sa.String(length=20), nullable=True),
    sa.Column('discharge_volume_m3', sa.Float(), nullable=True),
    sa.Column('expert_note', sa.Text(), nullable=True),
    sa.Column('created_by_id', sa.Integer(), nullable=True),
    sa.Column('updated_by_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('submitted_at', sa.DateTime(), nullable=True),
    sa.Column('approved_at', sa.DateTime(), nullable=True),
    sa.Column('reject_reason', sa.Text(), nullable=True),
    sa.Column('submitted_by_id', sa.Integer(), nullable=True),
    sa.Column('approved_by_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['approved_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['submitted_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['well_id'], ['wells.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('flow_tests', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_flow_tests_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_flow_tests_test_date'), ['test_date'], unique=False)
        batch_op.create_index(batch_op.f('ix_flow_tests_well_id'), ['well_id'], unique=False)

    op.create_table('flow_test_points',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('flow_test_id', sa.Integer(), nullable=False),
    sa.Column('operating_no', sa.Integer(), nullable=True),
    sa.Column('operating_type', sa.String(length=30), nullable=True),
    sa.Column('discharge_m3h', sa.Float(), nullable=True),
    sa.Column('discharge_lps', sa.Float(), nullable=True),
    sa.Column('head_m', sa.Float(), nullable=True),
    sa.Column('drawdown_m', sa.Float(), nullable=True),
    sa.Column('dynamic_level_m', sa.Float(), nullable=True),
    sa.Column('pressure_atm', sa.Float(), nullable=True),
    sa.Column('water_column_m', sa.Float(), nullable=True),
    sa.Column('water_column_change', sa.Float(), nullable=True),
    sa.Column('amperes', sa.String(length=40), nullable=True),
    sa.Column('efficiency', sa.Float(), nullable=True),
    sa.Column('cos_phi', sa.Float(), nullable=True),
    sa.Column('active_power_kw', sa.Float(), nullable=True),
    sa.Column('reactive_power_kvar', sa.Float(), nullable=True),
    sa.Column('apparent_power_kva', sa.Float(), nullable=True),
    sa.Column('mechanical_power_kw', sa.Float(), nullable=True),
    sa.Column('energy_intensity_kwh_m3', sa.Float(), nullable=True),
    sa.ForeignKeyConstraint(['flow_test_id'], ['flow_tests.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('flow_test_points', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_flow_test_points_flow_test_id'), ['flow_test_id'], unique=False)

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('flow_test_points', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_flow_test_points_flow_test_id'))

    op.drop_table('flow_test_points')
    with op.batch_alter_table('flow_tests', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_flow_tests_well_id'))
        batch_op.drop_index(batch_op.f('ix_flow_tests_test_date'))
        batch_op.drop_index(batch_op.f('ix_flow_tests_status'))

    op.drop_table('flow_tests')
    # ### end Alembic commands ###


