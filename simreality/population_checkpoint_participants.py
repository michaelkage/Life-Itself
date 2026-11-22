"""Concrete versioned checkpoint participants for population tick transactions.

This module binds the repository's existing save-state codecs to live subsystem
instances. Restore mutates those instances in place so adapters retain references
to their ledgers. Register in the returned order: world events and trust precede
consumers that validate against them.
"""
from __future__ import annotations

from dataclasses import asdict
import json
from typing import Mapping

from .model import NPC
from .npc_save_state import NPCCollectionSnapshot, SocialTrustSnapshot
from .social_belief_save_state import SocialBeliefSnapshot
from .social_replay_save_state import SocialConversationReplaySnapshot
from .travel_save_state import TravelSnapshot
from .presence_save_state import PresenceSnapshot
from .presence_encounter_save_state import PresenceEncounterSnapshot
from .routine_save_state import RoutineBookSnapshot
from .routine_execution_save_state import RoutineExecutionSnapshot
from .action_execution import ActionExecutionLedger, ActionExecutionSnapshot
from .action_world_state import ActionWorldState
from .household_economy import EconomicLedger, EconomicActionAdapter, EconomicTransfer, HouseholdLedger, HouseholdObligation
from .world_events import WorldEvent, WorldEventLedger
from .population_transaction import TransactionParticipant


def _json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _replace_mapping(target: dict, source: dict) -> None:
    target.clear()
    target.update(source)


def _npc_memory_payload(memory):
    from .model import NPC, AgeBand, TraumaLevel
    from .npc_save_state import NPCStateSnapshot
    # Reuse the authoritative memory codec rather than duplicating its schema.
    return json.loads(NPCStateSnapshot.capture(NPC(
        entity_id=memory.witness_id, memories=[memory],
        age_band=AgeBand.ADULT, trauma_level=TraumaLevel.BASELINE,
    )).to_json())["memories"][0]


def _npc_memory_from(payload):
    from .npc_save_state import NPCStateSnapshot
    wrapped = {
        "schema_version": NPCStateSnapshot.SCHEMA_VERSION,
        "entity_id": payload["witness_id"],
        "age_band": "adult",
        "moral_shackle": 0.8,
        "desperation_index": 0.0,
        "trauma_level": 0,
        "personal_stress": 0.0,
        "memories": [payload],
    }
    return NPCStateSnapshot.from_json(_json(wrapped)).memories[0]


