"""Application configuration.

Database selection is driven by the DATABASE_URL environment variable:
  - unset            -> SQLite under instance/water.db (zero-install dev)
  - postgresql://... -> PostgreSQL/PostGIS (production host)
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"


def _normalize_db_url(url: str) -> str:
    # Heroku-style "postgres://" -> SQLAlchemy "postgresql+psycopg2://"
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg2://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-insecure-change-me")

    _db_url = os.environ.get("DATABASE_URL")
    if _db_url:
        SQLALCHEMY_DATABASE_URI = _normalize_db_url(_db_url)
        IS_SQLITE = SQLALCHEMY_DATABASE_URI.startswith("sqlite")
    else:
        INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{INSTANCE_DIR / 'water.db'}"
        IS_SQLITE = True

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Concurrency hardening (carried over from the Financial system experience).
    if IS_SQLITE:
        SQLALCHEMY_ENGINE_OPTIONS = {
            "connect_args": {"check_same_thread": False, "timeout": 15},
        }
    else:
        SQLALCHEMY_ENGINE_OPTIONS = {
            "pool_pre_ping": True,
            "pool_size": 10,
            "max_overflow": 20,
        }

    # File uploads (document management). Stored under instance/ (gitignored).
    UPLOAD_DIR = INSTANCE_DIR / "uploads"
    MAX_CONTENT_LENGTH = 25 * 1024 * 1024   # 25 MB per upload
    ALLOWED_UPLOAD_EXT = {
        "pdf", "png", "jpg", "jpeg", "gif", "webp", "bmp", "tif", "tiff",
        "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "csv",
        "dwg", "dxf", "zip", "rar", "7z", "mp4", "avi", "mov",
    }

    # Babel/locale defaults (Persian UI, Tehran time).
    LANG = "fa"
