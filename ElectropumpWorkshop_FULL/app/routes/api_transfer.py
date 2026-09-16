"""/api/import and /api/export — raw data in and out (requirements 22 & 23)."""
import json

from flask import Blueprint, Response, request
from werkzeug.utils import secure_filename

from ..models import FormField
from ..paths import uploads_dir
from ..services.auth import login_required, permission_required
from ..services.audit import record_audit
from ..services.exporter import render
from ..services.importer import (commit_import, import_localstorage, preview,
                                 read_sheet)
from ..services.jalali import MONTHS_FA, today_jalali
from ..services.records import search_query, serialize_record
from ._helpers import body, fail, ok, query_params

bp = Blueprint("api_transfer", __name__, url_prefix="/api")

ALLOWED_EXT = {".xls", ".xlsx", ".xlsm"}


# ── export of the raw record table ───────────────────────────────────────────
def _export_columns():
    """The 51 Persian headers of the original export, driven by the form."""
    fields = (FormField.query.filter(FormField.is_active.is_(True))
              .order_by(FormField.section_id, FormField.sort_order).all())
    columns = [{"key": "row_no", "label": "ردیف"},
               {"key": "date_display", "label": "تاریخ"},
               {"key": "j_day", "label": "روز"},
               {"key": "month_name", "label": "ماه"},
               {"key": "j_month", "label": "ماه(عدد)"},
               {"key": "j_year", "label": "سال"}]
    seen = {c["key"] for c in columns}
    for field in fields:
        if field.field_name in ("op_jdate",):
            continue
        # The PM code and well class sit next to the well name, matching the
        # order the maintenance workbook uses.
        if field.field_name == "well":
            columns.append({"key": "well", "label": field.export_header or "نام چاه"})
            columns.append({"key": "well_pm_code", "label": "کد PM"})
            columns.append({"key": "well_class", "label": "کلاسه چاه"})
            seen.update({"well", "well_pm_code", "well_class"})
            continue
        key = (field.model_attr[:-3] if field.model_attr
               and field.model_attr.endswith("_id") else
               (field.model_attr or field.field_name))
        if field.field_name in ("failure", "workshop_opinion", "desc_tags"):
            key = field.field_name
        if key in seen:
            continue
        seen.add(key)
        columns.append({"key": key, "label": field.export_header or field.label})
    return columns


def _export_rows(columns):
    rows = []
    for idx, record in enumerate(search_query(query_params()).limit(50000).all(), 1):
        data = serialize_record(record)
        data["row_no"] = idx
        rows.append({c["key"]: data.get(c["key"]) for c in columns})
    return rows


@bp.get("/export.<fmt>")
@permission_required("record.export")
def export_records(fmt):
    columns = _export_columns()
    rows = _export_rows(columns)
    jy, jm, jd = today_jalali()
    stamp = f"{jy}-{jm:02d}-{jd:02d}"          # filenames: hyphens
    shown = f"{jy}/{jm:02d}/{jd:02d}"          # in-document text: slashes (bidi-safe)
    try:
        payload, mimetype, ext = render(
            fmt, columns, rows, "اطلاعات الکتروپمپ",
            {"تاریخ تهیه": shown, "تعداد رکورد": len(rows)})
    except (ValueError, RuntimeError) as exc:
        return fail(str(exc), 422)
    record_audit("export", "record", None,
                 summary=f"خروجی {fmt} از {len(rows)} رکورد", commit=True)
    return Response(payload, mimetype=mimetype, headers={
        "Content-Disposition": f'attachment; filename="electropump_{stamp}.{ext}"'})


# ── Excel import wizard ──────────────────────────────────────────────────────
@bp.post("/import/upload")
@permission_required("data.import")
def upload():
    upload_file = request.files.get("file")
    if upload_file is None or not upload_file.filename:
        return fail("فایلی انتخاب نشده است.", 422)
    name = secure_filename(upload_file.filename) or "import.xlsx"
    if not any(name.lower().endswith(e) for e in ALLOWED_EXT):
        return fail("فقط فایل‌های .xls و .xlsx پشتیبانی می‌شوند.", 422)
    path = uploads_dir() / name
    upload_file.save(path)
    try:
        sheets, _, _ = read_sheet(path)
    except Exception as exc:
        return fail(f"فایل اکسل قابل خواندن نیست: {exc}", 422)
    return ok({"filename": name, "sheets": sheets},
              message="فایل بارگذاری شد. شیت موردنظر را انتخاب کنید.")


@bp.get("/import/preview")
@permission_required("data.import")
def import_preview():
    name = secure_filename(request.args.get("filename", ""))
    path = uploads_dir() / name
    if not name or not path.exists():
        return fail("فایل بارگذاری‌شده یافت نشد. دوباره بارگذاری کنید.", 404)
    try:
        info = preview(path, request.args.get("sheet") or None,
                       limit=int(request.args.get("limit", 15)))
    except Exception as exc:
        return fail(f"خواندن شیت ناموفق بود: {exc}", 422)
    info["filename"] = name
    return ok(info)


@bp.post("/import/commit")
@permission_required("data.import")
def import_commit():
    payload = body()
    name = secure_filename(payload.get("filename", ""))
    path = uploads_dir() / name
    if not name or not path.exists():
        return fail("فایل بارگذاری‌شده یافت نشد.", 404)
    mapping = payload.get("mapping") or {}
    if not any(mapping.values()):
        return fail("هیچ ستونی نگاشت نشده است.", 422)
    try:
        result = commit_import(
            path, payload.get("sheet"), mapping,
            int(payload.get("data_start") or 0),
            skip_duplicates=payload.get("skip_duplicates", True)
            in (True, "true", "1", 1),
            dry_run=payload.get("dry_run") in (True, "true", "1", 1),
            filename=name)
    except Exception as exc:
        return fail(f"ورود داده ناموفق بود: {exc}", 500)
    verb = "بررسی آزمایشی" if result["dry_run"] else "ورود داده"
    return ok(result, message=f"{verb} انجام شد: {result['inserted']} درج، "
                              f"{result['skipped']} رد، {result['failed']} خطا.")


# ── localStorage migration ───────────────────────────────────────────────────
@bp.post("/import/localstorage")
@permission_required("data.import")
def localstorage():
    payload = body()
    raw = payload.get("records")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return fail("محتوای localStorage قابل خواندن نیست (JSON نامعتبر).", 422)
    if not isinstance(raw, list):
        return fail("ساختار داده باید یک آرایه از رکوردها باشد.", 422)
    if not raw:
        return fail("هیچ رکوردی برای انتقال یافت نشد.", 422)
    result = import_localstorage(
        raw, skip_duplicates=payload.get("skip_duplicates", True)
        in (True, "true", "1", 1))
    return ok(result, message=f"{result['inserted']} رکورد از localStorage منتقل شد "
                              f"({result['skipped']} تکراری، {result['failed']} خطا).")


@bp.get("/months")
@login_required
def months():
    return ok([{"value": i, "label": MONTHS_FA[i]} for i in range(1, 13)])
