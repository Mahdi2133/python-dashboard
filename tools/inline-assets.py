#!/usr/bin/env python3
"""یک HTML خودبسنده می‌سازد: عکس‌ها و فونت‌ها را به data: تبدیل می‌کند.

چرا: کارفرما باید بتواند فایل را هر جا باز کند — روی لپ‌تاپ، روی گوشی،
یا به‌صورت پیوستِ ایمیل — بدون اینکه پوشه‌ی img/ و fonts/ همراهش باشد.
"""
import base64, io, os, re, sys

SRC = sys.argv[1]
OUT = sys.argv[2]
ROOT = os.path.dirname(os.path.abspath(SRC))

MIME = {'.webp': 'image/webp', '.png': 'image/png', '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg', '.svg': 'image/svg+xml', '.woff2': 'font/woff2'}

s = io.open(SRC, encoding='utf-8').read()
seen, missing, total = {}, [], 0

def embed(path):
    """مسیرِ نسبی → data: URI. هر فایل فقط یک بار خوانده می‌شود."""
    global total
    if path in seen:
        return seen[path]
    full = os.path.normpath(os.path.join(ROOT, path))
    if not os.path.isfile(full):
        missing.append(path)
        return None
    ext = os.path.splitext(full)[1].lower()
    mime = MIME.get(ext)
    if not mime:
        missing.append(path + ' (نوعِ ناشناخته)')
        return None
    raw = open(full, 'rb').read()
    total += len(raw)
    uri = 'data:%s;base64,%s' % (mime, base64.b64encode(raw).decode('ascii'))
    seen[path] = uri
    return uri

# هر مسیرِ نسبی که پسوندش را می‌شناسیم — چه img/… چه ../themes/…
#
# ⚠️ نسخه‌ی اول فقط img/ و fonts/ را می‌گرفت. وقتی مسیرها به
#    ../themes/kadence-child/assets/… تغییر کردند، هیچ‌چیز match نشد و
#    ابزار بی‌صدا فایلی ساخت که همه‌ی عکس‌هایش شکسته بود. حالا بر پایه‌ی
#    پسوند کار می‌کند و اگر چیزی جا بماند، در پایان اعلام می‌شود.
EXT = '|'.join(e.lstrip('.') for e in MIME)
REL = r'(?!https?:|data:|//|/)([^"\')>]+\.(?:' + EXT + r'))'

def sub_attr(m):
    pre, path, post = m.group(1), m.group(2), m.group(3)
    uri = embed(path)
    return pre + (uri or path) + post

s = re.sub(r'((?:src|href)=")' + REL + r'(")', sub_attr, s)
s = re.sub(r'(url\(\s*[\'"]?)' + REL + r'([\'"]?\s*\))', sub_attr, s)

# srcset نداریم، ولی اگر بعداً اضافه شد، صدا بزند.
if 'srcset=' in s:
    print('⚠️ srcset هست و این ابزار پوشش‌اش نمی‌دهد.')

io.open(OUT, 'w', encoding='utf-8').write(s)

left = re.findall(r'(?:src|href)="' + REL + r'"', s)
print(f'✓ {len(seen)} فایل درون‌ریزی شد ({total/1048576:.2f}MB خام)')
print(f'  حجمِ خروجی: {os.path.getsize(OUT)/1048576:.2f}MB')
if not seen:
    print('✗ هیچ داراییِ نسبی‌ای پیدا نشد — الگوی مسیرها را بررسی کنید.')
    sys.exit(1)
if missing:
    print('✗ پیدا نشد:', ', '.join(missing))
if left:
    print('✗ هنوز بیرونی:', ', '.join(set(left)))
sys.exit(1 if (missing or left) else 0)
