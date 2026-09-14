# -*- coding: utf-8 -*-
"""Reference data definitions.

Every list here is traceable to a source:

* ``H`` — an option that exists in ``Data entry.html`` (kept, never dropped).
* ``X`` — an option that only appears in the real workshop spreadsheet and is
  added because the process needs it (see docs/ANALYSIS.md §3.1).

``aliases`` capture the spelling variants found in the sheets, so import
normalises "سعدابادی"/"سعد ابادی" onto one contractor without editing history.
"""

# (value, label, icon, source, aliases)
H, X = "html", "excel"


def _o(value, label=None, icon=None, source=H, aliases=()):
    return {"value": value, "label": label or value, "icon": icon,
            "source": source, "aliases": list(aliases)}


LOOKUP_CATEGORIES = [
    {
        "code": "center", "name_fa": "مرکز", "multiple": False,
        "items": [
            _o("سوران"), _o("امامیه"),
            _o("منزل آباد", aliases=["منزل اباد"]),
            _o("خیرآباد", aliases=["خیراباد"]),
            _o("دانشجو"), _o("گلشهر"), _o("امام علی"),
            _o("منطقه 5", "منطقه ۵", aliases=["منطقه5", "م5", "منطقه ۵"]),
            _o("تبادکان"),
            _o("تصفیه خانه دوستی", "تصفیه‌خانه دوستی", aliases=["تصفیه خانه"]),
            _o("سایر ارگان ها", "سایر ارگان‌ها", source=X, aliases=["سایرارگان ها"]),
        ],
    },
    {
        "code": "shift", "name_fa": "شیفت کاری", "multiple": False,
        "items": [_o("یک", "شیفت یک"), _o("دو", "شیفت دو")],
    },
    {
        "code": "operation", "name_fa": "نوع عملیات", "multiple": False,
        "items": [
            _o("کشیدن", "کشیدن", "🔼", aliases=["كشيدن"]),
            _o("نصب", "نصب", "🔽"),
            _o("جمع آوری", "جمع‌آوری", "📦", aliases=["جمع اوری", "جمع‌آوری"]),
            _o("نصب جدید", "نصب جدید", "🆕"),
        ],
    },
    {
        "code": "pm_form", "name_fa": "فرم نصب در PM", "multiple": False,
        "items": [
            _o("√", "دارد (√)", "✅", aliases=["v", "V", "✓"]),
            _o("ok", "ok", "✔", aliases=["OK", "Ok"]),
            _o("ندارد", "ندارد", "❌", aliases=["pm ندارد", "؟", "?"]),
        ],
    },
    {
        "code": "contractor", "name_fa": "پیمانکار", "multiple": False,
        "items": [
            _o("جوادی", aliases=["چوادی"]),
            _o("سعدآبادی", aliases=["سعدابادی", "سعد ابادی", "سعد آبادی"]),
            _o("موسوی نژاد", "موسوی‌نژاد", aliases=["مو سوی نژاد", "موسوی‌نژاد"]),
            _o("محمدزاده", aliases=["محمد زاده"]),
            _o("نیکاب", aliases=["نیکاپ"]),
            _o("جوادی (ایرج)", aliases=["ایرج"]),
            _o("اکبری منطقه 5", "اکبری م۵"),
            _o("توانا منطقه 5", "توانا م۵", aliases=["توانا"]),
            _o("قندی", source=X),
            _o("فرازی", source=X),
            _o("فرازی و نکویی", source=X),
            _o("فرازی و شایان دوست", source=X),
            _o("محمد زاده و جوادی", source=X),
        ],
    },
    {
        "code": "executor", "name_fa": "مجری", "multiple": False,
        "items": [_o("امانی", source=X), _o("پیمانی", source=X)],
    },
    {
        "code": "failure_reason", "name_fa": "شرح خرابی از نظر بهره‌بردار",
        "multiple": True,
        "items": [
            _o("سوختن الکتروپمپ", icon="🔥", aliases=["سوختن الکترو پمپ"]),
            _o("سوختن الکتروموتور", icon="🔥",
               aliases=["سوختن الکترو موتور", "سوختن موتور", "سوختن"]),
            _o("اهم دار", icon="⚡", aliases=["اهم‌دار"]),
            _o("اضافه آمپر", icon="📈", aliases=["افزایش آمپر", "افزایش امپر"]),
            _o("اضافه جریان", icon="📈"),
            _o("اتصال کوتاه", icon="⚡"),
            _o("کاهش آبدهی", icon="💧", aliases=["کاهش ابدهی", "کمبود آبدهی", "کاهش دبی"]),
            _o("افزایش دبی", icon="📊"),
            _o("افزایش فشار شبکه", icon="🔄"),
            _o("شولات", icon="🪨", aliases=["شولاتی", "شولات گل ولای"]),
            _o("هوادهی", icon="💨"),
            _o("صدا و لرزش", icon="📳", aliases=["لرزش و صدا شدید", "سر و صدا"]),
            _o("ایراد مکانیکی", icon="🔩"),
            _o("تعویض لوله آبده", icon="🔧"),
            _o("تجهیز چاه جدید", icon="🆕", aliases=["تجهیز جدید", "تجهیزجدید", "تجهیر جدید"]),
            _o("تجهیز جدید (جابجایی)", icon="🔀", aliases=["تجهیز جدید(جابجایی)"]),
            _o("مهندسی مجدد", icon="🏗️"),
            _o("بهسازی شده", icon="✅"),
            _o("جابجایی", icon="🔀"),
            _o("نصب جدید", icon="🆕", aliases=["نصب جدید(جابجایی)"]),
            _o("افزایش آبدهی", icon="💧"),
            _o("اهم دار و افزایش دبی", "اهم‌دار + دبی", "⚡"),
            _o("تغییر فشار و دبی", icon="🔄"),
            _o("جمع آوری (چاه قدیم)", "جمع‌آوری چاه قدیم", "📦", aliases=["جمع آوری"]),
            _o("عدم آبدهی", icon="🚱", source=X, aliases=["عدم ابدهی", "فاقدآبدهی"]),
            _o("پارگی لوله آبدهی", icon="🔧", source=X),
            _o("پارگی جدار", icon="🕳", source=X),
            _o("گیرپاژ", icon="🔒", source=X, aliases=["گیریپاژ"]),
            _o("خارج شدن پمپ از نقطه کار", icon="📉", source=X),
            _o("بهسازی و پمپاژ", icon="🏗️", source=X, aliases=["بهسازی و پمپاز"]),
            _o("اهم دار و سابقه شولات", icon="⚡", source=X),
        ],
    },
    {
        "code": "motor_type", "name_fa": "تیپ الکتروموتور (KW)", "multiple": False,
        "items": [_o(v) for v in
                  ["3", "5", "7.5", "11", "13", "15", "18", "22", "24", "30",
                   "37", "45", "55", "62", "73", "92", "110", "130"]]
        + [_o(v, source=X) for v in
           ["1.1", "2.2", "3.7", "5.5", "9", "9.2", "18.5", "63", "62.5", "73.5"]],
    },
    {
        "code": "pump_type", "name_fa": "تیپ پمپ", "multiple": False,
        "items": [_o(v) for v in
                  ["102", "152", "193", "233", "293", "345", "374", "384", "486",
                   "6606", "6608", "6609", "6611", "کفکش"]]
        + [_o(v, source=X) for v in ["348", "102urd", "104urd"]],
    },
    {
        "code": "maker", "name_fa": "سازنده / تعمیرکار", "multiple": False,
        "items": [
            _o("کارگاه مکانیک", aliases=["کارکاه مکانیک", "کار گاه مکانیک",
                                          "کارگاه مکانیبک"]),
            _o("پمپیران", aliases=["نو پمپیران", "بمبیران", "نو بمبیران"]),
            _o("سولار", aliases=["نو سولار"]),
            _o("گازار", aliases=["نو گازار"]),
            _o("بارش"), _o("اسرار"), _o("ناصری"),
            _o("حسن زاده", "حسن‌زاده"), _o("آریان"),
            _o("کارگاه لطفی", source=X),
            _o("شرق توس", source=X),
            _o("شرق (حسینی)", source=X),
            _o("اسپادان پمپ", source=X),
            _o("آناهیتا", source=X, aliases=["اناهیتا"]),
            _o("نصرالله زاده", "نصرالله‌زاده", source=X,
               aliases=["نصرا... زاده", "نصراله زاده"]),
            _o("روستایی", source=X),
            _o("منطقه 5", "منطقه ۵", source=X, aliases=["منطقه5"]),
            _o("برگشتی از چاه", source=X),
            _o("مشخص نیست", source=X, aliases=["نامعلوم"]),
        ],
    },
    {
        "code": "condition", "name_fa": "وضعیت (نو / تعمیری)", "multiple": False,
        "items": [
            _o("نو", "نو", "🆕"),
            _o("تعمیری", "تعمیری", "🔧"),
            _o("برگشتی", "برگشتی", "↩", aliases=["برگشتی از چاه"]),
        ],
    },
    {
        "code": "motor_rewind", "name_fa": "سیم‌پیچی / سرویس", "multiple": False,
        "items": [_o("سیم پیچی", "سیم‌پیچی", source=X), _o("سرویس", source=X)],
    },
    {
        "code": "change_flag", "name_fa": "وضعیت تغییر", "multiple": False,
        "items": [_o("دارد", "دارد", "✅"), _o("ندارد", "ندارد", "❌"),
                  _o("جدید", "جدید", "🆕", source=X)],
    },
    {
        "code": "pipe_diameter", "name_fa": "قطر لوله آبده (اینچ)", "multiple": False,
        "items": [_o("3", "3″"), _o("4", "4″"), _o("6", "6″"), _o("6*8", "6×8″"),
                  _o("8", "8″"), _o("10", "10″")]
        + [_o("2", "2″", source=X), _o("2.5", "2.5″", source=X), _o("5", "5″", source=X)],
    },
    {
        "code": "starter", "name_fa": "راه‌انداز", "multiple": False,
        "items": [
            _o("ستاره", "ستاره", "⭐"),
            _o("سافت", "سافت", "🔁", aliases=["سفت", "ساقت", "ساغت"]),
            _o("ستاره مثلث", "ستاره‌مثلث", "⭐△"),
            _o("تک فاز", "تک فاز", "1⚡"),
            _o("ندارد", "ندارد", "❌"),
        ],
    },
    {
        "code": "cable_size", "name_fa": "سایز کابل", "multiple": False,
        "items": [_o(v, v.replace("*", "×")) for v in
                  ["3*6", "3*10", "3*16", "3*25", "3*35", "3*50", "3*70", "3*95"]]
        + [_o("3*4", "3×4", source=X)]
        + [_o(v, v.replace("*", "×"), source=X) for v in
           ["3*16و25", "3*25و35", "3*35و16", "3*35و50", "3*50-3*35",
            "3*25-3*50", "3*25+3*35", "3*70+3*50"]],
    },
    {
        "code": "workshop_opinion", "name_fa": "نظر کارگاه مکانیک", "multiple": True,
        "items": [
            _o("سالم", "سالم", "✅"),
            _o("اهم دار", "اهم دار", "⚡"),
            _o("سوختن الکتروموتور", "سوختن الکتروموتور", "🔥"),
            _o("شولاتی", "شولاتی", "🪨"),
            _o("شولات-سوخته", "شولات + سوخته", "🪨🔥"),
            _o("شولات- سالم", "شولات + سالم", "🪨✅"),
            _o("ایراد در قطغه پمپ", "ایراد قطعه پمپ", "💧"),
            _o("شکستن طبقه", "شکستن طبقه", "💥"),
            _o("شکستن پمپ بعلت ورود جسم خارجی", "ورود جسم خارجی", "💥"),
            _o("نشستن به کف چاه", "نشستن کف چاه", "⬇"),
            _o("گیرپاژ", "گیرپاژ", "🔒"),
            _o("مشکل تابلو", "مشکل تابلو", "📟"),
            _o("مشکل در نصب", "مشکل در نصب", "🔧"),
            _o("خطا بهره بردار", "خطا بهره‌بردار", "⚠"),
            _o("کفکش سالم", "کفکش سالم", "✅"),
            _o("بررسی شود", "بررسی شود", "🔎", source=X),
            _o("توضیحات دارد", "توضیحات دارد", "📝", source=X),
        ],
    },
    {
        "code": "desc_tag", "name_fa": "برچسب توضیحات", "multiple": True,
        "items": [
            _o("الکتروموتور سالم", "موتور سالم"), _o("پمپ سالم"),
            _o("سیم‌پیچ سوخته"), _o("ورود شولات"), _o("خوردگی بوش"),
            _o("خرابی پروانه"), _o("کابل زخمی"), _o("لاستیک پاره"),
            _o("آرک سربندی"), _o("یاتاقان خراب"),
            _o("گیرکردن به جدار", "گیرکردن جدار"), _o("پرشدن چاه"),
            _o("داخل موتور گل و لای", "گل و لای"),
            _o("تغییر از ستاره به سافت", "ستاره→سافت"), _o("اسقاط پمپ"),
        ],
    },
    {
        "code": "casing_material", "name_fa": "جنس جدار", "multiple": False,
        "is_system": False, "items": [],   # sheet «خاص» has too few clean rows to seed
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# Form layout — the eight sections of Data entry.html, in the original order.
# ``attr`` is the Record column; ``cat`` is the lookup category for choices.
# ─────────────────────────────────────────────────────────────────────────────
def f(field_name, label, ftype, attr=None, cat=None, **kw):
    d = {"field_name": field_name, "label": label, "field_type": ftype,
         "model_attr": attr, "lookup_category": cat}
    d.update(kw)
    return d


FORM_SECTIONS = [
    {
        "code": "basic", "title": "اطلاعات پایه", "icon": "📌", "columns": 3,
        "fields": [
            f("op_jdate", "تاریخ عملیات", "jalali_date", attr="op_date", required=True,
              help_text="روز/ماه/سال شمسی؛ در پایگاه داده به میلادی ISO ذخیره می‌شود.",
              show_in_table=True, table_order=1, export_header="تاریخ"),
            f("well", "نام چاه", "autocomplete", attr="well_id", required=True,
              placeholder="جستجو یا تایپ نام چاه...", show_in_table=True, table_order=2,
              export_header="نام چاه"),
            f("center", "مرکز", "radio", attr="center_id", cat="center", required=True,
              show_in_table=True, table_order=3, export_header="مرکز"),
            f("shift", "شیفت کاری", "radio", attr="shift_id", cat="shift",
              show_in_table=True, table_order=4, export_header="شیفت کاری"),
        ],
    },
    {
        "code": "operation", "title": "عملیات و خرابی", "icon": "🔧", "columns": 2,
        "fields": [
            f("operation", "عملیات انجام شده", "radio", attr="operation_id",
              cat="operation", required=True, show_in_table=True, table_order=5,
              export_header="كشيدن/نصب/جمع آوری /نصب جدید"),
            f("failure", "شرح خرابی از نظر بهره‌بردار", "checkbox", cat="failure_reason",
              allow_other=True, show_in_table=True, table_order=6,
              export_header="شرح خرابی از نظر بهره بردار"),
            f("pm", "فرم نصب در PM", "radio", attr="pm_id", cat="pm_form",
              export_header="فرم نصب در PM"),
            f("executor", "مجری", "radio", attr="executor_id", cat="executor",
              help_text="کار توسط نیروی امانی انجام شده یا پیمانکار؟",
              export_header="مجری"),
            f("contractor", "نام پیمانکار", "radio", attr="contractor_id",
              cat="contractor", show_in_table=True, table_order=7,
              visible_when="executor=پیمانی",
              help_text="فقط وقتی مجری «پیمانی» باشد پرسیده می‌شود.",
              export_header="نام پيمانكار"),
        ],
    },
    {
        "code": "motor", "title": "مشخصات موتور", "icon": "⚡", "columns": 3,
        "fields": [
            f("motor_prev", "تیپ الکتروموتور قبلی (KW)", "radio", attr="motor_prev_id",
              cat="motor_type", allow_other=True, show_in_table=True, table_order=8,
              export_header="تیپ الکترو موتور قبلی"),
            f("motor_curr", "تیپ الکتروموتور فعلی (KW)", "radio", attr="motor_curr_id",
              cat="motor_type", required=True, allow_other=True, show_in_table=True,
              table_order=9, export_header="تیپ الکترو موتور فعلی"),
            f("motor_plaque", "پلاک موتور", "text", attr="motor_plaque",
              placeholder="شماره پلاک", export_header="پلاک موتور"),
            f("motor_maker", "سازنده / تعمیرکار موتور", "radio", attr="motor_maker_id",
              cat="maker", allow_other=True, export_header="سازنده/تعمیرکار موتور"),
            f("motor_condition", "نو / تعمیری موتور", "radio", attr="motor_condition_id",
              cat="condition", show_in_table=True, table_order=10,
              export_header="نو/تعمیری موتور"),
            f("motor_rewind", "سیم‌پیچی / سرویس", "radio", attr="motor_rewind_id",
              cat="motor_rewind", help_text="ستون ۱۶ شیت ۱۴۰۵ اکسل کارگاه.",
              export_header="سیم پیچی / سرویس"),
        ],
    },
    {
        "code": "pump", "title": "مشخصات پمپ", "icon": "💧", "columns": 3,
        "fields": [
            f("pump_prev", "تیپ پمپ قبلی", "autocomplete", attr="pump_prev_id",
              cat="pump_type", allow_other=True, placeholder="مثال: 384/10",
              help_text="اگر به شکل «تیپ/طبقه» وارد شود، طبقه جدا ذخیره می‌گردد.",
              show_in_table=True, table_order=11, export_header="تیپ پمپ قبلی"),
            f("pump_prev_stages", "طبقه پمپ قبلی", "number", attr="pump_prev_stages",
              min_value=1, max_value=40),
            f("pump_curr", "تیپ پمپ فعلی", "radio", attr="pump_curr_id", cat="pump_type",
              required=True, allow_other=True, show_in_table=True, table_order=12,
              export_header="تیپ پمپ فعلی"),
            f("pump_stages", "طبقه پمپ", "number", attr="pump_stages", min_value=1,
              max_value=40, placeholder="تعداد طبقه", show_in_table=True, table_order=13,
              export_header="طبقه پمپ"),
            f("pump_plaque", "پلاک پمپ", "text", attr="pump_plaque",
              placeholder="شماره پلاک", export_header="پلاک پمپ"),
            f("pump_maker", "سازنده / تعمیرکار پمپ", "radio", attr="pump_maker_id",
              cat="maker", allow_other=True, export_header="سازنده/تعمیرکار پمپ"),
            f("pump_condition", "نو / تعمیری پمپ", "radio", attr="pump_condition_id",
              cat="condition", show_in_table=True, table_order=14,
              export_header="نو/تعمیری پمپ"),
            f("type_change", "تغییر تیپ", "radio", attr="type_change_id",
              cat="change_flag", export_header="تغییر تیپ"),
        ],
    },
    {
        "code": "well_install", "title": "اطلاعات چاه و نصب", "icon": "📐", "columns": 3,
        "fields": [
            f("prev_install_date", "تاریخ نصب قبلی", "jalali_date",
              attr="prev_install_date", export_header="تاريخ نصب قبلي"),
            f("well_depth", "عمق چاه (متر)", "number", attr="well_depth",
              placeholder="متر", export_header="عمق چاه"),
            f("prev_install_depth", "عمق نصب قبلی (متر)", "number",
              attr="prev_install_depth", placeholder="متر", export_header="عمق نصب قبلی"),
            f("curr_install_depth", "عمق نصب فعلی (متر)", "number",
              attr="curr_install_depth", placeholder="متر", show_in_table=True,
              table_order=15, export_header="عمق نصب فعلی"),
            f("static_level", "سطح استاتیک (متر)", "number", attr="static_level",
              placeholder="متر", export_header="سطح استاتیک"),
            f("dynamic_level", "سطح دینامیک (متر)", "number", attr="dynamic_level",
              placeholder="متر", export_header="سطح دینامیک"),
            f("path_loss", "تلفات مسیر", "number", attr="path_loss", placeholder="متر",
              export_header="تلفات مسیر"),
            f("network_pressure", "فشار شبکه (متر)", "number", attr="network_pressure",
              placeholder="متر", export_header="فشار شبکه"),
            f("total_head", "هد کلی (متر)", "number", attr="total_head", placeholder="متر",
              show_in_table=True, table_order=16, export_header="هد کلی"),
            f("design_flow", "دبی طراحی", "number", attr="design_flow", step="0.1",
              placeholder="لیتر بر ثانیه", show_in_table=True, table_order=17,
              export_header="دبی طراحی"),
            f("pipe_diameter", "قطر لوله آبده (اینچ)", "radio", attr="pipe_diameter_id",
              cat="pipe_diameter", export_header="قطر لوله آبده"),
            f("cable_type_change", "تغییر تیپ کابل", "radio", attr="cable_type_change_id",
              cat="change_flag", export_header="تغییر تیپ کابل"),
            f("install_supervisor", "ناظر نصب", "text", attr="install_supervisor",
              help_text="از شیت «کشیدن شش ماه اول» اکسل کارگاه.",
              export_header="ناظر نصب"),
        ],
    },
    {
        "code": "pumping_test", "title": "آزمایش پمپاژ کارگاه مکانیک", "icon": "🔬",
        "columns": 2,
        "fields": [
            f("test_date", "تاریخ آزمایش پمپاژ", "jalali_date", attr="test_date",
              export_header="تاریخ آزمایش پمپاژ"),
            f("test_pressure", "فشار آزمایش پمپاژ", "number", attr="test_pressure",
              step="0.1", export_header="فشار آزمایش پمپاژ"),
            f("test_flow", "دبی آزمایش پمپاژ", "number", attr="test_flow", step="0.1",
              show_in_table=True, table_order=18, export_header="دبی آزمایش پمپاژ"),
            f("cable_size_change", "تغییر سایز کابل", "radio", attr="cable_size_change_id",
              cat="change_flag", export_header="تغییر سایز کابل"),
            f("flow_before_pull", "دبی قبل از کشیدن", "number", attr="flow_before_pull",
              step="0.1", help_text="ستون شیت ۱۳۹۸.", export_header="دبی قبل از کشیدن"),
            f("flow_after_install", "دبی پس از نصب پمپ جدید", "number",
              attr="flow_after_install", step="0.1",
              help_text="ستون شیت «کشیدن شش ماه اول».",
              export_header="دبی پس از نصب پمپ جدید"),
        ],
    },
    {
        "code": "cable_starter", "title": "کابل و راه‌انداز", "icon": "🔌", "columns": 2,
        "fields": [
            f("cable_well", "نام چاه استفاده شده (کابل)", "text", attr="cable_well",
              placeholder="نام چاه", export_header="نام چاه استفاده شده (کابل)"),
            f("starter", "راه‌انداز (نوع استارت)", "radio", attr="starter_id",
              cat="starter", show_in_table=True, table_order=19, export_header="راه انداز"),
            f("cable_size", "سایز کابل", "radio", attr="cable_size_id", cat="cable_size",
              allow_other=True, show_in_table=True, table_order=20,
              export_header="سایز کابل"),
            f("pull_year", "سال کشیدن فعلی", "number", attr="pull_year", min_value=1370,
              max_value=1450, placeholder="مثال: 1405", export_header="سال کشیدن فعلی"),
            f("pull_month", "ماه کشیدن فعلی", "select", attr="pull_month",
              cat="__months__", export_header="ماه کشیدن فعلی"),
            f("old_install_year", "سال نصب قدیم", "number", attr="old_install_year",
              min_value=1370, max_value=1450, placeholder="مثال: 1402",
              export_header="سال نصب قدیم"),
            f("old_install_month", "ماه نصب قدیم", "select", attr="old_install_month",
              cat="__months__", export_header="ماه نصب قدیم"),
        ],
    },
    {
        "code": "casing", "title": "جدار چاه (اختیاری)", "icon": "🕳", "columns": 3,
        "fields": [
            f("casing_length", "متراژ لوله جدار کشیده‌شده", "number", attr="casing_length",
              export_header="متراژ لوله کشیده شده"),
            f("casing_pulled_diameter", "قطر جدار کشیده‌شده", "text",
              attr="casing_pulled_diameter", export_header="قطر جدار کشیده شده"),
            f("casing_repair_count", "تعداد ترمیم", "number", attr="casing_repair_count",
              min_value=0, export_header="تعداد ترمیم"),
            f("casing_material", "جنس جدار", "text", attr="casing_material",
              export_header="جنس جدار"),
            f("casing_diameter", "قطر جدار", "text", attr="casing_diameter",
              export_header="قطر جدار"),
            f("documents_ref", "مستندات", "text", attr="documents_ref",
              placeholder="ارجاع به تصویر/سند", export_header="مستندات"),
        ],
    },
    {
        "code": "result", "title": "نتیجه بررسی و توضیحات", "icon": "📝", "columns": 2,
        "full_width": True,
        "fields": [
            f("workshop_opinion", "نظر کارگاه مکانیک", "checkbox", cat="workshop_opinion",
              show_in_table=True, table_order=21, export_header="نظر کارگاه مکانیک"),
            f("workshop_note", "شرح خرابی از نظر کارگاه مکانیک", "textarea",
              attr="workshop_note", help_text="شیت‌های «خاص» و «کشیدن شش ماه اول».",
              export_header="شرح خرابی از نظر کارگاه مکانیک"),
            f("young_wells", "چاه‌های با عمر کمتر از یک سال", "number", attr="young_wells",
              min_value=0, max_value=99, export_header="چاههای با عمر کمتر از یک سال"),
            f("working_months", "تعداد ماه‌های کارکرد", "number", attr="working_months",
              min_value=0, placeholder="تعداد ماه", export_header="تعداد ماه های کارکرد"),
            f("desc_tags", "توضیحات (برچسب‌ها)", "checkbox", cat="desc_tag"),
            f("description", "توضیحات", "textarea", attr="description",
              placeholder="توضیحات تکمیلی...", show_in_table=True, table_order=22,
              export_header="توضیحات"),
            f("reported_to_finance", "اعلام شده به مالی", "checkbox",
              attr="reported_to_finance", help_text="ستون شیت ۱۴۰۲.",
              export_header="اعلام شده به مالی"),
        ],
    },
]
