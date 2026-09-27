# -*- coding: utf-8 -*-
"""Users, permissions and login sessions.

The permission model is deliberately flat: a set of string permissions per
user, plus a role that supplies a default set. That is enough to express what
the workshop asked for — "this operator may record data and read the well
reports, nothing else" — without the ceremony of a full role/permission
matrix, and it is easy for a non-technical admin to read on screen.
"""
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta

from ..services.jalali import local_now

from ..extensions import db

# ── the permission vocabulary ────────────────────────────────────────────────
# (code, Persian label, group) — the admin screen renders these as checkboxes.
PERMISSIONS = [
    ("record.view",    "مشاهده رکوردها",              "رکوردها"),
    ("record.create",  "ثبت رکورد جدید",              "رکوردها"),
    ("record.edit",    "ویرایش رکورد",                "رکوردها"),
    ("record.delete",  "حذف / غیرفعال‌سازی رکورد",     "رکوردها"),
    ("record.export",  "خروجی گرفتن از رکوردها",       "رکوردها"),
    ("well.view",      "مشاهده چاه‌ها",                "چاه‌ها"),
    ("well.manage",    "افزودن و ویرایش چاه‌ها",        "چاه‌ها"),
    ("dashboard.view", "مشاهده داشبورد",               "گزارش‌ها"),
    ("report.view",    "مشاهده گزارش‌ها",              "گزارش‌ها"),
    ("report.build",   "گزارش‌ساز پویا",               "گزارش‌ها"),
    ("report.manage",  "طراحی، انتشار و دسترسی گزارش‌ها", "گزارش‌ها"),
    ("workflow.act",   "شرکت در فرایند (کارتابل)",     "فرایند"),
    ("workflow.view",  "مشاهده مسیر فرایندها",         "فرایند"),
    ("workflow.manage", "فرایندساز و تعریف مراحل",      "فرایند"),
    ("form.manage",    "فرم‌ساز و مدیریت گزینه‌ها",     "پیکربندی"),
    ("data.import",    "ورود داده از اکسل",            "پیکربندی"),
    ("backup.manage",  "پشتیبان‌گیری و بازیابی",        "سیستم"),
    ("audit.view",     "مشاهده گزارش تغییرات و لاگ",    "سیستم"),
    ("user.manage",    "مدیریت کاربران",               "سیستم"),
    ("settings.view",  "مشاهده تنظیمات سیستم",         "سیستم"),
]
PERMISSION_CODES = [p[0] for p in PERMISSIONS]

ROLES = {
    "admin": {
        "label": "مدیر سیستم",
        "description": "دسترسی کامل به همه بخش‌ها، شامل مدیریت کاربران.",
        "permissions": list(PERMISSION_CODES),
    },
    "supervisor": {
        "label": "سرپرست",
        "description": "ثبت و ویرایش داده، همه گزارش‌ها؛ بدون مدیریت کاربران و سیستم.",
        "permissions": ["record.view", "record.create", "record.edit", "record.export",
                        "well.view", "well.manage", "dashboard.view", "report.view",
                        "data.import", "audit.view",
                        "workflow.act", "workflow.view"],
    },
    "operator": {
        "label": "کاربر ثبت اطلاعات",
        "description": "فقط ثبت رکورد جدید و مشاهده گزارش چاه‌ها؛ بدون ویرایش و حذف.",
        "permissions": ["record.create", "well.view", "report.view",
                        "workflow.act"],
    },
    "stage_owner": {
        "label": "متولی مرحله فرایند",
        "description": "فقط کارتابل فرایند: مرحله‌ی خودش را پر می‌کند و "
                       "می‌فرستد؛ به جدول رکوردها و بقیه تب‌ها کاری ندارد.",
        # Deliberately just the one permission. Filling a stage needs the form
        # schema, the option lists and the well picker, and all three now
        # accept workflow.act — so a متولی never has to be handed the right to
        # create records outright just to do their own job.
        "permissions": ["workflow.act", "record.view", "record.export"],
    },
    "viewer": {
        "label": "فقط مشاهده",
        "description": "مشاهده رکوردها و گزارش‌ها، بدون هیچ تغییری.",
        "permissions": ["record.view", "well.view", "dashboard.view", "report.view"],
    },
}

