"""Personality-conditioned appraisal of cue-triggered emotional memories.

This read-only bridge lets stable identity traits amplify or attenuate a
memory-triggered emotion through explicit authored rules. It never changes
personality, memories, or the emotional event ledger.
"""
from __future__ import annotations
from dataclasses import dataclass
import math
from typing import Iterable
from .emotional_memory import EmotionalMemoryResponse
from .identity_evolution import NPCIdentityProfile

def _name(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value.strip()

def _number(value, label, low, high):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or not low <= value <= high):
        raise ValueError(f"{label} must be finite and in [{low}, {high}]")
    return float(value)

@dataclass(frozen=True)
class PersonalityEmotionRule:
    personality_axis: str
    emotion_axis: str
    coefficient: float
    def __post_init__(self):
        object.__setattr__(self, "personality_axis", _name(self.personality_axis, "personality_axis"))
        object.__setattr__(self, "emotion_axis", _name(self.emotion_axis, "emotion_axis"))
        object.__setattr__(self, "coefficient", _number(self.coefficient, "coefficient", -1.0, 1.0))

@dataclass(frozen=True)
class PersonalityEmotionContribution:
    association_id: str
    memory_id: str
    emotion_axis: str
    base_intensity: float
    personality_axis: str
    trait_value: float
    sensitivity: float
    coefficient: float
    modifier: float
    adjusted_intensity: float
    def __post_init__(self):
        for field in ("association_id", "memory_id", "emotion_axis", "personality_axis"):
            _name(getattr(self, field), field)
        _number(self.base_intensity, "base_intensity", 0.0, 1.0)
        _number(self.trait_value, "trait_value", -1.0, 1.0)
        _number(self.sensitivity, "sensitivity", 0.0, 2.0)
        _number(self.coefficient, "coefficient", -1.0, 1.0)
        _number(self.modifier, "modifier", -1.0, 1.0)
        _number(self.adjusted_intensity, "adjusted_intensity", 0.0, 1.0)

@dataclass(frozen=True)
class PersonalityConditionedEmotion:
    owner_id: str
    sampled_tick: int
    intensities: tuple[tuple[str, float], ...]
    contributions: tuple[PersonalityEmotionContribution, ...]
    source_response: EmotionalMemoryResponse
    def __post_init__(self):
        _name(self.owner_id, "owner_id")
        if isinstance(self.sampled_tick, bool) or not isinstance(self.sampled_tick, int) or self.sampled_tick < 0:
            raise ValueError("sampled_tick must be a non-negative integer")
        axes = [axis for axis, _ in self.intensities]
        if axes != sorted(set(axes)):
            raise ValueError("emotion axes must be unique and sorted")
        for axis, value in self.intensities:
            _name(axis, "emotion axis")
            _number(value, "emotion intensity", 0.0, 1.0)
        if any(not isinstance(x, PersonalityEmotionContribution) for x in self.contributions):
            raise TypeError("invalid personality emotion contribution")
        keys = [(x.association_id, x.memory_id, x.emotion_axis, x.personality_axis) for x in self.contributions]
        if keys != sorted(keys) or len(keys) != len(set(keys)):
            raise ValueError("contributions must be uniquely sorted")
        if (not isinstance(self.source_response, EmotionalMemoryResponse)
                or self.source_response.owner_id != self.owner_id
                or self.source_response.sampled_tick != self.sampled_tick):
            raise ValueError("source response owner and tick must match")

class PersonalityEmotionAdapter:
    """Apply explicit personality modifiers to one NPC's recalled emotion response."""
    @staticmethod
    def assess(response: EmotionalMemoryResponse, profile: NPCIdentityProfile,
               rules: Iterable[PersonalityEmotionRule]) -> PersonalityConditionedEmotion:
        if not isinstance(response, EmotionalMemoryResponse):
            raise TypeError("response must be an EmotionalMemoryResponse")
        if not isinstance(profile, NPCIdentityProfile):
            raise TypeError("profile must be an NPCIdentityProfile")
        if response.owner_id != profile.npc_id:
            raise ValueError("personality profile owner must match emotional response owner")
        items = tuple(rules)
        if any(not isinstance(rule, PersonalityEmotionRule) for rule in items):
            raise TypeError("rules must contain PersonalityEmotionRule values")
        keys = [(rule.personality_axis, rule.emotion_axis) for rule in items]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate personality/emotion rule")
        by_emotion = {}
        for rule in sorted(items, key=lambda x: (x.emotion_axis, x.personality_axis)):
            by_emotion.setdefault(rule.emotion_axis, []).append(rule)
        contributions, totals = [], {}
        for source in response.contributions:
            matching = by_emotion.get(source.emotion_axis, ())
            if not matching:
                totals[source.emotion_axis] = totals.get(source.emotion_axis, 0.0) + source.intensity
                continue
            for rule in matching:
                trait = profile.traits.get(rule.personality_axis, 0.0)
                sensitivity = (profile.sensitivities or {}).get(rule.personality_axis, 1.0)
                modifier = max(-1.0, min(1.0, trait * rule.coefficient * sensitivity))
                adjusted = max(0.0, min(1.0, source.intensity * (1.0 + modifier)))
                contributions.append(PersonalityEmotionContribution(
                    source.association_id, source.memory_id, source.emotion_axis,
                    source.intensity, rule.personality_axis, trait, sensitivity,
                    rule.coefficient, modifier, adjusted))
                totals[source.emotion_axis] = totals.get(source.emotion_axis, 0.0) + adjusted
        contributions.sort(key=lambda x: (x.association_id, x.memory_id, x.emotion_axis, x.personality_axis))
        return PersonalityConditionedEmotion(
            response.owner_id, response.sampled_tick,
            tuple(sorted((axis, min(1.0, value)) for axis, value in totals.items())),
            tuple(contributions), response)
