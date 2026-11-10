"""Owner-scoped, cue-driven retrieval of autobiographical memories.

Recall is a read-only projection. Explicit cue rules determine which memories
are eligible; salience and authored emotional weighting rank them. No memory
is invented, shared across owners, deleted, or applied as an action.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping

from .npc_life_history import AutobiographicalMemory, NPCLifeHistory


def _text(name, value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _unit(name, value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError(f"{name} must be finite and in [0, 1]")


@dataclass(frozen=True)
class MemoryRecallRule:
    rule_id: str
    cue_id: str
    tag: str | None = None
    involved_npc_id: str | None = None
    sensitivity: float = 1.0

    def __post_init__(self):
        _text("rule_id", self.rule_id)
        _text("cue_id", self.cue_id)
        for name in ("tag", "involved_npc_id"):
            value = getattr(self, name)
            if value is not None:
                _text(name, value)
        _unit("sensitivity", self.sensitivity)
        if self.tag is None and self.involved_npc_id is None:
            raise ValueError("a recall rule must specify a memory tag or involved NPC")


@dataclass(frozen=True)
class MemoryRecallProfile:
    owner_id: str
    rules: tuple[MemoryRecallRule, ...]
    emotional_weight: float = 0.0

    def __post_init__(self):
        _text("owner_id", self.owner_id)
        if not isinstance(self.rules, tuple) or any(not isinstance(x, MemoryRecallRule) for x in self.rules):
            raise TypeError("rules must be a tuple of MemoryRecallRule values")
        ids = [rule.rule_id for rule in self.rules]
        if len(ids) != len(set(ids)):
            raise ValueError("recall rule IDs must be unique per owner")
        _unit("emotional_weight", self.emotional_weight)


@dataclass(frozen=True)
class RecalledMemory:
    memory: AutobiographicalMemory
    score: float
    matched_cues: tuple[str, ...]
    matched_rules: tuple[str, ...]


@dataclass(frozen=True)
class MemoryRecallResult:
    owner_id: str
    current_tick: int
    recalled: tuple[RecalledMemory, ...]


class NPCMemoryRecallAdapter:
    """Retrieve only memories owned by the NPC and explicitly associated with observed cues."""

    @staticmethod
    def recall(
        profile: MemoryRecallProfile,
        history: NPCLifeHistory,
        observed_cues: Mapping[str, float],
        current_tick: int,
        *,
        half_life_ticks: float,
        minimum_score: float = 0.0,
        top_k: int = 5,
    ) -> MemoryRecallResult:
        if not isinstance(profile, MemoryRecallProfile):
            raise TypeError("profile must be MemoryRecallProfile")
        if not isinstance(history, NPCLifeHistory):
            raise TypeError("history must be NPCLifeHistory")
        if not isinstance(observed_cues, Mapping):
            raise TypeError("observed_cues must be a mapping of cue IDs to exposure")
        for cue, exposure in observed_cues.items():
            _text("cue ID", cue)
            _unit("cue exposure", exposure)
        _unit("minimum_score", minimum_score)
        if isinstance(current_tick, bool) or not isinstance(current_tick, int) or current_tick < 0:
            raise ValueError("current_tick must be a non-negative integer")
        if isinstance(half_life_ticks, bool) or not isinstance(half_life_ticks, (int, float)) or not math.isfinite(half_life_ticks) or half_life_ticks <= 0:
            raise ValueError("half_life_ticks must be positive and finite")
        if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 1:
            raise ValueError("top_k must be a positive integer")

        rules_by_cue = {}
        for rule in profile.rules:
            rules_by_cue.setdefault(rule.cue_id, []).append(rule)
        results = []
        for memory in history.memories(profile.owner_id):
            matches = []
            for cue_id, exposure in sorted(observed_cues.items()):
                if exposure <= 0:
                    continue
                for rule in sorted(rules_by_cue.get(cue_id, ()), key=lambda x: x.rule_id):
                    if rule.tag is not None and rule.tag not in memory.tags:
                        continue
                    if rule.involved_npc_id is not None and rule.involved_npc_id not in memory.involved_npc_ids:
                        continue
                    matches.append((cue_id, rule.rule_id, exposure * rule.sensitivity))
            if not matches:
                continue
            cue_strength = max(item[2] for item in matches)
            salience = history.recall_salience(
                memory.memory_id, current_tick, half_life_ticks=half_life_ticks,
            )
            emotional_factor = 1.0 + profile.emotional_weight * memory.emotional_impact
            score = min(1.0, cue_strength * salience * emotional_factor)
            if score < minimum_score:
                continue
            results.append(RecalledMemory(
                memory=memory,
                score=score,
                matched_cues=tuple(sorted({item[0] for item in matches})),
                matched_rules=tuple(sorted({item[1] for item in matches})),
            ))
        results.sort(key=lambda item: (-item.score, -item.memory.tick, item.memory.memory_id))
        return MemoryRecallResult(profile.owner_id, current_tick, tuple(results[:top_k]))
