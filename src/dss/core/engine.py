"""Simulation engine and the built-in MiniCity scenario."""
from __future__ import annotations

import copy
import json
import math
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from statistics import median
from typing import Dict, Iterable, List, Optional

from .models import (
    Business, Citizen, Event, Good, Household, Housing, InstitutionRules,
    Job, Location, MapGrid, Relationship, Transaction, to_dict,
)
from .rng import SeedRNG

# These subsystems are deliberately optional at the boundary: the core can
# still be imported as a small standard-library package, while a running
# engine exposes the richer relationship and information APIs.
from dss.systems.social import SocialNetwork, update_social_network
from dss.systems.information import InformationItem, InformationSystem


@dataclass
class SimulationConfig:
    seed: int = 1
    citizens: int = 100
    businesses: int = 20
    houses: int = 30
    days: int = 365
    snapshot_interval: int = 7
    width: int = 30
    height: int = 20


@dataclass
class Snapshot:
    day: int
    metrics: Dict[str, float]
    citizen_state: Dict[str, Dict] = field(default_factory=dict)
    business_state: Dict[str, Dict] = field(default_factory=dict)
    event_count: int = 0


@dataclass
class HealthReport:
    day: int
    ok: bool
    issues: List[str] = field(default_factory=list)


class SimulationEngine:
    """A deterministic, inspectable agent-based society simulation.

    Decision scores are stored in ``decision_log``.  No external model or API
    is used; all behavior is deterministic given the seed and configuration.
    """

    GOODS = {
        "food": Good("food", "Food", 10.0, True),
        "housing": Good("housing", "Housing", 100.0, True),
        "entertainment": Good("entertainment", "Entertainment", 15.0),
        "education": Good("education", "Education", 15.0),
        "transport": Good("transport", "Transport", 2.0),
        "basic": Good("basic", "Basic Goods", 8.0, True),
    }

    def __init__(self, config: Optional[SimulationConfig] = None, rules: Optional[InstitutionRules] = None):
        self.config = config or SimulationConfig()
        self.rules = copy.deepcopy(rules or InstitutionRules())
        self.rng = SeedRNG(self.config.seed)
        self.day = 0
        self.map = MapGrid(self.config.width, self.config.height)
        self.citizens: Dict[str, Citizen] = {}
        self.households: Dict[str, Household] = {}
        self.businesses: Dict[str, Business] = {}
        self.houses: Dict[str, Housing] = {}
        self.jobs: Dict[str, Job] = {}
        self.relationships: Dict[str, Relationship] = {}
        self.events: List[Event] = []
        self.transactions: List[Transaction] = []
        self.snapshots: List[Snapshot] = []
        self.health_reports: List[HealthReport] = []
        self.decision_log: List[Dict] = []
        self.government_cash = float(self.rules.government_budget)
        # Non-agent accounts make every monetary sink/source explicit.  They
        # are not hidden magic balances: production inputs and rent are posted
        # to these accounts and therefore remain auditable in the ledger.
        self.landlord_cash = 0.0
        self.resource_cash = 0.0
        self.welfare_paid = 0.0
        self.social_network = SocialNetwork(self.relationships)
        self.information_system = InformationSystem()
        self.information = self.information_system  # short compatibility alias
        self._position_history: Dict[str, List[str]] = {}
        self._deadlock_streaks: Dict[str, int] = {}
        self._last_transaction_day = 0
        self._initial_money = 0.0
        self._initial_inventory = 0.0
        self._tx_seq = 0
        self._event_seq = 0
        self._job_seq = 0
        self._build_world()
        # ``SocialNetwork`` keeps the same mapping object as the engine, so
        # relationships created during world construction are immediately
        # visible to both APIs.
        self.social_network.relationships = self.relationships
        self._initial_money = self.total_money()
        self._initial_inventory = self.total_inventory()

    # ----- world construction -------------------------------------------------
    def _build_world(self) -> None:
        kinds = [("res", "Residential"), ("com", "Commercial"), ("ind", "Industry"),
                 ("school", "School"), ("hospital", "Hospital"), ("gov", "Government"),
                 ("park", "Park"), ("transport", "Transport"), ("market", "Market")]
        for i, (prefix, kind) in enumerate(kinds):
            self.map.add_location(Location(f"{prefix}-0", kind, (i * 3) % self.map.width, (i * 5) % self.map.height, 100))
        residential = "res-0"
        for i in range(self.config.houses):
            h_id = f"house-{i:03d}"
            # Rent is a monthly scenario unit.  Keeping it below the typical
            # household's monthly income allows housing pressure to emerge
            # without making every citizen insolvent by construction.
            self.houses[h_id] = Housing(h_id, residential, 2 + i % 4,
                                        90.0 + (i % 5) * 12,
                                        0.7 + (i % 4) * .1)
        for i in range(self.config.citizens):
            hh_id = f"household-{i // 2:03d}"
            if hh_id not in self.households:
                self.households[hh_id] = Household(hh_id)
            c = Citizen(
                id=f"citizen-{i:03d}", age=self.rng.randint(18, 75), household_id=hh_id,
                education=round(self.rng.uniform(.2, .95), 3), savings=round(self.rng.uniform(80, 700), 2),
                skills={"general": round(self.rng.uniform(.2, 1.0), 3), "service": round(self.rng.uniform(.1, 1.0), 3)},
            )
            c.location_id = residential
            c.last_activity = "home"
            c.movement_history.append(residential)
            self.citizens[c.id] = c
            self.households[hh_id].member_ids.append(c.id)
            self.map.citizen_positions[c.id] = residential
            self._position_history[c.id] = [residential]
        # Assign houses, allowing capacity pressure to emerge naturally.
        hid = list(self.houses)
        for i, hh in enumerate(self.households.values()):
            house = self.houses[hid[i % len(hid)]]
            hh.housing_id = house.id
            for cid in hh.member_ids:
                if len(house.occupants) < house.capacity:
                    house.occupants.append(cid)
                self.citizens[cid].location_id = house.location_id
        products = ["food", "basic", "entertainment", "education", "transport"]
        for i in range(self.config.businesses):
            loc = "market-0" if i % 3 else "com-0"
            product = products[i % len(products)]
            b = Business(f"business-{i:03d}", f"Firm {i:03d}", loc, product, salary=28 + (i % 5) * 4,
                         price=self.GOODS[product].base_price * (0.85 + (i % 4) * .1),
                         inventory={product: 8.0}, cash=6000.0)
            self.businesses[b.id] = b
            b.employees_total = 0
            b.open_positions = 1 + i % 3
            for _ in range(b.open_positions):
                self._create_job(b)
        # Sparse social network: ring plus household links.
        cids = list(self.citizens)
        for i, cid in enumerate(cids):
            for other in (cids[(i + 1) % len(cids)], cids[(i + 7) % len(cids)]):
                self._add_relationship(cid, other, .6 if self.citizens[cid].household_id == self.citizens[other].household_id else .25)

    def _create_job(self, business: Business) -> Job:
        self._job_seq += 1
        j = Job(f"job-{self._job_seq:05d}", business.id, f"{business.product} worker", business.salary, self.rng.uniform(.15, .85))
        self.jobs[j.id] = j
        return j

    def _add_relationship(self, a: str, b: str, familiarity: float = .1) -> None:
        if a == b:
            return
        key = "rel:" + ":".join(sorted((a, b)))
        if key in self.relationships:
            return
        rel = Relationship(key, a, b, familiarity=familiarity, trust=.45, affinity=self.rng.uniform(-.1, .3), communication_frequency=.1)
        self.relationships[key] = rel
        self.citizens[a].relationship_ids.append(key)
        self.citizens[b].relationship_ids.append(key)

    # ----- simulation loop ----------------------------------------------------
    def run(self, days: Optional[int] = None, snapshot_interval: Optional[int] = None) -> List[Snapshot]:
        count = self.config.days if days is None else int(days)
        interval = self.config.snapshot_interval if snapshot_interval is None else int(snapshot_interval)
        for _ in range(count):
            self.step()
            if (interval > 0 and self.day % interval == 0) or self.day == count:
                self.take_snapshot()
        return self.snapshots

    # Compatibility aliases used by the UI and experiment runner.
    def run_day(self) -> None:
        self.step()

    @property
    def time(self) -> int:
        return self.day

    @property
    def state(self) -> "SimulationEngine":
        """Live state view; callers can inspect ``state.citizens`` etc."""
        return self

    def step(self) -> None:
        self.day += 1
        # ``income`` is a one-day observable; ``income_total`` is the
        # persistent history used by annual reports.
        for c in self.citizens.values():
            c.income = 0.0
        self._pay_wages_and_collect_tax()
        self._business_decisions()
        self._citizen_decisions()
        self._citizen_services_and_movement()
        self._housing_and_household_costs()
        self._social_and_information()
        self._age_and_cleanup()
        self.health_reports.append(self.health_check())

    def _record_tx(self, buyer: str, seller: str, amount: float, good: str, reason: str) -> None:
        if amount <= 0 or not math.isfinite(amount):
            return
        self._tx_seq += 1
        self.transactions.append(Transaction(f"tx-{self._tx_seq:07d}", buyer, seller,
                                             round(amount, 2), str(good), self.day, reason, 1.0))
        self._last_transaction_day = self.day

    def _move_citizen(self, citizen: Citizen, location_id: str, activity: str) -> None:
        """Move an agent through the map while retaining an audit trail."""
        if location_id not in self.map.locations:
            location_id = "res-0"
        citizen.location_id = location_id
        citizen.last_activity = activity
        citizen.movement_history.append(location_id)
        if len(citizen.movement_history) > 90:
            del citizen.movement_history[:-90]
        hist = self._position_history.setdefault(citizen.id, [])
        hist.append(location_id)
        if len(hist) > 90:
            del hist[:-90]
        self.map.citizen_positions[citizen.id] = location_id

    def _account_credit(self, account: str, amount: float) -> None:
        if account == "landlord":
            self.landlord_cash += amount
        elif account == "resources":
            self.resource_cash += amount

    def _sell_good(self, citizen: Citizen, business: Business, product: str,
                   quantity: float, reason: str) -> float:
        """Perform one bounded purchase and return the amount paid."""
        quantity = max(0.0, float(quantity))
        stock = max(0.0, float(business.inventory.get(product, 0.0)))
        price = max(0.01, float(business.price))
        quantity = min(quantity, stock, citizen.savings / price)
        if quantity <= 1e-9:
            return 0.0
        amount = quantity * price
        citizen.savings -= amount
        business.inventory[product] = max(0.0, stock - quantity)
        citizen.inventory[product] = citizen.inventory.get(product, 0.0) + quantity
        business.cash += amount
        business.revenue += amount
        self._record_tx(citizen.id, business.id, amount, product, reason)
        return amount

    def _pay_wages_and_collect_tax(self) -> None:
        for b in self.businesses.values():
            if not b.alive:
                continue
            for cid in list(b.employees):
                c = self.citizens[cid]
                # Salary is a weekly-ish scenario parameter.  Dividing by
                # three gives agents enough room for food and housing while
                # leaving firms exposed to demand and cash constraints.
                gross = max(self.rules.minimum_wage / 3.0, b.salary / 3.0)
                tax = gross * self.rules.tax_rate
                if b.cash < gross:
                    continue
                b.cash -= gross
                self.government_cash += tax
                net = gross - tax
                c.income += net
                c.income_total += net
                c.savings += net
                self._record_tx(b.id, cid, gross, "currency", "wage")
                self._record_tx(cid, "government", tax, "currency", "income_tax")
                b.cost += gross
                b.employees_total += 1
            # Small firms can reopen a vacant position after a good month;
            # this keeps the labour market dynamic rather than one-shot.
            vacant = max(0, b.open_positions - len(b.employees))
            if (b.alive and vacant == 0 and b.demand > 2 and b.cash > b.salary * 12
                    and b.open_positions < 12):
                b.open_positions += 1
                self._create_job(b)

    def _citizen_decisions(self) -> None:
        for c in self.citizens.values():
            if not c.alive:
                continue
            # Search for a job when unemployed; score is deliberately inspectable.
            if not c.job_id:
                c.unemployed_days += 1
                candidates = [j for j in self.jobs.values() if j.filled_by is None and self.businesses[j.business_id].alive]
                scored = []
                for j in candidates:
                    skill = c.skills.get("general", .5)
                    education = c.education
                    mobility = c.traits.get("mobility", .5)
                    distance = max(0.0, self.map.distance(c.location_id, self.businesses[j.business_id].location_id))
                    distance_score = max(0.0, 1 - distance / 50)
                    need_score = min(1.0, c.needs.get("food", .5) + c.needs.get("financial", .3)) / 2
                    wage_score = min(1.0, j.wage / max(1.0, self.rules.minimum_wage * 2))
                    score = (skill * .32 + education * .24 + mobility * .10 +
                             distance_score * .10 + need_score * .14 + wage_score * .10)
                    scored.append((score, j, {"skill": skill, "education": education,
                                              "mobility": mobility, "distance": distance_score,
                                              "need": need_score, "wage": wage_score}))
                if scored:
                    scored.sort(key=lambda x: (-x[0], x[1].id))
                    score, job, components = scored[0]
                    self.decision_log.append({"day": self.day, "agent": c.id,
                                              "decision": "job_search", "job": job.id,
                                              "score": round(score, 4), "weights": components})
                    if score > .28 and (self.rng.chance(.35) or c.unemployed_days > 5):
                        c.job_id, job.filled_by = job.id, c.id
                        business = self.businesses[job.business_id]
                        if c.id not in business.employees:
                            business.employees.append(c.id)
                        c.unemployed_days = 0
                        self.decision_log.append({"day": self.day, "agent": c.id, "decision": "hire", "job": job.id, "score": round(score, 4)})
            # Consume essentials using an explicit utility/affordability
            # decision.  Purchases move both currency and physical inventory.
            for product, need_key, quantity in (("food", "food", .35), ("basic", "basic", .18)):
                need = c.needs.get(need_key, .5)
                suppliers = [b for b in self.businesses.values()
                             if b.alive and b.product == product and b.inventory.get(product, 0) > 0]
                suppliers.sort(key=lambda b: (b.price, b.id))
                if suppliers and (need >= .15 or c.savings > suppliers[0].price * quantity * 4):
                    paid = self._sell_good(c, suppliers[0], product, quantity, "consumption")
                    if paid:
                        c.expenses_total += paid
                        c.needs[need_key] = max(0.0, need - (0.28 if product == "food" else 0.12))
            # Low-frequency discretionary consumption creates observable
            # demand for entertainment without bankrupting households.
            if self.day % 3 == 0:
                suppliers = [b for b in self.businesses.values() if b.alive and b.product == "entertainment" and b.inventory.get("entertainment", 0) > 0]
                suppliers.sort(key=lambda b: (b.price, b.id))
                if suppliers and c.savings > suppliers[0].price * .15:
                    paid = self._sell_good(c, suppliers[0], "entertainment", .15, "entertainment")
                    c.expenses_total += paid
            # Needs rise gradually after consumption.  Keeping values bounded
            # makes the decision trace and health checks stable over years.
            c.needs["food"] = min(1.0, c.needs.get("food", 0.0) + .055)
            c.needs["basic"] = min(1.0, c.needs.get("basic", 0.0) + .025)
            c.needs["social"] = min(1.0, c.needs.get("social", 0.0) + .02)

    def _citizen_services_and_movement(self) -> None:
        """Apply transport/education choices and give every agent a route.

        A route is intentionally simple but not random: it is a deterministic
        function of schedule, needs, job and distance.  This is enough to make
        mobility measurable and prevents a healthy home-bound citizen from
        being mistaken for a stuck agent.
        """
        for c in self.citizens.values():
            if not c.alive:
                continue
            home_location = self.houses.get(self.households.get(c.household_id, Household("x")).housing_id or "")
            home_id = home_location.location_id if home_location else "res-0"
            target = home_id
            activity = "home"
            if c.job_id and c.job_id in self.jobs:
                job = self.jobs[c.job_id]
                work = self.businesses.get(job.business_id)
                if work and self.day % 7 < 5:
                    target, activity = work.location_id, "work"
                elif self.day % 3 == 0:
                    target, activity = "market-0", "shop"
                else:
                    target, activity = "park-0", "social"
            elif self.day % 3 == 0:
                target, activity = "market-0", "shop"
            elif self.day % 7 == 6:
                target, activity = "park-0", "social"
            elif self.day % 5 == 0:
                target, activity = "transport-0", "travel"
            self._move_citizen(c, target, activity)

            # Education is a real resource decision: higher education need,
            # available cash and a low current workload increase the weight.
            if self.day % 14 == 0 and c.savings > self.rules.education_cost * 2 and c.education < .98:
                fee = min(self.rules.education_cost, c.savings * .08)
                c.savings -= fee
                c.expenses_total += fee
                self.government_cash += fee * .35
                self.resource_cash += fee * .65
                c.education = min(1.0, c.education + .012)
                c.skills["general"] = min(1.0, c.skills.get("general", .5) + .008)
                self._record_tx(c.id, "school-0", fee, "education", "study")

            # Transport is a small, explicit service flow on travel days.
            if activity == "travel" and c.savings >= self.rules.transport_cost:
                fee = float(self.rules.transport_cost)
                c.savings -= fee
                c.expenses_total += fee
                self.resource_cash += fee
                self._record_tx(c.id, "transport-0", fee, "transport", "transport")

    def _business_decisions(self) -> None:
        for b in self.businesses.values():
            if not b.alive:
                continue
            b.age_days += 1
            b.demand = sum(1 for tx in self.transactions[-max(1, len(self.citizens) * 3):]
                            if tx.seller == b.id and tx.good == b.product)
            # Production is constrained by labour and input cash.  Inputs are
            # paid to the explicit resource account, never silently deleted.
            labour_capacity = len(b.employees) * .85
            demand_signal = min(1.5, 0.5 + b.demand / max(1.0, len(self.citizens) * .08))
            planned = min(30.0, max(.25, labour_capacity * demand_signal + .25))
            unit_input_cost = self.GOODS[b.product].base_price * .07
            affordable = b.cash / max(.01, unit_input_cost)
            produced = min(planned, max(0.0, affordable))
            if produced > 0:
                input_cost = produced * unit_input_cost
                b.cash -= input_cost
                b.cost += input_cost
                self.resource_cash += input_cost
                self._record_tx(b.id, "resource-market", input_cost, "basic", "production_input")
            b.inventory[b.product] = min(500.0, max(0.0, b.inventory.get(b.product, 0.0)) + produced)
            # Price adjustment reacts slowly to demand and inventory.
            inv = b.inventory.get(b.product, 0)
            if b.demand > 5 and inv < 4:
                b.price = min(self.GOODS[b.product].base_price * 3, b.price * 1.01)
            elif inv > 25:
                b.price = max(self.GOODS[b.product].base_price * .5, b.price * .99)
            b.price = max(.1, min(self.GOODS[b.product].base_price * 3, b.price))
            # Hire/fire based on cash and observed demand.
            desired_employees = min(12, max(1, int(b.demand / 5) + 1))
            if b.demand > 5 and b.cash > b.salary * 4 and len(b.employees) < desired_employees:
                vacant_jobs = [j for j in self.jobs.values()
                                if j.business_id == b.id and j.filled_by is None]
                unemployed = [c for c in self.citizens.values() if c.alive and not c.job_id]
                unemployed.sort(key=lambda c: (-c.skills.get("general", .5), c.id))
                for job, candidate in zip(vacant_jobs, unemployed):
                    if len(b.employees) >= desired_employees:
                        break
                    candidate.job_id = job.id
                    job.filled_by = candidate.id
                    b.employees.append(candidate.id)
                    candidate.unemployed_days = 0
                    self.decision_log.append({"day": self.day, "agent": b.id,
                                              "decision": "hire", "citizen": candidate.id,
                                              "reason": "business_demand", "score": round(candidate.skills.get("general", .5), 4)})
            if b.cash < b.salary * 6 and len(b.employees) > desired_employees:
                cid = b.employees.pop()
                c = self.citizens[cid]
                if c.job_id in self.jobs:
                    self.jobs[c.job_id].filled_by = None
                c.job_id = None
                self.decision_log.append({"day": self.day, "agent": b.id, "decision": "fire", "citizen": cid, "reason": "cash"})
            elif b.cash < b.salary * 2 and b.employees:
                cid = b.employees.pop()
                c = self.citizens[cid]
                if c.job_id in self.jobs:
                    self.jobs[c.job_id].filled_by = None
                c.job_id = None
                self.decision_log.append({"day": self.day, "agent": b.id, "decision": "fire", "citizen": cid, "reason": "cash_floor"})
            # Firms with a sustained empty shop can close; default MiniCity
            # parameters keep most firms alive but policy experiments can
            # still expose business survival differences.
            if b.cash < -500 and b.age_days > 30:
                b.alive = False
                for cid in b.employees:
                    self.citizens[cid].job_id = None
                b.employees.clear()

    def _housing_and_household_costs(self) -> None:
        if self.day % 30 != 0:
            return
        for hh in self.households.values():
            if not hh.housing_id:
                continue
            h = self.houses[hh.housing_id]
            rent = max(0.0, h.rent - self.rules.rent_subsidy)
            per_member = rent / max(1, len(hh.member_ids))
            paid = 0.0
            for cid in hh.member_ids:
                c = self.citizens[cid]
                part = min(per_member, max(0.0, c.savings))
                c.savings -= part
                paid += part
                c.expenses_total += part
                self.landlord_cash += part
                self._record_tx(cid, "landlord-pool", part, "housing", "rent")
            unpaid = max(0.0, rent - paid)
            subsidy = 0.0
            if unpaid and self.rules.welfare_parameter > 0:
                subsidy = min(unpaid * self.rules.welfare_parameter, self.government_cash)
                self.government_cash -= subsidy
                self.landlord_cash += subsidy
                self.welfare_paid += subsidy
                self._record_tx("government", "landlord-pool", subsidy, "housing", "welfare_rent")
            hh.shared_expenses += paid + subsidy
            hh.shared_resources = sum(max(0.0, self.citizens[cid].savings) for cid in hh.member_ids)

            # A household can relocate when it repeatedly cannot cover rent.
            # The score is deterministic and uses capacity/quality/price, not
            # an opaque random teleport.
            if unpaid > 0:
                candidates = [x for x in self.houses.values()
                             if x.id != h.id and len(x.occupants) + len(hh.member_ids) <= x.capacity
                             and x.rent <= h.rent]
                candidates.sort(key=lambda x: (x.rent, -x.quality, x.id))
                if candidates:
                    new_h = candidates[0]
                    for cid in hh.member_ids:
                        if cid in h.occupants:
                            h.occupants.remove(cid)
                        new_h.occupants.append(cid)
                        self.citizens[cid].last_activity = "moving"
                    hh.housing_id = new_h.id
                    self._event_seq += 1
                    self.events.append(Event(f"event-{self._event_seq:05d}", self.day,
                                             "move", new_h.location_id,
                                             f"Household {hh.id} moved to {new_h.id}", hh.id,
                                             0, "location"))

    def _social_and_information(self) -> None:
        # Communication updates multiple relationship dimensions separately.
        if self.day % 3 == 0:
            update_social_network(self.social_network, self.citizens.values(), day=self.day)
        for rel in sorted(self.relationships.values(), key=lambda x: x.id):
            if self.rng.chance(.08):
                rel.communication_frequency = min(1.0, rel.communication_frequency + .04)
                rel.familiarity = min(1.0, rel.familiarity + .02)
                rel.trust = max(0.0, min(1.0, rel.trust + self.rng.uniform(-.01, .015)))
                rel.conflict = max(0.0, min(1.0, rel.conflict + self.rng.uniform(-.01, .01)))
        if self.day % 7 == 0:
            self.social_network.decay(7)
        if self.day % 30 == 0:
            self._event_seq += 1
            source = self.rng.choice(sorted(self.citizens))
            event = Event(f"event-{self._event_seq:05d}", self.day, "news",
                          self.citizens[source].location_id,
                          "monthly market conditions", source, 0, "media")
            event.spread = sum(1 for _ in range(self.rng.randint(1, 5)))
            self.events.append(event)
            item = InformationItem(event.id, "news", event.text, event.time,
                                   event.location_id, event.source, "media")
            self.information_system.publish(item, self.citizens.values())
        # Seed a neutral virtual-world information item once a quarter; there
        # is deliberately no real-world political content in the simulation.
        if self.day % 90 == 0:
            self._event_seq += 1
            event = Event(f"event-{self._event_seq:05d}", self.day, "rumor",
                          "market-0", "a new market opportunity is circulating", None, 0, "relationship")
            self.events.append(event)
            self.information_system.publish(InformationItem(event.id, "rumor", event.text,
                                                             event.time, event.location_id, None,
                                                             "relationship", .55), self.citizens.values())
        self.information_system.propagate(self.day, self.citizens.values(), self.social_network)

    def _age_and_cleanup(self) -> None:
        for c in self.citizens.values():
            # Age parameter is annualized; no random death in the demo keeps
            # population stable so experiments compare policies on equal
            # populations.
            if self.day % 365 == 0:
                c.age += 1
            c.needs = {k: max(0.0, min(1.0, float(v))) for k, v in c.needs.items()}

    # ----- observability, snapshots, persistence ------------------------------
    def total_money(self) -> float:
        """Total currency across tracked accounts (conservation invariant)."""
        return float(sum(max(0.0, c.savings) for c in self.citizens.values()) +
                     sum(b.cash for b in self.businesses.values()) +
                     self.government_cash + self.landlord_cash + self.resource_cash)

    def total_inventory(self) -> float:
        return float(sum(max(0.0, float(q)) for b in self.businesses.values()
                         for q in b.inventory.values()) +
                     sum(max(0.0, float(q)) for c in self.citizens.values()
                         for q in c.inventory.values()))

    @staticmethod
    def _gini(values: List[float]) -> float:
        xs = sorted(max(0.0, float(x)) for x in values)
        total = sum(xs)
        if not xs or total <= 1e-12:
            return 0.0
        n = len(xs)
        return sum((2 * i - n - 1) * x for i, x in enumerate(xs, 1)) / (n * total)

    def metrics(self) -> Dict[str, float]:
        incomes = [c.income for c in self.citizens.values()]
        savings = [c.savings for c in self.citizens.values()]
        employed = sum(1 for c in self.citizens.values() if c.job_id and c.alive)
        occupied_people = sum(len(h.occupants) for h in self.houses.values())
        capacity = sum(h.capacity for h in self.houses.values())
        prices = [b.price for b in self.businesses.values() if b.alive]
        consumed = sum(1 for tx in self.transactions if tx.time == self.day and tx.reason == "consumption")
        population = sum(c.alive for c in self.citizens.values())
        employment_rate = employed / max(1, population)
        average_income_today = sum(incomes) / max(1, len(incomes))
        average_daily_income = sum(c.income_total for c in self.citizens.values()) / max(1, self.day * max(1, population))
        movement = sum(len(set(c.movement_history[-30:])) > 1 for c in self.citizens.values()) / max(1, population)
        social_metrics = self.social_network.metrics(list(self.citizens))
        total = self.total_money()
        return {
            "day": self.day,
            "population": population,
            "employment": employment_rate,
            "employment_rate": employment_rate,
            "employed_count": employed,
            "average_income": average_daily_income,
            "average_income_today": average_income_today,
            "income_total": sum(c.income_total for c in self.citizens.values()),
            "median_savings": median(savings) if savings else 0.0,
            "savings_gini": self._gini(savings),
            "business_count": sum(b.alive for b in self.businesses.values()),
            "business_survival": sum(b.alive for b in self.businesses.values()) / max(1, len(self.businesses)),
            "average_price": sum(prices) / max(1, len(prices)),
            "prices": sum(prices) / max(1, len(prices)),
            "housing_occupancy": occupied_people / max(1, capacity),
            "consumption": consumed,
            "transactions": len(self.transactions),
            "transaction_volume": sum(tx.amount for tx in self.transactions if tx.time == self.day),
            "social_relationships": len(self.relationships),
            "social_clustering": float(social_metrics.get("connected_components", 0)),
            "mobility": movement,
            "government_cash": self.government_cash,
            "landlord_cash": self.landlord_cash,
            "resource_cash": self.resource_cash,
            "money_total": total,
            "money_conservation_error": total - self._initial_money,
            "inventory_total": self.total_inventory(),
        }

    def take_snapshot(self) -> Snapshot:
        s = Snapshot(self.day, self.metrics(),
                     {k: {"savings": v.savings, "job_id": v.job_id, "location_id": v.location_id} for k, v in self.citizens.items()},
                     {k: {"cash": v.cash, "inventory": dict(v.inventory), "alive": v.alive} for k, v in self.businesses.items()}, len(self.events))
        self.snapshots.append(s)
        return s

    def snapshot(self) -> Dict:
        """UI/experiment-friendly live snapshot."""
        return self.to_dict()

    def health_check(self) -> HealthReport:
        issues: List[str] = []
        for c in self.citizens.values():
            numeric = [c.savings, c.income, c.income_total, c.expenses_total]
            if not all(math.isfinite(float(x)) for x in numeric) or c.savings < -1e-6:
                issues.append(f"invalid citizen money:{c.id}")
            if c.location_id and c.location_id not in self.map.locations:
                issues.append(f"invalid location:{c.id}")
            if len(c.movement_history) >= 30 and len(set(c.movement_history[-30:])) <= 1:
                # A truly unchanged route for a month is a diagnostic, while
                # ordinary weekends/home days do not trigger it.
                issues.append(f"agent stuck:{c.id}")
        for b in self.businesses.values():
            if not math.isfinite(float(b.cash)) or any(v < -1e-6 or not math.isfinite(float(v)) for v in b.inventory.values()):
                issues.append(f"invalid business state:{b.id}")
            if any(float(v) > 500.0001 for v in b.inventory.values()):
                issues.append(f"infinite inventory:{b.id}")
        if not math.isfinite(self.total_money()) or self.total_money() > self._initial_money * 1.05 + 1:
            issues.append("money explosion")
        if self.day > 30 and self.day - self._last_transaction_day > 14:
            issues.append("no transactions")
        if not any(b.alive for b in self.businesses.values()):
            issues.append("all businesses dead")
        unemployed_available = any(c.alive and not c.job_id for c in self.citizens.values())
        for b in self.businesses.values():
            cond = (b.alive and b.open_positions > 0 and b.age_days > 60 and
                    b.demand > 10 and b.cash > b.salary * 4 and not b.employees and unemployed_available)
            self._deadlock_streaks[b.id] = self._deadlock_streaks.get(b.id, 0) + 1 if cond else 0
            if self._deadlock_streaks[b.id] >= 14:
                issues.append("company deadlock")
        if self.day > 30 and all(len(c.movement_history) <= 1 for c in self.citizens.values()):
            issues.append("population freeze")
        return HealthReport(self.day, not issues, issues)

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        data = self.to_dict()
        data["snapshots"] = to_dict(self.snapshots)
        data["health_reports"] = to_dict(self.health_reports)
        data["rng_state"] = to_dict(self.rng.state())
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "SimulationEngine":
        """Load a JSON state produced by :meth:`save`."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(data)

    def to_dict(self) -> Dict:
        """Return a complete JSON-friendly live state for dashboards/save-load."""
        return {"day": self.day, "seed": self.config.seed, "config": to_dict(self.config),
                "map": to_dict(self.map), "metrics": self.metrics(),
                "citizens": to_dict(self.citizens), "households": to_dict(self.households),
                "businesses": to_dict(self.businesses), "houses": to_dict(self.houses),
                "jobs": to_dict(self.jobs), "relationships": to_dict(self.relationships),
                "events": to_dict(self.events), "transactions": to_dict(self.transactions),
                "rules": to_dict(self.rules),
                "accounts": {"government_cash": self.government_cash,
                             "landlord_cash": self.landlord_cash,
                             "resource_cash": self.resource_cash,
                             "welfare_paid": self.welfare_paid,
                             "initial_money": self._initial_money,
                             "initial_inventory": self._initial_inventory},
                "decision_log": to_dict(self.decision_log[-10000:])}

    @classmethod
    def from_dict(cls, data: Dict) -> "SimulationEngine":
        """Restore a complete engine state produced by :meth:`to_dict`.

        Unknown future fields are ignored, making saved experiments forwards
        compatible.  ``save`` files are report-oriented; use this method with
        a ``to_dict`` payload when exact continuation is required.
        """
        config_data = dict(data.get("config") or {})
        config_data.setdefault("seed", int(data.get("seed", 1)))
        # Old reports may contain fields not present in the current config.
        config_fields = set(SimulationConfig.__dataclass_fields__)
        config_data = {k: v for k, v in config_data.items() if k in config_fields}
        e = cls(SimulationConfig(**config_data))

        def restore(mapping, klass):
            if not mapping:
                return {} if klass is not Event else []
            if isinstance(mapping, list):
                return [klass(**v) for v in mapping]
            return {k: klass(**v) for k, v in mapping.items()}

        def restore_citizens(mapping):
            result = {}
            for k, v in (mapping or {}).items():
                item = dict(v)
                from .models import Schedule
                if isinstance(item.get("schedule"), dict):
                    item["schedule"] = Schedule(**item["schedule"])
                result[k] = Citizen(**item)
            return result

        def restore_map(mapping):
            if not mapping:
                return e.map
            locations = {k: Location(**v) for k, v in (mapping.get("locations") or {}).items()}
            return MapGrid(int(mapping.get("width", e.config.width)),
                          int(mapping.get("height", e.config.height)), locations,
                          dict(mapping.get("citizen_positions") or {}))
        e.day = int(data.get("day", 0))
        if data.get("rules"):
            rule_fields = set(InstitutionRules.__dataclass_fields__)
            e.rules = InstitutionRules(**{k: v for k, v in data["rules"].items() if k in rule_fields})
        if data.get("citizens"):
            e.citizens = restore_citizens(data["citizens"])
        if data.get("households"):
            e.households = restore(data["households"], Household)
        if data.get("businesses"):
            e.businesses = restore(data["businesses"], Business)
        if data.get("houses"):
            e.houses = restore(data["houses"], Housing)
        if data.get("jobs"):
            e.jobs = restore(data["jobs"], Job)
        if data.get("relationships"):
            e.relationships = restore(data["relationships"], Relationship)
        if data.get("events"):
            e.events = restore(data["events"], Event)
        if data.get("transactions"):
            e.transactions = restore(data["transactions"], Transaction)
        if data.get("snapshots"):
            e.snapshots = [Snapshot(**v) for v in data["snapshots"]]
        if data.get("health_reports"):
            e.health_reports = [HealthReport(**v) for v in data["health_reports"]]
        if data.get("map"):
            e.map = restore_map(data["map"])
        accounts = data.get("accounts") or {}
        e.government_cash = float(accounts.get("government_cash", e.rules.government_budget))
        e.landlord_cash = float(accounts.get("landlord_cash", 0.0))
        e.resource_cash = float(accounts.get("resource_cash", 0.0))
        e.welfare_paid = float(accounts.get("welfare_paid", 0.0))
        e.decision_log = list(data.get("decision_log") or [])
        e._tx_seq = len(e.transactions)
        e._event_seq = len(e.events)
        e._job_seq = len(e.jobs)
        e.social_network.relationships = e.relationships
        e._position_history = {cid: list(c.movement_history or [c.location_id or "res-0"])
                               for cid, c in e.citizens.items()}
        e._last_transaction_day = max((int(t.time) for t in e.transactions), default=e.day)
        def tupleize(value):
            return tuple(tupleize(x) for x in value) if isinstance(value, list) else value
        if data.get("rng_state"):
            try:
                e.rng.set_state(tupleize(data["rng_state"]))
            except (TypeError, ValueError):
                # Older snapshots did not persist RNG state; they remain
                # readable, but exact continuation is only promised for new
                # save files.
                pass
        e._initial_money = float(accounts.get("initial_money", e.total_money()))
        e._initial_inventory = float(accounts.get("initial_inventory", e.total_inventory()))
        return e

    def annual_report(self) -> Dict:
        m = self.metrics()
        issue_counts: Dict[str, int] = {}
        for report in self.health_reports:
            for issue in report.issues:
                key = issue.split(":", 1)[0]
                issue_counts[key] = issue_counts.get(key, 0) + 1
        return {"title": "Digital Society Sandbox Annual Report", "simulation_only": True,
                "warning": "Results are simulated outcomes, not real-world policy predictions.",
                "seed": self.config.seed, "days": self.day, "metrics": m,
                "health_ok": all(r.ok for r in self.health_reports), "health_issue_counts": issue_counts,
                "transaction_count": len(self.transactions),
                "snapshot_count": len(self.snapshots),
                "emergence": {"commercial_center": max((sum(1 for b in self.businesses.values()
                    if b.alive and b.location_id == loc) for loc in self.map.locations), default=0) >= 3,
                               "housing_pressure": m["housing_occupancy"] >= .9,
                               "wealth_inequality": m["savings_gini"] >= .35,
                               "population_mobility": m["mobility"]},
                "disclaimer": "Simulation result only; it is not a prediction of real-world society or policy."}

    def set_rule(self, key: str, value: float) -> None:
        """Set and validate one virtual-world institution parameter."""
        aliases = {"welfare": "welfare_parameter", "tax": "tax_rate"}
        key = aliases.get(key, key)
        if not hasattr(self.rules, key):
            raise KeyError(key)
        value = float(value)
        if key in {"tax_rate", "business_tax_rate"} and not 0 <= value <= 1:
            raise ValueError(f"{key} must be in [0, 1]")
        if key not in {"tax_rate", "business_tax_rate"} and value < 0:
            raise ValueError(f"{key} must be non-negative")
        setattr(self.rules, key, value)

    def apply_policy(self, policy) -> None:
        """Apply a mapping/dataclass of virtual-world rules in place."""
        values = policy if isinstance(policy, dict) else getattr(policy, "__dict__", {})
        for key, value in values.items():
            if key == "business_rules":
                self.rules.business_rules = dict(value or {})
            elif hasattr(self.rules, key):
                self.set_rule(key, value)

    @classmethod
    def mini_city(cls, seed: int = 1) -> "SimulationEngine":
        return cls(SimulationConfig(seed=seed, citizens=100, businesses=20, houses=30, days=365))


def run_mini_city(seed: int = 1, days: int = 365) -> SimulationEngine:
    engine = SimulationEngine.mini_city(seed)
    engine.run(days=days)
    return engine


def build_minicity(seed: int = 1) -> SimulationEngine:
    """Canonical factory used by the desktop app and smoke tests."""
    return SimulationEngine.mini_city(seed)
