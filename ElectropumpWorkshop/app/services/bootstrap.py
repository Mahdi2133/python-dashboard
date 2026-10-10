"""Startup database check (requirement 3).

    instance/wells.db exists?  →  connect to it, never replace it.
    does not exist?           →  create it with the full schema and seed data.

The one thing this must never do is silently make a fresh database on top of
an existing one, so the file is only created when it genuinely is not there,
and an existing file is opened as-is.
"""
import datetime as _dt
import logging
import sqlite3

from sqlalchemy import inspect, text

from ..extensions import db
from ..paths import database_file

log = logging.getLogger(__name__)

# Tables that must exist for the app to serve a request at all.
_CORE_TABLES = {"records", "wells", "lookup_categories", "lookup_items",
                "form_sections", "form_fields"}


# Columns whose foreign key moved from the legacy ``users`` stub to the real
# ``app_users`` table when login was added. SQLite cannot alter a constraint in
# place, so the table has to be rebuilt — but only once, and only if the old
# constraint is actually still there.
_MOVED_FK = {
    "audit_logs": ("user_id", "users", "app_users"),
    "records": ("created_by", "users", "app_users"),
}


# Columns a later release added and this one removed again. ALTER TABLE can
# add a column but never drop one, so a table still carrying one has to be
# rebuilt — and it must be, not merely tidied: the graph release wrote
# `workflow_definitions.version` as NOT NULL with no default, and the model
# that replaced it does not know the column exists, so every INSERT into that
# table fails until it is gone.  table -> (a column only that release had, why)
_REMOVED_COLUMNS = {
    "workflow_definitions": ("version", "process templates are not versioned"),
}


def _rebuild_stale_fk_tables() -> list:
    """Rebuild tables still carrying a foreign key to the old users table.

    Without this, an existing wells.db would reject every audit row the moment
    someone logs in: the row points at an app_users id that the stale
    constraint tries to find in the empty legacy table. The rebuild copies the
    data across, so nothing is lost.

    It runs on a dedicated sqlite3 connection with the pool disposed first —
    SQLite refuses to rename a table or drop its indexes while another
    connection in the pool still has it open, and ``PRAGMA foreign_keys`` is a
    no-op inside a transaction.
    """
    insp = inspect(db.engine)
    tables = set(insp.get_table_names())
    todo = []
    for table, (column, old_target, _new_target) in _MOVED_FK.items():
        if table not in tables or table not in db.metadata.tables:
            continue
        if any(fk.get("referred_table") == old_target
               and column in (fk.get("constrained_columns") or [])
               for fk in insp.get_foreign_keys(table)):
            todo.append((table, [c["name"] for c in insp.get_columns(table)]))
    for table, (column, why) in _REMOVED_COLUMNS.items():
        if table not in tables or table not in db.metadata.tables:
            continue
        present = {c["name"] for c in insp.get_columns(table)}
        if column in present and column not in db.metadata.tables[table].columns:
            log.warning("Rebuilding %s to drop the leftover column %r: %s",
                        table, column, why)
            todo.append((table, sorted(present)))
    if not todo:
        return []

    from sqlalchemy.schema import CreateIndex, CreateTable

    dialect = db.engine.dialect
    plans = []
    for table, existing_cols in todo:
        model_table = db.metadata.tables[table]
        shared = [c.name for c in model_table.columns if c.name in existing_cols]
        plans.append({
            "table": table,
            "columns": ", ".join(f'"{c}"' for c in shared),
            "create": str(CreateTable(model_table).compile(dialect=dialect)),
            "indexes": [str(CreateIndex(i).compile(dialect=dialect))
                        for i in model_table.indexes],
        })

    path = str(database_file())
    db.session.remove()
    db.engine.dispose()

    rebuilt = []
    conn = sqlite3.connect(path, isolation_level=None, timeout=30)
    try:
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA foreign_keys=OFF")
        # Modern SQLite rewrites *other* tables' foreign keys to follow a
        # renamed table, which would leave record_tags pointing at
        # "records__old" once that is dropped. legacy_alter_table turns the
        # rename back into a plain rename, which is what a rebuild needs.
        conn.execute("PRAGMA legacy_alter_table=ON")
        for plan in plans:
            table = plan["table"]
            conn.execute("BEGIN")
            try:
                conn.execute(f'ALTER TABLE "{table}" RENAME TO "{table}__old"')
                # A rename carries the indexes along under their original
                # names, so they must go before the new table recreates them.
                for (index_name,) in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='index' "
                        "AND tbl_name=? AND sql IS NOT NULL",
                        (f"{table}__old",)).fetchall():
                    conn.execute(f'DROP INDEX IF EXISTS "{index_name}"')
                conn.execute(plan["create"])
                for index_sql in plan["indexes"]:
                    conn.execute(index_sql)
                conn.execute(f'INSERT INTO "{table}" ({plan["columns"]}) '
                             f'SELECT {plan["columns"]} FROM "{table}__old"')
                conn.execute(f'DROP TABLE "{table}__old"')
                conn.execute("COMMIT")
                rebuilt.append(table)
                log.warning("Rebuilt %s to match the current models", table)
            except Exception:
                conn.execute("ROLLBACK")
                log.exception("Could not rebuild %s; the original table is intact",
                              table)
        conn.execute("PRAGMA legacy_alter_table=OFF")
        broken = conn.execute("PRAGMA foreign_key_check").fetchall()
        if broken:
            log.error("Foreign key check after rebuild reported %d rows", len(broken))
        conn.execute("PRAGMA foreign_keys=ON")
    finally:
        conn.close()
    return rebuilt


