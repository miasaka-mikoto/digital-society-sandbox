"""Compatibility factory for scripts and external experiment harnesses."""
from .core.engine import SimulationEngine, SimulationConfig, build_minicity, run_mini_city

__all__ = ["SimulationEngine", "SimulationConfig", "build_minicity", "run_mini_city"]
