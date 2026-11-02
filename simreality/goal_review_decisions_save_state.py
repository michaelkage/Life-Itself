"""Canonical persistence for the NPC goal-review decision ledger."""
from __future__ import annotations

from dataclasses import dataclass
import json

from .goal_review import GoalReviewAction
from .goal_review_decisions import GoalReviewDecision, GoalReviewDecisionLedger


@dataclass(frozen=True)
class GoalReviewDecisionSnapshot:
    records: tuple[tuple[object, ...], ...]
    SCHEMA_VERSION = 1

    def __post_init__(self) -> None:
        if not isinstance(self.records, tuple):
            raise ValueError("records must be a tuple")
        ids = [record[0] for record in self.records if isinstance(record, tuple) and record]
        if len(ids) != len(self.records) or ids != sorted(ids) or len(ids) != len(set(ids)):
            raise ValueError("decision records must have unique sorted IDs")
        # Reconstruct every record to enforce the same invariants as live entries.
        for record in self.records:
            if len(record) != 15:
                raise ValueError("invalid goal review decision record")
            GoalReviewDecision(
                record[0], record[1], record[2], record[3], record[4],
                GoalReviewAction(record[5]), record[6], record[7], record[8],
                record[9], record[10], record[11], record[12], record[13], record[14],
            )

    @classmethod
    def capture(cls, ledger: GoalReviewDecisionLedger) -> "GoalReviewDecisionSnapshot":
        if not isinstance(ledger, GoalReviewDecisionLedger):
            raise TypeError("ledger must be a GoalReviewDecisionLedger")
        records = []
        for item in ledger.entries():
            records.append((
                item.decision_id, item.event_id, item.owner_id, item.goal_id,
                item.policy_id, item.action.value, item.accepted, item.decision_tick,
                item.rationale, item.current_category, item.proposed_category,
                item.current_priority, item.proposed_priority,
                item.current_confidence, item.proposed_confidence,
            ))
        return cls(tuple(sorted(records, key=lambda record: record[0])))

    def to_json(self) -> str:
        return json.dumps(
            {"schema_version": self.SCHEMA_VERSION,
             "records": [list(record) for record in self.records]},
            sort_keys=True, separators=(",", ":"), allow_nan=False,
        )

    @classmethod
    def from_json(cls, payload: str) -> "GoalReviewDecisionSnapshot":
        try:
            raw = json.loads(payload)
            if not isinstance(raw, dict) or raw.get("schema_version") != cls.SCHEMA_VERSION:
                raise ValueError("unsupported goal review decision schema version")
            records = []
            for record in raw["records"]:
                if not isinstance(record, list) or len(record) != 15:
                    raise ValueError("invalid goal review decision record")
                records.append(tuple(record))
            result = cls(tuple(records))
            if result.to_json() != payload:
                raise ValueError("goal review decision snapshot must use canonical JSON")
            return result
        except ValueError:
            raise
        except (TypeError, KeyError, IndexError, json.JSONDecodeError) as exc:
            raise ValueError("invalid goal review decision snapshot") from exc

    def restore(self) -> GoalReviewDecisionLedger:
        decisions = []
        for record in self.records:
            decisions.append(GoalReviewDecision(
                record[0], record[1], record[2], record[3], record[4],
                GoalReviewAction(record[5]), record[6], record[7], record[8],
                record[9], record[10], record[11], record[12], record[13], record[14],
            ))
        return GoalReviewDecisionLedger(decisions)
