"""Conditioning-aware NPC choice appraisal.

Learned associations contribute bounded, explicit consideration signals to
candidate choices. This is a read-only ranking adapter: it does not select or
execute an action, and callers define which cues each option may evoke.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping

from .appraisal import ChoiceOption, NPCValueProfile, NPCAppraiser
from .psychological_conditioning import NPCConditioningLedger


@dataclass(frozen=True)
class ConditionedDecisionProfile:
    owner_id: str
    cue_sensitivities: Mapping[str, float]

    def __post_init__(self):
        if not isinstance(self.owner_id, str) or not self.owner_id.strip():
            raise ValueError("owner_id must be a non-empty string")
        if not isinstance(self.cue_sensitivities, Mapping):
            raise ValueError("cue_sensitivities must be a mapping")
        for cue, value in self.cue_sensitivities.items():
            if not isinstance(cue, str) or not cue.strip():
                raise ValueError("cue names must be non-empty strings")
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not -1 <= value <= 1:
                raise ValueError("cue sensitivities must be finite and in [-1, 1]")


@dataclass(frozen=True)
class ConditionedChoiceResult:
    choice_id: str
    base_score: float
    conditioned_score: float
    conditioned_contributions: tuple[tuple[str, float], ...]


@dataclass(frozen=True)
class ConditionedDecisionResult:
    owner_id: str
    ranked: tuple[ConditionedChoiceResult, ...]

    @property
    def preferred(self) -> ConditionedChoiceResult | None:
        return self.ranked[0] if self.ranked else None


class PsychologicalDecisionAdapter:
    """Combine stable value appraisal with an NPC's learned cue associations."""

    @staticmethod
    def rank(
        owner_id: str,
        conditioning: NPCConditioningLedger,
        profile: NPCValueProfile,
        conditioning_profile: ConditionedDecisionProfile,
        options: tuple[ChoiceOption, ...] | list[ChoiceOption],
        *,
        cue_exposures: Mapping[str, Mapping[str, float]],
    ) -> ConditionedDecisionResult:
        if not isinstance(owner_id, str) or not owner_id.strip():
            raise ValueError("owner_id must be a non-empty string")
        if not isinstance(conditioning, NPCConditioningLedger):
            raise TypeError("conditioning must be an NPCConditioningLedger")
        if not isinstance(profile, NPCValueProfile) or profile.npc_id != owner_id:
            raise ValueError("value profile must belong to owner_id")
        if not isinstance(conditioning_profile, ConditionedDecisionProfile) or conditioning_profile.owner_id != owner_id:
            raise ValueError("conditioning profile must belong to owner_id")
        if not isinstance(cue_exposures, Mapping):
            raise ValueError("cue_exposures must be a mapping")
        base = {item.choice_id: item for item in NPCAppraiser.rank(profile, options)}
        option_ids = set(base)
        if set(cue_exposures) - option_ids:
            raise ValueError("cue exposure references an unknown choice")
        results = []
        for choice_id in sorted(base):
            exposures = cue_exposures.get(choice_id, {})
            if not isinstance(exposures, Mapping):
                raise ValueError("each choice exposure must be a cue mapping")
            contributions = []
            for cue, exposure in sorted(exposures.items()):
                if cue not in conditioning_profile.cue_sensitivities:
                    raise KeyError(f"no authored sensitivity for cue: {cue}")
                if isinstance(exposure, bool) or not isinstance(exposure, (int, float)) or not math.isfinite(exposure) or not 0 <= exposure <= 1:
                    raise ValueError("cue exposure must be finite and in [0, 1]")
                association = conditioning.association_for(owner_id, cue)
                contribution = association * exposure * conditioning_profile.cue_sensitivities[cue]
                contributions.append((cue, contribution))
            base_score = base[choice_id].score
            total = sum(value for _, value in contributions)
            results.append(ConditionedChoiceResult(
                choice_id, base_score, base_score + total, tuple(contributions)
            ))
        ranked = tuple(sorted(results, key=lambda item: (-item.conditioned_score, item.choice_id)))
        return ConditionedDecisionResult(owner_id, ranked)
