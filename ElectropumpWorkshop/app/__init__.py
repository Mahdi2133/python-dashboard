"""Application factory for the Electropump Workshop Management System."""
from __future__ import annotations

import logging
import os
import sqlite3

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

    # The migration tooling needs an app whose database has NOT been created
    # yet, so `flask db migrate` can diff the models against an empty schema.
    if os.environ.get("ELECTROPUMP_SKIP_BOOTSTRAP") != "1":
        from .services.bootstrap import ensure_database
        with app.app_context():
            ensure_database(app)

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
