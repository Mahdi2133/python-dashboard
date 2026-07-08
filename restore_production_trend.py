"""بازیابی جدول production_trend که به‌اشتباه توسط migration حذف شده بود.

این اسکریپت جدول را از فایل production_trend_restore.sql دوباره می‌سازد و داده را
برمی‌گرداند. به بقیه‌ی جدول‌ها دست نمی‌زند.

اجرا:  python restore_production_trend.py
"""
import sqlite3
import os

DB = "instance/water.db"
SQL = "production_trend_restore.sql"

if not os.path.exists(DB):
    raise SystemExit(f"دیتابیس پیدا نشد: {DB} — این اسکریپت را در ریشه‌ی پروژه اجرا کنید.")
if not os.path.exists(SQL):
    raise SystemExit(f"فایل SQL پیدا نشد: {SQL} — باید کنار این اسکریپت باشد.")

conn = sqlite3.connect(DB)
with open(SQL, encoding="utf-8") as f:
    script = f.read()

conn.executescript(script)
conn.commit()

n = conn.execute("SELECT count(*) FROM production_trend").fetchone()[0]
ncol = len(conn.execute("PRAGMA table_info(production_trend)").fetchall())
print(f"✓ جدول production_trend بازسازی شد: {n} ردیف، {ncol} ستون.")
conn.close()
