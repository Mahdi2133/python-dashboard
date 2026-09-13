# سامانه مدیریت کارگاه الکتروپمپ

**Electropump Workshop Management System** — یک وب‌اپلیکیشن محلی (Local Web Application)
برای ثبت، گزارش‌گیری و مدیریت روتین کارگاه الکتروپمپ.
روی یک رایانه/سرور سازمانی اجرا می‌شود و بقیه‌ی کاربران شبکه فقط با **مرورگر** به آن وصل می‌شوند.

```
             Company Network
                    │
          ┌─────────┴─────────┐
      PC User 1           PC User 2
       Chrome              Firefox
          └─────────┬─────────┘
                Server PC
          ElectropumpWorkshop.exe
                  Flask
                  SQLite
             instance/wells.db
```

روی رایانه‌های کاربر **هیچ نرم‌افزاری نصب نمی‌شود** — نه پایتون، نه Flask، نه SQLite.

---

## ۱. اجرای سریع (نسخه‌ی EXE)

```
dist\
├── ElectropumpWorkshop.exe
├── config.json
├── instance\wells.db      ← با Navicat for SQLite مستقیماً باز می‌شود
├── logs\
├── backups\
└── exports\
```

روی `ElectropumpWorkshop.exe` دابل‌کلیک کنید. خروجی کنسول:

```
================================================================
 ELECTROPUMP WORKSHOP MANAGEMENT SYSTEM
 سامانه مدیریت کارگاه الکتروپمپ
================================================================

Database:
  C:\Users\Mehdi Nasri\Desktop\Water supply\dist\instance\wells.db
  (SQLite — قابل باز کردن مستقیم با Navicat for SQLite)

Server running:
  http://127.0.0.1:5050

Other PCs on the same network:
  http://10.176.5.200:5050

Keep this window open.
Press Ctrl+C to stop the server.
================================================================
```

* مرورگر پیش‌فرض خودکار باز می‌شود (اگر از قبل باز باشد فقط یک تب جدید اضافه می‌شود).
* **IP شبکه hardcode نشده** و در هر اجرا از کارت شبکه خوانده می‌شود.
* این پنجره باید باز بماند؛ بستن آن سرور را متوقف می‌کند.

### دسترسی سایر رایانه‌ها
در Chrome یا Firefox آدرس `http://<IP سرور>:5050` را باز کنید.
آدرس دقیق در همان پنجره‌ی کنسول و نیز در صفحه‌ی **تنظیمات ← اطلاعات سیستم** نمایش داده می‌شود.

### فایروال ویندوز
اگر رایانه‌های دیگر وصل نشدند، در اولین اجرا برنامه خودش این پیام را می‌دهد:

```
[!] Network access may be blocked by Windows Firewall.
```

راه‌حل (بدون تغییر خودکار و خطرناک در فایروال):
1. **Windows Defender Firewall → Allow an app through firewall** و مجاز کردن
   `ElectropumpWorkshop.exe` برای شبکه‌ی **Private**؛ یا
2. در PowerShell با دسترسی Administrator:
   ```powershell
   netsh advfirewall firewall add rule name="ElectropumpWorkshop" ^
         dir=in action=allow protocol=TCP localport=5050
   ```

---

## ۲. تنظیمات — `config.json`

فایل کنار EXE قرار دارد و بدون تغییر کد قابل ویرایش است:

```json
{
    "host": "0.0.0.0",
    "port": 5050,
    "open_browser": true,
    "threads": 16,
    "database_filename": "wells.db",
    "database_path": "",
    "log_level": "INFO",
    "backup_keep": 30
}
```

| کلید | توضیح |
|---|---|
| `host` | `0.0.0.0` یعنی روی همه‌ی کارت‌های شبکه گوش می‌دهد (لازم برای دسترسی شبکه). `127.0.0.1` فقط همان رایانه. |
| `port` | پیش‌فرض **۵۰۵۰** (عمداً پورت پیش‌فرض Flask یعنی ۵۰۰۰ استفاده نشده). |
| `database_path` | خالی = `instance/wells.db` کنار EXE. می‌توانید مسیر مطلق دیگری بدهید (مثلاً درایو مشترک پشتیبان‌گیری‌شده). |
| `backup_keep` | تعداد پشتیبان‌هایی که نگه داشته می‌شود. |

