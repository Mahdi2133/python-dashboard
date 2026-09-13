"""Server-rendered pages. Each is a thin shell; data arrives over the API."""
from flask import Blueprint, current_app, render_template

from ..models import FormSection
from ..paths import database_file, load_config
from ..reports import REPORTS
from ..services.jalali import MONTHS_FA, today_jalali
from ..services.network import lan_addresses

bp = Blueprint("pages", __name__)

NAV = [
    ("dashboard", "داشبورد", "📊", "/"),
    ("entry", "ثبت اطلاعات", "📝", "/entry"),
    ("records", "رکوردها", "📋", "/records"),
    ("wells", "چاه‌ها", "🕳", "/wells"),
    ("reports", "گزارش‌ها", "📈", "/reports"),
    ("builder", "گزارش‌ساز", "🧩", "/report-builder"),
    ("formbuilder", "فرم‌ساز", "🛠", "/form-builder"),
    ("options", "مدیریت گزینه‌ها", "🗂", "/options"),
    ("transfer", "ورود / خروج داده", "🔁", "/transfer"),
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
def dashboard():
    return render_template("dashboard.html", active="dashboard")


@bp.get("/entry")
@bp.get("/entry/<int:record_id>")
def entry(record_id=None):
    return render_template("entry.html", active="entry", record_id=record_id)


@bp.get("/records")
def records():
    return render_template("records.html", active="records")


@bp.get("/wells")
def wells():
    return render_template("wells.html", active="wells")


@bp.get("/reports")
def reports():
    return render_template(
        "reports.html", active="reports",
        reports=[{"key": k, "title": v["title"], "desc": v["desc"]}
                 for k, v in REPORTS.items()])


@bp.get("/report-builder")
def report_builder():
    return render_template("report_builder.html", active="builder")


@bp.get("/form-builder")
def form_builder():
    return render_template("form_builder.html", active="formbuilder",
                           sections=FormSection.query.order_by(
                               FormSection.sort_order).all())


@bp.get("/options")
def options():
    return render_template("options.html", active="options")


@bp.get("/transfer")
def transfer():
    return render_template("transfer.html", active="transfer")


@bp.get("/settings")
def settings():
    cfg = load_config()
    return render_template("settings.html", active="settings",
                           db_path=str(database_file(cfg)),
                           port=cfg.get("port"),
                           network_urls=[f"http://{ip}:{cfg.get('port')}"
                                         for ip in lan_addresses()])


@bp.get("/print/report/<key>")
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
    return {"ok": True, "app": current_app.config["APP_TITLE"]}
