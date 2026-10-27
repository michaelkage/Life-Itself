"""Append-only deterministic journal of authoritative world events.

This ledger records what the simulation says happened, not how every NPC
interprets it. Observer-specific memory, rumours, trust, legal evidence and
reactions can be derived by separate systems without rewriting the event itself.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, TypeAlias

Scalar: TypeAlias = str | int | float | bool | None


def _non_empty(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _validate_attributes(attributes: tuple[tuple[str, Scalar], ...]) -> None:
    if not isinstance(attributes, tuple):
        raise ValueError("attributes must be a tuple of key/value pairs")
    seen: set[str] = set()
    for item in attributes:
        if not isinstance(item, tuple) or len(item) != 2:
            raise ValueError("each attribute must be a (key, scalar_value) tuple")
        key, value = item
        _non_empty("attribute key", key)
        if key in seen:
            raise ValueError(f"duplicate attribute key: {key}")
        seen.add(key)
        if value is not None and not isinstance(value, (str, int, float, bool)):
            raise ValueError(f"attribute {key!r} must have a scalar value")
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f"attribute {key!r} must be finite")


@dataclass(frozen=True)
class WorldEvent:
    """Immutable fact recorded on the simulation's world timeline.

    participants preserves role order (for example, victim then actor). Witnesses
    are canonicalized by the caller or ledger and are not treated as participants.
    Attributes are immutable scalar pairs rather than a mutable dictionary.
    """

    event_id: str
    tick: int
    event_type: str
    participants: tuple[str, ...] = ()
    witnesses: tuple[str, ...] = ()
    attributes: tuple[tuple[str, Scalar], ...] = ()

    def __post_init__(self) -> None:
        _non_empty("event_id", self.event_id)
        _non_empty("event_type", self.event_type)
        if isinstance(self.tick, bool) or not isinstance(self.tick, int) or self.tick < 0:
            raise ValueError("tick must be a non-negative integer")
        for field_name in ("participants", "witnesses"):
            values = getattr(self, field_name)
            if not isinstance(values, tuple):
                raise ValueError(f"{field_name} must be a tuple")
            for value in values:
                _non_empty(f"{field_name} entry", value)
            if len(values) != len(set(values)):
                raise ValueError(f"{field_name} entries must be unique")
        if set(self.participants) & set(self.witnesses):
            raise ValueError("a character cannot be both participant and witness for one event")
        _validate_attributes(self.attributes)
        if tuple(sorted(self.attributes, key=lambda pair: pair[0])) != self.attributes:
            raise ValueError("attributes must be sorted by key for canonical representation")


class WorldEventLedger:
    """Store world facts with stable replay, filtering and snapshot restoration.

    Identical event IDs and content are idempotent. Conflicting reuse is rejected.
    Queries and snapshots use (tick, event_id) ordering; ingestion order does not
    affect the returned timeline. The ledger never infers event meaning or mutates
    NPC systems.
    """

    def __init__(self, events: Iterable[WorldEvent] = ()) -> None:
        self._events: dict[str, WorldEvent] = {}
        self.append_many(events)

    @staticmethod
    def make_event(
        event_id: str,
        tick: int,
        event_type: str,
        *,
        participants: Iterable[str] = (),
        witnesses: Iterable[str] = (),
        attributes: dict[str, Scalar] | Iterable[tuple[str, Scalar]] | None = None,
    ) -> WorldEvent:
        """Build a canonical event from convenient mappings or pair iterables."""
        raw_attributes = attributes.items() if isinstance(attributes, dict) else (attributes or ())
        pairs = tuple(sorted(tuple(raw_attributes), key=lambda pair: pair[0]))
        return WorldEvent(
            event_id=event_id,
            tick=tick,
            event_type=event_type,
            participants=tuple(participants),
            witnesses=tuple(sorted(witnesses)),
            attributes=pairs,
        )

    def append(self, event: WorldEvent) -> WorldEvent:
        self.append_many((event,))
        return self._events[event.event_id]

    def append_many(self, events: Iterable[WorldEvent]) -> tuple[WorldEvent, ...]:
        items = tuple(events)
        batch_ids: set[str] = set()
        for event in items:
            if not isinstance(event, WorldEvent):
                raise TypeError("events must contain only WorldEvent instances")
            if event.event_id in batch_ids:
                raise ValueError(f"duplicate event ID in batch: {event.event_id}")
            batch_ids.add(event.event_id)
            existing = self._events.get(event.event_id)
            if existing is not None and existing != event:
                raise ValueError(f"event ID reused with different content: {event.event_id}")
        for event in sorted(items, key=lambda item: (item.tick, item.event_id)):
            self._events.setdefault(event.event_id, event)
        return tuple(self._events[event.event_id] for event in sorted(items, key=lambda item: (item.tick, item.event_id)))

    def get(self, event_id: str) -> WorldEvent:
        try:
            return self._events[event_id]
        except KeyError:
            raise KeyError(event_id) from None

    def query(
        self,
        *,
        start_tick: int | None = None,
        end_tick: int | None = None,
        participant_id: str | None = None,
        witness_id: str | None = None,
        event_type: str | None = None,
    ) -> tuple[WorldEvent, ...]:
        """Return matching events in stable timeline order; tick bounds are inclusive."""
        if start_tick is not None and (isinstance(start_tick, bool) or not isinstance(start_tick, int) or start_tick < 0):
            raise ValueError("start_tick must be a non-negative integer or None")
        if end_tick is not None and (isinstance(end_tick, bool) or not isinstance(end_tick, int) or end_tick < 0):
            raise ValueError("end_tick must be a non-negative integer or None")
        if start_tick is not None and end_tick is not None and start_tick > end_tick:
            raise ValueError("start_tick cannot exceed end_tick")
        if participant_id is not None:
            _non_empty("participant_id", participant_id)
        if witness_id is not None:
            _non_empty("witness_id", witness_id)
        if event_type is not None:
            _non_empty("event_type", event_type)
        matches = (
            event for event in self._events.values()
            if (start_tick is None or event.tick >= start_tick)
            and (end_tick is None or event.tick <= end_tick)
            and (participant_id is None or participant_id in event.participants)
            and (witness_id is None or witness_id in event.witnesses)
            and (event_type is None or event.event_type == event_type)
        )
        return tuple(sorted(matches, key=lambda item: (item.tick, item.event_id)))

    def snapshot(self) -> tuple[WorldEvent, ...]:
        """Return a stable, immutable representation suitable for save serialization."""
        return tuple(sorted(self._events.values(), key=lambda item: (item.tick, item.event_id)))

    @classmethod
    def from_snapshot(cls, snapshot: Iterable[WorldEvent]) -> "WorldEventLedger":
        """Restore a ledger, rejecting conflicting IDs in the supplied snapshot."""
        return cls(snapshot)

    def __len__(self) -> int:
        return len(self._events)
