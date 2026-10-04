#!/usr/bin/env python3
"""Run the test suite and emit a small machine-readable QA report."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "test_report.json"


def main() -> int:
    started = time.perf_counter()
    proc = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=ROOT,
                          text=True, capture_output=True)
    report = {"project": "Digital Society Sandbox", "simulation_only": True,
              "passed": proc.returncode == 0,
              "returncode": proc.returncode,
              "elapsed_seconds": round(time.perf_counter() - started, 3),
              "stdout": proc.stdout, "stderr": proc.stderr,
              "disclaimer": "Simulation tests do not constitute real-world validation."}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "path": str(OUT)}))
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
