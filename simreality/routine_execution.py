"""Idempotent ledger of resolved NPC routine executions.

All randomness is supplied by the caller as an explicit sample. The ledger
stores the complete request and result so replay after loading returns the
original decision rather than resolving against changed inputs.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Iterable

from .routines import RoutineBlock, RoutineBook, RoutineDisruption, RoutineResolution


@dataclass(frozen=True)
class RoutineExecution:
    execution_id: str
    routine_id: str
    minute_of_day: int
    disruptions: tuple[RoutineDisruption, ...]
    outcome_sample: float
    resolution: RoutineResolution

    def __post_init__(self):
        if not isinstance(self.execution_id, str) or not self.execution_id.strip():
            raise ValueError("execution_id must be a non-empty string")
        if not isinstance(self.routine_id, str) or not self.routine_id.strip():
            raise ValueError("routine_id must be a non-empty string")
        if isinstance(self.minute_of_day, bool) or not isinstance(self.minute_of_day, int) or not 0 <= self.minute_of_day < 1440:
            raise ValueError("minute_of_day must be an integer from 0 to 1439")
        if not isinstance(self.disruptions, tuple) or any(not isinstance(d, RoutineDisruption) for d in self.disruptions):
            raise ValueError("disruptions must be a tuple of RoutineDisruption values")
        if not isinstance(self.resolution, RoutineResolution):
            raise ValueError("resolution must be a RoutineResolution")


def _block_payload(b: RoutineBlock) -> dict:
    return {"routine_id": b.routine_id, "owner_id": b.owner_id, "activity": b.activity,
            "location_id": b.location_id, "start_minute": b.start_minute, "end_minute": b.end_minute,
            "priority": b.priority, "flexibility_minutes": b.flexibility_minutes,
            "fallback_activity": b.fallback_activity, "fallback_location_id": b.fallback_location_id}


def _disruption_payload(d: RoutineDisruption) -> dict:
    return {"disruption_id": d.disruption_id, "owner_id": d.owner_id, "kind": d.kind.value,
            "severity": d.severity, "start_minute": d.start_minute, "end_minute": d.end_minute,
            "affected_location_id": d.affected_location_id, "delay_minutes": d.delay_minutes,
            "alternative_activity": d.alternative_activity, "alternative_location_id": d.alternative_location_id}


def _resolution_payload(r: RoutineResolution) -> dict:
    return {"routine_id": r.routine_id, "owner_id": r.owner_id,
            "intended_activity": r.intended_activity, "intended_location_id": r.intended_location_id,
            "actual_activity": r.actual_activity, "actual_location_id": r.actual_location_id,
            "outcome": r.outcome.value, "delay_minutes": r.delay_minutes,
            "disruption_ids": list(r.disruption_ids), "reason": r.reason}


def _execution_payload(e: RoutineExecution) -> dict:
    return {"execution_id": e.execution_id, "routine_id": e.routine_id,
            "minute_of_day": e.minute_of_day,
            "disruptions": [_disruption_payload(d) for d in sorted(e.disruptions, key=lambda x: x.disruption_id)],
            "outcome_sample": e.outcome_sample, "resolution": _resolution_payload(e.resolution)}


def _execution_signature(e: RoutineExecution) -> str:
    return json.dumps(_execution_payload(e), sort_keys=True, separators=(",", ":"), allow_nan=False)


class RoutineExecutionLedger:
    """Record resolved routines with stable IDs and conflict-detecting replay."""

    def __init__(self):
        self._records: dict[str, RoutineExecution] = {}

    def execute(self, execution_id: str, book: RoutineBook, block: RoutineBlock,
                minute_of_day: int, disruptions: Iterable[RoutineDisruption] = (),
                *, outcome_sample: float = 0.0) -> RoutineExecution:
        if not isinstance(execution_id, str) or not execution_id.strip():
            raise ValueError("execution_id must be a non-empty string")
        if not isinstance(book, RoutineBook):
            raise TypeError("book must be a RoutineBook")
        supplied = tuple(sorted(disruptions, key=lambda d: d.disruption_id))
        existing = self._records.get(execution_id)
        if existing is not None:
            # A replay is identified from its request inputs before resolving
            # anything again. This returns the authoritative stored result even
            # if downstream tuning changes after the original execution.
            same_request = (
                existing.routine_id == block.routine_id
                and existing.minute_of_day == minute_of_day
                and existing.disruptions == supplied
                and existing.outcome_sample == outcome_sample
            )
            if not same_request:
                raise ValueError(f"conflicting routine execution ID: {execution_id}")
            return existing
        resolution = book.resolve(block, minute_of_day, supplied, outcome_sample=outcome_sample)
        record = RoutineExecution(execution_id, block.routine_id, minute_of_day,
                                  supplied, outcome_sample, resolution)
        self._records[execution_id] = record
        return record

    def get(self, execution_id: str) -> RoutineExecution | None:
        return self._records.get(execution_id)

    def snapshot(self) -> tuple[RoutineExecution, ...]:
        return tuple(self._records[key] for key in sorted(self._records))

    def _restore_record(self, record: RoutineExecution) -> None:
        if record.execution_id in self._records:
            raise ValueError(f"duplicate routine execution ID: {record.execution_id}")
        self._records[record.execution_id] = record
