# -*- coding: utf-8 -*-
"""«ارجاع برای تأیید» — send chosen forms, a note and documents for a ruling.

The person on a stage picks which of the forms filled so far (on earlier
stages, and their own stage as it stands) go with the request, writes why,
attaches documents, and chooses the approver. The approver sees exactly that —
a snapshot — and approves or rejects with a comment. The answer returns to the
person who asked; they then finish their stage and the process goes on.

The admin can also make it compulsory: a form on a stage marked «تأیید اجباری
توسط …» must have been sent to that person and approved — with the values it
now holds — before the stage can be finalised.
"""
from __future__ import annotations

import hashlib
import json

from ..extensions import db
from ..models import AppUser, WorkflowApprovalRequest, WorkflowAttachment
from ..models.workflow import (APPROVAL_APPROVED, APPROVAL_CANCELLED, APPROVAL_PENDING,
                               APPROVAL_REJECTED, ENTRY_DONE)
from .audit import record_audit
from .jalali import MONTHS_FA, local_now


class ApprovalError(ValueError):
    pass


def _wf():
    from . import workflow as wf
    return wf


def _fmt(field, value, files_by_field):
    if field.get("field_type") == "chart":
        return None
    if field.get("field_type") == "numbers":
        from .records import numbers_text
        parts = field.get("part_labels") or []
        text = numbers_text(value)
        return (f"{text} ({' / '.join(parts)})" if text and parts else text)
    if field.get("field_type") == "file":
        return "، ".join(a["filename"] for a in files_by_field.get(field.get("field_name"), [])) or "—"
    if value in (None, "", [], {}):
        return None
    if field.get("lookup_category") == "__months__" and str(value).isdigit() \
            and 1 <= int(value) <= 12:
        return MONTHS_FA[int(value)]
    if isinstance(value, list):
        return "، ".join(str(v) for v in value if v not in (None, ""))
    if value is True:
        return "بله"
    return str(value)


def _values_hash(fields, values, instance=None):
    """What «unchanged since approval» compares: the typed answers, the files in
    each «مستند» slot (from the attachments table), never the computed ones."""
    picked = {}
    for f in fields:
        name = f.get("field_name")
        if f.get("field_type") in ("formula", "chart") or f.get("read_only"):
            continue
        if f.get("field_type") == "file":
            picked[name] = sorted(a.id for a in (getattr(instance, "attachments", None) or [])
                                  if a.field_name == name)
            continue
        v = values.get(name)
        picked[name] = None if v in (None, "", [], {}) else (
            sorted(str(x) for x in v) if isinstance(v, list) else str(v))
    return hashlib.sha1(json.dumps(picked, ensure_ascii=False, sort_keys=True,
                                   default=str).encode("utf-8")).hexdigest()


def _stage_values(instance, stage, draft=None):
    entry = _wf()._entry_for(instance, stage.stage_number)
    values = dict(instance.payload)
    if entry is not None and entry.payload:
        values.update(entry.payload)
    if draft is None and entry is not None and entry.draft_json:
        values.update(entry.draft)       # what they had typed when they sent it
    if draft:
        values.update(draft)
    # what the approver reads includes the calculations, as they will be saved
    from .formfields import apply_formulas_to_payload
    return apply_formulas_to_payload(values)


def attachable_blocks(instance, stage, draft=None) -> list:
    """The forms that may go with a request from ``stage``: earlier finished
    stages' forms, and this stage's own as it stands now."""
    wf = _wf()
    from .formfields import files_by_field
    files = files_by_field(instance)
    out = []
    for other in wf.applicable_stages(instance):
        entry = wf._entry_for(instance, other.stage_number)
        current = other.stage_number == stage.stage_number
        if not current and (entry is None or entry.status not in ENTRY_DONE):
            continue
        values = _stage_values(instance, other, draft if current else None)
        form = wf.stage_form(instance, other, draft if current else None)
        for block in form["sections"]:
            if block.get("is_locked"):
                continue
            fields = block.get("fields") or []
            filled = [f for f in fields if _fmt(f, values.get(f.get("field_name")), files)
                      not in (None, "—")]
            # a form nobody opened (a cause not ticked) or a finished stage's
            # empty form has nothing to show an approver
            if not filled and (block.get("conditional") or not current):
                continue
            out.append({"key": f"{other.stage_number}:{block.get('code')}",
                        "stage_number": other.stage_number, "stage_title": other.title,
                        "code": block.get("code"), "title": block.get("title"),
                        "current": current, "filled": len(filled), "total": len(fields)})
    return out


