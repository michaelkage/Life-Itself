"""Composite persistence for the currently integrated simulation pipeline."""
from __future__ import annotations

from dataclasses import dataclass
import json
import math

from .adapter_replay_state import WorldEventMemoryReplaySnapshot
from .campaign import LifeItselfCampaign
from .misconduct import MisconductReportingSystem
from .misconduct_save_state import MisconductSnapshot
from .routine_save_state import RoutineBookSnapshot
from .routine_execution import RoutineExecutionLedger
from .routine_execution_save_state import RoutineExecutionSnapshot
from .routines import RoutineBook
from .npc_save_state import NPCCollectionSnapshot, SocialTrustSnapshot
from .save_state import SimulationSaveEnvelope
from .social_belief_save_state import SocialBeliefSnapshot
from .social_conversations import SocialConversationAdapter
from .social_consequences import SocialConsequenceRecorder
from .social_replay_save_state import SocialConsequenceReplaySnapshot, SocialConversationReplaySnapshot
from .simulation_tick import SimulationTickCoordinator
from .social_trust import SocialTrustLedger
from .tick_replay_save_state import SimulationTickReplaySnapshot
from .world_event_memory import WorldEventMemoryAdapter
from .world_events import WorldEventLedger


@dataclass(frozen=True)
class RestoredSimulation:
    current_tick: int
    events: WorldEventLedger
    npcs: dict
    trust: SocialTrustLedger
    beliefs: object
    memory_adapter: WorldEventMemoryAdapter
    conversation_adapter: SocialConversationAdapter
    coordinator: SimulationTickCoordinator
    metadata: tuple
    consequence_recorder: SocialConsequenceRecorder | None = None
    campaign: LifeItselfCampaign | None = None
    misconduct: MisconductReportingSystem | None = None
    routines: RoutineBook | None = None
    routine_executions: RoutineExecutionLedger | None = None


