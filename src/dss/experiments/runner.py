"""Deterministic, headless simulation runner and health checks."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
import inspect
import math
import statistics
import hashlib
import json
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional

from dss.core.models import to_dict


def _get(obj: Any, *names: str, default=None):
    for name in names:
        if isinstance(obj, Mapping) and name in obj:
            return obj[name]
        if hasattr(obj, name):
            return getattr(obj, name)
    return default


def _items(obj: Any, *names: str) -> list:
    value = _get(obj, *names, default=[])
    if isinstance(value, Mapping):
        return list(value.values())
    return list(value or [])


@dataclass
class ExperimentConfig:
    days: int = 365
    seeds: int = 1
    seed_start: int = 0
    population: int = 100
    businesses: int = 20
    houses: int = 30
    snapshot_interval: int = 7
    max_steps: Optional[int] = None
    fail_fast: bool = False
    output_dir: str = "artifacts/experiments"
    # Long batches should not retain a full object graph for every weekly
    # point.  The engine/SQLite layer can still persist complete snapshots
    # when explicitly requested.
    store_full_snapshots: bool = False
    include_final_state: bool = True


@dataclass
class HealthIssue:
    code: str
    severity: str
    message: str
    day: int = 0
    details: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self):
        return asdict(self)


class SimulationHealthMonitor:
    """Detect common invalid or stalled states without assuming one engine shape."""
    def __init__(self, no_transaction_days: int = 30, stuck_days: int = 14):
        self.no_transaction_days = no_transaction_days
        self.stuck_days = stuck_days
        self.issues: List[HealthIssue] = []
        self._last_transaction_count = 0
        self._last_tx_day = 0
        self._position_history: Dict[str, List[Any]] = {}

    def check(self, sim: Any, day: int) -> List[HealthIssue]:
        found: List[HealthIssue] = []
        citizens = _items(sim, "citizens", "population")
        businesses = _items(sim, "businesses", "companies")
        transactions = _items(sim, "transactions", "ledger")
        # Check numeric fields most likely to become invalid.  Walking an
        # entire relationship graph every day makes 100×365 sweeps needlessly
        # expensive; this targeted scan catches all simulation-critical money,
        # price and inventory values while remaining engine-shape agnostic.
        nan_path = None
        for obj, label, fields in [
            (citizens, "citizens", ("savings", "income", "education")),
            (businesses, "businesses", ("cash", "price", "revenue", "cost")),
        ]:
            for idx, item in enumerate(obj):
                for field in fields:
                    value = _get(item, field, default=None)
                    if isinstance(value, (int, float)) and not math.isfinite(float(value)):
                        nan_path = f"{label}[{idx}].{field}"; break
                if nan_path: break
            if nan_path: break
        if nan_path:
            found.append(HealthIssue("NAN_OR_INFINITY", "error", f"Non-finite value at {nan_path}", day))

        for b in businesses:
            inv = _get(b, "inventory", default={})
            vals = inv.values() if isinstance(inv, Mapping) else []
            if any(float(x) < -1e-9 for x in vals):
                found.append(HealthIssue("NEGATIVE_INVENTORY", "error", f"Business {_get(b,'id',default='?')} has negative inventory", day))
        alive_b = [b for b in businesses if bool(_get(b, "alive", default=True))]
        if businesses and not alive_b:
            found.append(HealthIssue("ALL_BUSINESSES_DEAD", "warning", "All businesses are closed", day))

        tx_count = len(transactions)
        if tx_count > self._last_transaction_count:
            self._last_transaction_count, self._last_tx_day = tx_count, day
        elif day - self._last_tx_day >= self.no_transaction_days:
            found.append(HealthIssue("NO_TRANSACTIONS", "warning", f"No transactions for {day-self._last_tx_day} days", day))

        # Population freeze/stuck: compare locations for citizens over a window.
        for c in citizens:
            cid = str(_get(c, "id", default=id(c)))
            loc = _get(c, "location_id", "location", default=None)
            hist = self._position_history.setdefault(cid, [])
            hist.append(loc)
            if len(hist) > self.stuck_days:
                del hist[:-self.stuck_days]
                if len(set(hist)) <= 1 and bool(_get(c, "alive", default=True)):
                    found.append(HealthIssue("AGENT_STUCK", "warning", f"Citizen {cid} has not moved for {self.stuck_days} days", day))
                    break
        if citizens and day > self.stuck_days and all(len(self._position_history.get(str(_get(c,"id",default=id(c))), [])) <= 1 for c in citizens):
            found.append(HealthIssue("POPULATION_FREEZE", "warning", "No citizen movement history available", day))
        # Avoid emitting identical issue repeatedly on every day.
        # Health reports should describe a condition once, not produce one
        # duplicate warning per simulated day (which is especially noisy in
        # 100-seed sweeps).  Distinguish separate agents/businesses by message.
        existing = {(x.code, x.message) for x in self.issues}
        found = [x for x in found if (x.code, x.message) not in existing]
        self.issues.extend(found)
        return found


def _state(sim: Any) -> Dict[str, Any]:
    if hasattr(sim, "to_dict"):
        value = sim.to_dict()
    elif hasattr(sim, "snapshot"):
        value = sim.snapshot()
    elif hasattr(sim, "state"):
        value = sim.state() if callable(sim.state) else sim.state
    else:
        value = vars(sim) if hasattr(sim, "__dict__") else sim
    # ``core.models.to_dict`` covers dataclasses; engines often return a
    # lightweight plain object from ``to_dict``.  Finish that conversion here
    # so snapshots and determinism comparisons never contain object identities.
    def jsonify(v, depth=0):
        if depth > 20: return "<max-depth>"
        if v is None or isinstance(v, (str, int, float, bool)): return v
        if isinstance(v, Mapping): return {str(k): jsonify(x, depth + 1) for k, x in v.items()}
        if isinstance(v, (list, tuple, set)): return [jsonify(x, depth + 1) for x in v]
        if hasattr(v, "__dataclass_fields__"): return jsonify(to_dict(v), depth + 1)
        if hasattr(v, "__dict__"): return jsonify(vars(v), depth + 1)
        return str(v)
    return jsonify(value)


def state_digest(sim: Any) -> str:
    """Stable digest used by determinism tests and experiment manifests."""
    payload = json.dumps(_state(sim), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class ExperimentRun:
    seed: int
    days: int
    final_state: Dict[str, Any]
    metrics: Dict[str, Any]
    issues: List[HealthIssue] = field(default_factory=list)
    snapshots: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None

    def as_dict(self):
        d = asdict(self)
        d["issues"] = [i.as_dict() if hasattr(i, "as_dict") else i for i in self.issues]
        return d


class HeadlessRunner:
    def __init__(self, factory: Callable[..., Any], config: Optional[ExperimentConfig] = None):
        self.factory, self.config = factory, config or ExperimentConfig()

    def _make(self, seed: int, policy: Any = None):
        # Accept build_minicity(seed=..., population=...), factory(seed, policy),
        # or the minimal factory(seed) shape.
        full = {"seed": seed, "policy": policy, "population": self.config.population,
                "businesses": self.config.businesses, "houses": self.config.houses}
        attempts = [full, {k: full[k] for k in ("seed", "policy")}, {"seed": seed}, {"seed": seed, "config": self.config}, None]
        for kwargs in attempts:
            try:
                if kwargs is None:
                    return self.factory()
                if kwargs:
                    return self.factory(**kwargs)
                return self.factory(seed)
            except TypeError:
                continue
        raise TypeError("Simulator factory must accept a seed")

    @staticmethod
    def _apply_policy(sim, policy):
        if policy is None: return
        if hasattr(sim, "apply_policy"): sim.apply_policy(policy)
        elif hasattr(sim, "rules") and isinstance(policy, Mapping):
            rules = sim.rules
            for k, v in policy.items():
                if hasattr(rules, k): setattr(rules, k, v)
                elif isinstance(rules, dict): rules[k] = v

    @staticmethod
    def _metrics(sim) -> Dict[str, Any]:
        citizens = _items(sim, "citizens", "population")
        businesses = _items(sim, "businesses", "companies")
        transactions = _items(sim, "transactions", "ledger")
        incomes = [float(_get(c, "income", default=0) or 0) for c in citizens]
        savings = [float(_get(c, "savings", default=0) or 0) for c in citizens]
        employed = sum(bool(_get(c, "job_id", "job", default=None)) for c in citizens)
        alive_b = sum(bool(_get(b, "alive", default=True)) for b in businesses)
        amounts = [float(_get(t, "amount", default=0) or 0) for t in transactions]
        consumption_amounts = [float(_get(t, "amount", default=0) or 0) for t in transactions
                               if str(_get(t, "reason", default="")) in
                               {"consumption", "entertainment", "purchase"}]
        return {
            "population": len(citizens), "employment": employed / len(citizens) if citizens else 0.0,
            "employed_count": employed, "average_income": statistics.fmean(incomes) if incomes else 0.0,
            "median_savings": statistics.median(savings) if savings else 0.0,
            "business_count": alive_b, "transaction_count": len(transactions),
            "consumption": sum(consumption_amounts), "ledger_volume": sum(amounts),
        }

    def run_one(self, seed: int, policy: Any = None) -> ExperimentRun:
        sim = self._make(seed, policy)
        self._apply_policy(sim, policy)
        monitor = SimulationHealthMonitor()
        snaps, error = [], None
        try:
            for day in range(self.config.days):
                if hasattr(sim, "step"):
                    sim.step()
                elif hasattr(sim, "run_day"):
                    sim.run_day()
                elif hasattr(sim, "tick"):
                    sim.tick()
                else:
                    # run(days=1) is the final compatibility option.
                    sim.run(days=1) if "days" in inspect.signature(sim.run).parameters else sim.run(1)
                if self.config.snapshot_interval and (day + 1) % self.config.snapshot_interval == 0:
                    snaps.append({"day": day + 1,
                                  "state": _state(sim) if self.config.store_full_snapshots else None,
                                  "metrics": self._metrics(sim)})
                monitor.check(sim, day + 1)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            if self.config.fail_fast: raise
        final_state = _state(sim) if self.config.include_final_state else {}
        return ExperimentRun(seed, self.config.days, final_state, self._metrics(sim), monitor.issues, snaps, error)

    def run(self, policy: Any = None) -> List[ExperimentRun]:
        return [self.run_one(self.config.seed_start + i, policy) for i in range(self.config.seeds)]
