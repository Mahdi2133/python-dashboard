#!/usr/bin/env python3
"""سلامتِ کلاس‌های sm-* را می‌سنجد.

دو چیز را می‌گیرد — هر دو بر پایه‌ی اشتباهاتی که واقعاً رخ داده‌اند:

  ۱. کلاسی که در قالب هست ولی هیچ CSSای ندارد.
     نسخه ۵٫۸: بلوکِ .sm-phase* را پاک کردم چون فکر کردم فقط صفحه‌ی
     اصلی از آن استفاده می‌کند. /smp/ و /about/ هم استفاده می‌کردند،
     و <ol> به شماره‌گذاریِ پیش‌فرضِ مرورگر برگشت — همان «۱ . ۱».

  ۲. کلاسی که در بیش از یک فایلِ CSS تعریف شده.
     نسخه ۵٫۸: .sm-hero__photo هم در home.css بود هم در pages.css.
     قاعده‌ی border-radius:50% دومی، عکسِ هیروی صفحه‌ی اصلی را به یک
     بیضیِ تمام‌صفحه تبدیل کرد.

⚠️ نکته‌ی مهم درباره‌ی استخراج:

   نسخه‌ی قبلیِ این فایل هر رشته‌ی sm-* را در کل سورس می‌گرفت. نتیجه
   چهل مورد هشدارِ الکی بود — idها (sm-result-badge)، تکه‌ی
   data-attributeها (data-sm-count → sm-count)، handleهای وردپرس
   (sm-forms) و متغیرهای CSS (--sm-i). با آن‌همه نویز، هشدارِ واقعی
   گم می‌شد و دقیقاً همین شد که دو باگِ بالا رد شدند.

   حالا فقط محتوای صفتِ class="…" خوانده می‌شود.
"""

import glob
import os
import re
import sys

# قالب در دو جا ممکن است باشد: مخزن (wordpress/themes/…) یا پوشه‌ی کارِ
# موقت (build/…). هرکدام که بود، همان را بردار.
_HERE = os.path.dirname(os.path.abspath(__file__))
for _cand in (os.path.join(_HERE, '..', 'wordpress', 'themes', 'kadence-child'),
              os.path.join(_HERE, '..', 'build', 'kadence-child')):
    if os.path.isdir(_cand):
        B = _cand
        break
else:
    sys.exit('❌ قالب kadence-child پیدا نشد.')

TOKEN = r'sm-[a-z0-9]+(?:[_-][a-z0-9]+)*'


def classes_in_templates():
    """هر کلاس → مجموعه‌ی فایل‌هایی که استفاده‌اش کرده‌اند.

    فقط از داخلِ class="…" و classList/className خوانده می‌شود.
    """
    used = {}
    prefixes = {}          # کلاس‌هایی که با PHP ساخته می‌شوند

    sources = []
    for pat in ('**/*.php', '**/*.js'):
        sources += glob.glob(os.path.join(B, pat), recursive=True)

    for f in sources:
        name = os.path.basename(f)
        src = open(f, encoding='utf-8').read()

        chunks = []
        chunks += re.findall(r'class=(["\'])(.*?)\1', src, re.S)
        chunks = [c[1] for c in chunks]
        chunks += re.findall(r'classList\.(?:add|remove|toggle)\(\s*[\'"]([^\'"]+)', src)
        chunks += re.findall(r'className\s*=\s*[\'"]([^\'"]+)', src)

        for chunk in chunks:
            # تکه‌های PHP را با فاصله جایگزین می‌کنیم تا نامِ کلاسِ
            # کناری‌شان سالم بماند، ولی خودشان شمرده نشوند.
            plain = re.sub(r'<\?php.*?\?>', ' § ', chunk, flags=re.S)

            for m in re.finditer(TOKEN, plain):
                tok = m.group(0)
                tail = plain[m.end():m.end() + 3]

                # 'sm-phead--' . $mode  ⇒ نامِ ناقص، پیشوند حساب می‌شود
                if tok.endswith('-') or tail.lstrip().startswith('§'):
                    prefixes.setdefault(tok.rstrip('-'), set()).add(name)
                else:
                    used.setdefault(tok, set()).add(name)

    return used, prefixes


def classes_in_css():
    """هر کلاس → مجموعه‌ی فایل‌های CSSای که تعریفش کرده‌اند."""
    out = {}
    files = sorted(glob.glob(os.path.join(B, 'assets/css/*.css')))
    files.append(os.path.join(B, 'style.css'))

    for f in files:
        css = open(f, encoding='utf-8').read()
        css = re.sub(r'/\*.*?\*/', '', css, flags=re.S)   # کامنت‌ها حساب نشوند
        for name in set(re.findall(r'\.(' + TOKEN + r')', css)):
            out.setdefault(name, set()).add(os.path.basename(f))

    # بعضی صفحه‌های پیشخوان CSSشان را درون خودِ PHP دارند (مثلاً
    # جعبه‌ی مدیریتِ inc/blog.php). آن‌ها هم «تعریف‌شده» حساب می‌شوند.
    for f in glob.glob(os.path.join(B, '**/*.php'), recursive=True):
        src = open(f, encoding='utf-8').read()
        for style in re.findall(r'<style[^>]*>(.*?)</style>', src, re.S):
            for name in set(re.findall(r'\.(' + TOKEN + r')', style)):
                out.setdefault(name, set()).add(os.path.basename(f))

    return out



