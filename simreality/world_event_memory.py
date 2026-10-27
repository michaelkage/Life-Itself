"""Create witness-specific memories from authoritative world events."""
from __future__ import annotations

import math
from typing import Mapping

from .model import ActionTag, Description, NPC, NPCMemory
from .world_events import WorldEvent, WorldEventLedger


class WorldEventMemoryAdapter:
    """Materialize explicitly described events as NPC memory entries.

    Event facts and witness memories are different layers. This adapter only
    creates memories for listed witnesses, and only when the event supplies an
    understood action tag and target. It does not decide visibility or infer who
    committed an event. Replaying the same event/witness pair is idempotent within
    this adapter instance.
    """

    def __init__(self, events: WorldEventLedger, *, ticks_per_hour: float = 1.0) -> None:
        if not isinstance(events, WorldEventLedger):
            raise TypeError("events must be a WorldEventLedger")
        if isinstance(ticks_per_hour, bool) or not isinstance(ticks_per_hour, (int, float)):
            raise ValueError("ticks_per_hour must be a positive finite number")
        if not math.isfinite(ticks_per_hour) or ticks_per_hour <= 0:
            raise ValueError("ticks_per_hour must be a positive finite number")
        self.events = events
        self.ticks_per_hour = float(ticks_per_hour)
        self._processed: dict[tuple[str, str], NPCMemory] = {}

    @staticmethod
    def _attributes(event: WorldEvent) -> dict[str, object]:
        return dict(event.attributes)

    def materialize(
        self,
        event_id: str,
        witness_id: str,
        npcs: Mapping[str, NPC],
    ) -> NPCMemory | None:
        """Create and attach a memory, or return None when the event lacks memory data.

        A witness must be listed in the authoritative event and must exist in the
        supplied NPC mapping. Required attributes: `action_tag`, `target_entity_id`,
        and optional `memory_impact` (default 1.0). Visual-description attributes
        are optional and default to an unknown description.
        """
        event = self.events.get(event_id)
        if witness_id not in event.witnesses:
            raise ValueError(f"{witness_id!r} is not recorded as a witness to {event_id!r}")
        if witness_id not in npcs:
            raise KeyError(f"NPC not found: {witness_id}")
        if not isinstance(npcs[witness_id], NPC):
            raise TypeError("witness mapping values must be NPC instances")
        attrs = self._attributes(event)
        raw_tag = attrs.get("action_tag")
        target_id = attrs.get("target_entity_id")
        if not isinstance(raw_tag, str) or not isinstance(target_id, str) or not target_id.strip():
            return None
        try:
            action_tag = ActionTag(raw_tag)
        except ValueError:
            return None
        impact = attrs.get("memory_impact", 1.0)
        if isinstance(impact, bool) or not isinstance(impact, (int, float)):
            raise ValueError("memory_impact must be numeric")
        if not math.isfinite(impact) or not 0.0 <= impact <= 1.0:
            raise ValueError("memory_impact must be finite and in [0, 1]")
        key = (event.event_id, witness_id)
        if key in self._processed:
            return self._processed[key]

        height = attrs.get("height_m", 0.0)
        height_uncertainty = attrs.get("height_uncertainty_m", 0.35)
        masked_confidence = attrs.get("masked_confidence", 0.0)
        for name, value in (
            ("height_m", height),
            ("height_uncertainty_m", height_uncertainty),
            ("masked_confidence", masked_confidence),
        ):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"{name} must be a finite number")
        if height_uncertainty < 0 or not 0.0 <= masked_confidence <= 1.0:
            raise ValueError("height uncertainty must be non-negative and masked confidence in [0, 1]")
        jacket_colour = attrs.get("jacket_colour")
        if jacket_colour is not None and not isinstance(jacket_colour, str):
            raise ValueError("jacket_colour must be a string")
        description = Description(
            height_m=float(height),
            height_uncertainty_m=float(height_uncertainty),
            jacket_colour_weights={jacket_colour: float(masked_confidence or 1.0)} if jacket_colour else {},
            masked=bool(attrs.get("masked", False)),
            masked_confidence=float(masked_confidence),
        )
        memory = NPCMemory(
            witness_id=witness_id,
            target_entity_id=target_id,
            initial_impact=float(impact),
            retention=float(impact),
            timestamp_hour=event.tick / self.ticks_per_hour,
            action_tag=action_tag,
            description=description,
        )
        npcs[witness_id].remember(memory)
        self._processed[key] = memory
        return memory

    def snapshot(self) -> tuple[tuple[str, str, NPCMemory], ...]:
        """Return stable processed-key state for a save system."""
        return tuple(
            (event_id, witness_id, memory)
            for (event_id, witness_id), memory in sorted(self._processed.items())
        )
