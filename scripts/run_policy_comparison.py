#!/usr/bin/env python3
"""Run same-seed Tax 5% vs Tax 15% virtual-world experiment."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dss.core.engine import build_minicity
from dss.experiments import ExperimentConfig, compare_policies


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=365)
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--seed-start", type=int, default=1)
    ap.add_argument("--out", type=Path, default=Path("artifacts/tax-policy"))
    args = ap.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    cfg = ExperimentConfig(days=args.days, seeds=args.seeds, seed_start=args.seed_start,
                           snapshot_interval=0, include_final_state=False)
    result = compare_policies(build_minicity,
                              {"Tax 5%": {"tax_rate": .05},
                               "Tax 15%": {"tax_rate": .15}}, cfg)
    result.to_json(args.out / "experiment_comparison.json")
    result.to_markdown(args.out / "experiment_comparison.md")
    result.to_csv(args.out / "experiment_comparison.csv")
    print(f"completed Tax 5% vs Tax 15% · {args.seeds} same-seed runs · {args.days} days")


if __name__ == "__main__":
    main()
