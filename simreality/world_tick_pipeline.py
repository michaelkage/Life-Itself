"""Atomic orchestration for travel, physical presence, encounters, and social ticks.

The world driver supplies road conditions, movement budgets, encounter opportunities,
and dialogue intents. This pipeline owns ordering and rollback, not world inference.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
import math
from typing import Mapping

from .model import NPC
from .presence import PresenceTickAdapter
from .presence_encounters import PresenceEncounterResult, PresenceSocialAdapter
from .route_planning import PersonalRoutePlanner
from .simulation_tick import (
    ConversationIntent,
    SimulationTickCoordinator,
    SimulationTickResult,
)
from .travel import TravelTickAdapter, TravelTickResult
from .world_events import WorldEventLedger


@dataclass(frozen=True)
class PresenceEncounterIntent:
    """A world-driver-confirmed social opportunity for two NPCs."""

    encounter_id: str
    first_id: str
    second_id: str
    opportunity: bool = True
    location_id: str | None = None
    conversation: bool = False
    conversation_id: str | None = None
    listener_id: str | None = None
    speaker_id: str | None = None
    district_id: str | None = None
    trust_directions: tuple[int, int] | None = None
    trust_strength: float = 0.0
    trust_context: str = "encounter"

    def __post_init__(self) -> None:
        for name in ("encounter_id", "first_id", "second_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if self.first_id == self.second_id:
            raise ValueError("an NPC cannot encounter themselves")
        if not isinstance(self.opportunity, bool) or not isinstance(self.conversation, bool):
            raise ValueError("opportunity and conversation must be booleans")
        for name in ("location_id", "conversation_id", "listener_id", "speaker_id", "district_id"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{name} must be None or a non-empty string")
        if self.conversation and not all(
            isinstance(value, str) and value.strip()
            for value in (self.conversation_id, self.listener_id, self.speaker_id)
        ):
            raise ValueError("conversational encounters require conversation, listener, and speaker IDs")
        if not self.conversation and any(
            value is not None for value in (self.conversation_id, self.listener_id, self.speaker_id)
        ):
            raise ValueError("dialogue IDs require conversation=True")
        if not isinstance(self.trust_context, str) or not self.trust_context.strip():
            raise ValueError("trust_context must be a non-empty string")
        if (isinstance(self.trust_strength, bool)
                or not isinstance(self.trust_strength, (int, float))
                or not math.isfinite(self.trust_strength)
                or not 0.0 <= self.trust_strength <= 1.0):
            raise ValueError("trust_strength must be finite and in [0, 1]")
        if self.trust_directions is not None and (
            not isinstance(self.trust_directions, tuple)
            or len(self.trust_directions) != 2
            or any(isinstance(value, bool) or value not in (-1, 1) for value in self.trust_directions)
        ):
            raise ValueError("trust_directions must contain two values of +1 or -1")


@dataclass(frozen=True)
class WorldTickPipelineResult:
    tick: int
    travel: TravelTickResult
    presence_updates: tuple
    encounters: tuple[PresenceEncounterResult, ...]
    social: SimulationTickResult


class SimulationWorldTickPipeline:
    """Commit a complete travel -> presence -> encounter -> social tick atomically.

    All authoritative event writes and subsystem replay indexes roll back together
    if any phase fails. Same-tick identical requests return the original result;
    conflicting replays and out-of-order new ticks are rejected.
    """

    def __init__(
        self,
        coordinator: SimulationTickCoordinator,
        travel: TravelTickAdapter,
        presence: PresenceTickAdapter,
        encounters: PresenceSocialAdapter,
    ) -> None:
        if not isinstance(coordinator, SimulationTickCoordinator):
            raise TypeError("coordinator must be a SimulationTickCoordinator")
        if not isinstance(travel, TravelTickAdapter):
            raise TypeError("travel must be a TravelTickAdapter")
        if not isinstance(presence, PresenceTickAdapter):
            raise TypeError("presence must be a PresenceTickAdapter")
        if not isinstance(encounters, PresenceSocialAdapter):
            raise TypeError("encounters must be a PresenceSocialAdapter")
        if presence.ledger is not encounters.presence:
            raise ValueError("presence and encounter adapters must share one PresenceLedger")
        if coordinator.memory_adapter.events is not coordinator.events:
            raise ValueError("coordinator memory adapter must use the coordinator event ledger")
        self.coordinator = coordinator
        self.travel = travel
        self.presence = presence
        self.encounters = encounters
        self.events: WorldEventLedger = coordinator.events
        self._requests: dict[int, str] = {}
        self._results: dict[int, WorldTickPipelineResult] = {}
        self._last_tick: int | None = None

    @staticmethod
    def _request_signature(
        tick: int,
        budgets: Mapping[str, float],
        closed_edge_ids: tuple[str, ...],
        time_multipliers: Mapping[str, float],
        replan_blocked: bool,
        avoidance_profiles_by_owner: Mapping[str, tuple],
        event_ids: tuple[str, ...],
        conversations: tuple[ConversationIntent, ...],
        encounters: tuple[PresenceEncounterIntent, ...],
        planner: PersonalRoutePlanner | None,
    ) -> str:
        payload = {
            "tick": tick,
            "budgets": sorted(budgets.items()),
            "closed_edge_ids": closed_edge_ids,
            "time_multipliers": sorted(time_multipliers.items()),
            "replan_blocked": replan_blocked,
            "avoidance_profiles": [
                (owner, [repr(profile) for profile in profiles])
                for owner, profiles in sorted(avoidance_profiles_by_owner.items())
            ],
            "event_ids": event_ids,
            "conversations": [repr(item) for item in conversations],
            "encounters": [repr(item) for item in encounters],
            "route_planner_identity": id(planner) if planner is not None else None,
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)

    def step(
        self,
        tick: int,
        npcs: Mapping[str, NPC],
        *,
        travel_budgets: Mapping[str, float],
        closed_edge_ids=(),
        time_multipliers: Mapping[str, float] | None = None,
        route_planner: PersonalRoutePlanner | None = None,
        replan_blocked: bool = False,
        avoidance_profiles_by_owner: Mapping[str, tuple] | None = None,
        event_ids: tuple[str, ...] = (),
        conversations: tuple[ConversationIntent, ...] = (),
        encounter_intents: tuple[PresenceEncounterIntent, ...] = (),
    ) -> WorldTickPipelineResult:
        if isinstance(tick, bool) or not isinstance(tick, int) or tick < 0:
            raise ValueError("tick must be a non-negative integer")
        if not isinstance(npcs, Mapping) or any(not isinstance(npc, NPC) for npc in npcs.values()):
            raise TypeError("npcs must map IDs to NPC instances")
        if any(key != npc.entity_id for key, npc in npcs.items()):
            raise ValueError("NPC mapping keys must match entity IDs")
        if not isinstance(travel_budgets, Mapping):
            raise TypeError("travel_budgets must be a mapping")
        if not isinstance(event_ids, tuple) or any(not isinstance(value, str) or not value.strip() for value in event_ids):
            raise ValueError("event_ids must be a tuple of non-empty strings")
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("event_ids must be unique")
        if not isinstance(conversations, tuple) or any(not isinstance(x, ConversationIntent) for x in conversations):
            raise ValueError("conversations must contain ConversationIntent values")
        if not isinstance(encounter_intents, tuple) or any(not isinstance(x, PresenceEncounterIntent) for x in encounter_intents):
            raise ValueError("encounter_intents must contain PresenceEncounterIntent values")
        if len({x.encounter_id for x in encounter_intents}) != len(encounter_intents):
            raise ValueError("encounter IDs must be unique within a tick")
        if any(x.first_id not in npcs or x.second_id not in npcs for x in encounter_intents):
            raise KeyError("encounter participant is missing from the supplied NPC roster")
        if any(x.listener_id not in npcs or x.speaker_id not in npcs
               for x in encounter_intents if x.conversation):
            raise KeyError("encounter dialogue participant is missing from the supplied NPC roster")
        multipliers = dict(time_multipliers or {})
        profiles = {owner: tuple(items) for owner, items in (avoidance_profiles_by_owner or {}).items()}
        closed = tuple(sorted(set(closed_edge_ids)))
        signature = self._request_signature(
            tick, travel_budgets, closed, multipliers, replan_blocked, profiles,
            event_ids, conversations, encounter_intents, route_planner,
        )
        if tick in self._requests:
            if self._requests[tick] != signature:
                raise ValueError(f"world tick {tick} replayed with different inputs")
            return self._results[tick]
        if self._last_tick is not None and tick <= self._last_tick:
            raise ValueError("new world ticks must be strictly increasing")

        conversation_adapter = self.coordinator.conversation_adapter
        beliefs = conversation_adapter.beliefs
        trust = conversation_adapter.trust
        memory_adapter = self.coordinator.memory_adapter
        affected_npcs = {
            owner: npc for owner, npc in npcs.items()
            if any(owner in (intent.listener_id, intent.speaker_id) for intent in conversations)
            or any(intent.conversation and owner in (intent.listener_id, intent.speaker_id)
                   for intent in encounter_intents)
            or any(owner in self.events.get(event_id).witnesses for event_id in event_ids
                   if self._event_exists(event_id))
        }

        rollback = {
            "events": deepcopy(self.events._events),
            "travel_journeys": deepcopy(self.travel.ledger._journeys),
            "travel_ticks": deepcopy(self.travel.ledger._ticks),
            "presence_records": deepcopy(self.presence.ledger._records),
            "presence_ticks": deepcopy(self.presence.ledger._ticks),
            "encounter_records": deepcopy(self.encounters.ledger._records),
            "encounter_ticks": deepcopy(self.encounters.ledger._ticks),
            "memory_replay": memory_adapter.transaction_snapshot(),
            "conversation_replay": conversation_adapter.transaction_snapshot(),
            "beliefs": beliefs.transaction_snapshot(),
            "trust": deepcopy(trust.__dict__),
            "npc_memories": {owner: deepcopy(npc.memories) for owner, npc in affected_npcs.items()},
            "coordinator_requests": deepcopy(self.coordinator._requests),
            "coordinator_results": deepcopy(self.coordinator._results),
            "coordinator_last_tick": self.coordinator._last_tick,
            "pipeline_requests": deepcopy(self._requests),
            "pipeline_results": deepcopy(self._results),
            "pipeline_last_tick": self._last_tick,
        }
        try:
            travel_result = self.travel.advance(
                tick, travel_budgets, closed_edge_ids=closed,
                time_multipliers=multipliers, route_planner=route_planner,
                replan_blocked=replan_blocked,
                avoidance_profiles_by_owner=profiles, events=self.events,
            )
            presence_updates = self.presence.synchronize(tick, self.travel.ledger, events=self.events)
            encounter_results = []
            for intent in sorted(encounter_intents, key=lambda item: item.encounter_id):
                result = self.encounters.encounter(
                    intent.encounter_id, intent.first_id, intent.second_id, tick,
                    opportunity=intent.opportunity, location_id=intent.location_id,
                    events=self.events, conversation=intent.conversation,
                    conversation_id=intent.conversation_id,
                    listener=npcs.get(intent.listener_id) if intent.listener_id else None,
                    speaker=npcs.get(intent.speaker_id) if intent.speaker_id else None,
                    conversation_adapter=conversation_adapter if intent.conversation else None,
                    district_id=intent.district_id,
                    trust=trust if intent.trust_directions is not None else None,
                    trust_directions=intent.trust_directions,
                    trust_strength=intent.trust_strength,
                    trust_context=intent.trust_context,
                )
                if result is not None:
                    encounter_results.append(result)

            tick_event_ids = tuple(sorted(set(event_ids).union(
                event.event_id for event in self.events.query(start_tick=tick, end_tick=tick)
            )))
            social_result = self.coordinator.step(
                tick, npcs, event_ids=tick_event_ids, conversations=conversations,
            )
            result = WorldTickPipelineResult(
                tick, travel_result, tuple(presence_updates),
                tuple(encounter_results), social_result,
            )
            self._requests[tick] = signature
            self._results[tick] = result
            self._last_tick = tick
            return result
        except BaseException:
            self.events._events = rollback["events"]
            self.travel.ledger._journeys = rollback["travel_journeys"]
            self.travel.ledger._ticks = rollback["travel_ticks"]
            self.presence.ledger._records = rollback["presence_records"]
            self.presence.ledger._ticks = rollback["presence_ticks"]
            self.encounters.ledger._records = rollback["encounter_records"]
            self.encounters.ledger._ticks = rollback["encounter_ticks"]
            memory_adapter.restore_transaction_snapshot(rollback["memory_replay"])
            conversation_adapter.restore_transaction_snapshot(rollback["conversation_replay"])
            beliefs.restore_transaction_snapshot(rollback["beliefs"])
            for key, value in rollback["trust"].items():
                setattr(trust, key, value)
            for owner, memories in rollback["npc_memories"].items():
                affected_npcs[owner].memories[:] = memories
            self.coordinator._requests = rollback["coordinator_requests"]
            self.coordinator._results = rollback["coordinator_results"]
            self.coordinator._last_tick = rollback["coordinator_last_tick"]
            self._requests = rollback["pipeline_requests"]
            self._results = rollback["pipeline_results"]
            self._last_tick = rollback["pipeline_last_tick"]
            raise

    def _event_exists(self, event_id: str) -> bool:
        try:
            self.events.get(event_id)
            return True
        except KeyError:
            return False