def _default_literal(column):
    """A column's default as a SQL literal, or None when it has no plain one.

    Used to fill in the rows that predate a column: SQLite's ALTER TABLE gives
    them NULL, which is the wrong answer for a column the model declares NOT
    NULL with a default — those rows would read as «تعیین نشده» instead of as
    the default the model promises.
    """
    default = getattr(column.default, "arg", None)
    if default is None or callable(default):
        return None
    if default is True:
        return "1"
    if default is False:
        return "0"
    if isinstance(default, (int, float)):
        return str(default)
    return "'" + str(default).replace("'", "''") + "'"


def _add_missing_columns() -> list:
    """Add columns the models gained since the database file was created.

    ``create_all`` only creates missing *tables*, never missing columns, so an
    EXE that has been running for months against its own ``wells.db`` would
    otherwise break the moment a release adds a field. Copying the DB is not an
    option — it is the customer's live data — so each new column is added in
    place with ALTER TABLE, which SQLite does cheaply and without rewriting
    rows. Only additive changes are handled here; anything structural belongs
    in an Alembic migration.
    """
    added = []
    insp = inspect(db.engine)
    tables = set(insp.get_table_names())
    for table, model in db.Model.registry._class_registry.items():
        if not hasattr(model, "__tablename__"):
            continue
        name = model.__tablename__
        if name not in tables:
            continue
        existing = {c["name"] for c in insp.get_columns(name)}
        for column in model.__table__.columns:
            if column.name in existing:
                continue
            ddl = column.type.compile(dialect=db.engine.dialect)
            try:
                with db.engine.begin() as conn:
                    conn.execute(text(
                        f'ALTER TABLE "{name}" ADD COLUMN "{column.name}" {ddl}'))
                    # SQLite fills the existing rows with NULL, which is wrong
                    # for a column the model declares NOT NULL with a default:
                    # the rows that predate the column would read as «تعیین
                    # نشده» rather than as the default the model promises.
                    backfill = _default_literal(column)
                    if backfill is not None:
                        conn.execute(text(
                            f'UPDATE "{name}" SET "{column.name}" = {backfill} '
                            f'WHERE "{column.name}" IS NULL'))
                added.append(f"{name}.{column.name}")
                log.warning("Added missing column %s.%s (%s)", name, column.name, ddl)
            except Exception:
                log.exception("Could not add column %s.%s", name, column.name)
    return added


# Key in app_meta recording which clock the stored timestamps are on.
_CLOCK_KEY = "timestamp_clock"


