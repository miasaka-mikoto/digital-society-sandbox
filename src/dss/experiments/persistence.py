"""Portable snapshot and SQLite persistence for simulation runs."""
from __future__ import annotations
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, Optional
from .runner import _state


class SnapshotStore:
    """Append-only SQLite store for daily/weekly snapshots and ledger records."""
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(self.path))
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS snapshots (
          id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, seed INTEGER, day INTEGER,
          payload TEXT NOT NULL, metrics TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(run_id, day)
        );
        CREATE TABLE IF NOT EXISTS transactions (
          run_id TEXT, tx_id TEXT, buyer TEXT, seller TEXT, amount REAL, good TEXT,
          time INTEGER, reason TEXT, payload TEXT, UNIQUE(run_id, tx_id)
        );
        """)
        self.db.commit()

    def set_metadata(self, key: str, value: Any):
        self.db.execute("INSERT OR REPLACE INTO metadata(key,value) VALUES (?,?)", (key, json.dumps(value, ensure_ascii=False)))
        self.db.commit()

    def save(self, run_id: str, seed: int, day: int, state: Any, metrics: Optional[Dict[str, Any]] = None):
        payload = json.dumps(state, ensure_ascii=False, sort_keys=True, default=str)
        self.db.execute("INSERT OR REPLACE INTO snapshots(run_id,seed,day,payload,metrics) VALUES (?,?,?,?,?)",
                        (run_id, seed, day, payload, json.dumps(metrics or {}, ensure_ascii=False, sort_keys=True)))
        # A final engine state commonly contains the append-only ledger.  Keep
        # a queryable normalized copy as well as the JSON snapshot; compact
        # weekly snapshots without a transaction list incur no duplication.
        if isinstance(state, dict) and state.get("transactions"):
            for i, t in enumerate(state.get("transactions") or []):
                def g(k, default=None):
                    return t.get(k, default) if isinstance(t, dict) else getattr(t, k, default)
                txid = str(g("id", i))
                self.db.execute(
                    "INSERT OR REPLACE INTO transactions(run_id,tx_id,buyer,seller,amount,good,time,reason,payload) VALUES (?,?,?,?,?,?,?,?,?)",
                    (run_id, txid, str(g("buyer", "")), str(g("seller", "")),
                     float(g("amount", 0) or 0), str(g("good", "")),
                     int(g("time", day) or day), str(g("reason", "")),
                     json.dumps(t, ensure_ascii=False, default=str)))
        self.db.commit()

    def save_simulation(self, run_id: str, seed: int, day: int, sim: Any, metrics: Optional[Dict[str, Any]] = None):
        self.save(run_id, seed, day, _state(sim), metrics)
        txs = getattr(sim, "transactions", getattr(sim, "ledger", []))
        if isinstance(txs, dict): txs = txs.values()
        for i, t in enumerate(txs or []):
            def g(k, default=None): return t.get(k, default) if isinstance(t, dict) else getattr(t, k, default)
            txid = str(g("id", i))
            self.db.execute("INSERT OR REPLACE INTO transactions(run_id,tx_id,buyer,seller,amount,good,time,reason,payload) VALUES (?,?,?,?,?,?,?,?,?)",
                            (run_id, txid, str(g("buyer", "")), str(g("seller", "")), float(g("amount", 0) or 0), str(g("good", "")), int(g("time", day) or day), str(g("reason", "")), json.dumps(g("__dict__", t), default=str)))
        self.db.commit()

    def load(self, run_id: str, day: Optional[int] = None) -> Optional[Dict[str, Any]]:
        if day is None:
            row = self.db.execute("SELECT run_id,seed,day,payload,metrics FROM snapshots WHERE run_id=? ORDER BY day DESC LIMIT 1", (run_id,)).fetchone()
        else:
            row = self.db.execute("SELECT run_id,seed,day,payload,metrics FROM snapshots WHERE run_id=? AND day=?", (run_id, day)).fetchone()
        if not row: return None
        return {"run_id": row[0], "seed": row[1], "day": row[2], "state": json.loads(row[3]), "metrics": json.loads(row[4])}

    def days(self, run_id: str):
        return [r[0] for r in self.db.execute("SELECT day FROM snapshots WHERE run_id=? ORDER BY day", (run_id,))]

    def close(self): self.db.close()
    def __enter__(self): return self
    def __exit__(self, *args): self.close()


def save_snapshot(path: str | Path, sim: Any, *, run_id: str = "default", seed: int = 0, day: Optional[int] = None, metrics: Optional[Dict[str, Any]] = None):
    day = int(day if day is not None else getattr(sim, "day", getattr(sim, "time", 0)))
    with SnapshotStore(path) as store:
        store.save_simulation(run_id, seed, day, sim, metrics)
    return Path(path)


def load_snapshot(path: str | Path, run_id: str = "default", day: Optional[int] = None):
    with SnapshotStore(path) as store:
        return store.load(run_id, day)