پس از تغییر، برنامه را دوباره اجرا کنید.

---

## ۳. پایگاه داده

* موتور: **SQLite**، فایل: `instance/wells.db`
* **بیرون از EXE** — جایگزینی یا حذف EXE هیچ داده‌ای را از بین نمی‌برد.
* در Startup: اگر فایل وجود داشته باشد به همان وصل می‌شود؛ اگر نباشد ساخته می‌شود.
  **هرگز روی پایگاه داده‌ی موجود، پایگاه داده‌ی جدید ساخته نمی‌شود.**
* برای محیط چندکاربره فعال است: `journal_mode=WAL`، `busy_timeout=15000`،
  `foreign_keys=ON`، `synchronous=NORMAL`.
* مسیر فایل در **تنظیمات ← اطلاعات سیستم** و در کنسول نمایش داده می‌شود.

### باز کردن با Navicat
Navicat for SQLite → New Connection → SQLite → Existing Database File →
انتخاب `dist\instance\wells.db`.

---

## ۴. ماژول‌ها

| بخش | توضیح |
|---|---|
| **داشبورد** | ۸ کارت شاخص و ۱۰ نمودار، مستقیماً از پایگاه داده، با فیلتر تاریخ/مرکز/عملیات. |
| **ثبت اطلاعات** | همان ۸ بخش و ۵۱ فیلد فرم اصلی، به‌علاوه‌ی فیلدهای برگرفته از اکسل واقعی. ساختار از «فرم‌ساز» خوانده می‌شود. |
| **رکوردها** | جستجو، فیلتر، مرتب‌سازی و صفحه‌بندی **سمت سرور**؛ مشاهده، ویرایش، غیرفعال‌سازی و بازیابی. |
| **چاه‌ها** | مدیریت جدول `wells`، تأیید چاه‌های واردشده از اکسل و **ادغام** نام‌های تکراری. |
| **گزارش‌ها** | ۱۴ گزارش خواسته‌شده + ۳ گزارش تکمیلی، همه با خروجی Excel/CSV/JSON/PDF/چاپ. |
| **گزارش‌ساز** | Dataset ← Fields ← Filters ← Grouping ← Sorting ← Aggregation. |
| **فرم‌ساز** | مدیریت بخش‌ها و فیلدها با ۱۰ نوع فیلد. |
| **مدیریت گزینه‌ها** | افزودن/ویرایش/مرتب‌سازی/فعال‌سازی گزینه‌ها + **نام‌های مستعار** برای نرمال‌سازی املاها. |
| **ورود / خروج داده** | Wizard ورود اکسل، انتقال از `localStorage`، خروجی خام. |
| **تنظیمات** | اطلاعات سیستم، پشتیبان‌گیری/بازیابی، Audit Log، مشاهده‌ی `logs/app.log`. |

### گزارش‌های آماده
۱ کلی کارگاه · ۲ بازه زمانی · ۳ ماهانه · ۴ سالانه · ۵ نوع عملیات · ۶ خرابی ·
۷ پیمانکار · ۸ مرکز · ۹ پمپ · ۱۰ الکتروموتور · ۱۱ چاه · ۱۲ تکرار خرابی ·
۱۳ تست پمپاژ · ۱۴ مقایسه‌ی طراحی و تست — به‌علاوه‌ی سازنده، نظر کارگاه و مجری.

---

## ۵. تقویم شمسی

* تمام فیلدهای تاریخی Date Picker شمسی، RTL، با ماه‌ها و روزهای فارسی دارند
  (بدون هیچ کتابخانه‌ی خارجی).
* **استاندارد ذخیره‌سازی:** تاریخ‌ها در پایگاه داده به‌صورت **میلادی ISO** (`op_date`)
  ذخیره می‌شوند و اجزای شمسی واردشده (`j_year/j_month/j_day`) نیز در کنار آن نگه داشته می‌شوند،
  تا تاریخ ناقصِ واردشده از اکسل قدیمی «اصلاح» نشود. رابط کاربری همیشه شمسی است.