def _backfill_defaults() -> list:
    """Give the model's default to rows that were left NULL.

    ``_add_missing_columns`` fills the rows behind a column it adds itself.
    This catches the other case: a column an *earlier* release added without a
    backfill, which then sat NULL in a table the model says is NOT NULL.
    Cheap and idempotent — after the first run it matches nothing.
    """
    filled = []
    insp = inspect(db.engine)
    tables = set(insp.get_table_names())
    for name, table in db.metadata.tables.items():
        if name not in tables:
            continue
        present = {c["name"] for c in insp.get_columns(name)}
        for column in table.columns:
            if column.nullable or column.name not in present:
                continue
            literal = _default_literal(column)
            if literal is None:
                continue
            try:
                with db.engine.begin() as conn:
                    count = conn.execute(text(
                        f'UPDATE "{name}" SET "{column.name}" = {literal} '
                        f'WHERE "{column.name}" IS NULL')).rowcount or 0
            except Exception:
                log.exception("Could not backfill %s.%s", name, column.name)
                continue
            if count:
                filled.append(f"{name}.{column.name} ({count})")
                log.warning("Filled %s empty %s.%s with %s",
                            count, name, column.name, literal)
    return filled


def _localise_timestamps(fresh_database: bool) -> dict:
    """Bring an older database's timestamps onto the wall clock. Runs once.

    Rows written before this release hold ``datetime.utcnow()``; the app now
    stores what the clock reads (see ``jalali.local_now``) and prints it back
    without arithmetic. Left alone, every historical login would suddenly
    display 3.5 hours early, so each DateTime column is shifted by the offset
    the machine is running at and the database is marked as converted.

    Date columns are deliberately untouched: an operation date is a day on the
    calendar, not an instant, and shifting it could move it to the day before.
    """
    from ..models.meta import AppMeta

    if AppMeta.get(_CLOCK_KEY):
        return {"converted": False, "reason": "already-local"}
    if fresh_database:
        AppMeta.set(_CLOCK_KEY, "local")
        db.session.commit()
        return {"converted": False, "reason": "new-database"}

    offset = _dt.datetime.now() - _dt.datetime.utcnow()
    seconds = round(offset.total_seconds())
    shifted = []
    if seconds:
        insp = inspect(db.engine)
        tables = set(insp.get_table_names())
        for table in db.metadata.sorted_tables:
            if table.name not in tables:
                continue
            columns = [c.name for c in table.columns
                       if isinstance(c.type, db.DateTime)]
            if not columns:
                continue
            with db.engine.begin() as conn:
                for column in columns:
                    result = conn.execute(text(
                        f'UPDATE "{table.name}" '
                        f'SET "{column}" = datetime("{column}", :shift) '
                        f'WHERE "{column}" IS NOT NULL'), {"shift": f"{seconds} seconds"})
                    if result.rowcount:
                        shifted.append(f"{table.name}.{column}={result.rowcount}")
    AppMeta.set(_CLOCK_KEY, "local")
    db.session.commit()
    log.warning("Converted stored timestamps to local time (%+d s): %s",
                seconds, ", ".join(shifted) or "nothing to shift")
    return {"converted": True, "offset_seconds": seconds, "columns": shifted}


