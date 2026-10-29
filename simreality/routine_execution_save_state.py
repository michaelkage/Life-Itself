"""Canonical JSON persistence for NPC routine execution history."""
from __future__ import annotations

from dataclasses import dataclass
import json

from .routines import DisruptionKind, RoutineDisruption, RoutineOutcome, RoutineResolution
from .routine_execution import (
    RoutineExecution, RoutineExecutionLedger, _block_payload, _disruption_payload,
    _execution_payload, _resolution_payload,
)


def _read_disruption(item):
    return RoutineDisruption(
        item["disruption_id"], item["owner_id"], DisruptionKind(item["kind"]),
        item["severity"], item["start_minute"], item["end_minute"],
        item.get("affected_location_id"), item.get("delay_minutes", 0),
        item.get("alternative_activity"), item.get("alternative_location_id"),
    )


def _read_resolution(item):
    return RoutineResolution(
        item["routine_id"], item["owner_id"], item["intended_activity"],
        item["intended_location_id"], item["actual_activity"],
        item.get("actual_location_id"), RoutineOutcome(item["outcome"]),
        item["delay_minutes"], tuple(item["disruption_ids"]), item["reason"],
    )


def _read_execution(item):
    return RoutineExecution(
        item["execution_id"], item["routine_id"], item["minute_of_day"],
        tuple(_read_disruption(d) for d in item["disruptions"]),
        item["outcome_sample"], _read_resolution(item["resolution"]),
    )


@dataclass(frozen=True)
class RoutineExecutionSnapshot:
    """Versioned, canonical snapshot of execution requests and resolved outcomes."""
    records: tuple[RoutineExecution, ...]

    SCHEMA_VERSION = 1

    def __post_init__(self):
        if not isinstance(self.records, tuple) or any(not isinstance(r, RoutineExecution) for r in self.records):
            raise ValueError("records must be a tuple of RoutineExecution values")
        ids = [r.execution_id for r in self.records]
        if ids != sorted(ids) or len(ids) != len(set(ids)):
            raise ValueError("routine execution records must have unique canonical IDs")

    @classmethod
    def capture(cls, ledger: RoutineExecutionLedger) -> "RoutineExecutionSnapshot":
        if not isinstance(ledger, RoutineExecutionLedger):
            raise TypeError("ledger must be a RoutineExecutionLedger")
        return cls(ledger.snapshot())

    def to_json(self) -> str:
        return json.dumps({"schema_version": self.SCHEMA_VERSION,
                           "records": [_execution_payload(r) for r in self.records]},
                          sort_keys=True, separators=(",", ":"), allow_nan=False)

    @classmethod
    def from_json(cls, payload: str) -> "RoutineExecutionSnapshot":
        try:
            raw = json.loads(payload)
            if not isinstance(raw, dict) or raw.get("schema_version") != cls.SCHEMA_VERSION:
                raise ValueError("unsupported routine execution snapshot schema version")
            records = tuple(_read_execution(item) for item in raw["records"])
            snapshot = cls(records)
            canonical = json.dumps({"schema_version": cls.SCHEMA_VERSION,
                                    "records": [_execution_payload(r) for r in records]},
                                   sort_keys=True, separators=(",", ":"), allow_nan=False)
            if canonical != payload:
                raise ValueError("routine execution snapshot must use canonical JSON")
            return snapshot
        except ValueError:
            raise
        except (TypeError, KeyError, IndexError, json.JSONDecodeError) as exc:
            raise ValueError("invalid routine execution snapshot") from exc

    def restore(self) -> RoutineExecutionLedger:
        ledger = RoutineExecutionLedger()
        for record in self.records:
            ledger._restore_record(record)
        return ledger
