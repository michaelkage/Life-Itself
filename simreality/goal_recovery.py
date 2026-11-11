"""Read-only reassessment of abandoned intentions after needs or circumstances recover."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Mapping

from .goals import GoalBook, GoalStatus
from .npc_goal_emergence import GoalLifecycleLedger


@dataclass(frozen=True)
class GoalRecoveryRule:
    rule_id: str
    goal_category: str
    need_key: str | None = None
    maximum_need_level: float = 0.35
    required_facts: tuple[str, ...] = ()
    forbidden_facts: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("rule_id", "goal_category"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if self.need_key is not None and (not isinstance(self.need_key, str) or not self.need_key.strip()):
            raise ValueError("need_key must be non-empty when supplied")
        if isinstance(self.maximum_need_level, bool) or not isinstance(self.maximum_need_level, (int, float)) or not math.isfinite(self.maximum_need_level) or not 0 <= self.maximum_need_level <= 1:
            raise ValueError("maximum_need_level must be finite and in [0, 1]")
        for name in ("required_facts", "forbidden_facts"):
            values = getattr(self, name)
            if not isinstance(values, tuple) or any(not isinstance(x, str) or not x.strip() for x in values):
                raise ValueError(f"{name} must be a tuple of non-empty strings")
            if len(values) != len(set(values)):
                raise ValueError(f"{name} must contain unique values")
        if not (self.need_key is not None or self.required_facts or self.forbidden_facts):
            raise ValueError("a recovery rule must define at least one recovery condition")
        if set(self.required_facts) & set(self.forbidden_facts):
            raise ValueError("a fact cannot be both required and forbidden")


@dataclass(frozen=True)
class GoalRecoveryProposal:
    proposal_id: str
    rule_id: str
    goal_id: str
    owner_id: str
    sampled_tick: int
    current_status: GoalStatus
    current_category: str
    current_priority: float
    current_confidence: float
    matched_facts: tuple[str, ...]
    context_signature: str
    rationale: str


class GoalRecoveryEvaluator:
    """Propose, but never silently perform, recovery of abandoned intentions."""

    @staticmethod
    def assess(
        goals: GoalBook,
        owner_id: str,
        current_tick: int,
        *,
        rules: tuple[GoalRecoveryRule, ...],
        need_levels: Mapping[str, float] | None = None,
        available_facts: frozenset[str] = frozenset(),
    ) -> tuple[GoalRecoveryProposal, ...]:
        if not isinstance(goals, GoalBook):
            raise TypeError("goals must be GoalBook")
        if not isinstance(owner_id, str) or not owner_id.strip():
            raise ValueError("owner_id must be non-empty")
        if isinstance(current_tick, bool) or not isinstance(current_tick, int) or current_tick < 0:
            raise ValueError("current_tick must be a non-negative integer")
        if not isinstance(rules, tuple) or any(not isinstance(rule, GoalRecoveryRule) for rule in rules):
            raise TypeError("rules must be a tuple of GoalRecoveryRule values")
        if len({rule.rule_id for rule in rules}) != len(rules):
            raise ValueError("recovery rule IDs must be unique")
        if not isinstance(available_facts, frozenset) or any(not isinstance(x, str) or not x.strip() for x in available_facts):
            raise TypeError("available_facts must be a frozenset of non-empty strings")
        needs = {} if need_levels is None else dict(need_levels)
        for key, value in needs.items():
            if not isinstance(key, str) or not key.strip() or isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError("need levels must be named finite values in [0, 1]")

        proposals = []
        for goal in sorted(goals.goals.values(), key=lambda item: item.goal_id):
            if goal.owner_id != owner_id or goal.status not in {GoalStatus.ABANDONED, GoalStatus.BLOCKED}:
                continue
            if current_tick < goal.review_tick:
                continue
            for rule in sorted(rules, key=lambda item: item.rule_id):
                if rule.goal_category != goal.category:
                    continue
                if rule.need_key is not None:
                    if rule.need_key not in needs or needs[rule.need_key] > rule.maximum_need_level:
                        continue
                if not set(rule.required_facts).issubset(available_facts):
                    continue
                if set(rule.forbidden_facts) & available_facts:
                    continue
                matched = tuple(sorted(
                    set(rule.required_facts)
                    | {"fact_absent:" + fact for fact in rule.forbidden_facts}
                ))
                if rule.need_key is not None:
                    matched += ("need_recovered:" + rule.need_key,)
                seed = "|".join((
                    owner_id, goal.goal_id, rule.rule_id, str(current_tick),
                    goal.status.value, goal.category, repr(goal.priority),
                    repr(goal.confidence), ",".join(matched),
                ))
                digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:20]
                proposals.append(GoalRecoveryProposal(
                    "goal-recovery-" + digest, rule.rule_id, goal.goal_id,
                    owner_id, current_tick, goal.status, goal.category,
                    goal.priority, goal.confidence, matched,
                    hashlib.sha256(json.dumps(
                        {"needs": sorted(needs.items()), "facts": sorted(available_facts)},
                        sort_keys=True, separators=(",", ":"), allow_nan=False,
                    ).encode("utf-8")).hexdigest(),
                    "Recovery rule " + rule.rule_id + " matched " + ", ".join(matched),
                ))
        return tuple(sorted(proposals, key=lambda item: (
            item.goal_id, item.rule_id, item.proposal_id
        )))


class GoalRecoveryAdapter:
    """Explicitly reopen a still-matching recovery proposal with lifecycle audit."""

    @staticmethod
    def apply(
        proposal: GoalRecoveryProposal,
        goals: GoalBook,
        lifecycle: GoalLifecycleLedger,
        *,
        need_levels: Mapping[str, float],
        available_facts: frozenset[str],
        reason: str | None = None,
    ):
        if not isinstance(proposal, GoalRecoveryProposal):
            raise TypeError("proposal must be GoalRecoveryProposal")
        if not isinstance(goals, GoalBook):
            raise TypeError("goals must be GoalBook")
        if not isinstance(lifecycle, GoalLifecycleLedger):
            raise TypeError("lifecycle must be GoalLifecycleLedger")
        if not isinstance(available_facts, frozenset) or any(
            not isinstance(value, str) or not value.strip() for value in available_facts
        ):
            raise TypeError("available_facts must be a frozenset of non-empty strings")
        needs = dict(need_levels)
        if any(not isinstance(key, str) or not key.strip() or isinstance(value, bool)
               or not isinstance(value, (int, float)) or not math.isfinite(value)
               or not 0 <= value <= 1 for key, value in needs.items()):
            raise ValueError("need levels must be named finite values in [0, 1]")
        signature = hashlib.sha256(json.dumps(
            {"needs": sorted(needs.items()), "facts": sorted(available_facts)},
            sort_keys=True, separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")).hexdigest()
        if signature != proposal.context_signature:
            raise ValueError("goal recovery proposal is stale: circumstances changed")
        goal = goals.goals.get(proposal.goal_id)
        if goal is None or goal.owner_id != proposal.owner_id:
            raise ValueError("recovery proposal references an unknown goal or owner")
        if (goal.status != proposal.current_status
                or goal.status not in {GoalStatus.ABANDONED, GoalStatus.BLOCKED}
                or goal.category != proposal.current_category
                or goal.priority != proposal.current_priority
                or goal.confidence != proposal.current_confidence
                or proposal.sampled_tick < goal.review_tick):
            raise ValueError("goal recovery proposal is stale")
        return lifecycle.transition(
            goals, goal.goal_id, GoalStatus.ACTIVE, proposal.sampled_tick,
            reason or proposal.rationale,
        )
