"""Separate felt emotion, outward expression, and decision influence.

This module is a read-only projection over the emotional ledger. Suppression
changes what an NPC displays, never the underlying felt state. Decision effects
are explicit policy coefficients and never select or execute an action.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping

from .identity_context import NPCEmotionalState


def _axis_map(values: Mapping[str, float], name: str, low: float, high: float) -> tuple[tuple[str, float], ...]:
    if not isinstance(values, Mapping):
        raise TypeError(f"{name} must be a mapping")
    result = []
    for axis, value in values.items():
        if not isinstance(axis, str) or not axis.strip():
            raise ValueError(f"{name} axes must be non-empty strings")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError(f"{name} values must be finite and in [{low}, {high}]")
        result.append((axis, float(value)))
    return tuple(sorted(result))


@dataclass(frozen=True)
class EmotionalRegulationProfile:
    """Owner-specific suppression and expression capacity for each emotion axis.

    suppression=1 hides the emotion completely; suppression=0 expresses the
    full felt intensity. Unlisted axes use zero suppression.
    """

    owner_id: str
    suppression: Mapping[str, float]

    def __post_init__(self):
        if not isinstance(self.owner_id, str) or not self.owner_id.strip():
            raise ValueError("owner_id must be a non-empty string")
        object.__setattr__(self, "suppression", dict(_axis_map(self.suppression, "suppression", 0.0, 1.0)))

    def suppression_for(self, axis: str) -> float:
        return self.suppression.get(axis, 0.0)


@dataclass(frozen=True)
class EmotionalExpression:
    owner_id: str
    sampled_tick: int
    felt: tuple[tuple[str, float], ...]
    displayed: tuple[tuple[str, float], ...]
    concealed: tuple[tuple[str, float], ...]

    def felt_for(self, axis: str) -> float:
        return dict(self.felt).get(axis, 0.0)

    def displayed_for(self, axis: str) -> float:
        return dict(self.displayed).get(axis, 0.0)

    def concealed_for(self, axis: str) -> float:
        return dict(self.concealed).get(axis, 0.0)


class EmotionalExpressionAdapter:
    """Project felt emotion into visible expression without mutating emotion."""

    @staticmethod
    def project(state: NPCEmotionalState, profile: EmotionalRegulationProfile) -> EmotionalExpression:
        if not isinstance(state, NPCEmotionalState):
            raise TypeError("state must be an NPCEmotionalState")
        if not isinstance(profile, EmotionalRegulationProfile):
            raise TypeError("profile must be an EmotionalRegulationProfile")
        if state.npc_id != profile.owner_id:
            raise ValueError("regulation profile owner must match emotional state owner")
        felt = dict(state.intensities)
        axes = sorted(set(felt) | set(profile.suppression))
        displayed = {}
        concealed = {}
        for axis in axes:
            intensity = felt.get(axis, 0.0)
            shown = intensity * (1.0 - profile.suppression_for(axis))
            displayed[axis] = shown
            concealed[axis] = intensity - shown
        return EmotionalExpression(
            state.npc_id, state.sampled_tick,
            tuple(sorted(felt.items())), tuple(sorted(displayed.items())),
            tuple(sorted(concealed.items())),
        )


@dataclass(frozen=True)
class EmotionalDecisionRule:
    """Explicit signed influence of one emotion on one decision consideration."""

    consideration: str
    emotion_axis: str
    coefficient: float

    def __post_init__(self):
        for name in ("consideration", "emotion_axis"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if isinstance(self.coefficient, bool) or not isinstance(self.coefficient, (int, float)) or not math.isfinite(self.coefficient) or not -1.0 <= self.coefficient <= 1.0:
            raise ValueError("coefficient must be finite and in [-1, 1]")


@dataclass(frozen=True)
class EmotionalDecisionInfluence:
    owner_id: str
    sampled_tick: int
    consideration: str
    baseline: float
    emotional_delta: float
    adjusted_score: float
    contributions: tuple[tuple[str, float], ...]


class EmotionalDecisionAdapter:
    """Calculate transparent emotion contributions; never choose an action."""

    @staticmethod
    def assess(
        state: NPCEmotionalState,
        consideration: str,
        *,
        baseline: float,
        rules: tuple[EmotionalDecisionRule, ...],
    ) -> EmotionalDecisionInfluence:
        if not isinstance(state, NPCEmotionalState):
            raise TypeError("state must be an NPCEmotionalState")
        if not isinstance(consideration, str) or not consideration.strip():
            raise ValueError("consideration must be a non-empty string")
        if isinstance(baseline, bool) or not isinstance(baseline, (int, float)) or not math.isfinite(baseline) or not -1.0 <= baseline <= 1.0:
            raise ValueError("baseline must be finite and in [-1, 1]")
        if not isinstance(rules, tuple) or any(not isinstance(rule, EmotionalDecisionRule) for rule in rules):
            raise TypeError("rules must be a tuple of EmotionalDecisionRule values")
        matching = [rule for rule in rules if rule.consideration == consideration]
        if len({rule.emotion_axis for rule in matching}) != len(matching):
            raise ValueError("decision rules must have unique emotion axes per consideration")
        intensities = dict(state.intensities)
        contributions = tuple(sorted(
            (rule.emotion_axis, intensities.get(rule.emotion_axis, 0.0) * rule.coefficient)
            for rule in matching
        ))
        delta = sum(value for _, value in contributions)
        return EmotionalDecisionInfluence(
            state.npc_id, state.sampled_tick, consideration, float(baseline),
            delta, max(-1.0, min(1.0, float(baseline) + delta)), contributions,
        )
