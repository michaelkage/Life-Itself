"""Independent, observer-specific relationship facets with evidence history.

No single good/bad score is produced. Warmth and resentment, respect and fear,
or obligation and rivalry may coexist. Changes are explicit and event-linked;
presence or familiarity alone never changes a relationship.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Iterable

RELATIONSHIP_FACETS = (
    "warmth", "resentment", "rivalry", "obligation",
    "dependence", "respect", "fear", "comfort",
)


@dataclass(frozen=True)
class RelationshipChange:
    change_id: str
    source_event_id: str
    observer_id: str
    target_id: str
    tick: int
    facet: str
    delta: float
    evidence_tag: str = ""

    def __post_init__(self):
        for name in ("change_id", "source_event_id", "observer_id", "target_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if self.observer_id == self.target_id:
            raise ValueError("an NPC cannot have a relationship facet toward themselves")
        if isinstance(self.tick, bool) or not isinstance(self.tick, int) or self.tick < 0:
            raise ValueError("tick must be a non-negative integer")
        if self.facet not in RELATIONSHIP_FACETS:
            raise ValueError(f"facet must be one of {', '.join(RELATIONSHIP_FACETS)}")
        if (isinstance(self.delta, bool) or not isinstance(self.delta, (int, float))
                or not math.isfinite(self.delta) or not -1 <= self.delta <= 1):
            raise ValueError("delta must be finite and in [-1, 1]")
        if not isinstance(self.evidence_tag, str):
            raise ValueError("evidence_tag must be a string")


@dataclass(frozen=True)
class RelationshipState:
    observer_id: str
    target_id: str
    facets: tuple[tuple[str, float], ...]

    def value(self, facet: str) -> float:
        if facet not in RELATIONSHIP_FACETS:
            raise ValueError(f"unknown relationship facet: {facet}")
        return dict(self.facets)[facet]


class SocialRelationshipLedger:
    """Append-only, directed facet changes; values are replayed deterministically."""

    def __init__(self, changes: Iterable[RelationshipChange] = ()):
        self._changes: dict[str, RelationshipChange] = {}
        for change in changes:
            self.add(change)

    def add(self, change: RelationshipChange) -> RelationshipChange:
        if not isinstance(change, RelationshipChange):
            raise TypeError("change must be a RelationshipChange")
        prior = self._changes.get(change.change_id)
        if prior is not None:
            if prior != change:
                raise ValueError(f"relationship change ID reused: {change.change_id}")
            return prior
        self._changes[change.change_id] = change
        return change

    def snapshot(self) -> tuple[RelationshipChange, ...]:
        return tuple(sorted(self._changes.values(), key=lambda x: (x.tick, x.change_id)))

    def changes_for(self, observer_id: str, target_id: str) -> tuple[RelationshipChange, ...]:
        return tuple(x for x in self.snapshot()
                     if x.observer_id == observer_id and x.target_id == target_id)

    def relationship(self, observer_id: str, target_id: str, *,
                     through_tick: int | None = None) -> RelationshipState:
        if (not isinstance(observer_id, str) or not observer_id.strip()
                or not isinstance(target_id, str) or not target_id.strip()
                or observer_id == target_id):
            raise ValueError("observer and target must be different non-empty NPC IDs")
        if through_tick is not None and (
                isinstance(through_tick, bool) or not isinstance(through_tick, int)
                or through_tick < 0):
            raise ValueError("through_tick must be a non-negative integer or None")
        values = {facet: 0.0 for facet in RELATIONSHIP_FACETS}
        for change in self.changes_for(observer_id, target_id):
            if through_tick is None or change.tick <= through_tick:
                values[change.facet] = min(1.0, max(-1.0, values[change.facet] + change.delta))
        return RelationshipState(observer_id, target_id, tuple(sorted(values.items())))


@dataclass(frozen=True)
class SocialRelationshipSnapshot:
    changes: tuple[RelationshipChange, ...]

    SCHEMA_VERSION = 1

    def __post_init__(self):
        if not isinstance(self.changes, tuple) or any(
                not isinstance(x, RelationshipChange) for x in self.changes):
            raise ValueError("changes must contain RelationshipChange records")
        ids = [x.change_id for x in self.changes]
        if ids != sorted(ids) or len(ids) != len(set(ids)):
            raise ValueError("relationship changes must be uniquely sorted by ID")

    @classmethod
    def capture(cls, ledger: SocialRelationshipLedger):
        if not isinstance(ledger, SocialRelationshipLedger):
            raise TypeError("ledger must be a SocialRelationshipLedger")
        return cls(tuple(sorted(ledger.snapshot(), key=lambda x: x.change_id)))

    def restore(self):
        return SocialRelationshipLedger(self.changes)

    def to_json(self):
        return json.dumps({
            "schema_version": self.SCHEMA_VERSION,
            "changes": [{
                "change_id": x.change_id, "source_event_id": x.source_event_id,
                "observer_id": x.observer_id, "target_id": x.target_id,
                "tick": x.tick, "facet": x.facet, "delta": x.delta,
                "evidence_tag": x.evidence_tag,
            } for x in self.changes],
        }, sort_keys=True, separators=(",", ":"), allow_nan=False)

    @classmethod
    def from_json(cls, payload: str):
        try:
            raw = json.loads(payload)
            if not isinstance(raw, dict) or raw.get("schema_version") != cls.SCHEMA_VERSION:
                raise ValueError("unsupported relationship snapshot schema version")
            records = tuple(sorted((RelationshipChange(**item) for item in raw["changes"]),
                                   key=lambda x: x.change_id))
            result = cls(records)
            if result.to_json() != payload:
                raise ValueError("relationship snapshot must use canonical JSON")
            return result
        except (TypeError, KeyError, json.JSONDecodeError) as exc:
            raise ValueError("invalid relationship snapshot") from exc
