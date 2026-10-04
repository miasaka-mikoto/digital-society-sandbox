"""Inspectable social-network dynamics for Digital Society Sandbox.

The network deliberately stores several dimensions rather than one opaque
``happiness`` value.  Updates are deterministic and use no global random
state, which makes network changes easy to replay and audit.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from dss.core.models import Citizen, Relationship


def relationship_id(a: str, b: str) -> str:
    """Return a stable, undirected relationship identifier."""
    x, y = sorted((str(a), str(b)))
    return f"rel:{x}:{y}"


class SocialNetwork:
    """Mutable undirected network with auditable relationship dimensions."""

    def __init__(self, relationships: Optional[Mapping[str, Relationship] | Iterable[Relationship]] = None):
        if isinstance(relationships, Mapping):
            self.relationships: Dict[str, Relationship] = dict(relationships)
        else:
            self.relationships = {r.id: r for r in (relationships or ())}
        self.interaction_log: List[dict] = []
        self._pair_index: Dict[tuple[str, str], str] = {}
        self._indexed_mapping_id = 0

    def _ensure_index(self) -> None:
        """Build a pair lookup once; legacy-ID fallback must stay O(1)."""
        if (self._indexed_mapping_id == id(self.relationships)
                and len(self._pair_index) >= len(self.relationships)):
            return
        self._pair_index = {}
        for rid, rel in self.relationships.items():
            self._pair_index[tuple(sorted((str(rel.a), str(rel.b))))] = rid
        self._indexed_mapping_id = id(self.relationships)

    @classmethod
    def from_engine(cls, engine) -> "SocialNetwork":
        """Create a live adapter over ``SimulationEngine.relationships``.

        The mapping is intentionally shared, so updates made by this system
        remain visible to the engine and its snapshots.
        """
        obj = cls()
        obj.relationships = engine.relationships
        obj._indexed_mapping_id = 0
        return obj

    def get(self, a: str, b: str) -> Optional[Relationship]:
        rid = relationship_id(a, b)
        if rid in self.relationships:
            return self.relationships[rid]
        self._ensure_index()
        legacy = self._pair_index.get(tuple(sorted((str(a), str(b)))))
        return self.relationships.get(legacy) if legacy else None

    def ensure(self, a: str, b: str, *, initial_trust: float = 0.5) -> Relationship:
        if a == b:
            raise ValueError("self-relationships are not supported")
        rid = relationship_id(a, b)
        rel = self.get(a, b)
        if rel is None:
            x, y = sorted((str(a), str(b)))
            rel = Relationship(id=rid, a=x, b=y, trust=float(initial_trust))
            self.relationships[rid] = rel
            self._pair_index[(x, y)] = rid
            self._indexed_mapping_id = id(self.relationships)
        return rel

    def record_interaction(
        self, a: str, b: str, *, day: int = 0, quality: float = 0.5,
        communication: float = 1.0, conflict: float = 0.0,
    ) -> Relationship:
        """Apply one observable interaction and append an audit record.

        ``quality`` and ``conflict`` are clamped to [0, 1].  Familiarity and
        communication are bounded; trust and affinity move gradually so one
        event cannot dominate a long simulation.
        """
        rel = self.ensure(a, b)
        q = max(0.0, min(1.0, float(quality)))
        c = max(0.0, min(1.0, float(conflict)))
        rel.familiarity = min(1.0, rel.familiarity + 0.04 * max(0.0, communication))
        rel.communication_frequency = min(1.0, rel.communication_frequency * 0.95 + 0.05 * max(0.0, communication))
        rel.trust = max(0.0, min(1.0, rel.trust + 0.04 * (q - c - (1.0 - q) * 0.25)))
        rel.affinity = max(-1.0, min(1.0, rel.affinity + 0.05 * (q - 0.5) - 0.04 * c))
        rel.conflict = max(0.0, min(1.0, rel.conflict * 0.96 + 0.06 * c))
        self.interaction_log.append({"day": int(day), "a": str(a), "b": str(b), "quality": q, "conflict": c})
        return rel

    def decay(self, days: int = 1) -> None:
        """Apply bounded time decay to communication and familiarity."""
        for _ in range(max(0, int(days))):
            for rel in self.relationships.values():
                rel.communication_frequency *= 0.995
                rel.familiarity *= 0.999
                rel.conflict *= 0.998

    def attach_to_citizens(self, citizens: Mapping[str, Citizen] | Iterable[Citizen]) -> None:
        values = citizens.values() if isinstance(citizens, Mapping) else citizens
        values = list(values)
        links: Dict[str, list[str]] = {c.id: [] for c in values}
        for r in self.relationships.values():
            if r.a in links:
                links[r.a].append(r.id)
            if r.b in links:
                links[r.b].append(r.id)
        for c in values:
            c.relationship_ids = sorted(links.get(c.id, ()))

    def metrics(self, citizen_ids: Optional[Sequence[str]] = None) -> dict:
        rels = list(self.relationships.values())
        ids = set(citizen_ids or [x for r in rels for x in (r.a, r.b)])
        possible = len(ids) * max(0, len(ids) - 1) / 2
        density = len(rels) / possible if possible else 0.0
        active = [r for r in rels if r.communication_frequency > 0.05 or r.familiarity > 0.05]
        return {
            "relationship_count": len(rels), "active_relationship_count": len(active),
            "density": density,
            "average_familiarity": sum(r.familiarity for r in rels) / len(rels) if rels else 0.0,
            "average_trust": sum(r.trust for r in rels) / len(rels) if rels else 0.0,
            "average_affinity": sum(r.affinity for r in rels) / len(rels) if rels else 0.0,
            "average_conflict": sum(r.conflict for r in rels) / len(rels) if rels else 0.0,
            "communication_frequency": sum(r.communication_frequency for r in rels) / len(rels) if rels else 0.0,
            "connected_components": self.connected_components(ids),
        }

    def connected_components(self, citizen_ids: Iterable[str]) -> int:
        ids = set(citizen_ids)
        graph = {x: set() for x in ids}
        for r in self.relationships.values():
            if r.a in graph and r.b in graph and (r.familiarity > 0.05 or r.communication_frequency > 0.05):
                graph[r.a].add(r.b); graph[r.b].add(r.a)
        count = 0
        while graph:
            count += 1; stack = [next(iter(graph))]
            while stack:
                node = stack.pop()
                if node not in graph: continue
                neighbours = graph.pop(node)
                stack.extend(neighbours)
        return count


def update_social_network(
    network: SocialNetwork, citizens: Iterable[Citizen], *, day: int = 0,
    same_location_quality: float = 0.55,
) -> List[Relationship]:
    """Create/update proximity interactions for citizens sharing a location.

    The input is sorted by ID; no hash iteration affects outcomes.
    """
    people = sorted((c for c in citizens if c.alive), key=lambda c: c.id)
    changed: List[Relationship] = []
    # Group by location and connect a bounded deterministic neighborhood.  A
    # complete graph at a busy market is both unrealistic and quadratic; a
    # ring plus a few short-range pairs preserves clustering while keeping
    # 100-agent/100-seed experiments fast.
    by_location: Dict[str, list[Citizen]] = {}
    for person in people:
        if person.location_id:
            by_location.setdefault(person.location_id, []).append(person)
    for location_id in sorted(by_location):
        group = by_location[location_id]
        for i, a in enumerate(group):
            neighbors = [group[(i + 1) % len(group)]] if len(group) > 1 else []
            if len(group) > 3:
                neighbors.append(group[(i + 3) % len(group)])
            seen = set()
            for b in neighbors:
                if b.id in seen or b.id == a.id:
                    continue
                seen.add(b.id)
                changed.append(network.record_interaction(a.id, b.id, day=day, quality=same_location_quality))
    network.attach_to_citizens(people)
    return changed


def social_network_from_engine(engine) -> SocialNetwork:
    return SocialNetwork.from_engine(engine)


__all__ = ["SocialNetwork", "relationship_id", "update_social_network", "social_network_from_engine"]
