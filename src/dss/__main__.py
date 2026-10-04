"""Command-line entry point for Digital Society Sandbox.

Examples::

    python -m dss --days 365 --seed 42 --out artifacts/minicity
    python -m dss --headless --days 365 --seeds 1-10 --out artifacts/batch
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .core.engine import build_minicity
from .experiments import ExperimentConfig, HeadlessRunner, build_annual_report


def _seeds(value: str) -> list[int]:
    out: list[int] = []
    for token in value.split(","):
        token = token.strip()
        if not token:
            continue
        if "-" in token:
            a, b = token.split("-", 1)
            out.extend(range(int(a), int(b) + 1))
        else:
            out.append(int(token))
    if not out:
        raise ValueError("no seeds")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Digital Society Sandbox deterministic ABM")
    ap.add_argument("--days", type=int, default=365)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--seeds", default=None, help="comma/range list for headless batch, e.g. 1-100")
    ap.add_argument("--out", type=Path, default=Path("artifacts/minicity"))
    ap.add_argument("--headless", action="store_true")
    args = ap.parse_args(argv)
    if args.days < 1:
        ap.error("--days must be positive")
    args.out.mkdir(parents=True, exist_ok=True)

    if args.seeds:
        seeds = _seeds(args.seeds)
        cfg = ExperimentConfig(days=args.days, seeds=len(seeds), seed_start=seeds[0],
                               snapshot_interval=0, include_final_state=False)
        runs = HeadlessRunner(build_minicity, cfg).run()
        # If the requested list is non-contiguous, run the missing seeds too;
        # the common range form remains fast and deterministic.
        if seeds != list(range(seeds[0], seeds[0] + len(seeds))):
            runs = [HeadlessRunner(build_minicity,
                                   ExperimentConfig(days=args.days, seeds=1,
                                                    seed_start=s, snapshot_interval=0,
                                                    include_final_state=False)).run()[0]
                    for s in seeds]
        report = build_annual_report(runs)
        report.to_json(args.out / "annual_report.json")
        report.to_markdown(args.out / "annual_report.md")
        print(json.dumps({"status": "ok", "seeds": seeds, "days": args.days,
                          "out": str(args.out), "disclaimer": report.disclaimer}, ensure_ascii=False))
        return 0

    sim = build_minicity(args.seed)
    sim.run(args.days)
    (args.out / "annual_report.json").write_text(
        json.dumps(sim.annual_report(), ensure_ascii=False, indent=2), encoding="utf-8")
    (args.out / "annual_report.md").write_text(
        "# Digital Society Sandbox Annual Report\n\n"
        "> Simulation results only; not a real-world prediction.\n\n"
        + "\n".join(f"- **{k}**: {v}" for k, v in sim.metrics().items()) + "\n",
        encoding="utf-8")
    print(json.dumps({"status": "ok", "seed": args.seed, "days": args.days,
                      "health_ok": sim.annual_report()["health_ok"], "out": str(args.out)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
