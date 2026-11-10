"""Canonical JSON persistence for presence-gated social encounters."""
from __future__ import annotations

from dataclasses import dataclass
import json

from .presence_encounters import PresenceEncounter, PresenceEncounterLedger


def _payload(record):
    return {"encounter_id": record.encounter_id, "tick": record.tick,
            "location_id": record.location_id, "participants": list(record.participants),
            "conversation_id": record.conversation_id,
            "trust_interaction_ids": list(record.trust_interaction_ids)}


def _read(raw):
    return PresenceEncounter(raw["encounter_id"], raw["tick"], raw["location_id"],
                             tuple(raw["participants"]), raw.get("conversation_id"),
                             tuple(raw.get("trust_interaction_ids", ())))


@dataclass(frozen=True)
class PresenceEncounterSnapshot:
    records: tuple[PresenceEncounter, ...]
    ticks: tuple[tuple[int, str, tuple[PresenceEncounter, ...]], ...]
    SCHEMA_VERSION = 1

    def __post_init__(self):
        if not isinstance(self.records, tuple) or any(not isinstance(x, PresenceEncounter) for x in self.records):
            raise ValueError("records must contain PresenceEncounter values")
        ids = [x.encounter_id for x in self.records]
        if len(ids) != len(set(ids)):
            raise ValueError("encounter IDs must be unique")
        keys = [(x.tick, x.encounter_id) for x in self.records]
        if keys != sorted(keys):
            raise ValueError("encounter records must be canonically ordered")
        ticks = [x[0] for x in self.ticks]
        if ticks != sorted(ticks) or len(ticks) != len(set(ticks)):
            raise ValueError("encounter ticks must be unique and increasing")
        for tick, signature, records in self.ticks:
            if isinstance(tick, bool) or not isinstance(tick, int) or tick < 0 or not isinstance(signature, str) or not signature:
                raise ValueError("invalid encounter tick")
            if not isinstance(records, tuple) or any(not isinstance(x, PresenceEncounter) for x in records):
                raise ValueError("tick records must contain PresenceEncounter values")
            if [(x.tick, x.encounter_id) for x in records] != sorted((x.tick, x.encounter_id) for x in records):
                raise ValueError("tick encounter records must be canonically ordered")
            try:
                signatures = json.loads(signature)
            except json.JSONDecodeError as exc:
                raise ValueError("invalid encounter tick signature") from exc
            if not isinstance(signatures, dict) or sorted(signatures) != sorted(x.encounter_id for x in records):
                raise ValueError("encounter tick signature IDs do not match records")

    @classmethod
    def capture(cls, ledger):
        if not isinstance(ledger, PresenceEncounterLedger):
            raise TypeError("ledger must be a PresenceEncounterLedger")
        return cls(ledger.snapshot(), ledger.tick_snapshot())

    def to_json(self):
        value = {"schema_version": self.SCHEMA_VERSION,
                 "records": [_payload(x) for x in self.records],
                 "ticks": [{"tick": tick, "signature": signature,
                            "records": [_payload(x) for x in records]}
                           for tick, signature, records in self.ticks]}
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)

    @classmethod
    def from_json(cls, payload):
        try:
            raw = json.loads(payload)
            if not isinstance(raw, dict) or raw.get("schema_version") != cls.SCHEMA_VERSION:
                raise ValueError("unsupported presence encounter schema")
            result = cls(tuple(_read(x) for x in raw["records"]),
                         tuple((x["tick"], x["signature"], tuple(_read(r) for r in x["records"]))
                               for x in raw["ticks"]))
            if result.to_json() != payload:
                raise ValueError("presence encounter snapshot must be canonical JSON")
            return result
        except ValueError:
            raise
        except (TypeError, KeyError, IndexError, json.JSONDecodeError) as exc:
            raise ValueError("invalid presence encounter snapshot") from exc

    def restore(self):
        ledger = PresenceEncounterLedger(self.records)
        for tick, signature, records in self.ticks:
            ledger._restore_tick(tick, signature, records)
        return ledger
