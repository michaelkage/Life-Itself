"""Deterministic bridge from a routine schedule to per-tick executions.

The adapter executes only routines active at the supplied minute. Disruptions
and outcome samples are explicit inputs; it does not invent events or consume
global randomness. Stable execution IDs make retries idempotent through the
existing RoutineExecutionLedger.
"""
from __future__ import annotations

from typing import Iterable, Mapping

from .routine_execution import RoutineExecution, RoutineExecutionLedger
from .routines import RoutineBook, RoutineDisruption


class RoutineTickAdapter:
    """Resolve active schedule blocks for one explicit simulation time.

    The caller supplies a stable tick_id (for example, a world tick number),
    a sample for every active routine, and the disruptions known for this
    time slice. The adapter scopes disruptions by owner in a deterministic
    way and executes blocks in stable routine-ID order.
    """

    def __init__(self, ledger: RoutineExecutionLedger | None = None) -> None:
        if ledger is not None and not isinstance(ledger, RoutineExecutionLedger):
            raise TypeError("ledger must be a RoutineExecutionLedger or None")
        self.ledger = ledger if ledger is not None else RoutineExecutionLedger()

    def execute_due(
        self,
        tick_id: str,
        book: RoutineBook,
        minute_of_day: int,
        *,
        disruptions: Iterable[RoutineDisruption] = (),
        outcome_samples: Mapping[str, float],
        owner_ids: Iterable[str] | None = None,
    ) -> tuple[RoutineExecution, ...]:
        """Execute all selected active routines, in canonical order.

        outcome_samples is keyed by routine ID. Missing samples are rejected
        rather than silently choosing a default. Extra samples are allowed so
        one shared sample map can be reused across subsets of NPCs.
        """
        if not isinstance(tick_id, str) or not tick_id.strip():
            raise ValueError("tick_id must be a non-empty string")
        if not isinstance(book, RoutineBook):
            raise TypeError("book must be a RoutineBook")
        if isinstance(minute_of_day, bool) or not isinstance(minute_of_day, int) or not 0 <= minute_of_day < 1440:
            raise ValueError("minute_of_day must be an integer from 0 to 1439")
        if not isinstance(outcome_samples, Mapping):
            raise TypeError("outcome_samples must be a mapping of routine IDs to samples")

        all_disruptions = tuple(disruptions)
        if any(not isinstance(item, RoutineDisruption) for item in all_disruptions):
            raise TypeError("disruptions must contain RoutineDisruption values")
        disruption_ids = [item.disruption_id for item in all_disruptions]
        if len(disruption_ids) != len(set(disruption_ids)):
            raise ValueError("disruption IDs must be unique within a tick")

        selected_owners = None if owner_ids is None else tuple(owner_ids)
        if selected_owners is not None:
            if any(not isinstance(owner, str) or not owner.strip() for owner in selected_owners):
                raise ValueError("owner_ids must contain non-empty strings")
            if len(selected_owners) != len(set(selected_owners)):
                raise ValueError("owner_ids must not contain duplicates")
            selected_owners = tuple(sorted(selected_owners))

        blocks = tuple(
            block for block in book.snapshot()
            if block.start_minute <= minute_of_day < block.end_minute
            and (selected_owners is None or block.owner_id in selected_owners)
        )
        results = []
        for block in blocks:
            if block.routine_id not in outcome_samples:
                raise ValueError(f"missing outcome sample for routine: {block.routine_id}")
            owner_disruptions = tuple(
                item for item in all_disruptions if item.owner_id == block.owner_id
            )
            execution_id = f"{tick_id}:{block.routine_id}"
            results.append(self.ledger.execute(
                execution_id,
                book,
                block,
                minute_of_day,
                owner_disruptions,
                outcome_sample=outcome_samples[block.routine_id],
            ))
        return tuple(results)
