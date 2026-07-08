# مدل داده‌ی تفصیلی — استخراج‌شده از فرم‌های واقعی

> این سند، اسکیمای جدول‌به‌جدول است که از فایل‌های واقعی پوشه‌ی `current data/` نرمال‌سازی شده. مکمل [ARCHITECTURE.md](ARCHITECTURE.md) است. هدف: تبدیل صفحات اکسلِ «پهن و تجمیعی» به جداول رابطه‌ای تمیز.

## منابع تحلیل‌شده
| فایل | چه چیزی را پوشش می‌دهد |
|------|------------------------|
| `نمونه اطلاعات آزمایش پمپاژ.docx` (صورتجلسه) | حفاری/لوله‌گذاری + آزمایش پمپاژ + پمپ پیشنهادی |
| `آزمایش پمپاژ- مرحله حفاری.xlsx` | داده‌ی آزمایش پلکانی + ضرایب هیدرودینامیکی |
| `دبی سنجی- تجمیعی .xlsx` (۵۹ ستون) + PDF نمونه | فرم بهره‌برداری/دبی‌سنجی |
| `نصب و کشیدن پمپ- تجمیعی.xlsx` + `... داده های ثبت شده.xls` | نصب/کشیدن پمپ، عمر مفید، شاخص پیمانکار |
| `روند تولید چاه ها.xlsx` (۴۴۴ ستون) | سری‌زمانی ماهانه‌ی تولید/فشار/کارکرد/دبی |

---

## ۱. شناسایی چاه — نکته‌ی کلیدی

در داده‌ی واقعی، یک چاه چند شناسه دارد و هیچ‌کدام به‌تنهایی پایدار/یکتا نیست:

| شناسه در فرم‌ها | نقش | پایداری |
|------------------|------|---------|
| `کد PM` (مثل 102433) | کد مدیریت نگهداری | **پایدارترین — کلید عملیاتی** |
| `کلاسه چاه / کلاسه پرونده` (مثل 516841) | شماره پرونده | **عوض می‌شود** (517726→617726) |
| `نام چاه` | نام محاوره‌ای | یکتا نیست، گاه املای متفاوت |
| `شماره اشتراک برق` | انشعاب برق | ممکن است تغییر کند |
| `UTM X/Y (Zone 40)` | موقعیت | با جابه‌جایی تغییر می‌کند |

**تصمیم طراحی:** کلید داخلی مصنوعی `wells.id` (PK) + جدول `well_identifiers` برای نگه‌داری تاریخچه‌ی شناسه‌ها (چون کلاسه/اشتراک عوض می‌شوند). `pm_code` به‌عنوان شناسه‌ی تجاری اصلی روی `wells`.

```
wells
  id PK
  pm_code            UNIQUE  (کد PM — کلید تجاری اصلی)
  name
  office_id          FK → org_units (اداره)
  center_id          FK → org_units (مرکز آبرسانی)
  zone, sub_zone     پهنه / زیرپهنه‌ی مقصد توزیع
  well_kind          enum: urban | rural (منطقه ۵)
  utm_x, utm_y, utm_zone (پیش‌فرض 40N) ، geom geometry(Point,4326)
  drill_year         سال حفر
  location_status    enum: pre_drilled(حفرشده ازقبل) | relocated_stage1(جابجائي مرحله ۱) | new(جدید)
  parent_well_id     FK → wells (در جابه‌جایی)
  status             enum: in_circuit(در مدار) | out | abandoned | relocated
  created/updated...

well_identifiers   (تاریخچه‌ی شناسه‌های متغیر)
  id PK, well_id FK, id_type enum(klasse|power_subscription|name), value, valid_from, valid_to
```

---

## ۲. ساختار سازمانی-مکانی

```
org_units  (خوددرختی)
  id, name, unit_type enum(office اداره | center مرکز | rural_region منطقه۵), parent_id
```
- مرکزهای دیده‌شده: گلشهر، خیرآباد، امامیه، امام علی، دانشجو، منزل‌آباد، سوران…
- `پهنه/زیرپهنه` (C, B3, N, S, L2…) فعلاً به‌صورت فیلد متنی روی `wells`؛ در صورت نیاز به جدول `zones` ارتقا می‌یابد.

