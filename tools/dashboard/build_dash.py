# -*- coding: utf-8 -*-
"""می‌سازد: داشبوردِ نمونه‌ی پایشِ پروتکل ۱۰۰ روزه — یک فایل HTML تکی."""

import html
import sys

from dash_data import (POINTS, BODY, KPI, SEGMENTS, LABS, DAILY,
                       WEEK_LABELS, NEEDS, fa)
from dash_charts import line_chart, dumbbell, body_figure, adherence_bar, meter
from dash_css import CSS

E = html.escape


# ---------------------------------------------------------------- نشان‌ها

ICONS = {
    'blood': '<path d="M12 3s6 7 6 11a6 6 0 0 1-12 0c0-4 6-11 6-11Z"/>',
    'scale': '<path d="M4 20h16M6 20V9a6 6 0 0 1 12 0v11M9 9h6"/><circle cx="12" cy="13" r="2.5"/>',
    'tape':  '<rect x="2.5" y="8" width="19" height="8" rx="3"/><path d="M7 12v3M11 12v3M15 12v3M19 12v3"/>',
    'log':   '<path d="M6 3h9l4 4v14H6z"/><path d="M14 3v5h5M9 12h6M9 16h4"/>',
    'photo': '<rect x="3" y="6" width="18" height="14" rx="3"/><circle cx="12" cy="13" r="3.5"/><path d="M8 6l1.5-2h5L16 6"/>',
    'file':  '<path d="M7 3h7l4 4v14H7z"/><path d="M14 3v5h5M10 12h6M10 16h6"/>',
    'ok':    '<path d="m5 12 4.5 4.5L19 7"/>',
    'warn':  '<path d="M12 4 2.5 20h19L12 4Z"/><path d="M12 10v4M12 17v.01"/>',
    'bad':   '<circle cx="12" cy="12" r="9"/><path d="m9 9 6 6M15 9l-6 6"/>',
    'sun':   '<circle cx="12" cy="12" r="4.5"/><path d="M12 2v2M12 20v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M2 12h2M20 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4"/>',
}


def icon(name, size=18, cls=''):
    d = ICONS.get(name, '')
    if not d:
        return ''
    c = f' class="{cls}"' if cls else ''
    return (f'<svg{c} viewBox="0 0 24 24" width="{size}" height="{size}" fill="none" '
            f'stroke="currentColor" stroke-width="1.8" stroke-linecap="round" '
            f'stroke-linejoin="round" aria-hidden="true">{d}</svg>')


# ------------------------------------------------- وضعیتِ یک عددِ آزمایش

def status(v, lo, hi):
    """عدد نسبت به محدوده‌ی مرجع کجاست؟"""
    if lo is not None and v < lo:
        far = (lo - v) / lo
        return ('bad', 'پایین‌تر از نرمال') if far > 0.15 else ('warn', 'کمی پایین')
    if hi is not None and v > hi:
        far = (v - hi) / hi
        return ('bad', 'بالاتر از نرمال') if far > 0.15 else ('warn', 'کمی بالا')
    return ('ok', 'در محدوده‌ی نرمال')


def tag(kind, text):
    ico = {'ok': 'ok', 'warn': 'warn', 'bad': 'bad'}[kind]
    return f'<span class="tag tag--{kind}">{icon(ico, 13)}{E(text)}</span>'


def ref_text(lo, hi):
    if lo is not None and hi is not None:
        return f'{fa(lo)} تا {fa(hi)}'
    if hi is not None:
        return f'کمتر از {fa(hi)}'
    if lo is not None:
        return f'بیشتر از {fa(lo)}'
    return '—'


def num(v):
    """عددِ فارسی، بدونِ صفرِ اعشارِ بی‌فایده."""
    if isinstance(v, float) and v == int(v):
        v = int(v)
    return fa(v)


# ===========================================================================
#  بخش‌ها
# ===========================================================================

def sec_kpi():
    cards = []
    for k in KPI:
        d = round(k['after'] - k['before'], 1)
        improved = (d < 0) if k['good'] == 'down' else (d > 0)
        sign = '−' if d < 0 else '+'
        cards.append(f'''<article class="card kpi">
  <p class="kpi__label">{E(k['label'])}</p>
  <p class="kpi__row">
    <span class="kpi__now">{num(k['after'])}</span>
    <span class="kpi__unit">{E(k['unit'])}</span>
  </p>
  <p class="kpi__from">در شروع: {num(k['before'])} {E(k['unit'])}</p>
  <p class="kpi__delta kpi__delta--{'good' if improved else 'bad'}">
    {icon('ok' if improved else 'warn', 13)} {sign}{num(abs(d))} {E(k['unit'])}
  </p>
  <p class="kpi__note">{E(k['note'])}</p>
</article>''')

    return f'''<section class="sec" aria-labelledby="s1">
  <div class="wrap">
    <header class="sec__head">
      <span class="sec__n">۱</span><h2 class="sec__title" id="s1">عددهای کلیدی پایان دوره</h2>
      <p class="sec__note">چهار عددی که در اولین نگاه وضعیت را می‌گویند. هر کدام، هم مقدار پایان را نشان می‌دهد هم نقطه‌ی شروع را — چون عددِ تنها بدونِ مبدأ معنا ندارد.</p>
    </header>
    <div class="grid grid--4">{''.join(cards)}</div>
  </div>
</section>'''


