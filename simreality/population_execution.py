"""Population-level orchestration for deterministic world ticks.

The loop composes the existing event-memory/conversation coordinator with the
routine execution ledger. It does not invent witnesses, encounters, disruptions,
or random outcomes: the world driver supplies those inputs explicitly.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Mapping

from .model import NPC
from .npc_autonomy import NPCDecision, NPCDecisionCycle
from .routine_execution import RoutineExecution, RoutineExecutionLedger
from .routines import RoutineBook, RoutineDisruption
from .travel import TravelTickAdapter, TravelTickResult
from .presence import PresenceTickAdapter, NPCPresence
from .simulation_tick import (
    ConversationIntent,
    SimulationTickCoordinator,
    SimulationTickResult,
)


@dataclass(frozen=True)
class NPCDecisionContext:
    """Explicit world and goal facts used for one NPC's read-only decision."""

    world_facts: frozenset[str]
    goal_facts: Mapping[str, frozenset[str]]
    committed_goal_id: str | None = None


@dataclass(frozen=True)
class PopulationTickResult:
    """Committed outputs from the two replay-safe phases of one population tick."""

    tick: int
    social: SimulationTickResult
    routine_executions: tuple[RoutineExecution, ...]
    decisions: tuple[NPCDecision, ...]
    processed_npc_ids: tuple[str, ...]
    travel: TravelTickResult | None = None
    presence: tuple[NPCPresence, ...] = ()


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
        decision_cycle: NPCDecisionCycle | None = None,
        travel_adapter: TravelTickAdapter | None = None,
        presence_adapter: PresenceTickAdapter | None = None,
    ) -> None:
        if not isinstance(coordinator, SimulationTickCoordinator):
            raise TypeError("coordinator must be a SimulationTickCoordinator")
        if not isinstance(routine_book, RoutineBook):
            raise TypeError("routine_book must be a RoutineBook")
        if not isinstance(routine_ledger, RoutineExecutionLedger):
            raise TypeError("routine_ledger must be a RoutineExecutionLedger")
        if decision_cycle is not None and not isinstance(decision_cycle, NPCDecisionCycle):
            raise TypeError("decision_cycle must be an NPCDecisionCycle or None")
        self.coordinator = coordinator
        self.routine_book = routine_book
        self.routine_ledger = routine_ledger
        self.decision_cycle = decision_cycle
        if travel_adapter is not None and not isinstance(travel_adapter, TravelTickAdapter):
            raise TypeError("travel_adapter must be a TravelTickAdapter or None")
        if presence_adapter is not None and not isinstance(presence_adapter, PresenceTickAdapter):
            raise TypeError("presence_adapter must be a PresenceTickAdapter or None")
        if (travel_adapter is None) != (presence_adapter is None):
            raise ValueError("travel and presence adapters must be configured together")
        self.travel_adapter = travel_adapter
        self.presence_adapter = presence_adapter
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
        decision_contexts: Mapping[str, NPCDecisionContext] | None = None,
        travel_budgets: Mapping[str, float] | None = None,
        closed_edge_ids: Iterable[str] = (),
        time_multipliers: Mapping[str, float] | None = None,
    ) -> PopulationTickResult:
        """Execute social/event and routine phases for one stable roster snapshot."""
        if isinstance(tick, bool) or not isinstance(tick, int) or tick < 0:
            raise ValueError("tick must be a non-negative integer")
        if isinstance(minute_of_day, bool) or not isinstance(minute_of_day, int) or not 0 <= minute_of_day < 1440:
            raise ValueError("minute_of_day must be an integer from 0 to 1439")
        roster = self._validate_roster(npcs)
        if owner_ids is None:
            selected_owners = roster
        else:
            supplied_owners = tuple(owner_ids)
            if any(not isinstance(owner, str) or not owner.strip() for owner in supplied_owners):
                raise ValueError("owner_ids must contain non-empty strings")
            if len(supplied_owners) != len(set(supplied_owners)):
                raise ValueError("owner_ids must not contain duplicates")
            selected_owners = tuple(sorted(supplied_owners))
        missing = sorted(set(selected_owners) - set(roster))
        if missing:
            raise KeyError(f"routine owners are absent from population: {', '.join(missing)}")

        if decision_contexts is not None and not isinstance(decision_contexts, Mapping):
            raise TypeError("decision_contexts must map NPC IDs to decision contexts")
        contexts = dict(decision_contexts or {})
        if contexts and self.decision_cycle is None:
            raise ValueError("decision contexts require an NPCDecisionCycle")
        for owner, context in contexts.items():
            if not isinstance(owner, str) or not owner.strip():
                raise ValueError("decision context owner IDs must be non-empty strings")
            if owner not in npcs:
                raise KeyError(f"decision owner is absent from population: {owner}")
            if not isinstance(context, NPCDecisionContext):
                raise TypeError("decision contexts must contain NPCDecisionContext values")
            if not isinstance(context.world_facts, frozenset) or any(not isinstance(fact, str) or not fact for fact in context.world_facts):
                raise ValueError("world_facts must be a frozenset of non-empty strings")
            if not isinstance(context.goal_facts, Mapping):
                raise TypeError("goal_facts must map goal IDs to desired fact sets")
            for goal_id, desired_facts in context.goal_facts.items():
                if not isinstance(goal_id, str) or not goal_id.strip():
                    raise ValueError("goal fact mappings require non-empty goal IDs")
                if not isinstance(desired_facts, (frozenset, set, tuple)) or any(
                    not isinstance(fact, str) or not fact for fact in desired_facts
                ):
                    raise ValueError("desired goal facts must be sets or tuples of non-empty strings")
            if context.committed_goal_id is not None and (not isinstance(context.committed_goal_id, str) or not context.committed_goal_id.strip()):
                raise ValueError("committed_goal_id must be None or a non-empty string")
        disruption_values = tuple(disruptions)
        if any(not isinstance(item, RoutineDisruption) for item in disruption_values):
            raise TypeError("disruptions must contain RoutineDisruption values")
        if len({item.disruption_id for item in disruption_values}) != len(disruption_values):
            raise ValueError("disruption IDs must be unique within a tick")
        if not isinstance(outcome_samples, Mapping):
            raise TypeError("outcome_samples must be a mapping")
        sample_values = dict(outcome_samples)
        closed_edges = tuple(sorted(set(closed_edge_ids)))
        multiplier_values = dict(time_multipliers or {})
        signature = (
            minute_of_day,
            roster,
            tuple(event_ids),
            tuple(conversations),
            tuple(sorted(disruption_values, key=lambda item: item.disruption_id)),
            tuple(sorted(sample_values.items())),
            selected_owners,
            tuple(sorted(contexts.items())),
            None if travel_budgets is None else tuple(sorted(dict(travel_budgets).items())),
            closed_edges,
            tuple(sorted(multiplier_values.items())),
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
            if not math.isfinite(sample) or not 0.0 <= sample <= 1.0:
                raise ValueError(f"outcome sample for {block.routine_id} must be finite and in [0, 1]")

        decisions = tuple(
            self.decision_cycle.decide(
                owner, tick, context.world_facts, context.goal_facts,
                committed_goal_id=context.committed_goal_id,
            )
            for owner, context in sorted(contexts.items())
        ) if self.decision_cycle is not None else ()

        travel_result = None
        presence_records: tuple[NPCPresence, ...] = ()
        if self.travel_adapter is None:
            if travel_budgets is not None or closed_edges or multiplier_values:
                raise ValueError("travel inputs require configured travel and presence adapters")
        else:
            if travel_budgets is None:
                raise ValueError("travel_budgets are required when travel integration is configured")
            travel_result = self.travel_adapter.advance(
                tick, travel_budgets, closed_edge_ids=closed_edges,
                time_multipliers=multiplier_values, events=self.coordinator.events,
            )
            presence_records = self.presence_adapter.synchronize(
                tick, self.travel_adapter.ledger, events=self.coordinator.events,
            )

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
            decisions=decisions,
            processed_npc_ids=roster,
            travel=travel_result,
            presence=presence_records,
        )
        self._requests[tick] = signature
        self._results[tick] = result
        return result

    def snapshot(self) -> tuple[PopulationTickResult, ...]:
        """Return successful population ticks in ascending tick order."""
        return tuple(self._results[tick] for tick in sorted(self._results))
