"""پر کردن اولیه‌ی انبار قطعات کارگاه مکانیک.
اجرا:  python seed_mechanic_parts.py
"""
from app import create_app
from app.extensions import db
from app.models.mechanic_part import MechanicPart

MOTOR_PARTS = [
    'پیچ دو سر رزوه واسطه', 'مهره', 'کوپلینگ', 'پیچ کوپلینگ', 'پیچ ورودی آب',
    'قطعه اتصال دهنده', 'شنگیر', 'بوش کاسه نمد', 'کاسه نمد', 'بلبرینگ',
    'بلبرینگ کف گرد', 'وایر', 'سیم پیچ', 'استاتور', 'روتور', 'شفت',
    'بوش سر یاتاقان', 'یاتاقان', 'پیستون', 'رینگ', 'دیافراگم', 'محفظه روغن',
    'واشر', 'اورینگ', 'پوسته موتور', 'درپوش بالا', 'درپوش پایین', 'ترمینال',
    'کابل موتور', 'مادگی کابل', 'نری کابل', 'لاستیک آب بند', 'فیلتر',
    'پروانه خنک کننده', 'بست', 'گلند', 'صفحه مشخصات', 'پیچ ارت', 'خار', 'فنر',
]
PUMP_PARTS = [
    'مهره سوپاپ', 'میل چتری سوپاپ', 'بدنه سوپاپ', 'فنر سوپاپ', 'چتری سوپاپ',
    'رینگ لاستیکی سوپاپ', 'رینگ آلیاژی سوپاپ', 'مهره 12', 'پروانه', 'دیفیوزر',
    'بوش بین طبقه', 'بوش نتراست', 'واشر پروانه', 'خار پروانه', 'شفت پمپ',
    'کوپلینگ پمپ', 'صافی', 'کاسه نمد پمپ', 'بلبرینگ پمپ', 'رینگ سایشی',
    'طبقه پمپ', 'کاسه پمپ', 'مهره شفت', 'واشر فلزی', 'پیچ اتصال', 'لاستیک بند',
]

app = create_app()

with app.app_context():
    added = 0
    skipped = 0
    for eq, names in [("موتور", MOTOR_PARTS), ("پمپ", PUMP_PARTS)]:
        for name in names:
            exists = db.session.scalar(
                db.select(MechanicPart).filter_by(equipment=eq, part_name=name))
            if exists:
                skipped += 1
                continue
            p = MechanicPart(equipment=eq, part_name=name,
                             total_count=0, usable=0, scrap=0, new_count=0, repaired=0)
            db.session.add(p)
            added += 1
    db.session.commit()
    print(f"✓ انبار قطعات پر شد: {added} قطعه‌ی جدید اضافه شد، {skipped} قطعه از قبل بود.")