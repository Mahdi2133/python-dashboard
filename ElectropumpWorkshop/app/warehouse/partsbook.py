"""The mechanical workshop's parts workbook, into warehouse.db.

«فرم قطعات و تجهیزات کارگاه مکانیک» carries, sheet by sheet:
  فهرست قطعات   — every part of the submersible motor and pump, with its
                  warehouse code (کد انباری) → the item catalogue
  تجهیزات       — every motor/pump by equipment code (EM/…, MP/…) → the register
  خلاصه عملکرد قطعات مورد استفاده — each part installed in or collected from
                  an equipment since 1398 → the part-action history
  لیست‌ها        — the drop-down lists (part names and codes)
Re-importing replaces the history rows and updates items and equipment in
place; the parts forms of the process keep their own rows.
"""
from __future__ import annotations

import hashlib
import io

from ..extensions import db
from ..refdata.textnorm import jdate_num, norm_label, norm_text, to_jdate, to_text
from .models import WhEquipment, WhItem, WhPartAction

MONTHS = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر",
          "دی", "بهمن", "اسفند"]


def _sheet(wb, *names):
    for ws in wb.worksheets:
        t = norm_label(ws.title)
        if any(t.startswith(norm_label(n)) for n in names):
            return ws
    return None


def _code(v):
    t = to_text(v)
    return t.strip() if t else None


