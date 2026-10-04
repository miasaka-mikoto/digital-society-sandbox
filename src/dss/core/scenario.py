"""Serializable scenario editor for virtual-world experiments."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Any, Mapping

from .models import InstitutionRules


@dataclass
class ScenarioSpec:
    population: int = 100
    businesses: int = 20
    houses: int = 30
    seed: int = 42
    days: int = 365
    width: int = 30
    height: int = 20
    resources: dict[str, float] = field(default_factory=lambda: {"food": 8.0, "basic": 8.0})
    rules: dict[str, Any] = field(default_factory=dict)
    map_overrides: dict[str, dict[str, Any]] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)

    def validate(self) -> None:
        for name in ("population", "businesses", "houses", "days", "width", "height"):
            if int(getattr(self, name)) < 0:
                raise ValueError(f"{name} must be non-negative")
        if self.population and self.houses == 0:
            raise ValueError("a populated scenario needs at least one house")
        for key, value in self.resources.items():
            if float(value) < 0:
                raise ValueError(f"resource {key} must be non-negative")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ScenarioSpec":
        allowed = set(cls.__dataclass_fields__)
        obj = cls(**{k: v for k, v in data.items() if k in allowed})
        obj.validate()
        return obj

    def save(self, path: str | Path) -> Path:
        p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return p

    @classmethod
    def load(cls, path: str | Path) -> "ScenarioSpec":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


class ScenarioEditor:
    """Small mutation API used by the GUI and batch scripts."""
    def __init__(self, scenario: ScenarioSpec | None = None):
        self.scenario = scenario or ScenarioSpec()

    def set(self, key: str, value: Any) -> "ScenarioEditor":
        if not hasattr(self.scenario, key):
            raise KeyError(key)
        setattr(self.scenario, key, value)
        self.scenario.validate()
        return self

    def set_rule(self, key: str, value: Any) -> "ScenarioEditor":
        self.scenario.rules[str(key)] = value
        return self

    def add_event(self, event: Mapping[str, Any]) -> "ScenarioEditor":
        self.scenario.events.append(dict(event))
        return self

    def set_resource(self, key: str, amount: float) -> "ScenarioEditor":
        self.scenario.resources[str(key)] = float(amount)
        self.scenario.validate()
        return self

    def build(self):
        from .engine import SimulationConfig, SimulationEngine
        self.scenario.validate()
        rules = InstitutionRules(**{k: v for k, v in self.scenario.rules.items()
                                    if k in InstitutionRules.__dataclass_fields__})
        return SimulationEngine(SimulationConfig(seed=self.scenario.seed,
            citizens=self.scenario.population, businesses=self.scenario.businesses,
            houses=self.scenario.houses, days=self.scenario.days,
            width=self.scenario.width, height=self.scenario.height), rules)

    def save(self, path: str | Path) -> Path:
        return self.scenario.save(path)


__all__ = ["ScenarioSpec", "ScenarioEditor"]
