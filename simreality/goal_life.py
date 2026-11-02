"""Goal-aware daily routine proposals with explicit life constraints.

This adapter connects long-term NPC intentions to recurring daily activities.
It is deliberately advisory: it proposes priority adjustments but never edits
routines, executes actions, spends resources, or changes goal progress.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable

from .goals import GoalBook
from .routines import RoutineBook, RoutineBlock


@dataclass(frozen=True)
class GoalLifeContext:
    owner_id: str
    current_tick: int
    available_minutes: int
    available_resources: float
    stress: float = 0.0
    obligation_load: float = 0.0
    social_support: float = 0.0
    recent_setbacks: float = 0.0

    def __post_init__(self) -> None:
        if not isinstance(self.owner_id, str) or not self.owner_id.strip():
            raise ValueError("owner_id must be a non-empty string")
        if isinstance(self.current_tick, bool) or not isinstance(self.current_tick, int) or self.current_tick < 0:
            raise ValueError("current_tick must be a non-negative integer")
        if isinstance(self.available_minutes, bool) or not isinstance(self.available_minutes, int) or self.available_minutes < 0:
            raise ValueError("available_minutes must be a non-negative integer")
        if isinstance(self.available_resources, bool) or not isinstance(self.available_resources, (int, float)) or not math.isfinite(self.available_resources) or self.available_resources < 0:
            raise ValueError("available_resources must be finite and non-negative")
        for name in ("stress", "obligation_load", "social_support", "recent_setbacks"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be finite and between 0 and 1")


@dataclass(frozen=True)
class GoalRoutinePolicy:
    policy_id: str
    goal_category: str
    routine_activity: str
    priority_bonus: float = 0.25
    time_cost_minutes: int = 0
    resource_cost: float = 0.0
    minimum_confidence: float = 0.0

    def __post_init__(self) -> None:
        for name in ("policy_id", "goal_category", "routine_activity"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if isinstance(self.priority_bonus, bool) or not isinstance(self.priority_bonus, (int, float)) or not math.isfinite(self.priority_bonus) or not 0.0 <= self.priority_bonus <= 1.0:
            raise ValueError("priority_bonus must be finite and between 0 and 1")
        if isinstance(self.time_cost_minutes, bool) or not isinstance(self.time_cost_minutes, int) or self.time_cost_minutes < 0:
            raise ValueError("time_cost_minutes must be a non-negative integer")
        if isinstance(self.resource_cost, bool) or not isinstance(self.resource_cost, (int, float)) or not math.isfinite(self.resource_cost) or self.resource_cost < 0:
            raise ValueError("resource_cost must be finite and non-negative")
        if isinstance(self.minimum_confidence, bool) or not isinstance(self.minimum_confidence, (int, float)) or not math.isfinite(self.minimum_confidence) or not 0.0 <= self.minimum_confidence <= 1.0:
            raise ValueError("minimum_confidence must be finite and between 0 and 1")


@dataclass(frozen=True)
class GoalRoutineProposal:
    owner_id: str
    goal_id: str
    routine_id: str
    policy_id: str
    activity: str
    accepted: bool
    baseline_priority: float
    proposed_priority: float
    goal_score: float
    life_capacity: float
    reason: str


@dataclass(frozen=True)
class GoalLifeAssessment:
    owner_id: str
    current_tick: int
    remaining_minutes: int
    remaining_resources: float
    proposals: tuple[GoalRoutineProposal, ...]


class GoalLifeAdapter:
    """Turn ranked intentions into bounded, resource-aware routine priorities."""

    def __init__(self, goals: GoalBook, routines: RoutineBook,
                 policies: Iterable[GoalRoutinePolicy]) -> None:
        if not isinstance(goals, GoalBook):
            raise TypeError("goals must be a GoalBook")
        if not isinstance(routines, RoutineBook):
            raise TypeError("routines must be a RoutineBook")
        items = tuple(policies)
        if any(not isinstance(item, GoalRoutinePolicy) for item in items):
            raise TypeError("policies must contain GoalRoutinePolicy values")
        if len({item.policy_id for item in items}) != len(items):
            raise ValueError("policy IDs must be unique")
        self.goals = goals
        self.routines = routines
        self.policies = tuple(sorted(items, key=lambda item: item.policy_id))

    @staticmethod
    def _life_capacity(context: GoalLifeContext) -> float:
        # Support helps people absorb pressure; stress, obligations and setbacks
        # make it harder to devote scarce time and attention to ambitions.
        value = (1.0 - 0.25 * context.stress
                 - 0.35 * context.obligation_load
                 + 0.15 * context.social_support
                 - 0.25 * context.recent_setbacks)
        return min(1.0, max(0.0, value))

    def assess(self, context: GoalLifeContext) -> GoalLifeAssessment:
        if not isinstance(context, GoalLifeContext):
            raise TypeError("context must be a GoalLifeContext")

        ranked = self.goals.ranked(context.owner_id, context.current_tick)
        goal_scores = {goal.goal_id: self.goals.evaluate(
            goal.goal_id, context.current_tick
        ).score for goal in ranked}
        candidates = []
        blocks = self.routines.snapshot()
        for goal in ranked:
            for policy in self.policies:
                if policy.goal_category != goal.category:
                    continue
                if goal.confidence < policy.minimum_confidence:
                    continue
                for block in blocks:
                    if block.owner_id == context.owner_id and block.activity == policy.routine_activity:
                        candidates.append(( -goal_scores[goal.goal_id], goal.goal_id,
                                            block.routine_id, policy.policy_id,
                                            goal, block, policy))

        candidates.sort(key=lambda item: item[:4])
        remaining_minutes = context.available_minutes
        remaining_resources = float(context.available_resources)
        capacity = self._life_capacity(context)
        proposals = []
        for _, _, _, _, goal, block, policy in candidates:
            enough_time = policy.time_cost_minutes <= remaining_minutes
            enough_resources = policy.resource_cost <= remaining_resources
            accepted = enough_time and enough_resources and capacity > 0.0
            if not enough_time:
                reason = "insufficient discretionary time"
            elif not enough_resources:
                reason = "insufficient available resources"
            elif capacity <= 0.0:
                reason = "life pressure leaves no capacity for this pursuit"
            else:
                reason = "goal-aligned routine fits the available life budget"
                remaining_minutes -= policy.time_cost_minutes
                remaining_resources -= policy.resource_cost

            score = goal_scores[goal.goal_id]
            normalized_goal_score = score / (1.0 + score)
            boost = (policy.priority_bonus * normalized_goal_score * capacity
                     if accepted else 0.0)
            proposed = min(1.0, block.priority + boost)
            proposals.append(GoalRoutineProposal(
                context.owner_id, goal.goal_id, block.routine_id, policy.policy_id,
                block.activity, accepted, block.priority, proposed, score,
                capacity, reason,
            ))

        proposals.sort(key=lambda item: (-item.proposed_priority,
                                         item.routine_id, item.goal_id,
                                         item.policy_id))
        return GoalLifeAssessment(context.owner_id, context.current_tick,
                                  remaining_minutes, remaining_resources,
                                  tuple(proposals))
