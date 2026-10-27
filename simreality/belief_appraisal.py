"""Belief-aware choice appraisal that keeps evidence effects explicit.

Beliefs influence a choice only when a caller supplies a claim-to-axis mapping.
The layer is deterministic and read-only; it does not infer consequences or truth.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping

from .appraisal import AppraisalResult, ChoiceOption, NPCAppraiser, NPCValueProfile
from .beliefs import BeliefLedger


def _validate_effects(name: str, effects: Mapping[str, Mapping[str, float]]) -> None:
    if not isinstance(effects, Mapping):
        raise ValueError(f"{name} must be a mapping")
    for claim_id, axes in effects.items():
        if not isinstance(claim_id, str) or not claim_id.strip():
            raise ValueError(f"{name} claim IDs must be non-empty strings")
        if not isinstance(axes, Mapping):
            raise ValueError(f"{name}[{claim_id!r}] must be a mapping")
        for axis, coefficient in axes.items():
            if not isinstance(axis, str) or not axis.strip():
                raise ValueError(f"{name} axis names must be non-empty strings")
            if isinstance(coefficient, bool) or not isinstance(coefficient, (int, float)):
                raise ValueError(f"{name}[{claim_id!r}][{axis!r}] must be numeric")
            if not math.isfinite(coefficient) or not -1.0 <= coefficient <= 1.0:
                raise ValueError(
                    f"{name}[{claim_id!r}][{axis!r}] must be finite and in [-1, 1]"
                )


@dataclass(frozen=True)
class BeliefAwareResult:
    """Appraisal plus inspectable adjustments contributed by explicit beliefs."""

    appraisal: AppraisalResult
    belief_value_contributions: tuple[tuple[str, str, float], ...]
    belief_bias_contributions: tuple[tuple[str, str, float], ...]

    @property
    def choice_id(self) -> str:
        return self.appraisal.choice_id

    @property
    def score(self) -> float:
        return self.appraisal.score


class BeliefAwareAppraiser:
    """Apply caller-mapped beliefs to impacts/cues, then use the standard appraiser.

    For each claim, confidence is centered around 0.5 and scaled to [-1, 1].
    A coefficient contributes coefficient * (2 * confidence - 1) to its axis.
    Thus unknown confidence (0.5) contributes zero; confidence 1 or 0 contributes
    the coefficient or its inverse. The caller defines what each claim means.
    """

    @staticmethod
    def appraise(
        profile: NPCValueProfile,
        option: ChoiceOption,
        beliefs: BeliefLedger,
        *,
        value_effects: Mapping[str, Mapping[str, float]] | None = None,
        bias_effects: Mapping[str, Mapping[str, float]] | None = None,
    ) -> BeliefAwareResult:
        value_effects = value_effects or {}
        bias_effects = bias_effects or {}
        _validate_effects("value_effects", value_effects)
        _validate_effects("bias_effects", bias_effects)

        value_adjustments: list[tuple[str, str, float]] = []
        bias_adjustments: list[tuple[str, str, float]] = []
        impacts = dict(option.impacts)
        cues = dict(option.bias_cues or {})

        for claim_id in sorted(value_effects):
            confidence = beliefs.get(claim_id).confidence
            signed_confidence = 2.0 * confidence - 1.0
            for axis in sorted(value_effects[claim_id]):
                adjustment = value_effects[claim_id][axis] * signed_confidence
                impacts[axis] = impacts.get(axis, 0.0) + adjustment
                value_adjustments.append((claim_id, axis, adjustment))

        for claim_id in sorted(bias_effects):
            confidence = beliefs.get(claim_id).confidence
            signed_confidence = 2.0 * confidence - 1.0
            for cue in sorted(bias_effects[claim_id]):
                adjustment = bias_effects[claim_id][cue] * signed_confidence
                cues[cue] = cues.get(cue, 0.0) + adjustment
                bias_adjustments.append((claim_id, cue, adjustment))

        adjusted_option = ChoiceOption(option.choice_id, impacts, cues)
        result = NPCAppraiser.appraise(profile, adjusted_option)
        return BeliefAwareResult(
            appraisal=result,
            belief_value_contributions=tuple(value_adjustments),
            belief_bias_contributions=tuple(bias_adjustments),
        )

    @classmethod
    def rank(
        cls,
        profile: NPCValueProfile,
        options: tuple[ChoiceOption, ...] | list[ChoiceOption],
        beliefs: BeliefLedger,
        *,
        value_effects: Mapping[str, Mapping[str, float]] | None = None,
        bias_effects: Mapping[str, Mapping[str, float]] | None = None,
    ) -> tuple[BeliefAwareResult, ...]:
        seen: set[str] = set()
        results = []
        for option in options:
            if option.choice_id in seen:
                raise ValueError(f"duplicate choice_id: {option.choice_id}")
            seen.add(option.choice_id)
            results.append(cls.appraise(
                profile, option, beliefs,
                value_effects=value_effects, bias_effects=bias_effects,
            ))
        return tuple(sorted(results, key=lambda result: (-result.score, result.choice_id)))
