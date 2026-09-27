"""Application factory for the Electropump Workshop Management System."""
from __future__ import annotations

import logging
import os
import sqlite3
from datetime import timedelta

from flask import Flask, jsonify, render_template, request
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.exceptions import HTTPException

from .extensions import csrf, db, migrate
from .logging_setup import configure_logging
from .paths import (app_dir, database_file, database_uri, instance_dir,
                    load_config, resource_dir)

log = logging.getLogger(__name__)


@event.listens_for(Engine, "connect")
def _sqlite_pragmas(dbapi_connection, connection_record):
    """Multi-user hardening for SQLite (requirement 10).

    WAL lets readers run while a writer commits, which is what makes several
    people on the LAN filling the form at the same time workable. The busy
    timeout turns a momentary write lock into a short wait instead of an
    immediate 'database is locked' error, and foreign keys are off by default
    in SQLite so they must be asked for explicitly.
    """
    if dbapi_connection.__class__.__module__.split(".")[0] != "sqlite3":
        return
    cur = dbapi_connection.cursor()
    try:
        # busy_timeout FIRST: switching to WAL needs a brief exclusive lock, so
        # if this connection is opened while another process is reading, the
        # switch must be allowed to wait rather than fail instantly. With the
        # order reversed, a second process attaching to a live database dies
        # with "database is locked".
        cur.execute("PRAGMA busy_timeout=15000")
        try:
            cur.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError as exc:
            # Already WAL, or a reader still holds the file: neither is fatal.
            log.warning("Could not switch journal_mode to WAL: %s", exc)
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA synchronous=NORMAL")
    finally:
        cur.close()


def create_app(config_overrides: dict | None = None) -> Flask:
    cfg = load_config()

    res = resource_dir()
    app = Flask(
        __name__,
        template_folder=str(res / "app" / "templates") if (res / "app" / "templates").exists()
        else "templates",
        static_folder=str(res / "app" / "static") if (res / "app" / "static").exists()
        else "static",
        instance_path=str(instance_dir()),
    )

    app.config.update(
        SECRET_KEY=os.environ.get("ELECTROPUMP_SECRET") or cfg.get("secret_key")
        or "change-me-electropump-workshop",
        SQLALCHEMY_DATABASE_URI=database_uri(cfg),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS={
            # check_same_thread=False is required because waitress serves each
            # request on a worker thread while the pool is shared.
            "connect_args": {"check_same_thread": False, "timeout": 15},
            "pool_pre_ping": True,
        },
        JSON_AS_ASCII=False,
        MAX_CONTENT_LENGTH=64 * 1024 * 1024,
        WTF_CSRF_TIME_LIMIT=None,
        PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        # The system runs on a plain-HTTP company LAN, so the cookie cannot be
        # marked Secure or browsers would drop it and nobody could log in.
        SESSION_COOKIE_SECURE=False,
        AUTH_ENABLED=bool(cfg.get("auth_enabled", True)),
        APP_CONFIG=cfg,
        APP_TITLE=cfg.get("app_title") or "سامانه مدیریت کارگاه الکتروپمپ",
        LOG_LEVEL=cfg.get("log_level", "INFO"),
        DB_FILE=str(database_file(cfg)),
        APP_DIR=str(app_dir()),
    )
    if config_overrides:
        app.config.update(config_overrides)
        if "SQLALCHEMY_DATABASE_URI" in config_overrides:
            app.config["DB_FILE"] = config_overrides["SQLALCHEMY_DATABASE_URI"].replace(
                "sqlite:///", "")

    configure_logging(app)
    if cfg.get("_config_error"):
        app.logger.warning("config.json unreadable, defaults applied: %s", cfg["_config_error"])

    db.init_app(app)
    migrate.init_app(app, db, directory=str(resource_dir() / "migrations"))
    csrf.init_app(app)

    from . import models  # noqa: F401  (register mappers)
    from .routes import register_blueprints
    register_blueprints(app)

    from .services.auth import load_current_user

    @app.before_request
    def _authenticate():
        load_current_user()

    @app.context_processor
    def _inject_user():
        from .services.auth import current_user
        user = current_user()
        return {"CURRENT_USER": user,
                "ALLOWED_PAGES": user.allowed_pages if user else set(),
                "AUTH_ENABLED": app.config["AUTH_ENABLED"]}

    # Stamp every static URL with the file's modification time. An update is
    # installed by copying files over the old ones, and without this a browser
    # keeps running yesterday's script against today's page — the new controls
    # simply never appear until someone clears the cache by hand.
    @app.url_defaults
    def _static_version(endpoint, values):
        if endpoint != "static" or "v" in values or not values.get("filename"):
            return
        try:
            path = os.path.join(app.static_folder, values["filename"])
            values["v"] = int(os.stat(path).st_mtime)
        except OSError:
            pass

    # Which code this process is running, against what is on disk now. An
    # update is copied over the files while the server window may still be
    # open: the browser then gets the new pages and scripts from disk, but
    # every request is answered by the old code already loaded — a switch that
    # «does not save», a button that never appears. The pages ask this, and
    # say plainly that the server has to be restarted.
    code_root = os.path.dirname(os.path.abspath(__file__))

    def _code_stamp():
        newest = 0.0
        for folder, _dirs, files in os.walk(code_root):
            if "__pycache__" in folder:
                continue
            for name in files:
                if name.endswith((".py", ".html")):
                    try:
                        newest = max(newest, os.stat(os.path.join(folder, name)).st_mtime)
                    except OSError:
                        pass
        return newest

    started_with = _code_stamp()

    @app.get("/api/build")
    def _build_info():
        from flask import jsonify
        on_disk = _code_stamp()
        return jsonify({"ok": True, "data": {
            "started_with": int(started_with), "on_disk": int(on_disk),
            "stale": on_disk > started_with + 1}})

    # The migration tooling needs an app whose database has NOT been created
    # yet, so `flask db migrate` can diff the models against an empty schema.
    if os.environ.get("ELECTROPUMP_SKIP_BOOTSTRAP") != "1":
        from .services.bootstrap import ensure_database
        with app.app_context():
            ensure_database(app)

    # Reports read live data through a cache keyed on a data version; any
    # write to reported-on tables bumps it. Scheduled reports run on a worker.
    from .analytics.catalogue import install_change_listener
    from .analytics.jobs import start_worker
    install_change_listener()
    start_worker(app)

    _register_error_handlers(app)
    _register_cli(app)

    from .services.jalali import to_jalali_str
    app.jinja_env.filters["jalali"] = to_jalali_str
    app.jinja_env.globals["APP_TITLE"] = app.config["APP_TITLE"]

    return app