---

## ۳. حفاری و سازه‌ی چاه (از صورتجلسه)

```
drilling
  id PK, well_id FK
  contractor (پیمانکار), consultant (مشاور), employer (کارفرما)
  contract_no, contract_date, project_title
  drill_method (روش دورانی…)
  casing_length    طول لوله جدار (m)         -- 223
  screen_length    طول لوله مشبک (m)         -- 108
  blank_length     طول لوله ساده (m)         -- 115
  pipe_material    جنس لوله (UPVC)
  casing_diameter_in  قطر لوله جدار (اینچ)   -- 14
  well_depth (m)
  static_level     سطح استاتیک (m)           -- 135
  max_dynamic_level حداکثر سطح دینامیک (m)   -- 204
  max_drawdown     حداکثر افت چاه (m)        -- 69
  max_yield_lps    حداکثر آبدهی (l/s)        -- 11
  test_end_date    پایان آزمایش پمپاژ
  wash_test_duration_h  مدت شستشو و آزمایش   -- 48
```

---

## ۴. آزمایش پمپاژ

سرآیند + سطرهای پلکانی + ضرایب + پمپ پیشنهادی.

```
pump_tests
  id PK, well_id FK, test_date, drilling_id FK (nullable)
  test_type enum(step پلکانی | constant دبی‌ثابت)
  coeff_a, coeff_b     ضرایب هیدرودینامیکی (افت = a·Q + b·Q²)
  -- پمپ پیشنهادی (هم‌پوشانی با ماژول انتخاب پمپ، بخش ۵):
  proposed_install_depth_m   عمق نصب پیشنهادی   -- 208
  proposed_yield_lps         دبی مجاز پیشنهادی  -- 8
  resulting_drawdown_m       میزان افت حاصله    -- 38
  -- مشخصات تجهیز پیشنهادی:
  motor_type, motor_power_hp, gearbox_power_hp, gearbox_ratio,
  pump_type (توربینی اورلی…), pump_stages, pump_diameter_in,
  max_rpm, discharge_pipe_diameter_in, install_depth_m

pump_test_steps   (هر پله)
  id, pump_test_id FK, rpm (دور موتور),
  discharge_lps (دبی), observed_drawdown (افت مشاهده‌ای),
  calc_drawdown (افت محاسبه‌شده), grid_loss (افت شبکه),
  aquifer_loss (افت سفره), efficiency (راندمان)
```

---

## ۵. ماژول انتخاب پمپ و بانک مشخصات

داده‌ی واقعی منحنی پمپ را دارد (در PDF: ردیف «داده‌های طراحی پمپ»، Q در برابر H و راندمان max). پس:

```
pump_models  (بانک مشخصات — ورودی ماژول انتخاب)
  id, manufacturer, model_designation (تیپ، مثل 384/8 ، 6609/10),
  pump_type, default_stages, diameter_in, max_efficiency, notes
pump_curve_points
  id, pump_model_id FK, discharge_lps, head_m, efficiency
pump_selections  (خروجی ماژول برای یک چاه)
  id, well_id FK, source_pump_test_id FK (nullable),
  required_q_lps, required_tdh_m, computed_shaft_power_kw,
  selected_model_id FK, selected_stages, selected_install_depth_m, decided_by, decided_at
```
> «تیپ پمپ» در فرم‌ها (مثل `384/8`, `6609/10`, `345/7`) = `model_designation`؛ عدد بعد از `/` معمولاً تعداد طبقه است → هنگام مهاجرت تجزیه می‌شود.

---

## ۶. پمپ به‌عنوان دارایی + نصب/کشیدن (پرجزئیات‌ترین بخش)

داده‌ی نصب/کشیدن این فیلدها را دارد: موتور (kW)، موتور نو/تعمیری، تیپ پمپ، سازنده، پمپ نو/تعمیری، طبقه، عمق، پلاک، شرح خرابی (بهره‌بردار + کارگاه مکانیک)، عمر مفید (ماه)، پیمانکار، شیفت کاری.

