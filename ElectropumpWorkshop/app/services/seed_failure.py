# -*- coding: utf-8 -*-
"""The parameters each علت خرابی asks for, as a form that opens when it is ticked.

Source: the workshop's own «Sheet2» workbook — one block of readings per
cause. Each block becomes a form section whose ``visible_when`` names the
cause, so ticking «سوختن الکتروپمپ» opens its dozen readings and ticking two
causes opens both blocks. Everything here is ordinary form-builder data: the
admin renames, reorders, adds, removes and re-points any of it afterwards,
and this file never touches it again.

Two shapes in the sheet need saying out loud:

* «مقاومت عایقی فاز با فاز» is measured at two places — محل تابلو and
  محل مفصل جدار — so it becomes two numbered readings rather than one.
* «جریان نرمال بهره‌برداری» carries three sample values, one per phase, so it
  becomes three readings (R, S, T). «درصد کاهش یا افزایش» is not asked at all:
  it is arithmetic on the other two, and the report builder computes it.
"""
import logging

from ..extensions import db
from ..models import FormField, FormFieldOption, FormSection

log = logging.getLogger(__name__)

SEED_KEY = "failure_cause_forms_v1"

# Two places each insulation reading is taken.
_SPOTS = ("محل تابلو", "محل مفصل جدار")
# The three phases the ampere readings carry one sample each for.
_PHASES = ("R", "S", "T")


def _n(label, **kw):
    return dict(kind="number", label=label, **kw)


def _pick(label, options, **kw):
    return dict(kind="radio", label=label, options=options, **kw)


def _at_spots(label):
    """One reading per measurement place."""
    return [_n(f"{label} — {spot}") for spot in _SPOTS]


def _per_phase(label):
    """One reading per phase."""
    return [_n(f"{label} — فاز {p}") for p in _PHASES]


# code · the علت خرابی it belongs to · title · icon · its readings.
#
# The cause is named by the value stored in the «علت خرابی» list, which is why
# a few differ from the sheet's own headings: the sheet describes the fault,
# the list is what the operator actually ticks. Any of them can be re-pointed
# in فرم‌ساز by editing the section's «نمایش فقط وقتی».
CAUSE_FORMS = [
    {
        "code": "fail_burn", "cause": "سوختن الکتروپمپ", "icon": "🔥",
        "title": "سوختن الکتروپمپ — پارامترها", "columns": 3,
        "fields": (
            _at_spots("مقاومت عایقی فاز با فاز")
            + _at_spots("مقاومت عایقی فاز با بدنه")
            + _at_spots("ولتاژ خاموش")
            + [
                _pick("نوع تابلو راه‌انداز",
                      ["ستاره مثلث", "سافت/درایو"], col_span=2),
                _n("تنظیم رله حرارتی (ستاره مثلث)"),
                _n("آمپر فیوز (ستاره مثلث)"),
                _n("تنظیم کلیدفیوز (ستاره مثلث)"),
                _pick("تنظیمات متناسب با موتور بوده است (سافت/درایو)",
                      ["بله", "خیر"]),
                dict(kind="text", label="کد خطای مشاهده‌شده (سافت/درایو)"),
                _pick("توان اسمی تابلو راه‌انداز با توان موتور متناسب است",
                      ["بله", "خیر"], col_span=2),
            ]
        ),
    },
    {
        "code": "fail_ohmdrop", "cause": "اهم دار", "icon": "🪫",
        "title": "کاهش مقاومت اهمی — پارامترها", "columns": 3,
        "fields": (_at_spots("مقاومت عایقی فاز با فاز")
                   + _at_spots("مقاومت عایقی فاز با بدنه")),
    },
    {
        "code": "fail_ampshift", "cause": "اضافه آمپر", "icon": "⚡",
        "title": "افزایش یا کاهش آمپر — پارامترها", "columns": 3,
        "fields": (
            _per_phase("جریان نرمال بهره‌برداری")
            + _per_phase("جریان فعلی")
            + [_n("ولتاژ خاموش"), _n("ولتاژ روشن")]
        ),
    },
    {
        "code": "fail_flowdrop", "cause": "کاهش آبدهی", "icon": "📉",
        "title": "کاهش آبدهی — پارامترها", "columns": 3,
        "fields": [
            _n("دبی مورد انتظار"), _n("آخرین دبی متوسط تولیدی"),
            _n("دبی فعلی مشاهده‌شده"), _n("فشار نرمال چاه"), _n("فشار فعلی"),
            _n("دبی اندازه‌گیری در حالت تخلیه با فشار شبکه"),
            _n("سطح استاتیک"), _n("سطح دینامیک"), _n("آمپر موتور"),
            _n("آمپر چپ‌گرد"), _n("آمپر راست‌گرد"),
            _pick("پارگی لوله آبده", ["دارد", "ندارد"]),
            _pick("سلامت کنتور", ["سالم", "ناسالم"]),
            _pick("کنترل شیر شبکه و یک‌طرفه", ["انجام شد", "نشد"]),
        ],
    },
    {
        "code": "fail_noflow", "cause": "عدم آبدهی", "icon": "🚱",
        "title": "عدم آبدهی — پارامترها", "columns": 3,
        "fields": [
            _pick("جریان موتور", ["بی‌بار", "کم‌بار"]),
            _pick("پارگی لوله آبده", ["دارد", "ندارد"]),
            _pick("سلامت کنتور", ["سالم", "ناسالم"]),
            _n("سطح استاتیک"), _n("سطح دینامیک"),
            _n("آمپر چپ‌گرد"), _n("آمپر راست‌گرد"),
            _pick("کنترل شیر شبکه و یک‌طرفه", ["انجام شد", "نشد"]),
        ],
    },
    {
        "code": "fail_aeration", "cause": "هوادهی", "icon": "💨",
        "title": "هوادهی — پارامترها", "columns": 2,
        "fields": [
            # Seven observations that are ticked off rather than measured, so
            # they are one checklist instead of seven yes/no questions.
            dict(kind="checklist", label="مشاهدات هوادهی", col_span=2,
                 options=[
                     "آب خروجی همراه با هوا مشاهده می‌شود",
                     "جریان آب ناپایدار و همراه با قطع و وصل است",
                     "صدای غیرعادی ناشی از ورود هوا مشاهده می‌شود",
                     "سطح دینامیکی/استاتیک آب چاه بررسی شده است",
                     "وضعیت لوله و اتصالات بررسی شده است",
                     "نوسان آمپر مشاهده شده است",
                     "پدیده هوادهی در چند نوبت تکرار شده است",
                 ]),
            _n("فشار تنظیمی"), _n("دبی در فشار تنظیمی"),
        ],
    },
    {
        "code": "fail_reeng", "cause": "مهندسی مجدد", "icon": "📐",
        "title": "مهندسی مجدد — پارامترها", "columns": 2,
        "fields": [
            _pick("تحلیل دبی‌سنجی و امکان افزایش دبی بهره‌برداری چاه",
                  ["انجام شده", "نشده"], col_span=2),
        ],
    },
    {
        "code": "fail_vibration", "cause": "صدا و لرزش", "icon": "🔊",
        "title": "صدا و لرزش پمپ — پارامترها", "columns": 3,
        "fields": [
            _n("آمپر نرمال"), _n("آمپر بعد از صدا و لرزش"),
            _n("دبی نرمال"), _n("دبی بعد از صدا و لرزش"),
            _pick("بررسی اتصالات و شاسی مکانیکال حوضچه",
                  ["انجام شده", "نشده"]),
            _pick("موقعیت لوله آبده در مرکز لوله جدار", ["هست", "نیست"]),
            _pick("سابقه شولات/ماسه‌دهی", ["دارد", "ندارد"]),
        ],
    },
    {
        "code": "fail_turbidity", "cause": "رخداد کدورت مکرر", "icon": "🌫",
        "title": "رخداد کدورت مکرر — پارامترها", "columns": 3,
        "fields": [
            _pick("کدورت‌سنج", ["دارد", "ندارد"]),
            _n("کدورت ثبت‌شده"),
            dict(kind="text", label="فواصل زمانی ثبت کدورت"),
            _n("دبی برداشتی"),
            _pick("دبی تنظیمی جهت کاهش کدورت", ["انجام شده", "نشده"]),
        ],
    },
    {
        "code": "fail_sanding", "cause": "شولات", "icon": "🏜",
        "title": "شولاتی شدن — پارامترها", "columns": 3,
        "fields": [
            _pick("آب پشت جدار", ["تخلیه شده", "نشده"]),
            _pick("مرئی‌سازی گراویه", ["انجام شده", "نشده"]),
            _pick("شارژ گراویه", ["انجام شده", "نشده"]),
            _pick("کدورت‌سنج", ["دارد", "ندارد"]),
            _n("کدورت ثبت‌شده"), _n("دبی برداشتی"),
        ],
    },
]


