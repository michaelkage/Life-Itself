"""Canonical persistence for append-only NPC goal commitments."""
from __future__ import annotations

from dataclasses import dataclass
import json

from .goal_arbitration import GoalCommitment, GoalCommitmentLedger


@dataclass(frozen=True)
class GoalCommitmentSnapshot:
    records: tuple[tuple[object, ...], ...]
    SCHEMA_VERSION = 1

    def __post_init__(self) -> None:
        if not isinstance(self.records, tuple):
            raise ValueError("records must be a tuple")
        entries = []
        for record in self.records:
            if not isinstance(record, tuple) or len(record) != 8:
                raise ValueError("invalid goal commitment record")
            entries.append(GoalCommitment(
                record[0], record[1], record[2], record[3], record[4],
                tuple(record[5]), record[6], record[7],
            ))
        if len({item.commitment_id for item in entries}) != len(entries):
            raise ValueError("commitment IDs must be unique")
        if tuple(sorted(entries, key=lambda x: (x.tick, x.owner_id, x.commitment_id))) != tuple(entries):
            raise ValueError("commitment records must use canonical chronological order")
        if len({(item.owner_id, item.tick) for item in entries}) != len(entries):
            raise ValueError("an NPC may have only one commitment per tick")
        GoalCommitmentLedger(tuple(entries))

    @classmethod
    def capture(cls, ledger: GoalCommitmentLedger) -> "GoalCommitmentSnapshot":
        if not isinstance(ledger, GoalCommitmentLedger):
            raise TypeError("ledger must be GoalCommitmentLedger")
        return cls(tuple(
            (x.commitment_id, x.assessment_id, x.owner_id, x.tick,
             x.selected_goal_id, tuple(x.deferred_goal_ids),
             x.selected_score, x.rationale)
            for x in ledger.entries()
        ))

    def to_json(self) -> str:
        return json.dumps(
            {"schema_version": self.SCHEMA_VERSION,
             "records": [list(x) for x in self.records]},
            sort_keys=True, separators=(",", ":"), allow_nan=False,
        )

    @classmethod
    def from_json(cls, payload: str) -> "GoalCommitmentSnapshot":
        try:
            raw = json.loads(payload)
            if not isinstance(raw, dict) or raw.get("schema_version") != cls.SCHEMA_VERSION:
                raise ValueError("unsupported goal commitment schema version")
            result = cls(tuple(
                (x[0], x[1], x[2], x[3], x[4], tuple(x[5]), x[6], x[7])
                for x in raw["records"]
            ))
            if result.to_json() != payload:
                raise ValueError("goal commitment snapshot must use canonical JSON")
            return result
        except ValueError:
            raise
        except (TypeError, KeyError, IndexError, json.JSONDecodeError) as exc:
            raise ValueError("invalid goal commitment snapshot") from exc

    def restore(self) -> GoalCommitmentLedger:
        entries = tuple(GoalCommitment(
            x[0], x[1], x[2], x[3], x[4], tuple(x[5]), x[6], x[7]
        ) for x in self.records)
        return GoalCommitmentLedger(entries)
