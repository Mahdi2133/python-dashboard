"""/api/reports — fixed reports, the report builder and their exports."""
from flask import Blueprint, Response, request

from ..reports import DATASETS, REPORTS, run_builder, run_report
from ..reports.builder import AGGREGATIONS, OPERATORS
from ..services.auth import permission_required
from ..services.audit import record_audit
from ..services.exporter import render
from ..services.jalali import today_jalali
from ._helpers import body, fail, ok, query_params

bp = Blueprint("api_reports", __name__, url_prefix="/api/reports")


@bp.get("")
@permission_required("report.view")
def list_reports():
    return ok({
        "reports": [{"key": k, "title": v["title"], "description": v["desc"]}
                    for k, v in REPORTS.items()],
        "datasets": {k: {"label": v["label"],
                         "fields": [{"key": f["key"], "label": f["label"],
                                     "kind": f["kind"]} for f in v["fields"]]}
                     for k, v in DATASETS.items()},
        "aggregations": [{"key": k, "label": v[0]} for k, v in AGGREGATIONS.items()],
        "operators": [{"key": k, "label": v} for k, v in OPERATORS.items()],
    })


@bp.get("/<key>")
@permission_required("report.view")
def get_report(key):
    if key not in REPORTS:
        return fail("گزارش موردنظر تعریف نشده است.", 404)
    return ok(run_report(key, query_params()))


@bp.post("/builder")
@permission_required("report.build")
def builder():
    try:
        result = run_builder(body())
    except ValueError as exc:
        return fail(str(exc), 422)
    result.setdefault("title", "گزارش سفارشی")
    return ok(result)


def _download(result, fmt, filename_stem):
    jy, jm, jd = today_jalali()
    stamp = f"{jy}-{jm:02d}-{jd:02d}"          # filenames: hyphens
    # Slashes, not hyphens, inside Persian text: the bidi algorithm treats a
    # hyphen between digit groups as a separator and reverses their order,
    # turning 1405-06-22 into 22-06-1405 in the PDF.
    shown = f"{jy}/{jm:02d}/{jd:02d}"
    meta = {"تاریخ تهیه": shown, "تعداد سطر": len(result["rows"])}
    meta.update({k: v for k, v in (result.get("filters") or {}).items()})
    try:
        payload, mimetype, ext = render(fmt, result["columns"], result["rows"],
                                        result.get("title", "گزارش"), meta)
    except (ValueError, RuntimeError) as exc:
        return fail(str(exc), 422)
    record_audit("export", "report", None,
                 summary=f"خروجی {fmt} از «{result.get('title')}»", commit=True)
    return Response(payload, mimetype=mimetype, headers={
        "Content-Disposition":
            f'attachment; filename="{filename_stem}_{stamp}.{ext}"; '
            f"filename*=UTF-8''{filename_stem}_{stamp}.{ext}"})


@bp.get("/<key>/export.<fmt>")
@permission_required("record.export")
def export_report(key, fmt):
    if key not in REPORTS:
        return fail("گزارش موردنظر تعریف نشده است.", 404)
    return _download(run_report(key, query_params()), fmt, f"report_{key}")


@bp.post("/builder/export.<fmt>")
@permission_required("record.export")
def export_builder(fmt):
    try:
        result = run_builder(body())
    except ValueError as exc:
        return fail(str(exc), 422)
    result.setdefault("title", "گزارش سفارشی")
    return _download(result, fmt, "custom_report")
