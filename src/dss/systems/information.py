"""Deterministic information diffusion (news, rumours and events).

This is intentionally a neutral simulation mechanism: content is supplied by
the scenario and no real-world political beliefs or topics are injected.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Mapping, Optional, Sequence

from dss.core.models import Citizen, Event, Relationship
from .social import SocialNetwork


@dataclass
class InformationItem:
    id: str
    kind: str  # news, rumor, event
    text: str
    created_at: int
    location_id: Optional[str] = None
    source: Optional[str] = None
    channel: str = "local"  # location, relationship, media
    reliability: float = 0.8
    reach: int = 0
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass
class Exposure:
    item_id: str
    citizen_id: str
    day: int
    channel: str
    sender: Optional[str] = None
    believed: bool = False


@dataclass
class MediaChannel:
    """A scenario-defined broadcast channel (no real-world ideology implied)."""
    id: str
    audience: List[str] = field(default_factory=list)
    reliability: float = 0.8
    active: bool = True


class InformationSystem:
    """Stores information and deterministic exposure history."""

    def __init__(self):
        self.items: Dict[str, InformationItem] = {}
        self.media_channels: Dict[str, MediaChannel] = {}
        self.known_by: Dict[str, set[str]] = {}
        self.exposures: List[Exposure] = []

    @classmethod
    def from_engine(cls, engine) -> "InformationSystem":
        """Hydrate information items from an existing engine's events."""
        system = cls()
        for event in sorted(getattr(engine, "events", ()), key=lambda e: e.id):
            system.publish_event(event, kind="event" if event.kind == "event" else "news")
        return system

    def add_media_channel(self, channel: MediaChannel) -> None:
        channel.reliability = max(0.0, min(1.0, float(channel.reliability)))
        self.media_channels[channel.id] = channel

    def publish(self, item: InformationItem, citizens: Iterable[Citizen] = ()) -> InformationItem:
        if item.kind not in {"news", "rumor", "event"}:
            raise ValueError("kind must be news, rumor, or event")
        item.reliability = max(0.0, min(1.0, float(item.reliability)))
        self.items[item.id] = item
        for c in citizens:
            self.known_by.setdefault(c.id, set())
        return item

    def publish_event(self, event: Event, *, kind: str = "event", channel: str = "location") -> InformationItem:
        return self.publish(InformationItem(event.id, kind, event.text, event.time, event.location_id, event.source, channel))

    def seed_exposure(self, item_id: str, citizen_id: str, day: int, channel: str = "media") -> None:
        if item_id not in self.items: raise KeyError(item_id)
        self.known_by.setdefault(citizen_id, set()).add(item_id)
        self.exposures.append(Exposure(item_id, citizen_id, int(day), channel, None, True))
        self.items[item_id].reach += 1

    def propagate(
        self, day: int, citizens: Iterable[Citizen], network: SocialNetwork,
        *, media_channels: Optional[Mapping[str, Sequence[str]]] = None,
    ) -> List[Exposure]:
        """Propagate one day through location, relationship and media channels.

        Unlike a stochastic viral model, each channel uses deterministic
        thresholds derived from relationship values and IDs.  Therefore a
        repeated seed/configuration is exactly reproducible.
        """
        people = {c.id: c for c in citizens if c.alive}
        out: List[Exposure] = []
        for item in sorted(self.items.values(), key=lambda x: x.id):
            already = {cid for cid, values in self.known_by.items() if item.id in values}
            candidates: List[tuple[str, str, Optional[str], float]] = []
            for cid, c in sorted(people.items()):
                if cid in already: continue
                if item.location_id and c.location_id == item.location_id:
                    candidates.append((cid, "location", None, 0.75))
                if item.channel == "media" or item.channel in self.media_channels:
                    channels = media_channels or {k: v.audience for k, v in self.media_channels.items()}
                    audience = channels.get(item.channel, ()) if item.channel in channels else ()
                    targeted = item.id in channels.get(cid, ()) or cid in channels.get("*", ())
                    if not channels or cid in audience or targeted:
                        candidates.append((cid, "media", None, 0.55))
                for rel in network.relationships.values():
                    if cid not in (rel.a, rel.b): continue
                    sender = rel.b if rel.a == cid else rel.a
                    if sender in already:
                        score = 0.35 + 0.35 * rel.trust + 0.2 * rel.familiarity + 0.1 * rel.communication_frequency
                        candidates.append((cid, "relationship", sender, score))
            # one strongest route per citizen
            strongest: Dict[str, tuple[str, Optional[str], float]] = {}
            for cid, channel, sender, score in candidates:
                if cid not in strongest or score > strongest[cid][2]: strongest[cid] = (channel, sender, score)
            for cid in sorted(strongest):
                channel, sender, score = strongest[cid]
                # deterministic threshold; reliability modifies likelihood without RNG
                believed = score * (0.5 + 0.5 * item.reliability) >= 0.45
                if believed or channel == "location":
                    self.known_by.setdefault(cid, set()).add(item.id)
                    ex = Exposure(item.id, cid, int(day), channel, sender, believed)
                    self.exposures.append(ex); out.append(ex); item.reach += 1
        return out

    def citizen_feed(self, citizen_id: str) -> List[InformationItem]:
        ids = self.known_by.get(citizen_id, set())
        return [self.items[x] for x in sorted(ids) if x in self.items]


def information_system_from_engine(engine) -> InformationSystem:
    return InformationSystem.from_engine(engine)


__all__ = ["InformationItem", "Exposure", "MediaChannel", "InformationSystem", "information_system_from_engine"]
