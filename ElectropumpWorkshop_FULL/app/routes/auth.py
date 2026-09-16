# -*- coding: utf-8 -*-
"""Login page, session endpoints and user administration."""
import datetime as dt

from flask import Blueprint, g, redirect, render_template, request, url_for
from sqlalchemy import func

from ..extensions import db
from ..models import AuditLog, Record
from ..models.auth import (PERMISSIONS, PERMISSION_CODES, ROLES, AppUser,
                           UserSession)
from ..services.audit import record_audit
from ..services.auth import (admin_required, attempt_login, current_user,
                             end_sessions_for, login_required, logout_current)
from ..services.jalali import (local_now, parse_jalali_to_date, tehran_time_str,
                               to_jalali_str)
from ..services.lookups import normalize_text
from ._helpers import body, fail, ok, paging

bp = Blueprint("auth", __name__)


# ── login / logout ───────────────────────────────────────────────────────────
@bp.get("/login")
def login_page():
    if current_user() is not None:
        return redirect(url_for("pages.entry"))
    return render_template("login.html", next=request.args.get("next", ""))


@bp.post("/api/login")
def api_login():
    payload = body()
    user, error = attempt_login(
        payload.get("username"), payload.get("password"),
        ip=request.remote_addr, user_agent=request.headers.get("User-Agent"))
    if error:
        return fail(error, 401)
    return ok(user.to_dict(), message=f"خوش آمدید، {user.full_name}.",
              next=payload.get("next") or "/")


@bp.post("/api/logout")
def api_logout():
    logout_current()
    return ok(message="از سامانه خارج شدید.")


@bp.get("/logout")
def logout_page():
    logout_current()
    return redirect(url_for("auth.login_page"))


@bp.get("/api/me")
def api_me():
    user = current_user()
    if user is None:
        return fail("وارد سامانه نشده‌اید.", 401)
    data = user.to_dict()
    record = getattr(g, "current_session", None)
    data["session"] = record.to_dict() if record else None
    return ok(data)


@bp.post("/api/me/password")
@login_required
def change_own_password():
    user = current_user()
    payload = body()
    if not user.check_password(payload.get("current_password") or ""):
        return fail("رمز عبور فعلی نادرست است.", 422)
    new = payload.get("new_password") or ""
    problem = _password_problem(new)
    if problem:
        return fail(problem, 422)
    user.set_password(new)
    user.must_change_password = False
    record_audit("update", "user", user.id, summary="تغییر رمز عبور توسط خود کاربر")
    db.session.commit()
    return ok(message="رمز عبور تغییر کرد.")


def _password_problem(password: str):
    if len(password or "") < 6:
        return "رمز عبور باید حداقل ۶ نویسه باشد."
    if password.isdigit():
        return "رمز عبور نباید فقط عدد باشد."
    return None


