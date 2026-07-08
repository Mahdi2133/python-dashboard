import sqlite3
c = sqlite3.connect("instance/water.db")
cols = [r[1] for r in c.execute("PRAGMA table_info(production_trend)").fetchall()]
# ستون‌های خرداد 1405 را نشان بده
target = [col for col in cols if "1405" in col and ("khordad" in col or "production" in col or "average_flow" in col or "runtime" in col)]
print("ستون‌های مرتبط با 1405:")
for t in target:
    n = c.execute(f'SELECT count(*) FROM production_trend WHERE "{t}" IS NOT NULL').fetchone()[0]
    print(f"  {t}: {n} مقدار پرشده")