def _wants_json() -> bool:
    return (
        request.path.startswith("/api/")
        or request.accept_mimetypes.best == "application/json"
        or request.is_json
    )


def _register_error_handlers(app: Flask) -> None:
    """No raw Python traceback ever reaches the user (requirement 39)."""

    messages = {
        400: "درخواست نامعتبر است.",
        403: "دسترسی به این بخش مجاز نیست.",
        404: "صفحه یا رکورد موردنظر یافت نشد.",
        405: "این عملیات روی این آدرس مجاز نیست.",
        413: "حجم فایل ارسالی بیش از حد مجاز است.",
        500: "خطای داخلی سرور. جزئیات در فایل logs/app.log ثبت شد.",
    }

    @app.errorhandler(HTTPException)
    def _http_error(exc: HTTPException):
        msg = messages.get(exc.code, exc.description or "خطایی رخ داد.")
        app.logger.info("HTTP %s on %s: %s", exc.code, request.path, exc.description)
        if _wants_json():
            return jsonify({"ok": False, "error": msg, "code": exc.code}), exc.code
        return render_template("error.html", code=exc.code, message=msg), exc.code

    @app.errorhandler(SQLAlchemyError)
    def _db_error(exc: SQLAlchemyError):
        db.session.rollback()
        app.logger.exception("Database error on %s", request.path)
        msg = "خطا در پایگاه داده. عملیات انجام نشد و تغییری ذخیره نگردید."
        if "database is locked" in str(exc).lower():
            msg = ("پایگاه داده در حال حاضر توسط کاربر دیگری در حال نوشتن است. "
                   "لطفاً چند لحظه بعد دوباره تلاش کنید.")
        if _wants_json():
            return jsonify({"ok": False, "error": msg}), 500
        return render_template("error.html", code=500, message=msg), 500

    @app.errorhandler(Exception)
    def _unhandled(exc: Exception):
        db.session.rollback()
        app.logger.exception("Unhandled error on %s", request.path)
        msg = "خطای پیش‌بینی‌نشده. جزئیات در فایل logs/app.log ثبت شد."
        if _wants_json():
            return jsonify({"ok": False, "error": msg}), 500
        return render_template("error.html", code=500, message=msg), 500


def _register_cli(app: Flask) -> None:
    import click

    @app.cli.command("seed-db")
    @click.option("--force", is_flag=True, help="حتی اگر داده موجود است، دوباره اجرا شود")
    def seed_db(force):
        """درج داده‌های مرجع (چاه‌ها، گزینه‌ها، ساختار فرم)."""
        from .services.seed import seed_all
        result = seed_all(force=force)
        click.echo(f"seed: {result}")

    @app.cli.command("import-xls")
    @click.argument("path")
    @click.option("--sheet", default=None)
    def import_xls(path, sheet):
        """وارد کردن یک فایل اکسل روتین کارگاه."""
        from .services.importer import import_workbook
        res = import_workbook(path, sheet_names=[sheet] if sheet else None)
        click.echo(res)

    @app.cli.command("backup-db")
    def backup_db():
        """تهیه پشتیبان از پایگاه داده."""
        from .services.backup import create_backup
        click.echo(create_backup()["filename"])
