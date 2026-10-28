"""Versioned persistence for the event-to-NPC-memory adapter replay index.

The NPC snapshot owns the actual memories. This codec stores only the adapter's
processed (event, witness) keys and the memory each key refers to, so restoration
can re-establish idempotency without applying the world event a second time.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
from typing import Any

from .model import ActionTag, Description, NPC, NPCMemory
from .world_event_memory import WorldEventMemoryAdapter


def _number(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    return float(value)


def _unit(name: str, value: Any) -> float:
    result = _number(name, value)
    if not 0.0 <= result <= 1.0:
        raise ValueError(f"{name} must be in [0, 1]")
    return result


def _memory_dict(memory: NPCMemory) -> dict[str, Any]:
    return {
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


def _memory_from(raw: dict[str, Any]) -> NPCMemory:
    try:
        desc = raw["description"]
        weights = desc["jacket_colour_weights"]
        if not isinstance(weights, dict) or any(not isinstance(k, str) for k in weights):
            raise ValueError("jacket_colour_weights must map strings to numbers")
        if not isinstance(desc["masked"], bool):
            raise ValueError("masked must be a boolean")
        observations = desc["observations"]
        if isinstance(observations, bool) or not isinstance(observations, int) or observations < 1:
            raise ValueError("observations must be a positive integer")
        target = raw["target_entity_id"]
        if target is not None and (not isinstance(target, str) or not target.strip()):
            raise ValueError("target_entity_id must be None or a non-empty string")
        return NPCMemory(
            witness_id=raw["witness_id"],
            target_entity_id=target,
            initial_impact=_unit("initial_impact", raw["initial_impact"]),
            retention=_unit("retention", raw["retention"]),
            timestamp_hour=_number("timestamp_hour", raw["timestamp_hour"]),
            action_tag=ActionTag(raw["action_tag"]),
            description=Description(
                height_m=_number("height_m", desc["height_m"]),
                height_uncertainty_m=_number("height_uncertainty_m", desc["height_uncertainty_m"]),
                jacket_colour_weights={k: _number("jacket colour weight", v) for k, v in weights.items()},
                masked=desc["masked"],
                masked_confidence=_unit("masked_confidence", desc["masked_confidence"]),
                observations=observations,
            ),
        )
    except ValueError:
        raise
    except (TypeError, KeyError, AttributeError) as exc:
        raise ValueError("memory replay entry has an invalid structure") from exc


@dataclass(frozen=True)
class WorldEventMemoryReplaySnapshot:
    """Canonical replay entries for one WorldEventMemoryAdapter instance."""

    entries: tuple[tuple[str, str, NPCMemory], ...]

    SCHEMA_VERSION = 1

    def __post_init__(self) -> None:
        if not isinstance(self.entries, tuple):
            raise ValueError("entries must be a tuple")
        keys = [(event_id, witness_id) for event_id, witness_id, _ in self.entries]
        if any(not isinstance(event_id, str) or not event_id.strip()
               or not isinstance(witness_id, str) or not witness_id.strip()
               for event_id, witness_id in keys):
            raise ValueError("event and witness IDs must be non-empty strings")
        if keys != sorted(keys) or len(keys) != len(set(keys)):
            raise ValueError("replay keys must be unique and sorted")
        for (_, witness_id, memory) in self.entries:
            if not isinstance(memory, NPCMemory) or memory.witness_id != witness_id:
                raise ValueError("each replay memory must match its witness ID")

    @classmethod
    def capture(cls, adapter: WorldEventMemoryAdapter) -> "WorldEventMemoryReplaySnapshot":
        if not isinstance(adapter, WorldEventMemoryAdapter):
            raise TypeError("adapter must be a WorldEventMemoryAdapter")
        return cls(tuple(
            (event_id, witness_id, memory)
            for (event_id, witness_id), memory in sorted(adapter._processed.items())
        ))

    def restore(self, adapter: WorldEventMemoryAdapter, npcs: dict[str, NPC]) -> None:
        """Restore keys only when their exact memories already exist on restored NPCs.

        Restore NPC state first. This method deliberately refuses to attach memories:
        doing so here could hide a partial or mismatched save and duplicate side effects.
        """
        if not isinstance(adapter, WorldEventMemoryAdapter):
            raise TypeError("adapter must be a WorldEventMemoryAdapter")
        if not isinstance(npcs, dict):
            raise TypeError("npcs must be a dict of restored NPCs")
        if adapter._processed:
            raise ValueError("adapter replay index must be empty before restore")
        restored: dict[tuple[str, str], NPCMemory] = {}
        for event_id, witness_id, memory in self.entries:
            if event_id not in {event.event_id for event in adapter.events.snapshot()}:
                raise ValueError(f"unknown world event in replay snapshot: {event_id}")
            npc = npcs.get(witness_id)
            if not isinstance(npc, NPC):
                raise ValueError(f"restored witness NPC is missing: {witness_id}")
            if memory not in npc.memories:
                raise ValueError(
                    f"saved replay memory is absent from restored NPC {witness_id!r}"
                )
            event = adapter.events.get(event_id)
            if witness_id not in event.witnesses:
                raise ValueError(f"saved NPC is not a witness to event {event_id!r}")
            restored[(event_id, witness_id)] = next(
                item for item in npc.memories if item == memory
            )
        adapter._processed.update(restored)

    def to_json(self) -> str:
        return json.dumps({
            "schema_version": self.SCHEMA_VERSION,
            "entries": [
                {"event_id": event_id, "witness_id": witness_id, "memory": _memory_dict(memory)}
                for event_id, witness_id, memory in self.entries
            ],
        }, sort_keys=True, separators=(",", ":"), allow_nan=False)

    @classmethod
    def from_json(cls, payload: str) -> "WorldEventMemoryReplaySnapshot":
        try:
            raw = json.loads(payload)
            if not isinstance(raw, dict) or raw.get("schema_version") != cls.SCHEMA_VERSION:
                raise ValueError("unsupported world-event memory replay schema version")
            entries = tuple(sorted(
                ((item["event_id"], item["witness_id"], _memory_from(item["memory"]))
                 for item in raw["entries"]),
                key=lambda item: (item[0], item[1]),
            ))
            return cls(entries)
        except ValueError:
            raise
        except (TypeError, KeyError, IndexError, json.JSONDecodeError) as exc:
            raise ValueError("world-event memory replay snapshot has an invalid structure") from exc