* الگوریتم تبدیل (Borkowski) با الگوریتم سمت سرور یکسان است و برای سال‌های
  ۱۱۷۸ تا ۱۴۹۹ رفت‌وبرگشت بدون خطا تست شده است.

---

## ۶. ورود داده از اکسل

**ورود / خروج داده ← ورود از اکسل**

1. بارگذاری `.xls` / `.xlsx`
2. انتخاب شیت
3. **تشخیص خودکار سرستون‌ها** — سرستون‌های دوسطحی و سه‌سطحی
   (گروه «موتور»/«پمپ» بالای زیرعنوان‌ها) پشتیبانی می‌شوند و ستون‌های هم‌نام
   مثل دو «پلاک» بر اساس گروهشان از هم تفکیک می‌گردند.
4. اصلاح دستی نگاشت ستون‌ها
5. **بررسی آزمایشی (Dry-run)** بدون ذخیره
6. اجرای نهایی با تشخیص رکورد تکراری

رفتار در برابر داده‌ی ناسالم — هیچ داده‌ای دور ریخته نمی‌شود:

| وضعیت | رفتار |
|---|---|
| مقدار خارج از فهرست گزینه‌ها | گزینه‌ی «خودکار» غیرفعال ساخته می‌شود و برای بازبینی در «مدیریت گزینه‌ها» نشان‌دار می‌گردد |
| املای متفاوت (سعدابادی / سعد ابادی) | از طریق جدول نام‌های مستعار به گزینه‌ی صحیح نگاشت می‌شود |
| نام چاه ناشناخته | چاه «تأییدنشده» ساخته می‌شود؛ در «چاه‌ها» قابل تأیید یا ادغام است |
| متن در ستون عددی («نامعلوم») | آن ستون خالی ثبت و یک **هشدار** گزارش می‌شود؛ بقیه‌ی سطر ثبت می‌گردد |
| تاریخ ناقص | سطر ثبت می‌شود و کمبود تاریخ هشدار داده می‌شود |
| سال آینده (اشتباه تایپی منبع) | ثبت می‌شود و هشدار داده می‌شود — تصحیح خودکار انجام **نمی‌شود** |

### انتقال از نسخه‌ی قبلی (`localStorage`)
**ورود / خروج داده ← انتقال از localStorage** — دکمه‌ی «خواندن از این مرورگر»
کلید `electropump_records_v1` را پیدا می‌کند، یا JSON آن را دستی بچسبانید.

---

## ۷. پشتیبان و بازیابی

* **تنظیمات ← پشتیبان‌گیری**
* نام فایل: `wells_backup_1405-06-22_143000.db`
* از API رسمی `sqlite3.backup` استفاده می‌شود، بنابراین حتی هنگام کار سایر
  کاربران، فایل خروجی سالم است. خروجی یک فایل مستقل است (بدون `-wal`/`-shm`).
* **بازیابی** ابتدا فایل را اعتبارسنجی می‌کند (integrity check + وجود جداول سامانه)
  و پیش از جایگزینی، یک نسخه‌ی ایمنی `wells_prerestore_*.db` می‌سازد.

---

## ۸. اجرا در محیط توسعه

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt

