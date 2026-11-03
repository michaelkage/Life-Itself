"""Explicit cognitive-bias and temporary-emotion context for NPC interpretation.

These are appraisal inputs, not personality mutations. Emotion snapshots are
sampled at a simulation tick and must be refreshed by the caller as the
character's state changes. Bias strengths are persistent profile inputs; the
emotional snapshot is transient state.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from types import MappingProxyType
from typing import Iterable, Mapping

from .identity_interpretation import InterpretedIdentityChange, IdentityBeliefInterpreter
from .identity_evolution import IdentityChangeProposal


def _bounded_axes(npc_id: str, axes: Mapping[str, float], low: float, high: float, label: str):
    if not isinstance(npc_id, str) or not npc_id.strip():
        raise ValueError("npc_id must be a non-empty string")
    if not isinstance(axes, Mapping):
        raise TypeError(f"{label} axes must be a mapping")
    copied = dict(axes)
    for axis, value in copied.items():
        if not isinstance(axis, str) or not axis.strip():
            raise ValueError(f"{label} axis names must be non-empty strings")
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or not low <= value <= high):
            raise ValueError(f"{label} axis values must be finite and in [{low}, {high}]")
    return MappingProxyType(copied)


@dataclass(frozen=True)
class NPCCognitiveBiasProfile:
    """Individual bias tendencies, normalized to [0, 1], not moral traits."""
    npc_id: str
    strengths: Mapping[str, float]

    def __post_init__(self):
        object.__setattr__(self, "strengths",
                           _bounded_axes(self.npc_id, self.strengths, 0.0, 1.0, "bias"))


@dataclass(frozen=True)
class NPCEmotionalState:
    """A temporary emotional snapshot; refresh it as the simulation advances."""
    npc_id: str
    sampled_tick: int
    intensities: Mapping[str, float]

    def __post_init__(self):
        if (isinstance(self.sampled_tick, bool) or not isinstance(self.sampled_tick, int)
                or self.sampled_tick < 0):
            raise ValueError("sampled_tick must be a non-negative integer")
        object.__setattr__(self, "intensities",
                           _bounded_axes(self.npc_id, self.intensities, 0.0, 1.0, "emotion"))


@dataclass(frozen=True)
class IdentityCognitiveBiasRule:
    """Map a named cognitive bias to a policy-specific signed appraisal effect."""
    policy_id: str
    bias_axis: str
    coefficient: float

    def __post_init__(self):
        _validate_rule(self.policy_id, self.bias_axis, self.coefficient)


@dataclass(frozen=True)
class IdentityEmotionRule:
    """Map a temporary emotional intensity to a policy-specific appraisal effect."""
    policy_id: str
    emotion_axis: str
    coefficient: float

    def __post_init__(self):
        _validate_rule(self.policy_id, self.emotion_axis, self.coefficient)


def _validate_rule(policy_id: str, axis: str, coefficient: float):
    if not isinstance(policy_id, str) or not policy_id.strip():
        raise ValueError("policy_id must be a non-empty string")
    if not isinstance(axis, str) or not axis.strip():
        raise ValueError("axis must be a non-empty string")
    if (isinstance(coefficient, bool) or not isinstance(coefficient, (int, float))
            or not math.isfinite(coefficient) or not -1.0 <= coefficient <= 1.0):
        raise ValueError("coefficient must be finite and in [-1, 1]")


@dataclass(frozen=True)
class ContextualIdentityChange:
    """Base interpretation plus separately inspectable bias/emotion effects."""
    base: InterpretedIdentityChange
    interpreted: IdentityChangeProposal
    bias_contributions: tuple[tuple[str, float, float], ...]
    emotion_contributions: tuple[tuple[str, float, float], ...]
    emotional_sample_tick: int | None


class IdentityCognitiveContextInterpreter:
    """Add explicit bias and transient emotion to a read-only appraisal.

    Inputs are deterministic snapshots. No profile, emotional state, identity
    trait, or decision ledger is mutated. Combined effects retain the original
    proposal's maximum-delta and [-1, 1] trait bounds.
    """

    def __init__(self, base_interpreter: IdentityBeliefInterpreter):
        if not isinstance(base_interpreter, IdentityBeliefInterpreter):
            raise TypeError("base_interpreter must be an IdentityBeliefInterpreter")
        self.base_interpreter = base_interpreter

    def interpret(
        self,
        proposals: Iterable[IdentityChangeProposal],
        *,
        biases_by_npc: Mapping[str, NPCCognitiveBiasProfile] | None = None,
        bias_rules: Iterable[IdentityCognitiveBiasRule] = (),
        emotions_by_npc: Mapping[str, NPCEmotionalState] | None = None,
        emotion_rules: Iterable[IdentityEmotionRule] = (),
        current_tick: int | None = None,
        max_emotion_age_ticks: int | None = None,
        beliefs_by_npc=None,
        npcs_by_id=None,
        memory_associations=(),
        trust=None,
        relationship_associations=(),
        personalities_by_npc=None,
        personality_rules=(),
        values_by_npc=None,
        value_rules=(),
    ) -> tuple[ContextualIdentityChange, ...]:
        proposals = tuple(proposals)
        base_results = self.base_interpreter.interpret_comprehensively(
            proposals,
            beliefs_by_npc=beliefs_by_npc,
            npcs_by_id=npcs_by_id,
            memory_associations=memory_associations,
            trust=trust,
            relationship_associations=relationship_associations,
            personalities_by_npc=personalities_by_npc,
            personality_rules=personality_rules,
            values_by_npc=values_by_npc,
            value_rules=value_rules,
        )
        bias_map = {} if biases_by_npc is None else biases_by_npc
        emotion_map = {} if emotions_by_npc is None else emotions_by_npc
        if not isinstance(bias_map, Mapping) or not isinstance(emotion_map, Mapping):
            raise TypeError("biases_by_npc and emotions_by_npc must be mappings")
        for npc_id, profile in bias_map.items():
            if not isinstance(profile, NPCCognitiveBiasProfile) or profile.npc_id != npc_id:
                raise ValueError("bias mapping keys must match NPCCognitiveBiasProfile.npc_id")
        for npc_id, state in emotion_map.items():
            if not isinstance(state, NPCEmotionalState) or state.npc_id != npc_id:
                raise ValueError("emotion mapping keys must match NPCEmotionalState.npc_id")
        if max_emotion_age_ticks is not None:
            if (isinstance(max_emotion_age_ticks, bool)
                    or not isinstance(max_emotion_age_ticks, int)
                    or max_emotion_age_ticks < 0):
                raise ValueError("max_emotion_age_ticks must be a non-negative integer")
            if current_tick is None or isinstance(current_tick, bool) or not isinstance(current_tick, int):
                raise ValueError("current_tick is required when max_emotion_age_ticks is set")
        if current_tick is not None and (
            isinstance(current_tick, bool) or not isinstance(current_tick, int) or current_tick < 0
        ):
            raise ValueError("current_tick must be a non-negative integer")

        bias_items = tuple(bias_rules)
        emotion_items = tuple(emotion_rules)
        if any(not isinstance(x, IdentityCognitiveBiasRule) for x in bias_items):
            raise TypeError("bias_rules must contain IdentityCognitiveBiasRule values")
        if any(not isinstance(x, IdentityEmotionRule) for x in emotion_items):
            raise TypeError("emotion_rules must contain IdentityEmotionRule values")
        bias_keys = [(x.policy_id, x.bias_axis) for x in bias_items]
        emotion_keys = [(x.policy_id, x.emotion_axis) for x in emotion_items]
        if len(bias_keys) != len(set(bias_keys)):
            raise ValueError("duplicate policy/bias-axis rule")
        if len(emotion_keys) != len(set(emotion_keys)):
            raise ValueError("duplicate policy/emotion-axis rule")
        bias_by_policy = {}
        emotion_by_policy = {}
        for rule in sorted(bias_items, key=lambda x: (x.policy_id, x.bias_axis)):
            bias_by_policy.setdefault(rule.policy_id, []).append(rule)
        for rule in sorted(emotion_items, key=lambda x: (x.policy_id, x.emotion_axis)):
            emotion_by_policy.setdefault(rule.policy_id, []).append(rule)

        results = []
        for base in base_results:
            proposal = base.interpreted
            adjustment = 0.0
            bias_contributions = []
            emotion_contributions = []
            bias_profile = bias_map.get(proposal.npc_id)
            for rule in bias_by_policy.get(proposal.policy_id, ()):
                strength = bias_profile.strengths.get(rule.bias_axis, 0.0) if bias_profile else 0.0
                contribution = strength * rule.coefficient
                adjustment += contribution
                bias_contributions.append((rule.bias_axis, strength, contribution))

            emotional_state = emotion_map.get(proposal.npc_id)
            sample_tick = emotional_state.sampled_tick if emotional_state else None
            if emotional_state is not None:
                if current_tick is not None and sample_tick > current_tick:
                    raise ValueError("emotional snapshot cannot come from a future tick")
                if (max_emotion_age_ticks is not None
                        and current_tick - sample_tick > max_emotion_age_ticks):
                    raise ValueError(f"stale emotional snapshot for {proposal.npc_id}")
            for rule in emotion_by_policy.get(proposal.policy_id, ()):
                intensity = emotional_state.intensities.get(rule.emotion_axis, 0.0) if emotional_state else 0.0
                contribution = intensity * rule.coefficient
                adjustment += contribution
                emotion_contributions.append((rule.emotion_axis, intensity, contribution))

            maximum = proposal.maximum_delta
            delta = max(-maximum, min(maximum, proposal.delta + adjustment))
            after = max(-1.0, min(1.0, proposal.before + delta))
            interpreted = IdentityChangeProposal(
                proposal.event_id, proposal.npc_id, proposal.policy_id, proposal.axis,
                proposal.before, after, after - proposal.before,
                proposal.evidence_strength, proposal.role, maximum,
            )
            results.append(ContextualIdentityChange(
                base, interpreted, tuple(bias_contributions),
                tuple(emotion_contributions), sample_tick,
            ))
        return tuple(results)