```
suppliers        نام سازنده/تعمیرکار: پمپیران، سولار، حسن‌زاده، بارش، ستاره، کارگاه مکانیک…
  id, name, supplier_kind enum(manufacturer | repair_shop | contractor)

pumps   (دارایی فیزیکی)
  id PK, asset_code (پایدار), nameplate (پلاک), model_designation,
  pump_model_id FK (nullable), manufacturer_id FK→suppliers,
  stages (طبقه), condition enum(new نو | repaired تعمیری),
  status enum(in_stock|installed|under_repair|scrapped), current_well_id FK

pump_install_events   (هر نصب/کشیدن — جایگزین نرمال‌شده‌ی نصب1..نصب5 و «نصب باز»)
  id PK, well_id FK, pump_id FK (nullable تا زمان تطبیق دارایی),
  event_type enum(install نصب | pull کشیدن | collect جمع‌آوری | new_equip نصب جدید),
  event_date, work_shift (شیفت),
  motor_power_kw (موتور), motor_condition enum(new|repaired),
  pump_type_prev (تیپ پمپ قبلی), pump_type_current (تیپ پمپ فعلی),
  pump_condition enum(new|repaired), stages, install_depth_m, well_depth_m,
  static_level, dynamic_level, route_loss (تلفات مسیر), grid_pressure_m,
  manufacturer_id FK, contractor_id FK→suppliers, executor (مجری),
  winding_or_service (سیم‌پیچی/سرویس), type_changed (تغییر تیپ bool),
  fault_by_operator (شرح خرابی بهره‌بردار),
  fault_by_workshop (شرح خرابی کارگاه مکانیک),
  pm_form_registered bool (فرم نصب در PM)

-- «دوره» = جفتِ نصب→کشیدن. عمر مفید از اختلاف تاریخ نصب و کشیدن محاسبه می‌شود
-- (نه ذخیره‌ی دستی)، و شاخص پیمانکار/سازنده از تجمیع همین دوره‌ها به‌دست می‌آید.
```
**خروجی تحلیلی (شیت `شاخص_پیمانکار`):** تعداد دوره کامل، میانگین عمر مفید (ماه)، شاخص عملکرد ۰–۱۰۰ — به‌صورت **View/گزارش محاسباتی** روی `pump_install_events`، نه جدول ذخیره‌شده.

**طول عمر بر اساس چرخه‌ی عملکردی (اصلاح مهم):** سنجش طول عمر پمپ صرفاً با ماه‌های تقویمی گمراه‌کننده است، چون شرایط کارکرد چاه‌ها فرق دارد. طول عمر باید با **ساعات کارکرد واقعی** در بازه‌ی نصب→کشیدن نرمال شود. این ساعات از `monthly_well_readings` (متریک `operating_hours`/کارکرد) در پنجره‌ی زمانی همان دوره تجمیع می‌شود:

```
-- معیارهای طول عمر هر دوره (محاسباتی، در View):
duration_months      = removal_date − install_date
operating_hours      = Σ monthly_well_readings(operating_hours) طی بازه‌ی نصب→کشیدن
operating_hours      = Σ monthly_well_readings(operating_hours) طی بازه‌ی نصب→کشیدن
produced_volume_m3   = Σ monthly_well_readings(production) طی همان بازه
lifetime_basis       = operating_hours  (مبنای اصلیِ مقایسه، نه ماه تقویمی)
```
هر دو دادهٔ **ساعات کارکرد** و **حجم تولید** موجودند (تأیید کاربر). مقایسه‌ی سازنده/پیمانکار بر پایه‌ی **میانگین ساعات کارکرد تا خرابی** انجام می‌شود؛ **حجم تولید تجمعی** مبنای جایگزین/مکمل است و ماه تقویمی فقط در نبودِ هر دو استفاده می‌شود.

---

## ۷. بهره‌برداری / دبی‌سنجی

هر «آزمایش» (در یک تاریخ) چند **نقطه‌ی کارکرد** دارد (زیرشبکه/فشارشبکه/عادی) — ساختار سرآیند+فرزند.

