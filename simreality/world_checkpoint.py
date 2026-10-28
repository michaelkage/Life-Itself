"""Composite persistence for the currently integrated simulation pipeline."""
from __future__ import annotations

from dataclasses import dataclass
import json
import math

from .adapter_replay_state import WorldEventMemoryReplaySnapshot
from .npc_save_state import NPCCollectionSnapshot, SocialTrustSnapshot
from .save_state import SimulationSaveEnvelope
from .social_belief_save_state import SocialBeliefSnapshot
from .social_conversations import SocialConversationAdapter
from .social_replay_save_state import SocialConversationReplaySnapshot
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


@dataclass(frozen=True)
class SimulationWorldCheckpoint:
    """One versioned container composed from the existing component codecs.

    Restore order is event journal, NPCs, trust, beliefs, memory replay index,
    conversation replay index, then coordinator replay history.
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
    def capture(cls, current_tick, coordinator, npcs, *, metadata=None):
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
        )

    def to_json(self):
        envelope, npcs, trust, beliefs, memory, conversations, ticks = self._components()
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
                       nested("tick_replay"), raw.get("ticks_per_hour", 1.0), metadata)
        except ValueError:
            raise
        except (TypeError, KeyError, IndexError, json.JSONDecodeError) as exc:
            raise ValueError("invalid simulation world checkpoint") from exc

    def restore(self):
        envelope, npc_snapshot, trust_snapshot, belief_snapshot, memory_snapshot, conversation_snapshot, tick_snapshot = self._components()
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
        return RestoredSimulation(self.current_tick, events, npcs, trust, beliefs,
                                  memory, conversations, coordinator, self.metadata)
