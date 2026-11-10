"""Arrival-gated execution of scheduled NPC routines.

A scheduled activity can begin only after its routine-linked journey has
arrived. Early arrivals wait; late arrivals consume the remaining flexibility;
arrivals after the scheduled end are recorded as missed (or redirected to an
explicit fallback). Execution IDs are journey-scoped and replay-safe.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Mapping

from .routine_execution import RoutineExecution, RoutineExecutionLedger
from .routine_world_events import RoutineWorldEventAdapter
from .routines import (
    RoutineBook, RoutineDisruption, RoutineOutcome, RoutineResolution,
)
from .travel import TravelLedger
from .world_events import WorldEvent


@dataclass(frozen=True)
class RoutineArrivalResult:
    journey_id: str
    routine_id: str
    owner_id: str
    status: str
    execution: RoutineExecution | None = None

    def __post_init__(self) -> None:
        if self.status not in ("waiting", "executed", "missed", "already_executed"):
            raise ValueError("invalid routine arrival status")


class RoutineArrivalAdapter:
    """Resolve routine-linked arrivals against an explicit simulation minute."""

    def __init__(self, executions: RoutineExecutionLedger) -> None:
        if not isinstance(executions, RoutineExecutionLedger):
            raise TypeError("executions must be a RoutineExecutionLedger")
        self.executions = executions

    def process(
        self,
        tick: int,
        minute_of_day: int,
        book: RoutineBook,
        travel: TravelLedger,
        *,
        disruptions: Iterable[RoutineDisruption] = (),
        outcome_samples: Mapping[str, float],
        world_events: RoutineWorldEventAdapter | None = None,
    ) -> tuple[RoutineArrivalResult, ...]:
        if isinstance(tick, bool) or not isinstance(tick, int) or tick < 0:
            raise ValueError("tick must be a non-negative integer")
        if isinstance(minute_of_day, bool) or not isinstance(minute_of_day, int) or not 0 <= minute_of_day < 1440:
            raise ValueError("minute_of_day must be an integer from 0 to 1439")
        if not isinstance(book, RoutineBook) or not isinstance(travel, TravelLedger):
            raise TypeError("book and travel must be RoutineBook and TravelLedger")
        if not isinstance(outcome_samples, Mapping):
            raise TypeError("outcome_samples must map routine IDs to samples")
        if world_events is not None and not isinstance(world_events, RoutineWorldEventAdapter):
            raise TypeError("world_events must be a RoutineWorldEventAdapter or None")
        supplied = tuple(disruptions)
        if any(not isinstance(item, RoutineDisruption) for item in supplied):
            raise TypeError("disruptions must contain RoutineDisruption values")
        ids = [item.disruption_id for item in supplied]
        if len(ids) != len(set(ids)):
            raise ValueError("disruption IDs must be unique")

        blocks = {block.routine_id: block for block in book.snapshot()}
        results: list[RoutineArrivalResult] = []
        materialized: list[RoutineExecution] = []
        for journey in travel.snapshot():
            if journey.status != "arrived" or journey.routine_id is None:
                continue
            block = blocks.get(journey.routine_id)
            if block is None or block.owner_id != journey.owner_id or block.location_id != journey.destination:
                raise ValueError(f"arrived journey does not match a saved routine: {journey.journey_id}")
            execution_prefix = f"arrival:{journey.journey_id}:{block.routine_id}:"
            execution_id = f"{execution_prefix}{tick}"
            previous = self.executions.get(execution_id)
            if previous is None:
                earlier = next(
                    (item for item in self.executions.snapshot()
                     if item.execution_id.startswith(execution_prefix)),
                    None,
                )
                if earlier is not None:
                    results.append(RoutineArrivalResult(
                        journey.journey_id, block.routine_id, block.owner_id,
                        "already_executed", earlier,
                    ))
                    continue
            if minute_of_day < block.start_minute and previous is None:
                results.append(RoutineArrivalResult(
                    journey.journey_id, block.routine_id, block.owner_id, "waiting",
                ))
                continue
            if block.routine_id not in outcome_samples:
                raise ValueError(f"missing outcome sample for routine: {block.routine_id}")
            sample = outcome_samples[block.routine_id]
            if isinstance(sample, bool) or not isinstance(sample, (int, float)) or not math.isfinite(sample) or not 0.0 <= sample <= 1.0:
                raise ValueError("outcome samples must be finite values between 0 and 1")
            relevant = tuple(sorted(
                (item for item in supplied if item.owner_id == block.owner_id),
                key=lambda item: item.disruption_id,
            ))
            base = book.resolve(block, minute_of_day, relevant, outcome_sample=float(sample))
            late_by = max(0, minute_of_day - block.start_minute)
            after_end = minute_of_day >= block.end_minute
            resolution = self._apply_arrival_delay(block, base, late_by, after_end)
            record = RoutineExecution(
                execution_id, block.routine_id, minute_of_day, relevant,
                float(sample), resolution,
            )
            if previous is not None:
                if previous != record:
                    raise ValueError(f"conflicting routine arrival execution: {execution_id}")
                results.append(RoutineArrivalResult(
                    journey.journey_id, block.routine_id, block.owner_id,
                    "already_executed", previous,
                ))
                materialized.append(previous)
                continue
            self.executions._restore_record(record)
            status = "missed" if resolution.outcome is RoutineOutcome.MISSED else "executed"
            results.append(RoutineArrivalResult(
                journey.journey_id, block.routine_id, block.owner_id, status, record,
            ))
            materialized.append(record)

        if world_events is not None and materialized:
            world_events.record(tick, tuple(materialized))
        return tuple(results)

    @staticmethod
    def _apply_arrival_delay(block, base: RoutineResolution, late_by: int, after_end: bool) -> RoutineResolution:
        if late_by == 0 and not after_end:
            return base
        total_delay = base.delay_minutes + late_by
        if base.outcome is RoutineOutcome.REDIRECTED:
            return RoutineResolution(
                base.routine_id, base.owner_id, base.intended_activity,
                base.intended_location_id, base.actual_activity,
                base.actual_location_id, base.outcome, total_delay,
                base.disruption_ids, base.reason + "; arrival was late",
            )
        if base.outcome is RoutineOutcome.MISSED:
            return RoutineResolution(
                base.routine_id, base.owner_id, base.intended_activity,
                base.intended_location_id, base.actual_activity, None,
                RoutineOutcome.MISSED, total_delay, base.disruption_ids,
                base.reason + "; arrival was late",
            )
        if not after_end and total_delay <= block.flexibility_minutes:
            return RoutineResolution(
                block.routine_id, block.owner_id, block.activity, block.location_id,
                block.activity, block.location_id, RoutineOutcome.DELAYED,
                total_delay, base.disruption_ids,
                "arrived late but within the routine's flexibility window",
            )
        if block.fallback_activity or block.fallback_location_id:
            return RoutineResolution(
                block.routine_id, block.owner_id, block.activity, block.location_id,
                block.fallback_activity or block.activity,
                block.fallback_location_id or block.location_id,
                RoutineOutcome.REDIRECTED, total_delay, base.disruption_ids,
                "late arrival exceeded the routine window; explicit fallback selected",
            )
        return RoutineResolution(
            block.routine_id, block.owner_id, block.activity, block.location_id,
            block.activity, None, RoutineOutcome.MISSED, total_delay,
            base.disruption_ids,
            "arrival occurred after the routine window or exceeded its flexibility",
        )
