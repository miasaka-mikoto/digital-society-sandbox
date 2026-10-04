"""Inspectable labor and business decision systems."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import math

from .economy import Economy, Good


def _g(o: Any, n: str, d: Any = None) -> Any:
    return o.get(n, d) if isinstance(o, dict) else getattr(o, n, d)


def _s(o: Any, n: str, v: Any) -> None:
    if isinstance(o, dict): o[n] = v
    else: setattr(o, n, v)


@dataclass
class JobPosting:
    posting_id: str
    business: Any
    role: str
    wage: float
    required_skills: dict[str, float] = field(default_factory=dict)
    slots: int = 1
    location: str | None = None
    applicants: list[Any] = field(default_factory=list)
    hired: list[Any] = field(default_factory=list)

    @property
    def open_slots(self) -> int:
        return max(0, self.slots - len(self.hired))


def _skill_score(citizen: Any, posting: JobPosting) -> float:
    skills = _g(citizen, "skills", {}) or {}
    if not posting.required_skills:
        return 1.0
    score = sum(min(1.0, float(skills.get(k, 0.0)) / max(0.01, req))
                for k, req in posting.required_skills.items())
    return score / len(posting.required_skills)


class LaborMarket:
    def __init__(self, economy: Economy, *, postings: list[JobPosting] | None = None) -> None:
        self.economy = economy
        self.postings = postings or []
        self._counter = 0

    def open_position(self, business: Any, role: str, wage: float,
                      required_skills: dict[str, float] | None = None,
                      slots: int = 1, location: str | None = None) -> JobPosting:
        wage = max(self.economy.minimum_wage, float(wage))
        self._counter += 1
        p = JobPosting(f"job-{self._counter}", business, role, wage,
                       required_skills or {}, max(1, int(slots)), location)
        self.postings.append(p)
        return p

    def decision_weights(self, citizen: Any, posting: JobPosting,
                         *, distance: float = 0.0) -> dict[str, float]:
        """Return components rather than a black-box score for auditability."""
        skills = _skill_score(citizen, posting)
        money = min(1.0, posting.wage / max(1.0, self.economy.minimum_wage * 2))
        dist = math.exp(-max(0.0, distance) / 10.0)
        needs = _g(citizen, "needs", {}) or {}
        income_need = float(needs.get("financial", needs.get("food", 0.5)))
        schedule = 1.0 if _g(citizen, "schedule", None) is not None else 0.8
        opportunity = 0.5 * skills + 0.3 * money + 0.2 * dist
        total = opportunity * (0.5 + 0.5 * min(1.0, max(0.0, income_need))) * schedule
        return {"skill_match": skills, "wage": money, "distance": dist,
                "needs": income_need, "schedule": schedule,
                "opportunity": opportunity, "total": total}

    def search_jobs(self, citizen: Any, *, distance_fn=None) -> list[tuple[JobPosting, dict[str, float]]]:
        available = []
        for p in self.postings:
            if p.open_slots <= 0:
                continue
            distance = distance_fn(citizen, p) if distance_fn else 0.0
            w = self.decision_weights(citizen, p, distance=float(distance))
            available.append((p, w))
        return sorted(available, key=lambda x: x[1]["total"], reverse=True)

    def apply(self, citizen: Any, posting: JobPosting) -> bool:
        if posting.open_slots <= 0 or citizen in posting.applicants:
            return False
        posting.applicants.append(citizen)
        return True

    def hire(self, posting: JobPosting, citizen: Any) -> bool:
        if posting.open_slots <= 0:
            return False
        if citizen not in posting.applicants:
            posting.applicants.append(citizen)
        posting.hired.append(citizen)
        _s(citizen, "job", posting)
        _s(citizen, "employer", posting.business)
        _s(citizen, "wage", posting.wage)
        employees = _g(posting.business, "employees", None)
        if employees is None:
            employees = []
            _s(posting.business, "employees", employees)
        if citizen not in employees:
            employees.append(citizen)
        return True

    def fire(self, citizen: Any, *, reason: str = "fired") -> bool:
        old = _g(citizen, "job", None)
        if not old:
            return False
        if citizen in old.hired: old.hired.remove(citizen)
        if citizen in (_g(old.business, "employees", []) or []):
            _g(old.business, "employees", []).remove(citizen)
        _s(citizen, "job", None); _s(citizen, "employer", None)
        _s(citizen, "job_status", reason)
        return True

    def quit(self, citizen: Any) -> bool:
        return self.fire(citizen, reason="quit")

    def daily_update(self, citizens: list[Any], day: int) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for c in citizens:
            if _g(c, "job", None) is None:
                options = self.search_jobs(c)
                if options and self.apply(c, options[0][0]):
                    events.append({"type": "job_application", "citizen": _g(c, "agent_id", c),
                                   "posting": options[0][0].posting_id, "day": day})
        # deterministic hiring: highest skill score then stable ID
        for p in self.postings:
            if not p.applicants: continue
            p.applicants.sort(key=lambda c: (-_skill_score(c, p), str(_g(c, "agent_id", c))))
            while p.open_slots and p.applicants:
                c = p.applicants.pop(0)
                self.hire(p, c)
                events.append({"type": "hire", "citizen": _g(c, "agent_id", c),
                               "posting": p.posting_id, "day": day})
        return events


class BusinessDecisionSystem:
    """Rule-based business choices with reasons returned for diagnostics."""
    def __init__(self, economy: Economy) -> None:
        self.economy = economy

    def decision_weights(self, business: Any) -> dict[str, float]:
        cash = float(_g(business, "cash", 0.0)); demand = float(_g(business, "demand", 0.0))
        inventory = sum(float(x) for x in (_g(business, "inventory", {}) or {}).values())
        costs = max(0.01, float(_g(business, "cost", _g(business, "costs", 1.0))))
        price = max(0.01, float(_g(business, "price", 1.0)))
        produce = max(0.0, demand - inventory) / max(1.0, demand + 1.0)
        hire = max(0.0, demand - len(_g(business, "employees", []) or [])) / max(1.0, demand)
        expand = min(1.0, cash / (10 * costs)) * max(0.0, demand / max(1.0, inventory + 1))
        adjust_price = max(-1.0, min(1.0, (demand - inventory) / max(1.0, demand + inventory)))
        return {"produce": produce, "hire": hire, "expand": expand,
                "adjust_price": adjust_price, "close": 1.0 if cash < -costs else 0.0,
                "price": price}

    def decide(self, business: Any) -> dict[str, Any]:
        w = self.decision_weights(business)
        if w["close"]:
            action = "close"
        elif w["produce"] > 0.2:
            action = "produce"
        elif w["hire"] > 0.3:
            action = "hire"
        elif w["expand"] > 0.7:
            action = "expand"
        else:
            action = "hold"
        return {"action": action, "weights": w}

    def daily_update(self, business: Any, day: int) -> dict[str, Any]:
        result = self.decide(business)
        if result["action"] == "adjust_price":
            _s(business, "price", max(0.01, float(_g(business, "price", 1.0)) *
                                      (1 + 0.05 * result["weights"]["adjust_price"])))
        return {"day": day, "business": _g(business, "agent_id", _g(business, "id", business)), **result}

