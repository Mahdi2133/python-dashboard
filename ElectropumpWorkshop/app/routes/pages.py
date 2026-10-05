"""Server-rendered pages. Each is a thin shell; data arrives over the API."""
from flask import (Blueprint, current_app, redirect, render_template,
                   url_for)

from ..models import FormSection
from ..paths import database_file, load_config
from ..reports import REPORTS
from ..services.auth import current_user, login_required, permission_required
from ..services.jalali import MONTHS_FA, today_jalali
from ..services.network import lan_addresses

bp = Blueprint("pages", __name__)

# Data entry comes first: it is what the workshop opens the program to do,
# and it is the landing page the EXE points the browser at.
NAV = [
    ("entry", "ثبت اطلاعات", "📝", "/"),
    ("inbox", "کارتابل فرایند", "📬", "/inbox"),
    ("dashboard", "داشبورد", "📊", "/dashboard"),
    ("records", "رکوردها", "📋", "/records"),
    ("documents", "مستندات", "📎", "/documents"),
    ("wells", "چاه‌ها", "🕳", "/wells"),
    ("reports", "گزارش‌ها", "📈", "/reports"),
    ("builder", "گزارش‌ساز", "🧩", "/report-builder"),
    ("formbuilder", "فرم‌ساز", "🛠", "/form-builder"),
    ("workflow", "فرایندساز", "🔀", "/workflow"),
    ("options", "مدیریت گزینه‌ها", "🗂", "/options"),
    ("catalogue", "کاتالوگ پمپ", "📘", "/catalogue"),
    ("transfer", "ورود / خروج داده", "🔁", "/transfer"),
    ("users", "کاربران", "👤", "/users"),
    ("settings", "تنظیمات", "⚙", "/settings"),
]


@bp.app_context_processor
def inject_globals():
    jy, jm, jd = today_jalali()
    return {
        "NAV": NAV,
        "MONTHS_FA": MONTHS_FA,
        "TODAY_J": {"year": jy, "month": jm, "day": jd},
        "TODAY_J_STR": f"{jy}/{jm:02d}/{jd:02d}",
    }


@bp.get("/")
@login_required
def home():
    """Send each user to the first page they are actually allowed to open.

    Data entry is the intended landing page, but a read-only account has no
    business there, so the redirect follows the NAV order and lands them on
    whatever they can use.
    """
    user = current_user()
    allowed = user.allowed_pages if user else set()
    for key, _label, _icon, href in NAV:
        if key in allowed:
            return redirect(href if href != "/" else url_for("pages.entry"))
    return render_template(
        "error.html", code=403,
        message="برای هیچ بخشی از سامانه به شما دسترسی داده نشده است. "
                "با مدیر سیستم تماس بگیرید."), 403


@bp.get("/entry")
@bp.get("/entry/<int:record_id>")
@permission_required("record.create")
def entry(record_id=None):
    return render_template("entry.html", active="entry", record_id=record_id)


@bp.get("/dashboard")
@permission_required("dashboard.view")
def dashboard():
    return render_template("dashboard.html", active="dashboard")


@bp.get("/records")
@permission_required("record.view")
def records():
    return render_template("records.html", active="records")


@bp.get("/wells")
@permission_required("well.view")
def wells():
    return render_template("wells.html", active="wells")


@bp.get("/reports")
@permission_required("report.view")
def reports():
    return render_template(
        "reports.html", active="reports",
        reports=[{"key": k, "title": v["title"], "desc": v["desc"]}
                 for k, v in REPORTS.items()])


@bp.get("/report-builder")
@permission_required("report.manage")
def report_builder():
    return render_template("report_builder.html", active="builder")


@bp.get("/report-builder/legacy")
@permission_required("report.build")
def report_builder_legacy():
    # the earlier builder: per-stage Excel export and the quick column report
    return render_template("report_builder_legacy.html", active="builder")


@bp.get("/form-builder")
@permission_required("form.manage")
def form_builder():
    return render_template("form_builder.html", active="formbuilder",
                           sections=FormSection.query.order_by(
                               FormSection.sort_order).all())


@bp.get("/inbox")
@permission_required("workflow.act")
def inbox():
    """The کارتابل: the stages this person owes, and the forms to fill them."""
    return render_template("inbox.html", active="inbox")


@bp.get("/documents")
@permission_required("workflow.act")
def documents():
    """Every file attached to any process — admin and stage owners alike."""
    return render_template("documents.html", active="documents")


@bp.get("/workflow")
@permission_required("workflow.manage")
def workflow():
    """The process builder, plus the map of every process in flight."""
    return render_template("workflow.html", active="workflow")


@bp.get("/options")
@permission_required("form.manage")
def options():
    return render_template("options.html", active="options")


@bp.get("/catalogue")
@permission_required("form.manage")
def catalogue():
    """The pump catalogue the forms read curves from: view, edit, Excel in/out."""
    return render_template("catalogue.html", active="catalogue")


@bp.get("/transfer")
@permission_required("data.import")
def transfer():
    return render_template("transfer.html", active="transfer")


@bp.get("/users")
@permission_required("user.manage")
def users():
    from ..models.auth import ROLES
    return render_template("users.html", active="users", roles=ROLES)


@bp.get("/settings")
@permission_required("settings.view")
def settings():
    cfg = load_config()
    return render_template("settings.html", active="settings",
                           db_path=str(database_file(cfg)),
                           port=cfg.get("port"),
                           network_urls=[f"http://{ip}:{cfg.get('port')}"
                                         for ip in lan_addresses()])


@bp.get("/print/report/<key>")
@permission_required("report.view")
def print_report(key):
    """Print-friendly page — the browser's Print → PDF keeps Persian/RTL perfect."""
    from ..reports import run_report
    from flask import request
    params = request.args.to_dict()
    try:
        result = run_report(key, params)
    except KeyError:
        result = None
    return render_template("print_report.html", report=result, key=key)


@bp.get("/healthz")
def healthz():
    """Unauthenticated on purpose: the launcher polls it before opening the
    browser, and a monitoring check must not need a password."""
    return {"ok": True, "app": current_app.config["APP_TITLE"]}
