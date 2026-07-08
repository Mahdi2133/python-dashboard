"""ارتقای دیتابیس برای دسته ۵ (مدیریت کاربران).

ستون‌های جدید جدول users را اضافه می‌کند و جدول login_logs را می‌سازد.
چون launcher دستور مهاجرت را اجرا نمی‌کند، این اسکریپت مثل import‌ها
مستقیماً و امن اجرا می‌شود (فقط چیزهای نبوده را می‌سازد).

اجرا:  python upgrade_users_db.py
"""
from sqlalchemy import text

from app import create_app
from app.extensions import db

NEW_USER_COLS = {
    "first_name": "VARCHAR(60)",
    "last_name": "VARCHAR(60)",
    "national_id": "VARCHAR(10)",
    "personnel_code": "VARCHAR(30)",
    "position": "VARCHAR(120)",
    "phone": "VARCHAR(20)",
    "notes": "TEXT",
    "last_login_at": "DATETIME",
    "last_login_ip": "VARCHAR(50)",
    "last_login_agent": "VARCHAR(255)",
}


def run():
    app = create_app()
    with app.app_context():
        existing = {row[1] for row in db.session.execute(text("PRAGMA table_info(users)"))}
        added = 0
        for col, typ in NEW_USER_COLS.items():
            if col not in existing:
                db.session.execute(text(f"ALTER TABLE users ADD COLUMN {col} {typ}"))
                added += 1
        db.session.commit()
        db.create_all()   # جدول login_logs را می‌سازد
        print(f"✓ تمام شد: {added} ستون جدید به users اضافه شد، جدول login_logs آماده است.")


if __name__ == "__main__":
    run()