```
flow_tests   (سرآیند هر دبی‌سنجی)
  id PK, well_id FK, test_date, test_year, test_month,
  test_reason (دلیل آزمایش: سالیانه/افت آبدهی…), network_type (نوع شبکه),
  electropump_type (تیپ الکتروپمپ), electropump_type_prev,
  install_date, install_depth, install_depth_prev, well_depth,
  water_pipe (لوله آبده), casing_pipe (لوله جدار), allowed_q (دبی مجاز),
  power_subscription (اشتراک برق), static_level, static_level_prev,
  last_rehab_date (تاریخ آخرین بهسازی), pull_reason (علت کشیدن پمپ),
  meter_status (کالیبراسیون/وضعیت کنتور),
  -- مشخصات الکتریکی تابلو:
  starter_type (نوع تابلو راه‌انداز: soft starter…), capacitor_capacity,
  voltage_on, voltage_off, capacitor_amp, ohm_ff (مقاومت ف-ف), ohm_fg (ف-ب)

flow_test_points   (هر نقطه‌ی کارکرد)
  id, flow_test_id FK, operating_no (شماره کارکرد), operating_type (نوع کارکرد),
  discharge_m3h, discharge_lps, head_m, drawdown_m, dynamic_level_m,
  pressure_atm, water_column_m, water_column_change_m,
  amperes (آمپرها A), efficiency, cos_phi (کسینوس فی),
  active_power_kw, reactive_power_kvar, apparent_power_kva,
  mechanical_power_kw, energy_intensity_kwh_m3 (شدت/مصرف ویژه انرژی)
```

---

## ۸. سری‌زمانی ماهانه‌ی تولید (از «روند تولید چاه‌ها»)

فایل ۴۴۴ ستونی در واقع چند متغیر × چند ماه × چند سال است. **نرمال‌سازی به فرمت بلند:**

```
monthly_well_readings
  id, well_id FK, jyear (سال شمسی), jmonth (۱..۱۲),
  metric enum(production تولید | pressure فشار | operating_hours کارکرد |
              avg_discharge دبی_متوسط | clearance ترخیص),
  value
  UNIQUE(well_id, jyear, jmonth, metric)
```
- ⚠️ نسبت «دبی متوسط سال X نسبت به ۱۳۹۹» در فایل اصلی وجود دارد ولی **مبنای درستی نیست** (چاه‌های جابه‌جا/بهسازی‌شده مرجعشان عوض شده). جایگزین: مقایسه با `well_baselines` (بخش ۱۲) که در هر رویداد ساختاری بازنشانی می‌شود.
- فیلدهای متن‌محورِ همان فایل (علت کارکرد کمتر از انتظار، خرابی طی آخرین بهسازی، وضعیت تعیین محل چاه، دبی مجاز پیشنهادی، سطح استاتیک/دینامیک) روی `wells` یا رویداد مربوطه می‌نشینند.

---

## ۹. نگهداری/تعمیر، بهسازی، جابه‌جایی

```
maintenance
  id, well_id FK, date, type enum(preventive|corrective),
  description, cost, downtime_days, parts, contractor_id FK

rehabilitations
  id, well_id FK, date, method, observed_fault (خرابی مشاهده‌شده),
  specific_capacity_before, specific_capacity_after, result, contractor_id FK

relocations
  id, source_well_id FK, target_well_id FK (چاه جدید),
  stage (مرحله ۱…), reason, date
```

---

## ۱۰. نگاشت معیارهای ماژول اولویت‌بندی به داده

| معیار | منبع داده |
|------|-----------|
| افت دبی نسبت به پایه | `monthly_well_readings` (دبی متوسط) ÷ `well_baselines.baseline_discharge_lps` (پویا، per-well) |
| افت راندمان | روند `flow_test_points.efficiency` در طول زمان |
| افزایش کدورت / مشکل کیفی | فیلد کیفی (در فرم‌ها «مشکل کیفی» در شرح خرابی) → نیاز به فیلد ساختاریافته‌ی کیفیت آب |
| سن/سابقه‌ی پمپ و سوختن | `pump_install_events` (عمر مفید، علت کشیدن=سوختن سیم‌پیچ) |
| تعداد دفعات تعمیر | شمارش `maintenance` و `pump_install_events` |
| اهمیت چاه | `monthly_well_readings` (تولید) + پهنه/جمعیت |

