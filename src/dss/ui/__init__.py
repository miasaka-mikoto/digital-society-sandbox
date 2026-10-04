"""Tkinter user interface for Digital Society Sandbox.

The UI is deliberately kept separate from the simulation engine.  It can be
used with a real simulation object or with the deterministic demo adapter.
"""

from .app import DigitalSocietyApp, run_app

__all__ = ["DigitalSocietyApp", "run_app"]

