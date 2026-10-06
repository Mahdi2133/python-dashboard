#!/usr/bin/env python3
"""اسکرین‌شاتِ صفحه‌ها را با نسخه‌ی قبلی مقایسه می‌کند.

چرا این ابزار هست
-----------------
در نسخه ۵٫۸ دو چیز شکست و هیچ‌کدام را لینت یا بررسیِ CSS نگرفت:

  • عکسِ هیروی صفحه‌ی اصلی به یک بیضیِ تمام‌صفحه تبدیل شد، چون
    کلاسی که برای صفحه‌ی شورا نوشتم با کلاسِ هیرو هم‌نام بود.
  • سه کارتِ فاز در /smp/ و /about/ بی‌استایل شدند، چون CSSشان را
    پاک کردم به خیالِ اینکه فقط صفحه‌ی اصلی استفاده می‌کند.

هر دو را فقط «نگاه کردن به صفحه» می‌گرفت. این ابزار همان نگاه را
خودکار می‌کند: قبل از هر تغییر یک بار baseline بگیرید، بعد از
تغییر مقایسه کنید.

کاربرد
------
    python3 tools/visual-diff.py save      عکس‌های فعلی را مبنا کن
    python3 tools/visual-diff.py check     با مبنا مقایسه کن

«check» وقتی خطا می‌دهد که ارتفاعِ صفحه یا پیکسل‌هایش بیش از آستانه
فرق کرده باشند. اگر تغییر عمدی بوده، دوباره save کنید.
"""

import os
import shutil
import sys

from PIL import Image, ImageChops

HERE = os.path.dirname(__file__)
SHOTS = os.path.join(HERE, '..', 'preview', 'shots')
BASE = os.path.join(HERE, '..', 'preview', 'baseline')
DIFFS = os.path.join(HERE, '..', 'preview', 'diffs')

#  چقدر تغییر «مهم» است.
#
#  ⚠️ درس گرفته‌شده: مقایسه‌ی میانگینِ کلِ صفحه کافی نیست.
#
#     وقتی عکسِ هیرو بیضی شد، فقط گوشه‌های همان عکس عوض شدند — چند
#     هزار پیکسل در صفحه‌ای شش‌هزار پیکسلی. میانگینِ کلِ صفحه زیر
#     آستانه ماند و ابزار چیزی نگفت.
#
#     پس صفحه را به نوارهای افقی می‌بریم و بدترین نوار را می‌سنجیم.
#     یک خرابیِ موضعی، در نوارِ خودش خیلی بالای آستانه می‌افتد.
H_TOL = 0.04     # ۴٪ تغییرِ ارتفاعِ کلِ صفحه
PX_TOL = 0.02    # ۲٪ پیکسلِ متفاوت در کلِ صفحه
BAND = 240       # ارتفاعِ هر نوار، بر حسب پیکسل
BAND_TOL = 0.06  # ۶٪ پیکسلِ متفاوت در بدترین نوار


def save():
    if not os.path.isdir(SHOTS):
        print('❌ پوشه‌ی shots نیست. اول preview/shot.js را اجرا کنید.')
        return 1

    shutil.rmtree(BASE, ignore_errors=True)
    shutil.copytree(SHOTS, BASE)
    n = len([f for f in os.listdir(BASE) if f.endswith('.png')])
    print(f'✓ {n} تصویر به‌عنوان مبنا ذخیره شد.')
    return 0


def check():
    if not os.path.isdir(BASE):
        print('ℹ️ هنوز مبنایی ذخیره نشده. اول «save» را بزنید.')
        return 0

    os.makedirs(DIFFS, exist_ok=True)
    changed, missing, new = [], [], []

    base_files = {f for f in os.listdir(BASE) if f.endswith('.png')}
    now_files = {f for f in os.listdir(SHOTS) if f.endswith('.png')}

    missing = sorted(base_files - now_files)
    new = sorted(now_files - base_files)

    for name in sorted(base_files & now_files):
        a = Image.open(os.path.join(BASE, name)).convert('RGB')
        b = Image.open(os.path.join(SHOTS, name)).convert('RGB')

        dh = abs(a.height - b.height) / max(a.height, b.height)

        if a.size != b.size:
            # برای مقایسه‌ی پیکسلی، هر دو را به کوچک‌ترین اندازه می‌بریم.
            h = min(a.height, b.height)
            w = min(a.width, b.width)
            a2, b2 = a.crop((0, 0, w, h)), b.crop((0, 0, w, h))
        else:
            a2, b2 = a, b

        diff = ImageChops.difference(a2, b2).convert('L')
        mask = diff.point(lambda p: 255 if p > 24 else 0)

        total = mask.width * mask.height
        hits = sum(mask.histogram()[255:])
        dp = hits / total if total else 0

        # بدترین نوارِ افقی
        worst, worst_y = 0.0, 0
        for y in range(0, mask.height, BAND):
            band = mask.crop((0, y, mask.width, min(y + BAND, mask.height)))
            area = band.width * band.height
            if not area:
                continue
            frac = sum(band.histogram()[255:]) / area
            if frac > worst:
                worst, worst_y = frac, y

        if dh > H_TOL or dp > PX_TOL or worst > BAND_TOL:
            changed.append((name, dh, dp, worst, worst_y))
            mask.save(os.path.join(DIFFS, name))

    if missing:
        print('⚠️ در مبنا بود ولی حالا نیست:', ', '.join(missing))

    if new:
        print('ℹ️ تازه (در مبنا نبود):', ', '.join(new))

    if changed:
        print('\n❌ تغییرِ معنادار:')
        for name, dh, dp, worst, wy in changed:
            print(f'   {name:22} ارتفاع {dh*100:5.1f}٪   پیکسل {dp*100:5.1f}٪'
                  f'   بدترین نوار {worst*100:5.1f}٪ (از y={wy})')
        print(f'\n   تصویرِ تفاوت‌ها: preview/diffs/')
        print('   اگر تغییر عمدی بوده، «save» را دوباره بزنید.')
        return 1

    print(f'✓ {len(base_files & now_files)} صفحه بدون تغییرِ معنادار.')
    return 0


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'check'
    sys.exit(save() if cmd == 'save' else check())