def _snapshot(instance, stage, keys, draft):
    wf = _wf()
    from .formfields import files_by_field
    files = files_by_field(instance)
    wanted = {}
    for k in keys:
        try:
            n, code = str(k).split(":", 1)
            wanted.setdefault(int(n), set()).add(code)
        except ValueError:
            continue
    snap, hashes = [], {}
    for other in wf.applicable_stages(instance):
        if other.stage_number not in wanted:
            continue
        current = other.stage_number == stage.stage_number
        values = _stage_values(instance, other, draft if current else None)
        form = wf.stage_form(instance, other, draft if current else None)
        for block in form["sections"]:
            if block.get("code") not in wanted[other.stage_number]:
                continue
            fields = block.get("fields") or []
            rows = []
            for f in fields:
                v = _fmt(f, values.get(f.get("field_name")), files)
                if v in (None,):
                    continue
                rows.append({"label": f.get("label"), "value": v,
                             "files": files.get(f.get("field_name"), [])
                             if f.get("field_type") == "file" else None})
            key = f"{other.stage_number}:{block.get('code')}"
            hashes[key] = _values_hash(fields, values, instance)
            snap.append({"key": key, "stage_number": other.stage_number,
                         "stage_title": other.title, "title": block.get("title"),
                         "values": rows})
    return snap, hashes


def allowed_approvers(stage) -> list:
    ids = [int(x) for x in (stage.approval_request_user_ids or "").split(",") if x.strip().isdigit()]
    q = AppUser.query.filter(AppUser.is_active.is_(True))
    if ids:
        q = q.filter(AppUser.id.in_(ids))
    return sorted(q.all(), key=lambda u: u.full_name or "")


def required_items(stage) -> list:
    return [i for i in stage.items if i.approval_user_id and i.section_id]


def _option_fields():
    """Fields with «تأیید گزینه» set: field_name (as drawn) → FormField."""
    from ..models import FormField
    from sqlalchemy import or_
    out = {}
    for f in FormField.query.filter(or_(FormField.approval_user_id.isnot(None),
                                        FormField.approval_rules.isnot(None)),
                                    FormField.is_active.is_(True)).all():
        if f.approval_rule_list:
            out[f.field_name] = f
    return out


def _names_on(stage, options) -> set:
    """Field names a stage may draw: its forms' and single fields, the fields
    assigned to it («مرحله‌ی پرکردن»), and «فیلد مشترک» by what they draw."""
    names = set()
    for item in stage.items:
        fields = (item.section.fields if item.section is not None
                  else [item.field] if item.field is not None else [])
        for f in fields:
            src = f.mirror_source() if f.field_type == "mirror" else f
            names.add((src or f).field_name)
    names.update(n for n, f in options.items() if stage.id in f.fill_stage_list)
    # forms opened by an answer on this stage («اتصال‌ها») are asked here too
    from ..models import FormSection
    from .conditions import parse_rules
    for sec in FormSection.query.filter(FormSection.visible_when.isnot(None),
                                        FormSection.is_active.is_(True)).all():
        if {on for on, _v in parse_rules(sec.visible_when)} & names:
            names.update(f.field_name for f in sec.fields)
    return names


def required_approver_ids(stage) -> set:
    """Everyone a stage's «تأیید اجباری» rules — forms or answers — may go to."""
    ids = {i.approval_user_id for i in required_items(stage)}
    options = _option_fields()
    if options:
        names = _names_on(stage, options)
        for n, f in options.items():
            if n in names:
                for rule in f.approval_rule_list:
                    ids.update(rule["approvers"])
    return ids


def answer_choices(field_name):
    """A choice field an approver answers: (the field, its option values)."""
    from ..models import FormField, LookupCategory
    field = FormField.query.filter_by(field_name=field_name).first()
    if field is None:
        return None, []
    if field.options:
        return field, [o.value for o in field.options if o.is_active]
    cat = LookupCategory.query.filter_by(code=field.lookup_category).first() \
        if field.lookup_category else None
    return field, ([i.value for i in sorted(cat.items, key=lambda x: x.sort_order)
                    if i.is_active] if cat else [])


