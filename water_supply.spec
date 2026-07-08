# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

# همه‌ی فایل‌های جانبی که اپ لازم دارد (قالب‌ها، استاتیک، دیتابیس، migrations)
datas = [
    ('app/templates', 'app/templates'),
    ('app/static', 'app/static'),
    ('instance', 'instance'),
    ('migrations', 'migrations'),
]

# ماژول‌هایی که PyInstaller ممکن است خودکار پیدا نکند
hiddenimports = []
hiddenimports += collect_submodules('app')
hiddenimports += [
    'flask_sqlalchemy', 'flask_migrate', 'flask_login', 'flask_wtf',
    'wtforms', 'jdatetime', 'openpyxl', 'sqlalchemy',
    'email_validator', 'waitress', 'pyproj',
]

a = Analysis(
    ['launcher.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='WaterSupply',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.ico',
)