set FLASK_APP=wsgi.py
.venv/Scripts/python.exe -m flask db upgrade     # ساخت اسکیما
.venv/Scripts/python.exe run.py                  # http://127.0.0.1:5050
```

دستورهای مدیریتی:

```bash
flask seed-db                      # درج داده‌های مرجع
flask import-xls "1.xls"           # ورود همه‌ی شیت‌های یک فایل
flask import-xls "1.xls" --sheet 1405
flask backup-db                    # پشتیبان
```

### ساخت EXE

```
build_exe.bat
```

اسکریپت محیط مجازی می‌سازد، کتابخانه‌ها را نصب می‌کند، با PyInstaller بیلد می‌گیرد و
`dist/` را می‌چیند. **پایگاه داده‌ی موجود در `dist/instance/` هرگز بازنویسی نمی‌شود.**

---

## ۹. ساختار پروژه

```
ElectropumpWorkshop/
├── app/
│   ├── __init__.py          app factory، PRAGMAهای SQLite، مدیریت خطا
│   ├── paths.py             مسیر خارجی پایگاه داده و config.json
│   ├── extensions.py        db / migrate / csrf
│   ├── logging_setup.py     logs/app.log
│   ├── models/              lookup · well · record · formbuilder · audit
│   ├── routes/              pages + ۸ بلوپرینت API
│   ├── services/            jalali · lookups · records · importer · exporter
│   │                        · backup · network · seed · audit · bootstrap
│   ├── reports/             registry (۱۷ گزارش) · builder (گزارش‌ساز)
│   ├── templates/           ۱۳ قالب Jinja2
│   └── static/              css · js · fonts (Vazirmatn محلی) · img
├── migrations/              Alembic
├── instance/wells.db        ← پایگاه داده (خارج از EXE)
├── logs/ backups/ exports/
├── docs/ANALYSIS.md         تحلیل فاز ۱ (HTML و Excel)
├── config.json  run.py  wsgi.py  requirements.txt
├── electropump.ico  build_exe.bat  ElectropumpWorkshop.spec
```

---

## ۱۰. API

| مسیر | کاربرد |
|---|---|
| `GET/POST /api/records`, `GET/PUT/DELETE /api/records/<id>` | رکوردها (صفحه‌بندی سمت سرور) |
| `POST /api/records/<id>/restore` | بازیابی رکورد غیرفعال |
| `GET/POST /api/wells`, `PUT/DELETE /api/wells/<id>`, `POST /api/wells/<id>/merge` | چاه‌ها |
| `GET /api/lookups`, `/api/lookups/<code>`, `PUT /api/lookups/item/<id>` | گزینه‌ها |
| `GET /api/form-builder`, `/sections`, `/fields`, `/reorder` | فرم‌ساز |
| `GET /api/dashboard` | داشبورد |
| `GET /api/reports`, `/api/reports/<key>`, `POST /api/reports/builder` | گزارش‌ها |
| `GET /api/reports/<key>/export.<xlsx\|csv\|json\|pdf>` | خروجی گزارش |
| `GET /api/export.<xlsx\|csv\|json\|pdf>` | خروجی داده خام |
| `POST /api/import/upload`, `GET /api/import/preview`, `POST /api/import/commit` | ورود اکسل |
| `POST /api/import/localstorage` | انتقال از نسخه‌ی قبلی |
| `GET/POST /api/backup`, `POST /api/backup/restore` | پشتیبان |
| `GET /api/system`, `/api/audit`, `/api/logs`, `/api/imports` | سیستم |

---

## ۱۱. امنیت

* **SQL Injection:** تمام کوئری‌ها از طریق SQLAlchemy با پارامتر bind می‌شوند.
  گزارش‌ساز فقط فیلدهای اعلام‌شده در `DATASETS` را می‌پذیرد.
* **CSRF:** روی همه‌ی درخواست‌های تغییردهنده فعال (Flask-WTF).
* **XSS:** خروجی تمام داده‌ها در جاوااسکریپت از `App.esc()` عبور می‌کند.
* **Validation:** نوع، بازه و الزامی بودن هر فیلد از تعریف فرم خوانده می‌شود.
* **Error handling:** هیچ traceback خامی به کاربر نمی‌رسد؛ پیام فارسی + ثبت در `logs/app.log`.
* **Audit log:** ایجاد، ویرایش، حذف، ورود، خروجی، پشتیبان و بازیابی ثبت می‌شوند.
* **آماده برای RBAC:** جدول `users` و ستون `user_id` در `audit_logs` موجود است؛
  ورود اجباری فعلاً غیرفعال است چون سامانه روی شبکه‌ی داخلی سازمان اجرا می‌شود.

> **هشدار استقرار:** این سامانه احراز هویت ندارد. آن را روی شبکه‌ی داخلی و مورد اعتماد
> شرکت اجرا کنید و پورت را روی اینترنت باز نکنید.

---

## ۱۲. بدون وابستگی به اینترنت

هیچ CDN‌ای استفاده نمی‌شود. فونت Vazirmatn (۵ وزن `woff2` + دو `ttf` برای PDF)
و تمام CSS/JS به‌صورت محلی در `app/static/` قرار دارند. نمودارها با CSS خالص
رسم می‌شوند و به کتابخانه‌ی نموداری نیاز ندارند.
