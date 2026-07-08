# سامانه جامع مدیریت چاه‌های آب شرب

سیستم مدیریت چرخه‌ی عمر چاه‌های آب شرب (حفاری، آزمایش پمپاژ، انتخاب پمپ، نصب، بهره‌برداری، نگهداری، بهسازی، جابه‌جایی، چاه‌نگاری).

اسناد طراحی: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) و [docs/DATA_MODEL.md](docs/DATA_MODEL.md).

## وضعیت: فاز ۰ (زیرساخت) ✅
- app factory، پیکربندی، افزونه‌ها
- مدل‌های پایه: کاربر/نقش/مجوز (RBAC)، واحد سازمانی، چاه + شناسه‌ها
- ورود/خروج و کنترل دسترسی (ماژول × عملیات)
- CRUD چاه‌ها و واحدهای سازمانی + داشبورد + نقشه‌ی Leaflet
- مهاجرت Alembic و دستور seed

## اجرا در محیط توسعه (این دستگاه — SQLite، بدون نصب چیزی)

```bash
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements.txt

export FLASK_APP=wsgi.py          # ویندوز PowerShell: $env:FLASK_APP="wsgi.py"
./.venv/Scripts/python.exe -m flask db upgrade      # ساخت اسکیما
./.venv/Scripts/python.exe -m flask seed-db         # کاربر admin و داده‌ی نمونه

./.venv/Scripts/python.exe wsgi.py                  # اجرا روی http://127.0.0.1:5000
```
ورود اولیه: `admin` / `admin` — **حتماً پس از اولین ورود گذرواژه عوض شود.**

## اجرا روی میزبان (تولید — PostgreSQL/PostGIS + LAN)

1. نصب PostgreSQL + افزونه‌ی PostGIS روی PC میزبان و ساخت دیتابیس:
   ```sql
   CREATE DATABASE water_supply;
   \c water_supply
   CREATE EXTENSION IF NOT EXISTS postgis;
   ```
2. تنظیم متغیر محیطی اتصال:
   ```
   DATABASE_URL=postgresql+psycopg2://water_user:password@localhost:5432/water_supply
   ```
3. اجرای مهاجرت و seed، سپس اجرای آفلاین روی شبکه:
   ```bash
   flask db upgrade && flask seed-db
   python launcher.py          # روی 0.0.0.0:5000 — سایر PCها: http://<IP میزبان>:5000
   ```

> **نکته‌ی مکانی:** مختصات به‌صورت ستون‌های عددی (`utm_x/y`, `latitude/longitude`) ذخیره می‌شوند و نقشه با همین‌ها کار می‌کند. ستون مکانی PostGIS (`geom`) و کوئری‌های فضایی در فاز تحلیل مکانی افزوده می‌شوند (ARCHITECTURE.md بخش ۷). نقشه‌ی پایه‌ی آفلاین از فایل `.mbtiles` سرو خواهد شد.

> **هشدار:** دارایی‌های CDN (Bootstrap/Leaflet/فونت) فعلاً برای توسعه از اینترنت بارگیری می‌شوند؛ برای میزبان آفلاین باید در `app/static/vendor/` محلی شوند (مانند سیستم مالی).

## دستورهای مدیریتی
```bash
flask seed-db                 # ساخت مجوزها، نقش مدیر، کاربر admin، واحدهای نمونه
flask sync-permissions        # افزودن مجوزهای ماژول‌های جدید (بدون دست‌زدن به بقیه)
flask db migrate -m "..."     # تولید مهاجرت پس از تغییر مدل‌ها
flask db upgrade              # اعمال مهاجرت‌ها
```

## مهاجرت داده (incremental)
داده‌ی واقعی **تدریجی و هم‌گام با توسعه** وارد می‌شود: داده‌ی پایه الان، و داده‌ی هر رویداد پس از ساخت ماژولش. Importerها idempotent‌اند (upsert) و با هر به‌روزرسانی فایل‌ها قابل اجرای مجددند.
```bash
flask import-wells            # رجیستری چاه‌ها: پایه = تجمیعی (نام+اداره)، مختصات از Borwells
flask import-drilling         # رویدادهای حفاری از Borwells + حفاری.xlsx (لینک به چاه‌ها)
flask import-flow             # دبی‌سنجی از تجمیعی: گروه‌بندی به آزمایش+نقاط کارکرد (تطبیق نام+اداره)
flask import-install          # نصب/کشیدن پمپ + تأمین‌کننده‌ها (تطبیق نام) — مبنای مقایسه تأمین‌کننده
flask import-rehab            # بهسازی (تطبیق نام، دبی قبل/بعد، تاریخ شمسی فشرده)
flask import-pump-test        # آزمایش پمپاژ از حفاری.xlsx (سرآیند هیدرولیک + پله‌ها) — منبع محاسبه‌گر پمپ
flask import-pump-select      # ثبت انتخاب پمپ/مهندسی مجدد (زنجیره‌ی صحت‌سنجی)
flask import-catalog          # بارگذاری کاتالوگ پمپ از pump_data.js (۴۵۸ مدل) — برای محاسبه‌گر انتخاب پمپ
flask reconcile-wells         # گزارش مغایرت هویت چاه بین فایل‌ها (الان و انتها اجرا شود)
flask export-discrepancies --out well_discrepancies.xlsx  # خروجی اکسل مغایرت‌های کد PM
```
**هویت چاه = نام + اداره (نه `pm_code`).** ستون `کد PM` در تجمیعی **خراب** است (یک pm به چند چاه چسبیده — مثلاً `10231155` به ۴۲ چاه). بنابراین:
- چاه با کلید `match_key(نام) + اداره` شناسایی می‌شود؛ `pm_code` فقط وقتی **تمیز** است (یک‌به‌یک) ذخیره می‌شود، وگرنه کلید موقت `W-<hash>` می‌گیرد (`well.display_pm` آن را «—» نشان می‌دهد). همه‌ی مقادیر pm/کلاسه در `well_identifiers` نگه‌داری می‌شوند.
- مختصات **UTM Zone 40N → WGS84** برای نقشه.
- وارد شد: **۸۵۲ چاه** (۳۵۶ دارای مختصات)، ۹+ اداره. تطبیق فرم‌های دبی‌سنجی: ۱۳۶/۱۴۳.
- رویدادهای حفاری: ۲۲۳ رکورد (`source='import:borwells'`)، **تأییدشده/قفل**، چاه‌های چند-حفاری جدا حفظ می‌شوند. idempotency: `(چاه، source، شماره قرارداد، تاریخ استقرار)`.
- **`well_discrepancies.xlsx`**: فهرست مغایرت‌های کد PM برای اصلاح دستی (ستون «کد PM صحیح» را پر و فایل را بازگردانید).
