# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build spec.

Two rules govern this file:

1. Templates, static assets and the migrations folder are *bundled* — they are
   read-only program resources.
2. ``instance/wells.db`` is deliberately **NOT** bundled. The database must
   live next to the EXE (``dist/instance/wells.db``) so it survives replacing
   the EXE and can be opened directly in Navicat for SQLite. ``app/paths.py``
   resolves it from ``sys.executable``'s folder for exactly this reason.
"""
import os

block_cipher = None
project_dir = os.path.abspath(os.getcwd())

datas = [
    (os.path.join(project_dir, 'app', 'templates'), os.path.join('app', 'templates')),
    (os.path.join(project_dir, 'app', 'static'), os.path.join('app', 'static')),
]
migrations_dir = os.path.join(project_dir, 'migrations')
if os.path.isdir(migrations_dir):
    datas.append((migrations_dir, 'migrations'))

hiddenimports = [
    'waitress', 'sqlalchemy.dialects.sqlite', 'openpyxl', 'xlrd',
    'reportlab.pdfbase._fontdata_enc_winansi',
    'reportlab.pdfbase._fontdata_enc_macroman',
    'reportlab.pdfbase._fontdata_widths_helvetica',
    'arabic_reshaper', 'bidi', 'bidi.algorithm',
    'app.models', 'app.routes', 'app.services', 'app.reports',
    'app.analytics', 'app.analytics.catalogue', 'app.analytics.engine', 'app.analytics.formula',
    'app.analytics.access', 'app.analytics.lifecycle', 'app.analytics.exports',
    'app.analytics.docx_writer', 'app.analytics.jobs', 'app.analytics.templates',
    'openpyxl.chart', 'reportlab.graphics.charts.barcharts', 'reportlab.graphics.charts.linecharts',
    'reportlab.graphics.charts.piecharts',
    'email.mime.text',
]

# reportlab, arabic_reshaper and python-bidi load parts of themselves by name
# (font metrics, encodings, the reshaper's config file), which PyInstaller's
# import scan does not see: a build without them opens fine and then fails the
# first time a PDF is asked for. Bundle them whole.
import importlib.util  # noqa: E402

from PyInstaller.utils.hooks import collect_data_files, collect_submodules  # noqa: E402

for _pkg in ('reportlab', 'arabic_reshaper', 'bidi'):
    if importlib.util.find_spec(_pkg) is None:
        raise SystemExit(f"'{_pkg}' is not installed in the build environment; "
                         f"run: pip install -r requirements.txt")
    hiddenimports += collect_submodules(_pkg)
    datas += collect_data_files(_pkg)

a = Analysis(
    ['run.py'],
    pathex=[project_dir],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'numpy', 'pandas', 'PyQt5', 'PySide2',
              'IPython', 'notebook', 'pytest'],
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
    name='ElectropumpWorkshop',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    # A console window is required: it shows the database path, the local and
    # network URLs, and the firewall hint (requirement 34).
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(project_dir, 'electropump.ico'),
)
