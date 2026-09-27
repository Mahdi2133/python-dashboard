# -*- coding: utf-8 -*-
"""Background work for reports: scheduled runs and heavy exports.

One daemon thread per server process wakes every minute, runs the schedules
that are due (each run is kept as a snapshot) and nothing else. A heavy export
runs on its own short-lived thread and leaves its file in the exports folder
for the person who asked for it.
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
import os
import threading
import time
import uuid

from ..extensions import db
from ..paths import exports_dir
from ..services.jalali import local_now

log = logging.getLogger(__name__)

FREQUENCIES = {"daily": "روزانه", "weekly": "هفتگی", "monthly": "ماهانه",
               "quarterly": "فصلی"}
_STARTED = {"worker": False}


def next_run(frequency: str, hour: int, after: _dt.datetime | None = None) -> _dt.datetime:
    after = after or local_now()
    hour = max(0, min(23, int(hour or 0)))
    base = after.replace(hour=hour, minute=0, second=0, microsecond=0)
    if frequency == "daily":
        return base if base > after else base + _dt.timedelta(days=1)
    if frequency == "weekly":
        # Saturday, the first day of the Iranian week
        days = (5 - base.weekday()) % 7
        cand = base + _dt.timedelta(days=days)
        return cand if cand > after else cand + _dt.timedelta(days=7)
    # monthly / quarterly: the first day of the next Jalali month (or quarter)
    from ..services.jalali import gregorian_to_jalali, jalali_to_gregorian
    jy, jm, _jd = gregorian_to_jalali(after.date())
    step = 3 if frequency == "quarterly" else 1
    if frequency == "quarterly":
        jm = ((jm - 1) // 3) * 3 + 1
    for _ in range(6):
        jm += step
        if jm > 12:
            jm -= 12
            jy += 1
        g = jalali_to_gregorian(jy, jm, 1)
        g = g if isinstance(g, _dt.date) else _dt.date(*g)
        cand = _dt.datetime(g.year, g.month, g.day, hour)
        if cand > after:
            return cand
    return after + _dt.timedelta(days=30)


def run_schedule(schedule) -> str:
    """Run one schedule now: a snapshot of the published version."""
    from ..models.report import ReportSnapshot
    from .engine import ReportError, run_report
    from .formula import FormulaError
    report = schedule.report
    version = report.published_version if report else None
    if version is None:
        schedule.last_status = "گزارش منتشرشده نیست؛ اجرا نشد."
    else:
        try:
            res = run_report(version.definition)
            from ..services.jalali import to_jalali_str
            snap = ReportSnapshot(report_id=report.id, version_id=version.id,
                                  title=f"{report.name} — {FREQUENCIES.get(schedule.frequency, '')} "
                                        f"{to_jalali_str(local_now())}",
                                  result_json=json.dumps(res, ensure_ascii=False, default=str),
                                  row_count=res.get("row_count") or 0, source="schedule",
                                  created_by=schedule.created_by)
            db.session.add(snap)
            schedule.last_status = f"اجرا شد ({res.get('row_count', 0):,} ردیف)"
        except (ReportError, FormulaError) as exc:
            schedule.last_status = f"خطا: {exc}"[:200]
    schedule.last_run_at = local_now()
    schedule.next_run_at = next_run(schedule.frequency, schedule.hour)
    return schedule.last_status


def run_due_schedules():
    from ..models.report import ReportSchedule
    due = (ReportSchedule.query.filter(ReportSchedule.is_active.is_(True))
           .filter(ReportSchedule.next_run_at <= local_now()).all())
    for s in due:
        try:
            run_schedule(s)
            db.session.commit()
        except Exception:  # noqa: BLE001
            db.session.rollback()
            log.exception("Scheduled report %s failed", s.id)


def start_worker(app):
    if _STARTED["worker"] or app.config.get("TESTING") \
            or os.environ.get("ELECTROPUMP_NO_WORKER") == "1":
        return
    _STARTED["worker"] = True

    def loop():
        time.sleep(20)
        while True:
            try:
                with app.app_context():
                    run_due_schedules()
            except Exception:  # noqa: BLE001
                log.exception("Report worker tick failed")
            time.sleep(60)

    threading.Thread(target=loop, name="report-worker", daemon=True).start()


# ── export jobs ─────────────────────────────────────────────────────────────
def job_path(stored_name: str):
    folder = exports_dir() / "report_jobs"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / stored_name


def start_export_job(app, job_id: int, build):
    """Run ``build() -> (bytes, filename)`` on a thread and keep the file."""
    from ..models.report import ReportExportJob

    def work():
        with app.app_context():
            job = db.session.get(ReportExportJob, job_id)
            if job is None:
                return
            job.status = "running"
            db.session.commit()
            try:
                payload, filename = build()
                stored = f"{uuid.uuid4().hex}.{job.fmt}"
                job_path(stored).write_bytes(payload)
                job.stored_name = stored
                job.file_name = filename
                job.status = "done"
                job.message = f"{len(payload) / 1024:,.0f} KB"
            except Exception as exc:  # noqa: BLE001
                log.exception("Export job %s failed", job_id)
                job.status = "failed"
                job.message = str(exc)[:500]
            job.finished_at = local_now()
            db.session.commit()

    threading.Thread(target=work, name=f"report-export-{job_id}", daemon=True).start()