> **پیشنهاد:** یک جدول `water_quality` مستقل اضافه شود (EC، کدورت، کلر، تاریخ نمونه) چون کیفیت آب معیار حذفی اولویت‌بندی است ولی در فرم‌های فعلی فقط به‌صورت متن پراکنده («مشکل کیفی») ثبت شده.

---

## ۱۱. نکات مهاجرت داده
- تاریخ‌ها شمسی و با فرمت‌های مختلط‌اند (`1404/02/08` و `14041110`). در مهاجرت به ISO میلادی نرمال شوند؛ نمایش شمسی در UI (طبق درس‌آموخته‌ی ارقام فارسی سیستم مالی).
- `تیپ پمپ` مثل `384/8` → تجزیه به `model_designation` + `stages`.
- بسیاری از سلول‌ها مقدار `0` به‌جای خالی دارند → در پاک‌سازی به NULL تبدیل شوند.
- نام چاه‌ها املای متعدد دارند (آزاد شهر / آزادشهر) → تطبیق با `pm_code` هنگام import.
- چندین «نصب باز» = نصب فعلیِ بدون کشیدن → `pull` ندارد، عمر مفید هنوز در حال شمارش.

---

## ۱۲. جداول رکن‌های جدید (خط‌پایه، چاه‌نگاری، تایم‌لاین)

### ۱۲٫۱ خط‌پایه‌ی پویای چاه (`well_baselines`)
مرجع مقایسه‌ی افت دبی/راندمان که در هر **رویداد ساختاری** بازنشانی می‌شود (به‌جای سال ثابت ۱۳۹۹).
```
well_baselines
  id PK, well_id FK,
  anchor_event_type enum(drilling | rehab | relocation | install),
  anchor_event_id   (ارجاع به رکورد رویدادِ لنگر), anchor_date,
  baseline_kind enum(design_allowed دبی‌مجاز‌آزمایش | best_observed بهترین‌مشاهده‌شده),
  baseline_discharge_lps, baseline_efficiency, baseline_dynamic_level,
  baseline_specific_capacity,
  is_current bool,   source enum(measured | proposed_by_system | user_confirmed)
```
> **هر دو نوع مرجع نگه‌داری می‌شوند** (تصمیم کاربر): `design_allowed` = دبی مجاز/پیشنهادی آزمایش پمپاژ، و `best_observed` = بهترین دبی ثبت‌شده در پیکربندی فعلی. یک تنظیم سراسری (`settings.prioritization_baseline_kind`) مشخص می‌کند کدام مبنای اولویت‌بندی باشد و مدیر می‌تواند عوضش کند. هنگام ثبت رویداد ساختاری، خط‌پایه‌های جدید (`is_current=true`) ساخته و قبلی‌ها بسته می‌شوند.

### ۱۲٫۲ چاه‌نگاری / Well Videometry
> ⏳ **موقت — در انتظار فرم واقعی کاربر.** اسکیمای زیر پیش‌فرض است و پس از دریافت فایل نمونه‌ی چاه‌نگاری (در `current data/`) با فیلدهای دقیق به‌روزرسانی می‌شود.
```
well_video_logs
  id PK, well_id FK, log_date, contractor_id FK→suppliers,
  depth_from_m, depth_to_m, equipment, video_file_ref (مسیر فایل، نه خود فایل), summary
well_video_findings
  id, video_log_id FK, depth_m,
  finding_type enum(casing_damage | encrustation | sediment | corrosion | hole | other),
  severity enum(low|medium|high), note
```
> یافته‌های شدید (مثل `casing_damage`/`hole`) می‌توانند به‌عنوان سیگنال در ماژول اولویت‌بندی (تصمیم بهسازی/جابه‌جایی) وارد شوند.

### ۱۲٫۳ تایم‌لاین واحد چاه (`well_timeline` — VIEW)
نمای فقط‌خواندنی که با `UNION ALL` همه‌ی جداول رویداد را یکی می‌کند؛ بدون افزونگی داده.
```sql
well_timeline (VIEW)
  well_id, event_date, event_type, event_module,
  ref_table, ref_id, title, summary, status, created_by
-- منابع UNION: drilling, pump_tests, pump_install_events, flow_tests,
--   maintenance, rehabilitations, relocations, well_video_logs
```
> در زنجیره‌ی `parent_well_id`، می‌توان تایم‌لاین **چندنسلی** (چاه قبلی + فعلی) ساخت. این View هم ورودیِ تشخیص «آخرین رویداد ساختاری» برای `well_baselines` است، هم خروجی گزارشیِ «پرونده‌ی چاه».

