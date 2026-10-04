# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import sys
from PyInstaller.utils.hooks import collect_submodules

root = Path(SPECPATH)
src = root / "src"
sys.path.insert(0, str(src))
hiddenimports = collect_submodules("dss") + [
    "dss",
    "dss.core", "dss.core.models", "dss.core.rng", "dss.core.engine",
]

a = Analysis(
    [str(root / "app.py")],
    pathex=[str(src), str(root)],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="DigitalSocietySandbox",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)
