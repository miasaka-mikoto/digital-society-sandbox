"""Money, goods and transaction accounting for the sandbox.

The module deliberately does not require a particular World implementation.  Objects
with ``cash``, ``inventory`` and ``skills`` attributes (or dictionaries) are enough,
which lets the simulation engine evolve without coupling all systems together.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable
import math


class Good(str, Enum):
    FOOD = "Food"
    HOUSING = "Housing"
    ENTERTAINMENT = "Entertainment"
    EDUCATION = "Education"
    TRANSPORT = "Transport"
    BASIC = "Basic Goods"


def _get(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _set(obj: Any, name: str, value: Any) -> None:
    if isinstance(obj, dict):
        obj[name] = value
    else:
        setattr(obj, name, value)


def _inventory(obj: Any) -> dict[str, float]:
    inv = _get(obj, "inventory")
    if inv is None:
        inv = {}
        _set(obj, "inventory", inv)
    return inv


@dataclass(frozen=True)
class Transaction:
    buyer: str
    seller: str
    amount: float
    good: str
    time: float | int
    reason: str
    quantity: float = 1.0


class TransactionLedger:
    """Append-only ledger with basic invariant checks and filtering."""

    def __init__(self) -> None:
        self.entries: list[Transaction] = []

    def record(self, buyer: Any, seller: Any, amount: float, good: str,
               time: float | int, reason: str, quantity: float = 1.0) -> Transaction:
        amount, quantity = float(amount), float(quantity)
        if not (math.isfinite(amount) and amount >= 0):
            raise ValueError("transaction amount must be finite and non-negative")
        if not (math.isfinite(quantity) and quantity >= 0):
            raise ValueError("transaction quantity must be finite and non-negative")
        tx = Transaction(str(_get(buyer, "agent_id", _get(buyer, "id", "government" if isinstance(buyer, Economy) else buyer))),
                         str(_get(seller, "agent_id", _get(seller, "id", "government" if isinstance(seller, Economy) else seller))),
                         amount, str(good), time, str(reason), quantity)
        self.entries.append(tx)
        return tx

    def by_day(self, day: int) -> list[Transaction]:
        return [e for e in self.entries if int(e.time) == int(day)]

    def total(self, *, good: str | None = None, reason: str | None = None) -> float:
        return sum(e.amount for e in self.entries
                   if (good is None or e.good == good) and
                   (reason is None or e.reason == reason))

    def as_dicts(self) -> list[dict[str, Any]]:
        return [e.__dict__.copy() for e in self.entries]


@dataclass
class Economy:
    prices: dict[str, float] = field(default_factory=lambda: {
        "food": 5.0, "housing": 20.0, "entertainment": 8.0,
        "education": 12.0, "transport": 3.0, "basic": 7.0,
    })
    tax_rate: float = 0.05
    minimum_wage: float = 10.0
    education_cost: float = 12.0
    transport_cost: float = 3.0
    welfare_parameter: float = 0.0
    government_cash: float = 0.0
    ledger: TransactionLedger = field(default_factory=TransactionLedger)

    def __post_init__(self) -> None:
        self.validate_rules()

    def validate_rules(self) -> None:
        if not 0 <= self.tax_rate <= 1:
            raise ValueError("tax_rate must be in [0, 1]")
        if self.minimum_wage < 0 or self.education_cost < 0 or self.transport_cost < 0:
            raise ValueError("costs and minimum wage must be non-negative")
        if any(v < 0 or not math.isfinite(v) for v in self.prices.values()):
            raise ValueError("prices must be finite and non-negative")

    @staticmethod
    def balance(obj: Any) -> float:
        # Core Citizen stores money as ``savings`` and exposes a cash property;
        # dictionary fixtures often only provide one of these names.
        value = _get(obj, "cash", None)
        if value is None:
            value = _get(obj, "money", _get(obj, "savings", 0.0))
        return float(value)

    @staticmethod
    def set_balance(obj: Any, value: float) -> None:
        if not math.isfinite(value):
            raise ValueError("invalid balance")
        _set(obj, "cash", float(value))

    def transfer(self, buyer: Any, seller: Any, amount: float, good: str,
                 time: float | int, reason: str, quantity: float = 1.0) -> bool:
        amount = float(amount)
        if amount < 0 or not math.isfinite(amount):
            raise ValueError("invalid transfer amount")
        if self.balance(buyer) + 1e-9 < amount:
            return False
        self.set_balance(buyer, self.balance(buyer) - amount)
        # government is represented by Economy itself; its balance is separate.
        if seller is self:
            self.government_cash += amount
        else:
            self.set_balance(seller, self.balance(seller) + amount)
        self.ledger.record(buyer, seller, amount, good, time, reason, quantity)
        return True

    def purchase(self, buyer: Any, seller: Any, good: str, quantity: float,
                 time: float | int, *, unit_price: float | None = None,
                 reason: str = "purchase") -> bool:
        quantity = float(quantity)
        key = (good.value if isinstance(good, Good) else str(good)).lower()
        price = self.prices.get(key, 0.0) if unit_price is None else float(unit_price)
        if quantity <= 0 or price < 0 or not math.isfinite(price):
            return False
        # Education, transport and other services can be sold without a
        # physical inventory.  A normal business still must have stock.
        stock = _inventory(seller)
        service_sale = seller is self or bool(_get(seller, "service_provider", False))
        if not service_sale and float(stock.get(key, stock.get(str(good), 0.0))) + 1e-9 < quantity:
            return False
        if not self.transfer(buyer, seller, quantity * price, key, time, reason, quantity):
            return False
        if not service_sale:
            stock[key] = float(stock.get(key, stock.get(str(good), 0.0))) - quantity
            _inventory(buyer)[key] = float(_inventory(buyer).get(key, 0.0)) + quantity
        return True

    def pay_salary(self, business: Any, citizen: Any, amount: float,
                   time: float | int, *, reason: str = "salary") -> bool:
        return self.transfer(business, citizen, amount, Good.BASIC, time, reason)

    def collect_tax(self, citizen: Any, amount: float, time: float,
                    *, reason: str = "tax") -> bool:
        return self.transfer(citizen, self, amount, Good.BASIC, time, reason)

    def apply_income_tax(self, citizen: Any, income: float, time: float) -> float:
        due = max(0.0, float(income) * self.tax_rate)
        if self.collect_tax(citizen, due, time):
            return due
        return 0.0

    def pay_rent(self, citizen: Any, landlord: Any, rent: float, time: float) -> bool:
        return self.transfer(citizen, landlord, rent, Good.HOUSING, time, "rent")

    def government_spend(self, recipient: Any, amount: float, good: str,
                         time: float, reason: str = "government_spending") -> bool:
        amount = float(amount)
        if amount < 0 or self.government_cash < amount:
            return False
        self.government_cash -= amount
        self.set_balance(recipient, self.balance(recipient) + amount)
        self.ledger.record(self, recipient, amount, good, time, reason)
        return True

    def validate_state(self, actors: Iterable[Any]) -> list[str]:
        errors: list[str] = []
        for a in actors:
            cash = self.balance(a)
            if not math.isfinite(cash):
                errors.append(f"NaN cash: {_get(a, 'agent_id', a)}")
            inv = _inventory(a)
            for g, q in inv.items():
                if not math.isfinite(float(q)) or float(q) < -1e-9:
                    errors.append(f"invalid inventory {g}: {_get(a, 'agent_id', a)}")
        return errors
