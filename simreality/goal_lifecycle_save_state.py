"""Canonical persistence for append-only NPC goal lifecycle history."""
from __future__ import annotations

from dataclasses import dataclass
import json

from .npc_goal_emergence import GoalLifecycleEvent, GoalLifecycleLedger


@dataclass(frozen=True)
class GoalLifecycleSnapshot:
    records: tuple[tuple[object, ...], ...]
    SCHEMA_VERSION = 1

    def __post_init__(self):
        if not isinstance(self.records, tuple):
            raise ValueError("records must be a tuple")
        events = []
        ids = []
        for record in self.records:
            if not isinstance(record, tuple) or len(record) != 8:
                raise ValueError("invalid goal lifecycle record")
            ids.append(record[0])
            events.append(GoalLifecycleEvent(
                record[0], record[1], record[2], record[3], record[4],
                record[5], record[6], tuple(record[7]),
            ))
        if ids != sorted(ids) or len(ids) != len(set(ids)):
            raise ValueError("lifecycle event IDs must be unique and sorted")
        # Ledger reconstruction validates transition continuity and terminal rules.
        ordered = sorted(events, key=lambda x: (x.tick, x.event_id))
        ledger = GoalLifecycleLedger()
        for event in ordered:
            ledger.append(event)

    @classmethod
    def capture(cls, ledger):
        if not isinstance(ledger, GoalLifecycleLedger):
            raise TypeError("ledger must be GoalLifecycleLedger")
        records = tuple(sorted((
            (e.event_id, e.goal_id, e.owner_id, e.from_status, e.to_status,
             e.tick, e.reason, tuple(e.evidence_ids))
            for e in ledger.snapshot()
        ), key=lambda x: x[0]))
        return cls(records)

    def to_json(self):
        return json.dumps(
            {"schema_version": self.SCHEMA_VERSION,
             "records": [list(x) for x in self.records]},
            sort_keys=True, separators=(",", ":"), allow_nan=False,
        )

    @classmethod
    def from_json(cls, payload):
        try:
            raw = json.loads(payload)
            if not isinstance(raw, dict) or raw.get("schema_version") != cls.SCHEMA_VERSION:
                raise ValueError("unsupported goal lifecycle schema version")
            records = tuple(
                (x[0], x[1], x[2], x[3], x[4], x[5], x[6], tuple(x[7]))
                for x in raw["records"]
            )
            result = cls(records)
            if result.to_json() != payload:
                raise ValueError("goal lifecycle snapshot must use canonical JSON")
            return result
        except ValueError:
            raise
        except (TypeError, KeyError, IndexError, json.JSONDecodeError) as exc:
            raise ValueError("invalid goal lifecycle snapshot") from exc

    def restore(self):
        events = tuple(GoalLifecycleEvent(
            r[0], r[1], r[2], r[3], r[4], r[5], r[6], tuple(r[7])
        ) for r in sorted(self.records, key=lambda x: (x[5], x[0])))
        return GoalLifecycleLedger(events)