def sec_body():
    series = [
        {'name': 'چربی',  'slot': 'series-1', 'values': BODY['fat']},
        {'name': 'عضله',  'slot': 'series-3', 'values': BODY['muscle']},
    ]
    chart = line_chart(POINTS, series, 15, 40)

    rows = ''.join(
        f'<tr><th scope="row">{E(p)}</th>'
        f'<td class="num">{num(BODY["fat"][i])}٪</td>'
        f'<td class="num">{num(BODY["muscle"][i])}٪</td></tr>'
        for i, p in enumerate(POINTS)
    )

    seg_rows = ''.join(
        f'''<tr>
  <th scope="row">{E(s['name'])}</th>
  <td class="num">{num(s['before'])}</td>
  <td class="num">{num(s['after'])}</td>
  <td class="num">{fa(round((s['after']-s['before'])/s['before']*100, 1))}٪+</td>
  <td class="num">{fa(s['norm'][0])} تا {fa(s['norm'][1])}</td>
  <td>{tag(*status(s['after'], s['norm'][0], s['norm'][1]))}</td>
</tr>''' for s in SEGMENTS
    )

    return f'''<section class="sec" aria-labelledby="s2">
  <div class="wrap">
    <header class="sec__head">
      <span class="sec__n">۲</span><h2 class="sec__title" id="s2">تحلیل ترکیب بدن</h2>
      <p class="sec__note">هر دو سریِ نمودار درصدِ وزنِ بدن‌اند، پس روی یک محور نشسته‌اند. نمودارِ دو محوره عمداً استفاده نشده — خواننده را گمراه می‌کند.</p>
    </header>

    <div class="grid grid--2">
      <article class="card">
        <h3 class="card__title">درصد چربی در برابر درصد عضله</h3>
        <p class="card__sub">چهار نقطه‌ی اندازه‌گیری، هم‌تراز با گیت‌های پروتکل</p>
        {chart}
        <ul class="legend">
          <li><i style="background:var(--series-1)"></i> درصد چربی بدن</li>
          <li><i style="background:var(--series-3)"></i> درصد عضله‌ی اسکلتی</li>
        </ul>
        <details class="data">
          <summary>نمایش جدول داده</summary>
          <div class="tbl-wrap"><table>
            <caption>همان عددهای نمودار، برای کسی که جدول را راحت‌تر می‌خواند.</caption>
            <thead><tr><th>نقطه</th><th>درصد چربی</th><th>درصد عضله</th></tr></thead>
            <tbody>{rows}</tbody>
          </table></div>
        </details>
      </article>

      <article class="card">
        <h3 class="card__title">آنالیز بخش‌به‌بخش عضله</h3>
        <p class="card__sub">همان خروجی که دستگاه InBody می‌دهد — روی هر بخش نگه دارید</p>
        <div class="figs">
          <figure>{body_figure(SEGMENTS, 'before')}<figcaption>روز ۰</figcaption></figure>
          <figure>{body_figure(SEGMENTS, 'after')}<figcaption>روز ۱۰۰</figcaption></figure>
        </div>
        <p class="ramp">
          <svg width="0" height="0" aria-hidden="true" style="position:absolute"></svg>
          <span class="ramp__s ramp__s--l1"></span>
          <span class="ramp__s ramp__s--l2"></span>
          <span class="ramp__s ramp__s--l3"></span>
          <span class="ramp__s ramp__s--l4"></span>
          کم‌رنگ: پایین‌تر از محدوده‌ی نرمال &nbsp;←&nbsp; پررنگ: داخل یا بالاتر از آن
        </p>
        <details class="data">
          <summary>نمایش جدول داده</summary>
          <div class="tbl-wrap"><table>
            <caption>توده‌ی عضلانی هر بخش، بر حسب کیلوگرم.</caption>
            <thead><tr><th>بخش</th><th>روز ۰</th><th>روز ۱۰۰</th><th>تغییر</th><th>محدوده‌ی نرمال</th><th>وضعیت</th></tr></thead>
            <tbody>{seg_rows}</tbody>
          </table></div>
        </details>
      </article>
    </div>
  </div>
</section>'''


