"""Translate resolved NPC routine executions into authoritative world events.

The adapter records explicit routine outcomes in the shared event journal so
other systems can observe, remember, or interpret them. It does not invent
witnesses, reactions, travel, or consequences.
"""
from __future__ import annotations

from typing import Iterable, Mapping

from .routine_execution import RoutineExecution
from .world_events import WorldEvent, WorldEventLedger


class RoutineWorldEventAdapter:
    """Append canonical routine outcomes to a world event ledger."""

    def __init__(self, events: WorldEventLedger) -> None:
        if not isinstance(events, WorldEventLedger):
            raise TypeError("events must be a WorldEventLedger")
        self.events = events

    def record(
        self,
        tick: int,
        executions: Iterable[RoutineExecution],
        *,
        witnesses_by_execution: Mapping[str, Iterable[str]] | None = None,
    ) -> tuple[WorldEvent, ...]:
        """Record one event per execution, preserving caller-supplied witnesses.

        Event IDs derive from the execution IDs. Identical retries are
        idempotent through WorldEventLedger; conflicting retries are rejected.
        Witnesses are optional and must be explicit because routine outcomes do
        not establish who could see or hear the NPC.
        """
        if isinstance(tick, bool) or not isinstance(tick, int) or tick < 0:
            raise ValueError("tick must be a non-negative integer")
        items = tuple(executions)
        if any(not isinstance(item, RoutineExecution) for item in items):
            raise TypeError("executions must contain only RoutineExecution values")
        ids = [item.execution_id for item in items]
        if len(ids) != len(set(ids)):
            raise ValueError("execution IDs must be unique within a batch")
        witness_map = witnesses_by_execution or {}
        unknown = set(witness_map) - set(ids)
        if unknown:
            raise ValueError(f"witness mapping contains unknown execution ID: {sorted(unknown)[0]}")

        events = []
        for execution in sorted(items, key=lambda item: item.execution_id):
            result = execution.resolution
            witnesses = tuple(witness_map.get(execution.execution_id, ()))
            event = WorldEventLedger.make_event(
                f"routine:{execution.execution_id}",
                tick,
                "routine_execution",
                participants=(result.owner_id,),
                witnesses=witnesses,
                attributes={
                    "routine_id": execution.routine_id,
                    "minute_of_day": execution.minute_of_day,
                    "intended_activity": result.intended_activity,
                    "intended_location_id": result.intended_location_id,
                    "actual_activity": result.actual_activity,
                    "actual_location_id": result.actual_location_id,
                    "outcome": result.outcome.value,
                    "delay_minutes": result.delay_minutes,
                    "reason": result.reason,
                    "disruption_ids": ",".join(result.disruption_ids),
                },
            )
            events.append(event)
        return self.events.append_many(events)