# ── user administration ──────────────────────────────────────────────────────
@bp.get("/api/users")
@admin_required
def list_users():
    page, size = paging(default_size=100)
    query = AppUser.query
    q = normalize_text(request.args.get("q", ""))
    if q:
        like = f"%{q}%"
        query = query.filter(db.or_(
            AppUser.username.ilike(like), AppUser.first_name.ilike(like),
            AppUser.last_name.ilike(like), AppUser.personnel_code.ilike(like),
            AppUser.national_id.ilike(like)))
    if request.args.get("active") == "1":
        query = query.filter(AppUser.is_active.is_(True))
    total = query.count()
    rows = (query.order_by(AppUser.is_active.desc(), AppUser.username)
            .limit(size).offset((page - 1) * size).all())
    counts = dict(db.session.query(Record.created_by, func.count(Record.id))
                  .filter(Record.created_by.isnot(None))
                  .group_by(Record.created_by).all())
    open_sessions = {r[0] for r in db.session.query(UserSession.user_id)
                     .filter(UserSession.logout_at.is_(None)).all()}
    data = []
    for u in rows:
        d = u.to_dict()
        d["records_created"] = counts.get(u.id, 0)
        d["is_online"] = u.id in open_sessions
        d["last_login_j"] = to_jalali_str(u.last_login_at)
        d["last_login_time"] = tehran_time_str(u.last_login_at, with_seconds=False)
        data.append(d)
    return ok(data, total=total, page=page, page_size=size,
              pages=max(1, (total + size - 1) // size))


@bp.get("/api/users/meta")
@admin_required
def users_meta():
    """Roles and the permission vocabulary, for the admin screen."""
    groups = {}
    for code, label, group in PERMISSIONS:
        groups.setdefault(group, []).append({"code": code, "label": label})
    return ok({
        "roles": [{"key": k, "label": v["label"], "description": v["description"],
                   "permissions": v["permissions"]} for k, v in ROLES.items()],
        "permission_groups": [{"group": g, "items": items}
                              for g, items in groups.items()],
    })


def _apply_user_payload(user, payload, creating=False):
    """Map the admin form onto a user. Returns an error message or None."""
    if creating or "username" in payload:
        username = normalize_text(payload.get("username"))
        if not username:
            return "نام کاربری الزامی است."
        if " " in username:
            return "نام کاربری نباید فاصله داشته باشد."
        clash = AppUser.query.filter(
            func.lower(AppUser.username) == username.lower(),
            AppUser.id != (user.id or 0)).first()
        if clash:
            return "این نام کاربری قبلاً ثبت شده است."
        user.username = username

    for attr in ("first_name", "last_name", "father_name", "national_id",
                 "personnel_code", "phone", "email", "position", "unit", "notes"):
        if attr in payload:
            setattr(user, attr, normalize_text(payload[attr]) or None)

    if "birth_date" in payload:
        user.birth_date = parse_jalali_to_date(payload["birth_date"])

    if "role" in payload:
        role = payload["role"]
        if role not in ROLES:
            return f"نقش نامعتبر است. مقادیر مجاز: {'، '.join(ROLES)}"
        user.role = role

    if "permissions" in payload:
        codes = payload["permissions"]
        if codes in (None, "", "default"):
            user.set_permissions(None)          # fall back to the role defaults
        elif isinstance(codes, list):
            unknown = [c for c in codes if c not in PERMISSION_CODES]
            if unknown:
                return f"مجوز ناشناخته: {'، '.join(unknown)}"
            user.set_permissions(codes)
        else:
            return "فهرست مجوزها باید آرایه باشد."

    if "edit_window_hours" in payload:
        raw = payload["edit_window_hours"]
        if raw in (None, "", "0", 0, "unlimited"):
            user.edit_window_hours = None       # no limit
        else:
            try:
                hours = int(raw)
            except (TypeError, ValueError):
                return "مهلت ویرایش باید عدد (ساعت) باشد."
            if hours < 1 or hours > 8760:
                return "مهلت ویرایش باید بین ۱ تا ۸۷۶۰ ساعت (یک سال) باشد."
            user.edit_window_hours = hours

    if "is_active" in payload:
        user.is_active = payload["is_active"] in (True, "true", "1", 1)
    if "must_change_password" in payload:
        user.must_change_password = payload["must_change_password"] in (True, "true", "1", 1)
    return None


@bp.post("/api/users")
@admin_required
def create_user():
    payload = body()
    user = AppUser()
    error = _apply_user_payload(user, payload, creating=True)
    if error:
        return fail(error, 422)
    password = payload.get("password") or ""
    problem = _password_problem(password)
    if problem:
        return fail(problem, 422)
    user.set_password(password)
    user.created_by = current_user().id
    db.session.add(user)
    db.session.flush()
    record_audit("create", "user", user.id,
                 summary=f"ایجاد کاربر «{user.username}» با نقش {user.role}")
    db.session.commit()
    return ok(user.to_dict(), message=f"کاربر «{user.username}» ایجاد شد.")


@bp.put("/api/users/<int:user_id>")
@admin_required
def update_user(user_id):
    user = db.session.get(AppUser, user_id)
    if user is None:
        return fail("کاربر یافت نشد.", 404)
    payload = body()
    me = current_user()

    # An admin must not be able to lock themselves out of user management.
    if user.id == me.id:
        if payload.get("is_active") in (False, "false", "0", 0):
            return fail("نمی‌توانید حساب خودتان را غیرفعال کنید.", 422)
        if "role" in payload and payload["role"] != "admin" and user.role == "admin":
            if AppUser.query.filter(AppUser.role == "admin",
                                    AppUser.is_active.is_(True),
                                    AppUser.id != user.id).count() == 0:
                return fail("شما تنها مدیر فعال سامانه هستید؛ نقش خود را تغییر ندهید.", 422)

    was_active = user.is_active
    error = _apply_user_payload(user, payload)
    if error:
        return fail(error, 422)

    if payload.get("password"):
        problem = _password_problem(payload["password"])
        if problem:
            return fail(problem, 422)
        user.set_password(payload["password"])
        user.failed_attempts = 0
        user.locked_until = None
        record_audit("update", "user", user.id,
                     summary=f"تغییر رمز عبور کاربر «{user.username}» توسط مدیر")

    # Disabling someone must take effect immediately, not at their next login.
    if was_active and not user.is_active:
        closed = end_sessions_for(user.id)
        record_audit("update", "user", user.id,
                     summary=f"غیرفعال‌سازی «{user.username}» و بستن {closed} نشست باز")
    else:
        record_audit("update", "user", user.id,
                     summary=f"ویرایش کاربر «{user.username}»")
    db.session.commit()
    return ok(user.to_dict(), message="کاربر به‌روزرسانی شد.")


@bp.delete("/api/users/<int:user_id>")
@admin_required
def deactivate_user(user_id):
    """Users are deactivated, never deleted — their audit trail must survive."""
    user = db.session.get(AppUser, user_id)
    if user is None:
        return fail("کاربر یافت نشد.", 404)
    if user.id == current_user().id:
        return fail("نمی‌توانید حساب خودتان را غیرفعال کنید.", 422)
    user.is_active = False
    closed = end_sessions_for(user.id)
    record_audit("delete", "user", user.id,
                 summary=f"غیرفعال‌سازی کاربر «{user.username}» ({closed} نشست بسته شد)")
    db.session.commit()
    return ok(message=f"کاربر «{user.username}» غیرفعال شد و سوابقش حفظ گردید.")


@bp.post("/api/users/<int:user_id>/unlock")
@admin_required
def unlock_user(user_id):
    user = db.session.get(AppUser, user_id)
    if user is None:
        return fail("کاربر یافت نشد.", 404)
    user.locked_until = None
    user.failed_attempts = 0
    record_audit("update", "user", user.id, summary=f"باز کردن قفل «{user.username}»")
    db.session.commit()
    return ok(user.to_dict(), message="قفل حساب برداشته شد.")


# ── activity ─────────────────────────────────────────────────────────────────
@bp.get("/api/users/<int:user_id>/activity")
@admin_required
def user_activity(user_id):
    user = db.session.get(AppUser, user_id)
    if user is None:
        return fail("کاربر یافت نشد.", 404)

    sessions = (UserSession.query.filter_by(user_id=user_id)
                .order_by(UserSession.login_at.desc()).limit(100).all())
    audits = (AuditLog.query.filter_by(user_id=user_id)
              .order_by(AuditLog.created_at.desc()).limit(300).all())

    created = Record.query.filter_by(created_by=user_id).count()
    edited = Record.query.filter(Record.updated_by == user_id,
                                 Record.created_by != user_id).count()
    recent = (Record.query.filter_by(created_by=user_id)
              .order_by(Record.created_at.desc()).limit(50).all())

    total_seconds = sum(s.duration_seconds or 0 for s in sessions)
    return ok({
        "user": user.to_dict(),
        "summary": {
            "records_created": created, "records_edited": edited,
            "logins": user.login_count or 0,
            "sessions_listed": len(sessions),
            "total_seconds": total_seconds,
            "total_hours": round(total_seconds / 3600, 1),
        },
        "sessions": [dict(s.to_dict(),
                          login_at_j=to_jalali_str(s.login_at),
                          login_time=tehran_time_str(s.login_at),
                          logout_time=tehran_time_str(s.logout_at))
                     for s in sessions],
        "audits": [dict(a.to_dict(), created_at_j=to_jalali_str(a.created_at),
                        time=tehran_time_str(a.created_at))
                   for a in audits],
        "recent_records": [{
            "id": r.id, "date": f"{r.j_year or ''}/{r.j_month or 0:02d}/{r.j_day or 0:02d}",
            "well": r.well.name if r.well else r.well_name_raw,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "created_at_j": to_jalali_str(r.created_at),
            "is_active": r.is_active,
        } for r in recent],
    })


@bp.get("/api/sessions")
@admin_required
def all_sessions():
    page, size = paging(default_size=100)
    query = UserSession.query
    if request.args.get("open") == "1":
        query = query.filter(UserSession.logout_at.is_(None))
    if request.args.get("user_id"):
        query = query.filter(UserSession.user_id == int(request.args["user_id"]))
    total = query.count()
    rows = (query.order_by(UserSession.login_at.desc())
            .limit(size).offset((page - 1) * size).all())
    return ok([dict(s.to_dict(),
                    login_at_j=to_jalali_str(s.login_at),
                    login_time=tehran_time_str(s.login_at),
                    logout_time=tehran_time_str(s.logout_at))
               for s in rows],
              total=total, page=page, page_size=size,
              pages=max(1, (total + size - 1) // size))


@bp.post("/api/sessions/<int:session_id>/close")
@admin_required
def close_session(session_id):
    record = db.session.get(UserSession, session_id)
    if record is None:
        return fail("نشست یافت نشد.", 404)
    if record.logout_at is not None:
        return ok(message="این نشست از قبل بسته شده است.")
    record.logout_at = local_now()
    record.end_reason = "closed_by_admin"
    record_audit("logout", "user", record.user_id,
                 summary=f"بستن نشست کاربر «{record.user.username}» توسط مدیر")
    db.session.commit()
    return ok(message="نشست بسته شد.")
