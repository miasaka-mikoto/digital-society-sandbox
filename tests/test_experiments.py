from pathlib import Path
import tempfile

from dss.core.models import Citizen, Business, Transaction
from dss.experiments.runner import ExperimentConfig, HeadlessRunner
from dss.experiments.persistence import SnapshotStore
from dss.experiments.reports import build_annual_report
from dss.experiments.comparison import compare_policies


class TinySim:
    def __init__(self, seed=0, policy=None):
        self.seed, self.day, self.policy = seed, 0, policy or {}
        self.citizens = [Citizen(f"c{i}", 30, "h", job_id="j" if i == 0 else None, savings=100) for i in range(4)]
        self.businesses = [Business("b", "shop", "m", inventory={"food": 10}, cash=1000)]
        self.transactions = []

    def step(self):
        self.day += 1
        self.citizens[0].savings += 1
        self.transactions.append(Transaction(f"t{self.day}", "c0", "b", 1, "food", self.day, "test"))

    def to_dict(self):
        from dss.core.models import to_dict
        return to_dict(self)


def test_deterministic_and_report():
    cfg = ExperimentConfig(days=10, seeds=2, snapshot_interval=5)
    a = HeadlessRunner(TinySim, cfg).run()
    b = HeadlessRunner(TinySim, cfg).run()
    assert [x.final_state for x in a] == [x.final_state for x in b]
    assert a[0].metrics["transaction_count"] == 10
    assert build_annual_report(a).seed_count == 2


def test_sqlite_snapshot_and_policy_comparison(tmp_path):
    sim = TinySim(1)
    sim.step()
    db = tmp_path / "run.sqlite"
    with SnapshotStore(db) as store:
        store.save_simulation("r", 1, 1, sim, {"x": 2})
        loaded = store.load("r")
    assert loaded["day"] == 1 and loaded["metrics"]["x"] == 2
    result = compare_policies(TinySim, {"A": {}, "B": {"tax_rate": .15}}, ExperimentConfig(days=2, seeds=1, snapshot_interval=0))
    assert "A" in result.summary and "B" in result.deltas
