#!/usr/bin/env python3
"""Run the deterministic MiniCity demo and write inspectable artifacts.

The script intentionally keeps a small compatibility layer while the engine is
evolving.  It accepts the common ``build_minicity``/``run`` APIs and reports a
clear error instead of silently claiming that a simulation completed.
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if SRC.exists() and str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _json_default(value: Any):
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if hasattr(value, "__dict__"):
        return value.__dict__
    raise TypeError(f"not JSON serializable: {type(value)!r}")


def _load_simulation():
    """Find the engine's public demo builder without hard-coding internals."""
    candidates = (
        ("dss.core.engine", "build_minicity"),
        ("dss.simulation", "build_minicity"),
        ("dss.engine", "build_minicity"),
        ("dss.app", "build_minicity"),
        ("dss.demo", "build_minicity"),
        ("dss", "build_minicity"),
    )
    errors = []
    for module_name, symbol in candidates:
        try:
            module = importlib.import_module(module_name)
            builder = getattr(module, symbol, None)
            if builder:
                return builder
        except Exception as exc:  # report all candidates at the end
            errors.append(f"{module_name}: {exc}")
    detail = "\n".join(errors)
    raise RuntimeError(
        "Could not find a public MiniCity builder. Expected dss.simulation.build_minicity "
        "or dss.engine.build_minicity.\n" + detail
    )


def _build(builder, seed: int):
    for kwargs in ({"seed": seed}, {"rng_seed": seed}, {}):
        try:
            return builder(**kwargs)
        except TypeError:
            continue
    return builder(seed)


def _run(sim, days: int, headless: bool):
    for method in ("run", "run_days", "simulate"):
        fn = getattr(sim, method, None)
        if not fn:
            continue
        for kwargs in (
            {"days": days, "headless": headless},
            {"num_days": days, "headless": headless},
            {"days": days},
            {"num_days": days},
        ):
            try:
                # Most engines return snapshots from run(); the live engine is
                # the useful object for reports, ledgers and health checks.
                fn(**kwargs)
                return sim
            except TypeError:
                continue
    raise RuntimeError("Simulation has no run/run_days/simulate(days=...) method")


def _export(result, output: Path):
    output.mkdir(parents=True, exist_ok=True)
    annual = getattr(result, "annual_report", None)
    if callable(annual):
        data = annual()
    elif isinstance(result, dict):
        data = result
    elif hasattr(result, "to_dict"):
        data = result.to_dict()
    elif hasattr(result, "report"):
        report = result.report() if callable(result.report) else result.report
        data = report if isinstance(report, dict) else {"report": report}
    else:
        data = getattr(result, "__dict__", {"result": str(result)})
    (output / "annual_report.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8"
    )
    md_lines = [f"# {data.get('title', 'Digital Society Sandbox Annual Report')}", "",
                "> Simulation results only; this is not a real-world policy prediction.", ""]
    metrics = data.get("metrics", {}) if isinstance(data, dict) else {}
    if isinstance(metrics, dict):
        md_lines.extend(["## Metrics", "", *[f"- **{k}**: {v}" for k, v in metrics.items()], ""])
    (output / "annual_report.md").write_text("\n".join(md_lines), encoding="utf-8")
    # Export the two high-value append-only streams when exposed by the engine.
    for attr, filename in (("transactions", "transactions.jsonl"), ("events", "events.jsonl")):
        values = getattr(result, attr, None)
        if values is not None:
            with (output / filename).open("w", encoding="utf-8") as stream:
                for value in values:
                    stream.write(json.dumps(value, ensure_ascii=False, default=_json_default) + "\n")
    health = getattr(result, "health_reports", None)
    if health is not None:
        (output / "health.json").write_text(json.dumps(health, ensure_ascii=False,
            indent=2, default=_json_default), encoding="utf-8")
    # Keep a compact plain-text marker useful in CI logs and for non-technical users.
    (output / "README.txt").write_text(
        "Digital Society Sandbox demo output\n"
        "This is a simulation result; it does not represent a real policy forecast.\n",
        encoding="utf-8",
    )
    return data


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run the Digital Society Sandbox MiniCity demo")
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, default=ROOT / "artifacts" / "minicity")
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args(argv)
    if args.days < 1:
        parser.error("--days must be positive")
    builder = _load_simulation()
    sim = _build(builder, args.seed)
    result = _run(sim, args.days, args.headless)
    data = _export(result, args.out)
    print(json.dumps({"status": "ok", "days": args.days, "seed": args.seed, "out": str(args.out),
                      "keys": sorted(data) if isinstance(data, dict) else []}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
