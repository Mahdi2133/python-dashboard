"""Startup database check (requirement 3).

    instance/wells.db exists?  →  connect to it, never replace it.
    does not exist?           →  create it with the full schema and seed data.

The one thing this must never do is silently make a fresh database on top of
an existing one, so the file is only created when it genuinely is not there,
and an existing file is opened as-is.
"""
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
                log.warning("Rebuilt %s so its user reference points at app_users",
                            table)
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
                added.append(f"{name}.{column.name}")
                log.warning("Added missing column %s.%s (%s)", name, column.name, ddl)
            except Exception:
                log.exception("Could not add column %s.%s", name, column.name)
    return added


def ensure_database(app) -> dict:
    path = database_file()
    existed = path.exists() and path.stat().st_size > 0
    status = {"path": str(path), "existed": existed, "created": False, "seeded": False}

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
    status["tables_rebuilt"] = _rebuild_stale_fk_tables()

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
