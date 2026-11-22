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
from .presence_encounters import PresenceSocialAdapter, PresenceEncounterResult
from .population_transaction import PopulationTickTransactionCoordinator
from .action_execution import ActionExecution, ActionExecutionLedger, ActiveActionExecution
from .action_world_state import ActionWorldState
from .inventory import ActionInventoryAdapter, InventoryTransfer
from .population_actions import NPCActionDispatch, NPCActionDispatchAdapter
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
        if self.transaction_coordinator is None:
            return self._run_tick_untransactional(tick, minute_of_day, npcs, **kwargs)
        normalized_kwargs = dict(kwargs)
        for iterable_name in ("disruptions", "closed_edge_ids", "owner_ids"):
            value = normalized_kwargs.get(iterable_name)
            if value is not None and not isinstance(value, (tuple, list, set, frozenset)):
                normalized_kwargs[iterable_name] = tuple(value)
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
        if not isinstance(encounter_opportunities, tuple) or any(not isinstance(item, PresenceEncounterIntent) for item in encounter_opportunities):
            raise TypeError("encounter_opportunities must be a tuple of PresenceEncounterIntent values")
        if len({item.encounter_id for item in encounter_opportunities}) != len(encounter_opportunities):
            raise ValueError("encounter IDs must be unique within a population tick")
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
        advanced_actions = self.action_dispatch_adapter.advance_active(tick, self.action_world_state) if self.action_dispatch_adapter is not None else ()
        tick_action_records = tuple(
            item for item in self.action_execution_ledger.snapshot()
            if item.tick == tick
        ) if self.action_execution_ledger is not None else ()
        completed_tick_actions = tuple(
            item for item in tick_action_records if item.status == "completed"
        )
        decisions = tuple(
            self.decision_cycle.decide(
                owner, tick, context.world_facts, context.goal_facts,
                committed_goal_id=context.committed_goal_id,
            )
            for owner, context in sorted(contexts.items())
        ) if self.decision_cycle is not None else ()
        action_dispatches = self.action_dispatch_adapter.dispatch(
            tick, decisions,
            self.action_world_state.world_facts_by_owner,
            self.action_world_state.resources_by_owner,
            unavailable_owner_ids=frozenset(
                {item.owner_id for item in completed_tick_actions}
                | {item.owner_id for item in completed_action_executions if item.status == "completed"}
            ),
        ) if self.action_dispatch_adapter is not None else ()

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

        encounter_results = []
        generated_event_ids = []
        if encounter_opportunities and self.encounter_adapter is None:
            raise ValueError("encounter opportunities require a configured PresenceSocialAdapter")
        for intent in sorted(encounter_opportunities, key=lambda item: item.encounter_id):
            if not intent.opportunity:
                continue
            result = self.encounter_adapter.encounter(
                intent.encounter_id, intent.first_id, intent.second_id, tick,
                opportunity=True, events=self.coordinator.events,
            )
            if result is not None:
                encounter_results.append(result)
                generated_event_ids.append(f"npc_encounter:{intent.encounter_id}")
        selected_event_ids = tuple(sorted(set(event_ids) | set(generated_event_ids)))
        social = self.coordinator.step(
            tick, npcs, event_ids=selected_event_ids, conversations=conversations,
        )
        executions = self.coordinator.execute_routines(
            tick, minute_of_day, self.routine_book, self.routine_ledger,
            disruptions=disruption_values,
            outcome_samples=sample_values,
            owner_ids=selected_owners,
        )
        economic_inputs = {}
        for item in (*completed_action_executions, *completed_tick_actions):
            prior = economic_inputs.get(item.execution_id)
            if prior is not None and prior != item:
                raise ValueError(f"conflicting completed action record: {item.execution_id}")
            economic_inputs[item.execution_id] = item
        economic_transfers = tuple(
            transfer
            for item in sorted(economic_inputs.values(), key=lambda value: value.execution_id)
            for transfer in self.economic_action_adapter.apply_all(item, tick)
        ) if self.economic_action_adapter is not None else ()
        action_obligations = tuple(
            obligation
            for item in sorted(economic_inputs.values(), key=lambda value: value.execution_id)
            for obligation in self.household_action_adapter.apply_all(item, tick)
        ) if self.household_action_adapter is not None else ()
        inventory_transfers = tuple(
            transfer
            for item in sorted(economic_inputs.values(), key=lambda value: value.execution_id)
            for transfer in self.inventory_action_adapter.apply_all(item, tick)
        ) if self.inventory_action_adapter is not None else ()
        household_records = tuple(
            self.household_ledger.add(item)
            for item in sorted(household_obligations, key=lambda value: value.obligation_id)
        ) if self.household_ledger is not None else ()
        household_settlements = tuple(
            self.household_ledger.settle(obligation_id, tick)
            for obligation_id in sorted(household_settlement_ids)
        ) if self.household_ledger is not None else ()
        action_result_by_id = {}
        for item in (
            *advanced_actions,
            *tick_action_records,
            *completed_action_executions,
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