def _inspect_copy(path, wal_mode=False):
    """The tables of a (throw-away copy of a) database, or None if it does not
    read cleanly — opened the way the app opens it (WAL mode) when asked."""
    try:
        con = sqlite3.connect(str(path))
        try:
            if wal_mode:
                con.execute("PRAGMA journal_mode=WAL")
            if con.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                return None
            return {r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            con.close()
    except sqlite3.DatabaseError:
        return None


def set_aside_foreign_wal(path) -> list:
    """Move a leftover «-wal»/«-shm» pair that belongs to another database.

    Replacing ``wells.db`` while the old ``wells.db-wal`` and ``wells.db-shm``
    stay beside it makes SQLite replay the old database's pending pages onto
    the new file — «database disk image is malformed». When the database is
    broken *with* its WAL but healthy *without* it, the WAL is not its own:
    the pair is renamed (never deleted) and the database opens as it is.
    Returns the names the files were moved to.
    """
    import shutil
    import tempfile
    from pathlib import Path
    path = Path(path)
    wal = path.with_name(path.name + "-wal")
    shm = path.with_name(path.name + "-shm")
    if not path.exists() or not wal.exists() or wal.stat().st_size == 0:
        return []
    # Judged on copies only: opening the real file with a foreign WAL would
    # replay it into the database, which is the damage this is here to avoid.
    with tempfile.TemporaryDirectory() as tmp:
        alone = Path(tmp) / "alone" / path.name
        alone.parent.mkdir()
        shutil.copy2(path, alone)
        own_tables = _inspect_copy(alone)
        if own_tables is None:
            return []                  # the database itself is damaged: leave it
        together = Path(tmp) / "with" / path.name
        together.parent.mkdir()
        for src in (path, wal, shm):
            if src.exists():
                shutil.copy2(src, together.parent / src.name)
        replayed = _inspect_copy(together, wal_mode=True)
        # A WAL of its own reads cleanly and never loses a table the file has
        # (this app only ever adds tables); another database's WAL does either.
        if replayed is not None and own_tables <= replayed:
            return []
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    moved = []
    for extra in (wal, shm):
        if extra.exists():
            target = extra.with_name(f"{extra.name}.stale-{stamp}")
            extra.rename(target)
            moved.append(target.name)
    log.warning("Leftover WAL files that did not belong to %s were set aside: %s",
                path.name, ", ".join(moved))
    return moved


def ensure_database(app) -> dict:
    path = database_file()
    # the file actually being opened (reading the URL does not connect)
    url = db.engine.url
    stale = set_aside_foreign_wal(url.database if url.get_backend_name() == "sqlite"
                                  and url.database and url.database != ":memory:" else path)
    existed = path.exists() and path.stat().st_size > 0
    status = {"path": str(path), "existed": existed, "created": False, "seeded": False,
              "stale_wal_moved": stale}

    insp = inspect(db.engine)
    tables = set(insp.get_table_names())
    expected = set(db.metadata.tables)
    missing = expected - tables

    if missing:
        # Either a brand-new file, or one predating a table a release added —
        # a user table, say. create_all only adds what is absent, so running it
        # against a populated database is safe.
        log.info("Creating missing tables: %s", ", ".join(sorted(missing)))
        db.create_all()
        status["created"] = True
    status["tables_added"] = sorted(missing)

    status["columns_added"] = _add_missing_columns()
    status["defaults_filled"] = _backfill_defaults()
    status["tables_rebuilt"] = _rebuild_stale_fk_tables()
    # A database with no tables at all before this run is brand new, so its
    # timestamps are already local and must not be shifted.
    status["clock"] = _localise_timestamps(fresh_database=not existed)

    try:
        from ..refdata import ensure_refdata
        status["refdata"] = ensure_refdata(app)
    except Exception:  # noqa: BLE001 — a reference file must never stop the app starting
        db.session.rollback()
        log.exception("Preparing the reference databases failed")

    from .seed import seed_all
    seeded = seed_all(force=False)
    status["seeded"] = bool(seeded.get("changed"))
    status["seed"] = seeded

    # The earlier fixed reports, as ordinary editable report definitions.
    try:
        from ..analytics.templates import seed_templates
        status["report_templates"] = seed_templates()
    except Exception:  # noqa: BLE001 — a template must never stop the app starting
        db.session.rollback()
        log.exception("Seeding report templates failed")

    # This release's changes to the forms the database was configured with
    # (once per database; a step the admin has overtaken is left alone).
    try:
        from .upgrade_r13 import apply_r13
        status["forms_r13"] = apply_r13()
    except Exception:  # noqa: BLE001 — a form change must never stop the app starting
        db.session.rollback()
        log.exception("Applying the R13 form changes failed")
    try:
        from .upgrade_r14 import apply_r14
        status["refdata_r14"] = apply_r14()
    except Exception:  # noqa: BLE001 — a reference relink must never stop the app starting
        db.session.rollback()
        log.exception("Applying the R14 changes failed")
    try:
        from .upgrade_r15 import apply_r15
        status["workshop_r15"] = apply_r15()
    except Exception:  # noqa: BLE001 — a form change must never stop the app starting
        db.session.rollback()
        log.exception("Applying the R15 changes failed")

    with db.engine.connect() as conn:
        status["journal_mode"] = conn.execute(text("PRAGMA journal_mode")).scalar()
        status["foreign_keys"] = bool(conn.execute(text("PRAGMA foreign_keys")).scalar())

    log.info("Database ready at %s (existed=%s, journal=%s)",
             path, existed, status["journal_mode"])
    return status
