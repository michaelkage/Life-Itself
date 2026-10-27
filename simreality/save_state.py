"""Portable JSON save envelope for authoritative event history and simulation clock.

This module deliberately serializes only the state it owns. It does not pretend
that arbitrary NPCs or adapter internals are restored; those require their own
versioned codecs and are listed as explicit extension points.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
from typing import Any

from .world_events import WorldEvent, WorldEventLedger


@dataclass(frozen=True)
class SimulationSaveEnvelope:
    """Versioned event-journal save with a monotonic simulation clock."""

    current_tick: int
    events: tuple[WorldEvent, ...]
    metadata: tuple[tuple[str, str | int | float | bool | None], ...] = ()

    SCHEMA_VERSION = 1

    def __post_init__(self) -> None:
        if isinstance(self.current_tick, bool) or not isinstance(self.current_tick, int) or self.current_tick < 0:
            raise ValueError("current_tick must be a non-negative integer")
        if not isinstance(self.events, tuple) or any(not isinstance(item, WorldEvent) for item in self.events):
            raise ValueError("events must be a tuple of WorldEvent records")
        if any(event.tick > self.current_tick for event in self.events):
            raise ValueError("event tick cannot be later than current_tick")
        if len({event.event_id for event in self.events}) != len(self.events):
            raise ValueError("event IDs must be unique")
        if tuple(sorted(self.events, key=lambda event: (event.tick, event.event_id))) != self.events:
            raise ValueError("events must be sorted by tick and event ID")
        if not isinstance(self.metadata, tuple):
            raise ValueError("metadata must be a tuple of key/value pairs")
        keys = []
        for item in self.metadata:
            if not isinstance(item, tuple) or len(item) != 2:
                raise ValueError("each metadata item must be a (key, value) tuple")
            key, value = item
            if not isinstance(key, str) or not key.strip():
                raise ValueError("metadata keys must be non-empty strings")
            if value is not None and not isinstance(value, (str, int, float, bool)):
                raise ValueError("metadata values must be JSON scalar values")
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError("metadata float values must be finite")
            keys.append(key)
        if len(keys) != len(set(keys)):
            raise ValueError("metadata keys must be unique")
        if tuple(sorted(self.metadata, key=lambda item: item[0])) != self.metadata:
            raise ValueError("metadata must be sorted by key")

    @classmethod
    def capture(
        cls,
        current_tick: int,
        events: WorldEventLedger,
        *,
        metadata: dict[str, str | int | float | bool | None] | None = None,
    ) -> "SimulationSaveEnvelope":
        if not isinstance(events, WorldEventLedger):
            raise TypeError("events must be a WorldEventLedger")
        return cls(
            current_tick=current_tick,
            events=events.snapshot(),
            metadata=tuple(sorted((metadata or {}).items())),
        )

    def to_json(self) -> str:
        payload: dict[str, Any] = {
            "schema_version": self.SCHEMA_VERSION,
            "current_tick": self.current_tick,
            "events": [
                {
                    "event_id": event.event_id,
                    "tick": event.tick,
                    "event_type": event.event_type,
                    "participants": list(event.participants),
                    "witnesses": list(event.witnesses),
                    "attributes": [[key, value] for key, value in event.attributes],
                }
                for event in self.events
            ],
            "metadata": [[key, value] for key, value in self.metadata],
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)

    @classmethod
    def from_json(cls, payload: str) -> "SimulationSaveEnvelope":
        try:
            raw = json.loads(payload)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("save payload must be valid JSON text") from exc
        if not isinstance(raw, dict) or raw.get("schema_version") != cls.SCHEMA_VERSION:
            raise ValueError("unsupported simulation save schema version")
        try:
            events = tuple(sorted((
                WorldEvent(
                    event_id=item["event_id"],
                    tick=item["tick"],
                    event_type=item["event_type"],
                    participants=tuple(item.get("participants", ())),
                    witnesses=tuple(item.get("witnesses", ())),
                    attributes=tuple((pair[0], pair[1]) for pair in item.get("attributes", ())),
                )
                for item in raw["events"]
            ), key=lambda event: (event.tick, event.event_id)))
            metadata = tuple(sorted(
                ((item[0], item[1]) for item in raw.get("metadata", ())),
                key=lambda item: item[0],
            ))
            return cls(
                current_tick=raw["current_tick"],
                events=events,
                metadata=metadata,
            )
        except (KeyError, TypeError, IndexError) as exc:
            raise ValueError("save payload has an invalid structure") from exc

    def restore_event_ledger(self) -> WorldEventLedger:
        """Restore the authoritative event ledger without mutating other systems."""
        return WorldEventLedger.from_snapshot(self.events)
