"""/api/system, /api/backup, /api/audit — settings, backup, audit trail."""
import platform
import socket
import sys

from flask import Blueprint, Response, current_app, request
from sqlalchemy import func, text
from werkzeug.utils import secure_filename

from ..extensions import db
from ..models import (AuditLog, FormField, ImportBatch, LookupItem, Record,
                      Well)
from ..paths import (app_dir, backups_dir, config_path, database_file,
                     load_config, logs_dir)
from ..services.auth import permission_required
from ..services.backup import (create_backup, list_backups, restore_backup,
                               validate_backup)
from ..services.jalali import tehran_time_str, to_jalali_str
from ..services.network import lan_addresses
from ._helpers import body, fail, ok, paging

bp = Blueprint("api_admin", __name__, url_prefix="/api")


@bp.get("/system")
@permission_required("settings.view")
def system_info():
    """Everything the Settings / System Information panel shows (req. 4)."""
    cfg = load_config()
    db_path = database_file(cfg)
    connected, journal, err = True, None, None
    try:
        with db.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            journal = conn.execute(text("PRAGMA journal_mode")).scalar()
    except Exception as exc:
        connected, err = False, str(exc)

    size = db_path.stat().st_size if db_path.exists() else 0
    return ok({
        "database": {
            "type": "SQLite",
            "status": "متصل" if connected else "قطع",
            "connected": connected,
            "path": str(db_path),
            "exists": db_path.exists(),
            "size_bytes": size,
            "size_mb": round(size / 1024 / 1024, 2),
            "journal_mode": journal,
            "error": err,
            "navicat_hint": "این فایل را می‌توانید مستقیماً در Navicat for SQLite باز کنید.",
        },
        "counts": {
            "records": db.session.query(func.count(Record.id))
                       .filter(Record.is_active.is_(True)).scalar() or 0,
            "records_inactive": db.session.query(func.count(Record.id))
                                .filter(Record.is_active.is_(False)).scalar() or 0,
            "wells": Well.query.count(),
            "wells_unverified": Well.query.filter_by(is_verified=False).count(),
            "lookup_items": LookupItem.query.count(),
            "lookup_adhoc": LookupItem.query.filter_by(is_adhoc=True).count(),
            "form_fields": FormField.query.count(),
            "audit_logs": AuditLog.query.count(),
            "import_batches": ImportBatch.query.count(),
        },
        "server": {
            "host": cfg.get("host"), "port": cfg.get("port"),
            "local_url": f"http://127.0.0.1:{cfg.get('port')}",
            "network_urls": [f"http://{ip}:{cfg.get('port')}" for ip in lan_addresses()],
            "hostname": socket.gethostname(),
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "frozen": getattr(sys, "frozen", False),
        },
        "paths": {
            "app_dir": str(app_dir()), "config": str(config_path()),
            "logs": str(logs_dir() / "app.log"), "backups": str(backups_dir()),
        },
        "app": {"title": current_app.config["APP_TITLE"], "version": "1.0.0"},
    })


@bp.get("/backup")
@permission_required("backup.manage")
def get_backups():
    return ok(list_backups())


@bp.post("/backup")
@permission_required("backup.manage")
def post_backup():
    try:
        info = create_backup(note=(body() or {}).get("note"))
    except (FileNotFoundError, OSError) as exc:
        return fail(f"تهیه پشتیبان ناموفق بود: {exc}", 500)
    return ok(info, message=f"پشتیبان «{info['filename']}» ساخته شد.")


@bp.get("/backup/<path:filename>/download")
@permission_required("backup.manage")
def download_backup(filename):
    safe = secure_filename(filename)
    path = backups_dir() / safe
    if not path.exists() or path.parent.resolve() != backups_dir().resolve():
        return fail("فایل پشتیبان یافت نشد.", 404)
    return Response(path.read_bytes(), mimetype="application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="{safe}"'})


@bp.post("/backup/restore")
@permission_required("backup.manage")
def post_restore():
    """Restore from an existing backup file, or from an uploaded one."""
    upload = request.files.get("file")
    if upload is not None and upload.filename:
        temp = backups_dir() / f"_upload_{secure_filename(upload.filename)}"
        upload.save(temp)
        source = temp
    else:
        name = secure_filename((body() or {}).get("filename") or "")
        source = backups_dir() / name
        if not name or not source.exists():
            return fail("فایل پشتیبان مشخص نشده یا یافت نشد.", 404)

    check = validate_backup(source)
    if not check["valid"]:
        return fail(check["reason"], 422)
    if str((body() or {}).get("confirm", request.form.get("confirm", ""))).lower() \
            not in ("1", "true", "yes"):
        return ok({"validation": check},
                  message="فایل معتبر است. برای اجرای بازیابی، تأیید را ارسال کنید.",
                  requires_confirm=True)
    try:
        result = restore_backup(source)
    except (ValueError, OSError) as exc:
        return fail(f"بازیابی ناموفق بود: {exc}", 500)
    return ok(result, message="پایگاه داده بازیابی شد. لطفاً برنامه را دوباره اجرا کنید.")


@bp.get("/audit")
@permission_required("audit.view")
def audit():
    page, size = paging(default_size=100)
    query = AuditLog.query
    if request.args.get("action"):
        query = query.filter(AuditLog.action == request.args["action"])
    if request.args.get("entity"):
        query = query.filter(AuditLog.entity == request.args["entity"])
    total = query.count()
    rows = (query.order_by(AuditLog.created_at.desc())
            .limit(size).offset((page - 1) * size).all())
    data = []
    for row in rows:
        d = row.to_dict()
        d["created_at_j"] = to_jalali_str(row.created_at)
        d["time"] = tehran_time_str(row.created_at)
        data.append(d)
    return ok(data, total=total, page=page, page_size=size,
              pages=max(1, (total + size - 1) // size))


@bp.get("/imports")
@permission_required("data.import")
def import_history():
    rows = ImportBatch.query.order_by(ImportBatch.started_at.desc()).limit(100).all()
    return ok([b.to_dict() for b in rows])


@bp.get("/logs")
@permission_required("audit.view")
def app_log():
    path = logs_dir() / "app.log"
    if not path.exists():
        return ok({"lines": [], "path": str(path)})
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        lines = fh.readlines()[-400:]
    return ok({"lines": [l.rstrip() for l in lines], "path": str(path)})