def build_population_transaction_participants(
    npcs: Mapping[str, NPC],
    tick_coordinator,
    routine_book,
    routine_ledger,
    *,
    travel_adapter=None,
    presence_adapter=None,
    encounter_adapter=None,
    economic_action_adapter: EconomicActionAdapter | None = None,
    household_ledger: HouseholdLedger | None = None,
    action_ledger: ActionExecutionLedger | None = None,
    action_world_state: ActionWorldState | None = None,
) -> tuple[TransactionParticipant, ...]:
    """Build complete participants for the supplied live population loop.

    The returned callbacks capture the supplied roster by reference. Keep that
    mapping and its NPC instances alive for the coordinator's lifetime.
    """
    from .simulation_tick import SimulationTickCoordinator
    from .routines import RoutineBook
    from .routine_execution import RoutineExecutionLedger
    if not isinstance(npcs, Mapping) or any(not isinstance(npc, NPC) or npc_id != npc.entity_id for npc_id, npc in npcs.items()):
        raise TypeError("npcs must map entity IDs to matching NPC instances")
    if not isinstance(tick_coordinator, SimulationTickCoordinator):
        raise TypeError("tick_coordinator must be a SimulationTickCoordinator")
    if not isinstance(routine_book, RoutineBook) or not isinstance(routine_ledger, RoutineExecutionLedger):
        raise TypeError("routine book and execution ledger are required")
    from .travel import TravelTickAdapter
    from .presence import PresenceTickAdapter
    from .presence_encounters import PresenceSocialAdapter
    if travel_adapter is not None and not isinstance(travel_adapter, TravelTickAdapter):
        raise TypeError("travel_adapter must be a TravelTickAdapter or None")
    if presence_adapter is not None and not isinstance(presence_adapter, PresenceTickAdapter):
        raise TypeError("presence_adapter must be a PresenceTickAdapter or None")
    if (travel_adapter is None) != (presence_adapter is None):
        raise ValueError("travel and presence checkpoint participants must be configured together")
    if encounter_adapter is not None and not isinstance(encounter_adapter, PresenceSocialAdapter):
        raise TypeError("encounter_adapter must be a PresenceSocialAdapter or None")
    if encounter_adapter is not None and (presence_adapter is None or encounter_adapter.presence is not presence_adapter.ledger):
        raise ValueError("encounter adapter must share the configured presence ledger")
    if economic_action_adapter is not None and not isinstance(economic_action_adapter, EconomicActionAdapter):
        raise TypeError("economic_action_adapter must be an EconomicActionAdapter or None")
    if household_ledger is not None and not isinstance(household_ledger, HouseholdLedger):
        raise TypeError("household_ledger must be a HouseholdLedger or None")
    if action_ledger is not None and not isinstance(action_ledger, ActionExecutionLedger):
        raise TypeError("action_ledger must be an ActionExecutionLedger or None")
    if action_world_state is not None and not isinstance(action_world_state, ActionWorldState):
        raise TypeError("action_world_state must be an ActionWorldState or None")
    participants = []

    def add(name, capture, restore):
        participants.append(TransactionParticipant(name, capture, restore))

    # NPC state: mutate existing NPC instances and their memory lists in place.
    def capture_npcs():
        return NPCCollectionSnapshot.capture(tuple(npcs.values())).to_json()
    def restore_npcs(payload):
        snapshot = NPCCollectionSnapshot.from_json(payload)
        restored = snapshot.restore()
        if set(restored) != set(npcs):
            raise ValueError("NPC roster changed across a durable tick; restore requires the same roster")
        for npc_id, saved in restored.items():
            live = npcs[npc_id]
            live.age_band = saved.age_band
            live.moral_shackle = saved.moral_shackle
            live.desperation_index = saved.desperation_index
            live.trauma_level = saved.trauma_level
            live.personal_stress = saved.personal_stress
            live.memories[:] = saved.memories
    add("npcs", capture_npcs, restore_npcs)

    events = tick_coordinator.events
    def capture_events():
        return _json({"schema_version": 1, "events": [
            {"event_id": e.event_id, "tick": e.tick, "event_type": e.event_type,
             "participants": list(e.participants), "witnesses": list(e.witnesses),
             "attributes": [list(x) for x in e.attributes]}
            for e in events.snapshot()
        ]})
    def restore_events(payload):
        raw = json.loads(payload)
        if raw.get("schema_version") != 1:
            raise ValueError("unsupported world event participant schema")
        records = [WorldEvent(
            item["event_id"], item["tick"], item["event_type"],
            tuple(item["participants"]), tuple(item["witnesses"]),
            tuple((x[0], x[1]) for x in item["attributes"]),
        ) for item in raw["events"]]
        restored = WorldEventLedger(records)
        _replace_mapping(events._events, restored._events)
    add("world_events", capture_events, restore_events)

    memory_adapter = tick_coordinator.memory_adapter
    def capture_event_memory():
        entries = []
        for (event_id, witness_id), memory in sorted(memory_adapter._processed.items()):
            entries.append({"event_id": event_id, "witness_id": witness_id,
                            "memory": _npc_memory_payload(memory)})
        return _json({"schema_version": 1, "entries": entries})
    def restore_event_memory(payload):
        raw = json.loads(payload)
        if raw.get("schema_version") != 1:
            raise ValueError("unsupported event-memory participant schema")
        restored = {(item["event_id"], item["witness_id"]): _npc_memory_from(item["memory"])
                    for item in raw["entries"]}
        _replace_mapping(memory_adapter._processed, restored)
    add("event_memory", capture_event_memory, restore_event_memory)

    conversation_adapter = tick_coordinator.conversation_adapter
    def capture_conversations():
        return SocialConversationReplaySnapshot.capture(conversation_adapter).to_json()
    def restore_conversations(payload):
        conversation_adapter._inputs.clear()
        conversation_adapter._results.clear()
        SocialConversationReplaySnapshot.from_json(payload).restore(conversation_adapter)
    add("social_conversations", capture_conversations, restore_conversations)

    trust = conversation_adapter.trust
    def capture_trust():
        return SocialTrustSnapshot.capture(trust).to_json()
    def restore_trust(payload):
        restored = SocialTrustSnapshot.from_json(payload).restore()
        _replace_mapping(trust._priors, restored._priors)
        _replace_mapping(trust._trust, restored._trust)
        _replace_mapping(trust._interactions, restored._interactions)
        _replace_mapping(trust._last_tick, restored._last_tick)
    add("social_trust", capture_trust, restore_trust)

    beliefs = conversation_adapter.beliefs
    def capture_beliefs():
        return SocialBeliefSnapshot.capture(beliefs).to_json()
    def restore_beliefs(payload):
        restored = SocialBeliefSnapshot.from_json(payload).restore(trust)
        _replace_mapping(beliefs._ledgers, restored._ledgers)
        _replace_mapping(beliefs._inputs, restored._inputs)
    add("social_beliefs", capture_beliefs, restore_beliefs)

    add("routine_book",
        lambda: RoutineBookSnapshot.capture(routine_book).to_json(),
        lambda payload: _replace_mapping(routine_book._blocks, {
            item.routine_id: item for item in RoutineBookSnapshot.from_json(payload).blocks
        }))
    add("routine_executions",
        lambda: RoutineExecutionSnapshot.capture(routine_ledger).to_json(),
        lambda payload: _replace_mapping(routine_ledger._records, {
            item.execution_id: item for item in RoutineExecutionSnapshot.from_json(payload).records
        }))

    if travel_adapter is not None:
        if presence_adapter is None:
            raise ValueError("travel transaction participant requires presence adapter")
        travel = travel_adapter.ledger
        add("travel",
            lambda: TravelSnapshot.capture(travel).to_json(),
            lambda payload: _restore_travel(travel, TravelSnapshot.from_json(payload).restore()))
        presence = presence_adapter.ledger
        add("presence",
            lambda: PresenceSnapshot.capture(presence).to_json(),
            lambda payload: _restore_presence(presence, PresenceSnapshot.from_json(payload).restore()))
    if encounter_adapter is not None:
        ledger = encounter_adapter.ledger
        add("encounters",
            lambda: PresenceEncounterSnapshot.capture(ledger).to_json(),
            lambda payload: _restore_encounters(ledger, PresenceEncounterSnapshot.from_json(payload).restore()))

    if economic_action_adapter is not None:
        economics = economic_action_adapter.economics
        add("economics",
            economics.to_json,
            lambda payload: _restore_economics(economics, EconomicLedger.from_json(payload)))
        def capture_economic_actions():
            records = []
            for execution_id, applied in sorted(economic_action_adapter._applied.items()):
                transfers = (applied,) if isinstance(applied, EconomicTransfer) else tuple(applied)
                records.append({
                    "execution_id": execution_id,
                    "transfer_ids": [item.transfer_id for item in transfers],
                })
            return _json({"schema_version": 2, "applied": records})
        def restore_economic_actions(payload):
            raw = json.loads(payload)
            if not isinstance(raw, dict) or raw.get("schema_version") not in (1, 2):
                raise ValueError("unsupported economic action participant schema")
            if raw["schema_version"] == 1:
                records = [
                    {"execution_id": execution_id, "transfer_ids": [f"action:{execution_id}:economic"]}
                    for execution_id in raw.get("applied", [])
                ]
            else:
                records = raw.get("applied")
            restored = {}
            for item in records:
                execution_id = item["execution_id"]
                if not isinstance(execution_id, str) or not execution_id.strip() or execution_id in restored:
                    raise ValueError("invalid or duplicate economic action execution ID")
                transfer_ids = item["transfer_ids"]
                if not isinstance(transfer_ids, list) or not transfer_ids:
                    raise ValueError("economic action checkpoint requires transfer IDs")
                transfers = []
                for transfer_id in transfer_ids:
                    transfer = economics._transfers.get(transfer_id)
                    if transfer is None:
                        raise ValueError("economic action checkpoint references a missing transfer")
                    transfers.append(transfer)
                restored[execution_id] = tuple(transfers)
            _replace_mapping(economic_action_adapter._applied, restored)
        add("economic_actions", capture_economic_actions, restore_economic_actions)

    if household_ledger is not None:
        def capture_households():
            return _json({"schema_version": 1, "obligations": [
                asdict(item) for item in household_ledger.snapshot()
            ]})
        def restore_households(payload):
            raw = json.loads(payload)
            if raw.get("schema_version") != 1:
                raise ValueError("unsupported household participant schema")
            restored = {item["obligation_id"]: HouseholdObligation(**item) for item in raw["obligations"]}
            _replace_mapping(household_ledger._obligations, restored)
        add("households", capture_households, restore_households)

    if action_world_state is not None:
        add("action_world_state", action_world_state.to_json, action_world_state.restore_json)

    if action_ledger is not None:
        if action_ledger.events is not events:
            raise ValueError("action ledger must share the tick coordinator world event ledger")
        if action_ledger.goals is not None:
            from .goals import GoalStatus, NPCGoal
            goal_book = action_ledger.goals
            def capture_action_goals():
                return _json({"schema_version": 1, "goals": [
                    {**asdict(goal), "status": goal.status.value}
                    for goal in sorted(goal_book.goals.values(), key=lambda item: item.goal_id)
                ]})
            def restore_action_goals(payload):
                raw = json.loads(payload)
                if raw.get("schema_version") != 1:
                    raise ValueError("unsupported action goal participant schema")
                restored = {}
                for item in raw["goals"]:
                    values = dict(item)
                    values["status"] = GoalStatus(values["status"])
                    goal = NPCGoal(**values)
                    goal.validate()
                    if goal.goal_id in restored:
                        raise ValueError("duplicate action goal ID in checkpoint")
                    restored[goal.goal_id] = goal
                existing = goal_book.goals
                for goal_id in tuple(existing):
                    if goal_id not in restored:
                        del existing[goal_id]
                for goal_id, saved in restored.items():
                    live = existing.get(goal_id)
                    if live is None:
                        existing[goal_id] = saved
                    else:
                        for field_name, value in asdict(saved).items():
                            if field_name == "status":
                                value = saved.status
                            setattr(live, field_name, value)
                goal_book._validate_dependency_graph()
            add("action_goals", capture_action_goals, restore_action_goals)
        def capture_actions():
            return action_ledger.to_snapshot().to_json()
        def restore_actions(payload):
            action_ledger.restore_snapshot(ActionExecutionSnapshot.from_json(payload))
        add("action_executions", capture_actions, restore_actions)

    return tuple(participants)


def _restore_travel(target, source):
    _replace_mapping(target._journeys, source._journeys)
    _replace_mapping(target._ticks, source._ticks)


def _restore_presence(target, source):
    _replace_mapping(target._records, source._records)
    _replace_mapping(target._ticks, source._ticks)


def _restore_encounters(target, source):
    _replace_mapping(target._records, source._records)
    _replace_mapping(target._ticks, source._ticks)


def _restore_economics(target, source):
    _replace_mapping(target._accounts, source._accounts)
    _replace_mapping(target._balances, source._balances)
    _replace_mapping(target._transfers, source._transfers)
