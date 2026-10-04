"""Macro indicators and emergence detectors derived from micro state."""
from __future__ import annotations

from collections import Counter, defaultdict
from statistics import median
from typing import Any, Iterable, Mapping, Optional, Sequence

from dss.core.models import Business, Citizen, Housing, Transaction
from .social import SocialNetwork


def _vals(items, attr, default=0.0):
    return [float(getattr(x, attr, default)) for x in items]


def macro_metrics(
    citizens: Iterable[Citizen], businesses: Iterable[Business], houses: Iterable[Housing] = (),
    transactions: Iterable[Transaction] = (), network: Optional[SocialNetwork] = None,
) -> dict:
    cs = [c for c in citizens if c.alive]; bs = [b for b in businesses if b.alive]; hs = list(houses); tx = list(transactions)
    incomes = _vals(cs, "income"); savings = _vals(cs, "savings")
    employed = sum(1 for c in cs if c.job_id)
    occupied = sum(1 for h in hs if h.occupants)
    prices = _vals(bs, "price")
    consumption = Counter(t.good for t in tx if t.reason in {"purchase", "consume", "consumption", "food", "entertainment"})
    result = {
        "population": len(cs), "employment": employed / len(cs) if cs else 0.0,
        "employed_count": employed, "average_income": sum(incomes) / len(incomes) if incomes else 0.0,
        "median_savings": median(savings) if savings else 0.0,
        "business_count": len(bs), "average_price": sum(prices) / len(prices) if prices else 0.0,
        "housing_occupancy": occupied / len(hs) if hs else 0.0,
        "consumption": dict(sorted(consumption.items())), "transaction_count": len(tx),
        "unemployed_count": sum(1 for c in cs if not c.job_id),
        "income_gini": _gini(incomes), "savings_gini": _gini(savings),
    }
    if network is not None: result["social_network"] = network.metrics([c.id for c in cs])
    return result


def _gini(values: Sequence[float]) -> float:
    xs = sorted(max(0.0, float(x)) for x in values)
    if not xs or sum(xs) == 0: return 0.0
    n = len(xs); return sum((2 * i - n - 1) * x for i, x in enumerate(xs, 1)) / (n * sum(xs))


def detect_emergence(
    citizens: Iterable[Citizen], businesses: Iterable[Business], houses: Iterable[Housing] = (),
    transactions: Iterable[Transaction] = (), network: Optional[SocialNetwork] = None,
) -> dict:
    """Return interpretable flags; thresholds are simulation diagnostics only."""
    cs = list(citizens); bs = list(businesses); hs = list(houses); tx = list(transactions)
    by_loc = Counter(b.location_id for b in bs if b.alive)
    citizen_loc = Counter(c.location_id for c in cs if c.alive and c.location_id)
    metrics = macro_metrics(cs, bs, hs, tx, network)
    flags = {
        "commercial_center": bool(by_loc and max(by_loc.values()) >= max(3, len(bs) // 4)),
        "wealth_inequality": metrics["income_gini"] >= 0.35 or metrics["savings_gini"] >= 0.35,
        "unemployment": metrics["employment"] < 0.7 if cs else False,
        "business_concentration": bool(by_loc and len(by_loc) > 1 and max(by_loc.values()) / len(bs) >= 0.5),
        "housing_pressure": metrics["housing_occupancy"] >= 0.9 if hs else False,
        "consumption_pattern": bool(metrics["consumption"]),
        "population_migration": len(citizen_loc) >= 2 and len(cs) > 0 and max(citizen_loc.values()) / len(cs) >= 0.7,
        "social_network_clustering": bool(network and network.metrics([c.id for c in cs]).get("connected_components", 0) > 1),
    }
    return {"metrics": metrics, "flags": flags, "location_business_counts": dict(sorted(by_loc.items()))}


def macro_metrics_from_engine(engine, network: Optional[SocialNetwork] = None) -> dict:
    """Adapter for the canonical ``SimulationEngine`` state shape."""
    return macro_metrics(engine.citizens.values(), engine.businesses.values(),
                         engine.houses.values(), engine.transactions, network)


def detect_emergence_from_engine(engine, network: Optional[SocialNetwork] = None) -> dict:
    return detect_emergence(engine.citizens.values(), engine.businesses.values(),
                            engine.houses.values(), engine.transactions, network)


__all__ = ["macro_metrics", "detect_emergence", "macro_metrics_from_engine", "detect_emergence_from_engine"]
