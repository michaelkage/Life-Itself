"""Canonical JSON persistence for long-term NPC emotional scars."""
from __future__ import annotations

from dataclasses import dataclass
import json

from .emotional_scars import NPCEmotionalScarLedger


@dataclass(frozen=True)
class EmotionalScarSnapshot:
    payload: str

    def __post_init__(self):
        if not isinstance(self.payload, str):
            raise TypeError("payload must be a string")
        raw = json.loads(self.payload)
        restored = NPCEmotionalScarLedger.from_snapshot(raw)
        canonical = json.dumps(restored.snapshot(), sort_keys=True, separators=(",", ":"), allow_nan=False)
        if canonical != self.payload:
            raise ValueError("emotional scar snapshot must use canonical JSON")

    @classmethod
    def capture(cls, ledger: NPCEmotionalScarLedger):
        if not isinstance(ledger, NPCEmotionalScarLedger):
            raise TypeError("ledger must be an NPCEmotionalScarLedger")
        return cls(json.dumps(ledger.snapshot(), sort_keys=True, separators=(",", ":"), allow_nan=False))

    @classmethod
    def from_json(cls, payload: str):
        return cls(payload)

    def restore(self):
        return NPCEmotionalScarLedger.from_snapshot(json.loads(self.payload))

    def to_json(self):
        return self.payload
