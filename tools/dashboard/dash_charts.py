# -*- coding: utf-8 -*-
"""نمودارهای داشبورد — همه SVG دست‌ساز، بدون هیچ کتابخانه‌ای.

چرا بدون کتابخانه: این فایل قرار است یک HTML تکی باشد که هم آفلاین
باز شود هم بعداً داخل سایت بیفتد. هر کتابخانه‌ای یک وابستگی شبکه‌ای
اضافه می‌کند که در هر دو حالت دردسر است.
"""

from dash_data import fa


# ---------------------------------------------------------------------------
#  نمودار خطی — درصد چربی و درصد عضله
# ---------------------------------------------------------------------------

def line_chart(points, series, vmin, vmax, w=640, h=300):
    """دو سری درصدی روی یک محور.

    هر دو سری واحدِ یکسان دارند (درصدِ وزنِ بدن)، پس یک محور کافی است.
    محورِ دوم ممنوع است و اینجا هم لازم نیست.
    """
    pad_r, pad_l, pad_t, pad_b = 54, 54, 22, 40
    iw = w - pad_l - pad_r
    ih = h - pad_t - pad_b
    n = len(points)

    # در RTL نقطه‌ی اول باید سمتِ راست بنشیند.
    def X(i):
        return pad_l + iw - (iw * i / (n - 1))

    def Y(v):
        return pad_t + ih - ih * (v - vmin) / (vmax - vmin)

    out = [f'<svg viewBox="0 0 {w} {h}" class="ch" role="img" '
           f'aria-label="روند درصد چربی و درصد عضله در چهار نقطه‌ی اندازه‌گیری">']

    # خطوط راهنمای افقی + برچسبِ محور
    step = 5
    g = vmin
    while g <= vmax + 0.01:
        y = Y(g)
        out.append(f'<line class="ch__grid" x1="{pad_l}" y1="{y:.1f}" x2="{pad_l+iw}" y2="{y:.1f}"/>')
        out.append(f'<text class="ch__tick" x="{pad_l+iw+8}" y="{y+4:.1f}">{fa(int(g))}٪</text>')
        g += step

    # برچسبِ نقاط روی محورِ افقی
    for i, p in enumerate(points):
        out.append(f'<text class="ch__tick ch__tick--x" x="{X(i):.1f}" y="{pad_t+ih+24}">{p}</text>')

    # هر سری: مسیر + نقطه‌ها + برچسبِ مستقیمِ آخرین نقطه
    for s in series:
        vals = s['values']
        d = ' '.join(
            ('M' if i == 0 else 'L') + f'{X(i):.1f} {Y(v):.1f}'
            for i, v in enumerate(vals)
        )
        out.append(f'<path class="ch__line" style="stroke:var(--{s["slot"]})" d="{d}"/>')

        for i, v in enumerate(vals):
            out.append(
                f'<circle class="ch__dot" style="fill:var(--{s["slot"]})" '
                f'cx="{X(i):.1f}" cy="{Y(v):.1f}" r="5">'
                f'<title>{s["name"]} — {points[i]}: {fa(v)}٪</title></circle>'
            )

        # برچسبِ مستقیم کنارِ آخرین نقطه (چپ‌ترین نقطه در RTL)
        lx, ly = X(len(vals) - 1), Y(vals[-1])
        out.append(
            f'<text class="ch__dlabel" style="fill:var(--{s["slot"]})" '
            f'x="{lx - 10:.1f}" y="{ly - 12:.1f}">{s["name"]} {fa(vals[-1])}٪</text>'
        )

    out.append('</svg>')
    return '\n'.join(out)


# ---------------------------------------------------------------------------
#  دامبل — پیش از / پس از برای یک شاخصِ آزمایشگاهی
# ---------------------------------------------------------------------------

