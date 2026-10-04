"""Deterministic agent-based simulation core for Digital Society Sandbox.

The package intentionally contains no chat/LLM agents.  It models citizens,
households, firms, goods, housing, transactions, and social relationships as
ordinary deterministic Python objects so experiments can be replayed by seed.
"""

from .models import (
    Business, Citizen, Event, Good, Household, Housing, InstitutionRules,
    Job, Location, MapGrid, Relationship, Schedule, Transaction,
)
from .scenario import ScenarioSpec, ScenarioEditor

_ENGINE_EXPORTS = {"SimulationEngine", "SimulationConfig", "Snapshot", "HealthReport",
                   "build_minicity", "run_mini_city"}


def __getattr__(name):
    """Lazy-load the engine to keep ``dss.systems`` imports acyclic."""
    if name in _ENGINE_EXPORTS:
        from . import engine
        value = getattr(engine, name)
        globals()[name] = value
        return value
    raise AttributeError(name)

__all__ = [
    "Business", "Citizen", "Event", "Good", "Household", "Housing",
    "InstitutionRules", "Job", "Location", "MapGrid", "Relationship",
    "Schedule", "Transaction", "SimulationEngine", "SimulationConfig",
    "Snapshot", "HealthReport", "build_minicity", "run_mini_city",
    "ScenarioSpec", "ScenarioEditor",
]
