"""Launch Digital Society Sandbox desktop UI.

The source tree is intentionally runnable without installation (``python
app.py``), so add the local ``src`` directory when needed.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from dss.ui.app import run_app

if __name__ == "__main__":
    run_app()