def sec_labs():
    rows = []
    last_group = None

    for L in LABS:
        if L['group'] != last_group:
            rows.append(f'<tr class="grouprow"><th colspan="6" scope="colgroup">{E(L["group"])}</th></tr>')
            last_group = L['group']

        kind, label = status(L['after'], L['low'], L['high'])
        unit = f' <span style="color:var(--ink-3);font-size:.9em">{E(L["unit"])}</span>' if L['unit'] else ''

        # عددِ شروع هم وضعیت دارد. نشان دادنش یعنی خواننده می‌فهمد
        # «در محدوده‌ی نرمال»ِ ستونِ آخر از کجا آمده است.
        kind0, _ = status(L['before'], L['low'], L['high'])
        before = f'{num(L["before"])}{unit}'
        if kind0 != 'ok':
            before = f'<span class="out">{icon("warn", 12)}{before}</span>'

        rows.append(f'''<tr>
  <th scope="row">{E(L['name'])}</th>
  <td class="num">{before}</td>
  <td class="num"><strong>{num(L['after'])}</strong>{unit}</td>
  <td>{dumbbell(L['before'], L['after'], L['low'], L['high'])}</td>
  <td class="num">{ref_text(L['low'], L['high'])}</td>
  <td>{tag(kind, label)}</td>
</tr>''')

    m = meter((5.36, 1.84), 2.0, 6.5)

    return f'''<section class="sec" aria-labelledby="s3">
  <div class="wrap">
    <header class="sec__head">
      <span class="sec__n">۳</span><h2 class="sec__title" id="s3">آزمایش خون</h2>
      <p class="sec__note">هر ردیف دو نقطه دارد: شروع و پایان. نوارِ خاکستریِ پشتِ آن‌ها محدوده‌ی مرجعِ آزمایشگاه است — یعنی در یک نگاه معلوم می‌شود عدد وارد محدوده شده یا نه.</p>
    </header>

    <article class="card" style="margin-block-end:1rem">
      <h3 class="card__title">شاخص مقاومت انسولینی (HOMA-IR)</h3>
      <p class="card__sub">مهم‌ترین عددِ این صفحه برای یک پرونده‌ی متابولیک</p>
      {m}
      <ul class="legend">
        <li><i style="background:var(--ink-3)"></i> شروع</li>
        <li><i style="background:var(--ok)"></i> پایان دوره</li>
        <li><i style="background:var(--ok-bg);border:1px solid var(--line)"></i> محدوده‌ی نرمال</li>
      </ul>
    </article>

    <article class="card">
      <h3 class="card__title">پنل کامل</h3>
      <p class="card__sub">دوازده شاخص، در چهار دسته</p>
      <div class="tbl-wrap"><table>
        <caption>نمونه — عددها ساختگی‌اند و به فرد واقعی‌ای مربوط نیستند.</caption>
        <thead><tr><th>شاخص</th><th>پیش از پروتکل</th><th>پایان دوره</th><th>روند</th><th>محدوده‌ی مرجع</th><th>وضعیت</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table></div>
    </article>
  </div>
</section>'''


def sec_daily():
    rows = ''.join(
        f'<tr><th scope="row">{E(d["name"])}</th>' + ''.join(
            f'<td class="num" style="min-width:8rem">{adherence_bar(v)}'
            f'<span style="font-size:.78rem;color:var(--ink-3)">{fa(v)}٪</span></td>'
            for v in d['weeks']
        ) + '</tr>'
        for d in DAILY
    )

    heads = ''.join(f'<th>{E(w)}</th>' for w in WEEK_LABELS)

    return f'''<section class="sec" aria-labelledby="s4">
  <div class="wrap">
    <header class="sec__head">
      <span class="sec__n">۴</span><h2 class="sec__title" id="s4">پایبندی روزانه</h2>
      <p class="sec__note">این بخش از ثبتِ روزانه‌ی خودِ مراجع ساخته می‌شود، نه از آزمایش. بدونِ این داده، وقتی عددی تکان نمی‌خورد نمی‌شود فهمید مشکل از پروتکل است یا از اجرا.</p>
    </header>
    <article class="card">
      <div class="tbl-wrap"><table class="ad">
        <caption>درصد روزهایی که هر مورد انجام شده است.</caption>
        <thead><tr><th>مورد</th>{heads}</tr></thead>
        <tbody>{rows}</tbody>
      </table></div>
    </article>
  </div>
</section>'''


