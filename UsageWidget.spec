# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

font_datas = []
for font_dir in (Path("fonts"), Path("assets") / "fonts"):
    if font_dir.exists():
        for pattern in ("*.ttf", "*.otf", "*.ttc"):
            font_datas.extend((str(path), str(font_dir)) for path in font_dir.glob(pattern))

if not font_datas:
    raise SystemExit("No bundled UI fonts found. Put a CJK-capable .ttf/.otf/.ttc file in fonts/ before building.")


a = Analysis(
    ['run.py'],
    pathex=[],
    binaries=[],
    datas=font_datas,
    hiddenimports=[],
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
    [],
    exclude_binaries=True,
    name='UsageWidget',
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
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='UsageWidget',
)
