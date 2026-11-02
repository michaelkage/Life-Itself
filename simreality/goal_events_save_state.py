"""Versioned persistence for GoalEventAdapter replay protection."""
from __future__ import annotations
from dataclasses import dataclass
import json
from .goal_events import GoalEventAdapter

@dataclass(frozen=True)
class GoalEventReplaySnapshot:
    entries: tuple[tuple[str, tuple[object, ...]], ...]
    SCHEMA_VERSION = 1

    def __post_init__(self):
        ids = [entry[0] for entry in self.entries]
        if ids != sorted(ids) or len(ids) != len(set(ids)):
            raise ValueError("goal event replay entries must have unique sorted IDs")

    @classmethod
    def capture(cls, adapter: GoalEventAdapter):
        if not isinstance(adapter, GoalEventAdapter):
            raise TypeError("adapter must be a GoalEventAdapter")
        return cls(tuple((key, value) for key, value in sorted(adapter._processed.items())))

    def to_json(self):
        return json.dumps({"schema_version": self.SCHEMA_VERSION,
                           "entries": [[key, list(value)] for key, value in self.entries]},
                          sort_keys=True, separators=(",", ":"), allow_nan=False)

    @classmethod
    def from_json(cls, payload):
        try:
            raw = json.loads(payload)
            if not isinstance(raw, dict) or raw.get("schema_version") != cls.SCHEMA_VERSION:
                raise ValueError("unsupported goal event replay schema version")
            entries = []
            for key, value in raw["entries"]:
                if (not isinstance(key, str) or not key or not isinstance(value, list)
                        or len(value) != 5):
                    raise ValueError("invalid goal event replay entry")
                tick, event_type, participants, witnesses, attributes = value
                if (isinstance(tick, bool) or not isinstance(tick, int) or tick < 0
                        or not isinstance(event_type, str)
                        or not isinstance(participants, list)
                        or not isinstance(witnesses, list)
                        or not all(isinstance(x, str) for x in participants + witnesses)
                        or not isinstance(attributes, str)):
                    raise ValueError("invalid goal event replay signature")
                entries.append((key, (tick, event_type, tuple(participants),
                                      tuple(witnesses), attributes)))
            result = cls(tuple(entries))
            if result.to_json() != payload:
                raise ValueError("goal event replay snapshot must use canonical JSON")
            return result
        except ValueError:
            raise
        except (TypeError, KeyError, IndexError, json.JSONDecodeError) as exc:
            raise ValueError("invalid goal event replay snapshot") from exc

    def restore(self, adapter: GoalEventAdapter):
        if not isinstance(adapter, GoalEventAdapter):
            raise TypeError("adapter must be a GoalEventAdapter")
        adapter._processed = dict(self.entries)
