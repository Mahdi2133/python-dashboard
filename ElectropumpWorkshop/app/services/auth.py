# -*- coding: utf-8 -*-
"""Login, session handling and the permission decorators."""
from __future__ import annotations

import functools
import logging
from datetime import datetime, timedelta

from flask import g, jsonify, redirect, render_template, request, session, url_for

from ..extensions import db
from ..models.auth import AppUser, UserSession
from .audit import record_audit

log = logging.getLogger(__name__)

SESSION_KEY = "electropump_session"
IDLE_TIMEOUT = timedelta(hours=12)
MAX_FAILED = 5
LOCK_MINUTES = 10


# ── current user ─────────────────────────────────────────────────────────────
def load_current_user():
    """Resolve the signed-in user for this request; runs in before_request."""
    g.current_user = None
    g.current_session = None
    token = session.get(SESSION_KEY)
    if not token:
        return
    record = UserSession.query.filter_by(token=token, logout_at=None).first()
    if record is None:
        session.pop(SESSION_KEY, None)
        return
    now = datetime.utcnow()
    if now - record.last_seen_at > IDLE_TIMEOUT:
        _close(record, "expired")
        db.session.commit()
        session.pop(SESSION_KEY, None)
        return
    if record.user is None or not record.user.is_active:
        _close(record, "disabled")
        db.session.commit()
        session.pop(SESSION_KEY, None)
        return
    # Throttle the write: a heartbeat per minute is enough to measure presence
    # and keeps a busy page from writing on every request.
    if (now - record.last_seen_at).total_seconds() > 60:
        record.last_seen_at = now
        db.session.commit()
    g.current_user = record.user
    g.current_session = record


def current_user():
    return getattr(g, "current_user", None)


def _close(record: UserSession, reason: str):
    record.logout_at = datetime.utcnow()
    record.end_reason = reason


# ── login / logout ───────────────────────────────────────────────────────────
def attempt_login(username: str, password: str, ip=None, user_agent=None):
    """Return (user, error_message). Never says which half was wrong."""
    username = (username or "").strip()
    user = AppUser.query.filter(db.func.lower(AppUser.username)
                                == username.lower()).first()
    generic = "نام کاربری یا رمز عبور نادرست است."

    if user is None:
        log.info("Login failed for unknown username %r from %s", username, ip)
        return None, generic
    if user.locked_until and user.locked_until > datetime.utcnow():
        remaining = int((user.locked_until - datetime.utcnow()).total_seconds() // 60) + 1
        return None, (f"این حساب به دلیل تلاش‌های ناموفق موقتاً قفل شده است. "
                      f"حدود {remaining} دقیقه دیگر دوباره تلاش کنید.")
    if not user.is_active:
        return None, "این حساب کاربری غیرفعال است. با مدیر سیستم تماس بگیرید."
    if not user.check_password(password):
        user.failed_attempts = (user.failed_attempts or 0) + 1
        if user.failed_attempts >= MAX_FAILED:
            user.locked_until = datetime.utcnow() + timedelta(minutes=LOCK_MINUTES)
            user.failed_attempts = 0
            log.warning("Account %s locked after repeated failures from %s",
                        user.username, ip)
        db.session.commit()
        return None, generic

    user.failed_attempts = 0
    user.locked_until = None
    user.last_login_at = datetime.utcnow()
    user.last_login_ip = ip
    user.login_count = (user.login_count or 0) + 1

    record = UserSession(user_id=user.id, token=UserSession.new_token(),
                         ip_address=ip, user_agent=(user_agent or "")[:300])
    db.session.add(record)
    db.session.flush()
    session.permanent = True
    session[SESSION_KEY] = record.token
    record_audit("login", "user", user.id,
                 summary=f"ورود کاربر «{user.username}»")
    db.session.commit()
    log.info("User %s logged in from %s", user.username, ip)
    return user, None


def logout_current():
    record = getattr(g, "current_session", None)
    user = current_user()
    if record is not None:
        _close(record, "logout")
        if user:
            record_audit("logout", "user", user.id,
                         summary=f"خروج کاربر «{user.username}»")
        db.session.commit()
    session.pop(SESSION_KEY, None)
    g.current_user = None
    g.current_session = None


def end_sessions_for(user_id: int, reason="disabled"):
    """Kick a user out everywhere — used when the admin disables the account."""
    count = 0
    for record in UserSession.query.filter_by(user_id=user_id, logout_at=None).all():
        _close(record, reason)
        count += 1
    return count


# ── guards ───────────────────────────────────────────────────────────────────
def _is_api():
    return request.path.startswith("/api/")


def _deny(message, status):
    if _is_api():
        return jsonify({"ok": False, "error": message}), status
    if status == 401:
        return redirect(url_for("auth.login_page", next=request.path))
    return render_template("error.html", code=403, message=message), 403


def login_required(view):
    @functools.wraps(view)
    def wrapper(*args, **kwargs):
        if current_user() is None:
            return _deny("برای ادامه باید وارد سامانه شوید.", 401)
        return view(*args, **kwargs)
    return wrapper


def permission_required(permission):
    def decorator(view):
        @functools.wraps(view)
        def wrapper(*args, **kwargs):
            user = current_user()
            if user is None:
                return _deny("برای ادامه باید وارد سامانه شوید.", 401)
            if not user.can(permission):
                log.info("User %s denied %s on %s", user.username, permission,
                         request.path)
                return _deny("شما مجوز دسترسی به این بخش را ندارید. "
                             "در صورت نیاز با مدیر سیستم هماهنگ کنید.", 403)
            return view(*args, **kwargs)
        return wrapper
    return decorator


def admin_required(view):
    return permission_required("user.manage")(view)
