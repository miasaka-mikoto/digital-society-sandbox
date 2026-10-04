#!/usr/bin/env python3
"""Parallel long-run validation for the canonical MiniCity scenario.

The worker returns only summary metrics and health diagnostics; full ledgers
remain available from a single-seed run/SQLite snapshot, so a 100-seed sweep
does not retain hundreds of megabytes of duplicate transaction history.
"""
from __future__ import annotations

import argparse
import concurrent.futures as futures
import csv
import hashlib
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def run_one(args):
    seed, days = args
    from dss.core.engine import build_minicity
    sim = build_minicity(seed)
    sim.run(days, snapshot_interval=0)
    report = sim.annual_report()
    digest = hashlib.sha256(json.dumps(sim.metrics(), sort_keys=True).encode()).hexdigest()[:16]
    return {"seed": seed, "days": days, "health_ok": report["health_ok"],
            "health_issue_counts": report["health_issue_counts"],
            "transaction_count": report["transaction_count"],
            "metrics": report["metrics"], "digest": digest}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=365)
    ap.add_argument("--seeds", type=int, default=100)
    ap.add_argument("--seed-start", type=int, default=0)
    ap.add_argument("--workers", type=int, default=max(1, min(8, os.cpu_count() or 1)))
    ap.add_argument("--out", type=Path, default=Path("artifacts/validation_100_seeds"))
    args = ap.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    jobs = [(args.seed_start + i, args.days) for i in range(args.seeds)]
    with futures.ProcessPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(run_one, jobs))
    rows.sort(key=lambda x: x["seed"])
    issue_counts = {}
    for row in rows:
        for k, v in row["health_issue_counts"].items():
            issue_counts[k] = issue_counts.get(k, 0) + v
    numeric_keys = sorted({k for r in rows for k, v in r["metrics"].items() if isinstance(v, (int, float))})
    aggregate = {k: sum(float(r["metrics"].get(k, 0)) for r in rows) / max(1, len(rows)) for k in numeric_keys}
    summary = {"title": "Digital Society Sandbox 100-Seed Validation",
               "simulation_only": True,
               "warning": "Simulation results only; not a real-world policy prediction.",
               "days": args.days, "seed_count": args.seeds, "seed_start": args.seed_start,
               "workers": args.workers, "elapsed_seconds": round(time.perf_counter() - started, 3),
               "all_health_ok": all(r["health_ok"] for r in rows),
               "health_issue_counts": issue_counts, "aggregate_metrics": aggregate,
               "runs": rows}
    (args.out / "validation.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    with (args.out / "metrics.csv").open("w", newline="", encoding="utf-8") as f:
        keys = ["seed", "health_ok", *numeric_keys]
        writer = csv.writer(f); writer.writerow(keys)
        for r in rows: writer.writerow([r["seed"], r["health_ok"], *[r["metrics"].get(k, "") for k in numeric_keys]])
    md = ["# Digital Society Sandbox — 100-Seed Validation", "",
          "> Simulation results only; not a real-world policy prediction.", "",
          f"- Days per seed: {args.days}", f"- Seeds: {args.seeds}",
          f"- Elapsed seconds: {summary['elapsed_seconds']}", f"- All health checks: {summary['all_health_ok']}", "",
          "## Aggregate metrics", "", "| Metric | Mean |", "|---|---:|"]
    md += [f"| {k} | {v:.4f} |" for k, v in aggregate.items()]
    md += ["", "## Health issues", "", "| Code | Count |", "|---|---:|"]
    md += [f"| {k} | {v} |" for k, v in sorted(issue_counts.items())] or ["| none | 0 |"]
    (args.out / "validation.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(json.dumps({"status": "ok", "all_health_ok": summary["all_health_ok"],
                      "elapsed_seconds": summary["elapsed_seconds"], "out": str(args.out)}))


if __name__ == "__main__":
    main()
