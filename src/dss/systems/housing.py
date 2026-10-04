"""Housing stock, occupancy and deterministic relocation."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
import math

from .economy import Economy


def _g(o, n, d=None): return o.get(n, d) if isinstance(o, dict) else getattr(o, n, d)
def _s(o, n, v): o.__setitem__(n, v) if isinstance(o, dict) else setattr(o, n, v)


@dataclass
class House:
    house_id: str
    capacity: int
    rent: float
    quality: float = 0.5
    location: str = "Residential"
    occupants: list[Any] = field(default_factory=list)
    landlord: Any = None

    @property
    def available(self) -> int:
        return max(0, self.capacity - len(self.occupants))


class HousingSystem:
    def __init__(self, economy: Economy, houses: list[House] | None = None) -> None:
        self.economy, self.houses = economy, houses or []
        self.evictions: list[dict[str, Any]] = []

    def add_house(self, house: House) -> None:
        if house.capacity <= 0 or house.rent < 0: raise ValueError("invalid house")
        self.houses.append(house)

    def score(self, citizen: Any, house: House, *, distance: float = 0.0) -> dict[str, float]:
        cash = float(_g(citizen, "cash", _g(citizen, "money", 0.0)))
        affordability = min(1.0, cash / max(1.0, house.rent * 4))
        quality = max(0.0, min(1.0, house.quality))
        dist = math.exp(-max(0.0, distance) / 10.0)
        total = 0.45 * affordability + 0.4 * quality + 0.15 * dist
        return {"affordability": affordability, "quality": quality, "distance": dist, "total": total}

    def find_home(self, citizen: Any, *, distance_fn=None) -> tuple[House | None, dict[str, float]]:
        candidates = []
        for h in self.houses:
            if h.available <= 0: continue
            dist = distance_fn(citizen, h) if distance_fn else 0.0
            candidates.append((h, self.score(citizen, h, distance=float(dist))))
        if not candidates: return None, {"total": 0.0}
        return max(candidates, key=lambda x: (x[1]["total"], -x[0].rent))[0:2]

    def move(self, citizen: Any, house: House, *, household: Any = None) -> bool:
        if house.available <= 0: return False
        old = _g(citizen, "house", None)
        if old is house: return True
        if old is not None and citizen in old.occupants: old.occupants.remove(citizen)
        house.occupants.append(citizen); _s(citizen, "house", house)
        if household is not None: _s(household, "housing", house)
        return True

    def collect_rent(self, day: int) -> list[dict[str, Any]]:
        events = []
        for h in self.houses:
            for c in list(h.occupants):
                landlord = h.landlord if h.landlord is not None else h
                if self.economy.pay_rent(c, landlord, h.rent, day):
                    events.append({"type": "rent", "citizen": _g(c, "agent_id", c),
                                   "house": h.house_id, "amount": h.rent, "day": day})
                else:
                    self.evictions.append({"citizen": _g(c, "agent_id", c), "house": h.house_id, "day": day})
        return events

    def occupancy(self) -> float:
        cap = sum(h.capacity for h in self.houses)
        return sum(len(h.occupants) for h in self.houses) / cap if cap else 0.0

