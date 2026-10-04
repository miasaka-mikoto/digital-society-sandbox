#!/usr/bin/env python3
"""Thin batch wrapper around the demo entry point.

The experiment runner is deliberately explicit about seeds. Each seed gets a
separate output folder, making comparison and failed-run diagnosis easy.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def parse_seeds(value: str):
    result = []
    for token in value.split(","):
        token = token.strip()
        if not token:
            continue
        if "-" in token:
            a, b = token.split("-", 1)
            result.extend(range(int(a), int(b) + 1))
        else:
            result.append(int(token))
    if not result:
        raise ValueError("no seeds")
    return result


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Run deterministic DSS simulations for multiple seeds")
    p.add_argument("--seeds", default="1-5")
    p.add_argument("--days", type=int, default=365)
    p.add_argument("--out", type=Path, default=Path("artifacts/batch"))
    p.add_argument("--headless", action="store_true")
    args = p.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    args.out.mkdir(parents=True, exist_ok=True)
    for seed in parse_seeds(args.seeds):
        out = args.out / f"seed_{seed:04d}"
        cmd = [sys.executable, str(root / "scripts" / "run_demo.py"),
               "--days", str(args.days), "--seed", str(seed), "--out", str(out)]
        if args.headless:
            cmd.append("--headless")
        print("RUN", " ".join(map(str, cmd)), flush=True)
        completed = subprocess.run(cmd, cwd=root)
        if completed.returncode:
            return completed.returncode
    print(f"BATCH_PASS seeds={args.seeds} days={args.days} out={args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