def _hits(options, value) -> list:
    """Which of the approval-needing ``options`` ``value`` holds."""
    if value in (None, "", [], {}):
        return []
    wanted = set(options)
    have = value if isinstance(value, list) else [value]
    return [str(v) for v in have if str(v) in wanted]


def _opened_by(blocks, field_name, values) -> list:
    """The forms of this page that ``field_name``'s answer opened («اتصال‌ها»):
    they go to the approver with it — the readings behind the answer."""
    from .conditions import parse_rules
    have = values.get(field_name)
    have = {str(v) for v in (have if isinstance(have, list) else [have])
            if v not in (None, "")}
    out = []
    for block in blocks:
        for on, wanted in parse_rules(block.get("visible_when")):
            if on == field_name and have & set(wanted):
                out.append(block)
                break
    return out


def option_rules(instance, stage, payload=None, form=None, values=None) -> list:
    """«تأیید گزینه»: the forms of this stage holding an answer that needs
    somebody's approval — one rule per form and approver."""
    options = _option_fields()
    if not options:
        return []
    wf = _wf()
    values = values if values is not None else _stage_values(instance, stage, payload)
    form = form or wf.stage_form(instance, stage, payload)
    rules = {}
    blocks = [b for b in form["sections"] if not b.get("is_locked")]
    for block in blocks:
        for f in block.get("fields") or []:
            field = options.get(f.get("field_name"))
            if field is None or f.get("read_only"):
                continue
            value = values.get(field.field_name)
            for spec in field.approval_rule_list:
                hits = _hits(spec["options"], value)
                if not hits:
                    continue
                opened = [b for b in _opened_by(blocks, field.field_name,
                                                {field.field_name: hits})
                          if b.get("code") != block.get("code")]
                # every approver named on the rule must approve, each on their own
                for approver_id in spec["approvers"]:
                    rid = f"f{field.id}:{block.get('code')}:{approver_id}"
                    rule = rules.setdefault((block.get("code"), approver_id), {
                        "item_id": rid, "block": block, "approver_id": approver_id,
                        "answers": [], "answer_field": None, "opened": []})
                    rule["answers"].append(f"{f.get('label') or field.label}: {'، '.join(hits)}")
                    rule["answer_field"] = rule["answer_field"] or spec.get("answer_field")
                    for b in opened:
                        if all(b.get("code") != o.get("code") for o in rule["opened"]):
                            rule["opened"].append(b)
    return list(rules.values())


def option_rules_possible(stage) -> bool:
    """Whether any answer on this stage could need «تأیید گزینه»."""
    options = _option_fields()
    return bool(options) and bool(_names_on(stage, options) & set(options))


def requests_for(instance, stage_number) -> list:
    return (WorkflowApprovalRequest.query
            .filter_by(instance_id=instance.id, stage_number=stage_number)
            .order_by(WorkflowApprovalRequest.id.desc()).all())


