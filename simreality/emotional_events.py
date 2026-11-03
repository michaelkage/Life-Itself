"""Event-driven emotional state with deterministic decay and replay protection.

World events remain authoritative facts. This module applies explicitly authored
per-event rules to NPCs who are recorded participants or witnesses; it does not
infer relationships, diagnose emotions, or decide what an event means.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Mapping

from .identity_context import NPCEmotionalState
from .world_events import WorldEvent
from .social_trust import SocialTrustLedger


@dataclass(frozen=True)
class EmotionalEventRule:
    rule_id: str
    event_type: str
    role: str
    emotion_axis: str
    delta: float

    def __post_init__(self):
        for name in ("rule_id", "event_type", "emotion_axis"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if self.role not in ("participant", "witness"):
            raise ValueError("role must be 'participant' or 'witness'")
        if (isinstance(self.delta, bool) or not isinstance(self.delta, (int, float))
                or not math.isfinite(self.delta) or not -1.0 <= self.delta <= 1.0):
            raise ValueError("delta must be finite and in [-1, 1]")


@dataclass(frozen=True)
class EmotionalRelationshipRule:
    """Relationship-sensitive emotion impulse using an event's explicit target ID.

    The event attribute named by target_attribute identifies who the event is
    about. Trust is sampled at the event tick, not at the later processing tick.
    """

    rule_id: str
    event_type: str
    role: str
    emotion_axis: str
    target_attribute: str
    coefficient: float

    def __post_init__(self):
        for name in ("rule_id", "event_type", "emotion_axis", "target_attribute"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if self.role not in ("participant", "witness"):
            raise ValueError("role must be 'participant' or 'witness'")
        value = self.coefficient
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or not -1.0 <= value <= 1.0):
            raise ValueError("coefficient must be finite and in [-1, 1]")


@dataclass(frozen=True)
class EmotionalMemoryRule:
    """Apply an emotional impulse when retained personal memories match an event.

    The event supplies a target NPC ID and action-tag string. Only memories
    explicitly matching both facts contribute; no semantic similarity is guessed.
    """

    rule_id: str
    event_type: str
    role: str
    emotion_axis: str
    target_attribute: str = "target_entity_id"
    action_tag_attribute: str = "action_tag"
    coefficient: float = 0.5
    minimum_retention: float = 0.0

    def __post_init__(self):
        for name in ("rule_id", "event_type", "emotion_axis",
                     "target_attribute", "action_tag_attribute"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if self.role not in ("participant", "witness"):
            raise ValueError("role must be 'participant' or 'witness'")
        for name, low, high in (("coefficient", -1.0, 1.0),
                                ("minimum_retention", 0.0, 1.0)):
            value = getattr(self, name)
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(value) or not low <= value <= high):
                raise ValueError(f"{name} must be finite and in [{low}, {high}]")

@dataclass(frozen=True)
class EmotionalDecayRule:
    emotion_axis: str
    retained_per_tick: float

    def __post_init__(self):
        if not isinstance(self.emotion_axis, str) or not self.emotion_axis.strip():
            raise ValueError("emotion_axis must be a non-empty string")
        value = self.retained_per_tick
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or not 0.0 <= value <= 1.0):
            raise ValueError("retained_per_tick must be finite and in [0, 1]")


class NPCEmotionalEventLedger:
    """Advance transient emotional snapshots from event history, exactly once.

    The ledger stores only emotional intensities and applied event/rule keys.
    Event order is canonicalized by (tick, event_id); identical retries are
    idempotent, while conflicting reuse or backwards time is rejected.
    """

    def __init__(
        self,
        initial_states: Mapping[str, NPCEmotionalState] | None = None,
        *,
        current_tick: int = 0,
    ):
        if isinstance(current_tick, bool) or not isinstance(current_tick, int) or current_tick < 0:
            raise ValueError("current_tick must be a non-negative integer")
        self.current_tick = current_tick
        self._states: dict[str, dict[str, float]] = {}
        self._applied: dict[tuple[str, str, str], tuple[int, float]] = {}
        self._events: dict[str, WorldEvent] = {}
        for npc_id, state in (initial_states or {}).items():
            if not isinstance(state, NPCEmotionalState) or state.npc_id != npc_id:
                raise ValueError("initial state mapping keys must match NPC IDs")
            if state.sampled_tick != current_tick:
                raise ValueError("initial emotional states must match current_tick")
            self._states[npc_id] = dict(state.intensities)

    def state_for(self, npc_id: str) -> NPCEmotionalState:
        if not isinstance(npc_id, str) or not npc_id.strip():
            raise ValueError("npc_id must be a non-empty string")
        return NPCEmotionalState(npc_id, self.current_tick, self._states.get(npc_id, {}))

    def states(self) -> tuple[NPCEmotionalState, ...]:
        return tuple(self.state_for(npc_id) for npc_id in sorted(self._states))

    def advance(
        self,
        tick: int,
        events: Iterable[WorldEvent],
        *,
        event_rules: Iterable[EmotionalEventRule],
        decay_rules: Iterable[EmotionalDecayRule] = (),
        relationship_rules: Iterable[EmotionalRelationshipRule] = (),
        trust_ledger: SocialTrustLedger | None = None,
        memory_rules: Iterable[EmotionalMemoryRule] = (),
        npcs_by_id: Mapping[str, object] | None = None,
    ) -> tuple[NPCEmotionalState, ...]:
        if isinstance(tick, bool) or not isinstance(tick, int) or tick < self.current_tick:
            raise ValueError("tick must be an integer not earlier than current_tick")
        event_items = tuple(events)
        if any(not isinstance(event, WorldEvent) for event in event_items):
            raise TypeError("events must contain WorldEvent values")
        if len({event.event_id for event in event_items}) != len(event_items):
            raise ValueError("event IDs must be unique within an advance batch")
        if any(event.tick > tick for event in event_items):
            raise ValueError("cannot apply an event from after the requested tick")
        rules = tuple(event_rules)
        decay = tuple(decay_rules)
        relationship = tuple(relationship_rules)
        memories = tuple(memory_rules)
        if any(not isinstance(rule, EmotionalEventRule) for rule in rules):
            raise TypeError("event_rules must contain EmotionalEventRule values")
        if any(not isinstance(rule, EmotionalDecayRule) for rule in decay):
            raise TypeError("decay_rules must contain EmotionalDecayRule values")
        if any(not isinstance(rule, EmotionalRelationshipRule) for rule in relationship):
            raise TypeError("relationship_rules must contain EmotionalRelationshipRule values")
        if any(not isinstance(rule, EmotionalMemoryRule) for rule in memories):
            raise TypeError("memory_rules must contain EmotionalMemoryRule values")
        if memories and not isinstance(npcs_by_id, Mapping):
            raise TypeError("memory rules require an NPC mapping keyed by entity ID")
        if memories and any(getattr(npc, "entity_id", None) != npc_id or not hasattr(npc, "memories") for npc_id, npc in npcs_by_id.items()):
            raise TypeError("NPC mapping keys must match NPC entity IDs")
        if relationship and not isinstance(trust_ledger, SocialTrustLedger):
            raise TypeError("relationship rules require a SocialTrustLedger")
        all_rule_ids = [r.rule_id for r in rules] + [r.rule_id for r in relationship] + [r.rule_id for r in memories]
        if len(set(all_rule_ids)) != len(all_rule_ids):
            raise ValueError("event and relationship rule IDs must be unique")
        if len({r.emotion_axis for r in decay}) != len(decay):
            raise ValueError("decay axes must be unique")

        # Validate retries before changing any state (atomic batch semantics).
        decay_by_axis = {rule.emotion_axis: rule.retained_per_tick for rule in decay}
        ordered_events = tuple(sorted(event_items, key=lambda e: (e.tick, e.event_id)))
        for event in ordered_events:
            existing_event = self._events.get(event.event_id)
            if existing_event is not None and existing_event != event:
                raise ValueError("world event ID reused with conflicting content")
            if existing_event is None and event.tick < self.current_tick:
                raise ValueError("new emotional events cannot be inserted before current_tick")
            for rule in rules:
                if rule.event_type != event.event_type:
                    continue
                people = event.participants if rule.role == "participant" else event.witnesses
                for npc_id in people:
                    key = (event.event_id, npc_id, rule.rule_id)
                    prior = self._applied.get(key)
                    signature = (event.tick, float(rule.delta))
                    if prior is not None and prior != signature:
                        raise ValueError("event/rule application ID reused with conflicting content")
            attributes = dict(event.attributes)
            for rule in relationship:
                if rule.event_type != event.event_type or rule.target_attribute not in attributes:
                    continue
                target_id = attributes[rule.target_attribute]
                if not isinstance(target_id, str) or not target_id.strip():
                    raise ValueError("relationship target event attribute must be a non-empty NPC ID")
                people = event.participants if rule.role == "participant" else event.witnesses
                for npc_id in people:
                    sampled_trust = trust_ledger.trust_at(npc_id, target_id, event.tick)
                    delta = float(rule.coefficient) * (2.0 * sampled_trust - 1.0)
                    key = (event.event_id, npc_id, rule.rule_id)
                    prior = self._applied.get(key)
                    signature = (event.tick, delta)
                    if prior is not None and prior != signature:
                        raise ValueError("event/rule application ID reused with conflicting content")

        # Exact event retries are no-ops; they must not rewind the decay cursor.
        ordered_events = tuple(event for event in ordered_events if event.event_id not in self._events)
        cursor = self.current_tick
        ordered_rules = sorted(rules, key=lambda r: (r.event_type, r.role, r.emotion_axis, r.rule_id))
        ordered_relationship_rules = sorted(relationship, key=lambda r: (r.event_type, r.role, r.emotion_axis, r.target_attribute, r.rule_id))
        for event in ordered_events:
            step = event.tick - cursor
            if step:
                self._decay_states(step, decay_by_axis)
                cursor = event.tick
            for rule in ordered_rules:
                if rule.event_type != event.event_type:
                    continue
                people = event.participants if rule.role == "participant" else event.witnesses
                for npc_id in people:
                    key = (event.event_id, npc_id, rule.rule_id)
                    signature = (event.tick, float(rule.delta))
                    if key in self._applied:
                        continue
                    values = self._states.setdefault(npc_id, {})
                    values[rule.emotion_axis] = max(
                        0.0, min(1.0, values.get(rule.emotion_axis, 0.0) + rule.delta)
                    )
                    self._applied[key] = signature
            attributes = dict(event.attributes)
            for rule in ordered_relationship_rules:
                if rule.event_type != event.event_type or rule.target_attribute not in attributes:
                    continue
                target_id = attributes[rule.target_attribute]
                people = event.participants if rule.role == "participant" else event.witnesses
                for npc_id in people:
                    sampled_trust = trust_ledger.trust_at(npc_id, target_id, event.tick)
                    delta = float(rule.coefficient) * (2.0 * sampled_trust - 1.0)
                    key = (event.event_id, npc_id, rule.rule_id)
                    signature = (event.tick, delta)
                    if key in self._applied:
                        continue
                    values = self._states.setdefault(npc_id, {})
                    values[rule.emotion_axis] = max(
                        0.0, min(1.0, values.get(rule.emotion_axis, 0.0) + delta)
                    )
                    self._applied[key] = signature
            self._events.setdefault(event.event_id, event)
        if tick > cursor:
            self._decay_states(tick - cursor, decay_by_axis)
        self.current_tick = tick
        return self.states()

    def _decay_states(self, elapsed: int, decay_by_axis: Mapping[str, float]) -> None:
        if elapsed <= 0:
            return
        for values in self._states.values():
            for axis, value in tuple(values.items()):
                values[axis] = value * (decay_by_axis.get(axis, 1.0) ** elapsed)

    def snapshot(self) -> dict:
        """Return a canonical JSON-compatible snapshot."""
        return {
            "version": 1,
            "current_tick": self.current_tick,
            "states": {
                npc_id: dict(sorted(values.items()))
                for npc_id, values in sorted(self._states.items())
            },
            "events": [
                {"event_id": event.event_id, "tick": event.tick,
                 "event_type": event.event_type, "participants": list(event.participants),
                 "witnesses": list(event.witnesses), "attributes": [list(pair) for pair in event.attributes]}
                for event in sorted(self._events.values(), key=lambda e: (e.tick, e.event_id))
            ],
            "applied": [
                {"event_id": event_id, "npc_id": npc_id, "rule_id": rule_id,
                 "event_tick": signature[0], "delta": signature[1]}
                for (event_id, npc_id, rule_id), signature in sorted(self._applied.items())
            ],
        }

    @classmethod
    def from_snapshot(cls, snapshot: dict) -> "NPCEmotionalEventLedger":
        if not isinstance(snapshot, dict) or snapshot.get("version") != 1:
            raise ValueError("unsupported emotional event snapshot")
        states = {
            npc_id: NPCEmotionalState(npc_id, snapshot["current_tick"], values)
            for npc_id, values in snapshot["states"].items()
        }
        ledger = cls(states, current_tick=snapshot["current_tick"])
        for item in snapshot.get("events", []):
            event = WorldEvent(
                event_id=item["event_id"], tick=item["tick"], event_type=item["event_type"],
                participants=tuple(item["participants"]), witnesses=tuple(item["witnesses"]),
                attributes=tuple(tuple(pair) for pair in item["attributes"]),
            )
            if event.event_id in ledger._events:
                raise ValueError("duplicate event ID in emotional snapshot")
            ledger._events[event.event_id] = event
        for item in snapshot["applied"]:
            key = (item["event_id"], item["npc_id"], item["rule_id"])
            signature = (item["event_tick"], item["delta"])
            if key in ledger._applied:
                raise ValueError("duplicate applied emotional event key")
            if signature[0] > ledger.current_tick or not math.isfinite(signature[1]):
                raise ValueError("invalid applied emotional event record")
            ledger._applied[key] = signature
        return ledger
