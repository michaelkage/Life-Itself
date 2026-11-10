"""Personality-conditioned appraisal of memory-triggered emotions.

This bridge lets stable identity traits modulate the intensity of an emotion
already activated by an observed autobiographical cue. It is an explicit,
read-only appraisal: it does not create memories, infer cues, mutate emotion
state, or select behavior.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

from .emotional_memory import EmotionalMemoryContribution, EmotionalMemoryResponse
from .identity_evolution import NPCIdentityProfile


def _name(field: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _finite(field: str, value: float, low: float, high: float) -> float:
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or not low <= value <= high):
        raise ValueError(f"{field} must be finite and in [{low}, {high}]")
    return float(value)


@dataclass(frozen=True)
class PersonalityEmotionRule:
    """Map one stable personality trait to the gain of one emotion axis."""
    rule_id: str
    emotion_axis: str
    trait_axis: str
    coefficient: float

    def __post_init__(self):
        for field in ("rule_id", "emotion_axis", "trait_axis"):
            object.__setattr__(self, field, _name(field, getattr(self, field)))
        object.__setattr__(self, "coefficient", _finite("coefficient", self.coefficient, -1.0, 1.0))


@dataclass(frozen=True)
class PersonalityEmotionContribution:
    source: EmotionalMemoryContribution
    rule_id: str | None
    trait_axis: str | None
    trait_value: float | None
    multiplier: float
    adjusted_intensity: float

    def __post_init__(self):
        if not isinstance(self.source, EmotionalMemoryContribution):
            raise TypeError("source must be an EmotionalMemoryContribution")
        if self.rule_id is None:
            if self.trait_axis is not None or self.trait_value is not None:
                raise ValueError("unmodified contributions cannot contain trait provenance")
        else:
            _name("rule_id", self.rule_id)
            _name("trait_axis", self.trait_axis)
            object.__setattr__(self, "trait_value", _finite("trait_value", self.trait_value, -1.0, 1.0))
        object.__setattr__(self, "multiplier", _finite("multiplier", self.multiplier, 0.0, 2.0))
        object.__setattr__(self, "adjusted_intensity", _finite("adjusted_intensity", self.adjusted_intensity, 0.0, 1.0))


@dataclass(frozen=True)
class PersonalityEmotionAppraisal:
    owner_id: str
    sampled_tick: int
    intensities: tuple[tuple[str, float], ...]
    contributions: tuple[PersonalityEmotionContribution, ...]

    def __post_init__(self):
        _name("owner_id", self.owner_id)
        if isinstance(self.sampled_tick, bool) or not isinstance(self.sampled_tick, int) or self.sampled_tick < 0:
            raise ValueError("sampled_tick must be a non-negative integer")
        axes = [axis for axis, _ in self.intensities]
        if axes != sorted(set(axes)):
            raise ValueError("emotion axes must be unique and sorted")
        for axis, value in self.intensities:
            _name("emotion axis", axis)
            _finite("emotion intensity", value, 0.0, 1.0)
        if not isinstance(self.contributions, tuple) or any(not isinstance(x, PersonalityEmotionContribution) for x in self.contributions):
            raise TypeError("contributions must contain PersonalityEmotionContribution values")
        keys = [(x.source.association_id, x.source.memory_id, x.source.cue_id, x.source.emotion_axis) for x in self.contributions]
        if keys != sorted(keys) or len(keys) != len(set(keys)):
            raise ValueError("contributions must be uniquely sorted")


class PersonalityEmotionAdapter:
    """Apply authored personality gains to a memory-triggered response."""

    @staticmethod
    def evaluate(response: EmotionalMemoryResponse, identity: NPCIdentityProfile, rules):
        if not isinstance(response, EmotionalMemoryResponse):
            raise TypeError("response must be an EmotionalMemoryResponse")
        if not isinstance(identity, NPCIdentityProfile):
            raise TypeError("identity must be an NPCIdentityProfile")
        if response.owner_id != identity.npc_id:
            raise ValueError("identity profile owner must match emotional response owner")
        rules = tuple(rules)
        if any(not isinstance(rule, PersonalityEmotionRule) for rule in rules):
            raise TypeError("rules must contain PersonalityEmotionRule values")
        if len({r.rule_id for r in rules}) != len(rules):
            raise ValueError("personality emotion rule IDs must be unique")
        if len({r.emotion_axis for r in rules}) != len(rules):
            raise ValueError("only one personality rule may target each emotion axis")
        by_axis = {r.emotion_axis: r for r in rules}
        contributions, totals = [], {}
        for source in response.contributions:
            rule = by_axis.get(source.emotion_axis)
            if rule is None:
                multiplier, rule_id, trait_axis, trait_value = 1.0, None, None, None
            else:
                if rule.trait_axis not in identity.traits:
                    raise KeyError(f"identity profile {identity.npc_id} has no trait axis {rule.trait_axis}")
                trait_value = float(identity.traits[rule.trait_axis])
                multiplier = 1.0 + trait_value * rule.coefficient
                rule_id, trait_axis = rule.rule_id, rule.trait_axis
            adjusted = min(1.0, source.intensity * multiplier)
            contributions.append(PersonalityEmotionContribution(source, rule_id, trait_axis, trait_value, multiplier, adjusted))
            totals[source.emotion_axis] = totals.get(source.emotion_axis, 0.0) + adjusted
        contributions.sort(key=lambda x: (x.source.association_id, x.source.memory_id, x.source.cue_id, x.source.emotion_axis))
        return PersonalityEmotionAppraisal(response.owner_id, response.sampled_tick,
            tuple(sorted((axis, min(1.0, value)) for axis, value in totals.items())), tuple(contributions))
