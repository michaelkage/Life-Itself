"""Individualized, read-only behavioral adaptations to accumulated stress.

The adapter translates an NPC's explicit stress assessment into bounded
consideration modifiers. It does not alter routines, choose actions, or mutate
the stress ledger. Higher-level decision systems decide whether and how to use
the returned signals.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping

from .emotional_stress import CopingProfile, NPCStressLedger, StressAssessment


CHANNELS = (
    "social_engagement",
    "work_performance",
    "sleep_priority",
    "risk_tolerance",
    "routine_flexibility",
    "conflict_sensitivity",
)


def _finite(value: float, name: str, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{name} must be finite and in [{low}, {high}]")
    return float(value)


@dataclass(frozen=True)
class StressAdaptationProfile:
    """NPC-specific response coefficients for stress and exhaustion.

    Coefficients describe changes to decision considerations, not direct
    behavioral commands. Positive and negative values are both meaningful:
    pressure may increase or decrease a consideration depending on the NPC.
    """

    owner_id: str
    stress_sensitivity: Mapping[str, float]
    exhaustion_sensitivity: Mapping[str, float]

    def __post_init__(self):
        if not isinstance(self.owner_id, str) or not self.owner_id.strip():
            raise ValueError("owner_id must be a non-empty string")
        for name in ("stress_sensitivity", "exhaustion_sensitivity"):
            values = getattr(self, name)
            if not isinstance(values, Mapping):
                raise TypeError(f"{name} must be a mapping")
            normalized = {}
            for channel, coefficient in values.items():
                if channel not in CHANNELS:
                    raise ValueError(f"unknown stress adaptation channel: {channel}")
                normalized[channel] = _finite(coefficient, channel, -1.0, 1.0)
            object.__setattr__(self, name, dict(sorted(normalized.items())))


@dataclass(frozen=True)
class StressBehaviorSignal:
    owner_id: str
    sampled_tick: int
    stress: float
    exhaustion: float
    modifiers: tuple[tuple[str, float], ...]
    contributions: tuple[tuple[str, str, float], ...]

    def modifier_for(self, channel: str) -> float:
        return dict(self.modifiers).get(channel, 0.0)


class StressBehaviorAdapter:
    """Project stress into explicit, bounded behavioral consideration signals."""

    @staticmethod
    def assess(
        ledger: NPCStressLedger,
        coping: CopingProfile,
        adaptation: StressAdaptationProfile,
    ) -> StressBehaviorSignal:
        if not isinstance(ledger, NPCStressLedger):
            raise TypeError("ledger must be an NPCStressLedger")
        if not isinstance(coping, CopingProfile):
            raise TypeError("coping must be a CopingProfile")
        if not isinstance(adaptation, StressAdaptationProfile):
            raise TypeError("adaptation must be a StressAdaptationProfile")
        if coping.owner_id != adaptation.owner_id:
            raise ValueError("coping and adaptation profiles must share an owner")
        assessment: StressAssessment = ledger.assess(coping.owner_id, coping)
        contributions = []
        modifiers = []
        for channel in CHANNELS:
            stress_part = assessment.stress * adaptation.stress_sensitivity.get(channel, 0.0)
            exhaustion_part = assessment.exhaustion * adaptation.exhaustion_sensitivity.get(channel, 0.0)
            contributions.extend((
                (channel, "stress", stress_part),
                (channel, "exhaustion", exhaustion_part),
            ))
            modifiers.append((channel, max(-1.0, min(1.0, stress_part + exhaustion_part))))
        return StressBehaviorSignal(
            coping.owner_id, assessment.sampled_tick, assessment.stress,
            assessment.exhaustion, tuple(modifiers), tuple(contributions),
        )
