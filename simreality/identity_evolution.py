"""Deterministic NPC identity proposals."""
from dataclasses import dataclass
from typing import Mapping

@dataclass(frozen=True)
class NPCIdentityProfile:
    npc_id: str
    traits: Mapping[str, float]
    sensitivities: Mapping[str, float] | None = None
