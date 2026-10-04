#!/usr/bin/env python3
"""Assemble a reproducible Digital Society Sandbox release bundle."""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "artifacts" / "DigitalSocietySandbox_v0.1.0"
ARCHIVE = ROOT / "artifacts" / "DigitalSocietySandbox_v0.1.0.zip"


def copy_tree(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    shutil.copytree(src, dst, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"))


def main() -> None:
    if RELEASE.exists():
        shutil.rmtree(RELEASE)
    RELEASE.mkdir(parents=True)
    # Source and build recipes.
    for name in ("src", "scripts", "tests"):
        copy_tree(ROOT / name, RELEASE / name)
    for name in ("README.md", "CHANGELOG.md", "LICENSE", "pyproject.toml", "requirements.txt",
                 "DigitalSocietySandbox.spec", "DigitalSocietySandboxCLI.spec",
                 "build_windows.ps1", "app.py", "ui_entry.py"):
        src = ROOT / name
        if src.exists(): shutil.copy2(src, RELEASE / name)

    # Keep the verified, queryable demo artifacts without duplicating the raw
    # JSONL ledger that is already represented in SQLite.
    for name in ("minicity_365_database", "validation_100_seeds", "tax-policy"):
        copy_tree(ROOT / "artifacts" / name, RELEASE / "artifacts" / name)
    test_report = ROOT / "artifacts" / "test_report.json"
    if test_report.exists():
        shutil.copy2(test_report, RELEASE / "artifacts" / "test_report.json")
    demo = RELEASE / "artifacts" / "final_demo"
    demo.mkdir(parents=True, exist_ok=True)
    for name in ("annual_report.json", "annual_report.md", "minicity_snapshot.png"):
        src = ROOT / "artifacts" / "final_demo" / name
        if src.exists(): shutil.copy2(src, demo / name)

    # Linux verification binaries are labelled explicitly; a true Windows
    # PE executable is produced by build_windows.ps1 on Windows.
    dist = RELEASE / "dist"
    dist.mkdir(parents=True, exist_ok=True)
    for source, target in ((ROOT / "dist" / "DigitalSocietySandbox", "DigitalSocietySandbox_linux"),
                           (ROOT / "dist" / "DigitalSocietySandboxCLI", "DigitalSocietySandboxCLI_linux")):
        if source.exists(): shutil.copy2(source, dist / target)

    manifest = {"project": "Digital Society Sandbox", "version": "0.1.0",
                "simulation_only": True, "files": []}
    for path in sorted(RELEASE.rglob("*")):
        if path.is_file():
            data = path.read_bytes()
            manifest["files"].append({"path": str(path.relative_to(RELEASE)).replace("\\", "/"),
                                       "bytes": len(data),
                                       "sha256": hashlib.sha256(data).hexdigest()})
    (RELEASE / "MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    if ARCHIVE.exists():
        ARCHIVE.unlink()
    with ZipFile(ARCHIVE, "w", compression=ZIP_DEFLATED, compresslevel=6) as z:
        for path in sorted(RELEASE.rglob("*")):
            if path.is_file():
                z.write(path, path.relative_to(RELEASE.parent))
    print(json.dumps({"release_dir": str(RELEASE), "archive": str(ARCHIVE),
                      "archive_bytes": ARCHIVE.stat().st_size,
                      "file_count": len(manifest["files"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
