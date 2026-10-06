# -*- coding: utf-8 -*-
"""استایلِ داشبورد. جدا نگه داشته شده تا فایلِ ساخت خوانا بماند."""

CSS = r"""
/* ==========================================================================
   پالت
   --------------------------------------------------------------------------
   سه رنگِ داده‌ای با اسکریپتِ اعتبارسنجیِ پالت آزموده شده‌اند و در هر دو
   حالتِ روشن و تیره همه‌ی گیت‌ها را رد می‌کنند:

     روشن، روی کارتِ سفید   #A8752A · #2A78D6 · #12916A
     تیره، روی #101C27      #B98A32 · #3C85DA · #189B72

   کمترین فاصله‌ی دو رنگِ همسایه در دیدِ رنگ‌پریش ΔE ۱۷٫۶ است (آستانه ۸)
   و در دیدِ عادی ΔE ۱۹٫۱ (آستانه ۱۵). با این حال هر سری برچسبِ مستقیم و
   جدولِ داده هم دارد، چون رنگ هیچ‌وقت نباید تنها حاملِ معنا باشد.
   ========================================================================== */

:root {
  color-scheme: light;

  --bg:          #F4F1EA;
  --surface:     #FFFFFF;
  --surface-2:   #FAF8F3;
  --line:        #E2DCCF;
  --line-soft:   #EFEAE0;

  --ink:         #10161C;
  --ink-2:       #46525E;
  --ink-3:       #6B7680;

  --brand:       #0C243C;
  --brand-2:     #12314F;
  --gold:        #A8843C;

  --series-1:    #A8752A;   /* چربی */
  --series-2:    #2A78D6;   /* وزن و اندازه */
  --series-3:    #12916A;   /* عضله */

  --ok:          #146B47;
  --warn:        #8A5D0E;
  --bad:         #A6342A;

  --ok-bg:       #E8F3ED;
  --warn-bg:     #FBF2DF;
  --bad-bg:      #FAEDEB;

  --radius:      14px;
  --radius-sm:   8px;
  --shadow:      0 1px 2px rgba(12,36,60,.05), 0 8px 24px rgba(12,36,60,.07);

  --font: "Vazirmatn", "Segoe UI", Tahoma, "Iranian Sans", system-ui, sans-serif;
}

@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --bg:        #0B141C;
    --surface:   #101C27;
    --surface-2: #16242F;
    --line:      #273745;
    --line-soft: #1D2B37;
    --ink:       #F2F5F8;
    --ink-2:     #B6C3CE;
    --ink-3:     #8A98A4;
    --brand:     #DCE5EE;
    --brand-2:   #B9C8D8;
    --gold:      #DCC189;
    --series-1:  #B98A32;
    --series-2:  #3C85DA;
    --series-3:  #189B72;
    --ok:        #5FC79B;
    --warn:      #E0B457;
    --bad:       #EC8278;
    --ok-bg:     #11291F;
    --warn-bg:   #2A2211;
    --bad-bg:    #2B1714;
    --shadow:    0 1px 2px rgba(0,0,0,.3), 0 10px 28px rgba(0,0,0,.35);
  }
}

:root[data-theme="dark"] {
  color-scheme: dark;
  --bg:        #0B141C;  --surface:   #101C27;  --surface-2: #16242F;
  --line:      #273745;  --line-soft: #1D2B37;
  --ink:       #F2F5F8;  --ink-2:     #B6C3CE;  --ink-3:     #8A98A4;
  --brand:     #DCE5EE;  --brand-2:   #B9C8D8;  --gold:      #DCC189;
  --series-1:  #B98A32;  --series-2:  #3C85DA;  --series-3:  #189B72;
  --ok:        #5FC79B;  --warn:      #E0B457;  --bad:       #EC8278;
  --ok-bg:     #11291F;  --warn-bg:   #2A2211;  --bad-bg:    #2B1714;
  --shadow:    0 1px 2px rgba(0,0,0,.3), 0 10px 28px rgba(0,0,0,.35);
}

* { box-sizing: border-box; }

body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font-family: var(--font);
  font-size: 15px;
  line-height: 1.9;
  -webkit-text-size-adjust: 100%;
}

.wrap { width: min(100% - 2rem, 1180px); margin-inline: auto; }

h1, h2, h3 { line-height: 1.5; margin: 0; }

/* ---------- نوارِ «این یک نمونه است» ---------- */

.demo {
  position: sticky;
  top: 0;
  z-index: 20;
  padding: .55rem 1rem;
  background: var(--gold);
  color: #1B1407;
  font-size: .84rem;
  font-weight: 700;
  text-align: center;
}

:root[data-theme="dark"] .demo,
@media (prefers-color-scheme: dark) { }

/* ---------- سربرگ ---------- */

.head {
  padding: clamp(1.75rem, 1.2rem + 2.5vw, 3rem) 0 clamp(1.5rem, 1rem + 2vw, 2.5rem);
  background: linear-gradient(155deg, #071A2B, #0C243C 55%, #12314F);
  color: #F4F7FA;
}

.head__eyebrow {
  margin: 0 0 .5rem;
  font-size: .76rem;
  font-weight: 700;
  letter-spacing: .14em;
  color: #DCC189;
}

.head__title {
  font-size: clamp(1.45rem, 1.1rem + 1.7vw, 2.3rem);
  font-weight: 800;
}

.head__sub {
  margin: .7rem 0 0;
  max-width: 62ch;
  font-size: .98rem;
  color: #B9C8D8;
}

.head__meta {
  display: flex;
  flex-wrap: wrap;
  gap: .5rem;
  margin: 1.25rem 0 0;
  padding: 0;
  list-style: none;
}

.head__meta li {
  padding: .35rem .85rem;
  border: 1px solid rgba(233,214,170,.3);
  border-radius: 999px;
  font-size: .8rem;
  color: #E9D6AA;
}

/* ---------- بخش و کارت ---------- */

.sec { padding-block: clamp(1.75rem, 1.2rem + 2vw, 2.75rem); }

.sec__head { margin-block-end: 1.1rem; }

.sec__n {
  display: inline-grid;
  place-items: center;
  width: 1.7rem; height: 1.7rem;
  margin-inline-end: .5rem;
  border-radius: 50%;
  background: var(--brand);
  color: var(--surface);
  font-size: .8rem; font-weight: 800;
  vertical-align: middle;
}

.sec__title { display: inline; font-size: clamp(1.1rem, .95rem + .7vw, 1.4rem); font-weight: 800; }

.sec__note { margin: .5rem 0 0; font-size: .89rem; color: var(--ink-3); max-width: 78ch; }

.card {
  padding: 1.25rem 1.3rem;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
}

.card__title { font-size: .98rem; font-weight: 800; margin-block-end: .25rem; }
.card__sub   { font-size: .83rem; color: var(--ink-3); margin: 0 0 1rem; }

.grid { display: grid; gap: 1rem; }
.grid--4 { grid-template-columns: repeat(auto-fit, minmax(13rem, 1fr)); }

/*
 * شش کارتِ «داده‌های لازم» با auto-fit می‌شد ۵ تا و بعد یکی تنها.
 * ستون‌ها را صریح می‌گذاریم تا همیشه ۳+۳ باشد.
 */
.grid--3 { grid-template-columns: minmax(0, 1fr); }
@media (min-width: 46rem) { .grid--3 { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (min-width: 70rem) { .grid--3 { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
.grid--2 { grid-template-columns: minmax(0, 1fr); }

@media (min-width: 60rem) { .grid--2 { grid-template-columns: minmax(0, 1.35fr) minmax(0, 1fr); } }

/* ---------- کارتِ عددِ کلیدی ---------- */

.kpi { display: flex; flex-direction: column; gap: .2rem; }

.kpi__label { font-size: .84rem; color: var(--ink-2); font-weight: 700; }

.kpi__row { display: flex; align-items: baseline; gap: .45rem; margin-block-start: .35rem; }

.kpi__now {
  font-size: clamp(1.8rem, 1.4rem + 1.6vw, 2.5rem);
  font-weight: 800;
  line-height: 1.1;
  font-variant-numeric: tabular-nums;
}

.kpi__unit { font-size: .82rem; color: var(--ink-3); font-weight: 700; }

.kpi__from {
  margin-block-start: .3rem;
  font-size: .82rem;
  color: var(--ink-3);
  font-variant-numeric: tabular-nums;
}

.kpi__delta {
  display: inline-flex;
  align-items: center;
  gap: .3rem;
  align-self: flex-start;
  margin-block-start: .55rem;
  padding: .22rem .6rem;
  border-radius: 999px;
  font-size: .8rem;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
}

.kpi__delta--good { background: var(--ok-bg);  color: var(--ok); }
.kpi__delta--bad  { background: var(--bad-bg); color: var(--bad); }

.kpi__note { margin: .6rem 0 0; font-size: .78rem; line-height: 1.8; color: var(--ink-3); }

/* ---------- نمودار ---------- */

/*
 * direction: ltr روی خودِ SVG عمدی است.
 *
 * داخلِ یک صفحه‌ی راست‌به‌چپ، text-anchor معنایش برعکس می‌شود و
 * برچسبِ محور سرِ جای اشتباه می‌نشیند. جای‌گذاریِ افقی را خودمان
 * در PHP/پایتون حساب کرده‌ایم (روز ۰ سمت راست)، پس SVG باید
 * مختصاتِ خام را بدونِ دخالت رسم کند. فقط متن‌هایی که کلمه‌ی
 * فارسی دارند دوباره rtl می‌شوند.
 */
.ch { width: 100%; height: auto; overflow: visible; direction: ltr; }

.ch__tick--x, .ch__dlabel { direction: rtl; }

.ch__grid  { stroke: var(--line-soft); stroke-width: 1; }
.ch__line  { fill: none; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
.ch__dot   { stroke: var(--surface); stroke-width: 2; }
.ch__tick  { font-size: 11px; fill: var(--ink-3); text-anchor: start; }
.ch__dlabel{ paint-order: stroke; stroke: var(--surface); stroke-width: 3px; }
.ch__tick--x { text-anchor: middle; }
.ch__dlabel{ font-size: 12px; font-weight: 800; text-anchor: end; }

.legend {
  display: flex;
  flex-wrap: wrap;
  gap: .3rem 1.1rem;
  margin: .9rem 0 0;
  padding: 0;
  list-style: none;
  font-size: .84rem;
  color: var(--ink-2);
}

.legend li { display: flex; align-items: center; gap: .4rem; }

.legend i {
  width: .85rem; height: .85rem;
  border-radius: 3px;
  flex: 0 0 auto;
}

/* ---------- پیکره‌ی بدن ---------- */

.figs { display: flex; gap: 1rem; justify-content: center; align-items: flex-start; }

.figs figure { margin: 0; text-align: center; flex: 1 1 0; }

.figs figcaption { font-size: .8rem; font-weight: 700; color: var(--ink-2); margin-block-start: .4rem; }

.fig { width: 100%; max-width: 160px; height: auto; }

.fig__inert { fill: var(--line-soft); }

.fig__seg {
  stroke: var(--surface);
  stroke-width: 1.5;
  cursor: help;
  transition: filter .18s ease;
}

.fig__seg:hover, .fig__seg:focus { filter: brightness(1.12); outline: none; }

/* رمپِ تک‌رنگ: کم‌رنگ = پایین‌تر از نرمال، پررنگ = بالاتر */
.fig__seg--l1 { fill: #CFE3DA; }
.fig__seg--l2 { fill: #93C6B0; }
.fig__seg--l3 { fill: #3F9E79; }
.fig__seg--l4 { fill: #12916A; }

:root[data-theme="dark"] .fig__seg--l1 { fill: #22453A; }
:root[data-theme="dark"] .fig__seg--l2 { fill: #2E6B55; }
:root[data-theme="dark"] .fig__seg--l3 { fill: #178763; }
:root[data-theme="dark"] .fig__seg--l4 { fill: #1FB184; }

@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) .fig__seg--l1 { fill: #22453A; }
  :root:not([data-theme="light"]) .fig__seg--l2 { fill: #2E6B55; }
  :root:not([data-theme="light"]) .fig__seg--l3 { fill: #178763; }
  :root:not([data-theme="light"]) .fig__seg--l4 { fill: #1FB184; }
}

.ramp { display: flex; align-items: center; gap: .45rem; margin-block-start: .9rem; font-size: .78rem; color: var(--ink-3); }

/* نمونه‌رنگ‌های رمپ همان چهار پله‌ی پیکره‌اند، پس باید با تمِ تیره
   هم عوض شوند — به همین خاطر کلاس‌اند نه رنگِ درون‌خطی. */
.ramp__s { width: 1.6rem; height: .55rem; border-radius: 2px; flex: 0 0 auto; }

.ramp__s--l1 { background: #CFE3DA; }
.ramp__s--l2 { background: #93C6B0; }
.ramp__s--l3 { background: #3F9E79; }
.ramp__s--l4 { background: #12916A; }

:root[data-theme="dark"] .ramp__s--l1 { background: #22453A; }
:root[data-theme="dark"] .ramp__s--l2 { background: #2E6B55; }
:root[data-theme="dark"] .ramp__s--l3 { background: #178763; }
:root[data-theme="dark"] .ramp__s--l4 { background: #1FB184; }

@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) .ramp__s--l1 { background: #22453A; }
  :root:not([data-theme="light"]) .ramp__s--l2 { background: #2E6B55; }
  :root:not([data-theme="light"]) .ramp__s--l3 { background: #178763; }
  :root:not([data-theme="light"]) .ramp__s--l4 { background: #1FB184; }
}

/* ---------- جدول ---------- */

.tbl-wrap { overflow-x: auto; }

table { width: 100%; border-collapse: collapse; font-size: .86rem; }

caption {
  text-align: start;
  font-size: .82rem;
  color: var(--ink-3);
  padding-block-end: .6rem;
}

th, td { padding: .6rem .7rem; text-align: start; border-block-end: 1px solid var(--line-soft); }

thead th {
  font-size: .78rem;
  font-weight: 800;
  color: var(--ink-2);
  border-block-end: 1px solid var(--line);
  white-space: nowrap;
}

tbody tr:hover { background: var(--surface-2); }

td.num { font-variant-numeric: tabular-nums; white-space: nowrap; }

.grouprow th {
  padding-block: 1rem .5rem;
  font-size: .8rem;
  color: var(--gold);
  border-block-end: 0;
}

.tag {
  display: inline-flex;
  align-items: center;
  gap: .3rem;
  padding: .15rem .55rem;
  border-radius: 999px;
  font-size: .76rem;
  font-weight: 800;
  white-space: nowrap;
}

.tag--ok   { background: var(--ok-bg);   color: var(--ok); }
.tag--warn { background: var(--warn-bg); color: var(--warn); }
.tag--bad  { background: var(--bad-bg);  color: var(--bad); }

/* عددِ شروع، وقتی بیرونِ محدوده‌ی مرجع بوده. رنگ تنها حاملِ معنا
   نیست: یک علامت هم کنارش می‌آید. */
.out {
  display: inline-flex;
  align-items: center;
  gap: .25rem;
  color: var(--bad);
  font-weight: 700;
}

.tag svg { flex: 0 0 auto; }

/* ---------- دامبل ---------- */

.db { width: 100%; max-width: 230px; height: auto; display: block; }

.db__ref  { fill: var(--line-soft); }
.db__bar  { stroke: var(--line); stroke-width: 3; stroke-linecap: round; }
.db__a    { fill: var(--ink-3); }
.db__b    { fill: var(--series-3); stroke: var(--surface); stroke-width: 2; }

/* ---------- سنجه ---------- */

.mt { width: 100%; height: auto; overflow: visible; }

.mt__track { fill: var(--line-soft); }
.mt__ok    { fill: var(--ok-bg); }
.mt__limit { stroke: var(--ink-3); stroke-width: 1.5; stroke-dasharray: 3 3; }
.mt__cap   { font-size: 11px; fill: var(--ink-3); text-anchor: middle; }
.mt__val   { font-size: 12px; font-weight: 800; fill: var(--ink); text-anchor: middle; }
.mt__a     { fill: var(--ink-3); }
.mt__b     { fill: var(--ok); stroke: var(--surface); stroke-width: 2; }

/* ---------- پایبندی ---------- */

.ad { width: 100%; }

.ad td { vertical-align: middle; }

.ad__track {
  display: block;
  width: 100%;
  min-width: 4.5rem;
  height: .55rem;
  border-radius: 999px;
  background: var(--line-soft);
  overflow: hidden;
}

.ad__fill { display: block; height: 100%; width: var(--v); border-radius: 999px; }

/* ---------- فهرستِ داده‌های لازم ---------- */

.need {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 1.3rem 1.3rem 1.4rem;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
}

.need__top { display: flex; align-items: flex-start; gap: .75rem; margin-block-end: .9rem; }

.need__icon {
  flex: 0 0 auto;
  display: grid;
  place-items: center;
  width: 2.5rem; height: 2.5rem;
  border-radius: 10px;
  background: var(--surface-2);
  border: 1px solid var(--line);
  color: var(--gold);
}

.need__title { font-size: 1.02rem; font-weight: 800; }

.need__when { font-size: .8rem; color: var(--series-2); font-weight: 700; margin-block-start: .15rem; }

.need__who { margin: 0 0 .9rem; font-size: .8rem; color: var(--ink-3); }

.need__list { margin: 0 0 1rem; padding: 0; list-style: none; }

.need__list li {
  position: relative;
  padding-inline-start: 1.25rem;
  font-size: .88rem;
  line-height: 1.95;
  color: var(--ink-2);
}

.need__list li::before {
  content: "";
  position: absolute;
  inset-inline-start: 0;
  top: .85em;
  width: .45rem; height: .45rem;
  border-radius: 50%;
  background: var(--gold);
}

.need__note {
  margin: auto 0 0;
  padding: .7rem .8rem;
  border-radius: var(--radius-sm);
  background: var(--surface-2);
  border-inline-start: 3px solid var(--gold);
  font-size: .8rem;
  line-height: 1.85;
  color: var(--ink-2);
}

/* ---------- جزئیاتِ جدولِ داده زیرِ هر نمودار ---------- */

details.data {
  margin-block-start: 1rem;
  border-block-start: 1px dashed var(--line);
  padding-block-start: .8rem;
}

details.data summary {
  cursor: pointer;
  font-size: .82rem;
  font-weight: 700;
  color: var(--series-2);
  list-style: none;
}

details.data summary::-webkit-details-marker { display: none; }

details.data summary::before { content: "⌄ "; font-weight: 800; }
details.data[open] summary::before { content: "⌃ "; }

details.data table { margin-block-start: .7rem; }

/* ---------- پاورقی ---------- */

.foot {
  padding-block: 1.75rem 2.5rem;
  border-block-start: 1px solid var(--line);
  font-size: .82rem;
  line-height: 2;
  color: var(--ink-3);
}

.foot strong { color: var(--ink-2); }

/* ---------- تمِ روشن/تیره ---------- */

.themebtn {
  position: fixed;
  inset-block-end: 1rem;
  inset-inline-end: 1rem;
  z-index: 30;
  display: grid;
  place-items: center;
  width: 2.75rem; height: 2.75rem;
  border-radius: 50%;
  border: 1px solid var(--line);
  background: var(--surface);
  color: var(--ink-2);
  box-shadow: var(--shadow);
  cursor: pointer;
}

@media print {
  .demo, .themebtn, details.data { position: static; }
  details.data { display: block; }
  body { background: #fff; }
}
"""
