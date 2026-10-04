"""Headless experiment, persistence and reporting utilities.

The experiment layer intentionally depends on a very small simulator protocol.
An engine may expose ``step``/``run_day`` (preferred), or ``run(days)`` and a
serialisable ``state``/``to_dict``.  This keeps experiments useful while the
interactive map and the domain engine evolve independently.
"""
from .runner import ExperimentConfig, ExperimentRun, HeadlessRunner, HealthIssue, SimulationHealthMonitor, state_digest
from .persistence import SnapshotStore, load_snapshot, save_snapshot
from .reports import AnnualReport, build_annual_report
from .comparison import compare_policies, ComparisonResult

__all__ = [
    "ExperimentConfig", "ExperimentRun", "HeadlessRunner", "HealthIssue",
    "SimulationHealthMonitor", "state_digest", "SnapshotStore", "save_snapshot", "load_snapshot",
    "AnnualReport", "build_annual_report", "compare_policies", "ComparisonResult",
]
