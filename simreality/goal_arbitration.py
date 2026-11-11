"""Deterministic arbitration and explicit temporary commitment between NPC goals.

Assessment is read-only. A commitment selects one currently actionable goal and
records the competing ambitions as deferred, without changing their lifecycle
status or erasing their history.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Mapping

from .goals import GoalBook, GoalStatus
from .identity_context import NPCEmotionalState


def _finite(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be finite numeric")
    return float(value)


@dataclass(frozen=True)
class GoalArbitrationRule:
    """Authored mapping from need, emotion, values, and resource costs to one goal."""
    goal_id: str
    need_axis: str | None = None
    emotion_axis: str | None = None
    value_axis: str | None = None
    need_weight: float = 0.0
    emotion_weight: float = 0.0
    value_weight: float = 0.0
    importance: float = 0.0
    resource_costs: tuple[tuple[str, float], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.goal_id, str) or not self.goal_id.strip():
            raise ValueError("goal_id must be non-empty")
        for name in ("need_axis", "emotion_axis", "value_axis"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{name} must be non-empty when supplied")
        for name in ("need_weight", "emotion_weight", "value_weight", "importance"):
            value = _finite(getattr(self, name), name)
            if not -1.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [-1, 1]")
        for name, weight in (("need_axis", self.need_weight),
                             ("emotion_axis", self.emotion_weight),
                             ("value_axis", self.value_weight)):
            if getattr(self, name) is None and weight != 0:
                raise ValueError(f"{name} is required when its weight is non-zero")
        if not isinstance(self.resource_costs, tuple):
            raise TypeError("resource_costs must be a tuple")
        names = []
        for item in self.resource_costs:
            if not isinstance(item, tuple) or len(item) != 2:
                raise ValueError("resource costs must be (resource, amount) pairs")
            resource, amount = item
            if not isinstance(resource, str) or not resource.strip():
                raise ValueError("resource names must be non-empty")
            amount = _finite(amount, "resource cost")
            if amount < 0:
                raise ValueError("resource costs cannot be negative")
            names.append(resource)
        if len(names) != len(set(names)):
            raise ValueError("resource costs must not repeat a resource")
        object.__setattr__(self, "resource_costs",
                           tuple(sorted((name, float(amount)) for name, amount in self.resource_costs)))


@dataclass(frozen=True)
class GoalArbitrationCandidate:
    goal_id: str
    score: float
    base_priority_score: float
    need_contribution: float
    emotion_contribution: float
    value_contribution: float
    importance_contribution: float
    feasible: bool
    feasibility_reason: str
    resource_costs: tuple[tuple[str, float], ...]

    def __post_init__(self) -> None:
        if not isinstance(self.goal_id, str) or not self.goal_id.strip():
            raise ValueError("goal_id must be non-empty")
        for name in ("score", "base_priority_score", "need_contribution",
                     "emotion_contribution", "value_contribution",
                     "importance_contribution"):
            value = _finite(getattr(self, name), name)
            if name in {"score", "base_priority_score"} and not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0, 1]")
        if not isinstance(self.feasible, bool):
            raise TypeError("feasible must be bool")
        if not isinstance(self.feasibility_reason, str):
            raise ValueError("feasibility_reason must be a string")


@dataclass(frozen=True)
class GoalArbitrationAssessment:
    owner_id: str
    tick: int
    candidates: tuple[GoalArbitrationCandidate, ...]
    selected_goal_id: str | None
    deferred_goal_ids: tuple[str, ...]
    goal_snapshot: tuple[tuple[object, ...], ...]
    assessment_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.owner_id, str) or not self.owner_id.strip():
            raise ValueError("owner_id must be non-empty")
        if isinstance(self.tick, bool) or not isinstance(self.tick, int) or self.tick < 0:
            raise ValueError("tick must be non-negative")
        if not isinstance(self.candidates, tuple) or any(
            not isinstance(item, GoalArbitrationCandidate) for item in self.candidates
        ):
            raise TypeError("candidates must be a tuple of GoalArbitrationCandidate values")
        if not isinstance(self.deferred_goal_ids, tuple):
            raise TypeError("deferred_goal_ids must be a tuple")
        if not isinstance(self.goal_snapshot, tuple):
            raise TypeError("goal_snapshot must be a tuple")
        ids = [item.goal_id for item in self.candidates]
        if len(ids) != len(set(ids)):
            raise ValueError("arbitration candidate goal IDs must be unique")
        if self.selected_goal_id is not None and self.selected_goal_id not in ids:
            raise ValueError("selected goal must be one of the candidates")
        if self.selected_goal_id is not None and not next(
            item for item in self.candidates if item.goal_id == self.selected_goal_id
        ).feasible:
            raise ValueError("selected goal must be resource-feasible")
        if tuple(x for x in ids if x != self.selected_goal_id) != self.deferred_goal_ids:
            raise ValueError("deferred goals must preserve candidate order")
        if not isinstance(self.assessment_id, str) or len(self.assessment_id) != 64:
            raise ValueError("assessment_id must be a SHA-256 hex digest")

    @property
    def actionable(self) -> bool:
        return self.selected_goal_id is not None

    @property
    def selected(self) -> GoalArbitrationCandidate | None:
        return next((item for item in self.candidates
                     if item.goal_id == self.selected_goal_id), None)


class GoalArbitrationEvaluator:
    """Rank currently actionable goals using explicit, inspectable appraisal inputs."""

    @staticmethod
    def assess(
        goals: GoalBook,
        owner_id: str,
        current_tick: int,
        *,
        rules: tuple[GoalArbitrationRule, ...] = (),
        need_deficits: Mapping[str, float] | None = None,
        emotional_state: NPCEmotionalState | None = None,
        value_alignment: Mapping[str, float] | None = None,
        resources: Mapping[str, float] | None = None,
        experience_adjustments: Mapping[str, float] | None = None,
    ) -> GoalArbitrationAssessment:
        if not isinstance(goals, GoalBook):
            raise TypeError("goals must be GoalBook")
        if not isinstance(owner_id, str) or not owner_id.strip():
            raise ValueError("owner_id must be non-empty")
        if isinstance(current_tick, bool) or not isinstance(current_tick, int) or current_tick < 0:
            raise ValueError("current_tick must be non-negative")
        if not isinstance(rules, tuple) or any(not isinstance(x, GoalArbitrationRule) for x in rules):
            raise TypeError("rules must be a tuple of GoalArbitrationRule values")
        if len({x.goal_id for x in rules}) != len(rules):
            raise ValueError("each goal may have only one arbitration rule")
        rule_map = {x.goal_id: x for x in rules}
        for goal_id in rule_map:
            if goal_id not in goals.goals or goals.goals[goal_id].owner_id != owner_id:
                raise ValueError("arbitration rules must reference goals owned by the NPC")
        if emotional_state is not None:
            if not isinstance(emotional_state, NPCEmotionalState) or emotional_state.npc_id != owner_id:
                raise ValueError("emotional state owner must match")
            if emotional_state.sampled_tick > current_tick:
                raise ValueError("emotional state cannot come from the future")

        def axis_map(values: Mapping[str, float] | None, label: str,
                     low: float, high: float) -> dict[str, float]:
            if values is None:
                return {}
            if not isinstance(values, Mapping):
                raise TypeError(f"{label} must be a mapping")
            result = {}
            for key, raw in values.items():
                if not isinstance(key, str) or not key.strip():
                    raise ValueError(f"{label} keys must be non-empty strings")
                value = _finite(raw, label)
                if not low <= value <= high:
                    raise ValueError(f"{label} values must be in [{low}, {high}]")
                result[key] = value
            return result

        needs = axis_map(need_deficits, "need deficits", 0.0, 1.0)
        values = axis_map(value_alignment, "value alignment", -1.0, 1.0)
        balances = axis_map(resources, "resources", 0.0, float("inf"))
        experience = axis_map(experience_adjustments, "experience adjustments", -0.25, 0.25)
        if any(goal_id not in goals.goals or goals.goals[goal_id].owner_id != owner_id
               for goal_id in experience):
            raise ValueError("experience adjustments must reference goals owned by the NPC")
        emotions = dict(emotional_state.intensities) if emotional_state else {}
        owner_goals = sorted(
            (goal for goal in goals.goals.values() if goal.owner_id == owner_id
             and goal.status == GoalStatus.ACTIVE),
            key=lambda item: item.goal_id,
        )
        candidates = []
        for goal in owner_goals:
            evaluation = goals.evaluate(goal.goal_id, current_tick, experience)
            if not evaluation.actionable:
                continue
            rule = rule_map.get(goal.goal_id)
            base = evaluation.score / (1.0 + evaluation.score)
            need = 0.0 if rule is None or rule.need_axis is None else (
                0.20 * rule.need_weight * needs.get(rule.need_axis, 0.0))
            emotion = 0.0 if rule is None or rule.emotion_axis is None else (
                0.20 * rule.emotion_weight * emotions.get(rule.emotion_axis, 0.0))
            value = 0.0 if rule is None or rule.value_axis is None else (
                0.20 * rule.value_weight * values.get(rule.value_axis, 0.0))
            importance = 0.10 * (rule.importance if rule else 0.0)
            costs = rule.resource_costs if rule else ()
            shortages = [(name, amount, balances.get(name, 0.0))
                         for name, amount in costs
                         if balances.get(name, 0.0) + 1e-12 < amount]
            feasible = not shortages
            reason = ("resources available" if feasible else
                      "; ".join(f"needs {amount:g} {name}, has {available:g}"
                                for name, amount, available in shortages))
            score = max(0.0, min(1.0, base + need + emotion + value + importance))
            candidates.append(GoalArbitrationCandidate(
                goal.goal_id, score, base, need, emotion, value, importance,
                feasible, reason, tuple(costs),
            ))
        candidates.sort(key=lambda item: (
            not item.feasible, -item.score, -item.base_priority_score, item.goal_id
        ))
        selected = next((item.goal_id for item in candidates if item.feasible), None)
        deferred = tuple(item.goal_id for item in candidates if item.goal_id != selected)
        snapshot = tuple(item for item in goals.snapshot() if item[1] == owner_id)
        canonical = {
            "owner": owner_id, "tick": current_tick,
            "goals": [list(item) for item in snapshot],
            "inputs": {
                "need_deficits": sorted(needs.items()),
                "emotions": sorted(emotions.items()),
                "value_alignment": sorted(values.items()),
                "resources": sorted(balances.items()),
                "experience_adjustments": sorted(experience.items()),
                "rules": [
                    [rule.goal_id, rule.need_axis, rule.emotion_axis, rule.value_axis,
                     rule.need_weight, rule.emotion_weight, rule.value_weight,
                     rule.importance, [list(cost) for cost in rule.resource_costs]]
                    for rule in rules
                ],
            },
            "candidates": [
                [x.goal_id, x.score, x.base_priority_score, x.need_contribution,
                 x.emotion_contribution, x.value_contribution,
                 x.importance_contribution, x.feasible, x.feasibility_reason,
                 [list(cost) for cost in x.resource_costs]]
                for x in candidates
            ],
            "selected": selected, "deferred": list(deferred),
        }
        assessment_id = hashlib.sha256(json.dumps(
            canonical, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")).hexdigest()
        return GoalArbitrationAssessment(
            owner_id, current_tick, tuple(candidates), selected, deferred,
            snapshot, assessment_id,
        )


@dataclass(frozen=True)
class GoalCommitment:
    commitment_id: str
    assessment_id: str
    owner_id: str
    tick: int
    selected_goal_id: str
    deferred_goal_ids: tuple[str, ...]
    selected_score: float
    rationale: str

    def __post_init__(self) -> None:
        for name in ("commitment_id", "assessment_id", "owner_id",
                     "selected_goal_id", "rationale"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be non-empty")
        if isinstance(self.tick, bool) or not isinstance(self.tick, int) or self.tick < 0:
            raise ValueError("tick must be non-negative")
        if not math.isfinite(self.selected_score) or not 0.0 <= self.selected_score <= 1.0:
            raise ValueError("selected_score must be finite and in [0, 1]")
        if not isinstance(self.deferred_goal_ids, tuple) or any(
            not isinstance(goal_id, str) or not goal_id.strip()
            for goal_id in self.deferred_goal_ids
        ):
            raise ValueError("deferred_goal_ids must be a tuple of non-empty goal IDs")
        if len(set(self.deferred_goal_ids)) != len(self.deferred_goal_ids):
            raise ValueError("deferred goal IDs must be unique")
        if len(self.assessment_id) != 64 or any(c not in "0123456789abcdef" for c in self.assessment_id):
            raise ValueError("assessment_id must be a SHA-256 hex digest")
        if len(self.commitment_id) != 64 or any(c not in "0123456789abcdef" for c in self.commitment_id):
            raise ValueError("commitment_id must be a SHA-256 hex digest")
        if self.selected_goal_id in self.deferred_goal_ids:
            raise ValueError("selected goal cannot also be deferred")


class GoalCommitmentLedger:
    """Append-only commitment history with one winning ambition per NPC and tick."""

    def __init__(self, entries: tuple[GoalCommitment, ...] = ()) -> None:
        self._entries: dict[str, GoalCommitment] = {}
        self._tick_index: dict[tuple[str, int], str] = {}
        self.record_many(entries)

    def record(self, item: GoalCommitment) -> GoalCommitment:
        if not isinstance(item, GoalCommitment):
            raise TypeError("item must be GoalCommitment")
        previous = self._entries.get(item.commitment_id)
        if previous is not None:
            if previous != item:
                raise ValueError("commitment ID reused with conflicting content")
            return previous
        key = (item.owner_id, item.tick)
        if key in self._tick_index:
            raise ValueError("an NPC already has a commitment for this tick")
        self._entries[item.commitment_id] = item
        self._tick_index[key] = item.commitment_id
        return item

    def record_many(self, items) -> tuple[GoalCommitment, ...]:
        batch = tuple(items)
        if any(not isinstance(item, GoalCommitment) for item in batch):
            raise TypeError("items must contain GoalCommitment values")
        if len({item.commitment_id for item in batch}) != len(batch):
            raise ValueError("commitment IDs must be unique within a batch")
        trial = GoalCommitmentLedger()
        for item in sorted((*self.entries(), *batch), key=lambda x: (x.tick, x.owner_id, x.commitment_id)):
            trial.record(item)
        self._entries, self._tick_index = trial._entries, trial._tick_index
        return tuple(sorted(batch, key=lambda x: (x.tick, x.owner_id, x.commitment_id)))

    def get(self, commitment_id: str) -> GoalCommitment | None:
        return self._entries.get(commitment_id)

    def for_owner(self, owner_id: str) -> tuple[GoalCommitment, ...]:
        return tuple(sorted((x for x in self._entries.values() if x.owner_id == owner_id),
                            key=lambda x: (x.tick, x.commitment_id)))

    def entries(self) -> tuple[GoalCommitment, ...]:
        return tuple(sorted(self._entries.values(),
                            key=lambda x: (x.tick, x.owner_id, x.commitment_id)))


class GoalCommitmentAdapter:
    """Explicitly commit to one assessed goal without mutating competing goals."""

    @staticmethod
    def commit(
        assessment: GoalArbitrationAssessment,
        goals: GoalBook,
        ledger: GoalCommitmentLedger,
        *,
        rationale: str,
    ) -> GoalCommitment:
        if not isinstance(assessment, GoalArbitrationAssessment):
            raise TypeError("assessment must be GoalArbitrationAssessment")
        if not isinstance(goals, GoalBook) or not isinstance(ledger, GoalCommitmentLedger):
            raise TypeError("goals and ledger must be GoalBook and GoalCommitmentLedger")
        if not isinstance(rationale, str) or not rationale.strip():
            raise ValueError("rationale must be non-empty")
        if assessment.selected_goal_id is None:
            raise ValueError("no resource-feasible actionable goal can be committed")
        commitment_id = hashlib.sha256(
            f"{assessment.assessment_id}:commit".encode("utf-8")
        ).hexdigest()
        prior = ledger.get(commitment_id)
        if prior is not None:
            return prior
        current = tuple(item for item in goals.snapshot() if item[1] == assessment.owner_id)
        if current != assessment.goal_snapshot:
            raise ValueError("arbitration assessment is stale: the NPC's goal state changed")
        goal = goals.goals.get(assessment.selected_goal_id)
        if goal is None or goal.owner_id != assessment.owner_id or goal.status != GoalStatus.ACTIVE:
            raise ValueError("selected goal is no longer active for this NPC")
        if not goals.evaluate(goal.goal_id, assessment.tick).actionable:
            raise ValueError("selected goal is no longer actionable")
        selected = assessment.selected
        if selected is None or not selected.feasible:
            raise ValueError("selected goal is not feasible")
        item = GoalCommitment(
            commitment_id, assessment.assessment_id, assessment.owner_id,
            assessment.tick, goal.goal_id, assessment.deferred_goal_ids,
            selected.score, rationale.strip(),
        )
        return ledger.record(item)
