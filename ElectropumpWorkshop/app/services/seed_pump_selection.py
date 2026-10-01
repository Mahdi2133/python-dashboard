# -*- coding: utf-8 -*-
"""«فرم تعویض، تعمیر، جمع‌آوری یا نصب جدید الکتروپمپ شناور» as form-builder forms.

Source: the workshop's «فرم انتخاب پمپ» workbook. Each block of the sheet —
the rows grouped under one heading, with a note in column J saying who fills
it — becomes its own small form, so the process builder can drop each on the
stage of the person who fills it:

  جمع‌آوری (امین، با دیتای قبلی) · تاریخ دبی‌سنجی (مرکز) · انتخاب الکتروپمپ (امین)
  · کابل موجود در چاه (کارگاه مکانیک) · آماده‌سازی (کارگاه مکانیک)
  · میزان آبدهی و کابل تحویلی (کارگاه؛ نیاز به تأیید امین)
  · کالا و لوازم مصرفی آماده‌سازی (کارگاه؛ بدون تأیید) · نصب (کارگاه؛ بدون تأیید)
  · فرم درخواست ادارات (برگه‌ی «ادارات»)

Items the system already asks for elsewhere — نام چاه، تیپ پمپ قبلی، عمق
چاه، سطح دینامیک، هد کلی… — are «فیلد مشترک»: the same answer shown in this
form too, so nothing is typed twice and no report sees two values.

Rules from the sheet:
* «تک کابل» opens when the راه‌انداز is سافت or درایو; «جفت کابل» when it is
  ستاره مثلث.
* Sp.Cap = دبی (l/s) × 0.001 ÷ سطح دینامیک (the sheet's =C13*0.001/E12).
* I1، I2، I3 will be filled from the pumping-test database once it arrives;
  until then they are typed.

Seeded once; afterwards everything here is the admin's to change.
"""
import logging

from ..extensions import db
from ..models import FormField, FormFieldOption, FormSection, LookupCategory, LookupItem

log = logging.getLogger(__name__)

SEED_KEY = "pump_selection_forms_v1"
SINGLE = "starter=سافت|درایو"
DOUBLE = "starter=ستاره مثلث"


def f(name, label, kind="text", **kw):
    return dict(name=name, label=label, kind=kind, **kw)


def mirror(name, label, of, **kw):
    return dict(name=name, label=label, kind="mirror", mirror_of=of, **kw)


def num(name, label, **kw):
    return f(name, label, "number", **kw)


def date(name, label, **kw):
    return f(name, label, "jalali_date", **kw)


def cable(prefix, title):
    return [
        f(f"{prefix}_spec", f"مشخصات {title}", col_span=2),
        num(f"{prefix}_length", "طول کابل (متر)"),
        num(f"{prefix}_joints", "تعداد مفصل"),
        f(f"{prefix}_single", "تک کابل — سایز", "radio", lookup="cable_size",
          visible_when=SINGLE, help_text="با راه‌انداز «سافت» یا «درایو» باز می‌شود."),
        f(f"{prefix}_double", "جفت کابل — سایز", "radio", lookup="cable_size",
          visible_when=DOUBLE, help_text="با راه‌انداز «ستاره مثلث» باز می‌شود."),
    ]


def consumables(prefix, rows):
    return [num(f"{prefix}_{i + 1:02d}", f"{label} ({unit})" if unit else label)
            for i, (label, unit) in enumerate(rows)]


