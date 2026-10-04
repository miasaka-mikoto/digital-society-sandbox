#!/usr/bin/env python3
"""Run MiniCity (or a compatible factory) headlessly and emit annual artifacts.

The import is intentionally late: projects can provide ``dss.minicity.build_minicity``
without coupling the reusable experiment package to the UI.
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from dss.experiments import ExperimentConfig, HeadlessRunner, build_annual_report
from dss.experiments.persistence import SnapshotStore


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=365)
    ap.add_argument("--seeds", type=int, default=1)
    ap.add_argument("--seed-start", type=int, default=0)
    ap.add_argument("--snapshot-interval", type=int, default=None, help="days between snapshots; default 7 for one seed, disabled for sweeps")
    ap.add_argument("--out", default="artifacts/experiments")
    args = ap.parse_args()
    try:
        from dss.core.engine import build_minicity
    except ImportError as e:
        raise SystemExit("dss.core.engine.build_minicity is unavailable") from e
    interval = args.snapshot_interval if args.snapshot_interval is not None else (7 if args.seeds == 1 else 0)
    # Keep weekly snapshots compact (day + metrics) so a year's transaction
    # ledger is not duplicated into every snapshot row.  The final state is
    # retained for a single-seed run and can be restored with SimulationEngine.load.
    cfg = ExperimentConfig(days=args.days, seeds=args.seeds, seed_start=args.seed_start,
                           snapshot_interval=interval, output_dir=args.out,
                           include_final_state=(args.seeds == 1),
                           store_full_snapshots=False)
    runs = HeadlessRunner(build_minicity, cfg).run()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    # Keep a queryable SQLite history, including every configured snapshot and
    # each run's final state.  This is intentionally independent of the map UI.
    with SnapshotStore(out / "simulation.sqlite") as store:
        store.set_metadata("days", args.days); store.set_metadata("seeds", args.seeds)
        for run in runs:
            rid = f"seed-{run.seed}"
            for snap in run.snapshots:
                compact = {"day": snap["day"], "metrics": snap.get("metrics", {}),
                           "simulation_only": True}
                store.save(rid, run.seed, snap["day"], compact, snap.get("metrics", {}))
            store.save(rid, run.seed, run.days, run.final_state, run.metrics)
    report = build_annual_report(runs)
    report.to_json(out / "annual_report.json")
    report.to_markdown(out / "annual_report.md")
    print(f"completed {len(runs)} seed(s) × {args.days} days; report={out/'annual_report.md'}")


if __name__ == "__main__": main()
