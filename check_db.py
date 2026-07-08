import sqlite3
c = sqlite3.connect("instance/water.db")
tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print("production_trend وجود دارد؟", "production_trend" in tables)
print("تعداد کل جدول‌ها:", len(tables))
print("جدول‌های شامل production یا permit:")
for t in tables:
    if "production" in t or "permit" in t:
        print("  -", t)