def required_status(instance, stage, payload=None) -> list:
    """Each «تأیید اجباری» form of this stage: filled yet, and approved as it now stands?"""
    wf = _wf()
    values = _stage_values(instance, stage, payload)
    form = wf.stage_form(instance, stage, payload)
    blocks = {b.get("code"): b for b in form["sections"]}
    history = requests_for(instance, stage.stage_number)
    out = []
    for item in required_items(stage):
        code = item.section.code
        block = blocks.get(code)
        if block is None:
            continue                         # not asked on this run
        key = f"{stage.stage_number}:{code}"
        fields = block.get("fields") or []
        filled = any(values.get(f.get("field_name")) not in (None, "", [], {})
                     for f in fields if not f.get("read_only"))
        now = _values_hash(fields, values, instance)
        state, req = "not_sent", None
        for r in history:
            if key not in r.keys or r.approver_id != item.approval_user_id:
                continue
            req = r
            if r.status == APPROVAL_PENDING:
                state = "pending"
            elif r.status == APPROVAL_APPROVED:
                state = "approved" if r.hashes.get(key) == now else "changed"
            elif r.status == APPROVAL_REJECTED:
                state = "rejected"
            else:
                continue
            break
        approver = db.session.get(AppUser, item.approval_user_id)
        out.append({"item_id": item.id, "key": key, "code": code, "title": block.get("title"),
                    "approver_id": item.approval_user_id,
                    "approver_name": approver.full_name if approver else None,
                    "filled": filled, "state": state,
                    "request_id": req.id if req else None})
    # «تأیید گزینه»: an answer chosen here that the admin said needs approval
    for rule in option_rules(instance, stage, payload, form=form, values=values):
        block = rule["block"]
        code = block.get("code")
        key = f"{stage.stage_number}:{code}"
        if any(o["key"] == key and o["approver_id"] == rule["approver_id"] for o in out):
            continue                         # the form's own rule already covers it
        # the answer's own form, and the forms it opened, are approved as a whole
        parts = [block] + rule.get("opened", [])
        keys = [f"{stage.stage_number}:{b.get('code')}" for b in parts]
        now = {f"{stage.stage_number}:{b.get('code')}":
               _values_hash(b.get("fields") or [], values, instance) for b in parts}
        state, req = _state_of(history, keys, rule["approver_id"], now)
        approver = db.session.get(AppUser, rule["approver_id"])
        out.append({"item_id": rule["item_id"], "key": key, "keys": keys, "code": code,
                    "title": f"{block.get('title')} — {' / '.join(rule['answers'])}",
                    "approver_id": rule["approver_id"],
                    "approver_name": approver.full_name if approver else None,
                    "filled": True, "state": state, "kind": "option",
                    "answer_field": rule.get("answer_field"),
                    "answer_value": req.answer_value if req is not None else None,
                    "request_id": req.id if req else None})
    return out


def _state_of(history, keys, approver_id, now):
    """The latest request covering ``keys`` sent to ``approver_id``, and what
    it means now (``now``: key → hash of what those forms hold today)."""
    for r in history:
        if any(k not in r.keys for k in keys) or r.approver_id != approver_id:
            continue
        if r.status == APPROVAL_PENDING:
            return "pending", r
        if r.status == APPROVAL_APPROVED:
            same = all(r.hashes.get(k) == now.get(k) for k in keys)
            return ("approved" if same else "changed"), r
        if r.status == APPROVAL_REJECTED:
            return "rejected", r
    return "not_sent", None


def answer_blockers(instance, stage, payload) -> list:
    """«مانع ارسال»: answers on this stage with which it may not be sent on —
    «مسیر دسترسی به چاه آماده است؟ خیر» — as Persian reasons."""
    from ..models import FormField
    blocking = {f.field_name: f for f in FormField.query.filter(
        FormField.block_options.isnot(None), FormField.is_active.is_(True)).all()
        if f.block_option_list}
    if not blocking:
        return []
    wf = _wf()
    values = _stage_values(instance, stage, payload)
    reasons = []
    for block in wf.stage_form(instance, stage, payload)["sections"]:
        if block.get("is_locked"):
            continue
        if (block.get("visible_when") or "").strip() \
                and wf._rule_met(block.get("visible_when"), values, set()) is not True:
            continue                         # a form that is not open asks nothing
        for f in block.get("fields") or []:
            field = blocking.get(f.get("field_name"))
            if field is None or f.get("read_only"):
                continue
            if (f.get("visible_when") or "").strip() \
                    and wf._rule_met(f.get("visible_when"), values, set()) is False:
                continue                     # a question not asked
            hits = _hits(field.block_option_list, values.get(field.field_name))
            if hits:
                reasons.append(f"با پاسخ «{'، '.join(hits)}» به «{f.get('label') or field.label}» "
                               "این مرحله به مرحله‌ی بعد نمی‌رود؛ پس از رفع مورد، پاسخ را اصلاح کنید.")
    return reasons


