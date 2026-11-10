"""Translate recalled personal memories into bounded choice-appraisal signals.

Associations are authored per owner and per memory. The adapter does not
infer that a painful memory must cause avoidance or that a positive memory
must cause approach; signed sensitivity is explicit configuration.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

from .npc_memory_recall import MemoryRecallResult


@dataclass(frozen=True)
class MemoryChoiceAssociation:
    association_id: str
    owner_id: str
    memory_id: str
    choice_id: str
    sensitivity: float

    def __post_init__(self):
        for name in ("association_id", "owner_id", "memory_id", "choice_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if (isinstance(self.sensitivity, bool)
                or not isinstance(self.sensitivity, (int, float))
                or not math.isfinite(self.sensitivity)
                or not -1.0 <= self.sensitivity <= 1.0):
            raise ValueError("sensitivity must be finite and in [-1, 1]")


@dataclass(frozen=True)
class MemoryDecisionProfile:
    owner_id: str
    associations: tuple[MemoryChoiceAssociation, ...]

    def __post_init__(self):
        if not isinstance(self.owner_id, str) or not self.owner_id.strip():
            raise ValueError("owner_id must be a non-empty string")
        if not isinstance(self.associations, tuple) or any(
            not isinstance(item, MemoryChoiceAssociation) for item in self.associations
        ):
            raise TypeError("associations must be a tuple of MemoryChoiceAssociation values")
        if any(item.owner_id != self.owner_id for item in self.associations):
            raise ValueError("all associations must belong to the profile owner")
        ids = [item.association_id for item in self.associations]
        if len(ids) != len(set(ids)):
            raise ValueError("association IDs must be unique")
        keys = [(item.memory_id, item.choice_id) for item in self.associations]
        if len(keys) != len(set(keys)):
            raise ValueError("only one association per memory and choice is allowed")


@dataclass(frozen=True)
class MemoryDecisionInfluence:
    owner_id: str
    current_tick: int
    # choice_id -> (memory_id, signed contribution), sorted and bounded in aggregate.
    choice_contributions: tuple[tuple[str, tuple[tuple[str, float], ...]], ...]

    def contributions_for(self, choice_id: str) -> tuple[tuple[str, float], ...]:
        for key, values in self.choice_contributions:
            if key == choice_id:
                return values
        return ()


class MemoryDecisionInfluenceAdapter:
    """Calculate read-only memory contributions from one recall result."""

    @staticmethod
    def evaluate(
        profile: MemoryDecisionProfile,
        recalled: MemoryRecallResult,
    ) -> MemoryDecisionInfluence:
        if not isinstance(profile, MemoryDecisionProfile):
            raise TypeError("profile must be MemoryDecisionProfile")
        if not isinstance(recalled, MemoryRecallResult):
            raise TypeError("recalled must be MemoryRecallResult")
        if profile.owner_id != recalled.owner_id:
            raise ValueError("memory decision profile and recall result owners must match")
        recalled_by_id = {}
        for item in recalled.recalled:
            if item.memory.owner_id != profile.owner_id:
                raise ValueError("recall result contains a memory owned by another NPC")
            if item.memory.memory_id in recalled_by_id:
                raise ValueError("recall result contains duplicate memory IDs")
            if isinstance(item.score, bool) or not isinstance(item.score, (int, float)) or not math.isfinite(item.score) or not 0 <= item.score <= 1:
                raise ValueError("recalled memory scores must be finite and in [0, 1]")
            recalled_by_id[item.memory.memory_id] = item.score

        grouped = {}
        for association in sorted(profile.associations, key=lambda x: x.association_id):
            score = recalled_by_id.get(association.memory_id)
            if score is None:
                continue
            contribution = score * association.sensitivity
            grouped.setdefault(association.choice_id, []).append(
                (association.memory_id, contribution)
            )
        output = []
        for choice_id, entries in sorted(grouped.items()):
            # Multiple memories accumulate, with a hard bound so the memory
            # subsystem cannot overwhelm the rest of the appraisal pipeline.
            total = max(-1.0, min(1.0, sum(value for _, value in entries)))
            raw_total = sum(value for _, value in entries)
            scale = total / raw_total if raw_total else 0.0
            output.append((choice_id, tuple(
                (memory_id, value * scale) for memory_id, value in entries
            )))
        return MemoryDecisionInfluence(profile.owner_id, recalled.current_tick, tuple(output))