def dumbbell(before, after, lo, hi, w=220, h=34):
    """یک ردیفِ کوچک: نقطه‌ی شروع، نقطه‌ی پایان، و نوارِ محدوده‌ی مرجع.

    مقیاس از خودِ داده ساخته می‌شود، نه از صفر — چون نسبت مهم نیست،
    جایِ عدد نسبت به محدوده‌ی مرجع مهم است.
    """
    vals = [v for v in (before, after, lo, hi) if v is not None]
    vmin, vmax = min(vals), max(vals)
    span = (vmax - vmin) or 1
    vmin -= span * 0.18
    vmax += span * 0.18
    span = vmax - vmin

    pad = 10
    iw = w - pad * 2

    def X(v):
        # RTL: کمترین مقدار سمتِ راست
        return pad + iw - iw * (v - vmin) / span

    y = h / 2
    out = [f'<svg viewBox="0 0 {w} {h}" class="db" aria-hidden="true">']

    # نوارِ محدوده‌ی مرجع
    rl = lo if lo is not None else vmin
    rh = hi if hi is not None else vmax
    x1, x2 = X(rh), X(rl)
    out.append(f'<rect class="db__ref" x="{x1:.1f}" y="{y-9:.0f}" width="{abs(x2-x1):.1f}" height="18" rx="4"/>')

    # خطِ بین دو نقطه
    out.append(f'<line class="db__bar" x1="{X(before):.1f}" y1="{y}" x2="{X(after):.1f}" y2="{y}"/>')
    out.append(f'<circle class="db__a" cx="{X(before):.1f}" cy="{y}" r="5"/>')
    out.append(f'<circle class="db__b" cx="{X(after):.1f}" cy="{y}" r="6"/>')
    out.append('</svg>')
    return '\n'.join(out)


# ---------------------------------------------------------------------------
#  پیکره‌ی بدن — آنالیز بخش‌به‌بخشِ عضله
# ---------------------------------------------------------------------------

#  مسیرِ هر بخش. عمداً ساده و تخت است: این یک شکلِ آناتومیک نیست،
#  یک نمودارِ پنج‌بخشی است که شکلِ آدم دارد تا سریع خوانده شود.
BODY_PARTS = {
    'head':  'M100 14a17 17 0 1 1 0 34 17 17 0 0 1 0-34Z',
    'trunk': 'M100 52c-15 0-27 5-30 10-2 4-3 14-3 26 0 16 2 30 5 44 1 6 2 10 4 13h48c2-3 3-7 4-13 3-14 5-28 5-44 0-12-1-22-3-26-3-5-15-10-30-10Z',
    'arm_r': 'M67 64c-7 3-11 8-13 16-3 12-6 30-7 44-1 7-1 13 0 17 1 4 7 5 9 1 2-4 3-10 4-17 2-14 5-30 7-40 1-6 2-12 0-21Z',
    'arm_l': 'M133 64c7 3 11 8 13 16 3 12 6 30 7 44 1 7 1 13 0 17-1 4-7 5-9 1-2-4-3-10-4-17-2-14-5-30-7-40-1-6-2-12 0-21Z',
    'leg_r': 'M96 145H76c-2 10-3 22-3 34 0 18 2 40 4 56 1 8 1 14 1 19 0 5 7 6 9 1 2-5 3-11 4-19 3-18 6-40 7-56 1-12 1-24-2-35Z',
    'leg_l': 'M104 145h20c2 10 3 22 3 34 0 18-2 40-4 56-1 8-1 14-1 19 0 5-7 6-9 1-2-5-3-11-4-19-3-18-6-40-7-56-1-12-1-24 2-35Z',
}


