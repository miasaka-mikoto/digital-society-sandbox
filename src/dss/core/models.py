"""Data model objects used by the simulation engine.

All identifiers are strings and all state is JSON-friendly.  The model is
deliberately explicit: this makes every decision and money flow inspectable.
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum


@dataclass
class Location:
    id: str
    kind: str
    x: int
    y: int
    capacity: int = 0
    quality: float = 1.0
    rent: float = 0.0


@dataclass
class MapGrid:
    width: int = 20
    height: int = 20
    locations: Dict[str, Location] = field(default_factory=dict)
    citizen_positions: Dict[str, str] = field(default_factory=dict)

    def add_location(self, location: Location) -> None:
        self.locations[location.id] = location

    def distance(self, a: Optional[str], b: Optional[str]) -> float:
        if not a or not b or a not in self.locations or b not in self.locations:
            return 9999.0
        la, lb = self.locations[a], self.locations[b]
        return abs(la.x - lb.x) + abs(la.y - lb.y)


@dataclass
class Good:
    id: str
    name: str
    base_price: float
    essential: bool = False


@dataclass
class Housing:
    id: str
    location_id: str
    capacity: int
    rent: float
    quality: float = 1.0
    occupants: List[str] = field(default_factory=list)

    @property
    def occupancy(self) -> int:
        """Number of current occupants (kept as a derived value)."""
        return len(self.occupants)


@dataclass
class Household:
    id: str
    member_ids: List[str] = field(default_factory=list)
    housing_id: Optional[str] = None
    shared_resources: float = 0.0
    shared_expenses: float = 0.0
    events: List[str] = field(default_factory=list)


@dataclass
class Schedule:
    # Mapping day-part to activity: sleep, work, shop, study, social, park.
    slots: Dict[str, str] = field(default_factory=lambda: {
        "morning": "work", "afternoon": "work", "evening": "home", "night": "sleep"
    })


@dataclass
class Job:
    id: str
    business_id: str
    title: str
    wage: float
    skill_required: float = 0.0
    filled_by: Optional[str] = None


@dataclass
class Citizen:
    id: str
    age: int
    household_id: str
    education: float = 0.5
    job_id: Optional[str] = None
    income: float = 0.0
    savings: float = 100.0
    needs: Dict[str, float] = field(default_factory=lambda: {"food": 0.8, "housing": 0.8, "social": 0.3})
    skills: Dict[str, float] = field(default_factory=lambda: {"general": 0.5})
    traits: Dict[str, float] = field(default_factory=lambda: {"risk": 0.5, "mobility": 0.5, "patience": 0.5})
    beliefs: Dict[str, float] = field(default_factory=dict)
    relationship_ids: List[str] = field(default_factory=list)
    schedule: Schedule = field(default_factory=Schedule)
    goals: List[str] = field(default_factory=lambda: ["security"])
    location_id: Optional[str] = None
    unemployed_days: int = 0
    alive: bool = True
    # Citizens carry a small physical inventory so purchases and stock flows
    # remain inspectable.  Money itself is represented by ``savings``; the
    # cash property below is a compatibility alias used by Economy helpers.
    inventory: Dict[str, float] = field(default_factory=dict)
    last_activity: str = "home"
    movement_history: List[str] = field(default_factory=list)
    income_total: float = 0.0
    expenses_total: float = 0.0

    @property
    def cash(self) -> float:
        return float(self.savings)

    @cash.setter
    def cash(self, value: float) -> None:
        self.savings = float(value)

    @property
    def employed(self) -> bool:
        return self.job_id is not None

    @property
    def age_parameter(self) -> int:
        """Human-readable alias for the model's age parameter."""
        return self.age


@dataclass
class Business:
    id: str
    name: str
    location_id: str
    product: str = "food"
    employees: List[str] = field(default_factory=list)
    open_positions: int = 1
    salary: float = 35.0
    inventory: Dict[str, float] = field(default_factory=dict)
    revenue: float = 0.0
    cost: float = 0.0
    price: float = 10.0
    demand: float = 0.0
    cash: float = 1000.0
    alive: bool = True
    age_days: int = 0
    service_provider: bool = False
    employees_total: int = 0

    @property
    def sector(self) -> str:
        return self.product

    @sector.setter
    def sector(self, value: str) -> None:
        self.product = str(value)


@dataclass
class Relationship:
    id: str
    a: str
    b: str
    familiarity: float = 0.0
    trust: float = 0.5
    affinity: float = 0.0
    conflict: float = 0.0
    communication_frequency: float = 0.0


@dataclass
class Transaction:
    id: str
    buyer: str
    seller: str
    amount: float
    good: str
    time: int
    reason: str
    quantity: float = 1.0


@dataclass
class Event:
    id: str
    time: int
    kind: str
    location_id: Optional[str]
    text: str
    source: Optional[str] = None
    spread: int = 0
    channel: str = "local"


@dataclass
class InstitutionRules:
    tax_rate: float = 0.05
    minimum_wage: float = 15.0
    education_cost: float = 15.0
    transport_cost: float = 2.0
    welfare_parameter: float = 0.0
    business_tax_rate: float = 0.05
    rent_subsidy: float = 0.0
    government_budget: float = 5000.0
    business_rules: Dict[str, float] = field(default_factory=dict)


def to_dict(obj, _seen=None):
    """Return a JSON-friendly representation without invoking user methods.

    Calling an arbitrary object's ``to_dict`` is tempting, but many tiny test
    fixtures implement that method as ``return to_dict(self)``.  Walking
    dataclass fields and ``__dict__`` directly avoids that recursion and also
    makes save/load behavior consistent across engines.
    """
    if _seen is None:
        _seen = set()
    if isinstance(obj, Enum):
        return obj.value
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    oid = id(obj)
    if oid in _seen:
        return "<cycle>"
    if is_dataclass(obj):
        _seen.add(oid)
        result = {f.name: to_dict(getattr(obj, f.name), _seen) for f in fields(obj)}
        _seen.discard(oid)
        return result
    if isinstance(obj, dict):
        _seen.add(oid)
        result = {str(k): to_dict(v, _seen) for k, v in obj.items()}
        _seen.discard(oid)
        return result
    if isinstance(obj, (list, tuple, set, frozenset)):
        _seen.add(oid)
        result = [to_dict(x, _seen) for x in obj]
        _seen.discard(oid)
        return result
    if hasattr(obj, "__dict__"):
        _seen.add(oid)
        result = {str(k): to_dict(v, _seen) for k, v in vars(obj).items()
                  if not str(k).startswith("_")}
        _seen.discard(oid)
        return result
    return str(obj)
