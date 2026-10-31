"""Event-sourced political relationships and influence inside an institution.

Events carry explicit effects: this module does not infer alliances, corruption,
merit, or political intent. Replaying the same canonical event set produces the
same institutional state regardless of append order.
"""
from __future__ import annotations

from dataclasses import dataclass
import math


def _identifier(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _finite(value: float, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be finite")


def _bounded(value: float, name: str, low: float, high: float) -> None:
    _finite(value, name)
    if not low <= value <= high:
        raise ValueError(f"{name} must be between {low} and {high}")


@dataclass(frozen=True)
class InstitutionalPoliticalEvent:
    event_id: str
    institution_id: str
    period_index: int
    department_id: str
    influence_delta: float = 0.0
    other_department_id: str | None = None
    relationship_delta: float = 0.0
    priority_tag: str | None = None
    leadership_priority_delta: float = 0.0
    rationale: str = "unspecified"

    def __post_init__(self) -> None:
        for name in ("event_id", "institution_id", "department_id", "rationale"):
            _identifier(getattr(self, name), name)
        if isinstance(self.period_index, bool) or not isinstance(self.period_index, int) or self.period_index < 0:
            raise ValueError("period_index must be a non-negative integer")
        _bounded(self.influence_delta, "influence_delta", -1.0, 1.0)
        _bounded(self.relationship_delta, "relationship_delta", -1.0, 1.0)
        _bounded(self.leadership_priority_delta, "leadership_priority_delta", -1.0, 1.0)
        if self.other_department_id is not None:
            _identifier(self.other_department_id, "other_department_id")
            if self.other_department_id == self.department_id:
                raise ValueError("a department cannot have a relationship with itself")
        if self.relationship_delta != 0.0 and self.other_department_id is None:
            raise ValueError("relationship changes require other_department_id")
        if self.priority_tag is not None:
            _identifier(self.priority_tag, "priority_tag")
        if self.leadership_priority_delta != 0.0 and self.priority_tag is None:
            raise ValueError("leadership priority changes require priority_tag")


@dataclass(frozen=True)
class InstitutionalPoliticalState:
    institution_id: str
    period_index: int
    department_influence: tuple[tuple[str, float], ...]
    department_relationships: tuple[tuple[str, str, float], ...]
    leadership_priorities: tuple[tuple[str, float], ...]
    event_ids: tuple[str, ...]


class InstitutionalPoliticalLedger:
    """Canonical event history for alliances, rivalries, lobbying and influence."""

    def __init__(self, institution_id: str, *, initial_influence=(), leadership_priorities=()):
        _identifier(institution_id, "institution_id")
        self.institution_id = institution_id
        self._initial_influence = self._normalise_pairs(initial_influence, "initial_influence")
        self._initial_priorities = self._normalise_pairs(leadership_priorities, "leadership_priorities")
        for _, value in self._initial_influence:
            _bounded(value, "initial influence", 0.0, 1.0)
        for _, value in self._initial_priorities:
            _bounded(value, "initial leadership priority", 0.0, 1.0)
        self._events: dict[str, InstitutionalPoliticalEvent] = {}

    @staticmethod
    def _normalise_pairs(values, name):
        if not isinstance(values, (tuple, list)):
            raise TypeError(f"{name} must be a sequence of pairs")
        pairs = []
        for item in values:
            if not isinstance(item, (tuple, list)) or len(item) != 2:
                raise TypeError(f"{name} entries must be pairs")
            key, value = item
            _identifier(key, f"{name} key")
            _finite(value, f"{name} value")
            pairs.append((key, float(value)))
        if len({key for key, _ in pairs}) != len(pairs):
            raise ValueError(f"{name} keys must be unique")
        return tuple(sorted(pairs))

    def append(self, event: InstitutionalPoliticalEvent) -> InstitutionalPoliticalState:
        if not isinstance(event, InstitutionalPoliticalEvent):
            raise TypeError("event must be InstitutionalPoliticalEvent")
        if event.institution_id != self.institution_id:
            raise ValueError("event belongs to a different institution")
        previous = self._events.get(event.event_id)
        if previous is not None:
            if previous != event:
                raise ValueError("event_id was reused with different content")
            return self.state()
        self._events[event.event_id] = event
        return self.state()

    def append_many(self, events) -> InstitutionalPoliticalState:
        if not isinstance(events, (tuple, list)):
            raise TypeError("events must be a sequence")
        for event in events:
            self.append(event)
        return self.state()

    def state(self) -> InstitutionalPoliticalState:
        influence = dict(self._initial_influence)
        priorities = dict(self._initial_priorities)
        relationships: dict[tuple[str, str], float] = {}
        ordered = sorted(self._events.values(), key=lambda item: (item.period_index, item.event_id))
        for event in ordered:
            influence[event.department_id] = min(1.0, max(0.0, influence.get(event.department_id, 0.5) + event.influence_delta))
            if event.other_department_id is not None and event.relationship_delta != 0.0:
                pair = tuple(sorted((event.department_id, event.other_department_id)))
                relationships[pair] = min(1.0, max(-1.0, relationships.get(pair, 0.0) + event.relationship_delta))
            if event.priority_tag is not None and event.leadership_priority_delta != 0.0:
                tag = event.priority_tag
                priorities[tag] = min(1.0, max(0.0, priorities.get(tag, 0.5) + event.leadership_priority_delta))
        return InstitutionalPoliticalState(
            self.institution_id,
            max((event.period_index for event in ordered), default=0),
            tuple(sorted(influence.items())),
            tuple((left, right, value) for (left, right), value in sorted(relationships.items())),
            tuple(sorted(priorities.items())),
            tuple(event.event_id for event in ordered),
        )

    @property
    def events(self) -> tuple[InstitutionalPoliticalEvent, ...]:
        return tuple(sorted(self._events.values(), key=lambda item: (item.period_index, item.event_id)))

    def snapshot(self) -> dict:
        return {
            "schema_version": 1,
            "institution_id": self.institution_id,
            "initial_influence": [list(item) for item in self._initial_influence],
            "leadership_priorities": [list(item) for item in self._initial_priorities],
            "events": [
                {
                    "event_id": event.event_id,
                    "institution_id": event.institution_id,
                    "period_index": event.period_index,
                    "department_id": event.department_id,
                    "influence_delta": event.influence_delta,
                    "other_department_id": event.other_department_id,
                    "relationship_delta": event.relationship_delta,
                    "priority_tag": event.priority_tag,
                    "leadership_priority_delta": event.leadership_priority_delta,
                    "rationale": event.rationale,
                }
                for event in self.events
            ],
        }

    @classmethod
    def from_snapshot(cls, data: dict) -> "InstitutionalPoliticalLedger":
        if not isinstance(data, dict) or data.get("schema_version") != 1:
            raise ValueError("unsupported institutional political snapshot")
        ledger = cls(
            data.get("institution_id"),
            initial_influence=data.get("initial_influence", ()),
            leadership_priorities=data.get("leadership_priorities", ()),
        )
        raw_events = data.get("events")
        if not isinstance(raw_events, list):
            raise ValueError("snapshot events must be a list")
        events = []
        for item in raw_events:
            if not isinstance(item, dict):
                raise ValueError("snapshot event must be an object")
            events.append(InstitutionalPoliticalEvent(**item))
        if events != sorted(events, key=lambda item: (item.period_index, item.event_id)):
            raise ValueError("snapshot events must be in canonical order")
        ledger.append_many(events)
        return ledger
