"""Canonical JSON persistence for authoritative NPC presence and replay history."""
from __future__ import annotations

from dataclasses import dataclass
import json

from .presence import NPCPresence, PresenceLedger


def _record_payload(r):
    return {"owner_id": r.owner_id, "status": r.status, "location_id": r.location_id,
            "journey_id": r.journey_id, "edge_id": r.edge_id,
            "edge_progress": r.edge_progress, "updated_tick": r.updated_tick}


def _read_record(raw):
    return NPCPresence(raw["owner_id"], raw["status"], raw["location_id"],
                       raw["journey_id"], raw["edge_id"], raw["edge_progress"],
                       raw["updated_tick"])


@dataclass(frozen=True)
class PresenceSnapshot:
    records: tuple[NPCPresence, ...]
    ticks: tuple[tuple[int, str, tuple[NPCPresence, ...]], ...]
    SCHEMA_VERSION = 1

    def __post_init__(self):
        if not isinstance(self.records, tuple) or any(not isinstance(r, NPCPresence) for r in self.records):
            raise ValueError("records must be a tuple of NPCPresence values")
        owners = [r.owner_id for r in self.records]
        if owners != sorted(owners) or len(owners) != len(set(owners)):
            raise ValueError("presence records must have unique sorted owners")
        if not isinstance(self.ticks, tuple):
            raise ValueError("ticks must be a tuple")
        tick_ids = [item[0] for item in self.ticks]
        if tick_ids != sorted(tick_ids) or len(tick_ids) != len(set(tick_ids)):
            raise ValueError("presence ticks must be unique and increasing")
        for tick, signature, records in self.ticks:
            if isinstance(tick, bool) or not isinstance(tick, int) or tick < 0 or not isinstance(signature, str) or not signature:
                raise ValueError("invalid presence tick history entry")
            if not isinstance(records, tuple) or any(not isinstance(r, NPCPresence) for r in records):
                raise ValueError("presence tick records must be NPCPresence values")
            owners = [r.owner_id for r in records]
            if owners != sorted(owners) or len(owners) != len(set(owners)):
                raise ValueError("presence tick records must have unique sorted owners")

    @classmethod
    def capture(cls, ledger):
        if not isinstance(ledger, PresenceLedger):
            raise TypeError("ledger must be a PresenceLedger")
        return cls(ledger.snapshot(), ledger.tick_snapshot())

    def to_json(self):
        payload = {"schema_version": self.SCHEMA_VERSION,
                   "records": [_record_payload(r) for r in self.records],
                   "ticks": [{"tick": tick, "signature": signature,
                              "records": [_record_payload(r) for r in records]}
                             for tick, signature, records in self.ticks]}
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)

    @classmethod
    def from_json(cls, payload):
        try:
            raw = json.loads(payload)
            if not isinstance(raw, dict) or raw.get("schema_version") != cls.SCHEMA_VERSION:
                raise ValueError("unsupported presence snapshot schema version")
            records = tuple(_read_record(item) for item in raw["records"])
            ticks = tuple((item["tick"], item["signature"],
                           tuple(_read_record(record) for record in item["records"]))
                          for item in raw["ticks"])
            result = cls(records, ticks)
            if result.to_json() != payload:
                raise ValueError("presence snapshot must use canonical JSON")
            return result
        except ValueError:
            raise
        except (TypeError, KeyError, json.JSONDecodeError) as exc:
            raise ValueError("invalid presence snapshot") from exc

    def restore(self):
        ledger = PresenceLedger(self.records)
        for tick, signature, records in self.ticks:
            ledger._restore_tick(tick, signature, records)
        return ledger
