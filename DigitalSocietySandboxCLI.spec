# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import sys
from PyInstaller.utils.hooks import collect_submodules

root = Path(SPECPATH)
src = root / "src"
sys.path.insert(0, str(src))
a = Analysis(
    [str(root / "scripts" / "run_demo.py")],
    pathex=[str(src), str(root)], binaries=[], datas=[],
    hiddenimports=collect_submodules("dss") + ["dss", "dss.core.engine"], hookspath=[],
    hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [],
          name="DigitalSocietySandboxCLI", debug=False,
          bootloader_ignore_signals=False, strip=False, upx=False, console=True)