### ۱۲٫۴ کیفیت آب (`water_quality` — شکاف داده‌ای)
معیار حذفیِ اولویت‌بندی؛ در فرم‌های فعلی فقط متن پراکنده («مشکل کیفی») است و نیاز به ساختار رسمی دارد.
```
water_quality
  id, well_id FK, sample_date, ec, turbidity (کدورت), chlorine,
  ph, tds, is_potable bool, lab_ref, note
```

---

## ۱۳. دور دوم داده‌ها (۱۴۰۵) — اسکیمای قطعی‌شده

تحلیل بسته‌ی دوم فایل‌های `current data/` (شامل `Borwells.xlsx`، `حفاری.xlsx`، فرم‌های خام دبی‌سنجی ۱۴۰۵، `... انتخاب پمپ`، `گزارش بهسازی و پمپاژ`، گانت بهسازی، و PDFهای چاه‌نگاری). این بخش بخش‌های پیش‌نویس بالا را با فیلدهای واقعی نهایی می‌کند.

### ۱۳٫۰ رویداد ساختاری سوم: «کف‌شکنی»
`پروانه چاه` سه نوع دارد: **جدید | جابجایی | کف‌شکنی** (deepening). پس `wells.location_status` و خط‌پایه (`well_baselines`) باید کف‌شکنی را هم به‌عنوان رویداد بازنشانی‌کننده بپذیرند. همچنین `نوع چاه (construction)` = **آهکی | سیمانتاسیون | معمولی** و در فرم بهره‌برداری **سیمانته/غیرسیمانته** → فیلد `wells.construction_type`.

### ۱۳٫۱ `Borwells` = رجیستری مرجع چاه (با مختصات) — منبع seed جدول `wells`
فیلدها: نام چاه · پروانه (جدید/جابجایی/کف‌شکنی) · نوع چاه · روش حفاری · شهری/روستایی · **کلاسه پرونده** · **X · Y · ZONE** (UTM 40) · پیمانکار · شماره/تاریخ قرارداد · سال حفر · تاریخ استقرار دستگاه حفاری · عمق چاه در پروانه · طول کلی لوله‌گذاری · طول لوله فولادی ساده/مشبک · طول لوله UPVC ساده/مشبک · طول قطعه تبدیلی · قطر لوله‌ها · تاریخ ترخیص دستگاه · تاریخ اتمام آزمایش پمپاژ · حداکثر آبدهی · **دبی پیشنهادی** · سطح استاتیک · سطح دینامیک در دبی پیشنهادی · مقدار افت · ویدیومتری(انجام‌شده؟) · توضیحات.
> این فایل `pm_code` ندارد ولی `کلاسه پرونده`+`نام چاه` دارد؛ تطبیق `pm_code` از `تجمیعی (400-405)` که هر سه را دارد.

### ۱۳٫۲ `drilling` — ستون‌های واقعی (از `حفاری.xlsx`, ۸۶ ستون، ۲۳۳ چاه)
به `drilling` افزوده شود: نام مجری · نام شرکت پیمانکار/پیمانکار/تلفن · محل تأمین اعتبار · نام ناظر/تلفن · عمق حفاری اولیه و **اصلاحی** · نوع درخواست · درپوش · الواتور · هد سرچاه · **ضرایب a, b** (افت=aQ+bQ²) · **آزمایش پلکانی**: دور موتور ۱..۵، حداکثر آبدهی ۱..۵، سطح استاتیک ۱..۵، سطح دینامیک ۱..۵، افت ۱..۵، نسبت افت‌به‌دبی ۱..۵ · آدرس. (سطرهای ۱..۵ → جدول فرزند `pump_test_steps`، نه ستون‌های پهن.)