def submit_blockers(instance, stage, payload) -> list:
    """Persian reasons this stage may not be finalised yet (empty = free)."""
    reasons = answer_blockers(instance, stage, payload)
    pending = [r for r in requests_for(instance, stage.stage_number) if r.status == APPROVAL_PENDING]
    for r in pending:
        reasons.append(f"درخواست تأیید این مرحله نزد «{r.approver.full_name if r.approver else '—'}» "
                       f"در انتظار پاسخ است؛ پس از پاسخ ادامه دهید.")
    for st in required_status(instance, stage, payload):
        if st["state"] == "approved" or st["state"] == "pending":
            continue
        if st.get("kind") == "option":
            what = st["title"].split(" — ", 1)[-1]
            if st["state"] == "rejected":
                reasons.append(f"پاسخ «{what}» را «{st['approver_name']}» تأیید نکرده است؛ "
                               f"پاسخ را اصلاح کنید یا دوباره برای تأیید بفرستید.")
            else:
                reasons.append(f"پاسخ «{what}» نیاز به تأیید «{st['approver_name']}» دارد"
                               + (" و پس از تأیید تغییر کرده است" if st["state"] == "changed" else "")
                               + "؛ از «ارجاع برای تأیید» آن را بفرستید.")
            continue
        if st["state"] == "changed":
            reasons.append(f"فرم «{st['title']}» پس از تأیید تغییر کرده است؛ دوباره برای تأیید "
                           f"«{st['approver_name']}» ارسال کنید.")
        elif st["state"] == "rejected":
            reasons.append(f"فرم «{st['title']}» را «{st['approver_name']}» تأیید نکرده است؛ "
                           f"پس از اصلاح دوباره برای تأیید ارسال کنید.")
        else:
            reasons.append(f"فرم «{st['title']}» باید پیش از ثبت نهایی به تأیید "
                           f"«{st['approver_name']}» برسد («ارجاع برای تأیید»).")
    return reasons


def create_request(instance, stage_number, user, approver_id, keys, note=None,
                   draft=None, rule_item_id=None):
    wf = _wf()
    if instance.status != "open":
        raise ApprovalError("این فرایند بسته شده است.")
    stage = wf.stage_by_number(instance, int(stage_number))
    if stage is None:
        raise ApprovalError("مرحله پیدا نشد.")
    if not wf.may_act(user, instance, stage):
        raise ApprovalError("این مرحله در اختیار شما نیست.")
    rule = None
    ruled = False
    answer_field = None
    if rule_item_id:
        # a form's «تأیید اجباری» (the stage item's id) or an answer's
        # «تأیید گزینه» ("f<field id>:<form code>"), as required_status lists them
        st = next((r for r in required_status(instance, stage, draft)
                   if str(r["item_id"]) == str(rule_item_id)), None)
        if st is None:
            raise ApprovalError("قاعده‌ی تأیید اجباری پیدا نشد (شاید پاسخ تغییر کرده است).")
        ruled = True
        if st.get("kind") != "option":
            rule = next((i for i in required_items(stage) if i.id == st["item_id"]), None)
        answer_field = st.get("answer_field")
        approver_id = st["approver_id"]
        keys = list(dict.fromkeys(list(keys or []) + list(st.get("keys") or [st["key"]])))
    elif not stage.approval_request_enabled and not required_items(stage) \
            and not option_rules(instance, stage, draft):
        raise ApprovalError("«ارجاع برای تأیید» برای این مرحله فعال نشده است.")
    approver = db.session.get(AppUser, int(approver_id or 0))
    if approver is None or not approver.is_active:
        raise ApprovalError("تأییدکننده را انتخاب کنید.")
    required_ids = required_approver_ids(stage)
    if not ruled and approver.id not in {u.id for u in allowed_approvers(stage)} \
            and approver.id not in required_ids:
        raise ApprovalError(f"«{approver.full_name}» در فهرست تأییدکننده‌های این مرحله نیست.")
    if approver.id == user.id:
        raise ApprovalError("نمی‌توانید درخواست تأیید را به خودتان بفرستید.")
    if not keys:
        raise ApprovalError("دست‌کم یک فرم را برای ضمیمه انتخاب کنید.")
    if any(r.status == APPROVAL_PENDING and r.approver_id == approver.id
           for r in requests_for(instance, stage.stage_number)):
        raise ApprovalError(f"یک درخواست تأیید نزد «{approver.full_name}» هنوز بی‌پاسخ است.")
    draft = {k: v for k, v in (draft or {}).items()} if draft else None
    # keep what they typed: the form is still theirs to finish when the answer comes
    entry = wf._ensure_entry(instance, stage)
    if draft:
        entry.draft_json = json.dumps(draft, ensure_ascii=False)
    snap, hashes = _snapshot(instance, stage, keys, draft)
    if not snap:
        raise ApprovalError("فرم‌های انتخاب‌شده در این فرایند پیدا نشدند.")
    req = WorkflowApprovalRequest(
        instance_id=instance.id, stage_number=stage.stage_number, requested_by=user.id,
        approver_id=approver.id, note=(note or "").strip() or None,
        sections_json=json.dumps([s["key"] for s in snap], ensure_ascii=False),
        snapshot_json=json.dumps(snap, ensure_ascii=False, default=str),
        hashes_json=json.dumps(hashes), rule_item_id=rule.id if rule else None,
        answer_field=answer_field)
    db.session.add(req)
    record_audit("update", "workflow", instance.id,
                 summary=f"ارجاع مرحله {stage.stage_number} «{stage.title}» برای تأیید "
                         f"به «{approver.full_name}» ({len(snap)} فرم)")
    db.session.commit()
    return req