# Which navigation entry each page needs; used to hide tabs a user cannot open.
PAGE_PERMISSION = {
    "entry": "record.create",
    "dashboard": "dashboard.view",
    "records": "record.view",
    "wells": "well.view",
    "reports": "report.view",
    # Designing, publishing and granting reports is the system admin's alone.
    "builder": "report.manage",
    "inbox": "workflow.act",
    "documents": "workflow.act",
    "workflow": "workflow.manage",
    "formbuilder": "form.manage",
    "options": "form.manage",
    "transfer": "data.import",
    "users": "user.manage",
    "settings": "settings.view",
}

_PBKDF2_ROUNDS = 200_000


def hash_password(password: str, salt: bytes | None = None) -> str:
    """PBKDF2-HMAC-SHA256. Stored as ``pbkdf2$rounds$salt$hash``."""
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ROUNDS)
    return f"pbkdf2${_PBKDF2_ROUNDS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored or not password:
        return False
    try:
        scheme, rounds, salt_hex, digest_hex = stored.split("$")
        if scheme != "pbkdf2":
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                                     bytes.fromhex(salt_hex), int(rounds))
    except (ValueError, TypeError):
        return False
    # Constant-time compare so a wrong password cannot be found byte by byte.
    return hmac.compare_digest(digest.hex(), digest_hex)


