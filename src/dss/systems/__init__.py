"""Deterministic, inspectable simulation subsystems."""

from .economy import Economy, Good as EconomyGood, Transaction, TransactionLedger
from .labor import LaborMarket, JobPosting, BusinessDecisionSystem
from .housing import HousingSystem, House
from .education import EducationSystem, Course
from .social import SocialNetwork, relationship_id, update_social_network, social_network_from_engine
from .information import InformationItem, Exposure, MediaChannel, InformationSystem, information_system_from_engine
from .policy import PolicyParameters, PolicyExperiment, apply_policy, run_policy_experiment
from .emergence import macro_metrics, detect_emergence, macro_metrics_from_engine, detect_emergence_from_engine

# ``Good`` is the economy-level enum for callers importing from dss.systems;
# the core dataclass Good remains available from dss.core.
Good = EconomyGood

__all__ = [
    "Economy", "Good", "EconomyGood", "Transaction", "TransactionLedger",
    "LaborMarket", "JobPosting", "BusinessDecisionSystem", "HousingSystem", "House",
    "EducationSystem", "Course", "SocialNetwork", "relationship_id",
    "update_social_network", "social_network_from_engine", "InformationItem", "Exposure",
    "MediaChannel", "InformationSystem", "information_system_from_engine",
    "PolicyParameters", "PolicyExperiment", "apply_policy", "run_policy_experiment",
    "macro_metrics", "detect_emergence", "macro_metrics_from_engine",
    "detect_emergence_from_engine",
]