@dataclass(frozen=True)
class SimulationWorldCheckpoint:
    """One versioned container composed from the existing component codecs.

    Restore order is event journal, NPCs, trust, beliefs, memory replay index,
    conversation replay index, coordinator replay history, then optional
    misconduct reports validated against the authoritative event journal.
    """
    current_tick: int
    events_json: str
    npcs_json: str
    trust_json: str
    beliefs_json: str
    memory_replay_json: str
    conversations_json: str
    tick_replay_json: str
    ticks_per_hour: float = 1.0
    metadata: tuple = ()
    consequence_replay_json: str | None = None
    campaign_json: str | None = None
    misconduct_json: str | None = None
    routines_json: str | None = None
    routine_executions_json: str | None = None

    SCHEMA_VERSION = 1

    def __post_init__(self):
        if isinstance(self.current_tick, bool) or not isinstance(self.current_tick, int) or self.current_tick < 0:
            raise ValueError("current_tick must be a non-negative integer")
        if isinstance(self.ticks_per_hour, bool) or not isinstance(self.ticks_per_hour, (int, float)) or not math.isfinite(self.ticks_per_hour) or self.ticks_per_hour <= 0:
            raise ValueError("ticks_per_hour must be positive and finite")
        if not isinstance(self.metadata, tuple):
            raise ValueError("metadata must be a tuple")
        keys = []
        for pair in self.metadata:
            if not isinstance(pair, tuple) or len(pair) != 2:
                raise ValueError("metadata entries must be key/value pairs")
            key, value = pair
            if not isinstance(key, str) or not key.strip():
                raise ValueError("metadata keys must be non-empty")
            if value is not None and not isinstance(value, (str, int, float, bool)):
                raise ValueError("metadata values must be JSON scalars")
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError("metadata values must be finite")
            keys.append(key)
        if keys != sorted(keys) or len(keys) != len(set(keys)):
            raise ValueError("metadata keys must be unique and sorted")
        self._components()

    @classmethod
    def capture(cls, current_tick, coordinator, npcs, *, metadata=None,
                consequence_recorder=None, campaign=None, misconduct=None, routines=None,
                routine_executions=None):
        if not isinstance(coordinator, SimulationTickCoordinator):
            raise TypeError("coordinator must be a SimulationTickCoordinator")
        if not isinstance(npcs, dict):
            raise TypeError("npcs must be a dict keyed by entity ID")
        if coordinator._last_tick is not None and current_tick < coordinator._last_tick:
            raise ValueError("current_tick cannot precede the last processed tick")
        for npc_id, npc in npcs.items():
            if not isinstance(npc_id, str) or not npc_id.strip() or getattr(npc, "entity_id", None) != npc_id:
                raise ValueError("NPC mapping keys must match NPC entity IDs")
        trust = coordinator.conversation_adapter.trust
        beliefs = coordinator.conversation_adapter.beliefs
        if beliefs.trust is not trust:
            raise ValueError("beliefs and conversation adapter must share trust")
        if consequence_recorder is not None:
            if not isinstance(consequence_recorder, SocialConsequenceRecorder):
                raise TypeError("consequence_recorder must be a SocialConsequenceRecorder or None")
            if consequence_recorder.trust is not trust or consequence_recorder.beliefs is not beliefs:
                raise ValueError("consequence recorder must share the checkpoint trust and belief systems")
        if campaign is not None and not isinstance(campaign, LifeItselfCampaign):
            raise TypeError("campaign must be a LifeItselfCampaign or None")
        if routines is not None and not isinstance(routines, RoutineBook):
            raise TypeError("routines must be a RoutineBook or None")
        routines_snapshot = RoutineBookSnapshot.capture(routines) if routines is not None else None
        if routine_executions is not None and not isinstance(routine_executions, RoutineExecutionLedger):
            raise TypeError("routine_executions must be a RoutineExecutionLedger or None")
        if routine_executions is not None and routines is None:
            raise ValueError("routine execution history requires the corresponding RoutineBook")
        execution_snapshot = RoutineExecutionSnapshot.capture(routine_executions) if routine_executions is not None else None
        if execution_snapshot is not None:
            known_routines = {block.routine_id for block in routines.snapshot()}
            if any(record.routine_id not in known_routines for record in execution_snapshot.records):
                raise ValueError("routine execution history references an unknown routine")
        misconduct_snapshot = None
        if misconduct is not None:
            if not isinstance(misconduct, MisconductReportingSystem):
                raise TypeError("misconduct must be a MisconductReportingSystem or None")
            misconduct_snapshot = MisconductSnapshot.capture(misconduct)
            if any(report.filed_tick > current_tick for report in misconduct_snapshot.reports):
                raise ValueError("misconduct reports cannot be filed after the checkpoint tick")
            if any(decision.tick > current_tick for decision in misconduct_snapshot.decisions):
                raise ValueError("misconduct review decisions cannot occur after the checkpoint tick")
            misconduct_snapshot.restore(coordinator.events)  # validate incident references before saving
        envelope = SimulationSaveEnvelope.capture(current_tick, coordinator.events)
        return cls(
            current_tick, envelope.to_json(),
            NPCCollectionSnapshot.capture(list(npcs.values())).to_json(),
            SocialTrustSnapshot.capture(trust).to_json(),
            SocialBeliefSnapshot.capture(beliefs).to_json(),
            WorldEventMemoryReplaySnapshot.capture(coordinator.memory_adapter).to_json(),
            SocialConversationReplaySnapshot.capture(coordinator.conversation_adapter).to_json(),
            SimulationTickReplaySnapshot.capture(coordinator).to_json(),
            coordinator.memory_adapter.ticks_per_hour,
            tuple(sorted((metadata or {}).items())),
            SocialConsequenceReplaySnapshot.capture(consequence_recorder).to_json() if consequence_recorder is not None else None,
            campaign.to_json() if campaign is not None else None,
            misconduct_snapshot.to_json() if misconduct_snapshot is not None else None,
            routines_snapshot.to_json() if routines_snapshot is not None else None,
            execution_snapshot.to_json() if execution_snapshot is not None else None,
        )

    def _components(self):
        envelope = SimulationSaveEnvelope.from_json(self.events_json)
        if envelope.current_tick != self.current_tick:
            raise ValueError("checkpoint clock does not match event envelope")
        return (
            envelope,
            NPCCollectionSnapshot.from_json(self.npcs_json),
            SocialTrustSnapshot.from_json(self.trust_json),
            SocialBeliefSnapshot.from_json(self.beliefs_json),
            WorldEventMemoryReplaySnapshot.from_json(self.memory_replay_json),
            SocialConversationReplaySnapshot.from_json(self.conversations_json),
            SimulationTickReplaySnapshot.from_json(self.tick_replay_json),
            SocialConsequenceReplaySnapshot.from_json(self.consequence_replay_json) if self.consequence_replay_json is not None else None,
            LifeItselfCampaign.from_json(self.campaign_json) if self.campaign_json is not None else None,
            MisconductSnapshot.from_json(self.misconduct_json) if self.misconduct_json is not None else None,
            RoutineBookSnapshot.from_json(self.routines_json) if self.routines_json is not None else None,
            RoutineExecutionSnapshot.from_json(self.routine_executions_json) if self.routine_executions_json is not None else None,
        )

    def to_json(self):
        envelope, npcs, trust, beliefs, memory, conversations, ticks, consequence, campaign, misconduct, routines, routine_executions = self._components()
        payload = {
            "schema_version": self.SCHEMA_VERSION, "current_tick": self.current_tick,
            "events": json.loads(envelope.to_json()), "npcs": json.loads(npcs.to_json()),
            "trust": json.loads(trust.to_json()), "beliefs": json.loads(beliefs.to_json()),
            "memory_replay": json.loads(memory.to_json()),
            "conversations": json.loads(conversations.to_json()),
            "tick_replay": json.loads(ticks.to_json()),
            "ticks_per_hour": self.ticks_per_hour,
            "metadata": [list(pair) for pair in self.metadata],
        }
        if consequence is not None:
            payload["consequence_replay"] = json.loads(consequence.to_json())
        if self.campaign_json is not None:
            payload["campaign"] = json.loads(self.campaign_json)
        if misconduct is not None:
            payload["misconduct"] = json.loads(misconduct.to_json())
        if routines is not None:
            payload["routines"] = json.loads(routines.to_json())
        if routine_executions is not None:
            payload["routine_executions"] = json.loads(routine_executions.to_json())
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)

    @classmethod
    def from_json(cls, payload):
        try:
            raw = json.loads(payload)
            if not isinstance(raw, dict) or raw.get("schema_version") != cls.SCHEMA_VERSION:
                raise ValueError("unsupported world checkpoint schema version")
            nested = lambda key: json.dumps(raw[key], sort_keys=True, separators=(",", ":"), allow_nan=False)
            metadata = tuple(sorted(((item[0], item[1]) for item in raw.get("metadata", ())), key=lambda pair: pair[0]))
            return cls(raw["current_tick"], nested("events"), nested("npcs"), nested("trust"),
                       nested("beliefs"), nested("memory_replay"), nested("conversations"),
                       nested("tick_replay"), raw.get("ticks_per_hour", 1.0), metadata,
                       json.dumps(raw["consequence_replay"], sort_keys=True, separators=(",", ":"), allow_nan=False) if raw.get("consequence_replay") is not None else None,
                       json.dumps(raw["campaign"], sort_keys=True, separators=(",", ":"), allow_nan=False) if raw.get("campaign") is not None else None,
                       json.dumps(raw["misconduct"], sort_keys=True, separators=(",", ":"), allow_nan=False) if raw.get("misconduct") is not None else None,
                       json.dumps(raw["routines"], sort_keys=True, separators=(",", ":"), allow_nan=False) if raw.get("routines") is not None else None,
                       json.dumps(raw["routine_executions"], sort_keys=True, separators=(",", ":"), allow_nan=False) if raw.get("routine_executions") is not None else None)
        except ValueError:
            raise
        except (TypeError, KeyError, IndexError, json.JSONDecodeError) as exc:
            raise ValueError("invalid simulation world checkpoint") from exc

    def restore(self):
        envelope, npc_snapshot, trust_snapshot, belief_snapshot, memory_snapshot, conversation_snapshot, tick_snapshot, consequence_snapshot, campaign, misconduct_snapshot, routine_snapshot, execution_snapshot = self._components()
        events = envelope.restore_event_ledger()
        npcs = npc_snapshot.restore()
        trust = trust_snapshot.restore()
        beliefs = belief_snapshot.restore(trust)
        memory = WorldEventMemoryAdapter(events, ticks_per_hour=self.ticks_per_hour)
        memory_snapshot.restore(memory, npcs)
        conversations = SocialConversationAdapter(trust, beliefs)
        conversation_snapshot.restore(conversations)
        coordinator = SimulationTickCoordinator(events, memory, conversations)
        tick_snapshot.restore(coordinator)
        consequence_recorder = SocialConsequenceRecorder(trust, beliefs) if consequence_snapshot is not None else None
        if consequence_snapshot is not None:
            consequence_snapshot.restore(consequence_recorder)
        misconduct = misconduct_snapshot.restore(events) if misconduct_snapshot is not None else None
        if misconduct is not None:
            if any(report.filed_tick > self.current_tick for report in misconduct.snapshot()[0]):
                raise ValueError("misconduct reports cannot be after the checkpoint tick")
            if any(decision.tick > self.current_tick for decision in misconduct.snapshot()[1]):
                raise ValueError("misconduct decisions cannot be after the checkpoint tick")
        routines = routine_snapshot.restore() if routine_snapshot is not None else None
        routine_executions = execution_snapshot.restore() if execution_snapshot is not None else None
        if routine_executions is not None:
            if routines is None:
                raise ValueError("routine execution history requires a routine schedule")
            known_routines = {block.routine_id for block in routines.snapshot()}
            if any(record.routine_id not in known_routines for record in routine_executions.snapshot()):
                raise ValueError("routine execution history references an unknown routine")
        return RestoredSimulation(self.current_tick, events, npcs, trust, beliefs,
                                  memory, conversations, coordinator, self.metadata,
                                  consequence_recorder, campaign, misconduct, routines, routine_executions)