FORMS = [
    {"code": "ps_collect", "icon": "🔼", "title": "فرم انتخاب پمپ — جمع‌آوری الکتروپمپ شناور",
     "description": "توسط امین (کارشناس) پر می‌شود؛ مقادیر «قبلی» از سوابق چاه پیشنهاد می‌شوند. "
                    "«تاریخ خارج نمودن الکتروپمپ» پس از مرحله‌ی مهدی یاقوتی پر می‌شود.",
     "fields": [
         mirror("ps_well", "نام چاه", "well"),
         date("ps_failure_date", "تاریخ اعلام خرابی"),
         mirror("ps_prev_install_date", "تاریخ آخرین نصب (قبلی)", "prev_install_date"),
         f("ps_operator_failure_desc", "شرح خرابی از نظر بهره‌بردار", "textarea"),
         date("ps_pull_date", "تاریخ خارج نمودن الکتروپمپ از چاه (جمع‌آوری)",
              help_text="پس از مرحله‌ی مهدی یاقوتی پر می‌شود."),
         mirror("ps_executor", "نام مجری", "executor"),
         mirror("ps_motor_prev", "تیپ الکتروموتور (قبلی)", "motor_prev"),
         mirror("ps_pump_prev", "تیپ پمپ (قبلی)", "pump_prev"),
         mirror("ps_last_flow", "آخرین دبی چاه (قبل)", "flow_before_pull"),
         num("ps_network_loss_coef", "ضریب افت شبکه"),
         num("ps_aquifer_loss_coef", "ضریب افت سفره"),
         f("ps_well_cementing", "وضعیت چاه", "radio", options=["سیمانته", "غیرسیمانته"]),
         f("ps_pipe_dia_prev", "قطر لوله آبده (قبلی)", "radio", lookup="pipe_diameter",
           prefill_from="pipe_diameter"),
         mirror("ps_well_depth", "عمق چاه", "well_depth"),
         mirror("ps_prev_install_depth", "عمق نصب قبلی", "prev_install_depth"),
     ]},
    {"code": "ps_center_flowtest", "icon": "📅", "title": "فرم انتخاب پمپ — تاریخ آخرین دبی‌سنجی (مرکز)",
     "description": "این فیلد را مرکز (واحد) پر می‌کند.",
     "fields": [date("ps_last_flow_test_date", "تاریخ آخرین دبی‌سنجی یا پمپاژ")]},
    {"code": "ps_select", "icon": "🎯", "title": "فرم انتخاب پمپ — انتخاب الکتروپمپ شناور",
     "description": "توسط امین پر می‌شود: خطاب به مسئول کارگاه مکانیک برای آماده‌سازی الکتروپمپ. "
                    "Sp.Cap خودکار محاسبه می‌شود.",
     "fields": [
         date("ps_form_delivery_date", "تاریخ تحویل فرم"),
         mirror("ps_requested_pump", "تیپ الکتروپمپ درخواستی جهت آماده‌سازی", "pump_curr"),
         f("ps_purpose", "جهت", "radio", options=["تعویض", "نصب جدید"]),
         mirror("ps_wellhead_pressure", "فشار سر چاه", "network_pressure"),
         mirror("ps_dynamic_level", "سطح دینامیک", "dynamic_level"),
         mirror("ps_path_loss", "تلفات مسیر", "path_loss"),
         mirror("ps_total_head", "هد کلی", "total_head"),
         mirror("ps_flow", "دبی (l/s)", "design_flow"),
         f("ps_sp_cap", "Sp.Cap", "formula",
           formula="[design_flow] * 0.001 / ([dynamic_level] - [static_level])",
           step="5", help_text="= دبی (l/s) × 0.001 ÷ (سطح دینامیک − سطح استاتیک)"),
         mirror("ps_static_level", "سطح استاتیک", "static_level"),
         mirror("ps_curr_install_depth", "عمق نصب فعلی", "curr_install_depth"),
         num("ps_max_amp", "حداکثر آمپر مجاز"),
         num("ps_extra_drawdown", "افت اضافه به دلیل گذشت زمان زیاد از دبی‌سنجی"),
         mirror("ps_pipe_dia_curr", "قطر لوله آبده (فعلی)", "pipe_diameter"),
         f("ps_select_note", "توضیحات", "textarea"),
     ]},
    {"code": "ps_cable_existing", "icon": "🧵", "title": "فرم انتخاب پمپ — کابل موجود در چاه",
     "description": "توسط کارگاه مکانیک پر می‌شود. تک یا جفت کابل با توجه به راه‌انداز باز می‌شود.",
     "fields": cable("ps_cable_exist", "کابل موجود")},
    {"code": "ps_prepare", "icon": "🔧", "title": "فرم انتخاب پمپ — آماده‌سازی الکتروپمپ و کابل رابط",
     "description": "تعمیر، سرویس و مونتاژ مجموعه‌ی الکتروپمپ و کابل رابط جهت نصب — کارگاه مکانیک.",
     "fields": [
         mirror("ps_motor_curr", "مشخصات الکتروموتور (تیپ)", "motor_curr"),
         mirror("ps_motor_condition", "وضعیت الکتروموتور (نو / تعمیری)", "motor_condition"),
         mirror("ps_motor_maker", "سازنده / تعمیرکار الکتروموتور", "motor_maker"),
         mirror("ps_pump_curr", "مشخصات پمپ (تیپ)", "pump_curr"),
         mirror("ps_pump_condition", "وضعیت پمپ (نو / تعمیری)", "pump_condition"),
         mirror("ps_pump_maker", "سازنده / تعمیرکار پمپ", "pump_maker"),
         num("ps_prep_cable_joints", "وضعیت کابل — تعداد مفصل"),
         f("ps_prep_cable_single", "تک کابل — سایز", "radio", lookup="cable_size", visible_when=SINGLE),
         f("ps_prep_cable_double", "جفت کابل — سایز", "radio", lookup="cable_size", visible_when=DOUBLE),
     ]},
    {"code": "ps_delivery", "icon": "💧", "title": "فرم انتخاب پمپ — میزان آبدهی و کابل تحویلی",
     "description": "کارگاه مکانیک پر می‌کند و برای تأیید امین ارجاع می‌دهد (در فرایندساز برای این فرم "
                    "«✅ تأیید اجباری» را تنظیم کنید). I1، I2، I3 پس از اتصال پایگاه «آزمایش پمپاژ» "
                    "بر اساس نام چاه، کلاسه و کد PM خودکار پر خواهند شد.",
     "fields": [
         num("ps_flow_i1", "میزان آبدهی در هد درخواستی — I1 (l/s)",
             help_text="به‌زودی از پایگاه آزمایش پمپاژ خوانده می‌شود."),
         num("ps_flow_i2", "میزان آبدهی در هد درخواستی — I2 (l/s)",
             help_text="به‌زودی از پایگاه آزمایش پمپاژ خوانده می‌شود."),
         num("ps_flow_i3", "میزان آبدهی در هد درخواستی — I3 (l/s)",
             help_text="به‌زودی از پایگاه آزمایش پمپاژ خوانده می‌شود."),
     ] + cable("ps_cable_deliv", "کابل تحویلی")},
    {"code": "ps_prep_consumables", "icon": "📦", "title": "فرم انتخاب پمپ — کالا و لوازم مصرفی آماده‌سازی",
     "description": "توسط کارگاه پر می‌شود؛ نیاز به تأیید ندارد.",
     "fields": consumables("ps_pc", [
         ("چسب برق", "عدد"), ("سیلپاک (رزین آبندی) M11", "عدد"), ("سیلپاک (رزین آبندی) M12", "عدد"),
         ("سیلپاک (رزین آبندی) M13", "بسته"), ("سیلپاک (رزین آبندی) M14", "عدد"), ("بوشن", "عدد"),
         ("آپارات نواری", "عدد"), ("چسب سیرو", "گرم"), ("کابل مصرفی", "متر"),
     ]) + [f("ps_pc_cable_spec", "مشخصات کابل مصرفی (مثلاً 3*16)")]},
    {"code": "ps_install", "icon": "🔽", "title": "فرم انتخاب پمپ — نصب",
     "description": "توسط کارگاه پر می‌شود؛ نیاز به تأیید ندارد.",
     "fields": [
         date("ps_install_date", "تاریخ نصب"),
         mirror("ps_install_contractor", "نام پیمانکار نصب", "contractor"),
     ] + consumables("ps_ic", [
         ("سیم جوش", "کیلوگرم"), ("صفحه برش", "عدد"), ("تسمه 5 × 40", "کیلوگرم"),
         ("تسمه 5 × 25", "کیلوگرم"), ("پیچ و مهره 70 × 16", "عدد"), ("واشر منجیتی", ""),
         ("گریس", ""), ("لوله آبده به همراه وصل 3 اینچ", ""), ("لوله آبده به همراه وصل 4 اینچ", ""),
         ("لوله آبده به همراه وصل 6 اینچ", ""),
     ]) + [date("ps_startup_date", "تاریخ راه‌اندازی چاه")]},
    {"code": "ps_request", "icon": "🏢", "title": "فرم درخواست تعویض، تعمیر، جمع‌آوری یا نصب منصوبات چاه (ادارات)",
     "description": "توسط کارشناس اداره‌ی بهره‌برداری پر می‌شود. «وضعیت تابلو برق» همان راه‌انداز است و "
                    "تک/جفت کابل را باز می‌کند.",
     "fields": [
         mirror("ps_r_well", "نام چاه", "well"),
         mirror("ps_r_failure_date", "تاریخ اعلام خرابی", "ps_failure_date"),
         mirror("ps_r_prev_install", "تاریخ آخرین نصب", "prev_install_date"),
         mirror("ps_r_failure_desc", "شرح خرابی از نظر بهره‌بردار", "ps_operator_failure_desc"),
         f("ps_well_history", "سابقه‌ی چاه", "checkbox", options=["شولاتی", "ماسه‌دهی"]),
         mirror("ps_r_starter", "وضعیت تابلو برق", "starter"),
         mirror("ps_r_cable_spec", "مشخصات کابل موجود", "ps_cable_exist_spec"),
         mirror("ps_r_cable_length", "طول کابل", "ps_cable_exist_length"),
         mirror("ps_r_cable_single", "تک کابل — سایز", "ps_cable_exist_single"),
         mirror("ps_r_cable_double", "جفت کابل — سایز", "ps_cable_exist_double"),
         mirror("ps_r_motor", "تیپ الکتروموتور", "motor_prev"),
         mirror("ps_r_pump", "تیپ پمپ", "pump_prev"),
         f("ps_motor_plaque_old", "شماره پلاک الکتروموتور"),
         f("ps_pump_plaque_old", "شماره پلاک پمپ"),
         mirror("ps_r_pressure", "فشار سطح چاه", "network_pressure"),
         mirror("ps_r_dynamic", "سطح دینامیک", "dynamic_level"),
         f("ps_flowtest_doc", "پیوست: فرم دبی‌سنجی", "file", file_accept="image/*,.pdf,.doc,.docx,.xls,.xlsx"),
     ]},
]


