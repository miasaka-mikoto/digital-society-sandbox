#!/usr/bin/env python3
"""Short, non-destructive smoke check for a fresh checkout."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    out = root / "artifacts" / "qa_smoke"
    cmd = [sys.executable, str(root / "scripts" / "run_demo.py"),
           "--days", str(args.days), "--seed", str(args.seed), "--headless", "--out", str(out)]
    proc = subprocess.run(cmd, cwd=root, text=True, capture_output=True)
    if proc.returncode:
        print(proc.stdout, end="")
        print(proc.stderr, end="", file=sys.stderr)
        print("QA_SMOKE_FAIL: demo did not complete", file=sys.stderr)
        return proc.returncode
    report = out / "annual_report.json"
    if not report.exists():
        print("QA_SMOKE_FAIL: annual_report.json missing", file=sys.stderr)
        return 2
    try:
        json.loads(report.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"QA_SMOKE_FAIL: invalid JSON: {exc}", file=sys.stderr)
        return 3
    print(f"QA_SMOKE_PASS days={args.days} seed={args.seed} report={report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

