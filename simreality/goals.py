"""Deterministic NPC goal tracking and bounded priority selection.

This module is engine-independent. It models intentions separately from daily
activities: goals can depend on other goals, make progress, become obsolete, or
fail. It deliberately does not invent actions or use global randomness; callers
supply world facts and translate a selected goal into concrete behavior.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math


class GoalStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    ABANDONED = "abandoned"
    BLOCKED = "blocked"


_TERMINAL_STATUSES = {
    GoalStatus.COMPLETED,
    GoalStatus.FAILED,
    GoalStatus.ABANDONED,
}


@dataclass
class NPCGoal:
    goal_id: str
    owner_id: str
    category: str
    priority: float
    created_tick: int = 0
    review_tick: int = 0
    deadline_tick: int | None = None
    progress: float = 0.0
    confidence: float = 0.5
    dependencies: tuple[str, ...] = ()
    related_entities: tuple[str, ...] = ()
    status: GoalStatus = GoalStatus.ACTIVE
    metadata: dict[str, str] = field(default_factory=dict)

    def validate(self) -> None:
        if not self.goal_id or not self.owner_id or not self.category:
            raise ValueError("goal_id, owner_id, and category must be non-empty")
        if not math.isfinite(self.priority) or self.priority < 0:
            raise ValueError("priority must be finite and non-negative")
        if self.created_tick < 0 or self.review_tick < 0:
            raise ValueError("goal ticks must be non-negative")
        if self.deadline_tick is not None and self.deadline_tick < self.created_tick:
            raise ValueError("deadline_tick cannot precede created_tick")
        if not math.isfinite(self.progress) or not 0.0 <= self.progress <= 1.0:
            raise ValueError("progress must be finite and between 0 and 1")
        if not math.isfinite(self.confidence) or not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be finite and between 0 and 1")
        if self.goal_id in self.dependencies:
            raise ValueError("a goal cannot depend on itself")
        if len(set(self.dependencies)) != len(self.dependencies):
            raise ValueError("goal dependencies must be unique")


@dataclass(frozen=True)
class GoalEvaluation:
    goal_id: str
    actionable: bool
    score: float
    reason: str


class GoalBook:
    """Own goals for one or more NPCs and choose goals deterministically."""

    def __init__(self) -> None:
        self.goals: dict[str, NPCGoal] = {}

    def add(self, goal: NPCGoal) -> None:
        goal.validate()
        if goal.goal_id in self.goals:
            raise ValueError(f"duplicate goal id: {goal.goal_id}")
        self.goals[goal.goal_id] = goal
        try:
            self._validate_dependency_graph()
        except Exception:
            del self.goals[goal.goal_id]
            raise

    def _validate_dependency_graph(self) -> None:
        for goal in self.goals.values():
            missing = [dep for dep in goal.dependencies if dep not in self.goals]
            if missing:
                raise ValueError(f"unknown goal dependency for {goal.goal_id}: {missing[0]}")
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(goal_id: str) -> None:
            if goal_id in visiting:
                raise ValueError("goal dependency cycle detected")
            if goal_id in visited:
                return
            visiting.add(goal_id)
            for dependency in self.goals[goal_id].dependencies:
                visit(dependency)
            visiting.remove(goal_id)
            visited.add(goal_id)

        for goal_id in sorted(self.goals):
            visit(goal_id)

    def update_progress(self, goal_id: str, progress: float, *, confidence: float | None = None) -> None:
        goal = self.goals[goal_id]
        if not math.isfinite(progress) or not 0.0 <= progress <= 1.0:
            raise ValueError("progress must be finite and between 0 and 1")
        if confidence is not None and (
            not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0
        ):
            raise ValueError("confidence must be finite and between 0 and 1")
        if goal.status in _TERMINAL_STATUSES or goal.status == GoalStatus.BLOCKED:
            raise ValueError("cannot update a terminal or blocked goal")
        # Progress may fall when an NPC loses resources or circumstances worsen.
        goal.progress = progress
        if confidence is not None:
            goal.confidence = confidence
        if progress >= 1.0:
            goal.status = GoalStatus.COMPLETED

    def set_status(self, goal_id: str, status: GoalStatus) -> None:
        goal = self.goals[goal_id]
        if goal.status in _TERMINAL_STATUSES:
            raise ValueError("terminal goal status cannot be changed")
        if status == GoalStatus.BLOCKED:
            raise ValueError("blocked status is derived from dependencies")
        goal.status = status
        if status == GoalStatus.COMPLETED:
            goal.progress = 1.0

    def evaluate(self, goal_id: str, current_tick: int) -> GoalEvaluation:
        if current_tick < 0:
            raise ValueError("current_tick must be non-negative")
        goal = self.goals[goal_id]
        if goal.status != GoalStatus.ACTIVE:
            return GoalEvaluation(goal_id, False, 0.0, f"goal is {goal.status.value}")
        dependencies = [self.goals[dep] for dep in goal.dependencies]
        failed = [dep for dep in dependencies
                  if dep.status in {GoalStatus.FAILED, GoalStatus.ABANDONED, GoalStatus.BLOCKED}]
        if failed:
            return GoalEvaluation(goal_id, False, 0.0, "a prerequisite can no longer be completed")
        if any(dep.status != GoalStatus.COMPLETED for dep in dependencies):
            return GoalEvaluation(goal_id, False, 0.0, "waiting for prerequisites")

        urgency = 1.0
        if goal.deadline_tick is not None:
            remaining = max(0, goal.deadline_tick - current_tick)
            horizon = max(1, goal.deadline_tick - goal.created_tick)
            urgency += min(1.0, max(0.0, 1.0 - remaining / horizon))
        # Confidence affects prioritization, not whether a goal is considered real.
        # Incomplete goals retain value; progress reduces urgency only mildly so
        # nearly finished goals do not always eclipse more important obligations.
        score = goal.priority * (0.5 + 0.5 * goal.confidence) * urgency
        score *= 1.0 - 0.25 * goal.progress
        return GoalEvaluation(goal_id, True, score, "prerequisites satisfied")

    def ranked(self, owner_id: str, current_tick: int) -> tuple[NPCGoal, ...]:
        """Return actionable goals in deterministic priority order."""
        candidates: list[tuple[float, str, NPCGoal]] = []
        for goal in self.goals.values():
            if goal.owner_id != owner_id:
                continue
            result = self.evaluate(goal.goal_id, current_tick)
            if result.actionable:
                candidates.append((-result.score, goal.goal_id, goal))
        candidates.sort(key=lambda item: (item[0], item[1]))
        return tuple(item[2] for item in candidates)

    def choose(self, owner_id: str, current_tick: int) -> NPCGoal | None:
        """Return the highest-scoring actionable goal with a stable tie-break."""
        ranked = self.ranked(owner_id, current_tick)
        return ranked[0] if ranked else None

    def snapshot(self) -> tuple[tuple[object, ...], ...]:
        """Return a stable, immutable representation suitable for save/replay checks."""
        return tuple(
            (g.goal_id, g.owner_id, g.category, g.priority, g.created_tick,
             g.review_tick, g.deadline_tick, g.progress, g.confidence,
             tuple(sorted(g.dependencies)), tuple(sorted(g.related_entities)),
             g.status.value, tuple(sorted(g.metadata.items())))
            for g in sorted(self.goals.values(), key=lambda item: item.goal_id)
        )
