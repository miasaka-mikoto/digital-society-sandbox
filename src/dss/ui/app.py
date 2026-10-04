"""Desktop dashboard for Digital Society Sandbox.

This module only depends on the Python standard library.  The simulation
engine is intentionally duck-typed: any object exposing ``step`` and a
snapshot-like state can be supplied.  A small deterministic demo simulation is
provided so the application remains useful before the engine is installed.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Optional

try:  # Tk is optional for headless servers and frozen CLI smoke tests.
    import tkinter as tk
    from tkinter import messagebox, ttk
except ImportError:  # pragma: no cover - depends on host packaging
    tk = None
    messagebox = None
    ttk = None


def _get(obj: Any, key: str, default: Any = None) -> Any:
    """Get a field from dicts or simple Python objects."""
    if obj is None:
        return default
    if isinstance(obj, Mapping):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _items(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, Mapping):
        return list(value.values())
    try:
        return list(value)
    except TypeError:
        return []


@dataclass
class DemoSimulation:
    """Deterministic miniature model used when no engine is available.

    It is not intended as a scientific model; it supplies realistic-looking
    state to exercise the visualization and makes the UI immediately usable.
    """

    seed: int = 42
    day: int = 0
    rng: random.Random = field(init=False)
    citizens: list[dict[str, Any]] = field(default_factory=list)
    businesses: list[dict[str, Any]] = field(default_factory=list)
    houses: list[dict[str, Any]] = field(default_factory=list)
    transactions: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    rules: dict[str, float] = field(default_factory=lambda: {
        "tax_rate": 0.05, "minimum_wage": 12.0, "education_cost": 10.0,
        "transport_cost": 2.0, "welfare": 25.0,
    })

    def __post_init__(self) -> None:
        self.rng = random.Random(self.seed)
        for i in range(30):
            self.houses.append({"id": f"H{i+1}", "x": 30 + (i % 10) * 55,
                               "y": 70 + (i // 10) * 100, "capacity": 4,
                               "occupancy": 1 + i % 3, "rent": 400 + (i % 4) * 75,
                               "quality": 0.5 + (i % 5) * 0.1})
        for i in range(20):
            self.businesses.append({"id": f"B{i+1}", "x": 160 + (i % 10) * 55,
                                    "y": 275 + (i // 2) * 45,
                                    "sector": ["Food", "Basic Goods", "Entertainment", "Transport"][i % 4],
                                    "employees": 2 + i % 8, "revenue": 5000 + i * 120,
                                    "cash": 10000 + i * 170, "price": 8 + i % 5})
        for i in range(100):
            h = self.houses[i % len(self.houses)]
            self.citizens.append({"id": f"C{i+1:03}", "x": h["x"], "y": h["y"],
                                  "home": h["id"], "age": 18 + i % 55,
                                  "income": 1800 + (i % 10) * 180,
                                  "savings": 500 + (i * 97) % 6000,
                                  "employed": i % 8 != 0, "target_x": h["x"], "target_y": h["y"]})

    def step(self, days: int = 1) -> None:
        for _ in range(max(1, int(days))):
            self.day += 1
            for c in self.citizens:
                if self.rng.random() < 0.7:
                    b = self.businesses[self.rng.randrange(len(self.businesses))]
                    c["target_x"], c["target_y"] = b["x"], b["y"]
                c["x"] += (c["target_x"] - c["x"]) * 0.32
                c["y"] += (c["target_y"] - c["y"]) * 0.32
                if c["employed"]:
                    c["savings"] += c["income"] / 30 - 20
                else:
                    c["savings"] = max(0, c["savings"] - 4)
                if self.rng.random() < 0.2:
                    b = self.businesses[self.rng.randrange(len(self.businesses))]
                    self.transactions.append({"buyer": c["id"], "seller": b["id"],
                                              "amount": round(4 + self.rng.random() * 40, 2),
                                              "good": b["sector"], "time": self.day,
                                              "reason": "consumption"})
            if self.rng.random() < 0.05:
                self.events.append({"time": self.day, "kind": "market", "text": "Demand signal updated"})
            self.transactions = self.transactions[-500:]
            self.events = self.events[-100:]

    def snapshot(self) -> dict[str, Any]:
        employed = sum(1 for c in self.citizens if c["employed"])
        return {"day": self.day, "citizens": self.citizens, "businesses": self.businesses,
                "houses": self.houses, "transactions": self.transactions,
                "events": self.events, "rules": self.rules,
                "metrics": {"population": len(self.citizens), "employment": employed,
                             "employment_rate": employed / max(1, len(self.citizens)),
                             "average_income": sum(c["income"] for c in self.citizens) / max(1, len(self.citizens)),
                             "median_savings": sorted(c["savings"] for c in self.citizens)[len(self.citizens)//2],
                             "business_count": len(self.businesses),
                             "prices": 8.6, "housing_occupancy": sum(h["occupancy"] for h in self.houses) / sum(h["capacity"] for h in self.houses),
                             "consumption": len(self.transactions), "social_clustering": 0.38}}


class SimulationAdapter:
    """Normalize engine state into a UI-friendly snapshot."""

    def __init__(self, simulation: Any = None):
        if simulation is not None:
            self.simulation = simulation
            return
        # Prefer the real deterministic MiniCity engine when present.  The
        # local demo remains a graceful fallback for a source-only checkout.
        try:
            from dss.core.engine import build_minicity
            self.simulation = build_minicity(seed=1)
        except Exception:
            self.simulation = DemoSimulation()

    def step(self, days: int = 1) -> None:
        fn = getattr(self.simulation, "step", None) or getattr(self.simulation, "run_day", None)
        if fn:
            try:
                fn(days)
            except TypeError:
                for _ in range(days):
                    fn()

    def snapshot(self) -> dict[str, Any]:
        fn = getattr(self.simulation, "snapshot", None) or getattr(self.simulation, "get_snapshot", None)
        state = fn() if callable(fn) else getattr(self.simulation, "state", self.simulation)
        if isinstance(state, Mapping):
            result = dict(state)
        else:
            result = {k: getattr(state, k, None) for k in ("day", "citizens", "businesses", "houses", "transactions", "events", "rules", "metrics", "map")}
        if callable(result.get("metrics")):
            result["metrics"] = result["metrics"]()
        result.setdefault("day", getattr(self.simulation, "day", 0))
        world = getattr(self.simulation, "world", None)
        result.setdefault("citizens", getattr(self.simulation, "citizens", getattr(world, "citizens", [])))
        result.setdefault("businesses", getattr(self.simulation, "businesses", getattr(world, "businesses", [])))
        result.setdefault("houses", getattr(self.simulation, "houses", getattr(world, "houses", [])))
        result.setdefault("map", getattr(self.simulation, "map", None))
        result.setdefault("transactions", getattr(self.simulation, "transactions", []))
        result.setdefault("events", getattr(self.simulation, "events", []))
        result.setdefault("rules", getattr(self.simulation, "rules", {}))
        result.setdefault("metrics", self._metrics(result))
        # Keep the dashboard vocabulary stable across engine versions.
        metrics = result["metrics"] if isinstance(result.get("metrics"), Mapping) else {}
        if "prices" not in metrics and "average_price" in metrics:
            metrics["prices"] = metrics["average_price"]
        if "social_clustering" not in metrics and "social_relationships" in metrics:
            metrics["social_clustering"] = min(1.0, float(metrics["social_relationships"]) / max(1, float(metrics.get("population", 0))))
        return result

    def _metrics(self, state: Mapping[str, Any]) -> dict[str, Any]:
        citizens = _items(state.get("citizens")); businesses = _items(state.get("businesses")); houses = _items(state.get("houses"))
        employed = sum(bool(_get(c, "employed", _get(c, "job", None))) for c in citizens)
        incomes = [float(_get(c, "income", 0) or 0) for c in citizens]
        savings = sorted(float(_get(c, "savings", 0) or 0) for c in citizens)
        occupied = sum(float(_get(h, "occupancy", 0) or 0) for h in houses)
        capacity = sum(float(_get(h, "capacity", 0) or 0) for h in houses)
        return {"population": len(citizens), "employment": employed, "employment_rate": employed/max(1,len(citizens)),
                "average_income": sum(incomes)/max(1,len(incomes)), "median_savings": savings[len(savings)//2] if savings else 0,
                "business_count": len(businesses), "prices": 0, "housing_occupancy": occupied/max(1,capacity),
                "consumption": len(_items(state.get("transactions"))), "social_clustering": 0}

    def set_rule(self, key: str, value: float) -> None:
        rules = getattr(self.simulation, "rules", None)
        if isinstance(rules, dict):
            rules[key] = value
        elif rules is not None and hasattr(rules, key):
            setattr(rules, key, value)
        fn = getattr(self.simulation, "set_rule", None)
        if callable(fn):
            fn(key, value)

    def rebuild_scenario(self, values: Mapping[str, Any]) -> None:
        """Rebuild a core engine from editable scenario dimensions."""
        try:
            from dss.core.engine import SimulationConfig, SimulationEngine
            current = getattr(self.simulation, "config", None)
            cfg = SimulationConfig(
                seed=int(values.get("seed", getattr(current, "seed", 42))),
                citizens=int(values.get("population", getattr(current, "citizens", 100))),
                businesses=int(values.get("businesses", getattr(current, "businesses", 20))),
                houses=int(values.get("houses", getattr(current, "houses", 30))),
                days=int(getattr(current, "days", 365)),
                width=int(getattr(current, "width", 30)), height=int(getattr(current, "height", 20)),
            )
            rules = getattr(self.simulation, "rules", None)
            self.simulation = SimulationEngine(cfg, rules)
        except Exception:
            # DemoSimulation intentionally remains usable even when the core
            # package is absent from a minimal frozen build.
            return


_TkBase = tk.Tk if tk is not None else object


class DigitalSocietyApp(_TkBase):
    """Main application window."""

    def __init__(self, simulation: Any = None):
        if tk is None:
            raise RuntimeError("Tkinter libraries are unavailable; use headless mode")
        super().__init__()
        self.title("Digital Society Sandbox · 数字社会仿真沙盒")
        self.geometry("1280x800")
        self.minsize(960, 640)
        self.adapter = SimulationAdapter(simulation)
        self.running = False
        self.speed = tk.StringVar(value="1x")
        self.status = tk.StringVar(value="Ready · simulation result, not a real-world prediction")
        self.metric_vars: dict[str, tk.StringVar] = {}
        self._build()
        self.refresh()

    def _build(self) -> None:
        toolbar = ttk.Frame(self, padding=(8, 6)); toolbar.pack(fill="x")
        ttk.Button(toolbar, text="▶ Run", command=self.toggle_run).pack(side="left")
        ttk.Button(toolbar, text="Step day", command=lambda: self._advance(1)).pack(side="left", padx=4)
        ttk.Button(toolbar, text="Run 365 days", command=lambda: self._advance(365)).pack(side="left", padx=4)
        ttk.Label(toolbar, text="Speed").pack(side="left", padx=(14, 3))
        ttk.Combobox(toolbar, textvariable=self.speed, values=("1x", "10x", "100x", "1000x"), width=7, state="readonly").pack(side="left")
        ttk.Label(toolbar, textvariable=self.status).pack(side="right")

        main = ttk.PanedWindow(self, orient="horizontal"); main.pack(fill="both", expand=True)
        left = ttk.Frame(main); right = ttk.Frame(main, width=250)
        main.add(left, weight=4); main.add(right, weight=1)
        self.canvas = tk.Canvas(left, bg="#101823", highlightthickness=0); self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _e: self.draw_map())
        nb = ttk.Notebook(left); nb.pack(fill="both", expand=False, padx=5, pady=5)
        self.tx_text = tk.Text(nb, height=7, width=40, state="disabled", bg="#111820", fg="#d5e7ef")
        self.ev_text = tk.Text(nb, height=7, width=40, state="disabled", bg="#111820", fg="#d5e7ef")
        nb.add(self.tx_text, text="Transactions"); nb.add(self.ev_text, text="Events")

        dash = ttk.LabelFrame(right, text="Macro Dashboard", padding=8); dash.pack(fill="x", padx=6, pady=6)
        for key, label in (("day", "Day"), ("population", "Population"), ("employment_rate", "Employment"),
                           ("average_income", "Average income"), ("median_savings", "Median savings"),
                           ("business_count", "Businesses"), ("prices", "Prices"),
                           ("housing_occupancy", "Housing occupancy"), ("consumption", "Consumption"),
                           ("social_clustering", "Social clustering"), ("health", "Health")):
            row = ttk.Frame(dash); row.pack(fill="x", pady=1)
            ttk.Label(row, text=label).pack(side="left"); v = tk.StringVar(value="–"); self.metric_vars[key] = v
            ttk.Label(row, textvariable=v).pack(side="right")
        self._build_editor(right)

    def _build_editor(self, parent: ttk.Frame) -> None:
        box = ttk.LabelFrame(parent, text="Scenario Editor", padding=8); box.pack(fill="x", padx=6, pady=6)
        self.scenario_vars: dict[str, tk.StringVar] = {}
        for key in ("population", "businesses", "houses", "seed"):
            row = ttk.Frame(box); row.pack(fill="x", pady=2)
            ttk.Label(row, text=key.title(), width=17).pack(side="left")
            var = tk.StringVar(); self.scenario_vars[key] = var
            ttk.Entry(row, textvariable=var, width=8).pack(side="right")
        self.rule_vars: dict[str, tk.StringVar] = {}
        for key in ("tax_rate", "minimum_wage", "education_cost", "transport_cost", "welfare"):
            row = ttk.Frame(box); row.pack(fill="x", pady=2)
            ttk.Label(row, text=key.replace("_", " ").title(), width=17).pack(side="left")
            var = tk.StringVar(); self.rule_vars[key] = var; ttk.Entry(row, textvariable=var, width=8).pack(side="right")
        ttk.Button(box, text="Apply virtual-world rules", command=self.apply_rules).pack(fill="x", pady=(6, 0))
        ttk.Button(box, text="Rebuild population / map", command=self.rebuild_scenario).pack(fill="x", pady=(4, 0))
        ttk.Label(box, text="Parameters are simulation variables;\nnot claims about real society.", foreground="#777").pack(pady=(6, 0))

    def _advance(self, days: int) -> None:
        self.adapter.step(days); self.refresh()

    def toggle_run(self) -> None:
        self.running = not self.running
        self.status.set("Running · simulation result, not a real-world prediction" if self.running else "Paused")
        if self.running: self._loop()

    def _loop(self) -> None:
        if not self.running: return
        factor = int(self.speed.get().replace("x", ""))
        self.adapter.step(min(factor, 1000)); self.refresh()
        self.after(80 if factor >= 100 else 250, self._loop)

    def apply_rules(self) -> None:
        try:
            for key, var in self.rule_vars.items(): self.adapter.set_rule(key, float(var.get()))
            self.status.set("Rules applied")
        except ValueError:
            messagebox.showerror("Invalid rule", "Please enter numeric simulation parameters.")

    def rebuild_scenario(self) -> None:
        try:
            values = {key: int(var.get()) for key, var in self.scenario_vars.items()}
            self.adapter.rebuild_scenario(values)
            self.status.set("Scenario rebuilt · virtual-world parameters")
            self.refresh()
        except ValueError:
            messagebox.showerror("Invalid scenario", "Population, businesses, houses and seed must be integers.")

    def refresh(self) -> None:
        state = self.adapter.snapshot(); m = dict(state.get("metrics") or {})
        m["day"] = state.get("day", 0)
        for key, var in self.metric_vars.items():
            if key == "health":
                reports = getattr(self.adapter.simulation, "health_reports", [])
                last = reports[-1] if reports else None
                var.set("OK" if last is None or bool(_get(last, "ok", True)) else "ISSUES")
                continue
            value = m.get(key, 0)
            if key in ("employment_rate", "housing_occupancy", "social_clustering"): value = f"{float(value)*100:.1f}%"
            elif isinstance(value, float): value = f"{value:,.1f}"
            var.set(str(value))
        rules = state.get("rules") or {}
        config = state.get("config") or {}
        for key, var in self.scenario_vars.items():
            if not var.get(): var.set(str(_get(config, key if key != "population" else "citizens", "")))
        for key, var in self.rule_vars.items():
            if not var.get(): var.set(str(_get(rules, key, "")))
        self.draw_map(); self._set_text(self.tx_text, state.get("transactions", []), self._tx_line, 18); self._set_text(self.ev_text, state.get("events", []), self._ev_line, 12)

    def _set_text(self, widget: tk.Text, rows: Iterable[Any], fn, limit: int) -> None:
        widget.configure(state="normal"); widget.delete("1.0", "end")
        for row in list(rows)[-limit:][::-1]: widget.insert("end", fn(row) + "\n")
        widget.configure(state="disabled")

    def _tx_line(self, x: Any) -> str:
        return f"D{_get(x,'time','?')}  {_get(x,'buyer','?')} → {_get(x,'seller','?')}  {_get(x,'good','?')}  ${float(_get(x,'amount',0) or 0):.2f}"

    def _ev_line(self, x: Any) -> str:
        return f"D{_get(x,'time','?')}  {_get(x,'kind','event')}: {_get(x,'text',_get(x,'message',''))}"

    def draw_map(self) -> None:
        if not hasattr(self, "canvas"): return
        self.canvas.delete("all"); w = max(1, self.canvas.winfo_width()); h = max(1, self.canvas.winfo_height())
        # fixed world coordinate (700x450) mapped to current canvas
        sx, sy = max(0.2, w/760), max(0.2, h/450)
        def p(x, y): return (float(x)*sx, float(y)*sy)
        def entity_xy(entity: Any, index: int = 0) -> tuple[float, float]:
            """Resolve either explicit x/y coordinates or engine location IDs."""
            ex, ey = _get(entity, "x", None), _get(entity, "y", None)
            if ex is not None and ey is not None:
                return float(ex), float(ey)
            loc_id = _get(entity, "location_id", None)
            grid = state.get("map") if isinstance(state, Mapping) else None
            locs = _get(grid, "locations", {})
            loc = locs.get(loc_id) if isinstance(locs, Mapping) else None
            if loc is not None:
                width = max(1, int(_get(grid, "width", 30) or 30)); height = max(1, int(_get(grid, "height", 20) or 20))
                # Slight deterministic jitter keeps households and firms visible.
                jx, jy = (index % 5) * 0.35, ((index // 5) % 5) * 0.35
                return 20 + (float(_get(loc, "x", 0)) + jx) / width * 700, 45 + (float(_get(loc, "y", 0)) + jy) / height * 370
            return 20 + (index % 12) * 55, 70 + (index // 12) * 30
        for x in (0, 760): self.canvas.create_line(*p(x, 0), *p(x, 450), fill="#263544")
        for y in (0, 450): self.canvas.create_line(*p(0, y), *p(760, y), fill="#263544")
        # light-weight district overlays provide context without claiming a
        # geographically accurate city map.
        for box, label, color in [((10,10,735,55),"Residential","#18283a"),
                                  ((10,235,735,430),"Commercial / Industry","#1b3030"),
                                  ((560,65,735,210),"School / Hospital","#293329"),
                                  ((20,350,145,430),"Park / Transport","#26352b")]:
            x1,y1,x2,y2=box; self.canvas.create_rectangle(*p(x1,y1),*p(x2,y2), fill=color, outline="#294b5c"); self.canvas.create_text(*p(x1+7,y1+12), text=label, anchor="w", fill="#6d8b9e")
        state = self.adapter.snapshot()
        # Movement intent is drawn as a subtle line, so a paused frame still
        # exposes where each citizen is trying to go.
        for i, c in enumerate(_items(state.get("citizens"))):
            tx, ty = _get(c, "target_x", None), _get(c, "target_y", None)
            x0, y0 = entity_xy(c, i); x, y = p(x0, y0)
            if tx is not None and ty is not None:
                xx, yy = p(tx, ty)
                if abs(xx-x) + abs(yy-y) > 4: self.canvas.create_line(x, y, xx, yy, fill="#365363", width=1)
        for i, house in enumerate(_items(state.get("houses"))):
            x,y=p(*entity_xy(house, i)); self.canvas.create_rectangle(x-8,y-6,x+8,y+6, fill="#426a8d", outline="")
        for i, b in enumerate(_items(state.get("businesses"))):
            x,y=p(*entity_xy(b, i)); self.canvas.create_rectangle(x-7,y-7,x+7,y+7, fill="#d58b43", outline=""); self.canvas.create_text(x,y, text="B", fill="#161b22", font=("TkDefaultFont", 7, "bold"))
        for i, c in enumerate(_items(state.get("citizens"))):
            x,y=p(*entity_xy(c, i)); self.canvas.create_oval(x-2.5,y-2.5,x+2.5,y+2.5, fill="#77d5a6" if (_get(c,"employed",False) or _get(c,"job_id",None)) else "#e07b84", outline="")
        self.canvas.create_text(12, h-12, text="● citizen   ■ business   ▰ house   green=employed / red=unemployed", anchor="w", fill="#b4c8d1")


def run_app(simulation: Any = None) -> None:
    if tk is None:
        print("Digital Society Sandbox UI needs Tkinter libraries (Windows build bundles them).")
        print("Use the headless simulation API for batch experiments.")
        return
    try:
        app = DigitalSocietyApp(simulation); app.mainloop()
    except tk.TclError as exc:
        # CI/headless servers have no display.  Keep import and simulation
        # checks usable there instead of emitting a long traceback.
        if "display" in str(exc).lower():
            print("Digital Society Sandbox UI needs a graphical display (Tkinter).")
            print("Use the headless simulation API for batch experiments.")
            return
        raise
