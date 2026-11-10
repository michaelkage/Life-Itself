"""Append-only reinterpretation history for immutable autobiographical memories.

A reflection changes the owner's current understanding, never the original
memory record or the authoritative world event it references.
"""
from __future__ import annotations

from dataclasses import dataclass
import json

from .npc_life_history import NPCLifeHistory


def _text(name, value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


@dataclass(frozen=True)
class MemoryReinterpretation:
    reflection_id: str
    owner_id: str
    memory_id: str
    tick: int
    previous_interpretation: str
    new_interpretation: str
    rationale: str

    def __post_init__(self):
        for name in ("reflection_id", "owner_id", "memory_id",
                     "previous_interpretation", "new_interpretation", "rationale"):
            _text(name, getattr(self, name))
        if self.previous_interpretation == self.new_interpretation:
            raise ValueError("reinterpretation must change the interpretation")
        if isinstance(self.tick, bool) or not isinstance(self.tick, int) or self.tick < 0:
            raise ValueError("tick must be a non-negative integer")


class MemoryReflectionLedger:
    """Store owner-authored reinterpretations without rewriting memory facts."""

    def __init__(self, history: NPCLifeHistory, entries=()):
        if not isinstance(history, NPCLifeHistory):
            raise TypeError("history must be NPCLifeHistory")
        self.history = history
        self._entries = {}
        self._keys = set()
        for entry in sorted(tuple(entries), key=lambda x: (x.tick, x.reflection_id)):
            self.record(entry)

    def current_interpretation(self, owner_id, memory_id):
        memory = self._memory(owner_id, memory_id)
        entries = [x for x in self._entries.values()
                   if x.owner_id == owner_id and x.memory_id == memory_id]
        if not entries:
            return memory.interpretation
        return max(entries, key=lambda x: (x.tick, x.reflection_id)).new_interpretation

    def _memory(self, owner_id, memory_id):
        _text("owner_id", owner_id)
        _text("memory_id", memory_id)
        for memory in self.history.memories(owner_id):
            if memory.memory_id == memory_id:
                return memory
        raise KeyError(memory_id)

    def record(self, entry: MemoryReinterpretation):
        if not isinstance(entry, MemoryReinterpretation):
            raise TypeError("entry must be MemoryReinterpretation")
        memory = self._memory(entry.owner_id, entry.memory_id)
        if entry.tick < memory.tick:
            raise ValueError("reflection cannot precede its source memory")
        prior = self._entries.get(entry.reflection_id)
        if prior is not None:
            if prior != entry:
                raise ValueError("reflection ID reused with conflicting content")
            return prior
        key = (entry.owner_id, entry.memory_id, entry.tick)
        if key in self._keys:
            raise ValueError("only one reinterpretation per memory and tick is allowed")
        expected = self.current_interpretation(entry.owner_id, entry.memory_id)
        if entry.previous_interpretation != expected:
            raise ValueError("previous_interpretation does not match the current interpretation")
        if any(x.owner_id == entry.owner_id and x.memory_id == entry.memory_id
               and x.tick > entry.tick for x in self._entries.values()):
            raise ValueError("reinterpretations must be recorded in chronological order")
        self._entries[entry.reflection_id] = entry
        self._keys.add(key)
        return entry

    def entries(self, owner_id=None, memory_id=None):
        values = self._entries.values()
        if owner_id is not None:
            values = (x for x in values if x.owner_id == owner_id)
        if memory_id is not None:
            values = (x for x in values if x.memory_id == memory_id)
        return tuple(sorted(values, key=lambda x: (x.tick, x.reflection_id)))

    def snapshot(self):
        records = tuple(tuple(getattr(x, field) for field in (
            "reflection_id", "owner_id", "memory_id", "tick",
            "previous_interpretation", "new_interpretation", "rationale",
        )) for x in sorted(self._entries.values(), key=lambda x: x.reflection_id))
        return MemoryReflectionSnapshot(records)


@dataclass(frozen=True)
class MemoryReflectionSnapshot:
    records: tuple[tuple[object, ...], ...]
    SCHEMA_VERSION = 1

    def __post_init__(self):
        if not isinstance(self.records, tuple) or any(not isinstance(x, tuple) or len(x) != 7 for x in self.records):
            raise ValueError("invalid memory reflection records")
        ids = [x[0] for x in self.records]
        if ids != sorted(set(ids)):
            raise ValueError("reflection IDs must be unique and sorted")
        if any(not isinstance(x[3], int) or isinstance(x[3], bool) for x in self.records):
            raise ValueError("reflection ticks must be integers")
        for record in self.records:
            MemoryReinterpretation(*record)

    def to_json(self):
        return json.dumps({"schema_version": self.SCHEMA_VERSION,
                           "records": [list(x) for x in self.records]},
                          sort_keys=True, separators=(",", ":"), allow_nan=False)

    @classmethod
    def from_json(cls, payload):
        try:
            raw = json.loads(payload)
            if not isinstance(raw, dict) or raw.get("schema_version") != cls.SCHEMA_VERSION:
                raise ValueError("unsupported memory reflection schema")
            result = cls(tuple(tuple(x) for x in raw["records"]))
            if result.to_json() != payload:
                raise ValueError("snapshot must use canonical JSON")
            return result
        except (KeyError, TypeError, IndexError, json.JSONDecodeError) as exc:
            raise ValueError("invalid memory reflection snapshot") from exc

    def restore(self, history):
        return MemoryReflectionLedger(
            history, tuple(MemoryReinterpretation(*x) for x in self.records),
        )
