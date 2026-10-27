"""Deterministic bridge from an NPC's own memories to transmissible rumours.

This adapter never reads the authoritative world-event journal. A fact becomes
gossip only after it has been materialized as a particular NPC's memory.
Decay is calculated from each memory's original impact and timestamp, so calling
the adapter repeatedly at the same simulation time cannot compound decay.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .decay import sweep
from .gossip import Rumour, retell
from .model import NPC, NPCMemory, Weather


@dataclass(frozen=True)
class MemoryRumourSnapshot:
    """Read-only result prepared for one NPC at one simulation hour."""

    witness_id: str
    current_hour: float
    memories: tuple[NPCMemory, ...]
    rumours: tuple[Rumour, ...]


class MemoryRumourAdapter:
    """Prepare rumours only from the named NPC's retained memories.

    The adapter is deliberately read-only: it does not overwrite NPC memories,
    mutate the world-event ledger, or transfer rumours to other NPCs. Use the
    existing `converse` function to model an actual conversation. This keeps
    time advancement explicit and avoids repeatedly decaying an already-decayed
    value when the simulation ticks more than once between save points.
    """

    def prepare(
        self,
        npc: NPC,
        current_hour: float,
        weather: Weather,
        *,
        lambda_base: float | None = None,
    ) -> MemoryRumourSnapshot:
        """Return decayed memory copies and every rumour those copies can support.

        Rumours below the existing transmission floors are omitted by `retell`.
        That function also removes a target ID when retention falls below the
        telephone threshold; the adapter does not invent or restore attribution.
        """
        if not isinstance(npc, NPC):
            raise TypeError("npc must be an NPC")
        if isinstance(current_hour, bool) or not isinstance(current_hour, (int, float)):
            raise ValueError("current_hour must be a finite number")
        if not math.isfinite(current_hour) or current_hour < 0:
            raise ValueError("current_hour must be a finite non-negative number")
        if not isinstance(weather, Weather):
            raise TypeError("weather must be a Weather value")
        if lambda_base is not None and (
            isinstance(lambda_base, bool)
            or not isinstance(lambda_base, (int, float))
            or not math.isfinite(lambda_base)
            or lambda_base < 0
        ):
            raise ValueError("lambda_base must be finite and non-negative")

        memories = tuple(
            sweep(npc.memories, npc.age_band, float(current_hour), weather, lambda_base)
        )
        rumours = tuple(
            rumour
            for memory in memories
            if (rumour := retell(memory)) is not None
        )
        return MemoryRumourSnapshot(
            witness_id=npc.entity_id,
            current_hour=float(current_hour),
            memories=memories,
            rumours=rumours,
        )
