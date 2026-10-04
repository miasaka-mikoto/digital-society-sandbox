"""Command line demo: python -m dss.core.demo --days 365 --seed 7"""
from __future__ import annotations
import argparse
import json
from .engine import run_mini_city


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=365)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--save", default="mini_city_365.json")
    args = ap.parse_args()
    e = run_mini_city(args.seed, args.days)
    e.save(args.save)
    print(json.dumps(e.annual_report(), ensure_ascii=False, indent=2))
    print("health:", e.health_reports[-1].ok, e.health_reports[-1].issues[:3])


if __name__ == "__main__":
    main()