class AppUser(db.Model):
    """A person who logs in.

    Kept separate from the legacy ``users`` table (which only ever held a stub)
    so the audit rows written before login existed stay valid.
    """
    __tablename__ = "app_users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)

    # مشخصات شناسنامه‌ای
    first_name = db.Column(db.String(80))
    last_name = db.Column(db.String(80))
    father_name = db.Column(db.String(80))
    national_id = db.Column(db.String(20), index=True)     # کد ملی
    personnel_code = db.Column(db.String(40), index=True)  # کد پرسنلی / کد کاربری
    birth_date = db.Column(db.Date)
    phone = db.Column(db.String(40))
    email = db.Column(db.String(120))
    position = db.Column(db.String(120))                   # سمت
    unit = db.Column(db.String(120))                       # واحد / مرکز

    role = db.Column(db.String(30), nullable=False, default="operator")
    # JSON list of permission codes; NULL means "use the role's defaults".
    permissions_json = db.Column(db.Text)

    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    must_change_password = db.Column(db.Boolean, nullable=False, default=False)
    notes = db.Column(db.Text)

    # How long after a record is written this user may still change it, in
    # hours. NULL means no limit, which is what every existing account keeps on
    # upgrade — the admin opts a user in. The admin role ignores it entirely.
    edit_window_hours = db.Column(db.Integer)

    last_login_at = db.Column(db.DateTime)
    last_login_ip = db.Column(db.String(60))
    login_count = db.Column(db.Integer, nullable=False, default=0)
    failed_attempts = db.Column(db.Integer, nullable=False, default=0)
    locked_until = db.Column(db.DateTime)

    created_at = db.Column(db.DateTime, default=local_now, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey("app_users.id"))

    sessions = db.relationship("UserSession", back_populates="user",
                               cascade="all, delete-orphan", lazy="dynamic")
    # The مراکز آبرسانی this person answers for. Only a stage that asks to be
    # routed by the well's مرکز reads it; everywhere else a user with no
    # centres behaves exactly as before.
    centers = db.relationship("LookupItem",
                              secondary="app_user_centers", lazy="selectin")

    # ── password ────────────────────────────────────────────────────────────
    def set_password(self, password: str):
        self.password_hash = hash_password(password)

    def check_password(self, password: str) -> bool:
        return verify_password(password, self.password_hash)

    # ── permissions ─────────────────────────────────────────────────────────
    @property
    def permissions(self) -> set:
        """Explicit grants if the admin set any, otherwise the role's defaults."""
        if self.permissions_json:
            import json
            try:
                explicit = json.loads(self.permissions_json)
                if isinstance(explicit, list):
                    return {p for p in explicit if p in PERMISSION_CODES}
            except ValueError:
                pass
        return set(ROLES.get(self.role, {}).get("permissions", []))

    def set_permissions(self, codes):
        import json
        if codes is None:
            self.permissions_json = None
            return
        clean = sorted({c for c in codes if c in PERMISSION_CODES})
        self.permissions_json = json.dumps(clean, ensure_ascii=False)

    def can(self, permission: str) -> bool:
        if not self.is_active:
            return False
        # The admin role is absolute; it cannot lock itself out of user
        # management by an accidental permission edit.
        if self.role == "admin":
            return True
        return permission in self.permissions

    @property
    def full_name(self):
        name = " ".join(filter(None, [self.first_name, self.last_name])).strip()
        return name or self.username

    @property
    def role_label(self):
        return ROLES.get(self.role, {}).get("label", self.role)

    # ── record edit window ──────────────────────────────────────────────────
    @property
    def has_edit_window(self) -> bool:
        """Whether this user's edits expire. Admins are never limited."""
        return self.role != "admin" and bool(self.edit_window_hours)

    @property
    def edit_window_label(self) -> str:
        hours = self.edit_window_hours
        if self.role == "admin" or not hours:
            return "نامحدود"
        if hours % 24 == 0:
            days = hours // 24
            return "۱ روز" if days == 1 else f"{days} روز"
        return f"{hours} ساعت"

    def edit_deadline(self, created_at):
        """When this user's window on a record written at ``created_at`` shuts.

        ``None`` means it never shuts — either the user has no window or the
        record carries no creation time (rows imported before this release).
        """
        if not self.has_edit_window or created_at is None:
            return None
        return created_at + timedelta(hours=self.edit_window_hours)

    @property
    def allowed_pages(self) -> set:
        return {page for page, perm in PAGE_PERMISSION.items() if self.can(perm)}

    def to_dict(self, include_permissions=True):
        from ..services.jalali import to_tehran
        data = {
            "id": self.id, "username": self.username,
            "first_name": self.first_name, "last_name": self.last_name,
            "full_name": self.full_name, "father_name": self.father_name,
            "national_id": self.national_id, "personnel_code": self.personnel_code,
            "birth_date": self.birth_date.isoformat() if self.birth_date else None,
            "phone": self.phone, "email": self.email,
            "position": self.position, "unit": self.unit,
            "role": self.role, "role_label": self.role_label,
            "is_active": self.is_active,
            "must_change_password": self.must_change_password,
            "notes": self.notes,
            "last_login_at": (to_tehran(self.last_login_at).isoformat()
                              if self.last_login_at else None),
            "last_login_ip": self.last_login_ip,
            "login_count": self.login_count,
            "is_locked": bool(self.locked_until and self.locked_until > local_now()),
            "edit_window_hours": self.edit_window_hours,
            "edit_window_label": self.edit_window_label,
            "center_ids": [c.id for c in self.centers],
            "center_names": [c.label for c in self.centers],
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if include_permissions:
            data["permissions"] = sorted(self.permissions)
            data["custom_permissions"] = self.permissions_json is not None
            data["allowed_pages"] = sorted(self.allowed_pages)
        return data


class UserSession(db.Model):
    """One login. Closed on logout, or marked expired by the sweeper."""
    __tablename__ = "user_sessions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("app_users.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    token = db.Column(db.String(64), unique=True, nullable=False, index=True)
    login_at = db.Column(db.DateTime, default=local_now, nullable=False, index=True)
    last_seen_at = db.Column(db.DateTime, default=local_now, nullable=False)
    logout_at = db.Column(db.DateTime)
    ip_address = db.Column(db.String(60))
    user_agent = db.Column(db.String(300))
    end_reason = db.Column(db.String(30))   # logout | expired | disabled

    user = db.relationship("AppUser", back_populates="sessions")

    @staticmethod
    def new_token() -> str:
        return secrets.token_urlsafe(32)[:64]

    @property
    def duration_seconds(self):
        end = self.logout_at or self.last_seen_at
        if not end or not self.login_at:
            return None
        return int((end - self.login_at).total_seconds())

    def to_dict(self):
        from ..services.jalali import to_tehran
        local = lambda v: to_tehran(v).isoformat() if v else None
        return {
            "id": self.id, "user_id": self.user_id,
            "username": self.user.username if self.user else None,
            "full_name": self.user.full_name if self.user else None,
            # Local (Tehran) times: what the operator's own clock showed.
            "login_at": local(self.login_at),
            "last_seen_at": local(self.last_seen_at),
            "logout_at": local(self.logout_at),
            "duration_seconds": self.duration_seconds,
            "ip_address": self.ip_address, "user_agent": self.user_agent,
            "end_reason": self.end_reason,
            "is_open": self.logout_at is None,
        }
