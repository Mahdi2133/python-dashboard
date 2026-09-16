# -*- coding: utf-8 -*-
"""End-to-end smoke test. Run with: python tools/smoke_test.py

Exercises every subsystem against a throwaway database so it can be run
before a release without touching instance/wells.db.
"""
import json
import os
import shutil
import sys
import tempfile
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASS, FAIL = [], []


def check(name, condition, detail=""):
    (PASS if condition else FAIL).append(name)
    print(f"  [{'OK ' if condition else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))


def _export_headers(client):
    """The column list the raw export produces, without downloading the file."""
    from app.routes.api_transfer import _export_columns
    return _export_columns()


def main():
    tmp = tempfile.mkdtemp(prefix="electropump_test_")
    db = os.path.join(tmp, "wells.db")
    from app import create_app
    app = create_app({"SQLALCHEMY_DATABASE_URI": f"sqlite:///{db}",
                      "WTF_CSRF_ENABLED": False})
    c = app.test_client()
    login = c.post("/api/login", json={"username": "admin", "password": "admin"})
    check("ورود مدیر پیش‌فرض", login.status_code == 200)

    print("\n— پایگاه داده و داده‌های مرجع —")
    sysinfo = c.get("/api/system").get_json()["data"]
    check("پایگاه داده ساخته و متصل شد", sysinfo["database"]["connected"])
    check("حالت WAL فعال است", sysinfo["database"]["journal_mode"] == "wal",
          sysinfo["database"]["journal_mode"])
    check("چاه‌ها از رفرنس درج شدند", sysinfo["counts"]["wells"] == 864,
          str(sysinfo["counts"]["wells"]))
    check("۲۱۳ گزینه درج شد", sysinfo["counts"]["lookup_items"] == 213,
          str(sysinfo["counts"]["lookup_items"]))
    check("۶۸ فیلد فرم درج شد", sysinfo["counts"]["form_fields"] == 68,
          str(sysinfo["counts"]["form_fields"]))

    print("\n— تقویم شمسی —")
    from app.services.jalali import (gregorian_to_jalali, is_leap_jalali,
                                     jalali_month_days, jalali_to_gregorian,
                                     parse_jalali)
    check("۱۴۰۴/۰۱/۰۱ = 2025-03-21",
          str(jalali_to_gregorian(1404, 1, 1)) == "2025-03-21")
    check("۱۴۰۳ کبیسه است و ۳۰ اسفند دارد",
          is_leap_jalali(1403) and jalali_month_days(1403, 12) == 30)
    bad = sum(1 for jy in range(1380, 1440) for jm in range(1, 13)
              for jd in range(1, jalali_month_days(jy, jm) + 1)
              if gregorian_to_jalali(jalali_to_gregorian(jy, jm, jd)) != (jy, jm, jd))
    check("رفت‌وبرگشت ۱۳۸۰ تا ۱۴۳۹ بدون خطا", bad == 0, f"{bad} mismatch")
    check("خواندن '99/01/01' → ۱۳۹۹", parse_jalali("99/01/01") == (1399, 1, 1))
    check("خواندن '400/01/06' → ۱۴۰۰", parse_jalali("400/01/06") == (1400, 1, 6))
    check("خواندن ارقام فارسی", parse_jalali("۱۴۰۵/۰۶/۲۲") == (1405, 6, 22))

    print("\n— چرخه‌ی رکورد —")
    payload = {"op_jdate": "1405/06/22", "well": "امام رضا 11", "center": "سوران",
               "operation": "نصب", "contractor": "جوادی", "motor_curr": "73",
               "pump_curr": "384", "pump_stages": 10, "design_flow": 31,
               "test_flow": 29.5, "failure": ["شولات", "اهم دار"],
               "workshop_opinion": ["شولاتی"], "desc_tags": ["ورود شولات"],
               "description": "smoke test"}
    r = c.post("/api/records", json=payload)
    check("ایجاد رکورد", r.status_code == 200)
    rec = r.get_json()["data"]
    rid = rec["id"]
    check("تاریخ میلادی محاسبه شد", rec["op_date"] == "2026-09-13", rec["op_date"])
    check("چندانتخابی‌ها به جدول تگ رفتند", sorted(rec["failure"]) == sorted(["شولات", "اهم دار"]))
    check("تیپ پمپ به‌عنوان مقدار (نه شناسه) ذخیره شد", rec["pump_curr"] == "384",
          str(rec["pump_curr"]))
    r = c.put(f"/api/records/{rid}", json={"description": "ویرایش شد"})
    check("ویرایش جزئی بدون ارسال دوباره‌ی تاریخ", r.status_code == 200)
    check("مقدار ویرایش‌شده خوانده شد",
          c.get(f"/api/records/{rid}").get_json()["data"]["description"] == "ویرایش شد")
    r = c.post("/api/records", json={"well": ""})
    check("اعتبارسنجی فرم خالی", r.status_code == 422 and r.get_json()["fields"])
    c.delete(f"/api/records/{rid}")
    check("حذف نرم (رکورد باقی می‌ماند)",
          c.get(f"/api/records/{rid}").get_json()["data"]["is_active"] is False)
    c.post(f"/api/records/{rid}/restore")
    check("بازیابی رکورد",
          c.get(f"/api/records/{rid}").get_json()["data"]["is_active"] is True)

    print("\n— نرمال‌سازی املا (نام مستعار) —")
    r = c.post("/api/records", json={**payload, "contractor": "سعدابادی",
                                     "executor": "پیمانی",
                                     "center": "منزل اباد", "starter": "سفت"})
    d = r.get_json()["data"]
    check("«سعدابادی» → «سعدآبادی»", d["contractor"] == "سعدآبادی", d["contractor"])
    check("«منزل اباد» → «منزل آباد»", d["center"] == "منزل آباد", d["center"])
    check("«سفت» → «سافت»", d["starter"] == "سافت", str(d["starter"]))
    c.delete(f"/api/records/{d['id']}?hard=1")

    print("\n— ورود از اکسل —")
    xls = os.environ.get("ELECTROPUMP_TEST_XLS")
    if xls and os.path.exists(xls):
        from app.services.importer import commit_import, preview
        with app.app_context():
            info = preview(xls, "1405", limit=1)
            mapped = sum(1 for v in info["mapping"].values() if v)
            check("تشخیص سرستون شیت ۱۴۰۵", mapped >= 45, f"{mapped} ستون")
            res = commit_import(xls, "1405", info["mapping"], info["data_start"],
                                dry_run=True, filename="test.xls")
            check("بررسی آزمایشی بدون خطا", res["failed"] == 0,
                  f"ins={res['inserted']} fail={res['failed']}")
    else:
        print("  [skip] ELECTROPUMP_TEST_XLS تنظیم نشده")

    print("\n— گزارش‌ها —")
    from app.reports import REPORTS
    for key in REPORTS:
        r = c.get(f"/api/reports/{key}")
        check(f"گزارش {key}", r.status_code == 200 and r.get_json()["ok"])
    r = c.post("/api/reports/builder", json={
        "dataset": "records", "group_by": ["center"],
        "aggregations": [{"fn": "count"}, {"fn": "avg", "field": "test_flow"}]})
    check("گزارش‌ساز (گروه‌بندی)", r.status_code == 200 and r.get_json()["data"]["rows"])
    r = c.post("/api/reports/builder", json={
        "dataset": "records", "fields": ["well", "op_date", "operation"]})
    check("گزارش‌ساز (فهرست)", r.status_code == 200)
    r = c.post("/api/reports/builder", json={"dataset": "records",
                                             "group_by": ["'; DROP TABLE records;--"]})
    check("گزارش‌ساز فیلد ناشناخته را نادیده می‌گیرد", r.status_code == 200)
    check("جدول رکوردها سالم است", c.get("/api/records").status_code == 200)

    print("\n— خروجی‌ها —")
    for fmt, magic in (("xlsx", b"PK"), ("csv", b"\xef\xbb\xbf"), ("json", b"{"),
                       ("pdf", b"%PDF")):
        r = c.get(f"/api/export.{fmt}")
        check(f"خروجی خام {fmt}", r.status_code == 200 and r.data.startswith(magic),
              f"{len(r.data)}B")
    for fmt in ("xlsx", "csv", "json", "pdf"):
        r = c.get(f"/api/reports/overall/export.{fmt}")
        check(f"خروجی گزارش {fmt}", r.status_code == 200 and len(r.data) > 200)

    print("\n— RTL در PDF —")
    from app.services.exporter import shape_rtl
    check("حروف فارسی به شکل متصل درمی‌آیند", shape_rtl("شاخص") != "شاخص")
    check("ترتیب بصری راست‌به‌چپ می‌شود", shape_rtl("شاخص")[::-1][0] == "ﺷ")
    check("تاریخ با اسلش وارونه نمی‌شود", "1405/06/22" in shape_rtl("تاریخ: 1405/06/22"))

    print("\n— فرم‌ساز —")
    r = c.post("/api/form-builder/sections", json={"code": "t", "title": "تست"})
    sid = r.get_json()["data"]["id"]
    r = c.post("/api/form-builder/fields",
               json={"field_name": "t_num", "label": "عدد تست",
                     "field_type": "number", "section_id": sid})
    fid = r.get_json()["data"]["id"]
    check("افزودن بخش و فیلد", bool(sid and fid))
    r = c.post("/api/records", json={**payload, "dynamic": {"t_num": "42"}})
    drid = r.get_json()["data"]["id"]
    check("مقدار فیلد پویا ذخیره شد",
          c.get(f"/api/records/{drid}").get_json()["data"]["dynamic"].get("t_num") == 42.0)
    c.delete(f"/api/form-builder/sections/{sid}")
    check("بخش دارای داده حذف نمی‌شود (فقط غیرفعال)",
          c.get(f"/api/records/{drid}").get_json()["data"]["dynamic"].get("t_num") == 42.0)
    builtin = next(f for s in c.get("/api/form-builder?all=1").get_json()["data"]["sections"]
                   for f in s["fields"] if f["field_name"] == "well")
    c.put(f"/api/form-builder/fields/{builtin['id']}",
          json={"field_name": "hacked", "field_type": "text"})
    still = any(f["field_name"] == "well"
                for s in c.get("/api/form-builder?all=1").get_json()["data"]["sections"]
                for f in s["fields"])
    check("نام فنی فیلد پایه تغییرناپذیر است", still)
    r = c.post("/api/form-builder/fields",
               json={"field_name": "bad", "label": "x", "field_type": "nope",
                     "section_id": sid})
    check("نوع فیلد نامعتبر رد می‌شود", r.status_code == 422)

    print("\n— گزینه‌ها —")
    r = c.post("/api/lookups/starter", json={"value": "اینورتر"})
    oid = r.get_json()["data"]["id"]
    r = c.delete(f"/api/lookups/item/{oid}")
    check("گزینه‌ی بدون استفاده حذف می‌شود", "حذف شد" in r.get_json()["message"])
    used = next(i for i in c.get("/api/lookups/operation").get_json()["data"]["items"]
                if i["value"] == "نصب")
    r = c.delete(f"/api/lookups/item/{used['id']}")
    check("گزینه‌ی در حال استفاده فقط غیرفعال می‌شود",
          "غیرفعال" in r.get_json()["message"])
    c.put(f"/api/lookups/item/{used['id']}", json={"is_active": True})

    print("\n— چاه‌ها —")
    r = c.post("/api/wells", json={"name": "چاه تست الف"})
    w1 = r.get_json()["data"]["id"]
    r = c.post("/api/wells", json={"name": "چاه تست ب"})
    w2 = r.get_json()["data"]["id"]
    c.post("/api/records", json={**payload, "well": "چاه تست ب"})
    r = c.post(f"/api/wells/{w1}/merge", json={"source_id": w2})
    check("ادغام چاه تکراری رکوردها را منتقل می‌کند",
          r.status_code == 200 and "رکورد" in r.get_json()["message"],
          r.get_json().get("message", ""))

    print("\n— انتقال از localStorage —")
    r = c.post("/api/import/localstorage", json={"records": json.dumps([{
        "id": "1", "day": "5", "month": "3", "year": "1404", "wellName": "گلشهر یک",
        "center": "گلشهر", "operation": "کشیدن", "contractor": "سعدآبادی",
        "motorCurr": "55", "pumpCurr": "345",
        "failure": "شولات, اهم دار", "description": "برچسب الف | متن آزاد"}])})
    check("انتقال از localStorage", r.status_code == 200
          and r.get_json()["data"]["inserted"] == 1,
          json.dumps(r.get_json().get("data", {}), ensure_ascii=False)[:80])

    print("\n— پشتیبان و بازیابی —")
    from app.services.backup import create_backup, restore_backup, validate_backup
    with app.app_context():
        info = create_backup(note="smoke")
        check("تهیه پشتیبان", os.path.exists(info["path"]))
        check("پشتیبان تک‌فایل است (بدون wal/shm)",
              not os.path.exists(info["path"] + "-wal"))
        check("اعتبارسنجی پشتیبان", validate_backup(info["path"])["valid"])
        bogus = os.path.join(tmp, "bogus.db")
        open(bogus, "wb").write(b"not a database")
        check("فایل نامعتبر رد می‌شود", not validate_backup(bogus)["valid"])
        before = c.get("/api/records?page_size=1").get_json()["total"]
        c.delete(f"/api/records/{rid}?hard=1")
        restore_backup(info["path"])
        check("بازیابی داده‌ها را برمی‌گرداند",
              c.get("/api/records?page_size=1").get_json()["total"] == before,
              f"{before} → {c.get('/api/records?page_size=1').get_json()['total']}")
        os.remove(info["path"])

    print("\n— گزارش تغییرات و صفحات —")
    check("Audit log ثبت شده", c.get("/api/audit").get_json()["total"] > 0)
    for path in ("/", "/entry", "/dashboard", "/records", "/wells", "/reports",
                 "/report-builder", "/form-builder", "/options", "/transfer",
                 "/users", "/settings", "/print/report/overall"):
        # "/" redirects to the first page the signed-in user may open.
        check(f"صفحه {path}",
              c.get(path, follow_redirects=True).status_code == 200)
    check("صفحه ۴۰۴ فارسی", "یافت نشد" in c.get("/nope").get_data(as_text=True))

    print("\n— ورود و سطح دسترسی —")
    r = c.post("/api/users", json={
        "username": "op_test", "password": "pass1234", "first_name": "کاربر",
        "last_name": "آزمایشی", "personnel_code": "T-1", "role": "operator"})
    check("ایجاد کاربر با نقش «ثبت اطلاعات»", r.status_code == 200)
    op_id = r.get_json()["data"]["id"]
    check("مجوزهای نقش اعمال شد",
          set(r.get_json()["data"]["permissions"]) ==
          {"record.create", "well.view", "report.view", "workflow.act"},
          str(sorted(r.get_json()["data"]["permissions"])))

    op = app.test_client()
    r = op.post("/api/login", json={"username": "op_test", "password": "pass1234"})
    check("ورود کاربر جدید", r.status_code == 200)
    check("کاربر می‌تواند رکورد ثبت کند",
          op.post("/api/records", json=payload).status_code == 200)
    check("کاربر نمی‌تواند ویرایش کند", op.put(f"/api/records/{rid}",
                                              json={"description": "x"}).status_code == 403)
    check("کاربر نمی‌تواند حذف کند",
          op.delete(f"/api/records/{rid}").status_code == 403)
    check("کاربر به مدیریت کاربران دسترسی ندارد",
          op.get("/api/users").status_code == 403)
    check("کاربر به تنظیمات دسترسی ندارد", op.get("/api/system").status_code == 403)
    check("تب‌های غیرمجاز باز نمی‌شوند", op.get("/settings").status_code == 403)
    check("تب مجاز باز می‌شود", op.get("/entry").status_code == 200)

    c.put(f"/api/users/{op_id}", json={"permissions": ["record.create"]})
    check("مجوز دستی جایگزین نقش می‌شود",
          op.get("/api/me").get_json()["data"]["permissions"] == ["record.create"])
    c.put(f"/api/users/{op_id}", json={"is_active": False})
    check("غیرفعال‌سازی بلافاصله اثر می‌کند", op.get("/api/records").status_code == 401)
    check("کاربر غیرفعال نمی‌تواند وارد شود",
          op.post("/api/login", json={"username": "op_test",
                                      "password": "pass1234"}).status_code == 401)

    activity = c.get(f"/api/users/{op_id}/activity").get_json()["data"]
    check("گزارش کارکرد: رکورد ثبت‌شده", activity["summary"]["records_created"] >= 1)
    check("گزارش کارکرد: نشست ثبت شده", len(activity["sessions"]) >= 1)
    check("گزارش کارکرد: اقدامات ثبت شده", len(activity["audits"]) >= 1)
    check("رمز نادرست پذیرفته نمی‌شود",
          app.test_client().post("/api/login",
                                 json={"username": "admin",
                                       "password": "x"}).status_code == 401)
    check("بدون ورود، API بسته است",
          app.test_client().get("/api/records").status_code == 401)

    print("\n— مهلت ویرایش رکورد —")
    # A recorder who may fix their own work, but only for a day.
    r = c.post("/api/users", json={
        "username": "win_op", "password": "window123", "role": "operator",
        "first_name": "مهلت", "last_name": "دار", "edit_window_hours": 24,
        "permissions": ["record.create", "record.view", "record.edit",
                        "record.delete", "well.view"]})
    win_id = r.get_json()["data"]["id"]
    check("مهلت ویرایش ذخیره می‌شود",
          r.get_json()["data"]["edit_window_hours"] == 24)
    check("برچسب فارسی مهلت", r.get_json()["data"]["edit_window_label"] == "۱ روز",
          r.get_json()["data"]["edit_window_label"])
    r = c.put(f"/api/users/{win_id}", json={"edit_window_hours": "abc"})
    check("مهلت نامعتبر رد می‌شود", r.status_code == 422)
    r = c.put(f"/api/users/{win_id}", json={"edit_window_hours": 99999})
    check("مهلت خارج از بازه رد می‌شود", r.status_code == 422)
    c.put(f"/api/users/{win_id}", json={"edit_window_hours": 24})

    c.post("/api/logout")
    c.post("/api/login", json={"username": "win_op", "password": "window123"})
    r = c.post("/api/records", json=payload)
    own = r.get_json()["data"]
    check("کاربر مهلت‌دار می‌تواند ثبت کند", r.status_code == 200)
    check("رکورد تازه قابل ویرایش است", own["can_edit"] is True, str(own["can_edit"]))
    check("تاریخ پایان مهلت برگردانده می‌شود", bool(own["edit_deadline_j"]),
          str(own["edit_deadline_j"]))
    r = c.put(f"/api/records/{own['id']}", json={"description": "داخل مهلت"})
    check("ویرایش داخل مهلت انجام می‌شود", r.status_code == 200)

    # Age the record past the window; the clock is the only thing that changed.
    with app.app_context():
        from app.models import Record
        from app.extensions import db as _db
        from app.services.jalali import local_now
        import datetime as _d
        rec = _db.session.get(Record, own["id"])
        rec.created_at = local_now() - _d.timedelta(hours=25)
        _db.session.commit()
    r = c.get(f"/api/records/{own['id']}")
    check("پس از مهلت، can_edit خاموش می‌شود",
          r.get_json()["data"]["can_edit"] is False)
    r = c.put(f"/api/records/{own['id']}", json={"description": "بعد از مهلت"})
    check("ویرایش پس از مهلت رد می‌شود", r.status_code == 403)
    check("پیام، کاربر را به مدیر ارجاع می‌دهد",
          "مدیر سیستم" in r.get_json()["error"], r.get_json()["error"])
    check("مقدار قبلی دست‌نخورده مانده",
          c.get(f"/api/records/{own['id']}").get_json()["data"]["description"]
          == "داخل مهلت")
    # Delete must be shut too, or the window is trivially sidestepped.
    r = c.delete(f"/api/records/{own['id']}")
    check("حذف پس از مهلت هم رد می‌شود", r.status_code == 403)
    r = c.post(f"/api/records/{own['id']}/restore")
    check("بازیابی پس از مهلت هم رد می‌شود", r.status_code == 403)

    c.post("/api/logout")
    c.post("/api/login", json={"username": "admin", "password": "admin"})
    r = c.put(f"/api/records/{own['id']}", json={"description": "مدیر آزاد است"})
    check("مدیر سیستم محدود نمی‌شود", r.status_code == 200)
    check("مدیر همیشه can_edit دارد",
          c.get(f"/api/records/{own['id']}").get_json()["data"]["can_edit"] is True)
    # Lifting the limit hands the record back without the admin touching it.
    c.put(f"/api/users/{win_id}", json={"edit_window_hours": None})
    c.post("/api/logout")
    c.post("/api/login", json={"username": "win_op", "password": "window123"})
    r = c.put(f"/api/records/{own['id']}", json={"description": "مهلت برداشته شد"})
    check("با برداشتن مهلت، کاربر دوباره می‌تواند ویرایش کند", r.status_code == 200)
    c.post("/api/logout")
    c.post("/api/login", json={"username": "admin", "password": "admin"})
    c.delete(f"/api/records/{own['id']}?hard=1")
    c.delete(f"/api/users/{win_id}")

    print("\n— کد PM و کلاسه چاه —")
    wells = c.get("/api/wells?limit=1&q=10/21/1").get_json()["data"]
    check("جستجوی چاه با کد PM", bool(wells) and wells[0]["pm_code"] == "10/21/1",
          str([w["name"] for w in wells]))
    check("نمایش ترکیبی نام و کد", "PM" in (wells[0]["display"] if wells else ""))
    exact = c.get("/api/wells?limit=3&q=" + quote("کورده 1")).get_json()["data"]
    check("تطابق دقیق در صدر نتایج", bool(exact) and exact[0]["name"] == "کورده 1",
          str([w["name"] for w in exact[:3]]))
    with app.app_context():
        from app.models import Well
        from app.services.lookups import fold_persian, well_key
        actives = Well.query.filter_by(is_active=True).all()
        folded = [fold_persian(w.name) for w in actives]
        keys = [well_key(w.name) for w in actives]
        codes = [w.pm_code for w in actives if w.pm_code]
        check("نام چاه تکراری وجود ندارد", len(folded) == len(set(folded)),
              f"{len(folded)-len(set(folded))} تکراری")
        from collections import Counter as _C
        _dupes = [k for k, n in _C(keys).items() if n > 1]
        check("نام چاه با ایندکس حرفی هم تکراری نیست", not _dupes,
              str([[w.name for w in actives if well_key(w.name) == k]
                   for k in _dupes]))
        check("کد PM تکراری وجود ندارد", len(codes) == len(set(codes)))
        check("چاه‌ها مرکز دارند",
              Well.query.filter(Well.center_id.isnot(None)).count() > 800)
        # The index may be written as a digit or as a word — one well, not two.
        check("«یک» و «1» یک چاه‌اند",
              well_key("ده غیبی یک") == well_key("ده غیبی 1"))
        check("«دو» و «2» یک چاه‌اند",
              well_key("مرکز تحقیقات دو") == well_key("مرکز تحقیقات 2"))
        check("ارقام فارسی هم یکی می‌شوند",
              well_key("الهیه ۳") == well_key("الهیه 3"))
        check("پرانتز و نقطه‌گذاری نادیده گرفته می‌شود",
              well_key("امرغان توس ( قدیم )") == well_key("امرغان توس قدیم"))
        check("ایندکس پیش از «قدیم» هم شناخته می‌شود",
              well_key("ابوطالب یک قدیم") == well_key("ابوطالب 1 قدیم"))
        # A number word that is part of the name must NOT be folded away.
        for a, b in (("ده سرخ", "10 سرخ"), ("چهار فصل", "4 فصل"),
                     ("سه راه دانش", "3 راه دانش"), ("جمال ده", "جمال 10")):
            check(f"«{a}» با «{b}» یکی نمی‌شود", well_key(a) != well_key(b))

    print("\n— کد PM با دو املا —")
    with app.app_context():
        from app.models import Well, Record
        from app.extensions import db as _db
        from app.services.seed import deduplicate_wells
        from app.services.lookups import pm_digits
        check("ارقام کد PM یکسان می‌شوند",
              pm_digits("10/24/41") == pm_digits("102441") == "102441")
        a = Well(name="چاه دوقلو", pm_code="10/99/7", well_class="900001",
                 is_active=True, is_verified=True)
        b = Well(name="چاه دوقلو (BOT)", pm_code="10997", well_class="900001",
                 is_active=True)
        # Same digits but a different کلاسه: a real second well, never merged.
        d = Well(name="چاه ناهمسان", pm_code="10997", well_class="900002",
                 is_active=True)
        _db.session.add_all([a, b, d])
        _db.session.commit()
        res = deduplicate_wells()
        check("دو املای یک کد PM ادغام می‌شوند",
              not Well.query.filter_by(name="چاه دوقلو (BOT)").one().is_active,
              str(res))
        check("املای رسمی «10/99/7» باقی می‌ماند",
              Well.query.filter_by(name="چاه دوقلو").one().is_active)
        check("املای قدیمی به‌عنوان نام مستعار می‌ماند",
              "چاه دوقلو (BOT)" in [al.alias for al in
                                    Well.query.filter_by(name="چاه دوقلو").one().aliases])
        check("کلاسه متفاوت مانع ادغام می‌شود",
              Well.query.filter_by(name="چاه ناهمسان").one().is_active)

    print("\n— «قدیم» و «جدید» —")
    with app.app_context():
        from app.models import Well
        from app.extensions import db as _db
        from app.services.seed import deduplicate_wells
        from app.services.lookups import qualifier_base_key
        check("پسوند «جدید» شناسایی می‌شود",
              qualifier_base_key("امامیه 17( جدید )") == qualifier_base_key("امامیه 17( قدیم )")
              != "", qualifier_base_key("امامیه 17( جدید )"))
        check("نام بدون پسوند، پایه ندارد", qualifier_base_key("امامیه 17") == "")
        base = Well.query.filter_by(name="امامیه 17").one()
        _db.session.add_all([
            Well(name="امامیه 17( جدید )", is_active=True, is_verified=False),
            Well(name="امامیه 17( قدیم )", is_active=True, is_verified=False),
            # Registered under a qualified name: that IS its name, keep it.
            Well(name="امامیه 90 جدید", pm_code="10/26/990", well_class="900090",
                 is_active=True, is_verified=True),
        ])
        _db.session.commit()
        deduplicate_wells()
        for variant in ("امامیه 17( جدید )", "امامیه 17( قدیم )"):
            check(f"«{variant}» حذف شد",
                  not Well.query.filter_by(name=variant).one().is_active)
        check("رکوردها به چاه اصلی رسیدند", Well.query.filter_by(name="امامیه 17")
              .one().is_active)
        check("نام‌های قبلی به‌عنوان نام مستعار ماندند",
              {"امامیه 17( جدید )", "امامیه 17( قدیم )"} <=
              {a.alias for a in Well.query.filter_by(name="امامیه 17").one().aliases})
        check("چاهِ ثبت‌شده با نام «جدید» دست‌نخورده می‌ماند",
              Well.query.filter_by(name="امامیه 90 جدید").one().is_active)

    print("\n— جستجوی چاه بدون تکرار —")
    with app.app_context():
        from app.models import Well
        from app.extensions import db as _db
        _db.session.add(Well(name="آماده سازی یک", is_active=True))
        _db.session.commit()
    hits = c.get("/api/wells?limit=20&q=" + quote("آماده سازی")).get_json()["data"]
    names = [w["name"] for w in hits]
    check("چاه هم‌نام دوباره در نتایج نمی‌آید",
          "آماده سازی یک" not in names and "آماده سازی 1" in names, str(names))
    r = c.post("/api/wells", json={"name": "آماده سازی 1"})
    check("افزودن چاه تکراری رد می‌شود", r.status_code == 409, r.get_json().get("error"))
    r = c.post("/api/wells", json={"name": "آماده سازی هفت"})
    check("چاه واقعاً جدید پذیرفته می‌شود", r.status_code == 200)

    print("\n— مرکز از روی چاه —")
    w = c.get("/api/wells?limit=1&q=" + quote("کورده 1")).get_json()["data"][0]
    check("چاه، مرکز خود را برمی‌گرداند", w["center_value"] == "سوران",
          str(w["center_value"]))

    print("\n— پیمانکار مشروط به مجری —")
    rules = c.get("/api/form-builder").get_json()["data"]["conditional"]
    check("قاعده نمایش پیمانکار تعریف شده",
          {"field": "contractor", "on": "executor", "value": "پیمانی"} in rules,
          str(rules))
    base = dict(payload)
    base.pop("dynamic", None)
    r = c.post("/api/records", json=dict(base, executor="امانی", contractor="جوادی"))
    check("با «امانی» پیمانکار ذخیره نمی‌شود",
          r.get_json()["data"]["contractor"] is None)
    c.delete(f"/api/records/{r.get_json()['data']['id']}?hard=1")
    r = c.post("/api/records", json=dict(base, executor="پیمانی", contractor="جوادی"))
    check("با «پیمانی» پیمانکار ذخیره می‌شود",
          r.get_json()["data"]["contractor"] == "جوادی")
    c.delete(f"/api/records/{r.get_json()['data']['id']}?hard=1")
    r = c.post("/api/records", json=dict(base, executor="امانی"))
    check("پیمانکار دیگر الزامی نیست", r.status_code == 200)
    if r.get_json().get("ok"):
        c.delete(f"/api/records/{r.get_json()['data']['id']}?hard=1")

    print("\n— ساعت محلی —")
    from app.services.jalali import (local_now, tehran_time_str, to_jalali_str,
                                     to_tehran)
    import datetime as _dt
    # Timestamps are stored on the wall clock, so what is written is what is
    # shown — no offset arithmetic that a mis-set Windows timezone can break.
    stamp = _dt.datetime(2026, 9, 13, 21, 15, 30)
    check("ساعت همان‌طور که ثبت شده نمایش داده می‌شود",
          tehran_time_str(stamp, with_seconds=False) == "21:15",
          tehran_time_str(stamp))
    check("تاریخ شمسی با ساعت محلی می‌خواند",
          to_jalali_str(stamp) == "1405/06/22", to_jalali_str(stamp))
    check("ساعت ثبت‌شده با ساعت سیستم یکی است",
          abs((local_now() - _dt.datetime.now()).total_seconds()) < 2)
    aware = stamp.replace(tzinfo=_dt.timezone.utc)
    check("مقدار دارای منطقه‌زمانی به وقت تهران می‌آید",
          to_tehran(aware).strftime("%H:%M") == "00:45",
          to_tehran(aware).strftime("%H:%M"))
    with app.app_context():
        cols = [col["label"] for col in _export_headers(c)]
    check("ستون «کد PM» در خروجی", "کد PM" in cols)
    check("ستون «کلاسه چاه» در خروجی", "کلاسه چاه" in cols)

    print("\n— ویرایش گزینه‌های فرم —")
    r = c.post("/api/form-builder/sections", json={"code": "opt_t", "title": "تست"})
    sid2 = r.get_json()["data"]["id"]
    r = c.post("/api/form-builder/fields",
               json={"field_name": "opt_pick", "label": "انتخاب", "field_type": "radio",
                     "section_id": sid2,
                     "options": [{"value": "الف", "label": "الف"},
                                 {"value": "ب", "label": "ب"}]})
    fid2 = r.get_json()["data"]["id"]
    r = c.put(f"/api/form-builder/fields/{fid2}",
              json={"options": [{"value": "الف", "label": "الف ویرایش‌شده"},
                                {"value": "ج", "label": "ج"}]})
    opts = {o["value"]: o for o in r.get_json()["data"]["own_options"]}
    check("ویرایش گزینه‌های فیلد سفارشی ذخیره می‌شود",
          opts.get("الف", {}).get("label") == "الف ویرایش‌شده")
    check("گزینه جدید افزوده می‌شود", "ج" in opts)
    check("گزینه حذف‌شده فقط غیرفعال می‌شود",
          "ب" in opts and opts["ب"]["is_active"] is False)

    builtin = next(f for s in c.get("/api/form-builder?all=1").get_json()["data"]["sections"]
                   for f in s["fields"] if f["field_name"] == "center")
    r = c.get(f"/api/form-builder/fields/{builtin['id']}/options").get_json()["data"]
    check("گزینه‌های فیلد پایه خوانده می‌شود", r["source"] == "lookup" and r["options"])
    edited = [{"value": o["value"], "label": o["label"], "is_active": o["is_active"]}
              for o in r["options"]]
    edited[0]["label"] = "سوران ✓"
    r = c.put(f"/api/form-builder/fields/{builtin['id']}/options",
              json={"options": edited})
    check("ویرایش گزینه‌های فیلد پایه ذخیره می‌شود", r.status_code == 200)
    after = c.get(f"/api/form-builder/fields/{builtin['id']}/options").get_json()["data"]
    check("برچسب جدید اعمال شد", after["options"][0]["label"] == "سوران ✓")

    print("\n— ستون‌های جدول و خروجی —")
    with app.app_context():
        labels = [col["label"] for col in _export_headers(c)]
    check("ستون «کد PM» در خروجی", "کد PM" in labels)
    check("ستون «کلاسه چاه» در خروجی", "کلاسه چاه" in labels)
    rec = c.get("/api/records?page_size=1").get_json()["data"]
    check("رکورد کد PM چاه را حمل می‌کند",
          bool(rec) and "well_pm_code" in rec[0])
    check("رکورد کلاسه چاه را حمل می‌کند", bool(rec) and "well_class" in rec[0])

    print("\n— تاریخ در حالت ویرایش —")
    r = c.post("/api/records", json={**payload, "prev_install_date": "1403/07/14",
                                     "test_date": "1405/06/01"})
    dated = r.get_json()["data"]
    check("تاریخ میلادی برای ماشین نگه داشته می‌شود",
          dated["prev_install_date"] == "2024-10-05", str(dated["prev_install_date"]))
    check("تاریخ شمسی برای فرم برگردانده می‌شود",
          dated["prev_install_date_j"] == "1403/07/14",
          str(dated.get("prev_install_date_j")))
    check("تاریخ آزمایش هم شمسی برمی‌گردد",
          dated["test_date_j"] == "1405/06/01", str(dated.get("test_date_j")))
    # A dynamic (admin-built) date field must round-trip in Jalali too, or
    # reopening the record shows 2024-10-05 where 1403/07/14 was typed.
    r = c.post("/api/form-builder/sections", json={"code": "dt_s", "title": "تاریخ"})
    dsid = r.get_json()["data"]["id"]
    r = c.post("/api/form-builder/fields",
               json={"field_name": "extra_date", "label": "تاریخ اضافه",
                     "field_type": "jalali_date", "section_id": dsid})
    check("فیلد تاریخ سفارشی ساخته شد", r.status_code == 200)
    r = c.put(f"/api/records/{dated['id']}",
              json={"dynamic": {"extra_date": "1404/02/03"}})
    back = c.get(f"/api/records/{dated['id']}").get_json()["data"]
    check("تاریخ فیلد سفارشی شمسی برمی‌گردد",
          back["dynamic"].get("extra_date") == "1404/02/03",
          str(back["dynamic"].get("extra_date")))
    c.delete(f"/api/records/{dated['id']}?hard=1")

    print("\n— نقشه فرایند: گره‌ها و پیکان‌ها —")
    wf = c.get("/api/workflow/definition").get_json()["data"]
    nodes = {n["key"]: n for n in wf["graph"]["nodes"]}
    edges = wf["graph"]["edges"]
    check("نقشه گره شروع دارد",
          any(n["node_type"] == "start" for n in nodes.values()),
          str(sorted(nodes)))
    check("نقشه گره پایان دارد",
          any(n["node_type"] == "end" for n in nodes.values()))
    check("نقشه گره تصمیم دارد",
          any(n["node_type"] == "decision" for n in nodes.values()))
    check("نقشه گره اقدام (ثبت رکورد) دارد",
          any((n.get("config") or {}).get("action") == "create_record"
              for n in nodes.values()))
    check("پیکان‌ها کشیده شده‌اند", len(edges) >= 10, str(len(edges)))
    branch = [e for e in edges if (e.get("condition") or {}).get("field")
              == "operation_kind"]
    check("مسیر بر اساس شرط روی پیکان انتخاب می‌شود", len(branch) >= 2,
          str(len(branch)))
    check("هر گره مختصات و اندازه دارد",
          all(n.get("x") is not None and n.get("width") for n in nodes.values()))
    check("پالت شامل بخش‌ها و فیلدهاست",
          wf["palette"]["sections"] and wf["palette"]["fields"])
    check("انواع گره، عملگرها و اقدام‌ها برای طراح فرستاده می‌شود",
          len(wf["node_types"]) == 6 and wf["operators"] and wf["actions"])
    start_node = next(n for n in nodes.values() if n["node_type"] == "start")
    check("گره شروع، چاه و نوع عملیات را می‌پرسد",
          {"intake", "well"} <= {i["code"] for i in start_node["items"]},
          str([i["code"] for i in start_node["items"]]))

    # Real accounts, one per person, exactly as the workshop will have them.
    owners, made = {}, {}
    for uname, first, last in (("markaz", "مرکز", "آبرسانی"),
                               ("bozorg", "امین", "بزرگمهر"),
                               ("yaghouti", "مهدی", "یاقوتی‌نیا"),
                               ("kahani", "علی", "کاهانی")):
        rr = c.post("/api/users", json={
            "username": uname, "password": "process123", "role": "stage_owner",
            "first_name": first, "last_name": last})
        made[uname] = rr.get_json()["data"]
        owners[uname] = made[uname]["id"]
    check("نقش «متولی مرحله»: کارتابل، نقشه، مشاهده رکوردها و خروجی",
          set(made["kahani"]["permissions"])
          == {"workflow.act", "workflow.map.view", "record.view",
              "record.export"},
          str(sorted(made["kahani"]["permissions"])))

    # Hand each node to its owner, the way the properties panel does.
    for key, uname in (("start", "markaz"), ("center", "markaz"),
                       ("review", "bozorg"), ("shop", "yaghouti"),
                       ("action", "bozorg"), ("well_install", "bozorg"),
                       ("final", "kahani")):
        rr = c.put(f"/api/workflow/nodes/{nodes[key]['id']}", json={
            "principals": [{"role": "assignee", "kind": "user",
                            "user_id": owners[uname]}]})
        if key == "start":
            check("انتساب متولی به گره", rr.status_code == 200,
                  str(rr.get_json().get("error")))

    def who(username):
        cc = app.test_client()
        cc.post("/api/login", json={"username": username, "password": "process123"})
        return cc

    markaz, bozorg, yaghouti, kahani = (who("markaz"), who("bozorg"),
                                        who("yaghouti"), who("kahani"))

    def start_run(kind, well, client=None):
        rr = (client or markaz).post("/api/workflow/instances", json={
            "data": {"operation_kind": kind, "well": well}})
        return rr

    def send(client, iid, key, data, note=None):
        return client.post(f"/api/workflow/instances/{iid}/submit",
                           json={"node_key": key, "data": data, "note": note})

    def detail(client, iid, key=None):
        url = f"/api/workflow/instances/{iid}"
        if key:
            url += "?node=" + quote(key)
        return client.get(url).get_json()["data"]

    print("\n— فرایند: متولی بدون مجوز ثبت رکورد کار می‌کند —")
    # A stage owner must be able to run their phase with workflow.act alone.
    # Needing record.create for it would hand them the whole data-entry tab.
    for label, path in (("صفحه کارتابل", "/inbox"),
                        ("ساختار فرم", "/api/form-builder"),
                        ("فهرست گزینه‌ها", "/api/lookups"),
                        ("جستجوی چاه", "/api/wells?q=" + quote("امام")),
                        ("کارتابل", "/api/workflow/inbox")):
        check(f"متولی به {label} دسترسی دارد",
              markaz.get(path).status_code == 200, path)
    for label, path in (("جدول رکوردها", "/records"),
                        ("مستندات", "/documents"),
                        ("نقشه فرایند", "/workflow")):
        check(f"متولی به {label} دسترسی دارد",
              markaz.get(path).status_code == 200, path)
    check("متولی خروجی اکسل می‌گیرد",
          markaz.get("/api/export.xlsx").status_code == 200)
    check("متولی خروجی CSV هم می‌گیرد",
          markaz.get("/api/export.csv").status_code == 200)
    for label, path in (("ثبت اطلاعات", "/entry"),
                        ("فرم‌ساز", "/form-builder"), ("کاربران", "/users")):
        check(f"متولی به {label} دسترسی ندارد",
              markaz.get(path).status_code == 403, path)
    check("متولی نمی‌تواند نقشه را تغییر دهد",
          markaz.put(f"/api/workflow/nodes/{nodes['final']['id']}",
                     json={"title": "دستکاری"}).status_code == 403)
    check("متولی نمی‌تواند رکورد را ویرایش کند",
          markaz.put("/api/records/1", json={"description": "x"}).status_code == 403)
    check("متولی نمی‌تواند رکورد مستقیم ثبت کند",
          markaz.post("/api/records", json={"well": "امام رضا 11"}).status_code == 403)

    rr = start_run("کشیدن", "امام رضا 11")
    check("متولی گره شروع می‌تواند فرایند را آغاز کند", rr.status_code == 200,
          str(rr.get_json().get("error")))
    check("و کارتابلش دکمه شروع را نشان می‌دهد",
          markaz.get("/api/workflow/inbox").get_json().get("may_start") is True)
    rr = start_run("کشیدن", "امام رضا 11", client=kahani)
    check("متولی گره‌های بعد نمی‌تواند فرایند شروع کند", rr.status_code == 422,
          str(rr.get_json().get("error"))[:60])
    check("و دکمه شروع برایش پنهان است",
          kahani.get("/api/workflow/inbox").get_json().get("may_start") is False)
    rr = markaz.post("/api/workflow/instances",
                     json={"data": {"operation_kind": "کشیدن"}})
    check("بدون نام چاه فرایند شروع نمی‌شود", rr.status_code == 422,
          str(rr.get_json().get("error"))[:50])
    rr = start_run("کشیدن", "چاه ناموجود ۹۹")
    check("چاه خارج از فهرست پذیرفته نمی‌شود", rr.status_code == 422)
    sf = markaz.get("/api/workflow/start-form").get_json()["data"]
    check("فرم شروع از روی گره شروع ساخته می‌شود",
          {"operation_kind", "well"}
          <= {f["field_name"] for s in sf["sections"] for f in s["fields"]},
          str([f["field_name"] for s in sf["sections"] for f in s["fields"]]))

    print("\n— فرایند: شرط روی پیکان مسیر «نصب» را می‌برد —")
    iid = start_run("نصب", "کورده 1").get_json()["data"]["id"]
    det = detail(yaghouti, iid)
    live = {n["key"]: n for n in det["map"]["nodes"]}
    check("نصب مستقیم به کارگاه می‌رود", det["current_node"] == "shop",
          str(det["current_node"]))
    check("گره‌های مسیر کشیدن طی نمی‌شوند",
          live["center"]["state"] == "skipped"
          and live["review"]["state"] == "skipped",
          f"{live['center']['state']} / {live['review']['state']}")
    check("در نصب، «علت خرابی» پرسیده نمی‌شود",
          "failure" not in [f["field_name"] for s in det["form"]["sections"]
                            for f in s["fields"]])
    check("در نصب، «نصب مرتبط با…» پرسیده می‌شود",
          "install_relates_to" in [f["field_name"] for s in det["form"]["sections"]
                                   for f in s["fields"]])
    check("در نصب، «اطلاعات چاه و نصب» در مسیر هست",
          live["well_install"]["reachable"] is True)

    print("\n— فرایند: فازها به هم وابسته نیستند —")
    pid = start_run("کشیدن", "امام رضا 11").get_json()["data"]["id"]
    box = yaghouti.get("/api/workflow/inbox").get_json()["data"]
    check("کارگاه بی‌درنگ در کارتابل می‌آید",
          any(b["id"] == pid and b["node_key"] == "shop" for b in box))
    check("بزرگمهر هر سه گره خودش را می‌بیند",
          {b["node_key"] for b in bozorg.get("/api/workflow/inbox")
           .get_json()["data"] if b["id"] == pid} >= {"review", "action"})
    det = detail(yaghouti, pid, "shop")
    check("هشدار فازهای ثبت‌نشده داده می‌شود",
          {w["node_key"] for w in det["waiting_on"]} == {"center", "review"},
          str(det["waiting_on"]))
    check("ولی کارگاه مسدود نیست", det["may_act"] is True)
    rr = send(yaghouti, pid, "shop",
              {"op_jdate": "1405/06/22", "well": "امام رضا 11",
               "center": "سوران", "operation": "کشیدن",
               "motor_curr": "73", "pump_curr": "384"})
    check("کارگاه پیش از فازهای قبل ثبت می‌شود", rr.status_code == 200,
          str(rr.get_json().get("error")))
    det = detail(markaz, pid, "center")
    asked = {f["field_name"] for s in det["form"]["sections"] for f in s["fields"]}
    check("«اطلاعات پایه» دوباره پرسیده نمی‌شود", "op_jdate" not in asked,
          str(sorted(asked)))
    check("ولی «علت خرابی» هنوز پرسیده می‌شود", "failure" in asked)
    rr = kahani.post(f"/api/workflow/instances/{pid}/submit",
                     json={"node_key": "shop", "data": {}})
    check("فاز دیگری را نمی‌توان به‌جای متولی ثبت کرد", rr.status_code == 422,
          str(rr.get_json().get("error"))[:60])

    print("\n— فرایند: دیدن کار فازهای قبل و قفل بودن چاه —")
    seen = start_run("کشیدن", "امام رضا 11").get_json()["data"]["id"]
    det = detail(markaz, seen, "center")
    wells = [f for s in det["form"]["sections"] for f in s["fields"]
             if f["field_name"] == "well"]
    check("چاه پس از گره شروع دوباره جستجو نمی‌شود",
          bool(wells) and wells[0].get("read_only") is True,
          str(wells and wells[0].get("read_only")))
    check("و مقدارش نمایش داده می‌شود",
          wells[0].get("read_only_value") == "امام رضا 11",
          str(wells[0].get("read_only_value")))
    send(markaz, seen, "center",
         {"op_jdate": "1405/06/22", "center": "سوران",
          "failure": ["شولات", "اهم دار"]})
    det = detail(bozorg, seen, "review")
    summary = det.get("summary") or []
    check("فاز بعدی کار فاز قبل را می‌بیند",
          any(b["node_key"] == "center" for b in summary), str(summary))
    values = {v["label"]: v["value"] for b in summary for v in b["values"]}
    check("علت خرابی ثبت‌شده را می‌بیند",
          values.get("علت خرابی") == "شولات، اهم دار", str(values))
    check("فاز خودش در خلاصه تکرار نمی‌شود",
          all(b["node_key"] != "review" for b in summary))
    check("خلاصه فقط خواندنی است (فیلد نیست)",
          all("field_name" not in v for b in summary for v in b["values"]))
    # The page can rebuild the same summary from the entries alone, so a
    # browser running ahead of its server still shows the earlier phases.
    entries = {e["node_key"]: e for e in det["entries"]
               if e["task_kind"] == "fill"}
    check("payload هر فاز برای بازسازی خلاصه در دسترس است",
          entries["center"]["status"] == "submitted"
          and entries["center"]["payload"].get("failure") == ["شولات", "اهم دار"],
          str(entries["center"].get("payload"))[:70])
    check("عنوان و ثبت‌کننده‌ی فاز هم همراه payload می‌آید",
          bool(entries["center"].get("title"))
          and bool(entries["center"].get("user_name")),
          f"{entries['center'].get('title')} / {entries['center'].get('user_name')}")
    send(bozorg, seen, "review", {"review_decision": "نیاز به کشیدن دارد"})
    det = detail(yaghouti, seen, "shop")
    keys_seen = {b["node_key"] for b in det.get("summary") or []}
    check("کارگاه کار دو فاز قبل را می‌بیند",
          {"center", "review"} <= keys_seen, str(sorted(keys_seen)))

    print("\n— فرایند: شرط دوگانه، «اطلاعات چاه و نصب» را باز یا بسته می‌کند —")
    def run_to_action(action, pump_now=None):
        i = start_run("کشیدن", "امام رضا 11").get_json()["data"]["id"]
        send(markaz, i, "center", {"op_jdate": "1405/06/22",
                                   "well": "امام رضا 11", "center": "سوران",
                                   "failure": ["شولات"]})
        send(bozorg, i, "review", {"review_decision": "نیاز به کشیدن دارد"})
        send(yaghouti, i, "shop", {"operation": "کشیدن", "motor_curr": "73",
                                   "pump_curr": "384"})
        data = {"required_action": action}
        if pump_now:
            data["pump_type_now"] = pump_now
        send(bozorg, i, "action", data)
        d = detail(bozorg, i)
        state = {n["key"]: n for n in d["map"]["nodes"]}["well_install"]
        return i, state

    _i, st = run_to_action("ویدئومتری")
    check("«ویدئومتری» از فرم نصب عبور می‌کند", st["state"] == "skipped",
          st["state"])
    _i, st = run_to_action("بهسازی")
    check("«بهسازی» هم از آن عبور می‌کند", st["state"] == "skipped")
    _i, st = run_to_action("نصب الکتروپمپ جدید", "خیر")
    check("«تیپ در این مرحله نه» یعنی عبور", st["state"] == "skipped",
          st["state"])
    last, st = run_to_action("نصب الکتروپمپ جدید", "بله")
    check("«تیپ در این مرحله بله» یعنی فرم نصب باز می‌شود",
          st["reachable"] is True and st["state"] != "skipped", st["state"])
    send(bozorg, last, "well_install", {"well_depth": 150})

    print("\n— فرایند: ثبت نهایی و مستندات —")
    det = detail(kahani, last, "final")
    check("فاز پایانی در کشیدن سه بخش دارد",
          len(det["form"]["sections"]) == 3,
          str([s["code"] for s in det["form"]["sections"]]))
    import io as _io
    up = kahani.post(f"/api/workflow/instances/{last}/attachments",
                     data={"file": (_io.BytesIO(b"%PDF-1.4 test"), "gozaresh.pdf")},
                     content_type="multipart/form-data")
    check("بارگذاری مستند PDF", up.status_code == 200,
          str(up.get_json().get("error")))
    doc_id = up.get_json()["data"]["id"]
    bad = kahani.post(f"/api/workflow/instances/{last}/attachments",
                      data={"file": (_io.BytesIO(b"MZ"), "virus.exe")},
                      content_type="multipart/form-data")
    check("فایل اجرایی رد می‌شود", bad.status_code == 415)
    check("دانلود مستند", kahani.get(f"/api/workflow/attachments/{doc_id}")
          .status_code == 200)
    rr = send(kahani, last, "final",
              {"test_flow": 30, "starter": "سافت", "workshop_opinion": ["شولاتی"]})
    body_ = rr.get_json()
    check("با ثبت فاز پایانی، گره اقدام رکورد می‌سازد",
          bool(body_.get("data", {}).get("record_id")), str(body_.get("error")))
    new_id = body_["data"]["record_id"]
    rec = c.get(f"/api/records/{new_id}").get_json()["data"]
    check("رکورد نوع عملیات را دارد",
          rec["dynamic"].get("operation_kind") == "کشیدن")
    check("رکورد علت خرابی را دارد", rec["failure"] == ["شولات"])
    check("رکورد نام چاه را دارد", rec["well"] == "امام رضا 11", str(rec["well"]))
    done = c.get(f"/api/workflow/instances/{last}").get_json()["data"]
    check("فرایند تکمیل‌شده علامت خورد", done["status"] == "completed")
    endn = {n["key"]: n for n in done["map"]["nodes"]}
    check("گره پایان سبز می‌شود", endn["end"]["status"] == "submitted",
          endn["end"]["status"])
    actions = [e for e in done["events"] if e["action"] == "action"]
    check("سابقه، اجرای اقدام را ثبت کرده", len(actions) == 1, str(len(actions)))
    check("سابقه شروع و تکمیل را هم دارد",
          {"started", "completed"} <= {e["action"] for e in done["events"]})

    print("\n— فرایند: تأیید چندنفره، رد و بازگشت —")
    # An approval node the admin adds now, with two approvers and a quorum of
    # two — nothing in the engine knows who they are or what they approve.
    ap = c.post("/api/workflow/nodes", json={
        "node_type": "approval", "title": "تأیید نهایی",
        "x": 1360, "y": 430}).get_json()["data"]
    c.put(f"/api/workflow/nodes/{ap['id']}", json={
        "config": {"approval_mode": "quorum", "approval_quorum": 2},
        "principals": [{"role": "approver", "kind": "user",
                        "user_id": owners["bozorg"]},
                       {"role": "approver", "kind": "user",
                        "user_id": owners["kahani"]}]})
    e_in = c.post("/api/workflow/edges", json={
        "source_id": nodes["shop"]["id"], "target_id": ap["id"]}).get_json()["data"]
    e_ok = c.post("/api/workflow/edges", json={
        "source_id": ap["id"], "target_id": nodes["final"]["id"]}).get_json()["data"]
    c.put(f"/api/workflow/edges/{e_ok['id']}",
          json={"kind": "approved", "label": "تأیید شد"})
    e_no = c.post("/api/workflow/edges", json={
        "source_id": ap["id"], "target_id": nodes["shop"]["id"]}).get_json()["data"]
    c.put(f"/api/workflow/edges/{e_no['id']}",
          json={"kind": "rejected", "label": "اصلاح شود"})
    check("افزودن گره تأیید و سه پیکان", bool(ap["id"]) and bool(e_in["id"]))

    aid = start_run("کشیدن", "امام رضا 11").get_json()["data"]["id"]
    box = [b for b in bozorg.get("/api/workflow/inbox").get_json()["data"]
           if b["id"] == aid]
    check("تأییدی که نوبتش نرسیده در کارتابل نمی‌آید",
          all(b["node_key"] != ap["key"] for b in box), str(box))
    send(yaghouti, aid, "shop", {"op_jdate": "1405/06/22",
                                 "well": "امام رضا 11", "center": "سوران",
                                 "operation": "کشیدن", "motor_curr": "73",
                                 "pump_curr": "384"})
    box = [b for b in bozorg.get("/api/workflow/inbox").get_json()["data"]
           if b["id"] == aid and b["node_key"] == ap["key"]]
    check("پس از ثبت فاز، تأیید در کارتابل می‌آید", len(box) == 1, str(box))
    check("و به‌عنوان کار «تأیید» شناخته می‌شود",
          box and box[0]["task_kind"] == "approve")
    det = detail(bozorg, aid, ap["key"])
    check("تأییدکننده داده‌های ثبت‌شده را می‌بیند",
          any(b["node_key"] == "shop" for b in det.get("summary") or []))
    check("و اجازه تأیید دارد", det["may_approve"] is True)
    check("و گره تأیید، منتظر تصمیم نشان داده می‌شود",
          {n["key"]: n for n in det["map"]["nodes"]}[ap["key"]]["state"]
          == "awaiting_approval",
          str({n["key"]: n for n in det["map"]["nodes"]}[ap["key"]]["state"]))
    rr = bozorg.post(f"/api/workflow/instances/{aid}/decide",
                     json={"node_key": ap["key"], "approved": False})
    check("رد بدون دلیل پذیرفته نمی‌شود", rr.status_code == 422,
          str(rr.get_json().get("error"))[:40])
    rr = yaghouti.post(f"/api/workflow/instances/{aid}/decide",
                       json={"node_key": ap["key"], "approved": True})
    check("کسی که تأییدکننده نیست تأیید نمی‌کند", rr.status_code == 422)
    bozorg.post(f"/api/workflow/instances/{aid}/decide",
                json={"node_key": ap["key"], "approved": True,
                      "comment": "موافقم"})
    det = detail(bozorg, aid, ap["key"])
    check("با یک تأیید از دو تأیید لازم، هنوز باز است",
          {n["key"]: n for n in det["map"]["nodes"]}[ap["key"]]["state"]
          == "awaiting_approval",
          str({n["key"]: n for n in det["map"]["nodes"]}[ap["key"]]["state"]))
    kahani.post(f"/api/workflow/instances/{aid}/decide",
                json={"node_key": ap["key"], "approved": True})
    det = detail(kahani, aid, "final")
    check("با رسیدن به حد نصاب، مسیر تأیید باز می‌شود",
          {n["key"]: n for n in det["map"]["nodes"]}[ap["key"]]["state"]
          == "approved")
    check("و فاز پس از تأیید در دسترس می‌آید",
          {n["key"]: n for n in det["map"]["nodes"]}["final"]["reachable"] is True)
    check("سابقه هر دو تأیید را دارد",
          len([e for e in det["events"] if e["action"] == "approved"]) == 2)

    rid = start_run("کشیدن", "امام رضا 11").get_json()["data"]["id"]
    send(yaghouti, rid, "shop", {"op_jdate": "1405/06/22",
                                 "well": "امام رضا 11", "center": "سوران",
                                 "operation": "کشیدن", "motor_curr": "73",
                                 "pump_curr": "384"})
    bozorg.post(f"/api/workflow/instances/{rid}/decide",
                json={"node_key": ap["key"], "approved": False,
                      "comment": "پلاک نمی‌خواند"})
    kahani.post(f"/api/workflow/instances/{rid}/decide",
                json={"node_key": ap["key"], "approved": False,
                      "comment": "موافق ردم"})
    det = detail(yaghouti, rid, "shop")
    check("رد، فرایند را به فاز قبل برمی‌گرداند",
          det["status"] == "returned", det["status"])
    check("و آن فاز دوباره باز می‌شود",
          {n["key"]: n for n in det["map"]["nodes"]}["shop"]["status"]
          == "pending")
    back = [e for e in det["events"] if e["action"] == "reopened"]
    check("سابقه بازگشت و دلیلش را نگه می‌دارد",
          bool(back) and "پلاک" in (back[0]["comment"] or ""),
          str(back[:1]))

    print("\n— فرایند: نسخه‌ها و ایمنی نقشه —")
    ver = c.post(f"/api/workflow/templates/{wf['workflow']['id']}/version",
                 json={}).get_json()["data"]
    check("ساخت نسخه جدید از نقشه", ver["version"] == 2, str(ver["version"]))
    check("نسخه جدید همه‌ی گره‌ها را دارد",
          ver["node_count"] == len(nodes) + 1, str(ver["node_count"]))
    check("نسخه جدید پیش‌فرض فعال نیست", ver["is_active"] is False)
    running = detail(kahani, aid)
    check("فرایند در جریان روی نسخه‌ی خودش می‌ماند",
          running["template_version"] == 1, str(running["template_version"]))
    # Redrawing must not move a run that is already going.
    rr = c.delete(f"/api/workflow/nodes/{nodes['review']['id']}")
    check("گره‌ای که سابقه دارد حذف نمی‌شود، از نقشه برداشته می‌شود",
          rr.status_code == 200 and "سابقه" in (rr.get_json().get("message") or ""),
          str(rr.get_json().get("message"))[:40])
    still = detail(bozorg, seen)
    check("و در فرایندهای قبلی همچنان دیده می‌شود",
          any(n["key"] == "review" for n in still["map"]["nodes"]))
    check("با عنوان و داده‌های خودش",
          any(b["node_key"] == "review" for b in still.get("summary") or []))
    rr = c.delete(f"/api/workflow/templates/{wf['workflow']['id']}")
    check("فرایندی که اجرا داشته حذف نمی‌شود، بایگانی می‌شود",
          rr.status_code == 200
          and (rr.get_json().get("data") or {}).get("status") == "archived",
          str((rr.get_json().get("data") or {}).get("status")))
    c.put(f"/api/workflow/templates/{wf['workflow']['id']}",
          json={"status": "published", "is_active": True})

    print("\n— فرایند: یک فرایند کاملاً تازه، بدون یک خط کد —")
    fresh_wf = c.post("/api/workflow/templates", json={
        "name": "درخواست مرخصی", "code": "leave"}).get_json()["data"]
    fresh = c.get(f"/api/workflow/definition?workflow_id={fresh_wf['id']}"
                  ).get_json()["data"]
    fnodes = {n["key"]: n for n in fresh["graph"]["nodes"]}
    check("فرایند تازه با گره شروع و پایان ساخته می‌شود",
          {"start", "end"} <= set(fnodes), str(sorted(fnodes)))
    mid = c.post("/api/workflow/nodes", json={
        "workflow_id": fresh_wf["id"], "node_type": "phase",
        "title": "بررسی کارگزینی", "x": 300, "y": 200}).get_json()["data"]
    c.post("/api/workflow/edges", json={"source_id": fnodes["start"]["id"],
                                        "target_id": mid["id"]})
    c.post("/api/workflow/edges", json={"source_id": mid["id"],
                                        "target_id": fnodes["end"]["id"]})
    c.put(f"/api/workflow/nodes/{fnodes['start']['id']}", json={
        "principals": [{"role": "assignee", "kind": "user",
                        "user_id": owners["kahani"]}]})
    c.put(f"/api/workflow/nodes/{mid['id']}", json={
        "principals": [{"role": "assignee", "kind": "user",
                        "user_id": owners["bozorg"]}]})
    c.put(f"/api/workflow/templates/{fresh_wf['id']}",
          json={"status": "published", "is_active": True})
    opts = kahani.get("/api/workflow/inbox").get_json().get("start_options") or []
    check("فرایند تازه در فهرست «شروع فرایند» می‌آید",
          any(o["code"] == "leave" for o in opts), str(opts))
    rr = kahani.post("/api/workflow/instances",
                     json={"workflow_code": "leave", "data": {}})
    check("و بدون هیچ تغییری در کد اجرا می‌شود", rr.status_code == 200,
          str(rr.get_json().get("error")))
    lid = rr.get_json()["data"]["id"]
    ldet = detail(bozorg, lid)
    check("فرایند تازه هیچ چاهی لازم ندارد", ldet["well"] is None,
          str(ldet["well"]))
    check("و کار به متولی گره میانی می‌رسد", ldet["current_node"] == mid["key"],
          str(ldet["current_node"]))
    send(bozorg, lid, mid["key"], {})
    ldet = detail(bozorg, lid)
    check("و تا پایان می‌رود", ldet["status"] == "completed", ldet["status"])
    check("بدون ساختن رکورد — چون گره اقدامی ندارد",
          ldet["record_id"] is None, str(ldet["record_id"]))

    print("\n— فرایند: مرکز مستندات —")
    listing = kahani.get("/api/workflow/attachments").get_json()
    check("فهرست مستندات برای متولی باز است", listing.get("ok") is True)
    docs = listing.get("data") or []
    check("مستند بارگذاری‌شده در فهرست هست",
          any(d["filename"] == "gozaresh.pdf" for d in docs), str(len(docs)))
    if docs:
        one = next(d for d in docs if d["filename"] == "gozaresh.pdf")
        check("فرایند و چاه مستند مشخص است",
              bool(one.get("instance_id")) and bool(one.get("well")),
              f"{one.get('instance_id')} / {one.get('well')}")
        check("فاز بارگذاری مشخص است", one.get("stage_title") is not None,
              str(one.get("stage_title")))
        check("دانلود از مرکز مستندات کار می‌کند",
              kahani.get(one["url"]).status_code == 200)
    check("جستجوی مستند با نام فایل",
          len((kahani.get("/api/workflow/attachments?q=gozaresh")
               .get_json().get("data") or [])) >= 1)
    check("مدیر هم همه‌ی مستندات را می‌بیند",
          c.get("/api/workflow/attachments").get_json().get("ok") is True)

    print("\n— فرایند: مقادیر «قبلی» —")
    prev = c.get("/api/workflow/previous?well=" + quote("امام رضا 11")).get_json()["data"]
    check("مقادیر قبلی از آخرین عملیات خوانده می‌شود",
          prev["values"].get("motor_prev") == "73", str(prev["values"]))
    check("تاریخ نصب قبلی شمسی است",
          str(prev["values"].get("prev_install_date", "")).startswith("14"),
          str(prev["values"].get("prev_install_date")))
    check("منبع مقادیر قبلی اعلام می‌شود", bool(prev["source"]))
    # A well with no history is not a broken prefill; the page must be able to
    # tell the two apart, which it does from an empty values map.
    with app.app_context():
        from app.models import Well
        from app.extensions import db as _db
        fresh_well = Well(name="چاه بدون سابقه", is_active=True, is_verified=True)
        _db.session.add(fresh_well); _db.session.commit()
        fresh_id = fresh_well.id
    empty = c.get(f"/api/workflow/previous?well_id={fresh_id}").get_json()["data"]
    check("چاه بدون سابقه مقادیر قبلی ندارد", not (empty.get("values") or {}),
          str(empty))
    check("و منبعی هم اعلام نمی‌شود", not empty.get("source"))

    print("\n— فرایند: گزینه‌های قفل‌شده —")
    with app.app_context():
        from app.models import LookupItem
        from app.services.lookups import get_category
        cat = get_category("failure_reason")
        locked = LookupItem.query.filter_by(category_id=cat.id,
                                            value="جمع آوری").one()
    check("«جمع آوری» به علت خرابی اضافه شده و قفل است", locked.is_locked)
    rr = c.delete(f"/api/lookups/item/{locked.id}")
    check("گزینه قفل‌شده حذف نمی‌شود", rr.status_code == 409)
    rr = c.put(f"/api/lookups/item/{locked.id}", json={"is_active": False})
    check("گزینه قفل‌شده غیرفعال نمی‌شود", rr.status_code == 409)
    rr = c.put(f"/api/lookups/item/{locked.id}", json={"label": "جمع‌آوری چاه"})
    check("ولی برچسبش قابل تغییر است", rr.status_code == 200)
    print("\n— ترتیب تب‌ها —")
    check("صفحه اصلی، ثبت اطلاعات است",
          b"page-mode" in c.get("/", follow_redirects=True).data)
    check("داشبورد روی /dashboard است", c.get("/dashboard").status_code == 200)

    print("\n— شبکه —")
    from app.services.network import lan_addresses, port_is_free, primary_lan_ip
    check("تشخیص IP", bool(primary_lan_ip()))
    check("فهرست آدرس‌های شبکه", len(lan_addresses()) >= 1, str(lan_addresses()))
    check("بررسی آزاد بودن پورت", isinstance(port_is_free("0.0.0.0", 59999), bool))

    shutil.rmtree(tmp, ignore_errors=True)
    print("\n" + "=" * 60)
    print(f"  PASSED {len(PASS)}   FAILED {len(FAIL)}")
    if FAIL:
        for name in FAIL:
            print("   ✗ " + name)
    print("=" * 60)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