### ۱۳٫۳ ماژول انتخاب پمپ / مهندسی مجدد (`pump_selections` — اسکیمای واقعی)
از `... انتخاب پمپ`:
```
pump_selections (بازنگری‌شده)
  id, well_id FK, action_needed (اقدام: «افزایش دبی»…),
  prev_pump_type, prev_motor_type, prev_discharge_lps,        -- وضعیت قبلی
  selected_pump_type, selected_motor_type, target_discharge_lps,
  discharge_increase_lps, selected_head_m,                    -- خروجی انتخاب
  status (وضعیت انجام), jyear, jmonth, form_delivery_date,
  pull_date, videometry_date, install_date,                  -- زنجیره‌ی اجرا
  verify_flowtest_date, verify_discharge_lps, verify_head_m   -- صحت‌سنجی پس از نصب
```
> این ماژول کل زنجیره را به‌هم وصل می‌کند: **انتخاب پمپ → کشیدن → چاه‌نگاری → نصب → دبی‌سنجیِ صحت‌سنجی**. `verify_discharge` در برابر `target_discharge` نشان‌دهنده‌ی موفقیت اقدام است.

### ۱۳٫۴ بهسازی (`rehabilitations` — اسکیمای واقعی)
از `گزارش بهسازی و پمپاژ`:
```
rehabilitations (بازنگری‌شده)
  id, well_id FK, stage (مرحله: اول/دوم…), jyear,
  rehab_date, rehab_contractor_id FK,
  pumping_end_date, pumping_contractor_id FK,
  pump_type_before, discharge_before_lps,
  pump_type_after,  discharge_after_lps, discharge_change_lps,
  reason (علت بهسازی: شولات/…)
```
> «شولات» (شن‌دهی) علت پرتکرار است؛ بهبود = `discharge_after − discharge_before`. پیمانکار بهسازی و پیمانکار پمپاژ **جدا** هستند.

### ۱۳٫۵ برنامه‌ریزی/گانت بهسازی (ماژول آینده)
`1405گانت چارت بهسازی` عملیات‌ها را به تفکیک **ویدئومتری / ترمیم / بهسازی** و پیمانکار در جدول ماهانه زمان‌بندی می‌کند → یک `rehab_plan` / نمای گانت در فاز برنامه‌ریزی. تأیید می‌کند که **چاه‌نگاری، ترمیم و بهسازی** عملیات مجزای پیمانکاری‌اند.

### ۱۳٫۶ فرم خام دبی‌سنجی — فیلدهای اضافی نسبت به فایل تجمیعی
هر فایل اکسلِ چاه = یک شیت به‌ازای هر **تاریخ آزمایش** (تاریخچه). افزوده شود به `flow_tests`: **دبی طراحی** و **دبی پروانه** (جدا از دبی مجاز) · `construction_type` (سیمانته/غیرسیمانته) · توان تابلو · سیستم راه‌انداز (سافت/ستاره‌مثلث/درایو/تک‌ضرب) · **آخرین سابقه شولات** (تاریخ) · فشار تنظیمی · حجم کل ابتدا/انتهای تخلیه و **حجم تخلیه** (m³) · برند/سایز کنتور + کنتور پرتابل · **نظر کارشناس** (متن آزاد — منبع اصلی ثبت کدورت/شولات). منحنی طراحی پمپ (هد/دبی + `xax`=راندمان حداکثر) داخل همین فرم است → می‌تواند `pump_models.curve` را پر کند.
> **کدورت** اینجا هم فقط در «نظر کارشناس» متنی است → جدول ساختاریافته‌ی `water_quality` (§۱۲٫۴) همچنان لازم است.

### ۱۳٫۷ چاه‌نگاری (`well_video_logs` — تأییدشده از PDFها)
گزارش‌های PDF پیمانکاران (تکین سازه / نگین سازه راه شرق). انواع یافته در `well_video_findings.finding_type` گسترش یابد به:
`casing_rupture (پارگی جدار) | screen_blockage (گرفتگی مشبک) | sediment (رسوب‌گذاری) | erosion (فرسایش) | corrosion | fallen_object (اشیاء سقوطی) | encrustation (سیمانته‌شدن پشت جداره) | other`؛ به‌علاوه `final_depth_m` و `water_level_m` در سرآیند گزارش. فایل PDF/ویدئو روی دیسک، ارجاع در DB.