def decide_request(req, user, approved: bool, note=None, answer=None):
    if req.status != APPROVAL_PENDING:
        raise ApprovalError("این درخواست قبلاً پاسخ گرفته است.")
    manager = user.role == "admin" or user.can("workflow.manage")
    if req.approver_id != user.id and not manager:
        raise ApprovalError("پاسخ به این درخواست در اختیار شما نیست.")
    if not approved and not (note or "").strip():
        raise ApprovalError("برای «تأیید نمی‌شود»، دلیل را بنویسید.")
    # «پاسخ تأییدکننده»: approving also says which way the work goes on
    if approved and req.answer_field:
        field, choices = answer_choices(req.answer_field)
        picked = str(answer or "").strip()
        if picked not in choices:
            label = field.label if field is not None else req.answer_field
            raise ApprovalError(f"برای تأیید، «{label}» را انتخاب کنید.")
        req.answer_value = picked
        instance = req.instance
        instance.set_payload({**instance.payload, req.answer_field: picked})
    req.status = APPROVAL_APPROVED if approved else APPROVAL_REJECTED
    req.decision_note = (note or "").strip() or None
    req.decided_at = local_now()
    req.result_seen = False
    record_audit("update", "workflow", req.instance_id,
                 summary=f"{'تأیید' if approved else 'عدم تأیید'} درخواست مرحله "
                         f"{req.stage_number} توسط «{user.full_name}»"
                         + (f" — {req.answer_value}" if approved and req.answer_value else "")
                         + (f": {req.decision_note}" if req.decision_note else ""))
    db.session.commit()
    return req


def cancel_request(req, user):
    if req.status != APPROVAL_PENDING:
        raise ApprovalError("فقط درخواست بی‌پاسخ لغو می‌شود.")
    if req.requested_by != user.id and user.role != "admin":
        raise ApprovalError("فقط فرستنده‌ی درخواست می‌تواند آن را لغو کند.")
    req.status = APPROVAL_CANCELLED
    req.decided_at = local_now()
    record_audit("update", "workflow", req.instance_id,
                 summary=f"لغو درخواست تأیید مرحله {req.stage_number}")
    db.session.commit()
    return req


def can_view(req, user) -> bool:
    return user is not None and (user.id in (req.requested_by, req.approver_id)
                                 or user.role == "admin" or user.can("workflow.manage")
                                 or user.can("workflow.view"))


def inbox_items(user) -> dict:
    to_me = (WorkflowApprovalRequest.query
             .filter_by(approver_id=user.id, status=APPROVAL_PENDING)
             .order_by(WorkflowApprovalRequest.id.desc()).all())
    results = (WorkflowApprovalRequest.query
               .filter(WorkflowApprovalRequest.requested_by == user.id,
                       WorkflowApprovalRequest.status.in_([APPROVAL_APPROVED, APPROVAL_REJECTED]),
                       WorkflowApprovalRequest.result_seen.is_(False))
               .order_by(WorkflowApprovalRequest.decided_at.desc()).all())
    return {"approval_requests": [r.to_dict() for r in to_me if r.instance and r.instance.status == "open"],
            "approval_results": [r.to_dict() for r in results if r.instance]}


def attachments_of(req) -> list:
    return WorkflowAttachment.query.filter_by(approval_request_id=req.id).all()
