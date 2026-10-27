"""Deterministic, value-relative appraisal of choices by individual NPCs.

Scores describe a modeled NPC's priorities and perceptions, not objective morality.
Missing dimensions contribute zero; no global good/bad label is assigned.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping


def _validate_axes(name: str, values: Mapping[str, float]) -> None:
    if not isinstance(values, Mapping):
        raise ValueError(f"{name} must be a mapping")
    for axis, value in values.items():
        if not isinstance(axis, str) or not axis.strip():
            raise ValueError(f"{name} axis names must be non-empty strings")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{name}[{axis!r}] must be numeric")
        if not math.isfinite(value) or not -1.0 <= value <= 1.0:
            raise ValueError(f"{name}[{axis!r}] must be finite and in [-1, 1]")


@dataclass(frozen=True)
class NPCValueProfile:
    """An NPC's stable value priorities and learned bias sensitivities.

    Positive and negative weights are both valid: the same perceived impact can
    be attractive to one NPC and aversive to another.
    """

    npc_id: str
    value_weights: Mapping[str, float]
    bias_weights: Mapping[str, float] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.npc_id, str) or not self.npc_id.strip():
            raise ValueError("npc_id must be a non-empty string")
        _validate_axes("value_weights", self.value_weights)
        _validate_axes("bias_weights", self.bias_weights or {})


@dataclass(frozen=True)
class ChoiceOption:
    """Caller-supplied predicted impacts and cues for one possible choice."""

    choice_id: str
    impacts: Mapping[str, float]
    bias_cues: Mapping[str, float] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.choice_id, str) or not self.choice_id.strip():
            raise ValueError("choice_id must be a non-empty string")
        _validate_axes("impacts", self.impacts)
        _validate_axes("bias_cues", self.bias_cues or {})


@dataclass(frozen=True)
class AppraisalResult:
    choice_id: str
    score: float
    value_contributions: tuple[tuple[str, float], ...]
    bias_contributions: tuple[tuple[str, float], ...]


class NPCAppraiser:
    """Ranks options with a transparent, deterministic weighted appraisal."""

    @staticmethod
    def appraise(profile: NPCValueProfile, option: ChoiceOption) -> AppraisalResult:
        value_contributions = tuple(
            (axis, profile.value_weights[axis] * option.impacts.get(axis, 0.0))
            for axis in sorted(profile.value_weights)
        )
        bias_weights = profile.bias_weights or {}
        cues = option.bias_cues or {}
        bias_contributions = tuple(
            (cue, bias_weights[cue] * cues.get(cue, 0.0))
            for cue in sorted(bias_weights)
        )
        score = sum(value for _, value in value_contributions) + sum(
            value for _, value in bias_contributions
        )
        return AppraisalResult(
            choice_id=option.choice_id,
            score=score,
            value_contributions=value_contributions,
            bias_contributions=bias_contributions,
        )

    @classmethod
    def rank(
        cls, profile: NPCValueProfile, options: tuple[ChoiceOption, ...] | list[ChoiceOption]
    ) -> tuple[AppraisalResult, ...]:
        """Return highest score first; ties are resolved by choice ID."""
        seen: set[str] = set()
        results = []
        for option in options:
            if option.choice_id in seen:
                raise ValueError(f"duplicate choice_id: {option.choice_id}")
            seen.add(option.choice_id)
            results.append(cls.appraise(profile, option))
        return tuple(sorted(results, key=lambda result: (-result.score, result.choice_id)))
