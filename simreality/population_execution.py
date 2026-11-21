"""Population-level orchestration for deterministic world ticks.

The loop composes the existing event-memory/conversation coordinator with the
routine execution ledger. It does not invent witnesses, encounters, disruptions,
or random outcomes: the world driver supplies those inputs explicitly.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from .model import NPC
from .routine_execution import RoutineExecution, RoutineExecutionLedger
from .routines import RoutineBook, RoutineDisruption
from .simulation_tick import (
    ConversationIntent,
    SimulationTickCoordinator,
    SimulationTickResult,
)


@dataclass(frozen=True)
class PopulationTickResult:
    """Committed outputs from the two replay-safe phases of one population tick."""

    tick: int
    social: SimulationTickResult
    routine_executions: tuple[RoutineExecution, ...]
    processed_npc_ids: tuple[str, ...]


class PopulationExecutionLoop:
    """Run stable population phases against an explicit roster snapshot.

    Event memory and social exchange are committed by SimulationTickCoordinator.
    Routine outcomes are then committed to RoutineExecutionLedger. Each phase is
    independently idempotent and checkpointable; this class intentionally does
    not claim a cross-ledger atomic transaction. A failure in the routine phase
    leaves the social phase committed and safe to replay with the same tick inputs.
    """

    def __init__(
        self,
        coordinator: SimulationTickCoordinator,
        routine_book: RoutineBook,
        routine_ledger: RoutineExecutionLedger,
    ) -> None:
        if not isinstance(coordinator, SimulationTickCoordinator):
            raise TypeError("coordinator must be a SimulationTickCoordinator")
        if not isinstance(routine_book, RoutineBook):
            raise TypeError("routine_book must be a RoutineBook")
        if not isinstance(routine_ledger, RoutineExecutionLedger):
            raise TypeError("routine_ledger must be a RoutineExecutionLedger")
        self.coordinator = coordinator
        self.routine_book = routine_book
        self.routine_ledger = routine_ledger
        self._results: dict[int, PopulationTickResult] = {}
        self._requests: dict[int, tuple[object, ...]] = {}

    @staticmethod
    def _validate_roster(npcs: Mapping[str, NPC]) -> tuple[str, ...]:
        if not isinstance(npcs, Mapping):
            raise TypeError("npcs must be a mapping of NPC IDs to NPC instances")
        for npc_id, npc in npcs.items():
            if not isinstance(npc_id, str) or not npc_id.strip():
                raise ValueError("NPC IDs must be non-empty strings")
            if not isinstance(npc, NPC):
                raise TypeError("population values must be NPC instances")
            if npc.entity_id != npc_id:
                raise ValueError("population keys must match NPC entity IDs")
        return tuple(sorted(npcs))

    def run_tick(
        self,
        tick: int,
        minute_of_day: int,
        npcs: Mapping[str, NPC],
        *,
        event_ids: tuple[str, ...] = (),
        conversations: tuple[ConversationIntent, ...] = (),
        disruptions: Iterable[RoutineDisruption] = (),
        outcome_samples: Mapping[str, float],
        owner_ids: Iterable[str] | None = None,
    ) -> PopulationTickResult:
        """Execute social/event and routine phases for one stable roster snapshot."""
        if isinstance(tick, bool) or not isinstance(tick, int) or tick < 0:
            raise ValueError("tick must be a non-negative integer")
        if isinstance(minute_of_day, bool) or not isinstance(minute_of_day, int) or not 0 <= minute_of_day < 1440:
            raise ValueError("minute_of_day must be an integer from 0 to 1439")
        roster = self._validate_roster(npcs)
        selected_owners = roster if owner_ids is None else tuple(sorted(set(owner_ids)))
        if any(not isinstance(owner, str) or not owner.strip() for owner in selected_owners):
            raise ValueError("owner_ids must contain non-empty strings")
        missing = sorted(set(selected_owners) - set(roster))
        if missing:
            raise KeyError(f"routine owners are absent from population: {', '.join(missing)}")

        disruption_values = tuple(disruptions)
        sample_values = dict(outcome_samples)
        signature = (
            minute_of_day,
            roster,
            tuple(event_ids),
            tuple(conversations),
            tuple(sorted(disruption_values, key=lambda item: item.disruption_id)),
            tuple(sorted(sample_values.items())),
            selected_owners,
        )
        existing = self._results.get(tick)
        if existing is not None:
            if self._requests[tick] != signature:
                raise ValueError(f"population tick {tick} replayed with different inputs")
            return existing

        active_blocks = tuple(
            block for block in self.routine_book.snapshot()
            if block.owner_id in selected_owners
            and block.start_minute <= minute_of_day < block.end_minute
        )
        for block in active_blocks:
            if block.owner_id not in npcs:
                raise KeyError(f"routine owner is absent from population: {block.owner_id}")
            if block.routine_id not in sample_values:
                raise ValueError(f"missing outcome sample for routine: {block.routine_id}")
            sample = sample_values[block.routine_id]
            if isinstance(sample, bool) or not isinstance(sample, (int, float)):
                raise ValueError(f"outcome sample for {block.routine_id} must be numeric")
            if not 0.0 <= sample <= 1.0:
                raise ValueError(f"outcome sample for {block.routine_id} must be in [0, 1]")

        social = self.coordinator.step(
            tick, npcs, event_ids=event_ids, conversations=conversations,
        )
        executions = self.coordinator.execute_routines(
            tick, minute_of_day, self.routine_book, self.routine_ledger,
            disruptions=disruption_values,
            outcome_samples=sample_values,
            owner_ids=selected_owners,
        )
        result = PopulationTickResult(
            tick=tick,
            social=social,
            routine_executions=executions,
            processed_npc_ids=roster,
        )
        self._requests[tick] = signature
        self._results[tick] = result
        return result

    def snapshot(self) -> tuple[PopulationTickResult, ...]:
        """Return successful population ticks in ascending tick order."""
        return tuple(self._results[tick] for tick in sorted(self._results))
