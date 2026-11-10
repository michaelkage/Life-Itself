"""Integrated belief- and conditioning-aware NPC choice appraisal.

Combines an observer's current social beliefs, stable value/bias profile, and
owner-specific learned cue associations. The adapter is deterministic and
read-only; callers explicitly map claims and cues to candidate choices.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping

from .appraisal import ChoiceOption, NPCValueProfile
from .belief_appraisal import BeliefAwareResult
from .psychological_conditioning import NPCConditioningLedger
from .psychological_decisions import ConditionedDecisionProfile
from .social_beliefs import SocialBeliefSystem
from .social_decisions import SocialBeliefDecisionAdapter


@dataclass(frozen=True)
class IntegratedChoiceResult:
    choice_id: str
    belief_appraisal: BeliefAwareResult
    conditioned_contributions: tuple[tuple[str, float], ...]
    final_score: float


@dataclass(frozen=True)
class IntegratedDecisionResult:
    observer_id: str
    ranked: tuple[IntegratedChoiceResult, ...]

    @property
    def preferred(self) -> IntegratedChoiceResult | None:
        return self.ranked[0] if self.ranked else None


class IntegratedPsychologicalDecisionAdapter:
    """Rank choices using the same NPC's beliefs, values, biases, and learning."""

    @staticmethod
    def rank(
        observer_id: str,
        beliefs: SocialBeliefSystem,
        conditioning: NPCConditioningLedger,
        value_profile: NPCValueProfile,
        conditioning_profile: ConditionedDecisionProfile,
        options: tuple[ChoiceOption, ...] | list[ChoiceOption],
        *,
        cue_exposures: Mapping[str, Mapping[str, float]],
        value_effects: Mapping[str, Mapping[str, float]] | None = None,
        bias_effects: Mapping[str, Mapping[str, float]] | None = None,
    ) -> IntegratedDecisionResult:
        if not isinstance(observer_id, str) or not observer_id.strip():
            raise ValueError("observer_id must be a non-empty string")
        if not isinstance(conditioning, NPCConditioningLedger):
            raise TypeError("conditioning must be an NPCConditioningLedger")
        if not isinstance(conditioning_profile, ConditionedDecisionProfile) or conditioning_profile.owner_id != observer_id:
            raise ValueError("conditioning profile must belong to observer")
        if not isinstance(cue_exposures, Mapping):
            raise ValueError("cue_exposures must be a mapping")
        belief_results = SocialBeliefDecisionAdapter.rank(
            observer_id, beliefs, value_profile, options,
            value_effects=value_effects, bias_effects=bias_effects,
        )
        by_id = {result.choice_id: result for result in belief_results.ranked}
        if set(cue_exposures) - set(by_id):
            raise ValueError("cue exposure references an unknown choice")
        results = []
        for choice_id in sorted(by_id):
            exposures = cue_exposures.get(choice_id, {})
            if not isinstance(exposures, Mapping):
                raise ValueError("each choice exposure must be a cue mapping")
            contributions = []
            for cue, exposure in sorted(exposures.items()):
                if cue not in conditioning_profile.cue_sensitivities:
                    raise KeyError(f"no authored sensitivity for cue: {cue}")
                if isinstance(exposure, bool) or not isinstance(exposure, (int, float)) or not math.isfinite(exposure) or not 0 <= exposure <= 1:
                    raise ValueError("cue exposure must be finite and in [0, 1]")
                association = conditioning.association_for(observer_id, cue)
                contribution = association * exposure * conditioning_profile.cue_sensitivities[cue]
                contributions.append((cue, contribution))
            base = by_id[choice_id]
            total = base.score + sum(value for _, value in contributions)
            results.append(IntegratedChoiceResult(
                choice_id, base, tuple(contributions), total,
            ))
        return IntegratedDecisionResult(
            observer_id,
            tuple(sorted(results, key=lambda item: (-item.final_score, item.choice_id))),
        )
