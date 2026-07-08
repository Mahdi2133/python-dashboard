"""ساخت جدول جدید well_permits (وضعیت پروانه).

این اسکریپت فقط جدول‌های تعریف‌شده‌ای را که هنوز در دیتابیس نیستند می‌سازد و
به جدول‌ها و داده‌های موجود دست نمی‌زند. پس از کپی فایل‌های بخش پروانه، یک‌بار
اجرا کنید:

    python setup_permit_table.py
"""
from app import create_app
from app.extensions import db
# اطمینان از اینکه مدل پروانه شناخته می‌شود
from app.models.permit import WellPermit  # noqa: F401

app = create_app()
with app.app_context():
    before = set(db.inspect(db.engine).get_table_names())
    db.create_all()
    after = set(db.inspect(db.engine).get_table_names())
    new = after - before
    if "well_permits" in after:
        if new:
            print("جدول‌های جدید ساخته شد:", ", ".join(sorted(new)))
        else:
            print("جدول well_permits از قبل وجود داشت — تغییری لازم نبود.")
        print("✓ آماده است. حالا می‌توانید داده‌ی پروانه را وارد کنید.")
    else:
        print("✗ ساخت جدول well_permits ناموفق بود.")
