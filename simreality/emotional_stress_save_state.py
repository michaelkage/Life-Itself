"""Canonical versioned persistence for NPC stress ledgers."""
from __future__ import annotations

from dataclasses import dataclass
import json

from .emotional_stress import NPCStressLedger


@dataclass(frozen=True)
class NPCStressSnapshot:
    payload: str

    def __post_init__(self):
        if not isinstance(self.payload, str):
            raise TypeError("payload must be a string")
        raw = json.loads(self.payload)
        restored = NPCStressLedger.from_snapshot(raw)
        canonical = (json.dumps(raw, sort_keys=True, separators=(",", ":"), allow_nan=False)
                     if raw.get("version") == 1 else
                     json.dumps(restored.snapshot(), sort_keys=True, separators=(",", ":"), allow_nan=False))
        if canonical != self.payload:
            raise ValueError("NPC stress snapshot must use canonical JSON")

    @classmethod
    def capture(cls, ledger: NPCStressLedger):
        if not isinstance(ledger, NPCStressLedger):
            raise TypeError("ledger must be an NPCStressLedger")
        return cls(json.dumps(ledger.snapshot(), sort_keys=True, separators=(",", ":"), allow_nan=False))

    @classmethod
    def from_json(cls, payload: str):
        return cls(payload)

    def restore(self):
        return NPCStressLedger.from_snapshot(json.loads(self.payload))

    def to_json(self):
        return self.payload
