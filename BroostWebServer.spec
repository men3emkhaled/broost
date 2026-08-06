# -*- mode: python ; coding: utf-8 -*-
import os


ROOT = os.path.dirname(os.path.abspath(SPEC))

static_files = ["styles.css", "index.html", "customer.js", "admin.html", "admin.js"]
image_files = [
    "hero-food-v1.webp",
    "category-chicken-v1.webp",
    "category-strips-v1.webp",
    "category-burger-v1.webp",
    "category-beef-burger-v1.webp",
    "category-rice-v1.webp",
    "category-sides-v1.webp",
]
datas_list = [
    (os.path.join(ROOT, "webapp", "static", name), "webapp/static")
    for name in static_files
]
datas_list.extend(
    (os.path.join(ROOT, "webapp", "static", "images", name), "webapp/static/images")
    for name in image_files
)
datas_list.append((os.path.join(ROOT, "logo.ico"), "."))

a = Analysis(
    ["run_web.py"],
    pathex=[ROOT],
    binaries=[],
    datas=datas_list,
    hiddenimports=[
        "uvicorn.logging",
        "uvicorn.loops.auto",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan.on",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="BroostWebServer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(ROOT, "logo.ico"),
)
