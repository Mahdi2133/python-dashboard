# -*- coding: utf-8 -*-
"""Entry point for the desktop/server build.

Double-clicking ElectropumpWorkshop.exe runs this: it resolves the external
database, starts the database, serves the app on the LAN with waitress, prints
the console banner, and opens the default browser.
"""
from __future__ import annotations

import logging
import sys
import threading
import time
import webbrowser

from app import create_app
from app.paths import (app_dir, backups_dir, config_path, database_file,
                       load_config, logs_dir)
from app.services.network import lan_addresses, port_is_free, port_reachable

LINE = "=" * 64
log = logging.getLogger("run")


def banner(cfg, db_path, urls, warnings):
    port = cfg.get("port")
    print("\n" + LINE)
    print(" ELECTROPUMP WORKSHOP MANAGEMENT SYSTEM")
    print(" سامانه مدیریت کارگاه الکتروپمپ")
    print(LINE)
    print("\nDatabase:")
    print(f"  {db_path}")
    print("  (SQLite — قابل باز کردن مستقیم با Navicat for SQLite)")
    print("\nServer running:")
    print(f"  http://127.0.0.1:{port}")
    if urls:
        print("\nOther PCs on the same network:")
        for url in urls:
            print(f"  {url}")
    else:
        print("\nNetwork access:")
        print("  آدرس شبکه‌ای شناسایی نشد (کارت شبکه متصل نیست؟)")
    print("\nFolders:")
    print(f"  config : {config_path()}")
    print(f"  logs   : {logs_dir() / 'app.log'}")
    print(f"  backups: {backups_dir()}")
    for warning in warnings:
        print(f"\n[!] {warning}")
    print("\nKeep this window open.")
    print("Press Ctrl+C to stop the server.")
    print(LINE + "\n")


def open_browser_later(url, delay=1.6):
    """Open the browser once the server is actually accepting connections.

    Opening it before the socket is listening gives the user a connection
    error on the very first run, so this waits for the port instead of
    sleeping blindly.
    """
    def worker():
        deadline = time.time() + 15
        while time.time() < deadline:
            if port_reachable("127.0.0.1", int(url.rsplit(":", 1)[1]), 0.3):
                break
            time.sleep(0.3)
        try:
            webbrowser.open(url)
        except Exception:
            log.info("Could not open a browser automatically; open %s manually", url)

    threading.Thread(target=worker, daemon=True).start()


def main() -> int:
    cfg = load_config()
    host = cfg.get("host") or "0.0.0.0"
    port = int(cfg.get("port") or 5050)

    warnings = []
    if cfg.get("_config_error"):
        warnings.append(f"config.json خوانده نشد ({cfg['_config_error']}) — "
                        "مقادیر پیش‌فرض به کار رفت.")
    if not port_is_free(host, port):
        print(f"\n[X] پورت {port} روی این سیستم آزاد نیست.")
        print("    یا نسخه‌ی دیگری از برنامه در حال اجراست، یا برنامه‌ای دیگر پورت را گرفته.")
        print(f"    می‌توانید پورت را در {config_path()} تغییر دهید.")
        return 1

    try:
        app = create_app()
    except Exception as exc:                       # startup must explain itself
        print("\n[X] برنامه اجرا نشد.")
        print(f"    {exc}")
        print(f"    جزئیات کامل در: {logs_dir() / 'app.log'}")
        input("\nبرای بستن این پنجره Enter را بزنید...")
        return 1

    db_path = database_file(cfg)
    ips = lan_addresses()
    urls = [f"http://{ip}:{port}" for ip in ips if ip != "127.0.0.1"]
    if host in ("127.0.0.1", "localhost"):
        warnings.append("host در config.json روی 127.0.0.1 است؛ سایر رایانه‌های شبکه "
                        "نمی‌توانند وصل شوند. برای دسترسی شبکه آن را 0.0.0.0 بگذارید.")
        urls = []

    banner(cfg, db_path, urls, warnings)

    if cfg.get("open_browser", True):
        open_browser_later(f"http://127.0.0.1:{port}")

    # Firewall probe: after the server is up, try to reach it on its own LAN
    # address. Failure almost always means Windows Firewall is blocking it.
    if urls:
        def probe():
            time.sleep(3)
            if not port_reachable(ips[0], port, 1.0):
                print("\n[!] Network access may be blocked by Windows Firewall.")
                print("    دسترسی شبکه احتمالاً توسط فایروال ویندوز مسدود است.")
                print("    لطفاً ElectropumpWorkshop.exe را در شبکه‌ی Private مجاز کنید،")
                print("    یا این دستور را در PowerShell با دسترسی Administrator اجرا نمایید:")
                print(f'    netsh advfirewall firewall add rule '
                      f'name="ElectropumpWorkshop" dir=in action=allow '
                      f'protocol=TCP localport={port}\n')
        threading.Thread(target=probe, daemon=True).start()

    try:
        from waitress import serve
        serve(app, host=host, port=port, threads=int(cfg.get("threads") or 16),
              ident="ElectropumpWorkshop")
    except ImportError:
        log.warning("waitress not installed — falling back to the Flask dev server")
        app.run(host=host, port=port, threaded=True, debug=False)
    except KeyboardInterrupt:
        print("\nسرور متوقف شد.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
