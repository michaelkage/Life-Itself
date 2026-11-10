"""Cue-triggered emotional responses grounded in autobiographical memory.

The world supplies literal observed cue IDs. Authored owner-specific
associations connect those cues to remembered experiences and emotion axes.
Evaluation is read-only: it returns bounded, attributable impulses and never
mutates the emotional ledger or assumes what a cue means.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping

from .npc_life_history import NPCLifeHistory


def _text(name, value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _unit(name, value):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or not 0.0 <= value <= 1.0):
        raise ValueError(f"{name} must be finite and in [0, 1]")
    return float(value)


@dataclass(frozen=True)
class EmotionalMemoryAssociation:
    association_id: str
    memory_id: str
    cue_id: str
    emotion_axis: str
    sensitivity: float = 1.0

    def __post_init__(self):
        for name in ("association_id", "memory_id", "cue_id", "emotion_axis"):
            object.__setattr__(self, name, _text(name, getattr(self, name)))
        object.__setattr__(self, "sensitivity", _unit("sensitivity", self.sensitivity))


@dataclass(frozen=True)
class EmotionalMemoryProfile:
    owner_id: str
    associations: tuple[EmotionalMemoryAssociation, ...]

    def __post_init__(self):
        object.__setattr__(self, "owner_id", _text("owner_id", self.owner_id))
        if isinstance(self.associations, (str, bytes)):
            raise TypeError("associations must be an iterable of EmotionalMemoryAssociation")
        items = tuple(self.associations)
        if any(not isinstance(x, EmotionalMemoryAssociation) for x in items):
            raise TypeError("associations must contain EmotionalMemoryAssociation values")
        ids = [x.association_id for x in items]
        keys = [(x.memory_id, x.cue_id, x.emotion_axis) for x in items]
        if len(ids) != len(set(ids)):
            raise ValueError("association IDs must be unique")
        if len(keys) != len(set(keys)):
            raise ValueError("memory/cue/emotion associations must be unique")
        object.__setattr__(self, "associations", tuple(sorted(
            items, key=lambda x: (x.cue_id, x.emotion_axis, x.memory_id, x.association_id)
        )))


@dataclass(frozen=True)
class EmotionalMemoryContribution:
    association_id: str
    memory_id: str
    cue_id: str
    emotion_axis: str
    exposure: float
    salience: float
    sensitivity: float
    intensity: float

    def __post_init__(self):
        for name in ("association_id", "memory_id", "cue_id", "emotion_axis"):
            _text(name, getattr(self, name))
        for name in ("exposure", "salience", "sensitivity", "intensity"):
            _unit(name, getattr(self, name))


@dataclass(frozen=True)
class EmotionalMemoryResponse:
    owner_id: str
    sampled_tick: int
    intensities: tuple[tuple[str, float], ...]
    contributions: tuple[EmotionalMemoryContribution, ...]

    def __post_init__(self):
        _text("owner_id", self.owner_id)
        if isinstance(self.sampled_tick, bool) or not isinstance(self.sampled_tick, int) or self.sampled_tick < 0:
            raise ValueError("sampled_tick must be a non-negative integer")
        axes = [axis for axis, _ in self.intensities]
        if axes != sorted(set(axes)):
            raise ValueError("emotion axes must be unique and sorted")
        for axis, value in self.intensities:
            _text("emotion axis", axis)
            _unit("emotion intensity", value)
        keys = [(x.association_id, x.memory_id, x.cue_id, x.emotion_axis) for x in self.contributions]
        if keys != sorted(keys) or len(keys) != len(set(keys)):
            raise ValueError("contributions must be uniquely sorted")


class EmotionalMemoryAdapter:
    """Evaluate observed cues against one owner's autobiographical associations."""

    @staticmethod
    def evaluate(
        history: NPCLifeHistory,
        profile: EmotionalMemoryProfile,
        observed_cues: Mapping[str, float],
        current_tick: int,
        *,
        half_life_ticks: float = 100.0,
        minimum_intensity: float = 0.0,
    ) -> EmotionalMemoryResponse:
        if not isinstance(history, NPCLifeHistory):
            raise TypeError("history must be an NPCLifeHistory")
        if not isinstance(profile, EmotionalMemoryProfile):
            raise TypeError("profile must be an EmotionalMemoryProfile")
        if isinstance(current_tick, bool) or not isinstance(current_tick, int) or current_tick < 0:
            raise ValueError("current_tick must be a non-negative integer")
        if (isinstance(half_life_ticks, bool) or not isinstance(half_life_ticks, (int, float))
                or not math.isfinite(half_life_ticks) or half_life_ticks <= 0):
            raise ValueError("half_life_ticks must be positive and finite")
        minimum_intensity = _unit("minimum_intensity", minimum_intensity)
        if not isinstance(observed_cues, Mapping):
            raise TypeError("observed_cues must map cue IDs to exposure strengths")
        exposures = {}
        for cue_id, exposure in observed_cues.items():
            cue_id = _text("cue_id", cue_id)
            exposures[cue_id] = _unit("cue exposure", exposure)
        memories = {item.memory_id: item for item in history.memories(profile.owner_id)}
        contributions = []
        for association in profile.associations:
            memory = memories.get(association.memory_id)
            if memory is None:
                raise KeyError(
                    f"association {association.association_id} references a memory not owned by {profile.owner_id}"
                )
            exposure = exposures.get(association.cue_id, 0.0)
            if exposure <= 0.0:
                continue
            if memory.tick > current_tick:
                raise ValueError("cannot emotionally react to a memory from a future tick")
            elapsed = current_tick - memory.tick
            salience = history.recall_salience(
                memory.memory_id, current_tick, half_life_ticks=half_life_ticks,
            )
            intensity = min(1.0, abs(memory.emotional_impact) * exposure
                            * association.sensitivity * salience)
            if intensity < minimum_intensity:
                continue
            contributions.append(EmotionalMemoryContribution(
                association.association_id, memory.memory_id, association.cue_id,
                association.emotion_axis, exposure, salience,
                association.sensitivity, intensity,
            ))
        contributions.sort(key=lambda x: (x.association_id, x.memory_id, x.cue_id, x.emotion_axis))
        totals = {}
        for item in contributions:
            totals[item.emotion_axis] = totals.get(item.emotion_axis, 0.0) + item.intensity
        intensities = tuple(sorted(
            (axis, min(1.0, value)) for axis, value in totals.items()
        ))
        return EmotionalMemoryResponse(
            profile.owner_id, current_tick, intensities, tuple(contributions),
        )
