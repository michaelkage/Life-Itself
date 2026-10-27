"""Versioned JSON codec for persistent NPC identity and witnessed memories.

This codec preserves the NPC fields owned by the core model. Social ledgers and
adapter replay indexes are separate state and are not silently implied by this
snapshot.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
from typing import Any

from .model import ActionTag, AgeBand, Description, NPC, NPCMemory, TraumaLevel


def _finite_number(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    return float(value)


def _unit(name: str, value: Any) -> float:
    number = _finite_number(name, value)
    if not 0.0 <= number <= 1.0:
        raise ValueError(f"{name} must be in [0, 1]")
    return number


@dataclass(frozen=True)
class NPCStateSnapshot:
    """Portable, canonical snapshot of a single NPC and all current memories."""

    entity_id: str
    age_band: AgeBand
    moral_shackle: float
    desperation_index: float
    trauma_level: TraumaLevel
    personal_stress: float
    memories: tuple[NPCMemory, ...]

    SCHEMA_VERSION = 1

    def __post_init__(self) -> None:
        if not isinstance(self.entity_id, str) or not self.entity_id.strip():
            raise ValueError("entity_id must be a non-empty string")
        if not isinstance(self.age_band, AgeBand):
            raise ValueError("age_band must be an AgeBand")
        if not isinstance(self.trauma_level, TraumaLevel):
            raise ValueError("trauma_level must be a TraumaLevel")
        _unit("moral_shackle", self.moral_shackle)
        _finite_number("desperation_index", self.desperation_index)
        if self.desperation_index < 0.0:
            raise ValueError("desperation_index must be non-negative")
        _finite_number("personal_stress", self.personal_stress)
        if self.personal_stress < 0.0:
            raise ValueError("personal_stress must be non-negative")
        if not isinstance(self.memories, tuple) or any(not isinstance(m, NPCMemory) for m in self.memories):
            raise ValueError("memories must be a tuple of NPCMemory records")

    @classmethod
    def capture(cls, npc: NPC) -> "NPCStateSnapshot":
        if not isinstance(npc, NPC):
            raise TypeError("npc must be an NPC")
        return cls(
            entity_id=npc.entity_id,
            age_band=npc.age_band,
            moral_shackle=npc.moral_shackle,
            desperation_index=npc.desperation_index,
            trauma_level=npc.trauma_level,
            personal_stress=npc.personal_stress,
            memories=tuple(npc.memories),
        )

    def restore(self) -> NPC:
        return NPC(
            entity_id=self.entity_id,
            age_band=self.age_band,
            moral_shackle=self.moral_shackle,
            desperation_index=self.desperation_index,
            trauma_level=self.trauma_level,
            personal_stress=self.personal_stress,
            memories=list(self.memories),
        )

    def to_json(self) -> str:
        payload: dict[str, Any] = {
            "schema_version": self.SCHEMA_VERSION,
            "entity_id": self.entity_id,
            "age_band": self.age_band.value,
            "moral_shackle": self.moral_shackle,
            "desperation_index": self.desperation_index,
            "trauma_level": int(self.trauma_level),
            "personal_stress": self.personal_stress,
            "memories": [
                {
                    "witness_id": memory.witness_id,
                    "target_entity_id": memory.target_entity_id,
                    "initial_impact": memory.initial_impact,
                    "retention": memory.retention,
                    "timestamp_hour": memory.timestamp_hour,
                    "action_tag": memory.action_tag.value,
                    "description": {
                        "height_m": memory.description.height_m,
                        "height_uncertainty_m": memory.description.height_uncertainty_m,
                        "jacket_colour_weights": dict(sorted(memory.description.jacket_colour_weights.items())),
                        "masked": memory.description.masked,
                        "masked_confidence": memory.description.masked_confidence,
                        "observations": memory.description.observations,
                    },
                }
                for memory in self.memories
            ],
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)

    @classmethod
    def from_json(cls, payload: str) -> "NPCStateSnapshot":
        try:
            raw = json.loads(payload)
            if not isinstance(raw, dict) or raw.get("schema_version") != cls.SCHEMA_VERSION:
                raise ValueError("unsupported NPC snapshot schema version")
            memories = []
            for item in raw["memories"]:
                description_data = item["description"]
                description = Description(
                    height_m=_finite_number("height_m", description_data["height_m"]),
                    height_uncertainty_m=_finite_number("height_uncertainty_m", description_data["height_uncertainty_m"]),
                    jacket_colour_weights={
                        str(key): _finite_number("jacket colour weight", value)
                        for key, value in description_data["jacket_colour_weights"].items()
                    },
                    masked=description_data["masked"],
                    masked_confidence=_unit("masked_confidence", description_data["masked_confidence"]),
                    observations=description_data["observations"],
                )
                memories.append(NPCMemory(
                    witness_id=item["witness_id"],
                    target_entity_id=item["target_entity_id"],
                    initial_impact=_unit("initial_impact", item["initial_impact"]),
                    retention=_unit("retention", item["retention"]),
                    timestamp_hour=_finite_number("timestamp_hour", item["timestamp_hour"]),
                    action_tag=ActionTag(item["action_tag"]),
                    description=description,
                ))
            return cls(
                entity_id=raw["entity_id"],
                age_band=AgeBand(raw["age_band"]),
                moral_shackle=_unit("moral_shackle", raw["moral_shackle"]),
                desperation_index=_finite_number("desperation_index", raw["desperation_index"]),
                trauma_level=TraumaLevel(raw["trauma_level"]),
                personal_stress=_finite_number("personal_stress", raw["personal_stress"]),
                memories=tuple(memories),
            )
        except ValueError:
            raise
        except (TypeError, KeyError, IndexError, json.JSONDecodeError) as exc:
            raise ValueError("NPC snapshot has an invalid structure") from exc


@dataclass(frozen=True)
class NPCCollectionSnapshot:
    """Canonical collection of NPC snapshots, keyed and ordered by entity ID."""

    npcs: tuple[NPCStateSnapshot, ...]

    SCHEMA_VERSION = 1

    def __post_init__(self) -> None:
        if not isinstance(self.npcs, tuple) or any(not isinstance(npc, NPCStateSnapshot) for npc in self.npcs):
            raise ValueError("npcs must be a tuple of NPCStateSnapshot records")
        ids = [npc.entity_id for npc in self.npcs]
        if len(ids) != len(set(ids)):
            raise ValueError("NPC entity IDs must be unique")
        if ids != sorted(ids):
            raise ValueError("NPC snapshots must be sorted by entity ID")

    @classmethod
    def capture(cls, npcs: tuple[NPC, ...] | list[NPC]) -> "NPCCollectionSnapshot":
        snapshots = tuple(sorted((NPCStateSnapshot.capture(npc) for npc in npcs), key=lambda item: item.entity_id))
        return cls(snapshots)

    def restore(self) -> dict[str, NPC]:
        return {snapshot.entity_id: snapshot.restore() for snapshot in self.npcs}

    def to_json(self) -> str:
        return json.dumps({
            "schema_version": self.SCHEMA_VERSION,
            "npcs": [json.loads(snapshot.to_json()) for snapshot in self.npcs],
        }, sort_keys=True, separators=(",", ":"), allow_nan=False)

    @classmethod
    def from_json(cls, payload: str) -> "NPCCollectionSnapshot":
        try:
            raw = json.loads(payload)
            if not isinstance(raw, dict) or raw.get("schema_version") != cls.SCHEMA_VERSION:
                raise ValueError("unsupported NPC collection schema version")
            snapshots = tuple(sorted((
                NPCStateSnapshot.from_json(json.dumps(item, allow_nan=False))
                for item in raw["npcs"]
            ), key=lambda item: item.entity_id))
            return cls(snapshots)
        except ValueError:
            raise
        except (TypeError, KeyError, json.JSONDecodeError) as exc:
            raise ValueError("NPC collection snapshot has an invalid structure") from exc
