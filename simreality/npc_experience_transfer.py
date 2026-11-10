"""Evidence-grounded transfer of NPC experiences without false autobiography.

A recipient receives a reported account, never a personal memory. Both the
original experience and the later communication must exist in the authoritative
world journal. The source autobiographical record remains immutable.
"""
from __future__ import annotations
from dataclasses import dataclass
import json
import math
from .npc_life_history import NPCLifeHistory
from .world_events import WorldEventLedger


@dataclass(frozen=True)
class ReportedExperience:
    transfer_id: str
    recipient_id: str
    source_npc_id: str
    source_memory_id: str
    source_event_id: str
    communication_event_id: str
    source_tick: int
    transfer_tick: int
    account: str
    source_role: str
    confidence: float

    def __post_init__(self):
        for name in ("transfer_id", "recipient_id", "source_npc_id", "source_memory_id",
                     "source_event_id", "communication_event_id", "account"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if self.recipient_id == self.source_npc_id:
            raise ValueError("recipient and source NPC must differ")
        for name in ("source_tick", "transfer_tick"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if self.source_tick > self.transfer_tick:
            raise ValueError("reported experience cannot precede its source")
        if self.source_role not in ("participant", "witness"):
            raise ValueError("source_role must be participant or witness")
        if (isinstance(self.confidence, bool) or not isinstance(self.confidence, (int, float))
                or not math.isfinite(self.confidence) or not 0 <= self.confidence <= 1):
            raise ValueError("confidence must be finite and in [0, 1]")


@dataclass(frozen=True)
class ExperienceTransferSnapshot:
    records: tuple[ReportedExperience, ...]

    def __post_init__(self):
        if not isinstance(self.records, tuple) or any(not isinstance(x, ReportedExperience) for x in self.records):
            raise TypeError("records must be a tuple of ReportedExperience")
        ids = [x.transfer_id for x in self.records]
        if ids != sorted(set(ids)):
            raise ValueError("transfer IDs must be unique and sorted")

    def to_json(self):
        return json.dumps({"schema_version": 1, "records": [
            {name: getattr(x, name) for name in (
                "transfer_id", "recipient_id", "source_npc_id", "source_memory_id",
                "source_event_id", "communication_event_id", "source_tick",
                "transfer_tick", "account", "source_role", "confidence")}
            for x in self.records]}, sort_keys=True, separators=(",", ":"), allow_nan=False)

    @classmethod
    def from_json(cls, payload):
        try:
            raw = json.loads(payload)
            if not isinstance(raw, dict) or raw.get("schema_version") != 1:
                raise ValueError("unsupported experience-transfer schema")
            result = cls(tuple(ReportedExperience(**x) for x in raw["records"]))
            if result.to_json() != payload:
                raise ValueError("snapshot must use canonical JSON")
            return result
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError("invalid experience-transfer snapshot") from exc


class NPCExperienceTransferLedger:
    """Append-only reported-experience records validated against source evidence."""
    def __init__(self, events: WorldEventLedger, history: NPCLifeHistory, snapshot=None):
        if not isinstance(events, WorldEventLedger):
            raise TypeError("events must be a WorldEventLedger")
        if not isinstance(history, NPCLifeHistory):
            raise TypeError("history must be an NPCLifeHistory")
        self.events, self.history = events, history
        self._records = {}
        if snapshot is not None:
            if not isinstance(snapshot, ExperienceTransferSnapshot):
                raise TypeError("snapshot must be an ExperienceTransferSnapshot")
            for record in snapshot.records:
                self._validate(record)
                self._insert(record)

    def _validate(self, record):
        memory = next((m for m in self.history.memories(record.source_npc_id)
                       if m.memory_id == record.source_memory_id), None)
        if memory is None:
            raise ValueError("transfer requires a source-owned autobiographical memory")
        if memory.event_id != record.source_event_id or memory.tick != record.source_tick:
            raise ValueError("transfer source memory provenance does not match")
        source = self.events.get(record.source_event_id)
        if source.tick != record.source_tick:
            raise ValueError("source event tick does not match memory")
        role = ("participant" if record.source_npc_id in source.participants else
                "witness" if record.source_npc_id in source.witnesses else "")
        if role != record.source_role:
            raise ValueError("source role does not match authoritative event")
        communication = self.events.get(record.communication_event_id)
        if communication.tick != record.transfer_tick:
            raise ValueError("communication event tick does not match transfer")
        if (record.source_npc_id not in communication.participants or
                record.recipient_id not in communication.participants):
            raise ValueError("communication event must include source and recipient")
        if communication.tick < source.tick:
            raise ValueError("communication cannot precede source experience")

    def _insert(self, record):
        prior = self._records.get(record.transfer_id)
        if prior is not None and prior != record:
            raise ValueError("transfer ID reused with different content")
        if prior is None and any(
            (x.recipient_id, x.source_npc_id, x.source_memory_id, x.communication_event_id) ==
            (record.recipient_id, record.source_npc_id, record.source_memory_id, record.communication_event_id)
            for x in self._records.values()
        ):
            raise ValueError("experience has already been transferred in this communication")
        self._records.setdefault(record.transfer_id, record)
        return self._records[record.transfer_id]

    def transfer(self, transfer_id, recipient_id, source_npc_id, source_memory_id,
                 communication_event_id, *, confidence):
        memory = next((m for m in self.history.memories(source_npc_id)
                       if m.memory_id == source_memory_id), None)
        if memory is None:
            raise ValueError("transfer requires a source-owned autobiographical memory")
        source = self.events.get(memory.event_id)
        role = ("participant" if source_npc_id in source.participants else
                "witness" if source_npc_id in source.witnesses else "")
        communication = self.events.get(communication_event_id)
        record = ReportedExperience(
            transfer_id, recipient_id, source_npc_id, source_memory_id, memory.event_id,
            communication_event_id, memory.tick, communication.tick, memory.interpretation,
            role, confidence)
        self._validate(record)
        return self._insert(record)

    def received_by(self, recipient_id):
        return tuple(sorted((x for x in self._records.values() if x.recipient_id == recipient_id),
                            key=lambda x: (x.transfer_tick, x.transfer_id)))

    def snapshot(self):
        return ExperienceTransferSnapshot(tuple(self._records[k] for k in sorted(self._records)))
