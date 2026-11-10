"""Gradual, memory-grounded personality adaptation proposals.

Repeated autobiographical experiences can exert small, cumulative pressure on
explicitly authored personality axes. This adapter never changes traits itself:
proposals must be accepted or rejected through IdentityDecisionLedger.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Mapping

from .identity_evolution import IdentityChangeProposal, NPCIdentityProfile
from .npc_life_history import NPCLifeHistory


@dataclass(frozen=True)
class PersonalityAdaptationRule:
    rule_id: str
    memory_tag: str
    personality_axis: str
    coefficient: float
    minimum_memories: int = 2
    minimum_evidence: float = 0.0
    half_life_ticks: float = 1000.0
    maximum_delta: float = 0.02

    def __post_init__(self):
        for name in ("rule_id", "memory_tag", "personality_axis"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if (isinstance(self.coefficient, bool) or not isinstance(self.coefficient, (int, float))
                or not math.isfinite(self.coefficient) or not -1.0 <= self.coefficient <= 1.0):
            raise ValueError("coefficient must be finite and in [-1, 1]")
        if (isinstance(self.minimum_memories, bool) or not isinstance(self.minimum_memories, int)
                or self.minimum_memories < 1):
            raise ValueError("minimum_memories must be a positive integer")
        if (isinstance(self.minimum_evidence, bool)
                or not isinstance(self.minimum_evidence, (int, float))
                or not math.isfinite(self.minimum_evidence)
                or not 0.0 <= self.minimum_evidence <= 1.0):
            raise ValueError("minimum_evidence must be finite and in [0, 1]")
        if (isinstance(self.half_life_ticks, bool)
                or not isinstance(self.half_life_ticks, (int, float))
                or not math.isfinite(self.half_life_ticks) or self.half_life_ticks <= 0):
            raise ValueError("half_life_ticks must be positive and finite")
        if (isinstance(self.maximum_delta, bool)
                or not isinstance(self.maximum_delta, (int, float))
                or not math.isfinite(self.maximum_delta)
                or not 0.0 < self.maximum_delta <= 0.1):
            raise ValueError("maximum_delta must be in (0, 0.1]")


@dataclass(frozen=True)
class PersonalityMemoryContribution:
    memory_id: str
    event_id: str
    tick: int
    identity_impact: float
    salience: float
    weighted_impact: float


@dataclass(frozen=True)
class PersonalityAdaptationAssessment:
    npc_id: str
    rule_id: str
    axis: str
    contributions: tuple[PersonalityMemoryContribution, ...]
    accumulated_evidence: float
    proposal: IdentityChangeProposal


class PersonalityAdaptationAdapter:
    """Convert repeated owner-specific memories into bounded trait proposals."""

    @staticmethod
    def propose(
        history: NPCLifeHistory,
        profiles: Iterable[NPCIdentityProfile],
        rules: Iterable[PersonalityAdaptationRule],
        *,
        current_tick: int,
        role_by_npc: Mapping[str, str],
    ) -> tuple[PersonalityAdaptationAssessment, ...]:
        if not isinstance(history, NPCLifeHistory):
            raise TypeError("history must be an NPCLifeHistory")
        if isinstance(current_tick, bool) or not isinstance(current_tick, int) or current_tick < 0:
            raise ValueError("current_tick must be a non-negative integer")
        if not isinstance(role_by_npc, Mapping):
            raise TypeError("role_by_npc must map NPC IDs to participant/witness roles")
        profile_items = tuple(profiles)
        rule_items = tuple(rules)
        if any(not isinstance(x, NPCIdentityProfile) for x in profile_items):
            raise TypeError("profiles must contain NPCIdentityProfile values")
        if any(not isinstance(x, PersonalityAdaptationRule) for x in rule_items):
            raise TypeError("rules must contain PersonalityAdaptationRule values")
        profile_map = {x.npc_id: x for x in profile_items}
        if len(profile_map) != len(profile_items):
            raise ValueError("duplicate NPC identity profiles")
        if len({x.rule_id for x in rule_items}) != len(rule_items):
            raise ValueError("personality adaptation rule IDs must be unique")
        for npc_id, role in role_by_npc.items():
            if not isinstance(npc_id, str) or not npc_id.strip() or role not in ("participant", "witness"):
                raise ValueError("roles must be participant or witness for non-empty NPC IDs")

        results = []
        memories_by_owner = {
            npc_id: history.memories(npc_id) for npc_id in sorted(profile_map)
        }
        for npc_id, profile in sorted(profile_map.items()):
            memories = memories_by_owner[npc_id]
            for rule in sorted(rule_items, key=lambda x: x.rule_id):
                if rule.personality_axis not in profile.traits:
                    continue
                matching = [memory for memory in memories if rule.memory_tag in memory.tags]
                if len(matching) < rule.minimum_memories:
                    continue
                contributions = []
                for memory in matching:
                    if memory.tick > current_tick:
                        raise ValueError("personality adaptation cannot use a future memory")
                    salience = history.recall_salience(
                        memory.memory_id, current_tick,
                        half_life_ticks=rule.half_life_ticks,
                    )
                    weighted = memory.identity_impact * salience
                    contributions.append(PersonalityMemoryContribution(
                        memory.memory_id, memory.event_id, memory.tick,
                        memory.identity_impact, salience, weighted,
                    ))
                contributions.sort(key=lambda x: (x.tick, x.memory_id))
                signed_evidence = sum(x.weighted_impact for x in contributions)
                accumulated = min(1.0, sum(abs(x.weighted_impact) for x in contributions))
                if accumulated < rule.minimum_evidence:
                    continue
                raw_delta = rule.coefficient * signed_evidence
                delta = max(-rule.maximum_delta, min(rule.maximum_delta, raw_delta))
                before = profile.traits[rule.personality_axis]
                after = max(-1.0, min(1.0, before + delta))
                if math.isclose(after, before, abs_tol=1e-15):
                    continue
                latest = contributions[-1]
                role = role_by_npc.get(npc_id)
                if role not in ("participant", "witness"):
                    raise ValueError(f"missing participant/witness role for {npc_id}")
                proposal = IdentityChangeProposal(
                    latest.event_id, npc_id, rule.rule_id, rule.personality_axis,
                    before, after, after - before, accumulated, role,
                    rule.maximum_delta,
                )
                results.append(PersonalityAdaptationAssessment(
                    npc_id, rule.rule_id, rule.personality_axis,
                    tuple(contributions), accumulated, proposal,
                ))
        return tuple(sorted(results, key=lambda x: (x.npc_id, x.axis, x.rule_id)))
