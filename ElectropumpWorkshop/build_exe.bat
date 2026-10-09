@echo off
chcp 65001 >nul
setlocal

echo ============================================================
echo  ساخت فایل اجرایی سامانه مدیریت کارگاه الکتروپمپ
echo  Building ElectropumpWorkshop.exe
echo ============================================================
echo.

cd /d "%~dp0"

REM ── 1. Python check ─────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo [X] Python روی این سیستم پیدا نشد.
    echo     از python.org نسخه 3.10 یا بالاتر را نصب کنید و گزینه
    echo     "Add Python to PATH" را حتما تیک بزنید.
    pause
    exit /b 1
)
python --version

REM ── 2. virtual environment ──────────────────────────────────
if not exist ".venv" (
    echo.
    echo [1/5] ساخت محیط مجازی...
    python -m venv .venv
    if errorlevel 1 ( echo [X] ساخت محیط مجازی ناموفق بود. & pause & exit /b 1 )
) else (
    echo [1/5] محیط مجازی موجود است.
)

set PY=.venv\Scripts\python.exe

REM ── 3. dependencies ─────────────────────────────────────────
echo.
echo [2/5] نصب کتابخانه‌ها...
"%PY%" -m pip install --upgrade pip --quiet
"%PY%" -m pip install -r requirements.txt
if errorlevel 1 (
    echo [X] نصب کتابخانه‌ها ناموفق بود. اتصال اینترنت را بررسی کنید.
    pause
    exit /b 1
)

REM ── 4. clean previous build ─────────────────────────────────
echo.
echo [3/5] پاکسازی خروجی قبلی...
if exist "build" rmdir /s /q "build"
if exist "dist\ElectropumpWorkshop.exe" del /q "dist\ElectropumpWorkshop.exe"

REM ── 5. build ────────────────────────────────────────────────
echo.
echo [4/5] ساخت فایل اجرایی (چند دقیقه طول می‌کشد)...
"%PY%" -m PyInstaller ElectropumpWorkshop.spec --noconfirm --clean
if errorlevel 1 ( echo [X] ساخت EXE ناموفق بود. & pause & exit /b 1 )

REM ── 6. lay out the runtime folder ───────────────────────────
REM The database, config, logs and backups live NEXT TO the EXE, never inside
REM it, so replacing the EXE never destroys data and Navicat can open the file.
echo.
echo [5/5] آماده‌سازی پوشه خروجی...
if not exist "dist\instance" mkdir "dist\instance"
if not exist "dist\logs"     mkdir "dist\logs"
if not exist "dist\backups"  mkdir "dist\backups"
if not exist "dist\exports"  mkdir "dist\exports"

if exist "dist\config.json" (
    echo     config.json موجود است - دست نخورد.
) else (
    copy /y "config.json" "dist\config.json" >nul
)

REM The whole instance folder travels: wells.db, the separate databases in
REM instance\refdata (flow tests, production, videometry, warehouse) and the
REM uploaded documents in instance\attachments. Nothing already in dist is
REM overwritten.
if exist "instance\wells.db" (
    if exist "dist\instance\wells.db" (
        echo     dist\instance\wells.db موجود است - جایگزین نشد.
    ) else (
        echo     کپی پایگاه داده موجود به dist\instance\
        copy /y "instance\wells.db" "dist\instance\wells.db" >nul
    )
) else (
    echo     پایگاه داده در اولین اجرای EXE ساخته می‌شود.
)
if exist "instance\refdata" (
    if exist "dist\instance\refdata" (
        echo     dist\instance\refdata موجود است - جایگزین نشد.
    ) else (
        echo     کپی بانک‌های اطلاعاتی و انبار به dist\instance\refdata\
        xcopy /e /i /q /y "instance\refdata" "dist\instance\refdata" >nul
    )
)
if exist "instance\attachments" (
    if not exist "dist\instance\attachments" (
        echo     کپی مستندات به dist\instance\attachments\
        xcopy /e /i /q /y "instance\attachments" "dist\instance\attachments" >nul
    )
)

echo.
echo ============================================================
echo  ساخت با موفقیت انجام شد.
echo.
echo  dist\
echo    ├── ElectropumpWorkshop.exe
echo    ├── config.json
echo    ├── instance\wells.db      ^<-- با Navicat for SQLite باز می‌شود
echo    ├── instance\refdata\      ^<-- دبی‌سنجی، روند تولید، ویدئومتری، انبار
echo    ├── logs\
echo    ├── backups\
echo    └── exports\
echo.
echo  برای اجرا: روی dist\ElectropumpWorkshop.exe دابل‌کلیک کنید.
echo ============================================================
pause
