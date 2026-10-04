"""Institution rules and same-seed policy experiment helpers."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Callable, Dict, Mapping, Optional

from dss.core.models import InstitutionRules


@dataclass
class PolicyParameters:
    """Scenario-owned virtual-world rules; not claims about real policies."""
    tax_rate: float = 0.05
    minimum_wage: float = 15.0
    education_cost: float = 15.0
    transport_cost: float = 2.0
    welfare_parameter: float = 0.0
    business_tax_rate: float = 0.05
    rent_subsidy: float = 0.0
    government_budget: float = 5000.0
    business_rules: Dict[str, float] = field(default_factory=dict)

    @classmethod
    def from_rules(cls, rules: InstitutionRules) -> "PolicyParameters":
        return cls(**{k: getattr(rules, k) for k in (
            "tax_rate", "minimum_wage", "education_cost", "transport_cost",
            "welfare_parameter", "business_tax_rate", "rent_subsidy", "government_budget")})

    def to_rules(self) -> InstitutionRules:
        return InstitutionRules(**{k: getattr(self, k) for k in (
            "tax_rate", "minimum_wage", "education_cost", "transport_cost",
            "welfare_parameter", "business_tax_rate", "rent_subsidy", "government_budget")})

    def validate(self) -> None:
        for name in ("tax_rate", "business_tax_rate"):
            value = getattr(self, name)
            if not 0 <= value <= 1: raise ValueError(f"{name} must be in [0,1]")
        for name in ("minimum_wage", "education_cost", "transport_cost", "rent_subsidy", "government_budget"):
            if getattr(self, name) < 0: raise ValueError(f"{name} must be non-negative")

    def merged(self, overrides: Mapping[str, Any]) -> "PolicyParameters":
        data = self.__dict__.copy(); data.update(overrides)
        data["business_rules"] = dict(data.get("business_rules", {}))
        self2 = PolicyParameters(**data); self2.validate(); return self2


@dataclass
class PolicyExperiment:
    name: str
    overrides: Dict[str, Any]
    description: str = "Virtual-world parameter experiment"


def apply_policy(rules: InstitutionRules, overrides: Mapping[str, Any]) -> InstitutionRules:
    """Return a validated copy without mutating baseline rules."""
    params = PolicyParameters.from_rules(rules).merged(overrides)
    return params.to_rules()


def run_policy_experiment(
    simulate: Callable[..., Mapping[str, Any]],
    baseline: PolicyParameters | InstitutionRules,
    experiment: PolicyExperiment,
    *, seed: int, **kwargs: Any,
) -> dict:
    """Run baseline and treatment with exactly the same seed and arguments.

    ``simulate`` must accept ``rules=`` and ``seed=`` and return metrics.  The
    result is explicitly labelled simulation output, never a real-world
    forecast.
    """
    base = baseline if isinstance(baseline, PolicyParameters) else PolicyParameters.from_rules(baseline)
    base.validate(); treatment = base.merged(experiment.overrides)
    left = dict(simulate(rules=base.to_rules(), seed=int(seed), **kwargs))
    right = dict(simulate(rules=treatment.to_rules(), seed=int(seed), **kwargs))
    metric_names = sorted(set(left) | set(right))
    delta = {k: right.get(k, 0) - left.get(k, 0) for k in metric_names if isinstance(right.get(k, 0), (int, float)) and isinstance(left.get(k, 0), (int, float))}
    return {"name": experiment.name, "seed": int(seed), "baseline": left, "treatment": right,
            "delta": delta, "interpretation": "simulation result; not a real-world policy prediction"}


__all__ = ["PolicyParameters", "PolicyExperiment", "apply_policy", "run_policy_experiment"]