def _ensure_starter_options():
    """The sheet's «سافت / درایو»: درایو is not on the راه‌انداز list yet."""
    cat = LookupCategory.query.filter_by(code="starter").first()
    if cat is None:
        return 0
    added = 0
    for value in ("سافت", "درایو", "ستاره مثلث"):
        if not any(i.value == value for i in cat.items):
            db.session.add(LookupItem(category_id=cat.id, value=value, label=value, is_active=True,
                                      sort_order=max((i.sort_order for i in cat.items), default=0) + 1))
            added += 1
    return added


def seed_pump_selection_forms() -> dict:
    from ..models.meta import AppMeta
    if AppMeta.get(SEED_KEY):
        return {}
    options_added = _ensure_starter_options()
    base = (db.session.query(db.func.max(FormSection.sort_order)).scalar() or 0)
    sections = fields = 0
    deferred = []            # mirrors pointing at fields made later in this seed
    for n, spec in enumerate(FORMS, start=1):
        section = FormSection.query.filter_by(code=spec["code"]).first()
        if section is None:
            section = FormSection(code=spec["code"], title=spec["title"], icon=spec["icon"],
                                  columns=3, full_width=True, sort_order=base + n, is_active=True,
                                  description=spec["description"], show_on_entry=False)
            db.session.add(section)
            db.session.flush()
            sections += 1
        for idx, fs in enumerate(spec["fields"]):
            if FormField.query.filter_by(field_name=fs["name"]).first():
                continue
            field = FormField(
                section_id=section.id, field_name=fs["name"], label=fs["label"],
                field_type=fs["kind"], is_required=False, is_builtin=False,
                sort_order=idx, col_span=fs.get("col_span", 1),
                lookup_category=fs.get("lookup"), help_text=fs.get("help_text"),
                visible_when=fs.get("visible_when"), prefill_from=fs.get("prefill_from"),
                formula=fs.get("formula"), step=fs.get("step"),
                file_accept=fs.get("file_accept"), file_multiple=fs.get("file_multiple", True),
                mirror_of=fs.get("mirror_of"),
                export_header=fs["label"])
            db.session.add(field)
            db.session.flush()
            for j, option in enumerate(fs.get("options") or []):
                db.session.add(FormFieldOption(field_id=field.id, value=option, label=option,
                                               sort_order=j, is_active=True))
            if fs["kind"] == "mirror":
                deferred.append(field)
            fields += 1
    db.session.flush()
    # a mirror whose target does not exist in this database is left out rather
    # than drawn broken (e.g. a built-in field someone deleted)
    dropped = 0
    for field in deferred:
        if field.mirror_source() is None:
            db.session.delete(field)
            dropped += 1
    AppMeta.set(SEED_KEY, "done")
    db.session.commit()
    result = {"pump_selection_forms": sections, "pump_selection_fields": fields - dropped}
    if options_added:
        result["starter_options_added"] = options_added
    log.info("Seeded the pump-selection forms: %s", result)
    return result
