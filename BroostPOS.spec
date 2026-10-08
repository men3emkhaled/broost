# -*- mode: python ; coding: utf-8 -*-
import os

# Root project directory
ROOT = os.path.dirname(os.path.abspath(SPEC))

# Assets to bundle inside the exe package (target is relative path inside dist/BroostPOS/)
datas_list = []
for asset in ['logo.ico']:
    src = os.path.join(ROOT, asset)
    if os.path.exists(src):
        datas_list.append((src, '.'))


a = Analysis(
    ['app.py'],
    pathex=[ROOT],
    binaries=[],
    datas=datas_list,
    hiddenimports=[
        'PyQt6.QtPrintSupport',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PyQt6.QtWebEngineWidgets', 'PyQt6.QtWebEngineCore'],
    noarchive=False,
    optimize=0,
)

# Windows supplies these DLLs. A developer's PATH may contain incompatible
# copies (especially ICU with version-suffixed exports), which break Qt startup.
a.binaries = [
    entry for entry in a.binaries
    if not os.path.basename(entry[0]).lower().startswith('api-ms-win-')
    and os.path.basename(entry[0]).lower() not in {'ucrtbase.dll', 'icuuc.dll', 'icuin.dll'}
]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='BroostPOS',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(ROOT, 'logo.ico'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='BroostPOS',
)