def body_figure(segments, which='after'):
    """پیکره، با هر بخش رنگ‌شده بر اساس جایش در محدوده‌ی نرمال.

    رنگ از یک رمپِ تک‌رنگ می‌آید (کم‌رنگ = پایین‌تر از نرمال، پررنگ =
    داخل یا بالای نرمال). رنگین‌کمان عمداً استفاده نشده.
    """
    by = {s['key']: s for s in segments}

    out = ['<svg viewBox="0 0 200 270" class="fig" role="img" '
           f'aria-label="پیکره‌ی بدن، توده‌ی عضلانی هر بخش {"پس از" if which == "after" else "پیش از"} پروتکل">']

    # سر، بدونِ داده
    out.append(f'<path class="fig__inert" d="{BODY_PARTS["head"]}"/>')

    for key, d in BODY_PARTS.items():
        if key == 'head':
            continue

        s = by.get(key)
        if not s:
            out.append(f'<path class="fig__inert" d="{d}"/>')
            continue

        v = s[which]
        lo, hi = s['norm']
        # نسبتِ جای عدد در محدوده‌ی نرمال، محدود به بازه‌ی ۰ تا ۱٫۲
        t = (v - lo) / (hi - lo) if hi > lo else 0
        t = max(0.0, min(1.2, t))
        lvl = 1 if t < 0.34 else (2 if t < 0.67 else (3 if t < 1.0 else 4))

        pct = round((v - s['before']) / s['before'] * 100, 1)
        sign = '+' if pct >= 0 else '−'
        out.append(
            f'<path class="fig__seg fig__seg--l{lvl}" d="{d}" tabindex="0">'
            f'<title>{s["name"]}: {fa(v)} کیلوگرم '
            f'({sign}{fa(abs(pct))}٪ نسبت به شروع) — '
            f'محدوده‌ی نرمال {fa(lo)} تا {fa(hi)}</title></path>'
        )

    out.append('</svg>')
    return '\n'.join(out)


# ---------------------------------------------------------------------------
#  میله‌ی پایبندی روزانه
# ---------------------------------------------------------------------------

def adherence_bar(pct, slot='series-3'):
    return (
        f'<span class="ad__track"><span class="ad__fill" '
        f'style="--v:{pct}%;background:var(--{slot})"></span></span>'
    )


# ---------------------------------------------------------------------------
#  سنجه‌ی HOMA-IR نسبت به مرزِ ۲
# ---------------------------------------------------------------------------

def meter(value, limit, vmax, w=520, h=56):
    """یک نسبت در برابرِ یک مرز. نه نمودارِ دایره‌ای، نه گیجِ سوزنی."""
    pad = 14
    iw = w - pad * 2

    def X(v):
        return pad + iw - iw * min(v, vmax) / vmax   # RTL

    out = [f'<svg viewBox="0 0 {w} {h}" class="mt" role="img" '
           f'aria-label="شاخص مقاومت انسولینی: از {fa(value[0])} به {fa(value[1])}، مرز نرمال {fa(limit)}">']

    y = 22
    out.append(f'<rect class="mt__track" x="{pad}" y="{y-9}" width="{iw}" height="18" rx="9"/>')

    # ناحیه‌ی نرمال (زیرِ مرز)
    xl = X(limit)
    out.append(f'<rect class="mt__ok" x="{xl:.1f}" y="{y-9}" width="{pad+iw-xl:.1f}" height="18" rx="9"/>')

    # مرز
    out.append(f'<line class="mt__limit" x1="{xl:.1f}" y1="{y-14}" x2="{xl:.1f}" y2="{y+14}"/>')
    out.append(f'<text class="mt__cap" x="{xl:.1f}" y="{y+30}">مرز نرمال {fa(limit)}</text>')

    # دو نقطه: شروع و پایان
    for v, cls, lab in ((value[0], 'mt__a', 'شروع'), (value[1], 'mt__b', 'پایان')):
        out.append(f'<circle class="{cls}" cx="{X(v):.1f}" cy="{y}" r="7"/>')
        out.append(f'<text class="mt__val" x="{X(v):.1f}" y="{y-16}">{fa(v)}</text>')

    out.append('</svg>')
    return '\n'.join(out)
