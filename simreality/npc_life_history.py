"""Observer-owned autobiographical history with permanent facts and separate relationship repair.

Objective event references remain distinct from subjective interpretation. Memory
salience can fade for retrieval, but records are never deleted. Forgiveness and
reconciliation are separate append-only actions and do not mutate social trust.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math


def _text(name, value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _unit(name, value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError(f"{name} must be finite and in [0, 1]")


@dataclass(frozen=True)
class AutobiographicalMemory:
    memory_id: str
    owner_id: str
    event_id: str
    tick: int
    involved_npc_ids: tuple[str, ...]
    interpretation: str
    emotional_impact: float
    identity_impact: float
    conflict_ids: tuple[str, ...] = ()
    learning_decision_ids: tuple[str, ...] = ()
    turning_point: bool = False
    tags: tuple[str, ...] = ()

    def __post_init__(self):
        for name in ("memory_id", "owner_id", "event_id", "interpretation"):
            _text(name, getattr(self, name))
        if isinstance(self.tick, bool) or not isinstance(self.tick, int) or self.tick < 0:
            raise ValueError("tick must be a non-negative integer")
        _unit("emotional_impact", self.emotional_impact)
        if isinstance(self.identity_impact, bool) or not isinstance(self.identity_impact, (int, float)) or not math.isfinite(self.identity_impact) or not -1 <= self.identity_impact <= 1:
            raise ValueError("identity_impact must be finite and in [-1, 1]")
        if not isinstance(self.turning_point, bool):
            raise TypeError("turning_point must be bool")
        for name in ("involved_npc_ids", "conflict_ids", "learning_decision_ids", "tags"):
            values = getattr(self, name)
            if not isinstance(values, tuple) or any(not isinstance(x, str) or not x.strip() for x in values):
                raise ValueError(f"{name} must be a tuple of non-empty strings")
            if len(values) != len(set(values)):
                raise ValueError(f"{name} must not contain duplicates")
        if self.owner_id in self.involved_npc_ids:
            raise ValueError("owner belongs in the memory owner field, not involved_npc_ids")


@dataclass(frozen=True)
class PersonalHistoryAction:
    action_id: str
    owner_id: str
    target_id: str
    event_id: str
    action: str
    tick: int
    rationale: str = ""

    def __post_init__(self):
        for name in ("action_id", "owner_id", "target_id", "event_id"):
            _text(name, getattr(self, name))
        if self.owner_id == self.target_id:
            raise ValueError("owner and target must differ")
        if self.action not in ("forgive", "reconcile"):
            raise ValueError("action must be forgive or reconcile")
        if isinstance(self.tick, bool) or not isinstance(self.tick, int) or self.tick < 0:
            raise ValueError("tick must be a non-negative integer")
        if not isinstance(self.rationale, str):
            raise ValueError("rationale must be a string")


class NPCLifeHistory:
    """Append-only autobiographical memories and explicitly chosen repair actions."""
    def __init__(self, memories=(), actions=()):
        self._memories = {}
        self._actions = {}
        self._action_keys = set()
        for item in sorted(tuple(memories), key=lambda x: (x.tick, x.memory_id)):
            self.record(item)
        for item in sorted(tuple(actions), key=lambda x: (x.tick, x.action_id)):
            self._store_action(item)

    def record(self, memory):
        if not isinstance(memory, AutobiographicalMemory):
            raise TypeError("memory must be AutobiographicalMemory")
        prior = self._memories.get(memory.memory_id)
        if prior is not None:
            if prior != memory:
                raise ValueError("memory ID reused with different content")
            return prior
        self._memories[memory.memory_id] = memory
        return memory

    def _store_action(self, item):
        if not isinstance(item, PersonalHistoryAction):
            raise TypeError("item must be PersonalHistoryAction")
        key = (item.owner_id, item.target_id, item.event_id, item.action)
        prior = self._actions.get(item.action_id)
        if prior is not None:
            if prior != item:
                raise ValueError("action ID reused with conflicting content")
            return prior
        if key in self._action_keys:
            raise ValueError("this history action has already been recorded")
        memory = any(m.owner_id == item.owner_id and m.event_id == item.event_id
                     and item.target_id in m.involved_npc_ids for m in self._memories.values())
        if not memory:
            raise ValueError("action requires an autobiographical memory linking owner, event, and target")
        if any(m.owner_id == item.owner_id and m.event_id == item.event_id and m.tick > item.tick
               for m in self._memories.values()):
            raise ValueError("action cannot precede its memory")
        self._actions[item.action_id] = item
        self._action_keys.add(key)
        return item

    def act(self, action_id, owner_id, target_id, event_id, *, action, tick, rationale=""):
        item = PersonalHistoryAction(action_id, owner_id, target_id, event_id, action, tick, rationale)
        prior = self._actions.get(action_id)
        if prior is not None:
            if prior != item:
                raise ValueError("action ID reused with conflicting content")
            return prior
        return self._store_action(item)

    def memories(self, owner_id=None):
        values = self._memories.values()
        if owner_id is not None:
            values = (m for m in values if m.owner_id == owner_id)
        return tuple(sorted(values, key=lambda m: (m.tick, m.memory_id)))

    def actions(self, owner_id=None):
        values = self._actions.values()
        if owner_id is not None:
            values = (a for a in values if a.owner_id == owner_id)
        return tuple(sorted(values, key=lambda a: (a.tick, a.action_id)))

    def turning_points(self, owner_id):
        return tuple(m for m in self.memories(owner_id) if m.turning_point)

    def relationship_history(self, owner_id, target_id, event_id):
        actions = [a for a in self._actions.values()
                   if (a.owner_id, a.target_id, a.event_id) == (owner_id, target_id, event_id)]
        return {
            "forgiven": any(a.action == "forgive" for a in actions),
            "reconciled": any(a.action == "reconcile" for a in actions),
            "actions": tuple(sorted(actions, key=lambda a: (a.tick, a.action_id))),
        }

    def recall_salience(self, memory_id, current_tick, *, half_life_ticks):
        """Retrieval salience decays; the underlying autobiographical record does not."""
        if memory_id not in self._memories:
            raise KeyError(memory_id)
        if isinstance(current_tick, bool) or not isinstance(current_tick, int) or current_tick < 0:
            raise ValueError("current_tick must be a non-negative integer")
        if isinstance(half_life_ticks, bool) or not isinstance(half_life_ticks, (int, float)) or not math.isfinite(half_life_ticks) or half_life_ticks <= 0:
            raise ValueError("half_life_ticks must be positive and finite")
        memory = self._memories[memory_id]
        if current_tick < memory.tick:
            raise ValueError("current_tick cannot precede memory")
        if memory.turning_point:
            return 1.0
        return 2.0 ** (-(current_tick - memory.tick) / half_life_ticks)

    def snapshot(self):
        memories = tuple(tuple(getattr(m, f) for f in (
            "memory_id", "owner_id", "event_id", "tick", "involved_npc_ids",
            "interpretation", "emotional_impact", "identity_impact", "conflict_ids",
            "learning_decision_ids", "turning_point", "tags"))
            for m in sorted(self._memories.values(), key=lambda x: x.memory_id))
        actions = tuple(tuple(getattr(a, f) for f in (
            "action_id", "owner_id", "target_id", "event_id", "action", "tick", "rationale"))
            for a in sorted(self._actions.values(), key=lambda x: x.action_id))
        return LifeHistorySnapshot(memories, actions)


@dataclass(frozen=True)
class LifeHistorySnapshot:
    memories: tuple[tuple[object, ...], ...]
    actions: tuple[tuple[object, ...], ...]
    SCHEMA_VERSION = 1

    def __post_init__(self):
        if not isinstance(self.memories, tuple) or any(not isinstance(x, tuple) or len(x) != 12 for x in self.memories):
            raise ValueError("invalid life-history memories")
        if not isinstance(self.actions, tuple) or any(not isinstance(x, tuple) or len(x) != 7 for x in self.actions):
            raise ValueError("invalid life-history actions")
        memory_ids = [x[0] for x in self.memories]
        action_ids = [x[0] for x in self.actions]
        if memory_ids != sorted(set(memory_ids)) or action_ids != sorted(set(action_ids)):
            raise ValueError("snapshot IDs must be unique and sorted")
        NPCLifeHistory(tuple(AutobiographicalMemory(*x) for x in self.memories),
                       tuple(PersonalHistoryAction(*x) for x in self.actions))

    def to_json(self):
        return json.dumps({"schema_version": self.SCHEMA_VERSION,
                           "memories": [list(x) for x in self.memories],
                           "actions": [list(x) for x in self.actions]},
                          sort_keys=True, separators=(",", ":"), allow_nan=False)

    @classmethod
    def from_json(cls, payload):
        try:
            raw = json.loads(payload)
            if not isinstance(raw, dict) or raw.get("schema_version") != cls.SCHEMA_VERSION:
                raise ValueError("unsupported life-history schema")
            result = cls(tuple((x[0], x[1], x[2], x[3], tuple(x[4]), x[5], x[6], x[7],
                                tuple(x[8]), tuple(x[9]), x[10], tuple(x[11])) for x in raw["memories"]),
                         tuple(tuple(x) for x in raw["actions"]))
            if result.to_json() != payload:
                raise ValueError("snapshot must use canonical JSON")
            return result
        except (KeyError, TypeError, IndexError, json.JSONDecodeError) as exc:
            raise ValueError("invalid life-history snapshot") from exc

    def restore(self):
        return NPCLifeHistory(tuple(AutobiographicalMemory(*x) for x in self.memories),
                              tuple(PersonalHistoryAction(*x) for x in self.actions))
