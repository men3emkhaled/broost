# -*- mode: python ; coding: utf-8 -*-
import os
import certifi
ROOT=os.path.dirname(os.path.abspath(SPEC))
a=Analysis(['app_cloud.py'],pathex=[ROOT],binaries=[],
    datas=[(os.path.join(ROOT,'build','pos_defaults.json'),'.'),(os.path.join(ROOT,'logo.ico'),'.'),(certifi.where(),'certifi')],
    hiddenimports=['PyQt6.QtPrintSupport','PyQt6.QtWebEngineWidgets','PyQt6.QtWebChannel','win32print'],
    hookspath=[],hooksconfig={},runtime_hooks=[],excludes=[],noarchive=False,optimize=0)
a.binaries=[e for e in a.binaries if not os.path.basename(e[0]).lower().startswith('api-ms-win-') and os.path.basename(e[0]).lower() not in {'icuuc.dll','icuin.dll','ucrtbase.dll'}]
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='BroostPOS',console=False,icon=os.path.join(ROOT,'logo.ico'))
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=True,name='BroostPOS')
