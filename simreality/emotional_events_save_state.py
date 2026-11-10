"""Canonical, versioned persistence for event-driven NPC emotional state."""
from __future__ import annotations

import json
import math
from dataclasses import dataclass

from .emotional_events import NPCEmotionalEventLedger


@dataclass(frozen=True)
class EmotionalEventSnapshot:
    """Immutable canonical snapshot of transient emotion and replay history."""

    payload: str

    SCHEMA_VERSION = 1

    def __post_init__(self):
        if not isinstance(self.payload, str):
            raise TypeError("payload must be a string")
        restored = self._decode(self.payload)
        canonical = json.dumps(restored, sort_keys=True, separators=(",", ":"), allow_nan=False)
        if canonical != self.payload:
            raise ValueError("emotional snapshot must use canonical JSON")

    @staticmethod
    def _decode(payload: str) -> dict:
        try:
            raw = json.loads(payload)
            if not isinstance(raw, dict) or raw.get("schema_version") != 1:
                raise ValueError("unsupported emotional snapshot schema version")
            ledger_data = raw.get("ledger")
            if not isinstance(ledger_data, dict):
                raise ValueError("ledger must be an object")
            # Reconstructing validates every state, event, and replay signature.
            ledger = NPCEmotionalEventLedger.from_snapshot(ledger_data)
            if ledger.current_tick != raw.get("current_tick"):
                raise ValueError("snapshot tick does not match emotional ledger")
            return {
                "schema_version": 1,
                "current_tick": ledger.current_tick,
                "ledger": ledger.snapshot(),
            }
        except (TypeError, KeyError, json.JSONDecodeError) as exc:
            raise ValueError("invalid emotional event snapshot") from exc

    @classmethod
    def capture(cls, ledger: NPCEmotionalEventLedger) -> "EmotionalEventSnapshot":
        if not isinstance(ledger, NPCEmotionalEventLedger):
            raise TypeError("ledger must be an NPCEmotionalEventLedger")
        raw = {
            "schema_version": cls.SCHEMA_VERSION,
            "current_tick": ledger.current_tick,
            "ledger": ledger.snapshot(),
        }
        return cls(json.dumps(raw, sort_keys=True, separators=(",", ":"), allow_nan=False))

    def restore(self) -> NPCEmotionalEventLedger:
        raw = self._decode(self.payload)
        return NPCEmotionalEventLedger.from_snapshot(raw["ledger"])

    def to_json(self) -> str:
        return self.payload

    @classmethod
    def from_json(cls, payload: str) -> "EmotionalEventSnapshot":
        return cls(payload)