def bad_css_math(paths):
    """اعلان‌هایی که به‌خاطرِ نبودِ فاصله دورِ + یا - بی‌صدا دور ریخته می‌شوند.

    در CSS، عملگرهای + و - داخلِ calc()/clamp()/min()/max() حتماً باید
    از دو طرف فاصله داشته باشند. `clamp(2rem,1rem+4vw,4rem)` نامعتبر است
    و مرورگر کلِ آن اعلان را دور می‌اندازد — بدون هیچ خطایی.

    چرا اینجاست: در پیشنهادِ طراحی ۲۵ اعلان همین‌طور از بین رفته بودند.
    صفحه باز می‌شد، تصویری خراب نبود، JS خطا نمی‌داد؛ فقط همه‌ی اندازه‌های
    تیتر روی پیش‌فرضِ مرورگر مانده بود. هیچ بررسیِ دیگری این را نمی‌گیرد.
    (× و ÷ به فاصله نیاز ندارند.)
    """
    hits = []
    for f in paths:
        try:
            src = open(f, encoding='utf-8').read()
        except (OSError, UnicodeDecodeError):
            continue
        for i, line in enumerate(src.splitlines(), 1):
            for m in re.finditer(r'(?:clamp|calc|min|max)\([^()]*[0-9a-z%)][+-][.0-9]', line):
                hits.append((os.path.basename(f), i, m.group(0)))
    return hits

def main():
    used, prefixes = classes_in_templates()
    defined = classes_in_css()

    def has_css(tok):
        if tok in defined:
            return True
        # کلاسی که فقط به‌عنوان پیشوندِ --modifier تعریف شده
        return any(d.startswith(tok + '--') or d.startswith(tok + '__') for d in defined)

    missing = {k: v for k, v in used.items() if not has_css(k)}

    # پیشوندهای ساخته‌شده با PHP: کافی است دست‌کم یک نسخه‌شان CSS داشته باشد
    for pre, who in prefixes.items():
        if not any(d.startswith(pre) for d in defined):
            missing.setdefault(pre + '…', set()).update(who)

    clash = {k: v for k, v in defined.items() if len(v) > 1}

    css_files = sorted(glob.glob(os.path.join(B, 'assets/css/*.css')))
    css_files.append(os.path.join(B, 'style.css'))
    css_files += glob.glob(os.path.join(B, '**/*.php'), recursive=True)
    math = bad_css_math(css_files)

    print('کلاس‌های به‌کاررفته در قالب:', len(used) + len(prefixes))
    print('کلاس‌های تعریف‌شده در CSS :', len(defined))

    bad = False

    if missing:
        bad = True
        print('\n❌ در قالب هست ولی CSS ندارد:')
        for k in sorted(missing):
            print(f'   {k:34} ← {", ".join(sorted(missing[k]))}')

    if math:
        bad = True
        print('\n❌ عملگرِ بی‌فاصله در تابعِ ریاضیِ CSS — مرورگر این اعلان‌ها را دور می‌اندازد:')
        for f, line, snip in math:
            print(f'   {f}:{line}  {snip}…')
        print('   چاره: دورِ + و - فاصله بگذارید → clamp(2rem, 1rem + 4vw, 4rem)')

    if clash:
        # ⚠️ عمداً خطا نیست.
        #
        # کلاس‌های پایه مثل .sm-btn و .sm-wrap و .sm-section طبیعتاً
        # در چند فایل می‌آیند: یک قاعده‌ی پایه و چند بازنویسیِ
        # صفحه‌محور. این فهرست برای «نگاه کن» است، نه «خراب است».
        #
        # آن چیزی که واقعاً دو باگِ نسخه ۵٫۸ را می‌گرفت، مقایسه‌ی
        # تصویریِ صفحه‌هاست: tools/visual-diff.py
        print('\n⚠️ در بیش از یک فایل CSS تعریف شده — ارزش یک نگاه را دارد:')
        for k in sorted(clash):
            print(f'   {k:34} CSS: {", ".join(sorted(clash[k]))}')
            print(f'   {"":34} قالب: {", ".join(sorted(used.get(k, {"—"})))}')

    if not bad:
        print('\n✓ هیچ کلاسِ بی‌استایل و هیچ تعریفِ تکراری‌ای نیست.')

    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
