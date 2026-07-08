"""Production/offline launcher: serves the app on the LAN via waitress.

Binds 0.0.0.0 so other PCs on the LAN can connect. When frozen by PyInstaller,
resolves bundled resources (templates/static/instance/migrations) from the
temporary extraction dir so pages and the database load correctly.
"""
import os
import sys
import socket


def resource_base():
    """مسیر پایه‌ی فایل‌های همراه: پوشه‌ی موقت اگزه یا پوشه‌ی پروژه."""
    if getattr(sys, "frozen", False):
        # وقتی به‌صورت اگزه اجرا می‌شود
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


BASE = resource_base()

# اپ Flask را با مسیر درست قالب‌ها و استاتیک بساز
from app import create_app

app = create_app()

# مسیر قالب‌ها و استاتیک را به پوشه‌ی همراه اگزه اصلاح کن
app.template_folder = os.path.join(BASE, "app", "templates")
app.static_folder = os.path.join(BASE, "app", "static")
# مسیر دیتابیس داخل بسته
_db_path = os.path.join(BASE, "instance", "water.db")
if os.path.exists(_db_path):
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + _db_path.replace("\\", "/")

HOST = "0.0.0.0"
PORT = 5000


def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


if __name__ == "__main__":
    ip = lan_ip()
    print(f"Water Supply system running:  http://127.0.0.1:{PORT}")
    print(f"Other PCs on the same network:  http://{ip}:{PORT}")
    print("این پنجره را باز نگه دارید. برای بستن سرور Ctrl+C بزنید.")
    try:
        from waitress import serve
        serve(app, host=HOST, port=PORT, threads=12)
    except ImportError:
        app.run(host=HOST, port=PORT)