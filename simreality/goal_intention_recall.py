"""Bounded, explainable recall of evidence-linked NPC goal experiences.

Recall never interprets prose or guesses what an experience means. Authored
per-goal rules assign signed influence to exact memory categories; age decay and
a hard aggregate bound prevent remembered events from becoming permanent locks.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math

from .goal_intention_memory import GoalIntentionMemoryLedger
from .goals import GoalBook
from .npc_life_history import NPCLifeHistory
from .npc_experience_transfer import NPCExperienceTransferLedger, experience_goal_guidance


_MEMORY_TYPES = frozenset({
    "adopted", "reopened", "completed", "failed", "abandoned", "blocked",
    "committed", "deferred", "plan_completed", "plan_failed",
    "plan_replanned", "personal_experience",
})


def _finite(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be finite numeric")
    return float(value)


@dataclass(frozen=True)
class GoalIntentionRecallRule:
    """Authored signed influence for memory categories belonging to one goal."""

    goal_id: str
    memory_type_weights: tuple[tuple[str, float], ...]
    half_life_ticks: float = 100.0
    max_adjustment: float = 0.25

    def __post_init__(self) -> None:
        if not isinstance(self.goal_id, str) or not self.goal_id.strip():
            raise ValueError("goal_id must be non-empty")
        if not isinstance(self.memory_type_weights, tuple):
            raise TypeError("memory_type_weights must be a tuple")
        seen = set()
        normalized = []
        for item in self.memory_type_weights:
            if not isinstance(item, tuple) or len(item) != 2:
                raise ValueError("memory weights must be (memory_type, weight) pairs")
            kind, raw_weight = item
            if not isinstance(kind, str) or kind not in _MEMORY_TYPES:
                raise ValueError(f"unsupported intention memory type: {kind}")
            if kind in seen:
                raise ValueError("memory types must not repeat")
            weight = _finite(raw_weight, "memory weight")
            if not -0.25 <= weight <= 0.25:
                raise ValueError("memory weights must be in [-0.25, 0.25]")
            seen.add(kind)
            normalized.append((kind, weight))
        half_life = _finite(self.half_life_ticks, "half_life_ticks")
        if half_life <= 0:
            raise ValueError("half_life_ticks must be positive")
        maximum = _finite(self.max_adjustment, "max_adjustment")
        if not 0.0 <= maximum <= 0.25:
            raise ValueError("max_adjustment must be in [0, 0.25]")
        object.__setattr__(self, "memory_type_weights", tuple(sorted(normalized)))
        object.__setattr__(self, "half_life_ticks", half_life)
        object.__setattr__(self, "max_adjustment", maximum)


@dataclass(frozen=True)
class GoalIntentionRecallEvidence:
    memory_id: str
    goal_id: str
    memory_type: str
    source_kind: str
    source_id: str
    evidence_ids: tuple[str, ...]
    content_digest: str
    age_ticks: int
    authored_weight: float
    decayed_contribution: float

    def __post_init__(self) -> None:
        for name in ("memory_id", "goal_id", "memory_type"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be non-empty")
        for name in ("source_kind", "source_id", "content_digest"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be non-empty")
        if self.source_kind not in {
            "goal_lifecycle", "goal_commitment", "plan_evaluation",
            "autobiographical_memory",
        }:
            raise ValueError("unsupported recall evidence source kind")
        allowed_types = {
            "goal_lifecycle": {"adopted", "reopened", "completed", "failed", "abandoned", "blocked"},
            "goal_commitment": {"committed", "deferred"},
            "plan_evaluation": {"plan_completed", "plan_failed", "plan_replanned"},
            "autobiographical_memory": {"personal_experience"},
        }
        if self.memory_type not in allowed_types[self.source_kind]:
            raise ValueError("recall memory type does not match its provenance source")
        if (len(self.content_digest) != 64
                or any(char not in "0123456789abcdef" for char in self.content_digest)):
            raise ValueError("content_digest must be a SHA-256 hex digest")
        if not isinstance(self.evidence_ids, tuple) or any(
            not isinstance(item, str) or not item.strip() for item in self.evidence_ids
        ):
            raise ValueError("evidence_ids must be a tuple of non-empty strings")
        if isinstance(self.age_ticks, bool) or not isinstance(self.age_ticks, int) or self.age_ticks < 0:
            raise ValueError("age_ticks must be non-negative")
        authored = _finite(self.authored_weight, "authored_weight")
        contribution = _finite(self.decayed_contribution, "decayed_contribution")
        if not -0.25 <= authored <= 0.25 or not -0.25 <= contribution <= 0.25:
            raise ValueError("recall evidence weights must be in [-0.25, 0.25]")


@dataclass(frozen=True)
class GoalIntentionStrategicEvidence:
    """Exact goal-tag evidence with its personal, witnessed, or reported source."""

    goal_id: str
    adjustment: float
    evidence_ids: tuple[str, ...]
    source_classes: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        if not isinstance(self.goal_id, str) or not self.goal_id.strip():
            raise ValueError("goal_id must be non-empty")
        adjustment = _finite(self.adjustment, "strategic experience adjustment")
        if not -0.25 <= adjustment <= 0.25:
            raise ValueError("strategic experience adjustment must be in [-0.25, 0.25]")
        if not isinstance(self.evidence_ids, tuple) or any(
            not isinstance(item, str) or not item.strip() for item in self.evidence_ids
        ):
            raise ValueError("evidence_ids must be a tuple of non-empty strings")
        if (not self.evidence_ids or self.evidence_ids != tuple(sorted(set(self.evidence_ids)))):
            raise ValueError("strategic evidence IDs must be unique and sorted")
        if not isinstance(self.source_classes, tuple) or any(
            not isinstance(item, tuple) or len(item) != 2
            or any(not isinstance(value, str) or not value.strip() for value in item)
            for item in self.source_classes
        ):
            raise ValueError("source_classes must contain non-empty (evidence_id, source_class) pairs")
        if tuple(sorted(self.source_classes)) != self.source_classes:
            raise ValueError("source classes must use canonical order")
        if {item[0] for item in self.source_classes} != set(self.evidence_ids):
            raise ValueError("every strategic evidence ID must have exactly one source class")
        if len(self.source_classes) != len(self.evidence_ids):
            raise ValueError("strategic source classes must not repeat evidence IDs")
        if any(source not in {"personal", "witnessed", "reported"}
               for _, source in self.source_classes):
            raise ValueError("unsupported strategic experience source class")


@dataclass(frozen=True)
class GoalIntentionRecall:
    owner_id: str
    tick: int
    adjustments: tuple[tuple[str, float], ...]
    evidence: tuple[GoalIntentionRecallEvidence, ...]
    recall_id: str
    strategic_evidence: tuple[GoalIntentionStrategicEvidence, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.owner_id, str) or not self.owner_id.strip():
            raise ValueError("owner_id must be non-empty")
        if isinstance(self.tick, bool) or not isinstance(self.tick, int) or self.tick < 0:
            raise ValueError("tick must be non-negative")
        if not isinstance(self.adjustments, tuple) or not isinstance(self.evidence, tuple):
            raise TypeError("adjustments and evidence must be tuples")
        if any(not isinstance(item, GoalIntentionRecallEvidence) for item in self.evidence):
            raise TypeError("evidence must contain GoalIntentionRecallEvidence values")
        if not isinstance(self.strategic_evidence, tuple) or any(
            not isinstance(item, GoalIntentionStrategicEvidence) for item in self.strategic_evidence
        ):
            raise TypeError("strategic_evidence must contain GoalIntentionStrategicEvidence values")
        strategic_goal_ids = [item.goal_id for item in self.strategic_evidence]
        if strategic_goal_ids != sorted(set(strategic_goal_ids)):
            raise ValueError("strategic evidence must have unique sorted goal IDs")
        if any(not isinstance(item, tuple) or len(item) != 2 for item in self.adjustments):
            raise ValueError("recall adjustments must be (goal_id, value) pairs")
        goal_ids = [item[0] for item in self.adjustments]
        if any(not isinstance(goal_id, str) or not goal_id.strip() for goal_id in goal_ids):
            raise ValueError("adjustment goal IDs must be non-empty")
        if goal_ids != sorted(set(goal_ids)):
            raise ValueError("recall adjustments must have unique sorted goal IDs")
        if any(item.goal_id not in goal_ids for item in self.evidence):
            raise ValueError("memory recall evidence must have a corresponding goal adjustment")
        if any(item.goal_id not in goal_ids for item in self.strategic_evidence):
            raise ValueError("strategic recall evidence must have a corresponding goal adjustment")
        for goal_id, value in self.adjustments:
            if not isinstance(goal_id, str) or not goal_id.strip():
                raise ValueError("adjustment goal IDs must be non-empty")
            if abs(_finite(value, "recall adjustment")) > 0.25:
                raise ValueError("recall adjustment must be in [-0.25, 0.25]")
        if any(item.age_ticks > self.tick for item in self.evidence):
            raise ValueError("recall evidence cannot come from the future")
        payload = {
            "owner": self.owner_id, "tick": self.tick,
            "adjustments": [list(item) for item in self.adjustments],
            "evidence": [
                [item.memory_id, item.goal_id, item.memory_type, item.source_kind,
                 item.source_id, list(item.evidence_ids), item.content_digest,
                 item.age_ticks, item.authored_weight, item.decayed_contribution]
                for item in self.evidence
            ],
            "strategic_evidence": [
                [item.goal_id, item.adjustment, list(item.evidence_ids),
                 [list(source) for source in item.source_classes]]
                for item in self.strategic_evidence
            ],
        }
        expected = hashlib.sha256(json.dumps(
            payload, sort_keys=True, separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")).hexdigest()
        if self.recall_id != expected:
            raise ValueError("recall_id does not match its deterministic evidence")


class GoalIntentionRecallAdapter:
    """Retrieve only explicitly weighted memories for the requested NPC."""

    @staticmethod
    def recall(
        ledger: GoalIntentionMemoryLedger,
        goals: GoalBook,
        owner_id: str,
        current_tick: int,
        *,
        rules: tuple[GoalIntentionRecallRule, ...],
        life_history: NPCLifeHistory | None = None,
        experience_transfers: NPCExperienceTransferLedger | None = None,
    ) -> GoalIntentionRecall:
        if not isinstance(ledger, GoalIntentionMemoryLedger):
            raise TypeError("ledger must be GoalIntentionMemoryLedger")
        if not isinstance(goals, GoalBook):
            raise TypeError("goals must be GoalBook")
        if not isinstance(owner_id, str) or not owner_id.strip():
            raise ValueError("owner_id must be non-empty")
        if isinstance(current_tick, bool) or not isinstance(current_tick, int) or current_tick < 0:
            raise ValueError("current_tick must be non-negative")
        if not isinstance(rules, tuple) or any(
            not isinstance(item, GoalIntentionRecallRule) for item in rules
        ):
            raise TypeError("rules must be a tuple of GoalIntentionRecallRule values")
        if len({item.goal_id for item in rules}) != len(rules):
            raise ValueError("each goal may have only one recall rule")
        if (life_history is None) != (experience_transfers is None):
            raise ValueError("life_history and experience_transfers must be supplied together")
        if life_history is not None and not isinstance(life_history, NPCLifeHistory):
            raise TypeError("life_history must be NPCLifeHistory")
        if experience_transfers is not None and not isinstance(
            experience_transfers, NPCExperienceTransferLedger
        ):
            raise TypeError("experience_transfers must be NPCExperienceTransferLedger")
        rule_map = {item.goal_id: item for item in rules}
        for goal_id in rule_map:
            goal = goals.goals.get(goal_id)
            if goal is None or goal.owner_id != owner_id:
                raise ValueError("recall rules must reference goals owned by the NPC")

        strategic_records = []
        strategic_adjustments = {}
        strategic_memory_keys = set()
        if life_history is not None and experience_transfers is not None:
            raw_adjustments, raw_evidence_ids, raw_sources = experience_goal_guidance(
                life_history, experience_transfers, owner_id, current_tick, goals,
            )
            for goal_id in sorted(raw_adjustments):
                evidence_ids = tuple(sorted(raw_evidence_ids[goal_id]))
                source_classes = tuple(sorted(
                    (evidence_id, raw_sources[evidence_id]) for evidence_id in evidence_ids
                ))
                strategic_records.append(GoalIntentionStrategicEvidence(
                    goal_id, raw_adjustments[goal_id], evidence_ids, source_classes,
                ))
                strategic_adjustments[goal_id] = raw_adjustments[goal_id]
                strategic_memory_keys.update(
                    (goal_id, evidence_id)
                    for evidence_id, source_class in source_classes
                    if source_class in {"personal", "witnessed"}
                )

        totals = {goal_id: 0.0 for goal_id in rule_map}
        evidence = []
        for memory in ledger.entries(owner_id=owner_id):
            goal = goals.goals.get(memory.goal_id)
            if goal is None or goal.owner_id != owner_id:
                raise ValueError("intention memory references an unknown goal or foreign owner")
            if memory.tick > current_tick:
                raise ValueError("intention memory cannot be recalled before it occurred")
            if (memory.memory_type == "personal_experience"
                    and (memory.goal_id, memory.source_id) in strategic_memory_keys):
                continue
            rule = rule_map.get(memory.goal_id)
            if rule is None:
                continue
            weight = dict(rule.memory_type_weights).get(memory.memory_type)
            if weight is None or weight == 0.0:
                continue
            age = current_tick - memory.tick
            contribution = weight * (2.0 ** (-age / rule.half_life_ticks))
            totals[memory.goal_id] += contribution
            evidence.append(GoalIntentionRecallEvidence(
                memory.memory_id, memory.goal_id, memory.memory_type,
                memory.source_kind, memory.source_id, tuple(memory.evidence_ids),
                hashlib.sha256(memory.content.encode("utf-8")).hexdigest(),
                age, weight, contribution,
            ))

        all_goal_ids = set(totals) | set(strategic_adjustments)
        adjustments = tuple(sorted(
            (
                goal_id,
                max(
                    -rule_map[goal_id].max_adjustment if goal_id in rule_map else -0.25,
                    min(
                        rule_map[goal_id].max_adjustment if goal_id in rule_map else 0.25,
                        totals.get(goal_id, 0.0) + strategic_adjustments.get(goal_id, 0.0),
                    ),
                ),
            )
            for goal_id in all_goal_ids
        ))
        evidence.sort(key=lambda item: (item.goal_id, item.age_ticks, item.memory_id))
        payload = {
            "owner": owner_id, "tick": current_tick,
            "adjustments": [list(item) for item in adjustments],
            "evidence": [
                [item.memory_id, item.goal_id, item.memory_type, item.source_kind,
                 item.source_id, list(item.evidence_ids), item.content_digest,
                 item.age_ticks, item.authored_weight, item.decayed_contribution]
                for item in evidence
            ],
            "strategic_evidence": [
                [item.goal_id, item.adjustment, list(item.evidence_ids),
                 [list(source) for source in item.source_classes]]
                for item in strategic_records
            ],
        }
        recall_id = hashlib.sha256(json.dumps(
            payload, sort_keys=True, separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")).hexdigest()
        return GoalIntentionRecall(
            owner_id, current_tick, adjustments, tuple(evidence), recall_id,
            tuple(strategic_records),
        )
