"""Same-seed policy comparisons and machine-readable exports."""
from __future__ import annotations
from dataclasses import dataclass, asdict
import csv, json
from pathlib import Path
from typing import Any, Dict, Mapping, Optional
from .runner import ExperimentConfig, ExperimentRun, HeadlessRunner
from .reports import build_annual_report


@dataclass
class ComparisonResult:
    policies: Dict[str, list]
    summary: Dict[str, Dict[str, Any]]
    deltas: Dict[str, Dict[str, Any]]
    disclaimer: str = "Simulation results only; not a prediction of real-world policy or society."

    def to_dict(self): return asdict(self)
    def to_json(self, path):
        Path(path).write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"); return Path(path)
    def to_markdown(self, path):
        lines = ["# Policy Experiment Comparison", "", f"> {self.disclaimer}", "", "| Policy | Metric | Value |", "|---|---|---:|"]
        for policy, metrics in self.summary.items():
            for k, v in metrics.items(): lines.append(f"| {policy} | {k.replace('_',' ').title()} | {v:.4f} |" if isinstance(v,float) else f"| {policy} | {k.replace('_',' ').title()} | {v} |")
        lines += ["", "## Delta from baseline", "", "| Policy | Metric | Delta |", "|---|---|---:|"]
        for policy, metrics in self.deltas.items():
            for k, v in metrics.items(): lines.append(f"| {policy} | {k.replace('_',' ').title()} | {v:.4f} |")
        Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8"); return Path(path)

    def to_csv(self, path):
        keys = sorted({k for m in self.summary.values() for k in m})
        with Path(path).open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f); w.writerow(["policy", *keys])
            for p, m in self.summary.items(): w.writerow([p, *[m.get(k, "") for k in keys]])
        return Path(path)


def compare_policies(factory, policies: Mapping[str, Any], config: Optional[ExperimentConfig] = None) -> ComparisonResult:
    config = config or ExperimentConfig()
    all_runs = {}
    for name, policy in policies.items():
        all_runs[name] = HeadlessRunner(factory, config).run(policy)
    summaries = {name: build_annual_report(runs).aggregate for name, runs in all_runs.items()}
    base_name = next(iter(summaries), None)
    base = summaries.get(base_name, {})
    deltas = {name: {k: float(v) - float(base.get(k, 0)) for k, v in m.items() if isinstance(v, (int, float)) and isinstance(base.get(k), (int, float))}
              for name, m in summaries.items() if name != base_name}
    return ComparisonResult({k: [r.as_dict() for r in v] for k, v in all_runs.items()}, summaries, deltas)
