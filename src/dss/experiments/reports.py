"""Annual report generation from one or more ExperimentRun objects."""
from __future__ import annotations
from dataclasses import dataclass, asdict
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List
from .runner import ExperimentRun


@dataclass
class AnnualReport:
    title: str
    disclaimer: str
    seed_count: int
    days: int
    aggregate: Dict[str, Any]
    per_seed: List[Dict[str, Any]]
    health: Dict[str, Any]

    def to_dict(self): return asdict(self)
    def to_json(self, path: str | Path):
        Path(path).write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return Path(path)
    def to_markdown(self, path: str | Path):
        p = Path(path)
        lines = [f"# {self.title}", "", f"> {self.disclaimer}", "", f"- Seeds: {self.seed_count}", f"- Simulated days: {self.days}", "", "## Aggregate metrics", "", "| Metric | Value |", "|---|---:|"]
        for k, v in self.aggregate.items(): lines.append(f"| {k.replace('_',' ').title()} | {v:.4f} |" if isinstance(v, float) else f"| {k.replace('_',' ').title()} | {v} |")
        lines.extend(["", "## Health", "", "| Code | Severity | Count |", "|---|---|---:|"])
        for code, d in self.health.items(): lines.append(f"| {code} | {d['severity']} | {d['count']} |")
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return p


def build_annual_report(runs: Iterable[ExperimentRun], title: str = "Digital Society Sandbox — Annual Simulation Report") -> AnnualReport:
    runs = list(runs)
    metric_keys = sorted({k for r in runs for k in r.metrics})
    aggregate = {}
    for k in metric_keys:
        vals = [r.metrics[k] for r in runs if isinstance(r.metrics.get(k), (int, float))]
        aggregate[k] = sum(vals) / len(vals) if vals else (runs[0].metrics.get(k) if runs else 0)
    health = {}
    for r in runs:
        for issue in r.issues:
            code = issue.code if hasattr(issue, "code") else issue.get("code", "UNKNOWN")
            severity = issue.severity if hasattr(issue, "severity") else issue.get("severity", "warning")
            health.setdefault(code, {"severity": severity, "count": 0})["count"] += 1
    return AnnualReport(title, "Simulation results only; not a prediction of real-world policy or society.", len(runs), runs[0].days if runs else 0, aggregate,
                        [{"seed": r.seed, **r.metrics, "error": r.error} for r in runs], health)
