# -*- coding: utf-8 -*-
"""Backup & restore of wells.db (requirement 28).

``sqlite3.Connection.backup`` is used rather than a file copy: it takes a
consistent snapshot while other users are connected, which a plain copy of a
WAL database cannot promise.
"""
from __future__ import annotations

import datetime as dt
import logging
import shutil
import sqlite3
from pathlib import Path

from ..paths import backups_dir, database_file
from .audit import record_audit
from .jalali import today_jalali

log = logging.getLogger(__name__)


def live_database_path():
    """The file the running app is actually attached to.

    ``paths.database_file()`` is the deployment default, but the app config is
    the authority — a test or an operator override in config.json can point
    somewhere else, and backing up a different file than the one being served
    would be worse than useless.
    """
    from flask import current_app, has_app_context
    if has_app_context():
        uri = current_app.config.get("SQLALCHEMY_DATABASE_URI", "")
        if uri.startswith("sqlite:///"):
            return Path(uri[len("sqlite:///"):])
    return database_file()


def _stamp() -> str:
    jy, jm, jd = today_jalali()
    now = dt.datetime.now()
    return f"{jy}-{jm:02d}-{jd:02d}_{now:%H%M%S}"


def create_backup(note: str | None = None) -> dict:
    source = live_database_path()
    if not source.exists():
        raise FileNotFoundError("فایل پایگاه داده یافت نشد.")
    target = backups_dir() / f"wells_backup_{_stamp()}.db"

    src = sqlite3.connect(str(source))
    dst = sqlite3.connect(str(target))
    try:
        with dst:
            src.backup(dst)
        # The copy inherits WAL from the source, which leaves -wal/-shm files
        # beside it. Switching the copy to a rollback journal collapses it into
        # one self-contained file — easier to hand to Navicat, mail or archive.
        dst.execute("PRAGMA journal_mode=DELETE")
    finally:
        src.close()
        dst.close()
    for suffix in ("-wal", "-shm"):
        stray = target.with_name(target.name + suffix)
        if stray.exists():
            try:
                stray.unlink()
            except OSError:
                log.warning("Could not remove %s", stray)

    _prune()
    record_audit("backup", "database", None,
                 summary=f"تهیه پشتیبان: {target.name}" + (f" — {note}" if note else ""),
                 commit=True)
    log.info("Backup written to %s", target)
    return {"filename": target.name, "path": str(target),
            "size": target.stat().st_size,
            "created_at": dt.datetime.now().isoformat()}


def _prune(keep: int | None = None):
    from ..paths import load_config
    keep = keep or int(load_config().get("backup_keep") or 30)
    files = sorted(backups_dir().glob("wells_backup_*.db"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    for old in files[keep:]:
        try:
            old.unlink()
            log.info("Pruned old backup %s", old.name)
        except OSError:
            log.warning("Could not remove old backup %s", old.name)


def list_backups() -> list:
    out = []
    for path in sorted(backups_dir().glob("wells_backup_*.db"),
                       key=lambda p: p.stat().st_mtime, reverse=True):
        stat = path.stat()
        out.append({"filename": path.name, "size": stat.st_size,
                    "modified": dt.datetime.fromtimestamp(stat.st_mtime).isoformat()})
    return out


def validate_backup(path) -> dict:
    """A restore candidate must be a real SQLite file holding our tables."""
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        return {"valid": False, "reason": f"فایل قابل باز شدن نیست: {exc}"}
    try:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            return {"valid": False, "reason": f"بررسی سلامت فایل ناموفق بود: {integrity}"}
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        required = {"records", "wells", "lookup_items", "form_fields"}
        missing = required - tables
        if missing:
            return {"valid": False,
                    "reason": "این فایل پایگاه داده‌ی این سامانه نیست. "
                              f"جدول‌های موجود نیست: {'، '.join(sorted(missing))}"}
        counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                  for t in sorted(required)}
        return {"valid": True, "tables": len(tables), "counts": counts}
    except sqlite3.Error as exc:
        return {"valid": False, "reason": f"خطا در خواندن فایل: {exc}"}
    finally:
        conn.close()


def restore_backup(source_path) -> dict:
    """Replace the live database, after validating and snapshotting the current one."""
    check = validate_backup(source_path)
    if not check["valid"]:
        raise ValueError(check["reason"])

    target = live_database_path()
    safety = None
    if target.exists():
        safety = backups_dir() / f"wells_prerestore_{_stamp()}.db"
        shutil.copy2(target, safety)

    from ..extensions import db
    db.session.remove()
    db.engine.dispose()          # release the file before overwriting it

    shutil.copy2(source_path, target)
    for suffix in ("-wal", "-shm"):
        stale = target.with_name(target.name + suffix)
        if stale.exists():
            try:
                stale.unlink()
            except OSError:
                log.warning("Could not clear %s", stale)

    # Backups are stored in rollback-journal mode so each is a single file;
    # the *live* database must go back to WAL, otherwise concurrent users on
    # the LAN would start blocking each other after every restore.
    conn = sqlite3.connect(str(target))
    try:
        conn.execute("PRAGMA busy_timeout=15000")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.commit()
    except sqlite3.Error as exc:
        log.warning("Could not restore WAL mode after restore: %s", exc)
    finally:
        conn.close()

    record_audit("db_restore", "database", None,
                 summary=f"بازیابی پایگاه داده از {getattr(source_path, 'name', source_path)}",
                 commit=True)
    log.warning("Database restored from %s (safety copy: %s)", source_path, safety)
    return {"restored": True, "counts": check.get("counts"),
            "safety_copy": safety.name if safety else None}