def import_partsbook(data: bytes) -> dict:
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    out = {"items_added": 0, "items_updated": 0, "equipment": 0, "history": 0}
    sha1 = hashlib.sha1(data).hexdigest()

    # ── items: فهرست قطعات (+ names/codes of لیست‌ها) ─────────────────────
    ws = _sheet(wb, "فهرست قطعات")
    if ws is None:
        raise ValueError("برگه‌ی «فهرست قطعات» در فایل نیست.")
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    hdr = next(i for i, r in enumerate(rows[:10])
               if any(isinstance(v, str) and norm_label(v) == "کد انباری" for v in r))
    head = [norm_label(v) if isinstance(v, str) else "" for v in rows[hdr]]
    c_kind, c_code, c_name = head.index("تجهیز"), head.index("کد انباری"), head.index("شرح قطعه")
    seen_codes = set()
    order = 0
    for r in rows[hdr + 1:]:
        code, name = _code(r[c_code]), to_text(r[c_name])
        if not code or not name:
            continue
        kind_name = norm_text(r[c_kind]) if r[c_kind] else None
        key = (code, kind_name)
        if key in seen_codes:
            continue
        seen_codes.add(key)
        order += 1
        item = WhItem.query.filter_by(code=_item_code(code, kind_name)).first()
        if item is None:
            item = WhItem(code=_item_code(code, kind_name))
            db.session.add(item)
            out["items_added"] += 1
        else:
            out["items_updated"] += 1
        item.name = norm_text(name)
        item.kind = "part"
        item.category = kind_name
        item.unit = item.unit or "عدد"
        item.is_active = True
        item.sort_order = 100 + order
        item.source = "فرم قطعات کارگاه مکانیک"
        item.note = f"کد انباری {code}"
    # the proposed starter parts give way to the real catalogue
    for item in WhItem.query.filter_by(source="پیشنهادی", kind="part").all():
        item.is_active = False
    for code, name, kind in (("EQ-01", "الکتروموتور شناور", "الکتروموتور شناور"),
                             ("EQ-02", "پمپ شناور", "پمپ شناور"),
                             ("EQ-03", "الکتروپمپ کامل (مونتاژشده)", "الکتروپمپ")):
        item = WhItem.query.filter_by(code=code).first() or WhItem(code=code, sort_order=0)
        item.name, item.kind, item.category = name, "equipment", kind
        item.unit, item.is_active, item.source = "دستگاه", True, "پایه"
        db.session.add(item)

    # ── equipment register: تجهیزات ─────────────────────────────────────
    ws = _sheet(wb, "تجهیزات")
    if ws is not None:
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
        hdr = next((i for i, r in enumerate(rows[:10])
                    if any(isinstance(v, str) and norm_label(v) == "کد تجهیز" for v in r)), None)
        if hdr is not None:
            head = [norm_label(v) if isinstance(v, str) else "" for v in rows[hdr]]
            col = {k: head.index(k) for k in ("کد تجهیز", "نام تجهیز", "نوع تجهیز",
                                              "آخرین تاریخ اقدام", "کد تاسیس") if k in head}
            fac = next((i for i, h in enumerate(head) if h.startswith("تاسیس")), None)
            have = {e.code: e for e in WhEquipment.query.all()}
            for r in rows[hdr + 1:]:
                code = _code(r[col["کد تجهیز"]])
                if not code:
                    continue
                e = have.get(code)
                if e is None:
                    e = WhEquipment(code=code)
                    db.session.add(e)
                    have[code] = e
                e.name = to_text(r[col["نام تجهیز"]]) if "نام تجهیز" in col else e.name
                e.kind = to_text(r[col["نوع تجهیز"]]) if "نوع تجهیز" in col else e.kind
                e.last_date = to_jdate(r[col["آخرین تاریخ اقدام"]]) if "آخرین تاریخ اقدام" in col else e.last_date
                e.last_facility = to_text(r[fac]) if fac is not None else e.last_facility
                e.last_facility_code = to_text(r[col["کد تاسیس"]]) if "کد تاسیس" in col else None
                out["equipment"] += 1
    db.session.flush()

    # ── history: خلاصه عملکرد قطعات مورد استفاده ─────────────────────────
    ws = _sheet(wb, "خلاصه عملکرد قطعات")
    if ws is not None:
        rows = ws.iter_rows(values_only=True)
        head = [norm_label(v) if isinstance(v, str) else "" for v in next(rows)]

        def ix(*names):
            for n in names:
                nl = norm_label(n)
                if nl in head:
                    return head.index(nl)
            return None
        c = {k: ix(*v) for k, v in {
            "center": ["مرکز استقرار"], "fcode": ["کد تاسیس"], "fname": ["نام تاسیس"],
            "ecode": ["کد تجهیز"], "ekind": ["نوع تجهیز"], "ename": ["نام تجهیز"],
            "date": ["تاریخ اقدام"], "year": ["سال"], "month": ["ماه"],
            "related": ["اقدام مرتبط"], "activity": ["نوع فعالیت"],
            "failure": ["خرابی مشاهده شده"], "cause": ["علت خرابی"],
            "done": ["اقدام انجام شده"], "note": ["توضیحات"],
            "pact": ["اقدام در سطح قطعه"], "ptype": ["نوع قطعه"],
            "state": ["وضعیت نو/کهنه"], "reuse": ["آیا قطعه قابل استفاده مجدد است؟"],
            "pcode": ["کد انباری قطعه"], "pname": ["شرح کد انباری قطعه"],
            "property": ["شماره اموال"], "maker": ["سازنده قطعه"],
        }.items()}
        if c["pcode"] is None or c["pact"] is None:
            raise ValueError("ستون‌های «کد انباری قطعه» و «اقدام در سطح قطعه» در برگه‌ی سوابق نیست.")
        WhPartAction.query.filter_by(source="history").delete()
        get = lambda r, k: (r[c[k]] if c[k] is not None and c[k] < len(r) else None)  # noqa: E731
        batch = []
        for r in rows:
            pact = norm_text(get(r, "pact"))
            if not pact:
                continue
            date = to_jdate(get(r, "date"))
            month = get(r, "month")
            month_n = (MONTHS.index(norm_text(month)) + 1) if norm_text(month) in MONTHS else (
                int(date[5:7]) if date else None)
            reuse = norm_text(get(r, "reuse"))
            batch.append(WhPartAction(
                source="history", jdate=date, date_num=jdate_num(date),
                year=int(str(get(r, "year"))[:4]) if str(get(r, "year") or "")[:4].isdigit() else (
                    int(date[:4]) if date else None),
                month=month_n,
                facility_code=to_text(get(r, "fcode")), facility_name=to_text(get(r, "fname")),
                center=to_text(get(r, "center")),
                equipment_code=_code(get(r, "ecode")), equipment_kind=to_text(get(r, "ekind")),
                equipment_name=to_text(get(r, "ename")),
                related_action=to_text(get(r, "related")), activity=to_text(get(r, "activity")),
                failure=to_text(get(r, "failure")), cause=to_text(get(r, "cause")),
                action_done=to_text(get(r, "done")), note=to_text(get(r, "note")),
                part_action="installed" if "نصب" in pact else "collected",
                state=to_text(get(r, "state")),
                reusable=(True if reuse == "بلی" else False if reuse == "خیر" else None),
                part_code=_code(get(r, "pcode")), part_name=to_text(get(r, "pname")),
                part_type=to_text(get(r, "ptype")), qty=1))
            if len(batch) >= 2000:
                db.session.bulk_save_objects(batch)
                out["history"] += len(batch)
                batch = []
        if batch:
            db.session.bulk_save_objects(batch)
            out["history"] += len(batch)
    from ..models.meta import AppMeta  # noqa: F401  (main DB untouched)
    db.session.commit()
    out["sha1"] = sha1
    from ..analytics.catalogue import bump_data_version
    bump_data_version()
    return out


def _item_code(code, kind_name):
    """One item per part and equipment kind: «30218015» may be a motor part
    and a pump part both, so the pump's copy is «30218015-P»."""
    if kind_name and "پمپ" in kind_name and "الکتروموتور" not in kind_name:
        return f"{code}-P"
    return str(code)


def is_partsbook(data: bytes) -> bool:
    from openpyxl import load_workbook
    try:
        wb = load_workbook(io.BytesIO(data), read_only=True)
    except Exception:  # noqa: BLE001
        return False
    return _sheet(wb, "فهرست قطعات") is not None