def seed_failure_forms() -> dict:
    """Create the cause forms once. After that the admin owns them."""
    from ..models.meta import AppMeta
    from .lookups import get_category

    if AppMeta.get(SEED_KEY):
        return {}

    # «رخداد کدورت مکرر» is the one cause the list did not already have.
    category = get_category("failure_reason")
    made_option = 0
    if category is not None:
        for spec in CAUSE_FORMS:
            exists = any(i.value == spec["cause"] for i in category.items)
            if not exists:
                from ..models import LookupItem
                db.session.add(LookupItem(
                    category_id=category.id, value=spec["cause"],
                    label=spec["cause"], is_active=True,
                    sort_order=(max((i.sort_order for i in category.items),
                                    default=0) + 1)))
                made_option += 1
        db.session.flush()

    sections = fields = 0
    base = (db.session.query(db.func.max(FormSection.sort_order)).scalar() or 0)
    for n, spec in enumerate(CAUSE_FORMS, start=1):
        if FormSection.query.filter_by(code=spec["code"]).first():
            continue
        section = FormSection(
            code=spec["code"], title=spec["title"], icon=spec["icon"],
            columns=spec.get("columns", 3), full_width=True,
            sort_order=base + n, is_active=True,
            visible_when=f"failure={spec['cause']}",
            description=("این بخش تنها وقتی باز می‌شود که «"
                         + spec["cause"] + "» در علت خرابی انتخاب شده باشد."))
        db.session.add(section)
        db.session.flush()
        sections += 1

        for idx, f in enumerate(spec["fields"]):
            name = f"{spec['code']}_p{idx + 1:02d}"
            if FormField.query.filter_by(field_name=name).first():
                continue
            field = FormField(
                section_id=section.id, field_name=name, label=f["label"],
                field_type=f["kind"], is_required=True, is_builtin=False,
                sort_order=idx, col_span=f.get("col_span", 1),
                export_header=f"{spec['cause']} — {f['label']}",
            )
            db.session.add(field)
            db.session.flush()
            for j, option in enumerate(f.get("options") or []):
                db.session.add(FormFieldOption(
                    field_id=field.id, value=option, label=option,
                    sort_order=j, is_active=True))
            fields += 1

    AppMeta.set(SEED_KEY, "done")
    db.session.commit()
    result = {"failure_forms": sections, "failure_fields": fields}
    if made_option:
        result["failure_causes_added"] = made_option
    log.info("Seeded the failure-cause forms: %s", result)
    return result
