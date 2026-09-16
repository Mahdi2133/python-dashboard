"""Audit log writer (requirement 29)."""
import json
import logging

from flask import g, has_request_context, request

from ..extensions import db
from ..models import AuditLog

log = logging.getLogger(__name__)


def record_audit(action, entity=None, entity_id=None, summary=None, details=None,
                 commit=False):
    """Append one audit row. Never raises — auditing must not break the work."""
    try:
        user = None
        if has_request_context():
            user = getattr(g, "current_user", None)
        entry = AuditLog(
            action=action, entity=entity, entity_id=entity_id, summary=summary,
            details=json.dumps(details, ensure_ascii=False) if details is not None else None,
            ip_address=request.remote_addr if has_request_context() else None,
            user_id=user.id if user else None,
            username=user.username if user else "system",
        )
        db.session.add(entry)
        if commit:
            db.session.commit()
        return entry
    except Exception:
        log.exception("Failed to write audit entry for %s/%s", action, entity)
        db.session.rollback()
        return None


def diff_fields(before: dict, after: dict) -> dict:
    """Only the keys whose value actually changed, for a compact audit detail."""
    changed = {}
    for key, new in after.items():
        old = before.get(key)
        if old != new:
            changed[key] = {"from": old, "to": new}
    return changed
