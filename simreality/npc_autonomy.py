"""Connect deterministic goal selection to symbolic planning without side effects.

The decision cycle selects an actionable goal, resolves its explicitly supplied
desired facts, and asks the planner for a bounded action sequence. It never
executes actions, changes world facts, or silently guesses a goal's meaning.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .goals import GoalBook
from .planning import DeterministicPlanner, PlanResult


@dataclass(frozen=True)
class NPCDecision:
    """One inspectable NPC decision proposal; it is not an executed action."""

    owner_id: str
    tick: int
    goal_id: str | None
    goal_category: str | None
    plan: PlanResult | None
    reason: str

    @property
    def actionable(self) -> bool:
        return self.goal_id is not None and self.plan is not None and self.plan.success


class NPCDecisionCycle:
    """Join a goal book and planner into a deterministic, read-only decision step."""

    def __init__(self, goals: GoalBook, planner: DeterministicPlanner) -> None:
        self.goals = goals
        self.planner = planner

    def decide(
        self,
        owner_id: str,
        current_tick: int,
        world_facts: frozenset[str] | set[str] | tuple[str, ...],
        goal_facts: Mapping[str, frozenset[str] | set[str] | tuple[str, ...]],
        *,
        max_expansions: int = 10_000,
    ) -> NPCDecision:
        """Propose a plan for the best actionable goal, leaving state unchanged.

        ``goal_facts`` explicitly maps goal IDs to their desired world facts. If
        the selected goal has no mapping, the cycle reports that configuration
        gap instead of guessing from the goal category or metadata.
        """
        if not owner_id or not owner_id.strip():
            raise ValueError("owner_id must be non-empty")
        if current_tick < 0:
            raise ValueError("current_tick must be non-negative")

        goal = self.goals.choose(owner_id, current_tick)
        if goal is None:
            return NPCDecision(owner_id, current_tick, None, None, None,
                               "no actionable goal")

        if goal.goal_id not in goal_facts:
            return NPCDecision(owner_id, current_tick, goal.goal_id, goal.category,
                               None, "selected goal has no desired-facts mapping")

        result = self.planner.plan(
            world_facts, goal_facts[goal.goal_id], max_expansions=max_expansions
        )
        reason = result.reason if result.success else f"planning failed: {result.reason}"
        return NPCDecision(owner_id, current_tick, goal.goal_id, goal.category,
                           result, reason)
