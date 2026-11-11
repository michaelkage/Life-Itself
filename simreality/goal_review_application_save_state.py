"""Canonical persistence for accepted goal-review application history."""
from __future__ import annotations

from dataclasses import dataclass
import json

from .goal_review import GoalReviewAction
from .goal_review_application import GoalReviewApplication, GoalReviewApplicationLedger
from .goals import GoalStatus


@dataclass(frozen=True)
class GoalReviewApplicationSnapshot:
    records: tuple[tuple[object, ...], ...]
    SCHEMA_VERSION = 1

    def __post_init__(self) -> None:
        if not isinstance(self.records, tuple):
            raise ValueError("records must be a tuple")
        ids = [record[0] for record in self.records if isinstance(record, tuple) and record]
        if len(ids) != len(self.records) or ids != sorted(ids) or len(ids) != len(set(ids)):
            raise ValueError("application records must have unique sorted decision IDs")
        for record in self.records:
            if len(record) != 9:
                raise ValueError("invalid goal review application record")
            GoalReviewApplication(
                record[0], record[1], record[2], record[3],
                GoalReviewAction(record[4]), record[5], record[6],
                record[7], GoalStatus(record[8]),
            )

    @classmethod
    def capture(cls, ledger: GoalReviewApplicationLedger) -> "GoalReviewApplicationSnapshot":
        if not isinstance(ledger, GoalReviewApplicationLedger):
            raise TypeError("ledger must be GoalReviewApplicationLedger")
        records = tuple(sorted((
            item.decision_id, item.goal_id, item.owner_id, item.applied_tick,
            item.action.value, item.resulting_category, item.resulting_priority,
            item.resulting_confidence, item.resulting_status.value,
        ) for item in ledger.entries()))
        return cls(records)

    def to_json(self) -> str:
        return json.dumps(
            {"schema_version": self.SCHEMA_VERSION,
             "records": [list(record) for record in self.records]},
            sort_keys=True, separators=(",", ":"), allow_nan=False,
        )

    @classmethod
    def from_json(cls, payload: str) -> "GoalReviewApplicationSnapshot":
        try:
            raw = json.loads(payload)
            if not isinstance(raw, dict) or raw.get("schema_version") != cls.SCHEMA_VERSION:
                raise ValueError("unsupported goal review application schema version")
            records = raw["records"]
            if not isinstance(records, list) or any(not isinstance(row, list) or len(row) != 9 for row in records):
                raise ValueError("invalid goal review application records")
            snapshot = cls(tuple(tuple(row) for row in records))
            if snapshot.to_json() != payload:
                raise ValueError("goal review application snapshot must use canonical JSON")
            return snapshot
        except ValueError:
            raise
        except (TypeError, KeyError, IndexError, json.JSONDecodeError) as exc:
            raise ValueError("invalid goal review application snapshot") from exc

    def restore(self) -> GoalReviewApplicationLedger:
        return GoalReviewApplicationLedger(tuple(
            GoalReviewApplication(
                row[0], row[1], row[2], row[3], GoalReviewAction(row[4]),
                row[5], row[6], row[7], GoalStatus(row[8]),
            ) for row in self.records
        ))
