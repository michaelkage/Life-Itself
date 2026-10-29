"""Deterministic, personal routine avoidance derived from explicitly linked memories.

NPC memories do not inherently contain a location. Callers must provide a
verified association between a specific memory and a location; this adapter
never guesses that link from an action tag, identity, or neighbourhood.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable

from .model import NPC, NPCMemory
from .routines import DisruptionKind, RoutineDisruption


@dataclass(frozen=True)
class MemoryLocationAssociation:
    association_id: str
    memory_index: int
    location_id: str
    avoidance_scale: float = 1.0
    alternative_location_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.association_id, str) or not self.association_id.strip():
            raise ValueError("association_id must be a non-empty string")
        if isinstance(self.memory_index, bool) or not isinstance(self.memory_index, int) or self.memory_index < 0:
            raise ValueError("memory_index must be a non-negative integer")
        for name in ("location_id", "alternative_location_id"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{name} must be None or a non-empty string")
        if isinstance(self.avoidance_scale, bool) or not isinstance(self.avoidance_scale, (int, float)) or not math.isfinite(self.avoidance_scale) or not 0.0 <= self.avoidance_scale <= 1.0:
            raise ValueError("avoidance_scale must be finite and in [0, 1]")


@dataclass(frozen=True)
class RoutineAvoidanceProfile:
    owner_id: str
    location_id: str
    strength: float
    source_memory_indices: tuple[int, ...]
    alternative_location_id: str | None

    def __post_init__(self) -> None:
        if not self.owner_id or not self.location_id:
            raise ValueError("owner and location IDs must be non-empty")
        if not math.isfinite(self.strength) or not 0.0 <= self.strength <= 1.0:
            raise ValueError("strength must be finite and in [0, 1]")


class MemoryRoutineAdapter:
    """Translate linked personal memories into stable location-avoidance disruptions."""

    def derive_avoidance(
        self,
        npc: NPC,
        associations: Iterable[MemoryLocationAssociation],
        *,
        start_minute: int,
        end_minute: int,
        minimum_strength: float = 0.25,
    ) -> tuple[RoutineDisruption, ...]:
        if not isinstance(npc, NPC):
            raise TypeError("npc must be an NPC")
        if isinstance(start_minute, bool) or not isinstance(start_minute, int) or isinstance(end_minute, bool) or not isinstance(end_minute, int) or not 0 <= start_minute < end_minute <= 1440:
            raise ValueError("avoidance window must fit within one day and have positive duration")
        if isinstance(minimum_strength, bool) or not isinstance(minimum_strength, (int, float)) or not math.isfinite(minimum_strength) or not 0.0 <= minimum_strength <= 1.0:
            raise ValueError("minimum_strength must be finite and in [0, 1]")
        items = tuple(sorted(associations, key=lambda item: item.association_id))
        if any(not isinstance(item, MemoryLocationAssociation) for item in items):
            raise TypeError("associations must contain MemoryLocationAssociation values")
        if len({item.association_id for item in items}) != len(items):
            raise ValueError("association IDs must be unique")

        grouped: dict[str, list[tuple[int, float, str | None, str]]] = {}
        for association in items:
            if association.memory_index >= len(npc.memories):
                raise ValueError(f"memory index out of range: {association.memory_index}")
            memory: NPCMemory = npc.memories[association.memory_index]
            # Relevance is based on this NPC's own retained memory and an explicit
            # location link. Action severity is not guessed or universally mapped.
            strength = memory.retention * association.avoidance_scale
            if strength < minimum_strength:
                continue
            grouped.setdefault(association.location_id, []).append(
                (association.memory_index, strength, association.alternative_location_id, association.association_id)
            )

        disruptions = []
        for location_id, entries in sorted(grouped.items()):
            entries.sort(key=lambda entry: (entry[0], entry[3]))
            # Independent memories compound without exceeding certainty. This is a
            # deterministic heuristic, not a clinical or universal fear model.
            strength = 1.0
            for _, item_strength, _, _ in entries:
                strength *= 1.0 - item_strength
            strength = 1.0 - strength
            if strength < minimum_strength:
                continue
            alternatives = sorted({entry[2] for entry in entries if entry[2] is not None})
            alternative = alternatives[0] if alternatives else None
            source_indices = tuple(sorted({entry[0] for entry in entries}))
            token = ",".join(entry[3] for entry in entries)
            disruption_id = f"memory-avoidance:{npc.entity_id}:{location_id}:{token}"
            disruptions.append(RoutineDisruption(
                disruption_id=disruption_id,
                owner_id=npc.entity_id,
                kind=DisruptionKind.LOCATION_AVOIDANCE,
                severity=min(1.0, strength),
                start_minute=start_minute,
                end_minute=end_minute,
                affected_location_id=location_id,
                alternative_activity="take an alternative route" if alternative else None,
                alternative_location_id=alternative,
            ))
        return tuple(sorted(disruptions, key=lambda disruption: disruption.disruption_id))
