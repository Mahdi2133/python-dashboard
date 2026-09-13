"""Audit trail, import batches and the (currently optional) user table."""
from datetime import datetime

from ..extensions import db

AUDIT_ACTIONS = ("create", "update", "delete", "restore", "import", "export",
                 "backup", "db_restore", "seed", "config")


class User(db.Model):
    """Present so RBAC can be switched on later without a schema rewrite.

    No login is enforced today — the system runs on a trusted company LAN —
    but every audit row already carries a nullable ``user_id``.
    """
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    full_name = db.Column(db.String(160))
    password_hash = db.Column(db.String(255))
    role = db.Column(db.String(40), default="admin")
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    username = db.Column(db.String(80))
    action = db.Column(db.String(40), nullable=False, index=True)
    entity = db.Column(db.String(60), index=True)
    entity_id = db.Column(db.Integer, index=True)
    summary = db.Column(db.Text)
    details = db.Column(db.Text)          # JSON blob of changed fields
    ip_address = db.Column(db.String(60))

    def to_dict(self):
        return {
            "id": self.id, "created_at": self.created_at.isoformat(),
            "user_id": self.user_id, "username": self.username, "action": self.action,
            "entity": self.entity, "entity_id": self.entity_id,
            "summary": self.summary, "details": self.details, "ip_address": self.ip_address,
        }


class ImportBatch(db.Model):
    __tablename__ = "import_batches"

    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255))
    sheet_name = db.Column(db.String(120))
    started_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    finished_at = db.Column(db.DateTime)
    total_rows = db.Column(db.Integer, default=0)
    inserted = db.Column(db.Integer, default=0)
    skipped = db.Column(db.Integer, default=0)
    failed = db.Column(db.Integer, default=0)
    status = db.Column(db.String(30), default="running")
    message = db.Column(db.Text)

    def to_dict(self):
        return {
            "id": self.id, "filename": self.filename, "sheet_name": self.sheet_name,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "total_rows": self.total_rows, "inserted": self.inserted,
            "skipped": self.skipped, "failed": self.failed,
            "status": self.status, "message": self.message,
        }
