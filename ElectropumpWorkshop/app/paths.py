"""Runtime path resolution.

The single rule that governs this module: **the database always lives next to
the executable, never inside it**.

    dist/
        ElectropumpWorkshop.exe
        instance/
            wells.db

When frozen by PyInstaller, ``sys.executable`` points at the EXE, so
``app_dir()`` is ``dist/`` and the database is ``dist/instance/wells.db`` — a
plain file Navicat for SQLite can open, back up and move. Bundled read-only
resources (templates, static, fonts) come from ``sys._MEIPASS`` instead.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_DEFAULT_CONFIG = {
    "host": "0.0.0.0",
    "port": 5050,
    "open_browser": True,
    "threads": 16,
    "secret_key": "change-me-electropump-workshop",
    "database_filename": "wells.db",
    "database_path": "",
    "log_level": "INFO",
    "backup_keep": 30,
    "app_title": "سامانه مدیریت کارگاه الکتروپمپ",
    "organization": "",
}


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def app_dir() -> Path:
    """Writable folder that travels with the program (EXE folder in a build)."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resource_dir() -> Path:
    """Read-only bundled resources (PyInstaller temp dir when frozen)."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", app_dir()))
    return Path(__file__).resolve().parent.parent


def instance_dir() -> Path:
    d = app_dir() / "instance"
    d.mkdir(parents=True, exist_ok=True)
    return d


def logs_dir() -> Path:
    d = app_dir() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def backups_dir() -> Path:
    d = app_dir() / "backups"
    d.mkdir(parents=True, exist_ok=True)
    return d


def exports_dir() -> Path:
    d = app_dir() / "exports"
    d.mkdir(parents=True, exist_ok=True)
    return d


def uploads_dir() -> Path:
    d = app_dir() / "instance" / "uploads"
    d.mkdir(parents=True, exist_ok=True)
    return d


def config_path() -> Path:
    return app_dir() / "config.json"


def load_config() -> dict:
    """Read config.json next to the program, writing defaults if absent.

    An unreadable or malformed file never stops the server: defaults are used
    and the problem is reported by the caller through the log.
    """
    cfg = dict(_DEFAULT_CONFIG)
    path = config_path()
    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as fh:
                user_cfg = json.load(fh)
            if isinstance(user_cfg, dict):
                cfg.update({k: v for k, v in user_cfg.items() if v is not None})
        except (OSError, ValueError) as exc:  # malformed JSON / unreadable
            cfg["_config_error"] = str(exc)
    else:
        try:
            with path.open("w", encoding="utf-8") as fh:
                json.dump(_DEFAULT_CONFIG, fh, ensure_ascii=False, indent=4)
        except OSError as exc:
            cfg["_config_error"] = str(exc)
    return cfg


def database_file(cfg: dict | None = None) -> Path:
    """Absolute path of wells.db — external to the EXE, always."""
    cfg = cfg or load_config()
    explicit = (cfg.get("database_path") or "").strip()
    if explicit:
        p = Path(explicit).expanduser()
        if not p.is_absolute():
            p = app_dir() / p
        p.parent.mkdir(parents=True, exist_ok=True)
        return p.resolve()
    return (instance_dir() / (cfg.get("database_filename") or "wells.db")).resolve()


def database_uri(cfg: dict | None = None) -> str:
    return "sqlite:///" + database_file(cfg).as_posix()
