"""File + console logging into logs/app.log."""
import logging
from logging.handlers import RotatingFileHandler

from .paths import logs_dir

_FMT = "%(asctime)s %(levelname)-8s [%(name)s] %(message)s"


def configure_logging(app):
    level = getattr(logging, str(app.config.get("LOG_LEVEL", "INFO")).upper(), logging.INFO)

    file_handler = RotatingFileHandler(
        logs_dir() / "app.log", maxBytes=2 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(logging.Formatter(_FMT))
    file_handler.setLevel(level)

    root = logging.getLogger()
    root.setLevel(level)
    # Re-running the factory (tests, CLI) must not stack handlers.
    for existing in list(root.handlers):
        if getattr(existing, "_electropump", False):
            root.removeHandler(existing)
    file_handler._electropump = True
    root.addHandler(file_handler)

    app.logger.setLevel(level)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    return file_handler
