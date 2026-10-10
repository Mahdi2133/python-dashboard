"""One-time changes for this release, once per database (see upgrade_r13).

* every reference row is matched to the register again with the corrected
  rules (refdata.matching) — the flow tests of sheets copied from another
  well's form, the rows that sat on a merged or «قدیم» copy of a well;
* «حداکثر آمپر مجاز» of the pump-selection form is the catalogue's rated
  current of the pump type and stage count chosen beside it;
* «دبی قبل از کشیدن» — drawn in the flow-test calculations as «آخرین دبی» —
  starts from the production trend's last operating flow.

A field the admin has changed since the previous release is left alone.
"""
from __future__ import annotations

import logging

from ..extensions import db

log = logging.getLogger(__name__)

KEY = "r14_refdata_forms_v1"

MAX_AMP_FORMULA = "CAT_A([am_pump], [no_ste_2])"
MAX_AMP_HELP = ("جریان نامی الکتروموتور در کاتالوگ پمپ، برای تیپ پمپ و تعداد طبقات پیشنهادی همین فرم؛ "
                "اگر خالی ماند، این ترکیب در کاتالوگ نیست.")
LAST_FLOW_PREFILL = "@ref:pr.last_flow"


def apply_r14() -> dict:
    from ..models import AppMeta
    if AppMeta.get(KEY):
        return {}
    done = {}
    for name, step in (("relink", _relink), ("max_amp", _max_amp), ("last_flow", _last_flow)):
        try:
            done[name] = step()
            db.session.commit()
        except Exception:  # noqa: BLE001 — one step failing leaves the others in
            db.session.rollback()
            log.exception("R14 change «%s» failed", name)
            done[name] = "failed"
    AppMeta.set(KEY, "done")
    db.session.commit()
    log.info("R14 changes: %s", done)
    return done


def _relink():
    from ..refdata import flowrecords, flowtest, production, videometry
    from ..refdata.matching import WellIndex
    index = WellIndex()
    return {"flowtest": flowtest.relink(index), "production": production.relink(index),
            "videometry": videometry.relink(index), "flowrec": flowrecords.relink(index)}


def _max_amp():
    from ..models import FormField
    f = FormField.query.filter_by(field_name="ps_max_amp").first()
    if f is None or f.field_type != "number" or (f.formula or "").strip():
        return 0
    if f.prefill_from not in (None, "", "@ref:ft.allowed_current"):
        return 0
    if not all(FormField.query.filter_by(field_name=n).first() for n in ("am_pump", "no_ste_2")):
        return 0
    f.field_type = "formula"
    f.formula = MAX_AMP_FORMULA
    f.prefill_from = None
    f.step = f.step or "1"
    if not f.help_text:
        f.help_text = MAX_AMP_HELP
    return 1


def _last_flow():
    from ..models import FormField
    f = FormField.query.filter_by(field_name="flow_before_pull").first()
    if f is None or f.field_type != "number" or (f.prefill_from or "").strip():
        return 0
    f.prefill_from = LAST_FLOW_PREFILL
    return 1
