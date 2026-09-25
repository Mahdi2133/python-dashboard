#!/usr/bin/env python3
"""هر کلاسِ sm-* که در PHP یا JS استفاده شده را با CSS مطابقت می‌دهد."""
import re, glob, sys, os
B = os.path.join(os.path.dirname(__file__), '..', 'build', 'kadence-child')
used = {}
for pat in ('**/*.php', '**/*.js'):
    for f in glob.glob(os.path.join(B, pat), recursive=True):
        src = open(f, encoding='utf-8').read()
        for m in re.finditer(r'\bsm-[a-z0-9_]+(?:__[a-z0-9_]+)?(?:--[a-z0-9_]+)?', src):
            used.setdefault(m.group(0), set()).add(os.path.basename(f))
defined = set()
for f in glob.glob(os.path.join(B, 'assets/css/*.css')) + [os.path.join(B, 'style.css')]:
    css = open(f, encoding='utf-8').read()
    css = re.sub(r'/\*.*?\*/', '', css, flags=re.S)          # کامنت‌ها حساب نشوند
    defined |= set(re.findall(r'\.(sm-[a-z0-9_]+(?:__[a-z0-9_]+)?(?:--[a-z0-9_]+)?)', css))
missing = {k: v for k, v in used.items() if k not in defined}
print('کلاس‌های استفاده‌شده:', len(used))
print('کلاس‌های تعریف‌شده  :', len(defined))
if missing:
    print('\n⚠️ بدون استایل:')
    for k in sorted(missing):
        print(f'   {k:32} ← {", ".join(sorted(missing[k]))}')
sys.exit(1 if missing else 0)
