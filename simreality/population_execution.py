"""Population-level orchestration for deterministic world ticks.

The loop composes the existing event-memory/conversation coordinator with the
routine execution ledger. It does not invent witnesses, encounters, disruptions,
or random outcomes: the world driver supplies those inputs explicitly.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Callable, Iterable, Mapping

from .model import NPC
from .npc_autonomy import NPCDecision, NPCDecisionCycle
from .routine_execution import RoutineExecution, RoutineExecutionLedger
from .routines import RoutineBook, RoutineDisruption
from .travel import TravelTickAdapter, TravelTickResult
from .presence import PresenceTickAdapter, NPCPresence
from .presence_encounters import PresenceSocialAdapter, PresenceEncounterResult
from .population_transaction import PopulationTickTransactionCoordinator
from .action_execution import ActionExecution, ActionExecutionLedger, ActiveActionExecution
from .action_world_state import ActionWorldState
from .inventory import ActionInventoryAdapter, InventoryTransfer
from .population_actions import NPCActionDispatch, NPCActionDispatchAdapter
from .population_lod_policy import PopulationLODPolicy
from .population_spatial import PopulationSchedule
from .household_economy import EconomicActionAdapter, EconomicTransfer, HouseholdActionAdapter, HouseholdLedger, HouseholdObligation
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
class PresenceEncounterIntent:
    encounter_id: str
    first_id: str
    second_id: str
    opportunity: bool = True

    def __post_init__(self):
        for name in ("encounter_id", "first_id", "second_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be non-empty text")
        if self.first_id == self.second_id:
            raise ValueError("encounter participants must be different NPCs")
        if not isinstance(self.opportunity, bool):
            raise TypeError("opportunity must be boolean")


@dataclass(frozen=True)
class PopulationTickResult:
    """Immutable outputs from all committed population tick phases."""

    tick: int
    social: SimulationTickResult
    routine_executions: tuple[RoutineExecution, ...]
    decisions: tuple[NPCDecision, ...]
    processed_npc_ids: tuple[str, ...]
    travel: TravelTickResult | None = None
    presence: tuple[NPCPresence, ...] = ()
    encounters: tuple[PresenceEncounterResult, ...] = ()
    economic_transfers: tuple[EconomicTransfer, ...] = ()
    household_settlements: tuple[HouseholdObligation, ...] = ()
    household_obligations: tuple[HouseholdObligation, ...] = ()
    action_dispatches: tuple[NPCActionDispatch, ...] = ()
    action_results: tuple[ActionExecution | ActiveActionExecution, ...] = ()
    action_obligations: tuple[HouseholdObligation, ...] = ()
    inventory_transfers: tuple[InventoryTransfer, ...] = ()


class PopulationExecutionLoop:
    """Run stable population phases against an explicit roster snapshot.

    The loop composes travel, presence, encounters, action execution, social
    memory, routines and configured economic effects. A durable cross-ledger
    transaction is used only when a transaction coordinator and complete
    participant set are explicitly supplied.
    """

    def __init__(
        self,
        coordinator: SimulationTickCoordinator,
        routine_book: RoutineBook,
        routine_ledger: RoutineExecutionLedger,
        decision_cycle: NPCDecisionCycle | None = None,
        travel_adapter: TravelTickAdapter | None = None,
        presence_adapter: PresenceTickAdapter | None = None,
        encounter_adapter: PresenceSocialAdapter | None = None,
        transaction_coordinator: PopulationTickTransactionCoordinator | None = None,
        economic_action_adapter: EconomicActionAdapter | None = None,
        household_ledger: HouseholdLedger | None = None,
        action_execution_ledger: ActionExecutionLedger | None = None,
        action_dispatch_adapter: NPCActionDispatchAdapter | None = None,
        action_world_state: ActionWorldState | None = None,
        household_action_adapter: HouseholdActionAdapter | None = None,
        inventory_action_adapter: ActionInventoryAdapter | None = None,
        phase_observer: Callable[[str, int], None] | None = None,
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
        if encounter_adapter is not None and not isinstance(encounter_adapter, PresenceSocialAdapter):
            raise TypeError("encounter_adapter must be a PresenceSocialAdapter or None")
        if encounter_adapter is not None and presence_adapter is None:
            raise ValueError("encounter integration requires travel and presence adapters")
        if encounter_adapter is not None and encounter_adapter.presence is not presence_adapter.ledger:
            raise ValueError("encounter and presence adapters must share the same PresenceLedger")
        self.encounter_adapter = encounter_adapter
        if transaction_coordinator is not None and not isinstance(transaction_coordinator, PopulationTickTransactionCoordinator):
            raise TypeError("transaction_coordinator must be a PopulationTickTransactionCoordinator or None")
        self.transaction_coordinator = transaction_coordinator
        if transaction_coordinator is not None:
            required_participants = {
                "npcs", "world_events", "event_memory", "social_conversations",
                "social_beliefs", "social_trust", "routine_book", "routine_executions",
            }
            if travel_adapter is not None:
                required_participants.update(("travel", "presence"))
            if encounter_adapter is not None:
                required_participants.add("encounters")
            if economic_action_adapter is not None:
                required_participants.update(("economics", "economic_actions"))
            if household_ledger is not None:
                required_participants.add("households")
            missing_participants = required_participants - transaction_coordinator.participant_names
            if missing_participants:
                raise ValueError("whole-tick transaction is missing participants: " + ", ".join(sorted(missing_participants)))
        if economic_action_adapter is not None and not isinstance(economic_action_adapter, EconomicActionAdapter):
            raise TypeError("economic_action_adapter must be an EconomicActionAdapter or None")
        if household_ledger is not None and not isinstance(household_ledger, HouseholdLedger):
            raise TypeError("household_ledger must be a HouseholdLedger or None")
        if household_ledger is not None and economic_action_adapter is not None and household_ledger.economics is not economic_action_adapter.economics:
            raise ValueError("household and action adapters must share the same EconomicLedger")
        self.economic_action_adapter = economic_action_adapter
        self.household_ledger = household_ledger
        if household_action_adapter is not None and not isinstance(household_action_adapter, HouseholdActionAdapter):
            raise TypeError("household_action_adapter must be a HouseholdActionAdapter or None")
        if household_action_adapter is not None and household_ledger is not household_action_adapter.households:
            raise ValueError("household action adapter must use the configured HouseholdLedger")
        if household_action_adapter is not None and household_ledger is None:
            raise ValueError("household action effects require a HouseholdLedger")
        self.household_action_adapter = household_action_adapter
        if household_action_adapter is not None and transaction_coordinator is not None and "household_actions" not in transaction_coordinator.participant_names:
            raise ValueError("transaction coordinator is missing the household_actions participant")
        if inventory_action_adapter is not None and not isinstance(inventory_action_adapter, ActionInventoryAdapter):
            raise TypeError("inventory_action_adapter must be an ActionInventoryAdapter or None")
        self.inventory_action_adapter = inventory_action_adapter
        if phase_observer is not None and not callable(phase_observer):
            raise TypeError("phase_observer must be callable or None")
        self.phase_observer = phase_observer
        if inventory_action_adapter is not None and transaction_coordinator is not None:
            missing_inventory = {"inventory", "inventory_actions"} - transaction_coordinator.participant_names
            if missing_inventory:
                raise ValueError("transaction coordinator is missing participants: " + ", ".join(sorted(missing_inventory)))
        if action_dispatch_adapter is not None and not isinstance(action_dispatch_adapter, NPCActionDispatchAdapter):
            raise TypeError("action_dispatch_adapter must be an NPCActionDispatchAdapter or None")
        if action_execution_ledger is None and action_dispatch_adapter is not None:
            action_execution_ledger = action_dispatch_adapter.executions
        if action_execution_ledger is not None and not isinstance(action_execution_ledger, ActionExecutionLedger):
            raise TypeError("action_execution_ledger must be an ActionExecutionLedger or None")
        if action_execution_ledger is not None and action_execution_ledger.events is not coordinator.events:
            raise ValueError("action execution ledger must share the population world event ledger")
        self.action_execution_ledger = action_execution_ledger
        if action_world_state is not None and not isinstance(action_world_state, ActionWorldState):
            raise TypeError("action_world_state must be an ActionWorldState or None")
        if (action_dispatch_adapter is None) != (action_world_state is None):
            raise ValueError("action dispatch adapter and checkpointable action world state must be configured together")
        if action_dispatch_adapter is not None and action_execution_ledger is not action_dispatch_adapter.executions:
            raise ValueError("action dispatch adapter must use the configured action execution ledger")
        if action_dispatch_adapter is not None and self.decision_cycle is None:
            raise ValueError("action dispatch requires a configured NPCDecisionCycle")
        self.action_dispatch_adapter = action_dispatch_adapter
        self.action_world_state = action_world_state
        if action_dispatch_adapter is not None and transaction_coordinator is not None and "action_world_state" not in transaction_coordinator.participant_names:
            raise ValueError("transaction coordinator is missing the action_world_state participant")
        if action_execution_ledger is not None and transaction_coordinator is not None and "action_executions" not in transaction_coordinator.participant_names:
            raise ValueError("transaction coordinator is missing the action_executions participant")
        if action_execution_ledger is not None and action_execution_ledger.goals is not None and transaction_coordinator is not None and "action_goals" not in transaction_coordinator.participant_names:
            raise ValueError("transaction coordinator is missing the action_goals participant")
        self._results: dict[int, PopulationTickResult] = {}
        self._requests: dict[int, tuple[object, ...]] = {}

    def _phase_completed(self, phase: str, tick: int) -> None:
        """Notify an optional deterministic observer after a committed phase boundary."""
        if self.phase_observer is not None:
            self.phase_observer(phase, tick)

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

    def run_tick(self, tick: int, minute_of_day: int, npcs: Mapping[str, NPC], **kwargs) -> PopulationTickResult:
        """Execute a population tick inside the configured durable transaction."""
        normalized_kwargs = dict(kwargs)
        population_schedule = normalized_kwargs.pop("population_schedule", None)
        lod_policy = normalized_kwargs.pop("lod_policy", None)
        if (population_schedule is None) != (lod_policy is None):
            raise ValueError("population_schedule and lod_policy must be supplied together")
        if population_schedule is not None:
            if not isinstance(population_schedule, PopulationSchedule):
                raise TypeError("population_schedule must be a PopulationSchedule")
            if not isinstance(lod_policy, PopulationLODPolicy):
                raise TypeError("lod_policy must be a PopulationLODPolicy")
            if population_schedule.tick != tick:
                raise ValueError("population schedule tick must match run_tick tick")
            if not isinstance(npcs, Mapping):
                raise TypeError("npcs must be a mapping when a population schedule is supplied")
            scheduled_owner_ids = set(population_schedule.selected_owner_ids) | set(population_schedule.deferred_owner_ids)
            if scheduled_owner_ids != set(npcs):
                raise ValueError("population schedule must partition the exact NPC roster")
            normalized_kwargs["subsystem_owner_ids"] = {
                item.subsystem_id: item.owner_ids
                for item in population_schedule.subsystem_slices(lod_policy)
            }
        for iterable_name in ("disruptions", "closed_edge_ids", "owner_ids"):
            value = normalized_kwargs.get(iterable_name)
            if value is not None and not isinstance(value, (tuple, list, set, frozenset)):
                normalized_kwargs[iterable_name] = tuple(value)
        if self.transaction_coordinator is None:
            try:
                return self._run_tick_untransactional(tick, minute_of_day, npcs, **normalized_kwargs)
            except BaseException:
                # Without rollback, preserve subsystem replay caches for state
                # that may already have been committed by earlier phases.
                self._requests.pop(tick, None)
                self._results.pop(tick, None)
                raise
        request = {
            "tick": tick,
            "minute_of_day": minute_of_day,
            "npc_ids": tuple(sorted(npcs)) if isinstance(npcs, Mapping) else npcs,
            "kwargs": normalized_kwargs,
        }
        try:
            return self.transaction_coordinator.execute(
                tick, request,
                lambda: self._run_tick_untransactional(tick, minute_of_day, npcs, **normalized_kwargs),
            )
        except BaseException:
            self.coordinator.discard_tick_cache(tick)
            if self.action_dispatch_adapter is not None:
                self.action_dispatch_adapter.discard_tick_cache(tick)
            self._requests.pop(tick, None)
            self._results.pop(tick, None)
            raise

    def _run_tick_untransactional(
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
        encounter_opportunities: tuple[PresenceEncounterIntent, ...] = (),
        completed_action_executions: tuple[ActionExecution, ...] = (),
        household_settlement_ids: tuple[str, ...] = (),
        household_obligations: tuple[HouseholdObligation, ...] = (),
        subsystem_owner_ids: Mapping[str, tuple[str, ...]] | None = None,
    ) -> PopulationTickResult:
        """Execute social/event and routine phases for one stable roster snapshot."""
        if isinstance(tick, bool) or not isinstance(tick, int) or tick < 0:
            raise ValueError("tick must be a non-negative integer")
        if isinstance(minute_of_day, bool) or not isinstance(minute_of_day, int) or not 0 <= minute_of_day < 1440:
            raise ValueError("minute_of_day must be an integer from 0 to 1439")
        roster = self._validate_roster(npcs)
        subsystem_plan = None
        if subsystem_owner_ids is not None:
            if not isinstance(subsystem_owner_ids, Mapping):
                raise TypeError("subsystem_owner_ids must map subsystem IDs to owner tuples")
            allowed_subsystems = {"action", "decision", "economy", "memory", "presence", "routine", "social", "travel"}
            if any(not isinstance(name, str) or name not in allowed_subsystems for name in subsystem_owner_ids):
                raise ValueError("subsystem_owner_ids contains an unknown subsystem")
            subsystem_plan = {}
            for name, owners in subsystem_owner_ids.items():
                if not isinstance(owners, tuple) or any(not isinstance(owner, str) or not owner.strip() for owner in owners):
                    raise ValueError(f"subsystem owner batch {name!r} must be a tuple of non-empty IDs")
                if tuple(sorted(set(owners))) != owners:
                    raise ValueError(f"subsystem owner batch {name!r} must be unique and sorted")
                absent = set(owners) - set(roster)
                if absent:
                    raise KeyError(f"subsystem {name!r} references absent NPCs: {', '.join(sorted(absent))}")
                subsystem_plan[name] = owners
        routine_owners = roster if subsystem_plan is None else subsystem_plan.get("routine", ())
        if owner_ids is None:
            selected_owners = tuple(routine_owners)
        else:
            supplied_owners = tuple(owner_ids)
            if any(not isinstance(owner, str) or not owner.strip() for owner in supplied_owners):
                raise ValueError("owner_ids must contain non-empty strings")
            if len(supplied_owners) != len(set(supplied_owners)):
                raise ValueError("owner_ids must not contain duplicates")
            missing = sorted(set(supplied_owners) - set(roster))
            if missing:
                raise KeyError(f"routine owners are absent from population: {', '.join(missing)}")
            selected_owners = tuple(sorted(set(supplied_owners) & set(routine_owners)))

        if not isinstance(event_ids, tuple) or any(not isinstance(item, str) or not item.strip() for item in event_ids):
            raise ValueError("event_ids must be a tuple of non-empty strings")
        if len(set(event_ids)) != len(event_ids):
            raise ValueError("event_ids must not contain duplicates")
        if not isinstance(conversations, tuple) or any(not isinstance(item, ConversationIntent) for item in conversations):
            raise TypeError("conversations must be a tuple of ConversationIntent values")
        if len({item.conversation_id for item in conversations}) != len(conversations):
            raise ValueError("conversation IDs must be unique within a tick")
        for event_id in event_ids:
            event = self.coordinator.events.get(event_id)
            if event.tick != tick:
                raise ValueError(f"event {event_id!r} is at tick {event.tick}, not requested tick {tick}")
            missing_witnesses = set(event.witnesses) - set(roster)
            if missing_witnesses:
                raise KeyError(f"event witnesses are absent from population: {', '.join(sorted(missing_witnesses))}")
        for intent in conversations:
            if intent.listener_id not in npcs or intent.speaker_id not in npcs:
                raise KeyError(f"conversation {intent.conversation_id!r} references an absent NPC")
        if not isinstance(encounter_opportunities, tuple) or any(not isinstance(item, PresenceEncounterIntent) for item in encounter_opportunities):
            raise TypeError("encounter_opportunities must be a tuple of PresenceEncounterIntent values")
        if len({item.encounter_id for item in encounter_opportunities}) != len(encounter_opportunities):
            raise ValueError("encounter IDs must be unique within a population tick")
        for intent in encounter_opportunities:
            if intent.first_id not in npcs or intent.second_id not in npcs:
                raise KeyError(f"encounter {intent.encounter_id!r} references an absent NPC")
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
        action_owners = set(roster if subsystem_plan is None else subsystem_plan.get("action", ()))
        decision_owners = set(roster if subsystem_plan is None else subsystem_plan.get("decision", ()))
        social_owners = set(roster if subsystem_plan is None else subsystem_plan.get("social", ()))
        memory_owners = set(roster if subsystem_plan is None else subsystem_plan.get("memory", ()))
        economy_owners = set(roster if subsystem_plan is None else subsystem_plan.get("economy", ()))
        travel_owners = set(roster if subsystem_plan is None else subsystem_plan.get("travel", ()))
        presence_owners = set(roster if subsystem_plan is None else subsystem_plan.get("presence", ()))
        contexts = {owner: context for owner, context in contexts.items() if owner in decision_owners}
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
        if not isinstance(completed_action_executions, tuple) or any(not isinstance(item, ActionExecution) for item in completed_action_executions):
            raise TypeError("completed_action_executions must be a tuple of ActionExecution values")
        if len({item.execution_id for item in completed_action_executions}) != len(completed_action_executions):
            raise ValueError("completed action execution IDs must be unique within a population tick")
        if not isinstance(household_obligations, tuple) or any(not isinstance(item, HouseholdObligation) for item in household_obligations):
            raise TypeError("household_obligations must be a tuple of HouseholdObligation values")
        if len({item.obligation_id for item in household_obligations}) != len(household_obligations):
            raise ValueError("household obligation IDs must be unique within a population tick")
        if household_obligations and self.household_ledger is None:
            raise ValueError("household obligations require a HouseholdLedger")
        if not isinstance(household_settlement_ids, tuple) or any(not isinstance(item, str) or not item.strip() for item in household_settlement_ids):
            raise TypeError("household_settlement_ids must be a tuple of non-empty strings")
        if len(set(household_settlement_ids)) != len(household_settlement_ids):
            raise ValueError("household settlement IDs must be unique within a population tick")
        if completed_action_executions and self.economic_action_adapter is None:
            raise ValueError("completed action executions require an EconomicActionAdapter")
        if completed_action_executions and self.transaction_coordinator is not None and "action_executions" not in self.transaction_coordinator.participant_names:
            raise ValueError("whole-tick transaction requires an action_executions participant for completed action inputs")
        if completed_action_executions and self.action_execution_ledger is not None:
            for execution in completed_action_executions:
                if self.action_execution_ledger.get(execution.execution_id) != execution:
                    raise ValueError(f"completed action {execution.execution_id} is not present in the configured action ledger")
        if subsystem_plan is not None:
            for execution in completed_action_executions:
                if execution.owner_id not in economy_owners and (
                    self.action_execution_ledger is None
                    or self.action_execution_ledger.get(execution.execution_id) != execution
                ):
                    raise ValueError(
                        "completed actions deferred by the economy LOD cadence must be recorded in the configured ActionExecutionLedger"
                    )
        if household_settlement_ids and self.household_ledger is None:
            raise ValueError("household settlements require a HouseholdLedger")
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
            tuple(sorted(encounter_opportunities, key=lambda item: item.encounter_id)),
            tuple(sorted(completed_action_executions, key=lambda item: item.execution_id)),
            tuple(sorted(household_settlement_ids)),
            tuple(sorted(household_obligations, key=lambda item: item.obligation_id)),
            None if subsystem_plan is None else tuple(
                (name, owners) for name, owners in sorted(subsystem_plan.items())
            ),
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

        # Existing actions advance before new decisions so completed effects are
        # visible to the decision phase in this same population tick.
        advanced_actions = self.action_dispatch_adapter.advance_active(
            tick, self.action_world_state, owner_ids=tuple(sorted(action_owners)),
        ) if self.action_dispatch_adapter is not None else ()
        tick_action_records = tuple(
            item for item in self.action_execution_ledger.snapshot()
            if item.tick == tick
        ) if self.action_execution_ledger is not None else ()
        decisions = tuple(
            self.decision_cycle.decide(
                owner, tick, context.world_facts, context.goal_facts,
                committed_goal_id=context.committed_goal_id,
            )
            for owner, context in sorted(contexts.items()) if owner in decision_owners
        ) if self.decision_cycle is not None else ()
        self._phase_completed("decisions", tick)
        action_dispatches = self.action_dispatch_adapter.dispatch(
            tick, tuple(item for item in decisions if item.owner_id in action_owners),
            self.action_world_state.world_facts_by_owner,
            self.action_world_state.resources_by_owner,
            unavailable_owner_ids=frozenset(
                {item.owner_id for item in tick_action_records}
                | {item.owner_id for item in completed_action_executions if item.status == "completed"}
            ),
        ) if self.action_dispatch_adapter is not None else ()
        self._phase_completed("actions", tick)

        travel_result = None
        presence_records: tuple[NPCPresence, ...] = ()
        if self.travel_adapter is None:
            if travel_budgets is not None or closed_edges or multiplier_values:
                raise ValueError("travel inputs require configured travel and presence adapters")
        else:
            if presence_owners != set(roster):
                raise ValueError("presence synchronization is authoritative and must include every roster owner")
            if travel_budgets is None:
                raise ValueError("travel_budgets are required when travel integration is configured")
            if not isinstance(travel_budgets, Mapping):
                raise TypeError("travel_budgets must map owner IDs to travel budgets")
            for owner, budget in travel_budgets.items():
                if owner not in npcs:
                    raise KeyError(f"travel budget owner is absent from population: {owner}")
                if isinstance(budget, bool) or not isinstance(budget, (int, float)) or not math.isfinite(budget) or budget < 0:
                    raise ValueError("each travel budget must be finite and non-negative")
            effective_travel_budgets = {
                owner: budget for owner, budget in travel_budgets.items()
                if owner in travel_owners
            }
            travel_result = self.travel_adapter.advance(
                tick, effective_travel_budgets, closed_edge_ids=closed_edges,
                time_multipliers=multiplier_values, events=self.coordinator.events,
            )
            presence_records = self.presence_adapter.synchronize(
                tick, self.travel_adapter.ledger, events=self.coordinator.events,
            )
            self._phase_completed("travel", tick)
            self._phase_completed("presence", tick)

        encounter_results = []
        generated_event_ids = []
        if encounter_opportunities and self.encounter_adapter is None:
            raise ValueError("encounter opportunities require a configured PresenceSocialAdapter")
        for intent in sorted(encounter_opportunities, key=lambda item: item.encounter_id):
            if not intent.opportunity or intent.first_id not in social_owners or intent.second_id not in social_owners:
                continue
            result = self.encounter_adapter.encounter(
                intent.encounter_id, intent.first_id, intent.second_id, tick,
                opportunity=True, events=self.coordinator.events,
            )
            if result is not None:
                encounter_results.append(result)
                generated_event_ids.append(f"npc_encounter:{intent.encounter_id}")
        self._phase_completed("encounters", tick)
        # Materialize only due witness memories. Events remain authoritative in
        # the world ledger until each witness's memory LOD cadence becomes due;
        # one dormant witness must not block memories for another due witness.
        memory_requests = []
        for event in self.coordinator.events.snapshot():
            if event.tick > tick:
                continue
            for witness_id in event.witnesses:
                if (
                    witness_id in memory_owners
                    and witness_id in npcs
                    and (
                        event.tick == tick
                        or not self.coordinator.memory_adapter.is_memory_resolved(event.event_id, witness_id)
                    )
                ):
                    memory_requests.append((event.event_id, witness_id))
        social_conversations = tuple(
            intent for intent in conversations
            if intent.listener_id in social_owners and intent.speaker_id in social_owners
        )
        social = self.coordinator.step(
            tick, npcs, memory_requests=tuple(sorted(memory_requests)),
            conversations=social_conversations,
        )
        self._phase_completed("social", tick)
        executions = self.coordinator.execute_routines(
            tick, minute_of_day, self.routine_book, self.routine_ledger,
            disruptions=disruption_values,
            outcome_samples=sample_values,
            owner_ids=selected_owners,
        )
        self._phase_completed("routines", tick)
        completed_action_inputs = {}
        ledger_completed_actions = tuple(
            item for item in self.action_execution_ledger.snapshot()
            if item.status == "completed"
        ) if self.action_execution_ledger is not None else ()
        for item in (*completed_action_executions, *ledger_completed_actions):
            prior = completed_action_inputs.get(item.execution_id)
            if prior is not None and prior != item:
                raise ValueError(f"conflicting completed action record: {item.execution_id}")
            completed_action_inputs[item.execution_id] = item
        due_economic_actions = tuple(
            item for item in sorted(completed_action_inputs.values(), key=lambda value: value.execution_id)
            if item.owner_id in economy_owners
        )
        pending_action_ids = {
            item.execution_id
            for item in due_economic_actions
            if (
                self.economic_action_adapter is not None
                and self.economic_action_adapter.has_policy(item.action_id)
                and not self.economic_action_adapter.has_applied(item.execution_id)
            ) or (
                self.household_action_adapter is not None
                and self.household_action_adapter.has_policy(item.action_id)
                and not self.household_action_adapter.has_applied(item.execution_id)
            ) or (
                self.inventory_action_adapter is not None
                and self.inventory_action_adapter.has_policy(item.action_id)
                and not self.inventory_action_adapter.has_applied(item.execution_id)
            )
        }
        economic_transfers = tuple(
            transfer
            for item in due_economic_actions
            if self.economic_action_adapter is not None
            and not self.economic_action_adapter.has_applied(item.execution_id)
            for transfer in self.economic_action_adapter.apply_all(item, tick)
        )
        self._phase_completed("economy", tick)
        action_obligations = tuple(
            obligation
            for item in due_economic_actions
            if self.household_action_adapter is not None
            and not self.household_action_adapter.has_applied(item.execution_id)
            for obligation in self.household_action_adapter.apply_all(item, tick)
        )
        inventory_transfers = tuple(
            transfer
            for item in due_economic_actions
            if self.inventory_action_adapter is not None
            and not self.inventory_action_adapter.has_applied(item.execution_id)
            for transfer in self.inventory_action_adapter.apply_all(item, tick)
        )
        self._phase_completed("inventory", tick)
        household_records = tuple(
            self.household_ledger.add(item)
            for item in sorted(household_obligations, key=lambda value: value.obligation_id)
        ) if self.household_ledger is not None else ()
        household_settlements = self.household_ledger.settle_many(
            tuple(sorted(household_settlement_ids)), tick,
        ) if self.household_ledger is not None else ()
        self._phase_completed("households", tick)
        action_result_by_id = {}
        for item in (
            *advanced_actions,
            *tick_action_records,
            *completed_action_executions,
            *(item for item in due_economic_actions if item.execution_id in pending_action_ids),
            *(dispatch.active for dispatch in action_dispatches if dispatch.active is not None),
        ):
            action_result_by_id[item.execution_id] = item

        result = PopulationTickResult(
            tick=tick,
            social=social,
            routine_executions=executions,
            decisions=decisions,
            processed_npc_ids=roster,
            travel=travel_result,
            presence=presence_records,
            encounters=tuple(encounter_results),
            economic_transfers=economic_transfers,
            household_settlements=household_settlements,
            household_obligations=household_records,
            action_dispatches=action_dispatches,
            action_obligations=action_obligations,
            inventory_transfers=inventory_transfers,
            action_results=tuple(
                action_result_by_id[execution_id]
                for execution_id in sorted(action_result_by_id)
            ),
        )
        self._requests[tick] = signature
        self._results[tick] = result
        return result

    def snapshot(self) -> tuple[PopulationTickResult, ...]:
        """Return successful population ticks in ascending tick order."""
        return tuple(self._results[tick] for tick in sorted(self._results))
