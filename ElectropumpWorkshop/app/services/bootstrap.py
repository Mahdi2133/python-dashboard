"""Startup database check (requirement 3).

    instance/wells.db exists?  →  connect to it, never replace it.
    does not exist?           →  create it with the full schema and seed data.

The one thing this must never do is silently make a fresh database on top of
an existing one, so the file is only created when it genuinely is not there,
and an existing file is opened as-is.
"""
import logging

from sqlalchemy import inspect, text

from ..extensions import db
from ..paths import database_file

log = logging.getLogger(__name__)

# Tables that must exist for the app to serve a request at all.
_CORE_TABLES = {"records", "wells", "lookup_categories", "lookup_items",
                "form_sections", "form_fields"}


def ensure_database(app) -> dict:
    path = database_file()
    existed = path.exists() and path.stat().st_size > 0
    status = {"path": str(path), "existed": existed, "created": False, "seeded": False}

    insp = inspect(db.engine)
    tables = set(insp.get_table_names())
    missing = _CORE_TABLES - tables

    if missing:
        # Either a brand-new file, or an older file predating a table. Neither
        # case may drop anything: create_all only adds what is absent.
        log.info("Creating missing tables: %s", ", ".join(sorted(missing)))
        db.create_all()
        status["created"] = True

    from .seed import seed_all
    seeded = seed_all(force=False)
    status["seeded"] = bool(seeded.get("changed"))
    status["seed"] = seeded

    with db.engine.connect() as conn:
        status["journal_mode"] = conn.execute(text("PRAGMA journal_mode")).scalar()
        status["foreign_keys"] = bool(conn.execute(text("PRAGMA foreign_keys")).scalar())

    log.info("Database ready at %s (existed=%s, journal=%s)",
             path, existed, status["journal_mode"])
    return status