def sec_needs():
    cards = []
    for n in NEEDS:
        items = ''.join(f'<li>{E(i)}</li>' for i in n['items'])
        cards.append(f'''<article class="need">
  <div class="need__top">
    <span class="need__icon">{icon(n['icon'], 20)}</span>
    <div>
      <h3 class="need__title">{E(n['title'])}</h3>
      <p class="need__when">{E(n['when'])}</p>
    </div>
  </div>
  <p class="need__who">{E(n['who'])}</p>
  <ul class="need__list">{items}</ul>
  <p class="need__note">{E(n['note'])}</p>
</article>''')

    return f'''<section class="sec" aria-labelledby="s5" style="background:var(--surface-2);border-block:1px solid var(--line)">
  <div class="wrap">
    <header class="sec__head">
      <span class="sec__n">۵</span><h2 class="sec__title" id="s5">چه داده‌ای از شما لازم است</h2>
      <p class="sec__note">همه‌ی چیزی که در صفحات بالا دیدید، از همین شش دسته ساخته می‌شود. هیچ‌کدام سخت نیست؛ فقط باید منظم باشد.</p>
    </header>
    <div class="grid grid--3">{''.join(cards)}</div>
  </div>
</section>'''


# ===========================================================================

def build():
    body = f'''<p class="demo">⚠️ این صفحه یک نمونه است. همه‌ی عددها ساختگی‌اند و به هیچ فرد واقعی‌ای مربوط نیستند.</p>

<header class="head">
  <div class="wrap">
    <p class="head__eyebrow">آکادمی تندرستی سعادت‌مهر — پروتکل ۱۰۰ روزه SMP</p>
    <h1 class="head__title">پرونده‌ی پایش متابولیک</h1>
    <p class="head__sub">این صفحه نشان می‌دهد در طول صد روز چه داده‌ای جمع می‌شود، چطور کنار هم خوانده می‌شود، و در پایان چه تصویری از بدن به دست می‌دهد.</p>
    <ul class="head__meta">
      <li>مراجع نمونه · مرد · ۳۸ ساله</li>
      <li>دوره: روز ۰ تا روز ۱۰۰</li>
      <li>۴ نوبت اندازه‌گیری · ۳ نوبت آزمایش خون</li>
    </ul>
  </div>
</header>

<main>
{sec_kpi()}
{sec_body()}
{sec_labs()}
{sec_daily()}
{sec_needs()}
</main>

<footer class="foot">
  <div class="wrap">
    <p><strong>درباره‌ی این فایل:</strong> این یک نمونه‌ی طراحی است، نه گزارشِ یک مراجع. هدفش این است که پیش از شروع، روشن باشد چه داده‌ای لازم است و خروجی چه شکلی خواهد داشت.</p>
    <p>هیچ‌یک از عددهای این صفحه نتیجه‌ی قابل‌انتظار نیست. پاسخ هر بدن متفاوت است و این صفحه جایگزین تشخیص، تجویز یا درمان پزشکی نیست.</p>
    <p>داده‌ی سلامت هر مراجع محرمانه است و فقط با رضایت کتبی خودش، و پس از حذف نشانه‌های هویتی، جایی منتشر می‌شود.</p>
  </div>
</footer>

<button class="themebtn" type="button" id="theme" aria-label="تغییر روشن و تیره">{icon('sun', 18)}</button>

<script>
/* تمِ روشن/تیره. پیش‌فرض همان تنظیمِ سیستم است؛ این دکمه فقط
   دستیِ آن را عوض می‌کند و انتخاب را نگه می‌دارد. */
( function () {{
  var KEY = 'sm-dash-theme';
  var root = document.documentElement;

  try {{
    var saved = localStorage.getItem( KEY );
    if ( saved ) {{ root.setAttribute( 'data-theme', saved ); }}
  }} catch ( e ) {{ /* حالتِ ناشناس یا کوکیِ بسته — مهم نیست */ }}

  document.getElementById( 'theme' ).addEventListener( 'click', function () {{
    var dark = root.getAttribute( 'data-theme' ) === 'dark'
      || ( ! root.hasAttribute( 'data-theme' )
           && window.matchMedia( '(prefers-color-scheme: dark)' ).matches );
    var next = dark ? 'light' : 'dark';
    root.setAttribute( 'data-theme', next );
    try {{ localStorage.setItem( KEY, next ); }} catch ( e ) {{}}
  }} );
}}() );
</script>'''

    return f'''<!doctype html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>نمونه پرونده پایش متابولیک — آکادمی تندرستی سعادت‌مهر</title>
<meta name="description" content="نمونه‌ی داشبورد پایش پروتکل ۱۰۰ روزه: ترکیب بدن، آزمایش خون، پایبندی روزانه و فهرست داده‌های لازم. همه‌ی عددها ساختگی‌اند.">
<meta name="robots" content="noindex">
<style>{CSS}</style>
</head>
<body>
{body}
</body>
</html>'''


if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else 'dashboard.html'
    with open(out, 'w', encoding='utf-8') as f:
        f.write(build())
    print('✓ ساخته شد:', out)
