"""Explicit observer-specific autobiographical memory formation from world events.

This bridge never guesses what an event means. Authored per-NPC rules decide
whether an observed event becomes a memory and supply its subjective meaning
and impact. The immutable WorldEvent remains the source of objective facts.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from .npc_life_history import AutobiographicalMemory, NPCLifeHistory
from .world_events import WorldEvent


@dataclass(frozen=True)
class AutobiographicalMemoryRule:
    rule_id: str
    event_type: str
    role: str
    interpretation: str
    emotional_impact: float
    identity_impact: float
    turning_point: bool = False
    tags: tuple[str, ...] = ()
    include_participants: bool = True
    include_witnesses: bool = False

    def __post_init__(self):
        for name in ("rule_id", "event_type", "interpretation"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if self.role not in ("participant", "witness"):
            raise ValueError("role must be participant or witness")
        if (isinstance(self.emotional_impact, bool)
                or not isinstance(self.emotional_impact, (int, float))
                or not 0 <= self.emotional_impact <= 1):
            raise ValueError("emotional_impact must be in [0, 1]")
        if (isinstance(self.identity_impact, bool)
                or not isinstance(self.identity_impact, (int, float))
                or not -1 <= self.identity_impact <= 1):
            raise ValueError("identity_impact must be in [-1, 1]")
        if not isinstance(self.turning_point, bool):
            raise TypeError("turning_point must be bool")
        if not isinstance(self.tags, tuple) or any(not isinstance(x, str) or not x.strip() for x in self.tags):
            raise ValueError("tags must be a tuple of non-empty strings")
        if len(self.tags) != len(set(self.tags)):
            raise ValueError("tags must not contain duplicates")
        if not isinstance(self.include_participants, bool) or not isinstance(self.include_witnesses, bool):
            raise TypeError("include_participants and include_witnesses must be bool")


@dataclass(frozen=True)
class AutobiographicalMemoryProfile:
    owner_id: str
    rules: tuple[AutobiographicalMemoryRule, ...]

    def __post_init__(self):
        if not isinstance(self.owner_id, str) or not self.owner_id.strip():
            raise ValueError("owner_id must be a non-empty string")
        if not isinstance(self.rules, tuple) or any(not isinstance(x, AutobiographicalMemoryRule) for x in self.rules):
            raise TypeError("rules must be a tuple of AutobiographicalMemoryRule values")
        ids = [x.rule_id for x in self.rules]
        if len(ids) != len(set(ids)):
            raise ValueError("memory rule IDs must be unique per observer")


class NPCAutobiographicalMemoryAdapter:
    """Materialize authored personal memories for explicitly observed events."""

    @staticmethod
    def process(
        events: Iterable[WorldEvent],
        profiles_by_npc: Mapping[str, AutobiographicalMemoryProfile],
        history: NPCLifeHistory,
        *,
        conflict_ids_by_event_observer: Mapping[tuple[str, str], tuple[str, ...]] | None = None,
        learning_decision_ids_by_event_observer: Mapping[tuple[str, str], tuple[str, ...]] | None = None,
    ) -> tuple[AutobiographicalMemory, ...]:
        if not isinstance(history, NPCLifeHistory):
            raise TypeError("history must be NPCLifeHistory")
        if not isinstance(profiles_by_npc, Mapping):
            raise TypeError("profiles_by_npc must be a mapping")
        for owner, profile in profiles_by_npc.items():
            if not isinstance(profile, AutobiographicalMemoryProfile) or profile.owner_id != owner:
                raise ValueError("profile mapping keys must match profile owner IDs")
        conflicts = {} if conflict_ids_by_event_observer is None else conflict_ids_by_event_observer
        decisions = {} if learning_decision_ids_by_event_observer is None else learning_decision_ids_by_event_observer
        if not isinstance(conflicts, Mapping) or not isinstance(decisions, Mapping):
            raise TypeError("linked record mappings must be mappings")
        batch = tuple(events)
        if any(not isinstance(event, WorldEvent) for event in batch):
            raise TypeError("events must contain WorldEvent values")
        if len({event.event_id for event in batch}) != len(batch):
            raise ValueError("event IDs must be unique within a batch")
        formed = []
        for event in sorted(batch, key=lambda x: (x.tick, x.event_id)):
            participants = set(event.participants)
            witnesses = set(event.witnesses)
            observers = sorted((participants | witnesses) & set(profiles_by_npc))
            for owner in observers:
                profile = profiles_by_npc[owner]
                role = "participant" if owner in participants else "witness"
                for rule in sorted(profile.rules, key=lambda x: x.rule_id):
                    if rule.event_type != event.event_type or rule.role != role:
                        continue
                    involved = set()
                    if rule.include_participants:
                        involved.update(participants)
                    if rule.include_witnesses:
                        involved.update(witnesses)
                    involved.discard(owner)
                    key = (event.event_id, owner)
                    conflict_ids = conflicts.get(key, ())
                    decision_ids = decisions.get(key, ())
                    memory = AutobiographicalMemory(
                        memory_id=f"autobio:{event.event_id}:{owner}:{rule.rule_id}",
                        owner_id=owner,
                        event_id=event.event_id,
                        tick=event.tick,
                        involved_npc_ids=tuple(sorted(involved)),
                        interpretation=rule.interpretation,
                        emotional_impact=rule.emotional_impact,
                        identity_impact=rule.identity_impact,
                        conflict_ids=tuple(conflict_ids),
                        learning_decision_ids=tuple(decision_ids),
                        turning_point=rule.turning_point,
                        tags=rule.tags,
                    )
                    formed.append(history.record(memory))
        return tuple(formed)
