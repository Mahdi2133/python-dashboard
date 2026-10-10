"""Reference databases: data the forms read instead of asking the user.

Each source is a separate SQLite file in ``refdata/`` next to wells.db —
its own schema, its own importer, replaceable on its own. See models.py.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)

# key → (title, file name, icon); the warehouse book is a bind too, but it is
# workflow data (app.warehouse), not reference data.
SOURCES = {
    "flowtest": ("دبی‌سنجی چاه‌ها", "flowtest.db", "💧"),
    "production": ("روند تولید", "production.db", "📈"),
    "videometry": ("ویدئومتری چاه‌ها", "videometry.db", "🎥"),
    "flowrec": ("سوابق سنجش دبی", "flowrecords.db", "📋"),
}
BIND_FILES = {key: fname for key, (_t, fname, _i) in SOURCES.items()}
BIND_FILES["warehouse"] = "warehouse.db"


def refdata_dir(db_file) -> Path:
    """``refdata/`` beside the main database file."""
    text = str(db_file or "")
    if not text or text == ":memory:":
        import tempfile
        base = Path(tempfile.gettempdir()) / "electropump_refdata"
    else:
        base = Path(text).resolve().parent / "refdata"
    base.mkdir(parents=True, exist_ok=True)
    return base


def bind_uris(db_file) -> dict:
    folder = refdata_dir(db_file)
    return {key: "sqlite:///" + (folder / fname).as_posix()
            for key, fname in BIND_FILES.items()}


def bind_path(app, key) -> str:
    uri = app.config["SQLALCHEMY_BINDS"][key]
    return uri.replace("sqlite:///", "")


def ensure_refdata(app) -> dict:
    """Create whatever tables the reference files lack (idempotent)."""
    from ..extensions import db
    from . import models  # noqa: F401  (register the bound tables)
    from ..warehouse import models as _wh  # noqa: F401
    keys = list(BIND_FILES)
    db.create_all(bind_key=keys)
    added = _add_missing_columns(db, keys)
    from ..warehouse.service import seed_warehouse
    seeded = seed_warehouse()
    return {"binds": {k: os.path.basename(bind_path(app, k)) for k in keys},
            "columns_added": added, "warehouse_seed": seeded}


def _add_missing_columns(db, keys) -> list:
    """A column a later release added to a bound table, added in place."""
    from sqlalchemy import inspect, text
    added = []
    for key in keys:
        engine = db.engines[key]
        insp = inspect(engine)
        for table in db.metadatas[key].sorted_tables:
            have = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in have:
                    continue
                ddl = col.type.compile(engine.dialect)
                with engine.begin() as conn:
                    conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {ddl}'))
                added.append(f"{key}.{table.name}.{col.name}")
    return added
